"""WP7 Phase 4 Batch Release/Conformance report cutover (2026-08-14)
regression tests.

Charlie's Downstream Reader Cutover Execution Instruction, section 6:
"ProductionOutputSummary becomes the active output fact. Overview, reports
and PI3 read its Actual quantity and controlled UOM." This file covers the
"reports" half for the Batch Release / Conformance Record report in
reports.py, following the Overview cutover done immediately before it
(see tests/test_wp7_phase4_overview_output_cutover.py).

WP7 Phase 4 targeted-completion correction (2026-08-14, Charlie's Closeout
Review Return to JC, Material Completion Item 1): section 1 below was
rewritten from reports._process_parameter_deviations() (a deviations-only
filter with flat "Setting"/"Planned"/"Actual" keys) to reports.
_process_parameter_report_rows() (definition-driven, category-bucketed,
with Category/UOM/Limit/Conformance columns) - see that function's
docstring for the full rationale.

Covers:
  1. reports._process_parameter_report_rows() - the shared-reader-backed,
     category-bucketed replacement: empty catalogue -> all-empty buckets,
     every eligible definition included (not deviations-only),
     Environment/Outcome kept structurally separate from Process Setting,
     controlled-limit resolution (override beats definition default) and
     conformance (Pass/Fail only when a limit exists and Actual is
     recorded numerically, else explicitly informational).
  2. reports.build_batch_release_record_data() - the new "output_summary"
     key: None when the run has no ProductionOutputSummary row (never
     inferred from the retired compute_runtime_output() formula),
     populated dict when a row exists, shown unconditionally (not gated
     by has_flags).
  3. Live AppTest evidence that the Report page's Batch Release tab and
     both the PDF and Word renderers produce output without exception,
     for both the "no output recorded" and "output recorded" states.

MANDATORY TEMPLATE: tests/test_wp7_phase4_overview_output_cutover.py
(AUTH_DISABLED/sqlite:// boilerplate, seeded_grade_chain/_make_run/
_add_output_summary fixtures, AppTest helpers).

Usage: python -m pytest tests/test_wp7_phase4_batch_release_cutover.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import analytics
import db
import reports

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_PAGE = os.path.join(APP_DIR, "views", "21_Report.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_grade_chain():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P4BR Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P4BR Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-WP7P4BR-{u}", name=f"WP7P4BR Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"WP7P4BR Machine {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()

    family = db.PUMaterialFamily(plant_id=plant.id, name=f"WP7P4BR Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"WP7P4BR Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    unit_m = db.UnitOfMeasure(controlled_id=f"UOM-WP7P4BR-M-{u}", symbol="m", name="Metres")
    session.add(unit_m); session.flush()

    setting_def = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P4BR-{u}", name=f"WP7P4BR Temperature {u}",
        parameter_category="Process Setting", data_type="Float",
        unit_id=unit_m.id,
    )
    session.add(setting_def); session.flush()
    session.add(db.ProcessSettingApplicability(
        setting_definition_id=setting_def.id, production_method_id=method.id, machine_id=None,
        controllable=True, analytics_eligible=True,
    ))
    session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "method_id": method.id,
        "machine_id": machine.id, "family_id": family.id, "grade_id": grade.id,
        "recipe_version_id": recipe.id, "unit_m_id": unit_m.id, "setting_def_id": setting_def.id,
    }
    session.close()
    return ids


def _make_run(ids, batch_suffix=None):
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
        recipe_version_id=ids["recipe_version_id"], run_date=dt.date(2026, 8, 1),
        batch_reference=f"B-WP7P4BR-{batch_suffix or uuid.uuid4().hex[:8]}",
        machine_id=ids["machine_id"], production_method_id=ids["method_id"],
        operator_or_team_reference="Shift A",
    )
    session.add(run); session.commit()
    run_id = run.id
    session.close()
    return run_id


def _add_output_summary(run_id, unit_id=None, planned_quantity=None, actual_quantity=None, disposition=None):
    session = db.get_session()
    row = db.ProductionOutputSummary(
        production_run_id=run_id, unit_id=unit_id,
        planned_quantity=planned_quantity, actual_quantity=actual_quantity, disposition=disposition,
    )
    session.add(row); session.commit()
    session.close()


def _add_parameter_value(run_id, setting_def_id, planned_value=None, actual_value=None):
    """Writes the Planned/Actual snapshot rows production_run_process_
    parameters() actually reads - ProcessParameterValue has no planned_
    value/actual_value columns directly; it stores one row per snapshot_
    type ('Planned'/'Actual'), value typed into numeric_value here since
    the fixture's setting definition is Float."""
    session = db.get_session()
    if planned_value is not None:
        session.add(db.ProcessParameterValue(
            production_run_id=run_id, setting_definition_id=setting_def_id,
            snapshot_type="Planned", numeric_value=planned_value,
        ))
    if actual_value is not None:
        session.add(db.ProcessParameterValue(
            production_run_id=run_id, setting_definition_id=setting_def_id,
            snapshot_type="Actual", numeric_value=actual_value,
        ))
    session.commit()
    session.close()


