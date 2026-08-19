"""CR-11 (Standardize Record Create, Edit/Delete and CSV/Excel Import
Functions, 2026-08-12) closeout correction - Group B direct functional
evidence.

CR-11 standardized the tab wording/order on every customer-facing
record-creation page ("Create <record>" / "Edit/Delete <record>" /
"CSV/Excel import <records>", via helpers.cr11_function_tab_labels()).
Charlie's review returned the first closeout package OPEN because it only
had wording/order tests (tab labels match, tab order matches) - not direct,
executed evidence that Create/Edit/Delete/Import actually still work
through the real UI on every applicable page.

This file supplies that missing direct evidence for the four Group B pages
- all four already had working Create/Edit/Delete/Import machinery BEFORE
CR-11 (CR-11 only relabeled/reordered their tabs onto the shared helper; no
new importer was built for any of them), so every test below is a
regression check that the pre-existing machinery still works correctly
under the new tab structure, not new-feature coverage:

  1. views/3_Recipe_Version_Record.py - record type Recipe.
  2. views/5_Physical_Property_Result.py - record type Quality Test Result.
  3. views/6_Quality_Observation.py - record type Quality Issue.
  4. views/9_Samples_Conditioning.py - record type Sample (this page also
     keeps a page-specific 4th "Sample Report" tab CR-11 explicitly allows
     to remain - not touched here).

CORRECTION v2 (2026-08-12, per Charlie's CR11_Closeout_Correction_Review_
Return_to_JC.docx): the block near the bottom of this file adds the two
pieces of direct evidence Charlie's second review found still missing for
all four pages above (neither had either piece before this pass):
  1. Delete permission/safeguards - a role denied "use" access (can_view=
     True, can_use=False) on each page's own page_key cannot actually
     delete a record through the real UI (test_..._view_only_role_cannot_
     delete, one per record type).
  2. Import validation handling - a direct invalid-row-rejection test for
     each importer (test_..._csv_import_validation_rejects_invalid_row,
     one per record type), since none of these four importers are among
     CR-11's six net-new importers (they pre-existed and were only
     relabeled), so they had no such evidence before this pass.

Follows the exact conventions of tests/test_cr10_product_family_grade_split.py
(the reviewer-accepted template for this kind of evidence, from the prior
CR-10 closeout correction):

  - os.environ.setdefault("DATABASE_URL", "sqlite://") + sys.path boilerplate.
  - _clear_relevant_caches(), called from every _reset_schema(), to defend
    against the documented @st.cache_data cross-test id-collision hazard
    (tenant_scope's id-scoping helpers and access_control.denied_page_keys
    cache on small integers alone - company_id/plant_ids/role_id - which
    repeat across tests/files once autoincrement ids restart at 1).
  - db.init_db() + Base.metadata.drop_all/create_all per fixture, seeding
    via SQLAlchemy ORM objects with a uuid.uuid4().hex[:8] suffix on names.
  - The dataframe-widget-own-selection-state technique for Edit/Delete:
    presetting at.session_state[<table_key>] = {"selection": {"rows": [i],
    "columns": []}} BEFORE .run() genuinely drives clickable_table's
    st.dataframe(on_select="rerun", selection_mode="single-row") row-click
    selection in streamlit==1.59.2 - confirmed again below against these
    four different pages, each with its own table key and derived
    "..._selected_id" session_state variable (read from each page's own
    source, not assumed).
  - The file_uploader technique for CSV import:
    at.file_uploader[...].set_value(("name.csv", csv_bytes, "text/csv"))
    before .run() genuinely drives st.file_uploader, paired with each
    page's own "Confirm import" button key.
  - at.secrets["AUTH_DISABLED"] = True for every AppTest run (dev-bypass
    auth - logs in as a synthetic platform-owner/super-admin with
    company_id=None, which tenant_scope's company_picker locks to the one
    real company seeded per fixture, so every scoping helper picks up the
    seeded data with no extra session_state needed).

Usage: python -m pytest tests/test_cr11_functional_evidence_group_b.py -v
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
import db
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_RECIPE = os.path.join(APP_DIR, "views", "3_Recipe_Version_Record.py")
PAGE_QTR = os.path.join(APP_DIR, "views", "5_Physical_Property_Result.py")
PAGE_QI = os.path.join(APP_DIR, "views", "6_Quality_Observation.py")
PAGE_SAMPLE = os.path.join(APP_DIR, "views", "9_Samples_Conditioning.py")


def _clear_relevant_caches():
    """Identical to test_cr10_product_family_grade_split.py's own helper -
    see that file's docstring for the full cache-collision hazard this
    defends against. Every fixture below creates a fresh Company/Plant
    after _reset_schema() restarts autoincrement ids at 1, so this must run
    on every reset or a later test could silently read another test's
    cached scope (same small-int company_id/plant_ids/role_id key)."""
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    _clear_relevant_caches()


def _run(page_path, session_state=None):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


# ---------------------------------------------------------------------------
# Shared seed helper: Company -> Plant -> ProductFamily -> FoamGrade.
# chemistry_id deliberately left unset on the grade (None) so
# reports._is_rigid_grade() reads it as a legacy/flexible-style grade -
# this keeps views/9's rigid_sample_dimension_fields() a no-op (it returns
# {} for a non-rigid grade), which is irrelevant to what CR-11 changed and
# would otherwise add unrelated widgets to work around.
# ---------------------------------------------------------------------------
def _seed_company_plant_family_grade(session, tag):
    company = db.Company(name=f"CR11B Co {tag}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11B Plant {tag}")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"CR11B Family {tag}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"CR11B-Grade-{tag}")
    session.add(grade); session.flush()
    return company, plant, family, grade


def _seed_shrinkage_issue_type(session, tag):
    """Phase 8 Wave A (2026-08-17): the Quality Issue picker on views/6 now
    reads its controlled vocabulary from the QualityIssueType DB master
    (quality_issue_registry.py) instead of quality_issue_taxonomy.py's
    static Python dict - so a test that drives the real category/issue-type
    selectboxes needs a real DB row, not just a name string. Seeds one
    active, Global (no QualityIssueTypeApplicability row) entry matching
    the "Density, shape & dimensional" / "Shrinkage" pair these fixtures
    have always used, so the picker's categories()/lookup() calls resolve
    it exactly as before the cutover."""
    issue = db.QualityIssueType(
        controlled_id=f"QI-CR11B-{tag}", name="Shrinkage",
        issue_category="Density, shape & dimensional", state="active",
    )
    session.add(issue); session.flush()
    return issue


# ===========================================================================
# 1. Recipe (views/3_Recipe_Version_Record.py)
# ===========================================================================

@pytest.fixture()
def seeded_grade_no_recipe():
    """A product grade with zero recipe versions yet - the minimum needed
    to exercise Recipe's own Create tab (which starts a grade's very first
    recipe) and CSV import tab (whose "first row for a grade becomes
    active" branch also needs a grade with no active version yet)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    _company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    session.commit()
    ids = {"plant_id": plant.id, "grade_id": grade.id, "grade_name": grade.grade_name}
    session.close()
    return ids


@pytest.fixture()
def seeded_active_recipe_version():
    """A product grade with one active RecipeVersion already on it (no
    components) - the minimum needed to exercise the "Recipe versions"
    list's own row-selection, in-place header edit, and delete-with-confirm
    flow unambiguously (a single row, no components to complicate the
    dependency-count warning)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    _company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    version = db.RecipeVersion(
        foam_grade_id=grade.id,
        version_label=f"CR11B-RV-{u}",
        change_note="Initial recipe, seeded for CR-11 closeout evidence.",
        approval_status="Draft",
        is_active=True,
        effective_date=dt.date.today(),
    )
    session.add(version); session.flush()
    session.commit()
    ids = {
        "plant_id": plant.id, "grade_id": grade.id, "grade_name": grade.grade_name,
        "version_id": version.id, "version_label": version.version_label,
    }
    session.close()
    return ids


def test_recipe_create_via_form(seeded_grade_no_recipe):
    """Fills the real 'Create Recipe' tab form (Product grade selectbox,
    Version label, Change note) and clicks the real 'Save recipe' submit
    button, confirming this pre-existing Create flow still works exactly
    as before CR-11 only relabeled/reordered its tab. Confirms the new
    RecipeVersion row landed in the database AND was set as the grade's
    active recipe (activate_recipe_version's own job on a grade with no
    prior active version)."""
    ids = seeded_grade_no_recipe
    at = AppTest.from_file(PAGE_RECIPE, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Recipes: {at.exception}"

    version_label_input = next(
        t for t in at.text_input if t.label == "Version label * (e.g. 28-MH-05)" and t.key is None
    )
    version_label_input.set_value("CR11-Correction-New-Recipe")
    change_note_area = next(a for a in at.text_area if a.label == "Change note (why this recipe exists) *")
    change_note_area.set_value("New formulation created for CR-11 closeout evidence.")
    save_btn = next(b for b in at.button if b.label == "Save recipe")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new recipe: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.RecipeVersion)
        .filter(
            db.RecipeVersion.foam_grade_id == ids["grade_id"],
            db.RecipeVersion.version_label == "CR11-Correction-New-Recipe",
        )
        .first()
    )
    assert created is not None, "New recipe version was not persisted"
    assert created.is_active, "The first recipe version created for a grade should become its active recipe"
    session.close()


def test_recipe_selection_edit_and_delete_via_ui(seeded_active_recipe_version):
    """Presets the recipe_versions_table dataframe widget's OWN on_select
    state (not rv_selected_id directly) to select row 0 before .run() -
    proving clickable_table's row-click selection is genuinely drivable
    against this page's "Recipe versions" list. Then edits the selected
    version's own header (its 'Edit details / delete this recipe version'
    expander form) and confirms the new label persisted, then deletes it
    through the real confirm-checkbox + delete-button flow
    (delete_with_confirm, calling cascades.delete_recipe_version_cascade)
    and confirms the cascade removed it."""
    ids = seeded_active_recipe_version
    at = AppTest.from_file(PAGE_RECIPE, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["recipe_versions_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["rv_selected_id"] == ids["version_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded recipe version"
    )
    assert at.session_state["rv_selected_kind"] == "version"

    # --- Edit ---
    label_input = next(t for t in at.text_input if t.key == f"edit_version_label_{ids['version_id']}")
    label_input.set_value("CR11-Correction-Edited-Recipe")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the recipe version: {at.exception}"

    session = db.get_session()
    edited = session.get(db.RecipeVersion, ids["version_id"])
    assert edited.version_label == "CR11-Correction-Edited-Recipe", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["recipe_versions_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"version_{ids['version_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"version_{ids['version_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the recipe version: {at.exception}"

    session = db.get_session()
    assert session.get(db.RecipeVersion, ids["version_id"]) is None, "Delete did not remove the recipe version"
    session.close()


def test_recipe_csv_import_via_ui(seeded_grade_no_recipe):
    """Drives the real st.file_uploader widget (key='recipe_version_upload')
    with an in-memory CSV of recipe version HEADER rows (this tab's own
    import - not the separate 'Bulk import recipe components' section
    further down the page), then the real 'Confirm import (recipe
    versions)' button, and confirms the row persisted and was auto-
    activated (the grade had no active recipe yet, so its first imported
    row becomes active per the page's own import logic)."""
    ids = seeded_grade_no_recipe
    at = AppTest.from_file(PAGE_RECIPE, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        f"foam_grade_id,version_label,change_note\n"
        f"{ids['grade_id']},CR11-Correction-Imported-Recipe,from CSV\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "recipe_version_upload")
    uploader.set_value(("recipe_versions.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_recipe_version_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.RecipeVersion)
        .filter(
            db.RecipeVersion.foam_grade_id == ids["grade_id"],
            db.RecipeVersion.version_label == "CR11-Correction-Imported-Recipe",
        )
        .first()
    )
    assert imported is not None, "Imported recipe version was not persisted"
    assert imported.is_active, "First imported version for a grade with no active recipe should become active"
    session.close()


# ===========================================================================
# 2. Quality Test Result (views/5_Physical_Property_Result.py) - record
# type "Quality Test Result" (customer-facing title "Test Results" since
# CR-01's label-only rename; backend model PhysicalPropertyResult).
# ===========================================================================

@pytest.fixture()
def seeded_run_with_property():
    """A production run (with its own required plant/grade/recipe-version
    chain) plus one PhysicalPropertyDefinition - the minimum needed to
    exercise the Create tab (needs a run to record against and a property
    to pick) and the CSV import tab (needs a property_name to match), with
    zero PhysicalPropertyResult rows yet."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    _company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    version = db.RecipeVersion(
        foam_grade_id=grade.id, version_label=f"CR11B-RV-{u}", change_note="For run seeding.",
        approval_status="Approved", is_active=True,
    )
    session.add(version); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=version.id,
        run_date=dt.date.today(), batch_reference=f"CR11B-Run-{u}",
    )
    session.add(run); session.flush()
    prop_def = db.PhysicalPropertyDefinition(
        name=f"CR11B Density {u}", what_it_measures="Test property for CR-11 closeout evidence.",
        category="Technical", is_common=False, sort_order=1,
    )
    session.add(prop_def); session.flush()
    session.commit()
    ids = {
        "plant_id": plant.id, "grade_id": grade.id, "run_id": run.id,
        "property_definition_id": prop_def.id, "property_name": prop_def.name,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_quality_test_result():
    """Extends seeded_run_with_property with one PhysicalPropertyResult row
    (seeded directly via the ORM, not through the form - matching the
    template's own pattern of seeding the row to be edited/deleted
    directly, since the Create flow is proven by its own separate test)
    - the minimum needed to exercise the results table's own row-selection,
    edit, and delete flow unambiguously."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    _company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    version = db.RecipeVersion(
        foam_grade_id=grade.id, version_label=f"CR11B-RV-{u}", change_note="For run seeding.",
        approval_status="Approved", is_active=True,
    )
    session.add(version); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=version.id,
        run_date=dt.date.today(), batch_reference=f"CR11B-Run-{u}",
    )
    session.add(run); session.flush()
    prop_def = db.PhysicalPropertyDefinition(
        name=f"CR11B Density {u}", what_it_measures="Test property for CR-11 closeout evidence.",
        category="Technical", is_common=False, sort_order=1,
    )
    session.add(prop_def); session.flush()
    result = db.PhysicalPropertyResult(
        production_run_id=run.id, property_definition_id=prop_def.id, property_name=prop_def.name,
        target_value=30.0, actual_value=31.5, unit="kg/m3", pass_fail="Pass",
        test_method="Original Method", replicate_no=1, tested_at=dt.date.today(),
        notes="Original notes.",
    )
    session.add(result); session.flush()
    session.commit()
    ids = {
        "plant_id": plant.id, "grade_id": grade.id, "run_id": run.id,
        "property_definition_id": prop_def.id, "property_name": prop_def.name,
        "result_id": result.id,
    }
    session.close()
    return ids


def test_quality_test_result_create_via_form(seeded_run_with_property):
    """Fills the real 'Add quality test result' expander/form inside the
    Create tab (typed method/unit, target/actual values - the Measuring
    method and Unit of measure selectboxes are left at their empty-list
    default since no PhysicalPropertyMethod/UOM master rows were seeded,
    exactly like a real plant that hasn't loaded that master list yet
    would use the 'type a method/unit not listed above' escape hatch) and
    clicks the real 'Save result' submit button, then confirms the new row
    landed in the database against the seeded production run."""
    ids = seeded_run_with_property
    at = AppTest.from_file(PAGE_QTR, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Test Results: {at.exception}"

    method_other = next(t for t in at.text_input if t.label == "Or type a method not listed above" and t.key is None)
    method_other.set_value("CR11 Test Method")
    uom_other = next(t for t in at.text_input if t.label == "Or type a unit not listed above" and t.key is None)
    uom_other.set_value("kg/m3")
    target_value = next(n for n in at.number_input if n.label == "Target value" and n.key is None)
    target_value.set_value(28.0)
    actual_value = next(n for n in at.number_input if n.label == "Actual value" and n.key is None)
    actual_value.set_value(29.2)
    save_btn = next(b for b in at.button if b.label == "Save result")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new quality test result: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.PhysicalPropertyResult)
        .filter(
            db.PhysicalPropertyResult.production_run_id == ids["run_id"],
            db.PhysicalPropertyResult.test_method == "CR11 Test Method",
        )
        .first()
    )
    assert created is not None, "New quality test result was not persisted"
    assert created.unit == "kg/m3"
    assert created.actual_value == 29.2
    session.close()


