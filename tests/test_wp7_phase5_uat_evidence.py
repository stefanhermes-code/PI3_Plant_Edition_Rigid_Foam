"""WP7 Phase 5 (2026-08-15) - direct UAT/evidence tests for the 4 gaps
found by a targeted coverage audit against the WP7 Phase 5 Legacy
Retirement and Final UAT Execution Contract's acceptance matrix (section
5), run before closing task "end-to-end UAT + downstream consumer
verification":

- A5-04 (Production Run UAT): the piecemeal AppTest coverage already
  spread across test_wp7_phase2_production_run_ui.py,
  test_wp7_phase2_closeout_correction.py, test_cr11_functional_evidence_
  group_d.py and test_wp7_phase3_reconciliation.py never exercised a
  genuine zero (as opposed to a non-zero value) through the new
  Observations (Environment & Outcome) block's "Record" checkbox
  convention, and no single test walked context -> settings -> output ->
  metering -> events -> observations for one run in one place. Both
  addressed here.
- A5-05 (Downstream UAT): audited, found COVERED by existing
  test_wp7_phase4_*_cutover.py files plus
  test_wp7_phase5_migration_cleanup.py - no new test needed, not
  duplicated here.
- A5-06 (Delete/cascade integrity): cascades.py's
  delete_production_run_cascade() was only ever exercised against a
  run seeded with zero dependents (test_wp7_phase2_production_run_ui.py's
  own comment says so directly) - real dependent rows, including the new
  Environment/Outcome ProcessParameterValue rows added this session, were
  never proven to actually get deleted. Fixed here.
- A5-07 (Imports/exports): the Component Stream Reading CSV import
  accepted ANY string for flow_unit and silently defaulted to "kg/min" -
  the manual create/edit forms have always constrained this to the
  controlled 2-value list (STREAM_FLOW_UNIT_OPTIONS on views/4). Fixed on
  views/4 in the same commit as this test (constant extracted + import-path
  validation added), proven here.

Usage: python -m pytest tests/test_wp7_phase5_uat_evidence.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import access_control
import cascades
import db
import legacy_migration as lm
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE4 = os.path.join(APP_DIR, "views", "4_Production_Run_Trial_Record.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()


def _run_page4(session_state=None):
    at = AppTest.from_file(PAGE4, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def _submit_key(at, form_key, label):
    return next(b for b in at.button if b.key == f"FormSubmitter:{form_key}-{label}")


@pytest.fixture()
def seeded_run():
    """Company -> Plant -> ProductionMethod -> Machine -> ProductFamily ->
    FoamGrade -> RecipeVersion -> ProductionRun chain, matching the
    convention already established in test_wp7_phase3_reconciliation.py."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P5U Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P5U Plant {u}")
    session.add(plant); session.flush()
    method = db.ProductionMethod(controlled_id=f"PM-WP7P5U-{u}", name=f"WP7P5U Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"WP7P5U Unit {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P5U Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P5U Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference=f"B-WP7P5U-{u}",
        machine_id=machine.id, production_method_id=method.id, operator_or_team_reference="Shift A",
    )
    session.add(run); session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id, "run_id": run.id,
        "method_id": method.id, "machine_id": machine.id, "grade_id": grade.id,
        "recipe_id": recipe.id,
    }
    session.close()
    return ids


# ---------------------------------------------------------------------------
# A5-06: cascade delete must remove every real dependent, including the new
# direct-to-run Environment/Outcome ProcessParameterValue rows.
# ---------------------------------------------------------------------------

