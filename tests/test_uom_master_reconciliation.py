"""Controlled UOM reconciliation (2026-08-18) - the standing guard on the
unit master, and evidence for the reconciliation itself.

Background. Phase 8 Wave A closed a three-way identifier collision for
kilogram, minute and bar. Scoping the separate reconciliation the ruling
reserved showed the collision was a symptom: most of the canonical unit
master had never been loaded into the live rigid_foam schema, so every work
package that needed a plain unit found nothing to link to and either left
the link NULL (Wave A's five settings) or created its own row (WP7 Phase 3's
UOM-038/039/040/041 block). Two different symptoms, one cause.

The reconciliation loaded the full canonical master, re-pointed seven
Process Setting definitions, and retired the four WP7 Phase 3 rows.

Live implementation this file's fixture mirrors (Supabase project
aazkdsqpytjciiqtvnfj, rigid_foam schema, 2026-08-18):

1. 26 canonical rows seeded - 21 transcribed from the Phase 1 / WP2
   technical master sheet 03_UOM, and the 5 remaining "New canonical" rows
   from the Phase 1 UOM Governance Correction Register v1 sheet
   02_Canonical_UOM. units_of_measure went 21 -> 47 rows.

   The WP2 sheet's UOM-023 php and UOM-024 wt% were deliberately not
   seeded: register decisions UOM-D-001 and UOM-D-002 map those meanings
   onto UOM-030 and UOM-031, which are already live, and say not to create
   the source identifiers as separate rows. The WP2 sheet's UOM-030 "index
   unit" and UOM-031 "class" were likewise not seeded, because decision
   UOM-D-005 moved those meanings to UOM-101 and UOM-102, also already live.

2. Seven Process Setting definitions re-pointed - PS-079 to UOM-010,
   PS-078 to UOM-007, PS-008 to UOM-009, PS-009 to UOM-029, PS-025 to
   UOM-006, and PS-023 and PS-024 to UOM-100 from unit_id NULL.

3. UOM-038, UOM-039, UOM-040 and UOM-041 deleted after a direct check that
   all seven foreign-key columns able to reference units_of_measure held
   zero references to them. Final count 43 rows.

Why the duplicate guard below is not decoration. legacy_migration's
ensure_environment_outcome_definitions() resolves a setting's unit by
building {u.symbol: u} over the whole table. Before this reconciliation
that dictionary silently discarded a row whenever two rows shared a symbol,
which is exactly the state UOM-041 "%" and the unseeded canonical UOM-006
"%" would have produced the moment the canonical row was loaded. Unique
symbols are a correctness precondition for that lookup, not tidiness.

Usage: python -m pytest tests/test_uom_master_reconciliation.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
import legacy_migration as lm


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


# The controlled unit master as it stands live after the reconciliation.
# (controlled_id, symbol, name, quantity_type)
CONTROLLED_UOM_MASTER = [
    ('UOM-001', 'kg/m3', 'kilogram per cubic metre', 'Density'),
    ('UOM-002', 'W/(m.K)', 'Watt per metre-Kelvin', 'Thermal conductivity'),
    ('UOM-003', 'm2.K/W', 'Square metre-Kelvin per Watt', 'Thermal resistance'),
    ('UOM-004', 'kPa', 'kilopascal', 'Stress/pressure'),
    ('UOM-005', 'MPa', 'megapascal', 'Modulus/pressure'),
    ('UOM-006', '%', 'percent', 'Relative quantity'),
    ('UOM-007', 'mm', 'millimetre', 'Length'),
    ('UOM-008', 'mm/m', 'millimetre per metre', 'Flatness/bow'),
    ('UOM-009', 'degC', 'degree Celsius', 'Temperature'),
    ('UOM-010', 's', 'second', 'Time'),
    ('UOM-011', 'min', 'minute', 'Time'),
    ('UOM-012', 'h', 'hour', 'Time'),
    ('UOM-013', 'd', 'day', 'Time'),
    ('UOM-014', 'g', 'gram', 'Mass'),
    ('UOM-015', 'kg', 'kilogram', 'Mass'),
    ('UOM-016', 'g/s', 'gram per second', 'Mass flow'),
    ('UOM-017', 'kg/min', 'kilogram per minute', 'Mass flow'),
    ('UOM-018', 'L/min', 'litre per minute', 'Volume flow'),
    ('UOM-019', 'bar', 'bar', 'Pressure'),
    ('UOM-020', 'rpm', 'revolution per minute', 'Rotational speed'),
    ('UOM-021', 'ratio', 'ratio', 'Dimensionless'),
    ('UOM-022', 'index', 'index', 'Dimensionless'),
    ('UOM-025', 'pc', 'piece', 'Count'),
    ('UOM-026', 'panel', 'panel', 'Count'),
    ('UOM-027', 'm2', 'square metre', 'Area'),
    ('UOM-028', 'm3', 'cubic metre', 'Volume'),
    ('UOM-029', '%RH', 'relative humidity percent', 'Humidity'),
    ('UOM-030', 'php', 'Parts per hundred polyol blend', 'Formulation basis'),
    ('UOM-031', 'wt%', 'Weight percent', 'Formulation basis'),
    ('UOM-032', 'N/mm', 'newton per millimetre', 'Peel force per width'),
    ('UOM-033', 'g/(m2.d)', 'gram per square metre per day', 'Water-vapour transmission'),
    ('UOM-034', 'count/basis', 'count per basis units', 'Normalized defect rate'),
    ('UOM-035', 'mm/s', 'millimetre per second', 'Flow velocity indicator'),
    ('UOM-036', 'degC/min', 'degree Celsius per minute', 'Temperature rise rate'),
    ('UOM-037', 'm3/kg', 'cubic metre per kilogram', 'Volume yield'),
    ('UOM-100', 'kg/kg', 'Mass ratio', 'Ratio basis'),
    ('UOM-101', 'index unit', 'Fire index unit', 'Fire index'),
    ('UOM-102', 'class', 'Class', 'Classification'),
    ('UOM-103', 'board', 'board', 'Count'),
    ('UOM-104', 'cycle', 'cycle', 'Count'),
    ('UOM-105', 'shot', 'shot', 'Count'),
    ('UOM-106', 'm', 'linear metre', 'Length'),
    ('UOM-107', 'L/L', 'volume ratio', 'Ratio basis'),
]

# Identifiers the reconciliation retired. They must never come back.
RETIRED_IDS = ["UOM-038", "UOM-039", "UOM-040", "UOM-041"]

# Source identifiers the governance register maps onto a canonical row
# rather than creating - decisions UOM-D-001, UOM-D-002 and UOM-D-005.
NEVER_SEED_IDS = ["UOM-023", "UOM-024"]

# The seven settings the reconciliation re-pointed.
# PS controlled_id -> (name, controlled UOM, symbol)
RECONCILED_SETTINGS = {
    "PS-008": ("Ambient temperature", "UOM-009", "degC"),
    "PS-009": ("Relative humidity", "UOM-029", "%RH"),
    "PS-023": ("Set mass ratio A:B", "UOM-100", "kg/kg"),
    "PS-024": ("Actual mass ratio A:B", "UOM-100", "kg/kg"),
    "PS-025": ("Ratio deviation", "UOM-006", "%"),
    "PS-078": ("Foam height", "UOM-007", "mm"),
    "PS-079": ("Rise time", "UOM-010", "s"),
}


@pytest.fixture()
def master_fixture():
    """Rebuilds the reconciled live shape: the full 43-row controlled
    master and the seven re-pointed Process Setting definitions."""
    db.init_db()
    _reset_schema()
    session = db.get_session()

    units = {}
    for controlled_id, symbol, name, quantity_type in CONTROLLED_UOM_MASTER:
        row = db.UnitOfMeasure(
            controlled_id=controlled_id, symbol=symbol, name=name,
            quantity_type=quantity_type,
            sort_order=int(controlled_id.split("-")[1]),
        )
        session.add(row)
        units[controlled_id] = row
    session.flush()

    for ps_id, (name, uom_id, _symbol) in RECONCILED_SETTINGS.items():
        session.add(db.ProcessSettingDefinition(
            controlled_id=ps_id, name=name, unit_id=units[uom_id].id,
        ))
    session.commit()

    yield session, units
    session.close()


# ---------------------------------------------------------------------------
# The standing guard
# ---------------------------------------------------------------------------

def test_no_two_rows_share_a_controlled_id(master_fixture):
    session, _units = master_fixture
    ids = [r.controlled_id for r in session.query(db.UnitOfMeasure).all()]
    assert len(ids) == len(set(ids))


def test_no_two_rows_share_a_symbol(master_fixture):
    """A correctness precondition for legacy_migration's symbol-keyed unit
    lookup, not a tidiness rule - see this module's docstring."""
    session, _units = master_fixture
    symbols = [r.symbol for r in session.query(db.UnitOfMeasure).all()]
    duplicates = sorted({s for s in symbols if symbols.count(s) > 1})
    assert not duplicates, f"symbols carried by more than one controlled row: {duplicates}"


