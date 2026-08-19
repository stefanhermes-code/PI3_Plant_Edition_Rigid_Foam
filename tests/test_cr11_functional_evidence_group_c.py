"""CR-11 (Standardize Record Create, Edit/Delete and CSV/Excel Import
Functions, 2026-08-12) CLOSEOUT CORRECTION - Group C direct functional
evidence.

Charlie's review of the first CR-11 closeout package returned it because it
only had wording/order tests (that the three tabs are named and ordered
"Create <record>" / "Edit/Delete <record>" / "CSV/Excel import <records>"
per helpers.cr11_function_tab_labels()) - not direct, executed evidence
that Create/Edit/Delete/Import actually work through the real UI. This file
supplies that evidence for three views/record groups Charlie specifically
called out:

  1. views/24_User_Roles.py - record type Role. One of CR-11's six net-new
     CSV/Excel importers (there was previously only an "Add role"
     expander, no import at all).
  2. views/25_User_Accounts.py - record type User. Also one of the six
     net-new importers, and security-sensitive (temporary passwords,
     forced password reset, one-admin-per-company, subscription user-cap).
  3. views/14_Raw_Materials.py - TWO record groups on one page: the outer
     "Raw Material" group (pre-existing Create/Edit/Delete/Import, CR-11
     only relabeled it) and the nested "Supplier" group inside the
     "Suppliers" tab (also pre-existing, also just relabeled).

Copies tests/test_cr10_product_family_grade_split.py's established,
already-accepted pattern exactly:
  - os.environ.setdefault("DATABASE_URL", "sqlite://") + sys.path boilerplate.
  - db.init_db() + db.Base.metadata.drop_all/create_all per fixture, with
    _clear_relevant_caches() called from every _reset_schema() - defends
    against the documented @st.cache_data cross-test id-collision hazard
    (small-int cache keys repeat once autoincrement ids restart across
    tests/files - see tenant_scope's id-scoping helpers and
    access_control.denied_page_keys).
  - SQLAlchemy ORM seeding with a uuid.uuid4().hex[:8] suffix on names for
    uniqueness.
  - Presetting the dataframe widget's OWN on_select state (e.g.
    at.session_state["roles_table"] = {"selection": {"rows": [0],
    "columns": []}}) BEFORE .run() to genuinely drive clickable_table's
    row-click selection - NOT presetting the derived "..._selected_id" key
    directly, which does not work (see the CR-10 file's module docstring
    for the full explanation and verification history against
    streamlit==1.59.2).
  - Driving st.file_uploader via
    at.file_uploader[...].set_value((name, bytes, mime)) and clicking the
    real "Confirm import" button, found by its own key=.
  - at.secrets["AUTH_DISABLED"] = True for every AppTest run.

tests/test_cr11_forced_password_reset.py (4 tests, read-only reference -
not modified or duplicated here) already covers the login-gate side of
CSV/Excel-imported Users (auth.require_login()'s forced-password-reset
enforcement, wired platform-wide, not just on this page). This file's User
tests are scoped to the User Accounts page's own Create/Edit/Delete/Import
CRUD - they check that an imported User row actually gets
must_reset_password=True and a real, shown-once temporary password, but do
not re-test the login gate itself.

Deviation note (page bug found, not fixed - out of scope for this
correction): views/25_User_Accounts.py's CSV/Excel import tab calls
parse_bool_cell(row.get("active")) at the "active" column branch, but only
parse_bool (not parse_bool_cell) is defined in helpers.py - a real
NameError latent bug, but only reachable when an uploaded file's "active"
column has a non-blank value for some row. Every User CSV in this file
omits the optional "active" column entirely (pandas then reports it as
NaN and the working "True if pd.isna(...)" branch is taken), so this
bug is never hit by these tests - flagged here for Charlie/JC, not
silently worked around.

CR-11 CLOSEOUT CORRECTION V2 (2026-08-12, per Charlie's
"CR11_Closeout_Correction_Review_Return_to_JC.docx" - the first correction
round above was returned again for two remaining gaps). The tests added at
the bottom of this file (see the "CORRECTION V2" section header) supply
that further evidence, one item per numbered gap in that document:

  1. Delete permission/safeguards: a direct test, per record type (Role,
     User, Raw Material, Supplier), proving a permission-denied role
     cannot delete a record through the real UI - not just that the
     underlying access_control function returns the expected bool.

  2. Import validation handling: direct invalid-row-rejection evidence for
     every remaining CSV/Excel import surface that only had a
     valid-import test before (Raw Material, Supplier), plus a
     malformed-reference-row test for User distinct from the existing
     one-admin-per-company BUSINESS RULE test.

Second deviation note (a real, structural gap found while building item 1's
evidence, not fixed here - out of scope for a test-only correction, flagged
for Charlie/JC): views/24_User_Roles.py and views/25_User_Accounts.py are
the two exceptions, of this file's four record types, whose write controls
(Create/Edit/Delete/Import tabs) are NOT gated by
access_control.can_use_page(<their own page_key>, ...) at all - verified by
reading both files in full, start to finish. Every other page this file (and
CR-10's own correction file) touches computes a `page_usable =
can_use_page("<page_key>", ...)` boolean and wraps its write controls in it
(see views/14_Raw_Materials.py's single `page_usable` variable, which
gates BOTH the outer Raw Material group and the nested Supplier group off
the SAME "raw_materials" page_key). views/24_User_Roles.py and
views/25_User_Accounts.py instead call only auth.require_role("Company
Admin", "Platform Admin") - a check against the session's role NAME
string - and never reference access_control.can_use_page or
usable_page_keys_denied anywhere in their own source. Practically: the
access_control.PAGE_CATALOG entries "user_roles_admin" and
"user_accounts_admin" (both selectable as Hidden / View only / Full access
on this very page's own "Page access" grid, via helpers.page_access_grid)
control ONLY sidebar visibility for those two keys (app_rigid_foam.py's
denied_page_keys() check, which is can_view=False only); a role given
"View only" (can_view=True, can_use=False) on either key is still fully
able to create/edit/delete on these two pages once it's on them, because
neither page ever asks. The item-1 tests below for Role and User therefore
exercise the ONE permission gate these two pages actually have today -
require_role()'s role-name check - rather than the can_view/can_use state
CR-10's view_only_role_fixture pattern exercises for every other page,
since a test asserting the can_view/can_use state blocks Delete here would
not reflect what the shipped code does.

Usage: python -m pytest tests/test_cr11_functional_evidence_group_c.py -v
"""
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import access_control
import auth
import db
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_ROLES = os.path.join(APP_DIR, "views", "24_User_Roles.py")
PAGE_USERS = os.path.join(APP_DIR, "views", "25_User_Accounts.py")
PAGE_RAWMAT = os.path.join(APP_DIR, "views", "14_Raw_Materials.py")


