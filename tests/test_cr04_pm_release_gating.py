"""Production Method release-gating tests.

Originally CR-04 step 6 (Charlie's "Database Reset and Clean UAT Baseline"
instruction, 2026-08-10), which introduced the gate but exempted the
platform-owner company from it. CR-06 (Production Method Release-Gate
Enforcement and Platform-Owner Bypass Removal, 2026-08-11) removed that
exemption entirely after a UAT finding showed a Platform Admin could
activate unreleased Production Methods (PM-200/PM-300) for both HTC Global
and a customer plant - see helpers.method_activatable_by_customer's
docstring for the full history. This file's tests were rewritten in place
for CR-06 rather than left as a stale record of the since-reversed CR-04
behavior; the file name is kept for git history continuity.

Covers two things:

1. helpers.method_activatable_by_customer() - the pure gating rule (no DB
   access, and as of CR-06 no role/company parameter at all) that decides
   whether a Production Method may be activated for ANY plant: only
   is_released methods may be activated (PM-100 only, at the Phase 1
   baseline) - by anyone, including HTC Global's own Platform Admin.
2. The Production Methods page itself: every checkbox for an unreleased
   method is disabled with an explanatory caption, regardless of whether
   the viewing session is a non-platform-owner Company Admin on their own
   plant, a Platform Admin on the platform-owner company's own plant, or a
   Platform Admin viewing a customer company's plant (the exact UAT
   scenario CR-06 fixes).

Also confirms the Operating Context feature CR-04 removed (the "Set as
operating context" button, and pages/31_Production_Equipment.py's
session-level default) is gone - see test_pm_hierarchy_pages_smoke.py's
own updated assertion for the page-30 half of that; this file focuses on
the release-gating behaviour.

Usage: python -m pytest tests/test_cr04_pm_release_gating.py
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import db
from helpers import method_activatable_by_customer

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE30 = os.path.join(APP_DIR, "pages", "30_Production_Methods.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


class _FakeMethod:
    """Stand-in for a ProductionMethod row - method_activatable_by_customer
    only reads .is_released, so no DB/session is needed for this half."""

    def __init__(self, is_released):
        self.is_released = is_released


def test_released_method_is_activatable():
    assert method_activatable_by_customer(_FakeMethod(is_released=True)) is True


def test_unreleased_method_is_never_activatable():
    assert method_activatable_by_customer(_FakeMethod(is_released=False)) is False


def test_activatable_check_takes_no_role_parameter_at_all():
    """CR-06 regression guard: the is_platform_owner bypass parameter this
    function had under CR-04 must be REMOVED, not merely ignored/defaulted
    off - a caller passing one (accidentally reintroducing the bypass
    upstream) should get a hard TypeError, not a silently-accepted no-op
    argument."""
    with pytest.raises(TypeError):
        method_activatable_by_customer(_FakeMethod(is_released=False), True)


def _seed_company_with_two_methods(is_platform_owner, label):
    """One company (either a real customer or a platform-owner-flagged
    company like HTC Global) with one plant and the same two Production
    Methods every fixture in this file uses: one released (simulating
    PM-100), one not (simulating PM-200), neither yet activated."""
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR06 {label} Co {u}", is_platform_owner=is_platform_owner)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR06 {label} Plant {u}")
    session.add(plant); session.flush()

    released_method = db.ProductionMethod(
        controlled_id=f"PM-100-{u}", name="Discontinuous Factory Foaming",
        maturity_status="Released", is_released=True,
    )
    unreleased_method = db.ProductionMethod(
        controlled_id=f"PM-200-{u}", name="Continuous Panel & Board Production",
        maturity_status="Defined / planned", is_released=False,
    )
    session.add_all([released_method, unreleased_method]); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "released_method_id": released_method.id, "released_method_name": released_method.name,
        "unreleased_method_id": unreleased_method.id, "unreleased_method_name": unreleased_method.name,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_customer_company():
    """A non-platform-owner ("Company Admin") company/plant."""
    db.init_db()
    _reset_schema()
    return _seed_company_with_two_methods(is_platform_owner=False, label="Customer")


@pytest.fixture()
def seeded_platform_owner_company():
    """A platform-owner ("Platform Admin", e.g. HTC Global) company/plant -
    the exact tenant CR-04 used to exempt from this gate."""
    db.init_db()
    _reset_schema()
    return _seed_company_with_two_methods(is_platform_owner=True, label="PlatformOwner")


def _run_as(company_id, is_platform_owner):
    """AUTH_DISABLED's require_login() only setdefault()s is_platform_owner
    to True, so pre-setting it False in session_state before .run() survives
    - the same technique for company_id, so this session is scoped to the
    fixture's own company rather than seeing every company's plants
    (company_picker's own platform-owner-only behaviour)."""
    at = AppTest.from_file(PAGE30, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["is_platform_owner"] = is_platform_owner
    at.session_state["company_id"] = company_id
    at.run()
    return at


def _assert_unreleased_gated_and_released_open(at, ids):
    assert not at.exception, f"Unhandled exception loading Production Methods: {at.exception}"
    released_cb = next(
        (cb for cb in at.checkbox if cb.key == f"pm_activate_{ids['plant_id']}_{ids['released_method_id']}"), None
    )
    unreleased_cb = next(
        (cb for cb in at.checkbox if cb.key == f"pm_activate_{ids['plant_id']}_{ids['unreleased_method_id']}"), None
    )
    assert released_cb is not None, "Released method's checkbox not found"
    assert unreleased_cb is not None, "Unreleased method's checkbox not found"
    assert released_cb.disabled is False, "PM-100 (released) must stay activatable"
    assert unreleased_cb.disabled is True, "An unreleased method must never be activatable, for any role"
    assert any(
        "Not yet released for customer activation" in c.value for c in at.caption
    ), "Expected an explanatory caption on the gated, unreleased method"


def test_company_admin_is_gated_on_their_own_customer_plant(seeded_customer_company):
    """Baseline case, unchanged by CR-06: a non-platform-owner (Company
    Admin) user on their own company's plant."""
    ids = seeded_customer_company
    at = _run_as(ids["company_id"], is_platform_owner=False)
    _assert_unreleased_gated_and_released_open(at, ids)


def test_platform_admin_is_gated_on_the_platform_owner_companys_own_plant(seeded_platform_owner_company):
    """CR-06's core regression guard: a Platform Admin viewing HTC Global's
    OWN plant no longer gets the CR-04 exemption - PM-200 stays disabled
    here exactly like it does for a customer."""
    ids = seeded_platform_owner_company
    at = _run_as(ids["company_id"], is_platform_owner=True)
    _assert_unreleased_gated_and_released_open(at, ids)


def test_platform_admin_is_gated_when_viewing_a_customer_companys_plant(seeded_customer_company):
    """The exact UAT scenario CR-06 was opened for: a Platform-Admin-scoped
    session (is_platform_owner=True) administering a CUSTOMER company's
    plant, not the platform owner's own. Only one company exists in this
    fixture, so tenant_scope.company_picker's own platform-owner branch
    auto-locks to it (no selectbox interaction needed) - this session is
    genuinely "Platform Admin looking at someone else's plant," matching
    Charlie's finding precisely."""
    ids = seeded_customer_company
    at = _run_as(ids["company_id"], is_platform_owner=True)
    _assert_unreleased_gated_and_released_open(at, ids)


def test_later_releasing_a_method_makes_it_activatable_for_every_role(seeded_customer_company):
    """Acceptance criterion 6: changing a Production Method to released
    status makes it eligible for activation with no role-specific
    exception needed - proven here by flipping is_released on the same
    method the two gating tests above found disabled, then re-running as
    both a Company Admin and a Platform Admin."""
    ids = seeded_customer_company
    session = db.get_session()
    method = session.query(db.ProductionMethod).filter(db.ProductionMethod.id == ids["unreleased_method_id"]).one()
    method.is_released = True
    session.commit()
    session.close()

    for is_platform_owner in (False, True):
        at = _run_as(ids["company_id"], is_platform_owner=is_platform_owner)
        assert not at.exception
        now_released_cb = next(
            (cb for cb in at.checkbox if cb.key == f"pm_activate_{ids['plant_id']}_{ids['unreleased_method_id']}"),
            None,
        )
        assert now_released_cb is not None
        assert now_released_cb.disabled is False, (
            f"A newly-released method must become activatable (is_platform_owner={is_platform_owner})"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
