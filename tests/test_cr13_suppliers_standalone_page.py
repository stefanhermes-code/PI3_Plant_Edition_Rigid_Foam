"""CR-13 (Split Suppliers into a Standalone Page, 2026-08-12) - direct
executed evidence for every CR-13 acceptance criterion and regression-test
requirement (sections 8/9 of CR13_Split_Suppliers_into_Standalone_Page.docx).

Supplier management used to live as a nested "Suppliers" tab inside
views/14_Raw_Materials.py, sharing that page's own "raw_materials"
access_control key. This CR moved it to views/32_Suppliers.py with its own
"suppliers" key. Every test that used to prove Supplier behavior against
PAGE_RAWMAT (tests/test_cr11_functional_evidence_group_c.py's Group C.3b,
plus its correction-v2 view-only-delete-block and import-validation tests)
is rebuilt here against the new standalone page - see that file's own
module docstring for the explicit pointer to this one.

Reuses the same established, already-verified patterns from
tests/test_cr10_product_family_grade_split.py and
tests/test_cr11_functional_evidence_group_c.py:
  - os.environ.setdefault("DATABASE_URL", "sqlite://") + sys.path boilerplate.
  - db.init_db() + db.Base.metadata.drop_all/create_all per fixture, with
    _clear_relevant_caches() called from every _reset_schema().
  - SQLAlchemy ORM seeding with a uuid.uuid4().hex[:8] suffix on names for
    uniqueness.
  - Presetting the dataframe widget's OWN on_select state (e.g.
    at.session_state["supplier_table"] = {"selection": {"rows": [0],
    "columns": []}}) BEFORE .run() to genuinely drive clickable_table's
    row-click selection.
  - Presetting role_id/is_super_admin/is_platform_owner/company_id in
    session_state BEFORE .run() to override the AUTH_DISABLED dev-bypass's
    setdefault()-based is_super_admin=True default, so a real restricted
    role can be tested.
  - at.secrets["AUTH_DISABLED"] = True for every AppTest run.

Usage: python -m pytest tests/test_cr13_suppliers_standalone_page.py -v
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
from helpers import cr11_function_tab_labels

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_SUPPLIERS = os.path.join(APP_DIR, "views", "32_Suppliers.py")
PAGE_RAWMAT = os.path.join(APP_DIR, "views", "14_Raw_Materials.py")


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


# ---------------------------------------------------------------------------
# Acceptance criteria 1, 3: standalone page registration/visibility and
# exact wording/order.
# ---------------------------------------------------------------------------

def test_suppliers_page_key_registered_in_page_catalog():
    """Acceptance criterion 1 (part): a dedicated "suppliers" page_key
    exists in access_control.PAGE_CATALOG, independent of "raw_materials" -
    direct proof this is a real, separately-permissioned page, not a
    relabeled tab still sharing the old key."""
    assert "suppliers" in access_control.PAGE_CATALOG
    assert access_control.PAGE_CATALOG["suppliers"] == "Suppliers"


def test_suppliers_page_registered_in_nav():
    """Acceptance criterion 1: Suppliers appears as its own st.Page entry
    in app_rigid_foam.py's navigation, in the same "Formulations" section
    Raw Materials lives in (CR-13 section 7 keeps the current section label
    unchanged for this CR) - not merely a key in access_control with no
    actual nav entry.

    app_rigid_foam.py is a Streamlit script (calls st.navigation()/st.sidebar
    at import time) - importing it directly outside AppTest isn't safe (see
    tests/test_cr10_product_family_grade_split.py's own
    test_sidebar_order_matches_cr10_section_3 for the same established
    reasoning), so this greps the module source for the formulation_pages
    list literal's own ordering instead of executing the file."""
    with open(os.path.join(APP_DIR, "app_rigid_foam.py"), encoding="utf-8") as f:
        source = f.read()
    start = source.index("formulation_pages = [")
    end = source.index("]", start)
    block = source[start:end]
    assert '"suppliers"' in block
    assert '"raw_materials"' in block
    assert 'st.Page("views/32_Suppliers.py"' in block
    # Suppliers immediately follows Raw Materials, still inside Formulations.
    raw_materials_pos = block.index('"raw_materials"')
    suppliers_pos = block.index('"suppliers"')
    between = block[raw_materials_pos:suppliers_pos]
    assert '"recipes"' not in between, (
        "Suppliers must sit immediately after Raw Materials in formulation_pages, not after Recipes"
    )


