"""R3-WP4 (Production Run carries its Production Unit / Cell as a snapshot).

Charlie's release of R3-WP4, section on evidence:

    "Include a negative test that creates or uses Equipment / Machine with no
     Production Unit / Cell, assigns it to an editable run, and then attempts
     to set that run to Completed. The transition must be refused. Include the
     corresponding positive test with equipment that resolves to a unit. Also
     run a mutation or equivalent negative control proving the failing fixture
     changes the expected outcome if the guard is removed or bypassed. Do not
     treat the current eight NULL-status rows as evidence that the completion
     guard works. They do not exercise that state transition."

WHY THE UI TESTS ARE HERE AND NOT ONLY THE HELPER TESTS

run_completion_blocker() can be tested directly and is, in section 3. That
proves the FUNCTION is correct. It does not prove the page CALLS it, and the
whole finding that produced Charlie's wording is that eight rows sitting at
status NULL looked like evidence of a guard that had never once run. So
sections 4 and 5 drive the real Streamlit forms through AppTest and read the
database afterwards - the create path and the edit path, refused and allowed.

THE MUTATION CONTROL (section 6)

Every refusal here is paired with a run of the SAME fixture with the guard
bypassed, asserting the run reaches Completed. Without that pair, a negative
test passes just as happily when the transition was refused for some unrelated
reason - a missing recipe version, a grade that never got assigned - and the
guard could be deleted tomorrow with the suite still green. The bypass is done
by replacing helpers.run_completion_blocker for the duration of one AppTest
run: the page does "from helpers import run_completion_blocker" at module
level and AppTest re-executes the page module on every .run(), so the patched
function is the one the page binds. test_the_bypass_actually_reaches_the_page
proves that rebinding claim rather than assuming it.

Usage: python -m pytest tests/test_r3wp4_production_run_unit_snapshot.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import access_control
import db
import helpers
import tenant_scope
from helpers import resolve_production_unit_id, run_completion_blocker
from migration_sql_helpers import set_targets as _set_targets

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(APP_DIR, "migrations")
MIGRATION = "0022_r3wp4_production_run_unit_snapshot.sql"
PAGE4 = os.path.join(APP_DIR, "views", "4_Production_Run_Trial_Record.py")


def _clear_relevant_caches():
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    _clear_relevant_caches()


def _run(session_state=None):
    at = AppTest.from_file(PAGE4, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def _migration_code():
    sql = open(os.path.join(MIGRATIONS_DIR, MIGRATION), encoding="utf-8").read()
    return "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))


def _build_chain(with_unit):
    """Company > Plant > (Production Unit) > Method > Machine > Family > Grade
    > RecipeVersion > ProductionRun, with the machine either assigned to a
    Production Unit / Cell or deliberately not.

    with_unit=False is the fixture under test in the negative cases. It is not
    an artificial state: it is exactly what PTU Korat's equipment looked like
    before migration 0019, and what any newly created machine looks like until
    somebody assigns it on the Production Units / Cells page."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP4 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP4 Plant {u}")
    session.add(plant); session.flush()

    unit_id = None
    if with_unit:
        unit = db.ProductionUnit(
            plant_id=plant.id, controlled_id=f"PU-WP4-{u}", name=f"WP4 Cell {u}",
        )
        session.add(unit); session.flush()
        unit_id = unit.id

    method = db.ProductionMethod(controlled_id=f"PM-WP4-{u}", name=f"WP4 Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(
        plant_id=plant.id, production_method_id=method.id, active=True,
    ))
    session.flush()

    machine = db.Machine(
        plant_id=plant.id, name=f"WP4 Machine {u}", production_method_id=method.id,
        active=True, production_unit_id=unit_id,
    )
    session.add(machine); session.flush()

    family = db.PUMaterialFamily(plant_id=plant.id, name=f"WP4 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"WP4 Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label="v1",
        approval_status="Approved", is_active=True,
    )
    session.add(recipe); session.flush()

    run = db.ProductionRun(
        plant_id=plant.id,
        foam_grade_id=grade.id,
        recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1),
        batch_reference=f"B-WP4-{u}",
        machine_id=machine.id,
        production_unit_id=unit_id,
        production_method_id=method.id,
        operator_or_team_reference="Shift A",
        notes="seed run",
    )
    session.add(run); session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "unit_id": unit_id,
        "method_id": method.id, "machine_id": machine.id, "machine_name": machine.name,
        "family_id": family.id, "grade_id": grade.id, "recipe_version_id": recipe.id,
        "run_id": run.id,
    }
    session.close()
    return ids


