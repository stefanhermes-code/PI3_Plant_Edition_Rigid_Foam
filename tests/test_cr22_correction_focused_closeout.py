"""CR-22 correction (2026-08-16) - direct AppTest evidence for the four
UI/import-level items Charlie's CR22_Focused_Closeout_Correction_
Instructions_to_JC.docx (returning CR22_Return_Package.docx for "focused
closeout correction") required beyond a helper-function truth table:

  Section 2 (F22-06 PM-applicability mechanism): "Add a direct automated
    test of the mechanism... The test must prove that the entry appears
    for a PM-500 Production Run, stays absent for PM-100 and PM-800
    Production Runs, and stays absent for Customer Trial and Optimization
    Trial paths." A synthetic STATE_ACTIVE, ["PM-500"]-restricted taxonomy
    entry is temporarily injected (quality_issue_taxonomy.py has zero
    method-specific entries on the real production taxonomy today - see
    that module's own docstring - so there is nothing real to test this
    mechanism against without a synthetic entry).
  Section 5 (direct PM-100/500/800 block_reference UI/import evidence):
    "Helper-function truth table alone does not satisfy this acceptance
    item" - AppTest-driven Add/Edit field presence, the mixed-method
    overview's empty marker, and CSV import accept/reject, beyond what
    test_cr22_semantic_freeze_evidence.py already proves at the
    report-builder-dict level.
  Section 6 (universal import wording): confirms the pre-existing
    pages/4_Production_Run_Trial_Record.py CSV-import-tab caption naming
    "block_reference (PM-500 only)" is actually rendered (implementation
    already existed before this correction; only evidence was missing).
  Section 7 (Customer/Optimization Trial Quality Issue direct tests): both
    trial paths show exactly the 32 Global active entries (AF22-01 Section
    4's frozen count), exclude all 10 quarantined entries from a fresh
    pick, and preserve historical readability for an already-recorded
    quarantined value on a trial-linked QualityObservation row.

Conventions follow tests/test_cr11_functional_evidence_group_b.py and
tests/test_cr11_functional_evidence_group_d.py (DATABASE_URL/sys.path
boilerplate, _clear_relevant_caches(), the dataframe-widget-own-selection-
state technique for row-click-driven Edit, the file_uploader technique for
CSV import, and - per test_cr13_suppliers_standalone_page.py's own note -
reading a real st.dataframe widget's rendered rows via at.dataframe's own
.value, a pandas DataFrame, rather than assuming values from source). The
three-method seed shape follows tests/test_cr22_semantic_freeze_evidence.py's
two_method_run_chain fixture, extended to three real controlled_id values
(PM-500/PM-100/PM-800) plus both trial paths.

Streamlit's own AppTest Selectbox.options is a list of FORMATTED display
strings (see streamlit/testing/v1/element_tree.py's Selectbox class -
options = list(proto.options), the rendered/format_func-applied labels),
not the raw option objects - so every object-valued selectbox below is
driven by matching a formatted-string prefix/substring and passing that
matched string to set_value(), the same pattern
test_cr11_functional_evidence_group_d.py's own
test_production_run_create_via_form uses for the Production Unit or Cell
picker.

Usage: python -m pytest tests/test_cr22_correction_focused_closeout.py -v
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
import quality_issue_taxonomy as qit
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_QI = os.path.join(APP_DIR, "pages", "6_Quality_Observation.py")
PAGE_RUN = os.path.join(APP_DIR, "pages", "4_Production_Run_Trial_Record.py")
PAGE_QTR = os.path.join(APP_DIR, "pages", "5_Physical_Property_Result.py")

EXPECTED_QUARANTINED = {
    "Bottom cavitation", "Bottom skin densification", "Gross splits", "Heavy skin",
    "Low block density", "Splits - abnormal fine/broken cell structure",
    "Splits - normal cell structure, open cells", "Stratification",
    "Tacky block surface", "Zigzag (tin) splits",
}


def _clear_relevant_caches():
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


def _run(page_path, session_state=None):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


# ---------------------------------------------------------------------------
# Shared fixture - Company -> Plant -> three ProductionMethods (real
# controlled_id PM-500/PM-100/PM-800) -> one Machine per method -> one
# shared ProductFamily/FoamGrade/RecipeVersion (assigned to all three
# machines) -> one ProductionRun per method (block_reference populated on
# ALL THREE - the same "gate is the method, not whether a value is
# present" proof test_cr22_semantic_freeze_evidence.py's two_method_run_
# chain fixture uses, extended to three methods) -> one CustomerTrial and
# one OptimizationTrial against the same grade (no Production Method
# context - the "Trial behavior" path).
# ---------------------------------------------------------------------------

@pytest.fixture()
def three_method_run_and_trial_chain():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR22C Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR22C Plant {u}")
    session.add(plant); session.flush()

    method_500 = db.ProductionMethod(controlled_id="PM-500", name=f"CR22C PM-500 {u}")
    method_100 = db.ProductionMethod(controlled_id="PM-100", name=f"CR22C PM-100 {u}")
    method_800 = db.ProductionMethod(controlled_id="PM-800", name=f"CR22C PM-800 {u}")
    session.add_all([method_500, method_100, method_800]); session.flush()
    for m in (method_500, method_100, method_800):
        session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=m.id, active=True))
    session.flush()

    machine_500 = db.Machine(
        plant_id=plant.id, name=f"CR22C Machine 500 {u}", production_method_id=method_500.id, active=True,
    )
    machine_100 = db.Machine(
        plant_id=plant.id, name=f"CR22C Machine 100 {u}", production_method_id=method_100.id, active=True,
    )
    machine_800 = db.Machine(
        plant_id=plant.id, name=f"CR22C Machine 800 {u}", production_method_id=method_800.id, active=True,
    )
    session.add_all([machine_500, machine_100, machine_800]); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"CR22C Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"CR22C Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine_500, machine_100, machine_800]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    run_500 = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference=f"B500-{u}", block_reference=f"BLK500-{u}",
        machine_id=machine_500.id, production_method_id=method_500.id,
    )
    run_100 = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference=f"B100-{u}", block_reference=f"BLK100-{u}",
        machine_id=machine_100.id, production_method_id=method_100.id,
    )
    run_800 = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference=f"B800-{u}", block_reference=f"BLK800-{u}",
        machine_id=machine_800.id, production_method_id=method_800.id,
    )
    session.add_all([run_500, run_100, run_800]); session.flush()

    customer_trial = db.CustomerTrial(
        plant_id=plant.id, foam_grade_id=grade.id, customer_name=f"CR22C Customer {u}", status="Open",
    )
    optimization_trial = db.OptimizationTrial(
        plant_id=plant.id, foam_grade_id=grade.id, status="Open",
    )
    session.add_all([customer_trial, optimization_trial]); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "plant_name": plant.name,
        "method_500_id": method_500.id, "method_100_id": method_100.id, "method_800_id": method_800.id,
        "method_500_name": method_500.name, "method_100_name": method_100.name, "method_800_name": method_800.name,
        "machine_500_id": machine_500.id, "machine_100_id": machine_100.id, "machine_800_id": machine_800.id,
        "machine_500_name": machine_500.name, "machine_100_name": machine_100.name, "machine_800_name": machine_800.name,
        "family_id": family.id, "grade_id": grade.id, "recipe_version_id": recipe.id,
        "run_500_id": run_500.id, "run_100_id": run_100.id, "run_800_id": run_800.id,
        "block_ref_500": run_500.block_reference, "block_ref_100": run_100.block_reference,
        "block_ref_800": run_800.block_reference,
        "customer_trial_id": customer_trial.id, "optimization_trial_id": optimization_trial.id,
    }
    session.close()
    return ids


def _select_formatted(selectbox, predicate):
    """Finds the single formatted display string among selectbox.options
    matching `predicate` and sets it as the widget's value - see the module
    docstring's note on why AppTest's Selectbox.options is a list of
    formatted strings, not raw objects."""
    match = next(opt for opt in selectbox.options if predicate(opt))
    selectbox.set_value(match)
    return selectbox


# ===========================================================================
# Part 1 - F22-06: direct evidence that the PM-applicability mechanism is
# genuinely wired into the Quality Issues page's UI, not just present as an
# unused module-level function (Charlie's Section 2/9).
# ===========================================================================

SYNTHETIC_ISSUE_NAME = "CR22 Correction Synthetic PM-500-Only Issue"
SYNTHETIC_CATEGORY = "Rise & cure behavior"


@pytest.fixture()
def synthetic_pm500_only_issue():
    """Temporarily injects one synthetic STATE_ACTIVE, production_methods=
    ["PM-500"] entry into an existing active category, mutating the same
    module-level structures quality_issue_taxonomy.py builds once at import
    time (QUALITY_ISSUE_TAXONOMY, _NAME_TO_ENTRY, _NAME_TO_ENTRY_LOWER),
    and removes it again in the finally block so no other test in the same
    process session is affected. Needed because the real production
    taxonomy has zero method-specific entries today (every active entry is
    Global) - see quality_issue_taxonomy.py's own docstring - so F22-06's
    mechanism has nothing real to prove itself against without a synthetic
    entry, exactly as Charlie's Section 2 anticipated."""
    entry = {
        "name": SYNTHETIC_ISSUE_NAME,
        "typical_causes": "Synthetic entry for CR-22 correction test evidence only - not a real issue type.",
        "state": qit.STATE_ACTIVE,
        "production_methods": ["PM-500"],
    }
    qit.QUALITY_ISSUE_TAXONOMY[SYNTHETIC_CATEGORY].append(entry)
    qit._NAME_TO_ENTRY[SYNTHETIC_ISSUE_NAME] = {"category": SYNTHETIC_CATEGORY, **entry}
    qit._NAME_TO_ENTRY_LOWER[SYNTHETIC_ISSUE_NAME.lower()] = qit._NAME_TO_ENTRY[SYNTHETIC_ISSUE_NAME]
    try:
        yield entry
    finally:
        qit.QUALITY_ISSUE_TAXONOMY[SYNTHETIC_CATEGORY].remove(entry)
        del qit._NAME_TO_ENTRY[SYNTHETIC_ISSUE_NAME]
        del qit._NAME_TO_ENTRY_LOWER[SYNTHETIC_ISSUE_NAME.lower()]


