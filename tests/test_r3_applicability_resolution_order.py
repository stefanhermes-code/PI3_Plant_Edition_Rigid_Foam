"""R3 - process-setting applicability gains Application Area and Production
Unit / Cell scope (migration 0024).

Charlie's R3 handover v3, section 3: "Process-setting applicability: Resolution
order is Machine, then Production Unit / Cell, then Application Area, then
Global."

TWO MIGRATIONS, AND WHY THEY ARE SEPARATE

0024 is the schema half: the two scope columns and the widened uniqueness
index. 0026 is the conversion: 37 method-only rows to Application Area
defaults, 9 machine-plus-method rows to Machine + Application Area, 4 global
rows untouched.

They are separate artifacts because they fail differently. A schema change that
goes wrong is caught by its own exit checks; a data conversion that goes wrong
is caught by comparing behaviour before and after, which needs the schema to
already exist. 0024 also carries an exit check refusing a half-converted state,
which is what made it safe to apply the two at different times.

    PM-100  Discontinuous Panel & Board Production   ->  APP-210
    PM-800  Discontinuous Appliance & Cavity Foaming ->  APP-310

Each plant running the method has exactly one Product Grade and that grade
carries the Application Area. This is test data; a real deployment derives its
own mapping the same way.

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
    """The legacy tier still resolves for a caller that supplies nothing else.

    No live row uses it after 0026, but the column and the tier remain until
    Production Method retirement, and a tier nothing exercises is a tier that
    quietly stops working."""
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


# ---------------------------------------------------------------------------
# Section 4 - the conversion (0026), and that it changed no behaviour
#
# Charlie asked for "before/after behaviour evidence for each of the 9
# dual-scope rules". Row counts are not that evidence: a conversion that moved
# every row to the wrong Application Area would produce identical counts. What
# follows compares what the RESOLVER RETURNS, before shape against after shape.
# ---------------------------------------------------------------------------

CONVERSION = "0026_r3_applicability_repoint_to_application_area.sql"


def _conversion_code():
    sql = open(os.path.join(MIGRATIONS_DIR, CONVERSION), encoding="utf-8").read()
    return "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))


@pytest.fixture()
def before_and_after():
    """The same rule set twice: once scoped the old way (Method, and Machine +
    Method) and once the new way (Application Area, and Machine + Application
    Area), on two independent definitions so neither can contest the other.

    Built side by side rather than by mutating one into the other, because a
    fixture that runs the conversion to produce its own "after" state proves
    the conversion agrees with itself and nothing more."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CONV Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CONV Plant {u}")
    session.add(plant); session.flush()
    area = db.Application(controlled_id=f"APP-{u[:3]}", name=f"Area {u}",
                          pu_material_family="Rigid")
    session.add(area); session.flush()
    method = db.ProductionMethod(controlled_id=f"PM-{u[:3]}", name=f"Method {u}")
    session.add(method); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"Machine {u}",
                         production_method_id=method.id)
    session.add(machine); session.flush()

    old_def = db.ProcessSettingDefinition(name=f"Old-shape {u}", active=True, sort_order=10)
    new_def = db.ProcessSettingDefinition(name=f"New-shape {u}", active=True, sort_order=20)
    session.add_all([old_def, new_def]); session.flush()

    rows = {}
    for label, definition, kwargs in (
        ("old_default", old_def, {"production_method_id": method.id}),
        ("old_machine", old_def, {"production_method_id": method.id, "machine_id": machine.id}),
        ("new_default", new_def, {"application_id": area.id}),
        ("new_machine", new_def, {"application_id": area.id, "machine_id": machine.id}),
    ):
        row = db.ProcessSettingApplicability(
            setting_definition_id=definition.id, active=True, **kwargs
        )
        session.add(row); session.flush()
        rows[label] = row.id

    session.commit()
    ids = {"area_id": area.id, "method_id": method.id, "machine_id": machine.id,
           "old_def": old_def.id, "new_def": new_def.id, "rows": rows}
    session.close()
    return ids


def _winner_for(session, definition_id, **scope):
    results = analytics.eligible_process_settings(session, **scope)
    matching = [a for d, a in results if d.id == definition_id]
    return matching[0].id if matching else None


