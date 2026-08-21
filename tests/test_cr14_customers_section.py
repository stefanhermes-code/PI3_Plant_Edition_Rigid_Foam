"""CR-14 (Create Customers Section and Lightweight Customer Master,
2026-08-12) - direct executed evidence for every CR-14 acceptance
criterion and regression-test requirement (sections 8/9 of
CR14_Create_Customers_Section_and_Customer_Master.docx).

Before this CR, "customer identity" existed only as a free-text
customer_name column on CustomerTrial - no master record, no permission
gate of its own, no validation beyond "not blank". This CR added a
lightweight db.Customer master (company_id, company_name, contact_person,
contact_email, customer_type) with its own "customers" page_key and its
own standalone page (views/33_Customers.py), moved into a brand-new
"Customers" sidebar section together with Customer Trials & Samples
(which moved out of "Samples & Trials"), and rewired
views/11_Customer_Trials.py's Create/Edit/Import flows to select a
Customer from that master via the new CustomerTrial.customer_id FK -
customer_name is kept as a synced display-only text snapshot (see both
pages' own module docstrings) so every existing reader of customer_name
elsewhere keeps working unchanged.

NOTE (CR-17, 2026-08-13): the "Customer Trials & Samples moved into
Customers" part of the placement above was later reversed by CR-17
(Restore Customer Trials & Samples to Samples & Trials Navigation) -
Stefan clarified the trial page belongs with the application's
trial/sample workflows, not the Customers master section. Customers now
holds only the Customers master page; Customer Trials & Samples is back
in Samples & Trials. test_customers_section_registered_in_nav_with_
correct_order below was updated in place to assert the corrected
(current) layout. Every other CR-14 behavior described above and tested
in this file - the Customer master itself, its permission gate, and the
CustomerTrial.customer_id relationship/CSV import linkage - is unaffected
by CR-17 and still fully covered by the rest of this file.

Reuses the same established, already-verified patterns from
tests/test_cr13_suppliers_standalone_page.py and
tests/test_cr10_pu_material_family_grade_split.py:
  - os.environ.setdefault("DATABASE_URL", "sqlite://") + sys.path boilerplate.
  - db.init_db() + db.Base.metadata.drop_all/create_all per fixture, with
    _clear_relevant_caches() called from every _reset_schema().
  - SQLAlchemy ORM seeding with a uuid.uuid4().hex[:8] suffix on names for
    uniqueness.
  - Presetting a dataframe/table widget's OWN on_select state (e.g.
    at.session_state["customer_table"] = {"selection": {"rows": [0],
    "columns": []}}) BEFORE .run() to genuinely drive clickable_table's
    row-click selection.
  - Presetting role_id/is_super_admin/is_platform_owner/company_id in
    session_state BEFORE .run() to override the AUTH_DISABLED dev-bypass's
    setdefault()-based is_super_admin=True default, so a real restricted
    role can be tested.
  - at.secrets["AUTH_DISABLED"] = True for every AppTest run.
  - Selectbox.options returns FORMATTED display strings (post
    format_func), not the raw underlying objects - select by index
    (.select_index(i)) rather than matching .options against a raw object.

Usage: python -m pytest tests/test_cr14_customers_section.py -v
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
from helpers import cr11_function_tab_labels, is_valid_email

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_CUSTOMERS = os.path.join(APP_DIR, "views", "33_Customers.py")
PAGE_CUSTOMER_TRIALS = os.path.join(APP_DIR, "views", "11_Customer_Trials.py")


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
# Acceptance criteria 1, 2, 3, 8: dedicated Customers section, in order,
# with Customer Trials & Samples positioned under it (section 2 of the CR).
# ---------------------------------------------------------------------------

def test_customers_page_key_registered_in_page_catalog():
    """Acceptance criterion 1 (part): a dedicated "customers" page_key
    exists in access_control.PAGE_CATALOG, independent of "customer_trials"
    - direct proof this is a real, separately-permissioned page, not a
    label reused from an existing key."""
    assert "customers" in access_control.PAGE_CATALOG
    assert access_control.PAGE_CATALOG["customers"] == "Customers"
    assert "customer_trials" in access_control.PAGE_CATALOG
    assert access_control.PAGE_CATALOG["customer_trials"] == "Customer Trials & Samples"


def test_customers_section_registered_in_nav_with_correct_order():
    """Acceptance criteria 1, 2, 8, as corrected by CR-17 (Restore Customer
    Trials & Samples to Samples & Trials Navigation, 2026-08-13): CR-14
    originally placed Customer Trials & Samples inside customer_pages,
    after Customers. This test's assertions were updated for CR-17, which
    reversed that specific placement per Stefan's direction - Customers now
    contains only the Customers master page, and Customer Trials & Samples
    is back in experiment_views/"Samples & Trials" (between Production
    Samples and Optimization Trials & Samples). CR-14's own dedicated
    "Customers" nav section, its "customers" page_key, and the
    CustomerTrial->Customer relationship are otherwise untouched - see
    tests/test_cr17_nav_restore.py for CR-17's own full nav-placement
    evidence; this test keeps CR-14's own acceptance-criteria numbering
    but now asserts the corrected (current) layout, not history.

    app_rigid_foam.py is a Streamlit script (calls st.navigation()/
    st.sidebar at import time) - importing it directly outside AppTest
    isn't safe (see tests/test_cr10_pu_material_family_grade_split.py's own
    reasoning), so this greps the module source for the page-list literals
    instead of executing the file."""
    with open(os.path.join(APP_DIR, "app_rigid_foam.py"), encoding="utf-8") as f:
        source = f.read()

    start = source.index("customer_pages = [")
    end = source.index("]", start)
    block = source[start:end]
    assert '"customers"' in block
    assert 'st.Page("views/33_Customers.py"' in block
    assert '"customer_trials"' not in block, (
        "CR-17: Customer Trials & Samples must no longer live in customer_pages"
    )

    # CR-17: Customer Trials & Samples is back in experiment_pages, between
    # Production Samples and Optimization Trials & Samples.
    exp_start = source.index("experiment_pages = [")
    exp_end = source.index("]", exp_start)
    exp_block = source[exp_start:exp_end]
    assert '"samples_conditioning"' in exp_block
    assert '"customer_trials"' in exp_block
    assert '"optimization_trials"' in exp_block
    assert 'st.Page("views/11_Customer_Trials.py"' in exp_block
    samples_pos = exp_block.index('"samples_conditioning"')
    customer_trials_pos = exp_block.index('"customer_trials"')
    optimization_pos = exp_block.index('"optimization_trials"')
    assert samples_pos < customer_trials_pos < optimization_pos, (
        "Samples & Trials must list Production Samples, then Customer "
        "Trials & Samples, then Optimization Trials & Samples, in that order"
    )

    # The "Customers" nav section itself must be registered and use
    # customer_pages as its page list; "Samples & Trials" must use
    # experiment_pages.
    nav_start = source.index("nav_sections_with_keys")
    nav_block = source[nav_start:nav_start + 800]
    assert '"Customers": customer_pages' in nav_block
    assert '"Samples & Trials": experiment_pages' in nav_block


# ---------------------------------------------------------------------------
# Acceptance criteria 3, 4, 5: Customers page opens directly, exposes the
# right fields and the CR-11 standard function triplet in order.
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_company_only():
    """One Company only - the minimum for the Customers page's Create tab
    Company selectbox to have exactly one option, with nothing to click."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR14 Customer Co {u}", is_platform_owner=True)
    session.add(company)
    session.commit()
    ids = {"company_id": company.id, "company_name": company.name}
    session.close()
    return ids


