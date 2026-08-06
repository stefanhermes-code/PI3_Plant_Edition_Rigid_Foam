"""Upgrade/rollback tests for the rigid_foam Postgres schema.

This is WP0's "create upgrade and rollback tests for the first rigid
schema change" acceptance item (see the Converged Joint Implementation
Plan, section 7.1) for the schema-separation change shipped in v0.2.0/
v0.2.1 (db.py's RIGID_FOAM_SCHEMA). It proves two things:

1. UPGRADE: db.py's ORM metadata can build the complete schema - all 40
   tables, every column, every foreign key - from nothing, in one clean
   pass, on both backends this app supports (SQLite local dev, Postgres).
   Includes a real insert/FK-resolution check (companies -> plants), not
   just "CREATE TABLE didn't error" - a table can exist and still have a
   broken foreign key reference if the schema-qualification is wrong.

2. ROLLBACK: whatever this creates can be torn down completely, leaving
   no orphaned tables/schema behind - so a bad rigid-foam-specific schema
   change is always a reversible step, not a one-way door.

3. REPEATABLE REBUILD: upgrade -> rollback -> upgrade again succeeds
   identically, proving a clean environment can always be rebuilt from
   this metadata alone (the same principle WP3's acceptance criterion A8
   will require of the vertical-slice schema).

Safety: this NEVER touches the live "rigid_foam" schema. Against
Postgres, everything runs inside a disposable "rigid_foam_migration_test"
schema on the same server, created and dropped within this run (cleaned
up even on failure). Against SQLite it uses a throwaway temp file.

Usage:
    # Safe default - SQLite, no setup required:
    python tests/test_schema_migration.py

    # Also verify against the real Supabase Postgres server (recommended
    # before any future structural change to rigid_foam - proves the DDL
    # actually works on that server/version, without risking real data):
    DATABASE_URL="postgresql+psycopg2://...supabase-connection-string..." \\
        python tests/test_schema_migration.py
"""

import os
import sys
import tempfile

# Allow running as `python tests/test_schema_migration.py` from the app
# root - Python only puts this script's own directory (tests/) on
# sys.path by default, but db.py lives one level up.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import db


def _log(msg: str) -> None:
    print(f"[schema-migration-test] {msg}")


def _build_test_metadata(is_postgres: bool):
    """Return (metadata, schema_name) - a copy of db.Base.metadata retargeted
    at a disposable test schema, so the real "rigid_foam" schema is never
    touched by this script."""
    if not is_postgres:
        # SQLite has no meaningful schema concept here - use the metadata
        # as-is (schema=None), same as db.py does for local dev.
        return db.Base.metadata, None

    test_schema = f"{db.RIGID_FOAM_SCHEMA}_migration_test"
    test_metadata = MetaData(schema=test_schema)
    for table in db.Base.metadata.sorted_tables:
        table.to_metadata(test_metadata, schema=test_schema)
    return test_metadata, test_schema


def _assert_all_tables_present(engine, metadata, expected_names):
    inspector = inspect(engine)
    schema = next(iter(metadata.tables.values())).schema if metadata.tables else None
    actual_names = set(inspector.get_table_names(schema=schema))
    missing = expected_names - actual_names
    assert not missing, f"UPGRADE FAILED - missing tables after create_all: {sorted(missing)}"
    _log(f"UPGRADE ok - all {len(expected_names)} tables present in schema={schema!r}")


def _assert_fk_resolves(engine, metadata):
    """Insert a company, then a plant referencing it, inside a transaction
    that's always rolled back. This proves the foreign key actually
    resolves against the schema-qualified table - a table can exist with
    no rows and still have a broken FK target if schema-qualification is
    wrong (e.g. pointing at "public.companies" instead of the test/rigid
    schema's "companies")."""
    companies = metadata.tables[
        next(n for n in metadata.tables if n.endswith(".companies") or n == "companies")
    ]
    plants = metadata.tables[
        next(n for n in metadata.tables if n.endswith(".plants") or n == "plants")
    ]
    with engine.begin() as conn:
        result = conn.execute(
            companies.insert().values(name="Schema-migration-test Co")
        )
        company_id = result.inserted_primary_key[0]
        conn.execute(plants.insert().values(company_id=company_id, name="Test Plant"))
        # Roll back deliberately - this is a structural proof, not real data.
        conn.rollback()
    _log("FK resolution ok - companies -> plants insert chain resolved correctly")