def _select_run_by_id(at, run_id):
    run_sb = next(sb for sb in at.selectbox if sb.key == "obs_run_select")
    _select_formatted(run_sb, lambda opt: opt.startswith(f"Run #{run_id} —"))
    at.run()
    return at


def test_f22_06_synthetic_pm500_only_issue_visible_only_for_pm500_run(
    three_method_run_and_trial_chain, synthetic_pm500_only_issue,
):
    """Drives the real 'Add quality issue' picker (outside any st.form,
    reacting immediately - see _issue_type_picker()'s own docstring) with
    'Record against' = Production Run, and proves the synthetic PM-500-only
    entry is offered for a PM-500 run and absent for PM-100 and PM-800
    runs - genuine AppTest-driven UI evidence of the mechanism end to end
    (page -> _issue_type_picker() -> quality_issue_taxonomy.
    active_issue_types_for_category()), not a call to that function in
    isolation."""
    ids = three_method_run_and_trial_chain
    at = _run(PAGE_QI)
    assert not at.exception, f"Unhandled exception loading Quality Issues: {at.exception}"

    source_sb = next(sb for sb in at.selectbox if sb.key == "obs_source_type")
    source_sb.set_value("Production Run")
    at.run()
    at = _select_run_by_id(at, ids["run_500_id"])

    cat_sb = next(sb for sb in at.selectbox if sb.key == "add_obs_category")
    cat_sb.set_value(SYNTHETIC_CATEGORY)
    at.run()

    issue_sb = next(sb for sb in at.selectbox if sb.key == "add_obs_issue_name")
    assert SYNTHETIC_ISSUE_NAME in issue_sb.options, (
        "Synthetic PM-500-only entry must be offered once 'Record against' resolves to a PM-500 run"
    )

    at = _select_run_by_id(at, ids["run_100_id"])
    issue_sb = next(sb for sb in at.selectbox if sb.key == "add_obs_issue_name")
    assert SYNTHETIC_ISSUE_NAME not in issue_sb.options, (
        "Synthetic PM-500-only entry must stay absent for a PM-100 Production Run"
    )

    at = _select_run_by_id(at, ids["run_800_id"])
    issue_sb = next(sb for sb in at.selectbox if sb.key == "add_obs_issue_name")
    assert SYNTHETIC_ISSUE_NAME not in issue_sb.options, (
        "Synthetic PM-500-only entry must stay absent for a PM-800 Production Run"
    )


