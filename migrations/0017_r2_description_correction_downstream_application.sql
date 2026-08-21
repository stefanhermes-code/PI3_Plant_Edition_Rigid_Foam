-- R2 wording correction, required before R3 starts.
-- Charlie's "Package C Acceptance and Consolidated R3 Release to JC v3",
-- 21 August 2026, section 2.
--
-- WHY THIS EXISTS
--
-- Migration 0014 wrote a classification rule into five Application Area
-- descriptions: decide by the END PRODUCT, by what leaves the plant. Charlie
-- has replaced that rule:
--
--   "Application Area is the downstream polyurethane application for which a
--    Product Grade or formulation is intended. A system house may ship
--    chemical even when the intended application is refrigerator insulation,
--    roof spray foam, pre-insulated pipe or another downstream use."
--
-- He is right, and the reason is stronger than style. Applied literally to
-- PTU, the old rule returns nothing: PTU ships chemical, so no end product
-- leaves its plant that matches any record. RF-Refrigerator-001 is correctly
-- on APP-310 only because Stefan told us the intended use is a refrigerator
-- cabinet and door - which is the downstream-application rule, not the
-- leaves-the-plant one.
--
-- The descriptions are what the next person reads while classifying a grade,
-- so the master was teaching a rule that had been overruled. Charlie ruled
-- this an R2 wording defect exposed before R3 and directed that it be fixed
-- with one controlled migration first.
--
-- SCOPE, DELIBERATELY NARROW
--
-- Charlie: "Do not edit migrations 0014 or 0015. Add the next controlled
-- migration and change descriptions only. Do not change Application Area IDs,
-- names, PU Material Family tags, Product Grade links or any other
-- classification data."
--
-- Description text only, on exactly the five records he listed. The
-- replacement wording below is his, verbatim from the table in v3 section 2 -
-- not a paraphrase, because the point of the exercise is that the master
-- carries the ruling's own words.
--
-- Nothing is reclassified. No grade or area changes what it is.
--
-- APP-110 IS NOT TOUCHED, AND THAT IS A DECISION
--
-- APP-110 Roof Spray Foam still reads "The end product is the finished roof,
-- and the material is delivered as chemical rather than as a component". That
-- phrasing is in the old style, but its SUBSTANCE is the new rule - it says
-- the material ships as chemical while the application is a roof, which is
-- exactly Charlie's example. He listed five records and APP-110 was not among
-- them. Correcting a sixth record he did not authorise would be scope creep
-- on a controlled master, so it stays and is raised for his ruling instead.
--
-- Re-runnable.

update applications
   set description = 'Insulated sandwich-panel application for cold-room walls '
                     'or ceilings. Select this area when the intended '
                     'downstream application is manufacture of the panel.'
 where controlled_id = 'APP-210';

update applications
   set description = 'Insulation formed as part of an installed industrial '
                     'refrigeration room or cell. This area applies when the '
                     'intended downstream application is the room or cell '
                     'insulation itself rather than manufacture of a separate '
                     'sandwich panel.'
 where controlled_id = 'APP-330';

update applications
   set description = 'Production of rigid PU blocks or cut-to-shape parts for '
                     'downstream uses such as tooling board, buoyancy or '
                     'packaging.'
 where controlled_id = 'APP-220';

update applications
   set description = 'Thermal insulation of pre-insulated pipe systems.'
 where controlled_id = 'APP-410';

update applications
   set description = 'Rock or ground stabilisation in mining.'
 where controlled_id = 'APP-510';


-- ============================================================================
-- EXIT CHECK
-- ============================================================================
do $$
declare n integer; leaked text;
begin
    -- All five took the new text.
    select count(*) into n from applications
     where (controlled_id = 'APP-210' and description like 'Insulated sandwich-panel application%')
        or (controlled_id = 'APP-330' and description like 'Insulation formed as part of an installed%')
        or (controlled_id = 'APP-220' and description like 'Production of rigid PU blocks%')
        or (controlled_id = 'APP-410' and description = 'Thermal insulation of pre-insulated pipe systems.')
        or (controlled_id = 'APP-510' and description = 'Rock or ground stabilisation in mining.');
    if n <> 5 then
        raise exception 'Expected 5 corrected descriptions, matched %.', n;
    end if;

    -- The overruled rule must be gone from every ACTIVE record, not only the
    -- five - otherwise a sixth could carry it back in later.
    select string_agg(controlled_id, ', ') into leaked from applications
     where is_active
       and (lower(description) like '%leaves the plant%'
            or lower(description) like '%leaving the plant%');
    if leaked is not null then
        raise exception 'The overruled classification rule survives in: %.', leaked;
    end if;

    -- Nothing was reclassified: the five still carry their names and tags.
    select count(*) into n from applications
     where controlled_id in ('APP-210','APP-330','APP-220','APP-410','APP-510')
       and is_active and pu_material_family = 'Rigid';
    if n <> 5 then
        raise exception 'A corrected record lost its active state or family tag (% of 5 intact).', n;
    end if;

    raise notice 'R2 description correction applied: 5 records, 0 reclassified.';
end $$;
