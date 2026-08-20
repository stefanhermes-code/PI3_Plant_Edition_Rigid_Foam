"""Control for the viscosity standard and its conversions.
R-PRE addendum, Redesign Migration Plan v3 Package A.

STEFAN'S RULING (20 August 2026)

cP is the controlled standard unit for viscosity. A value arriving from a
supplier data sheet in another unit is converted into cP rather than stored as
typed - the application is meant to be intelligent about units, not to make
the user do arithmetic and hope.

THE ONE THING THIS FILE EXISTS TO PREVENT

Dynamic and kinematic viscosity look interchangeable on a data sheet and are
not: kinematic = dynamic / density. Converting cSt straight to cP is wrong by
a factor of the material's density. For a polyol near 1.02 g/cm3 that is a 2%
error - small enough to pass for a plausible reading, large enough to matter
against a release specification. So:

  * convert() must REFUSE cSt -> cP outright;
  * dynamic_viscosity_cp() crosses between them ONLY when given a density;
  * with no density it returns None, never a best guess.

Saybolt, Engler and Redwood are refused entirely. Their relationship to cSt is
an empirical piecewise formula, not a factor, so there is no honest conversion
to perform.

Usage: python -m pytest tests/test_rpre_viscosity_uom_conversion.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import unit_conversion as uc

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(APP_DIR, "migrations", "0006_rpre_viscosity_controlled_uom.sql")

# 250 cP is a plausible polyol viscosity. Each of these is the SAME reading.
EQUIVALENT_TO_250_CP = [
    ("250", "cP", 250.0),
    ("250", "mPa.s", 250.0),
    ("250", "mPa*s", 250.0),
    ("250", "mPa·s", 250.0),
    ("250", "mPa s", 250.0),
    ("0.25", "Pa.s", 0.25),
    ("2.5", "P", 2.5),
    ("2.5", "poise", 2.5),
    ("0.25", "kg/(m.s)", 0.25),
]

REFUSED_OUTRIGHT = ["SUS", "SSU", "Saybolt seconds", "Engler", "Redwood 1", "bananas", ""]


def test_the_standard_unit_is_mpa_s():
    assert uc.VISCOSITY_STANDARD_UOM == "mPa.s"


def test_cp_is_still_accepted_on_entry():
    """Most polyurethane data sheets print cP. Dropping it as an input unit
    would make the standard change a user-visible loss instead of a label."""
    assert uc.dynamic_viscosity_cp(250.0, "cP") == pytest.approx(250.0)


@pytest.mark.parametrize("label,unit,value", EQUIVALENT_TO_250_CP)
def test_dynamic_units_convert_to_the_cp_standard(label, unit, value):
    assert uc.dynamic_viscosity_cp(value, unit) == pytest.approx(250.0)


def test_mpa_s_and_cp_are_exactly_the_same_size():
    """Not a rounded factor - if this ever drifts, every data sheet quoting
    mPa.s has been silently rescaled."""
    assert uc.convert(1.0, "mPa.s", "cP") == 1.0
    assert uc.convert(1.0, "cP", "mPa.s") == 1.0


# ---------------------------------------------------------------------------
# The kinematic/dynamic boundary
# ---------------------------------------------------------------------------

def test_convert_refuses_kinematic_to_dynamic():
    """The generic converter must not cross physical quantities. If this
    starts returning a number, every cSt reading in the system becomes wrong
    by the material's density and nothing flags it."""
    assert uc.convert(245.0, "cSt", "cP") is None
    assert uc.convert(245.0, "mm2/s", "cP") is None
    assert uc.convertible("cSt", "cP") is False


def test_kinematic_needs_a_density():
    assert uc.dynamic_viscosity_cp(245.0, "cSt") is None
    assert uc.dynamic_viscosity_cp(245.0, "cSt", None) is None


@pytest.mark.parametrize("bad_density", [0, -1.0, -0.001])
def test_kinematic_rejects_an_impossible_density(bad_density):
    assert uc.dynamic_viscosity_cp(245.0, "cSt", bad_density) is None


def test_kinematic_converts_when_the_density_is_known():
    """cP = cSt x density in g/cm3."""
    assert uc.dynamic_viscosity_cp(245.0, "cSt", 1.02) == pytest.approx(249.9)
    assert uc.dynamic_viscosity_cp(245.0, "mm2/s", 1.02) == pytest.approx(249.9)


def test_the_density_actually_changes_the_answer():
    """Guards the test above: if the density were ignored, both of these would
    return the same number and the test would pass for the wrong reason."""
    at_one = uc.dynamic_viscosity_cp(245.0, "cSt", 1.0)
    at_ten_percent_denser = uc.dynamic_viscosity_cp(245.0, "cSt", 1.1)
    assert at_one == pytest.approx(245.0)
    assert at_ten_percent_denser == pytest.approx(269.5)
    assert at_one != at_ten_percent_denser


