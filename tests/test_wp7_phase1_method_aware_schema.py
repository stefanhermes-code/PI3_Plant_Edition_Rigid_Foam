"""WP7 Phase 1 (Add method-aware schema, 2026-08-13) regression tests.

Proves the Phase 1 closeout gate defined in Charlie's WP7 Phase 1 Design
Review and Architecture Decision (PI3_Rigid_Foam_Development_Docs/Phase 1/
WP7_Phase1_Design_Review_Architecture_Decision_for_JC.docx, section 6),
against the actual db.py/analytics.py implementation of that decision -
not JC's original (superseded) Phase 1 design proposal.

Each test below is numbered to match that section 6 acceptance list:

  1. One canonical ProcessSettingDefinition can serve more than one
     Production Method through applicability rows, without duplicating
     the definition.
  2. eligible_process_settings() returns one deterministic parameter set
     for a run, with Machine-specific applicability taking precedence
     over Method-specific and Global applicability for the same
     definition.
  3. Planned and Actual ProcessParameterValue rows remain distinct and
     retain source plus captured_at metadata.
  4. Parameter UOM is controlled by the definition - ProcessParameterValue
     has no independent free-entry UOM field of its own (its `unit` column
     is a text snapshot only, not a second controlled FK).
  5. ProductionOutputSummary persists Planned and Actual quantity in one
     controlled UOM (a single unit_id FK, not two free-text unit fields)
     and a controlled disposition (PRODUCTION_OUTPUT_DISPOSITIONS).
  6. ComponentStreamReading can link directly to ProductionRun while
     existing ProductionPhase-linked rows remain readable.
  7. ProductionEvent supports optional parameter, raw-material and quality
     context links without changing existing (pre-Phase-1) event behavior.
  8. No Production Run UI, report, PI3 or Industrial Intelligence behavior
     is cut over in Phase 1 - source-grep proof that the new schema/helper
     is not yet referenced live outside db.py/analytics.py.
  9. (Full-suite, zero-skip acceptance is proven by the full regression
     run itself, not by an individual test in this file.)

MANDATORY TEMPLATE: tests/test_wp7_phase0_containment.py (AUTH_DISABLED/
sqlite:// boilerplate, _reset_schema(), seeded_grade_chain -> seeded_run
fixture chain, source-grep-with-allowlist pattern).

Usage: python -m pytest tests/test_wp7_phase1_method_aware_schema.py -v
"""
import datetime as dt
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import access_control
import analytics
import db
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE4 = os.path.join(APP_DIR, "pages", "4_Production_Run_Trial_Record.py")
REPORTS_PY = os.path.join(APP_DIR, "reports.py")
INTELLIGENCE_PAGES = [
    os.path.join(APP_DIR, "pages", f)
    for f in os.listdir(os.path.join(APP_DIR, "pages"))
    if f.startswith(("15_", "16_", "17_", "18_", "19_"))
]


def _clear_relevant_caches():
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    _clear_relevant_caches()


# ---------------------------------------------------------------------------
# Fixtures - same dependency chain as test_wp7_phase0_containment.py
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_grade_chain():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P1 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P1 Plant {u}")
    session.add(plant); session.flush()

    method_a = db.ProductionMethod(controlled_id=f"PM-WP7P1A-{u}", name=f"WP7P1 Method A {u}")
    method_b = db.ProductionMethod(controlled_id=f"PM-WP7P1B-{u}", name=f"WP7P1 Method B {u}")
    session.add_all([method_a, method_b]); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method_a.id, active=True))
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method_b.id, active=True))
    session.flush()

    machine = db.Machine(
        plant_id=plant.id, name=f"WP7P1 Machine {u}", production_method_id=method_a.id, active=True,
    )
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P1 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P1 Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True,
    )
    session.add(recipe); session.flush()

    unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P1-{u}", symbol="kg", name="Kilograms")
    session.add(unit); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "method_a_id": method_a.id, "method_b_id": method_b.id,
        "machine_id": machine.id, "family_id": family.id, "grade_id": grade.id,
        "recipe_version_id": recipe.id, "unit_id": unit.id,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_run(seeded_grade_chain):
    ids = seeded_grade_chain
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
        recipe_version_id=ids["recipe_version_id"], run_date=dt.date(2026, 8, 1),
        batch_reference=f"B-WP7P1-{uuid.uuid4().hex[:8]}", machine_id=ids["machine_id"],
        production_method_id=ids["method_a_id"], operator_or_team_reference="Shift A",
    )
    session.add(run); session.commit()
    out = dict(ids)
    out["run_id"] = run.id
    session.close()
    return out


