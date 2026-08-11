"""CR-07 (Product Grade Physical Property Target Architecture and Quality
Alignment, Charlie's instruction document
PI3_Rigid_Foam_Phase_1_CR07_Product_Grade_Physical_Property_Target_
Architecture_and_Quality_Alignment_for_UAT.docx, 2026-08-11).

UAT finding this closes: Add Product Grade had two fixed fields (Target
density, Target hardness (N, 40% ILD) - the second being Flexible Foam
legacy content with no place in the Rigid Foam property architecture) plus
a separate, simpler "other target properties" list (foam_grade_target_
properties) with no target-type/method/condition richness. This batch
removes both fixed fields from the active UI and retires that simpler list
in favor of a single dynamic Product Grade Property Targets section built
on GradeSpecification (extended here with target_type/class_value) - the
same model wp3_conformance.py already uses to evaluate live Quality
conformance, so a grade's targets and its Quality results share one
Property_ID structure by construction, not by convention.

Mirrors the established AUTH_DISABLED AppTest pattern (see
test_pm_hierarchy_pages_smoke.py). That file's own docstring documents why
this suite tests the Add-flow via AppTest but the Edit/property-target
flow (Save/Remove/Add a property target) directly against the database
instead: all of it sits behind pages/2's clickable_table row-selection,
which AppTest has no way to simulate (session_state presets get wiped by
clickable_table's own "no click event yet -> pop the selection" branch on
every run). The database-level assertions below exercise the exact same
SQLAlchemy operations the page's form-submit blocks perform - same model,
same session, same commit - so they verify the real persistence behavior,
not a mock of it.

Usage: python -m pytest tests/test_cr07_grade_property_targets.py
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError
from streamlit.testing.v1 import AppTest

import db
import wp3_conformance as wc

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE2 = os.path.join(APP_DIR, "pages", "2_Product_Family_Foam_Grade.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_grade():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR07 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR07 Plant {u}")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"CR07 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"CR07-Grade-{u}")
    session.add(grade); session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", is_active=True)
    session.add(recipe); session.flush()

    density_prop = db.PhysicalPropertyDefinition(
        name=f"Core density {u}", controlled_id=f"PROP-CR07-DENS-{u}",
        allowed_target_type="Nominal/Range", default_uom="kg/m3",
    )
    thermal_prop = db.PhysicalPropertyDefinition(
        name=f"Thermal conductivity {u}", controlled_id=f"PROP-CR07-THERM-{u}",
        allowed_target_type="Maximum/Maximum absolute", default_uom="W/(m.K)",
    )
    fire_prop = db.PhysicalPropertyDefinition(
        name=f"Fire class {u}", controlled_id=f"PROP-CR07-FIRE-{u}",
        allowed_target_type="Class",
    )
    session.add_all([density_prop, thermal_prop, fire_prop]); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "grade_id": grade.id,
        "grade_name": grade.grade_name, "recipe_id": recipe.id,
        "density_prop_id": density_prop.id, "density_prop_name": density_prop.name,
        "thermal_prop_id": thermal_prop.id, "thermal_prop_name": thermal_prop.name,
        "fire_prop_id": fire_prop.id, "fire_prop_name": fire_prop.name,
    }
    session.close()
    return ids


def _run(page_path):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


def test_add_product_grade_form_has_no_fixed_density_or_hardness_fields(seeded_grade):
    """CR-07 acceptance criterion (section 9, first bullet): 'Add Product
    Grade contains no fixed density or 40% ILD hardness input fields.'"""
    at = _run(PAGE2)
    assert not at.exception, f"Unhandled exception loading Product Family & Foam Grade: {at.exception}"

    number_input_labels = {ni.label for ni in at.number_input}
    assert "Target density (kg/m3)" not in number_input_labels, (
        "Add Product Grade must not have a fixed Target density field - see CR-07"
    )
    assert "Target hardness (N, 40% ILD)" not in number_input_labels, (
        "Add Product Grade must not have a fixed Target hardness field - see CR-07"
    )


