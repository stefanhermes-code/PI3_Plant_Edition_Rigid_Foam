"""Phase 8 Wave A correction #2 (2026-08-18) - direct evidence for Charlie's
controlled UOM ruling on the Wave A closeout return.

Charlie's ruling ("Phase8_PM800_WaveA_Correction_Review_and_UOM_Ruling_to_
JC.docx", 18 Aug 2026, section 2) resolved the three-way identifier
collision JC flagged: for these four physical units the Phase 1 / WP2
technical UOM master numbering is the active authority, superseding the
WP1 10_Units_Bases numbering where the two conflict. No fresh UOM-096..099
block. Existing live rows carrying conflicting legacy controlled IDs stay
intact pending a separate reconciliation.

Live implementation this file's fixture mirrors (run directly against
Supabase project aazkdsqpytjciiqtvnfj, rigid_foam schema, 2026-08-18):

1. `select * from rigid_foam.units_of_measure` before the write returned 17
   rows with no kilogram, minute, bar or kg/m3 row under any candidate ID -
   confirming JC's finding that the physical values were genuinely absent
   and only the controlled_id to assign them was in question.

2. Four rows seeded per the ruling, transcribed field-for-field from
   PI3_Rigid_Foam_Edition_WP2_Technical_Master_Data.xlsx sheet 03_UOM
   (cross-checked against PI3_Rigid_Foam_Phase_1_UOM_Governance_Correction_
   Register_v1.xlsx sheet 02_Canonical_UOM, which agrees on every field):
   UOM-001 kg/m3 Density, UOM-011 min Time, UOM-015 kg Mass, UOM-019 bar
   Pressure. Table went 17 -> 21 rows.

3. Five ProcessSettingDefinition rows linked off unit_id NULL: PS-076 ->
   UOM-001, PS-069 -> UOM-011, PS-074 -> UOM-015, PS-028 -> UOM-019,
   PS-051 -> UOM-019.

4. The live collision rule verified: UOM-038 second, UOM-039 millimetre,
   UOM-040 degree Celsius and UOM-041 percent were left byte-identical.
   Those four carry canonical-register meanings under non-canonical IDs
   (canonical UOM-010 / UOM-007 / UOM-009 / UOM-006 are all still free)
   and hold five Process Setting references between them, so they belong
   to the separate reconciliation the ruling reserves, not to Wave A.
   test_legacy_live_ids_retain_their_own_meaning below pins that
   separation so a later reconciliation cannot silently fold them in.

The ruling's second requirement - "the resulting ProcessParameterValue
snapshot cannot carry an independent conflicting unit" - is enforced by
db._process_parameter_value_enforce_controlled_unit, the WP7 Phase 1
before_insert/before_update mapper event. The tests here prove that hook
actually holds for these five settings, on both insert and update, and
that it degrades to None rather than to a stale symbol when a definition
carries no controlled unit.

Usage: python -m pytest tests/test_phase8_wave_a_uom_controlled_resolution.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


# The four rows the ruling makes authoritative, exactly as seeded live and
# exactly as they read in WP2 sheet 03_UOM.
# controlled_id -> (symbol, name, quantity_type, sort_order, unit_system)
_RULED_UOM = {
    "UOM-001": ("kg/m3", "kilogram per cubic metre", "Density", 1, "SI"),
    "UOM-011": ("min", "minute", "Time", 11, "SI accepted"),
    "UOM-015": ("kg", "kilogram", "Mass", 15, "SI"),
    "UOM-019": ("bar", "bar", "Pressure", 19, "SI accepted"),
}

# The five Process Setting definitions and the controlled UOM each must
# resolve to, per the ruling's section 3 completion list.
# PS controlled_id -> (name, expected UOM controlled_id)
_PS_TO_UOM = {
    "PS-076": ("Calculated core density", "UOM-001"),
    "PS-069": ("Cycle time", "UOM-011"),
    "PS-074": ("Finished item mass", "UOM-015"),
    "PS-028": ("Pressure differential", "UOM-019"),
    "PS-051": ("Vacuum level", "UOM-019"),
}

# Live legacy rows the ruling requires to remain intact, with the canonical
# ID each one's meaning actually belongs to under the governance register.
# live controlled_id -> (symbol, name, canonical controlled_id)
_LEGACY_LIVE_IDS = {
    "UOM-038": ("s", "second", "UOM-010"),
    "UOM-039": ("mm", "millimetre", "UOM-007"),
    "UOM-040": ("degC", "degree Celsius", "UOM-009"),
    "UOM-041": ("%", "percent", "UOM-006"),
}


@pytest.fixture()
def uom_fixture():
    """Rebuilds the post-write live shape: the four ruled rows, the four
    retained legacy rows, and the five linked Process Setting definitions."""
    db.init_db()
    _reset_schema()
    session = db.get_session()

    units = {}
    for controlled_id, (symbol, name, qty, order, system) in _RULED_UOM.items():
        row = db.UnitOfMeasure(
            controlled_id=controlled_id, symbol=symbol, name=name,
            quantity_type=qty, sort_order=order, unit_system=system,
            data_rule="Store numeric",
        )
        session.add(row)
        units[controlled_id] = row

    for controlled_id, (symbol, name, _canonical) in _LEGACY_LIVE_IDS.items():
        row = db.UnitOfMeasure(controlled_id=controlled_id, symbol=symbol, name=name)
        session.add(row)
        units[controlled_id] = row
    session.flush()

    definitions = {}
    for ps_id, (name, uom_id) in _PS_TO_UOM.items():
        row = db.ProcessSettingDefinition(
            controlled_id=ps_id, name=name, unit_id=units[uom_id].id,
            parameter_category="Process Setting",
        )
        session.add(row)
        definitions[ps_id] = row

    # Control: a definition deliberately left without a controlled unit.
    unlinked = db.ProcessSettingDefinition(
        controlled_id="PS-999", name="Unlinked control setting",
        parameter_category="Process Setting",
    )
    session.add(unlinked)
    definitions["PS-999"] = unlinked
    session.commit()

    yield session, units, definitions
    session.close()


@pytest.mark.parametrize("controlled_id", sorted(_RULED_UOM))
def test_ruled_uom_row_matches_the_wp2_technical_master(uom_fixture, controlled_id):
    """Each seeded row carries the exact name, symbol and quantity class the
    ruling requires - the ruling's "using their exact names, symbols and
    quantity classes" clause, field by field."""
    session, _units, _definitions = uom_fixture
    symbol, name, qty, order, system = _RULED_UOM[controlled_id]

    row = session.query(db.UnitOfMeasure).filter_by(controlled_id=controlled_id).one()
    assert row.symbol == symbol
    assert row.name == name
    assert row.quantity_type == qty
    assert row.sort_order == order
    assert row.unit_system == system


