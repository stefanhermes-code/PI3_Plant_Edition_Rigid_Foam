"""P8-OWR-001: Rigid Foam database-session recovery verification (2026-08-19).

Charlie's Phase 8 Open Work Register v1 requires a direct check of the Rigid Foam
session lifecycle rather than an inference from the Flexible Foam handoff.

THE FLEXIBLE FAILURE MODE

Supabase sets idle_in_transaction_session_timeout to five minutes. A Streamlit
rerun that ends with a transaction still open keeps its connection checked out;
five idle minutes later the server terminates it, and the next query from that
browser tab dies on a dead socket. The Flexible side recorded 16 such
terminations in ten hours.

pool_pre_ping does not help there, and the reason is the important part: pre-ping
validates a connection at POOL CHECKOUT, and a Session sitting on an open
transaction never returns its connection to the pool, so there is no checkout to
ping.

WHY RIGID FOAM DOES NOT HAVE IT

Rigid Foam closes the transaction on every rerun, so the precondition never
holds. app_rigid_foam.py wraps its pg.run() call in try/finally and calls
db.close_out_session() from the finally block, which runs even when the routed
page raises. The connection therefore returns to the pool every rerun, which is
also what makes pool_pre_ping effective here rather than decorative.

Two further layers behind that:

  db.py sets pool_recycle=280, below Supabase's 300-second timeout, so a pooled
  connection is retired before the server would consider terminating it.

  close_out_session()'s except branch handles the case where the connection has
  already died - if commit fails AND rollback also fails, the broken Session is
  discarded from st.session_state instead of being left cached, so the next
  get_session() builds a fresh one rather than every future rerun of that tab
  failing identically until a full page reload.

These tests exercise those paths directly. No application change was required;
this file is the evidence for closing P8-OWR-001.

Usage: python -m pytest tests/test_p8_owr_001_session_recovery.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
import streamlit as st

import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRYPOINT = os.path.join(APP_DIR, "app_rigid_foam.py")
DB_SOURCE = os.path.join(APP_DIR, "db.py")

# Supabase's idle_in_transaction_session_timeout, in seconds, as recorded in the
# Flexible Foam handoff of 18 August 2026.
SUPABASE_IDLE_TIMEOUT_SECONDS = 300


@pytest.fixture()
def clean_session_state():
    db.init_db()
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    st.session_state.pop("_sa_session", None)
    yield
    st.session_state.pop("_sa_session", None)


# ---------------------------------------------------------------------------
# 1. The precondition for the Flexible failure never holds here
# ---------------------------------------------------------------------------

def test_a_read_opens_a_transaction(clean_session_state):
    """Establishes the thing that has to be closed. Under autocommit=False any
    read opens a transaction, including on a page that only displays data."""
    session = db.get_session()
    session.query(db.Company).all()

    assert session.in_transaction(), "a read must open a transaction for this check to mean anything"


def test_close_out_session_leaves_no_open_transaction(clean_session_state):
    """The core of the defence. After close_out_session the connection is no
    longer held, so it returns to the pool and pool_pre_ping can validate it on
    the next checkout."""
    session = db.get_session()
    session.query(db.Company).all()
    assert session.in_transaction()

    db.close_out_session()

    assert not session.in_transaction(), (
        "a rerun that ends with an open transaction is exactly the Flexible "
        "failure mode - the connection stays checked out and the server later "
        "terminates it"
    )


def test_close_out_session_is_safe_with_no_session_cached(clean_session_state):
    """It is called unconditionally on every rerun, including reruns that never
    touched the database."""
    st.session_state.pop("_sa_session", None)
    db.close_out_session()  # must not raise


def test_close_out_session_commits_pending_work(clean_session_state):
    """Closing out is not a rollback - a page's own writes survive it."""
    session = db.get_session()
    session.add(db.Company(name="OWR-001 Co", is_platform_owner=True))

    db.close_out_session()

    assert session.query(db.Company).filter_by(name="OWR-001 Co").count() == 1


# ---------------------------------------------------------------------------
# 2. The dead-connection recovery path
# ---------------------------------------------------------------------------

