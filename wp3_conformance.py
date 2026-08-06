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


def _specs_match_result(spec, result):
    """A GradeSpecification row applies to a PhysicalPropertyResult row when
    the property matches and, wherever the spec pins down a specific test
    condition/orientation/location, the result's own context matches it too.
    A spec that leaves one of those context fields blank applies regardless
    of the result's value for it (e.g. a density spec that doesn't care
    about orientation matches a result measured at any orientation) -
    deliberately permissive, since not every spec in the WP3 package
    constrains every context dimension."""
    if spec.property_definition_id and result.property_definition_id:
        if spec.property_definition_id != result.property_definition_id:
            return False
    elif (spec.property_name or "").strip().lower() != (result.property_name or "").strip().lower():
        return False

    if spec.condition_id and result.condition_id and spec.condition_id != result.condition_id:
        return False
    if spec.orientation_id and result.orientation_id and spec.orientation_id != result.orientation_id:
        return False
    if spec.location_id and result.location_id and spec.location_id != result.location_id:
        return False
    return True


def compute_conformance_report(
    session, foam_grade_id, production_run_id=None, customer_trial_id=None, optimization_trial_id=None
):
    """Assembles a live conformance report: every GradeSpecification for
    this grade, matched against the best available PhysicalPropertyResult
    recorded for the given run/trial, with a freshly computed verdict. This
    IS the WP3 "Conformance Evaluation" and the data behind the "Report"
    (Gate 2 items G2-06/G2-11) - returned as a list of dicts, not written
    anywhere (see module docstring).

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
        matches = [r for r in results if _specs_match_result(spec, r)]
        result = matches[0] if matches else None
        actual_value = result.actual_value if result else None
        verdict, margin = evaluate_specification(spec, actual_value) if result else (None, None)
        rows.append(
            {
                "spec_id": spec.id,
                "property_name": spec.property_name,
                "target_operator": spec.target_operator,
                "target_value": spec.target_value,
                "lower_limit": spec.lower_limit,
                "upper_limit": spec.upper_limit,
                "unit": spec.unit,
                "result_id": result.id if result else None,
                "actual_value": actual_value,
                "verdict": verdict,
                "margin": margin,
            }
        )
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
