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


# ---------------------------------------------------------------------------
# Section 4 - the Production Units / Cells page
#
# Charlie's naming ruling, 21 August 2026, option A. db.ProductionUnit had
# been in the schema since 2026-08-06 with no screen at all, and nobody
# noticed because views/31_Production_Equipment.py labelled db.Machine
# records "Production Unit / Cell" - so the level looked present in the
# navigation when it was not.
#
# His minimum for the page: plant-scoped, through the existing access-control
# pattern, showing unit code/name, Plant and linked Equipment / Machines, with
# no invented master-data fields.
# ---------------------------------------------------------------------------
import ast as _ast

from streamlit.testing.v1 import AppTest

import access_control
import tenant_scope

PAGE_UNITS = os.path.join(APP_DIR, "views", "35_Production_Units.py")
PAGE_EQUIPMENT = os.path.join(APP_DIR, "views", "31_Production_Equipment.py")
NAV_FILE = os.path.join(APP_DIR, "app_rigid_foam.py")


def _clear_scope_caches():
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()


def _page_text(at):
    """Both streams, on purpose.

    helpers.render_data_table() emits HTML through st.markdown, but
    helpers.clickable_table() - which this page uses for its listing - calls
    st.dataframe. Reading only the markdown stream is how the first version of
    this test reported that the page did not list any units when it listed all
    of them. Which helper a page uses is not something a test should have to
    know, so both are read."""
    parts = [str(el.value) for el in at.markdown]
    parts += [str(el.value) for el in at.subheader]
    parts += [str(el.value) for el in at.caption]
    parts += [str(el.value) for el in at.info]
    for el in at.dataframe:
        # str() on a DataFrame gives pandas' TRUNCATED repr - "..." in place of
        # the middle columns - so a value that is plainly on screen reads as
        # absent. Every cell is stringified individually instead.
        frame = getattr(el, "value", None)
        if frame is None:
            continue
        try:
            for row in frame.astype(str).values.tolist():
                parts.extend(row)
            parts.extend(str(c) for c in frame.columns)
        except AttributeError:
            parts.append(str(frame))
    return " ".join(parts)


def _run_as_company_user(page_path, company_id):
    """A real company_id, never None.

    AUTH_DISABLED alone leaves company_id None, and
    tenant_scope.plant_ids_for_company(None) means UNFILTERED - so a scoping
    test written the easy way compares an unfiltered view with an unfiltered
    view and passes whatever the code does. That mistake cost a real
    cross-company leak in R2."""
    _clear_scope_caches()
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["is_super_admin"] = False
    at.session_state["is_platform_owner"] = False
    at.session_state["company_id"] = company_id
    at.run()
    return at


def _run_as_platform_owner(page_path):
    _clear_scope_caches()
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["is_super_admin"] = True
    at.session_state["is_platform_owner"] = True
    at.run()
    return at


def test_the_production_units_page_exists():
    """It did not, for a fortnight, while the table it serves held live rows."""
    assert os.path.exists(PAGE_UNITS), (
        "views/35_Production_Units.py is missing - db.ProductionUnit has no screen again."
    )


def test_the_page_is_registered_in_navigation():
    """A page file nobody can reach is the same defect as no page at all."""
    nav = open(NAV_FILE, encoding="utf-8").read()
    assert "views/35_Production_Units.py" in nav, (
        "The Production Units / Cells page is not registered in app_rigid_foam.py"
    )
    assert 'title="Production Units / Cells"' in nav
    assert nav.index("views/35_Production_Units.py") < nav.index("views/31_Production_Equipment.py"), (
        "Production Units / Cells must sit above Production Equipment - the operational "
        "order is Plant, then unit, then the equipment inside it."
    )


