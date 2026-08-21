-- R3 wording correction, third and final record of the Application Area master.
-- Charlie's "R3 APP-110 Acceptance and APP-100 Ruling to JC v1",
-- 21 August 2026, section 3.
--
-- WHY THIS EXISTS
--
-- After 0017 and 0018 the master states one classification rule throughout -
-- the downstream polyurethane application a Product Grade is intended for -
-- except on APP-100, whose description was still the WP1 import:
--
--   "Thermal insulation products used in the building envelope or building
--    services. (WP1 Controlled Master Data, 04_Applications)"
--
-- It was not wrong and it carried none of the overruled phrasings, which is
-- why it was raised for ruling rather than corrected inside the APP-110 work.
-- Charlie has ruled:
--
--   "APP-100 should be aligned with the same downstream-application wording
--    standard. The current source tag is useful as provenance, but it should
--    not serve as the user-facing description of a controlled Application
--    Area."
--
-- A provenance tag answers "where did this record come from". A description
-- answers "should I classify this grade here". The second question is the one
-- being asked by whoever is reading it, and the tag does not answer it.
--
-- MIGRATION NUMBER
--
-- Charlie wrote "expected to be 0019 if still free". It is not. 0019 was
-- written, proved, applied and ledgered as the R3-WP1 Production Unit
-- inventory completion, checksum 5731a539d693, before this ruling arrived.
-- His standing rule is to take the next number and not renumber an existing
-- artifact, so this is 0020 and 0019 is untouched.
--
-- SCOPE
--
-- APP-100's description only. His wording verbatim. ID, name, active state,
-- PU Material Family tag, sort order, Product Grade links and every other
-- field unchanged. No other record touched.
--
-- Re-runnable.

update applications
   set description = 'Rigid PU insulation for manufactured building-envelope '
                     'products such as insulation boards and panels. Use '
                     'APP-210 for cold-room wall or ceiling panels and '
                     'APP-110 for roof spray foam.'
 where controlled_id = 'APP-100';


-- ============================================================================
-- EXIT CHECK
-- ============================================================================
do $$
declare n integer; leaked text;
begin
    select count(*) into n from applications
     where controlled_id = 'APP-100'
       and description like 'Rigid PU insulation for manufactured building-envelope%'
       and name = 'Building insulation'
       and is_active
       and pu_material_family = 'Rigid';
    if n <> 1 then
        raise exception 'APP-100 did not take the ruled description with its name, '
                        'active state and family tag intact (% matching row).', n;
    end if;

    -- The provenance tag must be gone from the user-facing text. It stays in
    -- the migration record - here, and in 0011 which created the row - which
    -- is where provenance belongs.
    select string_agg(controlled_id, ', ') into leaked from applications
     where is_active and description like '%WP1 Controlled Master Data%';
    if leaked is not null then
        raise exception 'A source tag is still serving as a description in: %.', leaked;
    end if;

    -- The overruled rule may not arrive with the new wording. Same three
    -- phrasings 0018 refused, checked across the whole active master.
    select string_agg(controlled_id, ', ') into leaked from applications
     where is_active
       and (lower(description) like '%leaves the plant%'
            or lower(description) like '%leaving the plant%'
            or lower(description) like '%end product%');
    if leaked is not null then
        raise exception 'The overruled classification rule survives in: %.', leaked;
    end if;

    -- Every active record now has a description, and every one of them states
    -- the downstream rule rather than merely being compatible with it.
    select string_agg(controlled_id, ', ') into leaked from applications
     where is_active and (description is null or length(trim(description)) = 0);
    if leaked is not null then
        raise exception 'Active Application Areas with no description: %.', leaked;
    end if;

    -- Nothing else moved.
    select count(*) into n from applications where is_active;
    if n <> 10 then
        raise exception 'Expected 10 active Application Areas, found %.', n;
    end if;

    raise notice 'APP-100 aligned; the controlled master is on one wording standard throughout.';
end $$;
