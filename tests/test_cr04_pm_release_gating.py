"""CR-04 step 6 (Charlie's "Database Reset and Clean UAT Baseline"
instruction, 2026-08-10): Production Method release-gating tests.

Covers two things this batch changed on pages/30_Production_Methods.py:

1. helpers.method_activatable_by_customer() - the pure gating rule (no DB
   access) that decides whether a customer/company user may activate a
   given Production Method: only is_released methods may be activated by
   a real customer (PM-100 only, at the Phase 1 baseline); the
   platform-owner company is exempt, since it needs to activate any
   method for its own UAT/reference content ahead of a future release
   decision.
2. The Production Methods page itself: a non-platform-owner user sees
   PM-100's checkbox enabled and a not-yet-released method's checkbox
   disabled (with an explanatory caption); a platform-owner user (the
   AUTH_DISABLED dev-bypass default, and every other smoke test in this
   suite) sees every method's checkbox enabled regardless of release
   status - unchanged from before this batch.

Also confirms the Operating Context feature CR-04 removed (the "Set as
operating context" button, and pages/31_Production_Equipment.py's
session-level default) is gone - see test_pm_hierarchy_pages_smoke.py's
own updated assertion for the page-30 half of that; this file focuses on
the release-gating behaviour that replaced it.

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


def test_released_method_activatable_by_any_user():
    released = _FakeMethod(is_released=True)
    assert method_activatable_by_customer(released, is_platform_owner=False) is True
    assert method_activatable_by_customer(released, is_platform_owner=True) is True


def test_unreleased_method_blocked_for_customer_but_not_platform_owner():
    unreleased = _FakeMethod(is_released=False)
    assert method_activatable_by_customer(unreleased, is_platform_owner=False) is False
    assert method_activatable_by_customer(unreleased, is_platform_owner=True) is True


@pytest.fixture()
def seeded_two_methods_non_platform_owner():
    """A non-platform-owner company (unlike every other PM smoke fixture in
    this suite, which uses is_platform_owner=True) with one released method
    (simulating PM-100) and one not-released method (simulating PM-200),
    neither yet activated for the plant - so the checkbox gating itself is
    what's under test, not a pre-existing activation."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR04 Gating Customer Co {u}", is_platform_owner=False)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR04 Gating Plant {u}")
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


def _run_as(company_id, is_platform_owner):
    """AUTH_DISABLED's require_login() only setdefault()s is_platform_owner
    to True, so pre-setting it False in session_state before .run() survives
    - the same technique for company_id, so this session is scoped to the
    fixture's own non-platform-owner company rather than seeing every
    company's plants (company_picker's own platform-owner-only behaviour)."""
    at = AppTest.from_file(PAGE30, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["is_platform_owner"] = is_platform_owner
    at.session_state["company_id"] = company_id
    at.run()
    return at


def test_production_methods_page_gates_unreleased_method_for_customer(seeded_two_methods_non_platform_owner):
    ids = seeded_two_methods_non_platform_owner
    at = _run_as(ids["company_id"], is_platform_owner=False)
    assert not at.exception, f"Unhandled exception loading Production Methods: {at.exception}"

    released_cb = next(
        (cb for cb in at.checkbox if cb.key == f"pm_activate_{ids['plant_id']}_{ids['released_method_id']}"), None
    )
    unreleased_cb = next(
        (cb for cb in at.checkbox if cb.key == f"pm_activate_{ids['plant_id']}_{ids['unreleased_method_id']}"), None
    )
    assert released_cb is not None, "Released method's checkbox not found"
    assert unreleased_cb is not None, "Unreleased method's checkbox not found"

    assert released_cb.disabled is False, "A customer should be able to activate the released method (PM-100)"
    assert unreleased_cb.disabled is True, "A customer should NOT be able to activate an unreleased method"

    assert any(
        "Not yet released for customer activation" in c.value for c in at.caption
    ), "Expected an explanatory caption on the gated, unreleased method"


def test_production_methods_page_lets_platform_owner_activate_unreleased_method(seeded_two_methods_non_platform_owner):
    """Same fixture's methods, but read as the platform-owner tenant (the
    exemption) - both checkboxes should be enabled, matching every other PM
    smoke test in this suite that runs under AUTH_DISABLED's default
    is_platform_owner=True."""
    ids = seeded_two_methods_non_platform_owner
    at = _run_as(ids["company_id"], is_platform_owner=True)
    assert not at.exception, f"Unhandled exception loading Production Methods: {at.exception}"

    unreleased_cb = next(
        (cb for cb in at.checkbox if cb.key == f"pm_activate_{ids['plant_id']}_{ids['unreleased_method_id']}"), None
    )
    assert unreleased_cb is not None, "Unreleased method's checkbox not found"
    assert unreleased_cb.disabled is False, (
        "The platform-owner company should be exempt from the release gate"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