def test_the_page_uses_an_existing_access_control_key():
    """Charlie: "maintainable through the existing access-control pattern".

    It shares "plant_overview" with the Production Equipment page on purpose.
    A role permitted to maintain equipment must be able to maintain the unit
    holding it - a permission state granting one and not the other has no
    meaning - and reusing the key means no existing role silently loses access
    to a key it has never been shown."""
    src = open(PAGE_UNITS, encoding="utf-8").read()
    assert 'can_use_page(\n    "plant_overview"' in src or 'can_use_page("plant_overview"' in src, (
        "The page does not gate on the plant_overview access key."
    )
    equipment_src = open(PAGE_EQUIPMENT, encoding="utf-8").read()
    assert '"plant_overview"' in equipment_src, (
        "Production Equipment no longer uses plant_overview - the shared-key "
        "reasoning above needs revisiting rather than this assertion relaxing."
    )


def test_the_page_invents_no_master_data_fields():
    """Charlie: "Do not invent new master-data fields to fill the page."

    Read off the source: every keyword the page passes when constructing a
    ProductionUnit must already be a column on the model. A page that writes a
    field the schema does not have would fail at runtime; a page that writes a
    field somebody ADDED to the schema to fill the page is the thing being
    refused here, and only the model can tell you which."""
    src = open(PAGE_UNITS, encoding="utf-8").read()
    tree = _ast.parse(src)
    passed = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name) \
           and node.func.id == "ProductionUnit":
            passed.update(kw.arg for kw in node.keywords if kw.arg)
    assert passed, "The page never constructs a ProductionUnit - it cannot create one."
    columns = {c.name for c in db.ProductionUnit.__table__.columns}
    unknown = passed - columns
    assert not unknown, f"The page writes fields ProductionUnit does not have: {unknown}"

    # R3 (2026-08-22) note. Until v0.82.0 this test also asserted that no
    # user-visible string on the page said "continuous" or "shot-by-shot",
    # because that property belonged to a later work package. THIS IS THAT WORK
    # PACKAGE. Migration 0025 created production_units.operation_mode and
    # helpers.run_uses_cycle_shot_operation() reads it, so the field has earned
    # its place and the scan is deleted rather than adjusted to pass - it
    # recorded a decision, and the decision is over (working preferences 15a).
    #
    # What replaces it is not a weaker version of the same scan. It is
    # test_the_page_offers_the_operation_mode_property below, which asserts the
    # field is present and offers exactly the controlled vocabulary, and the
    # resolution tests in tests/test_r3_production_unit_operation_mode.py.


def test_the_page_offers_the_operation_mode_property(inventory):
    """R3: continuous versus shot-by-shot, captured at unit level.

    Asserts the vocabulary the picker offers rather than just that a control
    exists - a field offering a free-typed value would satisfy "the field is
    there" and defeat ck_production_units_operation_mode the moment somebody
    typed something else."""
    at = _run_as_platform_owner(PAGE_UNITS)
    assert not at.exception, at.exception
    pickers = [sb for sb in at.selectbox if str(sb.label) == "Operation mode"]
    assert pickers, "The Production Units / Cells page has no Operation mode field"
    for picker in pickers:
        options = [str(o) for o in picker.options]
        assert "Continuous" in options and "Shot-by-shot" in options, (
            f"The operation-mode picker does not offer the controlled vocabulary: {options}"
        )
        # AppTest reports the FORMATTED labels, which is what the user reads.
        # The empty value renders through format_func as the not-characterised
        # entry; asserting the raw "" here would be asserting an implementation
        # detail the user never sees.
        assert "— not characterised —" in options, (
            "There must be a way back to not-characterised. A unit somebody set by "
            f"mistake cannot be corrected otherwise. Options: {options}"
        )
        assert len(options) == 3, (
            f"The picker offers a value outside the controlled vocabulary: {options}"
        )


def test_no_live_unit_is_characterised_by_the_migration(inventory):
    """Charlie's WP7 Phase 2 closeout rejected inferring cycle/shot operation
    from a name, and BOTH live Production Methods are called "Discontinuous" -
    exactly the trap that ruling was written about. How a real line runs is
    plant fact. Migration 0025 adds the column and characterises nothing."""
    session = db.get_session()
    characterised = [u.controlled_id for u in session.query(db.ProductionUnit).all()
                     if u.operation_mode is not None]
    session.close()
    assert not characterised, (
        f"Unit(s) {characterised} were characterised without plant evidence."
    )


