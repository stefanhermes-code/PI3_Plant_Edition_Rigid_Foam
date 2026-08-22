"""R3 - the Application Area snapshot on a production run (migration 0023).

Charlie's R3 handover v3, section 3: "The authorised one-time migration may
backfill the controlled Application Area and Production Unit snapshot fields.
Record row-by-row before/after evidence and prove every other completed-run
field is unchanged." And the R-G3 exit condition: "each completed run retains a
row-by-row verified frozen Application Area."

WHY THIS EXISTS BEFORE THE APPLICABILITY MIGRATION

Process-setting applicability is about to resolve through Application Area as
its default tier. Without this column a run's Application Area would be read
live through foam_grades.application_id, which is the derivation migration 0022
removed for the Production Unit / Cell. Re-classify a Product Grade and every
finished run would start resolving a different rule set than the one it ran
under - and nothing would fail.

The tests are deliberately the same shape as
tests/test_r3wp4_production_run_unit_snapshot.py, including the one that
matters most: a test that moves the source and asserts the run does not follow.

Usage: python -m pytest tests/test_r3_production_run_application_snapshot.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
from migration_sql_helpers import set_targets as _set_targets

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(APP_DIR, "migrations")
MIGRATION = "0023_r3_production_run_application_area_snapshot.sql"


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def _migration_code():
    sql = open(os.path.join(MIGRATIONS_DIR, MIGRATION), encoding="utf-8").read()
    return "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))


@pytest.fixture()
def chain():
    """One classified grade with a run on it, and one UNCLASSIFIED grade with a
    run on it. The second is the case live data does not have - every live grade
    carries an Application Area - and without it the "nothing was invented"
    assertions could never fail."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"APP Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"APP Plant {u}")
    session.add(plant); session.flush()

    area = db.Application(controlled_id=f"APP-{u[:3]}", name=f"Cold-room {u}",
                          pu_material_family="Rigid")
    other = db.Application(controlled_id=f"APX-{u[:3]}", name=f"Somewhere Else {u}",
                           pu_material_family="Rigid")
    session.add_all([area, other]); session.flush()

    family = db.PUMaterialFamily(plant_id=plant.id, name=f"APP Family {u}")
    session.add(family); session.flush()

    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"APP Grade {u}",
                         application_id=area.id)
    unclassified = db.FoamGrade(pu_material_family_id=family.id,
                                grade_name=f"APP Unclassified {u}", application_id=None)
    session.add_all([grade, unclassified]); session.flush()

    ids = {"company_id": company.id, "plant_id": plant.id, "area_id": area.id,
           "other_area_id": other.id, "grade_id": grade.id,
           "unclassified_grade_id": unclassified.id, "runs": {}}

    for label, g in (("classified", grade), ("unclassified", unclassified)):
        recipe = db.RecipeVersion(foam_grade_id=g.id, version_label="v1",
                                  approval_status="Approved", is_active=True)
        session.add(recipe); session.flush()
        run = db.ProductionRun(
            plant_id=plant.id, foam_grade_id=g.id, recipe_version_id=recipe.id,
            run_date=dt.date(2026, 8, 1), batch_reference=f"B-{label}-{u}",
            application_id=g.application_id,
        )
        session.add(run); session.flush()
        ids["runs"][label] = run.id

    session.commit(); session.close()
    return ids


# ---------------------------------------------------------------------------
# Section 0 - the fixture is what it claims to be
# ---------------------------------------------------------------------------

def test_the_fixture_has_one_classified_and_one_unclassified_run(chain):
    session = db.get_session()
    classified = session.get(db.ProductionRun, chain["runs"]["classified"])
    unclassified = session.get(db.ProductionRun, chain["runs"]["unclassified"])
    assert classified.application_id == chain["area_id"]
    assert unclassified.application_id is None, (
        "The unclassified run carries an Application Area, so it does not exercise "
        "the case the migration leaves alone."
    )
    session.close()


# ---------------------------------------------------------------------------
# Section 1 - the artifact
# ---------------------------------------------------------------------------

def test_migration_exists():
    assert os.path.exists(os.path.join(MIGRATIONS_DIR, MIGRATION)), f"{MIGRATION} is missing"


