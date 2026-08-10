"""CR-05 (Default User Role Inheritance and Platform Admin Separation for
UAT, Charlie's instruction 2026-08-11): automated coverage for acceptance
criterion 13 - "Automated role/permission tests pass, including a
company-creation inheritance test and a test proving Platform Admin is
excluded from inherited company roles."

These tests build their own Role template fixtures against a fresh SQLite
schema (see _reset_schema below) rather than depending on live Supabase
data - role templates are pure runtime data (never seeded by init_db(), see
db.py's init_db docstring), so a test that assumed particular template rows
already existed would be testing Supabase's current data, not the
role_provisioning.py logic itself. Live-data verification (that Supabase's
actual templates/clones now match this fixture's expectations) is covered
separately in the CR-05 closeout evidence, not here.

Usage: python -m pytest tests/test_cr05_role_model.py
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
from access_control import ADMIN_ROLE_NAMES, STRUCTURALLY_REQUIRED_ROLE_NAMES, protected_role_name
from role_provisioning import clone_builtin_roles_for_company

# The 4 Default Company Roles CR-05 approves (§3) - the exact set every new
# company must be cloned with, and the exact set every existing company
# (HTC Global, PTU) was backfilled to on Supabase.
APPROVED_DEFAULT_ROLE_NAMES = {"Company Admin", "R&D", "Read Only", "Technical Engineer"}

# The literal legacy names CR-05 §5/§6 requires gone from the customer-facing
# role model - checked case-insensitively, since that's how the app's own
# ADMIN_ROLE_NAMES/protected_role_name comparisons work.
LEGACY_ROLE_NAMES_LOWER = {"admin", "technical", "viewer", "application admin"}


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_four_templates():
    """The 4 approved Default Company Role templates (company_id=NULL,
    is_builtin=True) - mirrors what pages/26_Default_User_Roles.py lets the
    platform owner build, and what CR-05 requires Supabase's real template
    set to contain."""
    db.init_db()
    _reset_schema()
    session = db.get_session()
    for name, description in [
        ("Company Admin", "Access to all company functionality except platform admin pages."),
        ("R&D", "R&D Manager, Engineer."),
        ("Read Only", "Read-only access to all screens."),
        ("Technical Engineer", "Can create/edit records, cannot approve their own trial closures or change commercial/admin settings."),
    ]:
        session.add(db.Role(company_id=None, name=name, description=description, is_builtin=True))
    session.commit()
    yield session
    session.close()


def test_default_templates_are_exactly_the_four_approved_roles(seeded_four_templates):
    session = seeded_four_templates
    templates = session.query(db.Role).filter(db.Role.company_id.is_(None), db.Role.is_builtin.is_(True)).all()
    names = {t.name for t in templates}
    assert names == APPROVED_DEFAULT_ROLE_NAMES
    assert not (names & {n for n in LEGACY_ROLE_NAMES_LOWER}), "no legacy literal name should survive as a template"
    for t in templates:
        assert t.name.strip().lower() not in LEGACY_ROLE_NAMES_LOWER


def test_new_company_creation_clones_exactly_the_four_approved_roles(seeded_four_templates):
    """Acceptance criterion 4/13: creating a company clones exactly the 4
    Default Company Roles - the same inheritance path
    pages/23_Companies.py's "Add company" flow calls."""
    session = seeded_four_templates
    u = uuid.uuid4().hex[:8]
    company = db.Company(name=f"CR-05 Inheritance Co {u}", is_platform_owner=False)
    session.add(company)
    session.flush()

    clone_builtin_roles_for_company(session, company.id)
    session.commit()

    clones = session.query(db.Role).filter(db.Role.company_id == company.id).all()
    clone_names = {c.name for c in clones}
    assert clone_names == APPROVED_DEFAULT_ROLE_NAMES
    assert len(clones) == 4, "exactly one clone per template, no duplicates"
    for c in clones:
        assert c.is_builtin is True


