"""WP3 - live-computed conformance evaluation, report, and analytics.

Converged Joint Implementation Plan, section 7.3; Gate 2 acceptance items
G2-06 ("conformance check computes correctly") and G2-11 ("rendered
application report") - see PI3_Rigid_Foam_Edition_WP3_Technical_Build_Pack_
and_Gate_2_Specification.docx.

Established project precedent (see quality_standards.py's module docstring,
and this app's own hard-won "Make pass/fail computed live everywhere, not
stored" fix from the flexible app's history, ported into this fork - see
version.py): a Pass/Fail verdict computed once and persisted goes stale the
moment the underlying specification or data changes. Charlie's WP3
Technical Build Pack literally specifies stored ConformanceEvaluation,
ReportRecord, and AnalyticsRecord tables - this module is a deliberate,
considered deviation from that literal spec: conformance, report, and
analytics data are all assembled live from GradeSpecification +
PhysicalPropertyResult (db.py) at read time and returned as plain
dicts/lists, never written to a table. This was flagged to Charlie/Stefan
in the deferred-concerns memo delivered 2026-08-05/06, not decided silently.

No stored table also means: correcting a grade specification's limits (or
re-testing a sample) takes effect on every report immediately, with no
separate recompute/migration step - exactly the property that made the
flexible app's live pass/fail worth the extra join cost.
"""

import pandas as pd
from sqlalchemy.orm import joinedload

import unit_conversion
from db import (
    CustomerTrial,
    GradeSpecification,
    OptimizationTrial,
    PhysicalPropertyResult,
    ProductionRun,
    RawMaterialLotUse,
    RecipeVersion,
)


def evaluate_specification(spec, actual_value):
    """Live Pass/Fail/None for one GradeSpecification row against one
    actual_value, using spec.target_operator / target_value / lower_limit /
    upper_limit exactly as entered - no separate industry-tolerance table
    here (contrast quality_standards.compute_pass_fail, used by the
    flexible app's fixed density/hardness/etc. properties): a rigid-foam
    grade specification's limits are Charlie's own controlled data (the
    WP2/WP3 Grade Specifications sheet), entered directly as the limit to
    evaluate against, not a tolerance band derived from a single target.

    Returns (verdict, margin):
    - verdict: "Pass" / "Fail" / None (None = nothing to compare - actual_value
      or the relevant limit is missing).
    - margin: how far inside (positive) or outside (negative) the limit the
      actual value is, in the property's own unit. None alongside a None
      verdict.

    WP6-S09 fix (2026-08-09, per Charlie's UAT-011 review): "<=" and ">="
    used to require spec.target_value specifically, with no fallback to
    lower_limit/upper_limit. That matched tests/test_wp3_uat_cases.py's
    frozen fixture (which always populates target_value alongside upper_
    limit/lower_limit for a "<="/">=" spec, e.g. target_value=0.024,
    upper_limit=0.024) but NOT the real seeded grade_specifications rows
    (WP5 Wave 5), which for every real "<="/">=" row leave target_value
    NULL and store the actual ceiling/floor in upper_limit/lower_limit -
    the exact same field convention "between" already used. The result was
    every real rigid-foam spec evaluating to (None, None) - a matched
    result silently excluded from Pass/Fail with no error, which is why
    Charlie found the Batch Release Record's target/Pass-Fail columns
    blank against real data despite this module existing since WP3. Fixed
    by falling back to upper_limit ("<=") / lower_limit (">=") whenever
    target_value is None - purely additive: the frozen fixture always sets
    target_value too, so its behavior is unchanged; this only starts
    evaluating specs that previously fell through to None.
    """
    if actual_value is None:
        return None, None

    op = (spec.target_operator or "<=").strip()

    if op == "<=":
        limit = spec.target_value if spec.target_value is not None else spec.upper_limit
        if limit is None:
            return None, None
        margin = limit - actual_value
        return ("Pass" if actual_value <= limit else "Fail"), margin

    if op == ">=":
        limit = spec.target_value if spec.target_value is not None else spec.lower_limit
        if limit is None:
            return None, None
        margin = actual_value - limit
        return ("Pass" if actual_value >= limit else "Fail"), margin

    if op == "=":
        if spec.target_value is None:
            return None, None
        margin = -abs(actual_value - spec.target_value)
        return ("Pass" if actual_value == spec.target_value else "Fail"), margin

    if op == "between":
        if spec.lower_limit is None or spec.upper_limit is None:
            return None, None
        passed = spec.lower_limit <= actual_value <= spec.upper_limit
        margin = min(actual_value - spec.lower_limit, spec.upper_limit - actual_value)
        return ("Pass" if passed else "Fail"), margin

    return None, None