@pytest.fixture()
def seeded_run(seeded_grade_chain):
    ids = seeded_grade_chain
    run_id = _make_run(ids)
    out = dict(ids)
    out["run_id"] = run_id
    return out


# ---------------------------------------------------------------------------
# 1. reports._process_parameter_report_rows()
# ---------------------------------------------------------------------------

def test_definition_driven_includes_row_even_with_no_recorded_values(seeded_run):
    """Charlie's Closeout Review Item 1.1 requires the section to be
    'definition-driven', not a deviations-only filter - the fixture's one
    eligible Process Setting definition (WP7P4BR Temperature) must appear
    as a row even though no ProcessParameterValue has been recorded for
    it at all (both Planned and Actual None), unlike the retired
    deviations-only _process_parameter_deviations() which would have
    excluded it. The fixture seeds no Environment/Outcome definitions, so
    those two buckets stay empty - the required category separation."""
    session = db.get_session()
    result = reports._process_parameter_report_rows(session, seeded_run["run_id"])
    assert len(result["Process Setting"]) == 1
    assert result["Environment"] == []
    assert result["Outcome"] == []
    row = result["Process Setting"][0]
    assert row["Parameter"].startswith("WP7P4BR Temperature")
    assert row["Planned"] is None
    assert row["Actual"] is None
    assert row["Delta"] is None
    session.close()


def test_near_equal_float_pair_still_included_with_small_delta(seeded_run):
    """The retired epsilon-skip behavior (dropping a Float pair within
    _SETTING_DEVIATION_EPSILON as 'unchanged') no longer applies - the new
    definition-driven section shows every eligible definition's Planned/
    Actual/Delta regardless of how close they are, since it is no longer
    a deviations-only filter."""
    _add_parameter_value(seeded_run["run_id"], seeded_run["setting_def_id"], planned_value=100.0, actual_value=100.0000001)
    session = db.get_session()
    result = reports._process_parameter_report_rows(session, seeded_run["run_id"])
    assert len(result["Process Setting"]) == 1
    row = result["Process Setting"][0]
    assert row["Planned"] == 100.0
    assert row["Actual"] == 100.0000001
    assert row["Delta"] is not None
    session.close()


def test_row_has_full_required_column_set(seeded_run):
    """Per Charlie's Item 1.1: Parameter, Category, Planned, Actual,
    numeric Delta, canonical UOM - plus Item 1.2's Limit/Conformance."""
    _add_parameter_value(seeded_run["run_id"], seeded_run["setting_def_id"], planned_value=100.0, actual_value=95.0)
    session = db.get_session()
    result = reports._process_parameter_report_rows(session, seeded_run["run_id"])
    row = result["Process Setting"][0]
    assert set(row.keys()) == {"Parameter", "Category", "Planned", "Actual", "Delta", "UOM", "Limit", "Conformance"}
    assert row["Category"] == "Process Setting"
    assert row["Planned"] == 100.0
    assert row["Actual"] == 95.0
    assert row["Delta"] == -5.0
    assert row["UOM"] == "m"
    session.close()


def test_one_sided_actual_only_value_is_included(seeded_run):
    _add_parameter_value(seeded_run["run_id"], seeded_run["setting_def_id"], planned_value=None, actual_value=95.0)
    session = db.get_session()
    result = reports._process_parameter_report_rows(session, seeded_run["run_id"])
    assert len(result["Process Setting"]) == 1
    row = result["Process Setting"][0]
    assert row["Planned"] is None
    assert row["Actual"] == 95.0
    session.close()


