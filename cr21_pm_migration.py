"""CR-21 (2026-08-15): Production Method Master Revision and PM-800 Addition.

Per Charlie's CR21_Production_Method_Master_Revision_and_PM800_Execution_
Contract.docx and the Architecture Freeze (AF21-01,
CR21_JC_Engineering_Challenge_Review_and_Architecture_Freeze.docx),
Section 3 (F21-01..F21-11). Implements R21-01/R21-02/R21-03/R21-04/R21-05.

Every function here is idempotent - safe to call more than once, and safe
to call against a database with zero pre-existing rows - matching the
precedent already established by legacy_migration.py (WP7 Phase 3).

CORRECTION (2026-08-15, CR21_Closeout_Review_Return_to_JC.docx, A21-10):
Charlie's review found that the original release of this module docstring-
claimed "safe to call against a database with zero pre-existing rows" but
did not actually deliver that - migrate_production_method_master() only
renamed methods that already existed (skipping absent ones outright) and
unconditionally created PM-800, so a truly zero-row clean database ended
up with ONLY PM-800 after this step. The next step,
reclassify_pm100_appliance_records_to_pm800(), then called .one() for
PM-100, which does not exist in that state, and crashed. This correction
replaces the old _RENAMES-only approach with a full canonical 8-row
master (_CONTROLLED_METHOD_MASTER, values re-queried live from Supabase
immediately before writing this correction to guarantee they match
production exactly) applied uniformly to PM-100 through PM-700: any row
that is ABSENT is created directly with its final, approved (post-CR-21)
definition - there is no legacy state to "rename away from" on a clean
build - and any row that already EXISTS has its fields converged to the
same canonical definition (a no-op for PM-200/300/400/700, whose values
CR-21 never changed; the actual rename for PM-100/500/600). PM-800
creation/convergence is unchanged. reclassify_pm100_appliance_records_to_
pm800() now also defensively no-ops (rather than crashing) if PM-100 or
PM-800 are somehow still absent when it runs, though the corrected step
above guarantees they will not be after migrate_production_method_master()
runs first in run_cr21_migration()'s required order.

Scope (F21-09): this module changes controlled master DATA only
(names/descriptions/release flags on ProductionMethod, and the
production_method_id FK on the 5 unambiguous reference_formulations rows
JC identified at challenge time). It does not touch db.py's schema, the
dynamic UI/report/PI3 readers (already generic - see JC's challenge
response Section 2), or WP7 Production Run architecture (F21-11).
"""

from db import ProductionMethod, ReferenceFormulation

