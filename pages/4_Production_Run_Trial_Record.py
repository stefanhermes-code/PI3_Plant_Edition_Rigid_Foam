"""Screen 5: Production Run

The primary, self-sufficient record of a batch: recipe used, machine
parameters, and (elsewhere) the quality results it produced. This is
routine, everyday data entry - it does NOT require framing a run as an
experiment. A deliberate trial/change investigation is captured as its own
independent Customer Trial or Optimization Trial record instead (see
pages/11_Customer_Trials.py / pages/12_Optimization_Trials.py) - the old
"Trial / Experiment" flag on a production run itself, and the standalone
Trial / Experiment page, were removed along with TrialRecord/
AdjustmentConclusion/ApprovalRecord (see cascades.py/db.py history).

Includes the Mandatory-tier process-data capture recommended in "Expanding
PI3 Plant Edition Production-Trial Data Capture for Polyurethane Foaming
Lines", adapted to what's actually capturable without a live PLC/OPC UA/MQTT
link or a machine data export/import: each run gets exactly two phase
snapshots, Setup (planned/configured before the run) and Finalized (what
actually happened, entered at shutdown).

CR-01 (UI Navigation and Rigid-Foam Terminology for UAT), implemented
2026-08-10: the tab bar's visible labels were renamed per CR-01's mandatory
terminology table - "Setup" -> "Planned Settings", "Runtime Data" ->
"Actual Run and Cycle Data", "Component Stream Readings" -> "Material
Metering and Actual Usage", "Fall-plate positions" -> "Tool Geometry and
Fill Configuration", "Meters produced" -> "Output Quantity and Unit". These
are label-only changes - the underlying ProductionPhase.phase_name values
("Setup"/"Finalized"), table/column names, and every docstring/comment
below that predates this rename still say "Setup"/"Runtime Data" etc.,
since renaming those would be a backend/data change CR-01 explicitly does
not require (see the CR-01 document's "backend entity name may stay"
guidance).

Laid out as one tab per function: Production Runs (overview/edit/delete +
create), Planned Settings, Actual Run and Cycle Data, Material Metering and
Actual Usage, and Production Events. Every function tab (other than
Production Runs) opens with a
production-run selector shared with the other tabs, shows that run's related
record(s) with edit + delete, and keeps CSV/Excel bulk import as its own
sub-tab. Raw material lot tracking has been removed from this page (not
workable — batches get mixed in tanks); the underlying table is left
untouched in the schema.

Setup and Runtime Data used to be a single generic "Process Phases" tab (a
phase_name dropdown picking which of the two ProductionPhase snapshots you
were editing) plus a separate standalone "Runtime Data" tab backed by its
own RuntimeDataRecord table — the two were doing overlapping work (e.g.
RuntimeDataRecord.line_speed duplicating ProductionPhase.conveyor_speed).
Restructured 2026-08-02 into two dedicated tabs instead: Setup (hardcoded to
the "Setup" ProductionPhase row) and Runtime Data (hardcoded to the
"Finalized" ProductionPhase row, now also carrying rise_time — one of the
two fields RuntimeDataRecord had that nothing else captured (the other,
curing_notes, was removed from the app entirely on 2026-08-03 - not a real,
reliably-captured field in practice). See RuntimeDataRecord in db.py for
why that table is still there but retired.

Setup's field set was narrowed again on 2026-08-03, after feedback that
several fields shown there weren't actually Setup-appropriate: foam_height_mm
(a measured outcome of the foaming process, not something planned) and the
ambient temperature/humidity readings (observed conditions, not configured)
moved to Runtime Data only; ratio_index moved off ProductionPhase entirely
onto RecipeVersion (it's a formulation constant, not a per-run setting - see
db.py); the free-text "laydown_mode" field was renamed "Foaming mode" and
converted to a controlled dropdown (FOAMING_MODES: LLD/Trough/Traverse); the
free-text "Other geometry notes" field was dropped now that fall-plate
section positions are captured in structured form below it; and a new
top_flat_system_used yes/no field was added. Both Setup and Runtime Data
still carry the shared machine settings (mixer/conveyor/air/sidewall/foaming
mode/top-flat), so the plan-vs-actual comparison still works for those.

WP7 Phase 0 (Contain inherited Flexible Foam functionality), implemented
2026-08-13: this app is Rigid Foam only, so the above 2026-08-03 additions
turned out to be structural inheritance from the Flexible Foam/slabstock
sibling app, not Rigid-relevant controls. Removed from both Setup and
Runtime Data: the "Foaming mode" dropdown (FOAMING_MODES: LLD/Trough/
Traverse - a slabstock line-configuration concept), the "Top-flat system in
use?" universal boolean, and the entire "Tool Geometry and Fill
Configuration" fall-plate-position sub-workflow (manual entry + CSV/Excel
import), since active fall-plate section-position entry is itself
Maxfoam/slabstock-specific tooling. This is a containment change only - no
schema/table changes: FallplateSectionPosition rows, and the foaming_mode/
top_flat_system_used columns on ProductionPhase, remain in the database
and historical data stays readable; only the active UI, CSV import parsing,
report generation, and analytics ranking surfaces were removed. See
analytics.py/reports.py/pages/21_Report.py for the matching changes, and
db.py for why FOAMING_MODES/FallplateSectionPosition/
expected_fallplate_section_count remain defined but are no longer
referenced from this page (FallplateSectionPosition itself is still
referenced here, by _delete_phase_cascade, for legitimate cascade-delete
cleanup of historical rows). Tunnel width (sidewall_width_mm), mixer rpm,
conveyor speed, and air injection rate/pressure are unchanged in this
phase - later WP7 phases will re-evaluate those as method-specific
parameters rather than universal ones.
"""

import datetime as dt

import pandas as pd
import streamlit as st

import analytics
from access_control import can_use_page
from auth import current_user, logout_button, require_login
from cascades import delete_production_run_cascade, production_run_dependency_counts
from db import (
    EVENT_TYPES,
    PRODUCTION_OUTPUT_DISPOSITIONS,
    PRODUCTION_RUN_STATUSES,
    SEVERITIES,
    Cavity,
    ComponentStreamReading,
    FallplateSectionPosition,
    FillPoint,
    FoamGrade,
    Machine,
    Mixhead,
    Plant,
    PhysicalPropertyResult,
    ProcessParameterValue,
    ProcessSettingDefinition,
    ProductionCycle,
    ProductionEvent,
    ProductionMethod,
    ProductionOutputSummary,
    ProductionPhase,
    ProductionRun,
    ProductionShot,
    QualityObservation,
    RawMaterialLotUse,
    RecipeComponent,
    RecipeVersion,
    Sample,
    Tool,
    UnitOfMeasure,
    get_session,
    init_db,
)
from helpers import (
    activated_methods_for_plant,
    clickable_table,
    combine_date_time,
    cr11_function_tab_labels,
    csv_excel_uploader,
    dedupe_import_rows,
    delete_with_confirm,
    import_within_row_limit,
    machines_for_plant_and_method,
    page_setup,
    parse_dt,
    render_data_table,
    render_function_action_intro,
    run_uses_cycle_shot_operation,
    set_pending_banner,
    show_pending_banner,
    upload_within_size_limit,
    view_only_notice,
)
from tenant_scope import apply_scope, clear_scope_cache, company_picker, grade_ids_for_company, plant_ids_for_company


@st.cache_data(ttl=30)
def _cached_versions_for_grade(_session, grade_id):
    """RecipeVersion rows for one product grade. This page's Edit-run form and
    Add-run form each independently re-ran this exact query on every
    rerun (a Streamlit rerun fires on every widget interaction anywhere on
    the page, including switching tabs) - one of the contributors to this
    page's ~31-query-per-click count found in the 2026-08-05 performance
    audit. clear_scope_cache() (called after every write on this page)
    invalidates this too."""
    if not grade_id:
        return []
    return _session.query(RecipeVersion).filter(RecipeVersion.foam_grade_id == grade_id).all()


RUN_REQUIRED_COLUMNS = ["foam_grade_id", "recipe_version_id"]
RUN_OPTIONAL_COLUMNS = [
    "machine_id", "run_date", "batch_reference", "block_reference",
    "operator_or_team_reference", "notes",
]

# Setup and Runtime Data are both ProductionPhase rows (phase_name "Setup"
# and "Finalized" respectively) - each tab is hardcoded to its own phase_name,
# so imports need production_run_id only; phase_name is implied by which tab
# you're importing into, not a file column.
#
# Setup's column set is deliberately narrower than Runtime Data's as of
# 2026-08-03: foam_height_mm (a measured outcome, not something planned) and
# ambient_temperature_c/ambient_humidity_pct (observed environmental
# conditions, not configured) were removed from Setup - both still exist on
# Runtime Data, the actual/observed snapshot. ratio_index was removed from
# both (it is now a recipe-level field - see RecipeVersion.ratio_index).
#
# WP7 Phase 0 (2026-08-13): foaming_mode and top_flat_system_used were
# removed from this import contract - they were inherited Flexible Foam/
# slabstock controls, not universal Rigid settings (see the module
# docstring). The columns still exist on ProductionPhase for historical
# rows; a file that still includes them simply has those columns ignored.
#
# WP7 Phase 5 (2026-08-15, Legacy Retirement): the machine-setting,
# ambient-condition, and runtime-outcome columns (mixer_rpm, conveyor_speed,
# air_injection_rate, air_pressure_bar, sidewall_width_mm,
# ambient_temperature_c, ambient_humidity_pct, rise_time, foam_height_mm,
# meters_produced) were removed from this import contract for the same
# reason - ProductionPhase is now ARCHIVE READ-ONLY for those fields (see
# the WP7 Phase 5 JC Pre-Coding Engineering Challenge Response, Section 4).
# Planned/Actual process settings import through the Method-Aware Process
# Settings tab's own data path instead; a file that still includes these
# columns simply has them ignored.
SETUP_REQUIRED_COLUMNS = ["production_run_id"]
SETUP_OPTIONAL_COLUMNS = ["phase_start", "phase_end", "notes"]

RUNTIME_REQUIRED_COLUMNS = ["production_run_id"]
RUNTIME_OPTIONAL_COLUMNS = SETUP_OPTIONAL_COLUMNS

# Component stream readings are actual measurements taken once production is
# running, so they only ever attach to a run's Finalized phase — never to
# Setup (which is the planned/configured snapshot before the run starts).
# phase_name is therefore not part of the import contract; the Finalized
# phase for the run is resolved automatically.
STREAM_REQUIRED_COLUMNS = ["production_run_id", "stream_name"]
STREAM_OPTIONAL_COLUMNS = [
    "flow_unit", "flow", "pump_speed", "flow_total_qty", "pressure_bar", "temperature_c",
    "calibration_status", "calibration_note", "notes",
]

# FALLPLATE_REQUIRED_COLUMNS/FALLPLATE_OPTIONAL_COLUMNS (the "Tool Geometry
# and Fill Configuration" CSV import contract) were removed under WP7 Phase
# 0 along with the active fall-plate section-position sub-workflow itself -
# see the module docstring. FallplateSectionPosition rows already imported
# remain in the database untouched.

