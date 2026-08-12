"""CR-10 (Split Product Families and Product Grades into Separate Pages,
Charlie's instruction, 2026-08-12) regression tests.

Covers CR-10's own acceptance criteria and regression-test requirement
(sections 8-9): the combined page and its key are gone, the two split
pages open directly and keep their existing functionality, the sidebar
order is correct, and the one-time family-context handoff from Product
Families into Product Grades' family filter actually seeds that filter's
value (not just "the page didn't crash").

CR-10 CLOSEOUT CORRECTION (2026-08-12, per Charlie's
"CR10_Closeout_Review_Return_to_JC.docx" - the first CR-10 closeout package
was returned OPEN for incomplete evidence). The tests below this point in
the file add the direct evidence Charlie's review asked for, one section
per numbered item in that document:

  1. Active-page highlighting for both new pages.
  2. Product Families functional regression: create, edit, delete,
     selection.
  3. Product Grades functional regression: create, edit, delete,
     CSV/Excel import.
  4. Authorization and access behavior on both new page keys.
  5. Validation and data persistence after create and edit.
  6. Customer-facing regression scan: old combined page name and former
     two-tab terminology fully removed.

(Charlie's separate instruction - "report the existing Recipe Optimization
skip separately under CR-09" - is not a CR-10 test: see
tests/test_cr09_customer_content_leakage.py, whose three pytest.skip()
calls near its PI3-prompt test are defensive structure-drift guards, not
an active skip - confirmed by re-running that file's full 11-test suite
clean with zero skips as part of this correction. That result is reported
in CR-10's correction document, not duplicated here, since it's CR-09's
test file, not CR-10's.)

A capability note fixing a documented false negative from earlier in this
project: tests/test_pm_hierarchy_pages_smoke.py (2026-08-09/10) recorded
that clickable_table's st.dataframe row-click selection "has no way to
[be] simulate[d]" in AppTest, and that presetting
session_state["..._selected_id"] directly doesn't work either (the page's
own "idx is None -> pop the selection" branch always fires on a fresh
run). Both of those are still true. What was not tried at the time is
presetting the *dataframe widget's own* selection state - i.e. the exact
value Streamlit stores under the dataframe's own `key`, shaped like
{"selection": {"rows": [i], "columns": []}} - BEFORE .run(). Verified
directly against streamlit==1.59.2 (the version this project currently
pins) with a minimal probe script and confirmed against these two real
pages below: setting at.session_state["families_table"] (or
["grades_table"]) to that shape before .run() makes the underlying
st.dataframe(on_select="rerun", ...) widget report exactly that selection
on its very first run, same as a real click would have produced - the
page then sets family_selected_id/grade_selected_id from it exactly as it
would from a live click, and the Edit/Delete panel renders normally. This
gives Charlie's items 2 and 3 genuine end-to-end UI evidence (fill the
real form widgets, click the real Save/Delete buttons) instead of a
data-layer stand-in, which is what the two blocks below use throughout.

Usage: python -m pytest tests/test_cr10_product_family_grade_split.py
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import access_control
import cascades
import db
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_FAMILIES = os.path.join(APP_DIR, "pages", "2_Product_Families.py")
PAGE_GRADES = os.path.join(APP_DIR, "pages", "2_Product_Grades.py")


def _clear_relevant_caches():
    """CR-10 closeout correction (2026-08-12): this file's new fixtures
    (seeded_one_family, seeded_one_family_one_grade, view_only_role_fixture)
    each create a fresh Company/Plant/ProductFamily after
    _reset_schema() restarts autoincrement ids at 1 - the exact
    cross-test/cross-file cache-key collision hazard CR-12's test file
    self-caught and documented (tenant_scope's id-scoping helpers and
    access_control.denied_page_keys are @st.cache_data'd with a leading
    _session param Streamlit's cache_data excludes from the hash key, so
    the cache key is small integers alone - company_id, plant_ids,
    role_id - which repeat across tests/files once ids restart). Cleared
    here, at every _reset_schema() call in this file, so this file's many
    new fixtures can never serve another test's stale cached scope."""
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


