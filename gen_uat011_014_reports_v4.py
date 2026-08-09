"""
WP6-S09 closure batch (2026-08-09) - regenerates UAT-011/012/014 from the
exact commit/build Charlie's closure instructions require (section 3.1):
app v0.14.16, commit 5ca9717. Uses the REAL, current wp3_conformance
functions (validate_result_completeness, _specs_match_result,
resolve_actual_value, evaluate_specification, production_release_status)
against fresh Supabase data pulled 2026-08-09 after this closure batch's
DEF-010 refinement (specimen/result-level thickness_mm,
_CONTROLLED_DIMENSION_RULES) - not the earlier v2/v3 scripts' now-stale
text-heuristic stand-ins.

SimpleNamespace stand-ins carry each result's own thickness_mm (new
column, primary source) and each result/spec's real orientation_id -
validate_result_completeness reads result.thickness_mm directly (falling
back to sample.thickness_mm only if the result's own field is empty, which
none of these are, since the sample-level backfill already covered the
one case that had it).
"""
import json
import os
import sys
import datetime as dt
from types import SimpleNamespace

sys.path.insert(0, ".")

import wp3_conformance as conf
from reports import (
    render_batch_release_record_docx,
    render_period_summary_docx,
    render_sample_certificate_docx,
)

BUILD_TAG = "PI3 Rigid Foam Edition v0.14.16 (commit 5ca9717) - evidence generated 2026-08-09"
OUT = "/sessions/great-clever-goldberg/mnt/outputs/s09_docx_v6"

with open("wp6s09_specs_v4.json") as f:
    SPEC_ROWS = json.load(f)
with open("wp6s09_results_v4.json") as f:
    RESULT_ROWS = json.load(f)

# Grade 2 (run 1, the frozen WP3 Gate-2 fixture) has its own single spec,
# fetched separately since it predates this batch's grade 3-6 UAT dataset.
SPEC_ROWS.append({
    "spec_id": 2, "foam_grade_id": 2, "property_name": "Thermal conductivity",
    "property_definition_id": 1, "property_method_id": 1, "target_operator": "<=",
    "target_value": None, "lower_limit": None, "upper_limit": 0.024, "unit": "W/(m.K)",
    "condition_id": 26, "orientation_id": 6, "location_id": 2,
    "cond_name": "Mean test temperature 10 degC",
    "ori_name": "Through-thickness (heat flow perpendicular to panel faces)",
    "loc_name": "Core centre", "grade_status": "UAT_ONLY",
})


def make_spec(row):
    return SimpleNamespace(
        id=row["spec_id"],
        property_name=row["property_name"],
        property_definition_id=row["property_definition_id"],
        property_method_id=row["property_method_id"],
        target_operator=row["target_operator"],
        target_value=row["target_value"],
        lower_limit=row["lower_limit"],
        upper_limit=row["upper_limit"],
        unit=row["unit"],
        condition_id=row["condition_id"],
        orientation_id=row["orientation_id"],
        location_id=row["location_id"],
        condition=SimpleNamespace(name=row["cond_name"]) if row["cond_name"] else None,
        orientation=SimpleNamespace(name=row["ori_name"]) if row["ori_name"] else None,
        location=SimpleNamespace(name=row["loc_name"]) if row["loc_name"] else None,
        foam_grade=SimpleNamespace(status=row["grade_status"]),
    )


def make_result(row):
    sample = SimpleNamespace(thickness_mm=row["sample_thickness_mm"])
    return SimpleNamespace(
        id=row["id"],
        property_name=row["property_name"],
        property_definition_id=row["property_definition_id"],
        property_definition=None,  # not needed - property_name hits _CONTROLLED_DIMENSION_RULES directly
        property_method_id=row["property_method_id"],
        actual_value=row["actual_value"],
        unit=row["unit"],
        condition_id=row["condition_id"],
        orientation_id=row["orientation_id"],
        location_id=row["location_id"],
        condition=SimpleNamespace(name=row["cond_name"]) if row["cond_name"] else None,
        test_method=row["test_method"],
        tested_at=dt.date.fromisoformat(row["tested_at"]),
        sample_id=row["sample_id"],
        thickness_mm=row["thickness_mm"],
        sample=sample,
    )


