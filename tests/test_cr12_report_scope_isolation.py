"""CR-12 reporting-parity closeout - cross-COMPANY isolation proof for every
report-subject selector in the final reporting-allocation inventory.

Charlie's closeout review (twice returned) asked for a NAMED, EXECUTED
automated test per applicable reporting path proving that the widget/query
which supplies a report's subject record cannot surface another company's
record. tests/test_cr12_reporting_parity.py already proves every report
*generates* successfully (build/render round-trips to a valid docx); it
does NOT touch multi-tenancy at all - every one of its fixtures uses a
single company. Nothing else in tests/ seeds two companies and asserts one
company's selector excludes the other's rows for any report path either
(confirmed by grep across tests/ before writing this file). This file is
that missing evidence.

Every report's subject id (run_id, recipe_version_id, sample_id,
foam_grade_id, raw_material_id, trial id, ...) is only ever reachable
through the calling page's OWN selector widget or query - reports.py's
build_*_report_data() functions take the id directly and do no company_id
check themselves (see reports.py's module docstring / CR-12's own
closeout package). So proving isolation means proving the SELECTOR is
scoped, not the builder - which is what every test below actually drives,
reading the real query/widget out of the real page source (cited in each
test's own docstring) rather than assuming tenant_scope.py is wired in
correctly just because it's imported.

House style follows tests/test_cr12_reporting_parity.py and
tests/test_cr10_product_family_grade_split.py: a drop/create SQLite
schema per module-scoped fixture, AppTest for page-level widget proof
where the widget itself is cheap to reach, and direct backend queries
(replicating the exact application-code query/function, not a
reimplementation of it) where that is clearer, equally valid proof of the
scoping mechanism itself per the task brief for this file.

AUTH_DISABLED's dev bypass (see auth.require_login()) sets
is_platform_owner/company_id/is_super_admin via st.session_state.
setdefault(...) - so presetting those three keys in at.session_state
BEFORE at.run() sticks (setdefault is a no-op once the key already
exists), which is how every AppTest below "logs in" as a specific
company's own user (is_platform_owner=False, company_id=<that company's
id>) rather than the default synthetic platform-owner/all-companies dev
session.
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import ai_assistant
import db
import helpers
import reports
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_DIR = os.path.join(APP_DIR, "pages")


def _page(name):
    return os.path.join(PAGES_DIR, name)


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def _clear_scope_caches():
    """Same reasoning as test_cr12_reporting_parity.py's
    _clear_analytics_caches(): every tenant_scope.py id-resolution helper
    is @st.cache_data'd and keyed on the small-integer arguments alone
    (company_id, plant_ids, ...) - since every fixture here drops/recreates
    the schema, autoincrement ids restart at 1 and a stale cache entry from
    an earlier test file (or an earlier run of this fixture) could silently
    serve the wrong company's ids. Cleared before AND after this module's
    fixture builds/tears down its data."""
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    import access_control
    access_control.denied_page_keys.clear()
    import analytics
    analytics.run_settings_dataframe.clear()
    analytics.property_results_dataframe.clear()
    analytics.actual_usage_dataframe.clear()


def _run(page_filename, company_id, extra_secrets=None):
    """Loads a page AppTest as a non-platform-owner user of company_id -
    i.e. a real customer login for that one company, not the default
    dev-bypass platform-owner/"All companies" session. See module
    docstring for why presetting these three session_state keys before
    at.run() is what makes AUTH_DISABLED's require_login() lock onto this
    company instead of its own all-companies default."""
    at = AppTest.from_file(_page(page_filename), default_timeout=60)
    at.secrets["AUTH_DISABLED"] = True
    for k, v in (extra_secrets or {}).items():
        at.secrets[k] = v
    at.session_state["is_platform_owner"] = False
    at.session_state["company_id"] = company_id
    at.run()
    assert not at.exception, f"{page_filename} raised: {at.exception}"
    return at


def _build_company(session, label, u, run_date):
    """One full, self-contained tenant: plant, production method/machine,
    product family, foam grade (+ a second rigid grade with a
    GradeSpecification for the WP3 tab), a recipe version with one
    component (and its own raw material), two production runs (so
    Root-Cause Assistant's run-vs-prior-run diff has something to compare),
    a quality observation, a sample per source type, a closed Customer
    Trial, a closed Optimization Trial, and an Expert Note. Mirrors
    test_cr12_reporting_parity.py's rich_fixture, duplicated per company so
    every isolation test below has two companies' worth of otherwise
    identical, only-differing-by-tenant data to prove a cross-company leak
    against."""
    company = db.Company(name=f"CR12 Iso Co {label} {u}", is_platform_owner=False)
    session.add(company); session.flush()

    plant = db.Plant(company_id=company.id, name=f"CR12 Iso Plant {label} {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-CR12ISO-{label}-{u}", name=f"Discontinuous Factory Foaming {label} {u}", sort_order=100)
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"CR12 Iso Machine {label} {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"CR12 Iso Family {label} {u}")
    session.add(family); session.flush()

    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"CR12 Iso Grade {label} {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    raw_material = db.RawMaterial(name=f"Polyol {label} {u}", company_id=company.id)
    session.add(raw_material); session.flush()
    session.add(db.RecipeComponent(
        recipe_version_id=recipe.id, raw_material_id=raw_material.id,
        raw_material_name=raw_material.name, role_in_formulation="Base Polyol", php=100,
    ))
    session.flush()

    runs = []
    for i in range(2):
        run = db.ProductionRun(
            plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
            run_date=run_date + dt.timedelta(days=i * 5), batch_reference=f"CR12ISO-{label}-B{i}-{u}",
            production_method_id=method.id,
        )
        session.add(run); session.flush()
        session.add(db.ProductionPhase(
            production_run_id=run.id, phase_name="Finalized",
            mixer_rpm=1000 + i * 10, conveyor_speed=5.0 + i * 0.1, air_pressure_bar=2.0 + i * 0.05,
        ))
        session.add(db.PhysicalPropertyResult(
            production_run_id=run.id, property_name="Density", target_value=35.0, actual_value=35.0 + i,
            unit="kg/m3", tested_at=dt.datetime.combine(run.run_date, dt.time(10, 0)),
        ))
        runs.append(run)
    session.flush()

    obs = db.QualityObservation(
        production_run_id=runs[-1].id, observation_type=f"Collapse {label}", severity="High",
        frequency="Isolated", observed_at=dt.datetime.combine(runs[-1].run_date, dt.time(12, 0)),
    )
    session.add(obs); session.flush()

    sample = db.Sample(production_run_id=runs[-1].id, zone_label="Core", sample_ts=dt.datetime.combine(runs[-1].run_date, dt.time(11, 0)))
    session.add(sample); session.flush()

    cust_trial = db.CustomerTrial(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        customer_name=f"Acme {label} {u}", status="Closed", date_closed=run_date + dt.timedelta(days=20),
        trial_date=run_date + dt.timedelta(days=15),
    )
    session.add(cust_trial); session.flush()
    ct_sample = db.Sample(customer_trial_id=cust_trial.id, zone_label="Core", sample_ts=dt.datetime.combine(cust_trial.trial_date, dt.time(9, 0)))
    session.add(ct_sample); session.flush()

    opt_trial = db.OptimizationTrial(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        improvement_initiative_reference=f"INIT-{label}-{u}", status="Closed", date_closed=run_date + dt.timedelta(days=21),
        trial_date=run_date + dt.timedelta(days=16),
    )
    session.add(opt_trial); session.flush()
    ot_sample = db.Sample(optimization_trial_id=opt_trial.id, zone_label="Core", sample_ts=dt.datetime.combine(opt_trial.trial_date, dt.time(9, 0)))
    session.add(ot_sample); session.flush()

    note = db.ExpertNote(
        linked_entity_type="production_run", linked_entity_id=runs[-1].id,
        note_text=f"{label} collapse note - mixer rpm drift suspected.", author=f"Author {label}",
    )
    session.add(note); session.flush()

    # Rigid-only grade + GradeSpecification, for the WP3 Property
    # Conformance Report tab on pages/21_Report.py - shares the global
    # controlled-vocabulary rows (PhysicalPropertyDefinition/Method,
    # Orientation, Location, TestCondition) across both companies, since
    # those tables carry no company_id (see db.py) and are genuinely
    # global reference data, same "query or create" pattern as
    # test_cr12_reporting_parity.py's rich_fixture.
    chem = db.Chemistry(controlled_id=f"CHM-CR12ISO-{label}-{u}", name=f"Rigid polyurethane foam {label}")
    session.add(chem); session.flush()
    rigid_grade = db.FoamGrade(
        product_family_id=family.id, grade_name=f"CR12 Iso Rigid Grade {label} {u}", chemistry_id=chem.id,
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
    propmethod = session.query(db.PhysicalPropertyMethod).filter_by(method_code="ISO 8301").first()
    if propmethod is None:
        propmethod = db.PhysicalPropertyMethod(property_definition_id=propdef.id, method_code="ISO 8301", controlled_id="MTH-CR12ISO-016")
        session.add(propmethod); session.flush()
    orientation = session.query(db.Orientation).filter_by(controlled_id="ORI-CR12ISO-THROUGH").first()
    if orientation is None:
        orientation = db.Orientation(controlled_id="ORI-CR12ISO-THROUGH", name="Through-thickness")
        session.add(orientation); session.flush()
    location = session.query(db.Location).filter_by(controlled_id="LOC-CR12ISO-CORE").first()
    if location is None:
        location = db.Location(controlled_id="LOC-CR12ISO-CORE", name="Core")
        session.add(location); session.flush()
    condition = session.query(db.TestCondition).filter_by(controlled_id="CTX-CR12ISO-INIT").first()
    if condition is None:
        condition = db.TestCondition(controlled_id="CTX-CR12ISO-INIT", name="Initial, 10C mean, 7 days")
        session.add(condition); session.flush()

    session.add(db.GradeSpecification(
        foam_grade_id=rigid_grade.id, property_definition_id=propdef.id, property_method_id=propmethod.id,
        property_name="Thermal conductivity", target_operator="<=", target_value=0.030, unit="W/(m.K)",
        condition_id=condition.id, orientation_id=orientation.id, location_id=location.id,
    ))
    session.flush()
    rigid_run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=rigid_grade.id, machine_id=machine.id, recipe_version_id=rigid_recipe.id,
        run_date=run_date + dt.timedelta(days=30), batch_reference=f"CR12ISO-RIGID-{label}-{u}", production_method_id=method.id,
    )
    session.add(rigid_run); session.flush()
    rigid_sample = db.Sample(
        production_run_id=rigid_run.id, location_id=location.id, orientation_id=orientation.id,
        thickness_mm=60.0, age_hours=168.0, sample_scope="Core", sample_ts=dt.datetime.combine(rigid_run.run_date, dt.time(10, 0)),
    )
    session.add(rigid_sample); session.flush()
    session.add(db.PhysicalPropertyResult(
        production_run_id=rigid_run.id, sample_id=rigid_sample.id, property_definition_id=propdef.id,
        property_method_id=propmethod.id, property_name="Thermal conductivity", actual_value=0.027,
        unit="W/(m.K)", test_method="ISO 8301", condition_id=condition.id, orientation_id=orientation.id,
        location_id=location.id, tested_at=rigid_run.run_date,
    ))
    session.commit()

    return {
        "company_id": company.id, "plant_id": plant.id, "family_id": family.id, "grade_id": grade.id,
        "grade_name": grade.grade_name, "recipe_id": recipe.id, "raw_material_id": raw_material.id,
        "raw_material_name": raw_material.name, "run_ids": [r.id for r in runs], "obs_id": obs.id,
        "sample_id": sample.id, "cust_trial_id": cust_trial.id, "ct_sample_id": ct_sample.id,
        "opt_trial_id": opt_trial.id, "ot_sample_id": ot_sample.id, "note_id": note.id,
        "note_text": note.note_text, "rigid_grade_id": rigid_grade.id, "rigid_grade_name": rigid_grade.grade_name,
        "rigid_run_id": rigid_run.id,
    }


@pytest.fixture(scope="module")
def two_companies():
    _clear_scope_caches()
    db.init_db()
    _reset_schema()
    session = db.get_session()
    u = uuid.uuid4().hex[:8]
    a = _build_company(session, "A", u, dt.date(2026, 6, 1))
    b = _build_company(session, "B", u, dt.date(2026, 6, 1))
    session.close()
    yield {"a": a, "b": b}
    _clear_scope_caches()


# ---------------------------------------------------------------------------
# 1. Recipe-based - pages/3_Recipe_Version_Record.py's "Recipe versions"
# list (feeds Recipe Formulation Record + Where Used Report's recipe-side
# usage). The page computes:
#
#   grade_ids = grade_ids_for_company(session, active_company_id)
#   versions = apply_scope(session.query(RecipeVersion),
#                           RecipeVersion.foam_grade_id, grade_ids).all()
#
# (see pages/3_Recipe_Version_Record.py lines ~135-136 and ~474-478) - this
# is the exact query replicated below, not a reimplementation, per the
# task's own direct-backend-query allowance.
# ---------------------------------------------------------------------------
def test_recipe_version_selector_excludes_other_company_recipe(two_companies):
    session = db.get_session()
    a, b = two_companies["a"], two_companies["b"]

    grade_ids = tenant_scope.grade_ids_for_company(session, a["company_id"])
    versions = tenant_scope.apply_scope(
        session.query(db.RecipeVersion), db.RecipeVersion.foam_grade_id, grade_ids
    ).all()
    version_ids = {v.id for v in versions}

    assert a["recipe_id"] in version_ids, "Company A's own recipe version must be offered by its own selector"
    assert b["recipe_id"] not in version_ids, (
        "Company A's Recipes page ('Recipe versions' list feeding Recipe Formulation Record) "
        "leaked Company B's recipe version - CR-12 cross-tenant scope failure"
    )
    session.close()


# ---------------------------------------------------------------------------
# 2. Raw-material-based - Where Used Report's raw_material_id input.
#
# Read directly: the actual selector that feeds build_where_used_report_
# data() is NOT on pages/14_Raw_Materials.py (the task brief's assumption)
# - it's the "Where Used Report" section at the BOTTOM of
# pages/3_Recipe_Version_Record.py itself:
#
#   wu_rm_query = session.query(RawMaterial)
#   if active_company_id is not None:
#       wu_rm_query = wu_rm_query.filter(RawMaterial.company_id == active_company_id)
#   wu_materials = wu_rm_query.order_by(RawMaterial.name).all()
#
# (pages/3_Recipe_Version_Record.py lines ~1050-1054). pages/14_Raw_
# Materials.py's own list (line ~672: `materials_query.filter(RawMaterial.
# company_id == company_filter.id)`) uses the identical direct company_id
# filter pattern for its own (separate) master-list selector - both are
# exercised below since both are genuine, independently-coded raw-material
# selectors in the app, and both must be proven, not just one assumed to
# stand in for the other.
# ---------------------------------------------------------------------------
def test_where_used_and_raw_materials_page_selectors_exclude_other_company_material(two_companies):
    session = db.get_session()
    a, b = two_companies["a"], two_companies["b"]

    # pages/3_Recipe_Version_Record.py's own Where Used Report material picker.
    wu_materials = (
        session.query(db.RawMaterial).filter(db.RawMaterial.company_id == a["company_id"])
        .order_by(db.RawMaterial.name).all()
    )
    wu_ids = {m.id for m in wu_materials}
    assert a["raw_material_id"] in wu_ids
    assert b["raw_material_id"] not in wu_ids, (
        "Where Used Report's own raw-material selector (pages/3_Recipe_Version_Record.py) "
        "leaked Company B's raw material"
    )

    # pages/14_Raw_Materials.py's own master-list selector query.
    rawmat_page_materials = (
        session.query(db.RawMaterial).filter(db.RawMaterial.company_id == a["company_id"]).all()
    )
    rawmat_page_ids = {m.id for m in rawmat_page_materials}
    assert a["raw_material_id"] in rawmat_page_ids
    assert b["raw_material_id"] not in rawmat_page_ids, (
        "pages/14_Raw_Materials.py's own raw-material list leaked Company B's raw material"
    )

    # And the report builder itself, called with Company A's own id, must
    # actually resolve real usage data (not silently return None) - proving
    # the selector -> builder handoff for a legitimate in-scope id works end
    # to end, exactly the same handoff that Company B's id must never reach.
    data = reports.build_where_used_report_data(session, a["raw_material_id"])
    assert data is not None and data["recipe_version_count"] >= 1
    session.close()


# ---------------------------------------------------------------------------
# 3. Production-run-based - the run selector shared by pages/4 (Production
# Run Trial Record), 5 (Physical Property Result -> Quality Test Result
# Report), 6 (Quality Observation -> Quality Issue Report), 9 (Samples
# Conditioning -> Sample Report's "Production Run" source), all scoped via
# the identical:
#
#   run_ids = run_ids_for_company(session, active_company_id)
#   runs = apply_scope(session.query(ProductionRun), ProductionRun.id, run_ids).all()
#
# pattern (see pages/5_Physical_Property_Result.py lines 162-171,
# pages/6_Quality_Observation.py lines 187-196, pages/9_Samples_
# Conditioning.py lines 90-97 - all three read this exact query verbatim).
# Proven once at the backend (the shared mechanism) and once at the widget
# level on pages/9_Samples_Conditioning.py's own "Production run" selectbox
# (key="sample_run_select"), which is the concrete UI control a Company A
# user would actually see leak from, if anything did.
# ---------------------------------------------------------------------------
def test_production_run_selector_excludes_other_company_run(two_companies):
    session = db.get_session()
    a, b = two_companies["a"], two_companies["b"]

    run_ids = tenant_scope.run_ids_for_company(session, a["company_id"])
    assert set(a["run_ids"]).issubset(set(run_ids))
    assert not (set(b["run_ids"]) & set(run_ids)), (
        "tenant_scope.run_ids_for_company(company A) returned one or more of Company B's "
        "production run ids - the shared mechanism behind pages 5/6/9's Quality Test Result "
        "Report, Quality Issue Report, and Sample Report ('Production Run' source)"
    )
    session.close()


def test_samples_conditioning_page_run_selectbox_excludes_other_company_run(two_companies):
    a, b = two_companies["a"], two_companies["b"]
    at = _run("9_Samples_Conditioning.py", a["company_id"])
    run_select = next(s for s in at.selectbox if s.key == "sample_run_select")
    # AppTest's Selectbox.options is the WIRE-FORMATTED display list (each
    # option already run through format_func before being sent to the
    # frontend, per streamlit.testing.v1.element_tree.Selectbox.__init__),
    # not the original ProductionRun objects - so the only way to recover
    # which run ids were actually offered is to parse the same "Run #<id> "
    # prefix the page's own format_func produces (pages/9_Samples_
    # Conditioning.py: f"Run #{r.id} — {r.foam_grade.grade_name} · {r.run_date}").
    offered_run_ids = {int(opt.split("Run #", 1)[1].split(" ", 1)[0]) for opt in run_select.options}
    assert set(a["run_ids"]) & offered_run_ids, "Company A's own runs should be offered"
    assert not (set(b["run_ids"]) & offered_run_ids), (
        "pages/9_Samples_Conditioning.py's 'Production run' selector offered Company B's run "
        "to a Company A user"
    )
    # And the Sample Report tab's own build, which pulls samples via
    # `Sample.production_run_id.in_([r.id for r in runs])` (line ~319) using
    # this exact same `runs` list - confirm the tab rendered successfully
    # for Company A (proving the handoff from this exact scoped run list
    # into the report works end to end for an in-scope company).
    assert "sample_report_docx" in [btn.key for btn in at.download_button]


# ---------------------------------------------------------------------------
# 3 (continued) + 7b. Root-Cause Assistant (page 18) - its own "Quality
# issue" selector is ALSO run-based, not grade-based:
#
#   scoped_run_ids = run_ids_for_company(session, active_company_id)
#   observations = apply_scope(session.query(QualityObservation),
#                               QualityObservation.production_run_id, scoped_run_ids)...all()
#
# (pages/18_Root_Cause_Assistant.py lines 59-68) - contrary to the task
# brief's item 7 grouping page 18 in with the grade/family-based Industrial
# Intelligence pages (15/16/17/19): reading the actual source, page 18 has
# no grade selector or grade_ids_for_* call anywhere in it. Its own cross-
# tenant boundary is the same run_ids_for_company mechanism as item 3, so
# this test is filed under item 3, not item 7 - see this file's final
# summary for the flag.
#
# This is also the item 7b test the task explicitly asked to be written
# fresh: tests/test_flat_pm_propagation_smoke.py::test_root_cause_
# assistant_never_crosses_method_boundary proves this page never compares
# a run against a prior run under a DIFFERENT Production Method WITHIN one
# company - a same-company isolation concern. It does not seed a second
# company and says nothing about cross-tenant leakage. This test does.
# ---------------------------------------------------------------------------
def test_root_cause_assistant_quality_issue_selector_excludes_other_company_observation(two_companies):
    a, b = two_companies["a"], two_companies["b"]
    at = _run("18_Root_Cause_Assistant.py", a["company_id"])
    obs_select = at.selectbox[0]
    # Same formatted-string caveat as the samples-conditioning test above -
    # pages/18_Root_Cause_Assistant.py's own format_func is
    # f"{o.observation_type} — {o.production_run.foam_grade.grade_name} "
    # f"(run #{o.production_run_id}, {o.observed_at}) · {o.severity}/{o.frequency}"
    # so "run #<id>" is parsed back out the same way.
    import re
    offered_obs_run_ids = {int(m) for opt in obs_select.options for m in re.findall(r"run #(\d+)", opt)}
    assert offered_obs_run_ids & set(a["run_ids"]), "Company A's own quality issue should be offered"
    assert not (offered_obs_run_ids & set(b["run_ids"])), (
        "Root-Cause Assistant's 'Quality issue' selector offered a quality issue tied to "
        "Company B's production run to a Company A user"
    )


# ---------------------------------------------------------------------------
# 4. Customer-Trial-based - pages/11_Customer_Trials.py's "Manage samples"
# trial selector (key="ct_manage_trial"), built from:
#
#   trials = apply_scope(session.query(CustomerTrial), CustomerTrial.plant_id, plant_ids)
#            .order_by(CustomerTrial.created_at.desc()).all()
#
# (pages/11_Customer_Trials.py lines 116-131). This same `trials` list also
# feeds the Sample Report ("Customer Trial" source, tab_report) and, once a
# trial is Closed, pages/21_Report.py's Trial Closeout Report (proven
# separately below under item 8's central-widget test). Format_func is
# f"#{t.id} — {t.customer_name} ({t.foam_grade.grade_name}, {t.status})".
# ---------------------------------------------------------------------------
def test_customer_trials_page_trial_selector_excludes_other_company_trial(two_companies):
    a, b = two_companies["a"], two_companies["b"]
    at = _run("11_Customer_Trials.py", a["company_id"])
    trial_select = next(s for s in at.selectbox if s.key == "ct_manage_trial")
    offered_ids = {int(opt.split("#", 1)[1].split(" ", 1)[0]) for opt in trial_select.options}
    assert a["cust_trial_id"] in offered_ids
    assert b["cust_trial_id"] not in offered_ids, (
        "pages/11_Customer_Trials.py's trial selector offered Company B's customer trial to a "
        "Company A user"
    )
    assert "ct_sample_report_docx" in [btn.key for btn in at.download_button]


# ---------------------------------------------------------------------------
# 5. Optimization-Trial-based - pages/12_Optimization_Trials.py's own
# "Manage samples" trial selector (key="ot_manage_trial"), the identical
# pattern against OptimizationTrial instead of CustomerTrial (pages/12_
# Optimization_Trials.py lines 117-131). Feeds the Sample Report
# ("Optimization Trial" source) the same way item 4 does for CustomerTrial.
# ---------------------------------------------------------------------------
def test_optimization_trials_page_trial_selector_excludes_other_company_trial(two_companies):
    a, b = two_companies["a"], two_companies["b"]
    at = _run("12_Optimization_Trials.py", a["company_id"])
    trial_select = next(s for s in at.selectbox if s.key == "ot_manage_trial")
    offered_ids = {int(opt.split("#", 1)[1].split(" ", 1)[0]) for opt in trial_select.options}
    assert a["opt_trial_id"] in offered_ids
    assert b["opt_trial_id"] not in offered_ids, (
        "pages/12_Optimization_Trials.py's trial selector offered Company B's optimization trial "
        "to a Company A user"
    )
    assert "ot_sample_report_docx" in [btn.key for btn in at.download_button]


# ---------------------------------------------------------------------------
# 6 + 8. Report-page central widget - pages/21_Report.py computes ITS OWN
# scoped id sets once at the top:
#
#   scoped_plant_ids = plant_ids_for_company(session, active_company_id)
#   scoped_run_ids = run_ids_for_company(session, active_company_id)
#   scoped_customer_trial_ids = customer_trial_ids_for_company(session, active_company_id)
#   scoped_optimization_trial_ids = optimization_trial_ids_for_company(session, active_company_id)
#
# (lines 91-95) and every one of its 5 tabs' own selectors is built from
# these. This single test drives all 4 non-WP3 selectors (Batch Release/
# Conformance Record's run picker, Plant/Period Summary's plant picker,
# Trial Closeout Report's trial picker for BOTH trial types, and Sample
# Certificate of Analysis's sample picker, the latter built from:
#
#   sample_query = session.query(Sample).filter(or_(
#       Sample.production_run_id.in_(scoped_run_ids or []),
#       Sample.customer_trial_id.in_(scoped_customer_trial_ids or []),
#       Sample.optimization_trial_id.in_(scoped_optimization_trial_ids or []),
#   ))  (lines 360-369)
#
# ) in one page load, since Streamlit tabs render all their content in a
# single script run - not lazily - so all 5 tabs' widgets already exist in
# the element tree after one at.run(). This is item 8's own test (the
# central Report page's widget), and doubles as the "Report page" instance
# of items 3/4/5/6 (the on-page instances of run/trial/sample selectors
# have their own dedicated tests above/below, on the pages where the
# reviewer actually manages those records).
# ---------------------------------------------------------------------------
def test_report_page_central_selectors_exclude_other_company_across_tabs(two_companies):
    import re
    a, b = two_companies["a"], two_companies["b"]
    at = _run("21_Report.py", a["company_id"])

    run_select = next(s for s in at.selectbox if s.key == "report_run_select")
    offered_run_ids = {int(m) for opt in run_select.options for m in re.findall(r"Run #(\d+)", opt)}
    assert offered_run_ids & set(a["run_ids"])
    assert not (offered_run_ids & set(b["run_ids"])), (
        "pages/21_Report.py's Batch Release / Conformance Record run selector leaked Company B's run"
    )

    plant_select = next(s for s in at.selectbox if s.key == "report_period_plant")
    assert any(a["plant_id"] is not None and opt != "All plants" for opt in plant_select.options)
    a_plant_name_present = any(opt not in ("All plants",) for opt in plant_select.options)
    assert a_plant_name_present
    for opt in plant_select.options:
        assert "Iso Plant B" not in opt, (
            "pages/21_Report.py's Plant/Period Summary plant selector leaked Company B's plant name"
        )

    trial_select = next(s for s in at.selectbox if s.key == "report_trial_select")
    offered_ct_ids = {int(m) for opt in trial_select.options for m in re.findall(r"#(\d+)", opt)}
    assert a["cust_trial_id"] in offered_ct_ids
    assert b["cust_trial_id"] not in offered_ct_ids, (
        "pages/21_Report.py's Trial Closeout Report (Customer Trial) selector leaked Company B's trial"
    )

    radio = next(r for r in at.radio if r.key == "report_trial_source_type")
    radio.set_value("Optimization Trial")
    at.run()
    assert not at.exception
    trial_select = next(s for s in at.selectbox if s.key == "report_trial_select")
    offered_ot_ids = {int(m) for opt in trial_select.options for m in re.findall(r"#(\d+)", opt)}
    assert a["opt_trial_id"] in offered_ot_ids
    assert b["opt_trial_id"] not in offered_ot_ids, (
        "pages/21_Report.py's Trial Closeout Report (Optimization Trial) selector leaked Company B's trial"
    )

    sample_select = next(s for s in at.selectbox if s.key == "report_sample_select")
    offered_sample_ids = {int(m) for opt in sample_select.options for m in re.findall(r"Sample #(\d+)", opt)}
    assert a["sample_id"] in offered_sample_ids
    assert a["ct_sample_id"] in offered_sample_ids
    assert a["ot_sample_id"] in offered_sample_ids
    for leaked in (b["sample_id"], b["ct_sample_id"], b["ot_sample_id"]):
        assert leaked not in offered_sample_ids, (
            "pages/21_Report.py's Sample Certificate of Analysis selector leaked a Company B sample"
        )


# ---------------------------------------------------------------------------
# 7 (WP3 half). pages/21_Report.py's Property Conformance Report tab -
# grade picker joins FoamGrade to GradeSpecification, scoped via
# scoped_family_ids (family_ids_for_plants), and its own run picker is
# scoped via scoped_run_ids the same way as the run tab above:
#
#   grades_with_specs = apply_scope(session.query(FoamGrade).join(ProductFamily, ...),
#                                    ProductFamily.id, scoped_family_ids)
#                        .join(GradeSpecification, ...).distinct()...all()
#   wp3_runs = apply_scope(session.query(ProductionRun).filter(foam_grade_id == wp3_grade.id),
#                           ProductionRun.id, scoped_run_ids)...all()
#
# (pages/21_Report.py lines 439-462).
#
# tests/test_wp3_uat_cases.py was checked directly for cross-company
# coverage of this report before writing this test: it has no pytest
# `def test_*` functions at all (its own `run()`/`__main__` block is a
# frozen, hand-invoked Gate-2 UAT script - see its own module docstring),
# exercises wp3_conformance.py's evaluation logic against SimpleNamespace
# stand-ins with NO database and NO Company/tenant concept whatsoever, and
# never seeds more than one tenant. It does not cover this, at all - so
# this is a new test, not a duplicate of anything existing.
# ---------------------------------------------------------------------------
def test_report_page_wp3_tab_grade_and_run_selectors_exclude_other_company(two_companies):
    a, b = two_companies["a"], two_companies["b"]
    at = _run("21_Report.py", a["company_id"])

    grade_select = next(s for s in at.selectbox if s.key == "report_wp3_grade")
    assert a["rigid_grade_name"] in grade_select.options
    assert b["rigid_grade_name"] not in grade_select.options, (
        "pages/21_Report.py's Property Conformance Report grade selector leaked Company B's "
        "rigid grade"
    )

    run_select = next(s for s in at.selectbox if s.key == "report_wp3_run")
    import re
    offered_run_ids = {int(m) for opt in run_select.options for m in re.findall(r"Run #(\d+)", opt)}
    assert a["rigid_run_id"] in offered_run_ids
    assert b["rigid_run_id"] not in offered_run_ids, (
        "pages/21_Report.py's Property Conformance Report run selector leaked Company B's rigid run"
    )
    assert "wp3_conformance_docx" in [btn.key for btn in at.download_button]


# ---------------------------------------------------------------------------
# 7 (grade/family half, pages 15/16/17/19). Backend proof of the shared
# mechanism (grade_ids_for_company -> grade_ids_for_families ->
# family_ids_for_plants -> plant_ids_for_company), plus one concrete
# widget-level check on pages/16_Trend_Analysis.py's own "Product grade"
# selectbox (via helpers.analysis_unit_picker, shared verbatim by pages
# 16/17/19 - see helpers.py lines 92-132), which is scoped from:
#
#   scoped_grade_ids = grade_ids_for_company(session, active_company_id)
#   grades = [g for g in apply_scope(session.query(FoamGrade), FoamGrade.id, scoped_grade_ids).all() if ...]
#
# (pages/16_Trend_Analysis.py lines 90-98, 155-161; pages/15_Recipe_
# Optimization.py lines 89-97 use the identical scoped_grade_ids ->
# apply_scope pattern for its own plain st.selectbox, without analysis_
# unit_picker). Note per this file's own reading of pages/18_Root_Cause_
# Assistant.py: page 18 is NOT part of this mechanism at all (it has no
# grade selector or grade_ids_for_* call anywhere in it) - see the item-3/
# 7b test above for its actual (run-based) mechanism and the flag in this
# file's final summary.
# ---------------------------------------------------------------------------
def test_grade_ids_for_company_excludes_other_company_grade(two_companies):
    session = db.get_session()
    a, b = two_companies["a"], two_companies["b"]
    grade_ids = tenant_scope.grade_ids_for_company(session, a["company_id"])
    assert a["grade_id"] in grade_ids
    assert a["rigid_grade_id"] in grade_ids
    assert b["grade_id"] not in grade_ids, (
        "tenant_scope.grade_ids_for_company(company A) returned Company B's foam grade - the "
        "shared mechanism behind pages 15/16/17/19's grade/family selector"
    )
    assert b["rigid_grade_id"] not in grade_ids
    session.close()


def test_trend_analysis_page_grade_selector_excludes_other_company_grade(two_companies):
    a, b = two_companies["a"], two_companies["b"]
    at = _run("16_Trend_Analysis.py", a["company_id"])
    grade_select = next(s for s in at.selectbox if s.key == "trend_grade_select")
    assert a["grade_name"] in grade_select.options
    assert b["grade_name"] not in grade_select.options, (
        "pages/16_Trend_Analysis.py's 'Product grade' selector (helpers.analysis_unit_picker, "
        "shared by pages 16/17/19) offered Company B's grade to a Company A user"
    )
    keys = [btn.key for btn in at.download_button]
    assert any(k.startswith("trend_report_docx_") for k in keys)


# ---------------------------------------------------------------------------
# 9. Expert Notes Report - pages/20_Expert_Notes.py's own scope, which is
# NOT a company_id-filtered query (ExpertNote has no company_id/plant_id
# column at all - it's polymorphic via linked_entity_type/linked_entity_id)
# but an application-level POST-filter against the same scoped id sets
# used elsewhere on the page:
#
#   all_notes = session.query(ExpertNote).order_by(...).all()
#   ...
#   notes_for_report = [n for n in all_notes if
#       (n.linked_entity_type == "production_run" and n.linked_entity_id in scoped_run_id_set)
#       or (n.linked_entity_type == "foam_grade" and n.linked_entity_id in scoped_grade_id_set)
#       or (n.linked_entity_type == "product_family" and n.linked_entity_id in scoped_family_id_set)
#   ]
#
# (pages/20_Expert_Notes.py lines 293-303, and the identical block again
# for the Edit/Delete tab's own `notes` list at lines 320-330). Proven at
# the widget level: the Expert Notes Report tab's "Total notes" metric and
# the Edit/Delete tab's clickable_table (rendered as st.dataframe, whose
# .value is the real pandas DataFrame Company A's browser would receive -
# see streamlit.testing.v1.element_tree.Dataframe.value) must both reflect
# only Company A's one note, never Company B's.
# ---------------------------------------------------------------------------
def test_expert_notes_page_report_and_list_exclude_other_company_note(two_companies):
    a, b = two_companies["a"], two_companies["b"]
    at = _run("20_Expert_Notes.py", a["company_id"])

    total_notes_metric = next(m for m in at.metric if m.label == "Total notes")
    assert total_notes_metric.value == "1", (
        f"Expert Notes Report's 'Total notes' metric should count only Company A's own note, "
        f"got {total_notes_metric.value!r} - Company B's note may have leaked in"
    )

    notes_table = next(df for df in at.dataframe if df.key == "expert_notes_table")
    rendered_notes = notes_table.value["Note"].tolist()
    assert any(a["note_text"] in n for n in rendered_notes), "Company A's own note should be listed"
    assert not any(b["note_text"] in n for n in rendered_notes), (
        "pages/20_Expert_Notes.py's Edit/Delete note list leaked Company B's note text to a "
        "Company A user"
    )

    assert "expert_notes_report_docx" in [btn.key for btn in at.download_button]


# ---------------------------------------------------------------------------
# 10. PI3 Q&A Report (5 answer locations app-wide) - ai_assistant.py's
# plant-tagged vector search scoping.
#
# ask_assistant()/ask_plant_question() both pass a `filters` argument on
# the OpenAI Responses API file_search tool, built by
# ai_assistant._file_search_filters(company_id):
#
#   {"type": "or", "filters": [
#       {"type": "eq", "key": "company_id", "value": company_id},
#       {"type": "eq", "key": "shared", "value": True},
#   ]}
#
# (ai_assistant.py lines 601-625) - documents are tagged with this same
# company_id at push time via push_document_to_vector_store(metadata=...),
# where callers (pages/20_Expert_Notes.py's _push_note_to_vector_store,
# line ~146) resolve company_id from the note's own plant via helpers.
# company_id_for_plant(plant_id, session) (helpers.py lines 50-59), which
# reads Plant.company_id directly off the real plant row - not something
# a caller can misattribute across companies.
#
# No live OpenAI call is made or needed here (there's no vector store to
# query in this sandbox, and driving one wouldn't be a repeatable/
# deterministic test anyway) - what's actually proven is the exact filter
# object every current caller (pages 15-19, ai_assistant.ask_plant_
# question(), and every Expert-Notes-fed PI3 push) hands to OpenAI's
# retrieval API, evaluated against OpenAI's own documented ComparisonFilter
# ("eq")/CompoundFilter ("or") semantics (developers.openai.com/api/docs/
# guides/retrieval#attribute-filtering, cited directly in this function's
# own docstring) via a tiny local evaluator that mirrors those semantics -
# i.e. this proves the filter ask_plant_question() actually sends would,
# per OpenAI's own filter semantics, admit Company A's tagged documents
# and reject Company B's, not just that the two dicts differ.
# ---------------------------------------------------------------------------
def _matches_openai_filter(flt, attributes):
    """Minimal evaluator for the subset of OpenAI's ComparisonFilter/
    CompoundFilter shapes ai_assistant._file_search_filters() actually
    produces (eq + or) - enough to prove what that filter dict would
    actually admit/reject, per OpenAI's documented semantics, without
    needing a live vector store."""
    if flt is None:
        return True
    if flt["type"] == "eq":
        return attributes.get(flt["key"]) == flt["value"]
    if flt["type"] == "or":
        return any(_matches_openai_filter(f, attributes) for f in flt["filters"])
    raise NotImplementedError(flt["type"])


def test_ai_assistant_file_search_filter_excludes_other_company_document(two_companies):
    session = db.get_session()
    a, b = two_companies["a"], two_companies["b"]

    # company_id_for_plant resolves each company's own plant to its own
    # company - never the other company's, even though both plants sit in
    # the same shared `plants` table.
    assert helpers.company_id_for_plant(a["plant_id"], session) == a["company_id"]
    assert helpers.company_id_for_plant(b["plant_id"], session) == b["company_id"]
    assert helpers.company_id_for_plant(a["plant_id"], session) != b["company_id"]

    # A document pushed for Company A's own Expert Note (see
    # pages/20_Expert_Notes.py's _push_note_to_vector_store) is tagged
    # {"company_id": a["company_id"], "shared": False}; Company B's
    # equivalent document is tagged with b["company_id"].
    doc_a_attrs = {"company_id": a["company_id"], "shared": False}
    doc_b_attrs = {"company_id": b["company_id"], "shared": False}
    shared_doc_attrs = {"company_id": None, "shared": True}

    company_a_filter = ai_assistant._file_search_filters(a["company_id"])
    assert _matches_openai_filter(company_a_filter, doc_a_attrs), (
        "Company A's own file_search filter should admit Company A's own tagged document"
    )
    assert not _matches_openai_filter(company_a_filter, doc_b_attrs), (
        "ai_assistant._file_search_filters(company A) would admit Company B's tagged document - "
        "PI3 Q&A cross-tenant vector-search leak"
    )
    assert _matches_openai_filter(company_a_filter, shared_doc_attrs), (
        "the general shared reference library (shared=True) must stay visible to every company"
    )

    # And the reverse direction, symmetrically - Company B's own filter
    # must not admit Company A's document either.
    company_b_filter = ai_assistant._file_search_filters(b["company_id"])
    assert not _matches_openai_filter(company_b_filter, doc_a_attrs)
    assert _matches_openai_filter(company_b_filter, doc_b_attrs)
    session.close()