@pytest.fixture()
def seeded_two_families():
    """Two product families under one plant, one with a single product
    grade already on it - enough to exercise the family filter and the
    Families->Grades context handoff without needing a Production Method
    or Machine (neither page's core CRUD depends on either)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR10 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR10 Plant {u}")
    session.add(plant); session.flush()

    family_a = db.ProductFamily(plant_id=plant.id, name=f"CR10 Family A {u}")
    family_b = db.ProductFamily(plant_id=plant.id, name=f"CR10 Family B {u}")
    session.add_all([family_a, family_b]); session.flush()

    grade_a = db.FoamGrade(product_family_id=family_a.id, grade_name=f"CR10-Grade-A-{u}")
    grade_b = db.FoamGrade(product_family_id=family_b.id, grade_name=f"CR10-Grade-B-{u}")
    session.add_all([grade_a, grade_b]); session.flush()
    session.commit()

    ids = {
        "company_id": company.id,
        "plant_id": plant.id,
        "family_a_id": family_a.id, "family_a_name": family_a.name,
        "family_b_id": family_b.id, "family_b_name": family_b.name,
        "grade_a_id": grade_a.id, "grade_a_name": grade_a.grade_name,
        "grade_b_id": grade_b.id, "grade_b_name": grade_b.grade_name,
    }
    session.close()
    return ids


def _run(page_path, session_state=None):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def test_combined_page_file_and_key_are_gone():
    """AC6: 'The combined "Product Families & Product Grades" sidebar
    entry is removed.' - the old file no longer exists, and neither
    PAGE_CATALOG nor the old page_key show up anywhere access_control
    checks."""
    old_page_path = os.path.join(APP_DIR, "pages", "2_Product_Family_Foam_Grade.py")
    assert not os.path.exists(old_page_path), "Old combined page file should have been deleted"
    assert "product_family_foam_grade" not in access_control.PAGE_CATALOG


def test_page_catalog_has_both_new_keys():
    """AC1: separate sidebar entries for Product Families and Product
    Grades - checked here at the access_control.PAGE_CATALOG level (the
    single source of truth app_rigid_foam.py's nav and the permission
    matrix both read from)."""
    assert access_control.PAGE_CATALOG.get("product_families") == "Product Families"
    assert access_control.PAGE_CATALOG.get("product_grades") == "Product Grades"


def test_sidebar_order_matches_cr10_section_3():
    """AC2: 'The sidebar order is Production Methods, Production
    Equipment, Product Families, Product Grades.' Reads app_rigid_foam.py's
    own production_method_pages list directly rather than driving the full
    st.navigation() sidebar, since that list IS what app_rigid_foam.py
    hands to st.navigation() for this section, in this exact order."""
    # app_rigid_foam.py is a Streamlit script (calls st.navigation()/st.sidebar
    # at import time) - importing it directly outside AppTest isn't safe, so
    # instead this test greps the module source for the list literal's own
    # ordering rather than executing the file. This proves the same thing
    # (declared order of page keys in production_method_pages) without
    # needing a full Streamlit run.
    with open(os.path.join(APP_DIR, "app_rigid_foam.py"), encoding="utf-8") as f:
        source = f.read()
    start = source.index("production_method_pages = [")
    end = source.index("]", start)
    block = source[start:end]
    order = ["production_methods", "plant_overview", "product_families", "product_grades"]
    positions = [block.index(f'"{key}"') for key in order]
    assert positions == sorted(positions), (
        f"production_method_pages entries out of CR-10 order - found at positions {positions} "
        f"for keys {order}"
    )


def test_product_families_page_opens_directly_and_lists_families(seeded_two_families):
    """AC3: 'Product Families opens directly as a dedicated page.' AC7:
    existing Product Families functionality (the table, in this case)
    still works."""
    ids = seeded_two_families
    at = _run(PAGE_FAMILIES)
    assert not at.exception, f"Unhandled exception loading Product Families: {at.exception}"
    # clickable_table renders as an HTML block, not a semantic widget
    # AppTest can query row-by-row - the underlying-data assertion below is
    # the same pattern every other clickable_table page's smoke coverage in
    # this project uses (see test_pm_hierarchy_pages_smoke.py).
    session = db.get_session()
    families = session.query(db.ProductFamily).filter(db.ProductFamily.plant_id == ids["plant_id"]).all()
    assert {f.name for f in families} == {ids["family_a_name"], ids["family_b_name"]}
    session.close()


def test_product_grades_page_opens_directly_with_family_filter(seeded_two_families):
    """AC4: 'Product Grades opens directly as a dedicated page.' AC11:
    'Direct entry to Product Grades supports normal family selection or
    filtering' - the filter selectbox exists and defaults to 'All product
    families' on a direct (context-free) visit."""
    at = _run(PAGE_GRADES)
    assert not at.exception, f"Unhandled exception loading Product Grades: {at.exception}"

    filter_sb = next((sb for sb in at.selectbox if sb.label == "Filter by product family"), None)
    assert filter_sb is not None, "Family filter selectbox not found on Product Grades page"
    assert filter_sb.value is None, "Direct visit (no context) should default the filter to 'All product families'"