def test_f22_06_synthetic_pm500_only_issue_absent_for_both_trial_paths(
    three_method_run_and_trial_chain, synthetic_pm500_only_issue,
):
    """AF22-01 Section 5's 'Trial behavior' requirement: Customer Trial and
    Optimization Trial carry no Production Method context, so a
    method-specific entry must never be offered there, regardless of which
    method the trial's underlying grade happens to also run on elsewhere."""
    ids = three_method_run_and_trial_chain
    at = _run(PAGE_QI)
    assert not at.exception

    source_sb = next(sb for sb in at.selectbox if sb.key == "obs_source_type")
    source_sb.set_value("Customer Trial")
    at.run()
    ct_sb = next(sb for sb in at.selectbox if sb.key == "obs_ct_select")
    _select_formatted(ct_sb, lambda opt: opt.startswith(f"Trial #{ids['customer_trial_id']} —"))
    at.run()
    cat_sb = next(sb for sb in at.selectbox if sb.key == "add_obs_category")
    cat_sb.set_value(SYNTHETIC_CATEGORY)
    at.run()
    issue_sb = next(sb for sb in at.selectbox if sb.key == "add_obs_issue_name")
    assert SYNTHETIC_ISSUE_NAME not in issue_sb.options, (
        "Synthetic PM-500-only entry must stay absent for the Customer Trial path"
    )

    source_sb = next(sb for sb in at.selectbox if sb.key == "obs_source_type")
    source_sb.set_value("Optimization Trial")
    at.run()
    ot_sb = next(sb for sb in at.selectbox if sb.key == "obs_ot_select")
    _select_formatted(ot_sb, lambda opt: opt.startswith(f"Trial #{ids['optimization_trial_id']} —"))
    at.run()
    cat_sb = next(sb for sb in at.selectbox if sb.key == "add_obs_category")
    cat_sb.set_value(SYNTHETIC_CATEGORY)
    at.run()
    issue_sb = next(sb for sb in at.selectbox if sb.key == "add_obs_issue_name")
    assert SYNTHETIC_ISSUE_NAME not in issue_sb.options, (
        "Synthetic PM-500-only entry must stay absent for the Optimization Trial path"
    )


