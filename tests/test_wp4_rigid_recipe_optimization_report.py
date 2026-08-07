"""WP4 (Converged Joint Implementation Plan, section 7.5) tests for
reports.build_rigid_recipe_optimization_report_data() - the rigid-foam
equivalent of build_recipe_optimization_report_data(), wired into
pages/15_Recipe_Optimization.py's "Recipe Optimization Report" section for
a rigid-foam grade (task #561). Exercises the data assembly directly
(achieved/not-achieved counts, operator-aware deviation-from-target %,
UAT-only production-release note, empty-input handling) plus a real
end-to-end DOCX render through the REUSED render_recipe_optimization_report_
docx() function, to confirm a rigid-shaped data dict renders through the
same renderer the flexible branch uses without any renderer-side change.

Uses an in-memory grade/recipe-version/cost object rather than a full DB
seed - build_rigid_recipe_optimization_report_data() only reads attributes
off the objects it's handed (grade.grade_name, grade.product_family, etc.)
and the achievement_summary/actual_ranked data the page already computed
elsewhere (compute_grade_achievement_summary/rank_lot_use_actual_correlations
- both already covered by their own WP4 test files), so no database is
needed here.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pandas as pd

import reports


class _FakeComponent:
    def __init__(self):
        pass


class _FakeVersion:
    def __init__(self, label="v1", status="Draft", n_components=2):
        self.version_label = label
        self.approval_status = status
        self.components = [_FakeComponent() for _ in range(n_components)]


class _FakeGrade:
    def __init__(self, name="RF-COLD-01"):
        self.grade_name = name
        self.product_family = None


def _achievement_row(**overrides):
    row = {
        "spec_id": 1,
        "property_name": "Thermal conductivity",
        "unit": "W/(m.K)",
        "target_operator": "<=",
        "target_value": 0.030,
        "lower_limit": None,
        "upper_limit": None,
        "condition": "Initial, 10C mean, 7 days",
        "orientation": "Through-thickness",
        "location": "Core",
        "avg_actual": 0.027,
        "achieved": "Yes",
        "n": 4,
        "n_fail": 0,
        "n_excluded_context": 0,
        "n_invalid": 0,
        "n_no_result": 0,
        "production_release": None,
    }
    row.update(overrides)
    return row


def _cost(total_cost=250.0, total_php=100.0, priced_php=100.0, missing=None):
    return {
        "total_cost": total_cost, "total_php": total_php,
        "priced_php": priced_php, "missing": missing or [], "complete": not missing,
    }


def test_build_rigid_report_counts_achieved_and_computes_deviation():
    grade, version = _FakeGrade(), _FakeVersion()
    achievement_summary = [
        _achievement_row(spec_id=1, property_name="Thermal conductivity", achieved="Yes",
                          avg_actual=0.027, target_value=0.030, target_operator="<="),
        _achievement_row(spec_id=2, property_name="Compressive strength", achieved="No",
                          avg_actual=90.0, target_value=100.0, target_operator=">=", unit="kPa"),
    ]
    data = reports.build_rigid_recipe_optimization_report_data(
        session=None, grade=grade, current_version=version, current_cost=_cost(),
        achievement_summary=achievement_summary, corr_property="Compressive strength",
        actual_ranked=pd.DataFrame(), include_trials=True,
    )
    assert len(data["expectation_rows"]) == 2
    assert data["expectation_rows"][0]["Achieved?"] == "Yes"
    assert data["expectation_rows"][1]["Achieved?"] == "No"
    # include_trials is always reported False for rigid regardless of what
    # the page's toggle was set to (see the function's own docstring) -
    # the achievement summary is always production-run-only.
    assert data["include_trials"] is False
    assert "1 of 2 tracked specifications are achieved" in data["conclusions"][0]
    # Thermal conductivity: (0.027-0.030)/0.030*100 = -10.0%; Compressive: (90-100)/100*100 = -10.0%
    assert data["deviation_categories"] == ["Thermal conductivity", "Compressive strength"]
    assert data["deviation_values"] == [-10.0, -10.0]


def test_build_rigid_report_skips_deviation_for_between_operator():
    grade, version = _FakeGrade(), _FakeVersion()
    achievement_summary = [
        _achievement_row(target_operator="between", lower_limit=20.0, upper_limit=30.0, target_value=None),
    ]
    data = reports.build_rigid_recipe_optimization_report_data(
        session=None, grade=grade, current_version=version, current_cost=_cost(),
        achievement_summary=achievement_summary, corr_property="Thermal conductivity",
        actual_ranked=pd.DataFrame(), include_trials=False,
    )
    assert data["deviation_categories"] == []
    assert data["expectation_rows"][0]["Limit / target"] == "20.0 – 30.0 W/(m.K)"


def test_build_rigid_report_flags_uat_only_production_release():
    grade, version = _FakeGrade(), _FakeVersion()
    achievement_summary = [
        _achievement_row(property_name="Thermal conductivity", achieved="Yes",
                          production_release="UAT_PASS_NO_RELEASE"),
    ]
    data = reports.build_rigid_recipe_optimization_report_data(
        session=None, grade=grade, current_version=version, current_cost=_cost(),
        achievement_summary=achievement_summary, corr_property="Thermal conductivity",
        actual_ranked=pd.DataFrame(), include_trials=False,
    )
    release_lines = [c for c in data["conclusions"] if "not yet cleared for production release" in c]
    assert len(release_lines) == 1
    assert "Thermal conductivity" in release_lines[0]


def test_build_rigid_report_handles_empty_achievement_summary():
    grade, version = _FakeGrade(), _FakeVersion()
    data = reports.build_rigid_recipe_optimization_report_data(
        session=None, grade=grade, current_version=version, current_cost=_cost(total_cost=None, total_php=None),
        achievement_summary=[], corr_property=None, actual_ranked=pd.DataFrame(), include_trials=False,
    )
    assert data["expectation_rows"] == []
    assert "No specifications recorded" in data["conclusions"][0]
    assert data["cost_per_kg"] is None


def test_build_rigid_report_correlation_rows_and_docx_renders():
    grade, version = _FakeGrade(), _FakeVersion()
    achievement_summary = [_achievement_row()]
    actual_ranked = pd.DataFrame([
        {"raw_material_name": "Flame Retardant X", "n_runs": 4, "correlation": 0.97},
        {"raw_material_name": "Polyol A", "n_runs": 4, "correlation": 0.12},
    ])
    data = reports.build_rigid_recipe_optimization_report_data(
        session=None, grade=grade, current_version=version, current_cost=_cost(),
        achievement_summary=achievement_summary, corr_property="Thermal conductivity",
        actual_ranked=actual_ranked, include_trials=False,
    )
    assert len(data["correlation_rows"]) == 2
    assert "Flame Retardant X" in data["conclusions"][1]

    # Reused, unmodified renderer - confirms a rigid-shaped data dict
    # produces a real DOCX (a zip archive - PK magic bytes) with no
    # rigid-specific branch needed in the renderer itself.
    docx_bytes = reports.render_recipe_optimization_report_docx(data)
    assert docx_bytes[:2] == b"PK"
    assert len(docx_bytes) > 1000
