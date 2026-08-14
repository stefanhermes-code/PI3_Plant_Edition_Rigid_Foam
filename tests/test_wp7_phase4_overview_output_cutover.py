"""WP7 Phase 4 Overview/output KPI cutover (2026-08-14) regression tests.

Charlie's Downstream Reader Cutover Execution Instruction, section 6:
"ProductionOutputSummary becomes the active output fact. Overview, reports
and PI3 read its Actual quantity and controlled UOM. Planned quantity
supports plan-versus-actual comparison ... The existing compute_runtime_
output logic is a legacy compatibility calculation ... Phase 4 removes
this formula from active universal KPI/report authority."

Covers:
  1. analytics.production_run_output_summary() - the single-run reader:
     None for a nonexistent run or a run with no recorded output row;
     otherwise the row's Planned/Actual/unit/disposition fields.
  2. analytics.production_output_totals() - the multi-run aggregator the
     Overview KPI now reads: empty input, a single-unit total, honest
     separation of multiple units (never summed together), and correct
     counting of runs with no ProductionOutputSummary row at all versus
     rows that exist but have no Actual quantity yet.
  3. app_rigid_foam.py's Overview page "Output Quantity and Unit" KPI
     card - live AppTest evidence that it now renders from
     ProductionOutputSummary (not compute_runtime_output's conveyor-speed/
     tunnel-geometry formula), no longer requires a single Production
     Method to be selected first, and explains itself instead of showing
     a number when the scoped runs' recorded output spans more than one
     unit.

MANDATORY TEMPLATE: tests/test_cr02_overview_pm_alignment.py (AUTH_DISABLED/
sqlite:// boilerplate, _reset_schema(), two-method-per-plant fixture,
_run_overview()/_sb()/_metrics() AppTest helpers).

Usage: python -m pytest tests/test_wp7_phase4_overview_output_cutover.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import analytics
import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_MAIN = os.path.join(APP_DIR, "app_rigid_foam.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_grade_chain():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P4OUT Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P4OUT Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-WP7P4OUT-{u}", name=f"WP7P4OUT Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(plant_id=plant.id, name=f"WP7P4OUT Machine {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P4OUT Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P4OUT Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    unit_m = db.UnitOfMeasure(controlled_id=f"UOM-WP7P4OUT-M-{u}", symbol="m", name="Metres")
    session.add(unit_m); session.flush()
    unit_kg = db.UnitOfMeasure(controlled_id=f"UOM-WP7P4OUT-KG-{u}", symbol="kg", name="Kilograms")
    session.add(unit_kg); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "method_id": method.id,
        "machine_id": machine.id, "family_id": family.id, "grade_id": grade.id,
        "recipe_version_id": recipe.id, "unit_m_id": unit_m.id, "unit_kg_id": unit_kg.id,
    }
    session.close()
    return ids


def _make_run(ids, batch_suffix=None, run_date=None):
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
        recipe_version_id=ids["recipe_version_id"], run_date=run_date or dt.date(2026, 8, 1),
        batch_reference=f"B-WP7P4OUT-{batch_suffix or uuid.uuid4().hex[:8]}",
        machine_id=ids["machine_id"], production_method_id=ids["method_id"],
        operator_or_team_reference="Shift A",
    )
    session.add(run); session.commit()
    run_id = run.id
    session.close()
    return run_id


def _add_output_summary(run_id, unit_id=None, planned_quantity=None, actual_quantity=None, disposition=None):
    session = db.get_session()
    row = db.ProductionOutputSummary(
        production_run_id=run_id, unit_id=unit_id,
        planned_quantity=planned_quantity, actual_quantity=actual_quantity, disposition=disposition,
    )
    session.add(row); session.commit()
    session.close()


@pytest.fixture()
def seeded_run(seeded_grade_chain):
    ids = seeded_grade_chain
    run_id = _make_run(ids)
    out = dict(ids)
    out["run_id"] = run_id
    return out


# ---------------------------------------------------------------------------
# 1. production_run_output_summary() - single-run reader
# ---------------------------------------------------------------------------

def test_no_output_summary_row_returns_none(seeded_run):
    session = db.get_session()
    assert analytics.production_run_output_summary(session, seeded_run["run_id"]) is None
    session.close()


def test_nonexistent_run_returns_none(seeded_run):
    session = db.get_session()
    assert analytics.production_run_output_summary(session, 999999999) is None
    session.close()


def test_output_summary_reads_all_fields(seeded_run):
    _add_output_summary(
        seeded_run["run_id"], unit_id=seeded_run["unit_m_id"],
        planned_quantity=100.0, actual_quantity=97.5, disposition="Released",
    )
    session = db.get_session()
    result = analytics.production_run_output_summary(session, seeded_run["run_id"])
    assert result["production_run_id"] == seeded_run["run_id"]
    assert result["planned_quantity"] == 100.0
    assert result["actual_quantity"] == 97.5
    assert result["unit_id"] == seeded_run["unit_m_id"]
    assert result["unit_symbol"] == "m"
    assert result["disposition"] == "Released"
    session.close()


def test_accepts_run_instance_as_well_as_id(seeded_run):
    _add_output_summary(seeded_run["run_id"], unit_id=seeded_run["unit_m_id"], actual_quantity=50.0)
    session = db.get_session()
    run_obj = session.get(db.ProductionRun, seeded_run["run_id"])
    by_id = analytics.production_run_output_summary(session, seeded_run["run_id"])
    by_instance = analytics.production_run_output_summary(session, run_obj)
    assert by_id == by_instance
    session.close()


# ---------------------------------------------------------------------------
# 2. production_output_totals() - multi-run aggregator
# ---------------------------------------------------------------------------

def test_empty_run_ids_returns_empty_totals():
    session = db.get_session()
    result = analytics.production_output_totals(session, [])
    assert result == {"totals_by_unit": [], "runs_without_summary": 0}
    session.close()


def test_single_unit_sums_correctly(seeded_grade_chain):
    ids = seeded_grade_chain
    run_1 = _make_run(ids, batch_suffix="a")
    run_2 = _make_run(ids, batch_suffix="b")
    _add_output_summary(run_1, unit_id=ids["unit_m_id"], planned_quantity=100.0, actual_quantity=95.0)
    _add_output_summary(run_2, unit_id=ids["unit_m_id"], planned_quantity=100.0, actual_quantity=105.0)

    session = db.get_session()
    result = analytics.production_output_totals(session, [run_1, run_2])
    assert len(result["totals_by_unit"]) == 1
    totals = result["totals_by_unit"][0]
    assert totals["unit_symbol"] == "m"
    assert totals["actual_total"] == pytest.approx(200.0)
    assert totals["planned_total"] == pytest.approx(200.0)
    assert totals["run_count"] == 2
    assert result["runs_without_summary"] == 0
    session.close()


def test_different_units_never_summed_together(seeded_grade_chain):
    ids = seeded_grade_chain
    run_m = _make_run(ids, batch_suffix="m")
    run_kg = _make_run(ids, batch_suffix="kg")
    _add_output_summary(run_m, unit_id=ids["unit_m_id"], actual_quantity=50.0)
    _add_output_summary(run_kg, unit_id=ids["unit_kg_id"], actual_quantity=1200.0)

    session = db.get_session()
    result = analytics.production_output_totals(session, [run_m, run_kg])
    totals = result["totals_by_unit"]
    assert len(totals) == 2, "different units must produce separate entries, never a combined total"
    by_symbol = {t["unit_symbol"]: t["actual_total"] for t in totals}
    assert by_symbol["m"] == pytest.approx(50.0)
    assert by_symbol["kg"] == pytest.approx(1200.0)
    session.close()


def test_run_with_no_summary_row_counted_as_missing(seeded_grade_chain):
    ids = seeded_grade_chain
    run_with = _make_run(ids, batch_suffix="with")
    run_without = _make_run(ids, batch_suffix="without")
    _add_output_summary(run_with, unit_id=ids["unit_m_id"], actual_quantity=10.0)
    # run_without gets no ProductionOutputSummary row at all.

    session = db.get_session()
    result = analytics.production_output_totals(session, [run_with, run_without])
    assert result["runs_without_summary"] == 1
    assert result["totals_by_unit"][0]["run_count"] == 1
    session.close()


def test_planned_only_row_does_not_contribute_to_actual_total(seeded_grade_chain):
    """A ProductionOutputSummary row that exists but has no Actual quantity
    yet must not be treated as 'missing' (runs_without_summary), but also
    must not contribute 0/None into the Actual total - it simply doesn't
    count toward either side, per Charlie's 'missing Actual remains
    missing' rule applied to this domain too."""
    ids = seeded_grade_chain
    run_id = _make_run(ids)
    _add_output_summary(run_id, unit_id=ids["unit_m_id"], planned_quantity=100.0, actual_quantity=None)

    session = db.get_session()
    result = analytics.production_output_totals(session, [run_id])
    assert result["totals_by_unit"] == [], "no Actual quantity anywhere - no unit total should be produced"
    assert result["runs_without_summary"] == 0, "the run DOES have a summary row - just no Actual yet"
    session.close()


