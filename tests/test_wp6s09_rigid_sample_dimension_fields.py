"""WP6-S09 smoke test (2026-08-09, per Charlie's WP6 sequence item 2,
"implement the correct test-specimen data handling for properties that
genuinely require dimensions") for helpers.rigid_sample_dimension_fields()
and its wiring into views/9_Samples_Conditioning.py's Create Sample form.

Before this batch, Sample.orientation_id/location_id/sample_scope/
thickness_mm/age_hours (added WP3, 2026-08-06) had no capture UI anywhere
in the app - every real rigid sample's thickness_mm on file was written by
a seeding script, never through this page. This test seeds one rigid
production run with no samples yet, loads the Production Samples page via
Streamlit's AppTest (mirroring test_wp4_recipe_optimization_page_smoke.py's
established AUTH_DISABLED pattern), fills in the new widgets, submits the
Create Sample form, and confirms the resulting Sample row in the database
actually has thickness_mm/orientation_id/location_id/sample_scope set -
proving the fields render, accept input, and are persisted, not just that
the page avoids throwing an exception.

Usage: python -m pytest tests/test_wp6s09_rigid_sample_dimension_fields.py
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

PAGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "views", "9_Samples_Conditioning.py"
)


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_rigid_run_no_samples():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"WP6S09 Smoke Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP6S09 Smoke Plant {u}")
    session.add(plant); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"WP6S09 Smoke Machine {u}")
    session.add(machine); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"Rigid Family {u}")
    session.add(family); session.flush()
    chem = db.Chemistry(controlled_id=f"CHM-SMOKE-{u}", name="Rigid polyurethane foam")
    session.add(chem); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"Rigid Grade {u}", chemistry_id=chem.id, status="UAT_ONLY")
    session.add(grade); session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Draft", is_active=True)
    session.add(recipe); session.flush()

    orientation = db.Orientation(controlled_id=f"ORI-SMOKE-{u}", name="Through-thickness")
    location = db.Location(controlled_id=f"LOC-SMOKE-{u}", name="Core")
    session.add_all([orientation, location]); session.flush()

    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference="SMOKE-B1",
    )
    session.add(run); session.flush()
    session.commit()
    ids = {
        "orientation_id": orientation.id, "orientation_name": orientation.name,
        "location_id": location.id, "location_name": location.name, "run_id": run.id,
    }
    session.close()
    return ids


def _run_page():
    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


def test_dimension_fields_render_and_persist_for_rigid_sample(seeded_rigid_run_no_samples):
    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Production Samples for a rigid grade: {at.exception}"

    # The new WP6-S09 widgets should be present (only rendered for a rigid
    # grade - see helpers.rigid_sample_dimension_fields).
    selectbox_labels = [sb.label for sb in at.selectbox]
    assert "Orientation" in selectbox_labels
    assert "Location in part" in selectbox_labels
    assert "Specimen scope" in selectbox_labels
    number_input_labels = [ni.label for ni in at.number_input]
    assert "Thickness (mm)" in number_input_labels
    assert "Age at test (hours)" in number_input_labels

    # Fill in the Create Sample form: zone, orientation, location, scope,
    # thickness, age - then submit. AppTest exposes selectbox .options as
    # the already-formatted display strings (format_func applied), not the
    # underlying objects, so match on the option's rendered name/label text.
    at.selectbox(key="add_sample_orientation").set_value(seeded_rigid_run_no_samples["orientation_name"])
    at.selectbox(key="add_sample_location").set_value(seeded_rigid_run_no_samples["location_name"])
    at.selectbox(key="add_sample_scope").set_value("Core")
    at.number_input(key="add_sample_thickness").set_value(58.5)
    at.number_input(key="add_sample_age").set_value(168.0)
    submit_button = next(b for b in at.button if b.label == "Save sample")
    submit_button.click().run()
    assert not at.exception, f"Unhandled exception submitting Create Sample: {at.exception}"

    session = db.get_session()
    saved = (
        session.query(db.Sample)
        .filter(db.Sample.production_run_id == seeded_rigid_run_no_samples["run_id"])
        .order_by(db.Sample.id.desc())
        .first()
    )
    assert saved is not None, "Sample was not saved"
    assert saved.orientation_id == seeded_rigid_run_no_samples["orientation_id"]
    assert saved.location_id == seeded_rigid_run_no_samples["location_id"]
    assert saved.sample_scope == "Core"
    assert saved.thickness_mm == 58.5
    assert saved.age_hours == 168.0
    session.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
