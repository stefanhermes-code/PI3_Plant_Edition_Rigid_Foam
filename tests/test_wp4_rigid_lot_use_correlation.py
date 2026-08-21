"""WP4 (Converged Joint Implementation Plan, section 7.5) tests for
wp3_conformance.rigid_actual_usage_dataframe() and
rank_lot_use_actual_correlations() - the rigid-foam equivalents of
analytics.actual_usage_dataframe()/rank_component_actual_correlations(),
sourced from RawMaterialLotUse.mass_kg (added this WP4 batch via a Supabase
migration - see db.py's RawMaterialLotUse.mass_kg docstring) instead of
ComponentStreamReading.flow_total_qty.

NOTE: as of this writing (2026-08-07) no page or CSV import in this app
actually writes mass_kg yet - these functions are the read side of the
schema addition, seeded directly here since there's no capture UI to seed
through. See rigid_actual_usage_dataframe's own docstring for why that's a
separately tracked gap, not something these tests paper over.
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
    company = db.Company(name=f"WP4 LotUse Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP4 LotUse Plant {u}")
    session.add(plant); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"Cold Room Panels {u}")
    session.add(family); session.flush()

    chem = db.Chemistry(controlled_id=f"CHM-010-L-{u}", name="Rigid polyurethane foam")
    method = db.ProductionMethod(controlled_id=f"PM-120-L-{u}", name="Closed-mold panel injection")
    session.add_all([chem, method]); session.flush()

    # FoamGrade.production_method_id removed 2026-08-10 (Charlie's "Database
    # Reset and Clean UAT Baseline" instruction).
    grade = db.FoamGrade(
        pu_material_family_id=family.id, grade_name=f"RF-COLD-LOTUSE-{u}",
        chemistry_id=chem.id, status="UAT_ONLY",
    )
    session.add(grade); session.flush()

    propdef = session.query(db.PhysicalPropertyDefinition).filter_by(name="Thermal conductivity").first()
    if propdef is None:
        propdef = db.PhysicalPropertyDefinition(name="Thermal conductivity")
        session.add(propdef); session.flush()
    propmethod = db.PhysicalPropertyMethod(property_definition_id=propdef.id, method_code="ISO 8301", controlled_id=f"MTH-016-L-{u}")
    session.add(propmethod); session.flush()

    orientation = db.Orientation(controlled_id=f"ORI-THROUGH-L-{u}", name="Through-thickness")
    location = db.Location(controlled_id=f"LOC-CORE-L-{u}", name="Core")
    condition = db.TestCondition(controlled_id=f"CTX-INIT-L-{u}", name="Initial, 10C mean, 7 days")
    session.add_all([orientation, location, condition]); session.flush()

    spec = db.GradeSpecification(
        foam_grade_id=grade.id, property_definition_id=propdef.id, property_method_id=propmethod.id,
        property_name="Thermal conductivity", target_operator="<=", target_value=0.030, unit="W/(m.K)",
        condition_id=condition.id, orientation_id=orientation.id, location_id=location.id,
    )
    session.add(spec); session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"WP4 LotUse Machine {u}")
    session.add(machine); session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Draft", is_active=True)
    session.add(recipe); session.flush()
    session.add(db.RecipeComponent(
        recipe_version_id=recipe.id, raw_material_name="Polyol A", role_in_formulation="Base Polyol", php=100,
    ))
    session.add(db.RecipeComponent(
        recipe_version_id=recipe.id, raw_material_name="Flame Retardant X", role_in_formulation="Additive", php=8,
    ))
    session.flush(); session.commit()
    return grade, plant, machine, recipe, spec, propdef, propmethod, orientation, location, condition


def _seed_run(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
              run_date, polyol_mass, additive_mass, actual_value, split_additive_across_two_lots=False):
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        run_date=run_date, batch_reference=f"BATCH-{run_date}",
    )
    session.add(run); session.flush()
    session.add(db.RawMaterialLotUse(
        production_run_id=run.id, component_stream_name="Polyol A", supplier_lot_no="LOT-P1", mass_kg=polyol_mass,
    ))
    if split_additive_across_two_lots:
        session.add(db.RawMaterialLotUse(
            production_run_id=run.id, component_stream_name="Flame Retardant X", supplier_lot_no="LOT-F1",
            mass_kg=additive_mass / 2,
        ))
        session.add(db.RawMaterialLotUse(
            production_run_id=run.id, component_stream_name="Flame Retardant X", supplier_lot_no="LOT-F2",
            mass_kg=additive_mass / 2,
        ))
    else:
        session.add(db.RawMaterialLotUse(
            production_run_id=run.id, component_stream_name="Flame Retardant X", supplier_lot_no="LOT-F1",
            mass_kg=additive_mass,
        ))
    sample = db.Sample(
        production_run_id=run.id, location_id=location.id, orientation_id=orientation.id,
        thickness_mm=60.0, age_hours=168.0, sample_scope="Core", sample_ts=dt.datetime.combine(run_date, dt.time(10, 0)),
    )
    session.add(sample); session.flush()
    result = db.PhysicalPropertyResult(
        production_run_id=run.id, sample_id=sample.id, property_definition_id=propdef.id,
        property_method_id=propmethod.id, property_name="Thermal conductivity", actual_value=actual_value,
        unit="W/(m.K)", test_method="ISO 8301", condition_id=condition.id, orientation_id=orientation.id,
        location_id=location.id, tested_at=run_date,
    )
    session.add(result); session.flush(); session.commit()
    return run


def test_rigid_actual_usage_dataframe_empty_with_no_lot_uses(session):
    grade, *_ = _seed_grade(session)
    df = wp3_conformance.rigid_actual_usage_dataframe(session, grade.id)
    assert df.empty


def test_rigid_actual_usage_dataframe_sums_split_lots_and_normalizes_to_polyol(session):
    grade, plant, machine, recipe, spec, propdef, propmethod, orientation, location, condition = _seed_grade(session)
    run = _seed_run(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
                     dt.date(2026, 8, 1), polyol_mass=500.0, additive_mass=40.0, actual_value=0.028,
                     split_additive_across_two_lots=True)

    df = wp3_conformance.rigid_actual_usage_dataframe(session, grade.id)
    assert len(df) == 2  # one row per material for this run, lots already summed
    additive_row = df[df["component_stream_name"] == "Flame Retardant X"].iloc[0]
    assert additive_row["mass_kg"] == pytest.approx(40.0)  # 20 + 20 from the two lots
    assert additive_row["actual_php_equivalent"] == pytest.approx(8.0)  # 40/500 * 100
    polyol_row = df[df["component_stream_name"] == "Polyol A"].iloc[0]
    assert polyol_row["actual_php_equivalent"] == pytest.approx(100.0)


def test_rank_lot_use_actual_correlations_finds_correlated_material(session):
    grade, plant, machine, recipe, spec, propdef, propmethod, orientation, location, condition = _seed_grade(session)
    # Flame retardant dosage 6,7,8,9 php -> thermal conductivity 0.026,0.027,0.028,0.029 (perfectly linear)
    for i, (additive_mass, value) in enumerate([(30, 0.026), (35, 0.027), (40, 0.028), (45, 0.029)]):
        _seed_run(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
                  dt.date(2026, 8, 1 + i), polyol_mass=500.0, additive_mass=additive_mass, actual_value=value)

    ranked = wp3_conformance.rank_lot_use_actual_correlations(session, grade.id, spec.id, min_runs=3)
    assert not ranked.empty
    row = ranked[ranked["raw_material_name"] == "Flame Retardant X"].iloc[0]
    assert row["n_runs"] == 4
    assert row["correlation"] == pytest.approx(1.0, abs=1e-6)


def test_rank_lot_use_actual_correlations_excludes_below_min_runs(session):
    grade, plant, machine, recipe, spec, propdef, propmethod, orientation, location, condition = _seed_grade(session)
    for i, (additive_mass, value) in enumerate([(30, 0.026), (45, 0.029)]):
        _seed_run(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
                  dt.date(2026, 9, 1 + i), polyol_mass=500.0, additive_mass=additive_mass, actual_value=value)

    ranked = wp3_conformance.rank_lot_use_actual_correlations(session, grade.id, spec.id, min_runs=3)
    assert ranked.empty


def test_rank_lot_use_actual_correlations_empty_for_wrong_spec_id(session):
    grade, plant, machine, recipe, spec, propdef, propmethod, orientation, location, condition = _seed_grade(session)
    for i, (additive_mass, value) in enumerate([(30, 0.026), (35, 0.027), (40, 0.028)]):
        _seed_run(session, plant, machine, recipe, grade, propdef, propmethod, orientation, location, condition,
                  dt.date(2026, 10, 1 + i), polyol_mass=500.0, additive_mass=additive_mass, actual_value=value)

    ranked = wp3_conformance.rank_lot_use_actual_correlations(session, grade.id, spec_id=999999, min_runs=3)
    assert ranked.empty
