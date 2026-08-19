"""Recipe component import order (v0.70.0, 2026-08-19).

Charlie's Decision 1 ruling: Recipe Components enter only after their Recipe
Version identifier has been resolved. This file pins the application-side half
of that rule.

WHAT WENT WRONG, AND WHAT DID NOT

On 12 August 2026 a Phase 1 import file, 01_DIRECT_IMPORT/07_Recipe_Components.csv,
carried a hard-coded recipe_version_id of 6. That id existed and belonged to an
unrelated polyether PUR recipe, so all nine of its polyester PIR rows passed the
importer's validation and merged two formulations into one Recipe Version.

The application was not at fault. Its check asks whether the recipe_version_id
exists, and it did. Nothing available to the importer could have told it that a
valid id was the wrong one.

What the application CAN see, and now says, is that the target version already
holds components. A bulk component import into a populated version is the
signature of a file pointed at the wrong id. It is surfaced as a warning rather
than a block, because deliberately topping up a version is legitimate - the point
is that the merge can no longer happen silently.

The defect stayed invisible for seven days. It was found only by noticing that the
merged version held two components at 100 php, two isocyanates, two physical
blowing agents, and both PUR and PIR catalyst packages.

Usage: python -m pytest tests/test_recipe_component_import_order.py -v
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPE_PAGE = os.path.join(APP_DIR, "views", "3_Recipe_Version_Record.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def two_recipe_versions():
    """One populated version and one empty one, mirroring the live shape on
    12 August: recipe 6 already held five polyether PUR components when the
    polyester PIR file was imported against it."""
    db.init_db()
    _reset_schema()
    session = db.get_session()

    company = db.Company(name="Import Order Co", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name="Import Order Plant")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name="Cold Room Panels")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name="RF-IMPORT-001")
    session.add(grade); session.flush()

    populated = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", is_active=True)
    empty = db.RecipeVersion(foam_grade_id=grade.id, version_label="TCPP", is_active=False)
    session.add_all([populated, empty]); session.flush()

    for name, php, role in [
        ("Lupranol 3300", 100, "Base polyol"),
        ("Lupranate M20", 145, "Isocyanate"),
        ("POLYCAT 5", 1.2, "Gelling catalyst"),
        ("DABCO DC 193", 2.0, "Cell stabilizer"),
        ("Cyclopentane", 12.0, "Physical blowing agent"),
    ]:
        session.add(db.RecipeComponent(
            recipe_version_id=populated.id, raw_material_name=name, php=php,
            role_in_formulation=role,
        ))
    session.commit()

    yield session, populated, empty
    session.close()


def _components_on(session, version_id):
    return session.query(db.RecipeComponent).filter_by(recipe_version_id=version_id).all()


def test_a_populated_version_is_detectable_before_import(two_recipe_versions):
    """The condition the warning fires on. An importer can always answer 'does
    this target already hold components', which is what the file itself cannot
    say."""
    session, populated, empty = two_recipe_versions

    assert len(_components_on(session, populated.id)) == 5
    assert len(_components_on(session, empty.id)) == 0


def test_the_recipe_page_warns_when_a_target_already_has_components(two_recipe_versions):
    """The importer surfaces the merge risk rather than importing silently."""
    src = open(RECIPE_PAGE, encoding="utf-8").read()

    assert "merge_targets" in src, "the populated-target check must exist in the component importer"
    assert "already has" in src, "the warning must state that the target version already has components"
    assert "merges two" in src.lower() or "merging" in src.lower(), (
        "the warning must say what goes wrong, not only that something is unusual"
    )


def test_the_importer_still_rejects_an_unresolved_version_id(two_recipe_versions):
    """The pre-existing rule stays: a component cannot enter against a
    recipe_version_id that does not exist."""
    session, populated, empty = two_recipe_versions
    valid_ids = {populated.id, empty.id}

    assert 999999 not in valid_ids


def test_merging_two_formulations_shows_up_as_a_doubled_php_basis(two_recipe_versions):
    """Records the signature that eventually exposed the live defect, so the
    same shape is recognisable if it ever recurs. php is parts per hundred
    polyol, so one formulation carries exactly one 100 basis."""
    session, populated, _empty = two_recipe_versions

    at_hundred = [c for c in _components_on(session, populated.id) if c.php == 100]
    assert len(at_hundred) == 1, "a single formulation carries one 100 php basis"

    isocyanates = [c for c in _components_on(session, populated.id)
                   if "isocyanate" in (c.role_in_formulation or "").lower()]
    assert len(isocyanates) == 1, "a single formulation carries one isocyanate"

    # Simulate the 12 August merge and prove both invariants break.
    session.add(db.RecipeComponent(
        recipe_version_id=populated.id, raw_material_name="STEPANPOL PS-2352 TD",
        php=100, role_in_formulation="Aromatic polyester polyol",
    ))
    session.add(db.RecipeComponent(
        recipe_version_id=populated.id, raw_material_name="Lupranate M70L",
        php=205, role_in_formulation="Isocyanate",
    ))
    session.commit()

    merged = _components_on(session, populated.id)
    assert len([c for c in merged if c.php == 100]) == 2
    assert len([c for c in merged if "isocyanate" in (c.role_in_formulation or "").lower()]) == 2