@pytest.fixture()
def chain_with_unit():
    return _build_chain(with_unit=True)


@pytest.fixture()
def chain_without_unit():
    return _build_chain(with_unit=False)


# ---------------------------------------------------------------------------
# Section 0 - the fixtures are what they claim to be
#
# Written first and deliberately. tests/test_r2_application_area_master.py had
# two tests that were green from the day they were written without ever having
# looked at anything, one of them because its fixture left the scanned column
# NULL. A negative test whose fixture is not actually in the failing state
# proves nothing, and does it silently.
# ---------------------------------------------------------------------------

def test_the_negative_fixture_really_has_no_unit(chain_without_unit):
    session = db.get_session()
    machine = session.get(db.Machine, chain_without_unit["machine_id"])
    run = session.get(db.ProductionRun, chain_without_unit["run_id"])
    assert machine.production_unit_id is None, (
        "The negative fixture's Equipment / Machine is assigned to a Production "
        "Unit / Cell, so it does not exercise the refusal at all."
    )
    assert run.production_unit_id is None
    assert run.status is None, "The run must start un-completed for the transition to be a transition"
    session.close()


def test_the_positive_fixture_really_has_a_unit(chain_with_unit):
    session = db.get_session()
    machine = session.get(db.Machine, chain_with_unit["machine_id"])
    run = session.get(db.ProductionRun, chain_with_unit["run_id"])
    assert machine.production_unit_id == chain_with_unit["unit_id"]
    assert run.production_unit_id == chain_with_unit["unit_id"]
    assert run.status is None
    session.close()


# ---------------------------------------------------------------------------
# Section 1 - the migration artifact
#
# Read off the artifact, not off the resulting database. A migration that
# added the column and then wrote something else as well would leave a
# database that looks identical in the one column anybody thought to check.
# ---------------------------------------------------------------------------

def test_migration_exists():
    assert os.path.exists(os.path.join(MIGRATIONS_DIR, MIGRATION)), f"{MIGRATION} is missing"


def test_migration_adds_the_column_idempotently():
    code = _migration_code().lower()
    assert "add column if not exists production_unit_id" in " ".join(code.split()), (
        "The column must be added with IF NOT EXISTS - the migration is proved on a "
        "disposable schema and then applied to live, so it runs more than once."
    )


def test_the_backfill_writes_only_the_snapshot_column():
    """set_targets() cuts the SET clause at the first FROM/WHERE and splits on
    commas. The earlier hand-rolled regex in 0017/0018 stopped at the first
    assignment and would have missed a second target after a comma, which is
    precisely how an unnoticed extra write would look."""
    code = _migration_code()
    updates = [l for l in code.splitlines() if l.strip().lower().startswith("set ")]
    assert updates, "No SET clause found - has the backfill been removed?"
    for clause in updates:
        assert _set_targets(clause) == ["production_unit_id"], (
            f"The backfill writes more than the snapshot column: {_set_targets(clause)}"
        )


def test_the_backfill_never_writes_status():
    code = _migration_code().lower()
    assert "set status" not in code and "status =" not in code.replace("status is not null", ""), (
        "R3-WP4 adds a snapshot. Setting a run's status is a state transition that "
        "belongs to a user in the UI, behind the completion guard."
    )


def test_the_fk_existence_check_is_scoped_to_the_current_schema():
    """Unscoped, the check would find the live constraint while running on a
    disposable probe schema and skip creating it there - so the probe would
    prove a migration that is not the one live gets. This defect was found and
    fixed before 0022 was applied; the test keeps it fixed."""
    code = " ".join(_migration_code().lower().split())
    assert "relnamespace = current_schema()::regnamespace" in code, (
        "The FK-existence guard must be scoped to current_schema()."
    )


def test_the_migration_is_schema_agnostic():
    for line in _migration_code().splitlines():
        assert "rigid_foam." not in line, (
            f"Migration hard-codes a schema name: {line.strip()!r}. 0021 was rejected for this."
        )


# ---------------------------------------------------------------------------
# Section 2 - the model
# ---------------------------------------------------------------------------