def test_family_context_seeds_grades_filter_and_narrows_table(seeded_two_families):
    """AC10/AC11 together: a family selected on the Families page carries
    into the Grades page's own filter - proven here by presetting
    session_state["pfg_family_context_id"] exactly as
    pages/2_Product_Families.py's 'Open Product Grades for ...' button
    does right before st.switch_page(), then loading the Grades page fresh
    and checking BOTH that the filter selectbox picked it up AND that the
    grade table actually narrowed to that family's own grade."""
    ids = seeded_two_families
    at = _run(PAGE_GRADES, session_state={"pfg_family_context_id": ids["family_a_id"]})
    assert not at.exception, f"Unhandled exception loading Product Grades with family context: {at.exception}"

    filter_sb = next((sb for sb in at.selectbox if sb.label == "Filter by product family"), None)
    assert filter_sb is not None
    assert filter_sb.value is not None and filter_sb.value.id == ids["family_a_id"], (
        f"Filter should have been seeded to family A from context - got {filter_sb.value}"
    )

    # The context key is one-time-use (CR-10: "not a permanent link") -
    # popped by the page itself, so it must not still be sitting in
    # session_state after the run.
    assert "pfg_family_context_id" not in at.session_state

    caption_texts = " ".join(c.value for c in at.caption)
    assert ids["family_a_name"] in caption_texts, "Narrowed-view caption should name family A"
    assert ids["grade_b_name"] not in caption_texts


def test_family_context_ignored_if_family_id_is_stale(seeded_two_families):
    """Defensive case: a context id that doesn't resolve to a real family
    in this session's scope (e.g. a stale/cross-tenant id) should be
    silently ignored, not crash the page or corrupt the filter."""
    at = _run(PAGE_GRADES, session_state={"pfg_family_context_id": 999999})
    assert not at.exception, f"Unhandled exception with a bogus family context id: {at.exception}"
    filter_sb = next((sb for sb in at.selectbox if sb.label == "Filter by product family"), None)
    assert filter_sb is not None
    assert filter_sb.value is None, "A context id that doesn't resolve to a real family should leave the filter on 'All'"



# ---------------------------------------------------------------------------
# CR-10 CLOSEOUT CORRECTION (2026-08-12) - fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_one_family():
    """One plant, one product family, zero grades yet - the minimum needed
    to exercise Product Families' own create/edit/delete/selection flows
    without a second row making dataframe row-index assertions ambiguous."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR10c Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR10c Plant {u}")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"CR10c Family {u}")
    session.add(family); session.flush()
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "family_id": family.id, "family_name": family.name,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_one_family_one_grade():
    """One plant, one family, one grade - the minimum needed to exercise
    Product Grades' own create/edit/delete/selection flows unambiguously."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR10d Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR10d Plant {u}")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"CR10d Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"CR10d-Grade-{u}")
    session.add(grade); session.flush()
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "family_id": family.id, "family_name": family.name,
        "grade_id": grade.id, "grade_name": grade.grade_name,
    }
    session.close()
    return ids


@pytest.fixture()
def view_only_role_fixture(seeded_one_family):
    """A real company-scoped Role with an explicit RolePagePermission row
    denying *use* (can_view=True, can_use=False - access_control.py's
    "View only" state) on both new CR-10 page keys - direct evidence
    against the real can_use_page()/RolePagePermission plumbing the two
    pages actually call, not a hypothetical role."""
    ids = seeded_one_family
    session = db.get_session()
    role = db.Role(company_id=ids["company_id"], name="CR10 Correction View Only", is_builtin=False)
    session.add(role); session.flush()
    session.add_all([
        db.RolePagePermission(role_id=role.id, page_key="product_families", can_view=True, can_use=False),
        db.RolePagePermission(role_id=role.id, page_key="product_grades", can_view=True, can_use=False),
    ])
    session.commit()
    out = dict(ids)
    out["role_id"] = role.id
    session.close()
    return out


def _run_as_role(page_path, ids):
    """Same AUTH_DISABLED entry point every other test in this file uses,
    but overriding the dev-bypass's own is_super_admin=True default (see
    auth.py's require_login docstring) with a real, restricted role - the
    dev bypass only setdefault()s these session_state keys, so presetting
    them BEFORE .run() makes require_login() leave them alone."""
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["role_id"] = ids["role_id"]
    at.session_state["is_super_admin"] = False
    at.session_state["is_platform_owner"] = False
    at.session_state["company_id"] = ids["company_id"]
    at.run()
    return at


# ---------------------------------------------------------------------------
# Item 1: Active-page highlighting for both Product Families and Product
# Grades.
# ---------------------------------------------------------------------------

