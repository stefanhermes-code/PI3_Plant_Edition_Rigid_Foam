"""Regression test for a production incident (2026-08-16): pages/
15_Recipe_Optimization.py crashed with

    TypeError: '<' not supported between instances of 'NoneType' and
    'datetime.datetime'

for every reviewer, on the line

    versions = sorted(grade.recipe_versions, key=lambda v: v.created_at)

RecipeVersion.created_at is DB-nullable (see db.py - `default=
dt.datetime.utcnow` is a Python-side ORM default that only fires when the
column is omitted from an INSERT; it is not a NOT NULL constraint), and a
row written via direct SQL during earlier data-loading work (see this
app's extensive history of raw-SQL WP5/CR reconciliation batches) can
legitimately skip it. Confirmed live: Supabase's rigid_foam.recipe_versions
had exactly one such row (id=6, foam_grade_id=7 "RF-COLDROOM-001") when
this was diagnosed, and it was the grade's only (and active) recipe
version, so every visit to Recipe Optimization with that grade selected
crashed the whole page for every reviewer, not just whoever created the
row.

The fix (both here and in ai_assistant.py's identical `analysis_type ==
"recipe_cost"` copy of this same sort, used by the PI3 query tool) is a
None-safe sort key: `v.created_at or dt.datetime.min`. This test seeds a
RecipeVersion with created_at explicitly set to None (reproducing the
live defect rather than asserting against a helper-function truth table -
Charlie's standing requirement per the CR-22 focused closeout return) and
confirms the page renders without an unhandled exception.

Usage: DATABASE_URL=sqlite:////tmp/.../db.db python -m pytest tests/test_recipe_version_null_created_at_defect.py
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
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_grade_with_null_created_at_recipe_version():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"Null CreatedAt Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"Null CreatedAt Plant {u}")
    session.add(plant); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"Null CreatedAt Machine {u}")
    session.add(machine); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"Null CreatedAt Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"RF-COLDROOM-{u}")
    session.add(grade); session.flush()

    # The defect-reproducing line: created_at explicitly None, exactly the
    # shape the live Supabase row had (a raw-SQL insert that skipped the
    # column entirely leaves the same NULL - passing None here is the
    # faithful in-memory equivalent).
    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label="v1", approval_status="Approved",
        is_active=True, created_at=None,
    )
    session.add(recipe); session.flush()
    session.add(db.RecipeComponent(recipe_version_id=recipe.id, raw_material_name="Polyol A", role_in_formulation="Base Polyol", php=100))
    session.add(db.RecipeComponent(recipe_version_id=recipe.id, raw_material_name="Additive X", role_in_formulation="Additive", php=5))
    session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 10), batch_reference="BATCH-2026-08-10-001",
    )
    session.add(run); session.flush()
    session.add(db.PhysicalPropertyResult(production_run_id=run.id, property_name="Density", target_value=25.0, actual_value=25.5, unit="kg/m3"))
    session.commit()
    session.close()
    return grade.grade_name


def _run_page():
    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    return at


def test_page_loads_cleanly_when_recipe_version_created_at_is_null(seeded_grade_with_null_created_at_recipe_version):
    at = _run_page()
    assert not at.exception, (
        f"Unhandled exception with a NULL RecipeVersion.created_at (the exact live "
        f"production defect - see module docstring): {at.exception}"
    )
    assert len(at.subheader) > 0


def test_sort_key_matches_pages15_none_safe_fallback():
    """Direct-evidence companion to the AppTest above: proves the specific
    sort expression pages/15 and ai_assistant.py now both use doesn't raise
    on a mixed None/datetime list, and orders the None entry first (oldest)
    - the same interpretation as an unknown creation time everywhere else
    on the page treats a missing value."""
    class _V:
        def __init__(self, created_at):
            self.created_at = created_at

    versions = [_V(dt.datetime(2026, 8, 10)), _V(None), _V(dt.datetime(2026, 1, 1))]
    ordered = sorted(versions, key=lambda v: v.created_at or dt.datetime.min)
    assert ordered[0].created_at is None
    assert ordered[1].created_at == dt.datetime(2026, 1, 1)
    assert ordered[2].created_at == dt.datetime(2026, 8, 10)
