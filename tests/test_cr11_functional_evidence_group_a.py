"""CR-11 (Standardize Record Create, Edit/Delete and CSV/Excel Import
Functions, 2026-08-12) closeout correction - direct functional evidence,
Group A.

Charlie returned CR-11's first closeout package because it only proved
*wording and tab order* (every applicable page exposes "Create <record>",
"Edit/Delete <record>", "CSV/Excel import <records>" via the shared
helpers.cr11_function_tab_labels()) - not that Create/Edit/Delete/Import
actually work end-to-end through the real UI, for every applicable page.
This file supplies that missing direct evidence for three of CR-11's six
net-new CSV/Excel importers:

  1. pages/1_Plant_Installation_Overview.py - Plant. Pre-CR-11 this page
     was a single "Add plant" expander with no import at all.
  2. pages/20_Expert_Notes.py - Expert Note. Pre-CR-11 a single "Add an
     expert note" form with no import at all. Its pre-existing "Expert
     Notes Report" 4th tab (an aggregate breakdown, not a record-creation
     function - CR-11 explicitly retained it) is untouched by this file.
  3. pages/31_Production_Equipment.py - Production Unit / Cell. Pre-CR-11
     a single "Add Production Unit / Cell" expander with no import at
     all. Its Create tab has a dependent-dropdown chain (Plant ->
     Production Method -> OEM -> Model) that CR-11 moved into tab context
     unchanged - covered explicitly below.

Mandatory template and conventions, copied exactly from
tests/test_cr10_product_family_grade_split.py (the pattern already
accepted by Charlie for this exact kind of evidence, Product Families /
Product Grades):

  - os.environ.setdefault("DATABASE_URL", "sqlite://") + sys.path
    boilerplate, db.init_db() + Base.metadata.drop_all/create_all per
    fixture, SQLAlchemy ORM seeding with a uuid.uuid4().hex[:8] suffix on
    every seeded name.
  - _clear_relevant_caches(), called from every _reset_schema(): defends
    against the documented st.cache_data cross-test id-collision hazard
    (tenant_scope's id-scoping helpers and access_control.denied_page_keys
    cache on small-int keys - company_id/plant_ids/role_id - that repeat
    across tests/files once autoincrement ids restart after a schema
    drop/create).
  - The KEY TECHNIQUE for Edit/Delete: every one of these three pages
    renders its browse/edit/delete list via helpers.clickable_table(), a
    st.dataframe(on_select="rerun", selection_mode="single-row", key=...).
    Presetting at.session_state[<the dataframe's own key>] =
    {"selection": {"rows": [i], "columns": []}} BEFORE .run() genuinely
    drives a real row-click selection in streamlit==1.59.2 - confirmed
    directly against these exact pages below, same as the CR-10
    correction's own probe. Presetting the page's *derived*
    "..._selected_id" session_state key directly does NOT work (that
    page's own "idx is None -> pop the selection" branch fires on a fresh
    run and wipes it) - this file never does that.
  - The KEY TECHNIQUE for CSV import: at.file_uploader[...].set_value(
    (filename, csv_bytes, "text/csv")) before .run() genuinely drives
    st.file_uploader in this streamlit version.
  - at.secrets["AUTH_DISABLED"] = True on every AppTest run (dev-bypass
    auth - see auth.py's require_login(): this sets is_platform_owner=True
    and company_id=None for the synthetic session). Every fixture below
    seeds exactly ONE Company, which makes tenant_scope.company_picker()
    lock silently onto that company (its "is_platform_owner and >1
    company" branch that renders a Company selectbox never fires with
    only one company in the system) - so none of the tests below need to
    drive a Company picker widget, matching the CR-10 template's own
    single-company-per-fixture convention.

A note on the CSV-import *validation* tests below (one per page, beyond
the base 3): pandas' pd.read_csv() turns a genuinely empty CSV cell into
NaN, not "". Since more than one of these pages' own bad-row filters use
`str(row.get(col, "") or "").strip()` - and `NaN or ""` evaluates to NaN
because a NaN float is truthy in Python - a literally-empty required
field does NOT reliably trip that particular check (it stringifies to
the literal text "nan", which is non-empty). This is the pages' own
existing behavior, not a defect introduced by this file; adapting to it
(per this correction's own instruction to treat the pages as ground
truth), each validation test below uses whichever rejection path is
genuinely, deterministically enforced by the page's own source for that
importer: a single space in a required text field (which pandas keeps as
the literal string " ", so `str(" " or "").strip()` correctly yields "")
for Plant's import (no foreign key to abuse there - Company is chosen
outside the CSV), and an out-of-scope/unactivated foreign-key id for
Expert Notes' and Production Equipment's imports (both importers check
membership in a real id set, which a wrong id deterministically fails
regardless of the NaN quirk). In every case the flagged row ends up as
the importer's *only* row, so its own "if good_rows and st.button(...)"
guard means the real "Confirm import" button never even renders -
directly proving the row can't be imported, not merely that some other
row was skipped alongside a successful one (see
test_plant_csv_import_via_ui et al. for the "at least one row genuinely
imports" side of this).

Usage: python -m pytest tests/test_cr11_functional_evidence_group_a.py -v
"""
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
PAGE_PLANTS = os.path.join(APP_DIR, "pages", "1_Plant_Installation_Overview.py")
PAGE_EXPERT_NOTES = os.path.join(APP_DIR, "pages", "20_Expert_Notes.py")
PAGE_PRODUCTION_EQUIPMENT = os.path.join(APP_DIR, "pages", "31_Production_Equipment.py")


