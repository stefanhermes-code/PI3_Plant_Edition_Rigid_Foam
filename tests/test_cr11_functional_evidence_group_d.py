"""CR-11 (Standardize Record Create, Edit/Delete and CSV/Excel Import
Functions, 2026-08-12) closeout correction, Group D.

Charlie's return of the first CR-11 closeout package: the package only had
wording/order tests (that the tab labels/order match
helpers.cr11_function_tab_labels()) - no DIRECT, EXECUTED evidence that
Create / Edit / Delete / CSV-Excel-import actually work through the real UI
for each standardized record group. Charlie's return explicitly named "the
five Production Run record groups" as the ones this evidence must cover, by
name. Those five groups all live on ONE page, pages/4_Production_Run_Trial_
Record.py, each behind its own independent st.tabs(cr11_function_tab_labels(
...)) call site:

  1. Production Run     (tab_runs)
  2. Setup Data         (tab_setup)
  3. Stream Reading     (tab_streams)
  4. Production Event   (tab_events)
  5. Runtime Data       (tab_runtime)

This file adds that missing direct evidence, at least one
create/edit-delete/import test per group (15 tests minimum).

PAGE STRUCTURE (read directly from pages/4_Production_Run_Trial_Record.py
before writing anything here, per instruction):

- All 5 top-level tabs are rendered on every single script run - Streamlit's
  st.tabs() unpacks into 5 containers and the code inside every `with tab:`
  block executes unconditionally on each rerun (which tab is visually
  "active" is a front-end-only concept; AppTest, like Streamlit itself, runs
  every tab's code every time). So a user is never "gated" into one group at
  a time by page navigation - all 5 are reachable without leaving the page.
  What each of the 4 non-Production-Run groups DOES gate on is data:
  Setup/Stream/Event/Runtime all render "Create a production run first" (an
  st.info(), no widgets) until at least one ProductionRun exists, and Stream
  Reading additionally gates on a Runtime Data (Finalized-phase) row already
  existing for the selected run (see FK chain below) - it shows "Add Runtime
  Data for <run> first" until then, with no Create/Edit/Import widgets.
- Every one of the 4 non-Production-Run tabs opens with the SAME kind of
  run-picker widget (helpers._run_selector(), a plain st.selectbox keyed
  "setup_tab_run_select" / "stream_tab_run_select" / "event_tab_run_select" /
  "runtime_tab_run_select") that defaults to st.session_state
  ["pr_selected_run_id"] (or index 0) - with exactly one seeded
  ProductionRun in every fixture below, that selectbox always resolves to
  it with no extra widget interaction needed.
- FK / dependency chain (from db.py, ground truth over the prompt's guess):
      ProductionRun
        |-- ProductionPhase (production_run_id, phase_name "Setup" or
        |     "Finalized" - Setup Data and Runtime Data are BOTH just this
        |     one table, filtered to one hardcoded phase_name each; there is
        |     no separate RuntimeDataRecord table involved - that table is
        |     retired, see db.py's own docstring on it)
        |     |-- ComponentStreamReading (production_phase_id) - Stream
        |     |     Reading rows only ever attach to the "Finalized" phase
        |     |     (never "Setup" - enforced by the page itself, not just
        |     |     documented: tab_streams looks up finalized_phase and
        |     |     shows nothing but an info box if it's None). This is
        |     |     THE extra FK hop beyond "just needs a ProductionRun":
        |     |     Stream Reading depends on Runtime Data, not on
        |     |     ProductionRun directly.
        |     `-- FallplateSectionPosition (production_phase_id) - the
        |           page-specific "Tool Geometry and Fill Configuration" 4th
        |           tab on both Setup Data and Runtime Data. Left alone per
        |           instruction, not tested here.
        `-- ProductionEvent (production_run_id, with an OPTIONAL
              production_phase_id FK) - Production Event attaches directly
              to the run, not via a phase, and never depends on Setup Data
              or Runtime Data existing first.
  ProductionRun itself depends on Plant -> ProductFamily -> FoamGrade
  (+ an assigned Machine, +an active RecipeVersion for that grade) - the
  same chain test_pm_hierarchy_pages_smoke.py's seeded_pm_hierarchy fixture
  builds for this same page, reused below as seeded_grade_chain().
- Delete behavior actually found in the code (not assumed): cascades.py's
  delete_production_run_cascade() has no blocking guard of any kind - a
  Production Run with dependents can always be deleted; the page only shows
  a WARNING listing what else will be deleted (production_run_dependency_
  counts()), never a hard block. Setup Data's and Runtime Data's own delete
  (pages/4's local _delete_phase_cascade()) is the same story: it always
  proceeds, deleting that phase's stream readings/fall-plate positions and
  UNLINKING (not deleting) any Production Events that referenced it. So
  every delete test below exercises a real, unblocked delete - there is no
  "delete is blocked" branch anywhere in this page's code to test instead.
- Setup Data and Runtime Data have at most ONE row per run per phase_name,
  so their Edit form renders directly once that one row exists - there is
  no clickable_table row-selection step for these two groups (unlike Stream
  Reading, Production Event, and Production Run, which list potentially-many
  rows via helpers.clickable_table() and need the CR-10-correction-derived
  "preset the dataframe widget's own on_select state before .run()"
  technique - see test_cr10_product_family_grade_split.py's module
  docstring for why setting the derived "..._selected_id" key directly does
  NOT work, only presetting the table's own key does).
- Production Run's own Edit form has an extra wrinkle not present on any
  other page in this app: st.session_state["pr_selected_run_id"] is shared
  and re-set by every one of the OTHER 4 tabs' run-selector widgets on every
  rerun (they all resolve to the same one seeded run and re-assign it), but
  tab_runs' OWN code (which runs FIRST in script order, before those other 4
  tabs) unconditionally POPS that same key whenever its own runs_overview_
  table has no fresh row-click event this rerun. Net effect: Production
  Run's Edit form only ever appears on the exact rerun immediately after
  presetting session_state["runs_overview_table"]'s own selection state -
  it must be re-preset before every single .run() call where that form
  needs to be visible (mirrored in the delete step below, exactly like
  test_cr10_product_family_grade_split.py's own delete flow re-presets its
  table selection before deleting).

MANDATORY TEMPLATE: tests/test_cr10_product_family_grade_split.py (see that
file for the accepted DATABASE_URL/sys.path boilerplate, the cache-clearing
defense, the dataframe-preset-selection technique, and the file_uploader
technique - all copied here unchanged).

Usage: python -m pytest tests/test_cr11_functional_evidence_group_d.py -v
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

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE4 = os.path.join(APP_DIR, "pages", "4_Production_Run_Trial_Record.py")


def _clear_relevant_caches():
    """Same cross-test/cross-file @st.cache_data id-collision defense
    test_cr10_product_family_grade_split.py's own _clear_relevant_caches()
    documents and uses - every fixture below creates a fresh Company/Plant/
    ProductFamily/FoamGrade/ProductionRun after _reset_schema() restarts
    autoincrement ids at 1, and tenant_scope's id-scoping helpers are
    @st.cache_data'd on small-int keys (company_id/plant_ids/role_id) that
    repeat across tests/files once ids restart. run_ids_for_plants is
    especially relevant here since it's directly in this file's dependency
    chain (pages/4 calls plant_ids_for_company/grade_ids_for_company on
    every load, and every one of the 5 record groups ultimately hangs off
    apply_scope(..., plant_ids)/apply_scope(..., grade_ids))."""
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


def _run(session_state=None):
    """Same AUTH_DISABLED entry point as the CR-10 template - the dev
    bypass grants is_super_admin=True/is_platform_owner=True/company_id=None,
    so every "Save"/"Delete"/"Confirm import" control on this page is
    enabled (page_usable=True) and company_picker() locks onto whichever
    single seeded Company exists without needing a selectbox click."""
    at = AppTest.from_file(PAGE4, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


# ---------------------------------------------------------------------------
# Fixtures - the dependency chain
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_grade_chain():
    """Company -> Plant -> ProductionMethod (+ PlantProductionMethod
    activation) -> Machine (tagged to that method, active) -> ProductFamily
    -> FoamGrade (assigned to the Machine via the foam_grade_machines
    many-to-many) -> RecipeVersion (is_active=True). Deliberately stops
    short of creating a ProductionRun - this is the exact chain
    test_pm_hierarchy_pages_smoke.py's seeded_pm_hierarchy fixture builds
    for this same page, and it's what Production Run's own Create form
    needs to have anything to select: a product grade with an active
    recipe version (so the form doesn't hit its "no recipe version yet"
    error branch) and at least one Machine assigned to that grade (so the
    "Production Unit or Cell" picker offers a real option instead of just
    "-- not selected --"). Used directly by Production Run's own
    create/import tests (which create the run themselves); seeded_run
    below extends this one step further for every other test in this file."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR11D Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11D Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-CR11D-{u}", name=f"CR11D Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(
        plant_id=plant.id, name=f"CR11D Machine {u}", production_method_id=method.id, active=True,
    )
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"CR11D Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"CR11D Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True,
    )
    session.add(recipe); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "method_id": method.id,
        "machine_id": machine.id, "machine_name": machine.name,
        "family_id": family.id, "grade_id": grade.id, "grade_name": grade.grade_name,
        "recipe_version_id": recipe.id,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_run(seeded_grade_chain):
    """Extends seeded_grade_chain with exactly one ProductionRun - the
    root of the FK chain every one of the other 4 record groups
    (Setup Data, Stream Reading, Production Event, Runtime Data) hangs off.
    This is the base fixture for all of them, and for Production Run's own
    Edit/Delete/import tests where a pre-existing run is needed."""
    ids = seeded_grade_chain
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"],
        foam_grade_id=ids["grade_id"],
        recipe_version_id=ids["recipe_version_id"],
        run_date=dt.date(2026, 8, 1),
        batch_reference=f"B-CR11D-{uuid.uuid4().hex[:8]}",
        machine_id=ids["machine_id"],
        production_method_id=ids["method_id"],
        operator_or_team_reference="Shift A",
        notes="seed run",
    )
    session.add(run); session.commit()
    out = dict(ids)
    out["run_id"] = run.id
    session.close()
    return out