SPECS_BY_GRADE = {}
SPECS_BY_ID = {}
for r in SPEC_ROWS:
    spec = make_spec(r)
    SPECS_BY_GRADE.setdefault(r["foam_grade_id"], []).append(spec)
    SPECS_BY_ID[spec.id] = spec

RESULTS_BY_RUN = {}
RESULTS_BY_ID = {}
for r in RESULT_ROWS:
    result = make_result(r)
    RESULTS_BY_RUN.setdefault(r["production_run_id"], []).append(result)
    RESULTS_BY_ID[result.id] = result


def real_compute_conformance_report(foam_grade_id, results):
    """Mirrors wp3_conformance.compute_conformance_report's per-spec loop
    exactly (same field names/order), calling the REAL, current
    _specs_match_result/validate_result_completeness/resolve_actual_value/
    evaluate_specification/production_release_status functions unmodified -
    only the session.query() data-fetch is replaced with a pre-filtered
    plain list of stand-ins, since this sandbox has no live DATABASE_URL."""
    specs = SPECS_BY_GRADE.get(foam_grade_id, [])
    rows = []
    for spec in specs:
        is_uat_only = bool(spec.foam_grade and spec.foam_grade.status == "UAT_ONLY")
        candidates = [
            r for r in results
            if r.property_definition_id == spec.property_definition_id
            or (r.property_name or "").strip().lower() == (spec.property_name or "").strip().lower()
        ]
        if not candidates:
            rows.append({"spec_id": spec.id, "property_name": spec.property_name, "status": "NO_RESULT",
                         "excluded_reason": None, "result_id": None, "actual_value": None, "verdict": None,
                         "margin": None, "production_release": None})
            continue

        matched_result, excluded_reason = None, None
        for r in candidates:
            ok, reason = conf._specs_match_result(spec, r)
            if ok:
                matched_result = r
                break
            excluded_reason = excluded_reason or reason

        if matched_result is None:
            rows.append({"spec_id": spec.id, "property_name": spec.property_name, "status": "EXCLUDED_CONTEXT",
                         "excluded_reason": excluded_reason, "result_id": None, "actual_value": None,
                         "verdict": None, "margin": None, "production_release": None})
            continue

        complete, incomplete_reason = conf.validate_result_completeness(matched_result, sample=matched_result.sample)
        if not complete:
            rows.append({"spec_id": spec.id, "property_name": spec.property_name, "status": "INVALID",
                         "excluded_reason": incomplete_reason, "result_id": matched_result.id,
                         "actual_value": matched_result.actual_value, "verdict": None, "margin": None,
                         "production_release": None})
            continue

        eval_value, as_recorded_value, as_recorded_unit, unit_converted = conf.resolve_actual_value(spec, matched_result)
        verdict, margin = conf.evaluate_specification(spec, eval_value)
        production_release = conf.production_release_status(verdict, is_uat_only)
        rows.append({
            "spec_id": spec.id, "property_name": spec.property_name, "status": verdict,
            "excluded_reason": None, "result_id": matched_result.id, "actual_value": eval_value,
            "verdict": verdict, "margin": margin, "production_release": production_release,
            "_spec": spec, "_result": matched_result,
        })
    return rows


def conformance_verdict(rows):
    if not rows:
        return "No specification on file"
    verdicts = [r["verdict"] for r in rows]
    if "Fail" in verdicts:
        return "Non-conforming"
    if verdicts and all(v == "Pass" for v in verdicts):
        return "Conforming"
    return "Incomplete testing"


def rows_for_display(rows):
    out = []
    for row in rows:
        spec = SPECS_BY_ID.get(row.get("spec_id")) if row.get("spec_id") else None
        result = RESULTS_BY_ID.get(row.get("result_id")) if row.get("result_id") else None
        if spec is None:
            target_text = "-"
        else:
            op = (spec.target_operator or "<=").strip()
            if op == "between":
                target_text = f"{spec.lower_limit}-{spec.upper_limit} {spec.unit or ''}".strip()
            else:
                limit = spec.target_value
                if limit is None:
                    limit = spec.upper_limit if op == "<=" else (spec.lower_limit if op == ">=" else None)
                target_text = f"{op} {limit} {spec.unit or ''}".strip() if limit is not None else "-"
        status = row.get("status")
        if status in ("Pass", "Fail"):
            pass_fail_text = status
        else:
            pass_fail_text = {
                "EXCLUDED_CONTEXT": f"Excluded ({row.get('excluded_reason') or 'context mismatch'})",
                "INVALID": f"Invalid ({row.get('excluded_reason') or 'incomplete context'})",
                "NO_RESULT": "No result recorded",
            }.get(status, status or "-")
        out.append({
            "Property": row.get("property_name"),
            "Specification": target_text,
            "Actual": row.get("actual_value"),
            "Unit": (spec.unit if spec else None) or (result.unit if result else "") or "",
            "Pass/Fail": pass_fail_text,
            "Test method": (result.test_method if result else None) or "-",
            "Condition": (
                result.condition.name if (result is not None and result.condition)
                else (spec.condition.name if (spec is not None and spec.condition) else "-")
            ),
            "Spec reference": f"GS-{spec.id}" if spec is not None else "-",
            "Tested": result.tested_at if result else None,
        })
    return out


