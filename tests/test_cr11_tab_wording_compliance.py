"""CR-11 (Standardize Record Create, Edit/Delete and CSV/Excel Import
Functions, 2026-08-12) - regression coverage for the mandated tab wording
and order itself.

Every customer-facing record-creation page must expose exactly three
functions, in this order, with this exact wording: "Create <record>",
"Edit/Delete <record>", "CSV/Excel import <records>" - see helpers.
cr11_function_tab_labels()'s own docstring for the canonical spec. This
file does not re-test each page's CRUD/import behavior (already covered by
that page's own test file, e.g. test_cr11_forced_password_reset.py for
User Accounts) - it only confirms the wording/order contract itself holds,
for every one of the 15 views/tab-groups identified by CR-11's inventory
(task #813) that call cr11_function_tab_labels().

Uses the AUTH_DISABLED dev bypass (see auth.py's require_login docstring)
to reach every page without a real login flow - this file is not
exercising the forced-password-reset gate, so (unlike test_cr11_forced_
password_reset.py) AUTH_DISABLED is the right tool here.

AppTest flattening gotcha (discovered while building this file): at.tabs
returns every Tab element in the whole page in a single flattened,
depth-first list - a nested st.tabs() call (e.g. pages 11/12's "Manage
samples" Sample sub-tabs, defined inside the outer "Create Trial" tab's own
body) is interleaved into that list at the point its parent tab appears,
NOT appended after the parent's own sibling group finishes. Confirmed by
direct probing (see this file's own history) that pages 11/12 render as
[Create Trial, Create Sample, Edit/Delete Sample, CSV/Excel import Samples,
Edit/Delete Trial, CSV/Excel import Trials, Sample Report] - the outer
Trial trio is NOT contiguous in that raw list because the nested Sample
trio sits inside "Create Trial"'s own body. _assert_triplet_adjacent()'s
ignore_labels parameter filters those known nested labels out before
checking the outer group's own adjacency, which is the actual CR-11
requirement (three functions, in order) - the nested trio is then checked
separately, unfiltered, against the raw list (nested trios were confirmed
by the same probing to always remain contiguous among themselves, since
they're created by one shared st.tabs() call with nothing else able to
interleave inside their own immediate span).

Page 4 (Production Run Trial Record) has five independent top-level record
groups (Production Run, Setup Data, Stream Reading, Production Event,
Runtime Data) from five separate st.tabs(cr11_function_tab_labels(...))
call sites - probing confirmed each group's own trio renders contiguously
(no cross-group interleaving), so all five are checked with the same plain
adjacency helper, no ignore_labels needed.
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
import tenant_scope
from helpers import cr11_function_tab_labels

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_DIR = os.path.join(APP_DIR, "views")


def _page(name):
    return os.path.join(PAGES_DIR, name)


def _clear_relevant_caches():
    """CR-11 correction (2026-08-12): added when the new
    tests/test_cr11_functional_evidence_group_*.py files (which run
    alphabetically BEFORE this file) exposed the same cross-test/cross-file
    @st.cache_data id-collision hazard first documented in CR-12 and
    defended against in test_cr10_product_family_grade_split.py -
    full_chain below is module-scoped and resets the schema (autoincrement
    ids restart at 1), but without this clear, tenant_scope's id-scoping
    helpers can still serve another module's stale cached scope for the
    same small-int company_id/plant_ids, which starves this file's own
    seeded chain of visibility and makes a target page hit its own
    'nothing to show yet' st.stop() guard instead of rendering tabs."""
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    _clear_relevant_caches()


@pytest.fixture(scope="module")
def full_chain():
    """One company/plant/product-family/foam-grade/active-recipe/production-
    run(with a Finalized phase)/customer-trial/optimization-trial chain -
    enough for every one of this file's 15 target views/groups to clear
    its own st.stop() guard and render its CR-11 tabs (see each page's own
    'Add a plant/product grade/production run first' guard, inventoried
    while building this file). Session-scoped (not per-test) since this
    file only ever reads this data via AppTest, never mutates it - matches
    the module-scoped seeding pattern used elsewhere in this suite (e.g.
    test_wp4_recipe_optimization_page_smoke.py's _reset_schema note about
    the shared in-memory StaticPool connection)."""
    db.init_db()
    _reset_schema()
    session = db.get_session()
    u = uuid.uuid4().hex[:8]

    company = db.Company(name=f"CR11 Tabs Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11 Tabs Plant {u}")
    session.add(plant); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"CR11 Tabs Machine {u}")
    session.add(machine); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"CR11 Tabs Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"CR11 Tabs Grade {u}")
    session.add(grade); session.flush()
    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True,
    )
    session.add(recipe); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference=f"CR11-B1-{u}",
    )
    session.add(run); session.flush()
    phase = db.ProductionPhase(production_run_id=run.id, phase_name="Finalized")
    session.add(phase); session.flush()
    session.add(db.CustomerTrial(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        customer_name=f"CR11 Tabs Customer {u}",
    ))
    session.add(db.OptimizationTrial(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        improvement_initiative_reference=f"CR11-INIT-{u}",
    ))
    session.commit()
    session.close()
    return {"company_id": company.id, "plant_id": plant.id, "grade_id": grade.id}


def _tab_labels(page_filename, extra_secrets=None):
    at = AppTest.from_file(_page(page_filename), default_timeout=60)
    at.secrets["AUTH_DISABLED"] = True
    for k, v in (extra_secrets or {}).items():
        at.secrets[k] = v
    at.run()
    assert not at.exception, f"{page_filename} raised: {at.exception}"
    return [t.label for t in at.tabs]


def _assert_triplet_adjacent(labels, record_singular, record_plural=None, ignore_labels=()):
    """The CR-11 contract itself: these three exact labels, in this exact
    order, immediately adjacent to each other. ignore_labels strips out a
    known nested sub-group's own labels first (see module docstring) so a
    nested group interleaved between the second and third tab of an OUTER
    group doesn't produce a false failure - the outer group's three tabs
    are still genuinely adjacent to a real user looking at that tab bar;
    the nested group renders as a second, separate tab bar one level down."""
    expected = list(cr11_function_tab_labels(record_singular, record_plural))
    filtered = [l for l in labels if l not in ignore_labels]
    positions = []
    for label in expected:
        assert label in filtered, f"Missing tab {label!r} - got {filtered}"
        positions.append(filtered.index(label))
    assert positions[1] == positions[0] + 1, (
        f"{expected[1]!r} is not immediately after {expected[0]!r} in {filtered}"
    )
    assert positions[2] == positions[1] + 1, (
        f"{expected[2]!r} is not immediately after {expected[1]!r} in {filtered}"
    )


# ---------------------------------------------------------------------------
# Single/near-single-group pages: strict CR-11 triplet, no nested groups.
# ---------------------------------------------------------------------------

def test_plant_installation_overview_tabs(full_chain):
    labels = _tab_labels("1_Plant_Installation_Overview.py")
    _assert_triplet_adjacent(labels, "Plant")


def test_product_families_tabs(full_chain):
    labels = _tab_labels("2_Product_Families.py")
    _assert_triplet_adjacent(labels, "Product Family", "Product Families")


def test_product_grades_tabs(full_chain):
    labels = _tab_labels("2_Product_Grades.py")
    _assert_triplet_adjacent(labels, "Product Grade", "Product Grades")


def test_recipes_tabs(full_chain):
    labels = _tab_labels("3_Recipe_Version_Record.py")
    _assert_triplet_adjacent(labels, "Recipe", "Recipes")


def test_quality_test_result_tabs(full_chain):
    labels = _tab_labels("5_Physical_Property_Result.py")
    _assert_triplet_adjacent(labels, "Quality Test Result", "Quality Test Results")


def test_quality_issue_tabs(full_chain):
    labels = _tab_labels("6_Quality_Observation.py")
    _assert_triplet_adjacent(labels, "Quality Issue", "Quality Issues")


def test_samples_conditioning_tabs(full_chain):
    labels = _tab_labels("9_Samples_Conditioning.py")
    _assert_triplet_adjacent(labels, "Sample")
    # Page-specific 4th tab explicitly allowed to remain alongside the
    # standard 3 (see CR-11 inventory, task #813).
    assert "Sample Report" in labels


def test_expert_notes_tabs(full_chain):
    labels = _tab_labels("20_Expert_Notes.py")
    _assert_triplet_adjacent(labels, "Expert Note")
    assert "Expert Notes Report" in labels


def test_user_roles_tabs(full_chain):
    labels = _tab_labels("24_User_Roles.py")
    _assert_triplet_adjacent(labels, "Role")


def test_user_accounts_tabs(full_chain):
    labels = _tab_labels("25_User_Accounts.py")
    _assert_triplet_adjacent(labels, "User")


def test_production_equipment_tabs(full_chain):
    labels = _tab_labels("31_Production_Equipment.py")
    _assert_triplet_adjacent(labels, "Production Unit / Cell", "Production Units / Cells")


# ---------------------------------------------------------------------------
# Nested-subtab pages: outer group's triplet checked with the nested
# group's own labels filtered out first (see module docstring); nested
# group's own triplet checked unfiltered against the raw list.
# ---------------------------------------------------------------------------

def test_customer_trials_tabs(full_chain):
    labels = _tab_labels("11_Customer_Trials.py")
    sample_labels = set(cr11_function_tab_labels("Sample"))
    _assert_triplet_adjacent(labels, "Trial", ignore_labels=sample_labels)
    _assert_triplet_adjacent(labels, "Sample")
    assert "Sample Report" in labels


def test_optimization_trials_tabs(full_chain):
    labels = _tab_labels("12_Optimization_Trials.py")
    sample_labels = set(cr11_function_tab_labels("Sample"))
    _assert_triplet_adjacent(labels, "Trial", ignore_labels=sample_labels)
    _assert_triplet_adjacent(labels, "Sample")
    assert "Sample Report" in labels


def test_raw_materials_tabs(full_chain):
    """CR-13 (Split Suppliers into a Standalone Page), implemented
    2026-08-12: views/14_Raw_Materials.py no longer has a nested "Suppliers"
    tab or Supplier sub-triplet - Supplier management moved to its own page
    (see test_raw_materials_no_suppliers_tab below and
    tests/test_cr13_suppliers_standalone_page.py for the moved page's own
    wording/order test). Only the Raw Material triplet plus the page-
    specific "Add from TDS" tab (task #813's explicitly allowed extra)
    remain here."""
    labels = _tab_labels("14_Raw_Materials.py")
    _assert_triplet_adjacent(labels, "Raw Material")
    assert "Add from TDS" in labels


def test_raw_materials_no_suppliers_tab(full_chain):
    """CR-13 acceptance criteria 2 and 10: the Raw Materials page must no
    longer contain a Suppliers tab, nested Supplier management controls, or
    any customer-facing presentation of Suppliers as a Raw Materials
    sub-tab."""
    labels = _tab_labels("14_Raw_Materials.py")
    supplier_labels = set(cr11_function_tab_labels("Supplier"))
    assert "Suppliers" not in labels, "Raw Materials must no longer expose a 'Suppliers' tab after the CR-13 split"
    assert not (supplier_labels & set(labels)), (
        "Raw Materials must no longer expose the Supplier Create/Edit-Delete/Import triplet after the CR-13 split"
    )


# ---------------------------------------------------------------------------
# Page 4: five independent top-level record groups in one page. Probing
# (see module docstring) confirmed each group's own triplet renders
# contiguously with no cross-group interleaving, so the same plain
# adjacency helper applies to all five, no ignore_labels needed.
# ---------------------------------------------------------------------------

def test_production_run_trial_record_all_five_groups(full_chain):
    labels = _tab_labels("4_Production_Run_Trial_Record.py")
    _assert_triplet_adjacent(labels, "Production Run")
    _assert_triplet_adjacent(labels, "Setup Data", "Setup Data")
    _assert_triplet_adjacent(labels, "Stream Reading")
    _assert_triplet_adjacent(labels, "Production Event")
    _assert_triplet_adjacent(labels, "Runtime Data", "Runtime Data")
