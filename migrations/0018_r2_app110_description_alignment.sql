-- R2 wording correction, second and final record.
-- Charlie's "R3 Section 2 Acceptance and APP-110 Ruling to JC v1",
-- 21 August 2026, section 2.
--
-- WHY THIS EXISTS
--
-- 0017 corrected the five Application Area descriptions Charlie listed, and
-- deliberately left APP-110 alone because it was not among them. That was
-- raised as a question rather than decided here, and he has now ruled:
--
--   "Bring APP-110 into the same wording standard. Its current description
--    points to the correct application, but still explains the distinction
--    through physical end product and delivery form. The controlled master
--    should use one rule throughout: the downstream polyurethane application
--    for which the Product Grade or formulation is intended."
--
-- The point is not that APP-110 said anything false. Its substance was already
-- the downstream rule - material ships as chemical, application is a roof. The
-- problem is that a controlled master explaining itself two different ways
-- teaches two rules, and the reader picks whichever one the record in front of
-- them happens to use.
--
-- 0017 is applied and ledgered and is not edited. Charlie: "Use 0018 if it is
-- still free; otherwise use the next migration number and do not renumber an
-- existing artifact." 0018 is free.
--
-- SCOPE
--
-- APP-110's description only. His wording verbatim. ID, name, PU Material
-- Family tag, active state and all links unchanged. No other record touched.
--
-- Re-runnable.

update applications
   set description = 'Rigid polyurethane foam spray-applied in place to roofs '
                     'or comparable building surfaces for thermal insulation. '
                     'Use APP-110 when the intended downstream application is '
                     'site-applied roof or building-surface insulation. '
                     'Manufactured board and panel products for the building '
                     'envelope remain under APP-100.'
 where controlled_id = 'APP-110';


-- ============================================================================
-- EXIT CHECK
-- ============================================================================
do $$
declare n integer; leaked text;
begin
    select count(*) into n from applications
     where controlled_id = 'APP-110'
       and description like 'Rigid polyurethane foam spray-applied in place%'
       and name = 'Roof Spray Foam'
       and is_active
       and pu_material_family = 'Rigid';
    if n <> 1 then
        raise exception 'APP-110 did not take the corrected description with its '
                        'name, active state and family tag intact (% matching row).', n;
    end if;

    -- The master must now explain itself one way. Both phrasings of the
    -- overruled rule are refused across every active record, so a later
    -- artifact cannot reintroduce either.
    select string_agg(controlled_id, ', ') into leaked from applications
     where is_active
       and (lower(description) like '%leaves the plant%'
            or lower(description) like '%leaving the plant%'
            or lower(description) like '%end product%');
    if leaked is not null then
        raise exception 'The overruled classification rule survives in: %.', leaked;
    end if;

    -- Nothing else moved.
    select count(*) into n from applications where is_active;
    if n <> 10 then
        raise exception 'Expected 10 active Application Areas, found %.', n;
    end if;

    raise notice 'APP-110 aligned; master now states one classification rule throughout.';
end $$;