# ===========================================================================
# Part 2 - direct PM-100/500/800 block_reference UI/import evidence
# (Charlie's Section 5), on pages/4_Production_Run_Trial_Record.py.
# ===========================================================================

def _select_plant_method_machine(at, plant_name, method_name, machine_name):
    plant_sb = next(sb for sb in at.selectbox if sb.key == "create_run_plant")
    _select_formatted(plant_sb, lambda opt: opt == plant_name)
    at.run()

    method_sb = next(sb for sb in at.selectbox if sb.key == "create_run_method")
    _select_formatted(method_sb, lambda opt: opt == method_name)
    at.run()

    machine_sb = next(sb for sb in at.selectbox if sb.key == "create_run_machine")
    _select_formatted(machine_sb, lambda opt: machine_name in opt)
    at.run()
    return at


def test_block_reference_add_form_field_present_only_for_pm500(three_method_run_and_trial_chain):
    """Drives the real Create Production Run form's Plant/Production
    Method/Production Unit or Cell pickers (all outside the st.form, same
    reactive-dependent-dropdown reasoning as pages/6's issue-type picker)
    for each of the three seeded methods and confirms the unkeyed 'Block
    reference' text_input inside the form is present only when the
    selected machine resolves to PM-500 (F22-04)."""
    ids = three_method_run_and_trial_chain
    at = _run(PAGE_RUN)
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"

    at = _select_plant_method_machine(at, ids["plant_name"], ids["method_500_name"], ids["machine_500_name"])
    assert any(t.label == "Block reference" and t.key is None for t in at.text_input), (
        "Block reference field must be shown on Create Production Run for a PM-500 machine"
    )

    at = _select_plant_method_machine(at, ids["plant_name"], ids["method_100_name"], ids["machine_100_name"])
    assert not any(t.label == "Block reference" and t.key is None for t in at.text_input), (
        "Block reference field must be hidden on Create Production Run for a PM-100 machine"
    )

    at = _select_plant_method_machine(at, ids["plant_name"], ids["method_800_name"], ids["machine_800_name"])
    assert not any(t.label == "Block reference" and t.key is None for t in at.text_input), (
        "Block reference field must be hidden on Create Production Run for a PM-800 machine"
    )