@pytest.mark.parametrize("ps_id", sorted(_PS_TO_UOM))
def test_process_setting_resolves_to_its_controlled_uom(uom_fixture, ps_id):
    """Each of the five Process Setting definitions resolves through its FK
    to the intended controlled UOM - the ruling's section 3 link list."""
    session, _units, _definitions = uom_fixture
    name, expected_uom = _PS_TO_UOM[ps_id]

    definition = session.query(db.ProcessSettingDefinition).filter_by(controlled_id=ps_id).one()
    assert definition.name == name
    assert definition.unit is not None, f"{ps_id} must carry a controlled unit"
    assert definition.unit.controlled_id == expected_uom
    assert definition.unit.symbol == _RULED_UOM[expected_uom][0]


def test_both_pressure_settings_share_one_controlled_row(uom_fixture):
    """PS-028 and PS-051 both resolve to UOM-019 through the same row rather
    than through two parallel bar rows - the outcome the ruling's
    no-fresh-block instruction is there to produce."""
    session, _units, _definitions = uom_fixture

    ps028 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-028").one()
    ps051 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-051").one()

    assert ps028.unit_id == ps051.unit_id
    assert ps028.unit.controlled_id == "UOM-019"
    bar_rows = session.query(db.UnitOfMeasure).filter_by(symbol="bar").all()
    assert len(bar_rows) == 1


