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

WP7 Phase 3 correction (2026-08-14, Charlie's closeout review of v0.44.0/
af23f8a): also covers direct evidence for the targeted correction -
Environment/Outcome ProcessSettingDefinitions are actual-only capture
(applicable_to_planned=False), a Setup-phase legacy value for one of these
fields is quarantined rather than migrated as "Planned", and the Method-
Aware Process Settings UI tab excludes Environment/Outcome categories
entirely while true Process Setting definitions continue to render
normally (direct AppTest UI evidence, not just ORM-level).

Usage: python -m pytest tests/test_wp7_phase3_reconciliation.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import access_control
import db
import legacy_migration as lm
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE4 = os.path.join(APP_DIR, "pages", "4_Production_Run_Trial_Record.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()


def _run_page4(session_state=None):
    """AppTest runner for pages/4, matching
    test_wp7_phase2_production_run_ui.py's own _run() convention exactly -
    used here only for the WP7 Phase 3 correction's UI-exclusion evidence
    (Charlie's acceptance criterion #2)."""
    at = AppTest.from_file(PAGE4, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def _submit_key(at, form_key, label):
    """Matches test_wp7_phase2_closeout_correction.py's own helper exactly
    - form_submit_button's derived widget key."""
    return next(b for b in at.button if b.key == f"FormSubmitter:{form_key}-{label}")


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
    ids = {
        "company_id": company.id, "plant_id": plant.id, "run_id": run.id,
        "method_id": method.id, "machine_id": machine.id,
    }
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
        # Canonical identifiers since the controlled UOM reconciliation
        # (2026-08-18) retired the original UOM-038/039/040/041 block.
        # UOM-029 %RH rather than a plain percent row: PS-009 Relative
        # humidity carries the dedicated humidity unit.
        db.UnitOfMeasure.controlled_id.in_(["UOM-007", "UOM-009", "UOM-010", "UOM-029"])
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
    assert result["applicabilities_corrected"] == 0

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
    # WP7 Phase 3 correction (2026-08-14, Charlie's closeout review, finding
    # #1): actual-only capture - Environment/Outcome measurements must never
    # be eligible as a "Planned" process setting.
    assert applicability.applicable_to_planned is False
    assert applicability.applicable_to_actual is True

    # Idempotent second call.
    result2 = lm.ensure_environment_outcome_definitions(session)
    session.commit()
    assert result2["definitions_created"] == 0
    assert result2["applicabilities_created"] == 0
    assert result2["applicabilities_corrected"] == 0
    session.close()


def test_ensure_definitions_corrects_pre_existing_planned_true_applicability(seeded_run):
    """WP7 Phase 3 correction (2026-08-14, Charlie's closeout review, finding
    #1): the original (pre-correction) Phase 3 release created these 4
    Global applicability rows with applicable_to_planned=True. Simulates
    that exact pre-correction state and proves a re-run of
    ensure_environment_outcome_definitions() self-heals it to False without
    creating a duplicate applicability row."""
    session = db.get_session()
    result1 = lm.ensure_environment_outcome_definitions(session)
    session.commit()
    assert result1["applicabilities_created"] == 4

    # Simulate the pre-correction (defective) live state.
    session.query(db.ProcessSettingApplicability).update({"applicable_to_planned": True})
    session.commit()

    result2 = lm.ensure_environment_outcome_definitions(session)
    session.commit()
    assert result2["applicabilities_created"] == 0
    assert result2["applicabilities_corrected"] == 4

    still_planned = session.query(db.ProcessSettingApplicability).filter_by(applicable_to_planned=True).count()
    assert still_planned == 0

    total_applicabilities = session.query(db.ProcessSettingApplicability).count()
    assert total_applicabilities == 4, "correction must update existing rows, not create new ones"

    # Idempotent third call: nothing left to correct.
    result3 = lm.ensure_environment_outcome_definitions(session)
    session.commit()
    assert result3["applicabilities_corrected"] == 0
    session.close()


# ---------------------------------------------------------------------------
# 2. backfill_environment_outcome_values - NULL-vs-zero preserved, idempotent
# ---------------------------------------------------------------------------

def test_backfill_environment_outcome_values_preserves_null_vs_zero(seeded_run):
    """WP7 Phase 3 correction (2026-08-14, Charlie's closeout review, finding
    #2): a Setup-phase legacy value for one of these 4 fields is quarantined
    (counted, not migrated) rather than reclassified as a Planned setting -
    only Finalized-phase values migrate, always as 'Actual'. The NULL-vs-zero
    distinction is still proven, now on the Finalized side."""
    ids = seeded_run
    session = db.get_session()

    setup_phase = db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Setup",
        ambient_temperature_c=21.5,
        ambient_humidity_pct=0.0,  # real recorded zero, but Setup-side -> quarantined, not migrated
        foam_height_mm=None,  # genuinely blank - must be skipped, not migrated as 0
        rise_time=45.0,
    )
    finalized_phase = db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Finalized",
        ambient_temperature_c=23.0, ambient_humidity_pct=55.5,
        foam_height_mm=180.0, rise_time=0.0,  # real recorded zero, Finalized-side -> must migrate as 0.0
    )
    session.add_all([setup_phase, finalized_phase])
    session.commit()

    result = lm.backfill_environment_outcome_values(session)
    session.commit()

    assert result["phases_read"] == 2
    # Setup: ambient_temp, ambient_humidity (0.0), rise_time are all quarantined = 3; foam_height skipped (null).
    # Finalized: ambient_temp, ambient_humidity, foam_height, rise_time (0.0) all migrate = 4.
    assert result["values_migrated"] == 4
    assert result["values_quarantined_setup"] == 3
    assert result["values_skipped_null"] == 1

    # Nothing was migrated as "Planned" - actual-only capture.
    planned_count = session.query(db.ProcessParameterValue).filter_by(
        production_run_id=ids["run_id"], snapshot_type="Planned",
    ).count()
    assert planned_count == 0, "Environment/Outcome values must never migrate as Planned settings"

    ps009 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-009").one()
    humidity_rows = session.query(db.ProcessParameterValue).filter_by(
        setting_definition_id=ps009.id, production_run_id=ids["run_id"],
    ).all()
    assert len(humidity_rows) == 1, "only the Finalized-side humidity value migrates; Setup-side is quarantined"
    assert humidity_rows[0].snapshot_type == "Actual"
    assert humidity_rows[0].numeric_value == 55.5

    ps079 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-079").one()
    rise_time_rows = session.query(db.ProcessParameterValue).filter_by(
        setting_definition_id=ps079.id, production_run_id=ids["run_id"],
    ).all()
    assert len(rise_time_rows) == 1
    assert rise_time_rows[0].numeric_value == 0.0, "a real recorded Finalized-side zero must persist, not be dropped"

    ps078 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-078").one()
    foam_height_rows = session.query(db.ProcessParameterValue).filter_by(
        setting_definition_id=ps078.id, production_run_id=ids["run_id"],
    ).all()
    assert len(foam_height_rows) == 1
    assert foam_height_rows[0].snapshot_type == "Actual"
    assert foam_height_rows[0].numeric_value == 180.0
    assert foam_height_rows[0].source == "WP7 Phase 3 migration"

    # Idempotent re-run: no duplicates, everything already-present; Setup
    # values are re-counted as quarantined each run (report-only, matching
    # quarantine_air_settings_report's own report-not-state convention).
    result2 = lm.backfill_environment_outcome_values(session)
    session.commit()
    assert result2["values_migrated"] == 0
    assert result2["values_already_present"] == 4
    assert result2["values_quarantined_setup"] == 3
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


