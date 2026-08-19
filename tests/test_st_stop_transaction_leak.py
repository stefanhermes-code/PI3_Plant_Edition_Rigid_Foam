"""st.stop() must not cost us the end-of-rerun clean-up (2026-08-19).

Origin: "st.stop() Deadlocks the Whole Browser Session", a defect note from the
Flexible Foam edition (found and fixed there at v2.12.2). The two editions share
the same navigation and session-handling design, so the note asked this edition
to check two things - whether the finally block around pg.run() releases its
lock unconditionally, and which pages call st.stop() on an ordinary render.

WHAT WAS FOUND HERE

st.stop() raises StopException and ALSO leaves Streamlit's stop flag set. Every
later st.* call re-checks that flag inside its own enqueue and re-raises -
including calls made outside the page script, from app_rigid_foam.py's own
finally block. That finally opened with an st.session_state read, so on any page
ending via st.stop() the read threw straight back out of the finally and
close_out_session() never ran.

This edition has no per-session lock (verified: no threading lock anywhere in
the source), so it never showed Flexible's headline "spins forever" symptom.
What it had instead was silent: the page's read transaction was left open with
its connection still checked out. That is precisely the idle-in-transaction
failure mode db.close_out_session()'s own docstring records as having blocked a
schema migration for eighteen hours.

The worst affected path was the login screen. auth.require_login() queries for
existing user accounts and then calls st.stop(), so EVERY render for an
unauthenticated visitor leaked a transaction - the most-visited path in the
application.

WHAT THESE TESTS PIN

test_stop_flag_makes_a_later_session_state_read_raise is the mechanism itself,
asserted against the pinned Streamlit rather than taken on trust from the note.
If a future Streamlit changes this behaviour, that test tells us why the rest of
this file suddenly looks unnecessary.

test_rendering_the_login_screen_leaves_no_open_transaction is the regression
that matters: the real application, rendered unauthenticated, must end with no
open transaction. It failed before the fix and passes after.

The rest pin the individual guards so a later refactor cannot quietly remove one
and still pass the headline test by accident.

Usage: python -m pytest tests/test_st_stop_transaction_leak.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_FILE = os.path.join(APP_DIR, "app_rigid_foam.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


# ---------------------------------------------------------------------------
# The mechanism
# ---------------------------------------------------------------------------

STOP_PROBE = '''
import streamlit as st

RESULT = {}

def page():
    st.stop()

try:
    page()
except BaseException:
    pass
finally:
    try:
        st.session_state.get("anything")
        RESULT["raised"] = False
    except BaseException as exc:
        RESULT["raised"] = True
        RESULT["type"] = type(exc).__name__

st.session_state["probe_result"] = dict(RESULT)
'''


def test_stop_flag_makes_a_later_session_state_read_raise(tmp_path):
    """After st.stop(), reading st.session_state raises - even from a finally.

    This is the whole defect in four lines. Asserted rather than assumed,
    because everything else in this file is only necessary while it holds.
    """
    probe = tmp_path / "stop_probe.py"
    probe.write_text(STOP_PROBE, encoding="utf-8")
    at = AppTest.from_file(str(probe), default_timeout=30)
    at.run()

    # The final write never lands - the re-raised StopException ends the script
    # before it - which is itself the point: nothing after the failed read runs.
    assert "probe_result" not in at.session_state


def test_stop_exception_is_not_an_ordinary_exception():
    """StopException derives from BaseException, so `except Exception` misses
    it. Any guard on this path has to catch BaseException, and this test is
    what stops someone narrowing one of them back to Exception."""
    from streamlit.runtime.scriptrunner_utils.exceptions import StopException

    assert issubclass(StopException, BaseException)
    assert not issubclass(StopException, Exception)


# ---------------------------------------------------------------------------
# The regression that matters
# ---------------------------------------------------------------------------

@pytest.fixture()
def clean_db():
    db.init_db()
    _reset_schema()
    yield


def test_rendering_the_login_screen_leaves_no_open_transaction(clean_db):
    """The real application, rendered unauthenticated.

    require_login() queries for user accounts and then st.stop()s, so this is
    the exact path that leaked before the fix. Before: in_transaction() was
    True with the connection still checked out. After: the transaction is
    closed out by app_rigid_foam.py's finally.
    """
    at = AppTest.from_file(APP_FILE, default_timeout=60)
    at.run()

    assert not at.exception, f"application raised on first render: {at.exception}"
    session = at.session_state["_sa_session"] if "_sa_session" in at.session_state else None
    assert session is not None, "expected the login render to have opened a session"
    assert session.in_transaction() is False, (
        "the login screen ended via st.stop() and left an open transaction - "
        "app_rigid_foam.py's finally is skipping close_out_session() again"
    )


def test_the_login_screen_stays_clean_across_reruns(clean_db):
    """One leaked transaction is a bug; one per rerun is the production
    incident. Renders three times and checks after each."""
    at = AppTest.from_file(APP_FILE, default_timeout=60)
    for attempt in range(3):
        at.run()
        session = at.session_state["_sa_session"] if "_sa_session" in at.session_state else None
        if session is not None:
            assert session.in_transaction() is False, f"open transaction after render {attempt + 1}"


# ---------------------------------------------------------------------------
# The individual guards
# ---------------------------------------------------------------------------

def test_close_out_session_accepts_an_explicit_session(clean_db):
    """The close-out must work without reading st.session_state at all, since
    that read is exactly what fails on a stopped page."""
    session = db.get_session()
    session.query(db.Plant).all()          # opens a read transaction
    assert session.in_transaction() is True

    db.close_out_session(session=session)
    assert session.in_transaction() is False


def test_close_out_session_with_no_argument_still_works(clean_db):
    """The explicit-session parameter is additive - existing callers that pass
    nothing must behave exactly as before."""
    session = db.get_session()
    session.query(db.Plant).all()
    assert session.in_transaction() is True

    db.close_out_session()
    assert session.in_transaction() is False


def test_safe_session_state_get_returns_the_default_instead_of_raising(monkeypatch):
    """db._safe_session_state_get is the only way the close-out path is allowed
    to read session state. It must swallow a BaseException, not just an
    Exception - see test_stop_exception_is_not_an_ordinary_exception."""
    class Exploding:
        def get(self, *args, **kwargs):
            raise BaseException("stop flag set")

    monkeypatch.setattr(st, "session_state", Exploding())
    assert db._safe_session_state_get("user_id") is None
    assert db._safe_session_state_get("user_id", "fallback") == "fallback"


def test_close_out_session_survives_an_unreadable_session_state(clean_db, monkeypatch):
    """With no session handed in and session_state unreadable, the close-out
    returns quietly rather than raising a second exception out of a finally
    block that is already unwinding one."""
    class Exploding:
        def get(self, *args, **kwargs):
            raise BaseException("stop flag set")

        def pop(self, *args, **kwargs):
            raise BaseException("stop flag set")

    monkeypatch.setattr(st, "session_state", Exploding())
    db.close_out_session()  # must not raise


# ---------------------------------------------------------------------------
# Keeping the design honest
# ---------------------------------------------------------------------------

def test_this_edition_still_has_no_page_lock():
    """Flexible Foam's headline symptom - every click spinning forever - came
    from a per-session RLock that the skipped finally never released. This
    edition has no such lock, which is why it only ever leaked transactions.

    If a lock is ever introduced here, its release must go in its own nested
    finally, and this test is the reminder to do that rather than a rule
    against locks.
    """
    import re

    lock_pattern = re.compile(r"threading\.(RLock|Lock)\s*\(|\.acquire\s*\(|\.release\s*\(")
    offenders = []
    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", "tests", "_to_delete", ".venv"}]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8", errors="replace") as handle:
                for number, line in enumerate(handle, 1):
                    if line.lstrip().startswith("#"):
                        continue
                    if lock_pattern.search(line):
                        offenders.append(f"{os.path.relpath(path, APP_DIR)}:{number}: {line.strip()}")
    assert not offenders, (
        "A lock has been introduced. Release it in its own nested finally so a "
        "page ending via st.stop() cannot deadlock the browser session:\n"
        + "\n".join(offenders)
    )