@pytest.fixture()
def seeded_company_only():
    """One Company only - the minimum for the Suppliers page's Create tab
    Company selectbox to have exactly one option, with nothing to click."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR13 Supplier Co {u}", is_platform_owner=True)
    session.add(company)
    session.commit()
    ids = {"company_id": company.id, "company_name": company.name}
    session.close()
    return ids


def test_suppliers_page_opens_directly_and_shows_cr11_triplet(seeded_company_only):
    """Acceptance criteria 1 and 3: the standalone page opens directly
    (AppTest.from_file against views/32_Suppliers.py, not reached through
    Raw Materials), and exposes exactly the three CR-11-standard tabs -
    'Create Supplier', 'Edit/Delete Supplier', 'CSV/Excel import Suppliers'
    - in that exact order and wording, with no other record type's tabs
    mixed in (unlike the old nested arrangement, which always rendered
    inside the outer Raw Material page)."""
    at = _run(PAGE_SUPPLIERS)
    assert not at.exception, f"Unhandled exception opening the standalone Suppliers page: {at.exception}"

    labels = [t.label for t in at.tabs]
    expected = list(cr11_function_tab_labels("Supplier"))
    assert labels == expected, f"Expected exactly {expected} in order, got {labels}"


# ---------------------------------------------------------------------------
# Acceptance criteria 4, 6, 7: Supplier create/edit/delete/import continue
# to work, and Raw Material <-> Supplier relationships remain intact.
# ---------------------------------------------------------------------------

def test_supplier_create_via_form(seeded_company_only):
    """Direct evidence the Create tab's real form (Supplier name text_input
    + 'Add supplier' submit button) persists a new Supplier row on the
    standalone page."""
    ids = seeded_company_only
    at = _run(PAGE_SUPPLIERS)

    name_input = next(t for t in at.text_input if t.label == "Supplier name *" and t.key is None)
    name_input.set_value("CR13-New-Supplier")
    save_btn = next(b for b in at.button if b.label == "Add supplier")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new supplier: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.Supplier)
        .filter(db.Supplier.company_id == ids["company_id"], db.Supplier.name == "CR13-New-Supplier")
        .first()
    )
    assert created is not None, "New supplier was not persisted"
    session.close()


@pytest.fixture()
def seeded_supplier():
    """One Company + one existing Supplier - the minimum to exercise
    selection/edit/delete on the standalone page's own Edit/Delete tab."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR13 SupplierEdit Co {u}", is_platform_owner=True)
    session.add(company)
    session.flush()
    supplier = db.Supplier(company_id=company.id, name=f"CR13 Supplier {u}", active=True)
    session.add(supplier)
    session.commit()
    ids = {"company_id": company.id, "supplier_id": supplier.id, "supplier_name": supplier.name}
    session.close()
    return ids