@pytest.mark.parametrize("ps_id", sorted(_PS_TO_UOM))
def test_snapshot_unit_derives_from_the_definition_on_insert(uom_fixture, ps_id):
    """A ProcessParameterValue written with a conflicting unit string is
    stored carrying the definition's controlled symbol instead - the
    ruling's "cannot carry an independent conflicting unit" requirement."""
    session, _units, definitions = uom_fixture
    expected_symbol = _RULED_UOM[_PS_TO_UOM[ps_id][1]][0]

    value = db.ProcessParameterValue(
        setting_definition_id=definitions[ps_id].id,
        numeric_value=12.5,
        unit="WRONG-UNIT",
    )
    session.add(value)
    session.commit()
    session.refresh(value)

    assert value.unit == expected_symbol


def test_snapshot_unit_is_re_derived_on_update(uom_fixture):
    """Reassigning the unit on an existing row is overwritten too, so the
    snapshot cannot drift away from the controlled definition after entry."""
    session, _units, definitions = uom_fixture

    value = db.ProcessParameterValue(
        setting_definition_id=definitions["PS-074"].id, numeric_value=3.0,
    )
    session.add(value)
    session.commit()
    assert value.unit == "kg"

    value.unit = "lb"
    session.commit()
    session.refresh(value)
    assert value.unit == "kg"


def test_snapshot_unit_follows_a_relinked_definition(uom_fixture):
    """Pointing a value at a different controlled setting re-derives the
    symbol from the new definition rather than keeping the old one."""
    session, _units, definitions = uom_fixture

    value = db.ProcessParameterValue(
        setting_definition_id=definitions["PS-069"].id, numeric_value=90.0,
    )
    session.add(value)
    session.commit()
    assert value.unit == "min"

    value.setting_definition_id = definitions["PS-076"].id
    session.commit()
    session.refresh(value)
    assert value.unit == "kg/m3"


def test_unlinked_definition_yields_no_snapshot_unit(uom_fixture):
    """A definition with no controlled unit produces an empty snapshot unit
    rather than accepting whatever the caller supplied - the same rule
    applied to the majority-null pattern still on the live table."""
    session, _units, definitions = uom_fixture

    value = db.ProcessParameterValue(
        setting_definition_id=definitions["PS-999"].id,
        numeric_value=1.0,
        unit="INVENTED",
    )
    session.add(value)
    session.commit()
    session.refresh(value)

    assert value.unit is None


@pytest.mark.parametrize("controlled_id", sorted(_LEGACY_LIVE_IDS))
def test_legacy_live_ids_retain_their_own_meaning(uom_fixture, controlled_id):
    """The four retained legacy rows keep their live meaning and stay
    distinct from the ruled block - the ruling's live collision rule. Their
    canonical identifiers remain unissued, which is what makes the separate
    reconciliation still possible."""
    session, _units, _definitions = uom_fixture
    symbol, name, canonical = _LEGACY_LIVE_IDS[controlled_id]

    row = session.query(db.UnitOfMeasure).filter_by(controlled_id=controlled_id).one()
    assert row.symbol == symbol
    assert row.name == name
    assert controlled_id not in _RULED_UOM

    assert session.query(db.UnitOfMeasure).filter_by(controlled_id=canonical).first() is None


def test_no_duplicate_controlled_ids_across_the_unit_master(uom_fixture):
    """Seeding the ruled block introduced no second row for any identifier
    already in use - the duplicate-ID check step 6 of the governance
    register's implementation instructions requires on every new UOM."""
    session, _units, _definitions = uom_fixture

    rows = session.query(db.UnitOfMeasure).all()
    controlled_ids = [r.controlled_id for r in rows]
    assert len(controlled_ids) == len(set(controlled_ids))

    symbols = [r.symbol for r in rows]
    assert len(symbols) == len(set(symbols))