def test_kinematic_units_still_convert_among_themselves():
    assert uc.convert(1.0, "cSt", "mm2/s") == pytest.approx(1.0)
    assert uc.convert(1.0, "St", "cSt") == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("unit", REFUSED_OUTRIGHT)
def test_unconvertible_readings_are_refused_not_guessed(unit):
    assert uc.dynamic_viscosity_cp(100.0, unit) is None
    assert uc.dynamic_viscosity_cp(100.0, unit, 1.02) is None


def test_no_value_means_no_answer():
    assert uc.dynamic_viscosity_cp(None, "cP") is None


def test_nothing_raises_on_junk():
    for unit in (None, "", "   ", "???", 0):
        uc.dynamic_viscosity_cp(1.0, unit)
        uc.viscosity_conversion_note(unit)


# ---------------------------------------------------------------------------
# The explanation given back to the user
# ---------------------------------------------------------------------------

def test_missing_density_is_explained_and_names_what_is_needed():
    note = uc.viscosity_conversion_note("cSt")
    assert "density" in note.lower()
    assert "specific gravity" in note.lower()


def test_saybolt_is_explained_rather_than_silently_dropped():
    note = uc.viscosity_conversion_note("SUS")
    assert note
    assert "mPa.s" in note or "cSt" in note


def test_a_convertible_reading_has_nothing_to_explain():
    assert uc.viscosity_conversion_note("mPa.s") == ""
    assert uc.viscosity_conversion_note("cSt", 1.02) == ""


# ---------------------------------------------------------------------------
# The controlled master
# ---------------------------------------------------------------------------

def _migration_sql():
    with open(MIGRATION, encoding="utf-8") as handle:
        return handle.read()


def test_migration_adds_both_quantity_types_and_keeps_them_apart():
    sql = _migration_sql()
    assert "'Dynamic viscosity'" in sql
    assert "'Kinematic viscosity'" in sql
    for controlled_id in ("UOM-108", "UOM-109", "UOM-110", "UOM-111", "UOM-112", "UOM-113"):
        assert f"'{controlled_id}'" in sql


def test_migration_sets_cp_as_the_property_default():
    sql = _migration_sql()
    assert "set default_uom = 'cP'" in sql  # 0006 sets it; 0007 moves it to mPa.s
    assert "'PROP-059'" in sql


def test_migration_is_guarded_and_unqualified():
    sql = _migration_sql()
    body = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    assert "where not exists" in body.lower()
    assert "rigid_foam." not in sql
    assert "pg_get_serial_sequence" in body
    for destructive in ("drop table", "drop column", "delete from"):
        assert destructive not in body.lower()


def test_migration_does_not_overwrite_a_default_someone_has_since_set():
    """The update fills the field only while it is empty. A re-run after a
    deliberate change must not quietly put cP back."""
    body = _migration_sql().lower()
    assert "default_uom is null or btrim(default_uom) = ''" in body


# ---------------------------------------------------------------------------
# ASTM D445 and the method routes (migration 0007)
# ---------------------------------------------------------------------------

MIGRATION_0007 = os.path.join(APP_DIR, "migrations", "0007_rpre_viscosity_standard_mpa_s.sql")


def _migration_0007_sql():
    with open(MIGRATION_0007, encoding="utf-8") as handle:
        return handle.read()


def test_0007_moves_the_property_default_to_mpa_s():
    sql = _migration_0007_sql()
    assert "set default_uom = 'mPa.s'" in sql
    assert "'PROP-059'" in sql


def test_0007_only_moves_the_value_this_chain_set():
    """Guarded so a deliberate later change is not reverted by a replay: it
    moves NULL, blank or 'cP' and nothing else."""
    assert "in ('', 'cP')" in _migration_0007_sql()


def test_0007_registers_both_method_routes():
    """D445 is a KINEMATIC method whose dynamic result is calculated using
    density; D2196 is rotational and reads dynamic directly. The application
    has to support both, so both are controlled methods and the choice sits on
    the individual result."""
    sql = _migration_0007_sql()
    assert "ASTM D445" in sql and "'MTH-039'" in sql
    assert "ASTM D2196" in sql and "'MTH-040'" in sql


def test_0007_records_that_d445_requires_a_density():
    sql = _migration_0007_sql()
    d445 = sql[sql.index("'MTH-039'"):sql.index("'MTH-040'")]
    lowered = d445.lower()
    assert "kinematic" in lowered
    assert "density" in lowered and "mandatory" in lowered


def test_0007_is_guarded_and_unqualified():
    sql = _migration_0007_sql()
    body = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    assert "where not exists" in body.lower()
    assert "rigid_foam." not in sql
    for destructive in ("drop table", "drop column", "delete from"):
        assert destructive not in body.lower()
