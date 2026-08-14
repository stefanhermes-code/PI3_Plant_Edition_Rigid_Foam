"""Shared cascade-delete helpers.

Deleting anything above a production run in the master-data hierarchy
(Plant -> Product Family -> Foam Grade -> Recipe Version) ultimately has
to delete every production run underneath it too, since
ProductionRun.plant_id, foam_grade_id, and recipe_version_id are all
NOT NULL foreign keys - there is no way to delete a Foam Grade, say,
while a run still points at it. This module centralizes that "delete a
run and everything under it" logic (and the master-data levels built on
top of it) so pages 1, 2, 3, and 4 all share one correct implementation
instead of four slightly-different copies.

None of these functions call session.commit() - callers commit once after
calling them (possibly several times, e.g. once per run under a foam
grade) so a whole master-data delete is one all-or-nothing transaction.
"""

import difflib

from sqlalchemy import func, or_

from db import (
    ComponentStreamReading,
    Customer,
    CustomerTrial,
    FallplateSectionPosition,
    FoamGrade,
    FoamGradeTargetProperty,
    GradeSpecification,
    Machine,
    OptimizationTrial,
    PhysicalPropertyResult,
    PI3AIConnectionSetting,
    Plant,
    PlantProductionMethod,
    ProcessParameterValue,
    ProductFamily,
    ProductionCycle,
    ProductionEvent,
    ProductionOutputSummary,
    ProductionPhase,
    ProductionRun,
    ProductionShot,
    QualityObservation,
    RawMaterialLotUse,
    RecipeComponent,
    RecipeVersion,
    RuntimeDataRecord,
    Sample,
    foam_grade_machines,
)


# ---------------------------------------------------------------------------
# Production run (the base case everything else builds on)
# ---------------------------------------------------------------------------

def production_run_dependency_counts(session, run_id):
    phase_ids = [
        p.id for p in session.query(ProductionPhase.id)
        .filter(ProductionPhase.production_run_id == run_id).all()
    ]
    sample_ids = [
        s.id for s in session.query(Sample.id)
        .filter(Sample.production_run_id == run_id).all()
    ]
    cycle_ids = [
        c.id for c in session.query(ProductionCycle.id)
        .filter(ProductionCycle.production_run_id == run_id).all()
    ]
    # WP7 Phase 1/2 (2026-08-13/14): ComponentStreamReading, ProductionOutputSummary,
    # and ProcessParameterValue can now all be linked directly to production_run_id
    # (not only via a ProductionPhase), per Charlie's decoupling decision - so their
    # counts/deletes below are no longer phase_ids-only.
    stream_conditions = [ComponentStreamReading.production_run_id == run_id]
    if phase_ids:
        stream_conditions.append(ComponentStreamReading.production_phase_id.in_(phase_ids))
    stream_count = (
        session.query(ComponentStreamReading).filter(or_(*stream_conditions)).count()
    )
    return {
        "process phase(s)": len(phase_ids),
        "component stream reading(s)": stream_count,
        "fall-plate section position(s)": (
            session.query(FallplateSectionPosition)
            .filter(FallplateSectionPosition.production_phase_id.in_(phase_ids)).count()
            if phase_ids else 0
        ),
        "production event(s)": session.query(ProductionEvent)
        .filter(ProductionEvent.production_run_id == run_id).count(),
        "raw material lot use(s)": session.query(RawMaterialLotUse)
        .filter(RawMaterialLotUse.production_run_id == run_id).count(),
        "runtime data record(s)": session.query(RuntimeDataRecord)
        .filter(RuntimeDataRecord.production_run_id == run_id).count(),
        "quality test result(s)": session.query(PhysicalPropertyResult)
        .filter(PhysicalPropertyResult.production_run_id == run_id).count(),
        "quality issue(s)": session.query(QualityObservation)
        .filter(QualityObservation.production_run_id == run_id).count(),
        "sample(s)": len(sample_ids),
        "method-aware process setting value(s)": session.query(ProcessParameterValue)
        .filter(ProcessParameterValue.production_run_id == run_id).count(),
        "production output summary": session.query(ProductionOutputSummary)
        .filter(ProductionOutputSummary.production_run_id == run_id).count(),
        # WP7 Phase 2 Closeout Correction (2026-08-14), Material Gap 3: the
        # new Cycle/Shot Data tab is the first UI surface that can ever
        # write ProductionCycle/ProductionShot rows - counted here so a
        # run's delete-confirmation warning is accurate once that tab is
        # used.
        "production cycle(s)": len(cycle_ids),
        "production shot(s)": (
            session.query(ProductionShot).filter(ProductionShot.production_cycle_id.in_(cycle_ids)).count()
            if cycle_ids else 0
        ),
    }


