"""CR-12 (Align Rigid Foam Reporting Structure with Flexible Foam, 2026-08-12)
- regression coverage for the final reporting-allocation inventory.

CR-12's own research phase (see the CR-12 closeout package for the full
side-by-side matrix) established that Rigid Foam's reporting architecture
was ALREADY at structural parity with Flexible Foam before any code in
this file was written: the same 11 on-page Word-download locations, the
same 4 central Report-page report types, identical reports.py build/
render function signatures, and identical "Download Word" button wording
- with exactly two legitimate, already-justified rigid-only additions
(the WP3 Property Conformance Report - a 5th Report-page tab - and the
rigid branch of the Recipe Optimization Report). No missing on-page
download or missing Report-page coverage was found, so this file's job is
proof, not new feature code: every item in the final inventory must be
shown to actually generate, with zero skipped verification paths (CR-12
Sec.9), and the two apps' allocation must be shown to still match going
forward (the structural parity test at the bottom of this file).

Discovery this file relies on throughout (see Streamlit's own
streamlit.testing.v1.element_tree source): st.download_button's `data=`
argument is evaluated EAGERLY at script-run time, exactly like any other
Python call argument - not lazily on click. So an AppTest run that reaches
a `st.download_button(..., data=reports.render_X_docx(build_data(...)))`
line with `at.exception` empty has already, by construction, proven that
full build -> render chain executed successfully and produced a real
docx. Asserting the button is present via `at.download_button` is
therefore sufficient proof of "successfully generates" for every
auto-rendering report on this page - no simulated click is needed or
would prove anything a real click doesn't already cover here.

Two reports on views/3_Recipe_Version_Record.py (Recipe Formulation
Record, Where Used Report) are the only ones in the whole inventory NOT
reached by a plain page load - they're gated behind a custom
`clickable_table` row-selection widget backed by st.session_state, which
AppTest cannot click directly. Recipe Formulation Record is proven via
AppTest with the relevant st.session_state keys pre-set (a supported
AppTest pattern - see AppTest.session_state docs); Where Used Report is
proven via a direct build_where_used_report_data() / render_where_used_
report_docx() call instead, since that half of the report is plain
Python with no Streamlit dependency (see reports.py's own module
docstring precedent for build_pi3_qa_report_data).

Fixture note: a single rich, module-scoped fixture (ten production runs
spanning three weeks with varying Finalized-phase settings and Density
results, one quality issue, one sample per source type, one closed
Customer Trial, one closed Optimization Trial, one Expert Note, and a
second rigid-only grade with a GradeSpecification) is shared by every
page-load test in this file, rather than one bespoke fixture per page -
this is deliberately overlapping with (not a replacement for) the
narrower single-purpose fixtures already used elsewhere in this suite
(e.g. test_wp4_recipe_optimization_page_smoke.py's single-grade fixtures,
test_flat_pm_propagation_smoke.py's two-method fixture) - this file's own
job is reporting-generation proof specifically, across every report type
at once, which needs one fixture with enough breadth to reach all of them
in a single seed.
"""
import datetime as dt
import os
import random
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import db
import reports

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_DIR = os.path.join(APP_DIR, "views")


def _page(name):
    return os.path.join(PAGES_DIR, name)


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def _clear_analytics_caches():
    """Every @st.cache_data-decorated function app-wide is keyed by its
    argument VALUES, not by underlying DB state, and persists across
    AppTest instances within the same pytest process (analytics.py's
    run_settings_dataframe/property_results_dataframe/actual_usage_dataframe,
    _DATA_CACHE_TTL - task #346; tenant_scope.py's plant/family/grade/run/
    trial id-scoping helpers, _SCOPE_CACHE_TTL - task #206; access_control.
    denied_page_keys). All of these take a leading `_session`-named param.
    which Streamlit's cache_data deliberately excludes from the hash key
    (its underscore-prefix convention for "don't hash this argument") -
    so the cache key is built from the OTHER, small-integer arguments alone
    (company_id, plant_ids, family_ids, foam_grade_id, role_id, ...).

    Every fixture in this test suite drops and recreates the schema with
    db.Base.metadata.drop_all/create_all, so autoincrement primary keys
    restart at 1 each time - meaning this file's foam_grade_id=1 (or
    plant_ids=(1,), family_ids=(1,), ...) can collide with a DIFFERENT
    test file's own same-numbered ids created after a later reset, and a
    still-live cache entry would silently serve one file's stale result to
    another, unrelated test (observed directly: running this file
    immediately before or after test_cr11_tab_wording_compliance.py or
    test_flat_pm_propagation_smoke.py without this clear() intermittently
    failed several otherwise-passing tests in whichever file ran second,
    purely from cache-key reuse - never from this file's own fixture logic).
    Clearing every cache at the start of this fixture (before any of this
    file's own data is queried) guarantees no leftover cache entry from an
    earlier test file can leak in, and leaves nothing live afterward for a
    later file to inherit either."""
    import access_control
    import analytics
    import tenant_scope
    analytics.run_settings_dataframe.clear()
    analytics.property_results_dataframe.clear()
    analytics.actual_usage_dataframe.clear()
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()


