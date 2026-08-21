-- R3-WP1. Production Units / Cells: complete the inventory.
-- Charlie's "Package C Acceptance and Consolidated R3 Release to JC v3",
-- section 3, first requirement:
--
--   "Production Units / Cells: Inventory the existing units and machine
--    assignments first. Create missing units only from existing
--    plant/equipment evidence or approved pilot data. A machine belongs to
--    one Production Unit / Cell at a time. Keep the current
--    one-machine-to-one-unit relationship; no association table is required."
--
-- WHAT THE INVENTORY FOUND
--
-- Two plants, two machines, one Production Unit.
--
--   plant 3  HTC Global - Phase 1 Plant  (company 1, HTC Global)
--     machine 3  "Panel Foamer 1"           PM-100   -> unit 3 PU-PH1-001
--   plant 4  PTU Korat                   (company 2, Pacific Thai Urethanes)
--     machine 4  "Appliance Cavity Foaming Unit"  PM-800  -> NO UNIT
--
-- Nothing else is wrong with it. Zero machines assigned to a unit belonging
-- to a different plant, zero units carrying more than one machine, zero units
-- with no machine at all. The one-machine-to-one-unit relationship Charlie
-- wants kept is already what the schema enforces - machines.production_unit_id
-- is a plain nullable FK - so nothing is added to hold it and no association
-- table is created.
--
-- The single gap is PTU Korat's machine. This migration closes it.
--
-- WHAT WAS DELIBERATELY NOT CREATED
--
-- PTU Korat has FIVE activated production methods: PM-100, PM-200, PM-300,
-- PM-400 and PM-800. It has ONE machine. An activated method is a statement
-- that the plant may run that method, not evidence that equipment exists to
-- run it - Charlie's wording is "existing plant/equipment evidence", and four
-- of those five methods have no equipment behind them at all.
--
-- So exactly one unit is created here, for the one machine that exists. Four
-- units are NOT created. Creating them would put five Production Units into
-- R3-WP4's snapshot backfill and into every picker, four of which no run
-- could ever reference.
--
-- NAMING, AND WHERE IT CAME FROM
--
-- Stefan chose the controlled ID PU-KOR-001. The rest follows the only
-- precedent in the data, PU-PH1-001 at HTC Phase 1: the unit is named for what
-- it is, and unit_type restates the production method it runs.
--
--   PU-PH1-001  "Panel Line 1"           "Discontinuous panel line"     PM-100
--   PU-KOR-001  "Appliance Cavity Cell 1" ...appliance and cavity...    PM-800
--
-- "Cell" rather than "Line" because PM-800 is discrete filling of an enclosed
-- cavity, not continuous line production - and because Stefan's own term for
-- this level is "Production Unit / Cell". If PTU runs it as a line, that is a
-- one-line correction carried forward in a later artifact; 0019 is not edited.
--
-- Matched on plant and machine name rather than on id, so the artifact says
-- what it means and does not depend on an id sequence.
--
-- Re-runnable.

insert into production_units (plant_id, controlled_id, name, unit_type)
select p.id, 'PU-KOR-001', 'Appliance Cavity Cell 1',
       'Discontinuous appliance and cavity foaming cell'
  from plants p
 where p.name = 'PTU Korat'
   and not exists (select 1 from production_units u
                    where u.controlled_id = 'PU-KOR-001');

update machines m
   set production_unit_id = u.id
  from production_units u, plants p
 where u.controlled_id = 'PU-KOR-001'
   and p.id = u.plant_id
   and m.plant_id = p.id
   and m.name = 'Appliance Cavity Foaming Unit'
   and m.production_unit_id is distinct from u.id;


-- ============================================================================
-- EXIT CHECK
-- ============================================================================
do $$
declare n integer; offenders text;
begin
    -- The unit exists, at the right plant, with the wording above intact.
    select count(*) into n
      from production_units u join plants p on p.id = u.plant_id
     where u.controlled_id = 'PU-KOR-001'
       and u.name = 'Appliance Cavity Cell 1'
       and p.name = 'PTU Korat';
    if n <> 1 then
        raise exception 'PU-KOR-001 is not present exactly once at PTU Korat (% rows).', n;
    end if;

    -- EVERY machine now belongs to a unit. This is the requirement R3-WP4
    -- rests on: a run cannot snapshot a unit its machine does not have.
    select string_agg(m.name, ', ') into offenders
      from machines m where m.production_unit_id is null;
    if offenders is not null then
        raise exception 'Machines still without a Production Unit / Cell: %.', offenders;
    end if;

    -- One machine, one unit. Charlie's relationship, asserted rather than
    -- assumed - a unit holding two machines would break the snapshot too.
    select count(*) into n from (
        select production_unit_id from machines
         where production_unit_id is not null
         group by production_unit_id having count(*) > 1) x;
    if n <> 0 then
        raise exception '% Production Unit(s) carry more than one machine.', n;
    end if;

    -- A machine may never sit in another plant's unit. This is the tenant
    -- boundary expressed in equipment terms: plant 3 is HTC Global and
    -- plant 4 is PTU, so a cross-plant assignment is a cross-COMPANY one.
    select string_agg(m.name || ' -> ' || u.controlled_id, ', ') into offenders
      from machines m join production_units u on u.id = m.production_unit_id
     where u.plant_id <> m.plant_id;
    if offenders is not null then
        raise exception 'Cross-plant machine/unit assignment: %.', offenders;
    end if;

    -- Nothing was fanned out. Two plants, one unit each.
    select count(*) into n from production_units;
    if n <> 2 then
        raise exception 'Expected 2 Production Units, found % - four PTU methods have no equipment and must not have units.', n;
    end if;

    raise notice 'R3-WP1: every machine belongs to exactly one Production Unit / Cell.';
end $$;
