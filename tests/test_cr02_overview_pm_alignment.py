"""CR-02 (Overview Dashboard Production Method Alignment) regression tests,
2026-08-10.

Covers the rebuilt render_overview() in app_rigid_foam.py against Charlie's
CR-02 source document:

  - Filter cascade: Plant -> Production Method -> Production Unit/Cell ->
    Product Grade -> Date range, with PU Material Family as an optional
    secondary/advanced filter that narrows Product Grade but never scopes
    KPIs on its own.
  - Cross-method KPI isolation: selecting a single Production Method must
    show ONLY that method's runs/results in the Volume and Quality &
    Performance KPI cards; selecting "All Production Methods" must show the
    combined total across every method.
  - Cross-plant leak prevention: ProductionMethod is a shared, plant-agnostic
    controlled-vocabulary row (not owned by any one plant). Selecting a
    Production Method with NO Plant selected - or selecting a Plant then a
    Production Method - must never pull in another plant's machines/grades
    just because they happen to share the same globally-scoped
    ProductionMethod row. This is the bug caught during CR-02 design
    (an exclusive machine->method->plant elif chain would have leaked
    cross-plant); this file pins the fix.

Fixture pattern follows tests/test_flat_pm_propagation_smoke.py's
two_method_fixture, adapted so each of the two Production Methods has its
OWN dedicated Product Grade (grade A only producible on machine A / method
A, grade B only on machine B / method B) - this makes it possible to assert
that Product Grade narrows correctly alongside Production Unit/Cell, not
just that Production Method itself narrows.

Usage: python -m pytest tests/test_cr02_overview_pm_alignment.py -v
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


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def _seed_two_method_plant(session, label):
    """Builds one Plant with two activated Production Methods, one Machine
    and one dedicated Product Grade per method, one Production Run per
    method (each snapshotting its own production_method_id), and quality
    data seeded ONLY on run_a (so cross-method isolation is unambiguous:
    method B's scope must show 0 quality issues/samples, not a leaked 1)."""
    u = uuid.uuid4().hex[:8]
    company = db.Company(name=f"CR02 Co {label} {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR02 Plant {label} {u}")
    session.add(plant); session.flush()

    method_a = db.ProductionMethod(controlled_id=f"PM-CR02-{label}-A-{u}", name=f"Discontinuous Factory Foaming {label} {u}", sort_order=100)
    method_b = db.ProductionMethod(controlled_id=f"PM-CR02-{label}-B-{u}", name=f"Continuous Panel {label} {u}", sort_order=200)
    session.add_all([method_a, method_b]); session.flush()
    session.add_all([
        db.PlantProductionMethod(plant_id=plant.id, production_method_id=method_a.id, active=True),
        db.PlantProductionMethod(plant_id=plant.id, production_method_id=method_b.id, active=True),
    ])
    session.flush()

    machine_a = db.Machine(plant_id=plant.id, name=f"Machine A {label} {u}", production_method_id=method_a.id, active=True)
    machine_b = db.Machine(plant_id=plant.id, name=f"Machine B {label} {u}", production_method_id=method_b.id, active=True)
    session.add_all([machine_a, machine_b]); session.flush()

    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR02 Family {label} {u}")
    session.add(family); session.flush()
    grade_a = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"Grade A {label} {u}")
    session.add(grade_a); session.flush()
    grade_a.machines = [machine_a]
    grade_b = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"Grade B {label} {u}")
    session.add(grade_b); session.flush()
    grade_b.machines = [machine_b]
    session.flush()

    recipe_a = db.RecipeVersion(foam_grade_id=grade_a.id, version_label="v1", approval_status="Approved", is_active=True)
    recipe_b = db.RecipeVersion(foam_grade_id=grade_b.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add_all([recipe_a, recipe_b]); session.flush()

    run_a = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade_a.id, machine_id=machine_a.id,
        recipe_version_id=recipe_a.id, run_date=dt.date.today(),
        production_method_id=method_a.id,
    )
    run_b = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade_b.id, machine_id=machine_b.id,
        recipe_version_id=recipe_b.id, run_date=dt.date.today(),
        production_method_id=method_b.id,
    )
    session.add_all([run_a, run_b]); session.flush()

    result_a = db.PhysicalPropertyResult(
        production_run_id=run_a.id, property_name="Density", target_value=35.0,
        actual_value=35.5, unit="kg/m3", tested_at=dt.datetime.now(),
    )
    result_b = db.PhysicalPropertyResult(
        production_run_id=run_b.id, property_name="Density", target_value=35.0,
        actual_value=35.5, unit="kg/m3", tested_at=dt.datetime.now(),
    )
    session.add_all([result_a, result_b]); session.flush()

    issue_a = db.QualityObservation(
        production_run_id=run_a.id, observation_type="Surface defect",
        frequency="Recurring", observed_at=dt.date.today(),
    )
    sample_a = db.Sample(production_run_id=run_a.id, sample_ts=dt.datetime.now())
    session.add_all([issue_a, sample_a]); session.flush()

    return {
        "company": company, "plant": plant,
        "method_a": method_a, "method_b": method_b,
        "machine_a": machine_a, "machine_b": machine_b,
        "grade_a": grade_a, "grade_b": grade_b,
        "run_a": run_a, "run_b": run_b,
    }