@pytest.fixture(scope="module")
def rich_fixture():
    _clear_analytics_caches()
    db.init_db()
    _reset_schema()
    session = db.get_session()
    u = uuid.uuid4().hex[:8]
    random.seed(42)

    company = db.Company(name=f"CR12 Rich Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR12 Rich Plant {u}")
    session.add(plant); session.flush()
    method = db.ProductionMethod(controlled_id=f"PM-CR12-100-{u}", name=f"Discontinuous Factory Foaming {u}", sort_order=100)
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"CR12 Rich Machine {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR12 Rich Family {u}")
    session.add(family); session.flush()

    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR12 Rich Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    raw_material = db.RawMaterial(name=f"Polyol A {u}")
    session.add(raw_material); session.flush()
    session.add(db.RecipeComponent(
        recipe_version_id=recipe.id, raw_material_id=raw_material.id,
        raw_material_name=raw_material.name, role_in_formulation="Base Polyol", php=100,
    ))
    session.flush()

    # WP7 Phase 4 Process-Property Correlation (#978) / Process Parameter
    # Optimization (#979) cutover (2026-08-14): pages 17/19 now source
    # process-setting facts exclusively through analytics.
    # production_run_parameter_dataframe() (the dynamic ProcessSettingDefinition/
    # ProcessParameterValue catalogue), not the legacy ProductionPhase columns
    # seeded below (kept for other, still-legacy-reading fixtures/tests in
    # this same file, e.g. the trend/root-cause pages' own settings paths).
    # Without a matching dynamic-catalogue definition + Actual values, pages
    # 17/19's ranked correlation table comes back empty and both pages
    # st.stop() before reaching their Word-download button - so one Process
    # Setting definition (mirroring the legacy mixer_rpm values below) is
    # seeded here, scoped to this fixture's Production Method via
    # ProcessSettingApplicability, per the seeding pattern established in
    # tests/test_wp7_phase4_root_cause_cutover.py's _seed_definition/_add_actual
    # helpers.
    mixer_rpm_def = db.ProcessSettingDefinition(
        controlled_id=f"PS-CR12-{u}", name=f"CR12 Mixer RPM {u}",
        data_type="Float", parameter_category="Process Setting",
    )
    session.add(mixer_rpm_def); session.flush()
    session.add(db.ProcessSettingApplicability(
        setting_definition_id=mixer_rpm_def.id, production_method_id=method.id, machine_id=None,
        controllable=True, analytics_eligible=True,
    ))
    session.flush()

    runs = []
    base_date = dt.date(2026, 6, 1)
    for i in range(10):
        run = db.ProductionRun(
            plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
            run_date=base_date + dt.timedelta(days=i * 3), batch_reference=f"CR12-B{i}-{u}",
            production_method_id=method.id,
        )
        session.add(run); session.flush()
        mixer_rpm_value = 1000 + i * 10 + random.uniform(-5, 5)
        session.add(db.ProductionPhase(
            production_run_id=run.id, phase_name="Finalized",
            mixer_rpm=mixer_rpm_value,
            conveyor_speed=5.0 + i * 0.1, air_pressure_bar=2.0 + i * 0.05,
        ))
        session.add(db.ProcessParameterValue(
            setting_definition_id=mixer_rpm_def.id, production_run_id=run.id,
            snapshot_type="Actual", numeric_value=mixer_rpm_value, source="Test seed",
        ))
        session.add(db.PhysicalPropertyResult(
            production_run_id=run.id, property_name="Density", target_value=35.0,
            actual_value=35.0 + random.uniform(-2, 2) + i * 0.05, unit="kg/m3",
            tested_at=dt.datetime.combine(run.run_date, dt.time(10, 0)),
        ))
        runs.append(run)
    session.flush()

    obs = db.QualityObservation(
        production_run_id=runs[-1].id, observation_type="Collapse", severity="High",
        frequency="Isolated", observed_at=dt.datetime.combine(runs[-1].run_date, dt.time(12, 0)),
    )
    session.add(obs); session.flush()

    sample = db.Sample(production_run_id=runs[-1].id, zone_label="Core", sample_ts=dt.datetime.combine(runs[-1].run_date, dt.time(11, 0)))
    session.add(sample); session.flush()

    cust_trial = db.CustomerTrial(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        customer_name=f"Acme {u}", status="Closed", date_closed=dt.date(2026, 7, 1),
        trial_date=dt.date(2026, 6, 25),
    )
    session.add(cust_trial); session.flush()
    opt_trial = db.OptimizationTrial(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        improvement_initiative_reference=f"INIT-{u}", status="Closed", date_closed=dt.date(2026, 7, 2),
        trial_date=dt.date(2026, 6, 26),
    )
    session.add(opt_trial); session.flush()
    session.add(db.Sample(customer_trial_id=cust_trial.id, zone_label="Core", sample_ts=dt.datetime(2026, 6, 26, 9, 0)))
    session.add(db.Sample(optimization_trial_id=opt_trial.id, zone_label="Core", sample_ts=dt.datetime(2026, 6, 27, 9, 0)))
    session.flush()

    session.add(db.ExpertNote(
        linked_entity_type="production_run", linked_entity_id=runs[-1].id,
        note_text="Collapse observed - reviewing mixer rpm drift.", author="Test Author",
    ))
    session.flush()

    # Rigid-only grade + GradeSpecification, for the WP3 Property Conformance
    # Report - Rigid's one legitimate report-inventory addition beyond
    # Flexible that has its own justification (rigid-only GradeSpecification
    # data with no Flexible equivalent).
    chem = db.Chemistry(controlled_id=f"CHM-CR12-010-{u}", name="Rigid polyurethane foam")
    session.add(chem); session.flush()
    rigid_grade = db.FoamGrade(
        pu_material_family_id=family.id, grade_name=f"CR12 Rigid Grade {u}", chemistry_id=chem.id, status="UAT_ONLY",
    )
    session.add(rigid_grade); session.flush()
    rigid_grade.machines = [machine]
    session.flush()
    rigid_recipe = db.RecipeVersion(foam_grade_id=rigid_grade.id, version_label="v1", approval_status="Draft", is_active=True)
    session.add(rigid_recipe); session.flush()

    propdef = session.query(db.PhysicalPropertyDefinition).filter_by(name="Thermal conductivity").first()
    if propdef is None:
        propdef = db.PhysicalPropertyDefinition(name="Thermal conductivity")
        session.add(propdef); session.flush()
    propmethod = db.PhysicalPropertyMethod(property_definition_id=propdef.id, method_code="ISO 8301", controlled_id=f"MTH-CR12-016-{u}")
    session.add(propmethod); session.flush()
    orientation = db.Orientation(controlled_id=f"ORI-CR12-THROUGH-{u}", name="Through-thickness")
    location = db.Location(controlled_id=f"LOC-CR12-CORE-{u}", name="Core")
    condition = db.TestCondition(controlled_id=f"CTX-CR12-INIT-{u}", name="Initial, 10C mean, 7 days")
    session.add_all([orientation, location, condition]); session.flush()
    session.add(db.GradeSpecification(
        foam_grade_id=rigid_grade.id, property_definition_id=propdef.id, property_method_id=propmethod.id,
        property_name="Thermal conductivity", target_operator="<=", target_value=0.030, unit="W/(m.K)",
        condition_id=condition.id, orientation_id=orientation.id, location_id=location.id,
    ))
    session.flush()
    rigid_run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=rigid_grade.id, machine_id=machine.id, recipe_version_id=rigid_recipe.id,
        run_date=dt.date(2026, 7, 1), batch_reference=f"RIGID-B0-{u}", production_method_id=method.id,
    )
    session.add(rigid_run); session.flush()
    rigid_sample = db.Sample(
        production_run_id=rigid_run.id, location_id=location.id, orientation_id=orientation.id,
        thickness_mm=60.0, age_hours=168.0, sample_scope="Core", sample_ts=dt.datetime(2026, 7, 2, 10, 0),
    )
    session.add(rigid_sample); session.flush()
    session.add(db.PhysicalPropertyResult(
        production_run_id=rigid_run.id, sample_id=rigid_sample.id, property_definition_id=propdef.id,
        property_method_id=propmethod.id, property_name="Thermal conductivity", actual_value=0.027,
        unit="W/(m.K)", test_method="ISO 8301", condition_id=condition.id, orientation_id=orientation.id,
        location_id=location.id, tested_at=dt.date(2026, 7, 3),
    ))
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "grade_id": grade.id,
        "recipe_id": recipe.id, "raw_material_id": raw_material.id,
        "run_ids": [r.id for r in runs], "obs_id": obs.id, "sample_id": sample.id,
        "cust_trial_id": cust_trial.id, "opt_trial_id": opt_trial.id,
        "rigid_grade_id": rigid_grade.id, "rigid_run_id": rigid_run.id,
    }
    session.close()
    yield ids
    # Teardown: clear again so nothing this module cached (e.g. this file's
    # own grade_id=1 results) can leak into the next test file's fixtures -
    # see _clear_analytics_caches()'s docstring above.
    _clear_analytics_caches()