def _clear_relevant_caches():
    """Same defensive clear as tests/test_cr10_product_family_grade_split.py's
    own helper of this name, called from every _reset_schema() in this file
    for the identical reason: this file's fixtures each create a fresh
    Company/Plant/etc. after ids restart at 1, and tenant_scope's
    @st.cache_data-decorated id-scoping helpers (plus
    access_control.denied_page_keys) key on small integers alone - a stale
    cached entry from an earlier test/file can otherwise leak into a test
    that never asked for it."""
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
# Fixtures - Plant (pages/1_Plant_Installation_Overview.py)
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_company_only():
    """One Company, zero plants - the minimum for Plant's own Create and
    CSV/Excel import tabs (neither depends on a pre-existing plant; the
    Edit/Delete tab needs a real plant, covered by seeded_one_plant
    below)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11a Co {u}", is_platform_owner=True)
    session.add(company); session.commit()
    ids = {"company_id": company.id}
    session.close()
    return ids


@pytest.fixture()
def seeded_one_plant():
    """One Company, one Plant - the minimum to exercise Plant's own
    selection/Edit/Delete flow unambiguously (a single row makes the
    clickable_table row-index assertion unambiguous)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11b Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11b Plant {u}")
    session.add(plant); session.commit()
    ids = {"company_id": company.id, "plant_id": plant.id, "plant_name": plant.name}
    session.close()
    return ids