def test_the_page_shows_charlies_minimum(inventory):
    """Unit code/name, Plant and linked Equipment / Machines, all three."""
    at = _run_as_platform_owner(PAGE_UNITS)
    assert not at.exception, at.exception
    text = _page_text(at)
    for expected in ("PU-PH1-001", "Panel Line 1", "HTC Global - Phase 1 Plant", "Panel Foamer 1",
                     "PU-KOR-001", "Appliance Cavity Cell 1", "PTU Korat",
                     "Appliance Cavity Foaming Unit"):
        assert expected in text, f"{expected!r} is not shown on the Production Units / Cells page"


def test_a_company_cannot_see_another_companys_units(inventory):
    """The plant scope IS the company scope here - a unit belongs to a plant
    and a plant belongs to a company - so an unscoped listing on this page
    would put PTU's production layout in front of HTC and the reverse."""
    at = _run_as_company_user(PAGE_UNITS, inventory["companies"]["ptu"])
    assert not at.exception, at.exception
    text = _page_text(at)
    assert "PU-KOR-001" in text, "PTU cannot see its own Production Unit"
    assert "PU-PH1-001" not in text, "PTU can see HTC's Production Unit"
    assert "Panel Line 1" not in text, "PTU can see HTC's Production Unit by name"
    assert "Panel Foamer 1" not in text, "PTU can see HTC's equipment"

    # The COUNTS, not only the listing. Dropping the plant scope from the
    # equipment query left every assertion above green: HTC's machine never
    # renders in PTU's table, because the table is keyed by the units in
    # scope - but it still reached the metrics, and it would still be NAMED in
    # the unassigned-equipment notice. A leak does not have to appear in the
    # table to be a leak, and this mutation survived until these three lines
    # were added.
    counts = {m.label: str(m.value) for m in at.metric}
    units_seen = next((v for k, v in counts.items() if "production unit" in k.lower()), None)
    equipment_seen = next((v for k, v in counts.items() if "equipment / machines" in k.lower()), None)
    assert units_seen == "1", f"PTU's Production Unit count includes another company ({units_seen})"
    assert equipment_seen == "1", f"PTU's equipment count includes another company ({equipment_seen})"


def test_the_leak_check_can_fail(inventory):
    """Negative control, and the reason it is not optional.

    Without it, this test passes if the fixture only ever contains one
    company's data - which is exactly how a real cross-company leak reached
    the deployed Application Areas page in R2. The platform owner genuinely
    sees both, so seeing both here proves the strings ARE reachable and the
    company-scoped assertion above is measuring scope rather than absence."""
    at = _run_as_platform_owner(PAGE_UNITS)
    assert not at.exception, at.exception
    text = _page_text(at)
    assert "PU-KOR-001" in text and "PU-PH1-001" in text, (
        "The platform owner cannot see both units, so the scoped test above is "
        "asserting that strings are missing for some other reason."
    )


def test_unassigned_equipment_is_surfaced_not_hidden(inventory):
    """A machine with no unit is legal during master-data setup - Charlie kept
    that state - but it stops being acceptable at R3-WP4, where a run may not
    complete unless its equipment resolves to a unit. The page says so rather
    than leaving that work package to discover it."""
    session = db.get_session()
    machine = session.get(db.Machine, inventory["machines"]["ptu"])
    machine.production_unit_id = None
    session.commit()
    session.close()

    at = _run_as_platform_owner(PAGE_UNITS)
    assert not at.exception, at.exception
    labels = {m.label: str(m.value) for m in at.metric}
    unassigned = next((v for k, v in labels.items() if "without a unit" in k.lower()), None)

    session = db.get_session()
    session.get(db.Machine, inventory["machines"]["ptu"]).production_unit_id = inventory["units"]["ptu"]
    session.commit()
    session.close()

    assert unassigned == "1", (
        f"Unassigned equipment is not surfaced on the page (metric read {unassigned!r})."
    )