def test_production_runs_carries_the_snapshot_column():
    """Replaces test_production_runs_do_not_carry_a_unit_yet in
    tests/test_r3_production_unit_inventory.py, deleted in this work package
    per its own docstring's instruction."""
    cols = {c.name: c for c in db.ProductionRun.__table__.columns}
    assert "production_unit_id" in cols, "production_runs.production_unit_id is missing"
    col = cols["production_unit_id"]
    assert col.nullable, (
        "The snapshot is nullable on purpose: a run may be created against equipment "
        "with no unit, it just may not be completed."
    )
    targets = {fk.target_fullname for fk in col.foreign_keys}
    assert targets == {"production_units.id"}, f"Unexpected FK target: {targets}"


def test_the_machine_relationship_is_still_the_source():
    assert "production_unit_id" in {c.name for c in db.Machine.__table__.columns}, (
        "The run snapshot is resolved from machines.production_unit_id - removing it "
        "would leave the snapshot with nothing to resolve from."
    )


# ---------------------------------------------------------------------------
# Section 3 - the two helpers, directly
# ---------------------------------------------------------------------------

def test_resolve_returns_the_machines_unit(chain_with_unit):
    session = db.get_session()
    assert resolve_production_unit_id(session, chain_with_unit["machine_id"]) == chain_with_unit["unit_id"]
    session.close()


def test_resolve_returns_none_for_unassigned_equipment(chain_without_unit):
    session = db.get_session()
    assert resolve_production_unit_id(session, chain_without_unit["machine_id"]) is None
    session.close()


def test_resolve_returns_none_when_no_equipment_is_selected(chain_with_unit):
    session = db.get_session()
    assert resolve_production_unit_id(session, None) is None
    session.close()


def test_blocker_refuses_equipment_with_no_unit(chain_without_unit):
    session = db.get_session()
    message = run_completion_blocker(session, chain_without_unit["machine_id"], None)
    assert message, "Completion must be refused for equipment with no Production Unit / Cell"
    assert "Production Unit / Cell" in message
    assert chain_without_unit["machine_name"] in message, (
        "The message must name the equipment - the user has to know which one to go and assign."
    )
    session.close()


def test_blocker_refuses_a_run_with_no_equipment(chain_with_unit):
    session = db.get_session()
    assert run_completion_blocker(session, None, None), (
        "A run with no Equipment / Machine cannot be completed"
    )
    session.close()


def test_blocker_refuses_a_missing_snapshot(chain_with_unit):
    """Equipment resolves, but the run carries nothing. Different sentence,
    different cause: this is a stale run rather than a master-data gap."""
    session = db.get_session()
    message = run_completion_blocker(session, chain_with_unit["machine_id"], None)
    assert message and "carries no Production Unit / Cell" in message
    session.close()


def test_blocker_refuses_a_stale_snapshot(chain_with_unit):
    session = db.get_session()
    message = run_completion_blocker(
        session, chain_with_unit["machine_id"], chain_with_unit["unit_id"] + 9999,
    )
    assert message and "no longer matches" in message
    session.close()


def test_blocker_allows_a_consistent_run(chain_with_unit):
    session = db.get_session()
    assert run_completion_blocker(
        session, chain_with_unit["machine_id"], chain_with_unit["unit_id"],
    ) is None, "A run whose snapshot matches its equipment must be completable"
    session.close()


def test_the_four_refusals_say_four_different_things(chain_with_unit):
    """A guard that returns the same sentence for every cause sends the user to
    the wrong page. Cheap to assert, and it fails the moment someone collapses
    the branches into one message.

    Both machines are built inside ONE fixture on purpose. _build_chain drops
    and recreates the schema, so asking for chain_with_unit and
    chain_without_unit in the same test leaves the first one's ids pointing at
    rows the second one deleted - which is how this test first "passed" with
    two messages instead of four."""
    ids = chain_with_unit
    session = db.get_session()
    spare = db.Machine(
        plant_id=ids["plant_id"], name="WP4 Spare (no unit)",
        production_method_id=ids["method_id"], active=True, production_unit_id=None,
    )
    session.add(spare); session.commit()
    assert spare.production_unit_id is None

    messages = {
        run_completion_blocker(session, None, None),
        run_completion_blocker(session, spare.id, None),
        run_completion_blocker(session, ids["machine_id"], None),
        run_completion_blocker(session, ids["machine_id"], ids["unit_id"] + 9999),
    }
    session.close()
    assert len(messages) == 4, f"Refusal messages are not distinct: {messages}"


