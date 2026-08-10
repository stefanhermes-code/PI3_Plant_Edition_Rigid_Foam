"""WP4 (Converged Joint Implementation Plan, section 7.5) smoke test for
pages/15_Recipe_Optimization.py's rigid/flexible branch (task #560), using
Streamlit's AppTest to actually run the page - not just the underlying
analytics/wp3_conformance functions (already covered by test_recipe_
optimization_baseline.py, test_wp4_rigid_achievement_summary.py, and
test_wp4_rigid_lot_use_correlation.py) - so the Streamlit-specific glue
code added to the page (selectbox construction, render_data_table calls,
session-state keys) is exercised too, for both a flexible and a rigid
foam grade.

Each test seeds ONLY one grade type so the page's grade selectbox has a
single option and the page never needs to switch grades mid-AppTest-
session - Streamlit's AppTest doesn't cleanly support a widget whose key
depends on which option is selected (this page's "Include lab trial data"
checkbox is keyed by grade.id) being switched out for a same-keyless one
mid-run; that's a testing-harness limitation, not something a real
browser session hits, so it's worked around here rather than something
the page itself needs to handle.

Uses the AUTH_DISABLED dev bypass (see auth.py's require_login docstring)
to reach the page without a real login flow.

Usage: DATABASE_URL=sqlite:////tmp/.../db.db python -m pytest tests/test_wp4_recipe_optimization_page_smoke.py
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import db

PAGE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pages", "15_Recipe_Optimization.py")


def _reset_schema():
    """Full drop/recreate before each fixture, not just init_db()'s
    create-if-missing. Needed since the db.py StaticPool fix for in-memory
    SQLite (2026-08-08, added so AppTest's separate thread can share the
    same connection as this fixture's thread) means the in-memory database
    now genuinely persists across both tests in this file within one
    pytest run, instead of accidentally getting a fresh database per test
    the way the old (crash-prone) SingletonThreadPool behavior happened to.
    Without this, seeded_flexible_only's grade row would still be present
    when seeded_rigid_only's test runs, giving the grade selectbox two
    options instead of the single one this file's tests are built around
    (see module docstring).

    Calls create_all() directly rather than db.init_db(): init_db's actual
    schema work is wrapped in @st.cache_resource (so a real server checks
    the schema only once per process, not once per rerun - see db.py) and
    would silently no-op the second time in this same test process, right
    after drop_all() just removed every table."""
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def _seed_base(u):
    _reset_schema()
    session = db.get_session()
    company = db.Company(name=f"WP4 Page Smoke Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP4 Page Smoke Plant {u}")
    session.add(plant); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"WP4 Page Smoke Machine {u}")
    session.add(machine); session.flush()
    session.commit()
    return session, plant, machine


@pytest.fixture()
def seeded_flexible_only():
    db.init_db()
    u = uuid.uuid4().hex[:8]
    session, plant, machine = _seed_base(u)

    family = db.ProductFamily(plant_id=plant.id, name=f"Flex Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"Flex Grade Smoke {u}")
    session.add(grade); session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()
    session.add(db.RecipeComponent(recipe_version_id=recipe.id, raw_material_name="Polyol A", role_in_formulation="Base Polyol", php=100))
    session.add(db.RecipeComponent(recipe_version_id=recipe.id, raw_material_name="Additive X", role_in_formulation="Additive", php=5))
    session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference="FLEX-B1",
    )
    session.add(run); session.flush()
    phase = db.ProductionPhase(production_run_id=run.id, phase_name="Finalized")
    session.add(phase); session.flush()
    session.add(db.ComponentStreamReading(production_phase_id=phase.id, stream_name="Polyol A", flow_total_qty=100.0))
    session.add(db.ComponentStreamReading(production_phase_id=phase.id, stream_name="Additive X", flow_total_qty=5.0))
    session.add(db.PhysicalPropertyResult(production_run_id=run.id, property_name="Density", target_value=25.0, actual_value=25.5, unit="kg/m3"))
    session.commit()
    session.close()
    return grade.grade_name


@pytest.fixture()
def seeded_rigid_only():
    db.init_db()
    u = uuid.uuid4().hex[:8]
    session, plant, machine = _seed_base(u)

    family = db.ProductFamily(plant_id=plant.id, name=f"Rigid Family {u}")
    session.add(family); session.flush()
    chem = db.Chemistry(controlled_id=f"CHM-SMOKE-010-{u}", name="Rigid polyurethane foam")
    method = db.ProductionMethod(controlled_id=f"PM-SMOKE-120-{u}", name="Closed-mold panel injection")
    session.add_all([chem, method]); session.flush()
    # FoamGrade.production_method_id removed 2026-08-10 (Charlie's "Database
    # Reset and Clean UAT Baseline" instruction) - chemistry_id alone is
    # what this test needs to exercise the rigid-vs-flexible branch.
    grade = db.FoamGrade(
        product_family_id=family.id, grade_name=f"Rigid Grade Smoke {u}",
        chemistry_id=chem.id, status="UAT_ONLY",
    )
    session.add(grade); session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Draft", is_active=True)
    session.add(recipe); session.flush()
    session.add(db.RecipeComponent(recipe_version_id=recipe.id, raw_material_name="Polyol R", role_in_formulation="Base Polyol", php=100))
    session.add(db.RecipeComponent(recipe_version_id=recipe.id, raw_material_name="Flame Retardant R", role_in_formulation="Additive", php=8))
    session.flush()

    propdef = session.query(db.PhysicalPropertyDefinition).filter_by(name="Thermal conductivity").first()
    if propdef is None:
        propdef = db.PhysicalPropertyDefinition(name="Thermal conductivity")
        session.add(propdef); session.flush()
    propmethod = db.PhysicalPropertyMethod(property_definition_id=propdef.id, method_code="ISO 8301", controlled_id=f"MTH-SMOKE-016-{u}")
    session.add(propmethod); session.flush()
    orientation = db.Orientation(controlled_id=f"ORI-SMOKE-THROUGH-{u}", name="Through-thickness")
    location = db.Location(controlled_id=f"LOC-SMOKE-CORE-{u}", name="Core")
    condition = db.TestCondition(controlled_id=f"CTX-SMOKE-INIT-{u}", name="Initial, 10C mean, 7 days")
    session.add_all([orientation, location, condition]); session.flush()
    spec = db.GradeSpecification(
        foam_grade_id=grade.id, property_definition_id=propdef.id, property_method_id=propmethod.id,
        property_name="Thermal conductivity", target_operator="<=", target_value=0.030, unit="W/(m.K)",
        condition_id=condition.id, orientation_id=orientation.id, location_id=location.id,
    )
    session.add(spec); session.flush()

    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference="RIGID-B1",
    )
    session.add(run); session.flush()
    session.add(db.RawMaterialLotUse(production_run_id=run.id, component_stream_name="Polyol R", supplier_lot_no="LOT-P1", mass_kg=500.0))
    session.add(db.RawMaterialLotUse(production_run_id=run.id, component_stream_name="Flame Retardant R", supplier_lot_no="LOT-F1", mass_kg=40.0))
    sample = db.Sample(
        production_run_id=run.id, location_id=location.id, orientation_id=orientation.id,
        thickness_mm=60.0, age_hours=168.0, sample_scope="Core", sample_ts=dt.datetime(2026, 8, 1, 10, 0),
    )
    session.add(sample); session.flush()
    session.add(db.PhysicalPropertyResult(
        production_run_id=run.id, sample_id=sample.id, property_definition_id=propdef.id,
        property_method_id=propmethod.id, property_name="Thermal conductivity", actual_value=0.027,
        unit="W/(m.K)", test_method="ISO 8301", condition_id=condition.id, orientation_id=orientation.id,
        location_id=location.id, tested_at=dt.date(2026, 8, 2),
    ))
    # Enabled here (not in seeded_flexible_only) so the rigid smoke test
    # exercises the "Ask PI3 for a formulation recommendation" branch's
    # target-property-prefill loop (built for the rigid PI3 recommendation
    # follow-up) instead of just the "PI3 not configured" caption. Fake
    # OPENAI_API_KEY/PI3_VECTOR_STORE_ID secrets are set in _run_page() -
    # this only satisfies ai_assistant.is_configured()'s presence check, it
    # never actually calls OpenAI, since the test never clicks the "Get PI3
    # recommendation" button (that would require a real API key/network
    # call, which a unit-style smoke test must not depend on).
    session.add(db.PI3AIConnectionSetting(plant_id=plant.id, pi3_ai_connectivity_enabled=True))
    session.commit()
    session.close()
    return grade.grade_name


def _run_page():
    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.secrets["OPENAI_API_KEY"] = "sk-test-not-a-real-key"
    at.secrets["PI3_VECTOR_STORE_ID"] = "vs_test_not_real"
    at.run()
    return at


def test_page_loads_cleanly_for_flexible_grade(seeded_flexible_only):
    at = _run_page()
    assert not at.exception, f"Unhandled exception loading a flexible-foam grade: {at.exception}"
    assert len(at.subheader) > 0
    body_text = " ".join(el.value for el in at.markdown) + " ".join(el.value for el in at.caption)
    assert "Does the current recipe meet target?" in [h.value for h in at.subheader]
    # Flexible branch renders the tolerance-based caption, not the rigid one.
    assert "industry accepted tolerance" in body_text


def test_page_loads_cleanly_for_rigid_grade(seeded_rigid_only):
    at = _run_page()
    assert not at.exception, f"Unhandled exception loading a rigid-foam grade: {at.exception}"
    assert len(at.subheader) > 0
    body_text = " ".join(el.value for el in at.markdown) + " ".join(el.value for el in at.caption)
    # Rigid branch renders spec-based language instead of the flexible tolerance caption.
    assert "GradeSpecification" not in body_text  # internal name should never leak to the UI
    assert "own specification limit" in body_text or "specification" in body_text.lower()
    # The Recipe Optimization Report and PI3 recommendation sections are no
    # longer gated placeholders for a rigid grade (both built out - report
    # in task #561, PI3 recommendation as a follow-up) - confirm neither
    # leftover "not yet available" caption is still showing.
    assert "tracked WP4 follow-up" not in body_text
    # The PI3 recommendation section's target-property text_area should be
    # prefilled from this grade's own specification (seeded_rigid_only sets
    # up a Thermal conductivity spec, <= 0.030 W/(m.K)) - confirms the new
    # rigid target-prefill loop ran without error (seeded_rigid_only also
    # enables PI3 for this plant and _run_page() sets fake secrets so this
    # branch is actually reached, not skipped for "PI3 not configured").
    target_area_values = [ta.value for ta in at.text_area if ta.label == "Target properties"]
    assert target_area_values, "Target properties text_area not found - PI3 recommendation branch didn't render"
    assert "Thermal conductivity" in target_area_values[0]
    assert "0.03" in target_area_values[0]
    assert any(b.label == "Get PI3 recommendation" for b in at.button)
