-- R-PRE-WP3. Redesign Migration Plan v3, Package A.
--
-- Adds the two controlled physical-property definitions the PTU pilot needs
-- and that the master does not already carry. Stefan's ruling of 20 August
-- 2026 settled the rest of Colin's QC list against existing records:
--
--     free-rise density  PROP-003   already present
--     cream time         PROP-047   already present
--     start time         PROP-057   already present
--     gel time           PROP-048   already present
--     tack-free time     PROP-049   already present
--     end-of-rise time   PROP-050   SAME PROPERTY AS "Rise time" - mapped,
--                                   NOT created. No row is added for it.
--
-- This file contains no DDL. It is a controlled-data change only, and it runs
-- through the runner rather than by hand so R-PRE carries the same ledger and
-- checksum evidence as every migration since P8-OWR-003.
--
-- WHY VISCOSITY HAS NO DEFAULT UOM
--
-- The controlled UOM master holds 40 records across 30 quantity types and has
-- no viscosity quantity type at all - no mPa.s, no cP, no Pa.s. Specific
-- gravity is dimensionless and uses the existing "ratio" unit (UOM-021), so it
-- is complete. Viscosity's default_uom is deliberately left NULL rather than
-- inventing a unit outside the controlled master, which the UOM reconciliation
-- ruling would not allow. Plan v3 R-PRE-WP3 provides for exactly this:
-- "Unconfirmed methods or units remain unset until PTU documentation supplies
-- them." Adding the viscosity unit is a separate controlled-master change and
-- is raised as its own item.
--
-- Both rows are marked provisional. 56 of the 57 existing definitions carry
-- source provenance; these two cannot until PTU's documentation is in hand, so
-- phase_status says so explicitly rather than leaving them looking finished.
--
-- Re-runnable: each insert is guarded on its controlled_id.

-- The id column is serial but historic rows were loaded with explicit ids, so
-- the sequence can sit behind max(id). Re-align it before inserting, otherwise
-- nextval collides with an existing primary key.
select setval(
    pg_get_serial_sequence('physical_property_definitions', 'id'),
    greatest((select coalesce(max(id), 1) from physical_property_definitions), 1),
    true
);

insert into physical_property_definitions (
    name, what_it_measures, category, is_common, sort_order, controlled_id,
    default_uom, scope, allowed_target_type, mandatory_context, source_ids, phase_status
)
select
    'Specific gravity',
    'Ratio of the density of the liquid polyurethane system, component or blend to the density of water at a stated reference temperature. Measured on the supplied system rather than on foam.',
    'Technical',
    false,
    58,
    'PROP-058',
    'ratio',
    'Supplied polyurethane system, component or blend',
    'Nominal/Range',
    'Record the sample temperature and the water reference temperature used for the ratio.',
    null,
    'Provisional - pending PTU documentation'
where not exists (
    select 1 from physical_property_definitions where controlled_id = 'PROP-058'
);

insert into physical_property_definitions (
    name, what_it_measures, category, is_common, sort_order, controlled_id,
    default_uom, scope, allowed_target_type, mandatory_context, source_ids, phase_status
)
select
    'Viscosity',
    'Resistance to flow of the liquid polyurethane system, component or blend at a stated temperature. Measured on the supplied system rather than on foam.',
    'Technical',
    false,
    59,
    'PROP-059',
    null,
    'Supplied polyurethane system, component or blend',
    'Nominal/Range',
    'Record the sample temperature, the instrument type and the spindle or shear conditions. The unit must be stated on the result until a controlled viscosity UOM exists.',
    null,
    'Provisional - pending PTU documentation'
where not exists (
    select 1 from physical_property_definitions where controlled_id = 'PROP-059'
);