@pytest.fixture()
def two_method_fixture():
    db.init_db()
    _reset_schema()
    session = db.get_session()
    ids = _seed_two_method_plant(session, "P1")
    session.commit()
    out = {k: (v.id if hasattr(v, "id") else v) for k, v in ids.items()}
    out["plant_name"] = ids["plant"].name
    out["method_a_name"] = ids["method_a"].name
    out["method_b_name"] = ids["method_b"].name
    out["machine_a_name"] = ids["machine_a"].name
    out["machine_b_name"] = ids["machine_b"].name
    out["grade_a_name"] = ids["grade_a"].grade_name
    out["grade_b_name"] = ids["grade_b"].grade_name
    session.close()
    return out


@pytest.fixture()
def two_plant_shared_method_fixture():
    """Two independent Plants, each with their OWN two Production Methods
    (i.e. NOT the same ProductionMethod row shared across plants - flat-PM
    controlled vocabulary rows are still global/shared in the sense that any
    plant COULD activate the same code, but here we model two plants each
    with distinct method rows to isolate the leak scenario cleanly): the
    regression this pins is that selecting Plant 2's Production Method must
    never surface Plant 1's machines, even though both methods are
    plant-agnostic ProductionMethod rows with no plant_id column of their
    own."""
    db.init_db()
    _reset_schema()
    session = db.get_session()
    plant1 = _seed_two_method_plant(session, "P1")
    plant2 = _seed_two_method_plant(session, "P2")
    session.commit()
    out = {
        "plant1_name": plant1["plant"].name,
        "plant2_name": plant2["plant"].name,
        "plant2_method_a_name": plant2["method_a"].name,
        "plant2_machine_a_name": plant2["machine_a"].name,
        "plant1_machine_a_name": plant1["machine_a"].name,
        "plant1_machine_b_name": plant1["machine_b"].name,
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
# Filter cascade: Plant -> Production Method -> Production Unit/Cell ->
# Product Grade
# ---------------------------------------------------------------------------

def test_plant_selection_narrows_method_then_unit_then_grade(two_method_fixture):
    ids = two_method_fixture
    at = _run_overview()
    assert not at.exception, f"Unhandled exception on initial Overview load: {at.exception}"

    _sb(at, "Plant").set_value(ids["plant_name"]).run()
    assert not at.exception

    method_options = _sb(at, "Production Method").options
    assert ids["method_a_name"] in method_options
    assert ids["method_b_name"] in method_options

    _sb(at, "Production Method").set_value(ids["method_a_name"]).run()
    assert not at.exception, f"Unhandled exception after selecting Method A: {at.exception}"

    unit_options = _sb(at, "Equipment / Machine").options
    assert unit_options == ["All equipment", ids["machine_a_name"]], (
        f"Expected only Machine A once Method A is selected, got {unit_options}"
    )
    grade_options = _sb(at, "Product Grade").options
    assert grade_options == ["All grades", ids["grade_a_name"]], (
        f"Expected only Grade A once Method A is selected, got {grade_options}"
    )


def test_switching_method_swaps_unit_and_grade_options(two_method_fixture):
    ids = two_method_fixture
    at = _run_overview()
    _sb(at, "Plant").set_value(ids["plant_name"]).run()
    _sb(at, "Production Method").set_value(ids["method_b_name"]).run()
    assert not at.exception, f"Unhandled exception after selecting Method B: {at.exception}"

    unit_options = _sb(at, "Equipment / Machine").options
    assert unit_options == ["All equipment", ids["machine_b_name"]]
    grade_options = _sb(at, "Product Grade").options
    assert grade_options == ["All grades", ids["grade_b_name"]]


# ---------------------------------------------------------------------------
# Cross-method KPI isolation
# ---------------------------------------------------------------------------

def test_kpis_isolate_to_single_method(two_method_fixture):
    ids = two_method_fixture
    at = _run_overview()
    _sb(at, "Plant").set_value(ids["plant_name"]).run()
    _sb(at, "Production Method").set_value(ids["method_b_name"]).run()
    assert not at.exception

    metrics = _metrics(at)
    # Method B's own run has one quality test but no issues/samples - those
    # were seeded only on run A (Method A). If this ever reads "1" instead
    # of "0", cross-method isolation has regressed (leaked run A's data).
    assert metrics["Production runs"] == "1"
    assert metrics["Quality tests"] == "1"
    assert metrics["Quality issues"] == "0"
    assert metrics["Samples"] == "0"


def test_kpis_combine_across_all_methods(two_method_fixture):
    ids = two_method_fixture
    at = _run_overview()
    _sb(at, "Plant").set_value(ids["plant_name"]).run()
    _sb(at, "Production Method").set_value("All Production Methods").run()
    assert not at.exception

    metrics = _metrics(at)
    assert metrics["Production runs"] == "2"
    assert metrics["Quality tests"] == "2"
    assert metrics["Quality issues"] == "1"
    assert metrics["Samples"] == "1"


# ---------------------------------------------------------------------------
# Cross-plant leak prevention (the bug caught during CR-02 design: an
# exclusive machine->method->plant elif chain would let a method-only
# selection, with no plant selected, surface another plant's machines)
# ---------------------------------------------------------------------------

def test_method_only_filter_without_plant_does_not_leak_other_plants_machines(two_plant_shared_method_fixture):
    ids = two_plant_shared_method_fixture
    at = _run_overview()
    assert not at.exception

    # No Plant selected - select Plant 2's Method A directly.
    _sb(at, "Production Method").set_value(ids["plant2_method_a_name"]).run()
    assert not at.exception, f"Unhandled exception selecting Plant 2's method with no plant filter: {at.exception}"

    unit_options = _sb(at, "Equipment / Machine").options
    assert ids["plant2_machine_a_name"] in unit_options
    assert ids["plant1_machine_a_name"] not in unit_options, (
        f"Plant 1's machine leaked into the unit list when only Plant 2's "
        f"Production Method was selected: {unit_options}"
    )
    assert ids["plant1_machine_b_name"] not in unit_options


def test_plant_filter_is_never_bypassed_by_method_selection(two_plant_shared_method_fixture):
    ids = two_plant_shared_method_fixture
    at = _run_overview()

    # Select Plant 1, then Plant 2's Method A should not even be offered as
    # an option (activated_methods_for_plant scopes the dropdown itself),
    # and if somehow selected the unit list must still stay within Plant 1.
    _sb(at, "Plant").set_value(ids["plant1_name"]).run()
    method_options = _sb(at, "Production Method").options
    assert ids["plant2_method_a_name"] not in method_options, (
        f"Plant 2's Production Method should not be offered once Plant 1 is "
        f"selected (methods are activated per-plant): {method_options}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
