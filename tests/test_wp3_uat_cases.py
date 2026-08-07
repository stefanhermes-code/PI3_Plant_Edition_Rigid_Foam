"""WP3 Gate 2 - the 10 UAT test cases from Charlie's
PI3_Rigid_Foam_Edition_WP3_Thermal_Conductivity_Vertical_Slice_Technical_
Package.xlsx, sheet "19_UAT_Test_Cases", run verbatim (same Test_Case_ID,
same inputs, same Expected_Result column) against wp3_conformance.py's live
conformance logic (Gate 2 items G2-09/G2-10).

Uses lightweight stand-ins (SimpleNamespace) instead of real ORM rows/a
live database - the sandbox this was developed in has no DATABASE_URL (see
README.md's migration-procedure section), and these 10 cases are pure
evaluation-logic tests: they exercise evaluate_specification(),
_specs_match_result(), validate_result_completeness(), and
production_release_status() directly, not database I/O (that's already
proven separately by tests/test_schema_migration.py and the disposable-
schema pass run against the real Supabase server for WP0/WP3). Controlled
IDs (e.g. "PROP-005") are used directly as the stand-ins' id fields, since
the matching logic only ever compares these fields for equality - it
doesn't care whether the underlying type is an int primary key or a
controlled-ID string.

Usage: python tests/test_wp3_uat_cases.py

FROZEN GATE 2 RECORD - read before "fixing" a failure here (2026-08-07):
This file is preserved exactly as it was when Gate 2 (Converged Joint
Implementation Plan, section 7.4, acceptance items A1-A10) was signed off
by Stefan. It is NOT re-run as a WP4 regression gate and its CASES/
expectations are deliberately left untouched, including UAT-06.

UAT-06 ("wrong unit, conversion deferred") will now report a MISMATCH if
this script is run: WP4 (see unit_conversion.py and
wp3_conformance.resolve_actual_value) closes exactly the gap this case's
own name flags as deferred - a spec/result pair in mW/(m.K) vs W/(m.K) is
now recognized as convertible and evaluated (23 mW/(m.K) converts to
0.023 W/(m.K), which passes the 0.024 upper limit), not excluded. This is
the intended, planned WP4 behavior change, not a regression - see
tests/test_wp4_unit_conversion.py for the current, correct expectation for
this exact scenario, evaluated against the real (non-stand-in)
wp3_conformance.compute_conformance_report. The other 9 cases are
unaffected (none of them involve a unit mismatch) and still match.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wp3_conformance as conf

# The one real WP3 grade specification (WP2 Implementation Slice 1, sheet
# 09_Grade_Specifications / WP3 package sheet 08_Product_Grade): a UAT-only
# maximum-limit spec for initial thermal conductivity.
SPEC = SimpleNamespace(
    property_definition_id="PROP-005",
    property_name="Thermal conductivity",
    property_method_id="MTH-016",
    condition_id="CTX-THERM-INIT-10C-7D",
    orientation_id="ORI-THERM-THROUGH-THICKNESS",
    location_id=None,  # spec doesn't pin a single location - core-only scope covers both LOC-021/LOC-030
    unit="W/(m.K)",
    target_operator="<=",
    target_value=0.024,
    lower_limit=None,
    upper_limit=0.024,
    foam_grade=SimpleNamespace(status="UAT_ONLY"),
)


def _result(measured_value, property_id="PROP-005", method_id="MTH-016", uom="W/(m.K)",
            condition_id="CTX-THERM-INIT-10C-7D", thickness_mm=60, orientation_id="ORI-THERM-THROUGH-THICKNESS",
            location_id=None):
    sample = SimpleNamespace(thickness_mm=thickness_mm)
    return SimpleNamespace(
        property_definition_id=property_id,
        property_name="Thermal conductivity",
        property_method_id=method_id,
        condition_id=condition_id,
        orientation_id=orientation_id,
        location_id=location_id,
        unit=uom,
        actual_value=measured_value,
        sample=sample,
    )


def _evaluate_case(result):
    """Mirrors compute_conformance_report's per-spec logic (db.py-free), so
    each UAT case exercises the exact same decision path the real
    Supabase-backed code path uses.

    Returns a dict with BOTH the conformance verdict/exclusion status AND
    the separate production-release status, because the workbook's
    Expected_Result column encodes two different questions depending on
    the scenario: "did it pass its functional limit" (UAT-01/02/03, etc.)
    vs. "can this UAT-only pass be used to release production" (UAT-10,
    same measured value as UAT-01, different question). Both can be true
    of the same row at once - compute_conformance_report's real return
    value already carries both fields side by side for exactly this
    reason, not as alternatives."""
    ok, reason = conf._specs_match_result(SPEC, result)
    if not ok:
        return {"status": "EXCLUDED_CONTEXT", "reason": reason, "production_release": None}
    complete, incomplete_reason = conf.validate_result_completeness(result, sample=result.sample)
    if not complete:
        return {"status": "INVALID", "reason": incomplete_reason, "production_release": None}
    verdict, margin = conf.evaluate_specification(SPEC, result.actual_value)
    release = conf.production_release_status(verdict, is_uat_only=SPEC.foam_grade.status == "UAT_ONLY")
    status = {"Pass": "PASS", "Fail": "FAIL"}.get(verdict, verdict)
    return {"status": status, "reason": None, "production_release": release}



# (test_case_id, scenario, result, expected_field, expected_value) - expected_field
# is "status" for every case except UAT-10, which asks the separate
# production-release question against the exact same measured value as UAT-01.
CASES = [
    ("UAT-01", "Valid pass", _result(0.023), "status", "PASS"),
    ("UAT-02", "Boundary pass", _result(0.024), "status", "PASS"),
    ("UAT-03", "Above-limit fail", _result(0.0241), "status", "FAIL"),
    ("UAT-04", "Wrong condition", _result(0.023, condition_id="CTX-THERM-INIT-15C-7D"), "status", "EXCLUDED_CONTEXT"),
    ("UAT-05", "Wrong method", _result(0.023, method_id="MTH-017"), "status", "EXCLUDED_CONTEXT"),
    ("UAT-06", "Wrong unit, conversion deferred", _result(23, uom="mW/(m.K)"), "status", "EXCLUDED_CONTEXT"),
    ("UAT-07", "Missing thickness", _result(0.023, thickness_mm=None), "status", "INVALID"),
    ("UAT-08", "Missing orientation", _result(0.023, orientation_id=None), "status", "INVALID"),
    ("UAT-09", "Patent benchmark excluded",
     _result(0.0201, property_id="PROP-005", method_id="MTH-EN12667", condition_id="CTX-PAT-UNKNOWN-AGE",
             orientation_id="ORI-UNKNOWN"), "status", "EXCLUDED_CONTEXT"),
    ("UAT-10", "UAT status blocks production release", _result(0.023), "production_release", "UAT_PASS_NO_RELEASE"),
]


def run():
    all_ok = True
    for case_id, scenario, result, expected_field, expected in CASES:
        outcome = _evaluate_case(result)
        actual = outcome[expected_field]
        ok = actual == expected
        all_ok = all_ok and ok
        result_label = "PASS" if ok else "FAIL - MISMATCH"
        detail = f" ({outcome['reason']})" if outcome["reason"] else ""
        print(f"[{case_id}] {scenario}: expected {expected_field}={expected} actual={actual}{detail} -> {result_label}")
    return all_ok


if __name__ == "__main__":
    ok = run()
    if ok:
        print("\nALL 10 WP3 UAT TEST CASES PASSED")
        sys.exit(0)
    else:
        print("\nWP3 UAT TEST CASES FAILED")
        sys.exit(1)
