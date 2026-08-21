"""WP7 Phase 4 shared reader (2026-08-14) regression tests.

Replaces tests/test_wp7_phase4_hybrid.py in full. That file tested the
v0.46.0 "hybrid" pattern (legacy PHASE_SETTING_FIELDS as an active source,
plus additive dynamic discovery) - Charlie's Architecture Clarification and
Direction to JC rejected that hybrid outright: "The v0.46.0 hybrid reader
keeps the five fixed ProductionPhase fields as an active source ... That
structure conflicts with the frozen Phase 4 source-of-truth rule and cannot
be the Phase 4 end state." eligible_phase_setting_fields()/
run_settings_dataframe()/rank_setting_correlations()/rank_setting_optimization()
were reverted to pure pre-hybrid legacy behavior (already covered by
pre-existing tests elsewhere) and now carry zero active-reader authority.

This file instead tests the new shared reader Charlie's execution
instruction requires: production_run_process_parameters() (single-run) and
production_run_parameter_dataframe() (multi-run), plus
dynamic_process_setting_field_key(). These are the sole intended source of
process-parameter facts for every Phase 4 consumer once cut over - reading
ProductionPhase or PHASE_SETTING_FIELDS/LABELS/PHASE1_RIGID_INELIGIBLE_SETTINGS
is out of scope for any of them per the frozen Phase 4 architecture.

Covers the required Phase 4 test gates that apply at the shared-reader
level today (2026-08-14):
  - empty-catalogue state (no approved applicability -> honest [] / {},
    never a legacy ProductionPhase fallback)
  - reader source isolation (legacy ProductionPhase columns never leak into
    the new reader's output, even when populated with conflicting values)
  - Machine > Method > Global applicability precedence (two runs on
    different Machines under the same Production Method correctly resolve
    to different eligible definitions/values)
  - NULL vs zero preservation (a real 0 stays 0, not None; a genuinely
    unset value stays None)
  - Planned vs Actual: Actual is the production fact, Planned is separate
    context, Planned never substitutes for a missing Actual
  - UOM control (unit_symbol always comes from the definition's own
    controlled unit relationship, never a caller-supplied unit)
  - category/eligibility metadata passthrough (parameter_category,
    controllable, analytics_eligible are all exposed accurately so
    downstream consumers - not yet cut over - can apply their own
    inclusion/exclusion rules)
  - multi-run dataframe shape (values_by_run/definitions_by_field contract)

The remaining gates (output source via ProductionOutputSummary, PI3
context, report row generation, full end-to-end regression with zero
Phase 4-relevant skips) are consumer-specific and will be added alongside
each consumer's own cutover task (#972-#980), not here - this file only
covers the shared reader foundation itself (task #970).

MANDATORY TEMPLATE: tests/test_wp7_phase1_method_aware_schema.py
(AUTH_DISABLED/sqlite:// boilerplate, _reset_schema(), seeded_grade_chain
-> seeded_run fixture chain).

Usage: python -m pytest tests/test_wp7_phase4_shared_reader.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import access_control
import analytics
import db
import tenant_scope


def _clear_relevant_caches():
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()
    analytics.run_settings_dataframe.clear()
    analytics.property_results_dataframe.clear()


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    _clear_relevant_caches()


# ---------------------------------------------------------------------------
# Fixtures - same dependency chain as test_wp7_phase1_method_aware_schema.py
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_grade_chain():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P4SR Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P4SR Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-WP7P4SR-{u}", name=f"WP7P4SR Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"WP7P4SR Machine {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()

    machine_2 = db.Machine(plant_id=plant.id, name=f"WP7P4SR Machine2 {u}", production_method_id=method.id, active=True)
    session.add(machine_2); session.flush()

    family = db.PUMaterialFamily(plant_id=plant.id, name=f"WP7P4SR Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"WP7P4SR Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine, machine_2]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P4SR-{u}", symbol="bar", name="Bar")
    session.add(unit); session.flush()
    other_unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P4SR-OTHER-{u}", symbol="kPa", name="Kilopascal")
    session.add(other_unit); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "method_id": method.id,
        "machine_id": machine.id, "machine2_id": machine_2.id,
        "family_id": family.id, "grade_id": grade.id,
        "recipe_version_id": recipe.id, "unit_id": unit.id, "other_unit_id": other_unit.id,
    }
    session.close()
    return ids


def _make_run(ids, machine_id=None, batch_suffix=None):
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
        recipe_version_id=ids["recipe_version_id"], run_date=dt.date(2026, 8, 1),
        batch_reference=f"B-WP7P4SR-{batch_suffix or uuid.uuid4().hex[:8]}",
        machine_id=machine_id if machine_id is not None else ids["machine_id"],
        production_method_id=ids["method_id"], operator_or_team_reference="Shift A",
    )
    session.add(run); session.commit()
    run_id = run.id
    session.close()
    return run_id


@pytest.fixture()
def seeded_run(seeded_grade_chain):
    ids = seeded_grade_chain
    run_id = _make_run(ids)
    out = dict(ids)
    out["run_id"] = run_id
    return out


def _seed_definition(ids, controllable=True, analytics_eligible=True,
                      parameter_category="Process Setting", data_type="Float",
                      name="Fill pressure", unit_id=None,
                      production_method_id="__default__", machine_id=None):
    """Seeds one ProcessSettingDefinition + one ProcessSettingApplicability
    row. production_method_id defaults to the fixture's method (pass None
    explicitly for a Global-scope row); machine_id defaults to None
    (Method/Global scope) - pass a machine id for a Machine-scope row."""
    session = db.get_session()
    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P4SR-{uuid.uuid4().hex[:6]}", name=name,
        data_type=data_type, unit_id=unit_id or ids["unit_id"], parameter_category=parameter_category,
    )
    session.add(definition); session.flush()
    pm_id = ids["method_id"] if production_method_id == "__default__" else production_method_id
    applicability = db.ProcessSettingApplicability(
        setting_definition_id=definition.id, production_method_id=pm_id, machine_id=machine_id,
        controllable=controllable, analytics_eligible=analytics_eligible,
    )
    session.add(applicability); session.commit()
    definition_id = definition.id
    session.close()
    return definition_id


def _add_value(run_id, definition_id, snapshot_type, numeric_value=None,
                text_value=None, boolean_value=None, source="Machine capture"):
    session = db.get_session()
    session.add(db.ProcessParameterValue(
        setting_definition_id=definition_id, production_run_id=run_id,
        snapshot_type=snapshot_type, numeric_value=numeric_value,
        text_value=text_value, boolean_value=boolean_value, source=source,
    ))
    session.commit()
    session.close()


# ---------------------------------------------------------------------------
# 1. Empty catalogue is a valid, honest empty state - never a legacy
#    ProductionPhase fallback (Charlie's clarification, section 3 item 4)
# ---------------------------------------------------------------------------

def test_empty_catalogue_returns_empty_list(seeded_run):
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert rows == []
    session.close()


def test_empty_catalogue_dataframe_contributes_empty_dict_per_run(seeded_run):
    session = db.get_session()
    values_by_run, definitions_by_field = analytics.production_run_parameter_dataframe(
        session, [seeded_run["run_id"]],
    )
    assert seeded_run["run_id"] in values_by_run
    assert values_by_run[seeded_run["run_id"]] == {}
    assert definitions_by_field == {}
    session.close()


def test_accepts_run_id_int_or_instance_and_none_run_returns_empty(seeded_run):
    session = db.get_session()
    by_id = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    run_obj = session.get(db.ProductionRun, seeded_run["run_id"])
    by_instance = analytics.production_run_process_parameters(session, run_obj)
    assert by_id == by_instance
    # A nonexistent run id must not raise - honest empty state.
    assert analytics.production_run_process_parameters(session, 999999999) == []
    session.close()


# ---------------------------------------------------------------------------
# 2. Reader source isolation - legacy ProductionPhase columns never leak in,
#    even when populated with values that directly conflict with the new
#    model's data for the same run
# ---------------------------------------------------------------------------

def test_legacy_production_phase_values_do_not_leak_into_shared_reader(seeded_run):
    session = db.get_session()
    # Populate the legacy ProductionPhase columns with a conflicting value
    # for a name that collides with the new definition's name below.
    session.add(db.ProductionPhase(
        production_run_id=seeded_run["run_id"], phase_name="Finalized", mixer_rpm=999.0,
    ))
    session.commit()

    definition_id = _seed_definition(seeded_run, name="mixer_rpm", data_type="Float")
    _add_value(seeded_run["run_id"], definition_id, "Actual", numeric_value=42.5)

    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert len(rows) == 1
    assert rows[0]["actual_value"] == 42.5, (
        "the new reader must source strictly from ProcessParameterValue - "
        "the legacy ProductionPhase.mixer_rpm=999.0 value must never surface here"
    )
    session.close()


def test_shared_reader_never_reads_phase_setting_fields_constant(seeded_run):
    """Sanity check that the new reader's keys are never any of the 5
    legacy PHASE_SETTING_FIELDS names - it is fully decoupled from that
    list per the frozen Phase 4 source-of-truth rule."""
    definition_id = _seed_definition(seeded_run, name="conveyor_speed")
    _add_value(seeded_run["run_id"], definition_id, "Actual", numeric_value=5.0)
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert rows[0]["definition_id"] == definition_id
    assert rows[0]["name"] == "conveyor_speed"
    # The row is keyed/identified by definition_id, never by a
    # PHASE_SETTING_FIELDS-style bare attribute name.
    assert "conveyor_speed" not in rows[0]
    session.close()


# ---------------------------------------------------------------------------
# 3. Machine > Method > Global applicability precedence, resolved per-run
# ---------------------------------------------------------------------------

def test_machine_specific_applicability_overrides_method_level(seeded_grade_chain):
    ids = seeded_grade_chain
    run_on_machine_1 = _make_run(ids, machine_id=ids["machine_id"], batch_suffix="m1")
    run_on_machine_2 = _make_run(ids, machine_id=ids["machine2_id"], batch_suffix="m2")

    # Method-level (Global-to-the-method) applicability: controllable=True.
    definition_id = _seed_definition(ids, controllable=True, name="Fill pressure")
    # Machine-specific override for machine_2 only: controllable=False.
    session = db.get_session()
    override = db.ProcessSettingApplicability(
        setting_definition_id=definition_id, production_method_id=ids["method_id"],
        machine_id=ids["machine2_id"], controllable=False, analytics_eligible=True,
    )
    session.add(override); session.commit()
    session.close()

    _add_value(run_on_machine_1, definition_id, "Actual", numeric_value=10.0)
    _add_value(run_on_machine_2, definition_id, "Actual", numeric_value=20.0)

    session = db.get_session()
    rows_m1 = analytics.production_run_process_parameters(session, run_on_machine_1)
    rows_m2 = analytics.production_run_process_parameters(session, run_on_machine_2)
    assert rows_m1[0]["controllable"] is True, "machine_1 run has no machine-level override - Method-level wins"
    assert rows_m2[0]["controllable"] is False, "machine_2 run has a machine-specific override - Machine wins"
    assert rows_m1[0]["actual_value"] == 10.0
    assert rows_m2[0]["actual_value"] == 20.0
    session.close()


def test_method_level_overrides_global(seeded_grade_chain):
    ids = seeded_grade_chain
    run_id = _make_run(ids)
    # Global row (production_method_id=None): controllable=False.
    global_definition_id = _seed_definition(ids, controllable=False, production_method_id=None, name="Global pressure")
    # Method-specific row for the SAME definition: controllable=True.
    session = db.get_session()
    method_row = db.ProcessSettingApplicability(
        setting_definition_id=global_definition_id, production_method_id=ids["method_id"],
        machine_id=None, controllable=True, analytics_eligible=True,
    )
    session.add(method_row); session.commit()
    session.close()

    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, run_id)
    assert len(rows) == 1, "one definition, one winning applicability row - not two"
    assert rows[0]["controllable"] is True, "Method-specific applicability must win over the Global row"
    session.close()


def test_different_machines_same_method_can_see_different_eligible_definitions(seeded_grade_chain):
    ids = seeded_grade_chain
    run_on_machine_1 = _make_run(ids, machine_id=ids["machine_id"], batch_suffix="dm1")
    run_on_machine_2 = _make_run(ids, machine_id=ids["machine2_id"], batch_suffix="dm2")

    # A definition eligible ONLY on machine_2 (Machine-scoped applicability,
    # no Method/Global row for it at all).
    session = db.get_session()
    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P4SR-{uuid.uuid4().hex[:6]}", name="Machine-2-only setting",
        data_type="Float", unit_id=ids["unit_id"], parameter_category="Process Setting",
    )
    session.add(definition); session.flush()
    applicability = db.ProcessSettingApplicability(
        setting_definition_id=definition.id, production_method_id=ids["method_id"],
        machine_id=ids["machine2_id"], controllable=True, analytics_eligible=True,
    )
    session.add(applicability); session.commit()
    m2_only_definition_id = definition.id
    session.close()

    session = db.get_session()
    values_by_run, definitions_by_field = analytics.production_run_parameter_dataframe(
        session, [run_on_machine_1, run_on_machine_2],
    )
    field_key = analytics.dynamic_process_setting_field_key(m2_only_definition_id)
    assert field_key not in values_by_run[run_on_machine_1], (
        "a Machine-2-scoped-only definition must not appear for a run on machine_1 "
        "(this reader does a genuine per-run resolution, not a Method/Global-only shortcut)"
    )
    assert field_key in values_by_run[run_on_machine_2]
    session.close()


# ---------------------------------------------------------------------------
# 4. NULL vs zero preservation
# ---------------------------------------------------------------------------

def test_actual_numeric_zero_is_preserved_not_treated_as_missing(seeded_run):
    definition_id = _seed_definition(seeded_run, data_type="Float")
    _add_value(seeded_run["run_id"], definition_id, "Actual", numeric_value=0.0)
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert rows[0]["actual_value"] == 0.0
    assert rows[0]["actual_value"] is not None
    session.close()


def test_actual_boolean_false_is_preserved_not_treated_as_missing(seeded_run):
    definition_id = _seed_definition(seeded_run, data_type="Boolean")
    _add_value(seeded_run["run_id"], definition_id, "Actual", boolean_value=False)
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert rows[0]["actual_value"] is False
    session.close()


def test_no_value_row_at_all_stays_none(seeded_run):
    _seed_definition(seeded_run, data_type="Float")
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert rows[0]["actual_value"] is None
    assert rows[0]["planned_value"] is None
    assert rows[0]["actual_source"] is None
    session.close()


# ---------------------------------------------------------------------------
# 5. Planned vs Actual: Actual is the production fact, Planned is separate
#    context and never substitutes for a missing Actual
# ---------------------------------------------------------------------------

def test_missing_actual_is_not_backfilled_from_planned(seeded_run):
    definition_id = _seed_definition(seeded_run, data_type="Float")
    _add_value(seeded_run["run_id"], definition_id, "Planned", numeric_value=17.0, source="Manual entry")
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert rows[0]["planned_value"] == 17.0
    assert rows[0]["actual_value"] is None, (
        "Charlie's clarification: 'Missing Actual remains missing' - Planned "
        "must never substitute for it"
    )
    assert rows[0]["delta"] is None
    session.close()


def test_planned_and_actual_both_present_produce_delta_for_numeric_types(seeded_run):
    definition_id = _seed_definition(seeded_run, data_type="Float")
    _add_value(seeded_run["run_id"], definition_id, "Planned", numeric_value=17.0)
    _add_value(seeded_run["run_id"], definition_id, "Actual", numeric_value=19.5)
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert rows[0]["planned_value"] == 17.0
    assert rows[0]["actual_value"] == 19.5
    assert rows[0]["delta"] == pytest.approx(2.5)
    session.close()


def test_delta_not_computed_for_non_numeric_data_types(seeded_run):
    definition_id = _seed_definition(seeded_run, data_type="String")
    _add_value(seeded_run["run_id"], definition_id, "Planned", text_value="A")
    _add_value(seeded_run["run_id"], definition_id, "Actual", text_value="B")
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert rows[0]["planned_value"] == "A"
    assert rows[0]["actual_value"] == "B"
    assert rows[0]["delta"] is None
    session.close()


def test_multi_run_dataframe_reads_actual_only_never_planned(seeded_run):
    definition_id = _seed_definition(seeded_run, data_type="Float")
    _add_value(seeded_run["run_id"], definition_id, "Planned", numeric_value=100.0)
    # No Actual recorded.
    session = db.get_session()
    values_by_run, _ = analytics.production_run_parameter_dataframe(session, [seeded_run["run_id"]])
    field_key = analytics.dynamic_process_setting_field_key(definition_id)
    assert values_by_run[seeded_run["run_id"]][field_key] is None, (
        "the multi-run dataframe reads Actual only - a Planned-only value must show as missing, not 100.0"
    )
    session.close()


# ---------------------------------------------------------------------------
# 6. UOM control - unit_symbol always comes from the definition's own
#    controlled unit, never a caller-supplied unit
# ---------------------------------------------------------------------------

def test_unit_symbol_comes_from_definition_not_caller(seeded_run):
    definition_id = _seed_definition(seeded_run, unit_id=seeded_run["unit_id"])
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert rows[0]["unit_symbol"] == "bar"
    assert rows[0]["unit_id"] == seeded_run["unit_id"]
    session.close()


def test_unit_symbol_reflects_each_definitions_own_unit_independently(seeded_run):
    d1 = _seed_definition(seeded_run, name="Pressure A", unit_id=seeded_run["unit_id"])
    d2 = _seed_definition(seeded_run, name="Pressure B", unit_id=seeded_run["other_unit_id"])
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    by_id = {r["definition_id"]: r for r in rows}
    assert by_id[d1]["unit_symbol"] == "bar"
    assert by_id[d2]["unit_symbol"] == "kPa"
    session.close()


# ---------------------------------------------------------------------------
# 7. Category / eligibility metadata passthrough (for not-yet-cut-over
#    consumers to apply their own inclusion/exclusion rules against)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", ["Process Setting", "Environment", "Process Observation", "Outcome", "Other"])
def test_parameter_category_is_passed_through_accurately(seeded_run, category):
    definition_id = _seed_definition(seeded_run, parameter_category=category)
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert rows[0]["parameter_category"] == category
    session.close()


@pytest.mark.parametrize("controllable,analytics_eligible", [
    (True, True), (True, False), (False, True), (False, False),
])
def test_controllable_and_analytics_eligible_flags_passed_through_accurately(seeded_run, controllable, analytics_eligible):
    definition_id = _seed_definition(seeded_run, controllable=controllable, analytics_eligible=analytics_eligible)
    session = db.get_session()
    rows = analytics.production_run_process_parameters(session, seeded_run["run_id"])
    assert rows[0]["controllable"] is controllable
    assert rows[0]["analytics_eligible"] is analytics_eligible
    session.close()


# ---------------------------------------------------------------------------
# 8. Multi-run dataframe shape contract
# ---------------------------------------------------------------------------

def test_dataframe_definitions_by_field_is_union_across_runs(seeded_grade_chain):
    ids = seeded_grade_chain
    run_1 = _make_run(ids, batch_suffix="u1")
    run_2 = _make_run(ids, batch_suffix="u2")
    d1 = _seed_definition(ids, name="Only on run 1")
    d2 = _seed_definition(ids, name="On both runs")
    _add_value(run_1, d1, "Actual", numeric_value=1.0)
    _add_value(run_1, d2, "Actual", numeric_value=2.0)
    _add_value(run_2, d2, "Actual", numeric_value=3.0)

    session = db.get_session()
    values_by_run, definitions_by_field = analytics.production_run_parameter_dataframe(session, [run_1, run_2])
    key1 = analytics.dynamic_process_setting_field_key(d1)
    key2 = analytics.dynamic_process_setting_field_key(d2)
    assert set(definitions_by_field.keys()) == {key1, key2}
    assert definitions_by_field[key2]["label"] == "On both runs"
    assert values_by_run[run_1][key1] == 1.0
    assert values_by_run[run_1][key2] == 2.0
    # d1 is Method-level (not Machine-restricted), so it's still eligible
    # for run_2 - it just has no recorded Actual there, so its value is
    # None rather than absent.
    assert values_by_run[run_2][key1] is None
    assert values_by_run[run_2][key2] == 3.0
    session.close()


def test_dynamic_process_setting_field_key_is_id_based_and_namespaced(seeded_run):
    definition_id = _seed_definition(seeded_run)
    key = analytics.dynamic_process_setting_field_key(definition_id)
    assert key == f"ps_{definition_id}"
    assert key.startswith("ps_")
    # WP7 Phase 5 (Legacy Retirement, 2026-08-15): PHASE_SETTING_FIELDS was
    # removed from analytics.py entirely (see the JC Pre-Coding Engineering
    # Challenge Response, Section 4) - the module no longer has that
    # attribute at all, which is itself the strongest form of "never a
    # legacy field name". Assert directly against the 5 names it used to
    # hold, to keep proving the id-based key can never collide with them.
    assert key not in {
        "mixer_rpm", "conveyor_speed", "air_injection_rate",
        "air_pressure_bar", "sidewall_width_mm",
    }
    assert not hasattr(analytics, "PHASE_SETTING_FIELDS")