def test_supplier_selection_edit_and_delete_via_ui(seeded_supplier):
    """Presets the supplier_table dataframe widget's OWN on_select state
    (the same verified technique used app-wide) to select row 0, then edits
    the selected supplier's name through the real 'Save changes' form and
    confirms it persisted, then deletes it through the real confirm-
    checkbox + delete-button flow and confirms it's gone - all against the
    standalone page, its own separate widget keys."""
    ids = seeded_supplier
    at = _run(PAGE_SUPPLIERS, session_state={"supplier_table": {"selection": {"rows": [0], "columns": []}}})
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["supplier_selected_id"] == ids["supplier_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded supplier"
    )

    # --- Edit ---
    name_input = next(t for t in at.text_input if t.key == f"edit_supplier_name_{ids['supplier_id']}")
    name_input.set_value("CR13-Edited-Supplier")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the supplier: {at.exception}"

    session = db.get_session()
    edited = session.get(db.Supplier, ids["supplier_id"])
    assert edited.name == "CR13-Edited-Supplier", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["supplier_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"supplier_{ids['supplier_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"supplier_{ids['supplier_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the supplier: {at.exception}"

    session = db.get_session()
    assert session.get(db.Supplier, ids["supplier_id"]) is None, "Delete did not remove the supplier"
    session.close()


@pytest.fixture()
def seeded_supplier_with_linked_raw_material(seeded_supplier):
    """Extends seeded_supplier with a RawMaterial whose default_supplier
    text snapshot matches the supplier's current name - the minimum needed
    to prove renaming a supplier on the STANDALONE page still cascades onto
    RawMaterial.default_supplier exactly as it did on the old nested tab
    (acceptance criteria 6, 7: Raw Material <-> Supplier relationships
    remain intact after the split, since default_supplier is a text
    snapshot, not a foreign key)."""
    ids = seeded_supplier
    session = db.get_session()
    category = db.RawMaterialCategory(controlled_id="RMC-CR13-TEST", name="CR13 Test Category", sort_order=1, active=True)
    session.add(category)
    session.flush()
    subcategory = db.RawMaterialCategory(
        controlled_id="RMC-CR13-TEST-SUB", name="CR13 Test Subcategory", sort_order=1,
        parent_category_id=category.id, active=True, is_exception_only=False,
    )
    session.add(subcategory)
    session.flush()
    material = db.RawMaterial(
        company_id=ids["company_id"], name="CR13 Linked Raw Material",
        category_id=category.id, subcategory_id=subcategory.id,
        default_supplier=ids["supplier_name"], active=True,
    )
    session.add(material)
    session.commit()
    out = dict(ids)
    out["material_id"] = material.id
    session.close()
    return out


def test_supplier_rename_on_standalone_page_cascades_to_raw_material_link(seeded_supplier_with_linked_raw_material):
    """Acceptance criteria 6, 7: renames the supplier through the
    STANDALONE page's own 'Save changes' form (not the old nested tab,
    which no longer exists) and confirms the linked RawMaterial's
    default_supplier text snapshot is updated to match - proving the
    Raw Material <-> Supplier relationship this CR promised to preserve is
    genuinely still wired, not merely that the Supplier row itself survived
    the page move."""
    ids = seeded_supplier_with_linked_raw_material
    at = _run(PAGE_SUPPLIERS, session_state={"supplier_table": {"selection": {"rows": [0], "columns": []}}})
    assert at.session_state["supplier_selected_id"] == ids["supplier_id"]

    name_input = next(t for t in at.text_input if t.key == f"edit_supplier_name_{ids['supplier_id']}")
    name_input.set_value("CR13-Renamed-Supplier")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception renaming the supplier: {at.exception}"

    session = db.get_session()
    material = session.get(db.RawMaterial, ids["material_id"])
    assert material.default_supplier == "CR13-Renamed-Supplier", (
        "Renaming a supplier on the standalone page must still cascade onto every RawMaterial.default_supplier "
        "text value that matched the old name - the same cross-record consistency behavior the nested tab had"
    )
    session.close()


def test_raw_material_default_supplier_picker_still_resolves_after_split(seeded_supplier_with_linked_raw_material):
    """Acceptance criteria 4, 6, 7: opens views/14_Raw_Materials.py (not
    the Suppliers page) and confirms its 'Default supplier' dropdown on
    the Create tab still lists the supplier that now lives only on the
    standalone page - direct proof the picker _supplier_picker() kept on
    Raw Materials still reads the same db.Supplier rows by name, with zero
    data migration needed for the split itself."""
    ids = seeded_supplier_with_linked_raw_material
    at = _run(PAGE_RAWMAT)
    assert not at.exception, f"Unhandled exception opening Raw Materials: {at.exception}"

    supplier_select = next(s for s in at.selectbox if s.key == "add_rawmat_supplier_choice")
    assert ids["supplier_name"] in supplier_select.options, (
        "The Raw Materials page's own 'Default supplier' dropdown must still resolve to the Supplier record "
        "that now lives on the standalone Suppliers page"
    )


# ---------------------------------------------------------------------------
# Acceptance criteria 4, 8: CSV/Excel Supplier import validation and
# persistence (valid row + invalid/duplicate row rejection).
# ---------------------------------------------------------------------------

def test_supplier_csv_import_via_ui(seeded_company_only):
    """Drives the real st.file_uploader (key='supplier_upload') and the
    real 'Confirm import' button (key='confirm_supplier_import') on the
    standalone page and confirms the imported row is persisted."""
    ids = seeded_company_only
    at = _run(PAGE_SUPPLIERS)

    csv_bytes = "name,notes\nCR13-Imported-Supplier,from CSV\n".encode()
    uploader = next(u for u in at.file_uploader if u.key == "supplier_upload")
    uploader.set_value(("suppliers.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_supplier_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.Supplier)
        .filter(db.Supplier.company_id == ids["company_id"], db.Supplier.name == "CR13-Imported-Supplier")
        .first()
    )
    assert imported is not None, "Imported supplier was not persisted"
    session.close()


@pytest.fixture()
def seeded_company_with_existing_supplier():
    """One Company + one existing Supplier - the minimum needed to
    exercise the CSV/Excel import's own bad-row check: a row whose name
    matches an existing supplier's name, case-insensitively, is bucketed
    as a duplicate and never created."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR13 SupplierImportBad Co {u}", is_platform_owner=True)
    session.add(company)
    session.flush()
    supplier = db.Supplier(company_id=company.id, name=f"CR13 Existing Supplier {u}", active=True)
    session.add(supplier)
    session.commit()
    ids = {"company_id": company.id, "supplier_id": supplier.id, "supplier_name": supplier.name}
    session.close()
    return ids


def test_supplier_csv_import_validation_rejects_invalid_row(seeded_company_with_existing_supplier):
    """Acceptance criterion 8: uploads one row whose name exactly matches
    an already-seeded Supplier alongside one genuinely new row, and
    confirms the duplicate is flagged/skipped (never creating a second row
    with that name) while the new one imports - the same validation
    evidence CR-11 correction v2 supplied against the old nested tab,
    rebuilt here against the standalone page."""
    ids = seeded_company_with_existing_supplier
    at = _run(PAGE_SUPPLIERS)

    csv_bytes = (
        "name,notes\n"
        f"{ids['supplier_name']},duplicate of an existing supplier\n"
        "CR13-New-Supplier-Valid,from CSV\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "supplier_upload")
    uploader.set_value(("suppliers_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading a duplicate-name CSV: {at.exception}"

    warnings_text = " ".join(w.value for w in at.warning)
    assert "already in the list" in warnings_text.lower(), (
        "The real 'match a supplier name already in the list' duplicate warning should have fired"
    )

    confirm_btn = next(b for b in at.button if b.key == "confirm_supplier_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    matching_existing = (
        session.query(db.Supplier)
        .filter(db.Supplier.company_id == ids["company_id"], db.Supplier.name == ids["supplier_name"])
        .all()
    )
    new_valid = (
        session.query(db.Supplier)
        .filter(db.Supplier.company_id == ids["company_id"], db.Supplier.name == "CR13-New-Supplier-Valid")
        .first()
    )
    assert len(matching_existing) == 1, "The duplicate-named row must not have created a second supplier with that name"
    assert new_valid is not None, "The genuinely new row should have imported"
    session.close()


# ---------------------------------------------------------------------------
# Acceptance criterion 8: authorization and company scoping on the
# standalone Suppliers page.
# ---------------------------------------------------------------------------

@pytest.fixture()
def view_only_role_fixture(seeded_supplier):
    """A real company-scoped Role with an explicit RolePagePermission row
    denying *use* (can_view=True, can_use=False) on the NEW "suppliers"
    page_key - direct evidence the standalone page's own permission gate
    (independent of "raw_materials") actually blocks Delete."""
    ids = seeded_supplier
    session = db.get_session()
    role = db.Role(company_id=ids["company_id"], name="CR13 Supplier View Only", is_builtin=False)
    session.add(role)
    session.flush()
    session.add(db.RolePagePermission(role_id=role.id, page_key="suppliers", can_view=True, can_use=False))
    session.commit()
    out = dict(ids)
    out["role_id"] = role.id
    session.close()
    return out


def test_supplier_view_only_role_cannot_delete_via_ui(view_only_role_fixture):
    """Presets role_id/is_super_admin/is_platform_owner/company_id in
    session_state (overriding the AUTH_DISABLED dev-bypass's own
    setdefault() defaults, the established technique from
    tests/test_cr10_product_family_grade_split.py's _run_as_role) alongside
    the supplier_table dataframe widget's own on_select state. Confirms the
    row is genuinely selected, then confirms neither the delete
    confirm-checkbox nor the delete button render for this
    page_usable=False role against the NEW "suppliers" page_key, and that
    the seeded supplier is still in the database afterward."""
    ids = view_only_role_fixture
    session = db.get_session()
    assert not access_control.can_use_page("suppliers", role_id=ids["role_id"], session=session, is_super_admin=False)
    session.close()

    at = _run(
        PAGE_SUPPLIERS,
        session_state={
            "role_id": ids["role_id"],
            "is_super_admin": False,
            "is_platform_owner": False,
            "company_id": ids["company_id"],
            "supplier_table": {"selection": {"rows": [0], "columns": []}},
        },
    )
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["supplier_selected_id"] == ids["supplier_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded supplier"
    )

    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()
    assert not any(c.key == f"supplier_{ids['supplier_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the delete confirm checkbox"
    )
    assert not any(b.key == f"supplier_{ids['supplier_id']}_btn" for b in at.button), (
        "View-only role should not see the delete button"
    )

    session = db.get_session()
    assert session.get(db.Supplier, ids["supplier_id"]) is not None, (
        "The seeded supplier must still exist - a view-only role must never be able to delete it"
    )
    session.close()


@pytest.fixture()
def two_companies_with_suppliers():
    """Two separate Companies, each with its own Supplier - the minimum
    needed to prove the standalone page's own company scoping (via
    tenant_scope.company_picker, the same helper Raw Materials uses)
    excludes the other company's Supplier record for a non-platform-owner
    viewer, and that the platform owner's 'All companies' view can still
    see both."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company_a = db.Company(name=f"CR13 Co A {u}", is_platform_owner=False)
    company_b = db.Company(name=f"CR13 Co B {u}", is_platform_owner=False)
    session.add_all([company_a, company_b])
    session.flush()
    supplier_a = db.Supplier(company_id=company_a.id, name=f"CR13 Supplier A {u}", active=True)
    supplier_b = db.Supplier(company_id=company_b.id, name=f"CR13 Supplier B {u}", active=True)
    session.add_all([supplier_a, supplier_b])
    session.commit()
    ids = {
        "company_a_id": company_a.id, "company_b_id": company_b.id,
        "supplier_a_name": supplier_a.name, "supplier_b_name": supplier_b.name,
    }
    session.close()
    return ids


def test_suppliers_page_excludes_other_company_supplier_for_non_platform_owner(two_companies_with_suppliers):
    """Acceptance criterion 8 (company scoping): runs as a non-platform-
    owner user of Company A and confirms Company B's Supplier never
    appears in the Edit/Delete tab's own rendered table - direct proof of
    tenant isolation on the new standalone page, independent of whatever
    isolation Raw Materials already had.

    helpers.clickable_table() renders through a real st.dataframe widget
    (not markdown/HTML), so the rendered rows are read from at.dataframe's
    own .value (a pandas DataFrame), not at.markdown."""
    ids = two_companies_with_suppliers
    at = _run(
        PAGE_SUPPLIERS,
        session_state={
            "is_platform_owner": False,
            "is_super_admin": False,
            "company_id": ids["company_a_id"],
        },
    )
    assert not at.exception, f"Unhandled exception for a non-platform-owner user: {at.exception}"

    supplier_table = next(d for d in at.dataframe if d.key == "supplier_table")
    names = set(supplier_table.value["Name"])
    assert ids["supplier_a_name"] in names, "Company A's own supplier should be visible to a Company A user"
    assert ids["supplier_b_name"] not in names, (
        "Company B's supplier must never be visible to a Company A user - cross-tenant scope leak"
    )