def test_a_dead_connection_discards_the_cached_session(clean_session_state, monkeypatch):
    """Simulates the server having killed the connection: commit fails, and
    rollback fails too because the socket is gone. The broken Session must not
    stay cached, or every later rerun of that tab repeats the failure until the
    user reloads the page.

    Note what is asserted. The cache key does not end up empty, because
    close_out_session logs the failure through audit_log and calls get_session()
    to do it, which builds a fresh Session and caches that. The property that
    matters is that the BROKEN Session is gone, not that the key is absent - an
    earlier version of this test asserted absence and failed against correct
    behaviour."""
    broken = db.get_session()
    broken.query(db.Company).all()

    def dead(*args, **kwargs):
        raise Exception("server closed the connection unexpectedly")

    monkeypatch.setattr(broken, "commit", dead)
    monkeypatch.setattr(broken, "rollback", dead)

    db.close_out_session()

    assert st.session_state.get("_sa_session") is not broken, (
        "a Session whose connection is dead must be discarded, not left cached"
    )


def test_a_fresh_session_is_built_after_a_discard(clean_session_state, monkeypatch):
    """The consequence that matters to the user: the next rerun works."""
    broken = db.get_session()
    broken.query(db.Company).all()

    def dead(*args, **kwargs):
        raise Exception("server closed the connection unexpectedly")

    monkeypatch.setattr(broken, "commit", dead)
    monkeypatch.setattr(broken, "rollback", dead)
    db.close_out_session()

    recovered = db.get_session()

    assert recovered is not broken, "get_session must build a new Session after a discard"
    assert recovered.query(db.Company).all() == []


def test_a_recoverable_failure_keeps_the_session(clean_session_state, monkeypatch):
    """Where rollback succeeds the connection is still usable, so the Session is
    kept rather than thrown away on every transient error."""
    session = db.get_session()
    session.query(db.Company).all()

    calls = {"rollback": 0}

    def failing_commit(*args, **kwargs):
        raise Exception("transient commit failure")

    real_rollback = session.rollback

    def counting_rollback(*args, **kwargs):
        calls["rollback"] += 1
        return real_rollback()

    monkeypatch.setattr(session, "commit", failing_commit)
    monkeypatch.setattr(session, "rollback", counting_rollback)

    db.close_out_session()

    assert calls["rollback"] == 1
    assert st.session_state.get("_sa_session") is session


# ---------------------------------------------------------------------------
# 3. Configuration and call-site guarantees
# ---------------------------------------------------------------------------

def test_pool_recycle_sits_below_the_supabase_idle_timeout():
    """A pooled connection is retired before the server would consider
    terminating it. Asserted against the source because the sqlite test path
    replaces the engine kwargs with StaticPool."""
    src = open(DB_SOURCE, encoding="utf-8").read()

    assert "pool_pre_ping=True" in src
    assert "pool_recycle=280" in src, (
        "pool_recycle must stay below Supabase's "
        f"{SUPABASE_IDLE_TIMEOUT_SECONDS}s idle_in_transaction_session_timeout"
    )
    assert 280 < SUPABASE_IDLE_TIMEOUT_SECONDS


def test_the_entrypoint_closes_out_on_every_rerun_including_failures():
    """close_out_session must run from a finally block. If it sat after pg.run()
    on the happy path only, a page raising would leave the transaction open -
    which is the Flexible failure mode reached by a different route."""
    src = open(ENTRYPOINT, encoding="utf-8").read()

    assert "close_out_session()" in src
    assert "finally:" in src

    finally_index = src.index("finally:")
    close_index = src.index("close_out_session()", finally_index)
    assert close_index > finally_index, (
        "close_out_session() must be reached from the finally block, so it runs "
        "even when the routed page raises"
    )


def test_close_out_session_documents_the_idle_transaction_case():
    """The reasoning is load-bearing and has already been lost once on this
    project. Keep it in the code, not only in a closeout document."""
    src = open(DB_SOURCE, encoding="utf-8").read()

    assert "idle-in-transaction" in src or "idle in transaction" in src
    assert "close_out_session" in src