# ---------------------------------------------------------------------------
# Fixtures - Expert Note (pages/20_Expert_Notes.py)
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_one_grade():
    """Company -> Plant -> Product Family -> Product Grade, no Expert Note
    yet. This is the minimum an Expert Note can link to (Create's "Link
    to: Product Grade" path, and both import tests' valid/invalid
    foreign-key checks all resolve against this same scoped grade)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11c Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11c Plant {u}")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"CR11c Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"CR11c-Grade-{u}")
    session.add(grade); session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "family_id": family.id, "grade_id": grade.id, "grade_name": grade.grade_name,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_one_note(seeded_one_grade):
    """Same chain as seeded_one_grade, plus one Expert Note already linked
    to that grade - the minimum for the selection/Edit/Delete flow."""
    ids = dict(seeded_one_grade)
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    note = db.ExpertNote(
        linked_entity_type="foam_grade",
        linked_entity_id=ids["grade_id"],
        note_text=f"CR11 seeded note {u}",
        confidence_level="Unconfirmed",
        author="Seed script",
        source="Manual",
    )
    session.add(note); session.commit()
    ids["note_id"] = note.id
    ids["note_text"] = note.note_text
    session.close()
    return ids


# ---------------------------------------------------------------------------
# Fixtures - Production Unit / Cell (pages/31_Production_Equipment.py)
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_plant_with_method():
    """Company -> Plant -> ProductionMethod, activated for that plant via
    PlantProductionMethod(active=True). This is the exact dependency chain
    Production Equipment's Create tab (and its import's foreign-key check)
    requires before a Production Unit/Cell can be added at all - same
    seeding shape as test_pm_hierarchy_pages_smoke.py's
    seeded_pm_hierarchy fixture, trimmed to just what this page's Create/
    Import tabs touch (no Machine, no ProductFamily/FoamGrade)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11d Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11d Plant {u}")
    session.add(plant); session.flush()
    method = db.ProductionMethod(controlled_id=f"PM-CR11-{u}", name=f"CR11 Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "method_id": method.id, "method_name": method.name,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_one_machine(seeded_plant_with_method):
    """Same chain as seeded_plant_with_method, plus one Production Unit/
    Cell (db.Machine) already recorded - the minimum for the selection/
    Edit/Delete flow. oem="Hennecke" deliberately (not "Laader Berg") so
    the Edit form's model field is a plain st.text_input, not the
    Maxfoam-generations selectbox - keeping the edit test focused on the
    name-field edit it's actually asserting, without also having to drive
    the OEM-dependent model widget it isn't touching."""
    ids = dict(seeded_plant_with_method)
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    machine = db.Machine(
        plant_id=ids["plant_id"],
        name=f"CR11d Unit {u}",
        oem="Hennecke",
        model="Old Model",
        active=True,
        production_method_id=ids["method_id"],
    )
    session.add(machine); session.commit()
    ids["machine_id"] = machine.id
    ids["machine_name"] = machine.name
    session.close()
    return ids


# ===========================================================================
# 1. Plant (pages/1_Plant_Installation_Overview.py)
# ===========================================================================

def test_plant_create_via_form(seeded_company_only):
    """Fills the real Create tab (Plant name * text_input; Plant code/
    Location/Notes left blank since they're optional) and clicks the real
    'Save plant' form_submit_button, then confirms the new row landed in
    the database under the seeded company. _target_company() resolves
    silently to the seeded single company (is_platform_owner=True from the
    AUTH_DISABLED bypass, but company_picker locks to the only company in
    the system, so _target_company's own "company_filter is not None"
    branch fires and no Company picker widget is ever rendered)."""
    ids = seeded_company_only
    at = _run(PAGE_PLANTS)
    assert not at.exception, f"Unhandled exception loading Plants: {at.exception}"

    name_input = next(t for t in at.text_input if t.label == "Plant name *" and t.key is None)
    name_input.set_value("CR11-New-Plant")
    save_btn = next(b for b in at.button if b.label == "Save plant")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new plant: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.Plant)
        .filter(db.Plant.company_id == ids["company_id"], db.Plant.name == "CR11-New-Plant")
        .first()
    )
    assert created is not None, "New plant was not persisted"
    session.close()