def _row_index_for_run(at, run_id):
    df_elem = next(d for d in at.dataframe if d.key == "runs_overview_table")
    df = df_elem.value
    return int(list(df["Run"]).index(run_id))


def test_block_reference_edit_form_field_present_only_for_pm500(three_method_run_and_trial_chain):
    """Presets the runs_overview_table dataframe widget's OWN on_select
    state (the only technique that genuinely drives clickable_table's
    row-click selection - see test_cr11_functional_evidence_group_d.py's
    module docstring for why tab_runs pops pr_selected_run_id every rerun
    without a fresh click event) for each of the three seeded runs in turn,
    and confirms the Edit form's Block reference text_input
    (key=f'edit_run_block_{run.id}') is present only for the PM-500 run.

    Uses a throwaway probe AppTest to read the overview table's rendered
    row order once (deterministic for this fixture's immutable data - see
    _row_index_for_run()), then a FRESH AppTest per run with that run's row
    selection preset BEFORE its own first .run() call. Presetting the
    selection on a SECOND .run() of an AppTest instance that already
    completed an unselected first run was verified (via a standalone
    repro) to resolve the wrong row - a real quirk of AppTest's dataframe
    on_select state, not of this page's own code - so every selection
    below is applied on a widget's very first render, exactly like every
    other passing test in this codebase that drives clickable_table."""
    ids = three_method_run_and_trial_chain
    probe = _run(PAGE_RUN)
    assert not probe.exception
    idx_500 = _row_index_for_run(probe, ids["run_500_id"])
    idx_100 = _row_index_for_run(probe, ids["run_100_id"])
    idx_800 = _row_index_for_run(probe, ids["run_800_id"])

    at_500 = _run(PAGE_RUN, session_state={"runs_overview_table": {"selection": {"rows": [idx_500], "columns": []}}})
    assert not at_500.exception
    assert at_500.session_state["pr_selected_run_id"] == ids["run_500_id"]
    assert any(t.key == f"edit_run_block_{ids['run_500_id']}" for t in at_500.text_input), (
        "Edit form's Block reference field must be shown for the PM-500 run"
    )

    at_100 = _run(PAGE_RUN, session_state={"runs_overview_table": {"selection": {"rows": [idx_100], "columns": []}}})
    assert not at_100.exception
    assert at_100.session_state["pr_selected_run_id"] == ids["run_100_id"]
    assert not any(t.key == f"edit_run_block_{ids['run_100_id']}" for t in at_100.text_input), (
        "Edit form's Block reference field must be hidden for the PM-100 run"
    )

    at_800 = _run(PAGE_RUN, session_state={"runs_overview_table": {"selection": {"rows": [idx_800], "columns": []}}})
    assert not at_800.exception
    assert at_800.session_state["pr_selected_run_id"] == ids["run_800_id"]
    assert not any(t.key == f"edit_run_block_{ids['run_800_id']}" for t in at_800.text_input), (
        "Edit form's Block reference field must be hidden for the PM-800 run"
    )


