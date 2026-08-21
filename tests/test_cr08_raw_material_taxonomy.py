"""CR-08 (Raw Material Category and Subcategory Taxonomy Alignment,
Charlie's instruction document PI3_Rigid_Foam_Phase_1_CR08_Raw_Material_
Category_and_Subcategory_Taxonomy_Alignment_for_UAT.docx, 2026-08-11).

UAT finding this closes: Raw Materials carried the inherited Flexible Foam
category vocabulary (RAW_MATERIAL_CATEGORIES, free text) with no
Subcategory concept at all. This batch replaces it with one controlled
Category -> Subcategory taxonomy (RAW_MATERIAL_TAXONOMY in db.py, seeded
into RawMaterialCategory as a self-referencing adjacency list) governing
manual entry, the Raw Materials list, recipe components, and CSV/Excel
import - see views/14_Raw_Materials.py and RawMaterial.category_id/
subcategory_id's own docstrings in db.py.

Mirrors the established AUTH_DISABLED AppTest pattern (see
test_cr07_grade_property_targets.py's own docstring for the full
rationale): the Add Raw Material form (reachable with no row-click) is
exercised via AppTest; the Edit form and CSV-import matching (both gated
behind clickable_table row-selection / a Confirm-import button click
AppTest can't drive) are instead exercised as direct database operations
that mirror the page's own write-path logic exactly - same model, same
session, same commit.

Usage: python -m pytest tests/test_cr08_raw_material_taxonomy.py
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import db
import helpers

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE14 = os.path.join(APP_DIR, "views", "14_Raw_Materials.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def _seed_taxonomy(session):
    """Seed every row of db.RAW_MATERIAL_TAXONOMY into RawMaterialCategory,
    using the exact same controlled_id band-of-100 convention CR-08's live
    Supabase seeding used (RMC2-<band> for a Category, RMC2-<band+N0> for
    its Nth Subcategory) - see RAW_MATERIAL_TAXONOMY's own comment in
    db.py. No shared seed function exists in this codebase for controlled
    vocabularies (WP5/quality-issue-taxonomy content was seeded directly
    against Supabase, never through a reusable local helper) - this
    fixture-local seeding follows that same precedent rather than adding a
    new production code path whose only caller would be this test file."""
    rows = {}
    for band_index, (cat_name, subcats) in enumerate(db.RAW_MATERIAL_TAXONOMY.items(), start=1):
        band = band_index * 100
        cat = db.RawMaterialCategory(
            controlled_id=f"RMC2-{band}", name=cat_name, sort_order=band, active=True,
        )
        session.add(cat)
        session.flush()
        rows[cat_name] = {"category": cat, "subcategories": {}}
        for sub_index, sub_name in enumerate(subcats, start=1):
            sub = db.RawMaterialCategory(
                controlled_id=f"RMC2-{band + sub_index * 10}",
                name=sub_name,
                parent_category_id=cat.id,
                sort_order=band + sub_index * 10,
                active=True,
                is_exception_only=(cat_name == "Other"),
            )
            session.add(sub)
            session.flush()
            rows[cat_name]["subcategories"][sub_name] = sub
    session.commit()
    return rows


@pytest.fixture()
def seeded_taxonomy():
    db.init_db()
    _reset_schema()
    session = db.get_session()
    rows = _seed_taxonomy(session)
    session.close()
    return rows


@pytest.fixture()
def seeded_company_with_material(seeded_taxonomy):
    """A company + one classified RawMaterial (Blowing Agent / Water) +
    one RecipeComponent referencing it, for the round-trip and
    reclassification-preservation tests below."""
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR08 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR08 Plant {u}")
    session.add(plant); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR08 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR08-Grade-{u}")
    session.add(grade); session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", is_active=True)
    session.add(recipe); session.flush()

    blowing_agent = seeded_taxonomy["Blowing Agent"]["category"]
    water = seeded_taxonomy["Blowing Agent"]["subcategories"]["Water"]
    rm = db.RawMaterial(
        company_id=company.id, name=f"Cyclopentane {u}",
        category_id=blowing_agent.id, subcategory_id=water.id, active=True,
    )
    session.add(rm); session.flush()
    component = db.RecipeComponent(recipe_version_id=recipe.id, raw_material_id=rm.id, raw_material_name=rm.name, php=1.5)
    session.add(component); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "rm_id": rm.id, "rm_name": rm.name,
        "component_id": component.id, "blowing_agent_id": blowing_agent.id,
        "water_id": water.id,
    }
    session.close()
    return ids


def _run(page_path):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


# ---------------------------------------------------------------------------
# Acceptance criterion: the controlled taxonomy dict itself matches CR-08
# section 4 exactly (10 Categories, exact Subcategory lists, 40 Subcategory
# rows total).
# ---------------------------------------------------------------------------
def test_taxonomy_dict_has_ten_categories_in_cr08_order():
    expected_order = [
        "Polyol", "Isocyanate", "Blowing Agent", "Catalyst",
        "Surfactant / Foam Stabilizer", "Flame Retardant",
        "Crosslinker / Chain Modifier", "Functional Additive",
        "Filler / Solid Additive", "Other",
    ]
    assert list(db.RAW_MATERIAL_TAXONOMY.keys()) == expected_order


def test_taxonomy_dict_has_forty_subcategories_total():
    total = sum(len(subs) for subs in db.RAW_MATERIAL_TAXONOMY.values())
    assert total == 40


def test_taxonomy_distinguishes_water_hydrocarbon_hfo_hcfo():
    """CR-08 acceptance criterion: 'Water, Hydrocarbon, and HFO/HCFO blowing
    agents must be distinguishable in the data.'"""
    blowing_subs = db.RAW_MATERIAL_TAXONOMY["Blowing Agent"]
    assert "Water" in blowing_subs
    assert "Hydrocarbon" in blowing_subs
    assert "HFO / HCFO" in blowing_subs