def delete_production_run_cascade(session, run_id):
    """Delete one production run and everything that depends on it."""
    phase_ids = [
        p.id for p in session.query(ProductionPhase.id)
        .filter(ProductionPhase.production_run_id == run_id).all()
    ]
    sample_ids = [
        s.id for s in session.query(Sample.id)
        .filter(Sample.production_run_id == run_id).all()
    ]
    cycle_ids = [
        c.id for c in session.query(ProductionCycle.id)
        .filter(ProductionCycle.production_run_id == run_id).all()
    ]

    if phase_ids:
        session.query(ComponentStreamReading).filter(
            ComponentStreamReading.production_phase_id.in_(phase_ids)
        ).delete(synchronize_session=False)
        session.query(FallplateSectionPosition).filter(
            FallplateSectionPosition.production_phase_id.in_(phase_ids)
        ).delete(synchronize_session=False)

    # WP7 Phase 1/2 (2026-08-13/14): ComponentStreamReading, ProcessParameterValue,
    # and ProductionOutputSummary can now also be linked directly to
    # production_run_id (not only via a ProductionPhase) - delete those too, or a
    # run-level delete would leave orphaned rows / fail Postgres FK constraints.
    session.query(ComponentStreamReading).filter(
        ComponentStreamReading.production_run_id == run_id
    ).delete(synchronize_session=False)
    session.query(ProcessParameterValue).filter(
        ProcessParameterValue.production_run_id == run_id
    ).delete(synchronize_session=False)
    session.query(ProductionOutputSummary).filter(
        ProductionOutputSummary.production_run_id == run_id
    ).delete(synchronize_session=False)

    session.query(ProductionEvent).filter(
        ProductionEvent.production_run_id == run_id
    ).delete(synchronize_session=False)
    session.query(ProductionPhase).filter(
        ProductionPhase.production_run_id == run_id
    ).delete(synchronize_session=False)
    session.query(RawMaterialLotUse).filter(
        RawMaterialLotUse.production_run_id == run_id
    ).delete(synchronize_session=False)
    session.query(RuntimeDataRecord).filter(
        RuntimeDataRecord.production_run_id == run_id
    ).delete(synchronize_session=False)
    session.query(PhysicalPropertyResult).filter(
        PhysicalPropertyResult.production_run_id == run_id
    ).delete(synchronize_session=False)
    session.query(QualityObservation).filter(
        QualityObservation.production_run_id == run_id
    ).delete(synchronize_session=False)
    session.query(Sample).filter(
        Sample.production_run_id == run_id
    ).delete(synchronize_session=False)

    # WP7 Phase 2 Closeout Correction (2026-08-14), Material Gap 3: the new
    # Cycle/Shot Data tab writes ProductionCycle/ProductionShot rows (and,
    # per the schema's own design, could write cycle/shot-linked
    # ProcessParameterValue rows too) - clean those up before the run row
    # itself, same phase_ids-style two-step (find ids, then delete
    # dependents-of-dependents) already used for Setup/Runtime Data above.
    if cycle_ids:
        session.query(ProcessParameterValue).filter(
            ProcessParameterValue.production_cycle_id.in_(cycle_ids)
        ).delete(synchronize_session=False)
        shot_ids = [
            s.id for s in session.query(ProductionShot.id)
            .filter(ProductionShot.production_cycle_id.in_(cycle_ids)).all()
        ]
        if shot_ids:
            session.query(ProcessParameterValue).filter(
                ProcessParameterValue.production_shot_id.in_(shot_ids)
            ).delete(synchronize_session=False)
            session.query(ProductionShot).filter(
                ProductionShot.id.in_(shot_ids)
            ).delete(synchronize_session=False)
        session.query(ProductionCycle).filter(
            ProductionCycle.id.in_(cycle_ids)
        ).delete(synchronize_session=False)

    session.query(ProductionRun).filter(ProductionRun.id == run_id).delete(synchronize_session=False)


def _merge_counts(total, addition):
    for k, v in addition.items():
        total[k] = total.get(k, 0) + v
    return total


