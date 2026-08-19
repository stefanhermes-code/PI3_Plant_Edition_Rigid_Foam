"""CR-19 (Correct Recipe Version, Product Grade, and Reference Formulation
Display) regression tests, 2026-08-13.

Covers views/3_Recipe_Version_Record.py's ("Recipes") combined "Recipe
versions" table against Charlie's CR-19 source document:

  - The table now carries separate Type, Product Grade, and Reference
    Formulation columns (previously a single "Product grade" column that
    put the imported reference formulation's own name inside it, prefixed
    "- ... (imported reference)" - a false semantic relationship, since
    that value never came from the Product Grade master).
  - Plant Recipe rows: Type = "Plant Recipe", Product Grade = the row's
    real linked FoamGrade.grade_name (never anything else).
  - Imported Reference rows: Type = "Imported Reference", Product Grade =
    "N/A", Reference Formulation = the reference formulation's own name.
  - A plant Recipe Version's existing, optional
    RecipeVersion.reference_formulation_id link (if set) is preserved and
    surfaces in the Reference Formulation column as supplemental context -
    the Product Grade column still shows the real Product Grade master.
  - Approval Status filtering, row selection/detail rendering, and every
    other pre-existing behavior on this page (Create/Edit/Delete/CSV
    import Recipe, single-active-recipe, Reference Formulation detail/
    provenance/governance) are unchanged - CR-19 is a display/column-
    mapping correction only, no schema change, no change to which records
    exist.

Usage: python -m pytest tests/test_cr19_recipe_product_grade_reference_display.py -v
"""
import inspect
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE3 = os.path.join(APP_DIR, "views", "3_Recipe_Version_Record.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def cr19_fixture():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR19 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR19 Plant {u}")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"CR19 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"CR19 Grade {u}")
    session.add(grade); session.flush()

    # A reference formulation with an existing explicit RecipeVersion.
    # reference_formulation_id link - CR-19 section 3's "supplemental
    # reference context" case.
    rf_linked = db.ReferenceFormulation(
        controlled_id=f"RF-1901-{u}", name=f"CR19 Linked Reference {u}",
        record_status="Locked public parameter summary", approval_status="Approved",
    )
    session.add(rf_linked); session.flush()

    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label=f"v1-{u}", approval_status="Approved",
        is_active=True, created_by="JC", reference_formulation_id=rf_linked.id,
    )
    session.add(recipe); session.flush()

    # A second, unrelated reference formulation - a plain Imported
    # Reference row with no plant recipe pointing at it.
    rf_unlinked = db.ReferenceFormulation(
        controlled_id=f"RF-1902-{u}", name=f"CR19 Unlinked Reference {u}",
        record_status="Locked public parameter summary", approval_status="Pending Review",
    )
    session.add(rf_unlinked); session.flush()
    session.commit()

    ids = {
        "u": u,
        "grade_id": grade.id, "grade_name": grade.grade_name,
        "recipe_id": recipe.id, "recipe_label": recipe.version_label,
        "rf_linked_id": rf_linked.id, "rf_linked_name": rf_linked.name,
        "rf_linked_controlled_id": rf_linked.controlled_id,
        "rf_unlinked_id": rf_unlinked.id, "rf_unlinked_name": rf_unlinked.name,
        "rf_unlinked_controlled_id": rf_unlinked.controlled_id,
    }
    session.close()
    return ids


