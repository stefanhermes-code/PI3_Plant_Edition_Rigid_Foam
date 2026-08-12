"""CR-11 (Standardize Record Create, Edit/Delete and CSV/Excel Import
Functions, 2026-08-12) - forced-password-reset gate for CSV/Excel-imported
User Accounts.

Per user direction on this specific page (security-sensitive, bulk account
creation): an account created through pages/25_User_Accounts.py's CSV/Excel
import tab gets a system-generated temporary password and
User.must_reset_password=True, and auth.require_login() must block that
account from reaching any page content until it sets its own password -
see auth.py's _render_forced_password_reset() and db.py's User.
must_reset_password docstring.

Mirrors the established AUTH_DISABLED AppTest pattern used elsewhere in
this suite (see test_cr08_raw_material_taxonomy.py's docstring), except
this test deliberately does NOT set AUTH_DISABLED - that dev bypass skips
real login (and therefore skips the must_reset_password gate) entirely, so
exercising the gate itself requires simulating an already-authenticated
"real" DB session the way _start_db_session() would have left it, flag and
all, then letting require_login() run against that state exactly as it
would for a real logged-in user."""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import auth
import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE1 = os.path.join(APP_DIR, "pages", "1_Plant_Installation_Overview.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_user():
    """One company + one built-in-shaped custom role + one User, with
    must_reset_password=True and a known temporary password hash - exactly
    the shape pages/25_User_Accounts.py's CSV/Excel import tab leaves
    behind for an imported account."""
    db.init_db()
    _reset_schema()
    session = db.get_session()
    u = uuid.uuid4().hex[:8]

    company = db.Company(name=f"CR11 Co {u}", is_platform_owner=False)
    session.add(company)
    session.flush()
    role = db.Role(company_id=company.id, name="Read Only", is_builtin=False)
    session.add(role)
    session.flush()
    temp_password = "Temp-" + uuid.uuid4().hex[:10]
    imported_user = db.User(
        company_id=company.id,
        email=f"imported.{u}@example.com",
        username=f"imported.{u}@example.com",
        password_hash=auth.hash_password(temp_password),
        display_name="Imported User",
        role_id=role.id,
        active=True,
        must_reset_password=True,
    )
    session.add(imported_user)
    session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "role_id": role.id, "role_name": role.name,
        "user_id": imported_user.id, "email": imported_user.email,
        "temp_password": temp_password,
    }
    session.close()
    return ids


def _authenticated_session_state(at, seeded, must_reset):
    """Populate at.session_state the way auth._start_db_session() would
    have, minus the parts (last_login_at write, audit log row) that don't
    matter for exercising the gate itself."""
    at.session_state["authenticated"] = True
    at.session_state["auth_source"] = "db"
    at.session_state["user_id"] = seeded["user_id"]
    at.session_state["username"] = seeded["email"]
    at.session_state["display_name"] = "Imported User"
    at.session_state["role_id"] = seeded["role_id"]
    at.session_state["role"] = seeded["role_name"]
    at.session_state["company_id"] = seeded["company_id"]
    at.session_state["is_platform_owner"] = False
    at.session_state["is_super_admin"] = False
    at.session_state["must_reset_password"] = must_reset
    return at


def test_must_reset_password_defaults_false_for_a_manually_created_user(seeded_user):
    """The manual Create-user path (pages/25_User_Accounts.py's Create tab)
    never passes must_reset_password - confirms the column's default (see
    db.py) leaves ordinary accounts unaffected, so this gate is specific to
    CSV/Excel-imported accounts, not every new account."""
    session = db.get_session()
    manually_created = db.User(
        company_id=seeded_user["company_id"],
        email="manual.create@example.com",
        username="manual.create@example.com",
        password_hash=auth.hash_password("whatever-the-admin-picked"),
        display_name="Manually Created",
        role_id=seeded_user["role_id"],
        active=True,
    )
    session.add(manually_created)
    session.commit()
    assert manually_created.must_reset_password is False
    session.close()


def test_forced_reset_gate_blocks_page_content_and_shows_reset_form(seeded_user):
    """An authenticated session carrying must_reset_password=True never
    reaches the real page - it sees only the forced-reset form, and the
    page's own title/content ('Plants', its tabs, etc.) never renders."""
    at = AppTest.from_file(PAGE1, default_timeout=30)
    _authenticated_session_state(at, seeded_user, must_reset=True)
    at.run()

    assert not at.exception
    warning_texts = " ".join(w.value for w in at.warning)
    assert "temporary password" in warning_texts.lower()
    title_texts = [t.value for t in at.title]
    assert "Plants" not in title_texts
    # The forced-reset form's own two password fields are present; nothing
    # from pages/1's Create/Edit-Delete/Import tabs is.
    assert len(at.text_input) == 2


def test_setting_a_new_password_clears_the_flag_and_unblocks_the_page(seeded_user):
    """Submitting the forced-reset form with matching passwords updates the
    stored hash, clears must_reset_password on both the DB row and
    session_state, and a subsequent run of the same page reaches real page
    content (CR-11's own 'Create Plant/Edit-Delete Plant/CSV-Excel import
    Plants' tab labels, confirming pages/1's restructuring from earlier in
    this CR is still intact end-to-end)."""
    at = AppTest.from_file(PAGE1, default_timeout=30)
    _authenticated_session_state(at, seeded_user, must_reset=True)
    at.run()

    new_password = "Brand-New-Password-42"
    at.text_input[0].set_value(new_password)
    at.text_input[1].set_value(new_password)
    at.button[0].click().run()

    assert not at.exception
    assert at.session_state["must_reset_password"] is False

    session = db.get_session()
    refreshed = session.query(db.User).filter(db.User.id == seeded_user["user_id"]).first()
    assert refreshed.must_reset_password is False
    assert auth.verify_password(new_password, refreshed.password_hash)
    assert not auth.verify_password(seeded_user["temp_password"], refreshed.password_hash)
    session.close()

    # Re-run now that the flag is cleared: the gate should no longer engage,
    # and the real page (CR-11's mandated tab labels) should render.
    at2 = AppTest.from_file(PAGE1, default_timeout=30)
    _authenticated_session_state(at2, seeded_user, must_reset=False)
    at2.run()
    assert not at2.exception
    title_texts = [t.value for t in at2.title]
    assert "Plants" in title_texts
    tab_labels = [t.label for t in at2.tabs]
    assert tab_labels[:3] == ["Create Plant", "Edit/Delete Plant", "CSV/Excel import Plants"]


def test_mismatched_passwords_are_rejected_and_flag_stays_set(seeded_user):
    at = AppTest.from_file(PAGE1, default_timeout=30)
    _authenticated_session_state(at, seeded_user, must_reset=True)
    at.run()

    at.text_input[0].set_value("one-password")
    at.text_input[1].set_value("a-different-password")
    at.button[0].click().run()

    assert not at.exception
    error_texts = " ".join(e.value for e in at.error)
    assert "match" in error_texts.lower()
    assert at.session_state["must_reset_password"] is True

    session = db.get_session()
    refreshed = session.query(db.User).filter(db.User.id == seeded_user["user_id"]).first()
    assert refreshed.must_reset_password is True
    session.close()