def test_the_default_tier_behaves_the_same_after_conversion(before_and_after):
    """A run in the Application Area resolves the converted default exactly as
    a run on the Production Method resolved the old one."""
    ids = before_and_after
    session = db.get_session()
    old = _winner_for(session, ids["old_def"], production_method_id=ids["method_id"])
    new = _winner_for(session, ids["new_def"], application_id=ids["area_id"])
    session.close()
    assert old == ids["rows"]["old_default"]
    assert new == ids["rows"]["new_default"], (
        "The converted Application Area default does not resolve where the Method "
        "default used to."
    )


def test_the_nine_dual_scope_rules_keep_their_dual_condition(before_and_after):
    """Machine + Method became Machine + Application Area. Both halves must
    still be required: the rule applies on that machine, and not on another."""
    ids = before_and_after
    session = db.get_session()

    old = _winner_for(session, ids["old_def"], production_method_id=ids["method_id"],
                      machine_id=ids["machine_id"])
    new = _winner_for(session, ids["new_def"], application_id=ids["area_id"],
                      machine_id=ids["machine_id"])
    assert old == ids["rows"]["old_machine"]
    assert new == ids["rows"]["new_machine"], (
        "The converted Machine + Application Area rule does not win on its own machine."
    )

    # And the other half of "dual": without the machine, the machine-scoped row
    # must not apply. The definition falls back to its default tier.
    assert _winner_for(session, ids["new_def"],
                       application_id=ids["area_id"]) == ids["rows"]["new_default"]
    session.close()


def test_a_converted_rule_does_not_apply_outside_its_application_area(before_and_after):
    """The conversion's real risk. A default that applied to one method must
    not become a default that applies everywhere."""
    ids = before_and_after
    session = db.get_session()
    assert _winner_for(session, ids["new_def"]) is None, (
        "The converted Application Area default applies to a run with no Application "
        "Area at all - it has become global."
    )
    session.close()


# ---------------------------------------------------------------------------
# Section 5 - the conversion artifact
# ---------------------------------------------------------------------------

def test_the_conversion_exists():
    assert os.path.exists(os.path.join(MIGRATIONS_DIR, CONVERSION)), f"{CONVERSION} is missing"


def test_the_conversion_maps_by_controlled_id_not_by_row_id():
    """Hard-coded ids are the reason a migration can pass on a probe and point
    at the wrong record live. The mapping is looked up by controlled_id, which
    is also what makes the artifact readable."""
    code = _conversion_code()
    for controlled in ("'PM-100'", "'PM-800'", "'APP-210'", "'APP-310'"):
        assert controlled in code, f"The mapping does not name {controlled}"
    assert "application_id = " in code and "ap.id" in code, (
        "The Application Area is not resolved by lookup."
    )


def test_the_conversion_clears_the_legacy_method_reference():
    """A row keeping both would apply only where method AND area match - a
    Method + Application Area rule, not the inherited default Charlie asked
    for."""
    code = " ".join(_conversion_code().split())
    assert "production_method_id = null" in code.lower(), (
        "Converted rows keep their Production Method reference."
    )


def test_the_conversion_writes_no_production_unit_reference():
    """Charlie: "Do not fan the 37 Application Area defaults out across every
    Production Unit." A unit row is supposed to mean "this line differs", and
    it cannot mean that if every unit has one."""
    code = _conversion_code().lower()
    assert "set production_unit_id" not in code
    assert "0026 writes none" in _conversion_code(), (
        "The exit check asserting no unit reference was written has been removed."
    )


def test_the_conversion_refuses_a_method_with_no_destination():
    """The check that stops a half conversion. Proved non-vacuous on the probe
    by planting a PM-200 row, which fired it."""
    code = _conversion_code()
    assert "no Application Area destination" in code


def test_the_conversion_keeps_the_row_count():
    code = _conversion_code()
    assert "must not add or remove rows" in code, (
        "Nothing asserts that a re-pointing did not become a rewrite."
    )
    assert "insert into process_setting_applicabilities" not in code.lower()
    assert "delete from process_setting_applicabilities" not in code.lower()


def test_the_conversion_leaves_the_global_rows_alone():
    """The 4 global rows are absent from every WHERE clause rather than
    excluded by a condition somebody could edit. Asserted by the exit check
    that counts them."""
    code = _conversion_code()
    assert "Expected exactly 4 global rows after conversion" in code


def test_the_conversion_is_schema_agnostic():
    for line in _conversion_code().splitlines():
        assert "rigid_foam." not in line, f"Migration hard-codes a schema name: {line.strip()!r}"