# ---------------------------------------------------------------------------
# Customer trial / Optimization trial - the two independent lab-trial flows
# added 2026-08-03 (see db.py's SAMPLE_SOURCE_TYPES / CustomerTrial /
# OptimizationTrial). Unlike a production run, these have no
# ProductionPhase underneath (no machine/process settings), so their
# dependency tree is much shallower: just samples and quality results/
# issues keyed directly to the trial.
# ---------------------------------------------------------------------------

def _sample_ids_for_customer_trial(session, customer_trial_id):
    return [
        s.id for s in session.query(Sample.id)
        .filter(Sample.customer_trial_id == customer_trial_id).all()
    ]


def customer_trial_dependency_counts(session, customer_trial_id):
    sample_ids = _sample_ids_for_customer_trial(session, customer_trial_id)
    return {
        "sample(s)": len(sample_ids),
        "quality test result(s)": session.query(PhysicalPropertyResult)
        .filter(PhysicalPropertyResult.customer_trial_id == customer_trial_id).count(),
        "quality issue(s)": session.query(QualityObservation)
        .filter(QualityObservation.customer_trial_id == customer_trial_id).count(),
    }


def delete_customer_trial_cascade(session, customer_trial_id):
    session.query(PhysicalPropertyResult).filter(
        PhysicalPropertyResult.customer_trial_id == customer_trial_id
    ).delete(synchronize_session=False)
    session.query(QualityObservation).filter(
        QualityObservation.customer_trial_id == customer_trial_id
    ).delete(synchronize_session=False)
    session.query(Sample).filter(
        Sample.customer_trial_id == customer_trial_id
    ).delete(synchronize_session=False)
    session.query(CustomerTrial).filter(CustomerTrial.id == customer_trial_id).delete(synchronize_session=False)


def _sample_ids_for_optimization_trial(session, optimization_trial_id):
    return [
        s.id for s in session.query(Sample.id)
        .filter(Sample.optimization_trial_id == optimization_trial_id).all()
    ]


def optimization_trial_dependency_counts(session, optimization_trial_id):
    sample_ids = _sample_ids_for_optimization_trial(session, optimization_trial_id)
    return {
        "sample(s)": len(sample_ids),
        "quality test result(s)": session.query(PhysicalPropertyResult)
        .filter(PhysicalPropertyResult.optimization_trial_id == optimization_trial_id).count(),
        "quality issue(s)": session.query(QualityObservation)
        .filter(QualityObservation.optimization_trial_id == optimization_trial_id).count(),
    }


def delete_optimization_trial_cascade(session, optimization_trial_id):
    session.query(PhysicalPropertyResult).filter(
        PhysicalPropertyResult.optimization_trial_id == optimization_trial_id
    ).delete(synchronize_session=False)
    session.query(QualityObservation).filter(
        QualityObservation.optimization_trial_id == optimization_trial_id
    ).delete(synchronize_session=False)
    session.query(Sample).filter(
        Sample.optimization_trial_id == optimization_trial_id
    ).delete(synchronize_session=False)
    session.query(OptimizationTrial).filter(
        OptimizationTrial.id == optimization_trial_id
    ).delete(synchronize_session=False)


# ---------------------------------------------------------------------------
# Recipe version
# ---------------------------------------------------------------------------

def _run_ids_for_recipe_version(session, recipe_version_id):
    return [
        r.id for r in session.query(ProductionRun.id)
        .filter(ProductionRun.recipe_version_id == recipe_version_id).all()
    ]


def recipe_version_dependency_counts(session, recipe_version_id):
    run_ids = _run_ids_for_recipe_version(session, recipe_version_id)
    counts = {
        "recipe component(s)": session.query(RecipeComponent)
        .filter(RecipeComponent.recipe_version_id == recipe_version_id).count(),
        "production run(s)": len(run_ids),
    }
    for run_id in run_ids:
        _merge_counts(counts, production_run_dependency_counts(session, run_id))
    # recipe_version_id is a NULLABLE, optional reference on both lab-trial
    # tables (unlike ProductionRun's NOT NULL one above) - these trials get
    # their recipe reference cleared, not deleted, so count them separately.
    ct_count = session.query(CustomerTrial).filter(CustomerTrial.recipe_version_id == recipe_version_id).count()
    ot_count = session.query(OptimizationTrial).filter(OptimizationTrial.recipe_version_id == recipe_version_id).count()
    if ct_count:
        counts["customer trial(s) (recipe reference will be cleared, not deleted)"] = ct_count
    if ot_count:
        counts["optimization trial(s) (recipe reference will be cleared, not deleted)"] = ot_count
    return counts