def _run(page_filename, extra_secrets=None):
    at = AppTest.from_file(_page(page_filename), default_timeout=60)
    at.secrets["AUTH_DISABLED"] = True
    for k, v in (extra_secrets or {}).items():
        at.secrets[k] = v
    at.run()
    assert not at.exception, f"{page_filename} raised: {at.exception}"
    return at


def _dl_keys(at):
    return [b.key for b in at.download_button]


# ---------------------------------------------------------------------------
# Report page (21) - all 5 report types, each its own tab.
# ---------------------------------------------------------------------------

def test_batch_release_conformance_record_generates(rich_fixture):
    at = _run("21_Report.py")
    assert "run_report_docx" in _dl_keys(at)


def test_plant_period_summary_generates(rich_fixture):
    at = _run("21_Report.py")
    assert "period_report_docx" in _dl_keys(at)


def test_trial_closeout_report_generates_customer_trial(rich_fixture):
    at = _run("21_Report.py")
    radio = next(r for r in at.radio if r.key == "report_trial_source_type")
    assert radio.value == "Customer Trial", "Customer Trial should be the default trial-type radio choice"
    assert "trial_report_docx" in _dl_keys(at)


def test_trial_closeout_report_generates_optimization_trial(rich_fixture):
    at = _run("21_Report.py")
    radio = next(r for r in at.radio if r.key == "report_trial_source_type")
    radio.set_value("Optimization Trial")
    at.run()
    assert not at.exception, f"Report page raised after switching to Optimization Trial: {at.exception}"
    assert "trial_report_docx" in _dl_keys(at)