# ---------------------------------------------------------------------------
# Section 5 - the rename's own scanner
#
# Written at the moment of the rename, not afterwards. R1 renamed Product
# Family to PU Material Family and shipped with nine files still saying the old
# thing, and the suite was green throughout because the only scanner looked for
# the term the rename had PRODUCED rather than the one it replaced. A rename
# needs a scanner for the term it is removing, and it needs it on the same day.
#
# Pre-change measurement, taken before any edit: 77 user-visible strings across
# 12 files. My conflict document to Charlie said nine files, counted by grep
# over views/ alone - reports.py, app_rigid_foam.py and cascades.py also
# carried labels. He asked for the count from an actual execution rather than
# the quoted figure, and this is why.
#
# Post-change: 28 strings across 3 files, every one of them referring to
# db.ProductionUnit.
# ---------------------------------------------------------------------------

PRODUCTION_UNIT_PHRASE = re.compile(r"production\s*units?\s*(?:/|\s+or\s+)?\s*cells?|production\s+units?", re.IGNORECASE)

# R3-WP4 found a second shape of the same mislabel, and PRODUCTION_UNIT_PHRASE
# could never have caught it. The v0.80.0 sweep looked for "Production Unit".
# Three strings said "equipment / machine or cell" instead - the machine
# presented as a cell without the forbidden words appearing at all. All three
# were split across implicit string concatenation ("equipment / machine or " +
# "cell changes"), so grep could not see them either. Found only by testing the
# JOINED constant, which is the same technique that found the last two.
EQUIPMENT_AS_CELL_PHRASE = re.compile(r"machines?\s*(?:/|\s+or\s+)\s*cells?", re.IGNORECASE)

# The only files whose user-visible strings may say "Production Unit", because
# they are the only ones that talk about db.ProductionUnit.
UNIT_BEARING_FILES = {
    "views/35_Production_Units.py",      # the page for the entity itself
    "views/34_Application_Areas.py",     # states the ratified hierarchy
    "app_rigid_foam.py",                 # the navigation entry for that page
}

# One file needs the phrase without being exempt from the rule.
#
# Charlie's ruling has two halves, and they pull in opposite directions on the
# Production Equipment page: db.Machine must never be LABELLED a Production
# Unit, and the unit a machine is ASSIGNED to must be visible there. So the
# page legitimately says "Production Unit / Cell" while never using it as the
# name of the equipment.
#
# A scanner cannot read that difference, and exempting the whole file would
# drop the guard on the one file that carried 21 of the 77 mislabels. So the
# permitted strings are listed exactly, each earning its place, and
# test_the_equipment_page_exceptions_are_all_used refuses an entry that has
# stopped being used - the same discipline as the file allowlist above.
# R3-WP4 adds a second such file for the same reason. helpers.py's completion
# guard has to TELL the user that their Equipment / Machine is not assigned to a
# Production Unit / Cell - a sentence that names both entities and, in naming
# them, distinguishes them. It is the opposite of the mislabel the rule exists
# to catch, and the scanner cannot read that difference any more than it could
# on the Equipment page. So the three messages are listed exactly, and
# test_the_permitted_strings_are_all_used refuses any that stops being used.
PERMITTED_UNIT_STRINGS = {
    "views/31_Production_Equipment.py": {
        "Production Unit / Cell",           # the listing column header
        "Production Unit / Cell: **",       # the edit panel's read-only caption
    },
    "views/4_Production_Run_Trial_Record.py": {
        # R3-WP4. The run RECORDS a Production Unit / Cell, so the page has to
        # name it - to show what was recorded, to say what will be recorded,
        # and to warn before the completion guard refuses. None of these names
        # the Equipment / Machine as a unit; the run-context sentence exists
        # specifically to say they are different things.
        "Production Unit / Cell",                        # the listing column header
        "Production Unit / Cell recorded on this run: **",
        "Production Unit / Cell that will be recorded: **",
        "Run context is captured in order - Plant, then Production Method, then "
        "Equipment / Machine, then Product Grade - because the Equipment / Machine "
        "you pick is what determines which Product Grades are producible on it. "
        "The Production Unit / Cell is not picked here; it follows the equipment.",
        " is not assigned to a Production Unit / Cell. The run can be created, but "
        "it cannot be set to Completed until the equipment is assigned on the "
        "Production Units / Cells page.",
        " is not assigned to a Production Unit / Cell. This run can be saved, but "
        "it cannot be set to Completed until the equipment is assigned on the "
        "Production Units / Cells page.",
        "Saving will record the Production Unit / Cell of the currently selected "
        "Equipment / Machine.",
    },
    "helpers.py": {
        # run_completion_blocker's three refusals. Each one contrasts the
        # equipment with the unit; none of them names the equipment as a unit.
        " is not assigned to a Production Unit / Cell, so this run cannot be "
        "completed. Assign it on the Production Units / Cells page, then "
        "reselect the equipment here.",
        "This run carries no Production Unit / Cell. Reselect its "
        "Equipment / Machine so the unit is recorded, then complete it.",
        "This run's recorded Production Unit / Cell no longer matches its "
        "Equipment / Machine. Reselect the equipment to refresh the "
        "recorded unit before completing the run.",
    },
}


