"""WP7 Phase 3 (2026-08-14) - direct unit-test evidence for
legacy_migration.py, proving the reconciliation logic itself is correct
against synthetic ProductionPhase/ComponentStreamReading data - since the
live rigid_foam Supabase schema currently has ZERO production_phases rows
(confirmed via direct count query before writing this module; the
CR-04/WP6-S02 database reset left only the minimal Phase 1 UAT baseline),
these tests are what proves the migration logic is ready and correct for
whenever real legacy data does exist, standing in for the "verified
migrated data" evidence the WP7 Phase 1 design doc's section 6.3 gate asks
for. See the WP7 Phase 3 closeout package for the live-data reconciliation
counts themselves (honestly all zero) and the explicit open items left for
Charlie (mixer_rpm/conveyor_speed/sidewall_width_mm PM-code mapping,
air_injection_rate/air_pressure_bar quarantine review, block_reference
review) - none of which this module touches, per its own docstring.

Usage: python -m pytest tests/test_wp7_phase3_reconciliation.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
import legacy_migration as lm
import tenant_scope


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()


@pytest.fixture()
def seeded_run():
    """Company -> Plant -> ProductionMethod -> Machine -> ProductFamily ->
    FoamGrade -> RecipeVersion -> ProductionRun chain - the minimum
    content any ProductionPhase row needs a production_run_id to attach
    to. No ProcessSettingDefinition/UOM content seeded - each test proves
    legacy_migration creates what it needs from a clean schema."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P3 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P3 Plant {u}")
    session.add(plant); session.flush()
    method = db.ProductionMethod(controlled_id=f"PM-WP7P3-{u}", name=f"WP7P3 Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"WP7P3 Unit {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P3 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P3 Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference=f"B-WP7P3-{u}",
        machine_id=machine.id, production_method_id=method.id, operator_or_team_reference="Shift A",
    )
    session.add(run); session.commit()
    ids = {"company_id": company.id, "plant_id": plant.id, "run_id": run.id}
    session.close()
    return ids


# ---------------------------------------------------------------------------
# 1. ensure_environment_outcome_uoms / ensure_environment_outcome_definitions
# ---------------------------------------------------------------------------

def test_ensure_uoms_creates_four_rows_and_is_idempotent(seeded_run):
    session = db.get_session()
    created_first = lm.ensure_environment_outcome_uoms(session)
    session.commit()
    assert created_first == 4

    created_second = lm.ensure_environment_outcome_uoms(session)
    session.commit()
    assert created_second == 0, "re-running must not create duplicate UOM rows"

    total = session.query(db.UnitOfMeasure).filter(
        db.UnitOfMeasure.controlled_id.in_(["UOM-038", "UOM-039", "UOM-040", "UOM-041"])
    ).count()
    assert total == 4
    session.close()


def test_ensure_definitions_reuses_existing_ps008_ps009_not_duplicates(seeded_run):
    """Simulates the real production state: PS-008 (Ambient temperature)
    and PS-009 (Relative humidity) already exist as dormant WP3f rows
    with parameter_category=NULL, exactly as the live rigid_foam schema
    has them today. ensure_environment_outcome_definitions() must adopt
    (categorize) these existing rows, not create PS-008-duplicate rows
    under a different controlled_id."""
    session = db.get_session()
    session.add(db.ProcessSettingDefinition(
        controlled_id="PS-008", name="Ambient temperature", data_type="Float", active=True,
    ))
    session.add(db.ProcessSettingDefinition(
        controlled_id="PS-009", name="Relative humidity", data_type="Float", active=True,
    ))
    session.commit()

    result = lm.ensure_environment_outcome_definitions(session)
    session.commit()

    # PS-008/PS-009 already existed (updated, not created); PS-078/PS-079 are new.
    assert result["definitions_created"] == 2
    assert result["definitions_updated"] == 2
    assert result["applicabilities_created"] == 4

    ps008 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-008").one()
    assert ps008.parameter_category == "Environment"
    ps078 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-078").one()
    assert ps078.name == "Foam height"
    assert ps078.parameter_category == "Outcome"

    total_ps008 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-008").count()
    assert total_ps008 == 1, "must not duplicate the existing dormant PS-008 row"

    applicability = session.query(db.ProcessSettingApplicability).filter_by(
        setting_definition_id=ps008.id, production_method_id=None, machine_id=None,
    ).one()
    assert applicability.controllable is False
    assert applicability.analytics_eligible is False

    # Idempotent second call.
    result2 = lm.ensure_environment_outcome_definitions(session)
    session.commit()
    assert result2["definitions_created"] == 0
    assert result2["applicabilities_created"] == 0
    session.close()


# ---------------------------------------------------------------------------
# 2. backfill_environment_outcome_values - NULL-vs-zero preserved, idempotent
# ---------------------------------------------------------------------------

def test_backfill_environment_outcome_values_preserves_null_vs_zero(seeded_run):
    ids = seeded_run
    session = db.get_session()

    setup_phase = db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Setup",
        ambient_temperature_c=21.5,
        ambient_humidity_pct=0.0,  # real recorded zero - must NOT be dropped
        foam_height_mm=None,  # genuinely blank - must be skipped, not migrated as 0
        rise_time=45.0,
    )
    finalized_phase = db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Finalized",
        ambient_temperature_c=23.0, ambient_humidity_pct=55.5,
        foam_height_mm=180.0, rise_time=None,
    )
    session.add_all([setup_phase, finalized_phase])
    session.commit()

    result = lm.backfill_environment_outcome_values(session)
    session.commit()

    assert result["phases_read"] == 2
    # Setup: ambient_temp, ambient_humidity (0.0), rise_time migrate = 3; foam_height skipped.
    # Finalized: ambient_temp, ambient_humidity, foam_height migrate = 3; rise_time skipped.
    assert result["values_migrated"] == 6
    assert result["values_skipped_null"] == 2

    ps009 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-009").one()
    humidity_planned = session.query(db.ProcessParameterValue).filter_by(
        setting_definition_id=ps009.id, production_run_id=ids["run_id"], snapshot_type="Planned",
    ).one()
    assert humidity_planned.numeric_value == 0.0, "a real recorded zero must persist as 0.0, not be dropped"

    ps078 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-078").one()
    foam_height_rows = session.query(db.ProcessParameterValue).filter_by(
        setting_definition_id=ps078.id, production_run_id=ids["run_id"],
    ).all()
    assert len(foam_height_rows) == 1
    assert foam_height_rows[0].snapshot_type == "Actual"
    assert foam_height_rows[0].numeric_value == 180.0
    assert foam_height_rows[0].source == "WP7 Phase 3 migration"

    # Idempotent re-run: no duplicates, everything already-present.
    result2 = lm.backfill_environment_outcome_values(session)
    session.commit()
    assert result2["values_migrated"] == 0
    assert result2["values_already_present"] == 6
    session.close()


