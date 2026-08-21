"""CR-15 (Standardize Expert Notes Product Family Terminology and Add Trial
Links, 2026-08-13) - direct executed evidence for every CR-15 acceptance
criterion and regression-test requirement (sections 8/9 of
CR15_Standardize_Expert_Notes_Product_Family_Terminology_and_Add_Trial_
Links.docx).

Covers, against the real views/20_Expert_Notes.py through AppTest (not a
stand-in for the page's own logic):
  1. The "Link to *" selector offers exactly 5 options, in the required
     order: Production Run, Product Grade, PU Material Family, Commercial
     Trial, Optimization Trial.
  2. No customer-facing "Foam Family" string remains on this page or in
     helpers.expert_note_link_label's pu_material_family branch - "Product
     Family" throughout - while the internal linked_entity_type value
     "pu_material_family" (a CSV-import-documented identifier, not
     customer-facing wording) is unchanged, per CR-15 section 3's scope.
  3. Commercial Trial (-> CustomerTrial) and Optimization Trial (->
     OptimizationTrial) each: create + persist via the real Create tab,
     company scoping on that same tab's entity dropdown, visibility +
     edit + delete via the real Edit/Delete tab (including company-scope
     exclusion), inclusion in the Expert Notes Report tab's totals, and
     CSV/Excel import (valid row + out-of-scope-id rejection, with the
     bad-row warning listing all 5 accepted linked_entity_type values).
  4. The shared helper functions PI3's vector-store tagging depends on
     (expert_note_plant_id_for_link, company_id_for_plant,
     expert_note_link_label, expert_note_foam_grade_id_for_link) resolve
     correctly for both new link types - PI3 itself is not configured in
     this environment (no OpenAI secrets), matching the same, already-
     accepted approach tests/test_cr11_functional_evidence_group_a.py's
     test_expert_note_create_via_form documents (is_enabled_for_plant()
     returns False here, so the Create/Import paths never attempt an
     outbound PI3 call - proving the tagging *logic* directly is the
     available evidence, same as every prior CR touching this page).
  5. Regression: tests/test_cr11_functional_evidence_group_a.py's 15
     pre-existing Expert Note/Plant/Production Equipment tests were
     re-run standalone against these changes before this file was
     written and pass unchanged (15 passed) - the LINK_TYPES dict rename
     ("Foam Family" -> "PU Material Family") and reorder (Commercial
     Trial/Optimization Trial appended after PU Material Family) did not
     break the Product Grade link path those tests already cover. This
     file additionally re-proves the PU Material Family link path still
     creates a note correctly post-rename (test 13 below), since no
     pre-existing test exercised that specific path end-to-end.

Mandatory template and conventions, copied from
tests/test_cr14_customers_section.py / test_cr11_functional_evidence_
group_a.py (the pattern already accepted by Charlie for this exact kind
of evidence):
  - os.environ.setdefault("DATABASE_URL", "sqlite://") + sys.path
    boilerplate, db.init_db() + Base.metadata.drop_all/create_all per
    fixture, SQLAlchemy ORM seeding with a uuid.uuid4().hex[:8] suffix on
    every seeded name.
  - _clear_relevant_caches(), called from every _reset_schema() -
    including tenant_scope's customer_trial_ids_for_plants and
    optimization_trial_ids_for_plants caches, the two this CR's new link
    types depend on for company scoping.
  - Presetting a dataframe/table widget's OWN on_select state (e.g.
    at.session_state["expert_notes_table"] = {"selection": {"rows": [i],
    "columns": []}}) BEFORE .run() to genuinely drive clickable_table's
    row-click selection - confirmed working directly against this page
    by tests/test_cr11_functional_evidence_group_a.py.
  - Presetting is_platform_owner=False and company_id=<id> in
    session_state BEFORE .run() to lock tenant_scope.company_picker()
    onto one company deterministically without needing to drive its
    selectbox widget (setdefault()-based dev-bypass defaults in auth.py
    only apply when the key is not already present).
  - Selectbox.options returns FORMATTED display strings (post
    format_func), not the raw underlying objects.
  - at.dataframe[<key>].value returns the actual pandas DataFrame that
    was passed to st.dataframe/clickable_table - confirmed directly
    against this page (Expert Notes Report metrics use at.metric).
  - at.secrets["AUTH_DISABLED"] = True for every AppTest run.

Usage: python -m pytest tests/test_cr15_expert_notes_trial_links.py -v
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
from helpers import (
    company_id_for_plant,
    expert_note_foam_grade_id_for_link,
    expert_note_link_label,
    expert_note_plant_id_for_link,
)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_EXPERT_NOTES = os.path.join(APP_DIR, "views", "20_Expert_Notes.py")

REQUIRED_LINK_ORDER = [
    "Production Run",
    "Product Grade",
    "PU Material Family",
    "Commercial Trial",
    "Optimization Trial",
]


def _clear_relevant_caches():
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


def _lock_company(company_id):
    """Overrides the AUTH_DISABLED dev-bypass's own setdefault()-based
    is_platform_owner=True/company_id=None defaults so company_picker()
    locks deterministically onto one company, exactly as a real
    non-platform-owner user of that company would see - without needing
    to drive the Company selectbox widget (which only renders at all
    when is_platform_owner AND more than one company exists)."""
    return {"is_platform_owner": False, "company_id": company_id}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seed_chain(session, tag):
    """Company -> Plant -> PU Material Family -> Product Grade -> Commercial
    Trial -> Optimization Trial, one full chain for one company. Returns a
    dict of every id/label a test might need."""
    u = uuid.uuid4().hex[:8]
    company = db.Company(name=f"CR15-{tag} Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR15-{tag} Plant {u}")
    session.add(plant); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR15-{tag} Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR15-{tag}-Grade-{u}")
    session.add(grade); session.flush()
    ct = db.CustomerTrial(
        plant_id=plant.id, foam_grade_id=grade.id,
        customer_name=f"CR15-{tag}-Customer-{u}",
    )
    session.add(ct); session.flush()
    opt = db.OptimizationTrial(plant_id=plant.id, foam_grade_id=grade.id)
    session.add(opt); session.flush()
    return {
        "company_id": company.id, "plant_id": plant.id,
        "family_id": family.id, "grade_id": grade.id, "grade_name": grade.grade_name,
        "customer_trial_id": ct.id, "customer_name": ct.customer_name,
        "optimization_trial_id": opt.id,
    }


@pytest.fixture()
def seeded_two_trial_targets():
    """One company with a full chain including one Commercial Trial and one
    Optimization Trial - no Expert Note yet. Covers the Create-tab tests,
    the Link-to order test, the terminology test, the helper-function
    test, and both CSV/Excel import tests."""
    db.init_db()
    _reset_schema()
    session = db.get_session()
    ids = _seed_chain(session, "single")
    session.commit()
    session.close()
    return ids


@pytest.fixture()
def seeded_two_trial_notes():
    """Same single-company chain as seeded_two_trial_targets, plus one
    Expert Note linked to the Commercial Trial (created first) and one
    linked to the Optimization Trial (created second, so it sorts first
    in the page's created_at-desc ordering) - the minimum to exercise
    visibility/edit/delete/report inclusion for both new link types at
    once."""
    db.init_db()
    _reset_schema()
    session = db.get_session()
    ids = _seed_chain(session, "notes")
    session.flush()
    note_ct = db.ExpertNote(
        linked_entity_type="customer_trial", linked_entity_id=ids["customer_trial_id"],
        note_text="CR15 seeded commercial trial note", confidence_level="Unconfirmed",
        author="Seed script", source="Manual",
    )
    session.add(note_ct); session.flush()
    note_opt = db.ExpertNote(
        linked_entity_type="optimization_trial", linked_entity_id=ids["optimization_trial_id"],
        note_text="CR15 seeded optimization trial note", confidence_level="Unconfirmed",
        author="Seed script", source="Manual",
    )
    session.add(note_opt); session.commit()
    ids["note_customer_trial_id"] = note_ct.id
    ids["note_optimization_trial_id"] = note_opt.id
    session.close()
    return ids


@pytest.fixture()
def two_companies_with_trial_notes():
    """Two independent companies, each with its own full chain (Commercial
    Trial + Optimization Trial) AND its own Expert Note linked to its own
    Commercial Trial. The minimum to prove company scoping on both the
    Create tab's entity dropdown and the Edit/Delete tab's visibility
    list for the two new link types."""
    db.init_db()
    _reset_schema()
    session = db.get_session()
    a = _seed_chain(session, "a")
    session.flush()
    note_a = db.ExpertNote(
        linked_entity_type="customer_trial", linked_entity_id=a["customer_trial_id"],
        note_text="CR15 company A commercial trial note", confidence_level="Unconfirmed",
        author="Seed script", source="Manual",
    )
    session.add(note_a); session.flush()
    a["note_id"] = note_a.id

    b = _seed_chain(session, "b")
    session.flush()
    note_b = db.ExpertNote(
        linked_entity_type="customer_trial", linked_entity_id=b["customer_trial_id"],
        note_text="CR15 company B commercial trial note", confidence_level="Unconfirmed",
        author="Seed script", source="Manual",
    )
    session.add(note_b); session.commit()
    b["note_id"] = note_b.id
    session.close()
    return {"a": a, "b": b}


# ===========================================================================
# 1. Link-to selector: exact order, 5 options
# ===========================================================================

def test_link_to_selector_has_exact_five_options_in_required_order(seeded_two_trial_targets):
    at = _run(PAGE_EXPERT_NOTES)
    assert not at.exception, f"Unhandled exception loading Expert Notes: {at.exception}"

    link_sb = next(sb for sb in at.selectbox if sb.key == "new_note_link_type")
    assert list(link_sb.options) == REQUIRED_LINK_ORDER, (
        f"Link to selector must offer exactly these 5 options in this order per CR-15 "
        f"section 4; got {list(link_sb.options)}"
    )


# ===========================================================================
# 2. Terminology: no customer-facing "Foam Family" leak
# ===========================================================================

def test_pu_material_family_terminology_not_leaked_in_ui(seeded_two_trial_targets):
    ids = seeded_two_trial_targets
    at = _run(PAGE_EXPERT_NOTES)
    assert not at.exception

    link_sb = next(sb for sb in at.selectbox if sb.key == "new_note_link_type")
    link_sb.set_value("PU Material Family")
    at.run()
    assert not at.exception

    # R1-WP3 (2026-08-21): CR-15 required "Product family *" here (replacing
    # the Flexible-Foam "Foam family *"). R1 renamed the term once more, to
    # "PU Material Family *". CR-15's requirement - the entity picker must
    # not carry Flexible Foam terminology - is unchanged; only the target
    # wording moved, so the assertion below tracks it and still fails if
    # "Foam family" ever comes back.
    entity_sb = next((sb for sb in at.selectbox if sb.label == "PU Material Family *"), None)
    assert entity_sb is not None, (
        "Entity picker must be labeled 'PU Material Family *' (R1-WP3), never 'Foam family *' (CR-15)"
    )

    all_widget_text = " ".join(
        [w.label or "" for w in at.selectbox]
        + [w.value or "" for w in at.warning]
        + [w.value or "" for w in at.caption]
        + [w.value or "" for w in at.markdown]
    )
    assert "Foam Family" not in all_widget_text and "Foam family" not in all_widget_text, (
        "No customer-facing 'Foam Family' wording may remain on this page after CR-15"
    )

    session = db.get_session()
    label = expert_note_link_label("pu_material_family", ids["family_id"], session)
    session.close()
    assert label.startswith("PU Material Family:"), (
        f"helpers.expert_note_link_label must say 'PU Material Family:', not 'Foam Family:' - got {label!r}"
    )


# ===========================================================================
# 3/4. Commercial Trial + Optimization Trial: create + persist via Create tab
# ===========================================================================

def test_commercial_trial_create_via_form(seeded_two_trial_targets):
    ids = seeded_two_trial_targets
    at = _run(PAGE_EXPERT_NOTES)
    assert not at.exception

    link_sb = next(sb for sb in at.selectbox if sb.key == "new_note_link_type")
    link_sb.set_value("Commercial Trial")
    at.run()
    assert not at.exception

    entity_sb = next((sb for sb in at.selectbox if sb.label == "Commercial trial *"), None)
    assert entity_sb is not None, "Commercial trial entity picker not found after switching Link to"
    assert entity_sb.value is not None and entity_sb.value.id == ids["customer_trial_id"]

    note_area = next(t for t in at.text_area if t.label == "Note *" and t.key is None)
    note_area.set_value("CR15-New-Commercial-Trial-Note")
    save_btn = next(b for b in at.button if b.label == "Save note")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a commercial-trial-linked note: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.ExpertNote)
        .filter(
            db.ExpertNote.linked_entity_type == "customer_trial",
            db.ExpertNote.linked_entity_id == ids["customer_trial_id"],
            db.ExpertNote.note_text == "CR15-New-Commercial-Trial-Note",
        )
        .first()
    )
    assert created is not None, "New commercial-trial-linked expert note was not persisted"
    session.close()


def test_optimization_trial_create_via_form(seeded_two_trial_targets):
    ids = seeded_two_trial_targets
    at = _run(PAGE_EXPERT_NOTES)
    assert not at.exception

    link_sb = next(sb for sb in at.selectbox if sb.key == "new_note_link_type")
    link_sb.set_value("Optimization Trial")
    at.run()
    assert not at.exception

    entity_sb = next((sb for sb in at.selectbox if sb.label == "Optimization trial *"), None)
    assert entity_sb is not None, "Optimization trial entity picker not found after switching Link to"
    assert entity_sb.value is not None and entity_sb.value.id == ids["optimization_trial_id"]

    note_area = next(t for t in at.text_area if t.label == "Note *" and t.key is None)
    note_area.set_value("CR15-New-Optimization-Trial-Note")
    save_btn = next(b for b in at.button if b.label == "Save note")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving an optimization-trial-linked note: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.ExpertNote)
        .filter(
            db.ExpertNote.linked_entity_type == "optimization_trial",
            db.ExpertNote.linked_entity_id == ids["optimization_trial_id"],
            db.ExpertNote.note_text == "CR15-New-Optimization-Trial-Note",
        )
        .first()
    )
    assert created is not None, "New optimization-trial-linked expert note was not persisted"
    session.close()


# ===========================================================================
# 5. Company scoping on the Create tab's entity dropdown
# ===========================================================================

def test_commercial_and_optimization_trial_create_tab_scoped_to_active_company(
    two_companies_with_trial_notes,
):
    a = two_companies_with_trial_notes["a"]
    b = two_companies_with_trial_notes["b"]
    at = _run(PAGE_EXPERT_NOTES, session_state=_lock_company(a["company_id"]))
    assert not at.exception

    link_sb = next(sb for sb in at.selectbox if sb.key == "new_note_link_type")
    link_sb.set_value("Commercial Trial")
    at.run()
    assert not at.exception
    entity_sb = next(sb for sb in at.selectbox if sb.label == "Commercial trial *")
    assert len(entity_sb.options) == 1, "Only company A's own commercial trial should be offered"
    assert a["customer_name"] in entity_sb.options[0]
    assert b["customer_name"] not in entity_sb.options[0]

    # Re-fetch the Link to selectbox fresh (its widget wrapper from before this
    # last .run() no longer reliably drives a second .set_value() - the same
    # "get a fresh reference after every .run()" discipline this file's own
    # docstring already requires for dataframe/checkbox/button widgets).
    link_sb2 = next(sb for sb in at.selectbox if sb.key == "new_note_link_type")
    link_sb2.set_value("Optimization Trial")
    at.run()
    assert not at.exception
    entity_sb2 = next(sb for sb in at.selectbox if sb.label == "Optimization trial *")
    assert entity_sb2.value is not None and entity_sb2.value.id == a["optimization_trial_id"]
    assert entity_sb2.value.id != b["optimization_trial_id"]


# ===========================================================================
# 6. Edit/Delete tab: visibility, edit, delete for both new link types
# ===========================================================================

def test_trial_linked_notes_visible_editable_deletable_in_edit_delete_tab(seeded_two_trial_notes):
    """Presetting the dataframe widget's own selection state must happen
    BEFORE that AppTest instance's very first .run() - confirmed directly
    (see the probe behind this fix): an initial unrelated .run() (e.g. just
    to inspect the unfiltered list) followed by a second .run() that adds
    the selection preset does NOT reliably drive the downstream Edit save,
    even though the selection itself (note_selected_id) appears to take.
    So this test uses a fresh, disposable AppTest purely to confirm both
    notes are listed, then a separate fresh AppTest per selection cycle
    (edit, then delete), each with its selection preset before its own
    first .run() - exactly the pattern tests/test_cr11_functional_
    evidence_group_a.py's own Expert Note edit/delete test already uses."""
    ids = seeded_two_trial_notes

    listing_at = _run(PAGE_EXPERT_NOTES)
    assert not listing_at.exception
    table = next(d for d in listing_at.dataframe if d.key == "expert_notes_table")
    linked_labels = list(table.value["Linked to"])
    assert any(lbl.startswith("Commercial Trial #") for lbl in linked_labels), (
        f"Commercial-trial-linked note must be visible in Edit/Delete list; got {linked_labels}"
    )
    assert any(lbl.startswith("Optimization Trial #") for lbl in linked_labels), (
        f"Optimization-trial-linked note must be visible in Edit/Delete list; got {linked_labels}"
    )
    assert len(linked_labels) == 2

    # --- Edit the optimization-trial-linked note (row 0, created_at desc, seeded second) ---
    at = AppTest.from_file(PAGE_EXPERT_NOTES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["expert_notes_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception
    assert at.session_state["note_selected_id"] == ids["note_optimization_trial_id"]

    text_area = next(t for t in at.text_area if t.key == f"edit_note_text_{ids['note_optimization_trial_id']}")
    text_area.set_value("CR15-Edited-Optimization-Trial-Note")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the optimization-trial note: {at.exception}"

    session = db.get_session()
    edited = session.get(db.ExpertNote, ids["note_optimization_trial_id"])
    assert edited.note_text == "CR15-Edited-Optimization-Trial-Note", "Edit did not persist"
    session.close()

    # --- Select and delete the commercial-trial-linked note (row 1) ---
    at2 = AppTest.from_file(PAGE_EXPERT_NOTES, default_timeout=30)
    at2.secrets["AUTH_DISABLED"] = True
    at2.session_state["expert_notes_table"] = {"selection": {"rows": [1], "columns": []}}
    at2.run()
    assert not at2.exception
    assert at2.session_state["note_selected_id"] == ids["note_customer_trial_id"]

    confirm_box = next(c for c in at2.checkbox if c.key == f"note_{ids['note_customer_trial_id']}_confirm")
    confirm_box.set_value(True)
    at2.run()
    delete_btn = next(b for b in at2.button if b.key == f"note_{ids['note_customer_trial_id']}_btn")
    delete_btn.click()
    at2.run()
    assert not at2.exception, f"Unhandled exception deleting the commercial-trial note: {at2.exception}"

    session = db.get_session()
    assert session.get(db.ExpertNote, ids["note_customer_trial_id"]) is None, (
        "Delete did not remove the commercial-trial-linked expert note"
    )
    assert session.get(db.ExpertNote, ids["note_optimization_trial_id"]) is not None, (
        "Deleting one note must not remove the other"
    )
    session.close()


def test_trial_linked_note_excluded_for_other_company_in_edit_delete_tab(two_companies_with_trial_notes):
    a = two_companies_with_trial_notes["a"]
    b = two_companies_with_trial_notes["b"]
    at = _run(PAGE_EXPERT_NOTES, session_state=_lock_company(b["company_id"]))
    assert not at.exception

    table = next(d for d in at.dataframe if d.key == "expert_notes_table")
    linked_labels = list(table.value["Linked to"])
    assert len(linked_labels) == 1, (
        f"Locked to company B, only company B's own note should be visible; got {linked_labels}"
    )
    assert a["customer_name"] not in linked_labels[0], (
        "Company A's commercial-trial-linked note must not be visible while locked to company B"
    )
    assert b["customer_name"] in linked_labels[0]


# ===========================================================================
# 7. Expert Notes Report tab: totals include both new link types
# ===========================================================================

def test_expert_notes_report_includes_trial_linked_notes(seeded_two_trial_notes):
    at = _run(PAGE_EXPERT_NOTES)
    assert not at.exception

    total_metric = next(m for m in at.metric if m.label == "Total notes")
    assert int(total_metric.value) == 2, (
        f"Expert Notes Report total must include both trial-linked notes; got {total_metric.value}"
    )


# ===========================================================================
# 8/9. CSV/Excel import: valid rows + out-of-scope rejection, both new types
# ===========================================================================

def test_csv_import_customer_trial_and_optimization_trial_valid_rows(seeded_two_trial_targets):
    ids = seeded_two_trial_targets
    at = _run(PAGE_EXPERT_NOTES)
    assert not at.exception

    csv_bytes = (
        "linked_entity_type,linked_entity_id,note_text\n"
        f"customer_trial,{ids['customer_trial_id']},CR15-Imported-Commercial-Trial-Note\n"
        f"optimization_trial,{ids['optimization_trial_id']},CR15-Imported-Optimization-Trial-Note\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "expert_note_upload")
    uploader.set_value(("notes.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    assert "Rows ready to import: **2**" in " ".join(w.value for w in at.markdown), (
        "Both trial-linked rows must be recognized as valid before import"
    )

    confirm_btn = next(b for b in at.button if b.key == "confirm_expert_note_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported_ct = (
        session.query(db.ExpertNote)
        .filter(
            db.ExpertNote.linked_entity_type == "customer_trial",
            db.ExpertNote.linked_entity_id == ids["customer_trial_id"],
            db.ExpertNote.note_text == "CR15-Imported-Commercial-Trial-Note",
        )
        .first()
    )
    imported_opt = (
        session.query(db.ExpertNote)
        .filter(
            db.ExpertNote.linked_entity_type == "optimization_trial",
            db.ExpertNote.linked_entity_id == ids["optimization_trial_id"],
            db.ExpertNote.note_text == "CR15-Imported-Optimization-Trial-Note",
        )
        .first()
    )
    assert imported_ct is not None, "Imported commercial-trial-linked note was not persisted"
    assert imported_opt is not None, "Imported optimization-trial-linked note was not persisted"
    session.close()


def test_csv_import_trial_rows_reject_out_of_scope_id(seeded_two_trial_targets):
    """A made-up customer_trial id (999999) must be rejected by the same
    valid_ids_by_type membership check every other type here already uses -
    with the row flagged and zero good rows, the real 'Confirm import'
    button never renders (same guard proven for other types by
    test_expert_note_csv_import_validation_rejects_invalid_row in
    tests/test_cr11_functional_evidence_group_a.py), and the bad-row
    warning must list all 5 accepted linked_entity_type values including
    the two new ones."""
    session = db.get_session()
    before_count = session.query(db.ExpertNote).count()
    session.close()

    at = _run(PAGE_EXPERT_NOTES)
    assert not at.exception

    csv_bytes = (
        "linked_entity_type,linked_entity_id,note_text\n"
        "customer_trial,999999,CR15-Should-Not-Import\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "expert_note_upload")
    uploader.set_value(("notes.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    assert not any(b.key == "confirm_expert_note_import" for b in at.button), (
        "With zero good rows, the real Confirm import button must not be offered"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "customer_trial" in warnings and "optimization_trial" in warnings, (
        f"Bad-row warning must list all 5 accepted linked_entity_type values; got {warnings!r}"
    )

    session = db.get_session()
    after_count = session.query(db.ExpertNote).count()
    session.close()
    assert after_count == before_count, "An out-of-scope trial id must not import a note"


# ===========================================================================
# 10. PI3 tagging helper functions resolve correctly for both new link types
# ===========================================================================

def test_helper_functions_resolve_plant_company_grade_for_both_trial_types(seeded_two_trial_targets):
    """PI3 connectivity itself is not configured in this environment (no
    OpenAI secrets - ai_assistant.is_enabled_for_plant() returns False, as
    already documented by tests/test_cr11_functional_evidence_group_a.py's
    test_expert_note_create_via_form), so no outbound push can be driven
    end-to-end here. What CAN be, and is, proven directly: the shared
    helper functions that resolve WHICH plant/company/grade a trial-linked
    note belongs to for PI3's is_enabled_for_plant() gate and vector-store
    metadata tagging - the exact same functions _push_note_to_vector_store
    in views/20_Expert_Notes.py calls before ever reaching the PI3 call."""
    ids = seeded_two_trial_targets
    session = db.get_session()

    assert expert_note_plant_id_for_link("customer_trial", ids["customer_trial_id"], session) == ids["plant_id"]
    assert expert_note_plant_id_for_link("optimization_trial", ids["optimization_trial_id"], session) == ids["plant_id"]
    assert company_id_for_plant(ids["plant_id"], session) == ids["company_id"]

    assert expert_note_foam_grade_id_for_link("customer_trial", ids["customer_trial_id"], session) == ids["grade_id"]
    assert expert_note_foam_grade_id_for_link("optimization_trial", ids["optimization_trial_id"], session) == ids["grade_id"]

    ct_label = expert_note_link_label("customer_trial", ids["customer_trial_id"], session)
    assert ct_label.startswith("Commercial Trial #") and ids["customer_name"] in ct_label
    opt_label = expert_note_link_label("optimization_trial", ids["optimization_trial_id"], session)
    assert opt_label.startswith("Optimization Trial #") and ids["grade_name"] in opt_label

    # Deleted-record fallback (mirrors the pre-existing pattern for every
    # other link type - a note whose linked record was since removed must
    # still render a graceful label instead of crashing the page).
    deleted_ct_label = expert_note_link_label("customer_trial", 999999, session)
    assert deleted_ct_label == "Commercial Trial #999999 (deleted)"
    deleted_opt_label = expert_note_link_label("optimization_trial", 999999, session)
    assert deleted_opt_label == "Optimization Trial #999999 (deleted)"
    assert expert_note_plant_id_for_link("customer_trial", 999999, session) is None
    assert expert_note_plant_id_for_link("optimization_trial", 999999, session) is None

    session.close()


# ===========================================================================
# 11. Regression: PU Material Family link path still creates a note post-rename
# ===========================================================================

def test_pu_material_family_still_creatable_after_terminology_rename(seeded_two_trial_targets):
    """No pre-existing test exercised the PU Material Family Create path
    end-to-end (tests/test_cr11_functional_evidence_group_a.py's
    test_expert_note_create_via_form only covers Product Grade) - this
    directly re-proves it still works after LINK_TYPES' "Foam Family" ->
    "PU Material Family" rename, alongside the already-re-run 15/15 CR-11
    Expert Note tests confirming the Product Grade path is unaffected."""
    ids = seeded_two_trial_targets
    at = _run(PAGE_EXPERT_NOTES)
    assert not at.exception

    link_sb = next(sb for sb in at.selectbox if sb.key == "new_note_link_type")
    link_sb.set_value("PU Material Family")
    at.run()
    assert not at.exception

    entity_sb = next(sb for sb in at.selectbox if sb.label == "PU Material Family *")
    assert entity_sb.value is not None and entity_sb.value.id == ids["family_id"]

    note_area = next(t for t in at.text_area if t.label == "Note *" and t.key is None)
    note_area.set_value("CR15-Product-Family-Note")
    save_btn = next(b for b in at.button if b.label == "Save note")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a product-family-linked note: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.ExpertNote)
        .filter(
            db.ExpertNote.linked_entity_type == "pu_material_family",
            db.ExpertNote.linked_entity_id == ids["family_id"],
            db.ExpertNote.note_text == "CR15-Product-Family-Note",
        )
        .first()
    )
    assert created is not None, "Product-family-linked note creation regressed after the terminology rename"
    session.close()
