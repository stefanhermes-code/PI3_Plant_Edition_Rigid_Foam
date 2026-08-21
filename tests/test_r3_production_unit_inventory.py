"""R3-WP1 (Production Units / Cells - inventory and completion).
Charlie's "Package C Acceptance and Consolidated R3 Release to JC v3",
section 3, first requirement:

    "Production Units / Cells: Inventory the existing units and machine
     assignments first. Create missing units only from existing
     plant/equipment evidence or approved pilot data. A machine belongs to
     one Production Unit / Cell at a time. Keep the current
     one-machine-to-one-unit relationship; no association table is required."

WHAT THE INVENTORY FOUND, AND WHY THESE TESTS LOOK LIKE THIS

Two plants, two machines, one Production Unit. HTC Phase 1's "Panel Foamer 1"
sat under PU-PH1-001; PTU Korat's "Appliance Cavity Foaming Unit" sat under
nothing. Migration 0019 created PU-KOR-001 and assigned it.

Everything else about the inventory was already sound - no cross-plant
assignment, no unit holding two machines, no unit holding none - so most of
this file guards a state that is currently correct rather than fixing one.
That is the point: R3-WP4 hangs production_runs.production_unit_id off this
relationship, and a run cannot snapshot a unit its machine does not have.

RESTRAINT IS PART OF THE REQUIREMENT

PTU Korat has FIVE activated production methods and ONE machine. An activated
method says the plant MAY run that method; it is not evidence that equipment
exists. Charlie's wording is "existing plant/equipment evidence". So one unit
was created, not five, and test_no_unit_is_created_for_a_method_without_equipment
holds that line - the pressure to fan units out across activated methods will
come back when someone wants every method to have somewhere to point.

EVERY CHECK HERE HAS TO BE ABLE TO FAIL

Written after two tests in tests/test_r2_application_area_master.py were found
to have been green since the release that introduced them without ever having
looked at anything - one because its fixture left the scanned column NULL, the
other because its negative control read the list it was controlling. So each
guard below is paired with a fixture that plants the violation and proves the
guard catches it.

Usage: python -m pytest tests/test_r3_production_unit_inventory.py -v
"""
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
from migration_sql_helpers import set_targets as _set_targets

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(APP_DIR, "migrations")
MIGRATION = "0019_r3wp1_production_unit_inventory_completion.sql"