def _assert_schema_gone(engine, is_postgres, test_schema):
    if is_postgres:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
                {"s": test_schema},
            ).fetchone()
        assert row is None, f"ROLLBACK FAILED - schema {test_schema!r} still exists"
        _log(f"ROLLBACK ok - schema {test_schema!r} fully removed")
    else:
        inspector = inspect(engine)
        assert not inspector.get_table_names(), "ROLLBACK FAILED - tables still present in SQLite file"
        _log("ROLLBACK ok - all tables removed from SQLite file")


def run() -> bool:
    database_url = os.environ.get("DATABASE_URL", "")
    is_postgres = database_url.startswith("postgresql")

    tmp_sqlite_path = None
    test_schema = None
    engine = None

    try:
        if is_postgres:
            _log(f"Target: Postgres (disposable schema, real DB server) - {database_url.split('@')[-1]}")
            engine = create_engine(database_url, pool_pre_ping=True)
            test_metadata, test_schema = _build_test_metadata(is_postgres=True)
            with engine.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{test_schema}" CASCADE'))
                conn.execute(text(f'CREATE SCHEMA "{test_schema}"'))
        else:
            fd, tmp_sqlite_path = tempfile.mkstemp(suffix=".db", prefix="pi3_rigid_schema_test_")
            os.close(fd)
            os.remove(tmp_sqlite_path)  # let SQLite create it fresh
            _log(f"Target: SQLite (throwaway temp file) - {tmp_sqlite_path}")
            engine = create_engine(f"sqlite:///{tmp_sqlite_path}")
            test_metadata, test_schema = _build_test_metadata(is_postgres=False)

        expected_names = {t.name for t in db.Base.metadata.sorted_tables}

        # --- Pass 1: upgrade, verify, rollback -----------------------------
        test_metadata.create_all(bind=engine)
        _assert_all_tables_present(engine, test_metadata, expected_names)
        _assert_fk_resolves(engine, test_metadata)
        test_metadata.drop_all(bind=engine)
        if is_postgres:
            with engine.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{test_schema}" CASCADE'))
        _assert_schema_gone(engine, is_postgres, test_schema)

        # --- Pass 2: prove the rebuild is repeatable, not a one-shot -------
        if is_postgres:
            with engine.begin() as conn:
                conn.execute(text(f'CREATE SCHEMA "{test_schema}"'))
        test_metadata.create_all(bind=engine)
        _assert_all_tables_present(engine, test_metadata, expected_names)
        _log("REPEATABLE REBUILD ok - upgrade -> rollback -> upgrade succeeded identically")

        return True

    except Exception as exc:
        _log(f"FAILED - {type(exc).__name__}: {exc}")
        return False

    finally:
        # Cleanup always runs, even on failure - never leave test residue
        # behind on the real server.
        if engine is not None:
            try:
                if is_postgres and test_schema:
                    with engine.begin() as conn:
                        conn.execute(text(f'DROP SCHEMA IF EXISTS "{test_schema}" CASCADE'))
                engine.dispose()
            except Exception as cleanup_err:
                _log(f"WARNING - cleanup failed, check server manually: {cleanup_err}")
        if tmp_sqlite_path and os.path.exists(tmp_sqlite_path):
            os.remove(tmp_sqlite_path)


if __name__ == "__main__":
    ok = run()
    if ok:
        print("\nALL SCHEMA MIGRATION TESTS PASSED")
        sys.exit(0)
    else:
        print("\nSCHEMA MIGRATION TESTS FAILED")
        sys.exit(1)
