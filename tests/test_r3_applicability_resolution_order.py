"""R3 - process-setting applicability gains Application Area and Production
Unit / Cell scope (migration 0024).

Charlie's R3 handover v3, section 3: "Process-setting applicability: Resolution
order is Machine, then Production Unit / Cell, then Application Area, then
Global."

WHAT THIS WORK PACKAGE DELIBERATELY DOES NOT DO

It moves no rows. Converting the 37 method-only rows to Application Area
defaults needs an Application Area destination for every legacy Production
Method, and 43 of the 50 live rows belong to PM-800 at PTU Korat, whose master
data is still being verified. Plan v5 R3-WP1 says what to do with that:
"unresolved master-data details are returned as data issues before write."

Converting the 7 rows that CAN be evidenced and leaving 43 would be worse than
converting none - the resolver would then have to arbitrate between the two
tiers on live data, on rows nobody had checked. So the schema and the
resolution order land first, every live row keeps resolving through the legacy
Method tier exactly as before, and migration 0024 carries an exit check that
refuses a half-converted state.

WHY THE LEGACY TIER SITS WHERE IT DOES

Machine (4) > Production Unit / Cell (3) > Application Area (2) > legacy
Production Method (1) > Global (0). Method sits directly below the tier that
REPLACES it, so a row converted from Method to Application Area can only ever
win more, never less. Put it above Application Area and a re-pointing migration
would silently change which rule wins - the one thing it must not do.

Usage: python -m pytest tests/test_r3_applicability_resolution_order.py -v
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import analytics
import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(APP_DIR, "migrations")
MIGRATION = "0024_r3_applicability_area_and_unit_scope.sql"


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def _migration_code():
    sql = open(os.path.join(MIGRATIONS_DIR, MIGRATION), encoding="utf-8").read()
    return "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))


@pytest.fixture()
def tiers():
    """ONE setting definition with a row at every tier, so precedence is
    observable rather than assumed. Five rows for one definition is not a
    realistic configuration and that is the point - a fixture that cannot
    produce a contest cannot show which tier wins it."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"PSA Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"PSA Plant {u}")
    session.add(plant); session.flush()
    area = db.Application(controlled_id=f"APP-{u[:3]}", name=f"Area {u}",
                          pu_material_family="Rigid")
    other_area = db.Application(controlled_id=f"APX-{u[:3]}", name=f"Other Area {u}",
                                pu_material_family="Rigid")
    session.add_all([area, other_area]); session.flush()
    unit = db.ProductionUnit(plant_id=plant.id, controlled_id=f"PU-{u[:3]}", name=f"Cell {u}")
    session.add(unit); session.flush()
    method = db.ProductionMethod(controlled_id=f"PM-{u[:3]}", name=f"Method {u}")
    session.add(method); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"Machine {u}",
                         production_method_id=method.id, production_unit_id=unit.id)
    session.add(machine); session.flush()

    definition = db.ProcessSettingDefinition(
        name=f"Fill pressure {u}", parameter_category="Process Setting",
        active=True, sort_order=10,
    )
    session.add(definition); session.flush()

    rows = {}
    for label, kwargs in (
        ("global", {}),
        ("method", {"production_method_id": method.id}),
        ("area", {"application_id": area.id}),
        ("unit", {"production_unit_id": unit.id}),
        ("machine", {"machine_id": machine.id}),
    ):
        row = db.ProcessSettingApplicability(
            setting_definition_id=definition.id, active=True, **kwargs
        )
        session.add(row); session.flush()
        rows[label] = row.id

    session.commit()
    ids = {
        "definition_id": definition.id, "area_id": area.id, "other_area_id": other_area.id,
        "unit_id": unit.id, "method_id": method.id, "machine_id": machine.id,
        "rows": rows,
    }
    session.close()
    return ids