def test_quality_test_result_selection_edit_and_delete_via_ui(seeded_quality_test_result):
    """Presets the results_table dataframe widget's OWN on_select state to
    select row 0 before .run() - the Edit/Delete tab's own row-selection,
    unambiguously distinct from the Create tab's own (always-rendered,
    keyless) form fields since Streamlit renders every tab's content on
    every run. Edits the selected result's Notes through the real Edit
    form (key=f'edit_result_{id}') and confirms it persisted, then deletes
    it through the real confirm-checkbox + delete-button flow and confirms
    the row is gone."""
    ids = seeded_quality_test_result
    at = AppTest.from_file(PAGE_QTR, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["results_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["result_selected_id"] == ids["result_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded result"
    )

    # --- Edit ---
    notes_area = next(a for a in at.text_area if a.key == f"edit_result_notes_{ids['result_id']}")
    notes_area.set_value("Edited via CR-11 closeout evidence test.")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the quality test result: {at.exception}"

    session = db.get_session()
    edited = session.get(db.PhysicalPropertyResult, ids["result_id"])
    assert edited.notes == "Edited via CR-11 closeout evidence test.", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["results_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"result_{ids['result_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"result_{ids['result_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the quality test result: {at.exception}"

    session = db.get_session()
    assert session.get(db.PhysicalPropertyResult, ids["result_id"]) is None, "Delete did not remove the result"
    session.close()


def test_quality_test_result_csv_import_via_ui(seeded_run_with_property):
    """Drives the real st.file_uploader widget (key='result_upload') with a
    CSV row whose property_name matches the seeded PhysicalPropertyDefinition
    (case-insensitively, per the page's own import matching) and whose
    production_run_id is the seeded run's - the exactly-one-parent-FK rule
    this page's import enforces - then the real 'Confirm import' button,
    confirming the row persisted with the imported test_method/unit/actual_value."""
    ids = seeded_run_with_property
    at = AppTest.from_file(PAGE_QTR, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        f"property_name,test_method,unit,actual_value,production_run_id\n"
        f"{ids['property_name'].upper()},CSV Import Method,kg/m3,32.4,{ids['run_id']}\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "result_upload")
    uploader.set_value(("results.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_result_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.PhysicalPropertyResult)
        .filter(
            db.PhysicalPropertyResult.production_run_id == ids["run_id"],
            db.PhysicalPropertyResult.test_method == "CSV Import Method",
        )
        .first()
    )
    assert imported is not None, "Imported quality test result was not persisted"
    assert imported.unit == "kg/m3"
    assert imported.actual_value == 32.4
    session.close()


# ===========================================================================
# 3. Quality Issue (views/6_Quality_Observation.py) - record type "Quality
# Issue" (backend model QualityObservation, unchanged per CR-01's
# label-only rename).
# ===========================================================================

@pytest.fixture()
def seeded_run_for_quality_issue():
    """A production run with its own required plant/grade/recipe-version
    chain - the minimum needed to exercise Quality Issue's Create tab (needs
    a run to record against) and CSV import tab, with zero
    QualityObservation rows yet."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    _company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    _seed_shrinkage_issue_type(session, u)
    version = db.RecipeVersion(
        foam_grade_id=grade.id, version_label=f"CR11B-RV-{u}", change_note="For run seeding.",
        approval_status="Approved", is_active=True,
    )
    session.add(version); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=version.id,
        run_date=dt.date.today(), batch_reference=f"CR11B-Run-{u}",
    )
    session.add(run); session.flush()
    session.commit()
    ids = {"plant_id": plant.id, "grade_id": grade.id, "run_id": run.id}
    session.close()
    return ids


@pytest.fixture()
def seeded_quality_issue():
    """Extends seeded_run_for_quality_issue with one QualityObservation row
    (seeded directly via the ORM) - the minimum needed to exercise the
    issues table's own row-selection, edit, and delete flow unambiguously.
    observation_type is a real controlled taxonomy name ("Shrinkage", under
    "Density, shape & dimensional" - see quality_issue_taxonomy.py) so the
    Edit form's _issue_type_picker() resolves a real match rather than
    falling back to the "Other / not yet classified" escape hatch."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    _company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    _seed_shrinkage_issue_type(session, u)
    version = db.RecipeVersion(
        foam_grade_id=grade.id, version_label=f"CR11B-RV-{u}", change_note="For run seeding.",
        approval_status="Approved", is_active=True,
    )
    session.add(version); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=version.id,
        run_date=dt.date.today(), batch_reference=f"CR11B-Run-{u}",
    )
    session.add(run); session.flush()
    obs = db.QualityObservation(
        production_run_id=run.id, observation_type="Shrinkage", severity="Medium", frequency="One-off",
        location_in_block="Original location", confidence_level="Likely", observed_at=dt.date.today(),
    )
    session.add(obs); session.flush()
    session.commit()
    ids = {"plant_id": plant.id, "grade_id": grade.id, "run_id": run.id, "obs_id": obs.id}
    session.close()
    return ids


def test_quality_issue_create_via_form(seeded_run_for_quality_issue):
    """Drives the real, controlled Issue category/Issue type selectboxes
    outside the form (key='add_obs_category' / 'add_obs_issue_name') -
    these sit outside st.form so a category change reruns immediately and
    narrows the issue-type options, exactly as a real user picking a
    category then a type would see - selecting "Density, shape &
    dimensional" / "Shrinkage" from the real controlled taxonomy, then
    fills the real Severity selectbox and Location text_input inside the
    form and clicks the real 'Save issue' submit button. Confirms the new
    QualityObservation row landed in the database against the seeded
    production run with exactly the picked issue type and severity."""
    ids = seeded_run_for_quality_issue
    at = AppTest.from_file(PAGE_QI, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Quality Issues: {at.exception}"

    category_sb = next(sb for sb in at.selectbox if sb.key == "add_obs_category")
    category_sb.set_value("Density, shape & dimensional")
    at.run()
    assert not at.exception, f"Unhandled exception after picking an issue category: {at.exception}"

    issue_sb = next(sb for sb in at.selectbox if sb.key == "add_obs_issue_name")
    assert issue_sb.value == "Shrinkage", (
        "'Shrinkage' is the first entry in the 'Density, shape & dimensional' category and should "
        f"be the picker's default once that category is selected - got {issue_sb.value!r}"
    )
    severity_sb = next(sb for sb in at.selectbox if sb.label == "Severity" and sb.key is None)
    severity_sb.set_value("High")
    # CR-22 / F22-03 (AF22-01): label renamed "Location in block" -> "Observed location".
    location_input = next(t for t in at.text_input if t.label == "Observed location" and t.key is None)
    location_input.set_value("Top corner")
    save_btn = next(b for b in at.button if b.label == "Save issue")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new quality issue: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.QualityObservation)
        .filter(db.QualityObservation.production_run_id == ids["run_id"], db.QualityObservation.observation_type == "Shrinkage")
        .first()
    )
    assert created is not None, "New quality issue was not persisted"
    assert created.severity == "High"
    assert created.location_in_block == "Top corner"
    session.close()


def test_quality_issue_selection_edit_and_delete_via_ui(seeded_quality_issue):
    """Presets the obs_table dataframe widget's OWN on_select state to
    select row 0 before .run(). Edits the selected issue's Location in
    block through the real Edit form (key=f'edit_obs_{id}') and confirms
    it persisted, then deletes it through the real confirm-checkbox +
    delete-button flow and confirms the row is gone."""
    ids = seeded_quality_issue
    at = AppTest.from_file(PAGE_QI, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["obs_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["obs_selected_id"] == ids["obs_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded quality issue"
    )

    # --- Edit ---
    location_input = next(t for t in at.text_input if t.key == f"edit_obs_location_{ids['obs_id']}")
    location_input.set_value("Edited location via CR-11 closeout evidence test")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the quality issue: {at.exception}"

    session = db.get_session()
    edited = session.get(db.QualityObservation, ids["obs_id"])
    assert edited.location_in_block == "Edited location via CR-11 closeout evidence test", (
        "Edit did not persist to the database"
    )
    session.close()

    # --- Delete ---
    at.session_state["obs_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"obs_{ids['obs_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"obs_{ids['obs_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the quality issue: {at.exception}"

    session = db.get_session()
    assert session.get(db.QualityObservation, ids["obs_id"]) is None, "Delete did not remove the quality issue"
    session.close()


def test_quality_issue_csv_import_via_ui(seeded_run_for_quality_issue):
    """Drives the real st.file_uploader widget (key='observation_upload')
    with a CSV row whose observation_type matches a real controlled
    taxonomy name case-insensitively ("shrinkage" -> canonical "Shrinkage",
    per the page's own quality_issue_taxonomy.lookup_case_insensitive() import
    check) and whose production_run_id is the seeded run's, then the real
    'Confirm import' button, confirming the row persisted with the
    canonical (not the CSV's lowercase) spelling."""
    ids = seeded_run_for_quality_issue
    at = AppTest.from_file(PAGE_QI, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        f"observation_type,production_run_id,severity\n"
        f"shrinkage,{ids['run_id']},High\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "observation_upload")
    uploader.set_value(("issues.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_observation_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.QualityObservation)
        .filter(db.QualityObservation.production_run_id == ids["run_id"], db.QualityObservation.observation_type == "Shrinkage")
        .first()
    )
    assert imported is not None, "Imported quality issue was not persisted"
    assert imported.severity == "High"
    session.close()


# ===========================================================================
# 4. Sample (views/9_Samples_Conditioning.py) - record type "Sample".
# This page also keeps a page-specific 4th "Sample Report" tab, which
# CR-11 explicitly allows to remain beyond the standard 3 - not touched by
# any test below, per this correction's scope.
# ===========================================================================

@pytest.fixture()
def seeded_run_for_sample():
    """A production run with its own required plant/grade/recipe-version
    chain - the minimum needed to exercise Sample's Create tab (needs a run
    to record the sample against) and CSV import tab, with zero Sample rows
    yet. The grade's chemistry_id is left unset (non-rigid), so
    rigid_sample_dimension_fields() renders nothing extra on the Create/Edit
    forms - irrelevant to what CR-11 changed on this page."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    _company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    version = db.RecipeVersion(
        foam_grade_id=grade.id, version_label=f"CR11B-RV-{u}", change_note="For run seeding.",
        approval_status="Approved", is_active=True,
    )
    session.add(version); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=version.id,
        run_date=dt.date.today(), batch_reference=f"CR11B-Run-{u}",
    )
    session.add(run); session.flush()
    session.commit()
    ids = {"plant_id": plant.id, "grade_id": grade.id, "run_id": run.id}
    session.close()
    return ids


@pytest.fixture()
def seeded_sample():
    """Extends seeded_run_for_sample with one Sample row (seeded directly
    via the ORM) - the minimum needed to exercise the samples table's own
    row-selection, edit, and delete flow unambiguously."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    _company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    version = db.RecipeVersion(
        foam_grade_id=grade.id, version_label=f"CR11B-RV-{u}", change_note="For run seeding.",
        approval_status="Approved", is_active=True,
    )
    session.add(version); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=version.id,
        run_date=dt.date.today(), batch_reference=f"CR11B-Run-{u}",
    )
    session.add(run); session.flush()
    sample = db.Sample(
        production_run_id=run.id, zone_label="Top", sample_ts=dt.datetime.now(), notes="Original notes.",
    )
    session.add(sample); session.flush()
    session.commit()
    ids = {"plant_id": plant.id, "grade_id": grade.id, "run_id": run.id, "sample_id": sample.id}
    session.close()
    return ids


def test_sample_create_via_form(seeded_run_for_sample):
    """Fills the real Create tab (Sample Location Reference selectbox
    inside the 'add_sample' form) and clicks the real 'Save sample' submit
    button, then confirms the new row landed in the database against the
    seeded production run."""
    ids = seeded_run_for_sample
    at = AppTest.from_file(PAGE_SAMPLE, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Production Samples: {at.exception}"

    zone_sb = next(sb for sb in at.selectbox if sb.label == "Sample Location Reference *" and sb.key is None)
    zone_sb.set_value("Middle")
    save_btn = next(b for b in at.button if b.label == "Save sample")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new sample: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.Sample)
        .filter(db.Sample.production_run_id == ids["run_id"], db.Sample.zone_label == "Middle")
        .first()
    )
    assert created is not None, "New sample was not persisted"
    session.close()


def test_sample_selection_edit_and_delete_via_ui(seeded_sample):
    """Presets the samples_table dataframe widget's OWN on_select state to
    select row 0 before .run(). Edits the selected sample's Notes through
    the real Edit form (key=f'edit_sample_{id}') and confirms it persisted,
    then deletes it through the real confirm-checkbox + delete-button flow
    and confirms the row is gone."""
    ids = seeded_sample
    at = AppTest.from_file(PAGE_SAMPLE, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["samples_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["sample_selected_id"] == ids["sample_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded sample"
    )

    # --- Edit ---
    notes_area = next(a for a in at.text_area if a.key == f"edit_sample_notes_{ids['sample_id']}")
    notes_area.set_value("Edited via CR-11 closeout evidence test.")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the sample: {at.exception}"

    session = db.get_session()
    edited = session.get(db.Sample, ids["sample_id"])
    assert edited.notes == "Edited via CR-11 closeout evidence test.", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["samples_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"sample_{ids['sample_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"sample_{ids['sample_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the sample: {at.exception}"

    session = db.get_session()
    assert session.get(db.Sample, ids["sample_id"]) is None, "Delete did not remove the sample"
    session.close()


def test_sample_csv_import_via_ui(seeded_run_for_sample):
    """Drives the real st.file_uploader widget (key='sample_upload') with a
    CSV row whose production_run_id is the seeded run's and a non-empty
    zone_label, then the real 'Confirm import' button, confirming the row
    persisted."""
    ids = seeded_run_for_sample
    at = AppTest.from_file(PAGE_SAMPLE, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = f"production_run_id,zone_label\n{ids['run_id']},Bottom\n".encode()
    uploader = next(u for u in at.file_uploader if u.key == "sample_upload")
    uploader.set_value(("samples.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_sample_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.Sample)
        .filter(db.Sample.production_run_id == ids["run_id"], db.Sample.zone_label == "Bottom")
        .first()
    )
    assert imported is not None, "Imported sample was not persisted"
    session.close()


# ===========================================================================
# CR-11 CORRECTION v2 (2026-08-12, per Charlie's CR11_Closeout_Correction_
# Review_Return_to_JC.docx) - gaps 1 and 2, for the same four Group B pages.
#
# Gap 1 - Delete permission/safeguards: direct evidence that a role denied
# "use" access (can_view=True, can_use=False - access_control.py's "View
# only" state) on each of these four pages' own page_key cannot actually
# delete a record through the real UI, not just that can_use_page() itself
# returns False in isolation. Follows tests/test_cr10_product_family_grade_
# split.py's own view_only_role_fixture / _run_as_role pattern exactly: a
# real db.Role + db.RolePagePermission row, presetting
# role_id/is_super_admin/is_platform_owner/company_id in session_state
# BEFORE .run() to override the AUTH_DISABLED dev-bypass's own setdefault()
# calls (see auth.py's require_login docstring - setdefault() only fills a
# session_state key that isn't already set, so presetting it first makes
# require_login() leave it alone).
#
# Gap 2 - Import validation handling: none of these four pages' importers
# are among CR-11's six net-new importers (all four pre-existed CR-11 and
# were only relabeled/reordered onto the shared tab helper), so unlike
# those six, they had no direct invalid-row-rejection evidence anywhere in
# this project before this correction - only the valid-import path (the
# four "..._csv_import_via_ui" tests above). Each test below uploads one
# row that fails that importer's own bad-row check (read from each page's
# own source, not assumed) and confirms the row is rejected: the "Confirm
# import" button doesn't render (every importer on these four pages gates
# it behind `if good_rows and st.button(...)`, so zero good rows means the
# button call itself never executes - short-circuit, not a disabled
# button) and the row count is unchanged.
# ===========================================================================

def _run_as_role(page_path, ids, session_state=None):
    """Identical to test_cr10_product_family_grade_split.py's own
    _run_as_role helper - overrides the AUTH_DISABLED dev-bypass's own
    is_super_admin=True / is_platform_owner=True / role_id=None /
    company_id=None setdefault() defaults with a real, restricted role
    BEFORE .run()."""
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["role_id"] = ids["role_id"]
    at.session_state["is_super_admin"] = False
    at.session_state["is_platform_owner"] = False
    at.session_state["company_id"] = ids["company_id"]
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


# ---------------------------------------------------------------------------
# Gap 1.1 - Recipe (page_key "recipes"). The "Edit details / delete this
# recipe version" expander gates delete_with_confirm() itself behind
# `if not page_usable: caption else: ... delete_with_confirm(...)` (see
# views/3_Recipe_Version_Record.py) - the "Recipe versions" list itself
# (and its row selection) is NOT gated on page_usable, so a view-only role
# can still select and view a row, just not delete it.
# ---------------------------------------------------------------------------

@pytest.fixture()
def view_only_role_fixture_recipe():
    """One company/plant/grade with one active RecipeVersion (same shape
    as seeded_active_recipe_version above), plus a real Role with an
    explicit RolePagePermission row denying use on page_key "recipes"
    (can_view=True, can_use=False) - direct evidence against the real
    can_use_page()/RolePagePermission plumbing views/3 actually calls, not
    a hypothetical role."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    version = db.RecipeVersion(
        foam_grade_id=grade.id,
        version_label=f"CR11B-RV-{u}",
        change_note="Seeded for CR-11 correction v2 delete-permission evidence.",
        approval_status="Draft",
        is_active=True,
        effective_date=dt.date.today(),
    )
    session.add(version); session.flush()
    role = db.Role(company_id=company.id, name="CR11B Correction View Only Recipe", is_builtin=False)
    session.add(role); session.flush()
    session.add(db.RolePagePermission(role_id=role.id, page_key="recipes", can_view=True, can_use=False))
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id, "grade_id": grade.id,
        "version_id": version.id, "role_id": role.id,
    }
    session.close()
    return ids


def test_recipe_view_only_role_cannot_delete(view_only_role_fixture_recipe):
    """CR-11 correction v2 item 1, page_key "recipes": with a role denied
    'use' on this page, the real 'Recipe versions' list lets the role
    select the seeded version, but its 'Edit details / delete this recipe
    version' expander must not render the real confirm-checkbox/delete-
    button pair - direct UI evidence, not just a can_use_page() check in
    isolation - and the version must still exist in the database
    afterward."""
    ids = view_only_role_fixture_recipe
    session = db.get_session()
    assert not access_control.can_use_page("recipes", role_id=ids["role_id"], session=session, is_super_admin=False)
    session.close()

    at = _run_as_role(
        PAGE_RECIPE, ids,
        session_state={"recipe_versions_table": {"selection": {"rows": [0], "columns": []}}},
    )
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["rv_selected_id"] == ids["version_id"], (
        "The view-only role should still be able to select and view the seeded recipe version"
    )

    assert not any(c.key == f"version_{ids['version_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the delete confirm-checkbox"
    )
    assert not any(b.key == f"version_{ids['version_id']}_btn" for b in at.button), (
        "View-only role should not see the delete button"
    )
    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()

    session = db.get_session()
    assert session.get(db.RecipeVersion, ids["version_id"]) is not None, (
        "The recipe version must still exist - a view-only role must not be able to delete it"
    )
    session.close()


# ---------------------------------------------------------------------------
# Gap 1.2 - Quality Test Result (page_key "quality_test_result").
# views/5_Physical_Property_Result.py gates delete_with_confirm() behind
# `if page_usable: delete_with_confirm(...) else: st.caption(...)` inside
# the Edit/Delete tab's selected-row branch - the browsable results table
# and row selection above it are not gated.
# ---------------------------------------------------------------------------

@pytest.fixture()
def view_only_role_fixture_qtr():
    """Same seed shape as seeded_quality_test_result above, plus a real
    Role denying use on page_key "quality_test_result"."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    version = db.RecipeVersion(
        foam_grade_id=grade.id, version_label=f"CR11B-RV-{u}", change_note="For run seeding.",
        approval_status="Approved", is_active=True,
    )
    session.add(version); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=version.id,
        run_date=dt.date.today(), batch_reference=f"CR11B-Run-{u}",
    )
    session.add(run); session.flush()
    prop_def = db.PhysicalPropertyDefinition(
        name=f"CR11B Density {u}", what_it_measures="Test property for CR-11 closeout evidence.",
        category="Technical", is_common=False, sort_order=1,
    )
    session.add(prop_def); session.flush()
    result = db.PhysicalPropertyResult(
        production_run_id=run.id, property_definition_id=prop_def.id, property_name=prop_def.name,
        target_value=30.0, actual_value=31.5, unit="kg/m3", pass_fail="Pass",
        test_method="Original Method", replicate_no=1, tested_at=dt.date.today(),
        notes="Seeded for CR-11 correction v2 delete-permission evidence.",
    )
    session.add(result); session.flush()
    role = db.Role(company_id=company.id, name="CR11B Correction View Only QTR", is_builtin=False)
    session.add(role); session.flush()
    session.add(db.RolePagePermission(role_id=role.id, page_key="quality_test_result", can_view=True, can_use=False))
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id, "grade_id": grade.id, "run_id": run.id,
        "result_id": result.id, "role_id": role.id,
    }
    session.close()
    return ids


def test_quality_test_result_view_only_role_cannot_delete(view_only_role_fixture_qtr):
    """CR-11 correction v2 item 1, page_key "quality_test_result": same
    evidence as the Recipe test above - the view-only role can select the
    seeded result, but sees neither the delete confirm-checkbox nor the
    delete button, and the result still exists afterward."""
    ids = view_only_role_fixture_qtr
    session = db.get_session()
    assert not access_control.can_use_page(
        "quality_test_result", role_id=ids["role_id"], session=session, is_super_admin=False
    )
    session.close()

    at = _run_as_role(
        PAGE_QTR, ids, session_state={"results_table": {"selection": {"rows": [0], "columns": []}}},
    )
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["result_selected_id"] == ids["result_id"], (
        "The view-only role should still be able to select and view the seeded result"
    )

    assert not any(c.key == f"result_{ids['result_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the delete confirm-checkbox"
    )
    assert not any(b.key == f"result_{ids['result_id']}_btn" for b in at.button), (
        "View-only role should not see the delete button"
    )
    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()

    session = db.get_session()
    assert session.get(db.PhysicalPropertyResult, ids["result_id"]) is not None, (
        "The result must still exist - a view-only role must not be able to delete it"
    )
    session.close()


# ---------------------------------------------------------------------------
# Gap 1.3 - Quality Issue (page_key "quality_issue"). Same delete gating
# pattern as Quality Test Result, on views/6_Quality_Observation.py.
# ---------------------------------------------------------------------------

@pytest.fixture()
def view_only_role_fixture_qi():
    """Same seed shape as seeded_quality_issue above, plus a real Role
    denying use on page_key "quality_issue"."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    _seed_shrinkage_issue_type(session, u)
    version = db.RecipeVersion(
        foam_grade_id=grade.id, version_label=f"CR11B-RV-{u}", change_note="For run seeding.",
        approval_status="Approved", is_active=True,
    )
    session.add(version); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=version.id,
        run_date=dt.date.today(), batch_reference=f"CR11B-Run-{u}",
    )
    session.add(run); session.flush()
    obs = db.QualityObservation(
        production_run_id=run.id, observation_type="Shrinkage", severity="Medium", frequency="One-off",
        location_in_block="Seeded location", confidence_level="Likely", observed_at=dt.date.today(),
    )
    session.add(obs); session.flush()
    role = db.Role(company_id=company.id, name="CR11B Correction View Only QI", is_builtin=False)
    session.add(role); session.flush()
    session.add(db.RolePagePermission(role_id=role.id, page_key="quality_issue", can_view=True, can_use=False))
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id, "grade_id": grade.id, "run_id": run.id,
        "obs_id": obs.id, "role_id": role.id,
    }
    session.close()
    return ids


def test_quality_issue_view_only_role_cannot_delete(view_only_role_fixture_qi):
    """CR-11 correction v2 item 1, page_key "quality_issue": same evidence
    pattern - the view-only role can select the seeded issue, but sees
    neither the delete confirm-checkbox nor the delete button, and the
    issue still exists afterward."""
    ids = view_only_role_fixture_qi
    session = db.get_session()
    assert not access_control.can_use_page(
        "quality_issue", role_id=ids["role_id"], session=session, is_super_admin=False
    )
    session.close()

    at = _run_as_role(
        PAGE_QI, ids, session_state={"obs_table": {"selection": {"rows": [0], "columns": []}}},
    )
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["obs_selected_id"] == ids["obs_id"], (
        "The view-only role should still be able to select and view the seeded quality issue"
    )

    assert not any(c.key == f"obs_{ids['obs_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the delete confirm-checkbox"
    )
    assert not any(b.key == f"obs_{ids['obs_id']}_btn" for b in at.button), (
        "View-only role should not see the delete button"
    )
    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()

    session = db.get_session()
    assert session.get(db.QualityObservation, ids["obs_id"]) is not None, (
        "The quality issue must still exist - a view-only role must not be able to delete it"
    )
    session.close()


# ---------------------------------------------------------------------------
# Gap 1.4 - Sample (page_key "samples_conditioning" - unchanged identity in
# the User Roles matrix per this page's own module docstring, even though
# its title/scope changed). Same delete gating pattern, on
# views/9_Samples_Conditioning.py.
# ---------------------------------------------------------------------------

@pytest.fixture()
def view_only_role_fixture_sample():
    """Same seed shape as seeded_sample above, plus a real Role denying
    use on page_key "samples_conditioning"."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company, plant, _family, grade = _seed_company_plant_family_grade(session, u)
    version = db.RecipeVersion(
        foam_grade_id=grade.id, version_label=f"CR11B-RV-{u}", change_note="For run seeding.",
        approval_status="Approved", is_active=True,
    )
    session.add(version); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=version.id,
        run_date=dt.date.today(), batch_reference=f"CR11B-Run-{u}",
    )
    session.add(run); session.flush()
    sample = db.Sample(
        production_run_id=run.id, zone_label="Top", sample_ts=dt.datetime.now(),
        notes="Seeded for CR-11 correction v2 delete-permission evidence.",
    )
    session.add(sample); session.flush()
    role = db.Role(company_id=company.id, name="CR11B Correction View Only Sample", is_builtin=False)
    session.add(role); session.flush()
    session.add(db.RolePagePermission(role_id=role.id, page_key="samples_conditioning", can_view=True, can_use=False))
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id, "grade_id": grade.id, "run_id": run.id,
        "sample_id": sample.id, "role_id": role.id,
    }
    session.close()
    return ids


def test_sample_view_only_role_cannot_delete(view_only_role_fixture_sample):
    """CR-11 correction v2 item 1, page_key "samples_conditioning": same
    evidence pattern - the view-only role can select the seeded sample, but
    sees neither the delete confirm-checkbox nor the delete button, and the
    sample still exists afterward."""
    ids = view_only_role_fixture_sample
    session = db.get_session()
    assert not access_control.can_use_page(
        "samples_conditioning", role_id=ids["role_id"], session=session, is_super_admin=False
    )
    session.close()

    at = _run_as_role(
        PAGE_SAMPLE, ids, session_state={"samples_table": {"selection": {"rows": [0], "columns": []}}},
    )
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["sample_selected_id"] == ids["sample_id"], (
        "The view-only role should still be able to select and view the seeded sample"
    )

    assert not any(c.key == f"sample_{ids['sample_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the delete confirm-checkbox"
    )
    assert not any(b.key == f"sample_{ids['sample_id']}_btn" for b in at.button), (
        "View-only role should not see the delete button"
    )
    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()

    session = db.get_session()
    assert session.get(db.Sample, ids["sample_id"]) is not None, (
        "The sample must still exist - a view-only role must not be able to delete it"
    )
    session.close()


# ---------------------------------------------------------------------------
# Gap 2.1 - Recipe CSV import validation. Bad-row check (views/3_Recipe_
# Version_Record.py, "CSV / Excel import" tab): `row.get("foam_grade_id")
# in valid_grade_ids and str(row.get("version_label", "")).strip()`.
# ---------------------------------------------------------------------------

def test_recipe_csv_import_validation_rejects_invalid_row(seeded_grade_no_recipe):
    """CR-11 correction v2 item 2: Recipe's CSV import (recipe version
    HEADER rows) pre-existed CR-11 (only relabeled/reordered), so it had no
    direct invalid-row evidence before this correction - only the valid-
    import path (test_recipe_csv_import_via_ui above). Uploads one row with
    an out-of-scope foam_grade_id and confirms it's flagged/rejected, not
    silently imported: no RecipeVersion is persisted and the real 'Confirm
    import (recipe versions)' button does not render (good_rows is empty,
    so the page's own `if good_rows and st.button(...)` guard never calls
    st.button at all)."""
    ids = seeded_grade_no_recipe
    session = db.get_session()
    before_count = session.query(db.RecipeVersion).count()
    session.close()

    at = AppTest.from_file(PAGE_RECIPE, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = b"foam_grade_id,version_label\n999999,CR11-Correction-Bad-Grade-Recipe\n"
    uploader = next(u for u in at.file_uploader if u.key == "recipe_version_upload")
    uploader.set_value(("recipe_versions_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading an invalid-grade-id CSV: {at.exception}"

    assert not any(b.key == "confirm_recipe_version_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "foam_grade_id" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.RecipeVersion).count()
    session.close()
    assert after_count == before_count, "An invalid-foam_grade_id row must not be persisted"


# ---------------------------------------------------------------------------
# Gap 2.2 - Quality Test Result CSV import validation. Bad-row check
# (views/5_Physical_Property_Result.py, tab_import): a row is only "ok" if
# property_name resolves against the property master list (case-
# insensitively), exactly one of the three parent FKs is in-scope, any
# sample_id given is in-scope, and test_method/unit/actual_value are all
# present. This test isolates the property_name check - every other field
# is otherwise valid.
# ---------------------------------------------------------------------------

def test_quality_test_result_csv_import_validation_rejects_invalid_row(seeded_run_with_property):
    """CR-11 correction v2 item 2: same evidence as above, for Quality Test
    Result's own importer. Uploads one row whose property_name does not
    match any entry in the seeded physical property master list -
    test_method, unit, actual_value, and production_run_id are all
    otherwise valid, isolating the unmatched property_name as the single
    reason this row is rejected."""
    ids = seeded_run_with_property
    session = db.get_session()
    before_count = session.query(db.PhysicalPropertyResult).count()
    session.close()

    at = AppTest.from_file(PAGE_QTR, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        f"property_name,test_method,unit,actual_value,production_run_id\n"
        f"CR11-Correction-No-Such-Property,CSV Import Method,kg/m3,32.4,{ids['run_id']}\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "result_upload")
    uploader.set_value(("results_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading an invalid-property CSV: {at.exception}"

    assert not any(b.key == "confirm_result_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "property_name" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.PhysicalPropertyResult).count()
    session.close()
    assert after_count == before_count, "An invalid-property_name row must not be persisted"


# ---------------------------------------------------------------------------
# Gap 2.3 - Quality Issue CSV import validation. Bad-row check (views/6_
# Quality_Observation.py, tab_import): a row is only "ok" if exactly one
# parent FK is in-scope AND observation_type matches the controlled
# taxonomy case-insensitively (quality_issue_taxonomy.lookup_case_
# insensitive()). This test isolates the taxonomy check.
# ---------------------------------------------------------------------------

def test_quality_issue_csv_import_validation_rejects_invalid_row(seeded_run_for_quality_issue):
    """CR-11 correction v2 item 2: same evidence as above, for Quality
    Issue's own importer. Uploads one row with a valid, in-scope
    production_run_id but an observation_type that matches no entry in the
    controlled issue-type taxonomy, isolating that as the single reason
    this row is rejected."""
    ids = seeded_run_for_quality_issue
    session = db.get_session()
    before_count = session.query(db.QualityObservation).count()
    session.close()

    at = AppTest.from_file(PAGE_QI, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        f"observation_type,production_run_id\n"
        f"CR11-Correction-Not-A-Real-Issue-Type,{ids['run_id']}\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "observation_upload")
    uploader.set_value(("issues_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading an invalid-issue-type CSV: {at.exception}"

    assert not any(b.key == "confirm_observation_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "observation_type" in warnings.lower() or "issue-type" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.QualityObservation).count()
    session.close()
    assert after_count == before_count, "An invalid-observation_type row must not be persisted"


# ---------------------------------------------------------------------------
# Gap 2.4 - Sample CSV import validation. Bad-row check (views/9_Samples_
# Conditioning.py, tab_import): `run_id_val in import_run_ids and
# str(row.get("zone_label", "")).strip()`. This test isolates the
# out-of-scope production_run_id check.
# ---------------------------------------------------------------------------

def test_sample_csv_import_validation_rejects_invalid_row(seeded_run_for_sample):
    """CR-11 correction v2 item 2: same evidence as above, for Sample's own
    importer. Uploads one row with a non-existent/out-of-scope
    production_run_id (a real, non-empty zone_label is given) and confirms
    it's flagged/rejected, not silently imported."""
    ids = seeded_run_for_sample
    session = db.get_session()
    before_count = session.query(db.Sample).count()
    session.close()

    at = AppTest.from_file(PAGE_SAMPLE, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = b"production_run_id,zone_label\n999999,Bottom\n"
    uploader = next(u for u in at.file_uploader if u.key == "sample_upload")
    uploader.set_value(("samples_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading an invalid-run-id CSV: {at.exception}"

    assert not any(b.key == "confirm_sample_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "production_run_id" in warnings.lower() or "zone_label" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.Sample).count()
    session.close()
    assert after_count == before_count, "An invalid-production_run_id row must not be persisted"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
