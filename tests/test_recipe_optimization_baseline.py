"""WP4 (Converged Joint Implementation Plan, section 7.5) baseline
regression tests for the flexible-foam Recipe Optimization achievement/
correlation logic - written BEFORE any WP4 refactor, per the plan's own
"regression tests for flexible-foam behaviour that remains in shared code"
deliverable and Stefan's 2026-08-07 direction to lock this down first since
there was previously zero coverage here.

Covers:
- quality_standards.compute_pass_fail() / tolerance_label() - pure logic,
  both tolerance modes (absolute/relative) plus the unpublished-property
  fallback band and the "nothing to compare" None case.
- analytics.property_results_dataframe() - one flexible-foam-shaped grade,
  confirms live-recomputed pass_fail matches quality_standards directly
  (not a stored/stale value) for both a Pass and a Fail row.
- analytics.rank_component_actual_correlations() - a flexible-foam-shaped
  grade with 4 production runs, metered Finalized-phase stream readings,
  and a deliberately perfectly-correlated outcome, confirming: the
  material is found and ranked, correlation sign/magnitude is correct,
  and a material below min_runs is excluded rather than shown.
- A rigid-foam-shaped grade (chemistry_id populated, no
  FoamGradeTargetProperty/ComponentStreamReading data) returns empty
  DataFrames from both functions rather than raising - the "silently does
  nothing useful for rigid grades yet" behavior WP4 is meant to replace,
  captured here so the replacement is a deliberate change, not an
  accidental regression in what happens today.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")  # in-memory, isolated per test run

import pytest

import db
import analytics
import quality_standards as qs


# ---------------------------------------------------------------------------
# Pure logic: quality_standards
# ---------------------------------------------------------------------------

def test_compute_pass_fail_absolute_tolerance():
    # Density: absolute +/-2 kg/m3 (see quality_standards.py's own worked example)
    assert qs.compute_pass_fail("Density", 25.0, 27.0) == "Pass"   # exactly at upper edge
    assert qs.compute_pass_fail("Density", 25.0, 27.1) == "Fail"
    assert qs.compute_pass_fail("Density", 25.0, 23.0) == "Pass"   # exactly at lower edge
    assert qs.compute_pass_fail("Density", 25.0, 22.9) == "Fail"


def test_compute_pass_fail_relative_tolerance():
    # Tensile strength: relative 10% of target
    assert qs.compute_pass_fail("Tensile strength", 100.0, 110.0) == "Pass"
    assert qs.compute_pass_fail("Tensile strength", 100.0, 110.1) == "Fail"
    assert qs.compute_pass_fail("Tensile strength", 100.0, 90.0) == "Pass"
    assert qs.compute_pass_fail("Tensile strength", 100.0, 89.9) == "Fail"


def test_compute_pass_fail_absolute_but_percentage_unit_is_percentage_points():
    # Compression set: absolute +/-1 PERCENTAGE POINT, not 1% of target -
    # this is the exact bug fixed 2026-08-01/02 (see module docstring).
    assert qs.compute_pass_fail("Compression set", 8.0, 9.0) == "Pass"
    assert qs.compute_pass_fail("Compression set", 8.0, 9.1) == "Fail"


def test_compute_pass_fail_unpublished_property_falls_back_to_10pct_relative():
    assert qs.compute_pass_fail("Some Unlisted Rigid Property", 0.024, 0.0264) == "Pass"  # +10%
    assert qs.compute_pass_fail("Some Unlisted Rigid Property", 0.024, 0.0265) == "Fail"


def test_compute_pass_fail_none_when_nothing_to_compare():
    assert qs.compute_pass_fail("Density", None, 25.0) is None
    assert qs.compute_pass_fail("Density", 25.0, None) is None
    assert qs.compute_pass_fail("Density", 0, 25.0) is None  # falsy target


def test_tolerance_label_formats():
    assert qs.tolerance_label("Density") == "± 2 kg/m3"
    assert qs.tolerance_label("Compression set") == "± 1%"
    assert qs.tolerance_label("Tensile strength") == "± 10% of target"
    assert "no industry tolerance published" in qs.tolerance_label("Something Else")


# ---------------------------------------------------------------------------
# DB-backed: analytics.property_results_dataframe / rank_component_actual_correlations
# ---------------------------------------------------------------------------

@pytest.fixture()
def session():
    db.init_db()
    s = db.get_session()
    yield s
    s.close()


def _make_flexible_grade(session, name):
    company = db.Company(name=f"{name} Co", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"{name} Plant")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"{name} Family")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=name)
    session.add(grade); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"{name} Machine")
    session.add(machine); session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()
    session.add(db.RecipeComponent(
        recipe_version_id=recipe.id, raw_material_name="Polyol A", role_in_formulation="Base Polyol", php=100,
    ))
    session.add(db.RecipeComponent(
        recipe_version_id=recipe.id, raw_material_name="Additive X", role_in_formulation="Additive", php=5,
    ))
    session.flush()
    return grade, plant, machine, recipe


def test_property_results_dataframe_recomputes_pass_fail_live(session):
    grade, plant, machine, recipe = _make_flexible_grade(session, "Baseline-PRD")
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 1, 1), batch_reference="B1",
    )
    session.add(run); session.flush()
    session.add(db.PhysicalPropertyResult(
        production_run_id=run.id, property_name="Density", target_value=25.0, actual_value=26.0, unit="kg/m3",
    ))
    session.add(db.PhysicalPropertyResult(
        production_run_id=run.id, property_name="Density", target_value=25.0, actual_value=30.0, unit="kg/m3",
    ))
    session.commit()

    df = analytics.property_results_dataframe(session, foam_grade_id=grade.id, property_name="Density")
    assert len(df) == 2
    by_actual = {row["actual_value"]: row["pass_fail"] for _, row in df.iterrows()}
    assert by_actual[26.0] == "Pass"
    assert by_actual[30.0] == "Fail"


def _seed_run_with_metered_streams(session, grade, plant, machine, recipe, run_date, additive_php, outcome_value):
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        run_date=run_date, batch_reference=f"B-{run_date}",
    )
    session.add(run); session.flush()
    phase = db.ProductionPhase(production_run_id=run.id, phase_name="Finalized")
    session.add(phase); session.flush()
    # Base polyol reading fixed at 100 -> additive's actual_php_equivalent == its own flow_total_qty.
    # WP7 Phase 4 targeted-completion correction (2026-08-14): also set
    # production_run_id directly, not just production_phase_id - since
    # analytics.actual_usage_dataframe() now reads ComponentStreamReading
    # exclusively by production_run_id (the same ProductionPhase-free
    # pattern Item 1.3 already applied to Batch Release), matching what
    # pages/4's own Material Metering capture UI actually writes today.
    # The ProductionPhase row above is still seeded/kept for realism (a
    # Finalized phase legitimately coexists with metering on a real run)
    # but is no longer what makes these readings findable.
    session.add(db.ComponentStreamReading(
        production_run_id=run.id, production_phase_id=phase.id, stream_name="Polyol A", flow_total_qty=100.0,
    ))
    session.add(db.ComponentStreamReading(
        production_run_id=run.id, production_phase_id=phase.id, stream_name="Additive X", flow_total_qty=additive_php,
    ))
    session.add(db.PhysicalPropertyResult(
        production_run_id=run.id, property_name="Density", target_value=25.0, actual_value=outcome_value, unit="kg/m3",
    ))
    session.commit()
    return run


def test_rank_component_actual_correlations_finds_perfectly_correlated_material(session):
    grade, plant, machine, recipe = _make_flexible_grade(session, "Baseline-Corr")
    # Additive dosage 3,4,5,6 php -> outcome 20,22,24,26 (perfectly linear, corr == 1.0)
    for i, (additive_php, outcome) in enumerate([(3, 20), (4, 22), (5, 24), (6, 26)]):
        _seed_run_with_metered_streams(
            session, grade, plant, machine, recipe, dt.date(2026, 1, 1 + i), additive_php, outcome,
        )

    ranked = analytics.rank_component_actual_correlations(session, grade.id, "Density", min_runs=3)
    assert not ranked.empty
    row = ranked[ranked["raw_material_name"] == "Additive X"].iloc[0]
    assert row["n_runs"] == 4
    assert row["correlation"] == pytest.approx(1.0, abs=1e-6)


def test_rank_component_actual_correlations_excludes_below_min_runs(session):
    grade, plant, machine, recipe = _make_flexible_grade(session, "Baseline-MinRuns")
    # Only 2 runs recorded - below the default min_runs=3 threshold.
    for i, (additive_php, outcome) in enumerate([(3, 20), (6, 26)]):
        _seed_run_with_metered_streams(
            session, grade, plant, machine, recipe, dt.date(2026, 2, 1 + i), additive_php, outcome,
        )

    ranked = analytics.rank_component_actual_correlations(session, grade.id, "Density", min_runs=3)
    assert ranked.empty


# ---------------------------------------------------------------------------
# Rigid-foam-shaped grade: today's (pre-WP4) behavior is "silently empty",
# not an error - locked down here so a future change is deliberate.
# ---------------------------------------------------------------------------

def test_flexible_functions_return_empty_not_error_for_rigid_grade(session):
    company = db.Company(name="Rigid Baseline Co", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name="Rigid Baseline Plant")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name="Rigid Baseline Family")
    session.add(family); session.flush()
    chem = db.Chemistry(controlled_id="CHM-BASE-010", name="Rigid polyurethane foam")
    session.add(chem); session.flush()
    grade = db.FoamGrade(
        product_family_id=family.id, grade_name="Rigid Baseline Grade",
        chemistry_id=chem.id, status="UAT_ONLY",
    )
    session.add(grade); session.flush()

    results_df = analytics.property_results_dataframe(session, foam_grade_id=grade.id, property_name="Thermal conductivity")
    assert results_df.empty

    ranked = analytics.rank_component_actual_correlations(session, grade.id, "Thermal conductivity", min_runs=3)
    assert ranked.empty