def test_no_two_rows_share_a_meaning(master_fixture):
    """Same preferred name under two identifiers is the condition that
    produced this reconciliation in the first place."""
    session, _units = master_fixture
    names = [(r.name or "").strip().lower() for r in session.query(db.UnitOfMeasure).all()]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, f"meanings carried by more than one controlled row: {duplicates}"


def test_symbol_lookup_resolves_every_row(master_fixture):
    """Builds the same {symbol: row} dictionary legacy_migration builds and
    proves nothing is lost to a collision."""
    session, _units = master_fixture
    rows = session.query(db.UnitOfMeasure).all()
    by_symbol = {r.symbol: r for r in rows}
    assert len(by_symbol) == len(rows)


@pytest.mark.parametrize("controlled_id,symbol,name,quantity_type", CONTROLLED_UOM_MASTER)
def test_every_master_row_is_present_and_exact(master_fixture, controlled_id, symbol, name, quantity_type):
    session, _units = master_fixture
    row = session.query(db.UnitOfMeasure).filter_by(controlled_id=controlled_id).one()
    assert row.symbol == symbol
    assert row.name == name
    assert row.quantity_type == quantity_type


def test_master_holds_no_rows_outside_the_register(master_fixture):
    """The register and the live table must agree in both directions. An
    unexpected identifier here is a work package that added a row without
    reissuing the register."""
    session, _units = master_fixture
    live = {r.controlled_id for r in session.query(db.UnitOfMeasure).all()}
    expected = {row[0] for row in CONTROLLED_UOM_MASTER}
    assert live == expected