def production_release_status(verdict, is_uat_only):
    """WP3 UAT case 10: a UAT-only grade specification passing its own
    functional limit still cannot be used to release production - the
    limit exists to prove the schema/app logic, not as an approved plant
    specification (see GradeSpecification/FoamGrade UAT_ONLY status and
    RecipeVersion.production_use_rule in db.py). Returns "UAT_PASS_NO_
    RELEASE" when a Pass verdict comes from a UAT-only spec, else None -
    a plain pass/fail is not itself a production-release decision."""
    if verdict == "Pass" and is_uat_only:
        return "UAT_PASS_NO_RELEASE"
    return None


def _specs_match_result(spec, result):
    """A GradeSpecification row applies to a PhysicalPropertyResult row when
    the property matches and, wherever the spec pins down a specific test
    method/condition/orientation/location/unit, the result's own context
    matches it too. A spec that leaves one of those context fields blank
    applies regardless of the result's value for it (e.g. a density spec
    that doesn't care about orientation matches a result measured at any
    orientation) - deliberately permissive, since not every spec in the
    WP3 package constrains every context dimension.

    Returns (matches: bool, reason: str|None) - reason is a short
    human-readable mismatch explanation, used by compute_conformance_report
    to report EXCLUDED_CONTEXT with a cause rather than a bare None
    (Gate 2 item G2-10, WP3 UAT cases 04/05/06/09 - wrong condition, wrong
    method, wrong unit, and the excluded patent benchmark all need a
    traceable "why" rather than silently returning nothing).

    Unit is compared as free text (spec.unit vs result.unit) rather than
    resolved through a UOM-ID cross-reference. WP3 (UAT case 06, "wrong
    unit, conversion deferred") treated every unit mismatch as an excluded
    context; WP4 (see unit_conversion.py) now recognizes a fixed, growing
    set of convertible unit pairs (e.g. mW/(m.K) vs W/(m.K)) and lets those
    through as a match rather than excluding them - compute_conformance_report
    then evaluates the result's value converted into the spec's unit, never
    the raw stored value in the wrong unit. A unit pair unit_conversion
    doesn't recognize (unknown unit, or two genuinely different physical
    quantities) is still excluded exactly as in WP3 - this is strictly an
    addition, not a loosening, of the WP3 matching behavior.
    """
    if spec.property_definition_id and result.property_definition_id:
        if spec.property_definition_id != result.property_definition_id:
            return False, "property mismatch"
    elif (spec.property_name or "").strip().lower() != (result.property_name or "").strip().lower():
        return False, "property mismatch"

    if spec.property_method_id and result.property_method_id and spec.property_method_id != result.property_method_id:
        return False, "method mismatch"
    if spec.condition_id and result.condition_id and spec.condition_id != result.condition_id:
        return False, "condition mismatch"
    if spec.orientation_id and result.orientation_id and spec.orientation_id != result.orientation_id:
        return False, "orientation mismatch"
    if spec.location_id and result.location_id and spec.location_id != result.location_id:
        return False, "location mismatch"
    if spec.unit and result.unit and spec.unit.strip().lower() != result.unit.strip().lower():
        if not unit_conversion.convertible(result.unit, spec.unit):
            return False, "unit mismatch (not convertible)"
        # Convertible - not treated as a mismatch. compute_conformance_report
        # (via resolve_actual_value below) converts the result's value into
        # the spec's unit before it's ever compared against a limit.
    return True, None