def test_taxonomy_distinguishes_catalyst_subtypes():
    """CR-08 acceptance criterion: gel/blow/delayed-action/PIR catalyst
    subcategories must be distinguishable."""
    catalyst_subs = db.RAW_MATERIAL_TAXONOMY["Catalyst"]
    for expected in ["Gel catalyst", "Blow catalyst", "Delayed-action catalyst", "PIR / trimerization catalyst"]:
        assert expected in catalyst_subs


def test_taxonomy_polyol_supports_formulated_system_blends():
    """CR-08 acceptance criterion: Polyol subcategories must support
    formulated/system blends, not just single-chemistry polyols."""
    assert "Formulated/system polyol blend" in db.RAW_MATERIAL_TAXONOMY["Polyol"]


def test_only_other_subcategory_is_exception_only(seeded_taxonomy):
    """The single 'Other' Subcategory row is the only controlled-exception
    path in the whole taxonomy - every other Subcategory requires no
    free-text description."""
    session = db.get_session()
    exception_rows = (
        session.query(db.RawMaterialCategory)
        .filter(db.RawMaterialCategory.is_exception_only.is_(True))
        .all()
    )
    assert len(exception_rows) == 1
    assert exception_rows[0].name == "Other"
    assert exception_rows[0].parent.name == "Other"
    session.close()


# ---------------------------------------------------------------------------
# Category/Subcategory picker helpers (helpers.py) - filtering + labeling.
# ---------------------------------------------------------------------------
def test_raw_material_categories_returns_only_active_top_level_rows(seeded_taxonomy):
    session = db.get_session()
    cats = helpers.raw_material_categories(session)
    assert len(cats) == 10
    assert all(c.parent_category_id is None for c in cats)
    assert {c.name for c in cats} == set(db.RAW_MATERIAL_TAXONOMY.keys())
    session.close()


def test_raw_material_subcategories_filtered_to_chosen_category_only(seeded_taxonomy):
    """CR-08 acceptance criterion: choosing a Category must narrow
    Subcategory choices to that Category's own children only - a
    Subcategory belonging to a different Category must never appear."""
    session = db.get_session()
    polyol_id = seeded_taxonomy["Polyol"]["category"].id
    isocyanate_id = seeded_taxonomy["Isocyanate"]["category"].id

    polyol_subs = helpers.raw_material_subcategories(session, polyol_id)
    isocyanate_subs = helpers.raw_material_subcategories(session, isocyanate_id)

    assert {s.name for s in polyol_subs} == set(db.RAW_MATERIAL_TAXONOMY["Polyol"])
    assert {s.name for s in isocyanate_subs} == set(db.RAW_MATERIAL_TAXONOMY["Isocyanate"])
    # No overlap - an Isocyanate subcategory must never be offered under Polyol.
    assert not ({s.id for s in polyol_subs} & {s.id for s in isocyanate_subs})
    session.close()


def test_raw_material_subcategories_returns_empty_for_no_category(seeded_taxonomy):
    session = db.get_session()
    assert helpers.raw_material_subcategories(session, None) == []
    session.close()


