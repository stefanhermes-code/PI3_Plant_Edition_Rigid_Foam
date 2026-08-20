"""Control for R-PRE-WP3, the PTU QC controlled-property additions.
Redesign Migration Plan v3, Package A.

WHAT PROBLEM THIS SOLVES

Migration 0004 adds two rows to a controlled master. Nothing in db.py changes,
so no ORM-derived check can see it, and nothing in the application will fail if
the rows are wrong - a property with the wrong scope, or a third row created for
end-of-rise time, would simply sit in the master looking legitimate.

The specification below is therefore written out LITERALLY rather than read back
from the migration or from the database. Reading it back would make the test
tautological: edit the migration and an ORM- or file-derived expectation edits
itself with it. This list is the ruling, transcribed, and it is meant to be
changed deliberately when the ruling changes.

WHAT IT CHECKS

  * exactly two definitions are inserted, and which two;
  * end-of-rise time is MAPPED to PROP-050 and NOT inserted - the single most
    likely way to get this wrong is to create a third record for it;
  * viscosity carries no default UOM, because the controlled UOM master has no
    viscosity unit and inventing one outside the master is what the UOM
    reconciliation ruling forbids;
  * both rows are marked provisional, so they cannot be mistaken for complete
    while their provenance is still outstanding;
  * the file contains no DDL - R-PRE is a controlled-data change;
  * each insert is individually guarded, so the migration is re-runnable;
  * the sequence guard is present. Without it the insert fails outright on any
    database whose id sequence sits behind max(id) - proven by mutation against
    a disposable schema on 20 August 2026, where removing the guard produced
    "duplicate key value violates unique constraint".

Usage: python -m pytest tests/test_rpre_ptu_qc_property_additions.py -v
"""
import os
import re

MIGRATION = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "migrations",
    "0004_rpre_ptu_qc_controlled_property_additions.sql",
)

# --- the specification, written out ---------------------------------------

INSERTED = {
    "PROP-058": {"name": "Specific gravity", "default_uom": "'ratio'"},
    "PROP-059": {"name": "Viscosity", "default_uom": None},
}

# Colin's QC list maps onto records that already exist. None of these may be
# created by this migration.
MAPPED_TO_EXISTING = {
    "free-rise density": "PROP-003",
    "cream time": "PROP-047",
    "start time": "PROP-057",
    "gel time": "PROP-048",
    "tack-free time": "PROP-049",
    "end-of-rise time": "PROP-050",
}

PROVISIONAL = "Provisional - pending PTU documentation"


def _sql():
    with open(MIGRATION, encoding="utf-8") as handle:
        return handle.read()


def _statements():
    """The executable statements, with comment lines removed."""
    body = "\n".join(
        line for line in _sql().splitlines() if not line.lstrip().startswith("--")
    )
    return [s.strip() for s in body.split(";") if s.strip()]


def test_migration_file_exists():
    assert os.path.exists(MIGRATION)


def test_contains_no_ddl():
    """R-PRE-WP3 is a controlled-data change. Any DDL here means the work
    package has quietly grown into a schema change."""
    for statement in _statements():
        lowered = statement.lower()
        for keyword in ("create table", "alter table", "drop table", "create index",
                        "add constraint", "drop constraint", "add column", "drop column"):
            assert keyword not in lowered, f"unexpected DDL {keyword!r} in: {statement[:80]}"


def test_inserts_exactly_two_definitions():
    inserts = [s for s in _statements() if s.lower().startswith("insert into physical_property_definitions")]
    assert len(inserts) == len(INSERTED) == 2


def test_each_inserted_definition_is_the_specified_one():
    sql = _sql()
    for controlled_id, spec in INSERTED.items():
        assert f"'{controlled_id}'" in sql, f"{controlled_id} is not inserted"
        assert f"'{spec['name']}'" in sql, f"{controlled_id} does not carry name {spec['name']!r}"


def test_end_of_rise_is_mapped_not_created():
    """PROP-050 "Rise time" already exists. Creating a second record for
    end-of-rise time would give the master two rows for one property."""
    for statement in _statements():
        if statement.lower().startswith("insert into physical_property_definitions"):
            assert "'PROP-050'" not in statement
            assert "'Rise time'" not in statement
            assert "end-of-rise" not in statement.lower()


def test_no_existing_controlled_property_is_recreated():
    for _label, controlled_id in MAPPED_TO_EXISTING.items():
        for statement in _statements():
            if statement.lower().startswith("insert into physical_property_definitions"):
                assert f"'{controlled_id}'" not in statement, (
                    f"{controlled_id} already exists in the master and must not be inserted"
                )


def test_specific_gravity_uses_the_controlled_ratio_unit():
    """"ratio" is UOM-021 in the controlled UOM master. Specific gravity is
    dimensionless, so it has a legitimate controlled unit and must use it."""
    statement = _insert_for("PROP-058")
    assert "'ratio'" in statement


def test_viscosity_has_no_default_uom():
    """When 0004 was written the controlled UOM master had no viscosity
    quantity type at all - no cP, no mPa.s, no Pa.s (43 records across 30
    quantity types, checked 20 August 2026). Supplying a unit here would have
    created an uncontrolled one, which is the failure the UOM reconciliation
    ruling exists to prevent, and Plan v3 R-PRE-WP3 explicitly allows a unit
    to remain unset.

    Migration 0006 has since added the viscosity units and set cP as the
    property's default. This assertion still stands and is deliberately not
    relaxed: 0004 is an artifact the ledger has checksummed, it must keep
    describing what was applied, and the default now comes from 0006. See
    tests/test_rpre_viscosity_uom_conversion.py for the standard itself."""
    statement = _insert_for("PROP-059")
    for bad in ("'mPa.s'", "'mPa*s'", "'cP'", "'Pa.s'", "'cSt'", "'mm2/s'"):
        assert bad not in statement, f"viscosity must not carry an uncontrolled unit {bad}"


def test_both_rows_are_marked_provisional():
    """56 of the 57 pre-existing definitions carry source provenance. These two
    cannot until PTU's documentation arrives, so they must say so rather than
    sit in the master looking finished."""
    for controlled_id in INSERTED:
        statement = _insert_for(controlled_id)
        assert f"'{PROVISIONAL}'" in statement
        assert "source_ids" in statement


def test_each_insert_is_individually_guarded():
    """Re-runnable: the runner's ledger is a convenience, not the thing
    correctness depends on."""
    for controlled_id in INSERTED:
        statement = _insert_for(controlled_id)
        guard = statement.lower()
        assert "where not exists" in guard
        assert f"controlled_id = '{controlled_id}'".lower() in guard


def test_sequence_guard_is_present_and_runs_before_the_inserts():
    statements = _statements()
    setvals = [i for i, s in enumerate(statements) if s.lower().startswith("select setval")]
    inserts = [i for i, s in enumerate(statements)
               if s.lower().startswith("insert into physical_property_definitions")]
    assert setvals, "the sequence guard is missing"
    assert min(setvals) < min(inserts), "the sequence guard must run before the inserts"
    assert "pg_get_serial_sequence" in statements[setvals[0]]


def test_object_names_are_unqualified():
    """Migration convention since P8-OWR-003: the runner sets search_path, so
    the same artifact can be replayed against a disposable schema."""
    assert "rigid_foam." not in _sql()


def _insert_for(controlled_id):
    for statement in _statements():
        if (statement.lower().startswith("insert into physical_property_definitions")
                and f"'{controlled_id}'" in statement):
            return statement
    raise AssertionError(f"no insert found for {controlled_id}")