# ---------------------------------------------------------------------------
# 3. backfill_component_stream_reading_run_ids
# ---------------------------------------------------------------------------

def test_backfill_component_stream_reading_run_ids(seeded_run):
    ids = seeded_run
    session = db.get_session()
    phase = db.ProductionPhase(production_run_id=ids["run_id"], phase_name="Finalized")
    session.add(phase); session.flush()

    reading = db.ComponentStreamReading(
        production_phase_id=phase.id, stream_name="Polyol A", flow=12.5,
    )
    session.add(reading); session.commit()
    assert reading.production_run_id is None

    result = lm.backfill_component_stream_reading_run_ids(session)
    session.commit()

    assert result["readings_read"] == 1
    assert result["readings_backfilled"] == 1
    assert result["readings_skipped_no_phase"] == 0

    session.refresh(reading)
    assert reading.production_run_id == ids["run_id"]

    # Idempotent: already-backfilled rows are not touched again.
    result2 = lm.backfill_component_stream_reading_run_ids(session)
    assert result2["readings_read"] == 0
    session.close()


# ---------------------------------------------------------------------------
# 4. quarantine_air_settings_report - no auto-migration, just a report
# ---------------------------------------------------------------------------

def test_quarantine_air_settings_report_lists_nonnull_values_only(seeded_run):
    ids = seeded_run
    session = db.get_session()
    session.add(db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Setup", air_injection_rate=12.0,
    ))
    session.add(db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Finalized", air_pressure_bar=3.2,
    ))
    session.add(db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Setup",  # neither field set
    ))
    session.commit()

    report = lm.quarantine_air_settings_report(session)
    assert len(report) == 2
    assert {row["air_injection_rate"] for row in report} == {12.0, None}
    assert {row["air_pressure_bar"] for row in report} == {None, 3.2}

    # No ProcessParameterValue rows must have been created for these -
    # quarantine means report-only, never auto-migrated.
    ppv_count = session.query(db.ProcessParameterValue).count()
    assert ppv_count == 0
    session.close()


# ---------------------------------------------------------------------------
# 5. phase3_reconciliation_summary - orchestration, and the zero-legacy-data case
# ---------------------------------------------------------------------------

def test_reconciliation_summary_on_empty_schema_is_honestly_zero(seeded_run):
    """Mirrors the actual live rigid_foam Supabase state today: zero
    ProductionPhase rows. Every count must be an honest 0, not an error -
    this is the exact evidence the WP7 Phase 3 closeout package cites for
    why live-data reconciliation counts are all zero."""
    session = db.get_session()
    summary = lm.phase3_reconciliation_summary(session)
    session.commit()

    assert summary["environment_outcome_values"]["phases_read"] == 0
    assert summary["environment_outcome_values"]["values_migrated"] == 0
    assert summary["component_stream_reading_backfill"]["readings_read"] == 0
    assert summary["quarantine_air_settings_count"] == 0
    # Definitions/UOMs/applicabilities are still established even with zero
    # legacy rows - this is schema-completeness, not data-dependent.
    assert summary["environment_outcome_definitions"]["definitions_created"] == 4
    session.close()


def test_reconciliation_summary_orchestrates_all_steps_together(seeded_run):
    ids = seeded_run
    session = db.get_session()
    session.add(db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Finalized",
        ambient_temperature_c=22.0, air_pressure_bar=2.8,
    ))
    session.commit()

    summary = lm.phase3_reconciliation_summary(session)
    session.commit()

    assert summary["environment_outcome_values"]["phases_read"] == 1
    assert summary["environment_outcome_values"]["values_migrated"] == 1
    assert summary["quarantine_air_settings_count"] == 1
    session.close()