def resolve_actual_value(spec, result):
    """Returns (value_to_evaluate, as_recorded_value, as_recorded_unit,
    converted: bool) for a spec/result pair that _specs_match_result has
    already accepted.

    When the spec and result share a unit (the WP3-only case, and still the
    overwhelming majority), value_to_evaluate is simply result.actual_value
    unchanged - nothing about existing behavior/UAT cases 01-05/07-10
    changes. When they differ but unit_conversion recognizes the pair,
    value_to_evaluate is the result's value converted into the spec's unit
    - that converted value is what evaluate_specification() compares
    against the spec's limit, and what the WP3 Property Conformance Report
    displays in the "Actual" column (which is always headed with the
    spec's own unit) - showing the raw as-recorded number there under the
    spec's unit label would silently misstate the result. as_recorded_value/
    as_recorded_unit preserve the original measurement for traceability
    (e.g. a report note like "converted from 23 mW/(m.K)")."""
    raw = result.actual_value
    if raw is None:
        return None, None, result.unit, False
    if spec.unit and result.unit and spec.unit.strip().lower() != result.unit.strip().lower():
        converted = unit_conversion.convert(raw, result.unit, spec.unit)
        if converted is not None:
            return converted, raw, result.unit, True
    return raw, raw, result.unit, False


# WP6-S09 closure (2026-08-09, per Charlie's technical closure instructions
# section 3.2): controlled, explicit per-property dimension rules, keyed by
# the property's own name (present on every real PhysicalPropertyResult as
# the auto-filled property_name snapshot, and on every test stand-in) - this
# is Charlie's domain call, not something to infer from free-text
# mandatory_context alone. Thermal conductivity and Compressive strength
# both need specimen-level thickness/geometry plus test direction; Core
# density and Closed-cell content need neither (orientation stays optional -
# a recorded valid result remains evaluable with orientation_id empty).
# Any property NOT in this table falls back to the original text-derived
# heuristic below, so properties Charlie hasn't explicitly ruled on keep
# their previous (already-correct) behavior.
_CONTROLLED_DIMENSION_RULES = {
    "thermal conductivity": (True, True),
    "compressive strength": (True, True),
    "core density": (False, False),
    "closed-cell content": (False, False),
    "closed cell content": (False, False),
}


def _property_dimension_requirements(property_definition, property_name=None):
    """(requires_thickness, requires_orientation) for one property result.

    Checks Charlie's controlled _CONTROLLED_DIMENSION_RULES table first (by
    property_name, case-insensitive) since that section 3.2 table is his
    explicit domain ruling and is authoritative over the four properties it
    names. Falls back to reading the property's own mandatory_context text
    (WP5 Wave 2 controlled data) for any property not in that table, so
    behavior for everything else is unchanged from the original WP6-S09
    action-1 fix.

    Returns (False, False) if neither a name match nor a property_definition
    with mandatory_context is available - nothing to check a requirement
    against."""
    name_key = (property_name or "").strip().lower()
    if name_key in _CONTROLLED_DIMENSION_RULES:
        return _CONTROLLED_DIMENSION_RULES[name_key]
    text = (getattr(property_definition, "mandatory_context", None) or "").lower()
    requires_thickness = "thickness" in text
    requires_orientation = "orientation" in text or "direction" in text
    return requires_thickness, requires_orientation


def validate_result_completeness(result, sample=None):
    """Checks that a PhysicalPropertyResult carries the minimum context
    its own property genuinely needs before it can be evaluated - Gate 2
    item G2-10 / WP3 UAT cases 07 and 08 ("missing thickness" / "missing
    orientation" both expect INVALID for thermal conductivity, which needs
    both).

    WP6-S09 fix (2026-08-09, Charlie's original sequence item 1): made this
    property-specific instead of requiring both fields unconditionally - see
    _property_dimension_requirements above.

    WP6-S09 closure refinement (2026-08-09, per Charlie's technical closure
    instructions section 3.2, "make test completeness property/method
    specific" + "use the Test Specimen / Test Result level for
    specimen-specific dimensions"): (1) the per-property rule now comes from
    Charlie's controlled table (thermal conductivity AND compressive
    strength both need thickness+direction; core density/closed-cell content
    need neither), and (2) thickness now reads PRIMARILY from
    PhysicalPropertyResult.thickness_mm (the specimen/result that actually
    produced this measurement - one parent Sample can feed several lab
    specimens with different geometry, so the dimension belongs to the
    specimen, not the parent). Sample.thickness_mm is kept only as a
    fallback for pre-existing rows captured before this column existed (the
    frozen Gate-2 fixture in tests/test_wp3_uat_cases.py sets thickness only
    on its sample stand-in and must keep working unchanged) - it is treated
    as parent-sample context only, never as the primary source for new data.

    Returns (True, None) if complete, or (False, reason) naming the first
    missing field."""
    property_definition = getattr(result, "property_definition", None)
    property_name = getattr(result, "property_name", None)
    requires_thickness, requires_orientation = _property_dimension_requirements(property_definition, property_name)

    if requires_orientation and result.orientation_id is None:
        return False, "missing orientation"
    if requires_thickness:
        thickness = getattr(result, "thickness_mm", None)
        if thickness is None and sample is not None:
            thickness = getattr(sample, "thickness_mm", None)
        if thickness is None:
            return False, "missing thickness"
    return True, None