# ---------------------------------------------------------------------------
# 1. One definition, multiple Methods, via applicability rows (no duplication)
# ---------------------------------------------------------------------------

def test_one_definition_serves_multiple_methods_via_applicability_rows(seeded_grade_chain):
    ids = seeded_grade_chain
    session = db.get_session()

    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P1-{uuid.uuid4().hex[:6]}", name="Fill pressure",
        data_type="Float", unit_id=ids["unit_id"], parameter_category="Process Setting",
    )
    session.add(definition); session.flush()

    session.add(db.ProcessSettingApplicability(
        setting_definition_id=definition.id, production_method_id=ids["method_a_id"],
    ))
    session.add(db.ProcessSettingApplicability(
        setting_definition_id=definition.id, production_method_id=ids["method_b_id"],
    ))
    session.commit()

    definition_count = session.query(db.ProcessSettingDefinition).filter(
        db.ProcessSettingDefinition.id == definition.id
    ).count()
    assert definition_count == 1, "one canonical definition must not be duplicated per Method"

    applicability_count = session.query(db.ProcessSettingApplicability).filter(
        db.ProcessSettingApplicability.setting_definition_id == definition.id
    ).count()
    assert applicability_count == 2

    eligible_a = analytics.eligible_process_settings(session, ids["method_a_id"])
    eligible_b = analytics.eligible_process_settings(session, ids["method_b_id"])
    assert any(d.id == definition.id for d, _app in eligible_a)
    assert any(d.id == definition.id for d, _app in eligible_b)
    session.close()


# ---------------------------------------------------------------------------
# 2. Deterministic precedence: Machine > Method > Global, one row per definition
# ---------------------------------------------------------------------------

def test_eligibility_precedence_machine_over_method_over_global(seeded_grade_chain):
    ids = seeded_grade_chain
    session = db.get_session()

    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P1-{uuid.uuid4().hex[:6]}", name="Mix temperature",
        data_type="Float", unit_id=ids["unit_id"], parameter_category="Process Setting",
    )
    session.add(definition); session.flush()

    app_global = db.ProcessSettingApplicability(setting_definition_id=definition.id, min_value_override=10.0)
    app_method = db.ProcessSettingApplicability(
        setting_definition_id=definition.id, production_method_id=ids["method_a_id"], min_value_override=20.0,
    )
    app_machine = db.ProcessSettingApplicability(
        setting_definition_id=definition.id, machine_id=ids["machine_id"], min_value_override=30.0,
    )
    session.add_all([app_global, app_method, app_machine])
    session.commit()

    # Machine + Method both match -> Machine-specific wins.
    eligible = analytics.eligible_process_settings(session, ids["method_a_id"], machine_id=ids["machine_id"])
    winners = {d.id: app for d, app in eligible}
    assert winners[definition.id].id == app_machine.id
    assert winners[definition.id].min_value_override == 30.0

    # Method only (no machine given) -> Method-specific wins over Global.
    eligible = analytics.eligible_process_settings(session, ids["method_a_id"])
    winners = {d.id: app for d, app in eligible}
    assert winners[definition.id].id == app_method.id

    # Unrelated Method, no machine -> only Global remains eligible.
    eligible = analytics.eligible_process_settings(session, ids["method_b_id"])
    winners = {d.id: app for d, app in eligible}
    assert winners[definition.id].id == app_global.id

    # Exactly one eligible row per definition, never more.
    eligible = analytics.eligible_process_settings(session, ids["method_a_id"], machine_id=ids["machine_id"])
    def_ids = [d.id for d, _app in eligible]
    assert len(def_ids) == len(set(def_ids))
    session.close()