@pytest.fixture()
def seeded_setup_phase(seeded_run):
    """Extends seeded_run with one "Setup" ProductionPhase row already
    recorded for that run - seeded directly via the ORM rather than through
    the page's own Create Setup Data form, since that Create flow is
    exactly what test_setup_data_create_via_form below already exercises;
    building this fixture's prerequisite row through a second UI pass here
    would just be redundant with that test (per the brief's own guidance)."""
    ids = seeded_run
    session = db.get_session()
    phase = db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Setup",
        phase_start=dt.datetime(2026, 8, 1, 6, 0), phase_end=dt.datetime(2026, 8, 1, 7, 0),
        mixer_rpm=1500.0, conveyor_speed=2.5, notes="seed setup",
        source_file_reference="seed",
    )
    session.add(phase); session.commit()
    out = dict(ids)
    out["setup_phase_id"] = phase.id
    session.close()
    return out


@pytest.fixture()
def seeded_finalized_phase(seeded_run):
    """Extends seeded_run with one "Finalized" ProductionPhase row already
    recorded for that run - i.e. a Runtime Data row. This is the extra FK
    hop Stream Reading actually depends on (ComponentStreamReading.
    production_phase_id only ever points at a Finalized phase - see
    tab_streams' own gate in pages/4, which shows nothing but an info box
    until this exists), so it's the prerequisite fixture for every Stream
    Reading test below. It doubles as Runtime Data's own Edit/Delete
    prerequisite too - a Finalized phase IS a Runtime Data row; they are
    the same table, just the other tab's function on it."""
    ids = seeded_run
    session = db.get_session()
    phase = db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Finalized",
        phase_start=dt.datetime(2026, 8, 1, 8, 0), phase_end=dt.datetime(2026, 8, 1, 10, 0),
        mixer_rpm=1500.0, conveyor_speed=2.5, foam_height_mm=40.0, notes="seed runtime",
        source_file_reference="seed",
    )
    session.add(phase); session.commit()
    out = dict(ids)
    out["finalized_phase_id"] = phase.id
    session.close()
    return out


@pytest.fixture()
def seeded_stream_reading(seeded_finalized_phase):
    """Extends seeded_finalized_phase with one ComponentStreamReading
    already attached to that run's Finalized phase - the minimum needed to
    exercise Stream Reading's own Edit/Delete flow unambiguously (exactly
    one row, so clickable_table's row index 0 is unambiguous)."""
    ids = seeded_finalized_phase
    session = db.get_session()
    reading = db.ComponentStreamReading(
        production_phase_id=ids["finalized_phase_id"], stream_name="Polyol A (seed)",
        flow_unit="kg/min", flow=12.0, pump_speed=45.0, source_file_reference="seed",
    )
    session.add(reading); session.commit()
    out = dict(ids)
    out["stream_reading_id"] = reading.id
    session.close()
    return out


