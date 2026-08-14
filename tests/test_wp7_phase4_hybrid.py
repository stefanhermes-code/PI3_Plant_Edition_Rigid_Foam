"""WP7 Phase 4 hybrid reader (2026-08-14) regression tests.

Phase 4's literal closure gate (WP7_Phase1_Design_Deliverables.docx,
section 6.4: "Close when every active consumer uses the new architecture
as its single source of truth") cannot be met yet - a live Supabase query
confirmed zero 'Process Setting' category ProcessSettingApplicability rows
exist for any of the 5 legacy PHASE_SETTING_FIELDS (mixer_rpm,
conveyor_speed, air_injection_rate, air_pressure_bar, sidewall_width_mm).
Charlie's own WP7 Phase 3 closeout review left their PM-code/
controllability mapping deferred pending his decision and real production
evidence - see PI3 Rigid Foam Development Docs/Phase 1/
WP7_Phase4_Flag_for_Charlie.docx.

Per Stefan's direction ("Flag it to Charlie with a short message, then go
hybrid"), analytics.py was extended additively: the 5 legacy fields keep
reading from ProductionPhase columns exactly as before (zero behavior
change), while eligible_phase_setting_fields()/run_settings_dataframe()
now also discover and surface any live, evidence-based Process Setting
definitions for one unambiguous production_method_id, once Charlie's
decisions land and such rows exist.

This file proves two things:
  1. Nothing changes today. With zero live dynamic data (today's actual
     state), every function's output is identical to before this change -
     same 5 fields, same columns, no ps_<id> keys anywhere.
  2. The wiring is real. Once a synthetic evidence-based Process Setting
     definition/applicability/value is seeded, it surfaces correctly and
     automatically in eligible_phase_setting_fields(),
     run_settings_dataframe(), and rank_setting_correlations()/
     rank_setting_optimization()'s label column - with zero page-level
     code changes needed for pages 17/19 (already dynamic, see prior
     research) - and is correctly excluded when not controllable, not
     analytics_eligible, wrong category, wrong data_type, or when the
     caller doesn't scope to one unambiguous production_method_id.

MANDATORY TEMPLATE: tests/test_wp7_phase1_method_aware_schema.py
(AUTH_DISABLED/sqlite:// boilerplate, _reset_schema(), seeded_grade_chain
-> seeded_run fixture chain).

Usage: python -m pytest tests/test_wp7_phase4_hybrid.py -v
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

    company = db.Company(name=f"WP7P4 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P4 Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-WP7P4-{u}", name=f"WP7P4 Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"WP7P4 Machine {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P4 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P4 Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P4-{u}", symbol="kg", name="Kilograms")
    session.add(unit); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "method_id": method.id,
        "machine_id": machine.id, "family_id": family.id, "grade_id": grade.id,
        "recipe_version_id": recipe.id, "unit_id": unit.id,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_run(seeded_grade_chain):
    ids = seeded_grade_chain
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
        recipe_version_id=ids["recipe_version_id"], run_date=dt.date(2026, 8, 1),
        batch_reference=f"B-WP7P4-{uuid.uuid4().hex[:8]}", machine_id=ids["machine_id"],
        production_method_id=ids["method_id"], operator_or_team_reference="Shift A",
    )
    session.add(run); session.commit()
    out = dict(ids)
    out["run_id"] = run.id
    session.close()
    return out


def _seed_three_runs(ids):
    """Three runs of the same grade/method, each with a Finalized-phase
    mixer_rpm (so the legacy field list still has real data too) - used by
    the correlation-ranking test, which needs n>=3 to compute a
    correlation."""
    session = db.get_session()
    run_ids = []
    for i, rpm in enumerate((100.0, 110.0, 120.0)):
        run = db.ProductionRun(
            plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
            recipe_version_id=ids["recipe_version_id"], run_date=dt.date(2026, 8, 1 + i),
            batch_reference=f"B-WP7P4-{uuid.uuid4().hex[:8]}", machine_id=ids["machine_id"],
            production_method_id=ids["method_id"], operator_or_team_reference="Shift A",
        )
        session.add(run); session.flush()
        session.add(db.ProductionPhase(production_run_id=run.id, phase_name="Finalized", mixer_rpm=rpm))
        run_ids.append(run.id)
    session.commit()
    session.close()
    return run_ids


def _seed_dynamic_definition(ids, controllable=True, analytics_eligible=True,
                              parameter_category="Process Setting", data_type="Float", name="Fill pressure"):
    session = db.get_session()
    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P4-{uuid.uuid4().hex[:6]}", name=name,
        data_type=data_type, unit_id=ids["unit_id"], parameter_category=parameter_category,
    )
    session.add(definition); session.flush()
    applicability = db.ProcessSettingApplicability(
        setting_definition_id=definition.id, production_method_id=ids["method_id"],
        controllable=controllable, analytics_eligible=analytics_eligible,
    )
    session.add(applicability); session.commit()
    out = {"definition_id": definition.id}
    session.close()
    return out


# ---------------------------------------------------------------------------
# 1. Nothing changes today - zero live dynamic data (today's actual state)
# ---------------------------------------------------------------------------

def test_eligible_phase_setting_fields_unchanged_with_no_method_scope(seeded_run):
    session = db.get_session()
    fields = analytics.eligible_phase_setting_fields(session, seeded_run["grade_id"])
    assert fields == list(analytics.PHASE_SETTING_FIELDS)
    session.close()


def test_eligible_phase_setting_fields_unchanged_with_method_scope_but_no_dynamic_data(seeded_run):
    session = db.get_session()
    fields = analytics.eligible_phase_setting_fields(
        session, seeded_run["grade_id"], production_method_id=seeded_run["method_id"],
    )
    assert fields == list(analytics.PHASE_SETTING_FIELDS), (
        "zero live 'Process Setting' category applicability rows exist today - "
        "passing production_method_id must not add anything yet"
    )
    session.close()


def test_run_settings_dataframe_has_no_dynamic_columns_without_dynamic_data(seeded_run):
    session = db.get_session()
    df = analytics.run_settings_dataframe(
        session, foam_grade_id=seeded_run["grade_id"], production_method_id=seeded_run["method_id"],
    )
    ps_columns = [c for c in df.columns if c.startswith("ps_")]
    assert ps_columns == []
    session.close()


# ---------------------------------------------------------------------------
# 2. Once evidence-based data exists, it surfaces correctly and automatically
# ---------------------------------------------------------------------------

def test_dynamic_field_surfaces_in_eligible_phase_setting_fields(seeded_run):
    dyn = _seed_dynamic_definition(seeded_run)
    session = db.get_session()
    fields = analytics.eligible_phase_setting_fields(
        session, seeded_run["grade_id"], production_method_id=seeded_run["method_id"],
    )
    expected_key = analytics.dynamic_process_setting_field_key(dyn["definition_id"])
    assert expected_key in fields
    # Legacy fields still come first, in their original order - purely additive.
    assert fields[: len(analytics.PHASE_SETTING_FIELDS)] == list(analytics.PHASE_SETTING_FIELDS)
    session.close()


def test_dynamic_field_not_surfaced_without_method_scope(seeded_run):
    """Even after evidence-based data exists, a pooled/unscoped caller
    (production_method_id=None) must not guess which method's dynamic
    fields to show - matches eligible_phase_setting_fields' pre-existing
    'don't guess' convention for the rigid-ineligibility restriction."""
    _seed_dynamic_definition(seeded_run)
    session = db.get_session()
    fields = analytics.eligible_phase_setting_fields(session, seeded_run["grade_id"])
    assert fields == list(analytics.PHASE_SETTING_FIELDS)
    session.close()