def test_inactive_definition_or_applicability_never_surfaces(seeded_grade_chain):
    ids = seeded_grade_chain
    session = db.get_session()

    retired_definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P1-{uuid.uuid4().hex[:6]}", name="Retired setting",
        data_type="Float", parameter_category="Process Setting", active=False,
    )
    session.add(retired_definition); session.flush()
    session.add(db.ProcessSettingApplicability(setting_definition_id=retired_definition.id))

    live_definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P1-{uuid.uuid4().hex[:6]}", name="Live setting with retired applicability",
        data_type="Float", parameter_category="Process Setting",
    )
    session.add(live_definition); session.flush()
    session.add(db.ProcessSettingApplicability(setting_definition_id=live_definition.id, active=False))
    session.commit()

    eligible = analytics.eligible_process_settings(session, ids["method_a_id"])
    eligible_ids = {d.id for d, _app in eligible}
    assert retired_definition.id not in eligible_ids
    assert live_definition.id not in eligible_ids
    session.close()


# ---------------------------------------------------------------------------
# 3. Planned/Actual ProcessParameterValue stay distinct, with source + captured_at
# ---------------------------------------------------------------------------

def test_planned_and_actual_values_distinct_with_source_and_captured_at(seeded_run):
    ids = seeded_run
    session = db.get_session()

    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P1-{uuid.uuid4().hex[:6]}", name="Line speed",
        data_type="Float", unit_id=ids["unit_id"], parameter_category="Process Setting",
    )
    session.add(definition); session.flush()

    planned = db.ProcessParameterValue(
        setting_definition_id=definition.id, production_run_id=ids["run_id"],
        snapshot_type="Planned", numeric_value=12.0, source="Manual entry",
        captured_at=dt.datetime(2026, 8, 1, 6, 0),
    )
    actual = db.ProcessParameterValue(
        setting_definition_id=definition.id, production_run_id=ids["run_id"],
        snapshot_type="Actual", numeric_value=11.4, source="Machine capture",
        captured_at=dt.datetime(2026, 8, 1, 6, 30),
    )
    session.add_all([planned, actual]); session.commit()

    rows = session.query(db.ProcessParameterValue).filter(
        db.ProcessParameterValue.setting_definition_id == definition.id
    ).order_by(db.ProcessParameterValue.snapshot_type).all()
    assert len(rows) == 2
    by_type = {r.snapshot_type: r for r in rows}
    assert by_type["Planned"].numeric_value == 12.0
    assert by_type["Planned"].source == "Manual entry"
    assert by_type["Planned"].captured_at == dt.datetime(2026, 8, 1, 6, 0)
    assert by_type["Actual"].numeric_value == 11.4
    assert by_type["Actual"].source == "Machine capture"
    assert by_type["Actual"].captured_at == dt.datetime(2026, 8, 1, 6, 30)
    session.close()


# ---------------------------------------------------------------------------
# 4. Parameter UOM controlled by the definition, not a free-entry field
# ---------------------------------------------------------------------------

def test_process_parameter_value_has_no_independent_uom_fk(seeded_run):
    """ProcessParameterValue.unit is a text snapshot only (auto-filled from
    the definition's controlled unit_id at entry time) - there is no
    separate ProcessParameterValue.unit_id FK a caller could set to a
    different, conflicting unit."""
    assert not hasattr(db.ProcessParameterValue, "unit_id")
    assert hasattr(db.ProcessSettingDefinition, "unit_id")

    ids = seeded_run
    session = db.get_session()
    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P1-{uuid.uuid4().hex[:6]}", name="Fill weight",
        data_type="Float", unit_id=ids["unit_id"], parameter_category="Process Setting",
    )
    session.add(definition); session.flush()

    definition_unit_symbol = session.query(db.UnitOfMeasure).get(ids["unit_id"]).symbol
    value = db.ProcessParameterValue(
        setting_definition_id=definition.id, production_run_id=ids["run_id"],
        snapshot_type="Actual", numeric_value=5.2, unit=definition_unit_symbol,
    )
    session.add(value); session.commit()

    reloaded = session.query(db.ProcessParameterValue).get(value.id)
    assert reloaded.unit == definition_unit_symbol
    assert reloaded.setting_definition.unit_id == ids["unit_id"]
    session.close()


