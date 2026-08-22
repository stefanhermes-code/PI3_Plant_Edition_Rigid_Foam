"""R3 - continuous versus shot-by-shot at Production Unit / Cell level
(migration 0025).

Charlie's R3 handover v3, section 3: "Production Unit properties: Capture
continuous versus shot-by-shot at Production Unit / Cell level as specified in
Migration Plan v5. Equipment remains linked to the relevant unit."

WHAT THIS PROPERTY JOINED

The application already answered "does this run capture Cycle / Shot data",
from ProductionMethod.uses_cycle_shot_operation with
Machine.cycle_shot_operation_override on top. That override's own comment says
what it was standing in for: "a plant running the same Production Method on one
cycle/shot cell and one continuous cell". Cell. The property always belonged to
the unit and there was nowhere to put it, so every such plant had to state it
per machine instead.

So this is a middle tier, not a new mechanism:

    Machine override  >  Production Unit / Cell  >  Production Method default

TWO THINGS THAT ARE EASY TO GET WRONG AND ARE TESTED HERE

The unit must come from the RUN'S OWN SNAPSHOT, not from run.machine's current
unit. Reading it through the machine means re-assigning equipment to another
cell retroactively changes which modules a finished run offers - the derivation
migration 0022 exists to prevent.

And an uncharacterised unit must FALL THROUGH rather than answer "continuous".
A two-valued read of a three-valued property is the same mistake as treating a
NULL boolean as False, and it would silently switch off Cycle / Shot capture
for every method that had it on.

Usage: python -m pytest tests/test_r3_production_unit_operation_mode.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
import helpers

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(APP_DIR, "migrations")
MIGRATION = "0025_r3_production_unit_operation_mode.sql"


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def _migration_code():
    sql = open(os.path.join(MIGRATIONS_DIR, MIGRATION), encoding="utf-8").read()
    return "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))


@pytest.fixture()
def run_chain():
    """A run whose Production Method says CONTINUOUS (uses_cycle_shot_operation
    False), on a machine with no override, in a unit that starts uncharacterised.

    The method default is False on purpose: every assertion below then reads as
    "the unit changed the answer" rather than "the answer happened to already
    be that". A fixture whose tiers all agree cannot show which one won."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"MODE Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"MODE Plant {u}")
    session.add(plant); session.flush()
    unit = db.ProductionUnit(plant_id=plant.id, controlled_id=f"PU-{u[:3]}",
                             name=f"Line {u}", operation_mode=None)
    other_unit = db.ProductionUnit(plant_id=plant.id, controlled_id=f"PX-{u[:3]}",
                                   name=f"Other Line {u}", operation_mode="Shot-by-shot")
    session.add_all([unit, other_unit]); session.flush()
    method = db.ProductionMethod(controlled_id=f"PM-{u[:3]}", name=f"Method {u}",
                                 uses_cycle_shot_operation=False)
    session.add(method); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"Machine {u}",
                         production_method_id=method.id, production_unit_id=unit.id,
                         cycle_shot_operation_override=None)
    session.add(machine); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"MODE Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"MODE Grade {u}")
    session.add(grade); session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1",
                              approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference=f"B-MODE-{u}",
        machine_id=machine.id, production_unit_id=unit.id,
        production_method_id=method.id,
    )
    session.add(run); session.commit()

    ids = {"plant_id": plant.id, "unit_id": unit.id, "other_unit_id": other_unit.id,
           "method_id": method.id, "machine_id": machine.id, "run_id": run.id}
    session.close()
    return ids


def _resolve(session, run_id):
    return helpers.run_uses_cycle_shot_operation(session.get(db.ProductionRun, run_id))


# ---------------------------------------------------------------------------
# Section 0 - the fixture's tiers disagree, so precedence is observable
# ---------------------------------------------------------------------------

def test_the_fixture_starts_with_the_method_answering_and_nothing_else(run_chain):
    session = db.get_session()
    run = session.get(db.ProductionRun, run_chain["run_id"])
    assert run.production_method.uses_cycle_shot_operation is False
    assert run.machine.cycle_shot_operation_override is None
    assert run.production_unit.operation_mode is None, (
        "The unit starts characterised, so the tests below would not show it winning."
    )
    session.close()


# ---------------------------------------------------------------------------
# Section 1 - the resolution order
# ---------------------------------------------------------------------------

def test_an_uncharacterised_unit_falls_through_to_the_method(run_chain):
    """The tier that must say nothing rather than say False."""
    session = db.get_session()
    assert _resolve(session, run_chain["run_id"]) is False
    session.close()


def test_the_unit_overrides_the_method(run_chain):
    session = db.get_session()
    session.get(db.ProductionUnit, run_chain["unit_id"]).operation_mode = "Shot-by-shot"
    session.commit()
    assert _resolve(session, run_chain["run_id"]) is True, (
        "A shot-by-shot unit did not turn Cycle / Shot capture on for a run in it."
    )
    session.close()


def test_the_unit_can_also_turn_it_off(run_chain):
    """Both directions. A tier that can only switch a feature ON is not an
    override, and a method flagged shot-by-shot with one continuous line is
    precisely the case Charlie's machine override was written for."""
    session = db.get_session()
    session.get(db.ProductionMethod, run_chain["method_id"]).uses_cycle_shot_operation = True
    session.get(db.ProductionUnit, run_chain["unit_id"]).operation_mode = "Continuous"
    session.commit()
    assert _resolve(session, run_chain["run_id"]) is False
    session.close()