EVENT_REQUIRED_COLUMNS = ["production_run_id", "event_type", "event_ts"]
EVENT_OPTIONAL_COLUMNS = ["phase_name", "severity", "description", "action_taken"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _run_label(r):
    return f"Run #{r.id} — {r.foam_grade.grade_name} · {r.run_date}"


def _max_batch_seq_for_prefix(session, prefix, plant_ids):
    """Highest existing sequence number already used under a given
    'B-DDMMYY' prefix, scoped to this company's plants (plant_ids=None means
    unfiltered - the platform owner viewing "All companies"). Uses the max,
    not a count, so a deleted or out-of-order batch reference never causes a
    duplicate number to be reissued. Scoping matters here too: without it,
    one company's daily batch count would jump around based on a different
    company's unrelated activity on the same calendar day."""
    query = session.query(ProductionRun.batch_reference).filter(ProductionRun.batch_reference.like(f"{prefix}-%"))
    existing = apply_scope(query, ProductionRun.plant_id, plant_ids).all()
    max_seq = 0
    for (br,) in existing:
        if not br:
            continue
        tail = br.rsplit("-", 1)[-1]
        if tail.isdigit():
            max_seq = max(max_seq, int(tail))
    return max_seq


def _generate_batch_reference(session, run_date, plant_ids):
    """Auto-generate a batch reference as B-DDMMYY-NN (e.g. B-240726-01),
    NN scoped per calendar day (and per company) so it resets daily and
    stays short. Manual batch numbers are error-prone (typos, accidental
    duplicates) so this is computed rather than typed."""
    prefix = f"B-{run_date:%d%m%y}"
    return f"{prefix}-{_max_batch_seq_for_prefix(session, prefix, plant_ids) + 1:02d}"


def _run_selector(runs, key):
    """Selectbox defaulting to the run selected elsewhere on the page
    (st.session_state['pr_selected_run_id']), keeping every tab in sync."""
    default_id = st.session_state.get("pr_selected_run_id")
    default_index = 0
    if default_id is not None:
        ids = [r.id for r in runs]
        if default_id in ids:
            default_index = ids.index(default_id)
    run = st.selectbox(
        "Production run *",
        runs,
        index=default_index,
        format_func=_run_label,
        key=key,
    )
    if run is not None:
        st.session_state["pr_selected_run_id"] = run.id
    return run


# --- Production run cascade delete (a run can have a lot hanging off it) ---
# Shared with pages 1/2/3, which have to delete every run under a plant/
# product family/product grade/recipe version being deleted - see cascades.py.

def _delete_phase_cascade(session, phase):
    phase_id = phase.id
    session.query(ComponentStreamReading).filter(
        ComponentStreamReading.production_phase_id == phase_id
    ).delete(synchronize_session=False)
    session.query(FallplateSectionPosition).filter(
        FallplateSectionPosition.production_phase_id == phase_id
    ).delete(synchronize_session=False)
    session.query(ProductionEvent).filter(
        ProductionEvent.production_phase_id == phase_id
    ).update({"production_phase_id": None}, synchronize_session=False)
    session.query(ProductionPhase).filter(ProductionPhase.id == phase_id).delete(synchronize_session=False)
    session.commit()


page_setup("Production Run")
init_db()
require_login()
logout_button()

st.title("Production Run")
render_function_action_intro(
    function_text=(
        "This is the master record for a production batch. It stores the recipe and machine the "
        "batch ran on, its Setup and Finalized process settings, the metered material flows, any "
        "production events, and the runtime data. Quality test results and issues are captured on "
        "separate pages but always link back to the run created here. A deliberate trial/change "
        "investigation is its own independent record on the Customer Trials & Samples or "
        "Optimization Trials & Samples page instead - most runs never need that."
    ),
    action_steps=[
        "Open the **Production Runs** tab and create the batch record: pick the product grade, "
        "recipe version, machine and run date. The batch reference is generated automatically.",
        "Open the **Setup** tab and log the planned/configured settings for this run, including "
        "ambient temperature and humidity.",
        "Open the **Runtime Data** tab once the run is finished and log what actually happened - "
        "the same settings as Setup, plus line-speed and rise time. Comparing Setup to Runtime "
        "Data is the plan-vs-actual read.",
        "Open the **Material Metering and Actual Usage** tab and log the metered material flows. Readings "
        "always attach to the Runtime Data (Finalized) snapshot.",
        "Open the **Production Events** tab and log any alarms, interventions or grade changes.",
    ],
    action_note=(
        "Every tab except Production Runs opens with the same run selector - pick the run once, "
        "then step through its tabs in order. Manual entry and CSV/Excel import are both "
        "available throughout."
    ),
)
session = get_session()
user = current_user()
page_usable = can_use_page("production_run", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()
company, _all_companies = company_picker(
    st, session, user["is_platform_owner"], user["company_id"], key="prod_run_company_filter"
)
active_company_id = company.id if company else None
plant_ids = plant_ids_for_company(session, active_company_id)
grade_ids = grade_ids_for_company(session, active_company_id)

grades = apply_scope(session.query(FoamGrade), FoamGrade.id, grade_ids).all()
if not grades:
    st.warning("Add a product grade and recipe version first.")
    st.stop()

# WP7 Phase 2 Closeout Correction, Material Gap 2: the Create/Edit Production
# Run forms below now walk Plant -> Production Method -> Production Unit or
# Cell -> Product Grade, matching the operational hierarchy Charlie's
# architecture correction already established for grade_production_methods()
# (see helpers.py) - Plant and activated Production Methods are loaded once
# here and reused by both forms.
plants = apply_scope(session.query(Plant), Plant.id, plant_ids).order_by(Plant.name).all()
if not plants:
    st.warning("Add a plant first (Plant & Foam Equipment Overview page).")
    st.stop()

runs = (
    apply_scope(session.query(ProductionRun), ProductionRun.plant_id, plant_ids)
    .order_by(ProductionRun.created_at.desc())
    .all()
)

tab_runs, tab_setup, tab_method_settings, tab_runtime, tab_streams, tab_output, tab_cycles, tab_events = st.tabs(
    [
        "📋 Production Runs",
        "🛠️ Planned Settings",
        "⚙️ Method-Aware Process Settings",
        "📊 Actual Run and Cycle Data",
        "🧪 Material Metering and Actual Usage",
        "📦 Production Output and Disposition",
        "🔄 Cycle / Shot Data",
        "🚨 Production Events",
    ]
)

# ---------------------------------------------------------------------------
# Production Runs — overview/edit/delete + create
# ---------------------------------------------------------------------------
with tab_runs:
    tab_create, tab_edit_delete, tab_import = st.tabs(cr11_function_tab_labels("Production Run"))

    with tab_edit_delete:
        if not runs:
            st.info("No production runs yet — use the Create Production Run tab.")
        else:
            run_rows = [
                {
                    "Run": r.id,
                    "Grade": r.foam_grade.grade_name,
                    "Date": r.run_date,
                    "Batch": r.batch_reference,
                    "Block": r.block_reference,
                    "Production Method": r.production_method.name if r.production_method else "—",
                    "Production Unit or Cell": r.machine.name if r.machine else "—",
                    "Operator": r.operator_or_team_reference,
                }
                for r in runs
            ]
            st.caption(f"{len(runs)} production run(s). Click a row to edit (and optionally delete) that run.")
            idx = clickable_table(run_rows, key="runs_overview_table")
            if idx is not None:
                st.session_state["pr_selected_run_id"] = runs[idx].id
            else:
                st.session_state.pop("pr_selected_run_id", None)

            selected_run_id = st.session_state.get("pr_selected_run_id")
            selected_run = next((r for r in runs if r.id == selected_run_id), None)

            if selected_run:
                st.divider()
                st.markdown(f"#### Edit Run #{selected_run.id}")
                st.caption(
                    "WP7 Phase 2 Closeout Correction: Run Context is captured context-first - "
                    "Plant, then Production Method, then Production Unit or Cell, then Product "
                    "Grade - since the Production Unit or Cell you pick is what actually "
                    "determines which Product Grades are producible on it."
                )
                # WP7 Phase 2 Closeout Correction v2 (2026-08-14, Charlie's
                # material completion item 1): Plant / Production Method /
                # Production Unit or Cell live OUTSIDE st.form(...) here,
                # exactly like the Create Run form below - st.form widgets
                # only release their changed values at submit, so an
                # upstream change (e.g. a new Plant) could not refresh the
                # downstream Method/Unit/Grade option sets within the same
                # edit interaction while these lived inside the form. A
                # user could then submit a new Plant together with stale
                # Method/Unit/Grade selections carried over from the
                # previously rendered options. Rendering them as ordinary
                # (non-form) widgets means every change triggers an
                # immediate rerun, so each downstream picker's options are
                # always freshly computed from the current upstream
                # selection before Product Grade (still inside the form,
                # same as Create Run) is ever shown.
                # Step 1: Plant.
                plant_idx = next((i for i, p in enumerate(plants) if p.id == selected_run.plant_id), 0)
                plant = st.selectbox(
                    "Plant *", plants, index=plant_idx, format_func=lambda p: p.name,
                    key=f"edit_run_plant_{selected_run.id}",
                )
                # Step 2: Production Method - only methods activated for
                # this plant (see helpers.activated_methods_for_plant),
                # matching the same gate Machine setup and Product Grade
                # method pickers already use.
                methods = activated_methods_for_plant(session, plant.id) if plant else []
                if plant and not methods:
                    st.caption(
                        "⚠️ This plant has no activated Production Method yet - activate one on "
                        "the Production Methods page first."
                    )
                method_idx = next(
                    (i for i, m in enumerate(methods) if m.id == selected_run.production_method_id), 0,
                )
                method = st.selectbox(
                    "Production Method *", methods, index=method_idx,
                    format_func=lambda m: m.name, key=f"edit_run_method_{selected_run.id}",
                    disabled=not methods,
                ) if methods else None
                # Step 3: Production Unit or Cell - Machines at this plant
                # whose own production_method_id matches the chosen
                # Production Method (helpers.machines_for_plant_and_method).
                # Same NULL-is-active handling as before (a row written
                # via raw SQL can have active=NULL; only an explicit
                # False deactivates).
                candidate_machines = (
                    machines_for_plant_and_method(session, plant.id, method.id) if (plant and method) else []
                )
                active_machines = [m for m in candidate_machines if m.active is not False]
                if plant and method and not active_machines:
                    st.caption(
                        "⚠️ No Production Unit or Cell is assigned to this Plant/Production Method "
                        "combination yet - assign one on the Plant & Foam Equipment Overview page "
                        "first."
                    )
                machine_options = [None] + active_machines
                machine_idx = next(
                    (i for i, m in enumerate(machine_options) if m is not None and m.id == selected_run.machine_id),
                    0,
                )
                machine = st.selectbox(
                    "Production Unit or Cell *", machine_options, index=machine_idx,
                    format_func=lambda m: "— not selected —" if m is None else f"{m.name} ({m.oem or 'OEM —'})",
                    key=f"edit_run_machine_{selected_run.id}",
                )
                with st.form(f"edit_run_form_{selected_run.id}"):
                    # Step 4: Product Grade - filtered to grades actually
                    # assigned to the chosen machine (Machine.foam_grades,
                    # the reverse side of FoamGrade.machines), scoped to this
                    # company's own grades.
                    grade_ids_in_scope = {g.id for g in grades}
                    assignable_grades = (
                        [g for g in machine.foam_grades if g.id in grade_ids_in_scope] if machine else []
                    )
                    if machine and not assignable_grades:
                        st.caption(
                            "⚠️ This Production Unit or Cell has no Product Grade assigned yet - "
                            "assign one on the Product Family & Product Grade page first."
                        )
                    grade_idx = next(
                        (i for i, g in enumerate(assignable_grades) if g.id == selected_run.foam_grade_id), 0,
                    )
                    grade = st.selectbox(
                        "Product grade *", assignable_grades, index=grade_idx,
                        format_func=lambda g: g.grade_name, key=f"edit_run_grade_{selected_run.id}",
                        disabled=not assignable_grades,
                    ) if assignable_grades else None
                    # No version picker here - a production run always uses whichever
                    # recipe version is currently active for the product grade (see
                    # RecipeVersion.is_active in db.py; only one can be active per
                    # grade at a time). Offering a dropdown of every version implied
                    # a choice that doesn't actually exist - the version to use isn't
                    # a decision made on this page, it's whatever Recipes has marked
                    # current. Same fallback as Recipe Optimization's current_version
                    # for legacy data recorded before is_active existed.
                    versions_for_grade = _cached_versions_for_grade(session, grade.id if grade else None)
                    current_version = next(
                        (v for v in versions_for_grade if v.is_active),
                        versions_for_grade[-1] if versions_for_grade else None,
                    )
                    if grade and current_version:
                        st.caption(f"Recipe version in use: **{current_version.version_label}** (current)")
                    elif grade:
                        st.caption("⚠️ This product grade has no recipe version yet - add one on the Recipes page first.")
                    run_date = st.date_input(
                        "Run date", value=selected_run.run_date or dt.date.today(),
                        key=f"edit_run_date_{selected_run.id}",
                    )
                    status_options = [""] + PRODUCTION_RUN_STATUSES
                    status_idx = (
                        status_options.index(selected_run.status)
                        if selected_run.status in status_options else 0
                    )
                    status = st.selectbox(
                        "Run status", status_options, index=status_idx,
                        format_func=lambda s: "— not set —" if s == "" else s,
                        key=f"edit_run_status_{selected_run.id}",
                    )
                    # Both the checkbox and combine_date_time's own widgets
                    # are always rendered, deliberately not nested (one
                    # gating the other's rendering) - inside an st.form,
                    # widgets don't trigger a script rerun until submit, so
                    # a widget whose very presence depended on another
                    # form widget's just-clicked state could never appear
                    # in time for the user to fill it in during the same
                    # submission (see the identical note on the Method-Aware
                    # Process Settings numeric fields above). The checkbox
                    # is the sole source of truth for whether the date/time
                    # below is actually saved; it stays fully independent of
                    # what the date/time picker happens to contain.
                    run_start_default = selected_run.run_start.date() if selected_run.run_start else None
                    run_start_time_default = selected_run.run_start.time() if selected_run.run_start else None
                    record_run_start = st.checkbox(
                        "Record a run start time", value=selected_run.run_start is not None,
                        key=f"edit_run_start_flag_{selected_run.id}",
                        help="Check to save the run start entered below. Leave unchecked to keep the "
                        "run start unset, regardless of what's entered below.",
                    )
                    run_start_value = combine_date_time(
                        "Run start", f"edit_run_start_{selected_run.id}",
                        default_date=run_start_default, default_time=run_start_time_default,
                    )
                    run_start = run_start_value if record_run_start else None
                    run_end_default = selected_run.run_end.date() if selected_run.run_end else None
                    run_end_time_default = selected_run.run_end.time() if selected_run.run_end else None
                    record_run_end = st.checkbox(
                        "Record a run end time", value=selected_run.run_end is not None,
                        key=f"edit_run_end_flag_{selected_run.id}",
                        help="Check to save the run end entered below. Leave unchecked to keep the "
                        "run end unset, regardless of what's entered below.",
                    )
                    run_end_value = combine_date_time(
                        "Run end", f"edit_run_end_{selected_run.id}",
                        default_date=run_end_default, default_time=run_end_time_default,
                    )
                    run_end = run_end_value if record_run_end else None
                    order_item_reference = st.text_input(
                        "Customer order / order item reference",
                        value=selected_run.order_item_reference or "",
                        key=f"edit_run_order_ref_{selected_run.id}",
                    )
                    batch_reference = st.text_input(
                        "Batch reference", value=selected_run.batch_reference or "",
                        key=f"edit_run_batch_{selected_run.id}",
                        help="Auto-generated when the run was created (B-DDMMYY-NN). Only change this "
                        "to correct a genuine mistake.",
                    )
                    block_reference = st.text_input(
                        "Block reference", value=selected_run.block_reference or "",
                        key=f"edit_run_block_{selected_run.id}",
                    )
                    operator = st.text_input(
                        "Operator / team reference", value=selected_run.operator_or_team_reference or "",
                        key=f"edit_run_operator_{selected_run.id}",
                    )
                    notes = st.text_area(
                        "Notes", value=selected_run.notes or "", key=f"edit_run_notes_{selected_run.id}"
                    )
                    save = st.form_submit_button("Save changes", disabled=not page_usable)
                    if save and page_usable:
                        if not grade:
                            st.error("Select a Production Unit or Cell that has a Product Grade assigned first.")
                        elif not current_version:
                            st.error("This product grade has no recipe version yet — add one on the Recipes page first.")
                        else:
                            selected_run.foam_grade_id = grade.id
                            selected_run.plant_id = plant.id
                            selected_run.recipe_version_id = current_version.id
                            selected_run.machine_id = machine.id if machine else None
                            # Production Method Hierarchy architecture change
                            # (2026-08-09): this snapshot is deliberately
                            # re-derived on every edit (not left as whatever
                            # it was originally set to) - editing a run's own
                            # Machine is a genuine correction to that run,
                            # not the "Machine master reclassified later"
                            # case the immutability rule protects against
                            # (see db.py's ProductionRun.production_method_id
                            # docstring).
                            selected_run.production_method_id = method.id if method else None
                            selected_run.run_date = run_date
                            selected_run.status = status or None
                            selected_run.run_start = run_start
                            selected_run.run_end = run_end
                            selected_run.order_item_reference = order_item_reference or None
                            selected_run.batch_reference = batch_reference
                            selected_run.block_reference = block_reference
                            selected_run.operator_or_team_reference = operator
                            selected_run.notes = notes
                            session.commit()
                            st.success("Production run updated.")
                            st.rerun()

                counts = production_run_dependency_counts(session, selected_run.id)
                total_related = sum(counts.values())
                if total_related:
                    detail = ", ".join(f"{v} {k}" for k, v in counts.items() if v)
                    warning = f"Deleting this run will also permanently delete {total_related} related record(s): {detail}."
                else:
                    warning = "This run has no related records — deleting it is safe."

                def _do_delete_run(_session=session, _run_id=selected_run.id):
                    delete_production_run_cascade(_session, _run_id)
                    _session.commit()
                    clear_scope_cache()
                    st.session_state.pop("pr_selected_run_id", None)

                if page_usable:
                    delete_with_confirm(
                        f"Run #{selected_run.id}", _do_delete_run, key_prefix=f"run_{selected_run.id}",
                        extra_warning=warning,
                    )
                else:
                    st.caption("View-only access - deleting is restricted for your role.")

                if st.button("Clear selection", key="clear_run_selection"):
                    st.session_state.pop("pr_selected_run_id", None)
                    st.rerun()

    with tab_create:
        # run_date lives outside the form so the batch-reference preview
        # below updates live as it's changed, before the operator commits
        # to saving - forms otherwise only release widget values on submit.
        run_date = st.date_input("Run date", value=dt.date.today(), key="create_run_date")
        batch_reference = _generate_batch_reference(session, run_date, plant_ids)
        st.caption(
            f"Batch reference (auto-generated, prevents typos/duplicates): **{batch_reference}**"
        )
        st.caption(
            "WP7 Phase 2 Closeout Correction: pick Plant, then Production Method, then Production "
            "Unit or Cell, then Product Grade - the Production Unit or Cell you select determines "
            "which Product Grades are producible on it."
        )
        # Steps 1-3 (Plant / Production Method / Production Unit or Cell)
        # live outside the form too, since Step 4's Product Grade choices
        # depend on Step 3's Production Unit or Cell - Streamlit forms only
        # release values on submit, so a dependent dropdown inside the same
        # form can't react to an earlier one until after the form is
        # already submitted. Same live-preview pattern as run_date/
        # batch_reference above.
        plant = st.selectbox(
            "Plant *", plants, format_func=lambda p: p.name, key="create_run_plant",
        )
        methods = activated_methods_for_plant(session, plant.id) if plant else []
        if plant and not methods:
            st.caption(
                "⚠️ This plant has no activated Production Method yet - activate one on the "
                "Production Methods page first."
            )
        method = st.selectbox(
            "Production Method *", methods, format_func=lambda m: m.name, key="create_run_method",
            disabled=not methods,
        ) if methods else None
        candidate_machines = (
            machines_for_plant_and_method(session, plant.id, method.id) if (plant and method) else []
        )
        active_machines = [m for m in candidate_machines if m.active is not False]
        if plant and method and not active_machines:
            st.caption(
                "⚠️ No Production Unit or Cell is assigned to this Plant/Production Method "
                "combination yet - assign one on the Plant & Foam Equipment Overview page first."
            )
        machine = st.selectbox(
            "Production Unit or Cell *", [None] + active_machines,
            format_func=lambda m: "— not selected —" if m is None else f"{m.name} ({m.oem or 'OEM —'})",
            key="create_run_machine",
        )
        grade_ids_in_scope = {g.id for g in grades}
        assignable_grades = (
            [g for g in machine.foam_grades if g.id in grade_ids_in_scope] if machine else []
        )
        if machine and not assignable_grades:
            st.caption(
                "⚠️ This Production Unit or Cell has no Product Grade assigned yet - assign one on "
                "the Product Family & Product Grade page first."
            )

        with st.form("add_run"):
            grade = st.selectbox(
                "Product grade *" + ("" if assignable_grades else " (none assignable yet)"),
                assignable_grades, format_func=lambda g: g.grade_name, disabled=not assignable_grades,
            ) if assignable_grades else None
            # No version picker - see the same note in the Edit Run form above.
            # A new run always uses whichever recipe version is currently active
            # for the chosen product grade.
            versions_for_grade = _cached_versions_for_grade(session, grade.id if grade else None)
            current_version = next(
                (v for v in versions_for_grade if v.is_active),
                versions_for_grade[-1] if versions_for_grade else None,
            )
            if grade and current_version:
                st.caption(f"Recipe version in use: **{current_version.version_label}** (current)")
            elif grade:
                st.caption("⚠️ This product grade has no recipe version yet - add one on the Recipes page first.")
            status_options = [""] + PRODUCTION_RUN_STATUSES
            status = st.selectbox(
                "Run status", status_options, format_func=lambda s: "— not set —" if s == "" else s,
                key="create_run_status",
            )
            # Both widgets always render (not one gating the other's
            # rendering) - see the identical note on the Edit Run form and
            # the Method-Aware Process Settings numeric fields.
            record_run_start = st.checkbox(
                "Record a run start time", value=False, key="create_run_start_flag",
                help="Check to save the run start entered below.",
            )
            run_start_value = combine_date_time("Run start", "create_run_start", default_date=run_date)
            run_start = run_start_value if record_run_start else None
            record_run_end = st.checkbox(
                "Record a run end time", value=False, key="create_run_end_flag",
                help="Check to save the run end entered below.",
            )
            run_end_value = combine_date_time("Run end", "create_run_end", default_date=run_date)
            run_end = run_end_value if record_run_end else None
            order_item_reference = st.text_input("Customer order / order item reference")
            block_reference = st.text_input("Block reference")
            operator = st.text_input("Operator / team reference")
            notes = st.text_area("Notes")

            submitted = st.form_submit_button("Save production run", disabled=not page_usable)
            if submitted and page_usable:
                if not grade:
                    st.error("Select a Production Unit or Cell that has a Product Grade assigned first.")
                elif not current_version:
                    st.error("This product grade has no recipe version yet — add one on the Recipes page first.")
                else:
                    run = ProductionRun(
                        plant_id=plant.id,
                        foam_grade_id=grade.id,
                        recipe_version_id=current_version.id,
                        run_date=run_date,
                        status=status or None,
                        run_start=run_start,
                        run_end=run_end,
                        order_item_reference=order_item_reference or None,
                        batch_reference=_generate_batch_reference(session, run_date, plant_ids),
                        block_reference=block_reference,
                        machine_id=machine.id if machine else None,
                        production_method_id=method.id if method else None,
                        operator_or_team_reference=operator,
                        notes=notes,
                    )
                    session.add(run)
                    session.commit()
                    clear_scope_cache()
                    st.session_state["pr_selected_run_id"] = run.id
                    st.success(f"Production run created. Batch reference: {run.batch_reference}.")
                    st.rerun()

    with tab_import:
        show_pending_banner("run_import_msg")
        st.caption(
            "recipe_version_id must belong to the foam_grade_id on the same row. plant_id and machine "
            "assignment are derived/validated from the product grade automatically."
        )
        run_df, run_filename = csv_excel_uploader(RUN_REQUIRED_COLUMNS, RUN_OPTIONAL_COLUMNS, key="run_upload")
        if run_df is not None:
            grades_by_id = {g.id: g for g in grades}
            # Scoped to this company's grades (not an unfiltered, every-
            # company RecipeVersion.all() as before the 2026-08-05
            # performance audit) - cheaper, and no reason to pull other
            # companies' recipe versions into a lookup dict just to
            # validate this CSV upload.
            versions_by_id = {
                v.id: v for v in apply_scope(session.query(RecipeVersion), RecipeVersion.foam_grade_id, grade_ids).all()
            }
            # Scoped to this company's plants too - otherwise a CSV row could
            # reference a machine_id belonging to a different company (the
            # foam_grade/recipe_version cross-check above doesn't catch this,
            # since machine_id isn't derived from either of those).
            machines_by_id = {
                m.id: m for m in apply_scope(session.query(Machine), Machine.plant_id, plant_ids).all()
            }
            good_rows, bad_rows = [], []
            for _, row in run_df.iterrows():
                try:
                    grade_row = grades_by_id.get(row.get("foam_grade_id"))
                    version_row = versions_by_id.get(row.get("recipe_version_id"))
                    machine_val = row.get("machine_id")
                    machine_ok = pd.isna(machine_val) or int(machine_val) in machines_by_id
                    ok = bool(grade_row and version_row and version_row.foam_grade_id == grade_row.id and machine_ok)
                except (TypeError, ValueError):
                    ok = False
                if ok:
                    good_rows.append(row)
                else:
                    bad_rows.append(row)

            st.write(f"Rows ready to import: **{len(good_rows)}** | Rows flagged/rejected: **{len(bad_rows)}**")
            if bad_rows:
                st.warning(
                    "Flagged rows reference an unknown foam_grade_id/recipe_version_id, a recipe version "
                    "that doesn't belong to that product grade, or an unknown machine_id."
                )
                render_data_table(pd.DataFrame(bad_rows), max_height="300px")

            if good_rows and st.button("Confirm import", key="confirm_run_import", disabled=not page_usable):
                # Rows with an explicit batch_reference are deduped against
                # what's already in the database, so re-clicking Confirm
                # import (e.g. because the previous success message wasn't
                # visibly persistent) can't silently insert the same batch
                # twice. Rows with a blank batch_reference always get a
                # fresh auto-generated one, so they need no such check.
                existing_batch_refs = {
                    r.batch_reference
                    for r in apply_scope(session.query(ProductionRun), ProductionRun.plant_id, plant_ids).all()
                    if r.batch_reference
                }
                import_rows, dup_rows = [], []
                for row in good_rows:
                    br = str(row.get("batch_reference", "") or "").strip()
                    if br and br in existing_batch_refs:
                        dup_rows.append(row)
                    else:
                        import_rows.append(row)
                        if br:
                            existing_batch_refs.add(br)

                # Rows that already carry a batch_reference (e.g. migrating a
                # historical log) keep it as-is; blank ones get auto-generated,
                # tracking the running sequence per day in-memory so multiple
                # blank rows for the same date in one file don't collide.
                seq_by_prefix = {}
                for row in import_rows:
                    grade_row = grades_by_id[row["foam_grade_id"]]
                    machine_val = row.get("machine_id")
                    run_date_val = pd.to_datetime(row.get("run_date"), errors="coerce")
                    final_run_date = run_date_val.date() if not pd.isna(run_date_val) else dt.date.today()
                    batch_val = str(row.get("batch_reference", "") or "").strip()
                    if not batch_val:
                        prefix = f"B-{final_run_date:%d%m%y}"
                        if prefix not in seq_by_prefix:
                            seq_by_prefix[prefix] = _max_batch_seq_for_prefix(session, prefix, plant_ids)
                        seq_by_prefix[prefix] += 1
                        batch_val = f"{prefix}-{seq_by_prefix[prefix]:02d}"
                    # Production Method architecture change (2026-08-09,
                    # flat-model redesign 2026-08-10): derive the
                    # snapshot the same way manual entry does - from the
                    # imported machine's own production_method, not the
                    # product grade's, since the machine is the actual
                    # source of method context (a grade can only be
                    # assigned to machines under one method per
                    # Charlie's consistency rule, so either source
                    # agrees). Flat model: direct attribute, no
                    # hierarchy resolution needed.
                    imported_machine = (
                        session.get(Machine, int(machine_val)) if not pd.isna(machine_val) else None
                    )
                    imported_method = imported_machine.production_method if imported_machine else None
                    session.add(
                        ProductionRun(
                            plant_id=grade_row.product_family.plant_id,
                            foam_grade_id=grade_row.id,
                            recipe_version_id=int(row["recipe_version_id"]),
                            run_date=final_run_date,
                            batch_reference=batch_val,
                            block_reference=str(row.get("block_reference", "") or ""),
                            machine_id=imported_machine.id if imported_machine else None,
                            production_method_id=imported_method.id if imported_method else None,
                            operator_or_team_reference=str(row.get("operator_or_team_reference", "") or ""),
                            notes=str(row.get("notes", "") or ""),
                        )
                    )
                session.commit()
                clear_scope_cache()
                msg = f"Imported {len(import_rows)} production run(s) from {run_filename}."
                if dup_rows:
                    msg += f" Skipped {len(dup_rows)} row(s) whose batch_reference already exists (likely a repeat click)."
                set_pending_banner("run_import_msg", msg)
                st.rerun()

# ---------------------------------------------------------------------------
# Setup (planned/configured settings, entered before the run starts)
# ---------------------------------------------------------------------------
with tab_setup:
    st.caption(
        "The Setup window for this run (start/end time and notes), entered before it starts. "
        "Planned and Actual process settings themselves are captured on the Method-Aware Process "
        "Settings tab."
    )

    if not runs:
        st.info("Create a production run first (Production Runs tab).")
    else:
        run = _run_selector(runs, key="setup_tab_run_select")
        st.caption(f"Showing Setup data for **{_run_label(run)}**")

        # CR-11: wording/order aligned via cr11_function_tab_labels(). The
        # page-specific 4th tab ("Tool Geometry and Fill Configuration",
        # the fall-plate section-position sub-workflow) was removed under
        # WP7 Phase 0 - see the module docstring.
        tab_create, tab_edit_delete, tab_import = st.tabs(
            cr11_function_tab_labels("Setup Data", "Setup Data")
        )

        setup_phase = (
            session.query(ProductionPhase)
            .filter(ProductionPhase.production_run_id == run.id, ProductionPhase.phase_name == "Setup")
            .first()
        )

        with tab_edit_delete:
            if not setup_phase:
                st.info("No Setup data recorded yet for this run — use the Create tab.")
            else:
                st.markdown("##### Edit Setup data")
                with st.form(f"edit_setup_form_{setup_phase.id}"):
                    phase_start = combine_date_time(
                        "Setup start", f"edit_setup_start_{setup_phase.id}",
                        default_date=setup_phase.phase_start.date() if setup_phase.phase_start else None,
                        default_time=setup_phase.phase_start.time() if setup_phase.phase_start else None,
                    )
                    phase_end = combine_date_time(
                        "Setup end", f"edit_setup_end_{setup_phase.id}",
                        default_date=setup_phase.phase_end.date() if setup_phase.phase_end else None,
                        default_time=setup_phase.phase_end.time() if setup_phase.phase_end else None,
                    )

                    # WP7 Phase 5 (Legacy Retirement): the machine-setting
                    # widgets formerly here (mixer rpm, conveyor speed, air
                    # injection rate, air pressure, tunnel width) are
                    # retired from active capture - ProductionPhase is now
                    # ARCHIVE READ-ONLY for those fields (see the WP7 Phase
                    # 5 JC Pre-Coding Engineering Challenge Response,
                    # Section 4). Planned/Actual process settings are
                    # captured on the Method-Aware Process Settings tab
                    # instead, which reads/writes the EAV schema.
                    notes = st.text_area(
                        "Notes", value=setup_phase.notes or "", key=f"edit_setup_notes_{setup_phase.id}"
                    )

                    save = st.form_submit_button("Save changes", disabled=not page_usable)
                    if save and page_usable:
                        if phase_end < phase_start:
                            st.error("Setup end must not be before Setup start.")
                        else:
                            setup_phase.phase_start = phase_start
                            setup_phase.phase_end = phase_end
                            setup_phase.notes = notes
                            session.commit()
                            st.success("Setup data updated.")
                            st.rerun()

                def _do_delete_setup(_session=session, _phase=setup_phase):
                    _delete_phase_cascade(_session, _phase)

                if page_usable:
                    delete_with_confirm(
                        f"Setup data (Run #{run.id})", _do_delete_setup, key_prefix=f"setup_{setup_phase.id}",
                        extra_warning=(
                            "Deleting this also deletes its fall-plate section positions, and unlinks (does "
                            "not delete) any production events that referenced it."
                        ),
                    )
                else:
                    st.caption("View-only access - deleting is restricted for your role.")

        with tab_create:
            if setup_phase:
                st.caption("Setup data already recorded for this run — edit it in the Overview & Edit tab.")
            else:
                with st.form(f"add_setup_{run.id}"):
                    # Default the date to the run's own run_date rather than
                    # today - setup happens on the day the batch is scheduled,
                    # and setup start/end are normally the same day (hours
                    # apart, not days), so both fields default to that one
                    # date. Still fully editable, including across a
                    # midnight-spanning setup if that genuinely happens.
                    phase_start = combine_date_time(
                        "Setup start", f"new_setup_start_{run.id}", default_date=run.run_date
                    )
                    phase_end = combine_date_time(
                        "Setup end", f"new_setup_end_{run.id}", default_date=run.run_date
                    )

                    # WP7 Phase 5 (Legacy Retirement): see the matching
                    # comment in the Edit form above - machine-setting
                    # fields are no longer captured here.
                    notes = st.text_area("Notes", key=f"new_setup_notes_{run.id}")

                    submitted = st.form_submit_button("Save Setup data", disabled=not page_usable)
                    if submitted and page_usable:
                        if phase_end < phase_start:
                            st.error("Setup end must not be before Setup start.")
                        else:
                            session.add(
                                ProductionPhase(
                                    production_run_id=run.id,
                                    phase_name="Setup",
                                    phase_start=phase_start,
                                    phase_end=phase_end,
                                    notes=notes,
                                    source_file_reference="manual entry",
                                )
                            )
                            session.commit()
                            st.success("Setup data saved.")
                            st.rerun()

        with tab_import:
            show_pending_banner("setup_import_msg")
            st.caption(
                "Required column: `production_run_id`. Optional columns: " + ", ".join(SETUP_OPTIONAL_COLUMNS)
                + ". One Setup row per run - a run that already has one is skipped as a duplicate."
            )
            uploaded = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx"], key="setup_upload")
            if uploaded and upload_within_size_limit(uploaded):
                try:
                    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
                except Exception as exc:
                    st.error(f"Could not read file: {exc}")
                    df = None

                if df is not None and import_within_row_limit(df):
                    missing_cols = [c for c in SETUP_REQUIRED_COLUMNS if c not in df.columns]
                    if missing_cols:
                        st.error(f"File is missing required column(s): {', '.join(missing_cols)}. Import rejected.")
                    else:
                        valid_run_ids = {r.id for r in runs}
                        good_rows, bad_rows = [], []
                        for _, row in df.iterrows():
                            if row.get("production_run_id") in valid_run_ids:
                                good_rows.append(row)
                            else:
                                bad_rows.append(row)

                        st.write(f"Rows ready to import: **{len(good_rows)}** | Rows flagged/rejected: **{len(bad_rows)}**")
                        if bad_rows:
                            st.warning("Flagged rows reference a production_run_id that does not exist and will be skipped.")
                            render_data_table(pd.DataFrame(bad_rows), max_height="300px")

                        if good_rows and st.button("Confirm import", key="confirm_setup_import", disabled=not page_usable):
                            # Dedupe on production_run_id: only one Setup row per run.
                            existing_keys = {
                                p.production_run_id
                                for p in session.query(ProductionPhase).filter(ProductionPhase.phase_name == "Setup").all()
                            }
                            accept, dup = dedupe_import_rows(
                                good_rows, existing_keys,
                                key_func=lambda row: int(row["production_run_id"]),
                            )
                            for row in accept:
                                # WP7 Phase 5 (Legacy Retirement): legacy
                                # machine-setting columns are no longer
                                # accepted on import - see the matching
                                # comment on the Edit form above.
                                session.add(
                                    ProductionPhase(
                                        production_run_id=int(row["production_run_id"]),
                                        phase_name="Setup",
                                        phase_start=parse_dt(row.get("phase_start")),
                                        phase_end=parse_dt(row.get("phase_end")),
                                        notes=str(row.get("notes", "") or ""),
                                        source_file_reference=uploaded.name,
                                    )
                                )
                            session.commit()
                            msg = f"Imported {len(accept)} Setup row(s) from {uploaded.name}."
                            if dup:
                                msg += f" Skipped {len(dup)} row(s) whose run already has Setup data (likely a repeat click)."
                            set_pending_banner("setup_import_msg", msg)
                            st.rerun()

# ---------------------------------------------------------------------------
# WP7 Phase 2 (2026-08-14): Method-Aware Process Settings — governing doc
# section 4 sections C/D (Planned/Actual Process Data, "conditional by
# Method/Unit"). Driven entirely by analytics.eligible_process_settings(),
# which resolves the WP7 Phase 1 ProcessSettingDefinition/
# ProcessSettingApplicability schema with Machine>Method>Global precedence
# (see Charlie's WP7 Phase 1 Design Review and Architecture Decision,
# section 3.1/4). Originally additive alongside the legacy Setup/Runtime
# Data tabs' fixed mixer_rpm/conveyor_speed/etc. fields ("temporary
# compatibility adapters" per decision doc section 7); those fields were
# retired from active capture under WP7 Phase 5 (Legacy Retirement,
# 2026-08-15 - see the JC Pre-Coding Engineering Challenge Response) once
# this tab became the sole active capture point for process settings.
#
# Note: as of Phase 2, there is no approved, evidence-based
# ProcessSettingDefinition/ProcessSettingApplicability catalogue seeded in
# production yet - Charlie's decision doc section 5 explicitly deferred
# things like the mixer-rpm-to-Method mapping to a later evidence-based
# migration, and that open item is still unresolved. Until real
# definitions/applicabilities exist for a run's Production Method/Unit,
# this tab correctly shows "no applicable settings yet" rather than
# inventing any - see the WP7 Phase 2 closeout package for the explicit
# flag on this open item.
# ---------------------------------------------------------------------------
with tab_method_settings:
    st.caption(
        "Only the process settings applicable to this run's Production Method and "
        "Production Unit or Cell are shown here (Machine-specific overrides Method-specific "
        "overrides Global)."
    )

    if not runs:
        st.info("Create a production run first (Production Runs tab).")
    else:
        run = _run_selector(runs, key="method_settings_tab_run_select")
        st.caption(
            f"Showing method-aware process settings for **{_run_label(run)}** — "
            f"Production Method: **{run.production_method.name if run.production_method else '—'}** · "
            f"Production Unit or Cell: **{run.machine.name if run.machine else '—'}**"
        )

        if not run.production_method_id:
            st.warning(
                "This run has no Production Method resolved (its Production Unit or Cell isn't "
                "assigned one). Set the Production Unit or Cell on the Production Runs tab first."
            )
        else:
            eligible = analytics.eligible_process_settings(
                session, run.production_method_id, machine_id=run.machine_id
            )
            # WP7 Phase 3 correction (2026-08-14, Charlie's closeout review,
            # findings #1/#2): this tab is for controllable Process Setting
            # levers only. Environment/Outcome definitions are measured
            # observations, not planned/actual machine settings, and must
            # never render here even if analytics.eligible_process_settings()
            # returns them as eligible by Machine>Method>Global precedence.
            # (Those categories are actual-only capture and belong on the
            # Runtime/Setup observation tabs; see legacy_migration.py's
            # ensure_environment_outcome_definitions() for the other half of
            # this fix.)
            eligible = [
                (definition, applicability)
                for definition, applicability in eligible
                if definition.parameter_category not in ("Environment", "Outcome")
            ]
            if not eligible:
                st.info(
                    "No process settings are configured as applicable to this run's Production "
                    "Method/Unit yet. This is expected until an approved, evidence-based process "
                    "setting definition/applicability catalogue exists for this Method/Unit — see "
                    "the WP7 Phase 1 design decision (Phase 1 Production Seeding Rule)."
                )
            else:
                existing_by_key = {
                    (pv.setting_definition_id, pv.snapshot_type): pv
                    for pv in session.query(ProcessParameterValue)
                    .filter(ProcessParameterValue.production_run_id == run.id)
                    .all()
                }

                with st.form(f"method_settings_form_{run.id}"):
                    field_plan = []  # (definition, applicability, snapshot_type, widget_value)
                    for definition, applicability in eligible:
                        st.markdown(
                            f"**{definition.name}**"
                            + (f" ({definition.unit.symbol})" if definition.unit else "")
                            + f" — _{definition.parameter_category or 'Uncategorized'}_"
                        )
                        cols = st.columns(2)
                        snapshot_cols = []
                        if applicability.applicable_to_planned:
                            snapshot_cols.append(("Planned", cols[0]))
                        if applicability.applicable_to_actual:
                            snapshot_cols.append(("Actual", cols[1]))
                        for snapshot_type, col in snapshot_cols:
                            existing = existing_by_key.get((definition.id, snapshot_type))
                            widget_key = f"pps_{definition.id}_{snapshot_type}_{run.id}"
                            record_flag = True  # only meaningful for Float/Integer; overwritten below
                            if definition.data_type == "Boolean":
                                options = ["", "Yes", "No"]
                                current = (
                                    "Yes" if existing and existing.boolean_value is True
                                    else "No" if existing and existing.boolean_value is False
                                    else ""
                                )
                                value = col.selectbox(
                                    snapshot_type, options, index=options.index(current), key=widget_key
                                )
                            elif definition.data_type == "String":
                                value = col.text_input(
                                    snapshot_type, value=(existing.text_value if existing else "") or "",
                                    key=widget_key,
                                )
                            else:
                                step = 1.0 if definition.data_type == "Integer" else 0.01
                                has_existing_value = existing is not None and existing.numeric_value is not None
                                # Deliberately NOT wired to number_input's
                                # disabled= parameter: widgets inside an
                                # st.form don't trigger a script rerun until
                                # the form is submitted, so a disabled state
                                # driven by this checkbox could never update
                                # live in the same interaction - the user
                                # would check the box and see the number
                                # field still greyed out until after they'd
                                # already submitted. Both widgets are simply
                                # independent and always editable; the
                                # checkbox is the sole source of truth for
                                # "is this an explicitly recorded value" on
                                # save, decoupled entirely from whatever the
                                # number field happens to contain.
                                record_flag = col.checkbox(
                                    f"Record a {snapshot_type.lower()} value",
                                    value=has_existing_value,
                                    key=f"{widget_key}_recorded",
                                    help=(
                                        "Check this to save the number entered below, including zero - "
                                        "zero is a distinct, valid recorded value and is never treated "
                                        "as blank. Leave unchecked to keep this value unset/blank, "
                                        "regardless of what's typed below."
                                    ),
                                )
                                value = col.number_input(
                                    snapshot_type, step=step,
                                    value=float(existing.numeric_value) if has_existing_value else 0.0,
                                    key=widget_key,
                                )
                            field_plan.append((definition, applicability, snapshot_type, value, existing, record_flag))

                    submitted = st.form_submit_button("Save process settings", disabled=not page_usable)
                    if submitted and page_usable:
                        now = dt.datetime.utcnow()
                        for definition, applicability, snapshot_type, value, existing, record_flag in field_plan:
                            is_blank = (
                                (definition.data_type == "Boolean" and value == "")
                                or (definition.data_type == "String" and not value.strip())
                                or (definition.data_type not in ("Boolean", "String") and not record_flag)
                            )
                            if is_blank:
                                if existing:
                                    session.delete(existing)
                                continue
                            row = existing or ProcessParameterValue(
                                setting_definition_id=definition.id,
                                production_run_id=run.id,
                                snapshot_type=snapshot_type,
                            )
                            if definition.data_type == "Boolean":
                                row.boolean_value = value == "Yes"
                                row.numeric_value = None
                                row.text_value = None
                            elif definition.data_type == "String":
                                row.text_value = value.strip()
                                row.numeric_value = None
                                row.boolean_value = None
                            else:
                                row.numeric_value = value
                                row.text_value = None
                                row.boolean_value = None
                            row.unit = definition.unit.symbol if definition.unit else None
                            row.source = "Manual entry"
                            row.captured_at = now
                            if not existing:
                                session.add(row)
                        session.commit()
                        st.success("Process settings saved.")
                        st.rerun()

                st.markdown("##### Currently captured values")
                current_values = (
                    session.query(ProcessParameterValue)
                    .filter(ProcessParameterValue.production_run_id == run.id)
                    .all()
                )
                if not current_values:
                    st.caption("No values captured yet for this run.")
                else:
                    by_def = {}
                    for pv in current_values:
                        by_def.setdefault(pv.setting_definition_id, {})[pv.snapshot_type] = pv

                    def _display_value(pv):
                        if pv is None:
                            return "—"
                        if pv.numeric_value is not None:
                            return pv.numeric_value
                        if pv.text_value is not None:
                            return pv.text_value
                        if pv.boolean_value is not None:
                            return "Yes" if pv.boolean_value else "No"
                        return "—"

                    value_rows = [
                        {
                            "Setting": definition.name,
                            "Category": definition.parameter_category or "—",
                            "Planned": _display_value(snapshots.get("Planned")),
                            "Actual": _display_value(snapshots.get("Actual")),
                            "Unit": definition.unit.symbol if definition.unit else "—",
                        }
                        for definition, applicability in eligible
                        for snapshots in [by_def.get(definition.id, {})]
                        if snapshots
                    ]
                    if value_rows:
                        render_data_table(pd.DataFrame(value_rows), max_height="300px")
                    else:
                        st.caption("No values captured yet for this run.")

# ---------------------------------------------------------------------------
# Component stream readings
# ---------------------------------------------------------------------------
with tab_streams:
    st.caption(
        "Per raw-material stream (polyol, isocyanate, water/blowing agent, catalyst, etc.), the flow, "
        "pressure, and temperature. WP7 Phase 1/2 (2026-08-13/14, per Charlie's decoupling decision, "
        "design doc section 3.4): these readings now attach directly to the production run and no "
        "longer require the Runtime Data (Finalized) snapshot to exist first - if a Finalized phase "
        "does exist for the run, new readings are still linked to it too for continuity with the "
        "legacy Setup/Runtime Data comparison."
    )

    if not runs:
        st.info("Create a production run first (Production Runs tab).")
    else:
        run = _run_selector(runs, key="stream_tab_run_select")
        phases_for_run = (
            session.query(ProductionPhase).filter(ProductionPhase.production_run_id == run.id).all()
        )
        finalized_phase = next((p for p in phases_for_run if p.phase_name == "Finalized"), None)
        if finalized_phase:
            st.caption(
                f"Showing stream readings for **{_run_label(run)}** — Finalized phase "
                f"({finalized_phase.phase_start})"
            )
        else:
            st.caption(
                f"Showing stream readings for **{_run_label(run)}**. No Runtime Data (Finalized) "
                "snapshot exists for this run yet - readings can still be recorded, linked "
                "directly to the run."
            )
        # CR-11: wording/order aligned via cr11_function_tab_labels().
        tab_create, tab_edit_delete, tab_import = st.tabs(cr11_function_tab_labels("Stream Reading"))

        # WP7 Phase 1/2: a reading may be linked via production_run_id directly
        # (new, Phase-2-era rows) and/or via its ProductionPhase (legacy rows,
        # and any run that still also has a Finalized phase) - union both so
        # nothing is missed either way.
        streams_for_run = (
            session.query(ComponentStreamReading)
            .outerjoin(ProductionPhase, ComponentStreamReading.production_phase_id == ProductionPhase.id)
            .filter(
                (ComponentStreamReading.production_run_id == run.id)
                | (ProductionPhase.production_run_id == run.id)
            )
            .order_by(ComponentStreamReading.id.desc())
            .all()
        )
        recipe_components = (
            session.query(RecipeComponent)
            .filter(RecipeComponent.recipe_version_id == run.recipe_version_id)
            .all()
        )

        with tab_edit_delete:
            if not streams_for_run:
                st.info("No stream readings recorded yet for this run — use the Create tab.")
            else:
                stream_rows = [
                    {
                        "Phase": r.phase.phase_name if r.phase else "—",
                        "Stream": r.stream_name,
                        "Pump speed": r.pump_speed,
                        "Flow": r.flow,
                        "Unit": r.flow_unit,
                        "Total delivered": r.flow_total_qty,
                        "Pressure (bar)": r.pressure_bar,
                        "Temp (°C)": r.temperature_c,
                        "Calibration": r.calibration_status or "—",
                    }
                    for r in streams_for_run
                ]
                idx = clickable_table(stream_rows, key=f"streams_table_{run.id}")
                if idx is not None:
                    st.session_state["pr_selected_stream_id"] = streams_for_run[idx].id
                else:
                    st.session_state.pop("pr_selected_stream_id", None)

                sel_stream = next(
                    (r for r in streams_for_run if r.id == st.session_state.get("pr_selected_stream_id")), None
                )
                if sel_stream:
                    st.markdown(f"##### Edit stream reading — {sel_stream.stream_name}")
                    with st.form(f"edit_stream_form_{sel_stream.id}"):
                        stream_name = st.text_input(
                            "Stream / raw material name *", value=sel_stream.stream_name,
                            key=f"edit_stream_name_{sel_stream.id}",
                        )
                        flow_unit_options = ["kg/min", "L/min"]
                        flow_unit_idx = (
                            flow_unit_options.index(sel_stream.flow_unit)
                            if sel_stream.flow_unit in flow_unit_options else 0
                        )
                        flow_unit = st.selectbox(
                            "Flow unit", flow_unit_options, index=flow_unit_idx,
                            key=f"edit_stream_flow_unit_{sel_stream.id}",
                        )
                        c1, c2, c3, c4 = st.columns(4)
                        flow = c1.number_input(
                            "Flow", min_value=0.0, step=0.1, value=float(sel_stream.flow or 0.0),
                            key=f"edit_stream_flow_{sel_stream.id}",
                        )
                        pump_speed = c2.number_input(
                            "Pump speed", min_value=0.0, step=0.1, value=float(sel_stream.pump_speed or 0.0),
                            key=f"edit_stream_pump_{sel_stream.id}",
                            help="Metering pump setting for this stream (RPM/Hz/% depending on OEM) — the "
                            "control input, distinct from the measured Flow.",
                        )
                        pressure_bar = c3.number_input(
                            "Pressure (bar)", min_value=0.0, step=0.1, value=float(sel_stream.pressure_bar or 0.0),
                            key=f"edit_stream_pressure_{sel_stream.id}",
                        )
                        temperature_c = c4.number_input(
                            "Temperature (°C)", step=0.1, value=float(sel_stream.temperature_c or 0.0),
                            key=f"edit_stream_temp_{sel_stream.id}",
                        )
                        flow_total_qty = st.number_input(
                            "Total delivered this phase (same base unit as flow unit, kg or L)",
                            min_value=0.0, step=0.1, value=float(sel_stream.flow_total_qty or 0.0),
                            key=f"edit_stream_total_{sel_stream.id}",
                        )
                        c5, c6 = st.columns(2)
                        calibration_options = ["", "Valid", "Expired", "Failed", "Not Verified"]
                        calibration_idx = (
                            calibration_options.index(sel_stream.calibration_status)
                            if sel_stream.calibration_status in calibration_options else 0
                        )
                        calibration_status = c5.selectbox(
                            "Instrument calibration status", calibration_options, index=calibration_idx,
                            key=f"edit_stream_calib_status_{sel_stream.id}",
                        )
                        calibration_note = c6.text_input(
                            "Calibration note (e.g. cal. due date, certificate ref.)",
                            value=sel_stream.calibration_note or "", key=f"edit_stream_calib_note_{sel_stream.id}",
                        )
                        notes = st.text_area(
                            "Notes", value=sel_stream.notes or "", key=f"edit_stream_notes_{sel_stream.id}"
                        )

                        save = st.form_submit_button("Save changes", disabled=not page_usable)
                        if save and page_usable:
                            if not stream_name.strip():
                                st.error("Stream / raw material name is required.")
                            else:
                                # WP7 Phase 1/2 decoupling: keep whatever legacy
                                # production_phase_id this row already had (don't
                                # force-relink it to the run's current Finalized
                                # phase) - production_run_id is now the primary,
                                # always-set anchor going forward.
                                sel_stream.production_run_id = run.id
                                sel_stream.stream_name = stream_name.strip()
                                sel_stream.flow_unit = flow_unit
                                sel_stream.flow = flow or None
                                sel_stream.pump_speed = pump_speed or None
                                sel_stream.flow_total_qty = flow_total_qty or None
                                sel_stream.pressure_bar = pressure_bar or None
                                sel_stream.temperature_c = temperature_c or None
                                sel_stream.calibration_status = calibration_status or None
                                sel_stream.calibration_note = calibration_note
                                sel_stream.notes = notes
                                session.commit()
                                st.success("Stream reading updated.")
                                st.rerun()

                    def _do_delete_stream(_session=session, _stream=sel_stream):
                        _session.delete(_stream)
                        _session.commit()
                        st.session_state.pop("pr_selected_stream_id", None)

                    if page_usable:
                        delete_with_confirm(
                            f"stream reading — {sel_stream.stream_name}", _do_delete_stream,
                            key_prefix=f"stream_{sel_stream.id}",
                        )
                    else:
                        st.caption("View-only access - deleting is restricted for your role.")
                else:
                    st.caption("Click a row above to edit (and optionally delete) that stream reading.")

        with tab_create:
            if finalized_phase:
                st.caption(
                    "Linked directly to the run, and also to the Finalized (Runtime Data) phase "
                    "since one already exists for this run."
                )
            else:
                st.caption(
                    "Linked directly to the run. No Runtime Data (Finalized) snapshot exists yet - "
                    "that's no longer required before recording metering readings."
                )
            if not recipe_components:
                st.warning(
                    "This run's recipe version has no components listed yet — add them on the Recipe "
                    "Version Record page. Falling back to free text for now."
                )
            stream_choice = st.selectbox(
                "Stream / raw material *",
                recipe_components,
                format_func=lambda c: f"{c.raw_material_name}" + (f" ({c.role_in_formulation})" if c.role_in_formulation else ""),
                key=f"stream_choice_select_{run.id}",
            ) if recipe_components else None
            with st.form(f"add_stream_reading_{run.id}"):
                stream_other = st.text_input(
                    "Or type a stream not in the recipe (e.g. blended stream, process air, water addition)"
                )
                flow_unit = st.selectbox("Flow unit", ["kg/min", "L/min"])
                c1, c2, c3, c4 = st.columns(4)
                flow = c1.number_input("Flow", min_value=0.0, step=0.1)
                pump_speed = c2.number_input(
                    "Pump speed", min_value=0.0, step=0.1,
                    help="Metering pump setting for this stream (RPM/Hz/% depending on OEM) — the "
                    "control input, distinct from the measured Flow.",
                )
                pressure_bar = c3.number_input("Pressure (bar)", min_value=0.0, step=0.1)
                temperature_c = c4.number_input("Temperature (°C)", step=0.1)
                flow_total_qty = st.number_input(
                    "Total delivered this phase (same base unit as flow unit, kg or L)", min_value=0.0, step=0.1
                )
                c5, c6 = st.columns(2)
                calibration_status = c5.selectbox(
                    "Instrument calibration status", ["", "Valid", "Expired", "Failed", "Not Verified"]
                )
                calibration_note = c6.text_input("Calibration note (e.g. cal. due date, certificate ref.)")
                notes = st.text_area("Notes")

                submitted = st.form_submit_button("Save stream reading", disabled=not page_usable)
                if submitted and page_usable:
                    final_stream_name = stream_other.strip() or (
                        stream_choice.raw_material_name if stream_choice else ""
                    )
                    if not final_stream_name:
                        st.error("Pick a stream from the recipe, or type one that isn't in it.")
                    else:
                        session.add(
                            ComponentStreamReading(
                                production_run_id=run.id,
                                production_phase_id=finalized_phase.id if finalized_phase else None,
                                stream_name=final_stream_name,
                                flow_unit=flow_unit,
                                flow=flow or None,
                                pump_speed=pump_speed or None,
                                flow_total_qty=flow_total_qty or None,
                                pressure_bar=pressure_bar or None,
                                temperature_c=temperature_c or None,
                                calibration_status=calibration_status or None,
                                calibration_note=calibration_note,
                                notes=notes,
                                source_file_reference="manual entry",
                            )
                        )
                        session.commit()
                        st.success("Stream reading saved.")
                        st.rerun()

        with tab_import:
            show_pending_banner("stream_import_msg")
            st.caption(
                "Required columns: " + ", ".join(STREAM_REQUIRED_COLUMNS) + ". Optional columns: "
                + ", ".join(STREAM_OPTIONAL_COLUMNS) + ". WP7 Phase 1/2: each row's production_run_id "
                "just needs to be a valid run - a Finalized phase is no longer required first. If a "
                "Finalized phase does already exist for that run, the imported reading is linked to it "
                "too for continuity."
            )
            uploaded = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx"], key="stream_upload")
            if uploaded and upload_within_size_limit(uploaded):
                try:
                    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
                except Exception as exc:
                    st.error(f"Could not read file: {exc}")
                    df = None

                if df is not None and import_within_row_limit(df):
                    missing_cols = [c for c in STREAM_REQUIRED_COLUMNS if c not in df.columns]
                    if missing_cols:
                        st.error(f"File is missing required column(s): {', '.join(missing_cols)}. Import rejected.")
                    else:
                        valid_run_ids = {r.id for r in runs}
                        finalized_by_run = {
                            p.production_run_id: p
                            for p in session.query(ProductionPhase)
                            .filter(ProductionPhase.phase_name == "Finalized").all()
                        }
                        good_rows, bad_rows, resolved_phase_ids = [], [], []
                        for _, row in df.iterrows():
                            run_id_val = row.get("production_run_id")
                            if run_id_val in valid_run_ids and row.get("stream_name"):
                                good_rows.append(row)
                                match = finalized_by_run.get(run_id_val)
                                resolved_phase_ids.append(match.id if match else None)
                            else:
                                bad_rows.append(row)

                        st.write(f"Rows ready to import: **{len(good_rows)}** | Rows flagged/rejected: **{len(bad_rows)}**")
                        if bad_rows:
                            st.warning(
                                "Flagged rows reference an unknown production_run_id, or are missing stream_name."
                            )
                            render_data_table(pd.DataFrame(bad_rows), max_height="300px")

                        if good_rows and st.button("Confirm import", key="confirm_stream_import", disabled=not page_usable):
                            # Dedupe on (production_run_id, stream_name): a repeat click of
                            # this button (e.g. because the previous success message wasn't
                            # visibly persistent) must not double-insert the same material's
                            # reading for the same run. WP7 Phase 1/2: existing keys now come
                            # from either linkage style (direct production_run_id, or the
                            # legacy phase relationship), matching the streams_for_run query.
                            existing_keys = {
                                (r.production_run_id or (r.phase.production_run_id if r.phase else None), r.stream_name.strip().lower())
                                for r in session.query(ComponentStreamReading).all()
                                if r.production_run_id or r.phase
                            }
                            paired = list(zip(good_rows, resolved_phase_ids))
                            accept, dup = [], []
                            for row, phase_id in paired:
                                key = (row["production_run_id"], str(row["stream_name"]).strip().lower())
                                if key in existing_keys:
                                    dup.append(row)
                                else:
                                    existing_keys.add(key)
                                    accept.append((row, phase_id))

                            for row, phase_id in accept:
                                session.add(
                                    ComponentStreamReading(
                                        production_run_id=int(row["production_run_id"]),
                                        production_phase_id=phase_id,
                                        stream_name=str(row["stream_name"]),
                                        flow_unit=str(row.get("flow_unit", "") or "kg/min"),
                                        flow=row.get("flow"),
                                        pump_speed=row.get("pump_speed"),
                                        flow_total_qty=row.get("flow_total_qty"),
                                        pressure_bar=row.get("pressure_bar"),
                                        temperature_c=row.get("temperature_c"),
                                        calibration_status=str(row.get("calibration_status", "") or "") or None,
                                        calibration_note=str(row.get("calibration_note", "") or ""),
                                        notes=str(row.get("notes", "") or ""),
                                        source_file_reference=uploaded.name,
                                    )
                                )
                            session.commit()
                            msg = f"Imported {len(accept)} stream reading(s) from {uploaded.name}."
                            if dup:
                                msg += (
                                    f" Skipped {len(dup)} row(s) already recorded for that run/material "
                                    "(likely a repeat click)."
                                )
                            set_pending_banner("stream_import_msg", msg)
                            st.rerun()

# ---------------------------------------------------------------------------
# WP7 Phase 2 (2026-08-14): Production Output and Disposition — governing
# doc section 4 section I ("Output and Run Disposition", always available).
# Backed by the WP7 Phase 1 ProductionOutputSummary table (Charlie's
# decision doc section 3.3: single controlled UOM for planned/actual
# quantity, controlled disposition). Additive alongside the legacy Runtime
# Data "Calculated output" section (analytics.compute_runtime_output, the
# universal length/volume/weight calc) - governing doc section 8 flags
# that legacy calculation for eventual retirement where it doesn't apply,
# but Phase 2 does not remove it; this tab is the new, explicit,
# Method-agnostic capture point.
# ---------------------------------------------------------------------------
with tab_output:
    st.caption(
        "The run's planned and actual output quantity in a single controlled unit, plus its "
        "disposition (Released / Quarantined / Rejected / Rework). One record per run."
    )

    if not runs:
        st.info("Create a production run first (Production Runs tab).")
    else:
        run = _run_selector(runs, key="output_tab_run_select")
        st.caption(f"Showing production output for **{_run_label(run)}**")

        output_summary = (
            session.query(ProductionOutputSummary)
            .filter(ProductionOutputSummary.production_run_id == run.id)
            .first()
        )
        units = session.query(UnitOfMeasure).order_by(UnitOfMeasure.sort_order, UnitOfMeasure.symbol).all()

        def _unit_label(u):
            if u is None:
                return "— not selected —"
            return u.symbol + (f" ({u.name})" if u.name else "")

        if output_summary:
            st.markdown("##### Edit production output")
            with st.form(f"edit_output_form_{output_summary.id}"):
                # WP7 Phase 2 Closeout Correction v2 (2026-08-14, Charlie's
                # material completion item 2): planned_quantity/actual_
                # quantity used to be persisted via "value or None", which
                # collapsed a real recorded zero into NULL. Same explicit
                # "Record a value" checkbox pattern as the Method-Aware
                # Process Settings numeric fields - the checkbox alone
                # decides persistence at save time, independent of the
                # number field's own contents, and is never wired to the
                # number_input's disabled= (st.form widgets don't rerun on
                # interaction until submit).
                record_planned = st.checkbox(
                    "Record a planned quantity", value=output_summary.planned_quantity is not None,
                    key=f"edit_output_planned_recorded_{output_summary.id}",
                    help="Check this to save the number entered below, including zero - zero is a "
                    "distinct, valid recorded output quantity and is never treated as blank.",
                )
                planned_quantity = st.number_input(
                    "Planned quantity", min_value=0.0, step=0.1,
                    value=float(output_summary.planned_quantity or 0.0),
                    key=f"edit_output_planned_{output_summary.id}",
                )
                record_actual = st.checkbox(
                    "Record an actual quantity", value=output_summary.actual_quantity is not None,
                    key=f"edit_output_actual_recorded_{output_summary.id}",
                    help="Check this to save the number entered below, including zero - zero is a "
                    "distinct, valid recorded output quantity (e.g. a run that produced no released "
                    "output) and is never treated as blank.",
                )
                actual_quantity = st.number_input(
                    "Actual quantity", min_value=0.0, step=0.1,
                    value=float(output_summary.actual_quantity or 0.0),
                    key=f"edit_output_actual_{output_summary.id}",
                )
                unit_options = [None] + units
                unit_idx = next(
                    (i for i, u in enumerate(unit_options) if u is not None and u.id == output_summary.unit_id), 0
                )
                unit = st.selectbox(
                    "Unit", unit_options, index=unit_idx, format_func=_unit_label,
                    key=f"edit_output_unit_{output_summary.id}",
                )
                disposition_options = [""] + PRODUCTION_OUTPUT_DISPOSITIONS
                disposition_idx = (
                    disposition_options.index(output_summary.disposition)
                    if output_summary.disposition in disposition_options else 0
                )
                disposition = st.selectbox(
                    "Disposition", disposition_options, index=disposition_idx,
                    key=f"edit_output_disposition_{output_summary.id}",
                )
                disposition_notes = st.text_area(
                    "Disposition notes", value=output_summary.disposition_notes or "",
                    key=f"edit_output_notes_{output_summary.id}",
                )
                save = st.form_submit_button("Save changes", disabled=not page_usable)
                if save and page_usable:
                    output_summary.planned_quantity = planned_quantity if record_planned else None
                    output_summary.actual_quantity = actual_quantity if record_actual else None
                    output_summary.unit_id = unit.id if unit else None
                    output_summary.disposition = disposition or None
                    output_summary.disposition_notes = disposition_notes
                    session.commit()
                    st.success("Production output updated.")
                    st.rerun()

            def _do_delete_output(_session=session, _row=output_summary):
                _session.delete(_row)
                _session.commit()

            if page_usable:
                delete_with_confirm(
                    f"production output record (Run #{run.id})", _do_delete_output,
                    key_prefix=f"output_{output_summary.id}",
                )
            else:
                st.caption("View-only access - deleting is restricted for your role.")
        else:
            st.info("No production output recorded yet for this run — use the form below.")
            with st.form(f"add_output_{run.id}"):
                # Same explicit "Record a value" checkbox pattern as the Edit
                # form above - see the comment there for why it's never wired
                # to number_input's disabled=.
                record_planned = st.checkbox(
                    "Record a planned quantity", value=False, key=f"new_output_planned_recorded_{run.id}",
                    help="Check this to save the number entered below, including zero - zero is a "
                    "distinct, valid recorded output quantity and is never treated as blank.",
                )
                planned_quantity = st.number_input(
                    "Planned quantity", min_value=0.0, step=0.1, key=f"new_output_planned_{run.id}"
                )
                record_actual = st.checkbox(
                    "Record an actual quantity", value=False, key=f"new_output_actual_recorded_{run.id}",
                    help="Check this to save the number entered below, including zero - zero is a "
                    "distinct, valid recorded output quantity (e.g. a run that produced no released "
                    "output) and is never treated as blank.",
                )
                actual_quantity = st.number_input(
                    "Actual quantity", min_value=0.0, step=0.1, key=f"new_output_actual_{run.id}"
                )
                unit = st.selectbox(
                    "Unit", [None] + units, format_func=_unit_label, key=f"new_output_unit_{run.id}"
                )
                disposition = st.selectbox(
                    "Disposition", [""] + PRODUCTION_OUTPUT_DISPOSITIONS, key=f"new_output_disposition_{run.id}"
                )
                disposition_notes = st.text_area("Disposition notes", key=f"new_output_notes_{run.id}")
                submitted = st.form_submit_button("Save production output", disabled=not page_usable)
                if submitted and page_usable:
                    session.add(
                        ProductionOutputSummary(
                            production_run_id=run.id,
                            planned_quantity=planned_quantity if record_planned else None,
                            actual_quantity=actual_quantity if record_actual else None,
                            unit_id=unit.id if unit else None,
                            disposition=disposition or None,
                            disposition_notes=disposition_notes,
                        )
                    )
                    session.commit()
                    st.success("Production output saved.")
                    st.rerun()

        st.divider()
        st.caption(
            "For reference, the legacy calculated output (length/volume/weight from tunnel width x "
            "foam height x conveyor speed) still shows on the Actual Run and Cycle Data tab. Per the "
            "WP7 governing document, that universal calculation only applies to methods it was "
            "designed for and is expected to be retired for others in a later WP7 phase - it is not "
            "removed here."
        )

# ---------------------------------------------------------------------------
# Cycle / Shot Data (WP7 Phase 2 Closeout Correction, Material Gap 3)
#
# Charlie's WP7 Phase 2 Closeout Review explicitly rejected the earlier
# closeout package's "schema support alone is sufficient, no UI needed"
# framing for cycle/shot capture - this tab is the real, conditionally-
# rendered module that framing incorrectly said wasn't required.
# Conditional on run_uses_cycle_shot_operation() (helpers.py), a
# config-driven declaration resolved from ProductionMethod.
# uses_cycle_shot_operation / Machine.cycle_shot_operation_override -
# never inferred from a Method's or Machine's name, and never seeded True
# on any live row without Charlie's evidence-based confirmation (same
# Phase 1 Production Seeding Rule as ProcessSettingApplicability).
# ---------------------------------------------------------------------------
with tab_cycles:
    st.caption(
        "Discrete cycle/shot capture for Production Methods/Production Units or Cells that operate "
        "in mold-fill-cure-demold cycles (a cycle can itself contain several shots, e.g. a multi-drop "
        "pour) rather than a continuous line. This module only becomes usable when the run's "
        "Production Method or Production Unit or Cell is explicitly configured for cycle/shot "
        "operation - it is never inferred from a name."
    )
    if not runs:
        st.info("Create a production run first (Production Runs tab).")
    else:
        run = _run_selector(runs, key="cycles_tab_run_select")
        if not run_uses_cycle_shot_operation(run):
            st.info(
                "Cycle/Shot data capture is not enabled for this run's Production Method/Production "
                "Unit or Cell. This is expected for continuous-line methods - the flag is set "
                "per Production Method (with an optional per-Production Unit or Cell override) on "
                "the Production Methods / Plant & Foam Equipment Overview pages, and only after an "
                "evidence-based confirmation that the method genuinely operates in discrete cycles."
            )
        else:
            st.caption(
                f"Showing Cycle/Shot data for **{_run_label(run)}** — Production Method: "
                f"**{run.production_method.name if run.production_method else '—'}**"
            )
            cycles = (
                session.query(ProductionCycle)
                .filter(ProductionCycle.production_run_id == run.id)
                .order_by(ProductionCycle.cycle_number)
                .all()
            )

            # Tool/Mixhead choices are optional and, where the run's Machine
            # has a resolved ProductionUnit, scoped to it - otherwise
            # unfiltered, since many plants haven't populated that equipment
            # master data yet and this module still has to be usable without
            # it (same "don't force a picker the data can't support yet"
            # precedent used throughout this app).
            production_unit_id = run.machine.production_unit_id if run.machine else None
            tool_query = session.query(Tool)
            mixhead_query = session.query(Mixhead)
            if production_unit_id:
                tool_query = tool_query.filter(Tool.production_unit_id == production_unit_id)
                mixhead_query = mixhead_query.filter(Mixhead.production_unit_id == production_unit_id)
            tools = tool_query.order_by(Tool.name).all()
            mixheads = mixhead_query.order_by(Mixhead.name).all()

            st.markdown("##### Cycles recorded for this run")
            if not cycles:
                st.caption("No cycles recorded yet for this run.")
            else:
                cycle_rows = [
                    {
                        "Cycle": c.cycle_number,
                        "Tool": c.tool.name if c.tool else "—",
                        "Mixhead": c.mixhead.name if c.mixhead else "—",
                        "Start": c.cycle_start,
                        "End": c.cycle_end,
                        "Shots": session.query(ProductionShot)
                        .filter(ProductionShot.production_cycle_id == c.id).count(),
                    }
                    for c in cycles
                ]
                render_data_table(pd.DataFrame(cycle_rows), max_height="260px")

            st.markdown("##### Add a cycle")
            with st.form(f"add_cycle_{run.id}"):
                next_cycle_number = max((c.cycle_number for c in cycles), default=0) + 1
                cycle_number = st.number_input(
                    "Cycle number *", min_value=1, step=1, value=next_cycle_number,
                    key=f"new_cycle_number_{run.id}",
                )
                tool = st.selectbox(
                    "Tool", [None] + tools,
                    format_func=lambda t: "— not selected —" if t is None else t.name,
                    key=f"new_cycle_tool_{run.id}",
                )
                mixhead = st.selectbox(
                    "Mixhead", [None] + mixheads,
                    format_func=lambda m: "— not selected —" if m is None else m.name,
                    key=f"new_cycle_mixhead_{run.id}",
                )
                record_cycle_start = st.checkbox(
                    "Record a cycle start time", value=False, key=f"new_cycle_start_flag_{run.id}",
                )
                cycle_start_value = combine_date_time(
                    "Cycle start", f"new_cycle_start_{run.id}", default_date=run.run_date,
                )
                record_cycle_end = st.checkbox(
                    "Record a cycle end time", value=False, key=f"new_cycle_end_flag_{run.id}",
                )
                cycle_end_value = combine_date_time(
                    "Cycle end", f"new_cycle_end_{run.id}", default_date=run.run_date,
                )
                cycle_notes = st.text_area("Notes", key=f"new_cycle_notes_{run.id}")
                submitted_cycle = st.form_submit_button("Save cycle", disabled=not page_usable)
                if submitted_cycle and page_usable:
                    session.add(ProductionCycle(
                        production_run_id=run.id,
                        cycle_number=int(cycle_number),
                        tool_id=tool.id if tool else None,
                        mixhead_id=mixhead.id if mixhead else None,
                        cycle_start=cycle_start_value if record_cycle_start else None,
                        cycle_end=cycle_end_value if record_cycle_end else None,
                        notes=cycle_notes,
                    ))
                    session.commit()
                    st.success("Cycle saved.")
                    st.rerun()

            if cycles:
                st.divider()
                st.markdown("##### Shots for a cycle")
                cycle = st.selectbox(
                    "Cycle *", cycles, format_func=lambda c: f"Cycle {c.cycle_number}",
                    key=f"cycles_tab_cycle_select_{run.id}",
                )
                shots = (
                    session.query(ProductionShot)
                    .filter(ProductionShot.production_cycle_id == cycle.id)
                    .order_by(ProductionShot.shot_number)
                    .all()
                )
                if not shots:
                    st.caption("No shots recorded yet for this cycle.")
                else:
                    shot_rows = [
                        {
                            "Shot": s.shot_number,
                            "Cavity": (s.cavity.name or f"Cavity {s.cavity.cavity_number}") if s.cavity else "—",
                            "Fill point": (
                                s.fill_point.name or f"Fill point {s.fill_point.fill_point_number}"
                            ) if s.fill_point else "—",
                            "Timestamp": s.shot_ts,
                        }
                        for s in shots
                    ]
                    render_data_table(pd.DataFrame(shot_rows), max_height="220px")

                # Cavity/Fill point pickers live outside the form (same reason
                # Plant/Production Method/Production Unit or Cell live outside
                # the Create Production Run form above): Fill point's choices
                # depend on the selected Cavity, and st.form widgets don't
                # rerun the script until submit, so a dependent dropdown
                # nested inside the same form can't react to an earlier one
                # in time for the same submission.
                cavity_query = session.query(Cavity)
                if cycle.tool_id:
                    cavity_query = cavity_query.filter(Cavity.tool_id == cycle.tool_id)
                cavities = cavity_query.order_by(Cavity.cavity_number).all()
                cavity = st.selectbox(
                    "Cavity", [None] + cavities,
                    format_func=lambda c: "— not selected —" if c is None else (c.name or f"Cavity {c.cavity_number}"),
                    key=f"new_shot_cavity_{cycle.id}",
                )
                fill_points = (
                    session.query(FillPoint).filter(FillPoint.cavity_id == cavity.id)
                    .order_by(FillPoint.fill_point_number).all()
                    if cavity else []
                )
                fill_point = st.selectbox(
                    "Fill point", [None] + fill_points,
                    format_func=lambda f: "— not selected —" if f is None else (f.name or f"Fill point {f.fill_point_number}"),
                    key=f"new_shot_fillpoint_{cycle.id}",
                )

                with st.form(f"add_shot_{cycle.id}"):
                    next_shot_number = max((s.shot_number for s in shots), default=0) + 1
                    shot_number = st.number_input(
                        "Shot number *", min_value=1, step=1, value=next_shot_number,
                        key=f"new_shot_number_{cycle.id}",
                    )
                    record_shot_ts = st.checkbox(
                        "Record a shot timestamp", value=False, key=f"new_shot_ts_flag_{cycle.id}",
                    )
                    shot_ts_value = combine_date_time(
                        "Shot timestamp", f"new_shot_ts_{cycle.id}", default_date=run.run_date,
                    )
                    shot_notes = st.text_area("Notes", key=f"new_shot_notes_{cycle.id}")
                    submitted_shot = st.form_submit_button("Save shot", disabled=not page_usable)
                    if submitted_shot and page_usable:
                        session.add(ProductionShot(
                            production_cycle_id=cycle.id,
                            shot_number=int(shot_number),
                            shot_ts=shot_ts_value if record_shot_ts else None,
                            cavity_id=cavity.id if cavity else None,
                            fill_point_id=fill_point.id if fill_point else None,
                            notes=shot_notes,
                        ))
                        session.commit()
                        st.success("Shot saved.")
                        st.rerun()

# ---------------------------------------------------------------------------
# Production events (alarms / interventions / grade changes)
# ---------------------------------------------------------------------------
with tab_events:
    st.caption(
        "Alarms, manual interventions, grade changes, and planned/unplanned pauses. This log is what "
        "explains outliers and lets transition material be excluded from steady-state analysis."
    )

    if not runs:
        st.info("Create a production run first (Production Runs tab).")
    else:
        run = _run_selector(runs, key="event_tab_run_select")
        st.caption(f"Showing events for **{_run_label(run)}**")
        phases_for_run = (
            session.query(ProductionPhase).filter(ProductionPhase.production_run_id == run.id).all()
        )

        # WP7 Phase 1/2 (2026-08-13/14, per Charlie's design review decision doc
        # section 3.5): ProductionEvent now carries 4 optional context links -
        # process setting, raw material lot use, quality issue, quality test
        # result - scoped to what's actually available on this run (except the
        # setting definition catalogue, which is global/controlled).
        setting_defs_for_picker = (
            session.query(ProcessSettingDefinition)
            .filter(ProcessSettingDefinition.active == True)  # noqa: E712
            .order_by(ProcessSettingDefinition.sort_order, ProcessSettingDefinition.name)
            .all()
        )
        lot_uses_for_run = (
            session.query(RawMaterialLotUse).filter(RawMaterialLotUse.production_run_id == run.id).all()
        )
        quality_obs_for_run = (
            session.query(QualityObservation).filter(QualityObservation.production_run_id == run.id).all()
        )
        physical_results_for_run = (
            session.query(PhysicalPropertyResult).filter(PhysicalPropertyResult.production_run_id == run.id).all()
        )

        def _setting_def_label(d):
            return "—" if d is None else d.name

        def _lot_use_label(l):
            return "—" if l is None else f"{l.component_stream_name} — lot {l.supplier_lot_no}"

        def _quality_obs_label(q):
            return "—" if q is None else f"#{q.id} — {q.observation_type}"

        def _physical_result_label(r):
            return "—" if r is None else f"#{r.id} — {r.property_name}"

        # CR-11: wording/order aligned via cr11_function_tab_labels().
        tab_create, tab_edit_delete, tab_import = st.tabs(cr11_function_tab_labels("Production Event"))

        events_for_run = (
            session.query(ProductionEvent)
            .filter(ProductionEvent.production_run_id == run.id)
            .order_by(ProductionEvent.event_ts.desc())
            .all()
        )

        with tab_edit_delete:
            if not events_for_run:
                st.info("No events logged yet for this run — use the Create tab.")
            else:
                severity_icon = {"Low": "🟡", "Medium": "🟠", "High": "🔴"}
                event_rows = [
                    {
                        "Time": e.event_ts,
                        "Type": e.event_type,
                        "Severity": severity_icon.get(e.severity, "") + " " + (e.severity or "") if e.severity else "",
                        "Phase": e.phase.phase_name if e.phase else "—",
                        "Description": e.description,
                        "Action taken": e.action_taken,
                    }
                    for e in events_for_run
                ]
                idx = clickable_table(event_rows, key=f"events_table_{run.id}")
                if idx is not None:
                    st.session_state["pr_selected_event_id"] = events_for_run[idx].id
                else:
                    st.session_state.pop("pr_selected_event_id", None)

                sel_event = next(
                    (e for e in events_for_run if e.id == st.session_state.get("pr_selected_event_id")), None
                )
                if sel_event:
                    st.markdown(f"##### Edit event — {sel_event.event_type}")
                    with st.form(f"edit_event_form_{sel_event.id}"):
                        event_type = st.selectbox(
                            "Event type *", EVENT_TYPES, index=EVENT_TYPES.index(sel_event.event_type),
                            key=f"edit_event_type_{sel_event.id}",
                        )
                        severity_options = [""] + SEVERITIES
                        severity_idx = severity_options.index(sel_event.severity) if sel_event.severity in severity_options else 0
                        severity = st.selectbox(
                            "Severity", severity_options, index=severity_idx, key=f"edit_event_severity_{sel_event.id}"
                        )
                        phase_options = [None] + phases_for_run
                        phase_idx = next(
                            (i for i, p in enumerate(phase_options) if p is not None and p.id == sel_event.production_phase_id),
                            0,
                        )
                        phase = st.selectbox(
                            "Phase (optional)", phase_options, index=phase_idx,
                            format_func=lambda p: "—" if p is None else f"{p.phase_name} ({p.phase_start})",
                            key=f"edit_event_phase_{sel_event.id}",
                        )
                        event_ts = combine_date_time(
                            "Event time", f"edit_event_ts_{sel_event.id}",
                            default_date=sel_event.event_ts.date() if sel_event.event_ts else None,
                            default_time=sel_event.event_ts.time() if sel_event.event_ts else None,
                        )
                        description = st.text_area(
                            "Description", value=sel_event.description or "", key=f"edit_event_desc_{sel_event.id}"
                        )
                        action_taken = st.text_area(
                            "Action taken", value=sel_event.action_taken or "", key=f"edit_event_action_{sel_event.id}"
                        )

                        st.markdown("**Optional context links** (WP7 Phase 2)")
                        ec1, ec2 = st.columns(2)
                        setting_options = [None] + setting_defs_for_picker
                        setting_idx = next(
                            (i for i, d in enumerate(setting_options) if d is not None and d.id == sel_event.setting_definition_id),
                            0,
                        )
                        setting_link = ec1.selectbox(
                            "Related process setting", setting_options, index=setting_idx,
                            format_func=_setting_def_label, key=f"edit_event_setting_{sel_event.id}",
                        )
                        lot_options = [None] + lot_uses_for_run
                        lot_idx = next(
                            (i for i, l in enumerate(lot_options) if l is not None and l.id == sel_event.raw_material_lot_use_id),
                            0,
                        )
                        lot_link = ec2.selectbox(
                            "Related raw material lot use", lot_options, index=lot_idx,
                            format_func=_lot_use_label, key=f"edit_event_lot_{sel_event.id}",
                        )
                        ec3, ec4 = st.columns(2)
                        obs_options = [None] + quality_obs_for_run
                        obs_idx = next(
                            (i for i, q in enumerate(obs_options) if q is not None and q.id == sel_event.quality_observation_id),
                            0,
                        )
                        obs_link = ec3.selectbox(
                            "Related quality issue", obs_options, index=obs_idx,
                            format_func=_quality_obs_label, key=f"edit_event_obs_{sel_event.id}",
                        )
                        result_options = [None] + physical_results_for_run
                        result_idx = next(
                            (i for i, r in enumerate(result_options) if r is not None and r.id == sel_event.physical_property_result_id),
                            0,
                        )
                        result_link = ec4.selectbox(
                            "Related quality test result", result_options, index=result_idx,
                            format_func=_physical_result_label, key=f"edit_event_result_{sel_event.id}",
                        )

                        save = st.form_submit_button("Save changes", disabled=not page_usable)
                        if save and page_usable:
                            sel_event.event_type = event_type
                            sel_event.severity = severity or None
                            sel_event.production_phase_id = phase.id if phase else None
                            sel_event.event_ts = event_ts
                            sel_event.description = description
                            sel_event.action_taken = action_taken
                            sel_event.setting_definition_id = setting_link.id if setting_link else None
                            sel_event.raw_material_lot_use_id = lot_link.id if lot_link else None
                            sel_event.quality_observation_id = obs_link.id if obs_link else None
                            sel_event.physical_property_result_id = result_link.id if result_link else None
                            session.commit()
                            st.success("Event updated.")
                            st.rerun()

                    def _do_delete_event(_session=session, _event=sel_event):
                        _session.delete(_event)
                        _session.commit()
                        st.session_state.pop("pr_selected_event_id", None)

                    if page_usable:
                        delete_with_confirm(
                            f"event — {sel_event.event_type}", _do_delete_event, key_prefix=f"event_{sel_event.id}"
                        )
                    else:
                        st.caption("View-only access - deleting is restricted for your role.")
                else:
                    st.caption("Click a row above to edit (and optionally delete) that event.")

        with tab_create:
            with st.form(f"add_event_{run.id}"):
                event_type = st.selectbox("Event type *", EVENT_TYPES)
                severity = st.selectbox("Severity", [""] + SEVERITIES)
                phase = st.selectbox(
                    "Phase (optional)",
                    [None] + phases_for_run,
                    format_func=lambda p: "—" if p is None else f"{p.phase_name} ({p.phase_start})",
                )
                event_ts = combine_date_time("Event time", f"new_event_ts_{run.id}")
                description = st.text_area("Description")
                action_taken = st.text_area("Action taken")

                st.markdown("**Optional context links** (WP7 Phase 2)")
                nc1, nc2 = st.columns(2)
                setting_link = nc1.selectbox(
                    "Related process setting", [None] + setting_defs_for_picker, format_func=_setting_def_label,
                    key=f"new_event_setting_{run.id}",
                )
                lot_link = nc2.selectbox(
                    "Related raw material lot use", [None] + lot_uses_for_run, format_func=_lot_use_label,
                    key=f"new_event_lot_{run.id}",
                )
                nc3, nc4 = st.columns(2)
                obs_link = nc3.selectbox(
                    "Related quality issue", [None] + quality_obs_for_run, format_func=_quality_obs_label,
                    key=f"new_event_obs_{run.id}",
                )
                result_link = nc4.selectbox(
                    "Related quality test result", [None] + physical_results_for_run, format_func=_physical_result_label,
                    key=f"new_event_result_{run.id}",
                )

                submitted = st.form_submit_button("Save event", disabled=not page_usable)
                if submitted and page_usable:
                    session.add(
                        ProductionEvent(
                            production_run_id=run.id,
                            production_phase_id=phase.id if phase else None,
                            event_ts=event_ts,
                            event_type=event_type,
                            severity=severity or None,
                            description=description,
                            action_taken=action_taken,
                            setting_definition_id=setting_link.id if setting_link else None,
                            raw_material_lot_use_id=lot_link.id if lot_link else None,
                            quality_observation_id=obs_link.id if obs_link else None,
                            physical_property_result_id=result_link.id if result_link else None,
                            source_file_reference="manual entry",
                        )
                    )
                    session.commit()
                    st.success("Event logged.")
                    st.rerun()

        with tab_import:
            st.caption(
                "Required columns: " + ", ".join(EVENT_REQUIRED_COLUMNS) + ". Optional columns: "
                + ", ".join(EVENT_OPTIONAL_COLUMNS) + " (phase_name must match an existing phase on that run if given)."
            )
            uploaded = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx"], key="event_upload")
            if uploaded and upload_within_size_limit(uploaded):
                try:
                    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
                except Exception as exc:
                    st.error(f"Could not read file: {exc}")
                    df = None

                if df is not None and import_within_row_limit(df):
                    missing_cols = [c for c in EVENT_REQUIRED_COLUMNS if c not in df.columns]
                    if missing_cols:
                        st.error(f"File is missing required column(s): {', '.join(missing_cols)}. Import rejected.")
                    else:
                        valid_run_ids = {r.id for r in runs}
                        all_phases_lookup = session.query(ProductionPhase).all()
                        good_rows, bad_rows, resolved_phase_ids = [], [], []
                        for _, row in df.iterrows():
                            run_ok = row.get("production_run_id") in valid_run_ids
                            ts = parse_dt(row.get("event_ts"))
                            if run_ok and row.get("event_type") in EVENT_TYPES and ts is not None:
                                phase_match = next(
                                    (
                                        p for p in all_phases_lookup
                                        if p.production_run_id == row.get("production_run_id")
                                        and p.phase_name == row.get("phase_name")
                                    ),
                                    None,
                                )
                                good_rows.append(row)
                                resolved_phase_ids.append(phase_match.id if phase_match else None)
                            else:
                                bad_rows.append(row)

                        st.write(f"Rows ready to import: **{len(good_rows)}** | Rows flagged/rejected: **{len(bad_rows)}**")
                        if bad_rows:
                            st.warning(
                                "Flagged rows have an unknown production_run_id, an event_type outside "
                                f"the controlled list ({', '.join(EVENT_TYPES)}), or an unparseable event_ts."
                            )
                            render_data_table(pd.DataFrame(bad_rows), max_height="300px")

                        if good_rows and st.button("Confirm import", key="confirm_event_import", disabled=not page_usable):
                            # Dedupe on (production_run_id, event_ts, event_type): a repeat
                            # click of this button must not double-insert the same logged
                            # event.
                            existing_keys = {
                                (e.production_run_id, e.event_ts, e.event_type)
                                for e in session.query(ProductionEvent).all()
                            }
                            paired = list(zip(good_rows, resolved_phase_ids))
                            accept, dup = [], []
                            for row, phase_id in paired:
                                key = (int(row["production_run_id"]), parse_dt(row.get("event_ts")), row["event_type"])
                                if key in existing_keys:
                                    dup.append(row)
                                else:
                                    existing_keys.add(key)
                                    accept.append((row, phase_id))

                            for row, phase_id in accept:
                                session.add(
                                    ProductionEvent(
                                        production_run_id=int(row["production_run_id"]),
                                        production_phase_id=phase_id,
                                        event_ts=parse_dt(row.get("event_ts")),
                                        event_type=row["event_type"],
                                        severity=str(row.get("severity", "") or "") or None,
                                        description=str(row.get("description", "") or ""),
                                        action_taken=str(row.get("action_taken", "") or ""),
                                        source_file_reference=uploaded.name,
                                    )
                                )
                            session.commit()
                            msg = f"Imported {len(accept)} event(s) from {uploaded.name}."
                            if dup:
                                msg += f" Skipped {len(dup)} row(s) already recorded for that run/time/type (likely a repeat click)."
                            st.success(msg)
                            st.rerun()

# ---------------------------------------------------------------------------
# Runtime Data (the Finalized snapshot: what actually happened, entered at
# shutdown - the same settings as Setup, plus line speed/rise time/curing
# outcomes that only exist once the run has actually happened).
# ---------------------------------------------------------------------------
with tab_runtime:
    st.caption(
        "The Finalized window for this run (start/end time and notes), entered at shutdown. "
        "Component stream readings and production events both attach to this snapshot, never to "
        "Setup. Actual process settings are captured on the Method-Aware Process Settings tab."
    )

    if not runs:
        st.info("Create a production run first (Production Runs tab).")
    else:
        run = _run_selector(runs, key="runtime_tab_run_select")
        st.caption(f"Showing Runtime Data for **{_run_label(run)}**")

        # CR-11: wording/order aligned via cr11_function_tab_labels(). The
        # page-specific 4th tab ("Tool Geometry and Fill Configuration",
        # the fall-plate section-position sub-workflow) was removed under
        # WP7 Phase 0 - see the module docstring.
        tab_create, tab_edit_delete, tab_import = st.tabs(
            cr11_function_tab_labels("Runtime Data", "Runtime Data")
        )

        finalized_phase = (
            session.query(ProductionPhase)
            .filter(ProductionPhase.production_run_id == run.id, ProductionPhase.phase_name == "Finalized")
            .first()
        )

        with tab_edit_delete:
            if not finalized_phase:
                st.info("No Runtime Data recorded yet for this run — use the Create tab.")
            else:
                st.markdown("##### Edit Runtime Data")
                with st.form(f"edit_runtime_form_{finalized_phase.id}"):
                    phase_start = combine_date_time(
                        "Run start", f"edit_runtime_start_{finalized_phase.id}",
                        default_date=finalized_phase.phase_start.date() if finalized_phase.phase_start else None,
                        default_time=finalized_phase.phase_start.time() if finalized_phase.phase_start else None,
                    )
                    phase_end = combine_date_time(
                        "Run end", f"edit_runtime_end_{finalized_phase.id}",
                        default_date=finalized_phase.phase_end.date() if finalized_phase.phase_end else None,
                        default_time=finalized_phase.phase_end.time() if finalized_phase.phase_end else None,
                    )

                    # WP7 Phase 5 (Legacy Retirement): the machine-setting,
                    # ambient-condition, and runtime-outcome widgets formerly
                    # here, plus the "Calculated output" block below (which
                    # called the now-retired analytics.compute_runtime_output,
                    # a continuous-conveyor-line formula architecturally
                    # inapplicable to Rigid Foam's discontinuous production),
                    # are retired from active capture - ProductionPhase is
                    # now ARCHIVE READ-ONLY for those fields (see the WP7
                    # Phase 5 JC Pre-Coding Engineering Challenge Response,
                    # Section 4). Planned/Actual process settings live on the
                    # Method-Aware Process Settings tab; output quantity and
                    # disposition live on the Production Output tab.
                    notes = st.text_area(
                        "Notes", value=finalized_phase.notes or "", key=f"edit_runtime_notes_{finalized_phase.id}"
                    )

                    save = st.form_submit_button("Save changes", disabled=not page_usable)
                    if save and page_usable:
                        if phase_end < phase_start:
                            st.error("Run end must not be before Run start.")
                        else:
                            finalized_phase.phase_start = phase_start
                            finalized_phase.phase_end = phase_end
                            finalized_phase.notes = notes
                            session.commit()
                            st.success("Runtime Data updated.")
                            st.rerun()

                def _do_delete_runtime(_session=session, _phase=finalized_phase):
                    _delete_phase_cascade(_session, _phase)

                if page_usable:
                    delete_with_confirm(
                        f"Runtime Data (Run #{run.id})", _do_delete_runtime, key_prefix=f"runtime_{finalized_phase.id}",
                        extra_warning=(
                            "Deleting this also deletes its component stream readings and fall-plate section "
                            "positions, and unlinks (does not delete) any production events that referenced it."
                        ),
                    )
                else:
                    st.caption("View-only access - deleting is restricted for your role.")

        with tab_create:
            if finalized_phase:
                st.caption("Runtime Data already recorded for this run — edit it in the Overview & Edit tab.")
            else:
                with st.form(f"add_runtime_{run.id}"):
                    # Same reasoning as the Setup Create form above: default
                    # to the run's own run_date, not today, since Runtime
                    # Data is normally logged the same day the batch ran
                    # (hours apart, not days) - still fully editable.
                    phase_start = combine_date_time(
                        "Run start", f"new_runtime_start_{run.id}", default_date=run.run_date
                    )
                    phase_end = combine_date_time(
                        "Run end", f"new_runtime_end_{run.id}", default_date=run.run_date
                    )

                    # WP7 Phase 5 (Legacy Retirement): see the matching
                    # comment in the Edit form above - machine-setting,
                    # ambient-condition, and runtime-outcome fields are no
                    # longer captured here.
                    notes = st.text_area("Notes", key=f"new_runtime_notes_{run.id}")

                    submitted = st.form_submit_button("Save Runtime Data", disabled=not page_usable)
                    if submitted and page_usable:
                        if phase_end < phase_start:
                            st.error("Run end must not be before Run start.")
                        else:
                            session.add(
                                ProductionPhase(
                                    production_run_id=run.id,
                                    phase_name="Finalized",
                                    phase_start=phase_start,
                                    phase_end=phase_end,
                                    notes=notes,
                                    source_file_reference="manual entry",
                                )
                            )
                            session.commit()
                            st.success("Runtime Data saved.")
                            st.rerun()

        with tab_import:
            show_pending_banner("runtime_import_msg")
            st.caption(
                "Required column: `production_run_id`. Optional columns: " + ", ".join(RUNTIME_OPTIONAL_COLUMNS)
                + ". One Runtime Data row per run - a run that already has one is skipped as a duplicate."
            )
            uploaded = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx"], key="runtime_upload")
            if uploaded and upload_within_size_limit(uploaded):
                try:
                    if uploaded.name.endswith(".csv"):
                        df = pd.read_csv(uploaded)
                    else:
                        df = pd.read_excel(uploaded)
                except Exception as exc:
                    st.error(f"Could not read file: {exc}")
                    df = None

                if df is not None and import_within_row_limit(df):
                    missing_cols = [c for c in RUNTIME_REQUIRED_COLUMNS if c not in df.columns]
                    if missing_cols:
                        st.error(f"File is missing required column(s): {', '.join(missing_cols)}. Import rejected.")
                    else:
                        valid_run_ids = {r.id for r in runs}
                        good_rows, bad_rows = [], []
                        for _, row in df.iterrows():
                            if row.get("production_run_id") in valid_run_ids:
                                good_rows.append(row)
                            else:
                                bad_rows.append(row)

                        st.write(f"Rows ready to import: **{len(good_rows)}** | Rows flagged/rejected: **{len(bad_rows)}**")
                        if bad_rows:
                            st.warning("Flagged rows reference a production_run_id that does not exist and will be skipped.")
                            render_data_table(pd.DataFrame(bad_rows), max_height="300px")

                        if good_rows and st.button("Confirm import", key="confirm_runtime_import", disabled=not page_usable):
                            # Dedupe on production_run_id: only one Finalized row per run.
                            existing_keys = {
                                p.production_run_id
                                for p in session.query(ProductionPhase).filter(ProductionPhase.phase_name == "Finalized").all()
                            }
                            accept, dup = dedupe_import_rows(
                                good_rows, existing_keys,
                                key_func=lambda row: int(row["production_run_id"]),
                            )
                            for row in accept:
                                # WP7 Phase 5 (Legacy Retirement): legacy
                                # machine-setting/ambient/outcome columns are
                                # no longer accepted on import - see the
                                # matching comment on the Edit form above.
                                session.add(
                                    ProductionPhase(
                                        production_run_id=int(row["production_run_id"]),
                                        phase_name="Finalized",
                                        phase_start=parse_dt(row.get("phase_start")),
                                        phase_end=parse_dt(row.get("phase_end")),
                                        notes=str(row.get("notes", "") or ""),
                                        source_file_reference=uploaded.name,
                                    )
                                )
                            session.commit()
                            msg = f"Imported {len(accept)} Runtime Data row(s) from {uploaded.name}."
                            if dup:
                                msg += f" Skipped {len(dup)} row(s) whose run already has Runtime Data (likely a repeat click)."
                            set_pending_banner("runtime_import_msg", msg)
                            st.rerun()