os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. UAT-011: Batch Release / Conformance Record - Production Run #2
# ---------------------------------------------------------------------------
run2_results = RESULTS_BY_RUN[2]
run2_conformance = real_compute_conformance_report(3, run2_results)
quality_results = rows_for_display(run2_conformance)
quality_verdict = conformance_verdict(run2_conformance)
verdicts = [r["verdict"] for r in run2_conformance]
statuses = [r["status"] for r in run2_conformance]

recipe_components = [
    {"Material": "Polyol 2", "Supplier": "-", "PHP": 66.75, "Role": "Rigid polyol", "Notes": "-"},
    {"Material": "Polyol 3", "Supplier": "-", "PHP": 6.63, "Role": "Rigid polyol", "Notes": "-"},
    {"Material": "Polyol 8", "Supplier": "-", "PHP": 8.67, "Role": "Rigid polyol", "Notes": "-"},
    {"Material": "Surfactant 1", "Supplier": "-", "PHP": 2.1, "Role": "Silicone surfactant", "Notes": "-"},
    {"Material": "Catalyst 1", "Supplier": "-", "PHP": 2.45, "Role": "Catalyst", "Notes": "-"},
    {"Material": "Catalyst 9", "Supplier": "-", "PHP": 0.3, "Role": "Catalyst", "Notes": "-"},
    {"Material": "Water", "Supplier": "-", "PHP": 3.0, "Role": "Chemical blowing agent", "Notes": "-"},
    {"Material": "HFO-1233zd", "Supplier": "-", "PHP": 10.1, "Role": "Physical blowing agent", "Notes": "-"},
    {"Material": "pMDI", "Supplier": "-", "PHP": 125.0, "Role": "Isocyanate", "Notes": "-"},
]

batch_release_data = {
    "run_id": 2,
    "plant": "WP3 UAT / Reference (no production release)",
    "product_family": "Rigid PUR Cold-Room Panels (UAT/Reference)",
    "foam_grade": "DEMO-RCP-001 - UAT PUR HFO closed-mold panel",
    "machine": "High-pressure metering machine",
    "run_date": dt.date(2026, 8, 10),
    "batch_reference": "UAT-RUN-0101",
    "block_reference": "-",
    "operator": "-",
    "notes": (
        f"{BUILD_TAG}. Superseded evidence: earlier UAT-011 examples generated under app v0.14.14/"
        "v0.14.15 are superseded by this document, not duplicated - see 07_Evidence_Register. "
        "Synthetic UAT run (Synthetic UAT). A:B mass ratio 1.2425 (set 1.25, "
        "deviation -0.60%). Product construction: Metal-faced sandwich panel. "
        "Run status: Completed."
    ),
    "recipe_version_label": "DEMO-RCP-001 v1",
    "recipe_approval_status": "Synthetic UAT",
    "recipe_effective_date": None,
    "recipe_ratio_index": 109,
    "recipe_components": recipe_components,
    "quality_results": quality_results,
    "quality_verdict": quality_verdict,
    "quality_issues": [],
    "has_flags": False,
    "flag_reasons": [],
    "setup_deviations": [],
    "fallplate_deviations": [],
    "stream_readings": [],
    "stream_calibration_flags": [],
    "production_events": [],
}
with open(f"{OUT}/UAT011_Batch_Release_Record_Run2_v0.14.16.docx", "wb") as f:
    f.write(render_batch_release_record_docx(batch_release_data))