def test_grade_spec_target_type_vocabulary_matches_cr07(seeded_grade):
    """CR-07 section 5's exact controlled vocabulary: Nominal, Range,
    Minimum, Maximum, Maximum absolute, Class."""
    assert set(db.GRADE_SPEC_TARGET_TYPES) == {
        "Nominal", "Minimum", "Maximum", "Maximum absolute", "Range", "Class",
    }
    # Every target type maps to a real evaluation operator (or "class" for
    # the one type with no numeric evaluation - see below).
    assert set(db.GRADE_SPEC_TARGET_TYPE_OPERATORS) == set(db.GRADE_SPEC_TARGET_TYPES)


@pytest.mark.parametrize(
    "target_type,target_value,lower,upper,actual,expected_verdict",
    [
        ("Nominal", 38.0, None, None, 38.0, "Pass"),
        ("Nominal", 38.0, None, None, 40.0, "Fail"),
        ("Minimum", 150.0, None, None, 160.0, "Pass"),
        ("Minimum", 150.0, None, None, 140.0, "Fail"),
        ("Maximum", 0.024, None, None, 0.021, "Pass"),
        ("Maximum", 0.024, None, None, 0.030, "Fail"),
        ("Maximum absolute", 0.024, None, None, 0.021, "Pass"),
        ("Range", None, 35.0, 45.0, 40.0, "Pass"),
        ("Range", None, 35.0, 45.0, 50.0, "Fail"),
    ],
)
def test_target_type_evaluates_via_derived_operator(
    seeded_grade, target_type, target_value, lower, upper, actual, expected_verdict
):
    """Each CR-07 target_type writes the matching target_operator (see
    db.GRADE_SPEC_TARGET_TYPE_OPERATORS) that wp3_conformance.
    evaluate_specification actually evaluates against - proving the new
    UI-facing vocabulary and the pre-existing evaluation engine agree."""
    ids = seeded_grade
    session = db.get_session()
    spec = db.GradeSpecification(
        foam_grade_id=ids["grade_id"], property_definition_id=ids["density_prop_id"],
        property_name=ids["density_prop_name"], target_type=target_type,
        target_operator=db.GRADE_SPEC_TARGET_TYPE_OPERATORS[target_type],
        target_value=target_value, lower_limit=lower, upper_limit=upper, unit="kg/m3",
    )
    session.add(spec); session.commit()

    verdict, margin = wc.evaluate_specification(spec, actual)
    assert verdict == expected_verdict, f"{target_type}: expected {expected_verdict}, got {verdict} (margin {margin})"


def test_class_target_is_captured_but_not_numerically_evaluated(seeded_grade):
    """CR-07 section 5: Class 'uses a controlled/text class value.' There is
    no text-valued actual result to compare it against today (see db.py's
    GradeSpecification.class_value docstring), so evaluate_specification
    correctly returns (None, None) - 'nothing to compare', not a false
    Pass/Fail - while the class_value itself is still stored and readable."""
    ids = seeded_grade
    session = db.get_session()
    spec = db.GradeSpecification(
        foam_grade_id=ids["grade_id"], property_definition_id=ids["fire_prop_id"],
        property_name=ids["fire_prop_name"], target_type="Class",
        target_operator=db.GRADE_SPEC_TARGET_TYPE_OPERATORS["Class"],
        class_value="Class B",
    )
    session.add(spec); session.commit()

    verdict, margin = wc.evaluate_specification(spec, 1.0)
    assert verdict is None and margin is None

    reloaded = session.get(db.GradeSpecification, spec.id)
    assert reloaded.class_value == "Class B"
    assert reloaded.target_operator == "class"