def delete_recipe_version_cascade(session, recipe_version_id):
    for run_id in _run_ids_for_recipe_version(session, recipe_version_id):
        delete_production_run_cascade(session, run_id)
    session.query(CustomerTrial).filter(CustomerTrial.recipe_version_id == recipe_version_id).update(
        {"recipe_version_id": None}, synchronize_session="fetch"
    )
    session.query(OptimizationTrial).filter(OptimizationTrial.recipe_version_id == recipe_version_id).update(
        {"recipe_version_id": None}, synchronize_session="fetch"
    )
    session.query(RecipeComponent).filter(
        RecipeComponent.recipe_version_id == recipe_version_id
    ).delete(synchronize_session=False)
    session.query(RecipeVersion).filter(RecipeVersion.id == recipe_version_id).delete(synchronize_session=False)


# ---------------------------------------------------------------------------
# Foam grade
# ---------------------------------------------------------------------------

def _version_ids_for_foam_grade(session, foam_grade_id):
    return [
        v.id for v in session.query(RecipeVersion.id)
        .filter(RecipeVersion.foam_grade_id == foam_grade_id).all()
    ]


def _run_ids_for_foam_grade(session, foam_grade_id):
    run_ids = set(
        r.id for r in session.query(ProductionRun.id)
        .filter(ProductionRun.foam_grade_id == foam_grade_id).all()
    )
    for version_id in _version_ids_for_foam_grade(session, foam_grade_id):
        run_ids.update(_run_ids_for_recipe_version(session, version_id))
    return run_ids


def _customer_trial_ids_for_foam_grade(session, foam_grade_id):
    return [
        t.id for t in session.query(CustomerTrial.id)
        .filter(CustomerTrial.foam_grade_id == foam_grade_id).all()
    ]


def _optimization_trial_ids_for_foam_grade(session, foam_grade_id):
    return [
        t.id for t in session.query(OptimizationTrial.id)
        .filter(OptimizationTrial.foam_grade_id == foam_grade_id).all()
    ]


def foam_grade_dependency_counts(session, foam_grade_id):
    version_ids = _version_ids_for_foam_grade(session, foam_grade_id)
    counts = {"recipe version(s)": len(version_ids)}
    for version_id in version_ids:
        counts["recipe component(s)"] = counts.get("recipe component(s)", 0) + (
            session.query(RecipeComponent).filter(RecipeComponent.recipe_version_id == version_id).count()
        )
    counts["other target physical propert(y/ies)"] = (
        session.query(FoamGradeTargetProperty)
        .filter(FoamGradeTargetProperty.foam_grade_id == foam_grade_id)
        .count()
    )
    # CR-07 (2026-08-11): grade_specifications is the real, active property-
    # target list for a grade now (see db.py's FoamGradeTargetProperty
    # docstring) - counted here so the delete-confirmation warning names it,
    # same as every other dependent record type on this grade.
    counts["product grade property target(s)"] = (
        session.query(GradeSpecification)
        .filter(GradeSpecification.foam_grade_id == foam_grade_id)
        .count()
    )
    run_ids = _run_ids_for_foam_grade(session, foam_grade_id)
    counts["production run(s)"] = len(run_ids)
    for run_id in run_ids:
        _merge_counts(counts, production_run_dependency_counts(session, run_id))
    # foam_grade_id is a NOT NULL, required FK on both lab-trial tables
    # (unlike recipe_version_id above) - these trials get fully deleted,
    # same as production runs.
    ct_ids = _customer_trial_ids_for_foam_grade(session, foam_grade_id)
    counts["customer trial(s)"] = len(ct_ids)
    for ct_id in ct_ids:
        _merge_counts(counts, customer_trial_dependency_counts(session, ct_id))
    ot_ids = _optimization_trial_ids_for_foam_grade(session, foam_grade_id)
    counts["optimization trial(s)"] = len(ot_ids)
    for ot_id in ot_ids:
        _merge_counts(counts, optimization_trial_dependency_counts(session, ot_id))
    return counts


