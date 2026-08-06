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

from db import (
    CustomerTrial,
    GradeSpecification,
    OptimizationTrial,
    PhysicalPropertyResult,
    ProductionRun,
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
    """
    if actual_value is None:
        return None, None

    op = (spec.target_operator or "<=").strip()

    if op == "<=":
        if spec.target_value is None:
            return None, None
        margin = spec.target_value - actual_value
        return ("Pass" if actual_value <= spec.target_value else "Fail"), margin

    if op == ">=":
        if spec.target_value is None:
            return None, None
        margin = actual_value - spec.target_value
        return ("Pass" if actual_value >= spec.target_value else "Fail"), margin

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
    resolved through a UOM-ID cross-reference - deliberately simple: UAT
    case 06 ("wrong unit, conversion deferred") explicitly defers any
    unit-conversion logic to WP4, so WP3 only needs to recognize a mismatched
    unit as an excluded context, not convert it.
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
        return False, "unit mismatch (conversion deferred to WP4)"
    return True, None


def validate_result_completeness(result, sample=None):
    """Checks that a PhysicalPropertyResult carries the minimum context a
    direction-sensitive, thickness-sensitive property like thermal
    conductivity needs before it can be evaluated at all - Gate 2 item
    G2-10 / WP3 UAT cases 07 and 08 ("missing thickness" / "missing
    orientation" both expect INVALID, not a computed verdict).

    thickness_mm lives on the linked Sample (see db.py's Sample model), not
    on PhysicalPropertyResult itself, so pass the Sample row (or None if
    unavailable) - a result with no thickness on file is exactly this case.

    Returns (True, None) if complete, or (False, reason) naming the first
    missing field."""
    if result.orientation_id is None:
        return False, "missing orientation"
    thickness = sample.thickness_mm if sample is not None else None
    if thickness is None:
        return False, "missing thickness"
    return True, None


def compute_conformance_report(
    session, foam_grade_id, production_run_id=None, customer_trial_id=None, optimization_trial_id=None
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
                "production_release": None,
            })
            continue

        verdict, margin = evaluate_specification(spec, matched_result.actual_value)
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
            "actual_value": matched_result.actual_value,
            "verdict": verdict,
            "margin": margin,
            "production_release": production_release,
        })
    return rows


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