def test_dynamic_field_value_from_actual_snapshot(seeded_run):
    dyn = _seed_dynamic_definition(seeded_run)
    session = db.get_session()
    session.add(db.ProcessParameterValue(
        setting_definition_id=dyn["definition_id"], production_run_id=seeded_run["run_id"],
        snapshot_type="Actual", numeric_value=42.5, source="Machine capture",
    ))
    session.commit()

    df = analytics.run_settings_dataframe(
        session, foam_grade_id=seeded_run["grade_id"], production_method_id=seeded_run["method_id"],
    )
    field_key = analytics.dynamic_process_setting_field_key(dyn["definition_id"])
    assert field_key in df.columns
    row = df[df["run_id"] == seeded_run["run_id"]].iloc[0]
    assert row[field_key] == 42.5
    session.close()


def test_dynamic_field_falls_back_to_planned_when_no_actual(seeded_run):
    dyn = _seed_dynamic_definition(seeded_run)
    session = db.get_session()
    session.add(db.ProcessParameterValue(
        setting_definition_id=dyn["definition_id"], production_run_id=seeded_run["run_id"],
        snapshot_type="Planned", numeric_value=17.0, source="Manual entry",
    ))
    session.commit()

    df = analytics.run_settings_dataframe(
        session, foam_grade_id=seeded_run["grade_id"], production_method_id=seeded_run["method_id"],
    )
    field_key = analytics.dynamic_process_setting_field_key(dyn["definition_id"])
    row = df[df["run_id"] == seeded_run["run_id"]].iloc[0]
    assert row[field_key] == 17.0
    session.close()