def test_duplicate_property_target_blocked_at_db_level(seeded_grade):
    """CR-07 acceptance criterion: 'Duplicate Product Grade + Property_ID
    combinations are blocked in both UI and write path.' The UI blocks it
    structurally (used properties drop out of the add-picker); this is the
    write-path backstop - uq_grade_specification_grade_property."""
    ids = seeded_grade
    session = db.get_session()
    session.add(db.GradeSpecification(
        foam_grade_id=ids["grade_id"], property_definition_id=ids["density_prop_id"],
        property_name=ids["density_prop_name"], target_type="Nominal",
        target_operator="=", target_value=38.0,
    ))
    session.commit()

    session.add(db.GradeSpecification(
        foam_grade_id=ids["grade_id"], property_definition_id=ids["density_prop_id"],
        property_name=ids["density_prop_name"], target_type="Nominal",
        target_operator="=", target_value=40.0,
    ))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    count = (
        session.query(db.GradeSpecification)
        .filter(
            db.GradeSpecification.foam_grade_id == ids["grade_id"],
            db.GradeSpecification.property_definition_id == ids["density_prop_id"],
        )
        .count()
    )
    assert count == 1, "Duplicate insert must not have landed a second row"


def test_available_properties_excludes_used_and_readmits_after_removal(seeded_grade):
    """Mirrors pages/2_Product_Family_Foam_Grade.py's own 'used_property_ids
    / available_properties' computation exactly - CR-07: 'A property already
    selected on the Product Grade is absent from subsequent property
    selectors until removed,' and readmitted once it is."""
    ids = seeded_grade
    session = db.get_session()
    all_props = session.query(db.PhysicalPropertyDefinition).all()
    assert len(all_props) == 3

    def _available():
        existing = (
            session.query(db.GradeSpecification)
            .filter(db.GradeSpecification.foam_grade_id == ids["grade_id"])
            .all()
        )
        used_ids = {s.property_definition_id for s in existing if s.property_definition_id}
        return [p for p in all_props if p.id not in used_ids]

    assert len(_available()) == 3, "Nothing added yet - all 3 properties should be available"

    spec = db.GradeSpecification(
        foam_grade_id=ids["grade_id"], property_definition_id=ids["density_prop_id"],
        property_name=ids["density_prop_name"], target_type="Nominal",
        target_operator="=", target_value=38.0,
    )
    session.add(spec); session.commit()

    remaining = _available()
    assert len(remaining) == 2
    assert ids["density_prop_id"] not in {p.id for p in remaining}, (
        "Density must drop out of the picker once it has a target"
    )

    session.delete(spec); session.commit()
    assert len(_available()) == 3, "Removing the target should return the property to the picker"


def test_all_properties_used_leaves_nothing_available(seeded_grade):
    """CR-07: 'When all available properties have been selected, disable
    the Add property target action and show that all available properties
    are already used.' Verifies the underlying condition the page's
    'available_properties' emptiness check renders that message from."""
    ids = seeded_grade
    session = db.get_session()
    all_props = session.query(db.PhysicalPropertyDefinition).all()
    for p in all_props:
        session.add(db.GradeSpecification(
            foam_grade_id=ids["grade_id"], property_definition_id=p.id,
            property_name=p.name, target_type="Nominal", target_operator="=", target_value=1.0,
        ))
    session.commit()

    used_ids = {
        s.property_definition_id for s in
        session.query(db.GradeSpecification).filter(db.GradeSpecification.foam_grade_id == ids["grade_id"]).all()
    }
    available = [p for p in all_props if p.id not in used_ids]
    assert available == [], "Every controlled property has a target - nothing should remain available"


def test_delete_foam_grade_cascade_removes_grade_specifications(seeded_grade):
    """CR-07 section 6: 'Deleting a Product Grade removes or safely cascades
    its property-target associations.' Regression guard for a real gap this
    batch fixed: cascades.delete_foam_grade_cascade bulk-deletes the grade
    row directly (bypassing the ORM-level cascade='all, delete-orphan' on
    FoamGrade.specifications, which only fires on session.delete(instance))
    and, before this fix, never explicitly deleted grade_specifications at
    all - deleting a grade would have orphaned its property-target rows."""
    from cascades import delete_foam_grade_cascade

    ids = seeded_grade
    session = db.get_session()
    session.add(db.GradeSpecification(
        foam_grade_id=ids["grade_id"], property_definition_id=ids["density_prop_id"],
        property_name=ids["density_prop_name"], target_type="Nominal", target_operator="=", target_value=38.0,
    ))
    session.commit()
    assert session.query(db.GradeSpecification).filter(
        db.GradeSpecification.foam_grade_id == ids["grade_id"]
    ).count() == 1

    delete_foam_grade_cascade(session, ids["grade_id"])
    session.commit()

    assert session.query(db.GradeSpecification).filter(
        db.GradeSpecification.foam_grade_id == ids["grade_id"]
    ).count() == 0, "grade_specifications rows must not survive their parent grade's deletion"
    assert session.get(db.FoamGrade, ids["grade_id"]) is None


