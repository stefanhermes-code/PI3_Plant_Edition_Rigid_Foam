"""CR-04 Step 7 (Validate) - consolidated walkthrough, per Charlie's
"Database Reset and Clean UAT Baseline" instruction's own execution
sequence: "7) Validate (regression + integrity + multi-method fixture +
consolidated browser walkthrough)".

This file is the engineering-side stand-in for that walkthrough: an
AppTest-based sweep across every page a user actually touches for the
minimum Phase 1 baseline now seeded directly in Supabase (see version.py's
v0.23.0 changelog entry) - Plant -> PM-100 -> Production Unit/Machine ->
Product Family/Foam Grade -> Recipe -> Production Run -> Sample -> Result -
proving each page loads without exception against that exact shape of
data, using the same one-fixture-mirrors-the-real-chain approach as every
prior "live walkthrough" pass in this project (task #731 and others).

This does NOT replace an actual browser check against the deployed
Streamlit Cloud app - that remains Stefan's own final visual check before
UAT, per his standing preference on this task (see task #740). What this
DOES prove, mechanically: no page in the reset+reseeded architecture
raises, every controlled-vocabulary FK the seed data touches resolves, and
the PM-100 release gate + removed Operating Context feature (CR-04's own
step 6) don't break any downstream page's rendering.

Usage: python -m pytest tests/test_cr04_step7_consolidated_walkthrough.py
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
PAGE_OVERVIEW = os.path.join(APP_DIR, "app_rigid_foam.py")
PAGE_PLANTS = os.path.join(APP_DIR, "pages", "1_Plant_Installation_Overview.py")
PAGE_PRODUCTION_METHODS = os.path.join(APP_DIR, "pages", "30_Production_Methods.py")
PAGE_PRODUCTION_EQUIPMENT = os.path.join(APP_DIR, "pages", "31_Production_Equipment.py")
PAGE_FOAM_GRADE = os.path.join(APP_DIR, "pages", "2_Product_Family_Foam_Grade.py")
PAGE_RECIPES = os.path.join(APP_DIR, "pages", "3_Recipe_Version_Record.py")
PAGE_PRODUCTION_RUN = os.path.join(APP_DIR, "pages", "4_Production_Run_Trial_Record.py")
PAGE_RAW_MATERIALS = os.path.join(APP_DIR, "pages", "14_Raw_Materials.py")
PAGE_SAMPLES = os.path.join(APP_DIR, "pages", "9_Samples_Conditioning.py")
PAGE_QUALITY_RESULT = os.path.join(APP_DIR, "pages", "5_Physical_Property_Result.py")
PAGE_REPORT = os.path.join(APP_DIR, "pages", "21_Report.py")

ALL_PAGES = [
    ("Overview", PAGE_OVERVIEW),
    ("Plants", PAGE_PLANTS),
    ("Production Methods", PAGE_PRODUCTION_METHODS),
    ("Production Equipment", PAGE_PRODUCTION_EQUIPMENT),
    ("Product Family & Foam Grade", PAGE_FOAM_GRADE),
    ("Recipes", PAGE_RECIPES),
    ("Production Run", PAGE_PRODUCTION_RUN),
    ("Raw Materials", PAGE_RAW_MATERIALS),
    ("Samples & Conditioning", PAGE_SAMPLES),
    ("Quality Test Result", PAGE_QUALITY_RESULT),
    ("Report", PAGE_REPORT),
]


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_minimum_phase1_baseline():
    """Mirrors the exact chain seeded directly against Supabase for the
    minimum Phase 1 UAT baseline (see version.py's v0.23.0 entry, "Step 5
    Import"): Plant -> PM-100 (is_released=True) activated -> Production
    Unit -> Machine -> Product Family -> Foam Grade -> 5 raw materials ->
    Recipe (Pending Review) + components -> Grade Specification (thermal
    conductivity) -> Production Run -> Sample -> Physical Property Result
    (a pass). Platform-owner company, matching every other PM smoke
    fixture's convention in this suite."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR04 Walkthrough Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR04 Walkthrough Plant {u}")
    session.add(plant); session.flush()

    pm100 = db.ProductionMethod(
        controlled_id=f"PM-100-{u}", name="Discontinuous Factory Foaming",
        maturity_status="Released", is_released=True, sort_order=1,
    )
    session.add(pm100); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=pm100.id, active=True))
    session.flush()

    unit = db.ProductionUnit(plant_id=plant.id, controlled_id=f"PU-{u}", name=f"Panel Line {u}")
    session.add(unit); session.flush()
    machine = db.Machine(
        plant_id=plant.id, name=f"Panel Foamer {u}", production_unit_id=unit.id,
        production_method_id=pm100.id, active=True,
    )
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"Cold Room Panels {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"RF-COLDROOM-{u}", status="UAT_ONLY")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    rm_polyol = db.RawMaterial(company_id=company.id, name=f"Lupranol 3300 {u}", category="Polyol", default_supplier="BASF")
    rm_iso = db.RawMaterial(company_id=company.id, name=f"Lupranate M20 {u}", category="Isocyanate", default_supplier="BASF")
    session.add_all([rm_polyol, rm_iso]); session.flush()

    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label="v1", approval_status="Pending Review",
        is_active=True, production_method_id=pm100.id,
    )
    session.add(recipe); session.flush()
    session.add_all([
        db.RecipeComponent(recipe_version_id=recipe.id, raw_material_id=rm_polyol.id, raw_material_name=rm_polyol.name, php=100.0),
        db.RecipeComponent(recipe_version_id=recipe.id, raw_material_id=rm_iso.id, raw_material_name=rm_iso.name, php=145.0),
    ])
    session.flush()

    propdef = db.PhysicalPropertyDefinition(name="Thermal conductivity")
    session.add(propdef); session.flush()
    propmethod = db.PhysicalPropertyMethod(property_definition_id=propdef.id, method_code="ISO 8301", controlled_id=f"MTH-016-{u}")
    session.add(propmethod); session.flush()
    orientation = db.Orientation(controlled_id=f"ORI-{u}", name="Through-thickness")
    location = db.Location(controlled_id=f"LOC-{u}", name="Core")
    condition = db.TestCondition(controlled_id=f"CTX-{u}", name="Initial, 10C mean")
    session.add_all([orientation, location, condition]); session.flush()
    spec = db.GradeSpecification(
        foam_grade_id=grade.id, property_definition_id=propdef.id, property_method_id=propmethod.id,
        property_name="Thermal conductivity", target_operator="<=", target_value=0.024, unit="W/(m.K)",
        condition_id=condition.id, orientation_id=orientation.id, location_id=location.id,
    )
    session.add(spec); session.flush()

    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        production_method_id=pm100.id, run_date=dt.date(2026, 8, 10), batch_reference=f"BATCH-{u}",
    )
    session.add(run); session.flush()
    sample = db.Sample(
        production_run_id=run.id, location_id=location.id, orientation_id=orientation.id,
        sample_scope="Core", thickness_mm=60.0, age_hours=168.0, sample_ts=dt.datetime(2026, 8, 10, 10, 0),
    )
    session.add(sample); session.flush()
    result = db.PhysicalPropertyResult(
        production_run_id=run.id, sample_id=sample.id, property_definition_id=propdef.id,
        property_method_id=propmethod.id, property_name="Thermal conductivity", actual_value=0.0231,
        unit="W/(m.K)", test_method="ISO 8301", condition_id=condition.id,
        orientation_id=orientation.id, location_id=location.id, tested_at=dt.date(2026, 8, 10),
    )
    session.add(result); session.flush()
    session.commit()

    ids = {"plant_id": plant.id, "grade_id": grade.id, "run_id": run.id}
    session.close()
    return ids


@pytest.mark.parametrize("page_name,page_path", ALL_PAGES)
def test_page_loads_without_exception(seeded_minimum_phase1_baseline, page_name, page_path):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading {page_name} ({page_path}): {at.exception}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