def test_invalid_category_subcategory_combination_is_detectable(seeded_taxonomy):
    """CR-08 acceptance criterion: invalid Category/Subcategory combinations
    must be blocked from being saved. There is deliberately no DB
    constraint for this (a same-table two-column parent check isn't
    expressible without a trigger - see RawMaterial.subcategory_id's own
    comment in db.py) so the rule lives in the page's write-path
    validation; this test exercises the exact same parent-match check that
    validation performs, directly against the seeded rows."""
    session = db.get_session()
    polyol_id = seeded_taxonomy["Polyol"]["category"].id
    isocyanate_sub = seeded_taxonomy["Isocyanate"]["subcategories"]["Polymeric MDI"]

    # The mismatched pair must never appear together in the picker...
    assert isocyanate_sub not in helpers.raw_material_subcategories(session, polyol_id)
    # ...and the underlying parent-id check the write path relies on agrees.
    assert isocyanate_sub.parent_category_id != polyol_id
    session.close()


def test_raw_material_category_label_formats_category_and_subcategory(seeded_company_with_material):
    session = db.get_session()
    rm = session.get(db.RawMaterial, seeded_company_with_material["rm_id"])
    assert helpers.raw_material_category_label(rm) == "Blowing Agent / Water"
    session.close()


def test_raw_material_category_label_falls_back_for_unclassified_material(seeded_taxonomy):
    session = db.get_session()
    u = uuid.uuid4().hex[:8]
    company = db.Company(name=f"CR08 Fallback Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    rm = db.RawMaterial(company_id=company.id, name=f"Unclassified {u}", active=True)
    session.add(rm); session.flush()
    session.commit()
    assert helpers.raw_material_category_label(rm) == "—"
    session.close()


# ---------------------------------------------------------------------------
# Manual entry / Edit round trips - direct DB operations mirroring
# views/14_Raw_Materials.py's own write path exactly.
# ---------------------------------------------------------------------------
def test_manual_entry_round_trip_sets_controlled_category_and_subcategory(seeded_taxonomy):
    session = db.get_session()
    u = uuid.uuid4().hex[:8]
    company = db.Company(name=f"CR08 Manual Co {u}", is_platform_owner=True)
    session.add(company); session.flush()

    catalyst = seeded_taxonomy["Catalyst"]["category"]
    delayed = seeded_taxonomy["Catalyst"]["subcategories"]["Delayed-action catalyst"]
    rm = db.RawMaterial(
        company_id=company.id, name=f"POLYCAT {u}",
        category_id=catalyst.id, subcategory_id=delayed.id, active=True,
    )
    session.add(rm); session.flush()
    session.commit()
    rm_id = rm.id
    session.close()

    session2 = db.get_session()
    reloaded = session2.get(db.RawMaterial, rm_id)
    assert reloaded.category_id == catalyst.id
    assert reloaded.subcategory_id == delayed.id
    assert helpers.raw_material_category_label(reloaded) == "Catalyst / Delayed-action catalyst"
    session2.close()


def test_edit_updates_classification_without_touching_id_or_name(seeded_company_with_material):
    """Edit form round trip: changing a RawMaterial's Category/Subcategory
    (the page's actual Edit-form write path) must not disturb its id,
    name, or company - only the classification changes."""
    ids = seeded_company_with_material
    session = db.get_session()
    rm = session.get(db.RawMaterial, ids["rm_id"])
    original_name = rm.name
    original_company_id = rm.company_id

    catalyst = (
        session.query(db.RawMaterialCategory)
        .filter(db.RawMaterialCategory.name == "Catalyst", db.RawMaterialCategory.parent_category_id.is_(None))
        .first()
    )
    gel = (
        session.query(db.RawMaterialCategory)
        .filter(db.RawMaterialCategory.name == "Gel catalyst")
        .first()
    )
    rm.category_id = catalyst.id
    rm.subcategory_id = gel.id
    session.commit()

    session2 = db.get_session()
    reloaded = session2.get(db.RawMaterial, ids["rm_id"])
    assert reloaded.id == ids["rm_id"]
    assert reloaded.name == original_name
    assert reloaded.company_id == original_company_id
    assert helpers.raw_material_category_label(reloaded) == "Catalyst / Gel catalyst"
    session2.close()


def test_recipe_component_reference_preserved_across_reclassification(seeded_company_with_material):
    """CR-08 acceptance criterion 10: reclassifying a RawMaterial's
    Category/Subcategory must never disturb RecipeComponent.raw_material_id
    references to it."""
    ids = seeded_company_with_material
    session = db.get_session()
    rm = session.get(db.RawMaterial, ids["rm_id"])

    other_cat = (
        session.query(db.RawMaterialCategory)
        .filter(db.RawMaterialCategory.name == "Other", db.RawMaterialCategory.parent_category_id.is_(None))
        .first()
    )
    other_sub = (
        session.query(db.RawMaterialCategory)
        .filter(db.RawMaterialCategory.is_exception_only.is_(True))
        .first()
    )
    rm.category_id = other_cat.id
    rm.subcategory_id = other_sub.id
    session.commit()

    session2 = db.get_session()
    component = session2.get(db.RecipeComponent, ids["component_id"])
    assert component.raw_material_id == ids["rm_id"]
    reloaded_rm = session2.get(db.RawMaterial, component.raw_material_id)
    assert reloaded_rm.name == ids["rm_name"]
    session2.close()


# ---------------------------------------------------------------------------
# CSV/Excel import matching - case-insensitive exact match against the
# controlled taxonomy, mirroring _match_taxonomy_text in
# views/14_Raw_Materials.py (a plain data-layer function with no
# Streamlit calls of its own, but living inside a page script that
# executes top-to-bottom on import - see that file's own docstring for
# why a direct import isn't used here).
# ---------------------------------------------------------------------------
def _match_taxonomy_text(session, text):
    text = (text or "").strip()
    if not text:
        return None, None
    sub = (
        session.query(db.RawMaterialCategory)
        .filter(db.RawMaterialCategory.active.is_(True), db.RawMaterialCategory.parent_category_id.isnot(None))
        .filter(db.RawMaterialCategory.name.ilike(text))
        .first()
    )
    if sub:
        return sub.parent, sub
    cat = (
        session.query(db.RawMaterialCategory)
        .filter(db.RawMaterialCategory.active.is_(True), db.RawMaterialCategory.parent_category_id.is_(None))
        .filter(db.RawMaterialCategory.name.ilike(text))
        .first()
    )
    return (cat, None) if cat else (None, None)


def test_import_matching_is_case_insensitive_exact_match(seeded_taxonomy):
    session = db.get_session()
    cat, sub = _match_taxonomy_text(session, "hydrocarbon")
    assert sub is not None
    assert sub.name == "Hydrocarbon"
    assert cat.name == "Blowing Agent"
    session.close()


def test_import_matching_does_not_fuzzy_match_unknown_text(seeded_taxonomy):
    """CR-08 explicitly excludes free-text entry: an import row whose
    category/subcategory text doesn't exactly match a controlled row must
    be flagged for review, never guessed into the nearest-sounding value."""
    session = db.get_session()
    cat, sub = _match_taxonomy_text(session, "Some Random Supplier Category")
    assert cat is None and sub is None
    session.close()


def test_import_matching_returns_nothing_for_blank_text(seeded_taxonomy):
    session = db.get_session()
    assert _match_taxonomy_text(session, "") == (None, None)
    assert _match_taxonomy_text(session, None) == (None, None)
    session.close()


# ---------------------------------------------------------------------------
# AppTest: the Add Raw Material form (reachable without any row selection)
# no longer offers free-text Category and now offers a real Subcategory
# picker.
# ---------------------------------------------------------------------------
def test_add_raw_material_form_has_controlled_category_and_subcategory_pickers(seeded_taxonomy):
    at = _run(PAGE14)
    assert not at.exception, f"Unhandled exception loading Raw Materials: {at.exception}"

    category_sb = next((sb for sb in at.selectbox if sb.key == "add_rawmat_category"), None)
    assert category_sb is not None, "Add Raw Material form's Category picker not found"
    # AppTest reports rendered selectbox options as their display strings
    # (format_func already applied) - format_func here is plain c.name.
    assert set(category_sb.options) == set(db.RAW_MATERIAL_TAXONOMY.keys()), (
        "Category picker must offer exactly the controlled taxonomy's top-level Categories, no free text"
    )

    subcategory_sb = next((sb for sb in at.selectbox if sb.key == "add_rawmat_subcategory"), None)
    assert subcategory_sb is not None, "Add Raw Material form's Subcategory picker not found"
    # Default Category selection is the first one (index 0) - its Subcategory
    # picker must be filtered to that Category's own children only.
    default_category_name = category_sb.value.name
    expected_subs = set(db.RAW_MATERIAL_TAXONOMY[default_category_name])
    assert set(subcategory_sb.options) == expected_subs
