"""Regression test for a real production incident (2026-08-09, v0.16.0 hotfix
-> v0.16.1): the Production Method Hierarchy batch added
FoamGrade<->Machine's many-to-many relationship using
`relationship(..., secondary="foam_grade_machines")` (a bare string). Every
test in this repo runs against SQLite (DATABASE_URL unset or "sqlite://"),
where db.py's RIGID_FOAM_SCHEMA is None and Base.metadata has no schema, so
the table's key in Base.metadata.tables is the plain "foam_grade_machines"
- the string resolved fine and every local py_compile / configure_mappers()
/ pytest check passed cleanly before release.

Against the real Supabase Postgres server, though, db.py sets
Base.metadata's own `schema` to RIGID_FOAM_SCHEMA ("rigid_foam"), which
changes that same table's key to "rigid_foam.foam_grade_machines" - so the
bare string secondary="foam_grade_machines" no longer resolves, and the
very first ORM query of the request (SQLAlchemy configures every mapper
lazily, on first use) raised:

    InvalidRequestError: ... expression 'foam_grade_machines' failed to
    locate a name ("name 'foam_grade_machines' is not defined")

This crashed every single page in production. The fix (see db.py's
foam_grade_machines Table definition, moved above Machine/FoamGrade) was
to pass the Table object directly as `secondary=foam_grade_machines`
instead of a string, which sidesteps name resolution regardless of
whether Base.metadata has a schema set.

This test exists because no other test in this suite exercises db.py
under a schema-qualified Base.metadata - test_schema_migration.py (WP0
Gate 0) proves raw DDL/FK correctness against a disposable Postgres
schema, but never calls SQLAlchemy's ORM configure_mappers() or runs an
ORM query, so it could not have caught a relationship string-resolution
bug like this one. Runs db.py's import in a fresh subprocess (not the
current process) with DATABASE_URL set to a postgresql:// URL, so
RIGID_FOAM_SCHEMA actually resolves to "rigid_foam" - db.py's own
create_engine() call does not need to actually connect for
configure_mappers() to succeed or fail, since mapper configuration only
inspects metadata/relationships, never issues SQL.

Usage: python -m pytest tests/test_orm_configure_under_schema_qualified_metadata.py
"""
import os
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CHECK_SCRIPT = """
import db
assert db.RIGID_FOAM_SCHEMA == "rigid_foam", (
    f"expected RIGID_FOAM_SCHEMA to be schema-qualified under a postgresql:// "
    f"DATABASE_URL, got {db.RIGID_FOAM_SCHEMA!r} - this test's premise (reproducing "
    f"the production schema-qualified metadata scenario) did not hold"
)
keys = [k for k in db.Base.metadata.tables.keys() if "foam_grade_machines" in k]
assert keys == ["rigid_foam.foam_grade_machines"], (
    f"expected the schema-qualified key, got {keys!r}"
)
from sqlalchemy.orm import configure_mappers
configure_mappers()
print("OK")
"""


def test_configure_mappers_succeeds_under_schema_qualified_metadata():
    env = dict(os.environ)
    env["DATABASE_URL"] = "postgresql://fake:fake@localhost/fakedb"
    result = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        cwd=APP_DIR, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, (
        f"db.py failed to configure ORM mappers under schema-qualified metadata "
        f"(the exact production failure mode this test guards against):\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "OK" in result.stdout


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
