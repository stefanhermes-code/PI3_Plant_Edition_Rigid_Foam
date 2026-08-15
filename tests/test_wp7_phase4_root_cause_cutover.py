"""WP7 Phase 4 Root-Cause Assistant cutover (2026-08-14) regression tests.

Charlie's Downstream Reader Cutover Execution Instruction lists Root Cause
Assistant among the consumers that must read process-parameter facts
exclusively through analytics.production_run_process_parameters() /
production_run_parameter_dataframe(), never through ProductionPhase or the
legacy PHASE_SETTING_FIELDS/PHASE_SETTING_LABELS/eligible_phase_setting_
fields() combination, which retain zero active-reader authority under
Phase 4.

pages/18_Root_Cause_Assistant.py's run-vs-prior-run "What was different"
diff previously built its Finalized-phase settings comparison from
analytics.run_settings_dataframe()'s PHASE_SETTING_FIELDS columns (backed
by ProductionPhase). This cutover replaces that one loop with
analytics.production_run_parameter_dataframe(session, [run_id, prior_id]),
scoped to parameter_category == "Process Setting" only (the same
Environment/Outcome exclusion pages/4's own Method-Aware Process Settings
tab already applies, per the WP7 Phase 3 correction) - run_settings_
dataframe() itself is still used for identity/candidate-selection columns
(run_id, run_date, recipe_version, machine, production_method), which was
never a legacy-reader concern.

Covers:
  1. A genuine Process Setting Actual-value shift between the flagged run
     and its prior run is reported, with the correct percentage-change
     wording, sourced from the shared reader (not ProductionPhase).
  2. An Environment-category definition that also differs between the two
     runs is never reported as a "setting that shifted" - proves the
     parameter_category filter, mirroring the WP7 Phase 3 correction's
     Environment/Outcome exclusion elsewhere.
  3. Boolean and String data_type Process Settings are compared and
     reported using the new non-numeric branches (Yes/No wording for
     Boolean, raw value wording for String) - PHASE_SETTING_FIELDS was
     numeric/boolean-only, so this is new coverage the dynamic catalogue
     now requires.
  4. No difference at all -> the existing "No meaningful difference"
     message, unchanged behavior.
  5. Live AppTest evidence: the page loads without exception, the deter-
     ministic diff list matches what the shared reader returned, and the
     Root-Cause Comparison Report (Word) renders end-to-end since the
     page calls reports.render_root_cause_report_docx() eagerly for its
     download button.
  6. Production Method isolation (pre-existing behavior, re-verified
     unaffected by the reader swap): a prior run under a different
     Production Method is never offered as the comparison baseline.

MANDATORY TEMPLATE: tests/test_wp7_phase4_shared_reader.py (seeded_grade_
chain -> seeded_run fixture chain, _seed_definition/_add_value helpers).

Usage: python -m pytest tests/test_wp7_phase4_root_cause_cutover.py -v
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
import analytics
import db
import reports
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE18 = os.path.join(APP_DIR, "pages", "18_Root_Cause_Assistant.py")


def _clear_relevant_caches():
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()
    analytics.run_settings_dataframe.clear()
    analytics.property_results_dataframe.clear()


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    _clear_relevant_caches()


@pytest.fixture()
def seeded_grade_chain():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P4RC Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P4RC Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-WP7P4RC-{u}", name=f"WP7P4RC Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"WP7P4RC Machine {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P4RC Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P4RC Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P4RC-{u}", symbol="bar", name="Bar")
    session.add(unit); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "method_id": method.id,
        "machine_id": machine.id, "family_id": family.id, "grade_id": grade.id,
        "recipe_version_id": recipe.id, "unit_id": unit.id,
    }
    session.close()
    return ids


def _make_run(ids, run_date, method_id="__default__", machine_id="__default__", batch_suffix=None):
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
        recipe_version_id=ids["recipe_version_id"], run_date=run_date,
        batch_reference=f"B-WP7P4RC-{batch_suffix or uuid.uuid4().hex[:8]}",
        machine_id=ids["machine_id"] if machine_id == "__default__" else machine_id,
        production_method_id=ids["method_id"] if method_id == "__default__" else method_id,
        operator_or_team_reference="Shift A",
    )
    session.add(run); session.commit()
    run_id = run.id
    session.close()
    return run_id


def _seed_definition(ids, name, parameter_category="Process Setting", data_type="Float", unit_id="__default__"):
    session = db.get_session()
    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P4RC-{uuid.uuid4().hex[:6]}", name=name,
        data_type=data_type, unit_id=None if data_type != "Float" else (
            ids["unit_id"] if unit_id == "__default__" else unit_id
        ),
        parameter_category=parameter_category,
    )
    session.add(definition); session.flush()
    session.add(db.ProcessSettingApplicability(
        setting_definition_id=definition.id, production_method_id=ids["method_id"], machine_id=None,
        controllable=True, analytics_eligible=True,
    ))
    session.commit()
    definition_id = definition.id
    session.close()
    return definition_id


def _add_actual(run_id, definition_id, numeric_value=None, text_value=None, boolean_value=None):
    session = db.get_session()
    session.add(db.ProcessParameterValue(
        setting_definition_id=definition_id, production_run_id=run_id,
        snapshot_type="Actual", numeric_value=numeric_value,
        text_value=text_value, boolean_value=boolean_value, source="Machine capture",
    ))
    session.commit()
    session.close()


def _add_observation(run_id, observation_type="Shrinkage"):
    session = db.get_session()
    obs = db.QualityObservation(
        production_run_id=run_id, observation_type=observation_type,
        severity="Medium", frequency="One-off", observed_at=dt.date(2026, 8, 2),
    )
    session.add(obs); session.commit()
    obs_id = obs.id
    session.close()
    return obs_id


def _run_page():
    at = AppTest.from_file(PAGE18, default_timeout=60)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


def _body_text(at):
    return "\n".join(m.value for m in at.markdown) + "\n" + "\n".join(i.value for i in at.info)


# ---------------------------------------------------------------------------
# 1-3. Shared-reader-backed diff: numeric shift, category exclusion,
#      Boolean/String comparison
# ---------------------------------------------------------------------------

@pytest.fixture()
def two_run_fixture(seeded_grade_chain):
    ids = seeded_grade_chain
    prior_id = _make_run(ids, dt.date(2026, 8, 1), batch_suffix="prior")
    current_id = _make_run(ids, dt.date(2026, 8, 5), batch_suffix="current")

    numeric_def = _seed_definition(ids, "WP7P4RC Fill pressure", parameter_category="Process Setting", data_type="Float")
    env_def = _seed_definition(ids, "WP7P4RC Ambient temperature", parameter_category="Environment", data_type="Float")
    bool_def = _seed_definition(ids, "WP7P4RC Top-flat system", parameter_category="Process Setting", data_type="Boolean")
    string_def = _seed_definition(ids, "WP7P4RC Foaming mode", parameter_category="Process Setting", data_type="String")

    # Numeric Process Setting: 100 -> 90 is a -10% shift, well over the 2%
    # threshold, so it must be reported.
    _add_actual(prior_id, numeric_def, numeric_value=100.0)
    _add_actual(current_id, numeric_def, numeric_value=90.0)

    # Environment definition also differs (20.0 -> 25.0) - must NEVER be
    # reported as a "setting that shifted", proving the parameter_category
    # filter actually excludes it rather than merely being untested.
    _add_actual(prior_id, env_def, numeric_value=20.0)
    _add_actual(current_id, env_def, numeric_value=25.0)

    # Boolean Process Setting: False -> True.
    _add_actual(prior_id, bool_def, boolean_value=False)
    _add_actual(current_id, bool_def, boolean_value=True)

    # String Process Setting: changed value.
    _add_actual(prior_id, string_def, text_value="Discontinuous")
    _add_actual(current_id, string_def, text_value="Continuous")

    obs_id = _add_observation(current_id)

    out = dict(ids)
    out.update({
        "prior_id": prior_id, "current_id": current_id, "obs_id": obs_id,
        "numeric_def": numeric_def, "env_def": env_def,
        "bool_def": bool_def, "string_def": string_def,
    })
    return out


def test_shared_reader_reports_numeric_process_setting_shift(two_run_fixture):
    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"
    body = _body_text(at)
    assert "WP7P4RC Fill pressure" in body
    assert "-10.00%" in body


def test_shared_reader_excludes_environment_category_from_setting_shifts(two_run_fixture):
    """WP7 Phase 4 targeted completion, Item 2 (2026-08-14) changed this:
    the Environment definition now legitimately appears in the page's own
    'Environment / Outcome context' section (see the new tests below) - so
    this test scopes its check to the 'What was different' text that
    precedes that new section, rather than the whole page body."""
    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"
    body = _body_text(at)
    env_context_idx = body.find("Environment / Outcome context")
    assert env_context_idx != -1
    what_was_different_section = body[:env_context_idx]
    assert "WP7P4RC Ambient temperature" not in what_was_different_section, (
        "An Environment-category definition must never be reported as a "
        "process-setting shift, even though its Actual value differs "
        "between the two runs - only parameter_category == 'Process "
        "Setting' definitions are eligible for this comparison."
    )


def test_shared_reader_reports_boolean_process_setting_change(two_run_fixture):
    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"
    body = _body_text(at)
    assert "WP7P4RC Top-flat system" in body
    assert "No → Yes" in body


def test_shared_reader_reports_string_process_setting_change(two_run_fixture):
    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"
    body = _body_text(at)
    assert "WP7P4RC Foaming mode" in body
    assert "Discontinuous → Continuous" in body


def test_root_cause_comparison_report_word_download_renders(two_run_fixture):
    """The page calls reports.render_root_cause_report_docx() eagerly to
    populate its download_button - so a clean page load with no exception
    already proves the full build_root_cause_report_data() ->
    render_root_cause_report_docx() pipeline succeeded against the new
    shared-reader-backed changes/setting_shifts lists."""
    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"
    dl_buttons = [b for b in at.get("download_button") if "root_cause_report_docx" in (b.key or "")]
    assert len(dl_buttons) == 1


# ---------------------------------------------------------------------------
# 4. No difference at all
# ---------------------------------------------------------------------------

def test_identical_process_settings_yield_no_meaningful_difference(seeded_grade_chain):
    ids = seeded_grade_chain
    prior_id = _make_run(ids, dt.date(2026, 8, 1), batch_suffix="prior")
    current_id = _make_run(ids, dt.date(2026, 8, 5), batch_suffix="current")
    numeric_def = _seed_definition(ids, "WP7P4RC Steady pressure", parameter_category="Process Setting", data_type="Float")
    _add_actual(prior_id, numeric_def, numeric_value=100.0)
    _add_actual(current_id, numeric_def, numeric_value=100.0)
    _add_observation(current_id)

    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"
    body = _body_text(at)
    assert "No meaningful difference found" in body


# ---------------------------------------------------------------------------
# 6. Production Method isolation still holds after the reader swap
# ---------------------------------------------------------------------------

def test_prior_run_under_different_method_never_offered(seeded_grade_chain):
    ids = seeded_grade_chain
    other_method = db.ProductionMethod(controlled_id=f"PM-WP7P4RC-OTHER-{uuid.uuid4().hex[:6]}", name="Other Method")
    session = db.get_session()
    session.add(other_method); session.commit()
    other_method_id = other_method.id
    session.close()

    other_machine = db.Machine(plant_id=ids["plant_id"], name="Other Machine", production_method_id=other_method_id, active=True)
    session2 = db.get_session()
    session2.add(other_machine); session2.commit()
    other_machine_id = other_machine.id
    session2.close()

    prior_other_method_id = _make_run(
        ids, dt.date(2026, 8, 1), method_id=other_method_id, machine_id=other_machine_id, batch_suffix="othermethod",
    )
    current_id = _make_run(ids, dt.date(2026, 8, 5), batch_suffix="current")
    _add_observation(current_id)

    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"
    assert any("No earlier production run" in i.value for i in at.info), (
        "A prior run under a different Production Method must never be "
        "offered as the comparison baseline, even after the process-"
        "setting reader swap."
    )


# ---------------------------------------------------------------------------
# 7. WP7 Phase 4 targeted completion, Item 2 (2026-08-14) - per Charlie's
# Closeout Review Return to JC: Environment/Outcome as separate context
# sections, plus run-linked material usage/metering, Production Events, and
# QC context as investigation facts separated from PI3's inferred
# hypotheses. Unit tests hit reports.environment_outcome_context_rows() /
# reports.root_cause_investigation_facts() directly; AppTest cases prove
# the page actually renders both new sections and never folds them into
# "What was different".
# ---------------------------------------------------------------------------

def test_environment_outcome_context_rows_separates_categories(two_run_fixture):
    """Direct unit test of reports.environment_outcome_context_rows() -
    reuses the exact values_by_run/definitions_by_field the page computes
    via analytics.production_run_parameter_dataframe()."""
    session = db.get_session()
    values_by_run, definitions_by_field = analytics.production_run_parameter_dataframe(
        session, [two_run_fixture["current_id"], two_run_fixture["prior_id"]],
    )
    current_values = values_by_run.get(two_run_fixture["current_id"], {})
    prior_values = values_by_run.get(two_run_fixture["prior_id"], {})
    rows = reports.environment_outcome_context_rows(definitions_by_field, current_values, prior_values)
    session.close()

    assert len(rows["Environment"]) == 1
    env_row = rows["Environment"][0]
    assert env_row["Parameter"] == "WP7P4RC Ambient temperature"
    assert env_row["Prior (Actual)"] == 20.0
    assert env_row["Current (Actual)"] == 25.0
    assert rows["Outcome"] == []
    # None of the Process Setting definitions leak into either bucket.
    assert all(r["Parameter"] != "WP7P4RC Fill pressure" for r in rows["Environment"] + rows["Outcome"])


def test_environment_outcome_context_shown_on_page_not_as_setting_change(two_run_fixture):
    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"
    body = _body_text(at)
    assert "Environment / Outcome context" in body
    assert "20.0" in body and "25.0" in body, "Ambient temperature Prior/Current values must render."
    # Re-confirms (alongside the existing category-exclusion test) that the
    # Environment definition's name never appears before the context
    # section - i.e. it is not part of "What was different" above it.
    env_context_idx = body.find("Environment / Outcome context")
    assert env_context_idx != -1
    assert "WP7P4RC Ambient temperature" not in body[:env_context_idx]


def test_investigation_facts_material_usage_reads_via_production_run_id_only(two_run_fixture):
    """Direct unit test of reports.root_cause_investigation_facts() Item
    1.3-pattern evidence: a ComponentStreamReading linked only via
    production_run_id (production_phase_id left NULL, no ProductionPhase
    row exists for this run at all) still surfaces as an investigation
    fact."""
    session = db.get_session()
    assert session.query(db.ProductionPhase).filter(
        db.ProductionPhase.production_run_id == two_run_fixture["current_id"]
    ).count() == 0
    session.add(db.ComponentStreamReading(
        production_run_id=two_run_fixture["current_id"], production_phase_id=None,
        stream_name="Polyol A", flow=10.0, flow_unit="kg/min",
    ))
    session.commit()
    session.close()

    session = db.get_session()
    run = session.get(db.ProductionRun, two_run_fixture["current_id"])
    facts = reports.root_cause_investigation_facts(session, run)
    session.close()

    assert len(facts["material_usage_rows"]) == 1
    assert facts["material_usage_rows"][0]["Stream"] == "Polyol A"


def test_investigation_facts_production_events_and_qc_context(two_run_fixture):
    session = db.get_session()
    session.add(db.ProductionEvent(
        production_run_id=two_run_fixture["current_id"], event_ts=dt.datetime(2026, 8, 5, 10, 0),
        event_type="Maintenance intervention", description="Filter changed mid-run",
    ))
    session.add(db.PhysicalPropertyResult(
        production_run_id=two_run_fixture["current_id"], property_name="Density",
        target_value=40.0, actual_value=39.5, unit="kg/m3",
    ))
    session.add(db.QualityObservation(
        production_run_id=two_run_fixture["current_id"], observation_type="Splitting",
        severity="Low", frequency="One-off", observed_at=dt.date(2026, 8, 5),
    ))
    session.commit()
    session.close()

    session = db.get_session()
    run = session.get(db.ProductionRun, two_run_fixture["current_id"])
    facts = reports.root_cause_investigation_facts(session, run)
    session.close()

    assert len(facts["production_event_rows"]) == 1
    assert facts["production_event_rows"][0]["Type"] == "Maintenance intervention"
    assert len(facts["qc_result_rows"]) == 1
    assert facts["qc_result_rows"][0]["Property"] == "Density"
    # Two QualityObservations now exist on this run: the fixture's original
    # (linked to the page's `obs` selectbox pick) plus this new Splitting
    # one - both must appear as investigation facts, not just the flagged one.
    assert len(facts["qc_issue_rows"]) == 2
    assert {r["Issue type"] for r in facts["qc_issue_rows"]} == {"Shrinkage", "Splitting"}


def test_investigation_facts_shown_on_page_separated_from_pi3_hypothesis(two_run_fixture):
    session = db.get_session()
    session.add(db.ComponentStreamReading(
        production_run_id=two_run_fixture["current_id"], production_phase_id=None,
        stream_name="TDI 80/20", flow=5.0, flow_unit="kg/min",
    ))
    session.add(db.ProductionEvent(
        production_run_id=two_run_fixture["current_id"], event_ts=dt.datetime(2026, 8, 5, 9, 0),
        event_type="Startup", description="Line restart after changeover",
    ))
    session.commit()
    session.close()

    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"
    body = _body_text(at)
    assert "Investigation facts" in body
    # Confirms the dedicated Root-Cause Comparison Report section (the
    # page's own deterministic report, distinct from PI3's free-form
    # hypothesis) still renders cleanly alongside the new facts section -
    # source order in pages/18 itself places Investigation facts first,
    # per this batch's edit (facts before the Report divider, which is
    # itself before the "Use PI3" button/hypothesis section).
    report_subheaders = [s for s in at.subheader if s.value == "Root-Cause Comparison Report"]
    assert len(report_subheaders) == 1
    assert "TDI 80/20" in body
    assert "Startup" in body


def test_empty_investigation_facts_render_as_no_data_not_crash(seeded_grade_chain):
    """A run with no metering/events/other-QC recorded must render the
    'No ... recorded' placeholders cleanly, never crash or silently omit
    the section headers."""
    ids = seeded_grade_chain
    prior_id = _make_run(ids, dt.date(2026, 8, 1), batch_suffix="prior")
    current_id = _make_run(ids, dt.date(2026, 8, 5), batch_suffix="current")
    numeric_def = _seed_definition(ids, "WP7P4RC Bare pressure", parameter_category="Process Setting", data_type="Float")
    _add_actual(prior_id, numeric_def, numeric_value=50.0)
    _add_actual(current_id, numeric_def, numeric_value=55.0)
    _add_observation(current_id)

    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"
    body = _body_text(at)
    assert "Investigation facts" in body
    assert "No metering data recorded" in body
    assert "No events recorded" in body


# ---------------------------------------------------------------------------
# 8. WP7 Phase 4 Root Cause FINAL targeted completion (2026-08-15) - per
# Charlie's Corrected Closeout Review Return to JC: (a) a dedicated
# current-run Process Setting Planned-vs-Actual context, separate from the
# run-vs-prior-run shift comparison above, and (b) real recorded fact
# VALUES (not just counts) reaching the PI3 hypothesis prompt. Direct unit
# tests hit reports.current_run_process_setting_rows() and
# reports.format_root_cause_facts_for_pi3() at the payload level (Charlie's
# item 4: "a payload-level assertion proving seeded ... fact values reach
# the PI3 hypothesis input" without mocking OpenAI or driving the button
# click); AppTest cases prove the page actually renders the new on-screen
# table and that source isolation from legacy ProductionPhase still holds.
# ---------------------------------------------------------------------------

def test_current_run_process_setting_rows_shows_planned_actual_delta(seeded_grade_chain):
    """Direct unit test: Planned=100, Actual=90 on the SAME run must
    surface as a Planned/Actual/Delta=-10 row with the correct UOM, sourced
    from analytics.production_run_process_parameters() via
    _process_parameter_report_rows() - never re-derived."""
    ids = seeded_grade_chain
    run_id = _make_run(ids, dt.date(2026, 8, 5), batch_suffix="planned-actual")
    definition_id = _seed_definition(
        ids, "WP7P4RC Melt temperature", parameter_category="Process Setting", data_type="Float",
    )
    session = db.get_session()
    session.add(db.ProcessParameterValue(
        setting_definition_id=definition_id, production_run_id=run_id,
        snapshot_type="Planned", numeric_value=100.0, source="Recipe",
    ))
    session.add(db.ProcessParameterValue(
        setting_definition_id=definition_id, production_run_id=run_id,
        snapshot_type="Actual", numeric_value=90.0, source="Machine capture",
    ))
    session.commit()
    session.close()

    session = db.get_session()
    rows = reports.current_run_process_setting_rows(session, run_id)
    session.close()

    matches = [r for r in rows if r["Parameter"] == "WP7P4RC Melt temperature"]
    assert len(matches) == 1
    row = matches[0]
    assert row["Planned"] == 100.0
    assert row["Actual"] == 90.0
    assert row["Delta"] == -10.0
    assert row["UOM"] == "bar"


def test_current_run_process_setting_rows_never_reads_production_phase(seeded_grade_chain):
    """Source-isolation re-proof (Charlie's item 4): seed a deliberately
    conflicting legacy ProductionPhase value on the same run/definition
    field and confirm it never leaks into current_run_process_setting_rows()
    - the shared reader remains the sole source of authority."""
    ids = seeded_grade_chain
    run_id = _make_run(ids, dt.date(2026, 8, 5), batch_suffix="isolation")
    definition_id = _seed_definition(
        ids, "WP7P4RC Isolation pressure", parameter_category="Process Setting", data_type="Float",
    )
    session = db.get_session()
    session.add(db.ProcessParameterValue(
        setting_definition_id=definition_id, production_run_id=run_id,
        snapshot_type="Actual", numeric_value=42.0, source="Machine capture",
    ))
    # Deliberately conflicting legacy ProductionPhase row on the same run -
    # a stale/legacy air_pressure_bar value that must never surface.
    session.add(db.ProductionPhase(
        production_run_id=run_id, phase_name="Finalized",
        air_pressure_bar=999.0,
    ))
    session.commit()
    session.close()

    session = db.get_session()
    rows = reports.current_run_process_setting_rows(session, run_id)
    session.close()

    matches = [r for r in rows if r["Parameter"] == "WP7P4RC Isolation pressure"]
    assert len(matches) == 1
    assert matches[0]["Actual"] == 42.0
    assert all(r["Actual"] != 999.0 for r in rows), (
        "The legacy ProductionPhase.fill_pressure_bar value must never leak "
        "into the shared-reader-backed current-run Process Setting rows."
    )


def test_current_run_setting_table_shown_on_page(two_run_fixture):
    at = _run_page()
    assert not at.exception, f"Unhandled exception loading Root-Cause Assistant: {at.exception}"
    body = _body_text(at)
    assert "Current run — Process Setting (Planned vs. Actual)" in body
    assert "What was different (vs. prior run)" in body


def test_format_root_cause_facts_for_pi3_carries_real_values_not_counts(two_run_fixture):
    """Payload-level assertion (Charlie's item 4): seed one fact in each
    category with a distinctive real value, then assert
    format_root_cause_facts_for_pi3()'s OUTPUT TEXT contains those actual
    values - not merely a count - proving the fact values genuinely reach
    what would be sent to PI3, without mocking ai_assistant.ask_assistant()
    or driving the button click."""
    ids = two_run_fixture
    current_id = ids["current_id"]
    prior_id = ids["prior_id"]

    session = db.get_session()
    session.add(db.ComponentStreamReading(
        production_run_id=current_id, production_phase_id=None,
        stream_name="WP7P4RC Polyol Stream", flow=12.34, flow_unit="kg/min",
        flow_total_qty=567.8, temperature_c=45.6, pressure_bar=3.21,
        calibration_status="Current",
    ))
    session.add(db.ProductionEvent(
        production_run_id=current_id, event_ts=dt.datetime(2026, 8, 5, 11, 30),
        event_type="WP7P4RC Nozzle clean", severity="Low",
        description="WP7P4RC distinctive event description",
    ))
    session.add(db.PhysicalPropertyResult(
        production_run_id=current_id, property_name="WP7P4RC Distinctive Property",
        target_value=40.0, actual_value=38.5, unit="kg/m3",
    ))
    session.commit()
    session.close()

    session = db.get_session()
    run = session.get(db.ProductionRun, current_id)
    investigation_facts = reports.root_cause_investigation_facts(session, run)
    values_by_run, definitions_by_field = analytics.production_run_parameter_dataframe(
        session, [current_id, prior_id],
    )
    env_outcome_rows = reports.environment_outcome_context_rows(
        definitions_by_field, values_by_run.get(current_id, {}), values_by_run.get(prior_id, {}),
    )
    current_setting_rows = reports.current_run_process_setting_rows(session, current_id)
    session.close()

    facts_text = reports.format_root_cause_facts_for_pi3(
        investigation_facts, env_outcome_rows, current_setting_rows,
    )

    # Current-run Process Setting Planned/Actual/Delta values (from
    # two_run_fixture's numeric_def, Actual=90.0 on the current run - no
    # Planned recorded, so Planned reads "not recorded", never 0/blank).
    assert "WP7P4RC Fill pressure" in facts_text
    assert "Actual 90" in facts_text
    assert "Planned not recorded" in facts_text

    # Environment context real values (20.0 / 25.0), not just a count.
    assert "WP7P4RC Ambient temperature" in facts_text
    assert "prior 20" in facts_text
    assert "current 25" in facts_text

    # Material usage/metering real values.
    assert "WP7P4RC Polyol Stream" in facts_text
    assert "567.8" in facts_text
    assert "45.6" in facts_text
    assert "3.21" in facts_text

    # Production event real description text.
    assert "WP7P4RC Nozzle clean" in facts_text
    assert "WP7P4RC distinctive event description" in facts_text

    # QC result real property/values.
    assert "WP7P4RC Distinctive Property" in facts_text
    assert "38.5" in facts_text


def test_format_root_cause_facts_for_pi3_empty_sections_say_none_recorded():
    """All-empty inputs must yield explicit 'None recorded' lines per
    section, never a silent omission or a crash on missing keys."""
    empty_facts = {
        "material_usage_rows": [], "production_event_rows": [],
        "qc_result_rows": [], "qc_issue_rows": [],
    }
    empty_env_outcome = {"Environment": [], "Outcome": []}
    text = reports.format_root_cause_facts_for_pi3(empty_facts, empty_env_outcome, [])
    # 7 sections total: current-run Process Setting, Environment, Outcome,
    # Material usage/metering, Production events, QC results, QC issues -
    # every one must emit its own explicit "None recorded" line.
    assert text.count("None recorded") == 7