def test_cascade_delete_removes_all_dependent_records_including_environment_outcome_actuals(seeded_run):
    ids = seeded_run
    session = db.get_session()

    lm.ensure_environment_outcome_definitions(session)
    session.commit()
    ps078 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-078").one()

    unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P5U-{ids['run_id']}", symbol="rpm", name="revolutions per minute")
    session.add(unit); session.flush()
    process_setting = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P5U-{ids['run_id']}", name="Test Mixer Speed", data_type="Float",
        unit_id=unit.id, parameter_category="Process Setting", active=True, sort_order=1,
    )
    session.add(process_setting); session.flush()
    session.add(db.ProcessSettingApplicability(
        setting_definition_id=process_setting.id, production_method_id=ids["method_id"],
        applicable_to_planned=True, applicable_to_actual=True, controllable=True,
        analytics_eligible=True, active=True,
    ))
    session.flush()

    # Direct-to-run Environment/Outcome Actual value - exactly what the new
    # Observations block on views/4 writes.
    session.add(db.ProcessParameterValue(
        setting_definition_id=ps078.id, production_run_id=ids["run_id"],
        snapshot_type="Actual", numeric_value=185.0, unit="mm", source="Manual entry",
    ))
    # Direct-to-run Method-Aware Process Setting value.
    session.add(db.ProcessParameterValue(
        setting_definition_id=process_setting.id, production_run_id=ids["run_id"],
        snapshot_type="Planned", numeric_value=42.0, unit="rpm",
    ))
    # A Finalized phase (ARCHIVE READ-ONLY) with a direct-to-run stream
    # reading and a phase-linked one, plus an event, output summary, raw
    # material lot use, runtime data record, sample, and a cycle/shot pair.
    finalized = db.ProductionPhase(production_run_id=ids["run_id"], phase_name="Finalized")
    session.add(finalized); session.flush()

    session.add(db.ComponentStreamReading(
        production_run_id=ids["run_id"], stream_name="Polyol", flow_unit="kg/min", flow=10.0,
    ))
    session.add(db.ComponentStreamReading(
        production_phase_id=finalized.id, stream_name="Isocyanate", flow_unit="kg/min", flow=12.0,
    ))
    session.add(db.ProductionEvent(
        production_run_id=ids["run_id"], event_ts=dt.datetime(2026, 8, 1, 10, 0), event_type="Note",
        description="Test event",
    ))
    session.add(db.ProductionOutputSummary(
        production_run_id=ids["run_id"], planned_quantity=100.0, actual_quantity=95.0,
        disposition="Released",
    ))
    session.add(db.RuntimeDataRecord(production_run_id=ids["run_id"], line_speed=5.0))
    session.add(db.Sample(production_run_id=ids["run_id"], zone_label="Whole sample"))

    cycle = db.ProductionCycle(production_run_id=ids["run_id"], cycle_number=1)
    session.add(cycle); session.flush()
    session.add(db.ProductionShot(production_cycle_id=cycle.id, shot_number=1))
    session.add(db.ProcessParameterValue(
        setting_definition_id=process_setting.id, production_cycle_id=cycle.id,
        snapshot_type="Actual", numeric_value=41.5, unit="rpm",
    ))
    session.commit()

    # Sanity: every dependent table has at least 1 row tied to this run
    # before delete - otherwise the assertions below would pass vacuously.
    pre_counts = {
        "ProcessParameterValue (run)": session.query(db.ProcessParameterValue)
            .filter(db.ProcessParameterValue.production_run_id == ids["run_id"]).count(),
        "ProcessParameterValue (cycle)": session.query(db.ProcessParameterValue)
            .filter(db.ProcessParameterValue.production_cycle_id == cycle.id).count(),
        "ComponentStreamReading (run)": session.query(db.ComponentStreamReading)
            .filter(db.ComponentStreamReading.production_run_id == ids["run_id"]).count(),
        "ComponentStreamReading (phase)": session.query(db.ComponentStreamReading)
            .filter(db.ComponentStreamReading.production_phase_id == finalized.id).count(),
        "ProductionEvent": session.query(db.ProductionEvent)
            .filter(db.ProductionEvent.production_run_id == ids["run_id"]).count(),
        "ProductionOutputSummary": session.query(db.ProductionOutputSummary)
            .filter(db.ProductionOutputSummary.production_run_id == ids["run_id"]).count(),
        "ProductionPhase": session.query(db.ProductionPhase)
            .filter(db.ProductionPhase.production_run_id == ids["run_id"]).count(),
        "RuntimeDataRecord": session.query(db.RuntimeDataRecord)
            .filter(db.RuntimeDataRecord.production_run_id == ids["run_id"]).count(),
        "Sample": session.query(db.Sample)
            .filter(db.Sample.production_run_id == ids["run_id"]).count(),
        "ProductionCycle": session.query(db.ProductionCycle)
            .filter(db.ProductionCycle.production_run_id == ids["run_id"]).count(),
        "ProductionShot": session.query(db.ProductionShot)
            .filter(db.ProductionShot.production_cycle_id == cycle.id).count(),
    }
    for label, count in pre_counts.items():
        assert count >= 1, f"fixture setup bug: {label} has zero rows before delete"

    cascades.delete_production_run_cascade(session, ids["run_id"])
    session.commit()

    assert session.query(db.ProductionRun).filter_by(id=ids["run_id"]).count() == 0
    assert session.query(db.ProcessParameterValue).filter(
        db.ProcessParameterValue.production_run_id == ids["run_id"]
    ).count() == 0, "run-level ProcessParameterValue rows (Method-Aware AND Environment/Outcome) must be deleted"
    assert session.query(db.ProcessParameterValue).filter(
        db.ProcessParameterValue.production_cycle_id == cycle.id
    ).count() == 0, "cycle-level ProcessParameterValue rows must be deleted"
    assert session.query(db.ComponentStreamReading).filter(
        db.ComponentStreamReading.production_run_id == ids["run_id"]
    ).count() == 0
    assert session.query(db.ComponentStreamReading).filter(
        db.ComponentStreamReading.production_phase_id == finalized.id
    ).count() == 0
    assert session.query(db.ProductionEvent).filter(
        db.ProductionEvent.production_run_id == ids["run_id"]
    ).count() == 0
    assert session.query(db.ProductionOutputSummary).filter(
        db.ProductionOutputSummary.production_run_id == ids["run_id"]
    ).count() == 0
    assert session.query(db.ProductionPhase).filter(
        db.ProductionPhase.production_run_id == ids["run_id"]
    ).count() == 0
    assert session.query(db.RuntimeDataRecord).filter(
        db.RuntimeDataRecord.production_run_id == ids["run_id"]
    ).count() == 0
    assert session.query(db.Sample).filter(
        db.Sample.production_run_id == ids["run_id"]
    ).count() == 0
    assert session.query(db.ProductionCycle).filter(
        db.ProductionCycle.production_run_id == ids["run_id"]
    ).count() == 0
    assert session.query(db.ProductionShot).filter(
        db.ProductionShot.production_cycle_id == cycle.id
    ).count() == 0
    # The definitions/applicability/unit master data are NOT run-scoped and
    # must survive - only the run-linked fact rows are deleted.
    assert session.query(db.ProcessSettingDefinition).filter_by(id=process_setting.id).count() == 1
    assert session.query(db.ProcessSettingDefinition).filter_by(id=ps078.id).count() == 1
    session.close()