def test_customers_page_opens_directly_and_shows_cr11_triplet(seeded_company_only):
    """Acceptance criteria 3, 5: the standalone Customers page opens
    directly (AppTest.from_file against views/33_Customers.py) and exposes
    exactly the three CR-11-standard tabs - 'Create Customer',
    'Edit/Delete Customer', 'CSV/Excel import Customers' - in that order
    and wording."""
    at = _run(PAGE_CUSTOMERS)
    assert not at.exception, f"Unhandled exception opening the Customers page: {at.exception}"

    labels = [t.label for t in at.tabs]
    expected = list(cr11_function_tab_labels("Customer"))
    assert labels == expected, f"Expected exactly {expected} in order, got {labels}"


def test_customers_page_create_form_has_required_fields(seeded_company_only):
    """Acceptance criterion 4: the Create Customer tab exposes Company
    Name, Contact Person, Contact Email, and Customer Type inputs."""
    at = _run(PAGE_CUSTOMERS)
    labels = {t.label for t in at.text_input}
    assert "Company Name *" in labels
    assert "Contact Person" in labels
    assert "Contact Email" in labels
    assert "Customer Type" in labels


# ---------------------------------------------------------------------------
# Acceptance criteria 4, 5, 6: Customer create/edit/delete persistence.
# ---------------------------------------------------------------------------

def test_customer_create_via_form(seeded_company_only):
    """Direct evidence the Create tab's real form persists a new Customer
    row, company-scoped."""
    ids = seeded_company_only
    at = _run(PAGE_CUSTOMERS)

    name_input = next(t for t in at.text_input if t.label == "Company Name *")
    name_input.set_value("CR14-New-Customer")
    contact_input = next(t for t in at.text_input if t.label == "Contact Person")
    contact_input.set_value("Jane Doe")
    email_input = next(t for t in at.text_input if t.label == "Contact Email")
    email_input.set_value("jane@example.com")
    save_btn = next(b for b in at.button if b.label == "Add customer")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new customer: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.Customer)
        .filter(db.Customer.company_id == ids["company_id"], db.Customer.company_name == "CR14-New-Customer")
        .first()
    )
    assert created is not None, "New customer was not persisted"
    assert created.contact_person == "Jane Doe"
    assert created.contact_email == "jane@example.com"
    session.close()


