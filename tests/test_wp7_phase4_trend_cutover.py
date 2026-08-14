"""WP7 Phase 4 Trend Analysis cutover (2026-08-14) regression tests.

Charlie's WP7 Phase 4 Closeout Review Return to JC, Material Completion
Item 3: "The closeout package classifies Trend Analysis as out of scope
because the current page is property-result SPC only. The governing Phase
4 instruction explicitly includes Trend Analysis and requires direct
UI/AppTest evidence using seeded method-aware values. This acceptance path
therefore cannot be skipped."

Required proof (Item 3's own wording):
  1. The method-aware parameter trend path (ProcessSettingDefinition +
     ProcessParameterValue, with Production Method context and canonical
     UOM) exists, and existing physical-property SPC functionality remains
     intact.
  2. Trend exposes Process Setting, Environment, and Outcome categories as
     recorded facts - comparisons stay within the same definition/
     canonical UOM, NULL stays unrecorded, zero stays a recorded zero.
  3. Direct AppTest coverage for at least one Process Setting and one
     Environment/Outcome definition, plus source-isolation evidence that a
     deliberately conflicting legacy ProductionPhase value never enters
     the trend result.

Covers:
  1. analytics.process_parameter_definitions_for_trend() offers Process
     Setting, Environment, and Outcome definitions together (numeric only
     - Boolean/String excluded, since the SPC toolkit needs a number).
  2. analytics.process_parameter_run_series(): NULL (never recorded)
     dropped from the series; a recorded Actual of exactly 0 kept.
  3. Source isolation: a deliberately conflicting ProductionPhase.
     ambient_temperature_c value never reaches the series - only the real
     ProcessParameterValue Actual for the picked definition does.
  4. Live AppTest: Process parameter trend subject, a Process Setting
     definition, renders the control chart/trend-test path without
     exception, with canonical UOM visible.
  5. Live AppTest: Process parameter trend subject, an Environment
     definition, also renders cleanly - proves category-agnostic exposure.
  6. Live AppTest: Quality property trend subject (the page's original
     default/path) still renders without exception against the same
     fixture - "existing physical-property SPC functionality remains
     intact."

MANDATORY TEMPLATE: tests/test_wp7_phase4_root_cause_cutover.py (same
seeded_grade_chain -> per-run fixture chain, _seed_definition/_add_actual
helpers, _run_page/_body_text AppTest pattern).

Usage: python -m pytest tests/test_wp7_phase4_trend_cutover.py -v
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
PAGE16 = os.path.join(APP_DIR, "pages", "16_Trend_Analysis.py")


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

    company = db.Company(name=f"WP7P4TR Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P4TR Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-WP7P4TR-{u}", name=f"WP7P4TR Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"WP7P4TR Machine {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P4TR Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P4TR Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P4TR-{u}", symbol="bar", name="Bar")
    session.add(unit); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "method_id": method.id,
        "machine_id": machine.id, "family_id": family.id, "grade_id": grade.id,
        "recipe_version_id": recipe.id, "unit_id": unit.id,
    }
    session.close()
    return ids


def _make_run(ids, run_date, batch_suffix=None):
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
        recipe_version_id=ids["recipe_version_id"], run_date=run_date,
        batch_reference=f"B-WP7P4TR-{batch_suffix or uuid.uuid4().hex[:8]}",
        machine_id=ids["machine_id"], production_method_id=ids["method_id"],
        operator_or_team_reference="Shift A",
    )
    session.add(run); session.commit()
    run_id = run.id
    session.close()
    return run_id


def _seed_definition(ids, name, parameter_category="Process Setting", data_type="Float"):
    session = db.get_session()
    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P4TR-{uuid.uuid4().hex[:6]}", name=name,
        data_type=data_type, unit_id=ids["unit_id"] if data_type == "Float" else None,
        parameter_category=parameter_category,
    )
    session.add(definition); session.flush()
    session.add(db.ProcessSettingApplicability(
        setting_definition_id=definition.id, production_method_id=ids["method_id"], machine_id=None,
        controllable=True, analytics_eligible=True,
    ))
    session.commit()
    definition_id = definition.id
    session.close()
    return definition_id


def _add_actual(run_id, definition_id, numeric_value=None, text_value=None, boolean_value=None):
    session = db.get_session()
    session.add(db.ProcessParameterValue(
        setting_definition_id=definition_id, production_run_id=run_id,
        snapshot_type="Actual", numeric_value=numeric_value,
        text_value=text_value, boolean_value=boolean_value, source="Machine capture",
    ))
    session.commit()
    session.close()


def _add_planned(run_id, definition_id, numeric_value):
    session = db.get_session()
    session.add(db.ProcessParameterValue(
        setting_definition_id=definition_id, production_run_id=run_id,
        snapshot_type="Planned", numeric_value=numeric_value, source="Recipe",
    ))
    session.commit()
    session.close()


def _run_page():
    at = AppTest.from_file(PAGE16, default_timeout=60)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


def _body_text(at):
    return (
        "\n".join(m.value for m in at.markdown) + "\n" + "\n".join(i.value for i in at.info)
        + "\n" + "\n".join(str(c.value) for c in at.caption) + "\n" + "\n".join(s.value for s in at.subheader)
    )


def _select_process_parameter_mode(at, field_key):
    """Drives the page into the new Process parameter trend subject and
    picks the given field_key (analytics.dynamic_process_setting_field_key
    output) on the resulting 'Process parameter' selectbox, then reruns.
    Index-based widget selection: analysis_unit_picker's own 'Analyze by'
    radio is always the first st.radio on the page (called before this
    page's new 'What to trend' radio), so the second radio is always the
    trend-subject control - robust to this batch's own dynamic session-
    state key (which embeds the picked grade's id)."""
    at.radio[1].set_value("Process parameter (Process Setting / Environment / Outcome)")
    at.run()
    param_select = next(sb for sb in at.selectbox if sb.label == "Process parameter")
    param_select.set_value(field_key)
    at.run()
    return at


# ---------------------------------------------------------------------------
# 1. Category-agnostic, numeric-only definition picker
# ---------------------------------------------------------------------------

def test_definitions_for_trend_includes_all_three_categories_numeric_only(seeded_grade_chain):
    ids = seeded_grade_chain
    run_id = _make_run(ids, dt.date(2026, 8, 1))
    ps_def = _seed_definition(ids, "WP7P4TR Fill pressure", parameter_category="Process Setting", data_type="Float")
    env_def = _seed_definition(ids, "WP7P4TR Ambient Temperature", parameter_category="Environment", data_type="Float")
    outcome_def = _seed_definition(ids, "WP7P4TR Rise time", parameter_category="Outcome", data_type="Float")
    bool_def = _seed_definition(ids, "WP7P4TR Top-flat system", parameter_category="Process Setting", data_type="Boolean")
    for d in (ps_def, env_def, outcome_def, bool_def):
        _add_actual(run_id, d, numeric_value=1.0) if d != bool_def else _add_actual(run_id, d, boolean_value=True)

    session = db.get_session()
    items = analytics.process_parameter_definitions_for_trend(session, [ids["grade_id"]])
    session.close()

    labels = {meta["label"] for _field_key, meta in items}
    categories = {meta["label"]: meta["parameter_category"] for _field_key, meta in items}
    assert labels == {"WP7P4TR Fill pressure", "WP7P4TR Ambient Temperature", "WP7P4TR Rise time"}, (
        "The Boolean definition must be excluded (non-numeric); all three numeric categories "
        "(Process Setting, Environment, Outcome) must be offered together."
    )
    assert categories["WP7P4TR Fill pressure"] == "Process Setting"
    assert categories["WP7P4TR Ambient Temperature"] == "Environment"
    assert categories["WP7P4TR Rise time"] == "Outcome"


# ---------------------------------------------------------------------------
# 2. NULL preserved as unrecorded; recorded zero kept
# ---------------------------------------------------------------------------

def test_run_series_drops_null_keeps_recorded_zero(seeded_grade_chain):
    ids = seeded_grade_chain
    run_zero = _make_run(ids, dt.date(2026, 8, 1), batch_suffix="zero")
    run_null = _make_run(ids, dt.date(2026, 8, 2), batch_suffix="null")
    run_five = _make_run(ids, dt.date(2026, 8, 3), batch_suffix="five")
    definition_id = _seed_definition(ids, "WP7P4TR Vent flow", parameter_category="Process Setting", data_type="Float")

    _add_actual(run_zero, definition_id, numeric_value=0.0)
    # run_null: deliberately no ProcessParameterValue row at all - never recorded.
    _add_actual(run_five, definition_id, numeric_value=5.0)

    session = db.get_session()
    series = analytics.process_parameter_run_series(session, [ids["grade_id"]], definition_id)
    session.close()

    assert len(series) == 2, "The never-recorded run must be dropped, not shown as a false zero."
    assert run_null not in series["run_id"].tolist()
    zero_row = series[series["run_id"] == run_zero].iloc[0]
    assert zero_row["actual_value"] == 0.0, "A genuinely recorded zero must be kept, not treated as missing."
    five_row = series[series["run_id"] == run_five].iloc[0]
    assert five_row["actual_value"] == 5.0


def test_run_series_carries_planned_as_target_and_canonical_unit_via_definitions(seeded_grade_chain):
    ids = seeded_grade_chain
    run_id = _make_run(ids, dt.date(2026, 8, 1))
    definition_id = _seed_definition(ids, "WP7P4TR Mixer speed", parameter_category="Process Setting", data_type="Float")
    _add_planned(run_id, definition_id, 100.0)
    _add_actual(run_id, definition_id, numeric_value=95.0)

    session = db.get_session()
    series = analytics.process_parameter_run_series(session, [ids["grade_id"]], definition_id)
    items = dict(analytics.process_parameter_definitions_for_trend(session, [ids["grade_id"]]))
    session.close()

    row = series.iloc[0]
    assert row["actual_value"] == 95.0
    assert row["target_value"] == 100.0
    field_key = analytics.dynamic_process_setting_field_key(definition_id)
    assert items[field_key]["unit_symbol"] == "bar", "Canonical UOM must come from the definition itself."


# ---------------------------------------------------------------------------
# 3. Source isolation: a conflicting legacy ProductionPhase value never
#    enters the trend result.
# ---------------------------------------------------------------------------

def test_source_isolation_conflicting_production_phase_value_never_enters_series(seeded_grade_chain):
    ids = seeded_grade_chain
    run_id = _make_run(ids, dt.date(2026, 8, 1))

    # A real, method-aware Environment definition with its own genuine
    # Actual value.
    env_def = _seed_definition(ids, "WP7P4TR Ambient Temperature", parameter_category="Environment", data_type="Float")
    _add_actual(run_id, env_def, numeric_value=22.5)

    # Deliberately conflicting legacy ProductionPhase value on the SAME
    # run, using the legacy same-concept field (ambient_temperature_c) -
    # this column retains zero active-reader authority under Phase 4 (see
    # ProductionPhase's own docstring in db.py) and must never surface.
    session = db.get_session()
    session.add(db.ProductionPhase(
        production_run_id=run_id, phase_name="Finalized", ambient_temperature_c=999.0,
    ))
    session.commit()
    session.close()

    session = db.get_session()
    series = analytics.process_parameter_run_series(session, [ids["grade_id"]], env_def)
    session.close()

    assert len(series) == 1
    assert series.iloc[0]["actual_value"] == 22.5, (
        "The real ProcessParameterValue Actual must be the only value in the series."
    )
    assert 999.0 not in series["actual_value"].tolist(), (
        "The conflicting legacy ProductionPhase.ambient_temperature_c value must never enter "
        "the trend result - process_parameter_run_series reads exclusively through the shared "
        "reader (production_run_parameter_dataframe), never ProductionPhase."
    )


# ---------------------------------------------------------------------------
# 4-6. Live AppTest evidence
# ---------------------------------------------------------------------------

@pytest.fixture()
def five_run_fixture(seeded_grade_chain):
    """5 runs (control_chart_analysis's own min_points), each with a
    Process Setting AND an Environment definition recorded, plus one
    PhysicalPropertyResult per run so the original quality-property trend
    path also has data to exercise in the same fixture."""
    ids = seeded_grade_chain
    ps_def = _seed_definition(ids, "WP7P4TR Fill pressure", parameter_category="Process Setting", data_type="Float")
    env_def = _seed_definition(ids, "WP7P4TR Ambient Temperature", parameter_category="Environment", data_type="Float")

    run_ids = []
    for i, ps_value in enumerate([100.0, 102.0, 98.0, 101.0, 99.0]):
        run_id = _make_run(ids, dt.date(2026, 8, 1 + i), batch_suffix=f"r{i}")
        _add_actual(run_id, ps_def, numeric_value=ps_value)
        _add_actual(run_id, env_def, numeric_value=20.0 + i)
        session = db.get_session()
        session.add(db.PhysicalPropertyResult(
            production_run_id=run_id, property_name="Density",
            target_value=40.0, actual_value=39.5 + i * 0.1, unit="kg/m3",
            tested_at=dt.date(2026, 8, 1 + i),
        ))
        session.commit()
        session.close()
        run_ids.append(run_id)

    out = dict(ids)
    out.update({"ps_def": ps_def, "env_def": env_def, "run_ids": run_ids})
    return out


def test_appTest_process_setting_trend_renders_with_canonical_unit(five_run_fixture):
    field_key = analytics.dynamic_process_setting_field_key(five_run_fixture["ps_def"])
    at = _run_page()
    at = _select_process_parameter_mode(at, field_key)
    assert not at.exception, f"Unhandled exception loading Trend Analysis (Process Setting): {at.exception}"
    body = _body_text(at)
    assert "WP7P4TR Fill pressure" in body
    assert "Process Setting" in body
    assert "bar" in body, "Canonical UOM (bar) must be visible."


def test_appTest_environment_trend_renders_cleanly(five_run_fixture):
    field_key = analytics.dynamic_process_setting_field_key(five_run_fixture["env_def"])
    at = _run_page()
    at = _select_process_parameter_mode(at, field_key)
    assert not at.exception, f"Unhandled exception loading Trend Analysis (Environment): {at.exception}"
    body = _body_text(at)
    assert "WP7P4TR Ambient Temperature" in body
    assert "Environment" in body


def test_appTest_quality_property_path_still_renders_unaffected(five_run_fixture):
    """Regression proof for "existing physical-property SPC functionality
    remains intact": the page's original default trend subject (Quality
    property) still loads cleanly against the same fixture, with no
    interaction needed to reach it (it's the radio's first/default
    option)."""
    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Trend Analysis (Quality property, default): {at.exception}"
    body = _body_text(at)
    assert "Density" in body
    assert "Sudden changes check" in body