def test_migration_adds_the_column_idempotently():
    code = " ".join(_migration_code().lower().split())
    assert "add column if not exists application_id" in code, (
        "The column must be added with IF NOT EXISTS - the artifact is proved on a "
        "disposable schema and then applied live, so it runs more than once."
    )


def test_the_backfill_writes_only_the_snapshot_column():
    code = _migration_code()
    updates = [l for l in code.splitlines() if l.strip().lower().startswith("set ")]
    assert updates, "No SET clause found - has the backfill been removed?"
    for clause in updates:
        assert _set_targets(clause) == ["application_id"], (
            f"The backfill writes more than the snapshot column: {_set_targets(clause)}"
        )


def test_the_backfill_only_reads_the_runs_own_grade():
    """The source must be foam_grades joined on the run's own foam_grade_id.
    Any other source - the plant's grades, the machine's grades - would assign
    an Application Area the run did not actually run under."""
    code = " ".join(_migration_code().lower().split())
    assert "from foam_grades g where g.id = r.foam_grade_id" in code, (
        "The backfill does not read the run's own Product Grade."
    )


def test_the_fk_existence_check_is_scoped_to_the_current_schema():
    """Unscoped, the guard finds the LIVE constraint while running on a probe
    and skips creating the probe's own - so the probe proves a migration that is
    not the one live gets. Found and fixed in 0022; kept fixed here."""
    code = " ".join(_migration_code().lower().split())
    assert "relnamespace = current_schema()::regnamespace" in code


def test_the_migration_is_schema_agnostic():
    for line in _migration_code().splitlines():
        assert "rigid_foam." not in line, (
            f"Migration hard-codes a schema name: {line.strip()!r}."
        )


def test_the_migration_never_writes_status_or_the_unit_snapshot():
    code = _migration_code().lower()
    assert "set status" not in code
    assert "production_unit_id" not in code, (
        "0023 is the Application Area snapshot. Touching the unit snapshot here would "
        "put two backfills behind one piece of evidence."
    )


# ---------------------------------------------------------------------------
# Section 2 - the model
# ---------------------------------------------------------------------------

def test_production_runs_carries_the_application_snapshot():
    cols = {c.name: c for c in db.ProductionRun.__table__.columns}
    assert "application_id" in cols, "production_runs.application_id is missing"
    col = cols["application_id"]
    assert col.nullable, (
        "Nullable on purpose - a Product Grade may be unclassified while master data "
        "is being set up, and nothing is guessed for such a run."
    )
    assert {fk.target_fullname for fk in col.foreign_keys} == {"applications.id"}


# ---------------------------------------------------------------------------
# Section 3 - the snapshot does not follow its source
#
# The test that carries the work package. Everything above would pass just as
# happily against an implementation that read foam_grade.application_id live.
# ---------------------------------------------------------------------------

def test_reclassifying_the_grade_does_not_move_a_recorded_run(chain):
    session = db.get_session()
    grade = session.get(db.FoamGrade, chain["grade_id"])
    grade.application_id = chain["other_area_id"]
    session.commit()

    run = session.get(db.ProductionRun, chain["runs"]["classified"])
    assert run.application_id == chain["area_id"], (
        "Re-classifying the Product Grade moved the Application Area recorded on a run "
        "that had already happened. The snapshot is being derived, not stored."
    )
    assert run.application.controlled_id != session.get(
        db.Application, chain["other_area_id"]).controlled_id
    session.close()


def test_the_relationship_reads_the_stored_column(chain):
    session = db.get_session()
    run = session.get(db.ProductionRun, chain["runs"]["classified"])
    assert run.application is not None
    assert run.application.id == chain["area_id"]
    session.close()


def test_an_unclassified_grade_leaves_the_run_with_no_area(chain):
    session = db.get_session()
    run = session.get(db.ProductionRun, chain["runs"]["unclassified"])
    assert run.application_id is None
    assert run.application is None, (
        "A run on an unclassified grade must show nothing rather than a stand-in - the "
        "gap is what tells the user to go and classify the grade."
    )
    session.close()