# ---------------------------------------------------------------------------
# Section 4 - the EDIT transition, through the real form
#
# Charlie's requirement in its own words: "assigns it to an editable run, and
# then attempts to set that run to Completed. The transition must be refused."
# ---------------------------------------------------------------------------

def _open_edit(ids):
    at = _run(session_state={"runs_overview_table": {"selection": {"rows": [0], "columns": []}}})
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"
    assert at.session_state["pr_selected_run_id"] == ids["run_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded run"
    )
    return at


def _submit_completed(at, ids):
    status_sb = next(sb for sb in at.selectbox if sb.key == f"edit_run_status_{ids['run_id']}")
    status_sb.set_value("Completed")
    save = next(
        b for b in at.button
        if b.key == f"FormSubmitter:edit_run_form_{ids['run_id']}-Save changes"
    )
    save.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving the production run: {at.exception}"
    return at


def _stored(run_id):
    session = db.get_session()
    run = session.get(db.ProductionRun, run_id)
    state = (run.status, run.production_unit_id)
    session.close()
    return state


def test_edit_to_completed_is_refused_without_a_unit(chain_without_unit):
    ids = chain_without_unit
    at = _submit_completed(_open_edit(ids), ids)

    status, unit_id = _stored(ids["run_id"])
    assert status is None, (
        "The run reached Completed on equipment with no Production Unit / Cell. "
        "The transition must be refused, not recorded."
    )
    assert unit_id is None
    errors = [str(e.value) for e in at.error]
    assert any("not assigned to a Production Unit / Cell" in e for e in errors), (
        f"No refusal message was shown to the user. Errors on screen: {errors}"
    )


def test_edit_to_completed_is_allowed_with_a_unit(chain_with_unit):
    ids = chain_with_unit
    at = _submit_completed(_open_edit(ids), ids)

    status, unit_id = _stored(ids["run_id"])
    assert status == "Completed", (
        "Equipment resolving to a Production Unit / Cell must be completable - a guard "
        "that refuses everything is not a guard."
    )
    assert unit_id == ids["unit_id"], "The completed run must carry its unit snapshot"


def test_a_non_completed_edit_is_never_blocked(chain_without_unit):
    """The guard is at the transition to Completed and nowhere else. Equipment
    with no unit must still be usable for planning and running - blocking the
    whole page would push users to invent a unit to get their work saved."""
    ids = chain_without_unit
    at = _open_edit(ids)
    status_sb = next(sb for sb in at.selectbox if sb.key == f"edit_run_status_{ids['run_id']}")
    status_sb.set_value("In Progress")
    notes = next(t for t in at.text_area if t.key == f"edit_run_notes_{ids['run_id']}")
    notes.set_value("WP4 in-progress edit")
    next(
        b for b in at.button
        if b.key == f"FormSubmitter:edit_run_form_{ids['run_id']}-Save changes"
    ).click()
    at.run()
    assert not at.exception, f"Unhandled exception: {at.exception}"

    session = db.get_session()
    run = session.get(db.ProductionRun, ids["run_id"])
    assert run.status == "In Progress", "A non-Completed edit was blocked"
    assert run.notes == "WP4 in-progress edit"
    session.close()


# ---------------------------------------------------------------------------
# Section 5 - the CREATE transition, through the real form
#
# "creates or uses Equipment / Machine with no Production Unit / Cell". A run
# may be CREATED against unassigned equipment - it may not be created straight
# into Completed, which would walk around the edit guard entirely.
# ---------------------------------------------------------------------------

def _create_with_status(ids, status_value):
    at = _run()
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"
    machine_sb = next(sb for sb in at.selectbox if sb.key == "create_run_machine")
    machine_display = next(opt for opt in machine_sb.options if ids["machine_name"] in str(opt))
    machine_sb.set_value(machine_display)
    at.run()
    status_sb = next(sb for sb in at.selectbox if sb.key == "create_run_status")
    status_sb.set_value(status_value)
    next(b for b in at.button if b.label == "Save production run").click()
    at.run()
    assert not at.exception, f"Unhandled exception creating a production run: {at.exception}"
    return at


def _created_after(ids):
    session = db.get_session()
    rows = (
        session.query(db.ProductionRun)
        .filter(db.ProductionRun.foam_grade_id == ids["grade_id"])
        .filter(db.ProductionRun.id != ids["run_id"])
        .all()
    )
    out = [(r.status, r.production_unit_id) for r in rows]
    session.close()
    return out


