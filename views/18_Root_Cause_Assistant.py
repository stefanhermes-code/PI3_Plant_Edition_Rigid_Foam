"""Industrial Intelligence: Root-Cause Assistant

Given a quality observation, surfaces what was different about that run
compared to the most recent prior run of the same product grade - recipe
version, machine, or recorded Actual process settings - as a starting
point for the reviewer's own investigation. Historical comparison for
technical review (see the advisory boundary at the bottom of this page).

WP7 Phase 4 cutover (2026-08-14): process-setting comparison reads
through analytics.production_run_parameter_dataframe(), the shared
reader - see the comment above that call below for the full rationale.
"""

import pandas as pd
import streamlit as st

import ai_assistant
from access_control import can_use_page
from analytics import production_run_parameter_dataframe, run_settings_dataframe
from auth import current_user, logout_button, require_login
from db import QualityObservation, get_session, init_db
import reports
from tenant_scope import apply_scope, company_picker, run_ids_for_company
from helpers import (
    log_export_click,
    page_setup,
    production_method_label,
    render_ask_pi3_section,
    render_data_table,
    render_function_action_intro,
    render_pi3_docx_download,
    render_pi3_feedback_control,
    render_save_to_expert_notes_button,
    view_only_notice,
)

page_setup("Root-Cause Assistant")
init_db()
require_login()
logout_button()