def test_mixed_method_overview_shows_empty_marker_for_non_pm500(three_method_run_and_trial_chain):
    """Reads the real runs_overview_table st.dataframe widget's OWN
    rendered .value (a pandas DataFrame reconstructed from arrow data - see
    test_cr13_suppliers_standalone_page.py's own note on why this is the
    genuine rendered-UI check, not a source-code read) and confirms the
    'Block' column shows the PM-500 run's populated block_reference value
    but the empty marker '—' for the PM-100 and PM-800 runs, even
    though all three rows carry a populated block_reference in the
    database - proving the UI gate is the run's Production Method, not
    merely whether a value is present (F22-04), at the actual rendered
    table level rather than only the report-builder-dict level
    test_cr22_semantic_freeze_evidence.py already covers."""
    ids = three_method_run_and_trial_chain
    at = _run(PAGE_RUN)
    assert not at.exception

    df_elem = next(d for d in at.dataframe if d.key == "runs_overview_table")
    df = df_elem.value
    row_500 = df[df["Run"] == ids["run_500_id"]].iloc[0]
    row_100 = df[df["Run"] == ids["run_100_id"]].iloc[0]
    row_800 = df[df["Run"] == ids["run_800_id"]].iloc[0]

    assert row_500["Block"] == ids["block_ref_500"]
    assert row_100["Block"] == "—", "PM-100 run's Block column should show the empty marker, not its stored value"
    assert row_800["Block"] == "—", "PM-800 run's Block column should show the empty marker, not its stored value"


def test_csv_import_tab_shows_universal_block_reference_wording(three_method_run_and_trial_chain):
    """Confirms the pre-existing pages/4 CSV-import-tab caption naming the
    block_reference PM-500-only rule is actually rendered (Charlie's
    Section 6) - the implementation itself predates this correction; only
    direct evidence that it renders was missing."""
    at = _run(PAGE_RUN)
    assert not at.exception

    captions = " ".join(c.value for c in at.caption)
    assert (
        "block_reference (PM-500 only): a value is accepted only when the row's machine_id resolves "
        "to PM-500 Rigid Block Production" in captions
    ), "The universal block_reference import-wording caption must be rendered on the CSV import tab"