def test_create_as_completed_is_refused_without_a_unit(chain_without_unit):
    ids = chain_without_unit
    at = _create_with_status(ids, "Completed")
    assert _created_after(ids) == [], (
        "A run was created straight into Completed on equipment with no Production "
        "Unit / Cell, which walks around the edit guard."
    )
    errors = [str(e.value) for e in at.error]
    assert any("not assigned to a Production Unit / Cell" in e for e in errors), (
        f"No refusal message was shown. Errors on screen: {errors}"
    )


def test_create_as_completed_is_allowed_with_a_unit(chain_with_unit):
    ids = chain_with_unit
    _create_with_status(ids, "Completed")
    created = _created_after(ids)
    assert created == [("Completed", ids["unit_id"])], (
        f"Expected one completed run carrying its unit snapshot, got {created}"
    )


def test_create_without_completing_is_allowed_and_snapshots_nothing(chain_without_unit):
    ids = chain_without_unit
    _create_with_status(ids, "Planned")
    created = _created_after(ids)
    assert created == [("Planned", None)], (
        f"Creating a planned run on unassigned equipment must be allowed, got {created}"
    )


# ---------------------------------------------------------------------------
# Section 6 - the mutation control
#
# Charlie: "Also run a mutation or equivalent negative control proving the
# failing fixture changes the expected outcome if the guard is removed or
# bypassed."
#
# The refusals above are only evidence if the SAME fixture reaches Completed
# once the guard is gone. Otherwise "refused" and "refused for some other
# reason the fixture happens to trip" are indistinguishable.
# ---------------------------------------------------------------------------

@pytest.fixture()
def guard_bypassed(monkeypatch):
    """Replaces the guard with one that never refuses. The page binds the name
    at module scope on every AppTest.run(), so this is what it calls."""
    calls = {"n": 0}

    def _never_blocks(session, machine_id, production_unit_id):
        calls["n"] += 1
        return None

    monkeypatch.setattr(helpers, "run_completion_blocker", _never_blocks)
    return calls


def test_the_bypass_actually_reaches_the_page(chain_without_unit, guard_bypassed):
    """Proves the mutation LANDS before any conclusion is drawn from it. A
    patch that the page never sees would make the control below pass for the
    wrong reason, and this project has already lost an afternoon to a mutation
    that silently never applied."""
    ids = chain_without_unit
    _submit_completed(_open_edit(ids), ids)
    assert guard_bypassed["n"] > 0, (
        "The page did not call the patched guard - the bypass never reached it, so "
        "the mutation control below would prove nothing."
    )


def test_mutation_control_edit_completes_once_the_guard_is_bypassed(chain_without_unit, guard_bypassed):
    ids = chain_without_unit
    _submit_completed(_open_edit(ids), ids)
    status, unit_id = _stored(ids["run_id"])
    assert status == "Completed", (
        "With the guard bypassed the same fixture still did not complete, so "
        "test_edit_to_completed_is_refused_without_a_unit is not evidence that the "
        "guard is what refuses it."
    )
    assert unit_id is None, (
        "And it completes carrying no unit - which is exactly the state the guard exists "
        "to prevent."
    )


def test_mutation_control_create_completes_once_the_guard_is_bypassed(chain_without_unit, guard_bypassed):
    ids = chain_without_unit
    _create_with_status(ids, "Completed")
    created = _created_after(ids)
    assert created == [("Completed", None)], (
        f"With the guard bypassed the create path must produce the very row the guard "
        f"prevents. Got {created}."
    )


@pytest.fixture()
def resolution_bypassed(monkeypatch):
    """The other half: leave the guard in place but break resolution, so the
    snapshot is never found. The positive tests must fail under this."""
    monkeypatch.setattr(helpers, "resolve_production_unit_id", lambda session, machine_id: None)


def test_mutation_control_the_positive_case_fails_without_resolution(chain_with_unit, resolution_bypassed):
    ids = chain_with_unit
    at = _submit_completed(_open_edit(ids), ids)
    status, _ = _stored(ids["run_id"])
    assert status != "Completed", (
        "With resolution broken the positive case still completed, so "
        "test_edit_to_completed_is_allowed_with_a_unit does not depend on the unit "
        "actually being resolved."
    )
    assert at.error, "Breaking resolution should surface a refusal, not fail silently"
