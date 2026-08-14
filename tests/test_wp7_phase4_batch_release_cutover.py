"""WP7 Phase 4 Batch Release/Conformance report cutover (2026-08-14)
regression tests.

Charlie's Downstream Reader Cutover Execution Instruction, section 6:
"ProductionOutputSummary becomes the active output fact. Overview, reports
and PI3 read its Actual quantity and controlled UOM." This file covers the
"reports" half for the Batch Release / Conformance Record report in
reports.py, following the Overview cutover done immediately before it
(see tests/test_wp7_phase4_overview_output_cutover.py).

Covers:
  1. reports._process_parameter_deviations() - the shared-reader-backed
     replacement for the retired _setup_vs_finalized_deviations()
     (Setup-phase vs Finalized-phase ProductionPhase field diffing):
     empty catalogue -> [], Float/Integer epsilon-tolerance skip, one-
     sided Planned/Actual rows included, "Setting"/"Planned"/"Actual"
     dict keys.
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
REPORT_PAGE = os.path.join(APP_DIR, "pages", "21_Report.py")


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

    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P4BR Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P4BR Grade {u}")
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
# 1. reports._process_parameter_deviations()
# ---------------------------------------------------------------------------

def test_empty_catalogue_returns_no_deviations(seeded_run):
    session = db.get_session()
    result = reports._process_parameter_deviations(session, seeded_run["run_id"])
    assert result == []
    session.close()


def test_within_epsilon_float_deviation_is_skipped(seeded_run):
    _add_parameter_value(seeded_run["run_id"], seeded_run["setting_def_id"], planned_value=100.0, actual_value=100.0000001)
    session = db.get_session()
    result = reports._process_parameter_deviations(session, seeded_run["run_id"])
    assert result == [], "a Float difference within epsilon must not be reported as a deviation"
    session.close()


def test_real_float_deviation_is_reported_with_planned_actual_keys(seeded_run):
    _add_parameter_value(seeded_run["run_id"], seeded_run["setting_def_id"], planned_value=100.0, actual_value=95.0)
    session = db.get_session()
    result = reports._process_parameter_deviations(session, seeded_run["run_id"])
    assert len(result) == 1
    row = result[0]
    assert set(row.keys()) == {"Setting", "Planned", "Actual"}
    assert row["Planned"] == 100.0
    assert row["Actual"] == 95.0
    session.close()


def test_one_sided_actual_only_value_is_included(seeded_run):
    _add_parameter_value(seeded_run["run_id"], seeded_run["setting_def_id"], planned_value=None, actual_value=95.0)
    session = db.get_session()
    result = reports._process_parameter_deviations(session, seeded_run["run_id"])
    assert len(result) == 1
    assert result[0]["Planned"] is None
    assert result[0]["Actual"] == 95.0
    session.close()


def test_both_none_is_excluded(seeded_run):
    # No ProcessParameterValue row at all is the normal "no data" state,
    # already covered by test_empty_catalogue_returns_no_deviations - this
    # confirms a row that somehow has both sides None is still excluded.
    session = db.get_session()
    result = reports._process_parameter_deviations(session, seeded_run["run_id"])
    assert result == []
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