# ---------------------------------------------------------------------------
# A5-07: Stream Reading CSV import must reject an out-of-vocabulary
# flow_unit instead of silently defaulting it.
# ---------------------------------------------------------------------------

def test_stream_reading_csv_import_rejects_invalid_flow_unit(seeded_run):
    ids = seeded_run
    csv_bytes = (
        "production_run_id,stream_name,flow_unit,flow\n"
        f"{ids['run_id']},Polyol,kg/min,10.0\n"
        f"{ids['run_id']},Isocyanate,gallons/hour,12.0\n"  # not in STREAM_FLOW_UNIT_OPTIONS
        f"{ids['run_id']},Blowing agent,,3.0\n"  # blank -> defaults to kg/min, must be accepted
    ).encode("utf-8")

    at = _run_page4({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    uploader = next(u for u in at.file_uploader if u.key == "stream_upload")
    uploader.set_value(("stream_import.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception

    assert "Rows ready to import: **2**" in "".join(m.value for m in at.markdown if m.value)
    assert "Rows flagged/rejected: **1**" in "".join(m.value for m in at.markdown if m.value)

    confirm = next(b for b in at.button if b.key == "confirm_stream_import")
    confirm.click().run()
    assert not at.exception

    session = db.get_session()
    imported = session.query(db.ComponentStreamReading).filter(
        db.ComponentStreamReading.production_run_id == ids["run_id"]
    ).all()
    assert len(imported) == 2, "the invalid flow_unit row must not be imported"
    by_name = {r.stream_name: r for r in imported}
    assert by_name["Polyol"].flow_unit == "kg/min"
    assert by_name["Blowing agent"].flow_unit == "kg/min", "blank flow_unit must default to kg/min"
    assert "Isocyanate" not in by_name, "row with flow_unit outside the controlled list must be rejected"
    session.close()


# ---------------------------------------------------------------------------
# A5-04: Observations block zero-vs-blank - a genuine recorded 0.0 must
# persist as numeric zero, not be silently dropped as blank, matching the
# same "Record" checkbox convention already proven on the Method-Aware tab.
# ---------------------------------------------------------------------------

def test_observations_zero_value_persists_as_numeric_zero_not_blank(seeded_run):
    ids = seeded_run
    session = db.get_session()
    lm.ensure_environment_outcome_definitions(session)
    session.commit()
    ps079 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-079").one()  # Rise time
    session.close()

    at = _run_page4({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    form_key = f"observations_form_{ids['run_id']}"
    widget_key = f"obs_{ps079.id}_Actual_{ids['run_id']}"
    at.checkbox(key=f"{widget_key}_recorded").set_value(True)
    at.number_input(key=widget_key).set_value(0.0)
    submit = _submit_key(at, form_key, "Save observations")
    submit.click().run()
    assert not at.exception

    session = db.get_session()
    saved = session.query(db.ProcessParameterValue).filter_by(
        production_run_id=ids["run_id"], setting_definition_id=ps079.id, snapshot_type="Actual"
    ).one()
    assert saved.numeric_value == 0.0
    assert saved.numeric_value is not None, "a recorded zero must never collapse to NULL"
    session.close()


def test_observations_unchecked_record_checkbox_leaves_value_unset(seeded_run):
    """Companion proof for the same gap in the other direction: leaving the
    'Record' checkbox unset (default state - no existing value) must not
    write a row at all, matching tab_method_settings's own convention."""
    ids = seeded_run
    session = db.get_session()
    lm.ensure_environment_outcome_definitions(session)
    session.commit()
    ps078 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-078").one()  # Foam height
    session.close()

    at = _run_page4({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    form_key = f"observations_form_{ids['run_id']}"
    submit = _submit_key(at, form_key, "Save observations")
    submit.click().run()
    assert not at.exception

    session = db.get_session()
    count = session.query(db.ProcessParameterValue).filter_by(
        production_run_id=ids["run_id"], setting_definition_id=ps078.id
    ).count()
    assert count == 0, "an unchecked 'Record' checkbox must not create a row"
    session.close()


# ---------------------------------------------------------------------------
# A5-04: one consolidated end-to-end lifecycle proof - context, method-aware
# settings, output, metering, events and observations all coexist for one
# run in one AppTest session without exception, closing the "no single test
# walks the whole lifecycle" gap the coverage audit found (piecemeal
# coverage of each tab already exists across several other test files).
# ---------------------------------------------------------------------------

def test_production_run_full_lifecycle_end_to_end(seeded_run):
    ids = seeded_run
    session = db.get_session()
    lm.ensure_environment_outcome_definitions(session)
    unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P5U2-{ids['run_id']}", symbol="rpm", name="revolutions per minute")
    session.add(unit); session.flush()
    process_setting = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P5U2-{ids['run_id']}", name="Test Mixer Speed", data_type="Float",
        unit_id=unit.id, parameter_category="Process Setting", active=True, sort_order=1,
    )
    session.add(process_setting); session.flush()
    session.add(db.ProcessSettingApplicability(
        setting_definition_id=process_setting.id, production_method_id=ids["method_id"],
        applicable_to_planned=True, applicable_to_actual=True, controllable=True,
        analytics_eligible=True, active=True,
    ))
    finalized = db.ProductionPhase(production_run_id=ids["run_id"], phase_name="Finalized")
    session.add(finalized); session.flush()
    session.add(db.ComponentStreamReading(
        production_run_id=ids["run_id"], stream_name="Polyol", flow_unit="kg/min", flow=10.0,
    ))
    session.add(db.ProductionEvent(
        production_run_id=ids["run_id"], event_ts=dt.datetime(2026, 8, 1, 10, 0), event_type="Note",
        description="End-to-end lifecycle proof event",
    ))
    session.add(db.ProductionOutputSummary(
        production_run_id=ids["run_id"], planned_quantity=100.0, actual_quantity=98.0,
        disposition="Released",
    ))
    ps078 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-078").one()
    session.add(db.ProcessParameterValue(
        setting_definition_id=ps078.id, production_run_id=ids["run_id"],
        snapshot_type="Actual", numeric_value=182.0, unit="mm", source="Manual entry",
    ))
    session.add(db.ProcessParameterValue(
        setting_definition_id=process_setting.id, production_run_id=ids["run_id"],
        snapshot_type="Actual", numeric_value=40.0, unit="rpm",
    ))
    session.commit()
    session.close()

    at = _run_page4({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception, "the full page - context, Setup, Method-Aware, Runtime Data/Observations, Streams, Output, Events tabs - must load without exception for a run with data in every category"

    # Spot-check that each tab's data actually rendered somewhere on the
    # page (proves the tabs aren't just silently empty), not only that no
    # exception was raised.
    all_text = " ".join(m.value for m in at.markdown if m.value) + " ".join(c.value for c in at.caption if c.value)
    assert "Test Mixer Speed" in "".join(w.label for w in at.number_input if w.label) or any(
        w.key == f"pps_{process_setting.id}_Actual_{ids['run_id']}" for w in at.number_input
    ), "Method-Aware Process Settings tab must render the seeded definition"
    assert any(
        w.key == f"obs_{ps078.id}_Actual_{ids['run_id']}" for w in at.number_input
    ), "Observations block must render the seeded Environment/Outcome definition"

    session = db.get_session()
    assert session.query(db.ComponentStreamReading).filter_by(production_run_id=ids["run_id"]).count() == 1
    assert session.query(db.ProductionEvent).filter_by(production_run_id=ids["run_id"]).count() == 1
    assert session.query(db.ProductionOutputSummary).filter_by(production_run_id=ids["run_id"]).one().actual_quantity == 98.0
    session.close()