def test_sample_certificate_of_analysis_generates(rich_fixture):
    at = _run("21_Report.py")
    assert "sample_cert_docx" in _dl_keys(at)


def test_wp3_property_conformance_report_generates(rich_fixture):
    """Rigid Foam's one legitimate 5th Report-page tab beyond Flexible's 4 -
    see CR-12 closeout matrix for the justification (rigid-only
    GradeSpecification data, no Flexible equivalent)."""
    at = _run("21_Report.py")
    assert "wp3_conformance_docx" in _dl_keys(at)


def test_report_page_has_exactly_five_tabs(rich_fixture):
    at = _run("21_Report.py")
    labels = [t.label for t in at.tabs]
    assert labels == [
        "Batch Release / Conformance Record", "Plant / Period Summary", "Trial Closeout Report",
        "Sample Certificate of Analysis", "Property Conformance Report",
    ]


# ---------------------------------------------------------------------------
# On-page reports, pages 5/6/9/11/12/20 - auto-render once the page's own
# filter selection (all defaulted to "everything in scope") resolves to a
# non-empty result set.
# ---------------------------------------------------------------------------

def test_quality_test_result_report_generates(rich_fixture):
    at = _run("5_Physical_Property_Result.py")
    assert "quality_test_report_docx" in _dl_keys(at)


def test_quality_issue_report_generates(rich_fixture):
    at = _run("6_Quality_Observation.py")
    assert "quality_issue_report_docx" in _dl_keys(at)


