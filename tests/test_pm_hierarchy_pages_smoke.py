"""Production Method architecture change (2026-08-09, per Charlie's spec
"PI3_Rigid_Foam_Edition_Architecture_Change_Production_Method_Hierarchy_
for_JC.docx" and Stefan's 5 resolved open decisions; flat-model redesign
2026-08-10, per Charlie's technical completion instruction replacing the
parent/child hierarchy with 7 flat PM-100..PM-700 codes) smoke test for the
pages touched by this batch:

  - pages/31_Production_Equipment.py: Machine setup's Production Method
    picker, filtered to the plant's activated methods. (Moved here from
    pages/1_Plant_Installation_Overview.py 2026-08-10 as part of CR-01's
    UI navigation restructure - see that page's own docstring. PAGE1
    below now points at the pure Plants page and is no longer where this
    picker lives.)
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
Add-record flows exercise the exact same Production Method filtering logic
(activated_methods_for_plant / machines_for_plant_and_method) since the
widgets narrowing each other live outside st.form on all three pages, same
as the Edit forms).

Updated 2026-08-10 for CR-01 follow-up (task #746, per Charlie's CR-04
conditional-acceptance instruction to finish the "Machine" -> "Production
Unit or Cell" customer-facing rename app-wide): the multiselect/selectbox
label assertions below now expect the completed labels ("Production Units
or Cells this PU Material can be produced on", "Production Unit or Cell"),
not the interim labels CR-01 itself shipped with.

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
PAGE30 = os.path.join(APP_DIR, "pages", "30_Production_Methods.py")
PAGE31 = os.path.join(APP_DIR, "pages", "31_Production_Equipment.py")


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
    # FoamGrade.production_method_id removed 2026-08-10 (Charlie's "Database
    # Reset and Clean UAT Baseline" instruction) - method now derives solely
    # from grade.machines, set just below.
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"PM Hierarchy Smoke Grade {u}")
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
    """Updated 2026-08-10 for CR-01: this picker now lives on the new
    Production Equipment page (pages/31_Production_Equipment.py), not the
    Plants page (pages/1_Plant_Installation_Overview.py, which no longer
    has any Machine/equipment UI at all - see that page's docstring)."""
    ids = seeded_pm_hierarchy
    at = _run(PAGE31)
    assert not at.exception, f"Unhandled exception loading Production Equipment: {at.exception}"

    method_sb = next((sb for sb in at.selectbox if sb.key == "add_machine_method"), None)
    assert method_sb is not None, "Add machine form's Production Method picker not found"
    assert ids["method_name"] in method_sb.options, (
        f"Plant's activated method {ids['method_name']!r} not offered - got {method_sb.options}"
    )


def test_plants_page_has_no_equipment_ui(seeded_pm_hierarchy):
    """CR-01 (2026-08-10): pages/1_Plant_Installation_Overview.py is now
    Plants-only - no Machine/equipment Add form and no Production Method
    activation checkboxes (both moved to pages/30/31). Loads clean and
    still shows the seeded plant."""
    ids = seeded_pm_hierarchy
    at = _run(PAGE1)
    assert not at.exception, f"Unhandled exception loading Plants: {at.exception}"
    assert not any(sb.key == "add_machine_method" for sb in at.selectbox), (
        "Plants page should no longer have a machine-assignment Production Method picker"
    )
    assert not any(cb.key and cb.key.startswith("pm_activate_") for cb in at.checkbox), (
        "Plants page should no longer have Production Method activation checkboxes"
    )


def test_production_methods_page_shows_activated_method_and_counts(seeded_pm_hierarchy):
    """New page (pages/30_Production_Methods.py, CR-01): shows the plant's
    activated method with its concise Production Units/Product Grades/
    Recipes counts. The 'Set as operating context' control was removed
    2026-08-10 per CR-04 step 6 (Charlie's instruction to remove the global
    Operating Context concept entirely) - see
    test_cr04_pm_release_gating.py for the release-gating behaviour that
    replaced part of this page's logic."""
    ids = seeded_pm_hierarchy
    at = _run(PAGE30)
    assert not at.exception, f"Unhandled exception loading Production Methods: {at.exception}"

    method_cb = next(
        (cb for cb in at.checkbox if cb.key == f"pm_activate_{ids['plant_id']}_{ids['method_id']}"), None
    )
    assert method_cb is not None, "Activated method's checkbox not found"
    assert method_cb.value is True, "Plant's already-activated method should show checked"

    units_metric = next((m for m in at.metric if m.label == "Production Units"), None)
    grades_metric = next((m for m in at.metric if m.label == "Product Grades"), None)
    recipes_metric = next((m for m in at.metric if m.label == "Recipes"), None)
    assert units_metric is not None and units_metric.value == "1", f"got {units_metric}"
    assert grades_metric is not None and grades_metric.value == "1", f"got {grades_metric}"
    assert recipes_metric is not None and recipes_metric.value == "1", f"got {recipes_metric}"

    assert not any(b.label == "Set as operating context" for b in at.button), (
        "Operating-context button should be gone entirely per CR-04 step 6"
    )


def test_foam_grade_form_offers_machines_across_activated_methods(seeded_pm_hierarchy):
    """Updated 2026-08-10 for Charlie's architecture correction: the Add
    Foam Grade form no longer gates the machine picker behind a separate
    "Production Method *" selectbox (removed - see
    helpers.grade_production_method_label() /
    machines_for_plant_across_activated_methods()). It now offers every
    machine across every one of the plant's activated methods up front,
    each labeled with its own method, so a grade whose machines span more
    than one method can be fully assigned in one save."""
    ids = seeded_pm_hierarchy
    at = _run(PAGE2)
    assert not at.exception, f"Unhandled exception loading Product Family & Foam Grade: {at.exception}"

    assert not any(sb.key == "add_grade_method" for sb in at.selectbox), (
        "Add foam grade form should no longer have a separate Production "
        "Method picker gating the machine multiselect"
    )

    machines_ms = next((ms for ms in at.multiselect if ms.label == "Production Units or Cells this PU Material can be produced on"), None)
    assert machines_ms is not None, "Machine-assignment multiselect not found"
    assert any(ids["machine_name"] in str(opt) for opt in machines_ms.options), (
        f"Machine tagged to the activated method should be offered - got {machines_ms.options}"
    )


def test_production_run_form_derives_method_snapshot_from_selected_machine(seeded_pm_hierarchy):
    ids = seeded_pm_hierarchy
    at = _run(PAGE4)
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"

    machine_sb = next((sb for sb in at.selectbox if sb.label == "Production Unit or Cell"), None)
    assert machine_sb is not None, "Create Production Run form's Production Unit or Cell picker not found"
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
