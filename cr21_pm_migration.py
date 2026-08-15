"""CR-21 (2026-08-15): Production Method Master Revision and PM-800 Addition.

Per Charlie's CR21_Production_Method_Master_Revision_and_PM800_Execution_
Contract.docx and the Architecture Freeze (AF21-01,
CR21_JC_Engineering_Challenge_Review_and_Architecture_Freeze.docx),
Section 3 (F21-01..F21-11). Implements R21-01/R21-02/R21-03/R21-04/R21-05.

Every function here is idempotent - safe to call more than once, and safe
to call against a database with zero pre-existing rows - matching the
precedent already established by legacy_migration.py (WP7 Phase 3).

Scope (F21-09): this module changes controlled master DATA only
(names/descriptions/release flags on ProductionMethod, and the
production_method_id FK on the 5 unambiguous reference_formulations rows
JC identified at challenge time). It does not touch db.py's schema, the
dynamic UI/report/PI3 readers (already generic - see JC's challenge
response Section 2), or WP7 Production Run architecture (F21-11).
"""

from db import ProductionMethod, ReferenceFormulation

# F21-01/F21-02: approved renames. PM-500's technical behavior is
# unchanged (D21-02) - only its preferred name changes. PM-600's
# description becomes pipe-only per F21-02/F21-05 (zero live vessel data
# at challenge time and re-confirmed immediately before migration - see
# the CR-21 return package's Section 4 recheck).
_RENAMES = {
    "PM-100": {
        "name": "Discontinuous Panel & Board Production",
        "description": (
            "Discontinuous, mold/press-based factory production of rigid "
            "PUR/PIR insulation panels and boards. Does not cover "
            "enclosed appliance or component cavity foaming - see PM-800."
        ),
    },
    "PM-500": {
        "name": "Rigid Block Production",
    },
    "PM-600": {
        "name": "Pre-insulated Pipe Processing",
        "description": (
            "Factory production of pre-insulated pipe. Vessel foaming is "
            "not in active scope - re-confirmed at CR-21 migration time: "
            "zero live PM-600-linked records across machines, production "
            "runs, recipe versions, reference formulations, and plant "
            "activations."
        ),
    },
}

# F21-01/D21-04/D21-05: PM-800's controlled definition, verbatim from the
# execution contract Section 3.
PM_800_DEFINITION = {
    "controlled_id": "PM-800",
    "name": "Discontinuous Appliance & Cavity Foaming",
    "description": (
        "A factory production method in which metered rigid PUR/PIR "
        "reactive components are introduced into an enclosed appliance "
        "or component cavity formed by liners, shells, doors, cabinet "
        "walls or dedicated fixtures. Production is discrete and "
        "traceable by run and, where configured, cycle/shot. Included "
        "application baseline: refrigerator/freezer cabinet; "
        "refrigerator/freezer door; commercial refrigeration equipment; "
        "water-heater insulation; comparable factory-filled enclosed "
        "assemblies when explicitly mapped. Excludes discontinuous "
        "panel/board production under PM-100 and field-installed cavity "
        "work under PM-300."
    ),
    "maturity_status": "Released",
    "is_released": True,
    "sort_order": 800,
    "uses_cycle_shot_operation": False,  # F21-08: accepted default for this CR
}

# F21-04: the exact reference_formulations reclassified from PM-100 to
# PM-800, identified by JC at challenge time (2026-08-15) and re-confirmed
# unchanged immediately before migration. Keyed by controlled_id, not
# database id, so the function is safe against a differently-ordered
# clean-build seed.
_PM100_TO_PM800_RECLASSIFY = ["RF-001", "RF-002", "RF-003", "RF-004", "RF-005"]


def migrate_production_method_master(session):
    """R21-01/R21-02/R21-03: rename PM-100/PM-500/PM-600 in place (same
    row, same id, same controlled_id - FK integrity is untouched by
    construction), and add PM-800 exactly once. Idempotent: renaming an
    already-renamed row is a no-op update; PM-800 is looked up by
    controlled_id before insert, so re-running never creates a duplicate.

    Returns a dict summary: {"renamed": [...], "pm800_created": bool}."""
    renamed = []
    for controlled_id, fields in _RENAMES.items():
        method = session.query(ProductionMethod).filter(
            ProductionMethod.controlled_id == controlled_id
        ).one_or_none()
        if method is None:
            continue  # F21-03: safe against a not-yet-seeded database
        changed = False
        for field, value in fields.items():
            if getattr(method, field) != value:
                setattr(method, field, value)
                changed = True
        if changed:
            renamed.append(controlled_id)

    pm800 = session.query(ProductionMethod).filter(
        ProductionMethod.controlled_id == PM_800_DEFINITION["controlled_id"]
    ).one_or_none()
    pm800_created = False
    if pm800 is None:
        session.add(ProductionMethod(**PM_800_DEFINITION))
        pm800_created = True
    else:
        # Idempotent re-run: converge an existing PM-800 row to the
        # approved definition rather than skipping it outright, so a
        # partially-applied prior run still reaches the frozen state.
        for field, value in PM_800_DEFINITION.items():
            if field == "controlled_id":
                continue
            if getattr(pm800, field) != value:
                setattr(pm800, field, value)

    session.commit()
    return {"renamed": renamed, "pm800_created": pm800_created}


def reclassify_pm100_appliance_records_to_pm800(session):
    """R21-04/R21-05: move the specific, evidence-identified appliance/
    cavity reference_formulations from PM-100 to PM-800 by controlled_id.
    Deliberately a fixed, named list (not a keyword/heuristic scan) per
    Charlie's "flag, don't guess" Phase 1 seeding rule - only the exact
    rows JC identified as unambiguous at challenge time move. Idempotent:
    a row already on PM-800 is left untouched; a controlled_id not found
    is skipped (reported, not silently ignored).

    Returns a dict: {"reclassified": [...], "already_pm800": [...],
    "not_found": [...]}."""
    pm100 = session.query(ProductionMethod).filter(ProductionMethod.controlled_id == "PM-100").one()
    pm800 = session.query(ProductionMethod).filter(ProductionMethod.controlled_id == "PM-800").one()

    reclassified, already_pm800, not_found = [], [], []
    for controlled_id in _PM100_TO_PM800_RECLASSIFY:
        rf = session.query(ReferenceFormulation).filter(
            ReferenceFormulation.controlled_id == controlled_id
        ).one_or_none()
        if rf is None:
            not_found.append(controlled_id)
            continue
        if rf.production_method_id == pm800.id:
            already_pm800.append(controlled_id)
            continue
        if rf.production_method_id == pm100.id:
            rf.production_method_id = pm800.id
            reclassified.append(controlled_id)
        # A row that belongs to neither PM-100 nor PM-800 is left alone -
        # out of this CR's evidence-based scope, not silently moved.

    session.commit()
    return {"reclassified": reclassified, "already_pm800": already_pm800, "not_found": not_found}


def run_cr21_migration(session):
    """Convenience entry point running both steps in the required order
    (master must exist with PM-800 before any row can be reclassified
    onto it). Idempotent as a whole - safe to call on every deploy, same
    contract as legacy_migration.py's functions."""
    master_result = migrate_production_method_master(session)
    reclass_result = reclassify_pm100_appliance_records_to_pm800(session)
    return {"master": master_result, "reclassification": reclass_result}