def compute_conformance_report(
    session, foam_grade_id, production_run_id=None, customer_trial_id=None, optimization_trial_id=None,
    sample_id=None,
):
    """Assembles a live conformance report: every GradeSpecification for
    this grade, matched against the best available PhysicalPropertyResult
    recorded for the given run/trial, with a freshly computed verdict. This
    IS the WP3 "Conformance Evaluation" and the data behind the "Report"
    (Gate 2 items G2-06/G2-11) - returned as a list of dicts, not written
    anywhere (see module docstring).

    Each row's "status" is one of:
    - "Pass" / "Fail": a matching result was found, was complete enough to
      evaluate, and evaluate_specification() ran (see that function).
    - "EXCLUDED_CONTEXT": a result exists for this run but its method/
      condition/orientation/location/unit doesn't match this spec - see
      _specs_match_result. "excluded_reason" names which field.
    - "INVALID": a matching result was found but is missing required
      context (orientation or thickness) - see validate_result_completeness.
    - "NO_RESULT": no result at all was recorded for this run against this
      spec's property.
    Additionally, "production_release" is "UAT_PASS_NO_RELEASE" whenever the
    verdict is "Pass" but the spec/grade is UAT-only (see
    GradeSpecification.notes / FoamGrade.status - a UAT-only grade specification
    passing its own functional limit still may not be used to release
    production, WP3 UAT case 10).

    Exactly one of production_run_id / customer_trial_id /
    optimization_trial_id is expected, matching the "exactly one of N
    optional source FKs" pattern already used throughout db.py (Sample,
    PhysicalPropertyResult, ...). Returns [] if none is given - nothing to
    evaluate against.

    sample_id (WP6-S09 addition, 2026-08-09, for the Sample Certificate of
    Analysis report - Charlie's UAT-014 review): optional additional filter
    narrowing the candidate results down to one specific sample, on top of
    whichever source filter above is given. A production run/trial can carry
    several samples, each with its own result per property - the Sample
    Certificate needs conformance evaluated against just the one sample it's
    reporting on, not every sample under that run.
    """
    specs = session.query(GradeSpecification).filter(GradeSpecification.foam_grade_id == foam_grade_id).all()

    query = session.query(PhysicalPropertyResult)
    if production_run_id:
        query = query.filter(PhysicalPropertyResult.production_run_id == production_run_id)
    elif customer_trial_id:
        query = query.filter(PhysicalPropertyResult.customer_trial_id == customer_trial_id)
    elif optimization_trial_id:
        query = query.filter(PhysicalPropertyResult.optimization_trial_id == optimization_trial_id)
    else:
        return []
    if sample_id:
        query = query.filter(PhysicalPropertyResult.sample_id == sample_id)
    results = query.all()

    rows = []
    for spec in specs:
        is_uat_only = bool(spec.foam_grade and spec.foam_grade.status == "UAT_ONLY")
        candidates = [r for r in results if r.property_definition_id == spec.property_definition_id
                      or (r.property_name or "").strip().lower() == (spec.property_name or "").strip().lower()]
        if not candidates:
            rows.append({
                "spec_id": spec.id, "property_name": spec.property_name, "status": "NO_RESULT",
                "excluded_reason": None, "result_id": None, "actual_value": None, "verdict": None,
                "margin": None, "production_release": None,
            })
            continue

        # Among same-property candidates, find the one whose full context
        # matches (method/condition/orientation/location/unit); keep the
        # first mismatch reason for reporting if none match.
        matched_result, excluded_reason = None, None
        for r in candidates:
            ok, reason = _specs_match_result(spec, r)
            if ok:
                matched_result = r
                break
            excluded_reason = excluded_reason or reason

        if matched_result is None:
            rows.append({
                "spec_id": spec.id, "property_name": spec.property_name, "status": "EXCLUDED_CONTEXT",
                "excluded_reason": excluded_reason, "result_id": None, "actual_value": None, "verdict": None,
                "margin": None, "production_release": None,
            })
            continue

        complete, incomplete_reason = validate_result_completeness(matched_result, sample=matched_result.sample)
        if not complete:
            rows.append({
                "spec_id": spec.id, "property_name": spec.property_name, "status": "INVALID",
                "excluded_reason": incomplete_reason, "result_id": matched_result.id,
                "actual_value": matched_result.actual_value, "verdict": None, "margin": None,
                "production_release": None, "unit_converted": False,
                "as_recorded_value": matched_result.actual_value, "as_recorded_unit": matched_result.unit,
            })
            continue

        eval_value, as_recorded_value, as_recorded_unit, unit_converted = resolve_actual_value(spec, matched_result)
        verdict, margin = evaluate_specification(spec, eval_value)
        production_release = production_release_status(verdict, is_uat_only)
        rows.append({
            "spec_id": spec.id,
            "property_name": spec.property_name,
            "status": verdict,
            "excluded_reason": None,
            "target_operator": spec.target_operator,
            "target_value": spec.target_value,
            "lower_limit": spec.lower_limit,
            "upper_limit": spec.upper_limit,
            "unit": spec.unit,
            "result_id": matched_result.id,
            "actual_value": eval_value,
            "as_recorded_value": as_recorded_value,
            "as_recorded_unit": as_recorded_unit,
            "unit_converted": unit_converted,
            "verdict": verdict,
            "margin": margin,
            "production_release": production_release,
        })
    return rows