st.title("Root-Cause Assistant")
render_function_action_intro(
    function_text=(
        "Given a logged quality issue, compares that run against the most recent prior run of the "
        "same product grade and lists what was different - recipe version, equipment / machine, "
        "or recorded Actual process settings - as a starting "
        "point for your own investigation, not a diagnosis. PI3 can then help interpret that diff "
        "against expert notes and similar past cases."
    ),
    action_text=(
        "Select the quality issue you're investigating, review the run-vs-prior-run diff shown, "
        "and check whether any of the flagged differences line up with a plausible cause. Use "
        "'Ask PI3' if you want that diff interpreted alongside historical expert notes and "
        "similar past cases before you commit to a root cause. Download the Root-Cause "
        "Comparison Report further down for a shareable Word summary of the diff above."
    ),
)
session = get_session()
user = current_user()
page_usable = can_use_page("root_cause_assistant", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice(action="using PI3 and saving to Expert Notes")
company, _all_companies = company_picker(
    st, session, user["is_platform_owner"], user["company_id"], key="rca_company_filter"
)
active_company_id = company.id if company else None
scoped_run_ids = run_ids_for_company(session, active_company_id)

observations = (
    apply_scope(session.query(QualityObservation), QualityObservation.production_run_id, scoped_run_ids)
    # Root-Cause Assistant compares a run against its most recent prior run's
    # machine/process settings - a lab trial (Customer Trial / Optimization
    # Trial, added 2026-08-03) has neither, so a trial-sourced quality issue
    # (production_run_id NULL) is excluded here unconditionally rather than
    # offered as a dead-end pick. See analytics.py's property_results_dataframe
    # docstring for why this page never accepts an include_trials toggle.
    .filter(QualityObservation.production_run_id.isnot(None))
    .order_by(QualityObservation.observed_at.desc())
    .all()
)
if not observations:
    st.info("No quality issues recorded yet.")
    st.stop()

obs = st.selectbox(
    "Quality issue",
    observations,
    format_func=lambda o: (
        f"{o.observation_type} — {o.production_run.foam_grade.grade_name} "
        f"(run #{o.production_run_id}, {o.observed_at}) · {o.severity}/{o.frequency}"
    ),
)

run = obs.production_run
grade = run.foam_grade

st.divider()
st.subheader(f"{obs.observation_type} on run #{run.id} ({run.run_date})")
c1, c2 = st.columns(2)
c1.metric("Severity", obs.severity)
c2.metric("Frequency", obs.frequency)
if obs.suspected_cause:
    st.caption(f"Logged suspected cause: {obs.suspected_cause}")
st.caption(f"Production Method: {production_method_label(obs)}")

# Production Method isolation (added 2026-08-10, per Charlie's flat-PM
# technical completion instruction): the "most recent prior run" comparison
# below must never cross a Production Method boundary - a machine/setting
# "difference" against a run made under a different Production Method
# would just reflect the two methods being different equipment classes,
# not a meaningful process shift. Restricting the candidate pool to the
# flagged run's own (immutable, snapshot) Production Method is what makes
# this comparison an apples-to-apples one. Falls back to unfiltered only
# when the flagged run itself has no Production Method recorded (no
# machine set at run creation) - see run_settings_dataframe's own
# production_method_id=None passthrough.
settings_df = run_settings_dataframe(
    session, foam_grade_id=grade.id, production_method_id=run.production_method_id,
)
settings_df = settings_df.sort_values("run_date")

current_rows = settings_df[settings_df["run_id"] == run.id]
if current_rows.empty:
    st.warning("No production run record found for this run yet — nothing to compare.")
    st.stop()
current = current_rows.iloc[0]

prior_rows = settings_df[settings_df["run_date"] < run.run_date]
if prior_rows.empty:
    method_hint = (
        f" under Production Method {current['production_method']}" if run.production_method_id else ""
    )
    st.info(f"No earlier production run of {grade.grade_name}{method_hint} to compare against.")
    st.stop()
prior = prior_rows.iloc[-1]

st.markdown(f"**Compared against run #{int(prior['run_id'])}** ({prior['run_date']})")

changes = []
setting_shifts = []
if current["recipe_version"] != prior["recipe_version"]:
    changes.append(f"Recipe version changed: {prior['recipe_version']} → {current['recipe_version']}")
if current["machine"] != prior["machine"]:
    changes.append(f"Equipment / Machine changed: {prior['machine'] or '—'} → {current['machine'] or '—'}")

# WP7 Phase 4 cutover (2026-08-14, per Charlie's Downstream Reader
# Cutover Execution Instruction): reads process-setting values through
# analytics.production_run_parameter_dataframe() - the shared reader's
# multi-run form - instead of the retired PHASE_SETTING_FIELDS /
# eligible_phase_setting_fields() / PHASE_SETTING_LABELS combination,
# which read ProductionPhase directly and retain zero active-reader
# authority under Phase 4. Scoped to parameter_category == "Process
# Setting" only - the same Environment/Outcome exclusion views/4's own
# Method-Aware Process Settings tab already applies (WP7 Phase 3
# correction) - so a measured ambient/outcome reading is never reported
# here as a "setting that shifted", only a genuine controllable process
# lever. Only Actual values are compared (values_by_run only ever
# carries Actual - Charlie's "Planned never substitutes for missing
# Actual" rule), matching this loop's prior implicit reliance on
# Finalized-phase (i.e. actual, not setup/planned) values. The two runs'
# eligible catalogues are each resolved through their own Machine >
# Method > Global precedence (see that function's docstring) - already
# apples-to-apples here since both runs were selected from settings_df,
# itself scoped to this run's own Production Method (see the isolation
# comment above).
values_by_run, definitions_by_field = production_run_parameter_dataframe(
    session, [run.id, int(prior["run_id"])],
)
current_values = values_by_run.get(run.id, {})
prior_values = values_by_run.get(int(prior["run_id"]), {})
for field_key, meta in sorted(definitions_by_field.items(), key=lambda kv: kv[1]["label"] or kv[0]):
    if meta["parameter_category"] != "Process Setting":
        continue
    label = meta["label"]
    prev_val, cur_val = prior_values.get(field_key), current_values.get(field_key)
    if prev_val is None or cur_val is None:
        continue
    if meta["data_type"] in ("Float", "Integer"):
        if prev_val == 0:
            continue
        pct_change = (cur_val - prev_val) / abs(prev_val)
        if abs(pct_change) >= 0.02:
            changes.append(f"{label} shifted {pct_change:+.2%}: {prev_val:g} → {cur_val:g}")
            # Kept alongside the display string (not re-derived) so the
            # Root-Cause Comparison Report below can chart shift magnitude
            # without duplicating this loop's math.
            setting_shifts.append({"label": label, "pct_change": pct_change})
    elif meta["data_type"] == "Boolean":
        if bool(prev_val) != bool(cur_val):
            changes.append(
                f"{label} changed: {'Yes' if prev_val else 'No'} → {'Yes' if cur_val else 'No'}"
            )
    elif prev_val != cur_val:
        changes.append(f"{label} changed: {prev_val} → {cur_val}")

# ---------------------------------------------------------------------------
# WP7 Phase 4 Root Cause final targeted completion (2026-08-15, per
# Charlie's Corrected Closeout Review Return to JC): a dedicated
# current-run Process Setting Planned-vs-Actual context, separate from the
# current-vs-prior-run shift comparison below. The shift comparison above
# only ever carries Actual (Planned never substitutes for missing Actual),
# so it cannot show what this run's own Planned target was - this section
# fills that gap using analytics.production_run_process_parameters()'s
# single-run form (via reports.current_run_process_setting_rows(), which
# reuses Batch Release's own definition-driven reader rather than
# re-deriving it).
# ---------------------------------------------------------------------------
current_setting_rows = reports.current_run_process_setting_rows(session, run.id)
st.write(f"**Current run — Process Setting (Planned vs. Actual)** for run #{run.id}")
render_data_table(pd.DataFrame(
    current_setting_rows or [{"—": "No eligible Process Setting definitions for this run"}]
))

if changes:
    st.write("**What was different (vs. prior run):**")
    for c in changes:
        st.write(f"- {c}")
else:
    st.info(
        "No meaningful difference found in recipe, equipment / machine, or recorded process "
        "settings between these two runs — the cause may lie outside what this app currently "
        "captures (raw material lot variation, ambient conditions, downstream handling)."
    )

# ---------------------------------------------------------------------------
# WP7 Phase 4 targeted completion, Item 2 (2026-08-14, per Charlie's
# Closeout Review Return to JC): Environment/Outcome shown as their own
# context sections - visible to the reviewer, but never folded into "What
# was different" above, so they never enter the controllable-setting
# comparison or the PI3 hypothesis prompt's change list. Reuses the exact
# values_by_run/definitions_by_field already computed above.
# ---------------------------------------------------------------------------
env_outcome_rows = reports.environment_outcome_context_rows(
    definitions_by_field, current_values, prior_values,
)
if env_outcome_rows["Environment"] or env_outcome_rows["Outcome"]:
    st.divider()
    st.write(
        "**Environment / Outcome context** (recorded values for both runs — shown for context, "
        "not counted as a controllable setting change)"
    )
    if env_outcome_rows["Environment"]:
        st.caption("Environment")
        render_data_table(pd.DataFrame(env_outcome_rows["Environment"]))
    if env_outcome_rows["Outcome"]:
        st.caption("Outcome")
        render_data_table(pd.DataFrame(env_outcome_rows["Outcome"]))

# ---------------------------------------------------------------------------
# WP7 Phase 4 targeted completion, Item 2 (2026-08-14): run-linked material
# usage/metering, Production Events, and QC context as investigation facts
# - recorded data about the flagged run itself, deliberately separated
# from PI3's inferred hypothesis further down the page.
# ---------------------------------------------------------------------------
investigation_facts = reports.root_cause_investigation_facts(session, run)
st.divider()
st.write(f"**Investigation facts** (recorded data for run #{run.id} — not inferred, not hypotheses)")
st.caption("Material usage / metering")
render_data_table(pd.DataFrame(
    investigation_facts["material_usage_rows"] or [{"—": "No metering data recorded"}]
))
st.caption("Production events")
render_data_table(pd.DataFrame(
    investigation_facts["production_event_rows"] or [{"—": "No events recorded"}]
))
st.caption("QC context — other quality test results on this run")
render_data_table(pd.DataFrame(
    investigation_facts["qc_result_rows"] or [{"—": "No quality test results recorded"}]
))
st.caption("QC context — quality issues logged on this run (including the flagged one)")
render_data_table(pd.DataFrame(
    investigation_facts["qc_issue_rows"] or [{"—": "No other quality issues logged"}]
))

# ---------------------------------------------------------------------------
# Root-Cause Comparison Report (Context / Analysis / Conclusions) - the
# page's own deterministic run-vs-prior-run diff, distinct from PI3's
# hypothesis further down (which has its own separate Word download). Uses
# the exact `changes`/`setting_shifts` already computed above - never
# re-derived.
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Root-Cause Comparison Report")
st.caption(
    f"Context, analysis, and conclusions for {obs.observation_type} on run #{run.id}, compared "
    f"against run #{int(prior['run_id'])}."
)
root_cause_report_data = reports.build_root_cause_report_data(
    session, obs, run, grade, prior, changes, setting_shifts,
    env_outcome_rows=env_outcome_rows, investigation_facts=investigation_facts,
    current_setting_rows=current_setting_rows,
)
rca_rc1, rca_rc2 = st.columns(2)
rca_rc1.metric("Differences found", len(changes))
rca_rc2.metric(
    "Largest setting shift",
    f"{max(setting_shifts, key=lambda s: abs(s['pct_change']))['label']}" if setting_shifts else "—",
)
st.download_button(
    "Download Word", data=reports.render_root_cause_report_docx(root_cause_report_data),
    file_name="root_cause_comparison_report.docx",
    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    key=f"root_cause_report_docx_{obs.id}",
    on_click=log_export_click, args=("root_cause_report_docx",),
    kwargs={"description": f"{obs.observation_type} · run #{run.id}"},
)

if ai_assistant.is_enabled_for_plant(session, run.plant_id):
    st.divider()
    if st.button(
        "Use PI3 to reason about this",
        key=f"ask_pi3_root_cause_{obs.id}",
        disabled=not page_usable,
    ):
        change_summary = (
            "\n".join(f"- {c}" for c in changes)
            if changes
            else (
                "No meaningful difference was found in recipe, equipment / machine, or "
                "recorded process settings between these two runs."
            )
        )
        # WP7 Phase 4 targeted completion, Item 2 (2026-08-14): the same
        # investigation_facts/env_outcome_rows already rendered on-screen,
        # summarized as recorded facts for PI3 - never re-derived, and
        # explicitly labeled as facts (not hypotheses) so PI3 doesn't
        # conflate a recorded metering reading or QC result with an
        # inferred cause.
        facts_lines = []
        if investigation_facts["material_usage_rows"]:
            facts_lines.append(
                f"- {len(investigation_facts['material_usage_rows'])} material metering "
                f"reading(s) recorded for run #{run.id}."
            )
        if investigation_facts["production_event_rows"]:
            facts_lines.append(
                f"- {len(investigation_facts['production_event_rows'])} production event(s) "
                f"logged for run #{run.id}."
            )
        if investigation_facts["qc_result_rows"]:
            facts_lines.append(
                f"- {len(investigation_facts['qc_result_rows'])} other quality test result(s) "
                f"recorded for run #{run.id}."
            )
        if investigation_facts["qc_issue_rows"]:
            facts_lines.append(
                f"- {len(investigation_facts['qc_issue_rows'])} other quality issue(s) logged "
                f"for run #{run.id}."
            )
        if env_outcome_rows["Environment"] or env_outcome_rows["Outcome"]:
            facts_lines.append(
                "- Environment/Outcome context is recorded for both runs (shown separately on "
                "the page - not a controllable setting, do not treat as a lever to adjust)."
            )
        facts_summary = (
            "\n".join(facts_lines)
            if facts_lines
            else "No additional metering, event, or QC context recorded for this run."
        )
        # WP7 Phase 4 Root Cause final targeted completion (2026-08-15, per
        # Charlie's Corrected Closeout Review Return to JC): the count-only
        # facts_summary above is retained as a short lead-in, but PI3 also
        # needs the actual recorded fact VALUES (not just counts) so it can
        # reason about specifics rather than being told "3 readings were
        # recorded" with no way to know what those readings were. Built via
        # reports.format_root_cause_facts_for_pi3() - a pure, testable
        # function - reusing the same investigation_facts/env_outcome_rows
        # already on screen, plus the new current-run Planned-vs-Actual
        # Process Setting context, never re-derived.
        detailed_facts = reports.format_root_cause_facts_for_pi3(
            investigation_facts, env_outcome_rows, current_setting_rows
        )
        prompt = (
            "You are helping a technical reviewer at a rigid PUR/PIR foam manufacturer "
            "investigate a quality issue. Below is a deterministic comparison between the "
            "flagged production run and the most recent prior run of the same product grade. "
            "Using this comparison plus any relevant expert notes or historical cases in the "
            "connected knowledge base, suggest possible hypotheses for the root cause.\n\n"
            "IMPORTANT: this is a starting point for investigation, not a diagnosis. Never "
            "phrase your answer as a directive or a definitive cause (e.g. do not say "
            "'increase TDI by X' or 'the cause is Y'). Always phrase it as hypotheses for the "
            "reviewer to investigate and confirm themselves.\n\n"
            "DISCIPLINE REQUIRED IN YOUR REASONING (a prior answer from this feature was "
            "reviewed by a formulation expert and found too quick to rank causes without "
            "enough evidence - follow these rules to avoid repeating that):\n"
            "1. State any percentage change to at least two decimal places, exactly as given "
            "below - never round '-3.47%' down to '-3%'.\n"
            "2. Before proposing any ranking, first ask what is actually known about the "
            "failure itself: did it collapse while still rising, settle immediately at peak "
            "rise, or shrink later during cooling? Was it localized or across the whole bun? "
            "What did the cell structure look like (coarse, ruptured, tight, normal)? If this "
            "app's data does not capture that, say so explicitly and list it as the first, "
            "still-open investigation item - do not silently assume a failure mode.\n"
            "3. Do not call any subset of hypotheses 'leading' or imply a priority ordering "
            "unless you can point to a specific piece of evidence in the comparison or the "
            "knowledge base that favors one hypothesis over another. If no such evidence "
            "exists, present hypotheses as an unranked candidate set and say the ranking "
            "requires more evidence (morphology, timing, actual-vs-setpoint deliveries).\n"
            "4. Give equal analytical weight to overall stoichiometry/index and mixing "
            "factors (water dosage, isocyanate/TDI delivery and index, component "
            "temperatures, mixing energy or pressure, polyol-blend homogeneity) alongside "
            "additive-level factors (silicone, catalysts). The fact that air injection is "
            "the only recorded numeric difference does not mean other factors are less "
            "likely - it only means this app didn't capture a difference in them for this "
            "comparison. Do not let one recorded change anchor the whole explanation.\n"
            "5. When discussing amine catalysts, do not say 'excessive amine' as a blanket "
            "statement. Amine catalysts vary - some are blow-selective, some gel-selective, "
            "some balanced. Frame this hypothesis as 'excessive effective blow catalysis "
            "relative to gel development', and note it could come from over-delivery of a "
            "blow-selective amine, under-delivery/deactivation of tin, excess water, a low "
            "index, temperature-driven acceleration, or a wrong catalyst grade/concentration.\n"
            "6. Keep 'reduced/wrong silicone performance' (wrong grade, degraded, incompatible, "
            "under- or over-dosed, poor blending) analytically separate from 'foreign-material "
            "contamination' (mold-release agent, external oil/grease, defoamer, cleaning "
            "residue, water). Do not describe silicone itself as a contaminant - it is a "
            "deliberate formulation component. Note that too much silicone/stabilization can "
            "also cause tight cells and shrinkage, not just too little causing collapse.\n"
            "7. Comment on whether the comparison run is actually a sound baseline (same "
            "formulation, comparable density, similar raw-material lots, comparable "
            "temperatures, same equipment configuration, no intervening maintenance) - if "
            "that cannot be confirmed from what's given, flag it as a caveat and suggest "
            "also checking the nearest stable run immediately before and after the flagged "
            "run, not only this one historical comparison.\n"
            "8. Close with a short, appropriately hedged synthesis: state plainly what is "
            "directly known (the recorded change) versus what is inferred, and avoid "
            "presenting a narrow additive-focused explanation as the most coherent one "
            "before the failure's timing and morphology are established.\n\n"
            f"Quality issue: {obs.observation_type} on run #{run.id} ({grade.grade_name}), "
            f"{obs.severity}/{obs.frequency}\n"
            + (f"Logged suspected cause: {obs.suspected_cause}\n" if obs.suspected_cause else "")
            + f"Compared against prior run #{int(prior['run_id'])} ({prior['run_date']})\n\n"
            f"What was different:\n{change_summary}\n\n"
            f"Recorded investigation facts for run #{run.id} (facts, not hypotheses - do not "
            f"present these counts themselves as a cause):\n{facts_summary}\n\n"
            f"Recorded fact VALUES for run #{run.id} (use these specific recorded values in "
            f"your reasoning - do not treat 'not recorded' fields as zero or as evidence of "
            f"absence):\n{detailed_facts}\n"
        )
        with st.spinner("Using PI3..."):
            answer, interaction_log_id = ai_assistant.ask_assistant(
                prompt, company_id=active_company_id, call_site="root_cause_assistant"
            )
        if answer:
            st.session_state[f"root_cause_ai_answer_{obs.id}"] = answer
            st.session_state[f"root_cause_ai_interaction_id_{obs.id}"] = interaction_log_id
            st.session_state.pop(f"root_cause_fixed_{obs.id}_saved_note_id", None)
            st.session_state.pop(f"root_cause_fixed_{obs.id}_feedback_submitted", None)

    ai_answer = st.session_state.get(f"root_cause_ai_answer_{obs.id}")
    if ai_answer:
        st.subheader("🤖 PI3 hypothesis")
        st.caption(
            "Generated by PI3 from the comparison above plus expert notes and historical "
            "cases. Confirm any hypothesis through your own investigation before acting on it."
        )
        st.write(ai_answer)
        render_pi3_feedback_control(
            session, st.session_state.get(f"root_cause_ai_interaction_id_{obs.id}"),
            key_prefix=f"root_cause_fixed_{obs.id}",
        )

        rc_question_label = f"PI3 root-cause hypothesis for {obs.observation_type} on run #{run.id} ({grade.grade_name})"
        rc_dl_col, rc_save_col = st.columns([1, 1])
        with rc_dl_col:
            render_pi3_docx_download(
                session,
                run.plant_id,
                key_prefix=f"root_cause_fixed_{obs.id}",
                question_label=rc_question_label,
                answer=ai_answer,
                foam_grade_id=grade.id,
            )
        with rc_save_col:
            render_save_to_expert_notes_button(
                session,
                key_prefix=f"root_cause_fixed_{obs.id}",
                answer=ai_answer,
                question_label=rc_question_label,
                link_type="production_run",
                entity_id=run.id,
                disabled=not page_usable,
            )

st.divider()
render_ask_pi3_section(
    session,
    run.plant_id,
    default_foam_grade_id=grade.id,
    page_context=(
        f"The reviewer is on the Root-Cause Assistant page, investigating "
        f"'{obs.observation_type}' ({obs.severity}/{obs.frequency}) on run #{run.id} of foam "
        f"grade '{grade.grade_name}', compared against prior run #{int(prior['run_id'])}."
    ),
    sample_questions=[
        f"What raw material lots were used on run #{run.id} versus run #{int(prior['run_id'])}?",
        f"Has {obs.observation_type} happened before on {grade.grade_name}, and what was found?",
        f"Were there any maintenance events or interventions logged around run #{run.id}?",
    ],
    key_prefix=f"ask_pi3_freeform_root_cause_{obs.id}",
    note_link_type="production_run",
    note_entity_id=run.id,
    disabled=not page_usable,
)

