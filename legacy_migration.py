"""WP7 Phase 3 (2026-08-14): Legacy data reconciliation and migration
helpers, per the WP7 Phase 1 Design Deliverables doc's section 5/6.3 and
Charlie's WP7 Phase 1 Design Review and Architecture Decision, section
3.4 and section 4 (PI3_Rigid_Foam_Development_Docs/Phase 1/).

Scope - what this module DOES migrate (the design doc's own "no
ambiguity" classes):

- Environment mapping: ProductionPhase.ambient_temperature_c/
  ambient_humidity_pct -> ProcessSettingDefinition (parameter_category=
  "Environment") + ProcessParameterValue, reusing the existing dormant
  WP3f PS-008/PS-009 definitions rather than duplicating them.
- Outcome/observation: ProductionPhase.foam_height_mm/rise_time ->
  new ProcessSettingDefinition rows (parameter_category="Outcome").
- ComponentStreamReading.production_run_id backfill from its existing
  ProductionPhase relationship (decision doc section 3.4).

Scope - what this module explicitly does NOT migrate (deferred by
Charlie's decision doc section 4, "Deferred to evidence-based
migration" / "Remain under Method-specific review" / "Remain
quarantined for semantic review" - do not seed speculative PM-*
mappings):

- ProductionPhase.mixer_rpm, conveyor_speed, sidewall_width_mm
  ("Conditional Method-specific migrate" - needs an evidenced,
  approved Production Method mapping that does not exist yet).
- ProductionPhase.air_injection_rate, air_pressure_bar ("Quarantine/
  manual review" - quarantine_air_settings_report() below surfaces
  these for review, never auto-migrates them).
- ProductionRun.block_reference ("Method-specific review" - a
  documentation/definition question, not a schema migration, and out
  of this module's scope entirely).

Every function here is idempotent - safe to call more than once, and
safe to call against a database with zero legacy rows (in which case
every reconciliation count is honestly 0, not an error)."""

from db import (
    ComponentStreamReading,
    ProcessParameterValue,
    ProcessSettingApplicability,
    ProcessSettingDefinition,
    ProductionPhase,
    UnitOfMeasure,
)

# ProductionPhase column -> target ProcessSettingDefinition. controlled_id
# PS-008/PS-009 are the pre-existing dormant WP3f rows (see db.py's
# ProcessSettingDefinition class docstring on why they must be reused, not
# duplicated); PS-078/PS-079 are new (no prior WP3f row covers foam height
# or rise time - the highest pre-existing controlled_id was PS-077).
ENVIRONMENT_OUTCOME_FIELD_MAP = {
    "ambient_temperature_c": {
        "controlled_id": "PS-008",
        "name": "Ambient temperature",
        "category": "Environment",
        "unit_symbol": "degC",
    },
    "ambient_humidity_pct": {
        "controlled_id": "PS-009",
        "name": "Relative humidity",
        "category": "Environment",
        "unit_symbol": "%",
    },
    "foam_height_mm": {
        "controlled_id": "PS-078",
        "name": "Foam height",
        "category": "Outcome",
        "unit_symbol": "mm",
    },
    "rise_time": {
        "controlled_id": "PS-079",
        "name": "Rise time",
        "category": "Outcome",
        "unit_symbol": "s",
    },
}

# None of these 4 plain units existed in units_of_measure before WP7 Phase 3
# - only compound/domain-specific units did (e.g. UOM-031 "wt%" for weight
# percent, not a plain relative-humidity "%"). Added here as controlled
# master data, following the existing UOM-0xx numbering convention (highest
# pre-existing was UOM-037).
ENVIRONMENT_OUTCOME_UOMS = [
    {"controlled_id": "UOM-038", "symbol": "s", "name": "second"},
    {"controlled_id": "UOM-039", "symbol": "mm", "name": "millimetre"},
    {"controlled_id": "UOM-040", "symbol": "degC", "name": "degree Celsius"},
    {"controlled_id": "UOM-041", "symbol": "%", "name": "percent"},
]