# ---------------------------------------------------------------------------
# The reconciliation itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("retired_id", RETIRED_IDS)
def test_retired_identifiers_are_absent(master_fixture, retired_id):
    session, _units = master_fixture
    assert session.query(db.UnitOfMeasure).filter_by(controlled_id=retired_id).first() is None


@pytest.mark.parametrize("source_id", NEVER_SEED_IDS)
def test_register_mapped_source_ids_are_never_created(master_fixture, source_id):
    """UOM-023 php and UOM-024 wt% map onto UOM-030 and UOM-031 per the
    register's decisions, and must not exist as parallel rows."""
    session, _units = master_fixture
    assert session.query(db.UnitOfMeasure).filter_by(controlled_id=source_id).first() is None


@pytest.mark.parametrize("ps_id", sorted(RECONCILED_SETTINGS))
def test_reconciled_setting_resolves_to_its_controlled_unit(master_fixture, ps_id):
    session, _units = master_fixture
    name, uom_id, symbol = RECONCILED_SETTINGS[ps_id]

    definition = session.query(db.ProcessSettingDefinition).filter_by(controlled_id=ps_id).one()
    assert definition.name == name
    assert definition.unit is not None, f"{ps_id} must carry a controlled unit"
    assert definition.unit.controlled_id == uom_id
    assert definition.unit.symbol == symbol


def test_relative_humidity_uses_the_dedicated_humidity_unit(master_fixture):
    """PS-009 carries %RH, not plain percent. WP2 sheet 07 gave %RH as its
    default unit and the live row's own description already said so - only
    the unit link disagreed, because UOM-029 had never been loaded."""
    session, _units = master_fixture
    definition = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-009").one()
    assert definition.unit.controlled_id == "UOM-029"
    assert definition.unit.quantity_type == "Humidity"

    percent = session.query(db.UnitOfMeasure).filter_by(controlled_id="UOM-006").one()
    assert definition.unit_id != percent.id


def test_both_mass_ratio_settings_share_one_controlled_row(master_fixture):
    """PS-023 and PS-024 are the two operands of the ratio deviation
    calculation, so they must be expressed in the same unit."""
    session, _units = master_fixture
    set_ratio = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-023").one()
    actual_ratio = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-024").one()

    assert set_ratio.unit_id == actual_ratio.unit_id
    assert set_ratio.unit.controlled_id == "UOM-100"


# ---------------------------------------------------------------------------
# legacy_migration seeds canonical identifiers, not the retired block
# ---------------------------------------------------------------------------

def test_legacy_migration_seeds_only_canonical_identifiers():
    seeded = {row["controlled_id"] for row in lm.ENVIRONMENT_OUTCOME_UOMS}
    assert seeded == {"UOM-007", "UOM-009", "UOM-010", "UOM-029"}
    assert not seeded & set(RETIRED_IDS)


def test_legacy_migration_maps_humidity_to_the_dedicated_unit():
    humidity = lm.ENVIRONMENT_OUTCOME_FIELD_MAP["ambient_humidity_pct"]
    assert humidity["controlled_id"] == "PS-009"
    assert humidity["unit_symbol"] == "%RH"


def test_legacy_migration_creates_no_duplicates_against_the_reconciled_master(master_fixture):
    """Running the WP7 Phase 3 migration against the reconciled table must
    be a no-op, and must not resurrect the retired block."""
    session, _units = master_fixture

    created = lm.ensure_environment_outcome_uoms(session)
    session.commit()
    assert created == 0

    live = {r.controlled_id for r in session.query(db.UnitOfMeasure).all()}
    assert live == {row[0] for row in CONTROLLED_UOM_MASTER}


def test_legacy_migration_is_still_idempotent_from_empty():
    """Against a table with none of its four rows, it creates them once and
    then stops - the original WP7 Phase 3 guarantee, preserved."""
    db.init_db()
    _reset_schema()
    session = db.get_session()

    assert lm.ensure_environment_outcome_uoms(session) == 4
    session.commit()
    assert lm.ensure_environment_outcome_uoms(session) == 0
    session.commit()

    seeded = {r.controlled_id for r in session.query(db.UnitOfMeasure).all()}
    assert seeded == {"UOM-007", "UOM-009", "UOM-010", "UOM-029"}
    session.close()