# ---------------------------------------------------------------------------
# 6. WP7 Phase 3 correction (2026-08-14, Charlie's closeout review) - direct
#    UI evidence that Environment/Outcome definitions never render as
#    enterable Planned/Actual process settings, while a true Process Setting
#    definition still renders normally (acceptance criterion #2).
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_env_outcome_and_process_setting(seeded_run):
    """Extends seeded_run with: (a) the corrected Environment/Outcome
    catalogue via ensure_environment_outcome_definitions() (actual-only,
    Global-scoped - eligible for any run), and (b) one ordinary
    Method-scoped Process Setting definition/applicability, following the
    same pattern as test_wp7_phase2_production_run_ui.py's
    seeded_method_setting fixture - the minimum content needed to prove the
    UI tab renders one and excludes the other."""
    ids = seeded_run
    session = db.get_session()
    lm.ensure_environment_outcome_definitions(session)
    session.commit()

    unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P3C-{ids['run_id']}", symbol="rpm", name="revolutions per minute")
    session.add(unit); session.flush()
    process_setting = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P3C-{ids['run_id']}", name="Test Mixer Speed", data_type="Float",
        unit_id=unit.id, parameter_category="Process Setting", active=True, sort_order=1,
    )
    session.add(process_setting); session.flush()
    applicability = db.ProcessSettingApplicability(
        setting_definition_id=process_setting.id, production_method_id=ids["method_id"],
        applicable_to_planned=True, applicable_to_actual=True, controllable=True,
        analytics_eligible=True, active=True,
    )
    session.add(applicability); session.commit()

    ps008 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-008").one()
    ps078 = session.query(db.ProcessSettingDefinition).filter_by(controlled_id="PS-078").one()

    out = dict(ids)
    out["process_setting_definition_id"] = process_setting.id
    out["ps008_id"] = ps008.id
    out["ps078_id"] = ps078.id
    session.close()
    return out


