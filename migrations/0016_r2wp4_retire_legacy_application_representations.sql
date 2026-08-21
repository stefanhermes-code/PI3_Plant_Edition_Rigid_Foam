-- R2-WP4. Redesign Migration Plan v5, Package C. Gate R-G2.
--
-- The destructive half of R2: remove the legacy free-text Application field
-- from PU Material Family, and delete APP-300 and APP-320 from the controlled
-- master. One global Application Area master remains.
--
-- Plan v5 R2-WP4: "remove the legacy free-text family Application field.
-- Remove APP-300 and APP-320 from the active controlled master only after
-- their live references have been cleared or re-pointed and the before/after
-- evidence is complete."
--
-- Both conditions are met. They are proved below rather than asserted, because
-- this artifact drops data and a wrong assumption here is not recoverable from
-- the file.
--
-- ============================================================================
-- CAPTURE BEFORE DESTROYING
-- ============================================================================
-- pu_material_families.application, every value, verbatim as at 21 August 2026.
-- These three strings were first captured in 0009's R1-WP1 block; they are
-- repeated here because THIS is the artifact that destroys the column, and a
-- capture that lives only in an earlier file is a capture someone has to know
-- to go looking for.
--
--   id 3  Rigid  (HTC Global - Phase 1 Plant)  -> "Cold-room wall/ceiling panel"
--   id 4  Rigid  (PTU Korat)                   -> "Refrigerator "
--                                                  (trailing space is in the
--                                                   data; preserved as found)
--   id 6  Coatings (HTC Global - Phase 1 Plant) -> null
--
-- Where each one went, so the column can be reconstructed if it is ever
-- needed:
--
--   "Cold-room wall/ceiling panel"  -> APP-210, and RF-COLDROOM-001, the one
--                                      grade under family 3, already carries
--                                      APP-210.
--   "Refrigerator "                 -> APP-310 Refrigerator/Freezer
--                                      Insulation, and RF-Refrigerator-001,
--                                      the one grade under family 4, already
--                                      carries APP-310.
--   null                            -> nothing to carry.
--
-- The Application Area now lives on the Product Grade, which is where R2 put
-- it. The family-level free-text field was the thing that let one family hold
-- an application, a market and a chemistry at once - the defect R1 started
-- from. This removes the last of it.
--
-- APP-300 and APP-320: retired at R2-WP2 (0011), zero references then and
-- zero now. Stefan confirmed the removal on 21 August: "Ok so I agree to take
-- out APP 300 and APP 320. They overlap with APP-310."
--
-- Re-runnable.


-- ============================================================================
-- 1  GUARD: NOTHING MAY STILL POINT AT THE TWO RECORDS
-- ============================================================================
do $$
declare n integer; offenders text;
begin
    select count(*), string_agg(src, ', ') into n, offenders from (
        select 'foam_grades#' || g.id::text as src
          from foam_grades g join applications a on a.id = g.application_id
         where a.controlled_id in ('APP-300', 'APP-320')
        union all
        select 'recipe_versions#' || rv.id::text
          from recipe_versions rv join applications a on a.id = rv.application_id
         where a.controlled_id in ('APP-300', 'APP-320')
        union all
        select 'reference_formulations#' || rf.id::text
          from reference_formulations rf join applications a on a.id = rf.application_id
         where a.controlled_id in ('APP-300', 'APP-320')
        union all
        select 'reference_formulation_families#' || rff.id::text
          from reference_formulation_families rff join applications a on a.id = rff.application_id
         where a.controlled_id in ('APP-300', 'APP-320')
    ) x;
    if n > 0 then
        raise exception 'APP-300/APP-320 still referenced by % row(s): %. '
                        'R2-WP4 refuses to delete a record something points at.',
                        n, offenders;
    end if;
    raise notice 'APP-300/APP-320: zero live references, safe to remove.';
end $$;


-- ============================================================================
-- 2  GUARD: EVERY GRADE THAT HAD A FAMILY APPLICATION HAS A GRADE-LEVEL ONE
-- ============================================================================
-- The column being dropped held the only Application Area content in the
-- system before R2. Dropping it while a grade under one of those families
-- still had no Application Area of its own would lose the information rather
-- than move it.
do $$
declare n integer; offenders text;
begin
    select count(*), string_agg(g.grade_name, ', ') into n, offenders
      from foam_grades g
      join pu_material_families f on f.id = g.pu_material_family_id
     where f.application is not null
       and btrim(f.application) <> ''
       and g.application_id is null;
    if n > 0 then
        raise exception '% product grade(s) sit under a family that still carries '
                        'free-text Application and have no Application Area of '
                        'their own: %. Assign them before the column is dropped.',
                        n, offenders;
    end if;
    raise notice 'Every grade under an Application-bearing family has its own Application Area.';
end $$;


-- ============================================================================
-- 3  DROP THE LEGACY COLUMN
-- ============================================================================
alter table pu_material_families drop column if exists application;


-- ============================================================================
-- 4  DELETE THE TWO RETIRED RECORDS
-- ============================================================================
delete from applications where controlled_id in ('APP-300', 'APP-320');


-- ============================================================================
-- 5  EXIT CHECK
-- ============================================================================
do $$
declare col_n integer; retired_n integer; total_n integer; untagged integer;
begin
    select count(*) into col_n from information_schema.columns
     where table_name = 'pu_material_families' and column_name = 'application';
    if col_n <> 0 then
        raise exception 'pu_material_families.application still exists.';
    end if;

    select count(*) into retired_n from applications where not is_active;
    if retired_n <> 0 then
        raise exception '% retired Application Area(s) remain in the master.', retired_n;
    end if;

    select count(*) into total_n from applications;
    if total_n <> 10 then
        raise exception 'Expected 10 Application Areas after R2-WP4, found %.', total_n;
    end if;

    select count(*) into untagged from applications where pu_material_family is null;
    if untagged > 0 then
        raise exception '% Application Area(s) carry no PU Material Family tag.', untagged;
    end if;

    raise notice 'R2-WP4 complete: legacy column gone, 10 records, none retired, all tagged.';
end $$;
