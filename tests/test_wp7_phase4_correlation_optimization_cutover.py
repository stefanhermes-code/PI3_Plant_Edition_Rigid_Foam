"""WP7 Phase 4 Process-Property Correlation (#978) / Process Parameter
Optimization (#979) cutover regression tests.

Charlie's Downstream Reader Cutover Execution Instruction section 3 lists
the required source for both pages: "Actual ProcessParameterValue rows
whose winning applicability is controllable=True and analytics_
eligible=True" - Environment/Outcome categories "never enter the
controllable-setting ranking by default", and section 11's "Optimization
eligibility" test gate requires "A definition with analytics_eligible=False
or controllable=False is excluded from optimization/correlation even when
values exist."

This file was added after the cutover's own analytics.py rewrite (see
version.py's v0.52.0 notes) because the WP7 Phase 4 static dependency scan
(task #981) found that merged_run_property_dataframe()'s original filter
only checked parameter_category/data_type - it never checked controllable/
analytics_eligible, so a definition with either flag False on its winning
applicability would still have appeared in both pages' rankings if it had
recorded values. That gap is fixed in analytics.py (definitions_by_field
filter now also requires meta["controllable"] and meta["analytics_
eligible"]); this file proves the fix and guards against a regression.

Also covers reader source isolation (legacy ProductionPhase values with
deliberately different numbers never leak into either page) and category
isolation (Environment excluded), both required test gates this batch's
targeted subset run didn't separately prove for pages 17/19 specifically
(only at the shared-reader level, in test_wp7_phase4_shared_reader.py).

MANDATORY TEMPLATE: tests/test_wp7_phase4_shared_reader.py (seeded_grade_
chain fixture, _seed_definition/_add_value helpers) and tests/
test_wp7_phase4_root_cause_cutover.py (AppTest page-load pattern).

Usage: python -m pytest tests/test_wp7_phase4_correlation_optimization_cutover.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import access_control
import analytics
import db
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE17 = os.path.join(APP_DIR, "views", "17_Process_Property_Correlation.py")
PAGE19 = os.path.join(APP_DIR, "views", "19_Machine_Settings_Optimization.py")


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


@pytest.fixture()
def seeded_grade_chain():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P4CO Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P4CO Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-WP7P4CO-{u}", name=f"WP7P4CO Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"WP7P4CO Machine {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P4CO Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P4CO Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P4CO-{u}", symbol="bar", name="Bar")
    session.add(unit); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "method_id": method.id,
        "machine_id": machine.id, "family_id": family.id, "grade_id": grade.id,
        "recipe_version_id": recipe.id, "unit_id": unit.id,
    }
    session.close()
    return ids


def _seed_definition(ids, controllable=True, analytics_eligible=True,
                      parameter_category="Process Setting", data_type="Float",
                      name="Fill pressure"):
    session = db.get_session()
    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P4CO-{uuid.uuid4().hex[:6]}", name=name,
        data_type=data_type, unit_id=ids["unit_id"], parameter_category=parameter_category,
    )
    session.add(definition); session.flush()
    session.add(db.ProcessSettingApplicability(
        setting_definition_id=definition.id, production_method_id=ids["method_id"], machine_id=None,
        controllable=controllable, analytics_eligible=analytics_eligible,
    ))
    session.commit()
    definition_id = definition.id
    session.close()
    return definition_id


def _add_actual(run_id, definition_id, numeric_value):
    session = db.get_session()
    session.add(db.ProcessParameterValue(
        setting_definition_id=definition_id, production_run_id=run_id,
        snapshot_type="Actual", numeric_value=numeric_value, source="Test seed",
    ))
    session.commit()
    session.close()


@pytest.fixture()
def four_run_fixture(seeded_grade_chain):
    """4 runs with a Density result each, plus 4 process-setting
    definitions covering every exclusion rule pages 17/19 must apply:
    an eligible Process Setting (must appear), a Process Setting with
    analytics_eligible=False (must be excluded), a Process Setting with
    controllable=False (must be excluded), and an Environment-category
    definition (must be excluded). Each run's legacy ProductionPhase.
    mixer_rpm is set to a deliberately different, unrelated number to
    prove reader source isolation - neither page may read it."""
    ids = seeded_grade_chain
    session = db.get_session()

    eligible_def = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P4CO-ELIG-{uuid.uuid4().hex[:6]}", name="WP7P4CO Fill pressure",
        data_type="Float", unit_id=ids["unit_id"], parameter_category="Process Setting",
    )
    ineligible_analytics_def = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P4CO-NOANALYTICS-{uuid.uuid4().hex[:6]}", name="WP7P4CO Not analytics eligible",
        data_type="Float", unit_id=ids["unit_id"], parameter_category="Process Setting",
    )
    ineligible_controllable_def = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P4CO-NOCONTROL-{uuid.uuid4().hex[:6]}", name="WP7P4CO Not controllable",
        data_type="Float", unit_id=ids["unit_id"], parameter_category="Process Setting",
    )
    environment_def = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P4CO-ENV-{uuid.uuid4().hex[:6]}", name="WP7P4CO Ambient humidity",
        data_type="Float", unit_id=ids["unit_id"], parameter_category="Environment",
    )
    session.add_all([eligible_def, ineligible_analytics_def, ineligible_controllable_def, environment_def])
    session.flush()

    session.add_all([
        db.ProcessSettingApplicability(
            setting_definition_id=eligible_def.id, production_method_id=ids["method_id"], machine_id=None,
            controllable=True, analytics_eligible=True,
        ),
        db.ProcessSettingApplicability(
            setting_definition_id=ineligible_analytics_def.id, production_method_id=ids["method_id"], machine_id=None,
            controllable=True, analytics_eligible=False,
        ),
        db.ProcessSettingApplicability(
            setting_definition_id=ineligible_controllable_def.id, production_method_id=ids["method_id"], machine_id=None,
            controllable=False, analytics_eligible=True,
        ),
        db.ProcessSettingApplicability(
            setting_definition_id=environment_def.id, production_method_id=ids["method_id"], machine_id=None,
            controllable=True, analytics_eligible=True,
        ),
    ])
    session.commit()
    def_ids = {
        "eligible": eligible_def.id, "no_analytics": ineligible_analytics_def.id,
        "no_controllable": ineligible_controllable_def.id, "environment": environment_def.id,
    }
    session.close()

    base_date = dt.date(2026, 8, 1)
    run_ids = []
    for i in range(4):
        session = db.get_session()
        run = db.ProductionRun(
            plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"], machine_id=ids["machine_id"],
            recipe_version_id=ids["recipe_version_id"], run_date=base_date + dt.timedelta(days=i * 2),
            batch_reference=f"WP7P4CO-B{i}", production_method_id=ids["method_id"],
        )
        session.add(run); session.flush()
        run_id = run.id
        # Legacy ProductionPhase, deliberately different numbers from any
        # process-parameter value below - proves reader source isolation.
        session.add(db.ProductionPhase(
            production_run_id=run.id, phase_name="Finalized", mixer_rpm=9000 + i * 500,
        ))
        session.add(db.PhysicalPropertyResult(
            production_run_id=run.id, property_name="Density", target_value=35.0,
            actual_value=35.0 + i * 0.5, unit="kg/m3",
            tested_at=dt.datetime.combine(run.run_date, dt.time(10, 0)),
        ))
        session.commit()
        session.close()
        run_ids.append(run_id)

        _add_actual(run_id, def_ids["eligible"], numeric_value=100.0 + i * 10)
        _add_actual(run_id, def_ids["no_analytics"], numeric_value=200.0 + i * 10)
        _add_actual(run_id, def_ids["no_controllable"], numeric_value=300.0 + i * 10)
        _add_actual(run_id, def_ids["environment"], numeric_value=20.0 + i)

    out = dict(ids)
    out.update({"run_ids": run_ids, **{f"{k}_def": v for k, v in def_ids.items()}})
    return out


# ---------------------------------------------------------------------------
# analytics.py level: merged_run_property_dataframe / rank_setting_
# correlations / rank_setting_optimization
# ---------------------------------------------------------------------------

def test_rank_correlations_excludes_analytics_ineligible_and_uncontrollable_and_environment(four_run_fixture):
    session = db.get_session()
    ranked = analytics.rank_setting_correlations(session, four_run_fixture["grade_id"], "Density")
    labels = set(ranked["label"])
    assert "WP7P4CO Fill pressure" in labels
    assert "WP7P4CO Not analytics eligible" not in labels, (
        "A definition with analytics_eligible=False on its winning "
        "applicability must be excluded from correlation ranking even "
        "though it has recorded Actual values - required test gate "
        "'Optimization eligibility'."
    )
    assert "WP7P4CO Not controllable" not in labels, (
        "A definition with controllable=False on its winning applicability "
        "must be excluded from correlation ranking even though it has "
        "recorded Actual values."
    )
    assert "WP7P4CO Ambient humidity" not in labels, (
        "An Environment-category definition must never enter the "
        "controllable-setting correlation ranking, per section 4's "
        "category rules."
    )


def test_rank_optimization_excludes_analytics_ineligible_and_uncontrollable_and_environment(four_run_fixture):
    session = db.get_session()
    ranked = analytics.rank_setting_optimization(session, four_run_fixture["grade_id"], "Density")
    labels = set(ranked["label"])
    assert "WP7P4CO Fill pressure" in labels
    assert "WP7P4CO Not analytics eligible" not in labels
    assert "WP7P4CO Not controllable" not in labels
    assert "WP7P4CO Ambient humidity" not in labels


def test_merged_dataframe_never_leaks_legacy_production_phase_mixer_rpm(four_run_fixture):
    """Reader source isolation: the legacy ProductionPhase.mixer_rpm values
    seeded above (9000, 9500, 10000, 10500) are deliberately far outside
    any process-parameter value seeded (100-330). run_settings_dataframe()
    (the legacy identity-column source, still used unchanged for run_id/
    run_date/machine/etc. - see merged_run_property_dataframe's own
    docstring) does carry its own incidental "mixer_rpm" column, but no
    downstream consumer (rank_setting_correlations/rank_setting_
    optimization/either page's selectbox) ever reads a column by that
    static name - both only ever iterate definitions_by_field's dynamic
    "ps_<definition_id>" keys. This test proves that isolation directly:
    the dynamic field-key columns - the only ones either page's ranking or
    selectbox ever touches - never carry a legacy-range value, and neither
    ranked output nor definitions_by_field ever exposes a "mixer_rpm"-named
    field."""
    session = db.get_session()
    merged, definitions_by_field = analytics.merged_run_property_dataframe(
        session, four_run_fixture["grade_id"], "Density",
    )
    assert "mixer_rpm" not in definitions_by_field, (
        "definitions_by_field must only ever contain dynamic ps_<id> keys "
        "sourced from the shared reader, never a legacy static field name."
    )
    dynamic_values = []
    for field_key in definitions_by_field:
        dynamic_values.extend(v for v in merged[field_key].tolist() if v is not None)
    assert not any(9000 <= v <= 10500 for v in dynamic_values if isinstance(v, (int, float))), (
        "A legacy ProductionPhase.mixer_rpm value leaked into one of the "
        "shared-reader-backed dynamic field-key columns - reader source "
        "isolation gate failed."
    )
    ranked = analytics.rank_setting_correlations(session, four_run_fixture["grade_id"], "Density")
    assert "mixer_rpm" not in set(ranked["field"]), (
        "The ranked correlation output must never surface a legacy static "
        "field name as a 'field' value."
    )


# ---------------------------------------------------------------------------
# Page-level AppTest evidence
# ---------------------------------------------------------------------------

def _run(page_path):
    at = AppTest.from_file(page_path, default_timeout=60)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


def test_process_property_correlation_page_shows_only_eligible_setting(four_run_fixture):
    at = _run(PAGE17)
    assert not at.exception, f"Unhandled exception loading Process-Property Correlation: {at.exception}"
    body = "\n".join(m.value for m in at.markdown) + "\n" + "\n".join(c.value for c in at.caption)
    assert "WP7P4CO Fill pressure" in body
    assert "WP7P4CO Not analytics eligible" not in body
    assert "WP7P4CO Not controllable" not in body
    assert "WP7P4CO Ambient humidity" not in body
    dl_buttons = [b for b in at.get("download_button") if "correlation_report_docx" in (b.key or "")]
    assert len(dl_buttons) == 1


def test_machine_settings_optimization_page_shows_only_eligible_setting(four_run_fixture):
    at = _run(PAGE19)
    assert not at.exception, f"Unhandled exception loading Process Parameter Optimization: {at.exception}"
    body = "\n".join(m.value for m in at.markdown) + "\n" + "\n".join(c.value for c in at.caption)
    assert "WP7P4CO Fill pressure" in body
    assert "WP7P4CO Not analytics eligible" not in body
    assert "WP7P4CO Not controllable" not in body
    assert "WP7P4CO Ambient humidity" not in body
    dl_buttons = [b for b in at.get("download_button") if "mso_report_docx" in (b.key or "")]
    assert len(dl_buttons) == 1