def compute_grade_achievement_summary(session, foam_grade_id, production_run_ids):
    """WP4 (Converged Joint Implementation Plan, section 7.5) rigid-foam
    equivalent of the flexible app's "Does the current recipe meet target?"
    table (pages/15_Recipe_Optimization.py's expectation_summary, built on
    analytics.property_results_dataframe + quality_standards.compute_pass_fail).

    That flexible logic can't be reused as-is for a rigid-foam grade: it
    compares one bare property_name/target_value/actual_value triple
    against a hardcoded industry-tolerance table, with no concept of a
    spec's operator (<=/>=/=/between), method/condition/orientation/
    location context, or UAT-only production-release gating - all of which
    a GradeSpecification carries and wp3_conformance.compute_conformance_report
    already evaluates correctly per production run. This function is the
    aggregation step on top of that: one row per GradeSpecification that
    had at least one matched, complete result across the given set of
    production runs (typically every run made under a grade's current
    recipe version - see pages/15_Recipe_Optimization.py), with:

    - avg_actual: mean of the (already unit-converted, see
      resolve_actual_value) evaluated actual value across every Pass/Fail
      row for this spec.
    - achieved: "Yes"/"No" from evaluating that AVERAGE against the spec
      (same "judge the average, not the per-run pass count" convention as
      the flexible page's Achieved? column - see that page's own
      docstring for the 2026-08-02 fix this mirrors), or "—" if no run
      produced a comparable result at all.
    - n / n_fail: how many individual runs' results factored into the
      average and how many of those were a Fail (the rigid-foam
      equivalent of the flexible page's "Runs outside tolerance").
    - n_excluded_context / n_invalid / n_no_result: WP3's three
      "couldn't evaluate" buckets, counted separately so a caller can
      show *why* a spec has few or no comparable runs rather than just a
      silent gap - context the flexible achievement table has no
      equivalent of, since compute_pass_fail never excludes anything.
    - production_release: UAT_PASS_NO_RELEASE (see production_release_status)
      computed from the aggregate verdict, for a UAT-only grade/spec.

    Returns [] if production_run_ids is empty - nothing to aggregate.
    """
    if not production_run_ids:
        return []

    rows_by_spec = {}
    for run_id in production_run_ids:
        for row in compute_conformance_report(session, foam_grade_id, production_run_id=run_id):
            if row.get("spec_id") is None:
                continue
            rows_by_spec.setdefault(row["spec_id"], []).append(row)

    summary = []
    for spec_id, rows in rows_by_spec.items():
        spec = session.get(GradeSpecification, spec_id)
        verdicted = [r for r in rows if r["verdict"] in ("Pass", "Fail")]
        n = len(verdicted)
        n_fail = sum(1 for r in verdicted if r["verdict"] == "Fail")

        avg_actual = None
        achieved = "—"
        production_release = None
        if verdicted and spec is not None:
            avg_actual = sum(r["actual_value"] for r in verdicted) / n
            verdict, _margin = evaluate_specification(spec, avg_actual)
            achieved = {"Pass": "Yes", "Fail": "No"}.get(verdict, "—")
            is_uat_only = bool(spec.foam_grade and spec.foam_grade.status == "UAT_ONLY")
            production_release = production_release_status(verdict, is_uat_only)

        summary.append({
            "spec_id": spec_id,
            "property_name": spec.property_name if spec else rows[0]["property_name"],
            "unit": spec.unit if spec else None,
            "target_operator": spec.target_operator if spec else None,
            "target_value": spec.target_value if spec else None,
            "lower_limit": spec.lower_limit if spec else None,
            "upper_limit": spec.upper_limit if spec else None,
            "condition": spec.condition.name if spec is not None and spec.condition else None,
            "orientation": spec.orientation.name if spec is not None and spec.orientation else None,
            "location": spec.location.name if spec is not None and spec.location else None,
            "avg_actual": round(avg_actual, 4) if avg_actual is not None else None,
            "achieved": achieved,
            "n": n,
            "n_fail": n_fail,
            "n_excluded_context": sum(1 for r in rows if r["status"] == "EXCLUDED_CONTEXT"),
            "n_invalid": sum(1 for r in rows if r["status"] == "INVALID"),
            "n_no_result": sum(1 for r in rows if r["status"] == "NO_RESULT"),
            "production_release": production_release,
        })
    return summary