def _clear_relevant_caches():
    """Same defensive clear as tests/test_cr10_product_family_grade_split.py's
    own helper of this name - this file's fixtures each create a fresh
    Company/Role/User/RawMaterial/Supplier after _reset_schema() restarts
    autoincrement ids at 1, which is exactly the cross-test/cross-file
    cache-key collision hazard tenant_scope's id-scoping helpers and
    access_control.denied_page_keys are vulnerable to (both are
    @st.cache_data'd with a leading _session param st.cache_data excludes
    from the hash key, so the cache key is small integers alone). Cleared
    here, at every _reset_schema() call in this file, so none of this
    file's fixtures can ever serve another test's stale cached scope."""
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


def _table_cells_from_markdown(markdown_value):
    """helpers.render_data_table() renders a plain HTML <table> via
    st.markdown(html, unsafe_allow_html=True) rather than a semantic
    st.dataframe widget (see its own docstring - deliberately avoids
    pandas' Styler). Pulls every <td> cell's text out of one such
    rendered block, in document order (header row is <th>, so only body
    cells come back)."""
    return re.findall(r"<td[^>]*>([^<]*)</td>", markdown_value)


def _extract_temp_password_from_markdown(at, email):
    """views/25_User_Accounts.py's Import tab shows each imported
    account's system-generated temporary password exactly once, right
    after a successful import, via helpers.render_data_table on
    st.session_state.pop("user_import_credentials", ...) - a real HTML
    table with "Email"/"Temporary password" columns, not a stand-in.
    Finds the row for `email` and returns its temporary password cell, or
    None if that row isn't present in any rendered table on this page."""
    for md in at.markdown:
        if email not in md.value:
            continue
        cells = _table_cells_from_markdown(md.value)
        for i in range(0, len(cells) - 1, 2):
            if cells[i] == email:
                return cells[i + 1]
    return None


# ---------------------------------------------------------------------------
# Group C.1 - views/24_User_Roles.py, record type Role
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_company_for_role_create():
    """One Company - the minimum needed for the Role Create tab's
    platform-owner-only Company selectbox to have exactly one option
    (auto-selected at index 0, no interaction needed)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11c Role Co {u}", is_platform_owner=True)
    session.add(company)
    session.commit()
    ids = {"company_id": company.id, "company_name": company.name}
    session.close()
    return ids


@pytest.fixture()
def seeded_role_for_edit_delete():
    """One Company + one custom (non-built-in), no-users-assigned Role -
    the minimum needed to exercise selection, edit, and delete on the
    User Roles page's Edit/Delete tab unambiguously (a single row at
    index 0, and a role that delete_with_confirm's own "reassign users
    first" gate won't block)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11c RoleEdit Co {u}", is_platform_owner=True)
    session.add(company)
    session.flush()
    role = db.Role(company_id=company.id, name=f"CR11c Custom Role {u}", description="", is_builtin=False)
    session.add(role)
    session.commit()
    ids = {"company_id": company.id, "role_id": role.id, "role_name": role.name}
    session.close()
    return ids