def test_customer_create_rejects_invalid_email(seeded_company_only):
    """Acceptance criterion 7: the Create tab's own is_valid_email() check
    blocks a malformed Contact Email and does not persist the row."""
    at = _run(PAGE_CUSTOMERS)

    name_input = next(t for t in at.text_input if t.label == "Company Name *")
    name_input.set_value("CR14-Bad-Email-Customer")
    email_input = next(t for t in at.text_input if t.label == "Contact Email")
    email_input.set_value("not-an-email")
    save_btn = next(b for b in at.button if b.label == "Add customer")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception on invalid-email submit: {at.exception}"

    errors_text = " ".join(e.value for e in at.error)
    assert "valid email" in errors_text.lower()

    session = db.get_session()
    created = session.query(db.Customer).filter(db.Customer.company_name == "CR14-Bad-Email-Customer").first()
    assert created is None, "A customer with an invalid Contact Email must not be persisted"
    session.close()


@pytest.fixture()
def seeded_customer():
    """One Company + one existing Customer - the minimum to exercise
    selection/edit/delete on the Customers page's Edit/Delete tab."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR14 CustomerEdit Co {u}", is_platform_owner=True)
    session.add(company)
    session.flush()
    customer = db.Customer(company_id=company.id, company_name=f"CR14 Customer {u}")
    session.add(customer)
    session.commit()
    ids = {"company_id": company.id, "customer_id": customer.id, "customer_name": customer.company_name}
    session.close()
    return ids


def test_customer_selection_edit_and_delete_via_ui(seeded_customer):
    """Acceptance criteria 5, 6: presets the customer_table dataframe
    widget's OWN on_select state to select row 0, edits the selected
    customer's name/contact fields through the real 'Save changes' form
    and confirms persistence, then deletes it through the real confirm-
    checkbox + delete-button flow and confirms it's gone."""
    ids = seeded_customer
    at = _run(PAGE_CUSTOMERS, session_state={"customer_table": {"selection": {"rows": [0], "columns": []}}})
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["customer_selected_id"] == ids["customer_id"]

    # --- Edit ---
    name_input = next(t for t in at.text_input if t.key == f"edit_customer_name_{ids['customer_id']}")
    name_input.set_value("CR14-Edited-Customer")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the customer: {at.exception}"

    session = db.get_session()
    edited = session.get(db.Customer, ids["customer_id"])
    assert edited.company_name == "CR14-Edited-Customer", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["customer_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"customer_{ids['customer_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"customer_{ids['customer_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the customer: {at.exception}"

    session = db.get_session()
    assert session.get(db.Customer, ids["customer_id"]) is None, "Delete did not remove the customer"
    session.close()


def test_customer_edit_rejects_invalid_email(seeded_customer):
    """Acceptance criterion 7: editing an existing customer with a
    malformed Contact Email is blocked and the prior value is unchanged."""
    ids = seeded_customer
    at = _run(PAGE_CUSTOMERS, session_state={"customer_table": {"selection": {"rows": [0], "columns": []}}})

    email_input = next(t for t in at.text_input if t.key == f"edit_customer_email_{ids['customer_id']}")
    email_input.set_value("still-not-an-email")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception on invalid-email edit submit: {at.exception}"

    errors_text = " ".join(e.value for e in at.error)
    assert "valid email" in errors_text.lower()

    session = db.get_session()
    unchanged = session.get(db.Customer, ids["customer_id"])
    assert unchanged.contact_email in (None, ""), "An invalid Contact Email edit must not be persisted"
    session.close()


@pytest.fixture()
def seeded_customer_with_linked_trial(seeded_customer):
    """Extends seeded_customer with a Plant/PUMaterialFamily/FoamGrade and a
    CustomerTrial linked to it via customer_id - the minimum needed to
    prove renaming a customer cascades onto CustomerTrial.customer_name
    (the display-snapshot sync), and that deleting the customer nullifies
    customer_id on the linked trial rather than leaving a dangling FK or
    deleting the trial itself."""
    ids = seeded_customer
    session = db.get_session()
    plant = db.Plant(company_id=ids["company_id"], name="CR14 Plant")
    session.add(plant)
    session.flush()
    fam = db.PUMaterialFamily(plant_id=plant.id, name="CR14 Family")
    session.add(fam)
    session.flush()
    grade = db.FoamGrade(pu_material_family_id=fam.id, grade_name="CR14 Grade")
    session.add(grade)
    session.flush()
    trial = db.CustomerTrial(
        plant_id=plant.id, foam_grade_id=grade.id,
        customer_id=ids["customer_id"], customer_name=ids["customer_name"], status="Open",
    )
    session.add(trial)
    session.commit()
    out = dict(ids)
    out["trial_id"] = trial.id
    session.close()
    return out


def test_customer_rename_cascades_to_linked_trial_customer_name(seeded_customer_with_linked_trial):
    """Acceptance criteria 9, 10, 11: renaming a customer through the
    Customers page's own 'Save changes' form updates the linked
    CustomerTrial's customer_name display snapshot to match, and the trial
    record itself remains fully intact (still exists, still linked)."""
    ids = seeded_customer_with_linked_trial
    at = _run(PAGE_CUSTOMERS, session_state={"customer_table": {"selection": {"rows": [0], "columns": []}}})

    name_input = next(t for t in at.text_input if t.key == f"edit_customer_name_{ids['customer_id']}")
    name_input.set_value("CR14-Renamed-Customer")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception renaming the customer: {at.exception}"

    session = db.get_session()
    trial = session.get(db.CustomerTrial, ids["trial_id"])
    assert trial is not None, "The linked customer trial must remain intact after a customer rename"
    assert trial.customer_id == ids["customer_id"]
    assert trial.customer_name == "CR14-Renamed-Customer", (
        "Renaming a customer must cascade onto every linked CustomerTrial.customer_name text snapshot"
    )
    session.close()


def test_customer_delete_nullifies_linked_trial_customer_id_but_preserves_trial(seeded_customer_with_linked_trial):
    """Acceptance criteria 10, 11: deleting a Customer that has a linked
    CustomerTrial must null out that trial's customer_id (never violate
    the FK, never cascade-delete the trial) - the trial and its
    customer_name text snapshot survive untouched."""
    ids = seeded_customer_with_linked_trial
    at = _run(PAGE_CUSTOMERS, session_state={"customer_table": {"selection": {"rows": [0], "columns": []}}})
    assert at.session_state["customer_selected_id"] == ids["customer_id"]

    confirm_box = next(c for c in at.checkbox if c.key == f"customer_{ids['customer_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"customer_{ids['customer_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting a linked customer: {at.exception}"

    session = db.get_session()
    assert session.get(db.Customer, ids["customer_id"]) is None
    trial = session.get(db.CustomerTrial, ids["trial_id"])
    assert trial is not None, "The customer trial must survive the customer's deletion"
    assert trial.customer_id is None, "customer_id must be nulled out, not left dangling"
    assert trial.customer_name == ids["customer_name"], "customer_name text snapshot must be preserved"
    session.close()


# ---------------------------------------------------------------------------
# Acceptance criteria 5, 7: CSV/Excel Customer import - validation
# (duplicate name, invalid email) and persistence.
# ---------------------------------------------------------------------------

def test_customer_csv_import_via_ui(seeded_company_only):
    """Drives the real st.file_uploader (key='customer_upload') and the
    real 'Confirm import' button (key='confirm_customer_import') and
    confirms the imported row is persisted."""
    ids = seeded_company_only
    at = _run(PAGE_CUSTOMERS)

    csv_bytes = (
        "company_name,contact_person,contact_email,customer_type\n"
        "CR14-Imported-Customer,John Smith,john@example.com,OEM\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "customer_upload")
    uploader.set_value(("customers.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_customer_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.Customer)
        .filter(db.Customer.company_id == ids["company_id"], db.Customer.company_name == "CR14-Imported-Customer")
        .first()
    )
    assert imported is not None, "Imported customer was not persisted"
    assert imported.contact_email == "john@example.com"
    session.close()


def test_customer_csv_import_validation_rejects_duplicate_and_bad_email(seeded_customer):
    """Acceptance criterion 7 + regression requirement (dedup +
    validation): uploads one row duplicating an existing customer's name,
    one row with an invalid email, and one genuinely valid new row -
    confirms only the valid row imports."""
    ids = seeded_customer
    at = _run(PAGE_CUSTOMERS)

    csv_bytes = (
        "company_name,contact_email\n"
        f"{ids['customer_name']},dup@example.com\n"
        "CR14-Bad-Email-Row,not-an-email\n"
        "CR14-Valid-Import-Row,valid@example.com\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "customer_upload")
    uploader.set_value(("customers_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading a mixed-validity CSV: {at.exception}"

    warnings_text = " ".join(w.value for w in at.warning)
    assert "already in the list" in warnings_text.lower()
    assert "valid email" in warnings_text.lower()

    confirm_btn = next(b for b in at.button if b.key == "confirm_customer_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    matching_existing = (
        session.query(db.Customer)
        .filter(db.Customer.company_id == ids["company_id"], db.Customer.company_name == ids["customer_name"])
        .all()
    )
    bad_email_row = session.query(db.Customer).filter(db.Customer.company_name == "CR14-Bad-Email-Row").first()
    valid_row = session.query(db.Customer).filter(db.Customer.company_name == "CR14-Valid-Import-Row").first()
    assert len(matching_existing) == 1, "The duplicate-named row must not create a second customer"
    assert bad_email_row is None, "The invalid-email row must not be imported"
    assert valid_row is not None, "The genuinely valid new row should have imported"
    session.close()


# ---------------------------------------------------------------------------
# Acceptance criteria 6, 8: company scoping and page permissions on the
# Customers page.
# ---------------------------------------------------------------------------

@pytest.fixture()
def two_companies_with_customers():
    """Two separate Companies, each with its own Customer - the minimum
    needed to prove the Customers page's own company scoping (via
    tenant_scope.company_picker) excludes the other company's Customer
    record for a non-platform-owner viewer."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company_a = db.Company(name=f"CR14 Co A {u}", is_platform_owner=False)
    company_b = db.Company(name=f"CR14 Co B {u}", is_platform_owner=False)
    session.add_all([company_a, company_b])
    session.flush()
    customer_a = db.Customer(company_id=company_a.id, company_name=f"CR14 Customer A {u}")
    customer_b = db.Customer(company_id=company_b.id, company_name=f"CR14 Customer B {u}")
    session.add_all([customer_a, customer_b])
    session.commit()
    ids = {
        "company_a_id": company_a.id, "company_b_id": company_b.id,
        "customer_a_name": customer_a.company_name, "customer_b_name": customer_b.company_name,
    }
    session.close()
    return ids


def test_customers_page_excludes_other_company_customer_for_non_platform_owner(two_companies_with_customers):
    """Acceptance criterion 6 (company scoping): runs as a non-platform-
    owner user of Company A and confirms Company B's Customer never
    appears in the Edit/Delete tab's own rendered table."""
    ids = two_companies_with_customers
    at = _run(
        PAGE_CUSTOMERS,
        session_state={
            "is_platform_owner": False,
            "is_super_admin": False,
            "company_id": ids["company_a_id"],
        },
    )
    assert not at.exception, f"Unhandled exception for a non-platform-owner user: {at.exception}"

    customer_table = next(d for d in at.dataframe if d.key == "customer_table")
    names = set(customer_table.value["Company Name"])
    assert ids["customer_a_name"] in names, "Company A's own customer should be visible to a Company A user"
    assert ids["customer_b_name"] not in names, (
        "Company B's customer must never be visible to a Company A user - cross-tenant scope leak"
    )


@pytest.fixture()
def view_only_role_fixture(seeded_customer):
    """A real company-scoped Role with an explicit RolePagePermission row
    denying *use* (can_view=True, can_use=False) on the "customers"
    page_key - direct evidence the Customers page's own permission gate
    actually blocks Delete."""
    ids = seeded_customer
    session = db.get_session()
    role = db.Role(company_id=ids["company_id"], name="CR14 Customer View Only", is_builtin=False)
    session.add(role)
    session.flush()
    session.add(db.RolePagePermission(role_id=role.id, page_key="customers", can_view=True, can_use=False))
    session.commit()
    out = dict(ids)
    out["role_id"] = role.id
    session.close()
    return out


def test_customer_view_only_role_cannot_delete_via_ui(view_only_role_fixture):
    """Acceptance criterion 11 (existing permissions/safeguards remain
    effective): presets role_id/is_super_admin/is_platform_owner/
    company_id in session_state alongside the customer_table dataframe
    widget's own on_select state. Confirms the row is genuinely selected,
    then confirms neither the delete confirm-checkbox nor the delete
    button render for this page_usable=False role, and that the seeded
    customer is still in the database afterward."""
    ids = view_only_role_fixture
    session = db.get_session()
    assert not access_control.can_use_page("customers", role_id=ids["role_id"], session=session, is_super_admin=False)
    session.close()

    at = _run(
        PAGE_CUSTOMERS,
        session_state={
            "role_id": ids["role_id"],
            "is_super_admin": False,
            "is_platform_owner": False,
            "company_id": ids["company_id"],
            "customer_table": {"selection": {"rows": [0], "columns": []}},
        },
    )
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["customer_selected_id"] == ids["customer_id"]

    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()
    assert not any(c.key == f"customer_{ids['customer_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the delete confirm checkbox"
    )
    assert not any(b.key == f"customer_{ids['customer_id']}_btn" for b in at.button), (
        "View-only role should not see the delete button"
    )

    session = db.get_session()
    assert session.get(db.Customer, ids["customer_id"]) is not None, (
        "The seeded customer must still exist - a view-only role must never be able to delete it"
    )
    session.close()


# ---------------------------------------------------------------------------
# Acceptance criteria 8, 9, 10: Customer Trials & Samples page - direct
# opening under the new section, customer selection sourced from the
# master, and preservation of existing trial/sample records.
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_grade_and_customer():
    """One Company + Plant + PUMaterialFamily + FoamGrade + Customer - the
    minimum to exercise the Create Trial tab's new Customer selectbox on
    views/11_Customer_Trials.py."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR14 CT Co {u}", is_platform_owner=True)
    session.add(company)
    session.flush()
    plant = db.Plant(company_id=company.id, name="CR14 CT Plant")
    session.add(plant)
    session.flush()
    fam = db.PUMaterialFamily(plant_id=plant.id, name="CR14 CT Family")
    session.add(fam)
    session.flush()
    grade = db.FoamGrade(pu_material_family_id=fam.id, grade_name="CR14 CT Grade")
    session.add(grade)
    session.flush()
    customer = db.Customer(company_id=company.id, company_name=f"CR14 CT Customer {u}")
    session.add(customer)
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id, "grade_id": grade.id,
        "customer_id": customer.id, "customer_name": customer.company_name,
    }
    session.close()
    return ids


def test_customer_trials_page_opens_directly_under_new_section(seeded_grade_and_customer):
    """Acceptance criterion 8: views/11_Customer_Trials.py opens directly
    and without error, independent of any change to its own section
    placement (nav-section membership is proven separately by
    test_customers_section_registered_in_nav_with_correct_order)."""
    at = _run(PAGE_CUSTOMER_TRIALS)
    assert not at.exception, f"Unhandled exception opening Customer Trials & Samples: {at.exception}"


def test_customer_trial_create_uses_customer_master_selectbox(seeded_grade_and_customer):
    """Acceptance criterion 9: the Create Trial tab's Customer field is a
    real selectbox (key='ct_add_customer') sourced from the Customer
    master, not a free-text input, and creating a trial through it
    persists both customer_id (the live FK) and customer_name (the synced
    display snapshot)."""
    ids = seeded_grade_and_customer
    at = _run(PAGE_CUSTOMER_TRIALS)
    assert not at.exception

    assert not any(t.label == "Customer name" for t in at.text_input), (
        "The old free-text 'Customer name' input must be gone - customer selection is now via the master"
    )
    customer_select = next(s for s in at.selectbox if s.key == "ct_add_customer")
    assert ids["customer_name"] in customer_select.options

    customer_select.select_index(0)
    save_btn = next(b for b in at.button if b.label == "Save customer trial")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new customer trial: {at.exception}"

    session = db.get_session()
    created = session.query(db.CustomerTrial).filter(db.CustomerTrial.plant_id == ids["plant_id"]).first()
    assert created is not None, "New customer trial was not persisted"
    assert created.customer_id == ids["customer_id"]
    assert created.customer_name == ids["customer_name"]
    session.close()


def test_customer_trial_create_warns_when_no_customers_exist():
    """Acceptance criterion 9 (graceful no-data handling): with a grade
    but zero Customer master rows, the Create Trial tab shows a warning
    directing the user to add a customer first, instead of crashing or
    silently allowing a trial with no customer."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR14 CT NoCust Co {u}", is_platform_owner=True)
    session.add(company)
    session.flush()
    plant = db.Plant(company_id=company.id, name="CR14 CT NoCust Plant")
    session.add(plant)
    session.flush()
    fam = db.PUMaterialFamily(plant_id=plant.id, name="CR14 CT NoCust Family")
    session.add(fam)
    session.flush()
    grade = db.FoamGrade(pu_material_family_id=fam.id, grade_name="CR14 CT NoCust Grade")
    session.add(grade)
    session.commit()
    session.close()

    at = _run(PAGE_CUSTOMER_TRIALS)
    assert not at.exception
    warnings_text = " ".join(w.value for w in at.warning)
    assert "add a customer" in warnings_text.lower()


@pytest.fixture()
def seeded_legacy_trial(seeded_grade_and_customer):
    """Extends seeded_grade_and_customer with two pre-CR-14-style
    CustomerTrial rows: one whose customer_name exactly matches the
    seeded Customer (the auto-suggest exact-match case), and one whose
    customer_name matches nothing in the master (the no-match case) -
    both with customer_id left NULL, exactly as a legacy row would be
    before cascades.backfill_trial_customers() runs.

    The page's Edit/Delete tab orders trials by CustomerTrial.created_at
    DESCENDING, so explicit, clearly-ordered timestamps are set here
    (rather than relying on default=utcnow() insertion-order timing,
    which is not reliably distinguishable at this precision) to make row
    index 0 deterministically the unmatched trial and row index 1
    deterministically the exact-match trial."""
    import datetime as _dt

    ids = seeded_grade_and_customer
    session = db.get_session()
    exact_trial = db.CustomerTrial(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
        customer_name=ids["customer_name"], status="Open",
        created_at=_dt.datetime(2026, 1, 1, 8, 0, 0),
    )
    session.add(exact_trial)
    unmatched_trial = db.CustomerTrial(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
        customer_name="CR14 Totally Unmatched Historical Name", status="Open",
        created_at=_dt.datetime(2026, 1, 2, 8, 0, 0),
    )
    session.add(unmatched_trial)
    session.commit()
    out = dict(ids)
    out["exact_trial_id"] = exact_trial.id
    out["unmatched_trial_id"] = unmatched_trial.id
    session.close()
    return out


def test_customer_trial_edit_auto_suggests_exact_match(seeded_legacy_trial):
    """Acceptance criteria 9, 10: editing a legacy trial (customer_id is
    NULL) whose customer_name exactly matches an existing Customer
    auto-preselects that Customer in the edit selectbox, with no
    'no exact match' caption, and the trial itself is unmodified until
    saved (preservation of existing data, criterion 10).

    trials is ordered by CustomerTrial.created_at DESCENDING, and the
    seeded_legacy_trial fixture gives the exact-match trial the EARLIER
    explicit created_at - so it is deterministically row index 1."""
    ids = seeded_legacy_trial
    at = _run(
        PAGE_CUSTOMER_TRIALS,
        session_state={"customer_trials_table": {"selection": {"rows": [1], "columns": []}}},
    )
    assert not at.exception
    selected_id = at.session_state["ct_selected_id"]
    assert selected_id == ids["exact_trial_id"], "Row index 1 must be the earlier-created exact-match trial"

    edit_sel = next(s for s in at.selectbox if s.key == f"ct_edit_customer_{selected_id}")
    captions_text = " ".join(c.value for c in at.caption)

    assert ids["customer_name"] in edit_sel.options
    # Selectbox.value returns the raw underlying object (a db.Customer),
    # not the formatted display string used in .options.
    assert edit_sel.value is not None and edit_sel.value.company_name == ids["customer_name"], (
        "An exact historical name match should auto-preselect that customer, not the unselected placeholder"
    )
    assert "no exact match" not in captions_text.lower()


def test_customer_trial_edit_shows_no_match_caption_for_unmatched_legacy_name(seeded_legacy_trial):
    """Acceptance criteria 9, 10: editing a legacy trial whose
    customer_name matches nothing in the Customer master defaults the
    selectbox to the unselected placeholder and shows the explanatory
    'No exact match found' caption, rather than guessing or auto-linking
    to the wrong customer.

    The seeded_legacy_trial fixture gives the unmatched trial the LATER
    explicit created_at, so it is deterministically row index 0 under the
    page's created_at-descending order."""
    ids = seeded_legacy_trial
    at = _run(
        PAGE_CUSTOMER_TRIALS,
        session_state={"customer_trials_table": {"selection": {"rows": [0], "columns": []}}},
    )
    assert not at.exception
    selected_id = at.session_state["ct_selected_id"]
    assert selected_id == ids["unmatched_trial_id"], "Row index 0 must be the later-created unmatched trial"

    edit_sel = next(s for s in at.selectbox if s.key == f"ct_edit_customer_{selected_id}")
    captions_text = " ".join(c.value for c in at.caption)

    # Selectbox.value returns the raw underlying object - the unselected
    # placeholder option is the literal None in customer_options.
    assert edit_sel.value is None
    assert "no exact match" in captions_text.lower()
    assert "CR14 Totally Unmatched Historical Name" in captions_text


def test_customer_trial_edit_requires_customer_selection(seeded_legacy_trial):
    """Acceptance criterion 9: saving the edit form with the customer
    selectbox left at the unselected placeholder is rejected with an
    error, rather than silently saving a trial with no customer link.

    Row index 0 is the unmatched trial (see seeded_legacy_trial's
    created_at ordering note) - its selectbox defaults to the unselected
    placeholder since no exact historical-name match exists, which is
    exactly the "nothing picked" state this test needs."""
    ids = seeded_legacy_trial
    at = _run(
        PAGE_CUSTOMER_TRIALS,
        session_state={"customer_trials_table": {"selection": {"rows": [0], "columns": []}}},
    )
    selected_id = at.session_state["ct_selected_id"]
    assert selected_id == ids["unmatched_trial_id"]
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving with no customer selected: {at.exception}"
    errors_text = " ".join(e.value for e in at.error)
    assert "pick a customer" in errors_text.lower()

    session = db.get_session()
    unchanged = session.get(db.CustomerTrial, selected_id)
    assert unchanged.customer_id is None, "customer_id must remain NULL since no customer was picked"
    session.close()


def test_customer_trial_csv_import_auto_links_exact_match_customer_name(seeded_grade_and_customer):
    """Acceptance criteria 9, 10. Charlie's CR-14 closeout review
    (2026-08-13) flagged that a CSV row with no exact Customer match
    originally imported with customer_id left NULL - a customer-
    identification path outside the Customer master. Corrected so import
    now uses the same exact-match-or-create rule as
    cascades.backfill_trial_customers(): an exact customer_name match
    auto-links customer_id to the existing Customer, and a non-matching
    name auto-creates a new Customer master record and links to that
    instead - every imported row ends up linked to a valid Customer,
    never with customer_id empty."""
    ids = seeded_grade_and_customer
    at = _run(PAGE_CUSTOMER_TRIALS)

    csv_bytes = (
        "foam_grade_id,customer_name\n"
        f"{ids['grade_id']},{ids['customer_name']}\n"
        f"{ids['grade_id']},CR14 Import Unmatched Customer Name\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "ct_trial_upload")
    uploader.set_value(("trials.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_ct_trial_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    matched = (
        session.query(db.CustomerTrial)
        .filter(db.CustomerTrial.customer_name == ids["customer_name"])
        .first()
    )
    unmatched = (
        session.query(db.CustomerTrial)
        .filter(db.CustomerTrial.customer_name == "CR14 Import Unmatched Customer Name")
        .first()
    )
    assert matched is not None and matched.customer_id == ids["customer_id"], (
        "An exact customer_name match on import must auto-link customer_id to the existing Customer"
    )
    assert unmatched is not None and unmatched.customer_id is not None, (
        "An unmatched customer_name must never import with customer_id left NULL - it must "
        "auto-create a new Customer and link to it"
    )
    new_customer = session.get(db.Customer, unmatched.customer_id)
    assert new_customer is not None and new_customer.company_name == "CR14 Import Unmatched Customer Name", (
        "The auto-created Customer must carry the imported row's exact customer_name"
    )
    assert new_customer.company_id == ids["company_id"], (
        "The auto-created Customer must be scoped to the importing row's own company"
    )
    session.close()


def test_customer_trial_csv_import_never_persists_unlinked_customer_id(seeded_grade_and_customer):
    """Regression requirement from Charlie's CR-14 closeout review
    (2026-08-13): 'Add an executed regression test proving an unmatched
    imported customer cannot result in a persisted Customer Trial with
    customer_id empty.' Imports a batch of rows with no Customer master
    match at all (fresh company, zero pre-existing Customers) and asserts
    every single persisted CustomerTrial row has a non-NULL customer_id
    pointing at a real Customer row."""
    ids = seeded_grade_and_customer
    at = _run(PAGE_CUSTOMER_TRIALS)

    csv_bytes = (
        "foam_grade_id,customer_name\n"
        f"{ids['grade_id']},CR14 Regress Unlinked Customer A\n"
        f"{ids['grade_id']},CR14 Regress Unlinked Customer B\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "ct_trial_upload")
    uploader.set_value(("trials.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_ct_trial_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.CustomerTrial)
        .filter(db.CustomerTrial.customer_name.in_(
            ["CR14 Regress Unlinked Customer A", "CR14 Regress Unlinked Customer B"]
        ))
        .all()
    )
    assert len(imported) == 2, "Both rows must have imported"
    for trial in imported:
        assert trial.customer_id is not None, (
            f"CustomerTrial #{trial.id} ('{trial.customer_name}') persisted with customer_id "
            "empty - every normal import path must produce a linked Customer Trial"
        )
        linked_customer = session.get(db.Customer, trial.customer_id)
        assert linked_customer is not None and linked_customer.company_name == trial.customer_name
    session.close()


# ---------------------------------------------------------------------------
# Acceptance criterion 10 + regression requirement: existing trial and
# sample records remain intact (preservation) after the relationship
# change - proven by seeding a Sample against a legacy (customer_id NULL)
# trial and confirming it is still readable through the page's own
# Manage samples workspace, unaffected by the new FK.
# ---------------------------------------------------------------------------

def test_existing_samples_on_legacy_trial_remain_intact(seeded_legacy_trial):
    """Acceptance criterion 10: a Sample recorded against a legacy trial
    (created before customer_id existed on any row) is still visible and
    editable through the Manage samples workspace after CR-14."""
    ids = seeded_legacy_trial
    session = db.get_session()
    sample = db.Sample(customer_trial_id=ids["exact_trial_id"], zone_label="Top")
    session.add(sample)
    session.commit()
    sample_id = sample.id
    session.close()

    at = _run(PAGE_CUSTOMER_TRIALS)
    assert not at.exception

    trial_select = next(s for s in at.selectbox if s.key == "ct_manage_trial")
    # Select whichever option corresponds to the exact-match trial (it has
    # a Sample seeded above; format_func embeds the trial id and customer
    # name, so match on the exact trial's id string).
    target_option_idx = next(
        i for i, opt in enumerate(trial_select.options) if f"#{ids['exact_trial_id']} " in opt
    )
    trial_select.select_index(target_option_idx)
    at.run()
    assert not at.exception

    session = db.get_session()
    still_there = session.get(db.Sample, sample_id)
    assert still_there is not None, "The pre-existing sample on a legacy trial must remain intact"
    assert still_there.customer_trial_id == ids["exact_trial_id"]
    session.close()


# ---------------------------------------------------------------------------
# Regression requirement: backfill/migration helper behavior (also
# separately smoke-tested standalone; this proves it's reachable/callable
# from the module the app actually imports it from and behaves the same
# way against a fixture seeded through the ORM like every other test in
# this file, rather than only a bespoke ad hoc script).
# ---------------------------------------------------------------------------

def test_backfill_trial_customers_links_creates_and_never_merges(seeded_legacy_trial):
    """Regression requirement (migration/mapping method): running
    cascades.backfill_trial_customers() against the legacy fixture links
    the exact-match trial to the existing Customer (no new Customer
    created for it), creates exactly one new Customer for the unmatched
    trial's historical name, and both trials keep their original
    customer_name text untouched throughout."""
    ids = seeded_legacy_trial
    session = db.get_session()
    pre_count = session.query(db.Customer).count()

    result = cascades.backfill_trial_customers(session)

    assert result["linked"] == 2
    assert result["created"] == 1
    post_count = session.query(db.Customer).count()
    assert post_count == pre_count + 1

    exact_trial = session.get(db.CustomerTrial, ids["exact_trial_id"])
    assert exact_trial.customer_id == ids["customer_id"], (
        "The exact-match legacy trial must link to the EXISTING customer, not a newly created duplicate"
    )
    assert exact_trial.customer_name == ids["customer_name"]

    unmatched_trial = session.get(db.CustomerTrial, ids["unmatched_trial_id"])
    assert unmatched_trial.customer_id is not None
    new_customer = session.get(db.Customer, unmatched_trial.customer_id)
    assert new_customer.company_name == "CR14 Totally Unmatched Historical Name"
    assert unmatched_trial.customer_name == "CR14 Totally Unmatched Historical Name"
    session.close()


# ---------------------------------------------------------------------------
# is_valid_email() unit coverage (direct, no UI) - both valid and invalid
# inputs, plus the "empty is valid" rule CR-14 section 3 requires
# ("validate email format WHEN a value is entered").
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [
        ("", True),
        (None, True),
        ("   ", True),
        ("a@b.com", True),
        ("john.doe+tag@sub.example.co", True),
        ("not-an-email", False),
        ("missing-at-sign.com", False),
        ("double@@at.com", False),
        ("no-domain@", False),
    ],
)
def test_is_valid_email_cases(value, expected):
    """Direct unit coverage of helpers.is_valid_email() - the same
    function both the Customers page's Create/Edit forms and CSV import
    path call, covering both valid and invalid formats plus the
    empty/blank-is-valid rule."""
    assert is_valid_email(value) is expected