def test_totals_sorted_by_run_count_descending(seeded_grade_chain):
    ids = seeded_grade_chain
    run_kg_1 = _make_run(ids, batch_suffix="kg1")
    run_kg_2 = _make_run(ids, batch_suffix="kg2")
    run_kg_3 = _make_run(ids, batch_suffix="kg3")
    run_m_1 = _make_run(ids, batch_suffix="m1")
    for r in (run_kg_1, run_kg_2, run_kg_3):
        _add_output_summary(r, unit_id=ids["unit_kg_id"], actual_quantity=10.0)
    _add_output_summary(run_m_1, unit_id=ids["unit_m_id"], actual_quantity=5.0)

    session = db.get_session()
    result = analytics.production_output_totals(session, [run_kg_1, run_kg_2, run_kg_3, run_m_1])
    assert result["totals_by_unit"][0]["unit_symbol"] == "kg"
    assert result["totals_by_unit"][0]["run_count"] == 3
    session.close()


# ---------------------------------------------------------------------------
# 3. Overview page live AppTest evidence
# ---------------------------------------------------------------------------

def _run_overview():
    at = AppTest.from_file(APP_MAIN, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


def _sb(at, label):
    return next(sb for sb in at.selectbox if sb.label == label)


def _metrics(at):
    return {m.label: m.value for m in at.metric}


def test_overview_loads_clean_with_no_output_data(seeded_run):
    at = _run_overview()
    assert not at.exception, f"Unhandled exception loading Overview: {at.exception}"
    metrics = _metrics(at)
    assert metrics["Output Quantity and Unit"] == "—"


def test_overview_shows_recorded_output_total(seeded_run):
    _add_output_summary(seeded_run["run_id"], unit_id=seeded_run["unit_m_id"], actual_quantity=123.0)
    at = _run_overview()
    assert not at.exception
    metrics = _metrics(at)
    assert metrics["Output Quantity and Unit"] == "123 m"


def test_overview_output_kpi_no_longer_requires_single_method_selected(seeded_run):
    """The old compute_runtime_output-based KPI required a single
    Production Method to be selected before showing any figure. The
    ProductionOutputSummary-based reader is method-agnostic, so the
    default 'All Production Methods' view must show the total too."""
    _add_output_summary(seeded_run["run_id"], unit_id=seeded_run["unit_m_id"], actual_quantity=77.0)
    at = _run_overview()
    assert not at.exception
    # No Production Method selected (default state) - the card should
    # still show a figure now, unlike the pre-Phase-4 behavior.
    method_sb = _sb(at, "Production Method")
    assert method_sb.value in (None, "All Production Methods")
    metrics = _metrics(at)
    assert metrics["Output Quantity and Unit"] == "77 m"


def test_overview_explains_mixed_unit_output_instead_of_summing(seeded_grade_chain):
    ids = seeded_grade_chain
    run_m = _make_run(ids, batch_suffix="ovm", run_date=dt.date(2026, 8, 1))
    run_kg = _make_run(ids, batch_suffix="ovkg", run_date=dt.date(2026, 8, 2))
    _add_output_summary(run_m, unit_id=ids["unit_m_id"], actual_quantity=10.0)
    _add_output_summary(run_kg, unit_id=ids["unit_kg_id"], actual_quantity=20.0)

    at = _run_overview()
    assert not at.exception
    metrics = _metrics(at)
    assert metrics["Output Quantity and Unit"] == "—", (
        "mixed-unit recorded output must never be summed into one figure"
    )
    captions = [c.value for c in at.caption]
    assert any("more than one unit" in c for c in captions), (
        f"expected a caption explaining the mixed-unit state, got: {captions}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