def _winner(session, ids, **scope):
    results = analytics.eligible_process_settings(session, **scope)
    matching = [(d, a) for d, a in results if d.id == ids["definition_id"]]
    assert len(matching) <= 1, "More than one row resolved for one definition"
    return matching[0][1].id if matching else None


# ---------------------------------------------------------------------------
# Section 0 - the fixture really contests every tier
# ---------------------------------------------------------------------------

def test_the_fixture_has_a_row_at_every_tier(tiers):
    session = db.get_session()
    rows = (session.query(db.ProcessSettingApplicability)
            .filter_by(setting_definition_id=tiers["definition_id"]).all())
    assert len(rows) == 5, f"Expected 5 competing rows, found {len(rows)}"
    scopes = {
        (r.machine_id is not None, r.production_unit_id is not None,
         r.application_id is not None, r.production_method_id is not None)
        for r in rows
    }
    assert len(scopes) == 5, f"The five rows do not occupy five distinct tiers: {scopes}"
    session.close()


# ---------------------------------------------------------------------------
# Section 1 - the resolution order, one tier removed at a time
#
# Each case supplies a scope and asserts WHICH ROW wins, not merely that
# something is returned. A test that only checks the count passes whatever the
# precedence does.
# ---------------------------------------------------------------------------

def test_machine_beats_everything(tiers):
    session = db.get_session()
    assert _winner(session, tiers, production_method_id=tiers["method_id"],
                   machine_id=tiers["machine_id"], application_id=tiers["area_id"],
                   production_unit_id=tiers["unit_id"]) == tiers["rows"]["machine"]
    session.close()


def test_unit_beats_area_and_below(tiers):
    session = db.get_session()
    assert _winner(session, tiers, production_method_id=tiers["method_id"],
                   application_id=tiers["area_id"],
                   production_unit_id=tiers["unit_id"]) == tiers["rows"]["unit"]
    session.close()


def test_area_beats_the_legacy_method_tier_and_global(tiers):
    """The ordering that makes the pending conversion safe. If Method beat
    Application Area, re-pointing a row from one to the other could change the
    winner - which a re-pointing migration must never do."""
    session = db.get_session()
    assert _winner(session, tiers, production_method_id=tiers["method_id"],
                   application_id=tiers["area_id"]) == tiers["rows"]["area"]
    session.close()


def test_the_legacy_method_tier_beats_global(tiers):
    session = db.get_session()
    assert _winner(session, tiers,
                   production_method_id=tiers["method_id"]) == tiers["rows"]["method"]
    session.close()


def test_global_wins_when_nothing_else_is_in_scope(tiers):
    session = db.get_session()
    assert _winner(session, tiers) == tiers["rows"]["global"]
    session.close()


def test_an_unrelated_area_does_not_inherit_another_areas_default(tiers):
    """Scope columns are filters, not hints. A run classified to a different
    Application Area must fall through to the tiers it does share."""
    session = db.get_session()
    assert _winner(session, tiers, production_method_id=tiers["method_id"],
                   application_id=tiers["other_area_id"]) == tiers["rows"]["method"]
    session.close()


def test_a_caller_that_knows_only_the_method_gets_the_old_behaviour(tiers):
    """The transition's safety property, stated as a test. Every live row is
    still a legacy Method or Global row, and every live caller passes a method,
    so nothing about today's resolution changed."""
    session = db.get_session()
    assert _winner(session, tiers,
                   production_method_id=tiers["method_id"]) == tiers["rows"]["method"]
    session.close()


# ---------------------------------------------------------------------------
# Section 2 - the model and the widened index
# ---------------------------------------------------------------------------

def test_the_scope_columns_exist_and_are_nullable():
    cols = {c.name: c for c in db.ProcessSettingApplicability.__table__.columns}
    for name, target in (("application_id", "applications.id"),
                         ("production_unit_id", "production_units.id")):
        assert name in cols, f"process_setting_applicabilities.{name} is missing"
        assert cols[name].nullable, f"{name} must be nullable - most rows do not use it"
        assert {fk.target_fullname for fk in cols[name].foreign_keys} == {target}