@pytest.fixture()
def seeded_event(seeded_run):
    """Extends seeded_run with one ProductionEvent already logged against
    that run (production_phase_id left None - Production Event's own Phase
    field is explicitly optional and never required) - the minimum needed
    to exercise Production Event's own Edit/Delete flow unambiguously."""
    ids = seeded_run
    session = db.get_session()
    event = db.ProductionEvent(
        production_run_id=ids["run_id"], event_ts=dt.datetime(2026, 8, 1, 9, 0),
        event_type="Alarm", severity="Low", description="seed event",
        source_file_reference="seed",
    )
    session.add(event); session.commit()
    out = dict(ids)
    out["event_id"] = event.id
    session.close()
    return out


# ---------------------------------------------------------------------------
# 1. Production Run
# ---------------------------------------------------------------------------

def test_production_run_create_via_form(seeded_grade_chain):
    """Drives the real Production Runs tab's Create sub-tab: picks the
    seeded Machine on the real "Production Unit or Cell" selectbox (its
    default index is 0 = "-- not selected --", since the widget's own
    option list is [None] + assigned_machines - so this must be explicitly
    selected, mirroring test_pm_hierarchy_pages_smoke.py's own Production
    Run create test for the same picker) and clicks the real "Save
    production run" submit button. seeded_grade_chain deliberately has no
    ProductionRun yet, so this test's own create is the only run in the
    database afterward."""
    ids = seeded_grade_chain
    at = _run()
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"

    machine_sb = next(sb for sb in at.selectbox if str(sb.label).startswith("Production Unit or Cell"))
    machine_display = next(opt for opt in machine_sb.options if ids["machine_name"] in str(opt))
    machine_sb.set_value(machine_display)

    save_btn = next(b for b in at.button if b.label == "Save production run")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new production run: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.ProductionRun)
        .filter(db.ProductionRun.foam_grade_id == ids["grade_id"])
        .order_by(db.ProductionRun.id.desc())
        .first()
    )
    assert created is not None, "New production run was not persisted"
    assert created.machine_id == ids["machine_id"]
    assert created.production_method_id == ids["method_id"], (
        "production_method_id snapshot should be derived from the selected machine"
    )
    session.close()