def test_platform_admin_is_excluded_from_new_company_clone(seeded_four_templates):
    """Acceptance criterion 2/13: Platform Admin must never be cloned into a
    customer company. "Platform Admin" is never a template row (it only
    ever exists as HTC's own company-scoped clone's name, per db.py's Role
    docstring) - simulate that real-world state (a company-scoped role
    literally named "Platform Admin", like HTC Global's id=4 row on
    Supabase) and prove a brand-new company's clone set still excludes it,
    because clone_builtin_roles_for_company only ever reads company_id IS
    NULL templates."""
    session = seeded_four_templates
    u = uuid.uuid4().hex[:8]

    htc = db.Company(name=f"HTC-like platform owner {u}", is_platform_owner=True)
    session.add(htc)
    session.flush()
    # HTC's own admin clone, deliberately relabeled "Platform Admin" - exactly
    # the real Supabase shape this test is guarding against leaking.
    session.add(db.Role(company_id=htc.id, name="Platform Admin", is_builtin=True))
    session.commit()

    new_company = db.Company(name=f"CR-05 Platform-Admin-Exclusion Co {u}", is_platform_owner=False)
    session.add(new_company)
    session.flush()
    clone_builtin_roles_for_company(session, new_company.id)
    session.commit()

    clone_names = {c.name for c in session.query(db.Role).filter(db.Role.company_id == new_company.id).all()}
    assert "Platform Admin" not in clone_names
    assert clone_names == APPROVED_DEFAULT_ROLE_NAMES


def test_company_role_customization_stays_isolated(seeded_four_templates):
    """Acceptance criterion 5: narrowing one company's clone must never
    affect another company's clone of the same template name - the
    2026-07-31 cross-tenant-leak fix this whole per-company-clone design
    exists for (see db.py's Role docstring), re-verified here for CR-05's
    new R&D role specifically since it's brand new."""
    session = seeded_four_templates
    u = uuid.uuid4().hex[:8]

    company_a = db.Company(name=f"CR-05 Isolation Co A {u}", is_platform_owner=False)
    company_b = db.Company(name=f"CR-05 Isolation Co B {u}", is_platform_owner=False)
    session.add_all([company_a, company_b])
    session.flush()
    clone_builtin_roles_for_company(session, company_a.id)
    clone_builtin_roles_for_company(session, company_b.id)
    session.commit()

    rd_a = session.query(db.Role).filter(db.Role.company_id == company_a.id, db.Role.name == "R&D").one()
    rd_b = session.query(db.Role).filter(db.Role.company_id == company_b.id, db.Role.name == "R&D").one()
    assert rd_a.id != rd_b.id, "each company must own its own row, not share one"

    # Narrow company A's R&D role: hide the Recipes page entirely.
    session.add(db.RolePagePermission(role_id=rd_a.id, page_key="recipes", can_view=False, can_use=False))
    session.commit()

    a_denied = {
        p.page_key for p in session.query(db.RolePagePermission).filter(db.RolePagePermission.role_id == rd_a.id).all()
    }
    b_denied = {
        p.page_key for p in session.query(db.RolePagePermission).filter(db.RolePagePermission.role_id == rd_b.id).all()
    }
    assert "recipes" in a_denied
    assert b_denied == set(), "company B's R&D clone must be untouched by company A's edit"


def test_admin_role_names_recognize_both_company_admin_and_platform_admin():
    """Acceptance criterion 1/6: the two labels that mean "the one
    administrator of this company/platform" - see access_control.py's
    ADMIN_ROLE_NAMES docstring for why there are two. Both must keep
    satisfying the same structural checks (require_role, one-admin-per-
    company) regardless of which one a given company's admin is named."""
    assert ADMIN_ROLE_NAMES == frozenset({"company admin", "platform admin"})
    assert STRUCTURALLY_REQUIRED_ROLE_NAMES == frozenset({"company admin"})
    assert protected_role_name("Company Admin") is True
    assert protected_role_name("company admin") is True
    # Only the clonable template name is protected on the Default User Roles
    # page - "Platform Admin" is never a template (see db.py's Role
    # docstring), so it is deliberately NOT in STRUCTURALLY_REQUIRED_ROLE_NAMES.
    assert protected_role_name("Platform Admin") is False


@pytest.mark.parametrize("legacy_name", ["admin", "technical", "viewer", "Application Admin"])
def test_legacy_names_are_not_protected_or_admin_equivalent_by_default(legacy_name):
    """Sanity check for the terminology sweep: none of the retired legacy
    names accidentally ended up wired into the structural role checks."""
    assert protected_role_name(legacy_name) is False
    assert legacy_name.strip().lower() not in ADMIN_ROLE_NAMES