def rigid_actual_usage_dataframe(session, foam_grade_id):
    """WP4 (Converged Joint Implementation Plan, section 7.5) rigid-foam
    equivalent of analytics.actual_usage_dataframe: one row per (production
    run, raw-material component), that component's total actually-consumed
    mass for the run, re-expressed as a php-equivalent share of the run's
    own Base-polyol consumption - the same batch-size-normalizing
    convention the flexible app's version uses (a run's ingredient dosage
    is compared as a ratio to the recipe's own basis, not skewed by two
    runs simply being different total batch sizes).

    Sourced from RawMaterialLotUse.mass_kg (added WP4 - see db.py) rather
    than ComponentStreamReading.flow_total_qty, because rigid-foam
    discrete-shot production doesn't have a continuous Finalized-phase
    stream reading to draw from. A run can draw the same material from more
    than one supplier lot, so every row for a given (run, component_stream_
    name) is summed first - unlike the flexible source table, which has at
    most one reading per material per run.

    Runs with no RawMaterialLotUse.mass_kg recorded at all, or with no
    identifiable Base-polyol consumption to normalize against, are skipped
    rather than guessed at. Returns an empty DataFrame if nothing qualifies
    - as of this writing (2026-08-07) that will be EVERY call, since no
    page or CSV import in this app writes mass_kg yet (this function is the
    read side of a WP4 schema addition; a capture path - a form and/or CSV
    import analogous to the flexible app's Component Stream Reading import
    - is tracked separately, not part of this function's scope)."""
    runs = (
        session.query(ProductionRun)
        .options(joinedload(ProductionRun.recipe_version).joinedload(RecipeVersion.components))
        .filter(ProductionRun.foam_grade_id == foam_grade_id)
        .all()
    )
    run_ids = [r.id for r in runs]
    if not run_ids:
        return pd.DataFrame()

    lot_uses = (
        session.query(RawMaterialLotUse)
        .filter(RawMaterialLotUse.production_run_id.in_(run_ids), RawMaterialLotUse.mass_kg.isnot(None))
        .all()
    )
    mass_by_run = {}
    for lu in lot_uses:
        per_run = mass_by_run.setdefault(lu.production_run_id, {})
        per_run[lu.component_stream_name] = (per_run.get(lu.component_stream_name) or 0) + lu.mass_kg

    rows = []
    for run in runs:
        materials = mass_by_run.get(run.id)
        if not materials:
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
        polyol_mass = next(
            (mass for name, mass in materials.items() if name and name.strip().lower() == polyol_name), None
        )
        if not polyol_mass:
            continue
        for name, mass in materials.items():
            rows.append({
                "run_id": run.id,
                "foam_grade_id": run.foam_grade_id,
                "recipe_version_id": run.recipe_version_id,
                "component_stream_name": name,
                "mass_kg": mass,
                "actual_php_equivalent": round((mass / polyol_mass) * 100, 4),
            })
    return pd.DataFrame(rows)