def test_method_settings_tab_excludes_environment_outcome_but_shows_process_setting(seeded_env_outcome_and_process_setting):
    """Direct UI proof of the correction: the Method-Aware Process Settings
    tab must not render any widget for PS-008 (Environment) or PS-078
    (Outcome), even though both are eligible by Machine>Method>Global
    precedence, while the ordinary Process Setting definition renders
    normally with both Planned and Actual inputs - exactly Charlie's
    acceptance criterion #2 wording."""
    ids = seeded_env_outcome_and_process_setting
    at = _run_page4({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    for excluded_id in (ids["ps008_id"], ids["ps078_id"]):
        assert not any(
            w.key and w.key.startswith(f"pps_{excluded_id}_") for w in at.number_input
        ), f"Environment/Outcome definition {excluded_id} must not render as a process setting input"

    process_setting_id = ids["process_setting_definition_id"]
    planned_key = f"pps_{process_setting_id}_Planned_{ids['run_id']}"
    actual_key = f"pps_{process_setting_id}_Actual_{ids['run_id']}"
    assert any(w.key == planned_key for w in at.number_input), "true Process Setting definition must still render (Planned)"
    assert any(w.key == actual_key for w in at.number_input), "true Process Setting definition must still render (Actual)"


def test_runtime_tab_observations_section_renders_environment_outcome_but_not_process_setting(seeded_env_outcome_and_process_setting):
    """WP7 Phase 5 gap-fix direct UI proof: the new 'Observations
    (Environment & Outcome)' block on the Runtime Data tab must render one
    Actual-value widget for each eligible Environment/Outcome definition
    (PS-008 ambient temperature, PS-078 foam height - both Float, both
    eligible via the Global applicability seeded by
    ensure_environment_outcome_definitions()), keyed
    obs_{definition_id}_Actual_{run_id} - and must NOT render the ordinary
    Process Setting definition there (that one belongs on the Method-Aware
    tab only, per the sibling test above). This is the closure of the gap
    left by v0.59.0's legacy ProductionPhase widget removal combined with
    the pre-existing WP7 Phase 3 correction's Environment/Outcome exclusion
    from the Method-Aware tab - see pages/4's own comment above this
    block and Decision Ledger D5-06 in the Phase 5 contract."""
    ids = seeded_env_outcome_and_process_setting
    at = _run_page4({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    for env_id in (ids["ps008_id"], ids["ps078_id"]):
        widget_key = f"obs_{env_id}_Actual_{ids['run_id']}"
        assert any(w.key == widget_key for w in at.number_input), (
            f"Environment/Outcome definition {env_id} must render as an Observations input"
        )

    process_setting_id = ids["process_setting_definition_id"]
    assert not any(
        w.key and w.key.startswith(f"obs_{process_setting_id}_") for w in at.number_input
    ), "true Process Setting definition must not render in the Observations section"


def test_runtime_tab_observations_form_saves_actual_value(seeded_env_outcome_and_process_setting):
    """Direct evidence the new capture path actually persists: filling and
    submitting the Observations form for PS-078 (Foam height, Outcome)
    creates a ProcessParameterValue row with snapshot_type='Actual' and
    source='Manual entry' - the only live way, post-WP7-Phase-5, to record a
    new measured Environment/Outcome value for a production run (the legacy
    ProductionPhase ambient/outcome widgets were retired in the same batch
    that created this gap; Decision Ledger D5-06 requires this class to
    remain ACTIVE / canonical Actual observations)."""
    ids = seeded_env_outcome_and_process_setting
    session = db.get_session()
    before = session.query(db.ProcessParameterValue).filter_by(
        production_run_id=ids["run_id"], setting_definition_id=ids["ps078_id"]
    ).count()
    assert before == 0
    session.close()

    at = _run_page4({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    form_key = f"observations_form_{ids['run_id']}"
    widget_key = f"obs_{ids['ps078_id']}_Actual_{ids['run_id']}"
    at.checkbox(key=f"{widget_key}_recorded").set_value(True)
    at.number_input(key=widget_key).set_value(42.5)
    submit = _submit_key(at, form_key, "Save observations")
    submit.click().run()
    assert not at.exception

    session = db.get_session()
    saved = session.query(db.ProcessParameterValue).filter_by(
        production_run_id=ids["run_id"], setting_definition_id=ids["ps078_id"], snapshot_type="Actual"
    ).one()
    assert saved.numeric_value == 42.5
    assert saved.source == "Manual entry"
    assert saved.unit == "mm"
    session.close()