def test_no_approved_limit_stays_informational_not_pass(seeded_run):
    """Charlie's Item 1.2: 'a row with no approved limit remains
    informational' - the fixture's setting definition has no min_value/
    max_value and no applicability override, so Conformance must say so
    explicitly rather than silently reading as Pass."""
    _add_parameter_value(seeded_run["run_id"], seeded_run["setting_def_id"], planned_value=100.0, actual_value=95.0)
    session = db.get_session()
    result = reports._process_parameter_report_rows(session, seeded_run["run_id"])
    row = result["Process Setting"][0]
    assert row["Limit"] == "—"
    assert row["Conformance"] == "Informational (no approved limit)"
    session.close()


def test_applicability_override_limit_wins_over_definition_default(seeded_run):
    """Charlie's Item 1.2: 'use min_value_override / max_value_override
    when populated, otherwise the definition min_value / max_value'."""
    session = db.get_session()
    definition = session.get(db.ProcessSettingDefinition, seeded_run["setting_def_id"])
    definition.min_value, definition.max_value = 0.0, 200.0
    applicability = (
        session.query(db.ProcessSettingApplicability)
        .filter(db.ProcessSettingApplicability.setting_definition_id == seeded_run["setting_def_id"])
        .one()
    )
    applicability.max_value_override = 90.0  # tighter than the definition default
    session.commit()
    session.close()

    _add_parameter_value(seeded_run["run_id"], seeded_run["setting_def_id"], planned_value=100.0, actual_value=95.0)
    session = db.get_session()
    result = reports._process_parameter_report_rows(session, seeded_run["run_id"])
    row = result["Process Setting"][0]
    # override max (90.0) beats definition default (200.0) -> 95.0 actual fails
    assert row["Conformance"] == "Fail"
    session.close()


def test_actual_within_limit_conforms(seeded_run):
    session = db.get_session()
    definition = session.get(db.ProcessSettingDefinition, seeded_run["setting_def_id"])
    definition.min_value, definition.max_value = 0.0, 200.0
    session.commit()
    session.close()

    _add_parameter_value(seeded_run["run_id"], seeded_run["setting_def_id"], planned_value=100.0, actual_value=95.0)
    session = db.get_session()
    result = reports._process_parameter_report_rows(session, seeded_run["run_id"])
    row = result["Process Setting"][0]
    assert row["Limit"] == "0.0–200.0"
    assert row["Conformance"] == "Pass"
    session.close()


def test_limit_exists_but_no_actual_recorded_is_not_silently_pass(seeded_run):
    session = db.get_session()
    definition = session.get(db.ProcessSettingDefinition, seeded_run["setting_def_id"])
    definition.min_value, definition.max_value = 0.0, 200.0
    session.commit()
    session.close()

    session = db.get_session()
    result = reports._process_parameter_report_rows(session, seeded_run["run_id"])
    row = result["Process Setting"][0]
    assert row["Actual"] is None
    assert row["Conformance"] == "No Actual value recorded"
    session.close()


# ---------------------------------------------------------------------------
# 2. build_batch_release_record_data() - output_summary field
# ---------------------------------------------------------------------------

def test_no_output_summary_row_yields_none_never_inferred(seeded_run):
    session = db.get_session()
    data = reports.build_batch_release_record_data(session, seeded_run["run_id"])
    assert data["output_summary"] is None
    session.close()


def test_output_summary_row_populates_field(seeded_run):
    _add_output_summary(
        seeded_run["run_id"], unit_id=seeded_run["unit_m_id"],
        planned_quantity=100.0, actual_quantity=97.5, disposition="Released",
    )
    session = db.get_session()
    data = reports.build_batch_release_record_data(session, seeded_run["run_id"])
    out = data["output_summary"]
    assert out is not None
    assert out["planned_quantity"] == 100.0
    assert out["actual_quantity"] == 97.5
    assert out["unit_symbol"] == "m"
    assert out["disposition"] == "Released"
    session.close()