def ensure_environment_outcome_uoms(session):
    """Idempotent: create any of ENVIRONMENT_OUTCOME_UOMS not already
    present (matched by controlled_id). Returns the number created."""
    created = 0
    for row in ENVIRONMENT_OUTCOME_UOMS:
        existing = session.query(UnitOfMeasure).filter_by(controlled_id=row["controlled_id"]).first()
        if existing is None:
            session.add(UnitOfMeasure(**row))
            created += 1
    session.flush()
    return created


def ensure_environment_outcome_definitions(session):
    """Idempotent: for each ProductionPhase field in
    ENVIRONMENT_OUTCOME_FIELD_MAP, ensure a ProcessSettingDefinition
    exists (reusing the existing dormant WP3f PS-008/PS-009 rows for the
    two Environment fields, per the module docstring), with
    parameter_category set and a Global (production_method_id NULL,
    machine_id NULL) ProcessSettingApplicability row with
    controllable=False, analytics_eligible=False - both classes are
    measured outcomes/environment readings, never controllable settings,
    per the WP7 Phase 1 design doc's own disposition.

    Returns {"definitions_created": n, "definitions_updated": n,
    "applicabilities_created": n}."""
    ensure_environment_outcome_uoms(session)
    uom_by_symbol = {u.symbol: u for u in session.query(UnitOfMeasure).all()}

    definitions_created = 0
    definitions_updated = 0
    applicabilities_created = 0

    for spec in ENVIRONMENT_OUTCOME_FIELD_MAP.values():
        definition = (
            session.query(ProcessSettingDefinition)
            .filter_by(controlled_id=spec["controlled_id"])
            .first()
        )
        unit = uom_by_symbol.get(spec["unit_symbol"])
        if definition is None:
            definition = ProcessSettingDefinition(
                controlled_id=spec["controlled_id"],
                name=spec["name"],
                data_type="Float",
                unit_id=unit.id if unit else None,
                parameter_category=spec["category"],
                active=True,
            )
            session.add(definition)
            session.flush()
            definitions_created += 1
        else:
            changed = False
            if definition.parameter_category != spec["category"]:
                definition.parameter_category = spec["category"]
                changed = True
            if definition.unit_id is None and unit is not None:
                definition.unit_id = unit.id
                changed = True
            if changed:
                definitions_updated += 1

        applicability = (
            session.query(ProcessSettingApplicability)
            .filter_by(setting_definition_id=definition.id, production_method_id=None, machine_id=None)
            .first()
        )
        if applicability is None:
            session.add(ProcessSettingApplicability(
                setting_definition_id=definition.id,
                production_method_id=None,
                machine_id=None,
                applicable_to_planned=True,
                applicable_to_actual=True,
                controllable=False,
                analytics_eligible=False,
                active=True,
            ))
            applicabilities_created += 1

    session.flush()
    return {
        "definitions_created": definitions_created,
        "definitions_updated": definitions_updated,
        "applicabilities_created": applicabilities_created,
    }


def backfill_environment_outcome_values(session):
    """One-time backfill (idempotent - safe to re-run): for every
    ProductionPhase row, for each of the 4 unambiguous fields in
    ENVIRONMENT_OUTCOME_FIELD_MAP that is non-null, ensure a matching
    ProcessParameterValue row exists (snapshot_type 'Planned' for a
    'Setup' phase, 'Actual' for a 'Finalized' phase - mirrors the
    Setup/Finalized <-> Planned/Actual convention already used
    everywhere else in this schema).

    Preserves the NULL-vs-zero distinction explicitly (WP7 governing doc
    section 9, and this project's established Gap-1 pattern): only a
    field that is None on the ProductionPhase row is skipped; a field
    holding 0.0 migrates as a real numeric_value == 0.0.

    Calls ensure_environment_outcome_definitions() first so this can be
    invoked standalone. Returns a reconciliation dict: {"phases_read": n,
    "values_migrated": n, "values_already_present": n,
    "values_skipped_null": n} - the exact evidence shape the WP7 Phase 1
    design doc's section 5.1 requires for this migration class."""
    ensure_environment_outcome_definitions(session)
    definitions_by_field = {
        field: session.query(ProcessSettingDefinition).filter_by(controlled_id=spec["controlled_id"]).one()
        for field, spec in ENVIRONMENT_OUTCOME_FIELD_MAP.items()
    }

    phases_read = 0
    values_migrated = 0
    values_already_present = 0
    values_skipped_null = 0

    for phase in session.query(ProductionPhase).all():
        phases_read += 1
        snapshot_type = "Planned" if phase.phase_name == "Setup" else "Actual"
        for field, definition in definitions_by_field.items():
            value = getattr(phase, field)
            if value is None:
                values_skipped_null += 1
                continue
            existing = (
                session.query(ProcessParameterValue)
                .filter_by(
                    setting_definition_id=definition.id,
                    production_run_id=phase.production_run_id,
                    snapshot_type=snapshot_type,
                )
                .first()
            )
            if existing is not None:
                values_already_present += 1
                continue
            session.add(ProcessParameterValue(
                setting_definition_id=definition.id,
                production_run_id=phase.production_run_id,
                snapshot_type=snapshot_type,
                numeric_value=value,
                source="WP7 Phase 3 migration",
                notes=f"Backfilled from production_phases.id={phase.id} ({field})",
            ))
            values_migrated += 1

    session.flush()
    return {
        "phases_read": phases_read,
        "values_migrated": values_migrated,
        "values_already_present": values_already_present,
        "values_skipped_null": values_skipped_null,
    }


