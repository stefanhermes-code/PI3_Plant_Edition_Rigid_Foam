-- R-PRE-WP1. Redesign Migration Plan v3, Package A.
--
-- One nullable column on the Production Unit / Cell recording how it gets
-- material into the mix: "Machine-metered", "Batch blended" or "Hand mix".
-- helpers.MATERIAL_DELIVERY_MODES holds the vocabulary.
--
-- WHY THIS IS NOT CONSTRAINED TO THE THREE VALUES
--
-- Deliberate. The vocabulary is expected to grow as company types outside the
-- rigid-foam pilot are onboarded, and R4's capability work may move this
-- control somewhere else entirely. A CHECK constraint here would have to be
-- dropped and rebuilt on every addition, and a controlled vocabulary that
-- moves is worse than an uncontrolled one that is honest about it. The page
-- offers only the controlled values; an unrecognised stored value stays
-- readable and selectable rather than being silently reset.
--
-- NULL IS THE SAFE DIRECTION
--
-- NULL means "not declared" and resolves to APPLICABLE - every existing
-- Production Unit or Cell keeps every module it has today. A module is only
-- withdrawn once somebody has positively declared a mode that excludes it.
-- The alternative - defaulting to a mode - would have silently withdrawn the
-- metering module from every unit in every plant on the day this shipped.
--
-- Re-runnable: guarded by "if not exists".

alter table machines
    add column if not exists material_delivery_mode varchar(40);