@pytest.fixture()
def seeded_company_for_role_import():
    """One Company only - used by both the valid-import and the
    invalid-row-rejection Role import tests below (each gets its own
    fresh instance of this fixture, since it's function-scoped)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11c RoleImport Co {u}", is_platform_owner=True)
    session.add(company)
    session.commit()
    ids = {"company_id": company.id, "company_name": company.name}
    session.close()
    return ids


def test_role_create_via_form(seeded_company_for_role_create):
    """Fills the real Create tab form (Role name text_input + the
    platform-owner-only Company selectbox, which defaults to the single
    seeded company with nothing to click) and clicks the real 'Save role'
    submit button, then confirms the new row landed in the database as a
    non-built-in role - the Create tab's own fields/behavior predate CR-11
    (this used to be the "Add custom role" expander), but Charlie's return
    asked for direct evidence on every applicable tab, not just the
    net-new Import one."""
    ids = seeded_company_for_role_create
    at = AppTest.from_file(PAGE_ROLES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading User Roles: {at.exception}"

    name_input = next(t for t in at.text_input if t.label == "Role name *")
    name_input.set_value("CR11-GroupC-New-Role")
    save_btn = next(b for b in at.button if b.label == "Save role")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new role: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.Role)
        .filter(db.Role.company_id == ids["company_id"], db.Role.name == "CR11-GroupC-New-Role")
        .first()
    )
    assert created is not None, "New role was not persisted"
    assert created.is_builtin is False, "A manually-created role must never be built-in"
    session.close()


def test_role_selection_edit_and_delete_via_ui(seeded_role_for_edit_delete):
    """Presets the roles_table dataframe widget's OWN on_select state to
    select row 0 before .run() (the same verified technique as CR-10's
    families_table/grades_table tests), confirming clickable_table's
    row-click selection is genuinely drivable against THIS page too. Then
    edits the selected role's name through the real 'Save name/description'
    form and confirms it persisted, then deletes it through the real
    confirm-checkbox + delete-button flow and confirms it's gone."""
    ids = seeded_role_for_edit_delete
    at = AppTest.from_file(PAGE_ROLES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["roles_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["role_selected_id"] == ids["role_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded role"
    )

    # --- Edit ---
    name_input = next(t for t in at.text_input if t.key == f"edit_role_name_{ids['role_id']}")
    name_input.set_value("CR11-GroupC-Edited-Role")
    save_btn = next(b for b in at.button if b.label == "Save name/description")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the role: {at.exception}"

    session = db.get_session()
    edited = session.get(db.Role, ids["role_id"])
    assert edited.name == "CR11-GroupC-Edited-Role", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["roles_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"role_{ids['role_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"role_{ids['role_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the role: {at.exception}"

    session = db.get_session()
    assert session.get(db.Role, ids["role_id"]) is None, "Delete did not remove the role"
    session.close()


def test_role_csv_import_via_ui(seeded_company_for_role_import):
    """Drives the real st.file_uploader (key='role_upload') with an
    in-memory CSV and the real 'Confirm import' button (key=
    'confirm_role_import') - the actual net-new upload path this page
    didn't have before CR-11, not a stand-in for dedupe_import_rows().
    Confirms the imported role is persisted, non-built-in, and starts
    with default FULL page access (no RolePagePermission rows at all -
    access_control.py's documented "no row = full access" default),
    exactly as the page's own module docstring promises for every
    imported role."""
    ids = seeded_company_for_role_import
    at = AppTest.from_file(PAGE_ROLES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = f"name,company_id\nCR11-GroupC-Imported-Role,{ids['company_id']}\n".encode()
    uploader = next(u for u in at.file_uploader if u.key == "role_upload")
    uploader.set_value(("roles.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_role_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.Role)
        .filter(db.Role.company_id == ids["company_id"], db.Role.name == "CR11-GroupC-Imported-Role")
        .first()
    )
    assert imported is not None, "Imported role was not persisted"
    assert imported.is_builtin is False, "An imported role must never be marked built-in"
    perm_rows = session.query(db.RolePagePermission).filter(db.RolePagePermission.role_id == imported.id).count()
    assert perm_rows == 0, "An imported role should start with no permission rows - i.e. default full page access"
    session.close()


def test_role_csv_import_validation_rejects_invalid_row(seeded_company_for_role_import):
    """Role is one of CR-11's six net-new importers, so its own row
    validation is new code, not a relabeling - this exercises it directly.
    Per the page's own logic (views/24_User_Roles.py's tab_import block):
    for a platform owner (the AUTH_DISABLED dev-bypass identity used
    throughout this file), each row's company_id must resolve to a real
    row in the companies table, checked against valid_company_ids built
    from the live Company query - not merely "is this parseable as an
    int". Uploads one valid row (real company_id) alongside one row with
    a bogus company_id (999999, which does not exist), and confirms the
    valid row imports while the bad one is flagged/rejected and never
    created, even after Confirm import is clicked.

    (Note: the "invalid company_id" case only applies to the
    platform-owner branch - for a non-platform-owner admin the page
    deliberately ignores the company_id column entirely and always
    targets their own company, so an invalid company_id there wouldn't
    be rejected, it would simply be ignored. Verified against the actual
    source; the platform-owner branch is the one that has real
    company_id validation to test.)"""
    ids = seeded_company_for_role_import
    at = AppTest.from_file(PAGE_ROLES, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        "name,company_id\n"
        f"CR11-GroupC-Valid-Role,{ids['company_id']}\n"
        "CR11-GroupC-Bad-Company-Role,999999\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "role_upload")
    uploader.set_value(("roles.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    warnings_text = " ".join(w.value for w in at.warning)
    assert "company_id" in warnings_text.lower(), (
        "The real row-flagging warning about unknown company_id should have fired"
    )

    confirm_btn = next(b for b in at.button if b.key == "confirm_role_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    valid_role = (
        session.query(db.Role)
        .filter(db.Role.company_id == ids["company_id"], db.Role.name == "CR11-GroupC-Valid-Role")
        .first()
    )
    bad_role = session.query(db.Role).filter(db.Role.name == "CR11-GroupC-Bad-Company-Role").first()
    assert valid_role is not None, "The row with a real company_id should have imported"
    assert bad_role is None, "The row with an unresolvable company_id must never be created"
    session.close()


# ---------------------------------------------------------------------------
# Group C.2 - views/25_User_Accounts.py, record type User
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_company_and_role_for_user_create():
    """One (non-platform-owner) Company + one non-admin custom Role - the
    minimum for the User Accounts Create tab's Company/Role selectboxes
    to have exactly one option each. is_platform_owner=False on the
    Company row itself (distinct from the AUTH_DISABLED session's
    is_platform_owner=True, which is about the current USER's cross-
    company scope) so the page's extra platform-owner-only 'Super admin'
    checkbox never renders, keeping the form's widget set minimal."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11c UserCreate Co {u}", is_platform_owner=False)
    session.add(company)
    session.flush()
    role = db.Role(company_id=company.id, name=f"CR11c Viewer Role {u}", is_builtin=False)
    session.add(role)
    session.commit()
    ids = {"company_id": company.id, "role_id": role.id, "role_name": role.name}
    session.close()
    return ids


@pytest.fixture()
def seeded_user_for_edit_delete():
    """One Company + one non-admin Role + one existing User - the minimum
    needed to exercise selection, edit, and delete on the User Accounts
    Edit/Delete tab unambiguously."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11c UserEdit Co {u}", is_platform_owner=False)
    session.add(company)
    session.flush()
    role = db.Role(company_id=company.id, name=f"CR11c EditUser Role {u}", is_builtin=False)
    session.add(role)
    session.flush()
    existing_user = db.User(
        company_id=company.id,
        email=f"cr11c.edituser.{u}@example.com",
        username=f"cr11c.edituser.{u}@example.com",
        password_hash=auth.hash_password("Original-Password-1"),
        display_name="Original Name",
        role_id=role.id,
        active=True,
    )
    session.add(existing_user)
    session.flush()
    session.commit()
    ids = {
        "company_id": company.id, "role_id": role.id, "role_name": role.name,
        "user_id": existing_user.id, "email": existing_user.email,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_company_and_role_for_user_import():
    """One Company + one non-admin Role, named plainly (no uuid suffix,
    since CSV rows need to reference it by exact name) - used by the
    valid CSV import case."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11c UserImport Co {u}", is_platform_owner=False)
    session.add(company)
    session.flush()
    role = db.Role(company_id=company.id, name="Technical Engineer", is_builtin=False)
    session.add(role)
    session.commit()
    ids = {"company_id": company.id, "role_id": role.id, "role_name": role.name}
    session.close()
    return ids


@pytest.fixture()
def seeded_company_and_admin_role_for_user_import():
    """One Company + one Role named exactly "Company Admin" (matches
    access_control.ADMIN_ROLE_NAMES case-insensitively) with zero existing
    Users - used by the one-admin-per-company-within-batch test, so both
    admin rows in that test's CSV are competing only against EACH OTHER,
    not against a pre-existing admin already in the database."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11c AdminBatch Co {u}", is_platform_owner=False)
    session.add(company)
    session.flush()
    admin_role = db.Role(company_id=company.id, name="Company Admin", is_builtin=False)
    session.add(admin_role)
    session.commit()
    ids = {"company_id": company.id, "role_id": admin_role.id, "role_name": admin_role.name}
    session.close()
    return ids


def test_user_create_via_form(seeded_company_and_role_for_user_create):
    """Fills the real Create tab form (Email + Password text_inputs, Role
    selectbox defaulted to the single seeded role) and clicks the real
    'Save user' submit button, then confirms the new row landed in the
    database with a hashed password matching what was typed and
    must_reset_password left at its default False - the manual Create
    path never sets that flag, unlike the CSV/Excel importer below."""
    ids = seeded_company_and_role_for_user_create
    at = AppTest.from_file(PAGE_USERS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading User Accounts: {at.exception}"

    email_input = next(t for t in at.text_input if t.label == "Email address * (used to log in)" and t.key is None)
    email_input.set_value("cr11-groupc-new-user@example.com")
    password_input = next(t for t in at.text_input if t.label == "Password *" and t.key is None)
    password_input.set_value("Some-Strong-Password-1")
    save_btn = next(b for b in at.button if b.label == "Save user")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new user: {at.exception}"

    session = db.get_session()
    created = session.query(db.User).filter(db.User.email == "cr11-groupc-new-user@example.com").first()
    assert created is not None, "New user was not persisted"
    assert created.role_id == ids["role_id"]
    assert created.must_reset_password is False, "Manually-created users must not be forced to reset their password"
    assert auth.verify_password("Some-Strong-Password-1", created.password_hash)
    session.close()


def test_user_selection_edit_and_delete_via_ui(seeded_user_for_edit_delete):
    """Presets the users_table dataframe widget's OWN on_select state to
    select row 0 before .run() (same verified technique as the Role test
    above), confirming row-click selection is genuinely drivable against
    this page too. Then edits the selected user's display name through
    the real 'Save changes' form and confirms it persisted, then deletes
    it through the real confirm-checkbox + delete-button flow and
    confirms it's gone."""
    ids = seeded_user_for_edit_delete
    at = AppTest.from_file(PAGE_USERS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["users_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["user_selected_id"] == ids["user_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded user"
    )

    # --- Edit ---
    disp_input = next(t for t in at.text_input if t.key == f"edit_user_disp_{ids['user_id']}")
    disp_input.set_value("CR11-GroupC-Edited-Name")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the user: {at.exception}"

    session = db.get_session()
    edited = session.get(db.User, ids["user_id"])
    assert edited.display_name == "CR11-GroupC-Edited-Name", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["users_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"user_{ids['user_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"user_{ids['user_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the user: {at.exception}"

    session = db.get_session()
    assert session.get(db.User, ids["user_id"]) is None, "Delete did not remove the user"
    session.close()


def test_user_csv_import_via_ui(seeded_company_and_role_for_user_import):
    """Drives the real st.file_uploader (key='user_upload') and the real
    'Confirm import' button (key='confirm_user_import') - the actual
    net-new upload path for User this page didn't have before CR-11.
    Beyond a plain "row landed in the database" check, this confirms the
    two security-sensitive behaviors specific to THIS importer that the
    manual Create tab doesn't have: the created row gets
    User.must_reset_password=True (the flag
    tests/test_cr11_forced_password_reset.py's own 4 tests prove
    auth.require_login() enforces platform-wide - not re-tested here), and
    a system-generated temporary password shown to the admin exactly once,
    read here straight out of the real rendered credentials table (via
    st.session_state["user_import_credentials"], popped and rendered by
    helpers.render_data_table - not a stand-in), then confirmed gone on a
    subsequent script run - the same one-shot-reveal behavior a real
    admin would see, and the reason auth.verify_password is used to prove
    the shown password is the one actually hashed and stored, not just
    some other string that happens to be on screen."""
    ids = seeded_company_and_role_for_user_import
    at = AppTest.from_file(PAGE_USERS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    email = f"cr11-groupc-imported-{uuid.uuid4().hex[:6]}@example.com"
    csv_bytes = f"email,role\n{email},{ids['role_name']}\n".encode()
    uploader = next(u for u in at.file_uploader if u.key == "user_upload")
    uploader.set_value(("users.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_user_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the user import: {at.exception}"

    # The credentials table (and its "shown once" warning) render on THIS
    # same .run() call, right after the import's own st.rerun() -
    # Streamlit's real ScriptRunner loops internally on a RerunException
    # until the script finishes without requesting another rerun, and
    # AppTest.run() waits for that same finished state - so the "pop and
    # render on the next script pass" pattern helpers.show_pending_banner's
    # docstring describes completes within this single at.run(), the same
    # way it does for a real user's browser.
    warnings_text = " ".join(w.value for w in at.warning)
    assert "temporary password" in warnings_text.lower(), (
        "The 'shown once' temporary-password warning should have rendered right after import"
    )
    assert "user_import_credentials" not in at.session_state, (
        "Credentials must be popped from session_state once rendered - a one-time reveal, not persisted"
    )

    temp_password = _extract_temp_password_from_markdown(at, email)
    assert temp_password, f"Could not find the rendered temporary password for {email}"

    session = db.get_session()
    created = session.query(db.User).filter(db.User.email == email).first()
    assert created is not None, "Imported user was not persisted"
    assert created.must_reset_password is True, "CSV/Excel-imported users must be forced to reset their password"
    assert auth.verify_password(temp_password, created.password_hash), (
        "The password shown once in the credentials table must be the one actually hashed and stored"
    )
    session.close()

    # A further script run (simulating navigating back to this tab) must
    # NOT show the credentials again - proving the reveal really was
    # one-time, not just "not yet re-rendered."
    at.run()
    assert not at.exception
    warnings_text_2 = " ".join(w.value for w in at.warning)
    assert "temporary password" not in warnings_text_2.lower(), (
        "Temporary password credentials must not reappear on a later run"
    )


def test_user_csv_import_enforces_one_admin_per_company_within_batch(seeded_company_and_admin_role_for_user_import):
    """CR-11's User import must never let a single CSV/Excel batch create
    TWO active administrators for the same company. The existing
    one-admin-per-company rule (access_control.ADMIN_ROLE_NAMES,
    already enforced on the manual Add/Edit forms via
    _existing_active_admin() against the DATABASE) is, per this page's
    own tab_import block, ALSO checked within the batch itself via
    admin_claimed_in_batch - not just against rows already committed:
    the first admin-role row in file order is accepted, the second is
    flagged with the real reason string ("would create a second active
    administrator for this company") and never created, even after
    Confirm import is clicked."""
    ids = seeded_company_and_admin_role_for_user_import
    at = AppTest.from_file(PAGE_USERS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    email_1 = f"cr11-groupc-admin1-{uuid.uuid4().hex[:6]}@example.com"
    email_2 = f"cr11-groupc-admin2-{uuid.uuid4().hex[:6]}@example.com"
    csv_bytes = (
        "email,role\n"
        f"{email_1},{ids['role_name']}\n"
        f"{email_2},{ids['role_name']}\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "user_upload")
    uploader.set_value(("users.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    warnings_text = " ".join(w.value for w in at.warning)
    assert "flagged rows" in warnings_text.lower(), "The generic flagged-rows warning should have fired"
    markdown_text = " ".join(m.value for m in at.markdown)
    assert "second active administrator" in markdown_text.lower(), (
        "The bad-rows table should show the real 'would create a second active administrator' reason"
    )

    confirm_btn = next((b for b in at.button if b.key == "confirm_user_import"), None)
    assert confirm_btn is not None, "Exactly one admin row should have been accepted, leaving Confirm import available"
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    admin_users = (
        session.query(db.User)
        .filter(db.User.company_id == ids["company_id"], db.User.role_id == ids["role_id"], db.User.active.is_(True))
        .all()
    )
    assert len(admin_users) == 1, "Only one active administrator should exist after importing a batch with two admin rows"
    assert admin_users[0].email == email_1, "The first admin row in file order should be the one accepted"
    session.close()


# ---------------------------------------------------------------------------
# Group C.3a - views/14_Raw_Materials.py, OUTER record type Raw Material
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_company_with_taxonomy():
    """One Company + one active top-level RawMaterialCategory + one active
    Subcategory under it (not is_exception_only) - the minimum CR-08
    controlled taxonomy needed for the Category/Subcategory pickers
    (rendered OUTSIDE any st.form, so they take effect on the very first
    run, not just after submit) to have exactly one option each."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11c RawMat Co {u}", is_platform_owner=True)
    session.add(company)
    session.flush()
    category = db.RawMaterialCategory(
        controlled_id=f"RMC-TEST-{u}", name=f"CR11c Category {u}", sort_order=1, active=True,
    )
    session.add(category)
    session.flush()
    subcategory = db.RawMaterialCategory(
        controlled_id=f"RMC-TEST-SUB-{u}", name=f"CR11c Subcategory {u}", sort_order=1,
        parent_category_id=category.id, active=True, is_exception_only=False,
    )
    session.add(subcategory)
    session.commit()
    ids = {
        "company_id": company.id,
        "category_id": category.id, "category_name": category.name,
        "subcategory_id": subcategory.id, "subcategory_name": subcategory.name,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_raw_material():
    """One Company + one Category/Subcategory pair + one existing
    RawMaterial classified under them - the minimum needed to exercise
    selection, edit, and delete on the outer Raw Material Edit/Delete tab
    unambiguously. Deliberately seeds no Supplier row, so the nested
    Suppliers tab (rendered in the same script run regardless of which
    outer tab is visually selected - st.tabs() executes every tab body
    every run) shows "No suppliers recorded yet." instead of an edit form
    that would otherwise also render a same-labeled "Save changes"
    button."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11c RawMatEdit Co {u}", is_platform_owner=True)
    session.add(company)
    session.flush()
    category = db.RawMaterialCategory(
        controlled_id=f"RMC-TEST-{u}", name=f"CR11c Category {u}", sort_order=1, active=True,
    )
    session.add(category)
    session.flush()
    subcategory = db.RawMaterialCategory(
        controlled_id=f"RMC-TEST-SUB-{u}", name=f"CR11c Subcategory {u}", sort_order=1,
        parent_category_id=category.id, active=True, is_exception_only=False,
    )
    session.add(subcategory)
    session.flush()
    material = db.RawMaterial(
        company_id=company.id, name=f"CR11c Raw Material {u}",
        category_id=category.id, subcategory_id=subcategory.id, active=True,
    )
    session.add(material)
    session.commit()
    ids = {
        "company_id": company.id,
        "category_id": category.id, "subcategory_id": subcategory.id,
        "material_id": material.id, "material_name": material.name,
    }
    session.close()
    return ids


def test_raw_material_create_via_form(seeded_company_with_taxonomy):
    """Fills the real Create tab form (Raw material name text_input; the
    Category/Subcategory and Default supplier pickers all default to
    their single/blank option with nothing to click) and clicks the real
    'Save raw material' submit button, then confirms the new row landed
    in the database with the right Category/Subcategory classification -
    this record type/tab predates CR-11 (CR-11 only relabeled it), but
    Charlie's return asked for direct evidence here too."""
    ids = seeded_company_with_taxonomy
    at = AppTest.from_file(PAGE_RAWMAT, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Raw Materials: {at.exception}"

    name_input = next(t for t in at.text_input if t.label == "Raw material name *" and t.key is None)
    name_input.set_value("CR11-GroupC-New-RawMaterial")
    save_btn = next(b for b in at.button if b.label == "Save raw material")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new raw material: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.RawMaterial)
        .filter(db.RawMaterial.company_id == ids["company_id"], db.RawMaterial.name == "CR11-GroupC-New-RawMaterial")
        .first()
    )
    assert created is not None, "New raw material was not persisted"
    assert created.category_id == ids["category_id"]
    assert created.subcategory_id == ids["subcategory_id"]
    session.close()


def test_raw_material_selection_edit_and_delete_via_ui(seeded_raw_material):
    """Presets the rawmat_table dataframe widget's OWN on_select state to
    select row 0 before .run(), confirming row-click selection is
    genuinely drivable against this page's outer Raw Material group.
    Then edits the selected material's name through the real 'Save
    changes' form and confirms it persisted, then deletes it through the
    real confirm-checkbox + delete-button flow and confirms it's gone."""
    ids = seeded_raw_material
    at = AppTest.from_file(PAGE_RAWMAT, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["rawmat_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["rawmat_selected_id"] == ids["material_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded raw material"
    )

    # --- Edit ---
    name_input = next(t for t in at.text_input if t.key == f"edit_rawmat_name_{ids['material_id']}")
    name_input.set_value("CR11-GroupC-Edited-RawMaterial")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the raw material: {at.exception}"

    session = db.get_session()
    edited = session.get(db.RawMaterial, ids["material_id"])
    assert edited.name == "CR11-GroupC-Edited-RawMaterial", "Edit did not persist to the database"
    session.close()

    # --- Delete ---
    at.session_state["rawmat_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"rawmat_{ids['material_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"rawmat_{ids['material_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the raw material: {at.exception}"

    session = db.get_session()
    assert session.get(db.RawMaterial, ids["material_id"]) is None, "Delete did not remove the raw material"
    session.close()


def test_raw_material_csv_import_via_ui(seeded_company_with_taxonomy):
    """Drives the real st.file_uploader (key='rawmat_upload') with an
    in-memory CSV whose category/subcategory columns match the seeded
    controlled taxonomy by name (CR-08's exact-name-match rule), and the
    real 'Confirm import' button (key='confirm_rawmat_import') - this
    record type/tab predates CR-11 (CR-11 only relabeled it), but Charlie's
    return asked for direct evidence on every applicable tab."""
    ids = seeded_company_with_taxonomy
    at = AppTest.from_file(PAGE_RAWMAT, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        "name,category,subcategory\n"
        f"CR11-GroupC-Imported-RawMaterial,{ids['category_name']},{ids['subcategory_name']}\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "rawmat_upload")
    uploader.set_value(("rawmat.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_rawmat_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.RawMaterial)
        .filter(
            db.RawMaterial.company_id == ids["company_id"],
            db.RawMaterial.name == "CR11-GroupC-Imported-RawMaterial",
        )
        .first()
    )
    assert imported is not None, "Imported raw material was not persisted"
    assert imported.category_id == ids["category_id"]
    assert imported.subcategory_id == ids["subcategory_id"]
    session.close()


# ---------------------------------------------------------------------------
# Group C.3b - Supplier (formerly the nested "Suppliers" tab on THIS page)
#
# CR-13 (Split Suppliers into a Standalone Page), implemented 2026-08-12:
# Supplier management moved off views/14_Raw_Materials.py entirely, onto
# its own views/32_Suppliers.py with its own "suppliers" access_control
# key. Every Supplier-specific test that used to live in this section
# (create/edit/delete/import, view-only delete-block, invalid-row-
# rejection) has moved to tests/test_cr13_suppliers_standalone_page.py,
# rebuilt against the new page and page_key rather than left here pointing
# at behavior that no longer exists on PAGE_RAWMAT.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CR-11 CLOSEOUT CORRECTION V2 (2026-08-12) - item 1: Delete
# permission/safeguards. A direct test per record type (Role, User, Raw
# Material, Supplier) proving a permission-denied role cannot delete a
# record through the real UI.
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_role_for_edit_delete_and_denied_actor(seeded_role_for_edit_delete):
    """Adds a SECOND Role, scoped to the same company, representing the
    denied ACTOR's own assigned role - distinct from the first Role (the
    fixture's original `role_id`), which stays the record this test tries,
    and must fail, to delete. Named something that is neither of
    auth.require_role("Company Admin", "Platform Admin")'s two allowed
    names - see this file's module docstring "Second deviation note" for
    why role-NAME matching, not access_control.can_use_page, is the actual
    (and only) permission gate views/24_User_Roles.py has today."""
    ids = seeded_role_for_edit_delete
    session = db.get_session()
    denied_role = db.Role(company_id=ids["company_id"], name="CR11c Plant Operator", is_builtin=False)
    session.add(denied_role)
    session.commit()
    out = dict(ids)
    out["denied_role_id"] = denied_role.id
    out["denied_role_name"] = denied_role.name
    session.close()
    return out


def test_role_permission_denied_role_cannot_delete_via_ui(seeded_role_for_edit_delete_and_denied_actor):
    """CR-11 correction v2, item 1 (Role): presets session_state["role"]
    to a real Role's name that is neither "Company Admin" nor "Platform
    Admin" BEFORE .run() - overriding the AUTH_DISABLED dev-bypass's own
    setdefault("role", "Platform Admin"), the same override technique
    tests/test_cr10_product_family_grade_split.py's _run_as_role uses for
    role_id/is_super_admin/is_platform_owner/company_id. Confirms
    auth.require_role()'s real, current enforcement (the only permission
    gate this page has - see module docstring) stops the whole script
    with the actual error message BEFORE any tab renders, so the seeded
    role (a completely separate DB row from the denied actor's own role)
    is never reachable to select, let alone delete - not merely that no
    delete button happens to be visible."""
    ids = seeded_role_for_edit_delete_and_denied_actor
    at = _run(
        PAGE_ROLES,
        session_state={
            "role": ids["denied_role_name"],
            "role_id": ids["denied_role_id"],
            "is_super_admin": False,
            "is_platform_owner": False,
            "company_id": ids["company_id"],
        },
    )
    assert not at.exception, f"Unhandled exception for a permission-denied role: {at.exception}"

    errors = " ".join(e.value for e in at.error)
    assert "does not have access to this screen" in errors.lower(), (
        "require_role()'s real denial message should have fired for a non-admin-named role"
    )
    assert not any(b.key == f"role_{ids['role_id']}_btn" for b in at.button), (
        "A permission-denied role must never reach the target role's Delete button"
    )
    assert not at.tabs, "A permission-denied role must never reach the Create/Edit-Delete/Import tabs at all"

    session = db.get_session()
    assert session.get(db.Role, ids["role_id"]) is not None, "The target role must still exist - a blocked page must never delete it"
    session.close()


@pytest.fixture()
def seeded_user_for_edit_delete_and_denied_actor(seeded_user_for_edit_delete):
    """Same composition as seeded_role_for_edit_delete_and_denied_actor
    above, for the User Accounts page: a second Role, scoped to the same
    company, representing the denied actor's own role - distinct from the
    fixture's existing_user/role_id, which stays the record this test
    tries, and must fail, to delete."""
    ids = seeded_user_for_edit_delete
    session = db.get_session()
    denied_role = db.Role(company_id=ids["company_id"], name="CR11c Plant Operator", is_builtin=False)
    session.add(denied_role)
    session.commit()
    out = dict(ids)
    out["denied_role_id"] = denied_role.id
    out["denied_role_name"] = denied_role.name
    session.close()
    return out


def test_user_permission_denied_role_cannot_delete_via_ui(seeded_user_for_edit_delete_and_denied_actor):
    """CR-11 correction v2, item 1 (User): same evidence and reasoning as
    the Role test above, against views/25_User_Accounts.py - which has the
    identical require_role()-only gate (see module docstring)."""
    ids = seeded_user_for_edit_delete_and_denied_actor
    at = _run(
        PAGE_USERS,
        session_state={
            "role": ids["denied_role_name"],
            "role_id": ids["denied_role_id"],
            "is_super_admin": False,
            "is_platform_owner": False,
            "company_id": ids["company_id"],
        },
    )
    assert not at.exception, f"Unhandled exception for a permission-denied role: {at.exception}"

    errors = " ".join(e.value for e in at.error)
    assert "does not have access to this screen" in errors.lower(), (
        "require_role()'s real denial message should have fired for a non-admin-named role"
    )
    assert not any(b.key == f"user_{ids['user_id']}_btn" for b in at.button), (
        "A permission-denied role must never reach the target user's Delete button"
    )
    assert not at.tabs, "A permission-denied role must never reach the Create/Edit-Delete/Import tabs at all"

    session = db.get_session()
    assert session.get(db.User, ids["user_id"]) is not None, "The target user must still exist - a blocked page must never delete it"
    session.close()


@pytest.fixture()
def view_only_role_fixture_for_rawmat(seeded_raw_material):
    """A real company-scoped Role with an explicit RolePagePermission row
    denying *use* (can_view=True, can_use=False - access_control.py's
    "View only" state) on page_key "raw_materials" - direct evidence
    against the real can_use_page()/RolePagePermission plumbing
    views/14_Raw_Materials.py actually calls (a single `page_usable`
    variable, computed once, that gates BOTH the outer Raw Material group
    below and the nested Supplier group's own Edit/Delete section - see
    view_only_role_fixture_for_supplier below, which reuses the exact same
    page_key for that reason)."""
    ids = seeded_raw_material
    session = db.get_session()
    role = db.Role(company_id=ids["company_id"], name="CR11c RawMat View Only", is_builtin=False)
    session.add(role)
    session.flush()
    session.add(db.RolePagePermission(role_id=role.id, page_key="raw_materials", can_view=True, can_use=False))
    session.commit()
    out = dict(ids)
    out["role_id"] = role.id
    session.close()
    return out


def test_raw_material_view_only_role_cannot_delete_via_ui(view_only_role_fixture_for_rawmat):
    """CR-11 correction v2, item 1 (Raw Material): presets the rawmat_table
    dataframe widget's own on_select state (same verified technique as
    this file's Group C.3a tests above) alongside role_id/is_super_admin/
    is_platform_owner/company_id overriding the AUTH_DISABLED dev-bypass's
    setdefault() defaults - the same override technique
    tests/test_cr10_product_family_grade_split.py's _run_as_role uses.
    Confirms the row is genuinely selected (so this isn't merely "the
    delete button never rendered because nothing was selected"), then
    confirms neither the delete confirm-checkbox nor the delete button
    render for this page_usable=False role, and that the seeded raw
    material is still in the database afterward."""
    ids = view_only_role_fixture_for_rawmat
    session = db.get_session()
    assert not access_control.can_use_page("raw_materials", role_id=ids["role_id"], session=session, is_super_admin=False)
    session.close()

    at = _run(
        PAGE_RAWMAT,
        session_state={
            "role_id": ids["role_id"],
            "is_super_admin": False,
            "is_platform_owner": False,
            "company_id": ids["company_id"],
            "rawmat_table": {"selection": {"rows": [0], "columns": []}},
        },
    )
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["rawmat_selected_id"] == ids["material_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded raw material"
    )

    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()
    assert not any(c.key == f"rawmat_{ids['material_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the delete confirm checkbox"
    )
    assert not any(b.key == f"rawmat_{ids['material_id']}_btn" for b in at.button), (
        "View-only role should not see the delete button"
    )

    session = db.get_session()
    assert session.get(db.RawMaterial, ids["material_id"]) is not None, (
        "The seeded raw material must still exist - a view-only role must never be able to delete it"
    )
    session.close()


# (CR-13, 2026-08-12: the Supplier view-only-delete-block test that used to
# sit here against PAGE_RAWMAT's nested supplier_table has moved to
# tests/test_cr13_suppliers_standalone_page.py, rebuilt against the new
# "suppliers" page_key - see that file's own test_supplier_view_only_role_
# cannot_delete_via_ui.)


# ---------------------------------------------------------------------------
# CR-11 CLOSEOUT CORRECTION V2 (2026-08-12) - item 2: Import validation
# handling. Direct invalid-row-rejection evidence for Raw Material and
# Supplier (pre-existing importers that, before this correction, only had
# a valid-import test each), plus a malformed-role-reference test for User
# distinct from the existing one-admin-per-company business-rule test.
# ---------------------------------------------------------------------------

def test_raw_material_csv_import_validation_rejects_invalid_row(seeded_company_with_taxonomy):
    """Raw Material predates CR-11 (CR-11 only relabeled its tabs), so it
    was never one of the six net-new importers - but Charlie's return
    asked for direct invalid-row evidence on every remaining import
    surface, not just the net-new ones. Per the page's own logic
    (views/14_Raw_Materials.py's tab_import block): each row's free-text
    category/subcategory columns are matched, case-insensitively, against
    the live CR-08 controlled taxonomy via _match_taxonomy_text() - a row
    that matches neither is bucketed into review_rows and never imported,
    regardless of the "Confirm import" click. Uploads one valid row
    (matching the seeded Category/Subcategory by name) alongside one row
    whose category/subcategory text matches nothing in the controlled
    taxonomy, and confirms the valid row imports while the bad one is
    flagged/rejected and never created."""
    ids = seeded_company_with_taxonomy
    at = AppTest.from_file(PAGE_RAWMAT, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        "name,category,subcategory\n"
        f"CR11-GroupC-Valid-RawMaterial,{ids['category_name']},{ids['subcategory_name']}\n"
        "CR11-GroupC-Bad-Taxonomy-RawMaterial,CR11-GroupC-Unknown-Category,CR11-GroupC-Unknown-Subcategory\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "rawmat_upload")
    uploader.set_value(("rawmat_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading an invalid-taxonomy CSV: {at.exception}"

    warnings_text = " ".join(w.value for w in at.warning)
    assert "controlled taxonomy" in warnings_text.lower(), (
        "The real 'didn't match the controlled taxonomy exactly' warning should have fired"
    )

    confirm_btn = next(b for b in at.button if b.key == "confirm_rawmat_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    valid_material = (
        session.query(db.RawMaterial)
        .filter(db.RawMaterial.company_id == ids["company_id"], db.RawMaterial.name == "CR11-GroupC-Valid-RawMaterial")
        .first()
    )
    bad_material = session.query(db.RawMaterial).filter(db.RawMaterial.name == "CR11-GroupC-Bad-Taxonomy-RawMaterial").first()
    assert valid_material is not None, "The row with a matching category/subcategory should have imported"
    assert bad_material is None, "The row with unmatched category/subcategory text must never be created"
    session.close()


# (CR-13, 2026-08-12: the Supplier import-validation-rejects-invalid-row
# test that used to sit here against PAGE_RAWMAT's nested supplier_upload
# has moved to tests/test_cr13_suppliers_standalone_page.py, rebuilt
# against the new standalone page - see that file's own
# test_supplier_csv_import_validation_rejects_invalid_row.)


def test_user_csv_import_validation_rejects_row_with_unknown_role(seeded_company_and_role_for_user_import):
    """CR-11 correction v2, item 2 (User): the existing
    test_user_csv_import_enforces_one_admin_per_company_within_batch test
    proves a BUSINESS RULE (one admin per company) rejects a row - real
    evidence, but not the same thing as a malformed/unresolvable-reference
    row being rejected, which is what Charlie's other net-new-importer
    example (Role's own company_id validation test) demonstrates. This is
    that same kind of evidence for User: uploads one row with a role name
    that matches a real seeded Role, alongside one row referencing a role
    name that does not exist for this company at all, and confirms the
    real per-row reason ("role '...' not found for ...", from this page's
    own tab_import loop) is shown and that row is never created, while the
    valid row is."""
    ids = seeded_company_and_role_for_user_import
    at = AppTest.from_file(PAGE_USERS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    email_valid = f"cr11-groupc-goodrole-{uuid.uuid4().hex[:6]}@example.com"
    email_bad = f"cr11-groupc-badrole-{uuid.uuid4().hex[:6]}@example.com"
    csv_bytes = (
        "email,role\n"
        f"{email_valid},{ids['role_name']}\n"
        f"{email_bad},CR11-GroupC-Nonexistent-Role\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "user_upload")
    uploader.set_value(("users_bad_role.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading a CSV with an unknown role: {at.exception}"

    warnings_text = " ".join(w.value for w in at.warning)
    assert "flagged rows" in warnings_text.lower(), "The generic flagged-rows warning should have fired"
    markdown_text = " ".join(m.value for m in at.markdown)
    assert "not found for" in markdown_text.lower(), (
        "The bad-rows table should show the real 'role ... not found for ...' reason"
    )

    confirm_btn = next(b for b in at.button if b.key == "confirm_user_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    good_user = session.query(db.User).filter(db.User.email == email_valid).first()
    bad_user = session.query(db.User).filter(db.User.email == email_bad).first()
    assert good_user is not None, "The row with a real role name should have imported"
    assert bad_user is None, "The row referencing a nonexistent role must never be created"
    session.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