def test_plant_selection_edit_and_delete_via_ui(seeded_one_plant):
    """Presets the plants_table dataframe widget's own on_select state to
    select row 0 before .run() (the confirmed-working technique - see this
    file's module docstring), confirming clickable_table's row-click
    selection genuinely drives plant_selected_id on this exact page. Then
    edits the selected plant's name through the real Edit form and
    confirms it persisted, then deletes it through the real confirm-
    checkbox + delete-button flow (helpers.delete_with_confirm) and
    confirms the plant is gone."""
    ids = seeded_one_plant
    at = AppTest.from_file(PAGE_PLANTS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["plants_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["plant_selected_id"] == ids["plant_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded plant"
    )

    # --- Edit ---
    name_input = next(t for t in at.text_input if t.key == f"edit_plant_name_{ids['plant_id']}")
    name_input.set_value("CR11-Edited-Plant")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the plant: {at.exception}"

    session = db.get_session()
    edited = session.get(db.Plant, ids["plant_id"])
    assert edited.name == "CR11-Edited-Plant", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["plants_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"plant_{ids['plant_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"plant_{ids['plant_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the plant: {at.exception}"

    session = db.get_session()
    assert session.get(db.Plant, ids["plant_id"]) is None, "Delete did not remove the plant"
    session.close()


def test_plant_csv_import_via_ui(seeded_company_only):
    """Drives the real st.file_uploader (key='plant_upload') with an
    in-memory one-row CSV, then clicks the real 'Confirm import' button
    (key='confirm_plant_import') - the actual upload/parse/dedupe/insert
    path, not a stand-in for dedupe_import_rows(). Confirms the row landed
    in the database under the seeded company."""
    ids = seeded_company_only
    at = _run(PAGE_PLANTS)
    assert not at.exception

    csv_bytes = b"name,plant_code\nCR11-Imported-Plant,PC-1\n"
    uploader = next(u for u in at.file_uploader if u.key == "plant_upload")
    uploader.set_value(("plants.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_plant_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.Plant)
        .filter(db.Plant.company_id == ids["company_id"], db.Plant.name == "CR11-Imported-Plant")
        .first()
    )
    assert imported is not None, "Imported plant was not persisted"
    session.close()


def test_plant_csv_import_validation_rejects_invalid_row(seeded_company_only):
    """A blank plant name must be rejected by the importer's own bad-row
    filter (`name_val = str(row.get("name", "") or "").strip()`, then
    "if name_val: good_rows.append(...) else: bad_rows.append(...)").
    Uses a single-space name field, not a truly empty CSV cell, because
    pandas turns a genuinely empty cell into NaN and `NaN or ""`
    evaluates to NaN (a NaN float is truthy in Python) - so a literally
    empty cell would stringify to the non-empty text "nan" and slip past
    this exact check. A single space survives as the literal string " ",
    which .strip() correctly reduces to "" - the same failure mode a
    real "typed a space and nothing else" operator mistake would produce.
    With the row flagged and zero good rows, the page's own
    "if good_rows and st.button(...)" guard means the real 'Confirm
    import' button never renders at all - so there is nothing to click
    and nothing gets imported; this is checked directly via the rendered
    warning/count and an unchanged plant count, not by clicking a button
    that doesn't exist."""
    ids = seeded_company_only
    session = db.get_session()
    before_count = session.query(db.Plant).filter(db.Plant.company_id == ids["company_id"]).count()
    session.close()

    at = _run(PAGE_PLANTS)
    assert not at.exception

    csv_bytes = b"name,plant_code\n ,BAD-1\n"
    uploader = next(u for u in at.file_uploader if u.key == "plant_upload")
    uploader.set_value(("plants.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    assert not any(b.key == "confirm_plant_import" for b in at.button), (
        "With zero good rows, the real Confirm import button must not be offered"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "no plant name" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.Plant).filter(db.Plant.company_id == ids["company_id"]).count()
    session.close()
    assert after_count == before_count, "A blank-name row must not insert a plant"


# ===========================================================================
# 2. Expert Note (pages/20_Expert_Notes.py)
# ===========================================================================

def test_expert_note_create_via_form(seeded_one_grade):
    """Switches the Create tab's 'Link to *' selector (key='new_note_link_type',
    outside the st.form by design so switching it reruns immediately) to
    'Product Grade', which swaps the form's entity picker to the seeded
    grade (only option, so no further selection needed), fills the real
    'Note *' text_area, and clicks the real 'Save note' form_submit_button.
    Confirms the new ExpertNote row landed in the database, linked to that
    grade. is_enabled_for_plant() returns False here (no PI3AIConnectionSetting
    row seeded / no OpenAI secrets configured), so this also implicitly
    proves the Create path doesn't require or attempt any outbound PI3
    call to save a plain manual note."""
    ids = seeded_one_grade
    at = _run(PAGE_EXPERT_NOTES)
    assert not at.exception, f"Unhandled exception loading Expert Notes: {at.exception}"

    link_sb = next(sb for sb in at.selectbox if sb.key == "new_note_link_type")
    link_sb.set_value("Product Grade")
    at.run()
    assert not at.exception

    entity_sb = next((sb for sb in at.selectbox if sb.label == "Product grade *"), None)
    assert entity_sb is not None, "Product grade entity picker not found after switching Link to"
    assert entity_sb.value is not None and entity_sb.value.id == ids["grade_id"]

    note_area = next(t for t in at.text_area if t.label == "Note *" and t.key is None)
    note_area.set_value("CR11-New-Expert-Note")
    save_btn = next(b for b in at.button if b.label == "Save note")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new expert note: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.ExpertNote)
        .filter(
            db.ExpertNote.linked_entity_type == "foam_grade",
            db.ExpertNote.linked_entity_id == ids["grade_id"],
            db.ExpertNote.note_text == "CR11-New-Expert-Note",
        )
        .first()
    )
    assert created is not None, "New expert note was not persisted"
    session.close()


def test_expert_note_selection_edit_and_delete_via_ui(seeded_one_note):
    """Presets the expert_notes_table dataframe widget's own on_select
    state to select row 0 before .run() (same confirmed-working technique
    as the Plant test above), confirming clickable_table's row-click
    selection genuinely drives note_selected_id on this page. Then edits
    the selected note's text through the real Edit form and confirms it
    persisted, then deletes it through the real confirm-checkbox +
    delete-button flow and confirms the note is gone."""
    ids = seeded_one_note
    at = AppTest.from_file(PAGE_EXPERT_NOTES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["expert_notes_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["note_selected_id"] == ids["note_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded note"
    )

    # --- Edit ---
    text_area = next(t for t in at.text_area if t.key == f"edit_note_text_{ids['note_id']}")
    text_area.set_value("CR11-Edited-Expert-Note")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the expert note: {at.exception}"

    session = db.get_session()
    edited = session.get(db.ExpertNote, ids["note_id"])
    assert edited.note_text == "CR11-Edited-Expert-Note", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["expert_notes_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"note_{ids['note_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"note_{ids['note_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the expert note: {at.exception}"

    session = db.get_session()
    assert session.get(db.ExpertNote, ids["note_id"]) is None, "Delete did not remove the expert note"
    session.close()


def test_expert_note_csv_import_via_ui(seeded_one_grade):
    """Drives the real st.file_uploader (key='expert_note_upload') with an
    in-memory CSV row referencing the seeded, in-scope product grade, then
    clicks the real 'Confirm import' button (key='confirm_expert_note_import').
    Confirms the row landed in the database, linked to that grade."""
    ids = seeded_one_grade
    at = _run(PAGE_EXPERT_NOTES)
    assert not at.exception

    csv_bytes = (
        f"linked_entity_type,linked_entity_id,note_text\n"
        f"foam_grade,{ids['grade_id']},CR11-Imported-Expert-Note\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "expert_note_upload")
    uploader.set_value(("notes.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_expert_note_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.ExpertNote)
        .filter(
            db.ExpertNote.linked_entity_type == "foam_grade",
            db.ExpertNote.linked_entity_id == ids["grade_id"],
            db.ExpertNote.note_text == "CR11-Imported-Expert-Note",
        )
        .first()
    )
    assert imported is not None, "Imported expert note was not persisted"
    session.close()


def test_expert_note_csv_import_validation_rejects_invalid_row(seeded_one_grade):
    """An out-of-scope linked_entity_id must be rejected by the importer's
    own check (`eid in valid_ids_by_type.get(etype, set())`, built from the
    same scoped grade/run/family id sets the manual Create tab uses) -
    this is a real foreign-key/membership check, not the NaN-sensitive
    blank-field check the Plant test above had to work around, so a
    plain made-up id (999999, guaranteed not to be the seeded grade's real
    autoincrement id) deterministically fails it. With the row flagged and
    zero good rows, the real 'Confirm import' button never renders (same
    "if good_rows and st.button(...)" guard as every other importer in
    this app) - checked directly via the rendered warning and an
    unchanged expert-note count."""
    ids = seeded_one_grade
    session = db.get_session()
    before_count = session.query(db.ExpertNote).count()
    session.close()

    at = _run(PAGE_EXPERT_NOTES)
    assert not at.exception

    csv_bytes = (
        f"linked_entity_type,linked_entity_id,note_text\n"
        f"foam_grade,999999,CR11-Should-Not-Import\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "expert_note_upload")
    uploader.set_value(("notes.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    assert not any(b.key == "confirm_expert_note_import" for b in at.button), (
        "With zero good rows, the real Confirm import button must not be offered"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "unrecognized" in warnings.lower() or "not in scope" in warnings.lower() or "no note_text" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.ExpertNote).count()
    session.close()
    assert after_count == before_count, "A row with an out-of-scope linked_entity_id must not insert a note"


# ===========================================================================
# 3. Production Unit / Cell (pages/31_Production_Equipment.py)
# ===========================================================================

def test_production_unit_create_via_form(seeded_plant_with_method):
    """Drives the full Plant -> Production Method -> OEM -> Model
    dependent-dropdown chain CR-11 moved into this tab unchanged: the
    Plant picker (key='add_machine_plant') defaults to the only seeded
    plant, which narrows the Production Method picker (key=
    'add_machine_method', via helpers.activated_methods_for_plant) to
    exactly the one method activated for that plant - asserted directly
    below, not assumed. Switching OEM (key='add_machine_oem') to
    'Hennecke' (deliberately not the default 'Laader Berg', which would
    instead swap in the Maxfoam-generations selectbox - a separate,
    already-covered branch of _machine_model_picker) swaps the Model
    field to a plain st.text_input (key='add_machine_model_text'), which
    is then filled directly - all four pickers live outside the
    surrounding st.form on purpose (see the page's own comment), so each
    change reruns and narrows the next immediately, exactly as a live
    user would experience it. Finally fills the real name field inside
    the form and clicks the real 'Save Production Unit / Cell' button,
    then confirms the new Machine row persisted with the expected plant/
    method/OEM/model."""
    ids = seeded_plant_with_method
    at = AppTest.from_file(PAGE_PRODUCTION_EQUIPMENT, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Production Equipment: {at.exception}"

    method_sb = next(sb for sb in at.selectbox if sb.key == "add_machine_method")
    assert method_sb.value is not None and method_sb.value.id == ids["method_id"], (
        "Plant -> Production Method narrowing did not offer the plant's own activated method"
    )

    oem_sb = next(sb for sb in at.selectbox if sb.key == "add_machine_oem")
    oem_sb.set_value("Hennecke")
    at.run()
    assert not at.exception, f"Unhandled exception switching OEM: {at.exception}"

    model_input = next(t for t in at.text_input if t.key == "add_machine_model_text")
    model_input.set_value("CR11-Test-Model")
    name_input = next(
        t for t in at.text_input
        if t.label == "Production Unit / Cell name * (e.g. Line 1, Maxfoam A)"
    )
    name_input.set_value("CR11-New-Unit")
    save_btn = next(b for b in at.button if b.label == "Save Production Unit / Cell")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new Production Unit / Cell: {at.exception}"

    session = db.get_session()
    created = session.query(db.Machine).filter(db.Machine.name == "CR11-New-Unit").first()
    assert created is not None, "New Production Unit / Cell was not persisted"
    assert created.plant_id == ids["plant_id"]
    assert created.production_method_id == ids["method_id"]
    assert created.oem == "Hennecke"
    assert created.model == "CR11-Test-Model"
    session.close()


def test_production_unit_selection_edit_and_delete_via_ui(seeded_one_machine):
    """Presets the machines_table dataframe widget's own on_select state
    to select row 0 before .run() (same confirmed-working technique as
    the Plant/Expert Note tests above), confirming clickable_table's
    row-click selection genuinely drives machine_selected_id on this
    page. Then edits the selected unit's name through the real Edit form
    and confirms it persisted, then deletes it through the real
    confirm-checkbox + delete-button flow (which also calls
    cascades.unlink_machine_dependents first) and confirms the unit is
    gone. Leaves OEM/Model untouched in the edit (the fixture seeds
    oem='Hennecke', so the Edit form's own defaults already round-trip
    correctly without any interaction - the dependent-dropdown chain
    itself is exercised by the Create test above)."""
    ids = seeded_one_machine
    at = AppTest.from_file(PAGE_PRODUCTION_EQUIPMENT, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["machines_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["machine_selected_id"] == ids["machine_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded unit"
    )

    # --- Edit ---
    name_input = next(t for t in at.text_input if t.key == f"edit_machine_name_{ids['machine_id']}")
    name_input.set_value("CR11-Edited-Unit")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the Production Unit / Cell: {at.exception}"

    session = db.get_session()
    edited = session.get(db.Machine, ids["machine_id"])
    assert edited.name == "CR11-Edited-Unit", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["machines_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"machine_{ids['machine_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"machine_{ids['machine_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the Production Unit / Cell: {at.exception}"

    session = db.get_session()
    assert session.get(db.Machine, ids["machine_id"]) is None, "Delete did not remove the Production Unit / Cell"
    session.close()


def test_production_unit_csv_import_via_ui(seeded_plant_with_method):
    """Drives the real st.file_uploader (key='machine_upload') with an
    in-memory CSV row referencing the seeded plant_id and its own
    activated production_method_id, then clicks the real 'Confirm import'
    button (key='confirm_machine_import'). Confirms the row landed in the
    database with the expected plant/method links."""
    ids = seeded_plant_with_method
    at = _run(PAGE_PRODUCTION_EQUIPMENT)
    assert not at.exception

    csv_bytes = (
        f"plant_id,production_method_id,name\n"
        f"{ids['plant_id']},{ids['method_id']},CR11-Imported-Unit\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "machine_upload")
    uploader.set_value(("machines.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_machine_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = session.query(db.Machine).filter(db.Machine.name == "CR11-Imported-Unit").first()
    assert imported is not None, "Imported Production Unit / Cell was not persisted"
    assert imported.plant_id == ids["plant_id"]
    assert imported.production_method_id == ids["method_id"]
    session.close()


def test_production_unit_csv_import_validation_rejects_invalid_row(seeded_plant_with_method):
    """A production_method_id that is NOT activated for the given plant
    must be rejected by the importer's own check (`method_id_val in
    valid_method_ids_by_plant.get(plant_id_val, set())` - the same
    plant-scoped activated-method set the manual Create tab's dependent
    dropdown narrows to). Uses 999999, guaranteed not to be an id
    PlantProductionMethod actually activated for this plant - a real
    foreign-key/membership check, not the NaN-sensitive blank-field check
    the Plant test had to work around. With the row flagged and zero good
    rows, the real 'Confirm import' button never renders - checked
    directly via the rendered warning and an unchanged Machine count."""
    ids = seeded_plant_with_method
    session = db.get_session()
    before_count = session.query(db.Machine).filter(db.Machine.plant_id == ids["plant_id"]).count()
    session.close()

    at = _run(PAGE_PRODUCTION_EQUIPMENT)
    assert not at.exception

    csv_bytes = (
        f"plant_id,production_method_id,name\n"
        f"{ids['plant_id']},999999,CR11-Should-Not-Import\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "machine_upload")
    uploader.set_value(("machines.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    assert not any(b.key == "confirm_machine_import" for b in at.button), (
        "With zero good rows, the real Confirm import button must not be offered"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "not activated" in warnings.lower() or "unknown plant_id" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.Machine).filter(db.Machine.plant_id == ids["plant_id"]).count()
    session.close()
    assert after_count == before_count, "A row with a non-activated production_method_id must not insert a unit"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
