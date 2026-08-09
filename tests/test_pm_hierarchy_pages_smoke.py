"""Production Method Hierarchy architecture change (2026-08-09, per Charlie's
spec "PI3_Rigid_Foam_Edition_Architecture_Change_Production_Method_Hierarchy_
for_JC.docx" and Stefan's 5 resolved open decisions) smoke test for the three
pages touched by this batch:

  - pages/1_Plant_Installation_Overview.py: Machine setup's Production
    Method picker, filtered to the plant's activated methods.
  - pages/2_Product_Family_Foam_Grade.py: Foam Grade's method picker +
    many-to-many Machine-assignment multiselect, filtered by method.
  - pages/4_Production_Run_Trial_Record.py: Machine picker filtered to the
    grade's own assigned machines, the Plant/Method/Machine breadcrumb, and
    the immutable production_method_id snapshot set on creation.

Mirrors the established AUTH_DISABLED AppTest pattern (see
test_wp4_recipe_optimization_page_smoke.py and
test_wp6s09_rigid_sample_dimension_fields.py). Deliberately exercises the
Add-record flows rather than the Edit flows on these three pages: all three
pages gate their Edit form behind clickable_table's st.dataframe row-click
selection event, which AppTest has no way to simulate (setting
st.session_state["plant_selected_id"]/"grade_selected_id"/"pr_selected_run_id"
directly gets wiped on the very next run, since clickable_table's own
"idx is None -> pop the selection" branch always fires when no row-click
event exists yet - a testing-harness limitation, not a page defect; the
Add-record flows exercise the exact same PM-hierarchy filtering logic
(activated_methods_for_plant / machines_for_plant_and_method /
effective_top_level_method) since the widgets narrowing each other live
outside st.form on all three pages, same as the Edit forms).

Usage: python -m pytest tests/test_pm_hierarchy_pages_smoke.py
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE1 = os.path.join(APP_DIR, "pages", "1_Plant_Installation_Overview.py")
PAGE2 = os.path.join(APP_DIR, "pages", "2_Product_Family_Foam_Grade.py")
PAGE4 = os.path.join(APP_DIR, "pages", "4_Production_Run_Trial_Record.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_pm_hierarchy():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"PM Hierarchy Smoke Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"PM Hierarchy Smoke Plant {u}")
    session.add(plant); session.flush()

    top_method = db.ProductionMethod(controlled_id=f"PM-SMOKE-400-{u}", name=f"Discontinuous factory-molded PUR/PIR {u}")
    session.add(top_method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=top_method.id, active=True))
    session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"PM Hierarchy Smoke Machine {u}", production_method_id=top_method.id, active=True)
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"PM Hierarchy Smoke Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"PM Hierarchy Smoke Grade {u}", production_method_id=top_method.id)
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()
    session.commit()

    ids = {
        "plant_id": plant.id, "method_id": top_method.id, "method_name": top_method.name,
        "method_controlled_id": top_method.controlled_id, "machine_id": machine.id,
        "machine_name": machine.name, "grade_id": grade.id, "grade_name": grade.grade_name,
    }
    session.close()
    return ids


def _run(page_path):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


def test_add_machine_form_offers_plants_activated_method(seeded_pm_hierarchy):
    ids = seeded_pm_hierarchy
    at = _run(PAGE1)
    assert not at.exception, f"Unhandled exception loading Plant Overview: {at.exception}"

    method_sb = next((sb for sb in at.selectbox if sb.key == "add_machine_method"), None)
    assert method_sb is not None, "Add machine form's Production Method picker not found"
    assert ids["method_name"] in method_sb.options, (
        f"Plant's activated method {ids['method_name']!r} not offered - got {method_sb.options}"
    )


def test_foam_grade_form_offers_method_and_narrows_machines(seeded_pm_hierarchy):
    ids = seeded_pm_hierarchy
    at = _run(PAGE2)
    assert not at.exception, f"Unhandled exception loading Product Family & Foam Grade: {at.exception}"

    method_sb = next((sb for sb in at.selectbox if sb.key == "add_grade_method"), None)
    assert method_sb is not None, "Add foam grade form's Production Method picker not found"
    assert ids["method_name"] in method_sb.options

    machines_ms = next((ms for ms in at.multiselect if ms.label == "Machines this PU Material can be produced on"), None)
    assert machines_ms is not None, "Machine-assignment multiselect not found"
    assert ids["machine_name"] in machines_ms.options, (
        f"Machine tagged to the activated method should be offered - got {machines_ms.options}"
    )


def test_production_run_form_derives_method_snapshot_from_selected_machine(seeded_pm_hierarchy):
    ids = seeded_pm_hierarchy
    at = _run(PAGE4)
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"

    machine_sb = next((sb for sb in at.selectbox if sb.label == "Machine / foaming line"), None)
    assert machine_sb is not None, "Create Production Run form's Machine picker not found"
    machine_display = next((opt for opt in machine_sb.options if ids["machine_name"] in opt), None)
    assert machine_display is not None, f"Grade's assigned machine not offered - got {machine_sb.options}"

    machine_sb.set_value(machine_display)
    submit = next(b for b in at.button if b.label == "Save production run")
    submit.click().run()
    assert not at.exception, f"Unhandled exception submitting Create Production Run: {at.exception}"

    session = db.get_session()
    run = (
        session.query(db.ProductionRun)
        .filter(db.ProductionRun.foam_grade_id == ids["grade_id"])
        .order_by(db.ProductionRun.id.desc())
        .first()
    )
    assert run is not None, "Production run was not created"
    assert run.machine_id == ids["machine_id"]
    assert run.production_method_id == ids["method_id"], (
        "New run's production_method_id snapshot should be derived from the "
        "selected machine's effective top-level method"
    )
    session.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