def rank_lot_use_actual_correlations(session, foam_grade_id, spec_id, min_runs=3):
    """WP4 rigid-foam equivalent of analytics.rank_component_actual_correlations:
    for every raw-material component with metered RawMaterialLotUse.mass_kg
    readings for this grade, correlates its ACTUAL per-run php-equivalent
    dosage (see rigid_actual_usage_dataframe) against that same run's
    evaluated actual value for one specific GradeSpecification (from
    compute_conformance_report - already unit-converted and context-
    matched, see resolve_actual_value), ranked by |correlation| descending.

    Takes a spec_id (not a bare property_name like the flexible version)
    because a rigid-foam property can have more than one GradeSpecification
    distinguished by method/condition/orientation/location - correlating
    against "the property" without pinning down which spec's evaluated
    value to use would silently mix incomparable contexts.

    Needs real per-run variation to say anything: a material must have
    metered mass_kg paired with an evaluated result for at least min_runs
    production runs, or it's excluded rather than shown as a misleading
    correlation. Returns an empty DataFrame if nothing qualifies."""
    usage_df = rigid_actual_usage_dataframe(session, foam_grade_id)
    if usage_df.empty:
        return pd.DataFrame()

    run_ids = usage_df["run_id"].unique().tolist()
    actual_by_run = {}
    for run_id in run_ids:
        values = [
            row["actual_value"]
            for row in compute_conformance_report(session, foam_grade_id, production_run_id=run_id)
            if row.get("spec_id") == spec_id and row.get("actual_value") is not None
        ]
        if values:
            actual_by_run[run_id] = sum(values) / len(values)
    if not actual_by_run:
        return pd.DataFrame()
    per_run_result = pd.Series(actual_by_run)

    rows = []
    for material, sub in usage_df.groupby("component_stream_name"):
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


def compute_grade_conformance_summary(session, foam_grade_id):
    """Aggregate pass-rate analytics (the WP3 'Analytics' function, again
    computed live rather than persisted - see module docstring) across
    every production run recorded against this grade, grouped by
    property_name so a specific property's conformance trend is visible,
    not just one overall number.

    Covers production-run conformance only - CustomerTrial/OptimizationTrial
    rows aren't grade-scoped by a foam_grade_id column on those tables (see
    db.py), so pooling lab-trial data in requires the caller to pass
    explicit trial ids to compute_conformance_report directly. Production
    runs are what Gate 2's 10 UAT cases (task #550) actually exercise.
    """
    run_ids = [r.id for r in session.query(ProductionRun.id).filter(ProductionRun.foam_grade_id == foam_grade_id).all()]

    all_rows = []
    for run_id in run_ids:
        all_rows.extend(compute_conformance_report(session, foam_grade_id, production_run_id=run_id))

    buckets = {}
    for row in all_rows:
        if row["verdict"] is None:
            continue
        bucket = buckets.setdefault(row["property_name"], {"pass": 0, "fail": 0})
        bucket["pass" if row["verdict"] == "Pass" else "fail"] += 1

    summary = []
    for property_name, counts in buckets.items():
        total = counts["pass"] + counts["fail"]
        summary.append(
            {
                "property_name": property_name,
                "pass_count": counts["pass"],
                "fail_count": counts["fail"],
                "total_evaluated": total,
                "pass_rate_pct": round(100.0 * counts["pass"] / total, 1) if total else None,
            }
        )
    return summary