def test_sample_report_generates_for_production_run_source(rich_fixture):
    at = _run("9_Samples_Conditioning.py")
    assert "sample_report_docx" in _dl_keys(at)


def test_sample_report_generates_for_customer_trial_source(rich_fixture):
    at = _run("11_Customer_Trials.py")
    assert "ct_sample_report_docx" in _dl_keys(at)


def test_sample_report_generates_for_optimization_trial_source(rich_fixture):
    at = _run("12_Optimization_Trials.py")
    assert "ot_sample_report_docx" in _dl_keys(at)


def test_expert_notes_report_generates(rich_fixture):
    at = _run("20_Expert_Notes.py")
    assert "expert_notes_report_docx" in _dl_keys(at)


# ---------------------------------------------------------------------------
# Recipe Formulation Record + Where Used Report (page 3) - the two report
# types not reached by a plain page load (see module docstring): gated
# behind a clickable_table row-selection widget AppTest cannot click.
# ---------------------------------------------------------------------------

def test_recipe_formulation_record_generates(rich_fixture):
    at = AppTest.from_file(_page("3_Recipe_Version_Record.py"), default_timeout=60)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["rv_selected_kind"] = "version"
    at.session_state["rv_selected_id"] = rich_fixture["recipe_id"]
    at.run()
    assert not at.exception, f"3_Recipe_Version_Record.py raised: {at.exception}"
    assert f"formrec_docx_{rich_fixture['recipe_id']}" in _dl_keys(at)


def test_where_used_report_generates(rich_fixture):
    session = db.get_session()
    data = reports.build_where_used_report_data(session, rich_fixture["raw_material_id"])
    assert data is not None
    docx_bytes = reports.render_where_used_report_docx(data)
    assert docx_bytes[:2] == b"PK", "Word (.docx) output should be a valid zip/OOXML package"
    session.close()


def test_pi3_qa_report_generates():
    """CR-12 closeout correction (2026-08-12, item 4): the matrix's own
    "PI3 Q&A Report (5 answer locations app-wide)" row had no test anywhere
    in the suite before this correction - a genuine access-path evidence
    gap, not caught earlier because build_pi3_qa_report_data()/render_
    pi3_qa_report_docx() need no live OpenAI call or AppTest page load to
    prove: per the module's own docstring precedent (see this file's
    header), the data-assembly half is plain Python with no Streamlit
    dependency, so it's proven the same direct-call way as Where Used
    Report just above - a real question/answer/tool_log shape (matching
    exactly what ai_assistant.ask_plant_question() returns) in, valid
    OOXML bytes out."""
    data = reports.build_pi3_qa_report_data(
        question="What drove the density variance on this run?",
        answer="1. Direct Answer\nDensity trended 2% below target on lots using Supplier B polyol.",
        tool_log=[{
            "tool": "query_plant_data",
            "sql": "SELECT * FROM production_runs WHERE id = 1",
            "rows_returned": 1,
            "rows": [{"id": 1, "batch_reference": "CR12-CORR-B1"}],
        }],
        page_context="Root-Cause Assistant",
        plant_name="CR-12 Correction Plant",
        foam_grade_name="CR-12 Correction Grade",
        asked_by="stefan.hermes@htcglobal.asia",
    )
    assert data["question"] and data["answer"] and data["tool_log"]
    docx_bytes = reports.render_pi3_qa_report_docx(data)
    assert docx_bytes[:2] == b"PK", "Word (.docx) output should be a valid zip/OOXML package"


# ---------------------------------------------------------------------------
# Industrial Intelligence pages (15-19) - each page's own deterministic
# Context/Analysis/Conclusions report, distinct from PI3's separate
# interpretation download (not part of CR-12's report-type inventory - see
# closeout matrix; both apps carry that PI3 feature identically already).
# ---------------------------------------------------------------------------

def test_recipe_optimization_report_generates(rich_fixture):
    at = _run("15_Recipe_Optimization.py", extra_secrets={
        "OPENAI_API_KEY": "sk-test-not-a-real-key", "PI3_VECTOR_STORE_ID": "vs_test_not_real",
    })
    keys = _dl_keys(at)
    assert any(k.startswith("recipe_opt_report_docx_") for k in keys)


def test_trend_analysis_report_generates(rich_fixture):
    at = _run("16_Trend_Analysis.py")
    keys = _dl_keys(at)
    assert any(k.startswith("trend_report_docx_") for k in keys)