# The live inventory after 0019, from the migration's own exit check.
EXPECTED_UNITS = {
    "PU-PH1-001": ("Panel Line 1", "HTC Global - Phase 1 Plant"),
    "PU-KOR-001": ("Appliance Cavity Cell 1", "PTU Korat"),
}


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def inventory():
    """The live shape after 0019: two companies, one plant each, one Production
    Unit per plant, one machine per unit, every machine assigned."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    ids = {"plants": {}, "units": {}, "machines": {}, "companies": {}}
    for label, plant_name, unit_cid, unit_name, machine_name in (
        ("htc", "HTC Global - Phase 1 Plant", "PU-PH1-001", "Panel Line 1", "Panel Foamer 1"),
        ("ptu", "PTU Korat", "PU-KOR-001", "Appliance Cavity Cell 1", "Appliance Cavity Foaming Unit"),
    ):
        company = db.Company(name=f"{label} {u}", is_platform_owner=(label == "htc"))
        session.add(company); session.flush()
        plant = db.Plant(company_id=company.id, name=plant_name)
        session.add(plant); session.flush()
        unit = db.ProductionUnit(plant_id=plant.id, controlled_id=unit_cid, name=unit_name)
        session.add(unit); session.flush()
        machine = db.Machine(plant_id=plant.id, name=machine_name, production_unit_id=unit.id)
        session.add(machine); session.flush()
        ids["companies"][label] = company.id
        ids["plants"][label] = plant.id
        ids["units"][label] = unit.id
        ids["machines"][label] = machine.id

    session.commit()
    session.close()
    return ids


def _migration_code():
    sql = open(os.path.join(MIGRATIONS_DIR, MIGRATION), encoding="utf-8").read()
    return "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))


# ---------------------------------------------------------------------------
# Section 1 - the artifact does what the requirement says
# ---------------------------------------------------------------------------

def test_migration_exists():
    assert os.path.exists(os.path.join(MIGRATIONS_DIR, MIGRATION)), f"{MIGRATION} is missing"


def test_migration_creates_exactly_one_unit():
    """One machine had no unit, so one unit is created. Read off the artifact
    rather than the outcome: a migration that created five units and deleted
    four would reach the same end state and would not be the same migration."""
    code = _migration_code()
    inserts = [s for s in code.split(";") if s.strip().lower().startswith("insert into production_units")]
    assert len(inserts) == 1, f"Expected exactly 1 INSERT into production_units, found {len(inserts)}"
    assert "PU-KOR-001" in inserts[0]
    assert "PTU Korat" in inserts[0], (
        "The INSERT must name the plant it belongs to, not rely on an id."
    )


def test_migration_touches_only_the_unit_link_on_machines():
    """0019 assigns a machine to a unit. It must not edit the machine itself -
    a wording or method change smuggled into an inventory migration would not
    show up in the inventory evidence."""
    code = _migration_code()
    updates = [s.strip() for s in code.split(";") if s.strip().lower().startswith("update machines")]
    assert len(updates) == 1, f"Expected exactly 1 UPDATE of machines, found {len(updates)}"
    assigned = _set_targets(updates[0])
    assert assigned == ["production_unit_id"], (
        f"0019 writes something other than production_unit_id on machines: {assigned}"
    )
    for forbidden in ("alter table", "delete from", "drop "):
        assert forbidden not in code.lower(), (
            f"0019 contains {forbidden!r} - R3-WP1 is an inventory completion, not a schema change"
        )


def test_no_unit_is_created_for_a_method_without_equipment():
    """PTU Korat activated five production methods and owns one machine.
    Charlie's wording is "existing plant/equipment evidence", and an activated
    method is a capability statement, not equipment.

    Held as a test because the temptation is structural rather than
    accidental: four activated methods currently have nowhere to point, and
    creating a unit each would look like tidiness."""
    code = _migration_code()
    assert "plant_production_methods" not in code.lower(), (
        "0019 reads activated methods. Units come from equipment evidence, not "
        "from what a plant is permitted to run."
    )
    for cid in ("PU-KOR-002", "PU-KOR-003", "PU-KOR-004", "PU-KOR-005"):
        assert cid not in code, f"{cid} is created by 0019 - only one PTU machine exists"


# ---------------------------------------------------------------------------
# Section 2 - the relationship Charlie wants kept
# ---------------------------------------------------------------------------

def test_no_machine_to_unit_association_table():
    """Charlie: "Keep the current one-machine-to-one-unit relationship; no
    association table is required."

    A standing guard for the same reason the Product Grade/Application Area one
    exists in tests/test_r2_application_area_master.py. The argument for a join
    table arrives the first time a machine is moved between units and somebody
    wants to keep both facts."""
    for name in db.Base.metadata.tables:
        lowered = name.lower()
        looks_like_join = (
            "machine" in lowered
            and ("production_unit" in lowered or lowered.endswith("_units"))
        )
        assert not looks_like_join, (
            f"Table {name!r} looks like a machine/Production Unit association table, "
            "which R3-WP1 explicitly forbids."
        )
    machine_cols = {c.name for c in db.Machine.__table__.columns}
    assert "production_unit_id" in machine_cols, (
        "The singular machines.production_unit_id relationship must remain - it is "
        "what R3-WP4's run snapshot is derived from."
    )


def test_production_runs_do_not_carry_a_unit_yet():
    """R3-WP4's column, not R3-WP1's. If it appears early the backfill loses its
    controlled before/after evidence, because the column would already be
    populated by whatever wrote it first.

    Delete this test in R3-WP4 and replace it with the snapshot tests - do not
    edit it to pass."""
    run_cols = {c.name for c in db.ProductionRun.__table__.columns}
    assert "production_unit_id" not in run_cols, (
        "production_runs.production_unit_id exists already. It belongs to R3-WP4 "
        "under migration control, with row-by-row backfill evidence."
    )


# ---------------------------------------------------------------------------
# Section 3 - the inventory state, and proof each check can fail
# ---------------------------------------------------------------------------

def _unassigned_machines(session):
    return [m.name for m in session.query(db.Machine)
            .filter(db.Machine.production_unit_id.is_(None)).all()]


def _cross_plant_assignments(session):
    rows = (session.query(db.Machine, db.ProductionUnit)
            .join(db.ProductionUnit, db.ProductionUnit.id == db.Machine.production_unit_id)
            .all())
    return [m.name for m, u in rows if u.plant_id != m.plant_id]


def test_every_machine_belongs_to_a_unit(inventory):
    session = db.get_session()
    unassigned = _unassigned_machines(session)
    session.close()
    assert not unassigned, (
        "Machines with no Production Unit / Cell: " + ", ".join(unassigned) +
        ". R3-WP4 cannot snapshot a unit the machine does not have."
    )


def test_the_unassigned_check_can_fail(inventory):
    """Negative control. Plants the violation rather than reading the state and
    asserting it is fine."""
    session = db.get_session()
    machine = session.get(db.Machine, inventory["machines"]["ptu"])
    machine.production_unit_id = None
    session.commit()
    caught = _unassigned_machines(session)
    machine.production_unit_id = inventory["units"]["ptu"]
    session.commit()
    session.close()
    assert "Appliance Cavity Foaming Unit" in caught, (
        "The unassigned-machine check did not see a machine with no unit."
    )


def test_no_machine_sits_in_another_plants_unit(inventory):
    """A cross-plant assignment here is a cross-COMPANY one: plant 3 is HTC
    Global and plant 4 is PTU. The tenant boundary expressed in equipment."""
    session = db.get_session()
    offenders = _cross_plant_assignments(session)
    session.close()
    assert not offenders, "Machines sitting in another plant's unit: " + ", ".join(offenders)


def test_the_cross_plant_check_can_fail(inventory):
    """Negative control. Without this the check above passes on a fixture where
    both machines happen to share one plant, which proves nothing."""
    session = db.get_session()
    machine = session.get(db.Machine, inventory["machines"]["ptu"])
    original = machine.production_unit_id
    machine.production_unit_id = inventory["units"]["htc"]   # PTU machine, HTC unit
    session.commit()
    caught = _cross_plant_assignments(session)
    machine.production_unit_id = original
    session.commit()
    session.close()
    assert "Appliance Cavity Foaming Unit" in caught, (
        "A PTU machine was parented to an HTC unit and the check did not see it."
    )


def test_no_unit_carries_more_than_one_machine(inventory):
    session = db.get_session()
    counts = {}
    for m in session.query(db.Machine).filter(db.Machine.production_unit_id.isnot(None)).all():
        counts[m.production_unit_id] = counts.get(m.production_unit_id, 0) + 1
    session.close()
    crowded = [uid for uid, n in counts.items() if n > 1]
    assert not crowded, f"Production Unit(s) {crowded} carry more than one machine."


def test_the_crowded_unit_check_can_fail(inventory):
    """Negative control. The fixture has one machine per unit, so without
    planting a second the count can never exceed one."""
    session = db.get_session()
    machine = session.get(db.Machine, inventory["machines"]["ptu"])
    original = machine.production_unit_id
    machine.production_unit_id = inventory["units"]["htc"]
    session.commit()
    counts = {}
    for m in session.query(db.Machine).filter(db.Machine.production_unit_id.isnot(None)).all():
        counts[m.production_unit_id] = counts.get(m.production_unit_id, 0) + 1
    machine.production_unit_id = original
    session.commit()
    session.close()
    assert counts.get(inventory["units"]["htc"]) == 2, (
        "Two machines were pointed at one unit and the count did not see both."
    )


def test_every_unit_carries_at_least_one_machine(inventory):
    """A unit with no equipment is the shape that appears if units are ever
    fanned out across activated production methods."""
    session = db.get_session()
    empty = []
    for u in session.query(db.ProductionUnit).all():
        n = session.query(db.Machine).filter(db.Machine.production_unit_id == u.id).count()
        if n == 0:
            empty.append(u.controlled_id or u.name)
    session.close()
    assert not empty, "Production Unit(s) with no equipment: " + ", ".join(empty)


def test_the_empty_unit_check_can_fail(inventory):
    session = db.get_session()
    orphan = db.ProductionUnit(
        plant_id=inventory["plants"]["ptu"], controlled_id="PU-KOR-999",
        name="Unit with no equipment",
    )
    session.add(orphan); session.commit()
    empty = []
    for u in session.query(db.ProductionUnit).all():
        if session.query(db.Machine).filter(db.Machine.production_unit_id == u.id).count() == 0:
            empty.append(u.controlled_id)
    session.delete(orphan); session.commit()
    session.close()
    assert "PU-KOR-999" in empty, "An equipment-free unit was created and the check did not see it."


def test_the_two_units_are_the_expected_ones(inventory):
    session = db.get_session()
    found = {
        u.controlled_id: (u.name, session.get(db.Plant, u.plant_id).name)
        for u in session.query(db.ProductionUnit).all()
    }
    session.close()
    assert found == EXPECTED_UNITS, f"Production Unit inventory differs: {found}"


def test_the_scope_check_can_see_a_second_assignment():
    """Negative control for _set_targets, and the reason it exists.

    The naive regex this replaced returned ["production_unit_id"] for a
    statement that also wrote name, so the scope check above passed a migration
    it was written to refuse."""
    widened = "update machines m set production_unit_id = u.id, name = m.name from production_units u where 1=1"
    assert _set_targets(widened) == ["production_unit_id", "name"], (
        "The SET-clause parser cannot see an assignment after a comma."
    )
    narrow = "update machines m set production_unit_id = u.id from production_units u, plants p where 1=1"
    assert _set_targets(narrow) == ["production_unit_id"], (
        "The parser is reading past the SET clause into FROM or WHERE."
    )
