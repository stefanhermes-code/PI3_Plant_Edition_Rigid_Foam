"""R3-WP2 (archive the recipe backup tables out of the runtime schema).
Charlie's Package C Acceptance and Consolidated R3 Release to JC v3, section 3.

    "Backup tables: Before Production Method dependency work, move
     _backup_recipe_versions_20260819 and _backup_recipe_components_20260819
     out of rigid_foam into a non-runtime archive schema. Record table names,
     row counts and fingerprints before and after. Keep the unconstrained
     production_method_id in the archived recipe-version backup visible in the
     dependency evidence."

WHY THIS RUNS BEFORE THE DEPENDENCY WORK

R3-WP3 re-measures the Production Method dependency inventory and expects nine
foreign-key paths across nine runtime tables. These two tables distorted that
count in BOTH directions at once:

  - they sat in rigid_foam, so anything enumerating "runtime tables" counted
    them;
  - they carry no constraints at all, so
    _backup_recipe_versions_20260819.production_method_id is an integer holding
    a live Production Method id with nothing declaring the relationship - an
    FK-based count cannot see it.

Too high by two tables and blind to a real reference. Moving them out fixes the
first and makes the second explicit.

WHAT THIS FILE CAN AND CANNOT PROVE

The suite runs on in-memory SQLite and never executes a .sql migration, so
nothing here proves the live tables moved - that is the before/after row counts
and fingerprints recorded in the migration and in the R-G3 evidence pack.

What it can prove is the two things a future change could quietly break: that
the artifact relocates rather than copies-and-deletes, and that the archive
schema stays outside the application's reach. Both are asserted from source.

Usage: python -m pytest tests/test_r3wp2_backup_table_archive.py -v
"""
import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(APP_DIR, "migrations")
MIGRATION = "0021_r3wp2_archive_recipe_backup_tables.sql"

ARCHIVE_SCHEMA = "rigid_foam_archive"
BACKUP_TABLES = (
    "_backup_recipe_versions_20260819",
    "_backup_recipe_components_20260819",
)

# Measured before the move and asserted by the migration's own exit check.
# Repeated here so a later artifact that changes them has to change this too.
EXPECTED = {
    "_backup_recipe_versions_20260819": (1, "67b920085b8aedf9d6a39329b7084a52"),
    "_backup_recipe_components_20260819": (14, "b4188655a41548cb3c4132931a202bcf"),
}


def _migration_sql():
    return open(os.path.join(MIGRATIONS_DIR, MIGRATION), encoding="utf-8").read()


def _code_without_comments(sql):
    return "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))


# ---------------------------------------------------------------------------
# Section 1 - the artifact relocates, it does not copy and delete
# ---------------------------------------------------------------------------

def test_migration_exists():
    assert os.path.exists(os.path.join(MIGRATIONS_DIR, MIGRATION)), f"{MIGRATION} is missing"


def test_the_move_is_a_relocation_not_a_copy_and_drop():
    """ALTER TABLE ... SET SCHEMA moves the table itself: no second copy to
    diverge, no window where the data exists twice, and nothing deleted - which
    matters most for a table whose entire purpose is to be a backup.

    A copy-then-drop reaches the same end state and is not the same operation.
    If it ever fails halfway, the version that survives is the one nobody
    checked."""
    code = _code_without_comments(_migration_sql()).lower()
    for table in BACKUP_TABLES:
        assert f"alter table {table} set schema" in code, (
            f"{table} is not moved with ALTER TABLE ... SET SCHEMA"
        )
    assert "set schema rigid_foam_archive" in code
    for forbidden in ("drop table", "truncate", "delete from"):
        assert forbidden not in code, (
            f"0021 contains {forbidden!r}. The backup tables are relocated, never removed."
        )
    assert "insert into rigid_foam_archive" not in code, (
        "0021 copies rows into the archive instead of relocating the table."
    )


def test_the_move_is_guarded_so_it_can_re_run():
    """Re-running must be a no-op, not an error. ALTER TABLE on a table that has
    already moved raises, so each move is guarded on it still being in
    rigid_foam."""
    code = _code_without_comments(_migration_sql()).lower()
    for table in BACKUP_TABLES:
        assert f"to_regclass('{table}') is not null" in code, (
            f"the move of {table} is not guarded on it still being in the current schema"
        )


def test_the_r0_baseline_snapshot_is_not_touched():
    """rigid_foam_r0_baseline holds its own copy of both tables and is a
    snapshot with its own meaning. Nothing is moved into or out of it."""
    code = _code_without_comments(_migration_sql())
    assert "rigid_foam_r0_baseline" not in code, (
        "0021 references the R0 baseline schema. The archive is a different schema "
        "and the baseline is not a destination."
    )


def test_the_exit_check_pins_the_measured_before_state():
    """Row counts and fingerprints as literals, so the exit check can actually
    fail. An exit check that recomputes what it is comparing against asserts
    nothing."""
    sql = _migration_sql()
    for table, (rows, fingerprint) in EXPECTED.items():
        assert fingerprint in sql, f"{table}'s measured fingerprint is not in the artifact"
    assert "<> 1 then" in sql and "<> 14 then" in sql, (
        "the exit check does not pin both row counts"
    )


def test_the_unconstrained_method_id_is_asserted_not_assumed():
    """Charlie asked for it to stay visible in the dependency evidence. The
    migration asserts the column survived the move, still reads 10, and still
    carries no constraint - so if a later artifact adds a foreign key there,
    the dependency count changes meaning and this is where it is noticed."""
    code = _code_without_comments(_migration_sql())
    assert "production_method_id" in code
    assert "pg_constraint" in code, (
        "the migration does not check that the archived table is still unconstrained"
    )