def test_process_property_correlation_report_generates(rich_fixture):
    at = _run("17_Process_Property_Correlation.py")
    keys = _dl_keys(at)
    assert any(k.startswith("correlation_report_docx_") for k in keys)


def test_root_cause_comparison_report_generates(rich_fixture):
    at = _run("18_Root_Cause_Assistant.py")
    keys = _dl_keys(at)
    assert any(k.startswith("root_cause_report_docx_") for k in keys)


def test_machine_settings_optimization_report_generates(rich_fixture):
    at = _run("19_Machine_Settings_Optimization.py")
    keys = _dl_keys(at)
    assert any(k.startswith("mso_report_docx_") for k in keys)


# ---------------------------------------------------------------------------
# Structural parity check - the actual CR-12 contract going forward: the
# two apps' on-page download_button locations and reports.py build/render
# function inventories must keep matching exactly, except for the two
# already-justified rigid-only additions (WP3 Property Conformance Report,
# rigid Recipe Optimization Report branch). If a future change adds an
# on-page download or a report function to one app without the other,
# this test catches it - the actual regression-prevention value of CR-12,
# not just a one-time inventory snapshot.
# ---------------------------------------------------------------------------
import re

RIGID_APP_DIR = APP_DIR
FLEX_APP_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "PI3_Plant_Edition_App"))

RIGID_ONLY_REPORT_FUNCTIONS = {
    "build_rigid_recipe_optimization_report_data",
    "build_wp3_conformance_report_data",
    "render_wp3_conformance_report_docx",
}


def _pages_with_download_button(app_dir, pages_dirname):
    """pages_dirname differs per edition and must be passed explicitly.

    Rigid Foam renamed its page directory to "views" in v0.69.0 so that
    Streamlit's legacy auto-discovered-pages mode can never engage - see the
    block comment in app_rigid_foam.py. The Flexible edition still uses
    "pages". Hard-coding either name here would silently compare one
    edition's pages against a directory the other does not have.
    """
    pages_dir = os.path.join(app_dir, pages_dirname)
    found = set()
    for fname in os.listdir(pages_dir):
        if not fname.endswith(".py"):
            continue
        with open(os.path.join(pages_dir, fname), encoding="utf-8") as f:
            if "download_button" in f.read():
                found.add(fname)
    return found


def _report_function_names(app_dir):
    with open(os.path.join(app_dir, "reports.py"), encoding="utf-8") as f:
        content = f.read()
    return set(re.findall(r"^def (build_\w+|render_\w+)\(", content, re.MULTILINE))


@pytest.mark.skipif(not os.path.isdir(FLEX_APP_DIR), reason="Flexible Foam sibling app not present in this checkout")
def test_on_page_download_locations_match_flexible_app():
    rigid_pages = _pages_with_download_button(RIGID_APP_DIR, "views")
    flex_pages = _pages_with_download_button(FLEX_APP_DIR, "pages")
    assert rigid_pages == flex_pages, (
        "Rigid Foam's on-page Word-download locations no longer match Flexible Foam's - "
        f"rigid-only: {rigid_pages - flex_pages}, flexible-only: {flex_pages - rigid_pages}. "
        "Per CR-12, any new on-page download added to one app belongs in both, or needs a "
        "documented, justified exception recorded in the CR-12 comparison matrix."
    )


@pytest.mark.skipif(not os.path.isdir(FLEX_APP_DIR), reason="Flexible Foam sibling app not present in this checkout")
def test_report_function_inventory_matches_flexible_app_except_justified_additions():
    rigid_functions = _report_function_names(RIGID_APP_DIR)
    flex_functions = _report_function_names(FLEX_APP_DIR)
    rigid_only = rigid_functions - flex_functions
    flex_only = flex_functions - rigid_functions
    assert rigid_only == RIGID_ONLY_REPORT_FUNCTIONS, (
        f"Expected Rigid Foam's only report-function additions beyond Flexible to be "
        f"{RIGID_ONLY_REPORT_FUNCTIONS}, got {rigid_only} - see CR-12 closeout matrix for "
        "the justification each addition needs."
    )
    assert not flex_only, (
        f"Flexible Foam has report function(s) Rigid Foam is missing: {flex_only} - this is "
        "exactly the gap CR-12 was written to close."
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