def _run_recipes_page():
    at = AppTest.from_file(PAGE3, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Recipes page: {at.exception}"
    return at


def _recipe_versions_table(at):
    return next(d for d in at.dataframe if d.key == "recipe_versions_table")


# ---------------------------------------------------------------------------
# Page renders, tabs intact (Create/Edit/Import untouched by this CR)
# ---------------------------------------------------------------------------

def test_recipes_page_renders_all_tabs_without_exception(cr19_fixture):
    at = _run_recipes_page()
    tab_labels = [t.proto.label for t in at.tabs]
    assert any("Create" in lbl for lbl in tab_labels)
    assert any("Edit" in lbl for lbl in tab_labels)
    assert any("import" in lbl.lower() for lbl in tab_labels)


# ---------------------------------------------------------------------------
# Column structure (acceptance criterion 1)
# ---------------------------------------------------------------------------

def test_recipe_versions_table_has_separate_type_product_grade_reference_columns(cr19_fixture):
    at = _run_recipes_page()
    table = _recipe_versions_table(at)
    columns = list(table.value.columns)
    assert "Type" in columns
    assert "Product Grade" in columns
    assert "Reference Formulation" in columns
    # The old conflated column name must be gone entirely.
    assert "Product grade" not in columns


# ---------------------------------------------------------------------------
# Plant Recipe row: Product Grade resolves to the real FoamGrade master
# (acceptance criteria 2, 6, and CR-19 section 8's first bullet: seeded
# Product Grade master + linked plant Recipe Version resolve to the SAME
# master record).
# ---------------------------------------------------------------------------

def test_plant_recipe_row_product_grade_matches_product_grade_master(cr19_fixture):
    ids = cr19_fixture
    at = _run_recipes_page()
    table = _recipe_versions_table(at)
    df = table.value
    plant_row = df[df["Version"] == ids["recipe_label"]].iloc[0]
    assert plant_row["Product Grade"] == ids["grade_name"], (
        "Recipe versions table's Product Grade value for a plant recipe must resolve to the "
        "same Product Grade master name as the grade it's actually linked to."
    )
    # Cross-check directly against the Product Grade master record itself,
    # not just the fixture's own copy of the name.
    session = db.get_session()
    grade_master = session.get(db.FoamGrade, ids["grade_id"])
    assert plant_row["Product Grade"] == grade_master.grade_name
    session.close()


def test_plant_recipe_row_type_is_plant_recipe(cr19_fixture):
    ids = cr19_fixture
    at = _run_recipes_page()
    df = _recipe_versions_table(at).value
    plant_row = df[df["Version"] == ids["recipe_label"]].iloc[0]
    assert plant_row["Type"] == "Plant Recipe"


def test_plant_recipe_row_preserves_existing_reference_formulation_link(cr19_fixture):
    """CR-19 section 3, bullet 3 and section 8's 'preservation' bullet: a
    plant Recipe Version with an existing explicit reference_formulation_id
    relationship still surfaces that linked reference formulation - as
    supplemental context in Reference Formulation - while Product Grade
    stays the actual Product Grade master."""
    ids = cr19_fixture
    at = _run_recipes_page()
    df = _recipe_versions_table(at).value
    plant_row = df[df["Version"] == ids["recipe_label"]].iloc[0]
    assert plant_row["Reference Formulation"] == ids["rf_linked_name"]
    assert plant_row["Product Grade"] == ids["grade_name"]

    # And the underlying FK itself is untouched at the ORM level.
    session = db.get_session()
    recipe = session.get(db.RecipeVersion, ids["recipe_id"])
    assert recipe.reference_formulation_id == ids["rf_linked_id"]
    assert recipe.foam_grade_id == ids["grade_id"]
    session.close()


# ---------------------------------------------------------------------------
# Imported Reference row: "N/A" Product Grade, own name in Reference
# Formulation (acceptance criteria 3, 4, 5).
# ---------------------------------------------------------------------------

def test_imported_reference_row_shows_na_product_grade_and_own_name(cr19_fixture):
    ids = cr19_fixture
    at = _run_recipes_page()
    df = _recipe_versions_table(at).value
    ref_row = df[df["Version"] == ids["rf_unlinked_controlled_id"]].iloc[0]
    assert ref_row["Type"] == "Imported Reference"
    assert ref_row["Product Grade"] == "N/A"
    assert ref_row["Reference Formulation"] == ids["rf_unlinked_name"]


def test_no_imported_reference_row_ever_shows_a_product_grade_master_name(cr19_fixture):
    """Direct assertion that Product Grade resolves exclusively from Product
    Grade master relationships (CR-19 section 8, third bullet): every
    Imported Reference row's Product Grade must be exactly 'N/A', never a
    FoamGrade name, and never the reference formulation's own name either."""
    ids = cr19_fixture
    at = _run_recipes_page()
    df = _recipe_versions_table(at).value
    ref_rows = df[df["Type"] == "Imported Reference"]
    assert len(ref_rows) >= 2  # rf_linked + rf_unlinked, both appear as Imported Reference rows
    assert set(ref_rows["Product Grade"].unique()) == {"N/A"}
    assert ids["grade_name"] not in set(ref_rows["Product Grade"].unique())


# ---------------------------------------------------------------------------
# Product Grade field resolves exclusively from the Product Grade master
# relationship - source-level assertion (CR-19 section 8, third bullet).
# ---------------------------------------------------------------------------

def test_product_grade_column_source_only_reads_foam_grade_relationship():
    source = open(PAGE3, encoding="utf-8").read()
    assert '"Product Grade": (' in source
    assert '(obj.foam_grade.grade_name if obj.foam_grade else "—") if kind == "version" else "N/A"' in source
    # The reference formulation's own name must never feed Product Grade.
    assert 'obj.name if kind == "version" else "N/A"' not in source


# ---------------------------------------------------------------------------
# Approval Status filtering continues to work across both record types
# (acceptance criterion 8).
# ---------------------------------------------------------------------------

def test_approval_status_filter_still_works_across_both_record_types(cr19_fixture):
    ids = cr19_fixture
    at = _run_recipes_page()
    status_sb = next(sb for sb in at.selectbox if sb.key == "recipe_status_filter")
    status_sb.set_value("Pending Review").run()
    assert not at.exception, f"Unhandled exception after filtering to Pending Review: {at.exception}"

    df = _recipe_versions_table(at).value
    # Only rf_unlinked ("Pending Review") should remain; the Approved plant
    # recipe and the Approved rf_linked reference row are filtered out.
    assert ids["rf_unlinked_controlled_id"] in set(df["Version"])
    assert ids["recipe_label"] not in set(df["Version"])
    assert ids["rf_linked_controlled_id"] not in set(df["Version"])

    status_sb.set_value("Approved").run()
    assert not at.exception
    df2 = _recipe_versions_table(at).value
    assert ids["recipe_label"] in set(df2["Version"])
    assert ids["rf_linked_controlled_id"] in set(df2["Version"])
    assert ids["rf_unlinked_controlled_id"] not in set(df2["Version"])


# ---------------------------------------------------------------------------
# Row selection / detail rendering for both record types (acceptance
# criterion 9). AppTest can't drive the dataframe's own on_select click
# (same limitation documented in test_cr03_recipe_consolidation.py and
# test_pm_hierarchy_pages_smoke.py), so selection is driven directly via
# session_state the same way the page's own on_select handler would set it.
# ---------------------------------------------------------------------------

def test_selecting_plant_recipe_row_opens_correct_detail_path(cr19_fixture):
    ids = cr19_fixture
    at = AppTest.from_file(PAGE3, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["rv_selected_kind"] = "version"
    at.session_state["rv_selected_id"] = ids["recipe_id"]
    at.run()
    assert not at.exception, f"Unhandled exception opening plant recipe detail: {at.exception}"

    headings = " ".join(md.value for md in at.markdown)
    assert ids["recipe_label"] in headings
    assert ids["grade_name"] in headings


def test_selecting_imported_reference_row_opens_correct_detail_path(cr19_fixture):
    ids = cr19_fixture
    at = AppTest.from_file(PAGE3, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["rv_selected_kind"] = "reference"
    at.session_state["rv_selected_id"] = ids["rf_unlinked_id"]
    at.run()
    assert not at.exception, f"Unhandled exception opening reference formulation detail: {at.exception}"

    headings = " ".join(md.value for md in at.markdown)
    assert ids["rf_unlinked_controlled_id"] in headings
    assert ids["rf_unlinked_name"] in headings
    warnings = " ".join(w.value for w in at.warning)
    assert "not a plant recipe" in warnings


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