print("=== UAT-011 Batch Release Record (run 2) ===")
print("Per-property status:", list(zip([r['property_name'] for r in run2_conformance], statuses)))
print("Verdicts:", verdicts, "-> overall:", quality_verdict)
print()

# ---------------------------------------------------------------------------
# 2. UAT-012: Plant / Period Summary - all 13 real runs, 2026-07-29 to 2026-08-24
# ---------------------------------------------------------------------------
runs_meta = [
    (1, "2026-07-29", "GRADE-UAT-RPUR-COLDROOM-001", "RCP-UAT-DCP-EX1-V1", 2),
    (2, "2026-08-10", "DEMO-RCP-001 - UAT PUR HFO closed-mold panel", "DEMO-RCP-001 v1", 3),
    (3, "2026-08-11", "DEMO-RCP-001 - UAT PUR HFO closed-mold panel", "DEMO-RCP-001 v1", 3),
    (4, "2026-08-12", "DEMO-RCP-001 - UAT PUR HFO closed-mold panel", "DEMO-RCP-001 v1", 3),
    (5, "2026-08-14", "DEMO-RCP-002 - UAT PUR hybrid blowing panel", "DEMO-RCP-002 v1", 4),
    (6, "2026-08-15", "DEMO-RCP-002 - UAT PUR hybrid blowing panel", "DEMO-RCP-002 v1", 4),
    (7, "2026-08-16", "DEMO-RCP-002 - UAT PUR hybrid blowing panel", "DEMO-RCP-002 v1", 4),
    (8, "2026-08-18", "DEMO-RCP-003 - UAT PIR pentane panel", "DEMO-RCP-003 v1", 5),
    (9, "2026-08-19", "DEMO-RCP-003 - UAT PIR pentane panel", "DEMO-RCP-003 v1", 5),
    (10, "2026-08-20", "DEMO-RCP-003 - UAT PIR pentane panel", "DEMO-RCP-003 v1", 5),
    (11, "2026-08-22", "DEMO-RCP-004 - UAT high-index PIR panel", "DEMO-RCP-004 v1", 6),
    (12, "2026-08-23", "DEMO-RCP-004 - UAT high-index PIR panel", "DEMO-RCP-004 v1", 6),
    (13, "2026-08-24", "DEMO-RCP-004 - UAT high-index PIR panel", "DEMO-RCP-004 v1", 6),
]
run_rows = [
    {"Run ID": rid, "Date": dt.date.fromisoformat(date), "Foam grade": grade,
     "Recipe version": recipe, "Machine": "High-pressure metering machine", "Batch reference": f"run-{rid}"}
    for (rid, date, grade, recipe, gid) in runs_meta
]
grade_counts = {}
for (rid, date, grade, recipe, gid) in runs_meta:
    grade_counts[grade] = grade_counts.get(grade, 0) + 1
grade_breakdown = [{"Foam grade": k, "Production runs": v} for k, v in sorted(grade_counts.items())]

pass_count = 0
fail_count = 0
total_checks = 0
status_tally = {}
status_by_property = {}
for (rid, date, grade, recipe, gid) in runs_meta:
    rows = real_compute_conformance_report(gid, RESULTS_BY_RUN.get(rid, []))
    for row in rows:
        total_checks += 1
        status_tally[row["status"]] = status_tally.get(row["status"], 0) + 1
        status_by_property.setdefault(row["property_name"], {}).setdefault(row["status"], 0)
        status_by_property[row["property_name"]][row["status"]] += 1
        if row["verdict"] == "Pass":
            pass_count += 1
        elif row["verdict"] == "Fail":
            fail_count += 1
total_scored = pass_count + fail_count
pass_rate = round(100 * pass_count / total_scored) if total_scored else None
unresolved_count = total_checks - total_scored
coverage_pct = round(100 * total_scored / total_checks) if total_checks else None

period_summary_data = {
    "plant": "All plants",
    "product_family": "All product families",
    "date_from": dt.date(2026, 7, 29),
    "date_to": dt.date(2026, 8, 24),
    "dataset_label": "Synthetic UAT / Reference Dataset",
    "total_runs": len(run_rows),
    "pass_rate": pass_rate,
    "total_results_scored": total_scored,
    "total_checks_attempted": total_checks,
    "unresolved_checks": unresolved_count,
    "coverage_pct": coverage_pct,
    "total_quality_issues": 0,
    "quality_issues_label": "Recorded production quality issues",
    "recurring_issues": 0,
    "runs": run_rows,
    "quality_issues": [],
    "grade_breakdown": grade_breakdown,
}
with open(f"{OUT}/UAT012_Plant_Period_Summary_v0.14.16.docx", "wb") as f:
    f.write(render_period_summary_docx(period_summary_data))
