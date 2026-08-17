"""
PI3 Plant Edition
Main entry point / navigation router.

HTC Global Co. Ltd - rigid foam expert system, commercialised
as PI3 - Rigid Foam Intelligence.

This file sets page config, sidebar branding, and global styling once (it
always runs first, on every page view, under st.navigation), then routes to
the individual screens.
"""

import datetime as dt
import time

import sqlalchemy.exc as sa_exc
import streamlit as st
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

import analytics
import audit_log
from access_control import denied_page_keys, page_visible
from auth import current_user, logout_button, require_login
from db import (
    Company,
    CustomerTrial,
    FoamGrade,
    Machine,
    OptimizationTrial,
    PhysicalPropertyResult,
    Plant,
    ProductFamily,
    ProductionMethod,
    ProductionRun,
    QualityObservation,
    RecipeVersion,
    Sample,
    close_out_session,
    get_session,
    init_db,
)
from helpers import (
    activated_methods_for_plant,
    all_production_methods,
    machines_for_plant_and_method,
    machines_for_plant_across_activated_methods,
    page_setup,
    render_function_action_intro,
)
from quality_standards import compute_pass_fail
from version import APP_VERSION

LOGO_PATH = "assets/htc_global_logo_blue_steel.png"

# See the sa_exc.InvalidRequestError handler around pg.run() below: how many
# consecutive cached-session corruptions (Streamlit cancelling an in-flight
# rerun mid-statement) this app will silently discard-and-retry, per browser
# tab, before giving up and letting the error surface to the user.
_MAX_SESSION_RECOVERY_ATTEMPTS = 2

st.set_page_config(page_title="PI3 - Rigid Foam Intelligence", page_icon="🏗️", layout="wide")

