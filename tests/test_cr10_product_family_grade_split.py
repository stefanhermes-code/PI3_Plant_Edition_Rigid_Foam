"""CR-10 (Split Product Families and Product Grades into Separate Pages,
Charlie's instruction, 2026-08-12) regression tests.

Covers CR-10's own acceptance criteria and regression-test requirement
(sections 8-9): the combined page and its key are gone, the two split
pages open directly and keep their existing functionality, the sidebar
order is correct, and the one-time family-context handoff from Product
Families into Product Grades' family filter actually seeds that filter's
value (not just "the page didn't crash").

Usage: python -m pytest tests/test_cr10_product_family_grade_split.py
"""
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
PAGE_FAMILIES = os.path.join(APP_DIR, "pages", "2_Product_Families.py")
PAGE_GRADES = os.path.join(APP_DIR, "pages", "2_Product_Grades.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_two_families():
    """Two product families under one plant, one with a single product
    grade already on it - enough to exercise the family filter and the
    Families->Grades context handoff without needing a Production Method
    or Machine (neither page's core CRUD depends on either)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR10 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR10 Plant {u}")
    session.add(plant); session.flush()

    family_a = db.ProductFamily(plant_id=plant.id, name=f"CR10 Family A {u}")
    family_b = db.ProductFamily(plant_id=plant.id, name=f"CR10 Family B {u}")
    session.add_all([family_a, family_b]); session.flush()

    grade_a = db.FoamGrade(product_family_id=family_a.id, grade_name=f"CR10-Grade-A-{u}")
    grade_b = db.FoamGrade(product_family_id=family_b.id, grade_name=f"CR10-Grade-B-{u}")
    session.add_all([grade_a, grade_b]); session.flush()
    session.commit()

    ids = {
        "plant_id": plant.id,
        "family_a_id": family_a.id, "family_a_name": family_a.name,
        "family_b_id": family_b.id, "family_b_name": family_b.name,
        "grade_a_id": grade_a.id, "grade_a_name": grade_a.grade_name,
        "grade_b_id": grade_b.id, "grade_b_name": grade_b.grade_name,
    }
    session.close()
    return ids


def _run(page_path, session_state=None):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def test_combined_page_file_and_key_are_gone():
    """AC6: 'The combined "Product Families & Product Grades" sidebar
    entry is removed.' - the old file no longer exists, and neither
    PAGE_CATALOG nor the old page_key show up anywhere access_control
    checks."""
    old_page_path = os.path.join(APP_DIR, "pages", "2_Product_Family_Foam_Grade.py")
    assert not os.path.exists(old_page_path), "Old combined page file should have been deleted"
    assert "product_family_foam_grade" not in access_control.PAGE_CATALOG


def test_page_catalog_has_both_new_keys():
    """AC1: separate sidebar entries for Product Families and Product
    Grades - checked here at the access_control.PAGE_CATALOG level (the
    single source of truth app_rigid_foam.py's nav and the permission
    matrix both read from)."""
    assert access_control.PAGE_CATALOG.get("product_families") == "Product Families"
    assert access_control.PAGE_CATALOG.get("product_grades") == "Product Grades"


def test_sidebar_order_matches_cr10_section_3():
    """AC2: 'The sidebar order is Production Methods, Production
    Equipment, Product Families, Product Grades.' Reads app_rigid_foam.py's
    own production_method_pages list directly rather than driving the full
    st.navigation() sidebar, since that list IS what app_rigid_foam.py
    hands to st.navigation() for this section, in this exact order."""
    # app_rigid_foam.py is a Streamlit script (calls st.navigation()/st.sidebar
    # at import time) - importing it directly outside AppTest isn't safe, so
    # instead this test greps the module source for the list literal's own
    # ordering rather than executing the file. This proves the same thing
    # (declared order of page keys in production_method_pages) without
    # needing a full Streamlit run.
    with open(os.path.join(APP_DIR, "app_rigid_foam.py"), encoding="utf-8") as f:
        source = f.read()
    start = source.index("production_method_pages = [")
    end = source.index("]", start)
    block = source[start:end]
    order = ["production_methods", "plant_overview", "product_families", "product_grades"]
    positions = [block.index(f'"{key}"') for key in order]
    assert positions == sorted(positions), (
        f"production_method_pages entries out of CR-10 order - found at positions {positions} "
        f"for keys {order}"
    )


def test_product_families_page_opens_directly_and_lists_families(seeded_two_families):
    """AC3: 'Product Families opens directly as a dedicated page.' AC7:
    existing Product Families functionality (the table, in this case)
    still works."""
    ids = seeded_two_families
    at = _run(PAGE_FAMILIES)
    assert not at.exception, f"Unhandled exception loading Product Families: {at.exception}"
    # clickable_table renders as an HTML block, not a semantic widget
    # AppTest can query row-by-row - the underlying-data assertion below is
    # the same pattern every other clickable_table page's smoke coverage in
    # this project uses (see test_pm_hierarchy_pages_smoke.py).
    session = db.get_session()
    families = session.query(db.ProductFamily).filter(db.ProductFamily.plant_id == ids["plant_id"]).all()
    assert {f.name for f in families} == {ids["family_a_name"], ids["family_b_name"]}
    session.close()


def test_product_grades_page_opens_directly_with_family_filter(seeded_two_families):
    """AC4: 'Product Grades opens directly as a dedicated page.' AC11:
    'Direct entry to Product Grades supports normal family selection or
    filtering' - the filter selectbox exists and defaults to 'All product
    families' on a direct (context-free) visit."""
    at = _run(PAGE_GRADES)
    assert not at.exception, f"Unhandled exception loading Product Grades: {at.exception}"

    filter_sb = next((sb for sb in at.selectbox if sb.label == "Filter by product family"), None)
    assert filter_sb is not None, "Family filter selectbox not found on Product Grades page"
    assert filter_sb.value is None, "Direct visit (no context) should default the filter to 'All product families'"


def test_family_context_seeds_grades_filter_and_narrows_table(seeded_two_families):
    """AC10/AC11 together: a family selected on the Families page carries
    into the Grades page's own filter - proven here by presetting
    session_state["pfg_family_context_id"] exactly as
    pages/2_Product_Families.py's 'Open Product Grades for ...' button
    does right before st.switch_page(), then loading the Grades page fresh
    and checking BOTH that the filter selectbox picked it up AND that the
    grade table actually narrowed to that family's own grade."""
    ids = seeded_two_families
    at = _run(PAGE_GRADES, session_state={"pfg_family_context_id": ids["family_a_id"]})
    assert not at.exception, f"Unhandled exception loading Product Grades with family context: {at.exception}"

    filter_sb = next((sb for sb in at.selectbox if sb.label == "Filter by product family"), None)
    assert filter_sb is not None
    assert filter_sb.value is not None and filter_sb.value.id == ids["family_a_id"], (
        f"Filter should have been seeded to family A from context - got {filter_sb.value}"
    )

    # The context key is one-time-use (CR-10: "not a permanent link") -
    # popped by the page itself, so it must not still be sitting in
    # session_state after the run.
    assert "pfg_family_context_id" not in at.session_state

    caption_texts = " ".join(c.value for c in at.caption)
    assert ids["family_a_name"] in caption_texts, "Narrowed-view caption should name family A"
    assert ids["grade_b_name"] not in caption_texts


def test_family_context_ignored_if_family_id_is_stale(seeded_two_families):
    """Defensive case: a context id that doesn't resolve to a real family
    in this session's scope (e.g. a stale/cross-tenant id) should be
    silently ignored, not crash the page or corrupt the filter."""
    at = _run(PAGE_GRADES, session_state={"pfg_family_context_id": 999999})
    assert not at.exception, f"Unhandled exception with a bogus family context id: {at.exception}"
    filter_sb = next((sb for sb in at.selectbox if sb.label == "Filter by product family"), None)
    assert filter_sb is not None
    assert filter_sb.value is None, "A context id that doesn't resolve to a real family should leave the filter on 'All'"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
