"""WP4 (Converged Joint Implementation Plan, section 7.5) tests for
wp3_conformance.compute_grade_achievement_summary() - the rigid-foam
equivalent of the flexible app's "Does the current recipe meet target?"
expectation_summary (pages/15_Recipe_Optimization.py).

Seeds a UAT-only thermal-conductivity grade spec (<= 0.024 W/(m.K), same
reference chain as test_wp4_unit_conversion.py) across three production
runs with a deliberate mix of Pass/Fail/excluded/invalid results, and
checks the aggregation - average-of-verdicted-values, achieved verdict
against that average, per-bucket counts, and UAT production-release
gating - matches what compute_conformance_report would say about each
individual run.
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
import wp3_conformance


@pytest.fixture()
def session():
    db.init_db()
    s = db.get_session()
    yield s
    s.close()


def _seed_grade(session):
    u = uuid.uuid4().hex[:8]
    company = db.Company(name=f"WP4 Achieve Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP4 Achieve Plant {u}")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"Cold Room Panels {u}")
    session.add(family); session.flush()

    chem = db.Chemistry(controlled_id=f"CHM-010-A-{u}", name="Rigid polyurethane foam")
    method = db.ProductionMethod(controlled_id=f"PM-120-A-{u}", name="Closed-mold panel injection")
    session.add_all([chem, method]); session.flush()

    grade = db.FoamGrade(
        product_family_id=family.id, grade_name=f"RF-COLD-ACHIEVE-{u}",
        chemistry_id=chem.id, production_method_id=method.id, status="UAT_ONLY",
    )
    session.add(grade); session.flush()

    propdef = session.query(db.PhysicalPropertyDefinition).filter_by(name="Thermal conductivity").first()
    if propdef is None:
        propdef = db.PhysicalPropertyDefinition(name="Thermal conductivity")
        session.add(propdef); session.flush()
    # mandatory_context set (unconditionally - the row may have been
    # created by a different fixture in this same in-memory-SQLite test
    # session without it, since "Thermal conductivity" is looked up/reused
    # by name across several WP4 test files) to match the real PROP-005 row
    # (WP5 Wave 2, Charlie's controlled data - see wp3_conformance._property_
    # dimension_requirements), so this fixture's missing_thickness/missing_
    # orientation scenarios below still correctly trigger validate_result_
    # completeness's INVALID status under the WP6-S09 property-specific
    # completeness fix (2026-08-09) - thermal conductivity genuinely needs
    # both fields, per its own real text.
    propdef.mandatory_context = "Record mean test temperature, thickness, orientation, test age and conditioning"
    session.flush()
    propmethod = db.PhysicalPropertyMethod(property_definition_id=propdef.id, method_code="ISO 8301", controlled_id=f"MTH-016-A-{u}")
    session.add(propmethod); session.flush()

    orientation = db.Orientation(controlled_id=f"ORI-THROUGH-A-{u}", name="Through-thickness")
    location = db.Location(controlled_id=f"LOC-CORE-A-{u}", name="Core")
    condition = db.TestCondition(controlled_id=f"CTX-INIT-A-{u}", name="Initial, 10C mean, 7 days")
    session.add_all([orientation, location, condition]); session.flush()

    spec = db.GradeSpecification(
        foam_grade_id=grade.id, property_definition_id=propdef.id, property_method_id=propmethod.id,
        property_name="Thermal conductivity", target_operator="<=", target_value=0.024, unit="W/(m.K)",
        condition_id=condition.id, orientation_id=orientation.id, location_id=location.id,
    )
    session.add(spec); session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"WP4 Achieve Machine {u}")
    session.add(machine); session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Draft", is_active=True)
    session.add(recipe); session.flush()
    session.commit()
    return grade, plant, machine, recipe, spec, propdef, propmethod, orientation, location, condition


def _add_run_with_result(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
                          run_date, value, unit="W/(m.K)", batch_suffix="", missing_thickness=False, missing_orientation=False):
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        run_date=run_date, batch_reference=f"BATCH-{run_date}{batch_suffix}",
    )
    session.add(run); session.flush()
    sample = db.Sample(
        production_run_id=run.id, location_id=location.id,
        orientation_id=None if missing_orientation else orientation.id,
        thickness_mm=None if missing_thickness else 60.0, age_hours=168.0, sample_scope="Core",
        sample_ts=dt.datetime.combine(run_date, dt.time(10, 0)),
    )
    session.add(sample); session.flush()
    result = db.PhysicalPropertyResult(
        production_run_id=run.id, sample_id=sample.id, property_definition_id=propdef.id,
        property_method_id=propmethod.id, property_name="Thermal conductivity", actual_value=value,
        unit=unit, test_method="ISO 8301", condition_id=condition.id,
        orientation_id=None if missing_orientation else orientation.id, location_id=location.id,
        tested_at=run_date,
    )
    session.add(result); session.flush()
    session.commit()
    return run


def test_achievement_summary_empty_for_no_runs(session):
    grade, *_ = _seed_grade(session)
    assert wp3_conformance.compute_grade_achievement_summary(session, grade.id, []) == []


def test_achievement_summary_averages_verdicted_runs_and_flags_uat_release(session):
    grade, plant, machine, recipe, spec, propdef, propmethod, orientation, location, condition = _seed_grade(session)
    run1 = _add_run_with_result(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
                                 dt.date(2026, 8, 1), 0.022, batch_suffix="-1")
    run2 = _add_run_with_result(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
                                 dt.date(2026, 8, 2), 0.023, batch_suffix="-2")

    summary = wp3_conformance.compute_grade_achievement_summary(session, grade.id, [run1.id, run2.id])
    assert len(summary) == 1
    row = summary[0]
    assert row["property_name"] == "Thermal conductivity"
    assert row["n"] == 2
    assert row["n_fail"] == 0
    assert row["avg_actual"] == pytest.approx(0.0225)
    assert row["achieved"] == "Yes"
    assert row["production_release"] == "UAT_PASS_NO_RELEASE"


def test_achievement_summary_flips_to_no_when_average_exceeds_limit(session):
    grade, plant, machine, recipe, spec, propdef, propmethod, orientation, location, condition = _seed_grade(session)
    # Average of 0.023 and 0.026 = 0.0245, above the 0.024 upper limit.
    run1 = _add_run_with_result(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
                                 dt.date(2026, 8, 1), 0.023, batch_suffix="-1")
    run2 = _add_run_with_result(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
                                 dt.date(2026, 8, 2), 0.026, batch_suffix="-2")

    summary = wp3_conformance.compute_grade_achievement_summary(session, grade.id, [run1.id, run2.id])
    row = summary[0]
    assert row["n"] == 2
    assert row["n_fail"] == 1  # only the 0.026 run individually fails
    assert row["avg_actual"] == pytest.approx(0.0245)
    assert row["achieved"] == "No"  # but the AVERAGE is what "achieved" judges, same convention as flexible page
    assert row["production_release"] is None  # verdict is Fail, so no UAT_PASS_NO_RELEASE


def test_achievement_summary_counts_excluded_invalid_no_result_separately(session):
    grade, plant, machine, recipe, spec, propdef, propmethod, orientation, location, condition = _seed_grade(session)
    good_run = _add_run_with_result(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
                                     dt.date(2026, 8, 1), 0.022, batch_suffix="-good")
    invalid_run = _add_run_with_result(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
                                        dt.date(2026, 8, 2), 0.023, batch_suffix="-invalid", missing_thickness=True)
    no_result_run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 3), batch_reference="BATCH-no-result",
    )
    session.add(no_result_run); session.flush(); session.commit()

    summary = wp3_conformance.compute_grade_achievement_summary(
        session, grade.id, [good_run.id, invalid_run.id, no_result_run.id]
    )
    row = summary[0]
    assert row["n"] == 1  # only the good run counts toward the average/verdict
    assert row["avg_actual"] == pytest.approx(0.022)
    assert row["achieved"] == "Yes"
    assert row["n_invalid"] == 1
    assert row["n_no_result"] == 1
    assert row["n_excluded_context"] == 0