def test_output_summary_shown_unconditionally_regardless_of_has_flags(seeded_run):
    """output_summary must be populated even when has_flags is False (no
    quality issues on this run) - it's a core release decision, not
    supplementary flag context gated behind the Flagged section."""
    _add_output_summary(seeded_run["run_id"], unit_id=seeded_run["unit_m_id"], actual_quantity=50.0)
    session = db.get_session()
    data = reports.build_batch_release_record_data(session, seeded_run["run_id"])
    assert data["has_flags"] is False
    assert data["output_summary"] is not None
    assert data["output_summary"]["actual_quantity"] == 50.0
    session.close()


def test_material_metering_reads_via_production_run_id_with_no_production_phase(seeded_run):
    """Charlie's Closeout Review Item 1.3 - direct evidence requirement:
    Batch Release's Material Metering section must read exclusively via
    ComponentStreamReading.production_run_id, never via a located Finalized
    ProductionPhase. This writes a stream reading with production_phase_id
    left NULL (no ProductionPhase row exists for this run at all - the
    fixture never creates one) and confirms it still surfaces, proving the
    query has no live ProductionPhase dependency."""
    session = db.get_session()
    assert session.query(db.ProductionPhase).filter(
        db.ProductionPhase.production_run_id == seeded_run["run_id"]
    ).count() == 0  # no ProductionPhase exists for this run at all
    reading = db.ComponentStreamReading(
        production_run_id=seeded_run["run_id"], production_phase_id=None,
        stream_name="Polyol A", flow=12.5, flow_unit="kg/min",
    )
    session.add(reading); session.commit()
    session.close()

    session = db.get_session()
    session.add(db.QualityObservation(
        production_run_id=seeded_run["run_id"], observation_type="Shrinkage", severity="Low",
    ))
    session.commit()
    session.close()

    session = db.get_session()
    data = reports.build_batch_release_record_data(session, seeded_run["run_id"])
    session.close()
    assert data["has_flags"] is True
    assert len(data["stream_readings"]) == 1
    assert data["stream_readings"][0]["Stream"] == "Polyol A"


# ---------------------------------------------------------------------------
# 3. Live AppTest + direct render evidence
# ---------------------------------------------------------------------------

def _run_report_page():
    at = AppTest.from_file(REPORT_PAGE, default_timeout=60)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


def test_report_page_batch_release_tab_loads_clean_no_output_recorded(seeded_run):
    at = _run_report_page()
    assert not at.exception, f"Unhandled exception loading Report page: {at.exception}"
    body = "\n".join(m.value for m in at.markdown) + "\n".join(i.value for i in at.info)
    assert "No Production Output has been recorded yet" in body


def test_report_page_batch_release_tab_shows_recorded_output(seeded_run):
    _add_output_summary(
        seeded_run["run_id"], unit_id=seeded_run["unit_m_id"],
        planned_quantity=100.0, actual_quantity=97.5, disposition="Released",
    )
    at = _run_report_page()
    assert not at.exception, f"Unhandled exception loading Report page: {at.exception}"
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Actual quantity"] == "97.5 m"
    assert metrics["Planned quantity"] == "100.0 m"
    assert metrics["Disposition"] == "Released"


def test_pdf_and_docx_render_with_output_summary(seeded_run):
    _add_output_summary(
        seeded_run["run_id"], unit_id=seeded_run["unit_m_id"],
        planned_quantity=100.0, actual_quantity=97.5, disposition="Released",
    )
    session = db.get_session()
    data = reports.build_batch_release_record_data(session, seeded_run["run_id"])
    session.close()
    pdf_bytes = reports.render_batch_release_record_pdf(data)
    docx_bytes = reports.render_batch_release_record_docx(data)
    assert pdf_bytes and len(pdf_bytes) > 100
    assert docx_bytes and len(docx_bytes) > 100


def test_pdf_and_docx_render_with_no_output_summary(seeded_run):
    session = db.get_session()
    data = reports.build_batch_release_record_data(session, seeded_run["run_id"])
    session.close()
    pdf_bytes = reports.render_batch_release_record_pdf(data)
    docx_bytes = reports.render_batch_release_record_docx(data)
    assert pdf_bytes and len(pdf_bytes) > 100
    assert docx_bytes and len(docx_bytes) > 100