def delete_foam_grade_cascade(session, foam_grade_id):
    version_ids = _version_ids_for_foam_grade(session, foam_grade_id)
    for run_id in _run_ids_for_foam_grade(session, foam_grade_id):
        delete_production_run_cascade(session, run_id)
    for ct_id in _customer_trial_ids_for_foam_grade(session, foam_grade_id):
        delete_customer_trial_cascade(session, ct_id)
    for ot_id in _optimization_trial_ids_for_foam_grade(session, foam_grade_id):
        delete_optimization_trial_cascade(session, ot_id)
    for version_id in version_ids:
        session.query(RecipeComponent).filter(
            RecipeComponent.recipe_version_id == version_id
        ).delete(synchronize_session=False)
    session.query(RecipeVersion).filter(RecipeVersion.foam_grade_id == foam_grade_id).delete(synchronize_session=False)
    session.query(FoamGradeTargetProperty).filter(
        FoamGradeTargetProperty.foam_grade_id == foam_grade_id
    ).delete(synchronize_session=False)
    # CR-07 (2026-08-11): grade_specifications rows were never deleted here
    # before this fix - a real gap, since this whole function uses bulk
    # session.query(...).delete() calls that bypass FoamGrade.specifications'
    # ORM-level cascade="all, delete-orphan" (that cascade only fires on
    # session.delete(instance), never on a bulk-delete query like the one
    # right below this that removes the FoamGrade row itself). Deleting a
    # grade would otherwise leave its property-target rows orphaned in the
    # database - CR-07 section 6 explicitly requires this cascade.
    session.query(GradeSpecification).filter(
        GradeSpecification.foam_grade_id == foam_grade_id
    ).delete(synchronize_session=False)
    # Production Method Hierarchy architecture change (2026-08-09): clear
    # this grade's Machine assignments (the foam_grade_machines join
    # table) before deleting the grade itself.
    session.execute(
        foam_grade_machines.delete().where(foam_grade_machines.c.foam_grade_id == foam_grade_id)
    )
    session.query(FoamGrade).filter(FoamGrade.id == foam_grade_id).delete(synchronize_session=False)


# ---------------------------------------------------------------------------
# Product family
# ---------------------------------------------------------------------------

def _grade_ids_for_family(session, product_family_id):
    return [
        g.id for g in session.query(FoamGrade.id)
        .filter(FoamGrade.product_family_id == product_family_id).all()
    ]


def product_family_dependency_counts(session, product_family_id):
    grade_ids = _grade_ids_for_family(session, product_family_id)
    counts = {"product grade(s)": len(grade_ids)}
    for grade_id in grade_ids:
        _merge_counts(counts, foam_grade_dependency_counts(session, grade_id))
    return counts


def delete_product_family_cascade(session, product_family_id):
    for grade_id in _grade_ids_for_family(session, product_family_id):
        delete_foam_grade_cascade(session, grade_id)
    session.query(ProductFamily).filter(ProductFamily.id == product_family_id).delete(synchronize_session=False)


# ---------------------------------------------------------------------------
# Plant (the deepest one - every level above collapses into this)
# ---------------------------------------------------------------------------