# ---------------------------------------------------------------------------
# 5. ProductionOutputSummary: single controlled UOM, controlled disposition
# ---------------------------------------------------------------------------

def test_production_output_summary_single_controlled_uom_and_disposition(seeded_run):
    assert not hasattr(db.ProductionOutputSummary, "planned_unit")
    assert not hasattr(db.ProductionOutputSummary, "actual_unit")
    assert hasattr(db.ProductionOutputSummary, "unit_id")

    ids = seeded_run
    session = db.get_session()
    summary = db.ProductionOutputSummary(
        production_run_id=ids["run_id"], planned_quantity=500.0, actual_quantity=487.5,
        unit_id=ids["unit_id"], disposition="Released",
    )
    assert summary.disposition in db.PRODUCTION_OUTPUT_DISPOSITIONS
    session.add(summary); session.commit()

    reloaded = session.query(db.ProductionOutputSummary).filter(
        db.ProductionOutputSummary.production_run_id == ids["run_id"]
    ).one()
    assert reloaded.unit_id == ids["unit_id"]
    assert reloaded.unit.symbol == "kg"
    # Planned and Actual are directly comparable - same unit_id governs both.
    assert reloaded.planned_quantity == 500.0
    assert reloaded.actual_quantity == 487.5
    assert reloaded.disposition == "Released"
    session.close()


# ---------------------------------------------------------------------------
# 6. ComponentStreamReading: direct ProductionRun link + legacy rows readable
# ---------------------------------------------------------------------------

def test_component_stream_reading_direct_run_link_and_legacy_rows_readable(seeded_run):
    ids = seeded_run
    session = db.get_session()

    # Legacy-style row: production_phase_id set, production_run_id NULL -
    # standing in for data written before this Phase 1 change shipped.
    phase = db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Setup",
        phase_start=dt.datetime(2026, 8, 1, 6, 0),
    )
    session.add(phase); session.flush()
    legacy_reading = db.ComponentStreamReading(
        production_phase_id=phase.id, stream_name="Polyol A", flow=10.0,
    )
    session.add(legacy_reading); session.flush()

    # New Phase-2-era row: production_run_id set directly, no phase.
    new_reading = db.ComponentStreamReading(
        production_run_id=ids["run_id"], stream_name="Isocyanate", flow=8.5,
    )
    session.add(new_reading); session.commit()

    reloaded_legacy = session.query(db.ComponentStreamReading).get(legacy_reading.id)
    assert reloaded_legacy.production_phase_id == phase.id
    assert reloaded_legacy.production_run_id is None
    assert reloaded_legacy.phase.id == phase.id  # legacy relationship still resolves

    reloaded_new = session.query(db.ComponentStreamReading).get(new_reading.id)
    assert reloaded_new.production_run_id == ids["run_id"]
    assert reloaded_new.production_phase_id is None
    assert reloaded_new.production_run.id == ids["run_id"]  # new relationship resolves
    session.close()


# ---------------------------------------------------------------------------
# 7. ProductionEvent: optional context links, existing behavior unchanged
# ---------------------------------------------------------------------------