# F21-01/F21-02/A21-10: the full, canonical, POST-CR-21 controlled master
# for PM-100 through PM-700 (PM-800 is defined separately below since it
# is always a pure creation, never a rename). Values re-confirmed live
# against Supabase (rigid_foam.production_methods) on 2026-08-15
# immediately before this correction, so a clean build reaches the exact
# same state as the already-migrated upgrade-path database. PM-500's
# technical behavior is unchanged (D21-02) - only its preferred name
# changes. PM-600's description is pipe-only per F21-02/F21-05 (zero live
# vessel data at challenge time and re-confirmed immediately before the
# original migration - see the CR-21 return package's Section 4 recheck).
# PM-200/300/400/700 are listed here (unchanged by CR-21) purely so a
# clean build can create them - convergence against an already-correct
# existing row is a no-op.
_CONTROLLED_METHOD_MASTER = {
    "PM-100": {
        "name": "Discontinuous Panel & Board Production",
        "description": (
            "Discontinuous, mold/press-based factory production of rigid "
            "PUR/PIR insulation panels and boards. Does not cover "
            "enclosed appliance or component cavity foaming - see PM-800."
        ),
        "maturity_status": "Released",
        "is_released": True,
        "sort_order": 100,
        "uses_cycle_shot_operation": False,
    },
    "PM-200": {
        "name": "Continuous Panel & Board Production",
        "description": None,
        "maturity_status": "Defined / planned",
        "is_released": False,
        "sort_order": 200,
        "uses_cycle_shot_operation": False,
    },
    "PM-300": {
        "name": "Field Cavity Foaming",
        "description": None,
        "maturity_status": "Defined / planned",
        "is_released": False,
        "sort_order": 300,
        "uses_cycle_shot_operation": False,
    },
    "PM-400": {
        "name": "Spray Foam Application",
        "description": None,
        "maturity_status": "Defined / planned",
        "is_released": False,
        "sort_order": 400,
        "uses_cycle_shot_operation": False,
    },
    "PM-500": {
        "name": "Rigid Block Production",
        "description": None,
        "maturity_status": "Placeholder",
        "is_released": False,
        "sort_order": 500,
        "uses_cycle_shot_operation": False,
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
        "maturity_status": "Placeholder",
        "is_released": False,
        "sort_order": 600,
        "uses_cycle_shot_operation": False,
    },
    "PM-700": {
        "name": "Structural & Composite Rigid Foam Processing",
        "description": None,
        "maturity_status": "Placeholder",
        "is_released": False,
        "sort_order": 700,
        "uses_cycle_shot_operation": False,
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


# F21-09: CR-21's frozen write scope only ever RENAMES an already-existing
# PM-100/500/600 row (plus creates/converges PM-800, handled separately
# below). PM-200/300/400/700 are create-only - if one is already present
# (the normal upgrade-path case) CR-21 must not touch its fields at all,
# even if a future controlled-vocabulary edit elsewhere made them differ
# from the values below; those values exist here solely so a true clean
# build (zero pre-existing rows) can create them.
_RENAME_ON_EXISTING = {"PM-100", "PM-500", "PM-600"}


def migrate_production_method_master(session):
    """R21-01/R21-02/R21-03/A21-10: bring PM-100 through PM-700 to their
    canonical, approved (post-CR-21) definitions, and add PM-800 exactly
    once. Two cases per row:

    - A row that does not exist yet (the true clean-build case) is
      CREATED directly with its final canonical definition for ALL of
      PM-100 through PM-700 - there is no legacy name to rename away from
      on a clean build.
    - A row that already exists (the upgrade-path case, e.g. a database
      seeded before CR-21) is only field-converged for PM-100/500/600 -
      the actual rename. PM-200/300/400/700, if already present, are left
      completely untouched, matching F21-09's frozen scope exactly (CR-21
      never rewrites them; it only knows how to create them from scratch).

    Idempotent either way: re-running against an already-canonical row
    makes zero changes; PM-800 is looked up by controlled_id before
    insert, so re-running never creates a duplicate.

    Returns a dict summary: {"created": [...], "renamed": [...],
    "pm800_created": bool}."""
    created, renamed = [], []
    for controlled_id, canonical_fields in _CONTROLLED_METHOD_MASTER.items():
        method = session.query(ProductionMethod).filter(
            ProductionMethod.controlled_id == controlled_id
        ).one_or_none()
        if method is None:
            # A21-10: the supported clean baseline has zero
            # ProductionMethod rows - create with the final definition
            # directly rather than assuming an upgrade-path legacy row.
            session.add(ProductionMethod(controlled_id=controlled_id, **canonical_fields))
            created.append(controlled_id)
            continue
        if controlled_id not in _RENAME_ON_EXISTING:
            continue  # F21-09: never rewrite an already-existing PM-200/300/400/700 row
        changed = False
        for field, value in canonical_fields.items():
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
    return {"created": created, "renamed": renamed, "pm800_created": pm800_created}


def reclassify_pm100_appliance_records_to_pm800(session):
    """R21-04/R21-05: move the specific, evidence-identified appliance/
    cavity reference_formulations from PM-100 to PM-800 by controlled_id.
    Deliberately a fixed, named list (not a keyword/heuristic scan) per
    Charlie's "flag, don't guess" Phase 1 seeding rule - only the exact
    rows JC identified as unambiguous at challenge time move. Idempotent:
    a row already on PM-800 is left untouched; a controlled_id not found
    is skipped (reported, not silently ignored).

    A21-10 correction: uses .one_or_none() rather than .one() for the
    PM-100/PM-800 lookups themselves and no-ops defensively (returning an
    all-not_found result) if either is somehow still absent, instead of
    raising. In practice this should never trigger when called through
    run_cr21_migration(), since migrate_production_method_master() now
    guarantees both rows exist by the time this step runs - but this
    function no longer assumes a specific caller/order to stay safe.

    Returns a dict: {"reclassified": [...], "already_pm800": [...],
    "not_found": [...]}."""
    pm100 = session.query(ProductionMethod).filter(ProductionMethod.controlled_id == "PM-100").one_or_none()
    pm800 = session.query(ProductionMethod).filter(ProductionMethod.controlled_id == "PM-800").one_or_none()
    if pm100 is None or pm800 is None:
        return {
            "reclassified": [],
            "already_pm800": [],
            "not_found": list(_PM100_TO_PM800_RECLASSIFY),
        }

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