def backfill_component_stream_reading_run_ids(session):
    """WP7 Phase 3, per Charlie's decision doc section 3.4: backfill
    production_run_id on every historical ComponentStreamReading that has
    a production_phase_id but no production_run_id yet, via its existing
    ProductionPhase relationship. Idempotent - only touches rows where
    production_run_id is currently NULL. Returns {"readings_read": n,
    "readings_backfilled": n, "readings_skipped_no_phase": n}."""
    readings_read = 0
    readings_backfilled = 0
    readings_skipped_no_phase = 0

    rows = (
        session.query(ComponentStreamReading)
        .filter(ComponentStreamReading.production_phase_id.isnot(None))
        .filter(ComponentStreamReading.production_run_id.is_(None))
        .all()
    )
    for reading in rows:
        readings_read += 1
        phase = reading.phase
        if phase is None:
            readings_skipped_no_phase += 1
            continue
        reading.production_run_id = phase.production_run_id
        readings_backfilled += 1

    session.flush()
    return {
        "readings_read": readings_read,
        "readings_backfilled": readings_backfilled,
        "readings_skipped_no_phase": readings_skipped_no_phase,
    }


def quarantine_air_settings_report(session):
    """WP7 Phase 3, per the WP7 Phase 1 design doc's section 5.1: produce
    a report of every non-null air_injection_rate/air_pressure_bar value
    for Charlie's semantic review - explicitly NOT auto-migrated
    (Charlie's decision doc section 4: "Remain quarantined for semantic
    review. No automatic mapping."). Returns a list of dicts, one per
    ProductionPhase row that has at least one of the two fields set."""
    report = []
    rows = (
        session.query(ProductionPhase)
        .filter(
            (ProductionPhase.air_injection_rate.isnot(None))
            | (ProductionPhase.air_pressure_bar.isnot(None))
        )
        .all()
    )
    for phase in rows:
        report.append({
            "production_phase_id": phase.id,
            "production_run_id": phase.production_run_id,
            "phase_name": phase.phase_name,
            "air_injection_rate": phase.air_injection_rate,
            "air_pressure_bar": phase.air_pressure_bar,
        })
    return report


def phase3_reconciliation_summary(session):
    """Runs every WP7 Phase 3 reconciliation step in order and returns
    one combined summary dict - the exact evidence shape the Phase 3
    closeout package presents. Deliberately does not touch mixer_rpm/
    conveyor_speed/sidewall_width_mm/block_reference - see this module's
    docstring for why those remain explicitly deferred pending Charlie's
    evidence-based approval."""
    definitions = ensure_environment_outcome_definitions(session)
    values = backfill_environment_outcome_values(session)
    streams = backfill_component_stream_reading_run_ids(session)
    quarantine = quarantine_air_settings_report(session)
    return {
        "environment_outcome_definitions": definitions,
        "environment_outcome_values": values,
        "component_stream_reading_backfill": streams,
        "quarantine_air_settings_count": len(quarantine),
        "quarantine_air_settings_report": quarantine,
    }