def test_production_event_optional_context_links_and_legacy_behavior_unchanged(seeded_run):
    ids = seeded_run
    session = db.get_session()

    # Pre-Phase-1-style event: none of the optional context FKs set.
    legacy_event = db.ProductionEvent(
        production_run_id=ids["run_id"], event_ts=dt.datetime(2026, 8, 1, 7, 0),
        event_type="Deviation", severity="Medium", description="Pre-existing event, no context links",
    )
    session.add(legacy_event); session.commit()
    reloaded_legacy = session.query(db.ProductionEvent).get(legacy_event.id)
    assert reloaded_legacy.setting_definition_id is None
    assert reloaded_legacy.raw_material_lot_use_id is None
    assert reloaded_legacy.quality_observation_id is None
    assert reloaded_legacy.physical_property_result_id is None
    assert reloaded_legacy.description == "Pre-existing event, no context links"

    # New event with all 4 optional context links populated.
    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P1-{uuid.uuid4().hex[:6]}", name="Context-linked setting",
        data_type="Float", parameter_category="Process Setting",
    )
    session.add(definition); session.flush()
    lot_use = db.RawMaterialLotUse(
        production_run_id=ids["run_id"], component_stream_name="Polyol A", supplier_lot_no="LOT-001",
    )
    quality_obs = db.QualityObservation(production_run_id=ids["run_id"], observation_type="Shrinkage")
    property_result = db.PhysicalPropertyResult(production_run_id=ids["run_id"], property_name="Density")
    session.add_all([lot_use, quality_obs, property_result]); session.flush()

    contextual_event = db.ProductionEvent(
        production_run_id=ids["run_id"], event_ts=dt.datetime(2026, 8, 1, 8, 0),
        event_type="Deviation", severity="High", description="Context-linked event",
        setting_definition_id=definition.id, raw_material_lot_use_id=lot_use.id,
        quality_observation_id=quality_obs.id, physical_property_result_id=property_result.id,
    )
    session.add(contextual_event); session.commit()

    reloaded = session.query(db.ProductionEvent).get(contextual_event.id)
    assert reloaded.setting_definition.id == definition.id
    assert reloaded.raw_material_lot_use.id == lot_use.id
    assert reloaded.quality_observation.id == quality_obs.id
    assert reloaded.physical_property_result.id == property_result.id
    session.close()


# ---------------------------------------------------------------------------
# 8. No Report/Intelligence cutover in Phase 1
#
# WP7 Phase 2 (2026-08-14) legitimately wired this Phase 1 schema into
# pages/4 (the Method-Aware Process Settings tab calls
# analytics.eligible_process_settings(); the Production Output and
# Disposition tab uses ProductionOutputSummary/PRODUCTION_OUTPUT_
# DISPOSITIONS) - that is exactly the Phase 2 scope per the WP7 governing
# doc section 6 ("Implement context-first run creation/editing, dynamic
# Planned/Actual process grid, ... output and disposition"). PAGE4 was
# removed from this test's parametrize list for that reason; the
# assertion still holds for the Report page and Industrial Intelligence
# pages, which remain out of scope until Phase 4's reader cutover.
# ---------------------------------------------------------------------------

_PHASE1_SCHEMA_TOKEN_RE = re.compile(
    r"\b(ProcessSettingApplicability|eligible_process_settings|ProductionOutputSummary|"
    r"PROCESS_PARAMETER_CATEGORIES|PRODUCTION_OUTPUT_DISPOSITIONS)\b"
)


def _live_code_hits(path):
    """Same technique as test_wp7_phase0_containment.py's source-grep: flag
    any non-comment, non-docstring line referencing a Phase 1 schema/helper
    symbol. Phase 1 is schema-only - these symbols must not yet be wired
    into live UI/report/Intelligence code paths."""
    hits = []
    in_triple_quote = False
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            stripped = line.strip()
            triple_markers = stripped.count('"""') + stripped.count("'''")
            if in_triple_quote:
                if triple_markers % 2 == 1:
                    in_triple_quote = False
                continue
            if triple_markers % 2 == 1:
                in_triple_quote = True
                continue
            if stripped.startswith("#"):
                continue
            code_part = line.split("#", 1)[0]
            if _PHASE1_SCHEMA_TOKEN_RE.search(code_part):
                hits.append((lineno, stripped))
    return hits


@pytest.mark.parametrize("path", [REPORTS_PY] + INTELLIGENCE_PAGES)
def test_phase1_schema_not_yet_wired_into_live_surfaces(path):
    hits = _live_code_hits(path)
    assert hits == [], f"Phase 1 schema/helper referenced in live code before Phase 4 cutover in {path}: {hits}"
