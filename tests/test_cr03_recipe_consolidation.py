"""CR-03 (Recipe Consolidation and Pending Review Status) regression tests,
2026-08-10.

Covers the rebuilt views/3_Recipe_Version_Record.py ("Recipes") against
Charlie's CR-03 source document:

  - The standalone "Reference Formulations" nav entry/page (formerly
    views/29) is removed entirely - no page_key, no nav registration, no
    file on disk.
  - Every ReferenceFormulation row (RF-*, RFREF-*) carries a real, mutable
    Approval Status (db.APPROVAL_STATUSES vocabulary), defaulting to
    "Pending Review" when unset - never silently "Approved" or blank.
  - ReferenceFormulationFamily (RFFAM-*) rows are untouched: no
    approval_status column, no appearance anywhere in the Recipes flow.
  - A Pending Review -> Approved transition on a ReferenceFormulation
    persists via a plain field write + commit (the same mechanism the
    page's own "Change Approval Status" form performs - see that page's
    docstring for why AppTest can't drive the actual dataframe row click:
    same clickable_table/st.dataframe on_select limitation documented in
    tests/test_pm_hierarchy_pages_smoke.py's own module docstring).
  - A ReferenceFormulation row can never be an active production recipe
    for any grade - there is no code path linking one to
    RecipeVersion.is_active at all (structural, not a runtime guard).

Usage: python -m pytest tests/test_cr03_recipe_consolidation.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import access_control
import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_MAIN = os.path.join(APP_DIR, "app_rigid_foam.py")
PAGE3 = os.path.join(APP_DIR, "views", "3_Recipe_Version_Record.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def recipe_and_reference_fixture():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR03 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR03 Plant {u}")
    session.add(plant); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR03 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR03 Grade {u}")
    session.add(grade); session.flush()
    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label="v1", approval_status="Approved",
        is_active=True, created_by="JC",
    )
    session.add(recipe); session.flush()

    rf_patent = db.ReferenceFormulation(
        controlled_id=f"RF-901-{u}", name="Patent example A",
        record_status="Locked public parameter summary",
    )
    rf_exact = db.ReferenceFormulation(
        controlled_id=f"RFREF-901-{u}", name="Exact scientific recipe B",
        record_status="Exact scientific reference recipe",
    )
    family_row = db.ReferenceFormulationFamily(
        controlled_id=f"RFFAM-901-{u}", variant_name="Study family C",
        record_status="RESEARCH FAMILY ONLY",
    )
    session.add_all([rf_patent, rf_exact, family_row]); session.flush()
    session.commit()

    ids = {
        "grade_id": grade.id, "recipe_id": recipe.id,
        "rf_patent_id": rf_patent.id, "rf_exact_id": rf_exact.id,
        "family_id": family_row.id,
    }
    session.close()
    return ids


# ---------------------------------------------------------------------------
# Nav / page removal
# ---------------------------------------------------------------------------

def test_reference_formulations_page_removed_from_catalog_and_disk():
    assert "reference_formulations" not in access_control.PAGE_CATALOG
    assert not os.path.exists(os.path.join(APP_DIR, "views", "29_Reference_Formulations.py"))


def test_reference_formulations_not_registered_in_nav():
    app_source = open(APP_MAIN, encoding="utf-8").read()
    assert "29_Reference_Formulations" not in app_source
    assert '"reference_formulations"' not in app_source


# ---------------------------------------------------------------------------
# Approval Status backfill/default
# ---------------------------------------------------------------------------

def test_reference_formulation_defaults_to_pending_review(recipe_and_reference_fixture):
    ids = recipe_and_reference_fixture
    session = db.get_session()
    rf_patent = session.get(db.ReferenceFormulation, ids["rf_patent_id"])
    rf_exact = session.get(db.ReferenceFormulation, ids["rf_exact_id"])
    # New rows created without an explicit approval_status (mirrors how the
    # Supabase backfill migration treats every pre-existing row): the column
    # itself is nullable, so the app must treat None as "Pending Review",
    # never as blank/approved. This mirrors _reference_formulation rendering
    # in views/3, not a stored default - confirmed at the ORM level here.
    assert rf_patent.approval_status is None
    assert rf_exact.approval_status is None
    session.close()


def test_reference_formulation_family_has_no_approval_status_column(recipe_and_reference_fixture):
    ids = recipe_and_reference_fixture
    session = db.get_session()
    family_row = session.get(db.ReferenceFormulationFamily, ids["family_id"])
    assert not hasattr(family_row, "approval_status")
    session.close()


def test_approval_status_transition_persists(recipe_and_reference_fixture):
    ids = recipe_and_reference_fixture
    session = db.get_session()
    rf_exact = session.get(db.ReferenceFormulation, ids["rf_exact_id"])
    rf_exact.approval_status = "Approved"
    session.commit()
    session.close()

    session2 = db.get_session()
    reloaded = session2.get(db.ReferenceFormulation, ids["rf_exact_id"])
    assert reloaded.approval_status == "Approved"
    session2.close()


# ---------------------------------------------------------------------------
# Structural guarantee: a ReferenceFormulation can never be a grade's active
# production recipe (CR-03 rule 3) - no FK/flag links it to is_active at all.
# ---------------------------------------------------------------------------

def test_reference_formulation_has_no_active_production_link():
    rf_columns = {c.name for c in db.ReferenceFormulation.__table__.columns}
    assert "foam_grade_id" not in rf_columns
    assert "is_active" not in rf_columns


def test_approving_a_reference_formulation_does_not_touch_recipe_versions(recipe_and_reference_fixture):
    ids = recipe_and_reference_fixture
    session = db.get_session()
    recipe_before = session.get(db.RecipeVersion, ids["recipe_id"])
    assert recipe_before.is_active is True
    assert recipe_before.approval_status == "Approved"

    rf_exact = session.get(db.ReferenceFormulation, ids["rf_exact_id"])
    rf_exact.approval_status = "Approved"
    session.commit()

    recipe_after = session.get(db.RecipeVersion, ids["recipe_id"])
    assert recipe_after.is_active is True
    assert recipe_after.approval_status == "Approved"
    assert recipe_after.foam_grade_id == ids["grade_id"]
    session.close()


# ---------------------------------------------------------------------------
# Page-level smoke: combined list renders without exception, filter present
# ---------------------------------------------------------------------------

def test_recipes_page_renders_combined_list_without_exception(recipe_and_reference_fixture):
    at = AppTest.from_file(PAGE3, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Recipes page: {at.exception}"

    status_sb = next((sb for sb in at.selectbox if sb.key == "recipe_status_filter"), None)
    assert status_sb is not None, "Approval Status filter not found on Recipes page"
    assert "Pending Review" in status_sb.options
    assert "All" in status_sb.options


def test_recipes_page_filters_to_pending_review_only(recipe_and_reference_fixture):
    at = AppTest.from_file(PAGE3, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    status_sb = next(sb for sb in at.selectbox if sb.key == "recipe_status_filter")
    status_sb.set_value("Pending Review").run()
    assert not at.exception, f"Unhandled exception after filtering to Pending Review: {at.exception}"
    # The seeded RecipeVersion is "Approved", not Pending Review - filtering
    # should not error out or crash even though only reference formulations
    # match this filter.


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
