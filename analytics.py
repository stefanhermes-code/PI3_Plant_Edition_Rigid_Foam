"""Shared data-assembly helpers for the Industrial Intelligence pages.

The real value of PI3 Plant Edition is the join that already exists in the
schema: a production run carries a recipe (version + components), a
machine, its Finalized-phase process settings, and the physical property
results / quality observations it produced - all keyed to the same
production_run_id. Every Industrial Intelligence function (Recipe
Optimization, Trend Analysis, Machine Settings vs Physical Properties
Correlation, Root-Cause Assistant, Machine Settings Optimization) starts
from that same join, so it is built once here rather than five
slightly-different copies of the same query living in each page.

Every `foam_grade_id` parameter below (see _grade_id_list) accepts either a
single product grade's id (the original, most common case) or a list of ids -
the latter is how "analyze by foam family" works (Trend Analysis,
Machine Settings vs Physical Properties Correlation, and Machine Settings
Optimization): a product family's member grades are resolved to their ids
by helpers.analysis_unit_picker and passed through here as a list, pooling
every one of those grades' runs into the same analysis. Recipe Optimization
and Root-Cause Assistant stay single-grade-only - their sections (current
formulation/cost, version diff, run-vs-prior-run diff) are inherently about
one specific grade's recipe, not something that pools sensibly.

Note: ProductionRun deliberately has no back-populated .phases/.results
collections (see the comment on ProductionRun in db.py - it avoids a
Streamlit/SQLAlchemy deepcopy crash). Every function below queries
ProductionPhase/PhysicalPropertyResult directly by production_run_id
instead.
"""

import datetime as dt
import random
import time

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats as scipy_stats
from sqlalchemy.orm import joinedload

from db import (
    ComponentStreamReading,
    CustomerTrial,
    FoamGrade,
    OptimizationTrial,
    PerformanceLog,
    PhysicalPropertyResult,
    ProcessParameterValue,
    ProcessSettingApplicability,
    ProcessSettingDefinition,
    ProductionMethod,
    ProductionOutputSummary,
    ProductionPhase,
    ProductionRun,
    RawMaterial,
    RawMaterialAttributeDefinition,
    RawMaterialAttributeValue,
    RecipeVersion,
    UnitOfMeasure,
)
from quality_standards import compute_pass_fail


# compute_runtime_output(phase, foam_grade) - the continuous-conveyor-line
# length/volume/weight calculation (conveyor speed x recorded duration,
# tunnel width x foam height x length x target density) - was retired
# under WP7 Phase 5 (2026-08-15, per the Phase 5 Legacy Retirement and
# Final UAT Execution Contract, Scope Item 4: "Remove universal
# compute_runtime_output authority and any obsolete geometry-based output
# logic from active code"). Its sole remaining active call site was
# pages/4_Production_Run_Trial_Record.py's Runtime Data "Calculated
# output" display, reading ProductionPhase.conveyor_speed/sidewall_width_
# mm/foam_height_mm/meters_produced - a formula architecturally
# inapplicable to Rigid Foam's discontinuous (press-foamed/molded)
# production and already superseded by the WP7 Phase 1/2 method-aware
# Production Output & Disposition tab (ProductionOutputSummary, the sole
# active production output/disposition fact per the Phase 5 contract's
# Decision Ledger D5-07). See WP7_Phase5_JC_PreCoding_Engineering_
# Challenge_Response.docx for the full dependency scan this retirement was
# based on.


def _log_performance(_session, function_name, foam_grade_id, property_name, duration_ms, row_count):
    """Records one PerformanceLog row (see db.py) for a cache-MISS call to
    one of the three functions below - added 2026-08-02 in response to a
    reported "app feels slow in general", so there's a real, persistent
    record of how expensive each actual database fetch was, visible on the
    Performance admin page, instead of only ever being able to guess.

    Best-effort only and must never be able to break a page: any failure
    (including this table not existing yet on some environment that hasn't
    picked up this migration) is swallowed silently rather than surfaced -
    a performance-monitoring feature must never be the thing that takes an
    Intelligence page down. Also does cheap, infrequent housekeeping (a ~2%
    chance per call of trimming rows older than 30 days) so this table
    doesn't grow unbounded on a deployment nobody manually tidies."""
    try:
        grade_ids = _grade_id_list(foam_grade_id)
        _session.add(
            PerformanceLog(
                function_name=function_name,
                grade_ids=",".join(str(g) for g in grade_ids) if grade_ids else None,
                property_name=property_name,
                row_count=row_count,
                duration_ms=round(duration_ms, 2),
            )
        )
        _session.commit()
        if random.random() < 0.02:
            cutoff = dt.datetime.utcnow() - dt.timedelta(days=30)
            _session.query(PerformanceLog).filter(PerformanceLog.created_at < cutoff).delete()
            _session.commit()
    except Exception:
        _session.rollback()

# Cache TTL for the three DB-loading functions below (run_settings_dataframe,
# property_results_dataframe, actual_usage_dataframe). Fixed 2026-08-02: these
# were being re-queried from scratch on every Streamlit rerun - which happens
# on every widget click on a page, not just on navigation - and each one is
# used by every Industrial Intelligence page, several of them multiple times
# per rerun (once to check which grades have data for a dropdown, again for
# the selected grade, again inside ranking/correlation helpers). Caching them
# turns most of those repeat calls within a single page visit into a
# dict-lookup instead of a round trip to Supabase. 30s is short enough that
# entering new data and immediately switching to an analysis page won't look
# stale for long, but long enough to absorb the burst of reruns a reviewer
# generates while adjusting selectboxes on one page. Keyed only on
# foam_grade_id/property_name (the session argument is prefixed with `_` so
# Streamlit doesn't try to hash the SQLAlchemy Session object itself) - safe
# across users because a foam_grade_id already scopes to one company, so
# there's no cross-tenant leak risk in sharing this cache.
_DATA_CACHE_TTL = 30


def _grade_id_list(foam_grade_id):
    """Every function below that takes `foam_grade_id` accepts either a
    single id (the original "analyze one product grade" case) or a list/tuple
    of ids (analyzing a whole foam family - a product family's grades
    pooled together, see analysis_unit_picker in helpers.py). Normalizes
    both shapes to a list (or None) so the caller can always filter with
    `.in_()`. None/empty means "no grade filter" (every grade)."""
    if foam_grade_id is None:
        return None
    if isinstance(foam_grade_id, (list, tuple, set)):
        return list(foam_grade_id) or None
    return [foam_grade_id]

# Machine/process settings captured per phase (see ProductionPhase in
# db.py) - deliberately CONTROLLABLE inputs only, not measured outcomes.
# These are the fields every process-vs-quality analysis works from: the
# "Machine Settings vs Physical Properties Correlation" and "Machine
# Settings Optimization" pages both present this list as "the settings you
# can act on", so a field that isn't actually something an operator sets
# has no business appearing in either ranking - it would read as if
# adjusting an outcome were the lever, which it never is.
#
# foam_height_mm, ambient_temperature_c, ambient_humidity_pct, and
# rise_time were removed from this list on 2026-08-05 (a user correctly
# spotted foam_height_mm still showing up in the correlation/optimization
# rankings as if it were a "process setting"): all 4 are measured outcomes
# of the foaming process, not configured inputs - see db.py's
# ProductionPhase docstrings, and the 2026-08-03 decision that already
# removed these same 4 fields from the Setup tab for exactly this reason
# (foam_height_mm/ambient_* "RETIRED FROM THE SETUP TAB... a measured
# outcome, not something planned"). That Setup-tab fix never propagated
# back to this list, which is why the correlation/optimization pages kept
# ranking them as settings for two more days. They're still readable
# directly off ProductionPhase wherever a page genuinely wants the
# observed outcome (e.g. Trend Analysis, or the Runtime Data tab's own
# display) - just no longer treated as a lever to "optimize".
#
# ratio_index removed from this list on 2026-08-05 for the same class of
# bug, different cause: it's not a measured outcome, it's a recipe-level
# formulation constant (the isocyanate index), moved from
# ProductionPhase.ratio_index to RecipeVersion.ratio_index back on
# 2026-08-03 (see db.py) specifically because every run of a given recipe
# version uses the same value - it isn't something an operator sets per
# production run the way mixer rpm or air pressure is. run_settings_
# dataframe below was correctly updated on 2026-08-03 to source its value
# from the recipe rather than the phase, but nobody removed it from this
# field/label list at the same time, so it kept showing up in the "Process
# setting" drill-down dropdowns and the correlation/optimization rankings
# on pages 17 and 19 as if it were a machine setting - a user correctly
# flagged this on 2026-08-05. It's still fully available as a recipe
# property wherever that's the right frame (pages/3_Recipe_Version_
# Record.py, and the Recipe report sections in reports.py) - just not
# ranked here as a lever an operator can "optimize" on a given run.
#
# Ported into PI3_Rigid_Foam_Edition_App on 2026-08-06: this fork was
# created from the flexible-foam app's v2.0.1 commit, one day before this
# fix shipped as v2.0.2 on the flexible side, so the fork was carrying the
# same stale-list bug. Applied identically here rather than re-deciding it,
# since it's a defect in inherited code, not a rigid-foam design choice -
# the rigid schema still needs its own settings model per the Technical
# Research and Data Population Plan (method-aware settings, not this
# Maxfoam-specific list), but that's separate, larger work - see
# version.py for the baseline note.
#
# PHASE_SETTING_FIELDS / PHASE_SETTING_LABELS / BOOLEAN_SETTING_FIELDS /
# PHASE1_RIGID_INELIGIBLE_SETTINGS / eligible_phase_setting_fields() - the
# five-field fixed ProductionPhase compatibility layer (mixer_rpm,
# conveyor_speed, air_injection_rate, air_pressure_bar, sidewall_width_mm)
# inherited from the flexible/continuous-line foam app's fork baseline -
# were removed under WP7 Phase 5 (2026-08-15, per the Phase 5 Legacy
# Retirement and Final UAT Execution Contract, Scope Item 4: "Remove fixed
# PHASE_SETTING_FIELDS, PHASE_SETTING_LABELS and related compatibility
# authority when no remaining active consumer requires them"). Their last
# remaining live consumer, run_settings_dataframe() below, was simplified
# in the same change to return identity/candidate-selection columns only
# (its only two live callers never read a legacy field value by name - see
# the Phase 5 challenge-response document's dependency scan). These five
# fields' data is not lost: the four with a completed migration (ambient_
# temperature_c, ambient_humidity_pct, foam_height_mm, rise_time) already
# live in ProcessParameterValue (see legacy_migration.py); the remaining
# five (mixer_rpm, conveyor_speed, sidewall_width_mm, air_injection_rate,
# air_pressure_bar) have no migrated equivalent and remain deferred/
# quarantined per the Phase 5 contract's Decision Ledger (D5-04, D5-05) -
# ProductionPhase itself is retained as an ARCHIVE READ-ONLY structure
# (ratio_index removal from correlation and the rest of the shared-reader
# cutover, WP7 Phase 4, already left it as zero-active-reader-authority
# for every other consumer).


def production_methods_used(session, foam_grade_id):
    """The distinct Production Methods actually behind the selected foam
    grade(s)' production runs (via each run's immutable production_
    method_id snapshot), ordered for a filter dropdown - what pages 15-19
    (Industrial Intelligence) offer as the "isolate to one Production
    Method" choice added 2026-08-10 per Charlie's flat-PM technical
    completion instruction. Deliberately built from actual run history,
    not from every method activated at the plant - a method nobody has
    actually run yet for this grade would be a dead-end filter choice.
    `foam_grade_id` accepts a single id or a list (a pooled foam family) -
    see _grade_id_list."""
    grade_ids = _grade_id_list(foam_grade_id)
    q = session.query(ProductionMethod).join(
        ProductionRun, ProductionRun.production_method_id == ProductionMethod.id
    )
    if grade_ids:
        q = q.filter(ProductionRun.foam_grade_id.in_(grade_ids))
    return sorted(set(q.all()), key=lambda m: (m.sort_order or 0, m.name))


