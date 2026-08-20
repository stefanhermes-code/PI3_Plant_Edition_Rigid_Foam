-- R-PRE-WP3 addendum 3. Redesign Migration Plan v3, Package A.
--
-- FOUND IN BROWSER EVIDENCE, NOT IN A TEST
--
-- Specific gravity and Viscosity were selectable on the Test Results page,
-- their descriptions read correctly, and the D445 method was offered - but the
-- "Unit of measure" picker showed "No options to select" and was greyed out.
--
-- The page builds that picker from physical_property_uoms, the per-property
-- allowed-unit link table, NOT from physical_property_definitions.default_uom.
-- Setting a default in 0006/0007 therefore recorded the standard without
-- making it selectable, and the only way to enter a unit was the free-text
-- "Or type a unit not listed above" box - the uncontrolled path the whole
-- viscosity ruling exists to close.
--
-- A PRE-EXISTING GAP, NOT ONE THIS RELEASE CREATED
--
-- physical_property_uoms holds ONE row in the entire database, for PROP-005
-- Thermal conductivity. All 56 other controlled properties have the same empty
-- picker and the same free-text fallback. That is a real finding and it is
-- raised as its own item; it is NOT fixed here, because fixing 56 properties
-- is not R-PRE's scope and would be a controlled-vocabulary exercise of its
-- own. This file closes it only for the two properties R-PRE added, so the
-- units it just standardised can actually be chosen.
--
-- WHY KINEMATIC UNITS ARE NOT OFFERED ON THE VISCOSITY PROPERTY
--
-- PROP-059 is DYNAMIC viscosity. Offering cSt or mm2/s in its picker would
-- invite a kinematic number to be stored under a dynamic property - the exact
-- confusion the two-quantity split in 0006 exists to prevent. A kinematic
-- reading is converted first, which needs the density;
-- unit_conversion.dynamic_viscosity_cp() does that and refuses without one.
--
-- mPa.s is listed first so it is the picker's default, per the ASTM D445
-- ruling. cP follows because it is what most polyurethane data sheets print.
--
-- Re-runnable: guarded on (property, unit_label).

insert into physical_property_uoms (property_definition_id, unit_label, sort_order, unit_id)
select d.id, v.unit_label, v.sort_order, u.id
from (values
    ('PROP-058', 'ratio', 1),
    ('PROP-059', 'mPa.s', 1),
    ('PROP-059', 'cP',    2),
    ('PROP-059', 'Pa.s',  3),
    ('PROP-059', 'P',     4)
) as v(property_controlled_id, unit_label, sort_order)
join physical_property_definitions d on d.controlled_id = v.property_controlled_id
left join units_of_measure u on u.symbol = v.unit_label
where not exists (
    select 1 from physical_property_uoms existing
     where existing.property_definition_id = d.id
       and existing.unit_label = v.unit_label
);
