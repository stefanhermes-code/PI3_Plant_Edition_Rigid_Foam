"""Control for R-PRE-WP1 - material-metering applicability by Production Unit / Cell.
Redesign Migration Plan v3, Package A.

WHAT THIS IS AND IS NOT

It is a general property of a Production Unit or Cell: how it gets material
into the mix. A metering machine, a blending vessel with an agitator and a
hand mix are three real ways of making polyurethane, and the vocabulary
describes the industry rather than any one customer. The pilot customer's
blending vessel is simply one value of it.

It is NOT a customer switch. Nothing in the resolver looks at the company, the
plant or the tenant. If it ever does, this file should fail.

THE DIRECTION THAT MATTERS

An undeclared unit keeps every module. Functionality is only withdrawn once
somebody has positively declared a mode this code recognises as non-metering.
Two consequences are tested explicitly because they are easy to get backwards:

  * NULL / blank resolves to APPLICABLE, so no existing plant loses the
    metering module on the day this ships;
  * an UNRECOGNISED value also resolves to applicable, so a typo or a value
    written by a future version cannot silently take a module away.

Usage: python -m pytest tests/test_rpre_material_delivery_mode.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
import helpers

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(APP_DIR, "migrations", "0005_rpre_material_delivery_mode.sql")

# The vocabulary, written out. Not read back from helpers - an expectation
# derived from the thing it checks cannot fail when that thing changes.
EXPECTED_MODES = ("Machine-metered", "Batch blended", "Hand mix")

METERING_APPLIES = [None, "", "   ", "Machine-metered", "Something nobody has seen before"]
METERING_DOES_NOT_APPLY = ["Batch blended", "Hand mix"]


class _FakeMachine:
    def __init__(self, mode):
        self.material_delivery_mode = mode


class _FakeRun:
    def __init__(self, machine):
        self.machine = machine


def test_vocabulary_is_the_declared_one():
    assert helpers.MATERIAL_DELIVERY_MODES == EXPECTED_MODES


def test_vocabulary_is_not_specific_to_one_customer_or_process():
    """A guard against the mistake this work package nearly made: building the
    condensed run page around the pilot customer instead of around a property
    every company type has."""
    joined = " ".join(helpers.MATERIAL_DELIVERY_MODES).lower()
    for banned in ("ptu", "colin", "korat", "rigid", "flexible", "pilot", "customer"):
        assert banned not in joined, f"the vocabulary names {banned!r}"


@pytest.mark.parametrize("mode", METERING_APPLIES)
def test_metering_applies(mode):
    assert helpers.run_uses_metered_material_delivery(_FakeRun(_FakeMachine(mode))) is True


@pytest.mark.parametrize("mode", METERING_DOES_NOT_APPLY)
def test_metering_does_not_apply(mode):
    assert helpers.run_uses_metered_material_delivery(_FakeRun(_FakeMachine(mode))) is False


def test_run_with_no_unit_keeps_the_module():
    assert helpers.run_uses_metered_material_delivery(_FakeRun(None)) is True


def test_resolver_never_raises_on_a_bare_object():
    class Bare:
        pass
    assert helpers.run_uses_metered_material_delivery(Bare()) is True


def test_resolver_reads_only_the_production_unit():
    """The resolver must not consult the company, plant or tenant. Anything it
    touches on the run other than .machine would make this a customer switch."""
    touched = []

    class Watcher:
        machine = _FakeMachine("Batch blended")

        def __getattr__(self, name):
            touched.append(name)
            raise AttributeError(name)

    helpers.run_uses_metered_material_delivery(Watcher())
    for forbidden in ("company", "company_id", "plant", "plant_id", "customer"):
        assert forbidden not in touched


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_column_exists_on_the_machine_model_and_is_nullable():
    column = db.Machine.__table__.columns["material_delivery_mode"]
    assert column.nullable is True, "a NOT NULL column would force a value onto every existing unit"
    assert column.default is None and column.server_default is None, (
        "a default would declare a mode for units nobody has configured"
    )


def test_migration_is_additive_and_guarded():
    with open(MIGRATION, encoding="utf-8") as handle:
        sql = handle.read()
    body = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--")).lower()
    assert "add column if not exists material_delivery_mode" in body
    assert "not null" not in body
    assert "default" not in body
    for destructive in ("drop column", "drop table", "delete from", "update "):
        assert destructive not in body
    assert "rigid_foam." not in sql


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

def test_run_page_gates_the_metering_module_on_the_resolver():
    with open(os.path.join(APP_DIR, "views", "4_Production_Run_Trial_Record.py"), encoding="utf-8") as handle:
        source = handle.read()
    assert "run_uses_metered_material_delivery" in source
    tab = source[source.index("with tab_streams:"):source.index("with tab_output:")]
    # The resolver is called once and its answer held in a local, because the
    # same answer gates both the banner and the entry form further down.
    assert "metering_applies = run_uses_metered_material_delivery(run)" in tab
    assert "if not metering_applies:" in tab


def test_equipment_page_offers_only_the_controlled_values():
    with open(os.path.join(APP_DIR, "views", "31_Production_Equipment.py"), encoding="utf-8") as handle:
        source = handle.read()
    assert "MATERIAL_DELIVERY_MODES" in source
    for mode in EXPECTED_MODES:
        assert f'"{mode}"' not in source, (
            f"{mode!r} is hard-coded on the page instead of coming from the vocabulary"
        )


# ---------------------------------------------------------------------------
# Withdrawing the module has to actually withdraw it
#
# Found in browser evidence on 20 August 2026: the banner correctly said
# metering did not apply, and the entry form was still sitting underneath it,
# ready to accept flow, pressure and temperature readings for a unit that has
# no metering. An explanation the user can ignore is not a gate - and the
# ruling was that context-specific fields APPEAR only where they apply, not
# that they are merely captioned.
#
# The other half matters just as much: editing and viewing existing readings
# stay open. Withdrawing a module must never strand data somebody has already
# entered, which is why only the create path is closed.
# ---------------------------------------------------------------------------

def _metering_tab_source():
    with open(os.path.join(APP_DIR, "views", "4_Production_Run_Trial_Record.py"), encoding="utf-8") as handle:
        source = handle.read()
    return source[source.index("with tab_streams:"):source.index("with tab_output:")]


def test_the_entry_form_is_closed_when_metering_does_not_apply():
    tab = _metering_tab_source()
    create = tab[tab.index("with tab_create:"):tab.index("with tab_import:")]
    assert "if metering_applies:" in create, (
        "the metering entry form is not guarded - a banner alone is not a gate"
    )
    # The stream picker is the first field of the form proper. It must sit
    # inside the guard, not beside it.
    guard_at = create.index("if metering_applies:")
    picker_at = create.index('"Stream / raw material *"')
    assert guard_at < picker_at, "the entry fields render before the guard"


def test_existing_readings_stay_reachable():
    """Only the create path closes. Edit/Delete is untouched, so nothing
    already recorded becomes unreachable."""
    tab = _metering_tab_source()
    edit = tab[tab.index("with tab_edit_delete:"):tab.index("with tab_create:")]
    assert "metering_applies" not in edit, (
        "editing existing readings must not be gated - that would strand recorded data"
    )


def test_the_banner_says_recording_is_closed_not_merely_inapplicable():
    tab = _metering_tab_source()
    banner = tab[tab.index("if not metering_applies:"):tab.index("phases_for_run")]
    assert "closed" in banner.lower()
    assert "editable" in banner.lower() or "visible" in banner.lower()