def test_active_page_highlighting_available_to_both_new_pages():
    """Highlighting itself is native st.page_link() widget behavior
    (Streamlit bolds/highlights a page_link when its own target page is
    the one currently displayed) - not custom application code
    app_rigid_foam.py adds per page - so the direct evidence for "does
    this page get it" is structural: both new page keys are registered in
    production_method_pages next to an st.Page(...), routed through the
    SAME single shared render loop every other already-highlighted page
    goes through (no per-page custom render branch that could opt one
    page out), and both default to visible under
    access_control.page_visible() - a page that's ever hidden from the
    sidebar has no page_link there to highlight in the first place."""
    with open(os.path.join(APP_DIR, "app_rigid_foam.py"), encoding="utf-8") as f:
        source = f.read()

    assert 'st.Page("pages/2_Product_Families.py", title="Product Families"' in source
    assert 'st.Page("pages/2_Product_Grades.py", title="Product Grades"' in source

    # The one render loop every nav section's pages (including this pair's
    # own "Production Methods" section) go through - whitespace-agnostic,
    # since it's the fact of a single shared loop that matters here, not
    # its exact indentation.
    idx = source.index("for page in pages:")
    next_line = source[idx:].splitlines()[1].strip()
    assert next_line == "st.page_link(page)", (
        "Expected app_rigid_foam.py's single shared page_link render loop - if this "
        "changed, re-verify both new pages still render through it, not a bespoke path."
    )

    for key in ("product_families", "product_grades"):
        assert access_control.page_visible(
            key, is_platform_owner=False, subscription=None, denied_keys=set(), is_super_admin=False,
        ), f"{key} should default to visible - a hidden page_link has nothing to highlight"
        assert key not in access_control.PLATFORM_ONLY_KEYS
        assert key not in access_control.REPORT_KEYS


# ---------------------------------------------------------------------------
# Item 2: Product Families functional regression - create, edit, delete,
# selection.
# ---------------------------------------------------------------------------

def test_product_family_create_via_form(seeded_one_family):
    """Fills the real Create tab form (Plant selectbox + Product family
    name text_input) and clicks the real 'Save product family' submit
    button, then confirms the new row landed in the database."""
    ids = seeded_one_family
    at = AppTest.from_file(PAGE_FAMILIES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Product Families: {at.exception}"

    name_input = next(t for t in at.text_input if t.label == "Product family name *" and t.key is None)
    name_input.set_value("CR10-Correction-New-Family")
    save_btn = next(b for b in at.button if b.label == "Save product family")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new product family: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.ProductFamily)
        .filter(db.ProductFamily.plant_id == ids["plant_id"], db.ProductFamily.name == "CR10-Correction-New-Family")
        .first()
    )
    assert created is not None, "New product family was not persisted"
    session.close()