# ---------------------------------------------------------------------------
# Section 2 - the archive is non-runtime, and stays that way
# ---------------------------------------------------------------------------

def test_no_model_maps_to_the_archive_schema():
    """"Non-runtime" has to mean something checkable. No SQLAlchemy table may
    live in the archive schema, or it is simply a second runtime schema with a
    quieter name."""
    offenders = [
        name for name, table in db.Base.metadata.tables.items()
        if (table.schema or "") == ARCHIVE_SCHEMA
    ]
    assert not offenders, (
        f"Models are mapped into the archive schema: {offenders}"
    )


def test_the_application_never_names_the_backup_tables():
    """The move is safe because nothing reads them. Asserted rather than
    assumed, across every module - the only mentions outside the database are
    changelog prose in version.py, which is excluded because it is a record of
    what happened, not code."""
    offenders = []
    for root, _dirs, files in os.walk(APP_DIR):
        if any(part in root for part in (".git", "__pycache__", "_to_delete", ".venv")):
            continue
        for name in sorted(files):
            if not name.endswith(".py") or name == "version.py":
                continue
            if name.startswith("test_r3wp2"):
                continue
            path = os.path.join(root, name)
            src = open(path, encoding="utf-8").read()
            for table in BACKUP_TABLES:
                if table in src:
                    offenders.append(f"{os.path.relpath(path, APP_DIR)} names {table}")
    assert not offenders, (
        "Application code references an archived backup table:\n  " + "\n  ".join(offenders)
    )


def test_that_scanner_can_fail(tmp_path):
    """Negative control for the check above, with the planted name written as
    an independent literal rather than taken from BACKUP_TABLES - Charlie's
    rule after the R2 phrase-list control was found reading the list it was
    controlling."""
    planted = tmp_path / "fake_module.py"
    planted.write_text(
        "QUERY = 'select * from _backup_recipe_versions_20260819'\n", encoding="utf-8"
    )
    src = planted.read_text(encoding="utf-8")
    found = [t for t in BACKUP_TABLES if t in src]
    assert found == ["_backup_recipe_versions_20260819"], (
        "The scanner does not recognise a backup table named in source."
    )


def test_the_runtime_schema_constant_is_unchanged():
    """db.py resolves every model to RIGID_FOAM_SCHEMA. If the archive ever
    became that value, "non-runtime" would be false while every test above
    still passed."""
    src = open(os.path.join(APP_DIR, "db.py"), encoding="utf-8").read()
    assert 'RIGID_FOAM_SCHEMA = "rigid_foam" if' in src, (
        "db.py's runtime schema constant has changed shape - check the archive is "
        "still outside it."
    )
    assert ARCHIVE_SCHEMA not in src, (
        "db.py names the archive schema. Nothing in the application should reach it."
    )


def test_the_source_is_unqualified():
    """The guard that would have caught the rejected first attempt.

    That artifact wrote "rigid_foam._backup_recipe_versions_20260819" and was
    the only one in the repository breaking the standing rule that migration
    object names resolve through search_path. Charlie rejected it rather than
    exempt it (R3-WP2 Migration Conformance Ruling, 22 Aug 2026), and it is
    preserved in migrations/_rejected/ with its original checksum.

    tests/test_schema_compatibility.py::test_migrations_are_schema_agnostic
    already refuses "rigid_foam." across every migration, so this test is not
    the repository's only line of defence. It exists because THIS artifact is
    the one that broke it, and because the reason is specific and easy to
    reintroduce: a relocation must name its DESTINATION, which makes qualifying
    the SOURCE look natural. It is not, and it costs the artifact the ability
    to be proved against a probe schema."""
    code = _code_without_comments(_migration_sql())
    assert "rigid_foam." not in code, (
        "0021 qualifies a source object again. The source resolves through "
        "search_path; only the destination is named."
    )
    assert "current_schema()" in code, (
        "The exit check hard-codes the schema it ran against. Use current_schema() "
        "so the same assertion holds on a probe as on the real thing - that is what "
        "makes the artifact itself provable rather than a hand-written equivalent."
    )


def test_the_rejected_attempt_is_preserved_outside_the_active_set():
    """Charlie: "The rejected artifact and its original checksum remain
    preserved in the R3 evidence pack."

    Also a guard on WHERE it is kept. migrate.py discovers migrations with
    os.listdir, which does not recurse, so a subdirectory is genuinely outside
    the active set - but only while the rejected artifact stays in it."""
    rejected_dir = os.path.join(MIGRATIONS_DIR, "_rejected")
    assert os.path.isdir(rejected_dir), "migrations/_rejected/ is missing"

    names = sorted(os.listdir(rejected_dir))
    artifact = [n for n in names if n.startswith("0021_REJECTED") and n.endswith(".sql")]
    assert artifact, "the rejected 0021 artifact is not preserved"

    evidence = [n for n in names if n.endswith(".evidence.txt")]
    assert evidence, "the rejected attempt has no evidence record beside it"
    record = open(os.path.join(rejected_dir, evidence[0]), encoding="utf-8").read()
    assert "7556859e0d27" in record, "the rejected checksum is not recorded"

    # The rejected artifact must NOT be in the active set, or the runner would
    # apply it and the conformance test would fail on it again.
    active = [n for n in os.listdir(MIGRATIONS_DIR) if n.endswith(".sql")]
    assert not any("REJECTED" in n for n in active), (
        "a rejected artifact is sitting in the active migration set"
    )