def test_production_run_selection_edit_and_delete_via_ui(seeded_run):
    """Presets the runs_overview_table dataframe widget's OWN on_select
    state (not pr_selected_run_id directly - see the module docstring's
    explanation of why tab_runs pops that key every rerun without a fresh
    click event) to select row 0 before each .run() where the Edit/Delete
    UI needs to be visible. Edits the run's Block reference through the
    real Edit form and confirms it persisted, then deletes it through the
    real confirm-checkbox + delete-button flow (delete_production_run_
    cascade has no blocking guard - production_run_dependency_counts() only
    drives a warning message - so this run, seeded with zero dependents,
    deletes cleanly) and confirms it's gone."""
    ids = seeded_run
    at = _run(session_state={"runs_overview_table": {"selection": {"rows": [0], "columns": []}}})
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["pr_selected_run_id"] == ids["run_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded run"
    )

    # --- Edit ---
    block_input = next(t for t in at.text_input if t.key == f"edit_run_block_{ids['run_id']}")
    block_input.set_value("CR11D-Correction-Edited-Block")
    # Filtered by the form_submit_button's own derived key
    # (f"FormSubmitter:{form_key}-{label}") rather than by label alone -
    # every one of the 5 record groups' Edit forms shares the identical
    # unkeyed "Save changes" label, and more than one of them can be
    # rendered on the page at the same time (each group's Edit form
    # appears independently, gated on ITS OWN selected/existing row) - a
    # plain label match would non-deterministically grab whichever
    # group's button AppTest's element list happens to order first.
    save_btn = next(b for b in at.button if b.key == f"FormSubmitter:edit_run_form_{ids['run_id']}-Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the production run: {at.exception}"

    session = db.get_session()
    edited = session.get(db.ProductionRun, ids["run_id"])
    assert edited.block_reference == "CR11D-Correction-Edited-Block", "Edit did not persist to the database"
    session.close()

    # --- Delete (re-preset the table selection - tab_runs pops it every rerun otherwise) ---
    at.session_state["runs_overview_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"run_{ids['run_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"run_{ids['run_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the production run: {at.exception}"

    session = db.get_session()
    assert session.get(db.ProductionRun, ids["run_id"]) is None, "Delete did not remove the production run"
    session.close()


def test_production_run_csv_import_via_ui(seeded_grade_chain):
    """Drives the real st.file_uploader on the Production Runs tab's
    Import sub-tab (key="run_upload") with an in-memory CSV, then clicks
    the real "Confirm import" button (key="confirm_run_import"). Row
    supplies foam_grade_id/recipe_version_id/machine_id - the exact
    columns the import validates a run's grade/recipe/machine against
    (recipe_version_id must belong to foam_grade_id; machine_id must
    resolve) - and leaves batch_reference blank so the page's own
    auto-generation runs, same as manual Create."""
    ids = seeded_grade_chain
    at = _run()
    assert not at.exception

    csv_bytes = (
        "foam_grade_id,recipe_version_id,machine_id,run_date,block_reference\n"
        f"{ids['grade_id']},{ids['recipe_version_id']},{ids['machine_id']},2026-08-02,CR11D-Imported-Block\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "run_upload")
    uploader.set_value(("runs.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_run_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.ProductionRun)
        .filter(
            db.ProductionRun.foam_grade_id == ids["grade_id"],
            db.ProductionRun.block_reference == "CR11D-Imported-Block",
        )
        .first()
    )
    assert imported is not None, "Imported production run was not persisted"
    assert imported.machine_id == ids["machine_id"]
    session.close()


# ---------------------------------------------------------------------------
# 2. Setup Data
# ---------------------------------------------------------------------------

def test_setup_data_create_via_form(seeded_run):
    """Drives the real Setup ("Planned Settings") tab's Create sub-tab:
    fills the real Mixer rpm / Conveyor speed number_inputs and clicks the
    real "Save Setup data" submit button. seeded_run has a ProductionRun
    but no ProductionPhase rows yet, so the run selector defaults straight
    to it (only one run exists) and no Setup row exists yet for the Create
    tab to defer to an Edit link instead."""
    ids = seeded_run
    at = _run()
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"

    mixer = next(n for n in at.number_input if n.key == f"new_setup_mixer_{ids['run_id']}")
    mixer.set_value(1200.0)
    conveyor = next(n for n in at.number_input if n.key == f"new_setup_conveyor_{ids['run_id']}")
    conveyor.set_value(2.2)

    save_btn = next(b for b in at.button if b.label == "Save Setup data")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving Setup data: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.ProductionPhase)
        .filter(db.ProductionPhase.production_run_id == ids["run_id"], db.ProductionPhase.phase_name == "Setup")
        .first()
    )
    assert created is not None, "New Setup data row was not persisted"
    assert created.mixer_rpm == 1200.0
    assert created.conveyor_speed == 2.2
    session.close()


def test_setup_data_selection_edit_and_delete_via_ui(seeded_setup_phase):
    """Setup Data has at most one row per run (hardcoded to phase_name=
    "Setup"), so there is no clickable_table row-selection step here (unlike
    Stream Reading/Production Event/Production Run below) - the real Edit
    form renders directly once seeded_setup_phase's one Setup row exists.
    Edits Conveyor speed through that real form and confirms it persisted,
    then deletes it through the real confirm-checkbox + delete-button flow
    (pages/4's local _delete_phase_cascade, unblocked - see module
    docstring) and confirms the row is gone."""
    ids = seeded_setup_phase
    at = _run()
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"

    conveyor = next(n for n in at.number_input if n.key == f"edit_setup_conveyor_{ids['setup_phase_id']}")
    conveyor.set_value(3.75)
    # Filtered by key, not label - see the same note in the Production Run
    # edit/delete test above (every group's Edit form shares the identical
    # unkeyed "Save changes" label).
    save_btn = next(
        b for b in at.button if b.key == f"FormSubmitter:edit_setup_form_{ids['setup_phase_id']}-Save changes"
    )
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing Setup data: {at.exception}"

    session = db.get_session()
    edited = session.get(db.ProductionPhase, ids["setup_phase_id"])
    assert edited.conveyor_speed == 3.75, "Edit did not persist to the database"
    session.close()

    confirm_box = next(c for c in at.checkbox if c.key == f"setup_{ids['setup_phase_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"setup_{ids['setup_phase_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting Setup data: {at.exception}"

    session = db.get_session()
    assert session.get(db.ProductionPhase, ids["setup_phase_id"]) is None, "Delete did not remove the Setup data row"
    session.close()


def test_setup_data_csv_import_via_ui(seeded_run):
    """Drives the real st.file_uploader on Setup's Import sub-tab
    (key="setup_upload") and the real "Confirm import" button
    (key="confirm_setup_import"). Required column is production_run_id
    only - phase_name is implied by which tab you import into (always
    "Setup" here), never a file column."""
    ids = seeded_run
    at = _run()
    assert not at.exception

    csv_bytes = f"production_run_id,mixer_rpm,conveyor_speed\n{ids['run_id']},1400,2.9\n".encode()
    uploader = next(u for u in at.file_uploader if u.key == "setup_upload")
    uploader.set_value(("setup.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_setup_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.ProductionPhase)
        .filter(db.ProductionPhase.production_run_id == ids["run_id"], db.ProductionPhase.phase_name == "Setup")
        .first()
    )
    assert imported is not None, "Imported Setup data row was not persisted"
    assert imported.mixer_rpm == 1400
    session.close()


# ---------------------------------------------------------------------------
# 3. Stream Reading
# ---------------------------------------------------------------------------

def test_stream_reading_create_via_form(seeded_finalized_phase):
    """Drives the real Material Metering and Actual Usage ("Component
    stream readings") tab's Create sub-tab. This group only renders any
    widgets once a Finalized phase (Runtime Data) exists for the selected
    run - seeded_finalized_phase supplies exactly that FK prerequisite,
    with no stream reading yet. Recipe components are empty here (no
    RecipeVersion component rows seeded - orthogonal to this group), so the
    form falls back to its real free-text "Or type a stream not in the
    recipe" input, exactly as the page's own fallback branch describes;
    fills that plus Flow, then clicks the real "Save stream reading"
    button."""
    ids = seeded_finalized_phase
    at = _run()
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"

    stream_other = next(
        t for t in at.text_input if str(t.label).startswith("Or type a stream not in the recipe")
    )
    stream_other.set_value("Isocyanate (manual entry)")
    flow_input = next(n for n in at.number_input if n.label == "Flow" and n.key is None)
    flow_input.set_value(15.5)

    save_btn = next(b for b in at.button if b.label == "Save stream reading")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a stream reading: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.ComponentStreamReading)
        .filter(
            db.ComponentStreamReading.production_phase_id == ids["finalized_phase_id"],
            db.ComponentStreamReading.stream_name == "Isocyanate (manual entry)",
        )
        .first()
    )
    assert created is not None, "New stream reading was not persisted"
    assert created.flow == 15.5
    session.close()


def test_stream_reading_selection_edit_and_delete_via_ui(seeded_stream_reading):
    """Presets the f"streams_table_{run_id}" dataframe widget's OWN
    on_select state to select row 0 before .run() - same CR-10-correction-
    derived technique as test_cr10_product_family_grade_split.py, applied
    to Stream Reading's own table key and its own pr_selected_stream_id
    derived state. Edits the stream name through the real Edit form and
    confirms it persisted, then deletes it through the real
    confirm-checkbox + delete-button flow and confirms it's gone."""
    ids = seeded_stream_reading
    table_key = f"streams_table_{ids['run_id']}"
    at = _run(session_state={table_key: {"selection": {"rows": [0], "columns": []}}})
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["pr_selected_stream_id"] == ids["stream_reading_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded stream reading"
    )

    name_input = next(t for t in at.text_input if t.key == f"edit_stream_name_{ids['stream_reading_id']}")
    name_input.set_value("Polyol A (edited)")
    # Filtered by key, not label. This is the one group where the
    # ambiguity is NOT hypothetical: seeded_stream_reading also carries a
    # Finalized ProductionPhase (it has to - Stream Reading only attaches
    # there), so Runtime Data's OWN Edit form (same page, same run, keyed
    # off that same phase row) is ALSO rendered at the same time, with the
    # identical unkeyed "Save changes" label - confirmed directly by
    # inspecting at.button during this correction: AppTest's element list
    # ordered "FormSubmitter:edit_runtime_form_<id>-Save changes" BEFORE
    # "FormSubmitter:edit_stream_form_<id>-Save changes" (alphabetical by
    # form key, not page/script execution order), so a plain
    # `b.label == "Save changes"` match silently grabbed Runtime Data's
    # button instead of Stream Reading's - a real false-pass this
    # key-based filter fixes.
    save_btn = next(
        b for b in at.button
        if b.key == f"FormSubmitter:edit_stream_form_{ids['stream_reading_id']}-Save changes"
    )
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the stream reading: {at.exception}"

    session = db.get_session()
    edited = session.get(db.ComponentStreamReading, ids["stream_reading_id"])
    assert edited.stream_name == "Polyol A (edited)", "Edit did not persist to the database"
    session.close()

    at.session_state[table_key] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"stream_{ids['stream_reading_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"stream_{ids['stream_reading_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the stream reading: {at.exception}"

    session = db.get_session()
    assert session.get(db.ComponentStreamReading, ids["stream_reading_id"]) is None, (
        "Delete did not remove the stream reading"
    )
    session.close()


def test_stream_reading_csv_import_via_ui(seeded_finalized_phase):
    """Drives the real st.file_uploader on Stream Reading's Import
    sub-tab (key="stream_upload") and the real "Confirm import" button
    (key="confirm_stream_import"). Required columns are production_run_id
    and stream_name - the import resolves production_run_id to that run's
    own Finalized phase automatically (readings always attach there, never
    to Setup); seeded_finalized_phase supplies that Finalized phase so the
    row is accepted rather than flagged."""
    ids = seeded_finalized_phase
    at = _run()
    assert not at.exception

    csv_bytes = f"production_run_id,stream_name,flow\n{ids['run_id']},Water blend (import),8.2\n".encode()
    uploader = next(u for u in at.file_uploader if u.key == "stream_upload")
    uploader.set_value(("streams.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_stream_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.ComponentStreamReading)
        .filter(
            db.ComponentStreamReading.production_phase_id == ids["finalized_phase_id"],
            db.ComponentStreamReading.stream_name == "Water blend (import)",
        )
        .first()
    )
    assert imported is not None, "Imported stream reading was not persisted"
    assert imported.flow == 8.2
    session.close()


# ---------------------------------------------------------------------------
# 4. Production Event
# ---------------------------------------------------------------------------

def test_production_event_create_via_form(seeded_run):
    """Drives the real Production Events tab's Create sub-tab: sets the
    real Event type / Severity selectboxes and Description text_area, then
    clicks the real "Save event" submit button. Unlike Setup Data/Runtime
    Data, Production Event's Create form is never deferred to an Edit link
    - a run can have many events - so this always renders regardless of
    whether other events already exist for the run (none do here)."""
    ids = seeded_run
    at = _run()
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"

    event_type_sb = next(sb for sb in at.selectbox if sb.label == "Event type *" and sb.key is None)
    event_type_sb.set_value("Intervention")
    severity_sb = next(sb for sb in at.selectbox if sb.label == "Severity" and sb.key is None)
    severity_sb.set_value("Medium")
    description = next(t for t in at.text_area if t.label == "Description" and t.key is None)
    description.set_value("Created via UI test")

    save_btn = next(b for b in at.button if b.label == "Save event")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a production event: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.ProductionEvent)
        .filter(db.ProductionEvent.production_run_id == ids["run_id"], db.ProductionEvent.event_type == "Intervention")
        .first()
    )
    assert created is not None, "New production event was not persisted"
    assert created.severity == "Medium"
    assert created.description == "Created via UI test"
    session.close()


def test_production_event_selection_edit_and_delete_via_ui(seeded_event):
    """Presets the f"events_table_{run_id}" dataframe widget's OWN
    on_select state to select row 0 before .run() - same technique as
    Stream Reading above, applied to Production Event's own table key and
    its own pr_selected_event_id derived state. Edits the event's
    Description through the real Edit form and confirms it persisted,
    then deletes it through the real confirm-checkbox + delete-button flow
    and confirms it's gone."""
    ids = seeded_event
    table_key = f"events_table_{ids['run_id']}"
    at = _run(session_state={table_key: {"selection": {"rows": [0], "columns": []}}})
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["pr_selected_event_id"] == ids["event_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded event"
    )

    desc_input = next(t for t in at.text_area if t.key == f"edit_event_desc_{ids['event_id']}")
    desc_input.set_value("Edited via UI test")
    # Filtered by key, not label - see the same note above.
    save_btn = next(
        b for b in at.button if b.key == f"FormSubmitter:edit_event_form_{ids['event_id']}-Save changes"
    )
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the production event: {at.exception}"

    session = db.get_session()
    edited = session.get(db.ProductionEvent, ids["event_id"])
    assert edited.description == "Edited via UI test", "Edit did not persist to the database"
    session.close()

    at.session_state[table_key] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"event_{ids['event_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"event_{ids['event_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the production event: {at.exception}"

    session = db.get_session()
    assert session.get(db.ProductionEvent, ids["event_id"]) is None, "Delete did not remove the production event"
    session.close()


def test_production_event_csv_import_via_ui(seeded_run):
    """Drives the real st.file_uploader on Production Event's Import
    sub-tab (key="event_upload") and the real "Confirm import" button
    (key="confirm_event_import"). Required columns are production_run_id,
    event_type, and event_ts; event_type must be one of the controlled
    EVENT_TYPES."""
    ids = seeded_run
    at = _run()
    assert not at.exception

    csv_bytes = (
        "production_run_id,event_type,event_ts,description\n"
        f"{ids['run_id']},Alarm,2026-08-01 10:00:00,Imported alarm\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "event_upload")
    uploader.set_value(("events.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_event_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.ProductionEvent)
        .filter(db.ProductionEvent.production_run_id == ids["run_id"], db.ProductionEvent.description == "Imported alarm")
        .first()
    )
    assert imported is not None, "Imported production event was not persisted"
    assert imported.event_type == "Alarm"
    session.close()


# ---------------------------------------------------------------------------
# 5. Runtime Data
# ---------------------------------------------------------------------------

def test_runtime_data_create_via_form(seeded_run):
    """Drives the real Runtime Data ("Actual Run and Cycle Data") tab's
    Create sub-tab: fills the real Mixer rpm / Conveyor speed
    number_inputs and clicks the real "Save Runtime Data" submit button.
    seeded_run has a ProductionRun but no Finalized-phase row yet, so this
    is a genuine first-time create, not a redundant pass over
    seeded_finalized_phase's already-seeded row."""
    ids = seeded_run
    at = _run()
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"

    mixer = next(n for n in at.number_input if n.key == f"new_runtime_mixer_{ids['run_id']}")
    mixer.set_value(1300.0)
    conveyor = next(n for n in at.number_input if n.key == f"new_runtime_conveyor_{ids['run_id']}")
    conveyor.set_value(2.6)

    save_btn = next(b for b in at.button if b.label == "Save Runtime Data")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving Runtime Data: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.ProductionPhase)
        .filter(db.ProductionPhase.production_run_id == ids["run_id"], db.ProductionPhase.phase_name == "Finalized")
        .first()
    )
    assert created is not None, "New Runtime Data row was not persisted"
    assert created.mixer_rpm == 1300.0
    assert created.conveyor_speed == 2.6
    session.close()


def test_runtime_data_selection_edit_and_delete_via_ui(seeded_finalized_phase):
    """Same as Setup Data above: Runtime Data has at most one row per run
    (hardcoded to phase_name="Finalized"), so there is no clickable_table
    row-selection step - the real Edit form renders directly once
    seeded_finalized_phase's one Finalized row exists. Edits Conveyor speed
    through that real form and confirms it persisted, then deletes it
    through the real confirm-checkbox + delete-button flow and confirms
    the row is gone. Uses a fixture with no Stream Reading rows attached
    (seeded_finalized_phase, not seeded_stream_reading), so the delete's
    real cascade (which also deletes any of this phase's stream readings)
    has nothing extra to remove here - this test is scoped to Runtime
    Data's own row only."""
    ids = seeded_finalized_phase
    at = _run()
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"

    conveyor = next(n for n in at.number_input if n.key == f"edit_runtime_conveyor_{ids['finalized_phase_id']}")
    conveyor.set_value(4.1)
    # Filtered by key, not label - see the same note in the Production Run
    # edit/delete test above.
    save_btn = next(
        b for b in at.button
        if b.key == f"FormSubmitter:edit_runtime_form_{ids['finalized_phase_id']}-Save changes"
    )
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing Runtime Data: {at.exception}"

    session = db.get_session()
    edited = session.get(db.ProductionPhase, ids["finalized_phase_id"])
    assert edited.conveyor_speed == 4.1, "Edit did not persist to the database"
    session.close()

    confirm_box = next(c for c in at.checkbox if c.key == f"runtime_{ids['finalized_phase_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"runtime_{ids['finalized_phase_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting Runtime Data: {at.exception}"

    session = db.get_session()
    assert session.get(db.ProductionPhase, ids["finalized_phase_id"]) is None, (
        "Delete did not remove the Runtime Data row"
    )
    session.close()


def test_runtime_data_csv_import_via_ui(seeded_run):
    """Drives the real st.file_uploader on Runtime Data's Import sub-tab
    (key="runtime_upload") and the real "Confirm import" button
    (key="confirm_runtime_import"). Required column is production_run_id
    only, same pattern as Setup Data - phase_name is implied (always
    "Finalized" on this tab)."""
    ids = seeded_run
    at = _run()
    assert not at.exception

    csv_bytes = f"production_run_id,mixer_rpm,foam_height_mm\n{ids['run_id']},1600,55\n".encode()
    uploader = next(u for u in at.file_uploader if u.key == "runtime_upload")
    uploader.set_value(("runtime.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_runtime_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.ProductionPhase)
        .filter(db.ProductionPhase.production_run_id == ids["run_id"], db.ProductionPhase.phase_name == "Finalized")
        .first()
    )
    assert imported is not None, "Imported Runtime Data row was not persisted"
    assert imported.mixer_rpm == 1600
    assert imported.foam_height_mm == 55
    session.close()


# ---------------------------------------------------------------------------
# CR-11 CLOSEOUT CORRECTION v2 (2026-08-12, per Charlie's CR11_Closeout_
# Correction_Review_Return_to_JC.docx) - items 1 and 2.
#
# Item 1 (Delete permission/safeguards): the first correction round never
# directly verified the permission-denied/view-only Delete behavior for any
# of these 5 record groups' real page key. Verified directly from the page
# source (line ~299 of pages/4_Production_Run_Trial_Record.py):
#   page_usable = can_use_page("production_run", role_id=user["role_id"],
#                               session=session, is_super_admin=user["is_super_admin"])
# is computed ONCE and reused, unmodified, as the gate for every one of the
# 5 groups' own `if page_usable: delete_with_confirm(...) else:
# st.caption("View-only access - deleting is restricted for your role.")`
# branch (Production Run ~line 491, Setup Data ~line 808, Stream Reading
# ~line 1286, Production Event ~line 1555, Runtime Data ~line 1877) - one
# page_key, "production_run", covers all 5. That means a single
# view_only_role_fixture below (one Role + one RolePagePermission row) is
# genuine, non-duplicated evidence for all 5 Delete-permission tests.
#
# Item 2 (Import validation handling): all 5 of these importers pre-existed
# CR-11 (only their tab wording/order was standardized) and, until now, only
# had successful-import evidence in this file - never a direct invalid-row/
# rejection test. Each test below drives that group's own actual bad-row
# check (read from the page source, not assumed) with a CSV row engineered
# to fail exactly that check, and confirms the row is flagged (a warning
# names the failing column/condition), the "Confirm import" button never
# renders (the page's own `if good_rows and st.button(...)` guard - no good
# rows means no button at all), and the database row count is unchanged.
# ---------------------------------------------------------------------------

@pytest.fixture()
def view_only_role_fixture(seeded_setup_phase, seeded_stream_reading, seeded_event):
    """A real company-scoped Role with an explicit RolePagePermission row
    denying *use* (can_view=True, can_use=False - access_control.py's "View
    only" state) on page_key="production_run" - direct evidence against the
    real can_use_page()/RolePagePermission plumbing pages/4 actually calls,
    not a hypothetical role. See the section docstring above for why one
    page_key/one role covers every one of the 5 groups' Delete-permission
    tests.

    Built by requesting seeded_setup_phase, seeded_stream_reading (which
    itself pulls in seeded_finalized_phase), and seeded_event together -
    three of this file's own dependency-chain fixtures, all ultimately
    extending the same seeded_run/seeded_grade_chain. pytest caches a
    function-scoped fixture once per test regardless of how many other
    fixtures request it, so this does not create three separate runs or
    call _reset_schema() more than once - it reuses the exact seeding logic
    already written above rather than rebuilding it, and leaves every one
    of the 5 groups with exactly one row to attempt to delete."""
    ids = dict(seeded_setup_phase)
    ids.update(seeded_stream_reading)
    ids.update(seeded_event)

    session = db.get_session()
    role = db.Role(company_id=ids["company_id"], name="CR11D Correction View Only", is_builtin=False)
    session.add(role); session.flush()
    session.add(db.RolePagePermission(role_id=role.id, page_key="production_run", can_view=True, can_use=False))
    session.commit()
    ids["role_id"] = role.id
    session.close()
    return ids


def _run_as_role(session_state, ids):
    """Same AUTH_DISABLED entry point as _run() above, but overriding the
    dev-bypass's own is_super_admin=True/is_platform_owner=True defaults
    (see auth.py's require_login docstring) with a real, restricted role -
    the dev bypass only setdefault()s these session_state keys, so
    presetting them BEFORE .run() makes require_login() leave them alone.
    Mirrors test_cr10_product_family_grade_split.py's own _run_as_role,
    applied to this page (PAGE4) instead."""
    at = AppTest.from_file(PAGE4, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["role_id"] = ids["role_id"]
    at.session_state["is_super_admin"] = False
    at.session_state["is_platform_owner"] = False
    at.session_state["company_id"] = ids["company_id"]
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


# --- Item 1: Delete permission/safeguards, one test per record group ---

def test_production_run_view_only_role_cannot_delete(view_only_role_fixture):
    """With a role denied 'use' on production_run, Production Run's real
    Edit/Delete tab still opens (the table and Edit form render - view-only
    is not "hidden", per access_control's own three-state model) but the
    confirm-checkbox + delete-button pair (key_prefix=f"run_{id}") never
    renders at all - the page's own `if page_usable: delete_with_confirm(
    ...) else: st.caption(...)` branch takes the caption path instead.
    Direct evidence the real UI, not just can_use_page() in isolation,
    blocks the delete surface for this role."""
    ids = view_only_role_fixture
    session = db.get_session()
    assert not access_control.can_use_page(
        "production_run", role_id=ids["role_id"], session=session, is_super_admin=False
    )
    before_count = session.query(db.ProductionRun).count()
    session.close()

    at = _run_as_role({"runs_overview_table": {"selection": {"rows": [0], "columns": []}}}, ids)
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["pr_selected_run_id"] == ids["run_id"]

    assert not any(c.key == f"run_{ids['run_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the Delete confirm-checkbox for Production Run"
    )
    assert not any(b.key == f"run_{ids['run_id']}_btn" for b in at.button), (
        "View-only role should not see the Delete button for Production Run"
    )
    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()

    session = db.get_session()
    after_count = session.query(db.ProductionRun).count()
    session.close()
    assert after_count == before_count, "Nothing should have been deletable/deleted for a view-only role"


def test_setup_data_view_only_role_cannot_delete(view_only_role_fixture):
    """Same evidence as above, for Setup Data's own delete surface
    (key_prefix=f"setup_{id}"). Setup Data's Edit form renders directly (no
    row-selection step - see the module docstring), so no table preset is
    needed before .run()."""
    ids = view_only_role_fixture
    session = db.get_session()
    before_count = session.query(db.ProductionPhase).filter(db.ProductionPhase.id == ids["setup_phase_id"]).count()
    session.close()

    at = _run_as_role(None, ids)
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"

    assert not any(c.key == f"setup_{ids['setup_phase_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the Delete confirm-checkbox for Setup Data"
    )
    assert not any(b.key == f"setup_{ids['setup_phase_id']}_btn" for b in at.button), (
        "View-only role should not see the Delete button for Setup Data"
    )
    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()

    session = db.get_session()
    after_count = session.query(db.ProductionPhase).filter(db.ProductionPhase.id == ids["setup_phase_id"]).count()
    session.close()
    assert after_count == before_count == 1, "The Setup data row must still exist for a view-only role"


def test_stream_reading_view_only_role_cannot_delete(view_only_role_fixture):
    """Same evidence as above, for Stream Reading's own delete surface
    (key_prefix=f"stream_{id}"). Requires presetting the
    streams_table_{run_id} dataframe widget's own selection state (same
    CR-10-derived technique the group's own edit/delete test above uses)
    so the Edit/Delete panel is actually visible to check."""
    ids = view_only_role_fixture
    session = db.get_session()
    before_count = session.query(db.ComponentStreamReading).filter(
        db.ComponentStreamReading.id == ids["stream_reading_id"]
    ).count()
    session.close()

    table_key = f"streams_table_{ids['run_id']}"
    at = _run_as_role({table_key: {"selection": {"rows": [0], "columns": []}}}, ids)
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["pr_selected_stream_id"] == ids["stream_reading_id"]

    assert not any(c.key == f"stream_{ids['stream_reading_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the Delete confirm-checkbox for Stream Reading"
    )
    assert not any(b.key == f"stream_{ids['stream_reading_id']}_btn" for b in at.button), (
        "View-only role should not see the Delete button for Stream Reading"
    )
    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()

    session = db.get_session()
    after_count = session.query(db.ComponentStreamReading).filter(
        db.ComponentStreamReading.id == ids["stream_reading_id"]
    ).count()
    session.close()
    assert after_count == before_count == 1, "The stream reading must still exist for a view-only role"


def test_production_event_view_only_role_cannot_delete(view_only_role_fixture):
    """Same evidence as above, for Production Event's own delete surface
    (key_prefix=f"event_{id}"). Requires presetting the
    events_table_{run_id} dataframe widget's own selection state, same
    technique."""
    ids = view_only_role_fixture
    session = db.get_session()
    before_count = session.query(db.ProductionEvent).filter(db.ProductionEvent.id == ids["event_id"]).count()
    session.close()

    table_key = f"events_table_{ids['run_id']}"
    at = _run_as_role({table_key: {"selection": {"rows": [0], "columns": []}}}, ids)
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["pr_selected_event_id"] == ids["event_id"]

    assert not any(c.key == f"event_{ids['event_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the Delete confirm-checkbox for Production Event"
    )
    assert not any(b.key == f"event_{ids['event_id']}_btn" for b in at.button), (
        "View-only role should not see the Delete button for Production Event"
    )
    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()

    session = db.get_session()
    after_count = session.query(db.ProductionEvent).filter(db.ProductionEvent.id == ids["event_id"]).count()
    session.close()
    assert after_count == before_count == 1, "The production event must still exist for a view-only role"


def test_runtime_data_view_only_role_cannot_delete(view_only_role_fixture):
    """Same evidence as above, for Runtime Data's own delete surface
    (key_prefix=f"runtime_{id}"). Like Setup Data, its Edit form renders
    directly (no row-selection step), so no table preset is needed."""
    ids = view_only_role_fixture
    session = db.get_session()
    before_count = session.query(db.ProductionPhase).filter(
        db.ProductionPhase.id == ids["finalized_phase_id"]
    ).count()
    session.close()

    at = _run_as_role(None, ids)
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"

    assert not any(c.key == f"runtime_{ids['finalized_phase_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the Delete confirm-checkbox for Runtime Data"
    )
    assert not any(b.key == f"runtime_{ids['finalized_phase_id']}_btn" for b in at.button), (
        "View-only role should not see the Delete button for Runtime Data"
    )
    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()

    session = db.get_session()
    after_count = session.query(db.ProductionPhase).filter(
        db.ProductionPhase.id == ids["finalized_phase_id"]
    ).count()
    session.close()
    assert after_count == before_count == 1, "The Runtime Data row must still exist for a view-only role"


# --- Item 2: Import validation handling, one test per record group ---

def test_production_run_csv_import_validation_rejects_invalid_row(seeded_grade_chain):
    """Production Run's own bad-row check (pages/4, tab_import under
    tab_runs): `ok = bool(grade_row and version_row and
    version_row.foam_grade_id == grade_row.id and machine_ok)`. This row
    supplies a real foam_grade_id but a recipe_version_id that does not
    exist at all, so version_row resolves to None and the row is flagged/
    rejected rather than silently imported."""
    ids = seeded_grade_chain
    at = _run()
    assert not at.exception

    session = db.get_session()
    before_count = session.query(db.ProductionRun).count()
    session.close()

    csv_bytes = (
        "foam_grade_id,recipe_version_id,machine_id,run_date,block_reference\n"
        f"{ids['grade_id']},999999,{ids['machine_id']},2026-08-02,CR11D-Bad-Recipe-Version\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "run_upload")
    uploader.set_value(("runs_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the invalid CSV: {at.exception}"

    assert not any(b.key == "confirm_run_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "recipe_version_id" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.ProductionRun).count()
    session.close()
    assert after_count == before_count, "A row with an unresolvable recipe_version_id must not be persisted"


def test_setup_data_csv_import_validation_rejects_invalid_row(seeded_run):
    """Setup Data's own bad-row check (pages/4, tab_import under
    tab_setup): `if row.get("production_run_id") in valid_run_ids`. This
    row's required column is present, but its value is a production_run_id
    that does not exist, so it is flagged/rejected rather than silently
    imported."""
    ids = seeded_run
    at = _run()
    assert not at.exception

    session = db.get_session()
    before_count = session.query(db.ProductionPhase).filter(db.ProductionPhase.phase_name == "Setup").count()
    session.close()

    bad_run_id = ids["run_id"] + 999999
    csv_bytes = f"production_run_id,mixer_rpm,conveyor_speed\n{bad_run_id},1400,2.9\n".encode()
    uploader = next(u for u in at.file_uploader if u.key == "setup_upload")
    uploader.set_value(("setup_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the invalid CSV: {at.exception}"

    assert not any(b.key == "confirm_setup_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "production_run_id" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.ProductionPhase).filter(db.ProductionPhase.phase_name == "Setup").count()
    session.close()
    assert after_count == before_count, "A row with a nonexistent production_run_id must not be persisted"


def test_stream_reading_csv_import_validation_rejects_invalid_row(seeded_finalized_phase):
    """Stream Reading's own bad-row check (pages/4, tab_import under
    tab_streams): `match = finalized_by_run.get(row.get("production_run_id"))`
    - readings only ever resolve against a run's Finalized phase. This row
    references a production_run_id that does not exist at all (so it has no
    Finalized phase, and never will), which is exactly the condition this
    importer's own check is guarding - distinct from every other group's
    "unknown run" check in that it's checking for a *phase*, not just the
    run row. seeded_finalized_phase gives the ONE real run here its own
    Finalized phase so the Import sub-tab actually renders (tab_streams
    shows nothing but an info box with zero Finalized phases anywhere for
    the selected run - see the module docstring)."""
    ids = seeded_finalized_phase
    at = _run()
    assert not at.exception

    session = db.get_session()
    before_count = session.query(db.ComponentStreamReading).count()
    session.close()

    bad_run_id = ids["run_id"] + 999999
    csv_bytes = f"production_run_id,stream_name,flow\n{bad_run_id},Water blend (bad),8.2\n".encode()
    uploader = next(u for u in at.file_uploader if u.key == "stream_upload")
    uploader.set_value(("streams_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the invalid CSV: {at.exception}"

    assert not any(b.key == "confirm_stream_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "finalized" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.ComponentStreamReading).count()
    session.close()
    assert after_count == before_count, "A row referencing a run with no Finalized phase must not be persisted"


def test_production_event_csv_import_validation_rejects_invalid_row(seeded_run):
    """Production Event's own bad-row check (pages/4, tab_import under
    tab_events): `if run_ok and row.get("event_type") in EVENT_TYPES and ts
    is not None`. This row has a valid production_run_id and a parseable
    event_ts, but an event_type outside the controlled EVENT_TYPES list, so
    it is flagged/rejected rather than silently imported."""
    ids = seeded_run
    at = _run()
    assert not at.exception

    session = db.get_session()
    before_count = session.query(db.ProductionEvent).count()
    session.close()

    csv_bytes = (
        "production_run_id,event_type,event_ts,description\n"
        f"{ids['run_id']},NotARealEventType,2026-08-01 10:00:00,Bad event type\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "event_upload")
    uploader.set_value(("events_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the invalid CSV: {at.exception}"

    assert not any(b.key == "confirm_event_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "event_type" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.ProductionEvent).count()
    session.close()
    assert after_count == before_count, "A row with an out-of-list event_type must not be persisted"


def test_runtime_data_csv_import_validation_rejects_invalid_row(seeded_run):
    """Runtime Data's own bad-row check (pages/4, tab_import under
    tab_runtime): `if row.get("production_run_id") in valid_run_ids` -
    identical shape to Setup Data's own check above (same required-columns
    contract, RUNTIME_REQUIRED_COLUMNS = ["production_run_id"]). This row's
    required column is present, but its value is a production_run_id that
    does not exist, so it is flagged/rejected rather than silently
    imported."""
    ids = seeded_run
    at = _run()
    assert not at.exception

    session = db.get_session()
    before_count = session.query(db.ProductionPhase).filter(db.ProductionPhase.phase_name == "Finalized").count()
    session.close()

    bad_run_id = ids["run_id"] + 999999
    csv_bytes = f"production_run_id,mixer_rpm,foam_height_mm\n{bad_run_id},1600,55\n".encode()
    uploader = next(u for u in at.file_uploader if u.key == "runtime_upload")
    uploader.set_value(("runtime_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the invalid CSV: {at.exception}"

    assert not any(b.key == "confirm_runtime_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "production_run_id" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.ProductionPhase).filter(db.ProductionPhase.phase_name == "Finalized").count()
    session.close()
    assert after_count == before_count, "A row with a nonexistent production_run_id must not be persisted"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
