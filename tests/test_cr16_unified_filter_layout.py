"""CR-16 (Consolidate Overview Dashboard Filters into a Unified Layout)
regression tests, 2026-08-13.

Covers Charlie's PI3_Rigid_Foam_Phase_1_CR16_Consolidate_Overview_Dashboard_
Filters_into_Unified_Layout.docx (implemented in render_overview(),
app_rigid_foam.py):

  - The old "Advanced filter (optional)" expander is gone - PU Material Family
    now renders directly in the visible filter area, no extra click.
  - All six filters (Plant, Production Method, Production Unit / Cell,
    PU Material Family, Product Grade, Date range) are present, in the exact
    order Row 1 (Plant, Production Method, Production Unit / Cell) then
    Row 2 (PU Material Family, Product Grade, Date range) puts them on screen -
    AppTest's element lists follow script render order, so list order here
    is a direct proxy for on-screen left-to-right, row-by-row order.
  - This is a presentation-only change (CR-16 section 4): every cascading
    rule and KPI-scoping rule CR-02 established is byte-for-byte unchanged.
    tests/test_cr02_overview_pm_alignment.py already re-confirms (unchanged,
    re-run standalone for this CR: 6 passed) that the Plant -> Production
    Method -> Production Unit / Cell -> Product Grade cascade, cross-method
    KPI isolation, and cross-plant leak prevention all still hold against
    the new layout - this file does not duplicate that coverage. It adds
    the layout-specific assertions plus one direct regression pinning that
    PU Material Family narrows Product Grade's options without independently
    scoping any KPI (CR-02's rule, reaffirmed unchanged by CR-16 section 4).

Usage: python -m pytest tests/test_cr16_unified_filter_layout.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_MAIN = os.path.join(APP_DIR, "app_rigid_foam.py")

EXPECTED_SELECTBOX_ORDER = [
    "Plant", "Production Method", "Production Unit / Cell",
    "PU Material Family", "Product Grade",
]
EXPECTED_FAMILY_HELP = (
    "Optional classification - narrows Product Grade below, does not "
    "scope KPIs on its own."
)


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def _seed_family_kpi_fixture(session):
    """One Plant, one Production Method, one Machine, two PU Material Families
    each with their own Grade - both grades producible on the SAME machine
    (so Production Method/Unit filters can't be the thing separating them,
    isolating PU Material Family as the only distinguishing filter) - and one
    Production Run per grade, so a KPI (Production runs) has a countable
    baseline of 2 that a PU Material Family selection must NOT reduce."""
    u = uuid.uuid4().hex[:8]
    company = db.Company(name=f"CR16 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR16 Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-CR16-{u}", name=f"CR16 Method {u}", sort_order=100)
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"CR16 Machine {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()

    family_a = db.PUMaterialFamily(plant_id=plant.id, name=f"CR16 Family A {u}")
    family_b = db.PUMaterialFamily(plant_id=plant.id, name=f"CR16 Family B {u}")
    session.add_all([family_a, family_b]); session.flush()

    grade_a = db.FoamGrade(pu_material_family_id=family_a.id, grade_name=f"CR16 Grade A {u}")
    grade_b = db.FoamGrade(pu_material_family_id=family_b.id, grade_name=f"CR16 Grade B {u}")
    session.add_all([grade_a, grade_b]); session.flush()
    grade_a.machines = [machine]
    grade_b.machines = [machine]
    session.flush()

    recipe_a = db.RecipeVersion(foam_grade_id=grade_a.id, version_label="v1", approval_status="Approved", is_active=True)
    recipe_b = db.RecipeVersion(foam_grade_id=grade_b.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add_all([recipe_a, recipe_b]); session.flush()

    run_a = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade_a.id, machine_id=machine.id,
        recipe_version_id=recipe_a.id, run_date=dt.date.today(),
        production_method_id=method.id,
    )
    run_b = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade_b.id, machine_id=machine.id,
        recipe_version_id=recipe_b.id, run_date=dt.date.today(),
        production_method_id=method.id,
    )
    session.add_all([run_a, run_b]); session.flush()

    return {
        "plant": plant, "method": method, "machine": machine,
        "family_a": family_a, "family_b": family_b,
        "grade_a": grade_a, "grade_b": grade_b,
    }


@pytest.fixture()
def family_kpi_fixture():
    db.init_db()
    _reset_schema()
    session = db.get_session()
    ids = _seed_family_kpi_fixture(session)
    session.commit()
    out = {
        "plant_name": ids["plant"].name,
        "method_name": ids["method"].name,
        "family_a_name": ids["family_a"].name,
        "grade_a_name": ids["grade_a"].grade_name,
        "grade_b_name": ids["grade_b"].grade_name,
    }
    session.close()
    return out


def _run_overview():
    at = AppTest.from_file(APP_MAIN, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


def _sb(at, label):
    return next(sb for sb in at.selectbox if sb.label == label)


def _metrics(at):
    return {m.label: m.value for m in at.metric}


# ---------------------------------------------------------------------------
# Layout: expander removed, all six filters present in the new two-row order
# ---------------------------------------------------------------------------

def test_advanced_filter_expander_removed():
    at = _run_overview()
    assert not at.exception, f"Unhandled exception on Overview load: {at.exception}"
    expander_labels = [e.label for e in at.expander]
    assert expander_labels == [], (
        f"CR-16 removed the 'Advanced filter (optional)' expander - Product "
        f"Family must render directly in the visible filter area, but found "
        f"expander(s): {expander_labels}"
    )


def test_all_six_filters_present_in_row_order():
    at = _run_overview()
    assert not at.exception

    selectbox_labels = [sb.label for sb in at.selectbox]
    assert selectbox_labels == EXPECTED_SELECTBOX_ORDER, (
        f"Expected Row 1 (Plant, Production Method, Production Unit / Cell) "
        f"then Row 2 (PU Material Family, Product Grade) in that render order, "
        f"got {selectbox_labels}"
    )

    date_labels = [d.label for d in at.date_input]
    assert date_labels == ["Date range"], (
        f"Expected exactly one Date range control (Row 2, third column), "
        f"got {date_labels}"
    )


def test_pu_material_family_help_text_present_and_unscoped_wording_preserved():
    at = _run_overview()
    family_sb = _sb(at, "PU Material Family")
    assert family_sb.help == EXPECTED_FAMILY_HELP, (
        f"PU Material Family's help text changed unexpectedly: {family_sb.help!r}"
    )


def test_date_range_default_still_year_to_date():
    at = _run_overview()
    di = at.date_input[0]
    today = dt.date.today()
    assert di.value == (dt.date(today.year, 1, 1), today), (
        f"CR-16 is presentation-only - the Date range default must remain "
        f"year-to-date, got {di.value}"
    )


def test_overview_full_smoke_no_unhandled_exception():
    at = _run_overview()
    assert not at.exception, f"Unhandled exception on initial Overview load: {at.exception}"
    # Touch every filter once, in Row 1 -> Row 2 order, confirming no
    # exception at any step of a normal top-to-bottom filtering session.
    _sb(at, "Plant").set_value(None).run()
    assert not at.exception
    _sb(at, "Production Method").set_value(None).run()
    assert not at.exception
    _sb(at, "Production Unit / Cell").set_value(None).run()
    assert not at.exception
    _sb(at, "PU Material Family").set_value(None).run()
    assert not at.exception
    _sb(at, "Product Grade").set_value(None).run()
    assert not at.exception


# ---------------------------------------------------------------------------
# Preserved logic: PU Material Family narrows Product Grade but never
# independently scopes a KPI (CR-02's rule, reaffirmed unchanged by CR-16)
# ---------------------------------------------------------------------------

def test_family_filter_narrows_grade_options_without_scoping_kpis(family_kpi_fixture):
    ids = family_kpi_fixture
    at = _run_overview()
    _sb(at, "Plant").set_value(ids["plant_name"]).run()
    _sb(at, "Production Method").set_value(ids["method_name"]).run()
    assert not at.exception

    baseline_metrics = _metrics(at)
    assert baseline_metrics["Production runs"] == "2", (
        "Baseline (no PU Material Family selected) should count both grades' runs"
    )

    grade_options_before = _sb(at, "Product Grade").options
    assert ids["grade_a_name"] in grade_options_before
    assert ids["grade_b_name"] in grade_options_before

    family_sb = next(sb for sb in at.selectbox if sb.label == "PU Material Family")
    family_sb.set_value(ids["family_a_name"]).run()
    assert not at.exception, f"Unhandled exception selecting PU Material Family: {at.exception}"

    grade_options_after = _sb(at, "Product Grade").options
    assert grade_options_after == ["All grades", ids["grade_a_name"]], (
        f"PU Material Family should narrow Product Grade's options to only its "
        f"own family's grades, got {grade_options_after}"
    )

    scoped_metrics = _metrics(at)
    assert scoped_metrics["Production runs"] == "2", (
        "PU Material Family alone must not scope the Production runs KPI - it "
        "only narrows the Product Grade dropdown (CR-02's rule, reaffirmed "
        "unchanged by CR-16 section 4). Selecting Product Grade itself, not "
        "PU Material Family, is what would narrow this KPI."
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
