-- R2-WP2. Redesign Migration Plan v5, Package C.
--
-- Promote the existing applications table into the single controlled
-- Application Area master, per Charlie's "Package B Acceptance, Final R2-WP1
-- Rulings and Package C Release to JC v2" (21 August 2026) sections 4 and 7,
-- and Plan v5 section 7.
--
-- This migration does the NON-DESTRUCTIVE half: tag, rename, create, and
-- deactivate. Removing APP-300 and APP-320 from the table is R2-WP4, and only
-- after their references are cleared and the evidence is complete. Splitting
-- it that way means every step here is reversible from the table itself, and
-- the retirement can be reviewed in the running application before anything
-- is dropped.
--
-- ============================================================================
-- WHAT CHANGED IN THE RULING, AND WHY THE SHAPE IS WHAT IT IS
-- ============================================================================
-- R2-WP1 asked whether a Product Grade that serves two applications needs a
-- many-to-many relationship. Stefan confirmed PTU's system fills both a
-- refrigerator cabinet and a door. Charlie's ruling did not add a join table
-- and did not use an umbrella record: he judged the classification too fine.
-- Cabinet and door become ONE Application Area, APP-310 renamed
-- "Refrigerator/Freezer Insulation", and APP-320 is retired.
--
-- So foam_grades.application_id stays singular. Section 4 of the ruling is
-- explicit: "No Product Grade/Application Area association table is to be
-- created." Nothing in this migration creates one.
--
-- The APP-* numbers are a controlled identifier and ordering convention, NOT
-- a parent-child hierarchy (ruling section 6). That is why APP-300 is retired
-- rather than kept as a parent of the refrigeration group, and why APP-210
-- does not need an APP-200 above it.
--
-- ============================================================================
-- CAPTURE BEFORE CHANGING
-- ============================================================================
-- The state this migration starts from, recorded here so the artifact is the
-- record. Verified against the live schema 21 August 2026.
--
--   APP-100  Building insulation                      10 references
--   APP-210  Cold-room wall or ceiling panel            2 references
--   APP-300  Refrigeration and appliance insulation     3 references (all
--            reference_formulations, all PM-800: ids 9, 10, 11)
--   APP-310  Refrigerator or freezer cabinet            2 references
--            (reference_formulations 7, 8)
--   APP-320  Refrigerator or freezer door               0 references
--   APP-330  Commercial refrigeration equipment         0 references
--   APP-340  Water-heater insulation                    0 references
--
-- APP-320 carries nothing, so "re-point any APP-320 reference to APP-310" is
-- a no-op on this database. The re-point is written anyway: it must be
-- correct on any database this runs against, not only on this one.
--
-- The three APP-300 links being set to NULL, preserved verbatim per ruling
-- section 4 ("Preserve each previous APP-300 relationship in the migration
-- evidence"):
--
--   reference_formulations id  9  "Appliance PUR, Novolac-polyether system"
--                                 -> was APP-300
--   reference_formulations id 10  "Appliance PUR, TIPA 5 php"
--                                 -> was APP-300
--   reference_formulations id 11  "Appliance PUR, higher-functionality TIPA
--                                 system" -> was APP-300
--
-- Charlie's instruction on these is explicit and is followed literally: "JC is
-- not to classify those formulations into a narrower Application Area from
-- formulation chemistry." They go to NULL. Ruling section 5 makes a NULL
-- Application Area valid for a reference formulation.
--
-- Re-runnable throughout.


-- ============================================================================
-- 1  ACTIVE / RETIRED, AND THE PU MATERIAL FAMILY TAG
-- ============================================================================
-- "Active controlled master" appears in the ruling and in Plan v5, but the
-- table had no way to express it - a record was either present or deleted.
-- is_active is that mechanism, and it is what makes R2-WP2 reversible: a
-- retired record stops appearing in pickers immediately while its row, and
-- anything still pointing at it, stays inspectable until R2-WP4 removes it.
alter table applications add column if not exists is_active boolean;
update applications set is_active = true where is_active is null;
alter table applications alter column is_active set default true;
alter table applications alter column is_active set not null;

-- The tag required by Plan v5 R2-WP2: "Tag each active Application Area with
-- the controlled PU Material Family value it belongs to." Same seven-value
-- vocabulary as pu_material_families.name, same reasoning as R1-WP2 for
-- leaving it a plain String rather than an Enum - the vocabulary extends by
-- migration without a type change.
alter table applications add column if not exists pu_material_family varchar(200);


-- ============================================================================
-- 2  RENAMES
-- ============================================================================
-- Keyed on controlled_id, never on name. controlled_id is the stable identity;
-- name is the thing being changed.
--
-- APP-340 is deliberately NOT renamed. The ruling says "Keep APP-340 as
-- Water-Heater Insulation", and "keep" means leave it alone. Its stored name
-- is "Water-heater insulation", which differs from the ruling's text only in
-- capitalisation. Renaming a controlled record on a difference in case, when
-- the instruction was to keep it, is not a decision to take silently - it is
-- raised in the R2 return as a house-style question instead.
update applications
   set name = 'Refrigerator/Freezer Insulation',
       description = 'Rigid foam insulation for refrigerator and freezer '
                     'assemblies, including cabinet and door. Cabinet versus '
                     'door is end-use detail recorded on the trial or '
                     'production record, not a separate Application Area '
                     '(Charlie ruling, 21 August 2026, section 4).'
 where controlled_id = 'APP-310';

update applications
   set name = 'Industrial Refrigeration Insulation'
 where controlled_id = 'APP-330';


-- ============================================================================
-- 3  APP-350  COOL BOX INSULATION
-- ============================================================================
-- New controlled record. sort_order 350 follows the existing convention.
-- No Production Method mapping is created for it: ruling section 4, "No
-- historical Production Method mapping is created for Cool Box Insulation
-- without evidence."
insert into applications (controlled_id, name, description, sort_order, is_active)
select 'APP-350', 'Cool Box Insulation',
       'Rigid foam insulation for portable and transport cool boxes and '
       'insulated containers.',
       350, true
 where not exists (select 1 from applications where controlled_id = 'APP-350');


-- ============================================================================
-- 4  RE-POINT APP-320 INTO APP-310, THEN RETIRE IT
-- ============================================================================
-- Zero rows on this database. Written to be correct anywhere.
do $$
declare
    src integer;
    dst integer;
    moved integer := 0;
    n integer;
begin
    select id into src from applications where controlled_id = 'APP-320';
    select id into dst from applications where controlled_id = 'APP-310';

    if src is null then
        raise notice 'APP-320 not present - nothing to re-point.';
        return;
    end if;
    if dst is null then
        raise exception 'APP-310 is missing. Refusing to retire APP-320 with '
                        'nowhere to send its references.';
    end if;

    update foam_grades set application_id = dst where application_id = src;
    get diagnostics n = row_count; moved := moved + n;
    update recipe_versions set application_id = dst where application_id = src;
    get diagnostics n = row_count; moved := moved + n;
    update reference_formulations set application_id = dst where application_id = src;
    get diagnostics n = row_count; moved := moved + n;
    update reference_formulation_families set application_id = dst where application_id = src;
    get diagnostics n = row_count; moved := moved + n;

    raise notice 'APP-320 -> APP-310: % reference(s) re-pointed.', moved;

    -- Prove it rather than trust it. R2-WP4 deletes this row, and a delete
    -- with a live reference still on it either fails or orphans data.
    select count(*) into n from (
        select 1 from foam_grades where application_id = src
        union all select 1 from recipe_versions where application_id = src
        union all select 1 from reference_formulations where application_id = src
        union all select 1 from reference_formulation_families where application_id = src
    ) remaining;
    if n > 0 then
        raise exception 'APP-320 still carries % reference(s) after re-point. '
                        'Refusing to retire it.', n;
    end if;

    update applications set is_active = false where id = src;
end $$;


-- ============================================================================
-- 5  RETIRE APP-300, ITS THREE REFERENCES TO NULL
-- ============================================================================
-- Not re-pointed. Set to NULL, deliberately, per ruling sections 4 and 5.
-- APP-300 was an umbrella; sending its rows to any one of the narrower records
-- would assert an application the evidence does not support.
do $$
declare
    src integer;
    cleared integer := 0;
    n integer;
begin
    select id into src from applications where controlled_id = 'APP-300';
    if src is null then
        raise notice 'APP-300 not present - nothing to clear.';
        return;
    end if;

    -- A Product Grade or Recipe Version pointing at APP-300 would be a live
    -- product claim, not a reference formulation, and clearing it silently
    -- would lose it. There are none today; if one appears, stop.
    select count(*) into n from foam_grades where application_id = src;
    if n > 0 then
        raise exception 'APP-300 carries % product grade(s). R2-WP1 recorded '
                        'none. Stop and re-map before retiring it.', n;
    end if;
    select count(*) into n from recipe_versions where application_id = src;
    if n > 0 then
        raise exception 'APP-300 carries % recipe version(s). R2-WP1 recorded '
                        'none. Stop and re-map before retiring it.', n;
    end if;

    update reference_formulations set application_id = null where application_id = src;
    get diagnostics n = row_count; cleared := cleared + n;
    update reference_formulation_families set application_id = null where application_id = src;
    get diagnostics n = row_count; cleared := cleared + n;

    raise notice 'APP-300: % reference formulation(s) set to NULL.', cleared;

    update applications set is_active = false where id = src;
end $$;


-- ============================================================================
-- 6  TAG THE ACTIVE MASTER
-- ============================================================================
-- Every active Application Area in this database is a rigid-foam end use.
-- Tagged explicitly by controlled_id rather than by a blanket update, so a
-- record added later without a tag stays visibly untagged instead of being
-- silently called Rigid.
update applications set pu_material_family = 'Rigid'
 where controlled_id in ('APP-100', 'APP-210', 'APP-310', 'APP-330', 'APP-340', 'APP-350');

-- The two retired records keep whatever tag they had (none) - they are on
-- their way out in R2-WP4 and tagging them would suggest otherwise.


-- ============================================================================
-- 7  GUARD: THE TAG VOCABULARY MUST MATCH R1'S
-- ============================================================================
-- Same seven values as ck_pumf_controlled_vocabulary on pu_material_families.
-- R2-WP3 validates that a Product Grade's Application Area carries the same
-- family value as the grade's own family; that comparison is only meaningful
-- if both sides are drawn from one vocabulary. NULL is permitted so a record
-- can exist before it is classified.
alter table applications drop constraint if exists ck_applications_pumf_vocabulary;
alter table applications add constraint ck_applications_pumf_vocabulary
    check (
        pu_material_family is null
        or pu_material_family in (
            'Molded Foam', 'Rigid', 'Coatings', 'Adhesives',
            'Sealants', 'Elastomers', 'TPU'
        )
    );


-- ============================================================================
-- 8  EXIT CHECK
-- ============================================================================
do $$
declare active_n integer; untagged integer; still_linked integer;
begin
    select count(*) into active_n from applications where is_active;
    if active_n <> 6 then
        raise exception 'Expected 6 active Application Areas after R2-WP2, found %.', active_n;
    end if;

    select count(*) into untagged from applications
     where is_active and pu_material_family is null;
    if untagged > 0 then
        raise exception '% active Application Area(s) carry no PU Material '
                        'Family tag.', untagged;
    end if;

    select count(*) into still_linked from (
        select 1 from foam_grades g join applications a on a.id = g.application_id
         where not a.is_active
        union all
        select 1 from recipe_versions rv join applications a on a.id = rv.application_id
         where not a.is_active
        union all
        select 1 from reference_formulations rf join applications a on a.id = rf.application_id
         where not a.is_active
        union all
        select 1 from reference_formulation_families rff join applications a on a.id = rff.application_id
         where not a.is_active
    ) x;
    if still_linked > 0 then
        raise exception '% row(s) still reference a retired Application Area.', still_linked;
    end if;

    raise notice 'R2-WP2 exit check passed: 6 active, all tagged, no live '
                 'reference to a retired record.';
end $$;