def _user_visible_strings(path):
    """String literals that reach a user, located by the AST.

    Docstrings and bare string statements are excluded BY NODE IDENTITY rather
    than by an allowlist or a "#" prefix. Every previous version of this idea
    in this repository failed the same way - a scanner over raw text fails on
    the comment that explains the rename it is enforcing."""
    src = open(path, encoding="utf-8").read()
    tree = _ast.parse(src)
    prose = set()
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            if _ast.get_docstring(node, clean=False) is not None and node.body \
               and isinstance(node.body[0], _ast.Expr):
                prose.add(id(node.body[0].value))
        if isinstance(node, _ast.Expr) and isinstance(node.value, _ast.Constant) \
           and isinstance(node.value.value, str):
            prose.add(id(node.value))
    return [
        (node.lineno, node.value)
        for node in _ast.walk(tree)
        if isinstance(node, _ast.Constant) and isinstance(node.value, str)
        and id(node) not in prose
    ]


def _scannable_files():
    files = []
    views_dir = os.path.join(APP_DIR, "views")
    for name in sorted(os.listdir(views_dir)):
        if name.endswith(".py"):
            files.append(("views/" + name, os.path.join(views_dir, name)))
    for name in sorted(os.listdir(APP_DIR)):
        if name.endswith(".py") and name != "version.py":
            files.append((name, os.path.join(APP_DIR, name)))
    return files


def test_no_machine_surface_calls_itself_a_production_unit():
    """Charlie's naming ruling: "Do not label db.Machine as Production Unit,
    Production Unit / Cell or Production Unit or Cell."

    Enforced as "no file outside the three that serve db.ProductionUnit may put
    that phrase in front of a user". A scanner cannot tell which entity a
    sentence means, but it can tell which file the sentence is in, and only
    three files have any business saying it."""
    offenders = []
    for rel, path in _scannable_files():
        if rel in UNIT_BEARING_FILES:
            continue
        permitted = PERMITTED_UNIT_STRINGS.get(rel, set())
        for lineno, value in _user_visible_strings(path):
            if value in permitted:
                continue
            if PRODUCTION_UNIT_PHRASE.search(value):
                offenders.append(f"{rel}:{lineno}: {value[:80]!r}")
    assert not offenders, (
        "User-visible strings still present db.Machine as a Production Unit:\n  "
        + "\n  ".join(offenders)
    )


def test_no_surface_calls_equipment_a_cell():
    """The other direction of Charlie's ruling. "Do not label db.Machine as
    Production Unit, Production Unit / Cell or Production Unit or Cell" is about
    the entity, not about a particular wording - and "equipment / machine or
    cell" labels it just as plainly while containing none of those phrases.

    No file is exempt from this one. There is no legitimate reason for any
    string to join Machine and Cell with a slash or an "or"; a sentence that
    needs both says which is which."""
    offenders = []
    for rel, path in _scannable_files():
        for lineno, value in _user_visible_strings(path):
            if EQUIPMENT_AS_CELL_PHRASE.search(value):
                offenders.append(f"{rel}:{lineno}: {value[:80]!r}")
    assert not offenders, (
        "User-visible strings still present Equipment / Machine as a Cell:\n  "
        + "\n  ".join(offenders)
    )