# Light styling on top of the .streamlit/config.toml color theme.
st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #DCE6EC;
        border-radius: 10px;
        padding: 10px 16px 4px 16px;
    }
    div[data-testid="stExpander"] {
        border-radius: 10px;
        border: 1px solid #DCE6EC;
    }
    div[data-testid="stContainer"] {
        border-radius: 10px;
    }
    /* st.caption() defaults to small, low-contrast grey text everywhere in
       the app (page descriptions, disclaimers, table captions, ...) - hard
       to read for plant-floor reviewers. Force it to normal body size and
       full black instead, app-wide, since this file's global style block
       runs first on every page under st.navigation. */
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] * {
        font-size: 1rem !important;
        color: #000000 !important;
        opacity: 1 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_overview():
    """Screen 1: Plant Intelligence Dashboard (default landing page).

    Rebuilt 2026-08-10 for CR-02 (Overview Dashboard Production Method
    Alignment, per Charlie's
    PI3_Rigid_Foam_Phase_1_CR02_Overview_Dashboard_Production_Method_
    Alignment_for_UAT.docx): the primary filter row now follows the
    approved operating hierarchy - Plant -> Production Method ->
    Production Unit / Cell -> Product Grade -> Date Range (CR-02 section
    3) - each cascading into the next exactly like the Production
    Equipment / Product Grade forms already do elsewhere in the app
    (helpers.activated_methods_for_plant / machines_for_plant_and_method
    / machines_for_plant_across_activated_methods). Product Family is
    demoted to an optional "Advanced filter" (CR-02: "a commercial/product
    classification... shall not replace Production Method, Production
    Unit/Cell or Product Grade in the primary operating filter sequence")
    that only narrows the Product Grade dropdown's options, never a
    separate KPI scope.

    CR-16 (Consolidate Overview Dashboard Filters into a Unified Layout,
    2026-08-13): removed that "Advanced filter (optional)" expander -
    Product Family now sits directly in the visible filter area, on its
    own second row alongside Product Grade and Date range (Row 1: Plant,
    Production Method, Production Unit / Cell; Row 2: Product Family,
    Product Grade, Date range), so all six filters are visible without
    an extra click. This is presentation-only: every cascading rule and
    KPI-scoping rule below (including Product Family narrowing Product
    Grade without independently scoping any KPI) is unchanged from CR-02.

    KPI aggregation rules (CR-02 section 6): the old "Meters produced /
    Kg produced" cards assumed a Flexible Foam/continuous-slabstock
    production model and are removed outright. In their place, a single
    "Output Quantity and Unit" card renders a number for the runs scoped
    by the filters above and the date range, using only recorded
    ProductionOutputSummary.actual_quantity rows (WP7 Phase 4 cutover,
    2026-08-14, per Charlie's Downstream Reader Cutover Execution
    Instruction section 6 - see analytics.production_output_totals()).
    This replaces the original CR-02 restriction to "a single Production
    Method whose runs have conveyor-speed/tunnel-geometry data" - that
    restriction existed only because the old analytics.
    compute_runtime_output() geometry formula could only ever produce a
    value for continuous, tunnel-based production (in practice, PM-200).
    ProductionOutputSummary is method-agnostic (any Production Method's
    runs can carry a recorded output row), so the KPI no longer requires
    a single Production Method to be selected - it still, however, never
    sums across different recorded units (CR-02 section 8's "meaningless
    mixed-unit total" prohibition still applies, now enforced by
    production_output_totals() grouping by unit_id instead of the old
    single-formula-implies-single-unit assumption) - if the scoped runs'
    recorded output spans more than one unit, the card explains why no
    single figure is shown instead of guessing which one to display. A
    run with no ProductionOutputSummary row, or one recorded without an
    Actual quantity yet, contributes nothing and is never inferred from
    geometry - compute_runtime_output() keeps zero authority over this
    card as of Phase 4; it remains only as the Production Run page's own
    legacy "Calculated output" display, unrelated to this KPI. Every
    other KPI ("cross-method comparable" per section 6 - runs, tests,
    issues, samples, trials, active grades) is scoped consistently to the
    same Plant/Method/Unit/Grade filters instead of being unscoped
    app-wide totals as before.
    """
    page_setup("Overview")
    init_db()
    require_login()
    logout_button()

    header_logo, header_text = st.columns([1, 6])
    with header_logo:
        st.image(LOGO_PATH, width=90)
    with header_text:
        st.title("PI3 — Rigid Foam Intelligence")
        st.caption(
            "Plant Intelligence Dashboard | PI3 Plant Edition, Rigid Foam | "
            "HTC Global Co. Ltd"
        )
    render_function_action_intro(
        function_text=(
            "This dashboard provides a snapshot of production activity, quality, performance, and "
            "trials across the selected Plant, Production Method, Production Unit, Product Grade, "
            "and date range. Production and performance indicators follow the selected Production "
            "Method and its applicable units and process logic."
        ),
        action_text=(
            "Select the Plant and Production Method first, then narrow the view by Production Unit, "
            "Product Grade, and date range. Use the navigation to open the underlying production, "
            "quality, sample, reporting, and Industrial Intelligence records."
        ),
    )

    session = get_session()

    # --- Unified filter area (CR-16, 2026-08-13, per Charlie's
    # "CR16_Consolidate_Overview_Dashboard_Filters_into_Unified_Layout.docx"):
    # replaces the old "Advanced filter (optional)" expander (Product
    # Family alone) plus a separate 5-column primary row with one visible
    # two-row, three-column filter area - Row 1: Plant, Production Method,
    # Production Unit / Cell; Row 2: Product Family, Product Grade, Date
    # range. This is a presentation-only change: every cascading rule
    # below is byte-for-byte the same logic CR-02 established (Plant ->
    # Production Method -> Production Unit / Cell -> Product Grade, with
    # Product Family narrowing Product Grade only, never an independent
    # KPI scope) - only the widget layout moved. -------------------------
    row1_col1, row1_col2, row1_col3 = st.columns(3)

    plants = session.query(Plant).all()
    with row1_col1:
        plant_filter = st.selectbox(
            "Plant", [None] + plants, format_func=lambda p: "All plants" if p is None else p.name
        )

    method_options = (
        activated_methods_for_plant(session, plant_filter.id) if plant_filter
        else all_production_methods(session)
    )
    with row1_col2:
        method_filter = st.selectbox(
            "Production Method", [None] + method_options,
            format_func=lambda m: "All Production Methods" if m is None else m.name,
        )

    if plant_filter and method_filter:
        machine_options = machines_for_plant_and_method(session, plant_filter.id, method_filter.id)
    elif plant_filter:
        machine_options = machines_for_plant_across_activated_methods(session, plant_filter.id)
    elif method_filter:
        machine_options = session.query(Machine).filter(Machine.production_method_id == method_filter.id).all()
    else:
        machine_options = session.query(Machine).all()
    with row1_col3:
        machine_filter = st.selectbox(
            "Production Unit / Cell", [None] + machine_options,
            format_func=lambda m: "All units" if m is None else m.name,
        )

    row2_col1, row2_col2, row2_col3 = st.columns(3)

    # Product Family (CR-02: a commercial classification, not part of the
    # primary operating hierarchy - only narrows Product Grade below,
    # never a separate KPI scope; CR-16: moved out of the removed
    # "Advanced filter" expander into this same visible row as Product
    # Grade so their relationship is immediately understandable).
    with row2_col1:
        family_filter = st.selectbox(
            "Product Family", [None] + session.query(ProductFamily).all(),
            format_func=lambda f: "All product families" if f is None else f.name,
            help="Optional classification - narrows Product Grade below, does not scope KPIs on its own.",
        )

    # Plant scoping is applied whenever a Plant is picked (via the grade's
    # ProductFamily.plant_id), independently of Method/Unit, since
    # ProductionMethod is a global controlled vocabulary shared across
    # plants - filtering grades by method alone would otherwise leak in
    # another plant's machines that happen to share the same method.
    grades_query = session.query(FoamGrade)
    if plant_filter:
        grades_query = grades_query.join(ProductFamily, FoamGrade.product_family_id == ProductFamily.id).filter(
            ProductFamily.plant_id == plant_filter.id
        )
    if machine_filter:
        grades_query = grades_query.filter(FoamGrade.machines.any(Machine.id == machine_filter.id))
    elif method_filter:
        grades_query = grades_query.filter(FoamGrade.machines.any(Machine.production_method_id == method_filter.id))
    if family_filter:
        grades_query = grades_query.filter(FoamGrade.product_family_id == family_filter.id)
    grades = grades_query.all()
    with row2_col2:
        grade_filter = st.selectbox(
            "Product Grade", [None] + grades, format_func=lambda g: "All grades" if g is None else g.grade_name
        )

    with row2_col3:
        date_range = st.date_input(
            "Date range",
            value=(dt.date(dt.date.today().year, 1, 1), dt.date.today()),
            help="Defaults to year-to-date. Scopes the Output Quantity and Unit KPI below.",
        )
    # st.date_input's 2-tuple can momentarily be a 1-tuple while the user
    # has only picked a start date - guarded here rather than crashing.
    range_start, range_end = (date_range if len(date_range) == 2 else (None, None))

    st.divider()

    # --- Scoped Production Runs - the one query every KPI below reuses,
    # using the run's own plant_id/production_method_id/machine_id/
    # foam_grade_id columns directly (no joins needed). -------------------
    run_query = session.query(ProductionRun)
    if plant_filter:
        run_query = run_query.filter(ProductionRun.plant_id == plant_filter.id)
    if method_filter:
        run_query = run_query.filter(ProductionRun.production_method_id == method_filter.id)
    if machine_filter:
        run_query = run_query.filter(ProductionRun.machine_id == machine_filter.id)
    if grade_filter:
        run_query = run_query.filter(ProductionRun.foam_grade_id == grade_filter.id)
    scoped_runs = run_query.options(joinedload(ProductionRun.foam_grade)).all()
    scoped_run_ids = [r.id for r in scoped_runs]

    # Customer/Optimization Trials (lab-only workflows - db.SAMPLE_SOURCE_
    # TYPES) have no Production Method or Production Unit of their own
    # (helpers.production_method_label() shows "N/A (lab trial)" for
    # exactly this reason) - they're scoped by Plant/Grade only, using
    # their own plant_id/foam_grade_id columns directly.
    def _trial_query(model):
        q = session.query(model)
        if plant_filter:
            q = q.filter(model.plant_id == plant_filter.id)
        if grade_filter:
            q = q.filter(model.foam_grade_id == grade_filter.id)
        return q

    customer_trials_q = _trial_query(CustomerTrial)
    optimization_trials_q = _trial_query(OptimizationTrial)
    customer_trials_count = customer_trials_q.count()
    optimization_trials_count = optimization_trials_q.count()
    active_trials = (
        customer_trials_q.filter(CustomerTrial.status != "Closed").count()
        + optimization_trials_q.filter(OptimizationTrial.status != "Closed").count()
    )

    # Quality tests/issues/samples fold in trial-sourced records too
    # (CR-02 section 6 lists these as "cross-method comparable") - but
    # only when no Production Method/Unit is selected, since a lab trial
    # can't be attributed to either and folding it into a method-specific
    # or unit-specific view would misrepresent that method's own figures.
    include_trials = method_filter is None and machine_filter is None
    customer_trial_ids = [t.id for t in customer_trials_q.all()] if include_trials else []
    optimization_trial_ids = [t.id for t in optimization_trials_q.all()] if include_trials else []

    def _scoped_count(model):
        return session.query(model).filter(
            or_(
                model.production_run_id.in_(scoped_run_ids),
                model.customer_trial_id.in_(customer_trial_ids),
                model.optimization_trial_id.in_(optimization_trial_ids),
            )
        )

    quality_results_q = _scoped_count(PhysicalPropertyResult)
    quality_issues_q = _scoped_count(QualityObservation)
    quality_tests_count = quality_results_q.count()
    quality_issues_count = quality_issues_q.count()
    recurring_issues_count = quality_issues_q.filter(QualityObservation.frequency == "Recurring").count()
    # Recomputed live via compute_pass_fail() rather than trusted from each
    # result's stored pass_fail column - see the same note in
    # analytics.property_results_dataframe. Keeps this KPI in sync with the
    # current tolerance rules immediately, with no separate recompute step.
    computed_verdicts = [
        compute_pass_fail(r.property_name, r.target_value, r.actual_value) for r in quality_results_q.all()
    ]
    known_verdicts = [v for v in computed_verdicts if v is not None]
    pass_count = known_verdicts.count("Pass")
    pass_rate = f"{round(100 * pass_count / len(known_verdicts))}%" if known_verdicts else "—"

    samples_count = _scoped_count(Sample).count()

    scoped_grade_ids = [grade_filter.id] if grade_filter else [g.id for g in grades]
    recipes_count = (
        session.query(RecipeVersion).filter(RecipeVersion.foam_grade_id.in_(scoped_grade_ids)).count()
        if scoped_grade_ids else 0
    )
    active_grades_count = len({r.foam_grade_id for r in scoped_runs})

    # Output Quantity and Unit (CR-02 section 6/7 KPI, cut over to
    # ProductionOutputSummary under WP7 Phase 4, 2026-08-14 - see
    # analytics.production_output_totals() and the docstring above for the
    # full rationale). No longer requires a single Production Method to be
    # selected - ProductionOutputSummary rows can exist for any method's
    # runs, unlike the retired compute_runtime_output() formula this
    # replaces. Still never sums across different recorded units.
    output_value, output_uom, output_note = None, None, None
    if not (range_start and range_end):
        output_note = "Pick a complete date range to compute output for this period."
    else:
        runs_in_range = [r for r in scoped_runs if r.run_date and range_start <= r.run_date <= range_end]
        run_ids_in_range = [r.id for r in runs_in_range]
        output_totals = analytics.production_output_totals(session, run_ids_in_range)
        totals_by_unit = output_totals["totals_by_unit"]
        if len(totals_by_unit) == 1:
            output_value = totals_by_unit[0]["actual_total"]
            output_uom = totals_by_unit[0]["unit_symbol"] or ""
        elif len(totals_by_unit) > 1:
            unit_list = ", ".join(sorted({t["unit_symbol"] or "unlabeled unit" for t in totals_by_unit}))
            output_note = (
                f"Recorded output for these runs spans more than one unit ({unit_list}) - narrow the "
                "filters above to a single Production Method or Product Grade to see one figure."
            )
        elif output_totals["runs_without_summary"] and run_ids_in_range:
            output_note = (
                "No Production Output has been recorded yet for the runs in this period - see the "
                "Production Output and Disposition tab on each run."
            )
        else:
            output_note = "No production runs in this period."

    # --- KPI cards, grouped for visual separation ------------------------
    st.subheader("Volume")
    v1, v2, v3, v4 = st.columns(4)
    v1.metric("Recipes", recipes_count)
    v2.metric("Production runs", len(scoped_runs))
    v3.metric("Active product grades", active_grades_count)
    v4.metric(
        "Output Quantity and Unit",
        f"{output_value:,.0f} {output_uom}" if output_value is not None else "—",
    )
    if output_note:
        st.caption(output_note)

    st.divider()

    st.subheader("Quality & Performance")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Quality tests", quality_tests_count)
    q2.metric("Quality issues", quality_issues_count)
    q3.metric("Recurring quality issues", recurring_issues_count)
    q4.metric("Quality test pass rate", pass_rate)

    st.divider()

    st.subheader("Trials & Samples")
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Samples", samples_count)
    t2.metric("Customer trials", customer_trials_count)
    t3.metric("Optimization trials", optimization_trials_count)
    t4.metric("Open customer/optimization trials", active_trials)

overview_page = st.Page(render_overview, title="Overview", icon="🏠", default=True)
report_page = st.Page("pages/21_Report.py", title="Reports", icon="🖨️")

# CR-01 (UI Navigation and Rigid-Foam Terminology for UAT), implemented
# 2026-08-10: sidebar restructured to Charlie's approved target structure -
# Production Method is now a first-class nav section (plant_setup_pages
# holds only Plants; production_method_pages holds the new Production
# Methods + Production Equipment pages plus Product Families & Product
# Grades, since equipment and grades both resolve inside a Production
# Method's context per CR-01). Formulations (Raw Materials, Recipes,
# Reference Formulations) stays its own section, reused as-is - CR-01
# treats these as shared/context-independent. See pages/1, 30, and 31's own
# docstrings for the page-level split rationale.
#
# CR-10 (Split Product Families and Product Grades into Separate Pages),
# implemented 2026-08-12: the single "Product Families & Product Grades"
# entry (formerly pages/2_Product_Family_Foam_Grade.py, two tabs) is
# replaced by two direct entries, in the exact order CR-10 section 3
# mandates (Production Methods, Production Equipment, Product Families,
# Product Grades) - see pages/2_Product_Families.py and
# pages/2_Product_Grades.py for the split page-level rationale, including
# the context handoff between them and the access_control key change.
plant_setup_pages = [
    ("plant_overview", st.Page("pages/1_Plant_Installation_Overview.py", title="Plants", icon="📍")),
]

production_method_pages = [
    ("production_methods", st.Page("pages/30_Production_Methods.py", title="Production Methods", icon="🧭")),
    ("plant_overview", st.Page("pages/31_Production_Equipment.py", title="Production Equipment", icon="🏭")),
    ("product_families", st.Page("pages/2_Product_Families.py", title="Product Families", icon="🧬")),
    ("product_grades", st.Page("pages/2_Product_Grades.py", title="Product Grades", icon="🏷️")),
]

# CR-13 (Split Suppliers into a Standalone Page), implemented 2026-08-12:
# "Suppliers" is added as its own direct entry, immediately after Raw
# Materials and still inside this same "Formulations" section - CR-13
# section 7 explicitly keeps the current section label unchanged for this
# CR, deferring any broader section rename/regroup to a later navigation
# decision. See pages/32_Suppliers.py's own module docstring for what
# moved out of pages/14_Raw_Materials.py and what (the supplier picker)
# deliberately stayed.
formulation_pages = [
    ("raw_materials", st.Page("pages/14_Raw_Materials.py", title="Raw Materials", icon="🧴")),
    ("suppliers", st.Page("pages/32_Suppliers.py", title="Suppliers", icon="🚚")),
    # CR-03 (Recipe Consolidation and Pending Review Status), implemented
    # 2026-08-10: the separate "Reference Formulations" nav entry/page is
    # removed per CR-03's target navigation table - imported scientific
    # formulations (RF-*, RFREF-*) now appear directly in the Recipes list
    # below, tagged with Approval Status = Pending Review, rather than
    # living behind their own sidebar item. See pages/3_Recipe_Version_
    # Record.py's own module docstring for the combined-list design.
    ("recipes", st.Page("pages/3_Recipe_Version_Record.py", title="Recipes", icon="📋")),
]

production_pages = [
    ("production_run", st.Page("pages/4_Production_Run_Trial_Record.py", title="Production Runs", icon="⚙️")),
]

# CR-17 (Restore Customer Trials & Samples to Samples & Trials Navigation,
# 2026-08-13): Customer Trials & Samples lives here again, between
# Production Samples and Optimization Trials & Samples - its pre-CR-14
# position, per Stefan's direction that the trial page belongs with the
# application's trial/sample workflows, not the Customers master section.
# This is a navigation-only correction: the customer_trials page key,
# its access-control behavior, and every CR-14 Customer-relationship
# behavior (customer selection, customer_id linkage, customer_name
# synchronization, CSV/Excel import auto-create) are unchanged - see
# pages/11_Customer_Trials.py itself, which was not touched by this CR.
experiment_pages = [
    ("samples_conditioning", st.Page("pages/9_Samples_Conditioning.py", title="Production Samples", icon="🧊")),
    ("customer_trials", st.Page("pages/11_Customer_Trials.py", title="Customer Trials & Samples", icon="🤝")),
    ("optimization_trials", st.Page("pages/12_Optimization_Trials.py", title="Optimization Trials & Samples", icon="🚀")),
]

# CR-14 (Create Customers Section and Lightweight Customer Master),
# implemented 2026-08-12: introduced a dedicated "Customers" section for
# the new Customers master page. CR-14 originally also moved Customer
# Trials & Samples into this section (second, after Customers) - CR-17
# (2026-08-13) reversed that placement per Stefan's direction (see
# experiment_pages above): Customers now holds only the Customers master
# page itself, its sole reason for existing. The CR-14 Customer master
# and its relationship to Customer Trial records are otherwise completely
# unaffected by this navigation correction.
customer_pages = [
    ("customers", st.Page("pages/33_Customers.py", title="Customers", icon="🧾")),
]

# Split out from Production 2026-08-04 per user direction (segregation of
# duties: quality inspection/testing shouldn't sit under the same nav
# section as the production floor that made the batch). Ordered after
# Samples & Trials since a result/issue is always recorded against a
# sample, and a sample can come from any of the 3 pages in that section.
# Titles updated 2026-08-10 per CR-01's mandatory terminology table
# ("Quality Test Result" -> "Test Results", "Quality Issue" -> "Quality
# Issues" - plural menu wording; page content may still say the singular
# term where it refers to one specific record).
quality_pages = [
    ("quality_test_result", st.Page("pages/5_Physical_Property_Result.py", title="Test Results", icon="📏")),
    ("quality_issue", st.Page("pages/6_Quality_Observation.py", title="Quality Issues", icon="🔍")),
]

# The value of PI3 Plant Edition is the join that already exists in the
# schema: recipe, machine settings, and physical property / quality
# results all keyed to the same production run. These pages are that join
# put to work - named after what they actually do, not branded as "AI".
# Titles updated 2026-08-10 per CR-01's mandatory terminology table
# ("Machine Settings vs Physical Properties" -> "Process Parameters vs
# Product Properties", "Machine Settings Optimization" -> "Process
# Parameter Optimization"). CR-01 explicitly retains this whole section
# as-is otherwise ("retain existing pages with PM context/filtering as
# already built") - no restructuring here beyond the title changes.
industrial_intelligence_pages = [
    ("recipe_optimization", st.Page("pages/15_Recipe_Optimization.py", title="Recipe Optimization", icon="🧪")),
    ("trend_analysis", st.Page("pages/16_Trend_Analysis.py", title="Trend Analysis", icon="📈")),
    (
        "machine_settings_correlation",
        st.Page(
            "pages/17_Process_Property_Correlation.py",
            title="Process Parameters vs Product Properties Correlation",
            icon="🔗",
        ),
    ),
    ("root_cause_assistant", st.Page("pages/18_Root_Cause_Assistant.py", title="Root-Cause Assistant", icon="🩺")),
    ("machine_settings_optimization", st.Page("pages/19_Machine_Settings_Optimization.py", title="Process Parameter Optimization", icon="⚙️")),
    ("expert_notes", st.Page("pages/20_Expert_Notes.py", title="Expert Notes", icon="🧠")),
]

admin_pages = [
    ("user_roles_admin", st.Page("pages/24_User_Roles.py", title="User Roles", icon="🔑")),
]

platform_admin_pages = [
    ("companies_admin", st.Page("pages/23_Companies.py", title="Companies", icon="🏢")),
    ("subscription_types_admin", st.Page("pages/22_Subscription_Types.py", title="Subscription Types", icon="🎟️")),
    ("default_user_roles_admin", st.Page("pages/26_Default_User_Roles.py", title="Default User Roles", icon="🗝️")),
    ("user_accounts_admin", st.Page("pages/25_User_Accounts.py", title="User Accounts", icon="👤")),
    ("pi3_ai_connectivity", st.Page("pages/10_PI3_AI_Connectivity.py", title="PI3 Connectivity", icon="🤖")),
    ("performance_admin", st.Page("pages/27_Performance.py", title="Performance", icon="⚡")),
    ("pilot_analysis_admin", st.Page("pages/28_Pilot_Analysis.py", title="Company Analysis", icon="🔬")),
]

# CR-01 target sidebar structure (2026-08-10): Overview (Overview, Reports
# - handled separately below as top_pages, not a nav_sections entry) / Plant
# Setup (Plants) / Production Methods (Production Methods, Production
# Equipment, Product Families & Product Grades) / Formulations (Raw
# Materials, Recipes, Reference Formulations) / Production (Production
# Runs) / Samples & Trials / Quality (Test Results, Quality Issues) /
# Industrial Intelligence (unchanged). Company Admin stays as-is - out of
# CR-01's scope (rigid-foam terminology/navigation for the operational app),
# not a customer-facing production-method concept. CR-10 (2026-08-12) later
# split "Product Families & Product Grades" into its own two direct entries
# within this same Production Methods section - see production_method_pages
# above.
#
# CR-14 (Create Customers Section and Lightweight Customer Master),
# implemented 2026-08-12: a new "Customers" section is inserted between
# Production and Samples & Trials, holding the new Customers master page.
#
# CR-17 (Restore Customer Trials & Samples to Samples & Trials Navigation),
# implemented 2026-08-13: CR-14 had also moved Customer Trials & Samples
# into the new Customers section (second, after Customers). Stefan
# clarified the trial page belongs with the application's trial/sample
# workflows, not the Customers master section, so CR-17 restores it to
# Samples & Trials in its pre-CR-14 position - between Production Samples
# and Optimization Trials & Samples (see experiment_pages/customer_pages
# above). Customers now contains only the Customers master page itself.
#
# CR-05 (Default User Role Inheritance and Platform Admin Separation),
# implemented 2026-08-11: the nav section for the platform-owner-only pages
# (Companies, Subscription Types, Default User Roles, User Accounts, PI3
# Connectivity, Performance, Company Analysis) was literally labeled
# "Application Admin" - a legacy term CR-05 requires replaced with "Platform
# Admin" everywhere it means platform-level HTC administration. This is the
# one place that term was still customer/HTC-staff-visible; renamed here.
nav_sections_with_keys = {
    "Plant Setup": plant_setup_pages,
    "Production Methods": production_method_pages,
    "Formulations": formulation_pages,
    "Production": production_pages,
    "Customers": customer_pages,
    "Samples & Trials": experiment_pages,
    "Quality": quality_pages,
    "Industrial Intelligence": industrial_intelligence_pages,
    "Company Admin": admin_pages,
    "Platform Admin": platform_admin_pages,
}

# Nav visibility: a fresh, unauthenticated script run has no role/company in
# session_state yet (require_login() only populates it once a page actually
# runs, further down) - show everything unfiltered in that case, since every
# page still gates its own content behind require_login()/require_role().
# Once logged in, narrow by the user's role (page_key deny-list) and their
# company's subscription (feature flags) - see access_control.py.
init_db()
_nav_session = get_session()
_is_authenticated = bool(st.session_state.get("authenticated"))
_is_platform_owner = bool(st.session_state.get("is_platform_owner", False)) if _is_authenticated else True
_is_super_admin = bool(st.session_state.get("is_super_admin", False)) if _is_authenticated else True
_denied_keys = denied_page_keys(_nav_session, st.session_state.get("role_id")) if _is_authenticated else set()
_company_id = st.session_state.get("company_id") if _is_authenticated else None
_subscription = None
if _company_id:
    _company = _nav_session.get(Company, _company_id)
    _subscription = _company.subscription_type if _company else None

def _visible(key):
    return page_visible(
        key, is_platform_owner=_is_platform_owner, subscription=_subscription, denied_keys=_denied_keys,
        is_super_admin=_is_super_admin,
    )


nav_sections = {
    section_name: [page for key, page in pages if _visible(key)]
    for section_name, pages in nav_sections_with_keys.items()
}
nav_sections = {name: pages for name, pages in nav_sections.items() if pages}

# Overview is the landing dashboard, not a gated feature - always shown once
# logged in. Report is a subscription-gated feature (reports_enabled), so it
# goes through the same page_visible() check as everything else.
top_pages = [overview_page]
if _visible("report"):
    top_pages.append(report_page)

# position="hidden" turns off Streamlit's built-in nav widget so we can draw
# our own sidebar from scratch below. This is the only reliable way to get
# custom content (logo + version) to appear ABOVE the page links: Streamlit
# always renders its automatic nav menu first, before any other sidebar
# content, regardless of where in the script that content is written.
pg = st.navigation(
    {"PI3 Plant Edition - Rigid Foam": top_pages, **nav_sections},
    position="hidden",
)

with st.sidebar:
    logo_col, version_col = st.columns([1, 1.4], vertical_alignment="center")
    logo_col.image(LOGO_PATH, width=140)
    with version_col:
        st.markdown("**PI3 Plant Edition - Rigid Foam**")
        st.caption(f"v{APP_VERSION}")
    st.divider()

    # CR-01 (2026-08-10): give the Overview/Reports group the same visible
    # "Overview" section caption every other group gets, matching CR-01's
    # approved sidebar structure table exactly (top_pages itself stays a
    # separate list from nav_sections, since Overview is never gated the
    # way every other section's pages are).
    st.caption("Overview")
    for page in top_pages:
        st.page_link(page)
    for section_name, pages in nav_sections.items():
        st.caption(section_name)
        for page in pages:
            st.page_link(page)

_page_load_t0 = time.perf_counter()
try:
    pg.run()
    # Reaching here means this rerun's page script ran to completion using
    # the cached session without SQLAlchemy objecting - clear any earlier
    # recovery count so a *future* burst of corruption (see except below)
    # can still be auto-recovered from, rather than only ever once per tab.
    st.session_state["_sa_session_recovery_attempts"] = 0
except sa_exc.InvalidRequestError:
    # Production incident, 2026-08-05: a plain, ordinary .all() query on
    # Default User Roles crashed with sqlalchemy.exc.InvalidRequestError
    # from deep inside Session._connection_for_bind - not a bad query, a
    # broken Session. get_session() deliberately caches ONE SQLAlchemy
    # Session per browser tab across every rerun (see its docstring), but
    # a Session is not thread-safe, and Streamlit can cancel an in-flight
    # script run the moment a newer rerun supersedes it (e.g. two quick
    # clicks, or a slow network round trip). If that cancellation lands
    # mid-statement, the Session's internal transaction state machine is
    # left stuck in a state that refuses ALL further SQL - on any page,
    # not just the one that was interrupted - because the Session object
    # itself is broken, not the data or the query.
    #
    # There is nothing page-specific to fix: discard the cached session
    # (the next get_session() call builds a fresh one against a
    # pool_pre_ping-verified connection) and rerun so the user gets the
    # page they asked for instead of a crash.
    #
    # Raised from 1 to 2 attempts on 2026-08-17: production incident that
    # day showed two of these cancellations landing back-to-back in the
    # same tab (a burst of rapid clicks/reruns is exactly the trigger
    # described above), which exhausted a 1-attempt cap and surfaced the
    # raw crash to the user even though the underlying cause was still
    # just this same transient session corruption. _MAX_SESSION_RECOVERY_
    # ATTEMPTS stays finite (not unlimited) so a different, page-code-level
    # bug that happens to also raise InvalidRequestError can't silently
    # rerun forever instead of surfacing normally - it just tolerates a
    # short burst before giving up.
    attempts = st.session_state.get("_sa_session_recovery_attempts", 0)
    if attempts < _MAX_SESSION_RECOVERY_ATTEMPTS:
        st.session_state["_sa_session_recovery_attempts"] = attempts + 1
        st.session_state.pop("_sa_session", None)
        st.rerun()
    raise
finally:
    # Only touch the session if it's still the healthy one this rerun
    # started with - if the except branch above discarded it, there is no
    # transaction left to time/close, and touching the (broken, discarded)
    # local reference again would just recreate the same failure.
    if st.session_state.get("_sa_session") is _nav_session:
        # Page-load timing (added 2026-08-05, v2.0 performance audit): pg.run()
        # is the single choke point every page's script executes through, on
        # both a fresh navigation and every widget-triggered rerun - timing
        # around it here captures the real "how long did this page take"
        # metric for every page, with no per-page-file instrumentation needed.
        # Logged via the same session pg.run() itself used (get_session()
        # returns one session per browser tab - see db.py), then committed by
        # close_out_session() right below, same as any other write a page made
        # during this rerun. Uses _nav_session rather than a fresh get_session()
        # call so this still works even if the routed page's own script raised
        # partway through (the finally still runs) and left that session's
        # transaction in a state a NEW session wouldn't share.
        audit_log.log_page_load(_nav_session, pg.title, (time.perf_counter() - _page_load_t0) * 1000)
        # See db.py close_out_session(): every rerun of every page must end
        # with no open transaction left on the database, or a read-only page
        # view (Trend Analysis, Recipe Optimization, ...) leaves one sitting
        # idle for as long as the browser tab stays open - which has already
        # caused a real production incident (an 18-hour-old idle transaction
        # blocking a schema migration). The try/finally ensures this still
        # runs even if the routed page's script raised an exception.
        close_out_session()