def plant_dependency_counts(session, plant_id):
    family_ids = [
        f.id for f in session.query(ProductFamily.id).filter(ProductFamily.plant_id == plant_id).all()
    ]
    counts = {"product family(ies)": len(family_ids)}
    already_counted_run_ids = set()
    already_counted_ct_ids = set()
    already_counted_ot_ids = set()
    for family_id in family_ids:
        _merge_counts(counts, product_family_dependency_counts(session, family_id))
        for grade_id in _grade_ids_for_family(session, family_id):
            already_counted_run_ids.update(_run_ids_for_foam_grade(session, grade_id))
            already_counted_ct_ids.update(_customer_trial_ids_for_foam_grade(session, grade_id))
            already_counted_ot_ids.update(_optimization_trial_ids_for_foam_grade(session, grade_id))

    # Runs keyed directly to this plant that weren't already reached via a
    # product family/foam grade above (shouldn't normally happen given how
    # runs are created, but a direct plant_id FK exists, so check for it).
    direct_run_ids = set(
        r.id for r in session.query(ProductionRun.id).filter(ProductionRun.plant_id == plant_id).all()
    )
    extra_run_ids = direct_run_ids - already_counted_run_ids
    counts["production run(s) not otherwise linked"] = len(extra_run_ids)
    for run_id in extra_run_ids:
        _merge_counts(counts, production_run_dependency_counts(session, run_id))

    # Same "not otherwise linked" check for the two lab-trial tables - both
    # carry their own direct plant_id (NOT NULL) alongside foam_grade_id.
    direct_ct_ids = set(
        t.id for t in session.query(CustomerTrial.id).filter(CustomerTrial.plant_id == plant_id).all()
    )
    extra_ct_ids = direct_ct_ids - already_counted_ct_ids
    counts["customer trial(s) not otherwise linked"] = len(extra_ct_ids)
    for ct_id in extra_ct_ids:
        _merge_counts(counts, customer_trial_dependency_counts(session, ct_id))

    direct_ot_ids = set(
        t.id for t in session.query(OptimizationTrial.id).filter(OptimizationTrial.plant_id == plant_id).all()
    )
    extra_ot_ids = direct_ot_ids - already_counted_ot_ids
    counts["optimization trial(s) not otherwise linked"] = len(extra_ot_ids)
    for ot_id in extra_ot_ids:
        _merge_counts(counts, optimization_trial_dependency_counts(session, ot_id))

    # CR-01 follow-up (task #746, 2026-08-10): label-only rename to match
    # every other "Machine" -> "Production Unit or Cell" customer-facing
    # string - this key renders verbatim in the delete-confirmation detail
    # text (e.g. "3 production unit(s) or cell(s)"), so it must read
    # naturally there, not just as a dict key.
    counts["production unit(s) or cell(s)"] = session.query(Machine).filter(Machine.plant_id == plant_id).count()
    counts["pi3/ai connectivity setting(s)"] = (
        session.query(PI3AIConnectionSetting).filter(PI3AIConnectionSetting.plant_id == plant_id).count()
    )
    counts["activated production method(s)"] = (
        session.query(PlantProductionMethod).filter(PlantProductionMethod.plant_id == plant_id).count()
    )
    return counts


def delete_plant_cascade(session, plant_id):
    family_ids = [
        f.id for f in session.query(ProductFamily.id).filter(ProductFamily.plant_id == plant_id).all()
    ]
    already_deleted_run_ids = set()
    already_deleted_ct_ids = set()
    already_deleted_ot_ids = set()
    for family_id in family_ids:
        for grade_id in _grade_ids_for_family(session, family_id):
            already_deleted_run_ids.update(_run_ids_for_foam_grade(session, grade_id))
            already_deleted_ct_ids.update(_customer_trial_ids_for_foam_grade(session, grade_id))
            already_deleted_ot_ids.update(_optimization_trial_ids_for_foam_grade(session, grade_id))
        delete_product_family_cascade(session, family_id)

    remaining_run_ids = set(
        r.id for r in session.query(ProductionRun.id).filter(ProductionRun.plant_id == plant_id).all()
    ) - already_deleted_run_ids
    for run_id in remaining_run_ids:
        delete_production_run_cascade(session, run_id)

    remaining_ct_ids = set(
        t.id for t in session.query(CustomerTrial.id).filter(CustomerTrial.plant_id == plant_id).all()
    ) - already_deleted_ct_ids
    for ct_id in remaining_ct_ids:
        delete_customer_trial_cascade(session, ct_id)

    remaining_ot_ids = set(
        t.id for t in session.query(OptimizationTrial.id).filter(OptimizationTrial.plant_id == plant_id).all()
    ) - already_deleted_ot_ids
    for ot_id in remaining_ot_ids:
        delete_optimization_trial_cascade(session, ot_id)

    # Production Method Hierarchy architecture change (2026-08-09): clear
    # this plant's Machines' foam_grade_machines assignments before
    # deleting the Machines themselves (a plain association table has no
    # ON DELETE CASCADE configured, and FoamGrade rows under a *different*
    # plant could theoretically still reference one of these machine ids
    # if data were ever malformed - belt-and-suspenders, not expected in
    # practice since FoamGrade/Machine are always assigned within the same
    # plant).
    plant_machine_ids = [
        m.id for m in session.query(Machine.id).filter(Machine.plant_id == plant_id).all()
    ]
    if plant_machine_ids:
        session.execute(
            foam_grade_machines.delete().where(foam_grade_machines.c.machine_id.in_(plant_machine_ids))
        )
    session.query(Machine).filter(Machine.plant_id == plant_id).delete(synchronize_session=False)
    session.query(PI3AIConnectionSetting).filter(PI3AIConnectionSetting.plant_id == plant_id).delete(synchronize_session=False)
    session.query(PlantProductionMethod).filter(PlantProductionMethod.plant_id == plant_id).delete(synchronize_session=False)
    session.query(Plant).filter(Plant.id == plant_id).delete(synchronize_session=False)