def test_the_equipment_as_cell_scanner_can_fail():
    """Negative control, written as independent literals - the three the
    codebase actually carried, plus the slash form."""
    for text in (
        "recipe version, equipment / machine or cell, or recorded Actual process settings",
        "the Equipment / Machine or Cell you pick",
        "equipment / machine or cell changes, and quality-issue history",
        "Machine / Cell",
    ):
        assert EQUIPMENT_AS_CELL_PHRASE.search(text), (
            f"The scanner does not recognise {text!r}, which is a form the codebase used."
        )
    for allowed in (
        "Production Unit / Cell",
        "Equipment / Machine",
        "equipment / machine or process settings behind them",
        "Production Unit / Cell recorded on this run",
    ):
        assert not EQUIPMENT_AS_CELL_PHRASE.search(allowed), (
            f"The scanner fires on {allowed!r}, which is correct wording."
        )


def test_the_rename_scanner_can_fail():
    """Negative control, with the planted string written as an independent
    literal rather than generated from PRODUCTION_UNIT_PHRASE - Charlie's rule
    after the R2 phrase-list control was found reading the list under test."""
    planted = [
        "Production Unit / Cell *",
        "Production Unit or Cell",
        "Production Units/Cells",
        "production unit(s) or cell(s)",
    ]
    for text in planted:
        assert PRODUCTION_UNIT_PHRASE.search(text), (
            f"The scanner does not recognise {text!r}, which is a form the codebase "
            "actually used before the rename."
        )
    for allowed in ("Equipment / Machine", "Equipment / Machines", "Machine", "Production Method"):
        assert not PRODUCTION_UNIT_PHRASE.search(allowed), (
            f"The scanner fires on {allowed!r}, which is the correct wording."
        )


def test_the_unit_bearing_files_actually_use_the_phrase():
    """The allowlist is only safe while every entry earns its place. A file
    that stops mentioning Production Units should leave the list, otherwise the
    list slowly becomes a place to hide a mislabel."""
    for rel in sorted(UNIT_BEARING_FILES):
        path = os.path.join(APP_DIR, rel)
        assert os.path.exists(path), f"{rel} is on the allowlist and does not exist"
        found = any(PRODUCTION_UNIT_PHRASE.search(v) for _, v in _user_visible_strings(path))
        assert found, (
            f"{rel} is allowed to say 'Production Unit' and no longer does - remove it "
            "from UNIT_BEARING_FILES rather than leaving an unused exemption."
        )


def test_the_equipment_page_shows_the_assigned_unit():
    """The other half of Charlie's ruling: "Update the Equipment / Machine
    surfaces so the assigned Production Unit / Cell is visible where it helps
    the user understand the relationship."

    Easy to leave undone, because the rename half is loud and this half is
    quiet - nothing fails without it. It is what makes the two entities
    distinguishable rather than merely differently named."""
    src = open(os.path.join(APP_DIR, "views", "31_Production_Equipment.py"), encoding="utf-8").read()
    assert "ProductionUnit" in src, (
        "The Production Equipment page does not read db.ProductionUnit at all, so it "
        "cannot be showing which unit a machine belongs to."
    )
    assert '"Production Unit / Cell": _unit_label(m)' in src, (
        "The equipment listing has no Production Unit / Cell column."
    )
    assert "plants" in src.split("_units_by_id", 1)[1][:400], (
        "The unit lookup on the equipment page is not scoped to the plants in scope - "
        "a unit name is another company's operational layout."
    )


def test_the_permitted_strings_are_all_used():
    """An allowlist entry that no longer matches anything is a hole waiting for
    a mislabel to fall into it.

    Renamed in R3-WP4 - it was written for the Production Equipment page alone
    and has always been generic; helpers.py is now a second entry and the old
    name would have read as though it were not covered."""
    for rel, permitted in PERMITTED_UNIT_STRINGS.items():
        found = {v for _, v in _user_visible_strings(os.path.join(APP_DIR, rel))}
        unused = permitted - found
        assert not unused, (
            f"{rel} no longer contains {unused} - remove the exemption rather than "
            "leaving it standing."
        )