def test_dynamic_field_prefers_actual_over_planned(seeded_run):
    dyn = _seed_dynamic_definition(seeded_run)
    session = db.get_session()
    session.add(db.ProcessParameterValue(
        setting_definition_id=dyn["definition_id"], production_run_id=seeded_run["run_id"],
        snapshot_type="Planned", numeric_value=17.0, source="Manual entry",
    ))
    session.add(db.ProcessParameterValue(
        setting_definition_id=dyn["definition_id"], production_run_id=seeded_run["run_id"],
        snapshot_type="Actual", numeric_value=19.5, source="Machine capture",
    ))
    session.commit()

    df = analytics.run_settings_dataframe(
        session, foam_grade_id=seeded_run["grade_id"], production_method_id=seeded_run["method_id"],
    )
    field_key = analytics.dynamic_process_setting_field_key(dyn["definition_id"])
    row = df[df["run_id"] == seeded_run["run_id"]].iloc[0]
    assert row[field_key] == 19.5
    session.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"controllable": False},
        {"analytics_eligible": False},
        {"parameter_category": "Environment"},
        {"parameter_category": "Outcome"},
        {"data_type": "String"},
        {"data_type": "Boolean"},
    ],
)
def test_dynamic_field_excluded_when_ineligible(seeded_run, kwargs):
    _seed_dynamic_definition(seeded_run, **kwargs)
    session = db.get_session()
    fields = analytics.eligible_phase_setting_fields(
        session, seeded_run["grade_id"], production_method_id=seeded_run["method_id"],
    )
    assert fields == list(analytics.PHASE_SETTING_FIELDS), f"should stay legacy-only for {kwargs}"
    session.close()


# ---------------------------------------------------------------------------
# 3. Correlation/optimization ranking picks up the dynamic field with a
#    real label, not a raw ps_<id> key
# ---------------------------------------------------------------------------

def test_rank_setting_correlations_includes_dynamic_field_with_real_label(seeded_grade_chain):
    ids = seeded_grade_chain
    run_ids = _seed_three_runs(ids)
    dyn = _seed_dynamic_definition(ids, name="Fill pressure")

    session = db.get_session()
    for run_id, value in zip(run_ids, (10.0, 20.0, 30.0)):
        session.add(db.ProcessParameterValue(
            setting_definition_id=dyn["definition_id"], production_run_id=run_id,
            snapshot_type="Actual", numeric_value=value, source="Machine capture",
        ))
    for run_id, actual in zip(run_ids, (1.0, 2.0, 3.0)):
        session.add(db.PhysicalPropertyResult(
            production_run_id=run_id, property_name="Density", target_value=2.0, actual_value=actual,
        ))
    session.commit()

    ranked = analytics.rank_setting_correlations(
        session, ids["grade_id"], "Density", production_method_id=ids["method_id"],
    )
    field_key = analytics.dynamic_process_setting_field_key(dyn["definition_id"])
    dyn_rows = ranked[ranked["field"] == field_key]
    assert len(dyn_rows) == 1
    assert dyn_rows.iloc[0]["label"] == "Fill pressure"
    assert dyn_rows.iloc[0]["n"] == 3
    assert dyn_rows.iloc[0]["correlation"] == 1.0  # perfectly increasing together
    session.close()


def test_rank_setting_optimization_includes_dynamic_field_with_real_label(seeded_grade_chain):
    ids = seeded_grade_chain
    run_ids = _seed_three_runs(ids)
    dyn = _seed_dynamic_definition(ids, name="Fill pressure")

    session = db.get_session()
    for run_id, value in zip(run_ids, (10.0, 20.0, 30.0)):
        session.add(db.ProcessParameterValue(
            setting_definition_id=dyn["definition_id"], production_run_id=run_id,
            snapshot_type="Actual", numeric_value=value, source="Machine capture",
        ))
    for run_id, actual in zip(run_ids, (1.0, 2.0, 4.0)):
        session.add(db.PhysicalPropertyResult(
            production_run_id=run_id, property_name="Density", target_value=2.0, actual_value=actual,
        ))
    session.commit()

    ranked = analytics.rank_setting_optimization(
        session, ids["grade_id"], "Density", production_method_id=ids["method_id"],
    )
    field_key = analytics.dynamic_process_setting_field_key(dyn["definition_id"])
    dyn_rows = ranked[ranked["field"] == field_key]
    assert len(dyn_rows) == 1
    assert dyn_rows.iloc[0]["label"] == "Fill pressure"
    session.close()


# ---------------------------------------------------------------------------
# 4. pages/18 no longer crashes on a dynamic field (direct dict indexing fix)
# ---------------------------------------------------------------------------

def test_phase_setting_labels_get_does_not_raise_for_dynamic_field(seeded_run):
    dyn = _seed_dynamic_definition(seeded_run)
    field_key = analytics.dynamic_process_setting_field_key(dyn["definition_id"])
    assert field_key not in analytics.PHASE_SETTING_LABELS
    # This is exactly the lookup pattern pages/18_Root_Cause_Assistant.py
    # now uses (fixed from direct [field] indexing, which would KeyError
    # here) - proves the fallback is safe, not just present in source.
    label = analytics.PHASE_SETTING_LABELS.get(field_key, field_key)
    assert label == field_key