def unlink_machine_dependents(session, machine_id):
    """Called right before deleting a Machine (page 1's inline delete
    handler - this is the one machine-delete path that isn't itself a
    "delete everything under X" cascade, since a Machine can be safely
    unlinked rather than dragging its Production Runs down with it).
    Clears the foam_grade_machines assignment rows for this machine (new,
    Production Method Hierarchy architecture change, 2026-08-09) and
    unlinks ProductionRun.machine_id (pre-existing behavior, moved here
    from the page's own inline code so both effects live in one place)."""
    session.execute(foam_grade_machines.delete().where(foam_grade_machines.c.machine_id == machine_id))
    session.query(ProductionRun).filter(ProductionRun.machine_id == machine_id).update(
        {"machine_id": None}, synchronize_session="fetch"
    )


# ---------------------------------------------------------------------------
# CR-14 (Create Customers Section and Lightweight Customer Master),
# implemented 2026-08-12: migration/mapping helper for existing
# CustomerTrial.customer_name text values, run once against a database that
# has pre-CR-14 trial rows (customer_id is NULL). NOT part of the delete-
# cascade family above - included here because it is the same kind of
# cross-cutting relationship-maintenance logic, and because
# pages/11_Customer_Trials.py's own module docstring already points here.
# ---------------------------------------------------------------------------

def backfill_trial_customers(session):
    """For every CustomerTrial with no customer_id yet, find-or-create a
    Customer master row for its plant's company + its customer_name text
    value (an EXACT, case/whitespace-normalized match only) and link
    customer_id to it. Commits once at the end.

    Never merges two different-looking customer_name strings into one
    Customer, no matter how similar - CR-14 section 5 requires "any
    ambiguous historical customer value must be surfaced ... for Stefan
    review rather than silently merged". Instead, after linking/creating,
    this does a second pass over the resulting Customer set (per company)
    and flags pairs of DIFFERENT company_name values that are suspiciously
    similar (difflib.SequenceMatcher ratio >= 0.82, tuned to catch things
    like "Acme Corp" vs "Acme Corp." or a likely typo, without flagging
    genuinely unrelated names) - those pairs are returned for a human to
    decide, never auto-merged.

    Returns {"linked": int, "created": int, "possible_duplicates":
    [(company_id, name_a, name_b, similarity_ratio), ...]}.

    Safe to call on a database with zero pre-CR-14 rows (returns all
    zeros/empty) - see the CR-14 closeout package for the live-data check
    confirming that was the actual state of the production database at
    the time of this CR."""
    trials = session.query(CustomerTrial).filter(CustomerTrial.customer_id.is_(None)).all()
    linked = 0
    created = 0
    for trial in trials:
        company_id = trial.plant.company_id if trial.plant else None
        name = (trial.customer_name or "").strip()
        if company_id is None or not name:
            continue
        existing = (
            session.query(Customer)
            .filter(Customer.company_id == company_id)
            .filter(func.lower(Customer.company_name) == name.lower())
            .first()
        )
        if existing is None:
            existing = Customer(company_id=company_id, company_name=name)
            session.add(existing)
            session.flush()
            created += 1
        trial.customer_id = existing.id
        linked += 1
    session.commit()

    possible_duplicates = []
    by_company = {}
    for c in session.query(Customer).all():
        by_company.setdefault(c.company_id, []).append(c)
    for company_id, company_customers in by_company.items():
        for i in range(len(company_customers)):
            for j in range(i + 1, len(company_customers)):
                a, b = company_customers[i], company_customers[j]
                name_a, name_b = a.company_name.strip().lower(), b.company_name.strip().lower()
                if name_a == name_b:
                    continue
                ratio = difflib.SequenceMatcher(None, name_a, name_b).ratio()
                if ratio >= 0.82:
                    possible_duplicates.append((company_id, a.company_name, b.company_name, round(ratio, 2)))

    return {"linked": linked, "created": created, "possible_duplicates": possible_duplicates}