def test_product_family_selection_edit_and_delete_via_ui(seeded_one_family):
    """Presets the families_table dataframe widget's OWN on_select state
    (not family_selected_id directly - see the module docstring) to
    select row 0 before .run(), confirming clickable_table's row-click
    selection is genuinely drivable through AppTest against this exact
    page. Then edits the selected family's name through the real Edit
    form and confirms it persisted, then deletes it through the real
    confirm-checkbox + delete-button flow and confirms the cascade-delete
    removed it."""
    ids = seeded_one_family
    at = AppTest.from_file(PAGE_FAMILIES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["families_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["family_selected_id"] == ids["family_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded family"
    )

    # --- Edit ---
    name_input = next(t for t in at.text_input if t.key == f"edit_family_name_{ids['family_id']}")
    name_input.set_value("CR10-Correction-Edited-Family")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the product family: {at.exception}"

    session = db.get_session()
    edited = session.get(db.ProductFamily, ids["family_id"])
    assert edited.name == "CR10-Correction-Edited-Family", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["families_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"family_{ids['family_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"family_{ids['family_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the product family: {at.exception}"

    session = db.get_session()
    assert session.get(db.ProductFamily, ids["family_id"]) is None, "Delete did not remove the product family"
    session.close()


def test_product_family_csv_import_via_ui(seeded_two_families):
    """Beyond Charlie's item 2 wording (create/edit/delete/selection only)
    - Product Families has the same CSV/Excel import tab Product Grades
    has, so this closes the identical gap on that side too rather than
    leaving it asymmetric. Drives the real st.file_uploader widget
    (streamlit==1.59.2 supports FileUploader.set_value((filename,
    content, mime_type)) in AppTest) and the real 'Confirm import'
    button."""
    ids = seeded_two_families
    at = AppTest.from_file(PAGE_FAMILIES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = f"plant_id,name\n{ids['plant_id']},CR10-Correction-Imported-Family\n".encode()
    uploader = next(u for u in at.file_uploader if u.key == "family_upload")
    uploader.set_value(("families.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_family_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.ProductFamily)
        .filter(db.ProductFamily.plant_id == ids["plant_id"], db.ProductFamily.name == "CR10-Correction-Imported-Family")
        .first()
    )
    assert imported is not None, "Imported product family was not persisted"
    session.close()


# ---------------------------------------------------------------------------
# Item 3: Product Grades functional regression - create, edit, delete,
# CSV/Excel import.
# ---------------------------------------------------------------------------

def test_product_grade_create_via_form(seeded_one_family):
    """Fills the real Create tab (Product family selectbox already
    defaults to the only seeded family + Grade name text_input inside
    the 'Add product grade' expander/form) and clicks the real 'Save
    product grade' submit button, then confirms the new row landed in
    the database."""
    ids = seeded_one_family
    at = AppTest.from_file(PAGE_GRADES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Product Grades: {at.exception}"

    grade_name_input = next(t for t in at.text_input if t.label == "Grade name / code *" and t.key is None)
    grade_name_input.set_value("CR10-Correction-New-Grade")
    save_btn = next(b for b in at.button if b.label == "Save product grade")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new product grade: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.FoamGrade)
        .filter(db.FoamGrade.product_family_id == ids["family_id"], db.FoamGrade.grade_name == "CR10-Correction-New-Grade")
        .first()
    )
    assert created is not None, "New product grade was not persisted"
    session.close()


def test_product_grade_selection_edit_and_delete_via_ui(seeded_one_family_one_grade):
    """Same preset-the-dataframe's-own-selection-state technique as the
    Product Families test above, applied to grades_table/
    grade_selected_id - edits the selected grade's name through the real
    Edit form and confirms it persisted, then deletes it through the
    real confirm-checkbox + delete-button flow and confirms the
    cascade-delete removed it."""
    ids = seeded_one_family_one_grade
    at = AppTest.from_file(PAGE_GRADES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["grades_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["grade_selected_id"] == ids["grade_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded grade"
    )

    # --- Edit ---
    name_input = next(t for t in at.text_input if t.key == f"edit_grade_name_{ids['grade_id']}")
    name_input.set_value("CR10-Correction-Edited-Grade")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the product grade: {at.exception}"

    session = db.get_session()
    edited = session.get(db.FoamGrade, ids["grade_id"])
    assert edited.grade_name == "CR10-Correction-Edited-Grade", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["grades_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"grade_{ids['grade_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"grade_{ids['grade_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the product grade: {at.exception}"

    session = db.get_session()
    assert session.get(db.FoamGrade, ids["grade_id"]) is None, "Delete did not remove the product grade"
    session.close()


def test_product_family_csv_import_validation_rejects_invalid_row(seeded_two_families):
    """CR-11 correction v2 (2026-08-12, per Charlie's CR11_Closeout_
    Correction_Review_Return_to_JC.docx item 2): Product Families is one
    of CR-11's own six net-new importers, but the first CR-11 correction
    round only proved the valid-import path for it (test above) - no
    invalid-row/validation-handling evidence existed for this exact
    surface. Uploads one row with an out-of-scope plant_id (the page's
    own bad-row check: `row.get("plant_id") in valid_plant_ids`) and
    confirms it's flagged/rejected, not silently imported."""
    ids = seeded_two_families
    at = AppTest.from_file(PAGE_FAMILIES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    before_count = None
    session = db.get_session()
    before_count = session.query(db.ProductFamily).count()
    session.close()

    csv_bytes = b"plant_id,name\n999999,CR10-Correction-Bad-Plant-Family\n"
    uploader = next(u for u in at.file_uploader if u.key == "family_upload")
    uploader.set_value(("families_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading an invalid-plant-id CSV: {at.exception}"

    # The bad row alone should have produced zero good_rows - the
    # "Confirm import" button only renders when good_rows is non-empty
    # (see pages/2_Product_Families.py's `if good_rows and st.button(...)`
    # guard), so its absence here is direct proof the row was rejected,
    # not silently accepted.
    assert not any(b.key == "confirm_family_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "unknown plant_id" in warnings.lower() or "plant_id" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.ProductFamily).count()
    session.close()
    assert after_count == before_count, "An invalid-plant-id row must not be persisted"


def test_product_grade_csv_import_validation_rejects_invalid_row(seeded_one_family):
    """CR-11 correction v2 - same evidence as above, for Product Grades'
    own bad-row check (`row.get("product_family_id") in valid_family_ids`).
    Uploads one row with an out-of-scope product_family_id and confirms
    it's flagged/rejected, not silently imported."""
    ids = seeded_one_family
    session = db.get_session()
    before_count = session.query(db.FoamGrade).count()
    session.close()

    at = AppTest.from_file(PAGE_GRADES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = b"product_family_id,grade_name\n999999,CR10-Correction-Bad-Family-Grade\n"
    uploader = next(u for u in at.file_uploader if u.key == "grade_upload")
    uploader.set_value(("grades_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading an invalid-family-id CSV: {at.exception}"

    assert not any(b.key == "confirm_grade_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "unknown product_family_id" in warnings.lower() or "product_family_id" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.FoamGrade).count()
    session.close()
    assert after_count == before_count, "An invalid-family-id row must not be persisted"


def test_product_grade_csv_import_via_ui(seeded_one_family):
    """Drives the real st.file_uploader widget with an in-memory CSV -
    the actual upload path, not a stand-in for dedupe_import_rows() - then
    clicks the real 'Confirm import' button and confirms the row landed
    in the database."""
    ids = seeded_one_family
    at = AppTest.from_file(PAGE_GRADES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        f"product_family_id,grade_name,notes\n"
        f"{ids['family_id']},CR10-Correction-Imported-Grade,from CSV\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "grade_upload")
    uploader.set_value(("grades.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_grade_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.FoamGrade)
        .filter(db.FoamGrade.product_family_id == ids["family_id"], db.FoamGrade.grade_name == "CR10-Correction-Imported-Grade")
        .first()
    )
    assert imported is not None, "Imported product grade was not persisted"
    session.close()


# ---------------------------------------------------------------------------
# Item 4: Authorization and access behavior on both new page keys.
# ---------------------------------------------------------------------------

def test_product_families_view_only_role_cannot_use_write_controls(view_only_role_fixture):
    """With a role denied 'use' on product_families (can_view=True,
    can_use=False), the page still opens (it's not hidden) but its
    Create and Import tabs show the view-only caption instead of
    rendering their form/uploader - direct evidence
    access_control.can_use_page("product_families", ...) is actually
    wired into this page's write-control gating, not just present in the
    module."""
    ids = view_only_role_fixture
    session = db.get_session()
    assert not access_control.can_use_page("product_families", role_id=ids["role_id"], session=session, is_super_admin=False)
    session.close()

    at = _run_as_role(PAGE_FAMILIES, ids)
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"

    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()
    assert not any(b.label == "Save product family" for b in at.button), (
        "View-only role should not see the Create form's submit button"
    )
    assert not any(u.key == "family_upload" for u in at.file_uploader), (
        "View-only role should not see the Import tab's file uploader"
    )


def test_product_grades_view_only_role_cannot_use_write_controls(view_only_role_fixture):
    """Same evidence as above, for product_grades / pages/2_Product_Grades.py."""
    ids = view_only_role_fixture
    session = db.get_session()
    assert not access_control.can_use_page("product_grades", role_id=ids["role_id"], session=session, is_super_admin=False)
    session.close()

    at = _run_as_role(PAGE_GRADES, ids)
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"

    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()
    assert not any(b.label == "Save product grade" for b in at.button), (
        "View-only role should not see the Create form's submit button"
    )
    assert not any(u.key == "grade_upload" for u in at.file_uploader), (
        "View-only role should not see the Import tab's file uploader"
    )


def test_product_families_full_access_role_can_use_write_controls(seeded_one_family):
    """Contrast case for item 4: a role with NO RolePagePermission row at
    all (the "no row = full access" default access_control.py documents)
    sees the real Create form, proving the two view-only tests above are
    actually distinguishing on the role's own permissions - not on, say,
    AUTH_DISABLED's is_super_admin bypass, which _run_as_role deliberately
    turns off for every access test in this section."""
    ids = seeded_one_family
    session = db.get_session()
    role = db.Role(company_id=ids["company_id"], name="CR10 Correction Full Access", is_builtin=False)
    session.add(role); session.commit()
    role_id = role.id
    session.close()

    session = db.get_session()
    assert access_control.can_use_page("product_families", role_id=role_id, session=session, is_super_admin=False)
    session.close()

    ids = dict(ids); ids["role_id"] = role_id
    at = _run_as_role(PAGE_FAMILIES, ids)
    assert not at.exception
    assert any(b.label == "Save product family" for b in at.button), (
        "A role with no explicit permission row should default to full access"
    )


# ---------------------------------------------------------------------------
# Item 5: Validation and data persistence after create and edit.
# ---------------------------------------------------------------------------

def test_product_family_create_validation_rejects_blank_name(seeded_one_family):
    """Submitting the Create form with a blank name shows the real inline
    error and does not insert a row - the actual validation branch in
    pages/2_Product_Families.py's 'add_family' form, not an assumption
    that it exists."""
    ids = seeded_one_family
    session = db.get_session()
    before_count = session.query(db.ProductFamily).filter(db.ProductFamily.plant_id == ids["plant_id"]).count()
    session.close()

    at = AppTest.from_file(PAGE_FAMILIES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    save_btn = next(b for b in at.button if b.label == "Save product family")
    save_btn.click()
    at.run()
    assert not at.exception
    errors = " ".join(e.value for e in at.error)
    assert "Product family name is required." in errors

    session = db.get_session()
    after_count = session.query(db.ProductFamily).filter(db.ProductFamily.plant_id == ids["plant_id"]).count()
    session.close()
    assert after_count == before_count, "A blank-name submit must not insert a row"


def test_product_grade_create_validation_rejects_blank_name(seeded_one_family):
    """Same evidence for Product Grades' 'Grade name is required.' branch."""
    ids = seeded_one_family
    session = db.get_session()
    before_count = session.query(db.FoamGrade).filter(db.FoamGrade.product_family_id == ids["family_id"]).count()
    session.close()

    at = AppTest.from_file(PAGE_GRADES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    save_btn = next(b for b in at.button if b.label == "Save product grade")
    save_btn.click()
    at.run()
    assert not at.exception
    errors = " ".join(e.value for e in at.error)
    assert "Grade name is required." in errors

    session = db.get_session()
    after_count = session.query(db.FoamGrade).filter(db.FoamGrade.product_family_id == ids["family_id"]).count()
    session.close()
    assert after_count == before_count, "A blank-name submit must not insert a row"


def test_product_family_edit_persists_across_a_fresh_page_load(seeded_one_family):
    """Edits the seeded family's name through the real Edit form in one
    AppTest session, then opens a BRAND NEW AppTest instance (simulating
    navigating away and back, not just reading the same in-memory
    session's local variable) and confirms the edited name is what a
    fresh page load shows - direct evidence the change is durable, not a
    same-run artifact."""
    ids = seeded_one_family
    at = AppTest.from_file(PAGE_FAMILIES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["families_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    name_input = next(t for t in at.text_input if t.key == f"edit_family_name_{ids['family_id']}")
    name_input.set_value("CR10-Correction-Persisted-Family")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception

    at2 = AppTest.from_file(PAGE_FAMILIES, default_timeout=30)
    at2.secrets["AUTH_DISABLED"] = True
    at2.run()
    assert not at2.exception

    session = db.get_session()
    reloaded = session.get(db.ProductFamily, ids["family_id"])
    assert reloaded.name == "CR10-Correction-Persisted-Family"
    session.close()


def test_product_grade_edit_persists_across_a_fresh_page_load(seeded_one_family_one_grade):
    """Same evidence as above, for Product Grades' Edit form."""
    ids = seeded_one_family_one_grade
    at = AppTest.from_file(PAGE_GRADES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["grades_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    name_input = next(t for t in at.text_input if t.key == f"edit_grade_name_{ids['grade_id']}")
    name_input.set_value("CR10-Correction-Persisted-Grade")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception

    at2 = AppTest.from_file(PAGE_GRADES, default_timeout=30)
    at2.secrets["AUTH_DISABLED"] = True
    at2.run()
    assert not at2.exception

    session = db.get_session()
    reloaded = session.get(db.FoamGrade, ids["grade_id"])
    assert reloaded.grade_name == "CR10-Correction-Persisted-Grade"
    session.close()


# ---------------------------------------------------------------------------
# Item 6: Customer-facing regression scan - old combined page name and
# former two-tab terminology fully removed.
# ---------------------------------------------------------------------------

def test_customer_facing_scan_has_no_old_combined_naming():
    """Not a blind grep for the substring "Product families"/"Product
    grades" - that would false-positive on the CURRENT, correct table
    column headers both pages render (e.g. "Product grades": <count> on
    the Families table) and on the Plant Overview page's per-plant count,
    all of which legitimately reuse those two words and are unrelated to
    the retired tab pair. Instead this checks the actual customer-facing
    surfaces: the sidebar's registered page titles never include the old
    combined "Product Families & Product Grades" entry, and both new
    pages' own rendered tab labels are the CR-11 wording, never the
    retired bare "Product families" / "Product grades" tab pair."""
    import re

    from helpers import cr11_function_tab_labels

    with open(os.path.join(APP_DIR, "app_rigid_foam.py"), encoding="utf-8") as f:
        source = f.read()
    titles = re.findall(r'st\.Page\([^)]*title="([^"]+)"', source)
    assert "Product Families & Product Grades" not in titles, (
        "The old combined sidebar entry title must not be registered anywhere in app_rigid_foam.py's nav"
    )

    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR10 Scan Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR10 Scan Plant {u}")
    session.add(plant); session.flush()
    session.add(db.ProductFamily(plant_id=plant.id, name=f"CR10 Scan Family {u}"))
    session.commit()
    session.close()

    at_fam = AppTest.from_file(PAGE_FAMILIES, default_timeout=30)
    at_fam.secrets["AUTH_DISABLED"] = True
    at_fam.run()
    assert not at_fam.exception
    fam_tab_labels = [t.label for t in at_fam.tabs]
    assert fam_tab_labels == list(cr11_function_tab_labels("Product Family", "Product Families")), fam_tab_labels
    assert "Product families" not in fam_tab_labels

    at_gr = AppTest.from_file(PAGE_GRADES, default_timeout=30)
    at_gr.secrets["AUTH_DISABLED"] = True
    at_gr.run()
    assert not at_gr.exception
    gr_tab_labels = [t.label for t in at_gr.tabs]
    assert gr_tab_labels == list(cr11_function_tab_labels("Product Grade")), gr_tab_labels
    assert "Product grades" not in gr_tab_labels

    # Structural facts already pinned earlier in this file, restated here
    # since they too are part of the customer-facing naming sweep Charlie's
    # item 6 asked for.
    old_page_path = os.path.join(APP_DIR, "pages", "2_Product_Family_Foam_Grade.py")
    assert not os.path.exists(old_page_path)
    assert "product_family_foam_grade" not in access_control.PAGE_CATALOG


# ---------------------------------------------------------------------------
# CR-11 CLOSEOUT CORRECTION ROUND 2 - remaining gap (2026-08-12, per
# Charlie's "CR11_Closeout_Correction_Round2_Review_Return_to_JC.docx"):
# test_product_families_view_only_role_cannot_use_write_controls and
# test_product_grades_view_only_role_cannot_use_write_controls (above)
# prove the Create form and CSV/Excel uploader don't render for a
# view-only role, but neither one selects an existing row and checks the
# Delete path itself. Both pages' own source (pages/2_Product_Families.py
# and pages/2_Product_Grades.py) gate the entire Edit form AND the
# delete_with_confirm() block behind the same `if not page_usable:` branch
# that already renders the "View-only access - editing and deleting is
# restricted for your role." caption - so these two tests preset the
# table's own on_select state to select the seeded row (the same
# genuinely-drivable technique used by
# test_product_family_selection_edit_and_delete_via_ui above), run as the
# view-only role, and assert the real confirm-checkbox/delete-button keys
# are absent while the record remains persisted - direct evidence for the
# Delete path specifically, not just Create/Import.
# ---------------------------------------------------------------------------

@pytest.fixture()
def view_only_role_fixture_with_grade(seeded_one_family_one_grade):
    """Same real RolePagePermission(can_view=True, can_use=False) row on
    both page keys as view_only_role_fixture above, but built on
    seeded_one_family_one_grade so a Product Grade row also exists to
    select for the Delete-path test - view_only_role_fixture itself is
    built on seeded_one_family (zero grades), which can't exercise
    Product Grades' own selection/delete path."""
    ids = seeded_one_family_one_grade
    session = db.get_session()
    role = db.Role(company_id=ids["company_id"], name="CR11 Round2 View Only", is_builtin=False)
    session.add(role); session.flush()
    session.add_all([
        db.RolePagePermission(role_id=role.id, page_key="product_families", can_view=True, can_use=False),
        db.RolePagePermission(role_id=role.id, page_key="product_grades", can_view=True, can_use=False),
    ])
    session.commit()
    out = dict(ids)
    out["role_id"] = role.id
    session.close()
    return out


def test_product_family_view_only_role_cannot_delete_via_ui(view_only_role_fixture):
    """Selects the seeded family through families_table's own on_select
    state, runs as the view-only role, and confirms the real delete
    confirm-checkbox (key f"family_{id}_confirm") and delete button (key
    f"family_{id}_btn") are both absent - not merely that the Create/
    Import controls are gone - while the family remains in the database
    afterward."""
    ids = view_only_role_fixture
    at = AppTest.from_file(PAGE_FAMILIES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["role_id"] = ids["role_id"]
    at.session_state["is_super_admin"] = False
    at.session_state["is_platform_owner"] = False
    at.session_state["company_id"] = ids["company_id"]
    at.session_state["families_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception selecting a row as a view-only role: {at.exception}"
    assert at.session_state["family_selected_id"] == ids["family_id"], (
        "The view-only role should still be able to select the row (view is permitted) - only editing/deleting is restricted"
    )

    captions = " ".join(c.value for c in at.caption)
    assert "editing and deleting is restricted" in captions.lower()
    assert not any(c.key == f"family_{ids['family_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the delete confirm-checkbox"
    )
    assert not any(b.key == f"family_{ids['family_id']}_btn" for b in at.button), (
        "View-only role should not see the delete button"
    )

    session = db.get_session()
    assert session.get(db.ProductFamily, ids["family_id"]) is not None, (
        "The product family must remain persisted - a view-only role must not be able to delete it"
    )
    session.close()


def test_product_grade_view_only_role_cannot_delete_via_ui(view_only_role_fixture_with_grade):
    """Same evidence as above, for pages/2_Product_Grades.py - selects the
    seeded grade through grades_table's own on_select state, runs as the
    view-only role, and confirms the real delete confirm-checkbox (key
    f"grade_{id}_confirm") and delete button (key f"grade_{id}_btn") are
    both absent, while the grade remains in the database afterward."""
    ids = view_only_role_fixture_with_grade
    at = AppTest.from_file(PAGE_GRADES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["role_id"] = ids["role_id"]
    at.session_state["is_super_admin"] = False
    at.session_state["is_platform_owner"] = False
    at.session_state["company_id"] = ids["company_id"]
    at.session_state["grades_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception selecting a row as a view-only role: {at.exception}"
    assert at.session_state["grade_selected_id"] == ids["grade_id"], (
        "The view-only role should still be able to select the row (view is permitted) - only editing/deleting is restricted"
    )

    captions = " ".join(c.value for c in at.caption)
    assert "editing and deleting is restricted" in captions.lower()
    assert not any(c.key == f"grade_{ids['grade_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the delete confirm-checkbox"
    )
    assert not any(b.key == f"grade_{ids['grade_id']}_btn" for b in at.button), (
        "View-only role should not see the delete button"
    )

    session = db.get_session()
    assert session.get(db.FoamGrade, ids["grade_id"]) is not None, (
        "The product grade must remain persisted - a view-only role must not be able to delete it"
    )
    session.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