def test_the_unique_index_covers_every_scope_column():
    """Adding scope columns without widening this index reopens the defect it
    was created for: two active rows at one scope, winner decided arbitrarily
    (Charlie's WP7 Phase 1 closeout, item 2.1)."""
    index = next(
        (ix for ix in db.ProcessSettingApplicability.__table__.indexes
         if ix.name == "ix_psa_unique_active_scope"), None,
    )
    assert index is not None, "ix_psa_unique_active_scope is gone"
    assert index.unique
    rendered = " ".join(str(e) for e in index.expressions)
    for column in ("setting_definition_id", "application_id", "production_unit_id",
                   "production_method_id", "machine_id"):
        assert column in rendered, (
            f"{column} is not part of the active-scope uniqueness rule: {rendered}"
        )


def test_two_active_rows_at_the_same_new_scope_are_refused(tiers):
    """The index proved by behaviour rather than by reading its definition."""
    session = db.get_session()
    duplicate = db.ProcessSettingApplicability(
        setting_definition_id=tiers["definition_id"],
        application_id=tiers["area_id"], active=True,
    )
    session.add(duplicate)
    with pytest.raises(Exception):
        session.commit()
    session.rollback()
    session.close()


def test_the_same_definition_may_hold_one_row_per_tier(tiers):
    """The other direction: the widened index must not make the five-tier
    fixture itself illegal. It is built and committed by the fixture, so this
    test passing at all is the evidence - stated explicitly so a future
    tightening of the index fails here rather than somewhere confusing."""
    session = db.get_session()
    n = (session.query(db.ProcessSettingApplicability)
         .filter_by(setting_definition_id=tiers["definition_id"], active=True).count())
    assert n == 5
    session.close()


# ---------------------------------------------------------------------------
# Section 3 - the artifact
# ---------------------------------------------------------------------------

def test_migration_exists():
    assert os.path.exists(os.path.join(MIGRATIONS_DIR, MIGRATION)), f"{MIGRATION} is missing"


def test_the_migration_moves_no_rows():
    """0024 is the schema half. An UPDATE here would mean a conversion had been
    smuggled in beside a migration whose evidence says it moved nothing."""
    code = _migration_code().lower()
    assert "update process_setting_applicabilities" not in code, (
        "0024 contains an UPDATE of the applicability table. The row conversion is a "
        "separate artifact, pending the PTU Application Area destinations."
    )
    assert "0024 moves no rows" in _migration_code(), (
        "The exit check asserting that nothing was moved has been removed."
    )


def test_the_migration_rebuilds_the_index_in_the_same_artifact():
    code = " ".join(_migration_code().lower().split())
    assert "drop index if exists ix_psa_unique_active_scope" in code
    assert "create unique index ix_psa_unique_active_scope" in code
    for column in ("coalesce(application_id, -1)", "coalesce(production_unit_id, -1)"):
        assert column in code, f"The rebuilt index omits {column}"


def test_the_fk_existence_checks_are_scoped_to_the_current_schema():
    code = " ".join(_migration_code().lower().split())
    assert code.count("relnamespace = current_schema()::regnamespace") >= 2, (
        "Each FK guard must be scoped to current_schema() - unscoped, a probe finds the "
        "live constraint and skips creating its own."
    )


def test_the_migration_guards_against_a_half_finished_conversion():
    code = _migration_code()
    assert "have both an Application Area row and a legacy Method row active" in code, (
        "The transitional invariant check is missing. It is what makes stopping "
        "half-way a loud failure rather than a quiet one."
    )


def test_the_migration_is_schema_agnostic():
    for line in _migration_code().splitlines():
        assert "rigid_foam." not in line, f"Migration hard-codes a schema name: {line.strip()!r}"