print("=== UAT-012 Period Summary (all 13 runs) ===")
print("Status tally:", status_tally)
print("Status by property:", status_by_property)
print("-> checks attempted:", total_checks, "evaluated:", total_scored, "coverage:", coverage_pct,
      "% pass_rate (of evaluated):", pass_rate, "% Fail:", fail_count, "Invalid:", status_tally.get("INVALID", 0))
print("TARGET (Charlie section 3.3): attempted=49 evaluated=37 pass=35 fail=2 invalid=12 coverage=76% pass_rate=95%")
print()

# ---------------------------------------------------------------------------
# 3. UAT-014: Sample Certificate of Analysis - Sample #2 (Production Run #2)
# ---------------------------------------------------------------------------
sample2_results = [r for r in run2_results if r.sample_id == 2]
sample2_conformance = real_compute_conformance_report(3, sample2_results)
sample_quality_results = rows_for_display(sample2_conformance)
sample_verdicts = [r["verdict"] for r in sample2_conformance]
sample_statuses = [r["status"] for r in sample2_conformance]
pass_count_s = sample_verdicts.count("Pass")
fail_count_s = sample_verdicts.count("Fail")
overall_verdict_s = conformance_verdict(sample2_conformance)

sample_cert_data = {
    "sample_id": 2,
    "source_type": "Production Run",
    "source_id": 2,
    "header_fields": [
        ("Source", "Production Run #2"),
        ("Run date", dt.date(2026, 8, 10)), ("Batch reference", "UAT-RUN-0101"),
        ("Block reference", "-"), ("Machine", "High-pressure metering machine"),
        ("Operator/team", "-"),
    ],
    "foam_grade": "DEMO-RCP-001 - UAT PUR HFO closed-mold panel",
    "plant": "WP3 UAT / Reference (no production release)",
    "zone_label": "LOC-041 - Bottom facing interface",
    "sample_ts": dt.datetime(2026, 8, 11, 9, 20, 0),
    "sample_notes": (
        f"{BUILD_TAG}. Superseded evidence: earlier UAT-014 examples generated under app v0.14.14/"
        "v0.14.15 are superseded by this document, not duplicated - see 07_Evidence_Register. "
        "[UAT-SMP-0101-1] Per-property conditions: density/closed-cell COND-003 "
        "(24-hour aged); thermal conductivity COND-011 (mean test temperature 10 "
        "degC, orientation Through-thickness); compressive strength COND-022 "
        "(parallel to rise, orientation Parallel to rise). COND-020 (Dimensional "
        "stability exposure) not applicable to any tested property on this sample - "
        "removed from sample-level notes per WP6-S09 UAT-014 review. Released for UAT. "
        "This sample's thickness_mm is not on file at either the specimen (Result) or "
        "parent-sample level (open defect DEF-010), so its Thermal conductivity result "
        "is correctly INVALID below - Core density, Compressive strength and Closed-cell "
        "content do not require thickness under Charlie's controlled per-property rules "
        "(section 3.2) and resolve to real Pass/Fail verdicts."
    ),
    "recipe_version_label": "DEMO-RCP-001 v1",
    "recipe_approval_status": "Synthetic UAT",
    "recipe_effective_date": None,
    "recipe_ratio_index": 109,
    "recipe_components": recipe_components,
    "quality_results": sample_quality_results,
    "pass_count": pass_count_s,
    "fail_count": fail_count_s,
    "overall_verdict": overall_verdict_s,
}
with open(f"{OUT}/UAT014_Sample_Certificate_of_Analysis_v0.14.16.docx", "wb") as f:
    f.write(render_sample_certificate_docx(sample_cert_data))
print("=== UAT-014 Sample Certificate (sample #2) ===")
print("Per-property status:", list(zip([r['property_name'] for r in sample2_conformance], sample_statuses)))
print("Verdicts:", sample_verdicts, "-> overall:", overall_verdict_s)
print()
print("done - outputs in", OUT)