def test_block_reference_csv_import_accepts_pm500_rejects_others(three_method_run_and_trial_chain):
    """Uploads three CSV rows, one per seeded method, each with a populated
    block_reference. Confirms only the PM-500 row is accepted (Rows ready
    to import: 1) and the other two are flagged/rejected (Rows flagged/
    rejected: 2), then confirms the import and proves only the PM-500 row
    actually landed in the database - direct import-level evidence beyond
    the Add/Edit form UI checks above."""
    ids = three_method_run_and_trial_chain
    at = _run(PAGE_RUN)
    assert not at.exception

    csv_bytes = (
        "foam_grade_id,recipe_version_id,machine_id,run_date,block_reference\n"
        f"{ids['grade_id']},{ids['recipe_version_id']},{ids['machine_500_id']},2026-08-05,CR22C-Import-500\n"
        f"{ids['grade_id']},{ids['recipe_version_id']},{ids['machine_100_id']},2026-08-05,CR22C-Import-100\n"
        f"{ids['grade_id']},{ids['recipe_version_id']},{ids['machine_800_id']},2026-08-05,CR22C-Import-800\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "run_upload")
    uploader.set_value(("runs.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    markdown_text = "".join(m.value for m in at.markdown if m.value)
    assert "Rows ready to import: **1**" in markdown_text, markdown_text
    assert "Rows flagged/rejected: **2**" in markdown_text, markdown_text

    confirm_btn = next(b for b in at.button if b.key == "confirm_run_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported_500 = (
        session.query(db.ProductionRun)
        .filter(db.ProductionRun.block_reference == "CR22C-Import-500")
        .first()
    )
    imported_100 = (
        session.query(db.ProductionRun)
        .filter(db.ProductionRun.block_reference == "CR22C-Import-100")
        .first()
    )
    imported_800 = (
        session.query(db.ProductionRun)
        .filter(db.ProductionRun.block_reference == "CR22C-Import-800")
        .first()
    )
    assert imported_500 is not None, "The PM-500 row should have imported"
    assert imported_100 is None, "The PM-100 row must not have imported (block_reference set on a non-PM-500 machine)"
    assert imported_800 is None, "The PM-800 row must not have imported (block_reference set on a non-PM-500 machine)"
    session.close()


# ===========================================================================
# Part 2b - rendered UI evidence for the Product scope radio's frozen order
# (Charlie's Section 5 standard applied to F22-01/F22-02): the existing
# test_cr18_product_family_terminology.py::test_quality_pages_product_scope_
# control_says_product_family only reads pages/5 and pages/6's SOURCE CODE
# for the exact options-list string - a helper/source-text check, not
# genuine rendered-widget evidence. These two tests drive the real
# st.radio widget and read its actual rendered .options.
# ===========================================================================

def test_quality_test_result_product_scope_radio_renders_frozen_order(three_method_run_and_trial_chain):
    at = _run(PAGE_QTR)
    assert not at.exception, f"Unhandled exception loading Quality Test Results: {at.exception}"
    radio = next(r for r in at.radio if r.key == "qtr_foam_scope_mode")
    assert list(radio.options) == ["All product grades", "Product family", "Product grade"], (
        f"Quality Test Result's rendered Product scope radio order is {list(radio.options)!r}"
    )


def test_quality_issue_product_scope_radio_renders_frozen_order(three_method_run_and_trial_chain):
    at = _run(PAGE_QI)
    assert not at.exception, f"Unhandled exception loading Quality Issues: {at.exception}"
    radio = next(r for r in at.radio if r.key == "qi_foam_scope_mode")
    assert list(radio.options) == ["All product grades", "Product family", "Product grade"], (
        f"Quality Issue's rendered Product scope radio order is {list(radio.options)!r}"
    )


# ===========================================================================
# Part 3 - Customer/Optimization Trial Quality Issue direct tests
# (Charlie's Section 7).
# ===========================================================================

def _collect_all_active_issue_names(at, category_key, issue_key):
    """Drives the real category selectbox through every AF22-01-active
    category and unions the real issue-name selectbox's offered options -
    a genuine, executed sweep of everything the picker will show for
    whichever source is currently selected, not a call to
    active_issue_types_for_category() in isolation."""
    names = set()
    for category in qit.active_categories():
        cat_sb = next(sb for sb in at.selectbox if sb.key == category_key)
        cat_sb.set_value(category)
        at.run()
        issue_sb = next(sb for sb in at.selectbox if sb.key == issue_key)
        names.update(issue_sb.options)
    return names


def test_customer_trial_quality_issue_picker_shows_all_32_active_global_entries(
    three_method_run_and_trial_chain,
):
    """AF22-01 Section 4 froze the taxonomy at 32 ACTIVE / 10 QUARANTINED
    entries (test_cr22_semantic_freeze_evidence.py's own test proves the
    counts at the function level). This is the UI-level proof for the
    Customer Trial path specifically: sweeping every active category's
    picker while 'Record against' = Customer Trial yields exactly 32
    distinct issue names, none of them from the quarantined set."""
    ids = three_method_run_and_trial_chain
    at = _run(PAGE_QI)
    assert not at.exception

    source_sb = next(sb for sb in at.selectbox if sb.key == "obs_source_type")
    source_sb.set_value("Customer Trial")
    at.run()
    ct_sb = next(sb for sb in at.selectbox if sb.key == "obs_ct_select")
    _select_formatted(ct_sb, lambda opt: opt.startswith(f"Trial #{ids['customer_trial_id']} —"))
    at.run()

    names = _collect_all_active_issue_names(at, "add_obs_category", "add_obs_issue_name")
    assert len(names) == 32, f"Expected exactly 32 active Global entries offered for Customer Trial, got {len(names)}: {sorted(names)}"
    assert names.isdisjoint(EXPECTED_QUARANTINED), (
        f"Quarantined name(s) leaked into the Customer Trial picker: {names & EXPECTED_QUARANTINED}"
    )


def test_optimization_trial_quality_issue_picker_shows_all_32_active_global_entries(
    three_method_run_and_trial_chain,
):
    """Same evidence as the Customer Trial test above, for the
    Optimization Trial path."""
    ids = three_method_run_and_trial_chain
    at = _run(PAGE_QI)
    assert not at.exception

    source_sb = next(sb for sb in at.selectbox if sb.key == "obs_source_type")
    source_sb.set_value("Optimization Trial")
    at.run()
    ot_sb = next(sb for sb in at.selectbox if sb.key == "obs_ot_select")
    _select_formatted(ot_sb, lambda opt: opt.startswith(f"Trial #{ids['optimization_trial_id']} —"))
    at.run()

    names = _collect_all_active_issue_names(at, "add_obs_category", "add_obs_issue_name")
    assert len(names) == 32, f"Expected exactly 32 active Global entries offered for Optimization Trial, got {len(names)}: {sorted(names)}"
    assert names.isdisjoint(EXPECTED_QUARANTINED), (
        f"Quarantined name(s) leaked into the Optimization Trial picker: {names & EXPECTED_QUARANTINED}"
    )


@pytest.fixture()
def trial_quarantined_observations(three_method_run_and_trial_chain):
    """Extends three_method_run_and_trial_chain with one QualityObservation
    per trial path, each already carrying a real QUARANTINED taxonomy name
    ('Low block density') - seeded directly via the ORM (matching a
    historical/legacy row, or one recorded before the entry was
    quarantined), the minimum needed to test F22-06/F22-07's 'historical
    readability' guarantee on the two trial paths specifically (already
    proven for Production Run by test_cr22_semantic_freeze_evidence.py's
    test_quarantined_entry_still_selectable_when_already_recorded_on_a_row
    at the function level)."""
    ids = three_method_run_and_trial_chain
    session = db.get_session()
    ct_obs = db.QualityObservation(
        customer_trial_id=ids["customer_trial_id"], observation_type="Low block density",
        severity="Medium", frequency="One-off", confidence_level="Likely", observed_at=dt.date.today(),
    )
    ot_obs = db.QualityObservation(
        optimization_trial_id=ids["optimization_trial_id"], observation_type="Low block density",
        severity="Medium", frequency="One-off", confidence_level="Likely", observed_at=dt.date.today(),
    )
    session.add_all([ct_obs, ot_obs]); session.flush()
    session.commit()
    out = dict(ids)
    out["ct_obs_id"] = ct_obs.id
    out["ot_obs_id"] = ot_obs.id
    session.close()
    return out


def _row_index_in_obs_table(at, predicate):
    df_elem = next(d for d in at.dataframe if d.key == "obs_table")
    df = df_elem.value
    for i, row in df.iterrows():
        if predicate(row):
            return int(i)
    raise AssertionError(f"No matching row found in obs_table: {df.to_dict('records')}")


def test_customer_trial_quality_issue_edit_keeps_quarantined_value_readable(trial_quarantined_observations):
    """Selects the seeded Customer-Trial-linked QualityObservation (already
    carrying the quarantined 'Low block density' value) via the real
    obs_table row-click, and confirms the Edit form's own issue-name
    picker still shows and defaults to 'Low block density' for that one
    row - the include_names escape hatch proven at the function level by
    test_cr22_semantic_freeze_evidence.py, now proven through the real
    Customer Trial Edit UI."""
    ids = trial_quarantined_observations
    at = _run(PAGE_QI)
    assert not at.exception

    idx = _row_index_in_obs_table(at, lambda r: r["Source"] == "Customer Trial")
    at.session_state["obs_table"] = {"selection": {"rows": [idx], "columns": []}}
    at.run()
    assert at.session_state["obs_selected_id"] == ids["ct_obs_id"]

    issue_sb = next(sb for sb in at.selectbox if sb.key == f"edit_obs_{ids['ct_obs_id']}_issue_name")
    assert issue_sb.value == "Low block density", (
        "Edit form should default to the already-recorded quarantined value on this row"
    )
    assert "Low block density" in issue_sb.options, (
        "The quarantined value must remain selectable while editing the row that already carries it"
    )


def test_optimization_trial_quality_issue_edit_keeps_quarantined_value_readable(trial_quarantined_observations):
    """Same evidence as the Customer Trial test above, for the
    Optimization-Trial-linked observation."""
    ids = trial_quarantined_observations
    at = _run(PAGE_QI)
    assert not at.exception

    idx = _row_index_in_obs_table(at, lambda r: r["Source"] == "Optimization Trial")
    at.session_state["obs_table"] = {"selection": {"rows": [idx], "columns": []}}
    at.run()
    assert at.session_state["obs_selected_id"] == ids["ot_obs_id"]

    issue_sb = next(sb for sb in at.selectbox if sb.key == f"edit_obs_{ids['ot_obs_id']}_issue_name")
    assert issue_sb.value == "Low block density", (
        "Edit form should default to the already-recorded quarantined value on this row"
    )
    assert "Low block density" in issue_sb.options, (
        "The quarantined value must remain selectable while editing the row that already carries it"
    )
