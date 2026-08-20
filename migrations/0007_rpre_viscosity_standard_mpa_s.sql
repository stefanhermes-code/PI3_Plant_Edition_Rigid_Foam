-- R-PRE-WP3 addendum 2. Redesign Migration Plan v3, Package A.
--
-- Stefan's ruling of 20 August 2026, superseding the cP ruling earlier the
-- same day: follow ASTM D445 and hold viscosity in mPa.s.
--
-- THIS CHANGES NO NUMBER ANYWHERE
--
-- 1 cP = 1 mPa.s exactly. The two units are the same size, so this is a
-- relabelling of the controlled standard and not a conversion. Every factor
-- in unit_conversion._UNIT_GROUPS["dynamic_viscosity"] is unchanged, cP
-- remains an accepted input unit at 1:1, and no stored value is touched -
-- there are none yet in any case: zero results exist against PROP-058 or
-- PROP-059, and zero results anywhere carry a viscosity unit. Checked before
-- writing this file. Doing it now costs nothing; doing it after the pilot
-- loads its data would mean re-labelling records a customer has already seen.
--
-- WHAT D445 ACTUALLY MEASURES - WORTH KNOWING BEFORE IT IS ADOPTED AS THE METHOD
--
-- ASTM D445 is a KINEMATIC viscosity method. A glass capillary viscometer
-- gives mm2/s (cSt), and the standard then CALCULATES dynamic viscosity in
-- mPa.s by multiplying by the density at the same temperature. So under D445
-- the density is not an optional extra - it is part of the method, and the
-- as-measured quantity is the kinematic one.
--
-- ASTM D2196 (rotational / Brookfield) is the other route, and the one more
-- usually run on a polyol or a prepolymer system: it reads dynamic viscosity
-- directly in mPa.s and needs no density at all.
--
-- Both are added below as controlled methods, because the application has to
-- support both and the choice belongs on the individual result, not in this
-- file. unit_conversion.dynamic_viscosity_cp() already refuses to cross from
-- kinematic to dynamic without a density, which is exactly D445's own rule.
--
-- Re-runnable: the update only moves the value this migration chain itself
-- set, so a deliberate later change is not silently reverted; the inserts are
-- guarded on their controlled_id.

update physical_property_definitions
   set default_uom = 'mPa.s'
 where controlled_id = 'PROP-059'
   and (default_uom is null or btrim(default_uom) in ('', 'cP'));

-- The two dynamic units swap roles: mPa.s becomes the standard, cP stays
-- accepted and converts 1:1.
update units_of_measure
   set data_rule = 'CONTROLLED STANDARD for viscosity, per ASTM D445. Store numeric. 1 mPa.s = 1 cP exactly. Always record the sample temperature - a viscosity without a temperature is not a measurement.'
 where controlled_id = 'UOM-109';

update units_of_measure
   set data_rule = 'Store numeric. Identical in size to the mPa.s standard; converts 1:1. Still the unit most polyurethane data sheets print, so it stays accepted on entry.'
 where controlled_id = 'UOM-108';

select setval(
    pg_get_serial_sequence('physical_property_methods', 'id'),
    greatest((select coalesce(max(id), 1) from physical_property_methods), 1),
    true
);

insert into physical_property_methods (
    property_definition_id, method_code, controlled_id, standard_reference,
    method_category, applicable_property_ids, implementation_rule
)
select
    (select id from physical_property_definitions where controlled_id = 'PROP-059'),
    'Kinematic viscosity by glass capillary viscometer',
    'MTH-039',
    'ASTM D445',
    'Viscosity',
    'PROP-059',
    'Measures KINEMATIC viscosity in mm2/s. Dynamic viscosity in mPa.s is calculated from it using the density at the SAME temperature, so the density (or specific gravity, PROP-058) is mandatory alongside the reading. Record the sample temperature and the capillary size.'
where not exists (
    select 1 from physical_property_methods where controlled_id = 'MTH-039'
);

insert into physical_property_methods (
    property_definition_id, method_code, controlled_id, standard_reference,
    method_category, applicable_property_ids, implementation_rule
)
select
    (select id from physical_property_definitions where controlled_id = 'PROP-059'),
    'Apparent viscosity by rotational viscometer',
    'MTH-040',
    'ASTM D2196',
    'Viscosity',
    'PROP-059',
    'Reads DYNAMIC viscosity directly in mPa.s; no density needed. Record the sample temperature, the spindle and the rotational speed - an apparent viscosity is meaningless without them for a non-Newtonian material.'
where not exists (
    select 1 from physical_property_methods where controlled_id = 'MTH-040'
);