def test_foam_grade_dependency_counts_include_property_targets(seeded_grade):
    """cascades.foam_grade_dependency_counts now names property-target rows
    in the delete-confirmation warning, same as every other dependent
    record type - CR-07 batch fix, paired with the cascade-delete fix above."""
    from cascades import foam_grade_dependency_counts

    ids = seeded_grade
    session = db.get_session()
    session.add_all([
        db.GradeSpecification(
            foam_grade_id=ids["grade_id"], property_definition_id=ids["density_prop_id"],
            property_name=ids["density_prop_name"], target_type="Nominal", target_operator="=", target_value=38.0,
        ),
        db.GradeSpecification(
            foam_grade_id=ids["grade_id"], property_definition_id=ids["thermal_prop_id"],
            property_name=ids["thermal_prop_name"], target_type="Maximum", target_operator="<=", target_value=0.024,
        ),
    ])
    session.commit()

    counts = foam_grade_dependency_counts(session, ids["grade_id"])
    assert counts.get("product grade property target(s)") == 2


def test_quality_result_shares_property_id_with_grade_target(seeded_grade):
    """CR-07 section 7 (Quality alignment): 'Quality results must use the
    same Property_ID as Product Grade targets' and 'PI3 can compare the
    actual Quality result with the applicable target.' Proves the link is
    structural (both reference physical_property_definitions.id) by
    running a real result through wp3_conformance.compute_conformance_report
    - the same live-evaluation path Recipe Optimization's achievement
    summary and the Batch Release report both already use."""
    ids = seeded_grade
    session = db.get_session()
    session.add(db.GradeSpecification(
        foam_grade_id=ids["grade_id"], property_definition_id=ids["density_prop_id"],
        property_name=ids["density_prop_name"], target_type="Nominal",
        target_operator="=", target_value=38.0, unit="kg/m3",
    ))
    session.commit()

    run = db.ProductionRun(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"], recipe_version_id=ids["recipe_id"],
        run_date=dt.date.today(),
    )
    session.add(run); session.flush()
    session.add(db.PhysicalPropertyResult(
        production_run_id=run.id, property_definition_id=ids["density_prop_id"],
        property_name=ids["density_prop_name"], actual_value=38.0, unit="kg/m3",
    ))
    session.commit()

    report = wc.compute_conformance_report(session, ids["grade_id"], production_run_id=run.id)
    assert len(report) == 1
    assert report[0]["status"] == "Pass"


def test_quality_result_without_a_grade_target_is_not_invalidated(seeded_grade):
    """CR-07 section 7: 'A Quality result may exist for a property that is
    not defined as a Product Grade target. The absence of a grade target
    does not invalidate the measurement.' No GradeSpecification is created
    for thermal_prop here - the result must simply not appear in the
    conformance report (there is nothing to evaluate it against), not error."""
    ids = seeded_grade
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"], recipe_version_id=ids["recipe_id"],
        run_date=dt.date.today(),
    )
    session.add(run); session.flush()
    session.add(db.PhysicalPropertyResult(
        production_run_id=run.id, property_definition_id=ids["thermal_prop_id"],
        property_name=ids["thermal_prop_name"], actual_value=0.021, unit="W/(m.K)",
    ))
    session.commit()

    report = wc.compute_conformance_report(session, ids["grade_id"], production_run_id=run.id)
    assert report == [], "No grade spec exists for this property - nothing to report, not an error"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