def eligible_process_settings(session, production_method_id, machine_id=None):
    """WP7 Phase 1 (2026-08-13). Returns the method-aware
    ProcessSettingDefinition rows eligible for a given Production Method
    (and, optionally, a specific Machine / "Production Unit or Cell"),
    each paired with its winning ProcessSettingApplicability row.

    Per Charlie's WP7 Phase 1 Design Review and Architecture Decision
    (PI3_Rigid_Foam_Development_Docs/Phase 1/WP7_Phase1_Design_Review_
    Architecture_Decision_for_JC.docx), section 3.1/4: applicability is
    looked up on the separate ProcessSettingApplicability table (NOT
    ProcessSettingDefinition.production_method_id, which is a deprecated,
    dormant field left over from before this correction - see that
    column's docstring in db.py). Eligibility precedence for the same
    setting_definition_id is deterministic: Machine-specific first, then
    Method-specific, then Global (production_method_id NULL and
    machine_id NULL) - exactly one eligible row is returned per
    definition. No name matching and no supersedes_id mechanism (an
    explicit decision, closing the open question JC raised in the Phase 1
    design deliverables).

    Returns a list of (ProcessSettingDefinition, ProcessSettingApplicability)
    tuples, ordered by definition.sort_order then definition.name. Both
    the definition and the applicability row must be active=True; retired
    (active=False) rows never surface here, on either side."""
    query = (
        session.query(ProcessSettingApplicability)
        .join(ProcessSettingDefinition, ProcessSettingApplicability.setting_definition_id == ProcessSettingDefinition.id)
        .filter(ProcessSettingApplicability.active == True)  # noqa: E712
        .filter(ProcessSettingDefinition.active == True)  # noqa: E712
        .filter(
            (ProcessSettingApplicability.production_method_id == production_method_id)
            | (ProcessSettingApplicability.production_method_id.is_(None))
        )
    )
    if machine_id is not None:
        query = query.filter(
            (ProcessSettingApplicability.machine_id == machine_id)
            | (ProcessSettingApplicability.machine_id.is_(None))
        )
    else:
        query = query.filter(ProcessSettingApplicability.machine_id.is_(None))

    # WP7 Phase 1 correction (Charlie's closeout review, 2026-08-14, item
    # 2.1): db.py's ix_psa_unique_active_scope partial unique index now
    # makes a same-scope active tie impossible at the data layer. This
    # ORDER BY is defense-in-depth only, so that even if that constraint
    # were ever bypassed, tie resolution below is deterministic (lowest id
    # wins) rather than depending on unordered database row order.
    query = query.order_by(ProcessSettingApplicability.id)

    rows = query.all()

    # Deterministic precedence per definition: Machine-specific (2) >
    # Method-specific (1) > Global (0). Highest-specificity row wins; a
    # same-specificity tie (prevented by ix_psa_unique_active_scope, see
    # above) would keep the lowest-id row, per the ORDER BY.
    def _specificity(row):
        if row.machine_id is not None:
            return 2
        if row.production_method_id is not None:
            return 1
        return 0

    winners = {}
    for row in rows:
        current = winners.get(row.setting_definition_id)
        if current is None or _specificity(row) > _specificity(current):
            winners[row.setting_definition_id] = row

    results = [(row.setting_definition, row) for row in winners.values()]
    results.sort(key=lambda pair: (pair[0].sort_order if pair[0].sort_order is not None else 999999, pair[0].name))
    return results


def dynamic_process_setting_field_key(setting_definition_id):
    """The synthetic field key one method-aware ProcessSettingDefinition is
    exposed under in production_run_parameter_dataframe()'s columns -
    id-based (not controlled_id-based) so it stays stable even if a
    controlled_id were ever renumbered, and namespaced with 'ps_' so it
    can never collide with a legacy PHASE_SETTING_FIELDS column name
    (none of which start with 'ps_')."""
    return f"ps_{setting_definition_id}"


def production_run_process_parameters(session, production_run):
    """WP7 Phase 4 shared reader (2026-08-14, per Charlie's WP7 Phase 4
    Downstream Reader Cutover Execution Instruction and his Architecture
    Clarification and Direction to JC, which rejected the v0.46.0 hybrid
    approach this function replaces). THE canonical, single source of
    truth for one production run's process-parameter facts - every active
    consumer (Overview/output KPIs, Batch Release/Conformance, generated
    reports, PI3 Production Run context, Root Cause Assistant, Trend
    Analysis, Process-Property Correlation, Process Parameter
    Optimization, shared CSV/Excel exports) must read through this
    function (or production_run_parameter_dataframe below, its multi-run
    form), never through ProductionPhase or the legacy
    PHASE_SETTING_FIELDS/PHASE_SETTING_LABELS/
    PHASE1_RIGID_INELIGIBLE_SETTINGS lists, which retain zero
    active-reader authority per the Phase 4 architecture.

    `production_run` accepts either a ProductionRun instance or its id.

    Resolves this run's eligible ProcessSettingDefinition rows via
    eligible_process_settings(session, run.production_method_id,
    machine_id=run.machine_id) - unchanged Machine > Method > Global
    precedence, one winning ProcessSettingApplicability per definition.
    An empty live catalogue (today's actual state - see
    WP7_Phase4_Flag_for_Charlie.docx) correctly returns [] here: Charlie's
    clarification, section 3 item 4, "Allow the live Process Setting
    result to be empty when no approved applicability exists. The UI and
    downstream consumers present the honest empty state rather than
    reviving legacy values." This is not an error and never falls back to
    ProductionPhase.

    Returns a list of dicts, one per eligible definition, each with:
      definition_id, controlled_id, name, parameter_category, data_type,
      unit_id, unit_symbol (the definition's own canonical UOM - never a
      caller-supplied unit), controllable, analytics_eligible (both from
      the winning applicability), planned_value, actual_value (typed -
      whichever of numeric_value/text_value/boolean_value is populated on
      the matching ProcessParameterValue row; None if that snapshot was
      never recorded for this run/definition), delta (actual_value -
      planned_value, only when both are present AND data_type is Float
      or Integer - otherwise None; a numeric type never silently
      substitutes Planned for a missing Actual, per Charlie's fallback-
      semantics correction), planned_source/actual_source,
      planned_captured_at/actual_captured_at.

    WP7 Phase 4 targeted-completion addition (2026-08-14, Charlie's
    Closeout Review Return to JC, Material Completion Item 1.2): also
    returns min_value, max_value (the definition's own default validation
    range) and min_value_override, max_value_override (the winning
    applicability row's scope-specific override, when set) - purely
    additive fields so existing consumers (Overview, Correlation,
    Optimization, Trend, Root Cause) that only read the keys they already
    know about are unaffected. The Batch Release / generated-report
    reader is the first consumer to resolve these into a controlled
    acceptance limit (reports._effective_limit); a caller that ignores
    these four keys sees no behavior change at all.

    Actual is the production fact this function's callers must treat as
    the analytics input; Planned is separate plan/target/delta context
    only, and is never substituted when Actual is missing - a missing
    Actual value stays None all the way through, exactly as Charlie's
    clarification requires ("Missing Actual remains missing").

    Ordered in the same sort_order/name order eligible_process_settings
    already returns, so callers needing display order never re-sort."""
    if isinstance(production_run, int):
        run = session.get(ProductionRun, production_run)
    else:
        run = production_run
    if run is None:
        return []

    eligible = eligible_process_settings(session, run.production_method_id, machine_id=run.machine_id)
    if not eligible:
        return []

    definition_ids = [definition.id for definition, _applicability in eligible]
    value_rows = (
        session.query(ProcessParameterValue)
        .filter(
            ProcessParameterValue.production_run_id == run.id,
            ProcessParameterValue.setting_definition_id.in_(definition_ids),
            ProcessParameterValue.snapshot_type.in_(("Planned", "Actual")),
        )
        .all()
    )
    values_by_definition = {}
    for value_row in value_rows:
        values_by_definition.setdefault(value_row.setting_definition_id, {})[value_row.snapshot_type] = value_row

    def _typed_value(value_row):
        if value_row is None:
            return None
        if value_row.numeric_value is not None:
            return value_row.numeric_value
        if value_row.text_value is not None:
            return value_row.text_value
        if value_row.boolean_value is not None:
            return value_row.boolean_value
        return None

    rows = []
    for definition, applicability in eligible:
        slot = values_by_definition.get(definition.id, {})
        planned_row = slot.get("Planned")
        actual_row = slot.get("Actual")
        planned_value = _typed_value(planned_row)
        actual_value = _typed_value(actual_row)
        delta = None
        if (
            definition.data_type in ("Float", "Integer")
            and planned_value is not None
            and actual_value is not None
        ):
            delta = actual_value - planned_value
        rows.append({
            "definition_id": definition.id,
            "controlled_id": definition.controlled_id,
            "name": definition.name,
            "parameter_category": definition.parameter_category,
            "data_type": definition.data_type,
            "unit_id": definition.unit_id,
            "unit_symbol": definition.unit.symbol if definition.unit else None,
            "controllable": bool(applicability.controllable),
            "analytics_eligible": bool(applicability.analytics_eligible),
            "planned_value": planned_value,
            "actual_value": actual_value,
            "delta": delta,
            "planned_source": planned_row.source if planned_row else None,
            "actual_source": actual_row.source if actual_row else None,
            "planned_captured_at": planned_row.captured_at if planned_row else None,
            "actual_captured_at": actual_row.captured_at if actual_row else None,
            # WP7 Phase 4 targeted-completion addition (2026-08-14) - see
            # docstring above. Additive only.
            "min_value": definition.min_value,
            "max_value": definition.max_value,
            "min_value_override": applicability.min_value_override,
            "max_value_override": applicability.max_value_override,
        })
    return rows


def production_run_parameter_dataframe(session, run_ids):
    """WP7 Phase 4 shared reader (multi-run form, 2026-08-14). Calls
    production_run_process_parameters(session, run_id) once per run in
    `run_ids` - a genuine per-run Machine > Method > Global resolution,
    not a Method/Global-only shortcut applied uniformly across a pooled
    set of runs - so two runs on different Units/Cells under the same
    Production Method can correctly surface different eligible
    definitions, exactly per Charlie's "Applicability depth" correction
    to the v0.46.0 hybrid.

    Returns a tuple (values_by_run, definitions_by_field):
      values_by_run: {run_id: {field_key: actual_value, ...}} - one dict
        per run, keyed by dynamic_process_setting_field_key(definition_id).
        Only Actual values populate this dataframe-style structure -
        Process Parameter Optimization/Correlation analyze Actual as the
        production fact (Charlie's Planned-never-substitutes rule); a
        caller needing Planned/delta/metadata should read
        production_run_process_parameters directly for that one run.
      definitions_by_field: {field_key: {"definition_id", "label",
        "parameter_category", "data_type", "controllable",
        "analytics_eligible", "unit_symbol"}} - the union of every
        definition encountered across all requested runs, so a caller can
        build column headers/labels without a second query, and can
        filter columns by category/controllable/analytics_eligible/
        data_type itself (Charlie's "individual analytics functions may
        restrict to compatible numeric inputs" - this shared reader does
        not pre-filter by data_type, only the correlation/optimization
        callers do).

    A run whose eligible catalogue is empty (today's actual live state -
    zero approved 'Process Setting' applicability rows anywhere, see
    WP7_Phase4_Flag_for_Charlie.docx) contributes an empty {} to
    values_by_run for that run_id - the honest empty state, never a
    legacy ProductionPhase fallback."""
    values_by_run = {}
    definitions_by_field = {}
    for run_id in run_ids:
        params = production_run_process_parameters(session, run_id)
        row = {}
        for p in params:
            field_key = dynamic_process_setting_field_key(p["definition_id"])
            row[field_key] = p["actual_value"]
            if field_key not in definitions_by_field:
                definitions_by_field[field_key] = {
                    "definition_id": p["definition_id"],
                    "label": p["name"] or p["controlled_id"] or field_key,
                    "parameter_category": p["parameter_category"],
                    "data_type": p["data_type"],
                    "controllable": p["controllable"],
                    "analytics_eligible": p["analytics_eligible"],
                    "unit_symbol": p["unit_symbol"],
                }
        values_by_run[run_id] = row
    return values_by_run, definitions_by_field


