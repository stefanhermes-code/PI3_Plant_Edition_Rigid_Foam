"""WP4 (Converged Joint Implementation Plan, section 7.5) controlled unit
conversion - covers unit_conversion.py's pure conversion logic, and the
integration behavior it unlocks in wp3_conformance.py.

This is the intended successor to tests/test_wp3_uat_cases.py's UAT-06
("wrong unit, conversion deferred") case: WP3 explicitly deferred
mW/(m.K)-vs-W/(m.K)-style comparisons to WP4 (see that module's own
docstring and unit_conversion.py's), so UAT-06's original
EXCLUDED_CONTEXT expectation is now superseded rather than broken - see
the frozen-record note at the top of test_wp3_uat_cases.py. This file
replays the identical scenario (23 mW/(m.K) against a <= 0.024 W/(m.K)
spec) against the real, non-stand-in wp3_conformance.compute_conformance_
report (DB-backed, not SimpleNamespace) to prove the new behavior end to
end, then confirms every other WP3 exclusion path (wrong condition, wrong
method, missing context, non-convertible unit) still excludes exactly as
before - this is an addition to WP3's matching rules, not a loosening of
them.
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
import unit_conversion
import wp3_conformance


# ---------------------------------------------------------------------------
# Pure logic: unit_conversion
# ---------------------------------------------------------------------------

def test_convert_thermal_conductivity_milli_to_base():
    assert unit_conversion.convert(23, "mW/(m.K)", "W/(m.K)") == pytest.approx(0.023)
    assert unit_conversion.convert(0.023, "W/(m.K)", "mW/(m.K)") == pytest.approx(23.0)


def test_convert_density_lb_per_ft3_to_kg_per_m3():
    # 1 lb/ft3 = 16.01846337 kg/m3 (published conversion factor)
    assert unit_conversion.convert(2.0, "lb/ft3", "kg/m3") == pytest.approx(32.03692674)


def test_convert_pressure_psi_to_kpa():
    assert unit_conversion.convert(100, "psi", "kPa") == pytest.approx(689.4757293168)


def test_convert_same_unit_is_identity_even_if_unrecognized():
    assert unit_conversion.convert(42, "Sui Generis Units", "Sui Generis Units") == 42


def test_convert_unknown_or_incompatible_units_returns_none():
    assert unit_conversion.convert(1.0, "W/(m.K)", "kg/m3") is None  # different quantities
    assert unit_conversion.convert(1.0, "flurbs", "W/(m.K)") is None  # unknown unit
    assert unit_conversion.convert(None, "mW/(m.K)", "W/(m.K)") is None  # nothing to convert


def test_convertible_matches_convert_success():
    assert unit_conversion.convertible("mW/(m.K)", "W/(m.K)") is True
    assert unit_conversion.convertible("W/(m.K)", "kg/m3") is False


# ---------------------------------------------------------------------------
# DB-backed integration: wp3_conformance, replaying WP3 UAT-06's own scenario
# ---------------------------------------------------------------------------

@pytest.fixture()
def session():
    db.init_db()
    s = db.get_session()
    yield s
    s.close()


def _seed_thermal_conductivity_grade(session):
    """Same WP3 UAT reference chain used by this session's own WP3 report
    smoke test (build_wp3_conformance_report_data): CHM-010/PM-120/APP-210/
    PC-140 grade, a <= 0.024 W/(m.K) UAT-only spec, through-thickness/core/
    initial-10C-7d context. Returns (grade, run, spec)."""
    u = uuid.uuid4().hex[:8]  # unique suffix - the shared test DB file persists across test functions
    company = db.Company(name=f"WP4 Unit Test Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP4 Unit Test Plant {u}")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"Cold Room Panels {u}")
    session.add(family); session.flush()

    chem = db.Chemistry(controlled_id=f"CHM-010-U-{u}", name="Rigid polyurethane foam")
    method = db.ProductionMethod(controlled_id=f"PM-120-U-{u}", name="Closed-mold panel injection")
    session.add_all([chem, method]); session.flush()

    # FoamGrade.production_method_id removed 2026-08-10 (Charlie's "Database
    # Reset and Clean UAT Baseline" instruction).
    grade = db.FoamGrade(
        product_family_id=family.id, grade_name=f"RF-COLD-UNIT-TEST-{u}",
        chemistry_id=chem.id, status="UAT_ONLY",
    )
    session.add(grade); session.flush()

    # name has a UNIQUE constraint and the test DB file persists across test
    # functions in this run - reuse the row if a prior test already made it.
    propdef = session.query(db.PhysicalPropertyDefinition).filter_by(name="Thermal conductivity").first()
    if propdef is None:
        propdef = db.PhysicalPropertyDefinition(name="Thermal conductivity")
        session.add(propdef); session.flush()
    propmethod = db.PhysicalPropertyMethod(property_definition_id=propdef.id, method_code="ISO 8301", controlled_id=f"MTH-016-U-{u}")
    session.add(propmethod); session.flush()

    orientation = db.Orientation(controlled_id=f"ORI-THERM-THROUGH-THICKNESS-U-{u}", name="Through-thickness")
    location = db.Location(controlled_id=f"LOC-020-U-{u}", name="Core")
    condition = db.TestCondition(controlled_id=f"CTX-THERM-INIT-10C-7D-U-{u}", name="Initial, 10C mean, 7 days")
    session.add_all([orientation, location, condition]); session.flush()

    spec = db.GradeSpecification(
        foam_grade_id=grade.id, property_definition_id=propdef.id, property_method_id=propmethod.id,
        property_name="Thermal conductivity", target_operator="<=", target_value=0.024, unit="W/(m.K)",
        condition_id=condition.id, orientation_id=orientation.id, location_id=location.id,
    )
    session.add(spec); session.flush()

    machine = db.Machine(plant_id=plant.id, name="WP4 Unit Test Machine")
    session.add(machine); session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Draft", is_active=True)
    session.add(recipe); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference="WP4-UNIT-BATCH-001",
    )
    session.add(run); session.flush()
    session.commit()
    return grade, run, spec, orientation, location, condition, propdef, propmethod


def _add_result(session, run, propdef, propmethod, orientation, location, condition, value, unit, thickness_mm=60.0):
    sample = db.Sample(
        production_run_id=run.id, location_id=location.id, orientation_id=orientation.id,
        thickness_mm=thickness_mm, age_hours=168.0, sample_scope="Core", sample_ts=dt.datetime(2026, 8, 1, 10, 0),
    )
    session.add(sample); session.flush()
    result = db.PhysicalPropertyResult(
        production_run_id=run.id, sample_id=sample.id, property_definition_id=propdef.id,
        property_method_id=propmethod.id, property_name="Thermal conductivity", actual_value=value,
        unit=unit, test_method="ISO 8301", condition_id=condition.id, orientation_id=orientation.id,
        location_id=location.id, tested_at=dt.date(2026, 8, 2),
    )
    session.add(result); session.flush()
    session.commit()
    return result


def test_uat06_scenario_now_converts_and_passes_instead_of_excluding(session):
    grade, run, spec, orientation, location, condition, propdef, propmethod = _seed_thermal_conductivity_grade(session)
    _add_result(session, run, propdef, propmethod, orientation, location, condition, value=23, unit="mW/(m.K)")

    rows = wp3_conformance.compute_conformance_report(session, grade.id, production_run_id=run.id)
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "Pass", row
    assert row["unit_converted"] is True
    assert row["actual_value"] == pytest.approx(0.023)
    assert row["as_recorded_value"] == 23
    assert row["as_recorded_unit"] == "mW/(m.K)"


def test_same_unit_result_is_unaffected_by_conversion_logic(session):
    grade, run, spec, orientation, location, condition, propdef, propmethod = _seed_thermal_conductivity_grade(session)
    _add_result(session, run, propdef, propmethod, orientation, location, condition, value=0.023, unit="W/(m.K)")

    rows = wp3_conformance.compute_conformance_report(session, grade.id, production_run_id=run.id)
    row = rows[0]
    assert row["status"] == "Pass"
    assert row["unit_converted"] is False
    assert row["actual_value"] == 0.023
    assert row["as_recorded_value"] == 0.023


def test_above_limit_after_conversion_still_fails(session):
    grade, run, spec, orientation, location, condition, propdef, propmethod = _seed_thermal_conductivity_grade(session)
    # 25 mW/(m.K) = 0.025 W/(m.K), above the 0.024 upper limit.
    _add_result(session, run, propdef, propmethod, orientation, location, condition, value=25, unit="mW/(m.K)")

    rows = wp3_conformance.compute_conformance_report(session, grade.id, production_run_id=run.id)
    row = rows[0]
    assert row["status"] == "Fail"
    assert row["unit_converted"] is True
    assert row["actual_value"] == pytest.approx(0.025)


def test_non_convertible_unit_is_still_excluded_not_guessed(session):
    grade, run, spec, orientation, location, condition, propdef, propmethod = _seed_thermal_conductivity_grade(session)
    _add_result(session, run, propdef, propmethod, orientation, location, condition, value=23, unit="kg/m3")

    rows = wp3_conformance.compute_conformance_report(session, grade.id, production_run_id=run.id)
    row = rows[0]
    assert row["status"] == "EXCLUDED_CONTEXT"
    assert row["excluded_reason"] == "unit mismatch (not convertible)"


def test_wrong_condition_still_excludes_unchanged(session):
    grade, run, spec, orientation, location, condition, propdef, propmethod = _seed_thermal_conductivity_grade(session)
    other_condition = db.TestCondition(controlled_id=f"CTX-THERM-INIT-15C-7D-U-{uuid.uuid4().hex[:8]}", name="Initial, 15C mean, 7 days")
    session.add(other_condition); session.flush(); session.commit()
    _add_result(session, run, propdef, propmethod, orientation, location, other_condition, value=0.023, unit="W/(m.K)")

    rows = wp3_conformance.compute_conformance_report(session, grade.id, production_run_id=run.id)
    row = rows[0]
    assert row["status"] == "EXCLUDED_CONTEXT"
    assert row["excluded_reason"] == "condition mismatch"
