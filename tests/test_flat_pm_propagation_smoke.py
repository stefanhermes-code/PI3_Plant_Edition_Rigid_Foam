"""Flat Production Method (PM-100..PM-700) propagation/filtering regression
tests (2026-08-10, per Charlie's flat-PM technical completion instruction).

Complements test_pm_hierarchy_pages_smoke.py (which covers pages 1, 2, 4 -
activation, machine/grade assignment, and the run-creation snapshot). This
file covers what happens DOWNSTREAM of that snapshot once a foam grade's
production runs actually span two Production Methods:

  - helpers.production_method_label(): the inherited-label helper used by
    pages 5 (Quality Test Result), 6 (Quality Issue), 9 (Production Samples).
  - analytics.py: production_methods_used() + the production_method_id
    isolation filter threaded through property_results_dataframe() -
    the shared data layer behind pages 15-19 (Industrial Intelligence).
  - pages/16_Trend_Analysis.py: the Production Method filter widget only
    appears once a grade/family's runs actually span more than one method,
    and both method names are offered.
  - pages/18_Root_Cause_Assistant.py: the run-vs-prior-run comparison never
    crosses a Production Method boundary, even when an earlier run of the
    same grade exists under a different method.
  - pages/21_Report.py: the Batch Release / Conformance Record surfaces the
    RUN's own immutable Production Method snapshot (not the grade's or
    machine's current one).

Fixture: one foam grade producible on two machines under two different
Production Methods (mirrors the eventual PM-100/PM-200 two-method UAT
fixture - task #724 - without depending on that real Supabase data existing
yet). Run 1 -> Method A, Run 2 -> Method B, same property tested on both.

Usage: python -m pytest tests/test_flat_pm_propagation_smoke.py
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import analytics
import db
from helpers import production_method_label

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE16 = os.path.join(APP_DIR, "pages", "16_Trend_Analysis.py")
PAGE18 = os.path.join(APP_DIR, "pages", "18_Root_Cause_Assistant.py")
PAGE21 = os.path.join(APP_DIR, "pages", "21_Report.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def two_method_fixture():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"Flat-PM Smoke Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"Flat-PM Smoke Plant {u}")
    session.add(plant); session.flush()

    method_a = db.ProductionMethod(controlled_id=f"PM-SMOKE-100-{u}", name=f"Discontinuous Factory Foaming {u}", sort_order=100)
    method_b = db.ProductionMethod(controlled_id=f"PM-SMOKE-200-{u}", name=f"Continuous Panel & Board Production {u}", sort_order=200)
    session.add_all([method_a, method_b]); session.flush()
    session.add_all([
        db.PlantProductionMethod(plant_id=plant.id, production_method_id=method_a.id, active=True),
        db.PlantProductionMethod(plant_id=plant.id, production_method_id=method_b.id, active=True),
    ])
    session.flush()

    machine_a = db.Machine(plant_id=plant.id, name=f"Machine A {u}", production_method_id=method_a.id, active=True)
    machine_b = db.Machine(plant_id=plant.id, name=f"Machine B {u}", production_method_id=method_b.id, active=True)
    session.add_all([machine_a, machine_b]); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"Flat-PM Smoke Family {u}")
    session.add(family); session.flush()
    # Grade itself carries method_a as its own WP3-style classification, but
    # is producible on BOTH machines - this is what lets its own production
    # runs span two Production Methods (the isolation dimension under test).
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"Flat-PM Smoke Grade {u}", production_method_id=method_a.id)
    session.add(grade); session.flush()
    grade.machines = [machine_a, machine_b]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    run_a = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine_a.id,
        recipe_version_id=recipe.id, run_date=dt.date.today() - dt.timedelta(days=2),
        production_method_id=method_a.id,
    )
    run_b = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine_b.id,
        recipe_version_id=recipe.id, run_date=dt.date.today(),
        production_method_id=method_b.id,
    )
    session.add_all([run_a, run_b]); session.flush()

    result_a = db.PhysicalPropertyResult(
        production_run_id=run_a.id, property_name="Density", target_value=35.0,
        actual_value=35.5, unit="kg/m3", tested_at=dt.datetime.now(),
    )
    result_b = db.PhysicalPropertyResult(
        production_run_id=run_b.id, property_name="Density", target_value=35.0,
        actual_value=40.0, unit="kg/m3", tested_at=dt.datetime.now(),
    )
    session.add_all([result_a, result_b]); session.flush()

    observation_a = db.QualityObservation(
        production_run_id=run_a.id, observation_type="Collapse", severity="Minor",
        frequency="Isolated", observed_at=dt.datetime.now(),
    )
    sample_a = db.Sample(production_run_id=run_a.id, zone_label="Core", sample_ts=dt.datetime.now())
    session.add_all([observation_a, sample_a]); session.flush()
    session.commit()

    ids = {
        "plant_id": plant.id, "grade_id": grade.id, "grade_name": grade.grade_name,
        "method_a_id": method_a.id, "method_a_name": method_a.name,
        "method_b_id": method_b.id, "method_b_name": method_b.name,
        "run_a_id": run_a.id, "run_b_id": run_b.id,
        "observation_a_id": observation_a.id, "sample_a_id": sample_a.id,
    }
    session.close()
    return ids


# ---------------------------------------------------------------------------
# helpers.production_method_label() - pages 5, 6, 9's inherited breadcrumb
# ---------------------------------------------------------------------------

def test_production_method_label_shows_runs_own_snapshot(two_method_fixture):
    ids = two_method_fixture
    session = db.get_session()
    obs = session.get(db.QualityObservation, ids["observation_a_id"])
    sample = session.get(db.Sample, ids["sample_a_id"])
    assert production_method_label(obs) == ids["method_a_name"]
    assert production_method_label(sample) == ids["method_a_name"]
    session.close()


def test_production_method_label_lab_trial_is_not_applicable():
    session = db.get_session()
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    u = uuid.uuid4().hex[:8]
    company = db.Company(name=f"Lab Trial Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"Lab Trial Plant {u}")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"Lab Trial Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"Lab Trial Grade {u}")
    session.add(grade); session.flush()
    trial = db.CustomerTrial(
        plant_id=plant.id, foam_grade_id=grade.id, customer_name="Acme",
        trial_date=dt.date.today(), status="Open",
    )
    session.add(trial); session.flush()
    result = db.PhysicalPropertyResult(
        customer_trial_id=trial.id, property_name="Density", actual_value=35.0,
        unit="kg/m3", tested_at=dt.datetime.now(),
    )
    session.add(result); session.flush()
    session.commit()
    assert production_method_label(result) == "N/A (lab trial)"
    session.close()


# ---------------------------------------------------------------------------
# analytics.py - production_methods_used() + isolation filter, the shared
# data layer behind pages 15-19
# ---------------------------------------------------------------------------

def test_production_methods_used_finds_both_methods(two_method_fixture):
    ids = two_method_fixture
    session = db.get_session()
    methods = analytics.production_methods_used(session, ids["grade_id"])
    method_names = {m.name for m in methods}
    assert method_names == {ids["method_a_name"], ids["method_b_name"]}
    session.close()


def test_property_results_dataframe_isolates_by_method(two_method_fixture):
    ids = two_method_fixture
    session = db.get_session()

    pooled = analytics.property_results_dataframe(session, foam_grade_id=ids["grade_id"])
    assert len(pooled) == 2, "Unfiltered call should see both runs' results"

    isolated_a = analytics.property_results_dataframe(
        session, foam_grade_id=ids["grade_id"], production_method_id=ids["method_a_id"],
    )
    assert len(isolated_a) == 1
    assert isolated_a.iloc[0]["production_method_id"] == ids["method_a_id"]
    assert isolated_a.iloc[0]["actual_value"] == 35.5

    isolated_b = analytics.property_results_dataframe(
        session, foam_grade_id=ids["grade_id"], production_method_id=ids["method_b_id"],
    )
    assert len(isolated_b) == 1
    assert isolated_b.iloc[0]["production_method_id"] == ids["method_b_id"]
    assert isolated_b.iloc[0]["actual_value"] == 40.0
    session.close()


# ---------------------------------------------------------------------------
# Page-level smoke: filter widget appears + isolates when a grade's runs
# span two methods
# ---------------------------------------------------------------------------

def _run(page_path):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


def test_trend_analysis_offers_both_methods_when_grade_spans_two(two_method_fixture):
    ids = two_method_fixture
    at = _run(PAGE16)
    assert not at.exception, f"Unhandled exception loading Trend Analysis: {at.exception}"

    method_sb = next((sb for sb in at.selectbox if "trend_method_filter" in (sb.key or "")), None)
    assert method_sb is not None, (
        "Production Method filter should appear once this grade's runs span two methods"
    )
    assert ids["method_a_name"] in method_sb.options
    assert ids["method_b_name"] in method_sb.options
    assert "All" in method_sb.options


def test_root_cause_assistant_never_crosses_method_boundary(two_method_fixture):
    ids = two_method_fixture
    at = _run(PAGE18)
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"

    # Run B (Method B) is the only logged quality issue's run; Run A (an
    # earlier run of the SAME grade) exists but sits under Method A. Without
    # the 2026-08-10 isolation fix, the page would offer Run A as "the most
    # recent prior run" and diff Machine A vs Machine B as if that were a
    # meaningful process shift, when it's actually just two different
    # Production Methods. With the fix, no in-method prior run exists, so
    # the page must say so rather than silently cross-matching.
    body_text = "\n".join(md.value for md in at.info) + "\n".join(md.value for md in at.markdown)
    assert ids["method_b_name"] not in body_text or "No earlier production run" in "\n".join(i.value for i in at.info), (
        "Expected the page to report no in-method prior run rather than "
        "silently comparing against a run made under a different method"
    )
    assert any("No earlier production run" in i.value for i in at.info), (
        f"Expected an isolation-aware 'no prior run' message; info blocks: {[i.value for i in at.info]}"
    )


def test_batch_release_record_shows_runs_own_method_snapshot(two_method_fixture):
    ids = two_method_fixture
    at = _run(PAGE21)
    assert not at.exception, f"Unhandled exception loading Report page: {at.exception}"

    run_sb = next((sb for sb in at.selectbox if sb.key == "report_run_select"), None)
    assert run_sb is not None, "Batch Release Record's Production run picker not found"
    run_a_option = next((opt for opt in run_sb.options if f"Run #{ids['run_a_id']}" in str(opt)), None)
    assert run_a_option is not None, f"Run A not offered - got {run_sb.options}"

    run_sb.set_value(run_a_option)
    at.run()
    assert not at.exception, f"Unhandled exception after selecting Run A: {at.exception}"

    body_text = "\n".join(w.value for w in at.markdown)
    assert ids["method_a_name"] in body_text, (
        f"Expected Run A's own Production Method snapshot ({ids['method_a_name']!r}) "
        "displayed on the Batch Release Record"
    )


# ---------------------------------------------------------------------------
# Architecture correction (2026-08-10, Charlie's competing-source-of-truth
# finding): FoamGrade.production_method_id deprecated in favor of deriving a
# grade's Production Method(s) from its assigned Machines. The
# two_method_fixture grade above is a perfect regression bed for this: it
# sets grade.production_method_id = method_a (the old, now-deprecated
# single-method field) while grade.machines spans BOTH method_a and
# method_b - exactly the disagreement Charlie flagged as possible.
# ---------------------------------------------------------------------------

def test_grade_production_methods_derives_from_machines_not_deprecated_field(two_method_fixture):
    ids = two_method_fixture
    session = db.get_session()
    grade = session.get(db.FoamGrade, ids["grade_id"])
    # The deprecated field still holds its old value (never migrated away) -
    # this assertion documents that fact, it does not endorse reading it.
    assert grade.production_method_id == ids["method_a_id"]

    from helpers import grade_production_method_label, grade_production_methods
    methods = grade_production_methods(grade)
    method_names = {m.name for m in methods}
    assert method_names == {ids["method_a_name"], ids["method_b_name"]}, (
        "Expected grade_production_methods() to derive BOTH methods from "
        f"grade.machines, got {method_names}"
    )
    label = grade_production_method_label(grade)
    assert ids["method_a_name"] in label and ids["method_b_name"] in label, (
        f"Expected the derived label to name both methods, got {label!r}"
    )
    session.close()


def test_wp3_conformance_report_uses_runs_own_snapshot_not_grades_stale_field(two_method_fixture):
    """The exact competing-source-of-truth scenario: grade.production_method_id
    says Method A, but this report is being generated for Run B, which ran
    under Method B. Before the fix, build_wp3_conformance_report_data() read
    grade.production_method.name and would have wrongly shown "Method A" on
    a Run B report. After the fix, it reads run.production_method.name and
    correctly shows Method B."""
    ids = two_method_fixture
    session = db.get_session()
    import reports
    data = reports.build_wp3_conformance_report_data(session, ids["grade_id"], ids["run_b_id"])
    assert data is not None
    assert data["production_method"] == ids["method_b_name"], (
        f"Expected Run B's own snapshot ({ids['method_b_name']!r}), got {data['production_method']!r} - "
        "this would indicate the report regressed to reading the deprecated "
        "grade-level field instead of the run's own immutable snapshot"
    )
    assert data["production_method"] != ids["method_a_name"]
    session.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