def process_parameter_definitions_for_trend(session, foam_grade_id, production_method_id=None):
    """WP7 Phase 4 targeted completion, Item 3 (2026-08-14, per Charlie's
    WP7 Phase 4 Closeout Review Return to JC, Material Completion Item 3 -
    "the governing Phase 4 instruction explicitly includes Trend Analysis
    ... this acceptance path therefore cannot be skipped"). The picker
    list behind Trend Analysis's new "Process parameter" trend subject:
    every ProcessSettingDefinition eligible for at least one of this
    grade's/family's production runs (via the shared reader,
    production_run_parameter_dataframe - never ProductionPhase), with no
    category restriction - Process Setting, Environment, and Outcome are
    all offered, per Charlie's instruction 3.2 ("Trend may expose Process
    Setting, Environment and Outcome categories as recorded facts").
    Restricted to a numeric data_type (Float/Integer) because the SPC
    toolkit (control chart/capability/CUSUM/trend test) this page reuses
    unchanged needs a numeric series - a Boolean or Text definition has no
    meaningful control limit or slope. `foam_grade_id` accepts a single id
    or a list (a pooled foam family) - see _grade_id_list.

    Returns a list of (field_key, meta_dict) pairs, meta_dict being the
    same dict shape production_run_parameter_dataframe's definitions_by_field
    already returns (definition_id, label, parameter_category, data_type,
    controllable, analytics_eligible, unit_symbol), sorted by label."""
    grade_ids = _grade_id_list(foam_grade_id)
    q = session.query(ProductionRun.id)
    if grade_ids:
        q = q.filter(ProductionRun.foam_grade_id.in_(grade_ids))
    if production_method_id:
        q = q.filter(ProductionRun.production_method_id == production_method_id)
    run_ids = [row[0] for row in q.all()]
    if not run_ids:
        return []
    _values_by_run, definitions_by_field = production_run_parameter_dataframe(session, run_ids)
    items = [
        (field_key, meta) for field_key, meta in definitions_by_field.items()
        if meta["data_type"] in ("Float", "Integer")
    ]
    items.sort(key=lambda pair: pair[1]["label"])
    return items


