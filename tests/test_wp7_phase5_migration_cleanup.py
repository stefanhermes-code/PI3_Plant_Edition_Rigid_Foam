"""WP7 Phase 5 (2026-08-15) - direct evidence for the contract's A5-01
(legacy dependency inventory), A5-02 (data reconciliation) and A5-03
(schema safety) acceptance items, and for the Decision Ledger's D5-08
("Legacy migration utilities... retain only utilities still required for
upgrade/rollback evidence").

Scope of this module - what it proves, and why no physical schema change
happens in Phase 5 (per the JC Pre-Coding Engineering Challenge Response,
section 3, "Resolved nuance: physical schema disposition for
ProductionPhase"):

1. ProductionPhase (and its two physically-dependent tables,
   RuntimeDataRecord and FallplateSectionPosition) remain ARCHIVE
   READ-ONLY this phase - the table/columns stay physically in the schema
   for historical integrity and FK safety. This is proven directly here
   (test_production_phase_and_dependents_still_physically_present) rather
   than asserted in prose, so a future accidental DROP would fail this
   test immediately.

2. legacy_migration.py's reconciliation utilities (D5-08: MIGRATION
   SUPPORT, RETAIN) still function correctly after the Phase 5 active-code
   retirement batch (analytics.py's run_settings_dataframe() simplification
   and views/4's widget removal) - proven by re-running the exact
   reconciliation path against synthetic legacy data and getting the same
   correct result test_wp7_phase3_reconciliation.py already established.
   This module does not duplicate that file's ~20 assertions; it adds the
   one assertion that file's docstring predates: that retirement of the
   *consumers* of ProductionPhase's legacy fields did not also disturb the
   *migration* path, which reads those same columns independently.

3. The five DEFERRED/QUARANTINED fields (D5-04: mixer_rpm, conveyor_speed,
   sidewall_width_mm; D5-05: air_injection_rate, air_pressure_bar) have
   zero migrated ProcessParameterValue equivalent - direct proof that
   "remain untouched" (the JC response's own phrase) is actually true of
   the reconciliation logic, not just of the retired UI.

4. A5-03 ("Any physical removal has tested upgrade and rollback/restore
   behavior") is schema safety for physical removal specifically. Phase 5
   performs zero physical removal (see point 1) - the physical-removal
   gate itself (Decision Ledger Edge-state rule: "Physical column/table
   removal occurs only after zero active dependency, successful migration
   reconciliation and tested rollback/restore path") is intentionally a
   future, separately-scoped item once Method/Unit applicability evidence
   exists for the five deferred/quarantined fields. This module proves the
   *preconditions* for that future gate are being tracked correctly
   (schema still present, migration path still correct, deferred fields
   still isolated) rather than fabricating a DDL rollback test for a
   removal that is not happening this phase.

Live rigid_foam Supabase state as of 2026-08-15 (direct query, project
aazkdsqpytjciiqtvnfj): production_runs=1, production_phases=0,
process_parameter_values=0, component_stream_readings=0,
fallplate_section_positions=0 - the CR-04 database reset (2026-08-10) left
only the minimal Phase 1 UAT baseline, so live pre/post counts for the
four migrated fields are honestly 0=0 (matching test_wp7_phase3_
reconciliation.py's own "on empty schema" test) and are not repeated here.

Usage: python -m pytest tests/test_wp7_phase5_migration_cleanup.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import datetime as dt
import uuid

import pytest
from sqlalchemy import inspect

import analytics
import db
import legacy_migration as lm


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_run():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P5MC Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P5MC Plant {u}")
    session.add(plant); session.flush()
    method = db.ProductionMethod(controlled_id=f"PM-WP7P5MC-{u}", name=f"WP7P5MC Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"WP7P5MC Unit {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P5MC Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P5MC Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference=f"B-WP7P5MC-{u}",
        machine_id=machine.id, production_method_id=method.id, operator_or_team_reference="Shift A",
    )
    session.add(run); session.commit()
    ids = {"run_id": run.id, "method_id": method.id, "machine_id": machine.id}
    session.close()
    return ids


# ---------------------------------------------------------------------------
# A5-01 / Decision Ledger D5-01, D5-03: schema disposition is ARCHIVE
# READ-ONLY, not REMOVE, this phase.
# ---------------------------------------------------------------------------

def test_production_phase_and_dependents_still_physically_present():
    """Direct schema-inspection proof of the JC response's disposition
    (section 3): ProductionPhase, RuntimeDataRecord and
    FallplateSectionPosition remain physically in the schema this phase.
    A future accidental DROP of any of these fails this test immediately,
    rather than being discovered only when a historical read breaks."""
    db.init_db()
    _reset_schema()
    inspector = inspect(db.ENGINE)
    table_names = set(inspector.get_table_names())

    assert "production_phases" in table_names
    assert "runtime_data_records" in table_names
    assert "fallplate_section_positions" in table_names

    phase_columns = {c["name"] for c in inspector.get_columns("production_phases")}
    # The 5 deferred/quarantined legacy fields must still exist physically -
    # ARCHIVE READ-ONLY means retained columns, not dropped ones.
    for field in ("mixer_rpm", "conveyor_speed", "air_injection_rate", "air_pressure_bar", "sidewall_width_mm"):
        assert field in phase_columns, f"{field} must remain physically present (ARCHIVE READ-ONLY)"
    # The 4 already-migrated fields must also still exist physically -
    # migration copies the value forward, it does not remove the source.
    for field in ("ambient_temperature_c", "ambient_humidity_pct", "foam_height_mm", "rise_time"):
        assert field in phase_columns, f"{field} must remain physically present (ARCHIVE READ-ONLY)"

    fk_columns = inspector.get_columns("fallplate_section_positions")
    phase_fk = next(c for c in fk_columns if c["name"] == "production_phase_id")
    assert phase_fk["nullable"] is False, (
        "fallplate_section_positions.production_phase_id NOT NULL is the exact FK-safety reason "
        "the JC response gives for why ProductionPhase cannot be physically dropped this phase"
    )


# ---------------------------------------------------------------------------
# D5-08: legacy_migration.py still functions correctly after the Phase 5
# active-code-retirement batch (analytics.py / views/4 changes).
# ---------------------------------------------------------------------------

def test_migration_utility_unaffected_by_active_code_retirement(seeded_run):
    """legacy_migration.py reads ProductionPhase columns directly via the
    ORM - it does not go through analytics.run_settings_dataframe() or any
    views/4 widget. Proves that is actually true post-retirement: seed one
    legacy Finalized phase with all 4 migratable fields plus one deferred
    and one quarantined field set, run the real reconciliation path, and
    confirm the migrated/deferred/quarantined counts are exactly what
    test_wp7_phase3_reconciliation.py already established pre-retirement -
    i.e. retiring the consumers did not silently change the producer."""
    ids = seeded_run
    session = db.get_session()
    session.add(db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Finalized",
        ambient_temperature_c=22.5, ambient_humidity_pct=48.0,
        foam_height_mm=175.0, rise_time=62.0,
        mixer_rpm=58.0, conveyor_speed=3.1, sidewall_width_mm=1180.0,
        air_injection_rate=12.0, air_pressure_bar=2.1,
    ))
    session.commit()

    summary = lm.phase3_reconciliation_summary(session)
    session.commit()

    assert summary["environment_outcome_values"]["values_migrated"] == 4
    assert summary["quarantine_air_settings_count"] == 1

    migrated = session.query(db.ProcessParameterValue).filter_by(source="WP7 Phase 3 migration").all()
    assert len(migrated) == 4
    migrated_values = {round(v.numeric_value, 1) for v in migrated}
    assert migrated_values == {22.5, 48.0, 175.0, 62.0}
    session.close()


def test_deferred_and_quarantined_fields_have_zero_migrated_equivalent(seeded_run):
    """Direct proof that the 5 deferred/quarantined fields (D5-04, D5-05)
    remain untouched by the reconciliation path: even with all 5 populated
    on a real row, zero ProcessSettingDefinition or ProcessParameterValue
    rows are ever created for mixer_rpm/conveyor_speed/sidewall_width_mm/
    air_injection_rate/air_pressure_bar - only the quarantine *report*
    (data unchanged, list output only) surfaces air settings, per
    quarantine_air_settings_report()'s own docstring."""
    ids = seeded_run
    session = db.get_session()
    session.add(db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Finalized",
        mixer_rpm=60.5, conveyor_speed=3.22, sidewall_width_mm=1180.0,
        air_injection_rate=12.6, air_pressure_bar=2.28,
    ))
    session.commit()

    lm.phase3_reconciliation_summary(session)
    session.commit()

    deferred_names = {"Mixer speed", "Conveyor speed", "Tunnel width", "Sidewall width",
                       "Air injection rate", "Air pressure"}
    leaked_definitions = session.query(db.ProcessSettingDefinition).filter(
        db.ProcessSettingDefinition.name.in_(deferred_names)
    ).count()
    assert leaked_definitions == 0, "no ProcessSettingDefinition may exist for a deferred/quarantined field"

    # Every ProcessParameterValue created must trace back to one of the 4
    # migrated definitions (PS-008/PS-009/PS-078/PS-079) only.
    migrated_ids = {
        d.id for d in session.query(db.ProcessSettingDefinition).filter(
            db.ProcessSettingDefinition.controlled_id.in_(["PS-008", "PS-009", "PS-078", "PS-079"])
        ).all()
    }
    all_ppv_definition_ids = {v.setting_definition_id for v in session.query(db.ProcessParameterValue).all()}
    assert all_ppv_definition_ids.issubset(migrated_ids)

    # The original legacy row itself is untouched (source data preserved).
    phase = session.query(db.ProductionPhase).filter_by(production_run_id=ids["run_id"]).one()
    assert phase.mixer_rpm == 60.5
    assert phase.conveyor_speed == 3.22
    assert phase.air_injection_rate == 12.6
    assert phase.air_pressure_bar == 2.28
    session.close()


# ---------------------------------------------------------------------------
# A5-01: run_settings_dataframe() (the one remaining active ProductionPhase-
# adjacent reader) genuinely never touches the 5 deferred/quarantined or 4
# migrated columns any more - re-proven here at the analytics-module
# boundary specifically for the Phase 5 closure gate (test_wp7_phase0_
# containment.py already covers the identity-column shape; this adds the
# "even with legacy data present" case that file's fixture doesn't seed).
# ---------------------------------------------------------------------------

def test_run_settings_dataframe_ignores_legacy_phase_data_even_when_present(seeded_run):
    ids = seeded_run
    session = db.get_session()
    session.add(db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Finalized",
        mixer_rpm=999.0, ambient_temperature_c=999.0,
    ))
    session.commit()

    df = analytics.run_settings_dataframe(session)
    assert list(df.columns) == [
        "run_id", "run_date", "foam_grade_id", "foam_grade",
        "recipe_version_id", "recipe_version", "machine_id", "machine",
        "production_method_id", "production_method",
    ]
    assert "mixer_rpm" not in df.columns
    assert "ambient_temperature_c" not in df.columns
    session.close()