def test_the_machine_override_still_beats_the_unit(run_chain):
    session = db.get_session()
    session.get(db.ProductionUnit, run_chain["unit_id"]).operation_mode = "Shot-by-shot"
    session.get(db.Machine, run_chain["machine_id"]).cycle_shot_operation_override = False
    session.commit()
    assert _resolve(session, run_chain["run_id"]) is False, (
        "The equipment-specific override no longer wins - R3 added a tier ABOVE the "
        "method, not above the machine."
    )
    session.close()


def test_a_false_machine_override_is_not_treated_as_unset(run_chain):
    """The NULL-versus-False trap, one tier up from where it usually bites."""
    session = db.get_session()
    session.get(db.ProductionMethod, run_chain["method_id"]).uses_cycle_shot_operation = True
    session.get(db.ProductionUnit, run_chain["unit_id"]).operation_mode = "Shot-by-shot"
    session.get(db.Machine, run_chain["machine_id"]).cycle_shot_operation_override = False
    session.commit()
    assert _resolve(session, run_chain["run_id"]) is False
    session.close()


def test_the_run_reads_its_own_unit_snapshot_not_its_machines_current_unit(run_chain):
    """Move the equipment to a shot-by-shot cell and leave the run's snapshot
    alone. The finished run must keep answering as it did.

    This is the test that fails against the tempting implementation - reading
    run.machine.production_unit - and it is the reason 0022 stored the unit on
    the run in the first place."""
    session = db.get_session()
    session.get(db.ProductionUnit, run_chain["other_unit_id"]).operation_mode = "Shot-by-shot"
    machine = session.get(db.Machine, run_chain["machine_id"])
    machine.production_unit_id = run_chain["other_unit_id"]
    run = session.get(db.ProductionRun, run_chain["run_id"])
    assert run.production_unit_id == run_chain["unit_id"], "The run's snapshot must not move"
    session.commit()

    assert _resolve(session, run_chain["run_id"]) is False, (
        "Re-assigning the equipment to a shot-by-shot cell changed what a finished run "
        "captures. The resolution is reading the machine's CURRENT unit instead of the "
        "unit the run recorded."
    )
    session.close()


def test_a_run_with_nothing_resolved_never_raises(run_chain):
    session = db.get_session()
    run = session.get(db.ProductionRun, run_chain["run_id"])
    run.machine_id = None
    run.production_unit_id = None
    run.production_method_id = None
    session.commit()
    assert _resolve(session, run_chain["run_id"]) is False
    session.close()


# ---------------------------------------------------------------------------
# Section 2 - the helper on its own
# ---------------------------------------------------------------------------

def test_unit_helper_is_three_valued():
    assert helpers.unit_uses_cycle_shot_operation(None) is None
    class _U:
        operation_mode = None
    assert helpers.unit_uses_cycle_shot_operation(_U()) is None, (
        "An uncharacterised unit must answer None, not False - False is an assertion "
        "that the line runs continuously, which nobody has made."
    )
    _U.operation_mode = "Shot-by-shot"
    assert helpers.unit_uses_cycle_shot_operation(_U()) is True
    _U.operation_mode = "Continuous"
    assert helpers.unit_uses_cycle_shot_operation(_U()) is False


def test_the_vocabulary_is_exactly_two_values():
    """No "Not specified" entry. The absence of a value already means that, and
    a third option would be stored as though somebody had decided."""
    assert helpers.PRODUCTION_UNIT_OPERATION_MODES == ("Continuous", "Shot-by-shot")


# ---------------------------------------------------------------------------
# Section 3 - the model and the artifact
# ---------------------------------------------------------------------------

def test_the_column_exists_and_is_nullable():
    cols = {c.name: c for c in db.ProductionUnit.__table__.columns}
    assert "operation_mode" in cols, "production_units.operation_mode is missing"
    assert cols["operation_mode"].nullable, (
        "Nullable is the not-characterised state, and it is load-bearing."
    )


def test_migration_exists():
    assert os.path.exists(os.path.join(MIGRATIONS_DIR, MIGRATION)), f"{MIGRATION} is missing"


def test_the_migration_enforces_the_vocabulary_in_the_database():
    """The tuple in helpers.py is what the pages offer. This is what makes it
    true - the same split as ck_pumf_controlled_vocabulary."""
    code = " ".join(_migration_code().lower().split())
    assert "ck_production_units_operation_mode" in code
    assert "'continuous', 'shot-by-shot'" in code, (
        "The CHECK constraint does not list the controlled vocabulary."
    )
    for mode in helpers.PRODUCTION_UNIT_OPERATION_MODES:
        assert mode.lower() in code, (
            f"{mode!r} is offered by the application and not permitted by the constraint."
        )


def test_the_migration_characterises_nothing():
    code = _migration_code().lower()
    assert "update production_units" not in code, (
        "0025 sets an operation mode on a live unit. How a real line runs is plant "
        "fact, and Charlie's WP7 Phase 2 closeout forbids inferring it."
    )
    assert "characterises nothing" in _migration_code(), (
        "The exit check asserting that no unit was characterised has been removed."
    )


def test_the_migration_is_schema_agnostic():
    for line in _migration_code().splitlines():
        assert "rigid_foam." not in line, f"Migration hard-codes a schema name: {line.strip()!r}"
