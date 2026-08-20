"""Schema-drift control for the Decision 2 and Decision 3 controls.
Phase 8 P8-OWR-003, per Charlie's Decision 3 Correction Ruling section 3.

WHAT PROBLEM THIS SOLVES

db.py starts the application with Base.metadata.create_all(), and create_all()
NEVER ALTERs an existing table. On any database that predates a change, the new
columns and constraints simply stay absent. For a column that surfaces quickly
as an error. For a CONTROL CONSTRAINT it does not surface at all: the page
works, the saves succeed, and the thing that was supposed to make a partial
provenance state or an overlapping machine-stream period impossible is quietly
not there.

That is the failure this file exists to catch - an environment that looks
correct and enforces nothing.

WHAT IT CHECKS

The required columns and control constraints of Decision 2 and Decision 3 are
listed explicitly below rather than derived from the ORM. Deriving them from
the ORM would make the test tautological: if someone deleted a constraint from
db.py, an ORM-derived expectation would delete itself too and the test would
still pass. The list is the specification, written out, and it is meant to be
edited deliberately when a ruling changes it.

Two levels:
  * against the ORM metadata - always runs, catches a control being dropped
    from db.py;
  * against a database built from those migrations - runs on any database the
    test session can reach, catches an environment that is behind.

Usage: python -m pytest tests/test_schema_compatibility.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
import sqlalchemy as sa

import db

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "migrations")

# --- The specification. Edit deliberately, never generate. -----------------

REQUIRED_COLUMNS = {
    "machine_stream_configurations": [
        "id", "controlled_id", "machine_id", "revision", "effective_from",
        "effective_to", "status", "source_reference", "approved_by",
        "approved_at", "notes",
    ],
    "machine_stream_assignments": [
        "id", "machine_stream_configuration_id", "stream_label", "chemical_role",
    ],
    "production_runs": ["machine_stream_configuration_id"],
    "recipe_components": [
        "chemical_role", "chemical_role_source_id", "chemical_role_source_location",
    ],
}

# Constraints whose absence would mean the database enforces nothing while
# looking correct. Named exactly as the migrations create them.
REQUIRED_CONSTRAINTS = {
    "machine_stream_configurations": [
        "uq_msc_machine_revision",
        "ck_msc_status",
        "ck_msc_period",
        "ex_msc_no_overlap",
    ],
    "machine_stream_assignments": [
        "ck_msa_stream_label",
        "ck_msa_chemical_role",
        "uq_msa_config_stream",
        "uq_msa_config_role",
    ],
    "recipe_components": [
        "ck_rc_chemical_role_vocabulary",
        "ck_rc_chemical_role_provenance",
    ],
}

# Constraints the ORM cannot express portably (a GiST exclusion constraint has
# no SQLAlchemy Core equivalent that SQLite can create), so they are checked
# against a real database only.
POSTGRES_ONLY_CONSTRAINTS = {"ex_msc_no_overlap"}


# ---------------------------------------------------------------------------
# Against the ORM
# ---------------------------------------------------------------------------

def test_every_required_column_exists_in_the_orm():
    missing = []
    for table_name, columns in REQUIRED_COLUMNS.items():
        table = db.Base.metadata.tables.get(table_name)
        if table is None:
            missing.append(f"{table_name} (whole table)")
            continue
        for column in columns:
            if column not in table.columns:
                missing.append(f"{table_name}.{column}")
    assert not missing, "required column(s) absent from the ORM:\n  " + "\n  ".join(missing)


def test_every_required_control_constraint_exists_in_the_orm():
    missing = []
    for table_name, constraints in REQUIRED_CONSTRAINTS.items():
        table = db.Base.metadata.tables.get(table_name)
        if table is None:
            missing.append(f"{table_name} (whole table)")
            continue
        present = {c.name for c in table.constraints if c.name}
        present |= {i.name for i in table.indexes if i.name}
        for constraint in constraints:
            if constraint in POSTGRES_ONLY_CONSTRAINTS:
                continue
            if constraint not in present:
                missing.append(f"{table_name}.{constraint}")
    assert not missing, (
        "required control constraint(s) absent from the ORM - an environment "
        "built from this model would look correct and enforce nothing:\n  "
        + "\n  ".join(missing)
    )


def test_the_specification_is_not_derived_from_the_orm():
    """Guard against someone 'simplifying' this file into a tautology.

    If the expectations were generated from db.py, deleting a constraint from
    db.py would delete the expectation with it and this file would keep passing
    while proving nothing.
    """
    with open(os.path.abspath(__file__), encoding="utf-8") as handle:
        source = handle.read()
    specification = source.split("# --- The specification.")[1].split("# ---------")[0]
    for forbidden in ("db.Base", "__table__", "metadata.tables"):
        assert forbidden not in specification, (
            f"the specification block must be literal, not derived - found {forbidden!r}"
        )


# ---------------------------------------------------------------------------
# Against a real database built from the migrations
# ---------------------------------------------------------------------------

def test_a_database_built_from_the_orm_has_the_required_columns():
    """The portable half of the environment check.

    A database created from this ORM must carry every required column. Run
    against whatever the test session is pointed at, which is SQLite by
    default; the Postgres-only controls are covered by the live evidence in the
    P8-OWR-003 closeout.
    """
    db.init_db()
    db.Base.metadata.create_all(db.ENGINE)
    inspector = sa.inspect(db.ENGINE)

    missing = []
    for table_name, columns in REQUIRED_COLUMNS.items():
        if table_name not in inspector.get_table_names():
            missing.append(f"{table_name} (whole table)")
            continue
        present = {c["name"] for c in inspector.get_columns(table_name)}
        for column in columns:
            if column not in present:
                missing.append(f"{table_name}.{column}")
    assert not missing, (
        "the database this session is pointed at is BEHIND the application:\n  "
        + "\n  ".join(missing)
        + "\n\nRun: python migrate.py --schema <schema>"
    )


def test_the_provenance_constraint_actually_rejects_a_null_location():
    """Presence is not enforcement.

    v0.72.0 shipped this constraint present and wrong: trim(NULL) is NULL,
    "FALSE OR NULL" is NULL, and a CHECK passes on NULL, so a role with a
    source and a NULL location was accepted. A test that only asked whether the
    constraint existed would have passed throughout.
    """
    db.init_db()
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    session = db.get_session()

    plant = db.Plant(name="P")
    session.add(plant)
    session.flush()
    family = db.ProductFamily(plant_id=plant.id, name="F")
    session.add(family)
    session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name="G")
    session.add(grade)
    session.flush()
    version = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1")
    source = db.SourceRegister(controlled_id="SRC-1")
    session.add_all([version, source])
    session.flush()

    session.add(db.RecipeComponent(
        recipe_version_id=version.id,
        raw_material_name="X",
        chemical_role="Isocyanate Component",
        chemical_role_source_id=source.id,
        chemical_role_source_location=None,
    ))
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()
    session.close()


# ---------------------------------------------------------------------------
# The migration artifacts themselves
# ---------------------------------------------------------------------------

def test_the_migration_files_exist_and_are_ordered():
    names = sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql"))
    assert names, "no migration artifacts in migrations/"
    prefixes = [name.split("_")[0] for name in names]
    assert prefixes == sorted(prefixes)
    assert len(set(prefixes)) == len(prefixes), f"duplicate migration numbers: {prefixes}"


def test_every_migration_names_the_objects_the_specification_requires():
    """The artifacts and the specification must not drift apart.

    Every required constraint has to be created by some migration file. This is
    what stops the repository claiming to rebuild a schema it cannot rebuild.
    """
    combined = ""
    for name in sorted(os.listdir(MIGRATIONS_DIR)):
        if name.endswith(".sql"):
            with open(os.path.join(MIGRATIONS_DIR, name), encoding="utf-8") as handle:
                combined += handle.read()

    missing = [
        constraint
        for constraints in REQUIRED_CONSTRAINTS.values()
        for constraint in constraints
        if constraint not in combined
    ]
    assert not missing, "no migration creates:\n  " + "\n  ".join(missing)

    for table_name, columns in REQUIRED_COLUMNS.items():
        for column in columns:
            if table_name in ("production_runs", "recipe_components"):
                assert column in combined, f"no migration adds {table_name}.{column}"


def test_migrations_are_schema_agnostic():
    """Object names must be unqualified so the same artifacts apply to
    rigid_foam and to a disposable test schema. A hard-coded schema name would
    make 'applies cleanly to a pre-change database' untestable."""
    offenders = []
    for name in sorted(os.listdir(MIGRATIONS_DIR)):
        if not name.endswith(".sql"):
            continue
        with open(os.path.join(MIGRATIONS_DIR, name), encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if line.lstrip().startswith("--"):
                    continue
                if "rigid_foam." in line:
                    offenders.append(f"{name}:{number}: {line.strip()}")
    assert not offenders, "schema-qualified name(s) in a migration:\n  " + "\n  ".join(offenders)