def process_parameter_run_series(session, foam_grade_id, setting_definition_id, production_method_id=None):
    """WP7 Phase 4 targeted completion, Item 3 (2026-08-14). One row per
    production run for a single method-aware ProcessSettingDefinition,
    sourced exclusively through the shared reader
    (production_run_parameter_dataframe, itself built on
    production_run_process_parameters) - never ProductionPhase or the
    legacy PHASE_SETTING_FIELDS/PHASE_SETTING_LABELS lists, which retain
    zero active-reader authority under the Phase 4 architecture. A run
    whose ProductionPhase happens to carry a same-named legacy field (e.g.
    ambient_temperature_c) with a conflicting value never enters this
    series - only a real ProcessParameterValue Actual snapshot for this
    exact setting_definition_id does (see
    tests/test_wp7_phase4_trend_cutover.py's source-isolation test, which
    seeds a deliberately conflicting ProductionPhase value to prove this).

    Mirrors property_run_series's output shape/contract exactly (run_id,
    tested_at, actual_value, target_value, recipe_version, machine,
    foam_grade, source, n_replicates columns) so it plugs into the
    existing SPC functions (control_chart_analysis, capability_analysis,
    cusum_analysis, trend_test) - and the existing
    reports.build_trend_analysis_report_data() - completely unchanged.
    This is a second, fully separate series builder; property_run_series
    itself is not touched, so "existing physical-property SPC
    functionality remains intact" per Charlie's instruction.

    A run with no recorded Actual for this definition is dropped from the
    series - NULL preserved as unrecorded, per Charlie's instruction 3.2.
    A run with a recorded Actual of exactly 0 is kept - dropna() only
    removes None/NaN, never a real recorded zero, exactly as
    property_run_series already behaves for a quality property.
    target_value is this run's own Planned snapshot for the same
    definition (when recorded) - the process-parameter analogue of a
    property's target_value, letting capability_analysis's +/-10%
    fallback and cusum_analysis's reference-point logic work unchanged.
    unit_symbol (canonical UOM) always comes from the definition itself,
    the same single source of truth eligible_process_settings/
    production_run_process_parameters already resolve it from - never
    re-derived or caller-supplied here.

    Returns an empty DataFrame if this definition isn't eligible for any
    of this grade's/family's runs, isn't numeric (Float/Integer), or has
    no recorded Actual anywhere yet."""
    grade_ids = _grade_id_list(foam_grade_id)
    q = session.query(ProductionRun).options(
        joinedload(ProductionRun.recipe_version),
        joinedload(ProductionRun.machine),
        joinedload(ProductionRun.foam_grade),
    )
    if grade_ids:
        q = q.filter(ProductionRun.foam_grade_id.in_(grade_ids))
    if production_method_id:
        q = q.filter(ProductionRun.production_method_id == production_method_id)
    runs = q.order_by(ProductionRun.run_date).all()
    if not runs:
        return pd.DataFrame()

    run_ids = [run.id for run in runs]
    runs_by_id = {run.id: run for run in runs}
    field_key = dynamic_process_setting_field_key(setting_definition_id)

    values_by_run, definitions_by_field = production_run_parameter_dataframe(session, run_ids)
    definition_meta = definitions_by_field.get(field_key)
    if definition_meta is None or definition_meta["data_type"] not in ("Float", "Integer"):
        return pd.DataFrame()

    planned_by_run = {
        row.production_run_id: row.numeric_value
        for row in session.query(ProcessParameterValue).filter(
            ProcessParameterValue.production_run_id.in_(run_ids),
            ProcessParameterValue.setting_definition_id == setting_definition_id,
            ProcessParameterValue.snapshot_type == "Planned",
        ).all()
    }

    rows = []
    for run_id in run_ids:
        actual = values_by_run.get(run_id, {}).get(field_key)
        if actual is None:
            continue
        run = runs_by_id[run_id]
        planned = planned_by_run.get(run_id)
        rows.append({
            "run_id": run_id,
            "tested_at": run.run_date,
            "actual_value": float(actual),
            "target_value": float(planned) if planned is not None else None,
            "recipe_version": run.recipe_version.version_label if run.recipe_version else None,
            "machine": run.machine.name if run.machine else None,
            "foam_grade": run.foam_grade.grade_name if run.foam_grade else None,
            "source": "Production Run",
            "n_replicates": 1,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.dropna(subset=["tested_at", "actual_value"]).sort_values("tested_at").reset_index(drop=True)


def production_run_output_summary(session, production_run):
    """WP7 Phase 4 shared reader (2026-08-14), output domain. THE canonical
    single-run output fact, per Charlie's Downstream Reader Cutover
    Execution Instruction section 6: "ProductionOutputSummary becomes the
    active output fact. Overview, reports and PI3 read its Actual quantity
    and controlled UOM. Planned quantity supports plan-versus-actual
    comparison. Disposition remains a controlled run-level output
    decision." compute_runtime_output() (the conveyor-speed x tunnel-width
    x foam-height geometry formula above) loses universal KPI/report
    authority as of this function's introduction - it remains in place
    only as the legacy, additive "Calculated output" display inside the
    Production Run page's own Runtime Data tab (never removed by Phase 4,
    since that page-level display isn't in the Phase 4 consumer matrix),
    never as a value this function or its callers fall back to.

    `production_run` accepts either a ProductionRun instance or its id.
    Returns None if the run doesn't exist, or if no ProductionOutputSummary
    row has ever been recorded for it - a genuinely unrecorded output stays
    unrecorded here; it is never inferred from geometry. Otherwise returns
    a dict: production_run_id, planned_quantity, actual_quantity (the
    production fact - Planned is separate plan/target context and never
    substitutes for a missing Actual, same rule as the process-parameter
    reader above), unit_id, unit_symbol (the row's own single controlled
    UOM - both Planned and Actual already share it, per Charlie's decision
    doc section 3.3), disposition, disposition_notes."""
    if isinstance(production_run, int):
        run = session.get(ProductionRun, production_run)
    else:
        run = production_run
    if run is None:
        return None

    row = (
        session.query(ProductionOutputSummary)
        .filter(ProductionOutputSummary.production_run_id == run.id)
        .first()
    )
    if row is None:
        return None

    return {
        "production_run_id": run.id,
        "planned_quantity": row.planned_quantity,
        "actual_quantity": row.actual_quantity,
        "unit_id": row.unit_id,
        "unit_symbol": row.unit.symbol if row.unit else None,
        "disposition": row.disposition,
        "disposition_notes": row.disposition_notes,
    }


def production_output_totals(session, run_ids):
    """WP7 Phase 4 shared reader (2026-08-14), output domain - multi-run
    aggregation for KPI cards (first consumer: the Overview page's "Output
    Quantity and Unit" card). Sums ProductionOutputSummary.actual_quantity
    across `run_ids`, grouped by unit_id - deliberately never summed
    across different units, mirroring the Overview page's own pre-existing
    "never a meaningless mixed-unit total" rule (CR-02 section 8), which
    Charlie's Phase 4 instruction reaffirms applies to ProductionOutputSummary
    too. A run with no recorded ProductionOutputSummary row, or one whose
    Actual quantity was never captured, contributes nothing to any total -
    the honest missing-data state, never a compute_runtime_output fallback.

    Returns a dict:
      totals_by_unit: a list of dicts, one per distinct unit_id actually
        present among `run_ids`' Actual quantities - {"unit_id",
        "unit_symbol", "actual_total", "planned_total", "run_count"} -
        sorted by run_count descending, so a caller showing a single
        headline figure can prefer the unit most of the scoped runs used.
        planned_total only sums the rows that also have a non-None
        planned_quantity - it is not forced to the same row count as
        actual_total.
      runs_without_summary: count of `run_ids` with no ProductionOutputSummary
        row at all (not even a Planned-only one) - distinguishable from a
        run whose summary row exists but has no Actual quantity yet, which
        instead simply doesn't add to any unit's actual_total/run_count."""
    if not run_ids:
        return {"totals_by_unit": [], "runs_without_summary": 0}

    rows = (
        session.query(ProductionOutputSummary)
        .filter(ProductionOutputSummary.production_run_id.in_(run_ids))
        .all()
    )
    covered_run_ids = {row.production_run_id for row in rows}

    by_unit = {}
    for row in rows:
        if row.actual_quantity is None:
            continue
        slot = by_unit.setdefault(row.unit_id, {
            "unit_id": row.unit_id,
            "unit_symbol": row.unit.symbol if row.unit else None,
            "actual_total": 0.0,
            "planned_total": 0.0,
            "run_count": 0,
        })
        slot["actual_total"] += row.actual_quantity
        if row.planned_quantity is not None:
            slot["planned_total"] += row.planned_quantity
        slot["run_count"] += 1

    totals_by_unit = sorted(by_unit.values(), key=lambda d: -d["run_count"])
    runs_without_summary = len(set(run_ids) - covered_run_ids)
    return {"totals_by_unit": totals_by_unit, "runs_without_summary": runs_without_summary}


def format_setting_range(is_boolean, series):
    """Human-readable label for one qcut bucket's range of a given setting
    field - "Yes"/"No" when is_boolean is True, "{min}-{max}" otherwise.
    Shared by rank_setting_optimization below and the Process Parameter
    Optimization page's own drill-down bucketing, so the two never disagree
    on how a bucket is labeled.

    WP7 Phase 4 cutover (2026-08-14): takes an explicit is_boolean flag
    rather than a field name checked against the static BOOLEAN_SETTING_
    FIELDS set - callers now source data_type from the live, dynamic
    ProcessSettingDefinition catalogue (see merged_run_property_dataframe
    below), which can't be looked up by static field-name membership."""
    if is_boolean:
        return "Yes" if series.max() >= 0.5 else "No"
    return f"{series.min():g}–{series.max():g}"


@st.cache_data(ttl=_DATA_CACHE_TTL, show_spinner=False)
def run_settings_dataframe(_session, foam_grade_id=None, production_method_id=None):
    """One row per production run: identifying info only (grade, recipe
    version, machine, production method). `foam_grade_id` accepts a single
    id or a list of ids (a foam family's grades pooled together) - see
    _grade_id_list above.

    `production_method_id` (added 2026-08-10, per Charlie's flat-PM
    technical completion instruction) narrows to runs whose own immutable
    production_method_id snapshot (see ProductionRun in db.py) matches -
    the isolation dimension the Industrial Intelligence pages (15-19) use
    so a Trend/Correlation/Optimization view for one Production Method
    never silently pools in another method's runs. None (default) means
    no method filter, matching every caller's behavior before this
    parameter existed.

    Simplified under WP7 Phase 5 (Legacy Retirement, per the JC Pre-Coding
    Engineering Challenge Response) - previously eager-loaded every run's
    ProductionPhase rows and populated a PHASE_SETTING_FIELDS column on
    every row, but both live callers (this module's own
    merged_run_property_dataframe, and pages/18 Root Cause Assistant) only
    ever consumed the identity columns below; the actual method-aware
    process-setting values come from the ProcessSettingDefinition/
    ProcessParameterValue EAV schema via production_run_process_parameters()
    / production_run_parameter_dataframe() instead - never re-derived from
    ProductionPhase, which is now ARCHIVE READ-ONLY (no active reader).

    Cached (see _DATA_CACHE_TTL) and eager-loads foam_grade/recipe_version/
    machine in one query. The `_session` parameter name (leading
    underscore) tells Streamlit's cache not to try to hash the SQLAlchemy
    Session object - the cache key is just foam_grade_id. Logs its own
    duration to PerformanceLog on every call (see _log_performance) - this
    function only runs at all on a cache miss, so every logged row here is
    real database work, not a cache hit.
    """
    _t0 = time.perf_counter()
    q = _session.query(ProductionRun).options(
        joinedload(ProductionRun.foam_grade),
        joinedload(ProductionRun.recipe_version),
        joinedload(ProductionRun.machine),
        joinedload(ProductionRun.production_method),
    )
    grade_ids = _grade_id_list(foam_grade_id)
    if grade_ids:
        q = q.filter(ProductionRun.foam_grade_id.in_(grade_ids))
    if production_method_id:
        q = q.filter(ProductionRun.production_method_id == production_method_id)
    runs = q.order_by(ProductionRun.run_date).all()

    rows = []
    for run in runs:
        row = {
            "run_id": run.id,
            "run_date": run.run_date,
            "foam_grade_id": run.foam_grade_id,
            "foam_grade": run.foam_grade.grade_name if run.foam_grade else None,
            "recipe_version_id": run.recipe_version_id,
            "recipe_version": run.recipe_version.version_label if run.recipe_version else None,
            "machine_id": run.machine_id,
            "machine": run.machine.name if run.machine else None,
            "production_method_id": run.production_method_id,
            "production_method": run.production_method.name if run.production_method else None,
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    _log_performance(_session, "run_settings_dataframe", foam_grade_id, None, (time.perf_counter() - _t0) * 1000, len(df))
    return df


@st.cache_data(ttl=_DATA_CACHE_TTL, show_spinner=False)
def property_results_dataframe(
    _session, foam_grade_id=None, property_name=None, include_trials=False, production_method_id=None
):
    """One row per physical property result, joined with the run's grade,
    recipe version, and machine - the base table for trend/correlation
    work. `foam_grade_id` accepts a single id or a list of ids (a foam
    family's grades pooled together).

    pass_fail is recomputed live via quality_standards.compute_pass_fail()
    rather than read from the result's stored pass_fail column - a stored
    verdict only reflects whatever tolerance rule was in effect at the
    moment it was written, so every consumer of this dataframe (Recipe
    Optimization, Trend Analysis, Process-Property Correlation, Root-Cause
    Assistant, Machine Settings Optimization) needs the current rule, not
    a historical snapshot of it.

    `include_trials` (default False - production-run-only, matching every
    caller's behavior before 2026-08-03) additionally unions in results
    sourced from CustomerTrial/OptimizationTrial (see
    db.SAMPLE_SOURCE_TYPES) - the two independent lab-trial flows that have
    no ProductionPhase/machine behind them. Only Trend Analysis and Recipe
    Optimization ever pass True for this - Process-Property Correlation,
    Root-Cause Assistant, and Machine Settings Optimization are keyed on
    PHASE_SETTING_FIELDS (machine/process settings) that simply don't
    exist for a lab trial, so they stay production-run-only unconditionally
    rather than accepting this parameter. Trial-sourced rows carry
    run_id=None, run_date=None, machine=None, and a "source" column
    ("Production Run" / "Customer Trial" / "Optimization Trial") so callers
    can tell the two apart when it matters (e.g. excluding trial rows from
    anything that assumes a real run_date for time-ordering).

    `production_method_id` (added 2026-08-10, see run_settings_dataframe's
    docstring) narrows Production-Run-sourced rows to that method's
    immutable run snapshot. Customer/Optimization Trial rows have no
    Production Method of their own (lab-only workflows, out of scope for
    this rollout) and are simply not included when this filter is set -
    the isolation this parameter provides means a method-scoped view never
    silently pools in another method's runs OR an unrelated lab trial.

    Cached (see _DATA_CACHE_TTL) and eager-loads each result's production
    run plus that run's foam_grade/recipe_version/machine in the same
    query - fixed 2026-08-02, previously touched each of those 3
    relationships as a separate lazy-loaded query PER RESULT ROW (roughly
    1 + 4x the number of results), which is the main reason this got
    slower as more quality data was recorded. The `_session` parameter
    name (leading underscore) tells Streamlit's cache not to try to hash
    the SQLAlchemy Session object - the cache key is just foam_grade_id/
    property_name/include_trials. Logs its own duration to PerformanceLog
    on every call (see _log_performance) - only runs at all on a cache
    miss."""
    _t0 = time.perf_counter()
    run_load = joinedload(PhysicalPropertyResult.production_run)
    q = (
        _session.query(PhysicalPropertyResult)
        .join(ProductionRun)
        .options(
            run_load.joinedload(ProductionRun.foam_grade),
            run_load.joinedload(ProductionRun.recipe_version),
            run_load.joinedload(ProductionRun.machine),
            run_load.joinedload(ProductionRun.production_method),
        )
    )
    grade_ids = _grade_id_list(foam_grade_id)
    if grade_ids:
        q = q.filter(ProductionRun.foam_grade_id.in_(grade_ids))
    if property_name:
        q = q.filter(PhysicalPropertyResult.property_name == property_name)
    if production_method_id:
        q = q.filter(ProductionRun.production_method_id == production_method_id)
    results = q.all()

    rows = []
    for r in results:
        run = r.production_run
        if run is None:
            continue
        rows.append(
            {
                "result_id": r.id,
                "source": "Production Run",
                "run_id": run.id,
                "trial_id": None,
                "run_date": run.run_date,
                "foam_grade_id": run.foam_grade_id,
                "foam_grade": run.foam_grade.grade_name if run.foam_grade else None,
                "recipe_version_id": run.recipe_version_id,
                "recipe_version": run.recipe_version.version_label if run.recipe_version else None,
                "machine_id": run.machine_id,
                "machine": run.machine.name if run.machine else None,
                "production_method_id": run.production_method_id,
                "production_method": run.production_method.name if run.production_method else None,
                "property_name": r.property_name,
                "target_value": r.target_value,
                "actual_value": r.actual_value,
                "unit": r.unit,
                "pass_fail": compute_pass_fail(r.property_name, r.target_value, r.actual_value),
                "tested_at": r.tested_at,
            }
        )

    # Lab trials (Customer/Optimization) have no Production Method of
    # their own - excluded outright when a method filter is set, rather
    # than included with a null method, so the isolation this parameter
    # provides is real: a method-scoped view never silently pools in an
    # unrelated lab trial.
    if include_trials and not production_method_id:
        for source_label, trial_model, fk_col in (
            ("Customer Trial", CustomerTrial, PhysicalPropertyResult.customer_trial_id),
            ("Optimization Trial", OptimizationTrial, PhysicalPropertyResult.optimization_trial_id),
        ):
            trial_load = joinedload(getattr(PhysicalPropertyResult, "customer_trial" if trial_model is CustomerTrial else "optimization_trial"))
            tq = (
                _session.query(PhysicalPropertyResult)
                .join(trial_model, fk_col == trial_model.id)
                .options(
                    trial_load.joinedload(trial_model.foam_grade),
                    trial_load.joinedload(trial_model.recipe_version),
                )
            )
            if grade_ids:
                tq = tq.filter(trial_model.foam_grade_id.in_(grade_ids))
            if property_name:
                tq = tq.filter(PhysicalPropertyResult.property_name == property_name)
            for r in tq.all():
                trial = r.customer_trial if trial_model is CustomerTrial else r.optimization_trial
                if trial is None:
                    continue
                rows.append(
                    {
                        "result_id": r.id,
                        "source": source_label,
                        "run_id": None,
                        "trial_id": trial.id,
                        "run_date": trial.trial_date,
                        "foam_grade_id": trial.foam_grade_id,
                        "foam_grade": trial.foam_grade.grade_name if trial.foam_grade else None,
                        "recipe_version_id": trial.recipe_version_id,
                        "recipe_version": trial.recipe_version.version_label if trial.recipe_version else None,
                        "machine_id": None,
                        "machine": None,
                        "production_method_id": None,
                        "production_method": "N/A (lab trial)",
                        "property_name": r.property_name,
                        "target_value": r.target_value,
                        "actual_value": r.actual_value,
                        "unit": r.unit,
                        "pass_fail": compute_pass_fail(r.property_name, r.target_value, r.actual_value),
                        "tested_at": r.tested_at,
                    }
                )

    df = pd.DataFrame(rows)
    _log_performance(
        _session, "property_results_dataframe", foam_grade_id, property_name,
        (time.perf_counter() - _t0) * 1000, len(df),
    )
    return df


def pass_rate(series) -> float | None:
    """Share of non-null Pass/Fail values that are 'Pass', or None if there
    is nothing to compute from."""
    known = series.dropna()
    if known.empty:
        return None
    return round((known == "Pass").sum() / len(known), 3)


def _safe_int(value):
    """int(value), or None if value is missing/NaN - a lab-trial-sourced row
    in an SPC series (see property_run_series's include_trials) has no
    run_id, and int(nan) raises rather than producing something usable, so
    every SPC function below that surfaces a flagged point's run id goes
    through this instead of a bare int() cast."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return int(value)


def normalize_to_pct_of_target(df):
    """Re-expresses a dataframe's actual_value/target_value columns on a
    "percent of target" basis - target becomes 100 for every row,
    actual_value becomes (actual/target)*100 - instead of the property's
    own raw unit. This is what makes pooling multiple product grades into one
    analysis (see helpers.analysis_unit_picker's "foam family" mode)
    statistically sound rather than misleading: two grades of the same
    property (e.g. two different density grades) can have very different
    target values, so a control chart, capability index, or raw
    setting-vs-actual_value correlation built from RAW values would read a
    plain grade-to-grade target difference as a false shift/drift/
    correlation. Building on % of target instead makes every run's target
    identical, so pooling grades together no longer confounds "which grade
    is this run" with the thing actually being measured.

    Only ever applied in foam-family mode - single-grade analyses keep
    using each property's own raw unit/scale exactly as before (this
    function is never called for foam_grade_id being a single id), so
    existing single-grade numbers are completely unaffected by this.

    Rows with a missing or zero target_value are dropped (nothing to
    normalize against). The original raw values are kept under
    _raw_actual_value/_raw_target_value in case a caller wants to still
    display/export the real unit alongside the normalized one. Returns a
    copy; safe to call on an empty dataframe (returns it unchanged)."""
    if df.empty:
        return df
    out = df.dropna(subset=["target_value"])
    out = out[out["target_value"] != 0].copy()
    if out.empty:
        return out
    out["_raw_actual_value"] = out["actual_value"]
    out["_raw_target_value"] = out["target_value"]
    out["actual_value"] = (out["actual_value"] / out["target_value"]) * 100
    out["target_value"] = 100.0
    return out.reset_index(drop=True)


def merged_run_property_dataframe(
    session, foam_grade_id, property_name, normalize_pct_of_target=False, production_method_id=None
):
    """One row per production run for a given grade/property: process
    settings joined to that run's mean result for the chosen property.
    Used by Process Parameters vs Product Properties Correlation and
    Process Parameter Optimization, which both need "one settings snapshot"
    per "one quality outcome". `normalize_pct_of_target=True` re-expresses
    actual_value/target_value as percent-of-target before returning (see
    normalize_to_pct_of_target) - pass this when foam_grade_id is a foam
    family's list of grade ids, since those grades can have different
    target values for the same property.

    WP7 Phase 4 cutover (2026-08-14, per Charlie's Downstream Reader
    Cutover Execution Instruction): the settings side is now sourced from
    analytics.production_run_parameter_dataframe() - the shared reader -
    instead of run_settings_dataframe()'s PHASE_SETTING_FIELDS columns
    (backed by ProductionPhase), which retain zero active-reader authority
    under Phase 4. run_settings_dataframe() is still used here, unchanged,
    for identity columns only (run_id, run_date, foam_grade, recipe_
    version, machine, production_method) - never a legacy-reader concern,
    since those come from ProductionRun itself. Scoped to parameter_
    category == "Process Setting", data_type in (Float, Integer, Boolean),
    controllable == True, and analytics_eligible == True - a String
    setting has no numeric meaning for a correlation or a Low/Medium/High
    quantile split, Environment/Outcome definitions are excluded the same
    way pages/4's own Method-Aware Process Settings tab excludes them
    (WP7 Phase 3 correction), and the controllable/analytics_eligible
    filter is section 3 of the execution instruction's explicit
    requirement for both Process-Property Correlation ("Actual
    ProcessParameterValue rows whose winning applicability is
    controllable=True and analytics_eligible=True") and Process Parameter
    Optimization ("Actual values for controllable=True and analytics_
    eligible=True definitions") - a definition with either flag False on
    its winning applicability must never enter either ranking, even when
    values are recorded for it (Required Tests section 11, "Optimization
    eligibility" gate).

    Returns a tuple (merged, definitions_by_field): merged is the joined
    DataFrame (columns: identity columns, one dynamic_process_setting_
    field_key() column per eligible definition, actual_value, target_value);
    definitions_by_field is the {field_key: {"label", "data_type", ...}}
    dict production_run_parameter_dataframe() returns, already filtered to
    the eligible subset above - callers building a field-key -> label/
    data_type lookup (e.g. a selectbox's format_func, or a Boolean-branch
    check) should read it from here rather than the retired PHASE_SETTING_
    LABELS/BOOLEAN_SETTING_FIELDS statics, which have no entry for a
    dynamic "ps_<definition_id>" key."""
    identity_df = run_settings_dataframe(session, foam_grade_id=foam_grade_id, production_method_id=production_method_id)
    results_df = property_results_dataframe(
        session, foam_grade_id=foam_grade_id, property_name=property_name, production_method_id=production_method_id
    )
    if identity_df.empty or results_df.empty:
        return pd.DataFrame(), {}

    run_ids = identity_df["run_id"].tolist()
    values_by_run, all_definitions_by_field = production_run_parameter_dataframe(session, run_ids)
    definitions_by_field = {
        field_key: meta for field_key, meta in all_definitions_by_field.items()
        if meta["parameter_category"] == "Process Setting" and meta["data_type"] in ("Float", "Integer", "Boolean")
        and meta["controllable"] and meta["analytics_eligible"]
    }

    settings_rows = []
    for _, id_row in identity_df.iterrows():
        row = id_row.to_dict()
        run_values = values_by_run.get(row["run_id"], {})
        for field_key, meta in definitions_by_field.items():
            raw = run_values.get(field_key)
            if meta["data_type"] == "Boolean":
                # Coerced to 0.0/1.0/NaN, matching every downstream
                # consumer's expectation (.corr(), pd.qcut's numeric
                # fields, the deviation_pct math) - the exact same
                # None-safe coercion run_settings_dataframe used to apply
                # to its own BOOLEAN_SETTING_FIELDS columns.
                row[field_key] = (1.0 if raw else 0.0) if raw is not None else None
            else:
                row[field_key] = raw
        settings_rows.append(row)
    settings_df = pd.DataFrame(settings_rows)

    per_run_result = (
        results_df.groupby("run_id")
        .agg(actual_value=("actual_value", "mean"), target_value=("target_value", "mean"))
        .reset_index()
    )
    merged = settings_df.merge(per_run_result, on="run_id", how="inner")
    if normalize_pct_of_target:
        merged = normalize_to_pct_of_target(merged)
    return merged, definitions_by_field


def rank_setting_correlations(
    session, foam_grade_id, property_name, normalize_pct_of_target=False, production_method_id=None
):
    """For EVERY process setting at once, compute its correlation with the
    chosen property's actual value across this grade's runs, ranked by
    |correlation| descending. This is the difference between "intelligence"
    and "a graph you have to already know where to point": instead of
    picking one setting and hoping it's the relevant one, the reviewer sees
    immediately which of the live catalogue's settings actually moves this
    property, and by how much, before drilling into any single scatter
    plot.

    `normalize_pct_of_target` - see merged_run_property_dataframe - pass
    True when pooling a foam family's grades together.

    WP7 Phase 4 cutover (2026-08-14): iterates merged_run_property_
    dataframe()'s definitions_by_field (the live, method-aware catalogue)
    instead of the retired eligible_phase_setting_fields()/PHASE_SETTING_
    LABELS statics. A definition with zero recorded values across every
    requested run still gets a "no data yet" row (correlation=None) here,
    matching the old static list's behavior of always showing every
    tracked setting - the difference is this list is now the live
    catalogue's own eligible settings, not a fixed 5-field list. Returns
    the same columns as before (field/label/n/correlation) plus a new
    data_type column, so callers needing a Boolean-vs-numeric branch (e.g.
    format_setting_range) don't have to re-derive it from a separate
    lookup."""
    merged, definitions_by_field = merged_run_property_dataframe(
        session, foam_grade_id, property_name,
        normalize_pct_of_target=normalize_pct_of_target, production_method_id=production_method_id,
    )
    rows = []
    for field, meta in definitions_by_field.items():
        if merged.empty:
            sub = merged
        else:
            sub = merged.dropna(subset=[field, "actual_value"])
        n = len(sub)
        corr = round(sub[field].corr(sub["actual_value"]), 3) if n >= 3 else None
        rows.append({
            "field": field, "label": meta["label"], "data_type": meta["data_type"],
            "n": n, "correlation": corr,
        })
    ranked = pd.DataFrame(rows)
    # Every field is appended above regardless of whether a correlation could
    # be computed (unlike rank_component_actual_correlations etc., which
    # skip uncomputable rows entirely) - so if every setting has too few points,
    # "correlation" ends up an all-None object-dtype column, and pandas'
    # .abs() raises TypeError on that (bad operand type for abs(): 'NoneType')
    # rather than treating it as NaN. pd.to_numeric coerces None/object-None
    # to a proper float NaN first, which .abs() (and na_position="last"
    # below) handle correctly regardless of how many rows have no value yet.
    if ranked.empty:
        ranked = pd.DataFrame(columns=["field", "label", "data_type", "n", "correlation"])
        return ranked
    ranked["_abs"] = pd.to_numeric(ranked["correlation"], errors="coerce").abs()
    ranked = ranked.sort_values("_abs", ascending=False, na_position="last").drop(columns=["_abs"]).reset_index(drop=True)
    return ranked


def rank_setting_optimization(
    session, foam_grade_id, property_name, normalize_pct_of_target=False, production_method_id=None
):
    """For EVERY process setting, bucket its values into Low/Medium/High (or
    Low/High) ranges and measure the gap between the best- and
    worst-performing range's average absolute deviation from target. A
    bigger gap means that setting more clearly separates good outcomes from
    bad ones for this grade/property - ranked so the most actionable
    setting surfaces first, instead of the reviewer checking each of the
    live catalogue's settings one at a time to find out which one matters.

    `normalize_pct_of_target` - see merged_run_property_dataframe. Note this
    function's own deviation_pct math below is already scale-invariant
    under that normalization ((actual-target)/target is unchanged whether
    actual/target are raw or already expressed as percent-of-target), so
    passing True here only matters for keeping this function's INPUT
    consistent with rank_setting_correlations' when both are shown
    side-by-side for the same foam-family selection - it does not change
    this function's own ranking numbers.

    WP7 Phase 4 cutover (2026-08-14): iterates merged_run_property_
    dataframe()'s definitions_by_field instead of the retired eligible_
    phase_setting_fields()/PHASE_SETTING_LABELS statics, and branches on
    meta["data_type"] == "Boolean" instead of a field in BOOLEAN_SETTING_
    FIELDS membership check - BOOLEAN_SETTING_FIELDS is a static field-name
    set that has no entry for a dynamic "ps_<definition_id>" key. Returns
    the same columns as before plus a new data_type column (see
    rank_setting_correlations)."""
    merged, definitions_by_field = merged_run_property_dataframe(
        session, foam_grade_id, property_name,
        normalize_pct_of_target=normalize_pct_of_target, production_method_id=production_method_id,
    )
    rows = []
    for field, meta in definitions_by_field.items():
        label = meta["label"]
        is_boolean = meta["data_type"] == "Boolean"
        empty_row = {
            "field": field, "label": label, "data_type": meta["data_type"], "n": 0,
            "best_range": None, "best_range_setting": None,
            "best_range_avg_dev_pct": None, "spread_pct": None,
        }
        if merged.empty:
            rows.append(empty_row)
            continue
        sub = merged.dropna(subset=[field, "actual_value"]).copy()
        if len(sub) < 3:
            empty_row["n"] = len(sub)
            rows.append(empty_row)
            continue

        sub["deviation_pct"] = ((sub["actual_value"] - sub["target_value"]) / sub["target_value"]).abs()
        sub.loc[sub["target_value"].isna() | (sub["target_value"] == 0), "deviation_pct"] = float("nan")

        range_col = None
        if is_boolean:
            # A strictly 0/1 field is a group comparison, not a quantile
            # split - pd.qcut is the wrong tool here regardless, and
            # actively fails (raises ValueError under duplicates="drop")
            # for the skewed splits a Yes/No setting produces in practice
            # (e.g. 5 Yes vs 2 No), which would otherwise fall through to
            # the "not enough variation" empty row even though a clean
            # two-group comparison exists. Map directly to Yes/No instead.
            range_col = sub[field].map({1.0: "Yes", 0.0: "No"})
        else:
            for q, labels in ((3, ["Low", "Medium", "High"]), (2, ["Low", "High"])):
                try:
                    range_col = pd.qcut(sub[field], q=q, labels=labels, duplicates="drop")
                    break
                except ValueError:
                    continue
        if range_col is None or range_col.nunique(dropna=True) < 2:
            empty_row["n"] = len(sub)
            rows.append(empty_row)
            continue

        sub["range"] = range_col
        summary = (
            sub.groupby("range", observed=True)
            .agg(avg_dev=("deviation_pct", "mean"), setting_range=(field, lambda s: format_setting_range(is_boolean, s)))
            .dropna(subset=["avg_dev"])
        )
        if summary.empty:
            empty_row["n"] = len(sub)
            rows.append(empty_row)
            continue

        summary = summary.sort_values("avg_dev")
        best, worst = summary.iloc[0], summary.iloc[-1]
        rows.append(
            {
                "field": field,
                "label": label,
                "data_type": meta["data_type"],
                "n": len(sub),
                "best_range": summary.index[0],
                "best_range_setting": best["setting_range"],
                "best_range_avg_dev_pct": round(best["avg_dev"] * 100, 1),
                "spread_pct": round((worst["avg_dev"] - best["avg_dev"]) * 100, 1),
            }
        )
    ranked = pd.DataFrame(rows)
    if ranked.empty:
        return pd.DataFrame(columns=[
            "field", "label", "data_type", "n",
            "best_range", "best_range_setting", "best_range_avg_dev_pct", "spread_pct",
        ])
    ranked = ranked.sort_values("spread_pct", ascending=False, na_position="last").reset_index(drop=True)
    return ranked


# ---------------------------------------------------------------------------
# Recipe Optimization: cost, version diff, component-level correlation
# ---------------------------------------------------------------------------
# These three functions are what turn "a table of ingredients" and "a table
# of quality outcomes" into an actual optimization view: what does this
# formulation cost, what specifically changed between two versions, and
# which raw material's dosage is actually associated with which property -
# instead of leaving the reviewer to eyeball two ingredient lists and a
# results table side by side.


def _resolve_component_cost_per_kg(session, component, raw_material_cache):
    """Cost/kg for a recipe component: prefer the linked RawMaterial (by
    raw_material_id), fall back to a case-insensitive name match against
    the Raw Materials master list (covers components entered as free text
    before a matching master record existed). Returns None if no cost is
    recorded anywhere for this material - callers must treat that as
    "unknown", never as zero."""
    if component.raw_material_id and component.raw_material_id in raw_material_cache:
        rm = raw_material_cache[component.raw_material_id]
        if rm and rm.cost_per_kg is not None:
            return rm.cost_per_kg
    name_key = (component.raw_material_name or "").strip().lower()
    for rm in raw_material_cache.values():
        if rm and rm.name.strip().lower() == name_key and rm.cost_per_kg is not None:
            return rm.cost_per_kg
    return None


def recipe_version_cost(session, recipe_version):
    """Formulation cost for one recipe version, in cost per 100 parts (the
    standard php-based costing convention: sum of each component's php x
    its cost/kg, since php already expresses each material as parts per
    hundred of the base polyol). Returns a dict:
    - total_cost: float, or None if NO component has cost data at all
    - priced_php / total_php: how much of the formulation (by php) is
      actually covered by known costs, so a partial total can be flagged
    - missing: list of raw material names with no cost recorded
    Never fabricates a cost for an unpriced material - a formulation with
    missing prices gets an honest partial total, not a silently wrong one.
    """
    raw_material_cache = {rm.id: rm for rm in session.query(RawMaterial).all()}
    total_cost = 0.0
    priced_php = 0.0
    total_php = 0.0
    missing = []
    any_priced = False

    for c in recipe_version.components:
        php = c.php or 0.0
        total_php += php
        cost_per_kg = _resolve_component_cost_per_kg(session, c, raw_material_cache)
        if cost_per_kg is None:
            missing.append(c.raw_material_name)
            continue
        any_priced = True
        total_cost += php * cost_per_kg
        priced_php += php

    return {
        "total_cost": round(total_cost, 4) if any_priced else None,
        "priced_php": round(priced_php, 2),
        "total_php": round(total_php, 2),
        "missing": missing,
        "complete": not missing,
    }


# ---------------------------------------------------------------------------
# Formulation chemistry: A:B mass ratio, theoretical CO2, equivalent
# weights, isocyanate index (WP6-S06 DEF-006, 2026-08-08)
#
# Charlie's calculation_definitions library documents these formulas
# (CALC-001, CALC-010, CALC-011, CALC-015, CALC-026) and three of the four
# are flagged phase_status = "Phase 1" in his own controlled data, but
# nothing in this app computed them live before now. Same "never fabricate
# missing data" discipline as recipe_version_cost above: every function
# here returns an honest None/partial result plus an explicit reason the
# moment a required input isn't recorded, rather than guessing or
# defaulting to zero.
# ---------------------------------------------------------------------------


def _component_side(component):
    """A-side vs B-side for one recipe component, for the A:B MASS RATIO
    only - this is a formulation-reporting label, not a chemistry
    classification (different recipes in this app use it inconsistently:
    the WP3 seed recipe calls the isocyanate 'A-side', the WP5-era
    reference recipes call the isocyanate 'B-side' - see recipe_versions
    2-5 vs 1). Prefers the structured stream_assignment field (RCF-004)
    where populated, falling back to the free-text 'A-side (...)' /
    'B-side (...)' prefix on role_in_formulation for older recipes that
    predate stream_assignment. Returns "A", "B", or None if neither field
    resolves a side - callers must not guess."""
    sa = (component.stream_assignment or "").strip().lower()
    if sa.startswith("a-side") or sa == "a":
        return "A"
    if sa.startswith("b-side") or sa == "b":
        return "B"
    role = (component.role_in_formulation or "").strip().lower()
    if role.startswith("a-side"):
        return "A"
    if role.startswith("b-side"):
        return "B"
    return None


def recipe_version_ab_mass_ratio(session, recipe_version):
    """CALC-001 'A:B mass ratio' = A_mass / B_mass. Uses each component's
    php as its mass - php already puts every component on the same
    100-part formulation basis, so summing php within a side gives a real
    mass ratio, not just an ingredient count. Components with no resolvable
    side (see _component_side) are listed under unassigned_components
    rather than silently dropped or guessed onto a side, and 'complete'
    is False whenever any exist. Also returns the recipe's own recorded
    target_ab_mass_ratio (RHF-010) for comparison, when set."""
    a_php = 0.0
    b_php = 0.0
    unassigned = []
    for c in recipe_version.components:
        side = _component_side(c)
        php = c.php or 0.0
        if side == "A":
            a_php += php
        elif side == "B":
            b_php += php
        else:
            unassigned.append(c.raw_material_name)

    ratio = round(a_php / b_php, 4) if b_php else None
    return {
        "a_side_php": round(a_php, 2),
        "b_side_php": round(b_php, 2),
        "computed_ratio": ratio,
        "target_ratio": recipe_version.target_ab_mass_ratio,
        "unassigned_components": unassigned,
        "complete": not unassigned and b_php > 0,
    }


def recipe_version_theoretical_co2(session, recipe_version):
    """CALC-026 'Theoretical CO2 from water' = Water_mass x 44.01 / 18.02
    (stoichiometric water-isocyanate reaction only; excludes any physical
    blowing agent's own contribution, per CALC-026's validation_rule).
    Water_mass is the recipe's Water component php, on the same 100-part
    formulation basis as recipe_version_cost/recipe_version_ab_mass_ratio -
    so the result is theoretical CO2 per 100 parts of formulation, not an
    absolute batch mass. Returns co2_per_100_parts=None with an explicit
    reason if the recipe has no component named 'Water', rather than
    assuming zero water."""
    water_components = [
        c for c in recipe_version.components
        if (c.raw_material_name or "").strip().lower() == "water"
    ]
    if not water_components:
        return {
            "water_php": None,
            "co2_per_100_parts": None,
            "reason": "No component named 'Water' found in this recipe's components.",
        }
    water_php = sum(c.php or 0.0 for c in water_components)
    return {
        "water_php": round(water_php, 3),
        "co2_per_100_parts": round(water_php * 44.01 / 18.02, 3),
        "reason": None,
    }


def recipe_version_equivalent_weights(session, recipe_version):
    """CALC-010 (isocyanate equivalent weight, 4200 / NCO%) and CALC-011
    (reactive-hydrogen/polyol equivalent weight, 56100 / OH number) for
    every component of one recipe version. NCO%/OH# are looked up from
    RawMaterialAttributeValue (RMA-004 / RMA-001), keyed off the
    component's linked raw_material_id - the WP5 Wave 1 EAV table built
    for exactly this purpose, but not yet populated for any raw material
    in this app (0 rows, see the DEF-006 data-gap note to Charlie). A
    component is treated as the isocyanate side if its role_in_formulation
    mentions "isocyanate" or its nco_equivalent_flag is set; everything
    else is treated as the reactive-hydrogen side. Never guesses a value:
    a component with no linked raw_material_id, or no recorded attribute
    value, gets an explicit missing_reason instead of being skipped or
    defaulted to zero."""
    attr_defs = {
        d.controlled_id: d
        for d in session.query(RawMaterialAttributeDefinition)
        .filter(RawMaterialAttributeDefinition.controlled_id.in_(["RMA-001", "RMA-004"]))
        .all()
    }
    oh_def = attr_defs.get("RMA-001")
    nco_def = attr_defs.get("RMA-004")

    raw_material_ids = [c.raw_material_id for c in recipe_version.components if c.raw_material_id]
    values_by_material = {}
    def_ids = [d.id for d in (oh_def, nco_def) if d]
    if raw_material_ids and def_ids:
        for v in (
            session.query(RawMaterialAttributeValue)
            .filter(
                RawMaterialAttributeValue.raw_material_id.in_(raw_material_ids),
                RawMaterialAttributeValue.attribute_definition_id.in_(def_ids),
            )
            .all()
        ):
            values_by_material.setdefault(v.raw_material_id, {})[v.attribute_definition_id] = v.value_numeric

    rows = []
    for c in recipe_version.components:
        role = (c.role_in_formulation or "").lower()
        is_isocyanate = bool(c.nco_equivalent_flag) or "isocyanate" in role
        entry = {
            "component": c.raw_material_name,
            "role": c.role_in_formulation,
            "php": c.php or 0.0,
            "side": "Isocyanate" if is_isocyanate else "Reactive-hydrogen",
            "nco_pct": None,
            "oh_number": None,
            "equivalent_weight_g_eq": None,
            "missing_reason": None,
        }
        mat_values = values_by_material.get(c.raw_material_id, {}) if c.raw_material_id else {}
        if not c.raw_material_id:
            entry["missing_reason"] = "Component has no linked raw_material_id, so no attribute data can be looked up."
            rows.append(entry)
            continue
        if is_isocyanate:
            nco_pct = mat_values.get(nco_def.id) if nco_def else None
            entry["nco_pct"] = nco_pct
            if nco_pct:
                entry["equivalent_weight_g_eq"] = round(4200.0 / nco_pct, 2)
            else:
                entry["missing_reason"] = "No NCO% recorded for this raw material (RMA-004 in raw_material_attribute_values)."
        else:
            oh_number = mat_values.get(oh_def.id) if oh_def else None
            entry["oh_number"] = oh_number
            if oh_number:
                entry["equivalent_weight_g_eq"] = round(56100.0 / oh_number, 2)
            else:
                entry["missing_reason"] = "No OH number recorded for this raw material (RMA-001 in raw_material_attribute_values)."
        rows.append(entry)
    return rows


def recipe_version_isocyanate_index(session, recipe_version):
    """CALC-015 'Actual isocyanate index' = Actual_NCO_equivalents /
    Actual_reactive_H_equivalents x 100, using each component's php as its
    mass basis (same 100-part convention as the other functions here).
    Per CALC-015's own validation_rule ("Block calculation when any
    reactive component equivalent data is missing"), this returns
    computed_index=None with an explicit per-component reason the moment
    ANY component lacks the NCO%/OH# data it needs - it never partially
    computes or guesses. Also returns the recipe's own recorded
    ratio_index (RecipeVersion.ratio_index) for reference, since that is
    the index value actually used in production today regardless of
    whether it can be independently re-derived here."""
    eq_rows = recipe_version_equivalent_weights(session, recipe_version)
    blocking = [r for r in eq_rows if r["equivalent_weight_g_eq"] is None]
    result = {
        "recorded_ratio_index": recipe_version.ratio_index,
        "computed_index": None,
        "blocked": bool(blocking) or not eq_rows,
        "blocking_reasons": [f"{r['component']}: {r['missing_reason']}" for r in blocking],
        "components": eq_rows,
    }
    if result["blocked"]:
        return result

    nco_equivalents = 0.0
    reactive_h_equivalents = 0.0
    for r in eq_rows:
        eq_weight = r["equivalent_weight_g_eq"]
        if not eq_weight:
            continue
        # php treated as grams on the standard 100-part basis; g / (g/eq) = eq
        equivalents = (r["php"] * 1000.0) / eq_weight
        if r["side"] == "Isocyanate":
            nco_equivalents += equivalents
        else:
            reactive_h_equivalents += equivalents

    if not reactive_h_equivalents:
        result["blocked"] = True
        result["blocking_reasons"].append("Total reactive-hydrogen equivalents computed to zero.")
        return result

    result["computed_index"] = round(nco_equivalents / reactive_h_equivalents * 100, 1)
    return result


def recipe_version_diff(version_a, version_b):
    """Component-by-component diff between two recipe versions of the same
    product grade: for every raw material appearing in either version, its php
    in each, the change, and whether it's new/removed/unchanged. This is
    the same "what actually changed" question Root-Cause Assistant answers
    for process settings between two production runs - applied to
    formulation instead, since today the only way to compare two versions
    is to read both ingredient lists by eye."""
    a_by_name = {c.raw_material_name.strip().lower(): c for c in version_a.components}
    b_by_name = {c.raw_material_name.strip().lower(): c for c in version_b.components}
    all_keys = sorted(set(a_by_name) | set(b_by_name))

    rows = []
    for key in all_keys:
        ca, cb = a_by_name.get(key), b_by_name.get(key)
        php_a = ca.php if ca else None
        php_b = cb.php if cb else None
        name = (ca or cb).raw_material_name
        role = (cb or ca).role_in_formulation
        if php_a is None:
            status, delta, delta_pct = "Added", php_b, None
        elif php_b is None:
            status, delta, delta_pct = "Removed", -php_a, None
        else:
            delta = round(php_b - php_a, 3)
            delta_pct = round((delta / php_a) * 100, 1) if php_a else None
            status = "Unchanged" if abs(delta) < 1e-9 else "Changed"
        rows.append(
            {
                "raw_material_name": name,
                "role": role,
                "php_a": php_a,
                "php_b": php_b,
                "delta": delta,
                "delta_pct": delta_pct,
                "status": status,
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        status_order = {"Added": 0, "Removed": 1, "Changed": 2, "Unchanged": 3}
        df["_order"] = df["status"].map(status_order)
        df = df.sort_values(["_order", "raw_material_name"]).drop(columns=["_order"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Actual (metered) usage vs. outcome.
# ---------------------------------------------------------------------------
# A recipe version's php is a target, not a measurement: the same recipe
# version, run a hundred times, does not meter out the exact same dosage of
# every material every time - that is what the flow meters on
# ComponentStreamReading exist to capture. Correlating a raw material's
# PLANNED php across recipe versions against outcomes was tried here and
# deliberately removed - the reviewer for this app judged it not a
# meaningful analysis (recipe versions replace each other rather than
# forming a comparable series, so "does changing the planned formulation
# matter" isn't a question worth ranking materials by). The functions below
# ask the question a plant running one settled recipe actually needs
# answered instead: "does this run's ACTUAL metered dosage of each material
# line up with this run's actual outcome" - with n = number of production
# runs, not number of recipe versions, so it works even for a grade with a
# single recipe version that has simply been run (and metered, and tested)
# many times.


@st.cache_data(ttl=_DATA_CACHE_TTL, show_spinner=False)
def actual_usage_dataframe(_session, foam_grade_id=None, production_method_id=None):
    """One row per (production run, raw-material stream): that stream's
    actual delivered quantity for the run, re-expressed as an actual-php-
    equivalent using the run's own Base-polyol stream reading as the
    100-parts basis - the same convention every planned recipe uses,
    computed here from what the flow meters actually measured for that one
    batch instead of from the recipe. Runs with no metered stream readings,
    or with no identifiable Base-polyol reading to normalize against, are
    skipped rather than guessed at. `foam_grade_id` accepts a single id or
    a list of ids (a foam family's grades pooled together).

    WP7 Phase 4 targeted-completion correction (2026-08-14, Charlie's
    Closeout Review Return to JC, targeted closure gate instruction 2 -
    "Include direct model reads such as ProductionPhase in addition to
    fixed-symbol searches"): this function previously located each run's
    Finalized ProductionPhase first and only read ComponentStreamReading
    rows linked to that phase (production_phase_id) - a direct
    ProductionPhase model read that the original Item-1/fixed-symbol scan
    missed because it doesn't touch PHASE_SETTING_FIELDS/PHASE_SETTING_
    LABELS at all. pages/4_Production_Run_Trial_Record.py's Material
    Metering capture UI was decoupled from ProductionPhase back in WP7
    Phase 2 ("a Finalized phase is no longer required first" - see that
    page's stream-import tab caption) and always writes production_run_id
    directly, so a run metered under the current architecture with no
    Finalized ProductionPhase ever created for it was silently excluded
    here - the same class of bug Item 1.3 already fixed for Batch
    Release's build_batch_release_record_data(). Fixed the same way:
    ComponentStreamReading is now queried directly by production_run_id
    (backfilled onto every historical row by legacy_migration.py's
    backfill_component_stream_reading_run_ids() during WP7 Phase 3), never
    via a located ProductionPhase. See
    tests/test_wp7_phase4_targeted_closure.py for the direct-evidence
    proof: a ComponentStreamReading with production_phase_id left NULL for
    a run that has zero ProductionPhase rows at all still surfaces here.

    Cached (see _DATA_CACHE_TTL) and batch-loads this grade's runs' stream
    readings in one query instead of one query per run - originally fixed
    2026-08-02 against the N+1 pattern shared with run_settings_dataframe/
    property_results_dataframe above; the ProductionPhase indirection
    removed in this correction was itself a second, smaller N+1-shaped
    query this batch load no longer needs. Logs its own duration to
    PerformanceLog on every call (see _log_performance) - only runs at all
    on a cache miss."""
    _t0 = time.perf_counter()
    q = _session.query(ProductionRun).options(
        joinedload(ProductionRun.recipe_version).joinedload(RecipeVersion.components)
    )
    grade_ids = _grade_id_list(foam_grade_id)
    if grade_ids:
        q = q.filter(ProductionRun.foam_grade_id.in_(grade_ids))
    if production_method_id:
        q = q.filter(ProductionRun.production_method_id == production_method_id)
    runs = q.all()

    run_ids = [run.id for run in runs]
    readings_by_run = {}
    if run_ids:
        all_readings = (
            _session.query(ComponentStreamReading)
            .filter(ComponentStreamReading.production_run_id.in_(run_ids))
            .all()
        )
        for r in all_readings:
            readings_by_run.setdefault(r.production_run_id, []).append(r)

    rows = []
    for run in runs:
        readings = readings_by_run.get(run.id, [])
        if not readings:
            continue

        recipe_version = run.recipe_version
        polyol_name = None
        if recipe_version:
            for c in recipe_version.components:
                if c.role_in_formulation and "base polyol" in c.role_in_formulation.strip().lower():
                    polyol_name = c.raw_material_name.strip().lower()
                    break
        if polyol_name is None:
            continue

        polyol_reading = next(
            (r for r in readings if r.stream_name and r.stream_name.strip().lower() == polyol_name), None
        )
        if polyol_reading is None or not polyol_reading.flow_total_qty:
            continue
        polyol_qty = polyol_reading.flow_total_qty

        for r in readings:
            if r.flow_total_qty is None:
                continue
            rows.append(
                {
                    "run_id": run.id,
                    "foam_grade_id": run.foam_grade_id,
                    "recipe_version_id": run.recipe_version_id,
                    "stream_name": r.stream_name,
                    "flow_total_qty": r.flow_total_qty,
                    "actual_php_equivalent": round((r.flow_total_qty / polyol_qty) * 100, 4),
                }
            )
    df = pd.DataFrame(rows)
    _log_performance(_session, "actual_usage_dataframe", foam_grade_id, None, (time.perf_counter() - _t0) * 1000, len(df))
    return df


def rank_component_actual_correlations(session, foam_grade_id, property_name, min_runs=3, production_method_id=None):
    """For every raw-material stream with metered readings for this grade,
    correlate its ACTUAL per-run dosage (see actual_usage_dataframe) against
    that same run's actual outcome for the chosen property, ranked by
    |correlation| descending.

    Needs real per-run variation to say anything: a material must have
    metered readings paired with a quality result for at least `min_runs`
    production runs, or it's excluded rather than shown as a misleading
    correlation. Returns an empty DataFrame if nothing qualifies -
    callers should treat that as "not enough metered/tested runs yet", not
    as "no relationship found"."""
    usage_df = actual_usage_dataframe(session, foam_grade_id=foam_grade_id, production_method_id=production_method_id)
    if usage_df.empty:
        return pd.DataFrame()

    results_df = property_results_dataframe(
        session, foam_grade_id=foam_grade_id, property_name=property_name, production_method_id=production_method_id
    )
    if results_df.empty:
        return pd.DataFrame()
    per_run_result = results_df.groupby("run_id")["actual_value"].mean()

    rows = []
    for material, sub in usage_df.groupby("stream_name"):
        php_series = sub.set_index("run_id")["actual_php_equivalent"]
        outcome_series = per_run_result.reindex(php_series.index)
        paired = pd.DataFrame({"php": php_series, "outcome": outcome_series}).dropna()
        n = len(paired)
        if n < min_runs:
            continue
        corr = paired["php"].corr(paired["outcome"])
        if pd.isna(corr):
            continue
        rows.append({"raw_material_name": material, "n_runs": n, "correlation": round(corr, 3)})

    ranked = pd.DataFrame(rows)
    if not ranked.empty:
        ranked["_abs"] = ranked["correlation"].abs()
        ranked = ranked.sort_values("_abs", ascending=False).drop(columns=["_abs"]).reset_index(drop=True)
    return ranked


# ---------------------------------------------------------------------------
# Trend Analysis: statistical process control, not just a line chart
# ---------------------------------------------------------------------------
# A plot of actual-vs-target over time cannot, by itself, tell a reviewer
# whether a wobble is real or just noise, or when a real shift actually
# started. That is what statistical process control (SPC) exists for. The
# four functions below are the standard SPC toolkit for exactly this kind of
# data (one measurement per production run, tracked over time against a
# target): an individuals control chart with real control limits and the
# classic Western Electric/Nelson run rules (catches sudden shifts and
# short-run drift), a process capability index against the property's
# tolerance band (catches "technically stable but too close to spec" even
# with no rule violations), a CUSUM chart (catches slow sustained drift a
# Shewhart chart is notoriously bad at catching early - pump wear, catalyst
# degradation, a slightly-off raw material lot), and a formal trend test
# (replaces "average of the first half vs. the second half" with an actual
# significance test). All four are deterministic - no ingredient list, no
# assumption, no interpretation. Interpretation is PI3's job, downstream of
# these numbers, same as everywhere else in the app.

_D2_MOVING_RANGE = 1.128  # control-chart constant for a 2-point moving range (individuals chart)


def property_run_series(
    session, foam_grade_id, property_name, normalize_pct_of_target=False, include_trials=False,
    production_method_id=None,
):
    """One row per production run (mean of any replicate results) for a
    product grade/property, sorted chronologically by test date. This is the
    base series every SPC function below works from - a control chart,
    capability index, or trend test needs one point per run, not one point
    per replicate.

    `normalize_pct_of_target=True` re-expresses actual_value/target_value
    as percent-of-target (see normalize_to_pct_of_target) before returning
    - pass this when foam_grade_id is a foam family's list of grade ids, so
    the control chart/capability/CUSUM/trend-test functions downstream
    don't mistake a grade-to-grade target difference for a real shift or
    drift. Every SPC function reads only actual_value/target_value, so
    normalizing here is sufficient - nothing downstream needs to know
    whether it's looking at a raw unit or percent-of-target.

    `include_trials` (default False) is passed straight through to
    property_results_dataframe() - see that function's docstring. Only
    Trend Analysis passes True here. Trial-sourced rows have no run_id
    (lab trials have no ProductionRun behind them), so grouping can't use
    plain run_id alone once trials are included - "source"/"run_id"/
    "trial_id" together identify one event (one production run, or one
    lab trial) regardless of source; dropna=False keeps trial rows (which
    have a null run_id) and production-run rows (which have a null
    trial_id) from being silently dropped by groupby's default NaN
    handling."""
    df = property_results_dataframe(
        session, foam_grade_id=foam_grade_id, property_name=property_name, include_trials=include_trials,
        production_method_id=production_method_id,
    )
    if df.empty:
        return df
    group_cols = ["source", "run_id", "trial_id"] if "trial_id" in df.columns else ["run_id"]
    per_run = (
        df.groupby(group_cols, dropna=False)
        .agg(
            actual_value=("actual_value", "mean"),
            target_value=("target_value", "mean"),
            tested_at=("tested_at", "max"),
            recipe_version=("recipe_version", "first"),
            machine=("machine", "first"),
            foam_grade=("foam_grade", "first"),
            n_replicates=("result_id", "count"),
        )
        .reset_index()
    )
    per_run = per_run.dropna(subset=["tested_at", "actual_value"]).sort_values("tested_at").reset_index(drop=True)
    if normalize_pct_of_target:
        per_run = normalize_to_pct_of_target(per_run)
    return per_run


def _moving_range_sigma(values):
    """Short-term sigma estimated from the mean moving range between
    consecutive points (values / d2), rather than the naive sample stdev -
    the standard control-chart estimator, since it isn't inflated by a real
    shift the way the plain stdev of the whole series would be. Falls back
    to the sample stdev if there aren't enough points for a moving range."""
    n = len(values)
    if n < 2:
        return 0.0
    mr = np.abs(np.diff(values))
    mr_bar = mr.mean()
    if mr_bar > 0:
        return mr_bar / _D2_MOVING_RANGE
    return float(np.std(values, ddof=1)) if n >= 2 else 0.0


def control_chart_analysis(series_df, min_points=5):
    """Individuals (I-MR) control chart: center line at the process mean,
    control limits at +/-3 sigma (moving-range sigma, see
    _moving_range_sigma), plus the 4 most commonly used Western
    Electric/Nelson run rules so a real signal is flagged explicitly instead
    of left for the reviewer to eyeball:
    - beyond the 3-sigma control limits (a genuine special-cause point)
    - 8+ consecutive points on one side of the center line (a sustained shift)
    - 6+ consecutive points steadily rising or falling (a sustained drift)
    - 2 of any 3 consecutive points beyond the 2-sigma warning line
    Returns a dict with the annotated per-point DataFrame, the control
    limits, and a flags list (each flag reduced to its first occurrence -
    "the earliest point where this pattern is already true" - plus how many
    points match it). Returns {"ready": False, "n": n} if there aren't at
    least `min_points` results yet - a control chart from a handful of
    points is noise dressed up as insight."""
    n = len(series_df)
    if n < min_points:
        return {"ready": False, "n": n}

    values = series_df["actual_value"].to_numpy(dtype=float)
    mean = float(values.mean())
    sigma = _moving_range_sigma(values)
    ucl = mean + 3 * sigma
    lcl = mean - 3 * sigma
    warn_hi = mean + 2 * sigma
    warn_lo = mean - 2 * sigma

    chart_df = series_df.copy().reset_index(drop=True)
    chart_df["center_line"] = mean
    chart_df["ucl"] = ucl
    chart_df["lcl"] = lcl

    flag_hits = {}  # rule -> list of point indices

    def _record(rule, idx):
        flag_hits.setdefault(rule, []).append(idx)

    if sigma > 0:
        for i, v in enumerate(values):
            if v > ucl or v < lcl:
                _record("Beyond 3-sigma control limit", i)

        side = np.sign(values - mean)
        run_len = 1
        for i in range(1, n):
            run_len = run_len + 1 if side[i] == side[i - 1] and side[i] != 0 else 1
            if run_len >= 8:
                _record("Sustained shift (8+ consecutive points on one side)", i)

        trend_len = 1
        direction = 0
        for i in range(1, n):
            d = np.sign(values[i] - values[i - 1])
            trend_len = trend_len + 1 if d == direction and d != 0 else 1
            direction = d if d != 0 else direction
            if trend_len >= 6:
                _record("Sustained drift (6+ consecutive points trending)", i)

        for i in range(2, n):
            window = values[i - 2 : i + 1]
            if (window > warn_hi).sum() >= 2 or (window < warn_lo).sum() >= 2:
                _record("2-of-3 beyond 2-sigma warning line", i)

    flags = []
    for rule, indices in flag_hits.items():
        first_i = min(indices)
        flags.append(
            {
                "rule": rule,
                "first_index": first_i,
                "first_run_id": _safe_int(chart_df.iloc[first_i]["run_id"]),
                "first_source": chart_df.iloc[first_i]["source"] if "source" in chart_df.columns else "Production Run",
                "first_tested_at": chart_df.iloc[first_i]["tested_at"],
                "points_matching": len(indices),
            }
        )
    flags.sort(key=lambda f: f["first_index"])

    return {
        "ready": True,
        "n": n,
        "mean": mean,
        "sigma": sigma,
        "ucl": ucl,
        "lcl": lcl,
        "chart_df": chart_df,
        "flags": flags,
        "in_control": len(flags) == 0,
    }


def capability_analysis(series_df, tolerance_pct=0.10, min_points=5, spec=None):
    """Process capability (Cpk) against the property's real spec limit when
    one is available, or the app's own +/-10% pass/fail convention as a
    fallback. Cpk answers a different question than the control chart: a
    process can be perfectly "in control" (no rule violations, stable mean)
    and still be a Cpk of 0.6 - too close to its own spec limits to have any
    real margin. Returns None if there isn't a usable, consistent target
    value or not enough points yet.

    WP6-S09 closure (2026-08-09, per Charlie's technical closure
    instructions section 3.7, UAT-016): pass the real GradeSpecification row
    (or any object exposing target_operator/target_value/lower_limit/
    upper_limit, e.g. a WP3 GradeSpecification) via `spec` when one exists
    for this exact property/grade. A one-sided spec ("<=0.024 W/(m.K)", no
    real lower bound) is evaluated one-sided (Cpu only) instead of being
    forced into a symmetric target+/-10% band that invents a lower limit
    Charlie's own controlled data never specified - the old +/-10% fallback
    below stays in place for properties/pages with no real spec wired
    through yet (flexible-foam properties, pooled foam-family analysis).

    Rule of thumb this function's callers should use for the number:
    Cpk >= 1.33 is generally considered capable, 1.0-1.33 marginal, <1.0 not
    capable (the process routinely produces some results outside the
    tolerance band even when "in control")."""
    n = len(series_df)
    if n < min_points:
        return None

    values = series_df["actual_value"].to_numpy(dtype=float)
    mean = float(values.mean())
    sigma = _moving_range_sigma(values)
    if sigma <= 0:
        return None

    op = (getattr(spec, "target_operator", None) or "").strip() if spec is not None else ""
    if spec is not None and op in ("<=", ">="):
        if op == "<=":
            usl = spec.target_value if spec.target_value is not None else spec.upper_limit
            lsl = None
        else:
            usl = None
            lsl = spec.target_value if spec.target_value is not None else spec.lower_limit
        target = usl if op == "<=" else lsl
        if target is None:
            return None
        cpu = (usl - mean) / (3 * sigma) if usl is not None else None
        cpl = (mean - lsl) / (3 * sigma) if lsl is not None else None
        cpk = cpu if op == "<=" else cpl
        return {
            "n": n,
            "target": target,
            "mean": mean,
            "sigma": sigma,
            "usl": usl,
            "lsl": lsl,
            "cpu": round(cpu, 3) if cpu is not None else None,
            "cpl": round(cpl, 3) if cpl is not None else None,
            "cpk": round(cpk, 3),
            "one_sided": True,
            "operator": op,
        }
    if spec is not None and op == "between":
        usl, lsl = spec.upper_limit, spec.lower_limit
        target = spec.target_value if spec.target_value is not None else (
            (usl + lsl) / 2 if usl is not None and lsl is not None else None
        )
        if target is None or usl is None or lsl is None:
            return None
        cpu = (usl - mean) / (3 * sigma)
        cpl = (mean - lsl) / (3 * sigma)
        cpk = min(cpu, cpl)
        return {
            "n": n, "target": target, "mean": mean, "sigma": sigma,
            "usl": usl, "lsl": lsl, "cpu": round(cpu, 3), "cpl": round(cpl, 3),
            "cpk": round(cpk, 3), "one_sided": False, "operator": op,
        }

    # Fallback: no real spec wired through for this property/page - use the
    # app's own +/-tolerance_pct convention as before (unchanged behavior).
    target = series_df["target_value"].dropna().median()
    if pd.isna(target) or target == 0:
        return None
    usl = target * (1 + tolerance_pct)
    lsl = target * (1 - tolerance_pct)
    cpu = (usl - mean) / (3 * sigma)
    cpl = (mean - lsl) / (3 * sigma)
    cpk = min(cpu, cpl)

    return {
        "n": n,
        "target": target,
        "mean": mean,
        "sigma": sigma,
        "usl": usl,
        "lsl": lsl,
        "cpu": round(cpu, 3),
        "cpl": round(cpl, 3),
        "cpk": round(cpk, 3),
        "one_sided": False,
        "operator": None,
    }


def cusum_analysis(series_df, k=0.5, h=5.0, min_points=8):
    """Two-sided tabular CUSUM: standardizes each point to z = (x -
    reference) / sigma, then accumulates C+ (upward drift) and C- (downward
    drift), resetting toward zero each step by a slack k (in sigma units -
    default 0.5 sigma, tuned to detect a sustained ~1-sigma shift) and
    flagging a breach once the cumulative sum exceeds the decision interval
    h (default 5 sigma). This exists because a Shewhart control chart is
    bad at catching exactly this failure mode: a small, sustained shift (a
    pump slowly wearing, a catalyst slowly losing activity) that never puts
    any single point outside the 3-sigma control limits but is still a
    real, accumulating drift.

    The reference point is the property's own recorded target value, not
    the sample mean of the series - deliberately. CUSUM is meant to detect
    drift away from where the process is supposed to be; if the series
    already contains an unaddressed shift, the sample mean is itself
    contaminated by that shift; centering on it would dilute the very drift
    this function exists to catch (and can even flag the earlier, correct
    period as the anomaly instead of the later, shifted one). Falls back to
    the sample mean only if no target value is recorded for this property.
    Returns None if there aren't enough points yet."""
    n = len(series_df)
    if n < min_points:
        return None

    values = series_df["actual_value"].to_numpy(dtype=float)
    target = series_df["target_value"].dropna().median()
    reference = float(target) if pd.notna(target) else float(values.mean())
    sigma = _moving_range_sigma(values)
    if sigma <= 0:
        return None

    z = (values - reference) / sigma
    c_pos = np.zeros(n)
    c_neg = np.zeros(n)
    for i in range(n):
        prev_pos = c_pos[i - 1] if i > 0 else 0.0
        prev_neg = c_neg[i - 1] if i > 0 else 0.0
        c_pos[i] = max(0.0, prev_pos + z[i] - k)
        c_neg[i] = min(0.0, prev_neg + z[i] + k)

    breach_index = None
    breach_direction = None
    for i in range(n):
        if c_pos[i] > h:
            breach_index, breach_direction = i, "upward"
            break
        if c_neg[i] < -h:
            breach_index, breach_direction = i, "downward"
            break

    chart_df = series_df.copy().reset_index(drop=True)
    chart_df["cusum_positive"] = c_pos
    chart_df["cusum_negative"] = c_neg

    result = {
        "n": n,
        "k": k,
        "h": h,
        "reference": reference,
        "chart_df": chart_df,
        "breach_index": breach_index,
        "breach_direction": breach_direction,
    }
    if breach_index is not None:
        result["breach_run_id"] = _safe_int(chart_df.iloc[breach_index]["run_id"])
        result["breach_source"] = (
            chart_df.iloc[breach_index]["source"] if "source" in chart_df.columns else "Production Run"
        )
        result["breach_tested_at"] = chart_df.iloc[breach_index]["tested_at"]
    return result


def trend_test(series_df, min_points=5, alpha=0.05):
    """Formal test for a monotonic trend over the run sequence - two
    complementary checks, not one, so the verdict doesn't rest on a single
    assumption about the trend's shape (fixed 2026-08-05: a user correctly
    pointed out that a linear-only test silently assumes the drift is a
    straight line, and never says so):

    1. Linear regression (scipy.stats.linregress) of actual_value against
       run order - the primary test. Assumes the drift proceeds at a
       roughly CONSTANT rate (a straight line) - the shape a steady
       mechanical/chemical cause (pump wear, catalyst degradation, a
       drifting raw-material lot) typically produces. slope/intercept
       together define the fitted line the page draws directly on the
       results chart; r_squared is how much of the run-to-run variation
       that line explains; p_value is the chance a slope this steep is
       just random noise.
    2. Mann-Kendall (Kendall's tau via scipy.stats.kendalltau, of
       actual_value against run order) - a secondary, non-parametric
       cross-check that only assumes the DIRECTION is consistent, not
       that the rate is constant. This is what catches a real trend that
       curves or changes pace, which the linear test's R² would otherwise
       under-credit and risk being read as noise. mk_significant usually
       agrees with `significant`; when it doesn't, that disagreement
       itself is the useful signal (see pages/16_Trend_Analysis.py's
       cross-check message) - it means the drift likely isn't a straight
       line.

    p < 0.05 (alpha) is the conventional threshold used for both. Returns
    None if there aren't enough points yet."""
    n = len(series_df)
    if n < min_points:
        return None

    values = series_df["actual_value"].to_numpy(dtype=float)
    x = np.arange(n, dtype=float)
    result = scipy_stats.linregress(x, values)

    direction = "increasing" if result.slope > 0 else ("decreasing" if result.slope < 0 else "flat")
    significant = result.pvalue < alpha

    mk = scipy_stats.kendalltau(x, values)
    mk_tau = float(mk.correlation)
    mk_p_value = float(mk.pvalue)
    if np.isnan(mk_tau):
        mk_tau = 0.0
    if np.isnan(mk_p_value):
        mk_p_value = 1.0
    mk_significant = mk_p_value < alpha
    mk_direction = "increasing" if mk_tau > 0 else ("decreasing" if mk_tau < 0 else "flat")

    return {
        "n": n,
        "slope_per_run": round(float(result.slope), 5),
        "intercept": round(float(result.intercept), 5),
        "r_squared": round(float(result.rvalue) ** 2, 3),
        "p_value": round(float(result.pvalue), 4),
        "significant": significant,
        "direction": direction,
        "alpha": alpha,
        "mk_tau": round(mk_tau, 3),
        "mk_p_value": round(mk_p_value, 4),
        "mk_significant": mk_significant,
        "mk_direction": mk_direction,
    }
