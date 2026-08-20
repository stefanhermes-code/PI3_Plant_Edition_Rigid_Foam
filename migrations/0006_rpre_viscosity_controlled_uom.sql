-- R-PRE-WP3 addendum. Redesign Migration Plan v3, Package A.
--
-- Stefan's ruling of 20 August 2026: cP is the controlled standard unit for
-- viscosity, and a value arriving from a supplier data sheet in some other
-- unit must be converted into it rather than stored as typed.
--
-- 0004 created the Viscosity definition (PROP-059) with NO default unit,
-- because the controlled UOM master had no viscosity quantity type at all.
-- This file closes that gap and sets the default.
--
-- A CORRECTION TO 0004's OWN COMMENT
--
-- 0004 says the UOM master holds "40 records across 30 quantity types". The
-- quantity-type count is right; the record count is 43, not 40 - the figure
-- was carried over from a group-by whose rows were counted rather than
-- summed. 0004 is left exactly as it was applied: its SQL is correct, only a
-- comment is wrong, and silently rewriting an artifact the ledger has already
-- checksummed is a worse habit than carrying the correction forward here.
--
-- WHY TWO QUANTITY TYPES AND NOT ONE
--
-- Dynamic viscosity (cP, mPa.s, Pa.s, P) and kinematic viscosity (cSt, mm2/s)
-- are different physical quantities. They look interchangeable on a data
-- sheet and are not: kinematic = dynamic / density. Putting them in one list
-- would invite a straight cSt -> cP conversion, which is wrong by a factor of
-- the material's density - for a polyol around 1.02, so the error is small
-- enough to look plausible and large enough to matter. They are kept apart
-- here, and unit_conversion.dynamic_viscosity_cp() will only cross between
-- them when a density is supplied.
--
-- 1 cP = 1 mPa.s EXACTLY. Not a rounded factor - the two units are the same
-- size, which is why a data sheet quoting either can be taken at face value.
--
-- Re-runnable: every insert is guarded on its controlled_id and the update is
-- idempotent.

select setval(
    pg_get_serial_sequence('units_of_measure', 'id'),
    greatest((select coalesce(max(id), 1) from units_of_measure), 1),
    true
);

insert into units_of_measure (controlled_id, symbol, name, quantity_type, sort_order, unit_system, data_rule)
select v.controlled_id, v.symbol, v.name, v.quantity_type, v.sort_order, v.unit_system, v.data_rule
from (values
    ('UOM-108', 'cP',    'centipoise',                 'Dynamic viscosity',   108, 'Accepted',
     'CONTROLLED STANDARD for viscosity. Store numeric. 1 cP = 1 mPa.s exactly. Always record the sample temperature - a viscosity without a temperature is not a measurement.'),
    ('UOM-109', 'mPa.s', 'millipascal second',         'Dynamic viscosity',   109, 'SI derived',
     'Store numeric. Identical in size to cP; convert 1:1 to the cP standard.'),
    ('UOM-110', 'Pa.s',  'pascal second',              'Dynamic viscosity',   110, 'SI derived',
     'Store numeric. 1 Pa.s = 1000 cP.'),
    ('UOM-111', 'P',     'poise',                      'Dynamic viscosity',   111, 'Accepted',
     'Store numeric. 1 P = 100 cP.'),
    ('UOM-112', 'cSt',   'centistokes',                'Kinematic viscosity', 112, 'Accepted',
     'Store numeric. KINEMATIC, not dynamic. Conversion to the cP standard requires the material density: cP = cSt x density in g/cm3. Never convert without it.'),
    ('UOM-113', 'mm2/s', 'square millimetre per second','Kinematic viscosity', 113, 'SI derived',
     'Store numeric. Identical in size to cSt. KINEMATIC - see UOM-112 on converting to the cP standard.')
) as v(controlled_id, symbol, name, quantity_type, sort_order, unit_system, data_rule)
where not exists (
    select 1 from units_of_measure existing where existing.controlled_id = v.controlled_id
);

-- Give the Viscosity property its controlled default now that one exists.
-- Guarded so a later deliberate change is not silently overwritten by a
-- re-run: only fills the field while it is still empty.
update physical_property_definitions
   set default_uom = 'cP'
 where controlled_id = 'PROP-059'
   and (default_uom is null or btrim(default_uom) = '');

-- Same for the mandatory-context note, which 0004 wrote to say the unit had
-- to be stated because no controlled one existed. It now does.
update physical_property_definitions
   set mandatory_context = 'Record the sample temperature, the instrument type and the spindle or shear conditions. Values are held in the controlled cP standard; a data sheet quoting another unit is converted on entry.'
 where controlled_id = 'PROP-059'
   and mandatory_context like '%until a controlled viscosity UOM exists%';
