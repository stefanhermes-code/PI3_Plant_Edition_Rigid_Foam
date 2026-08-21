-- R2-WP2 correction. Redesign Migration Plan v5, Package C.
--
-- APP-330's description, which 0011 left describing the record's OLD meaning.
-- Carried forward rather than corrected in place: 0011 is applied and
-- ledgered, and an applied artifact records what ran that day.
--
-- WHAT WENT WRONG IN 0011
--
-- 0011 renamed APP-330 from "Commercial refrigeration equipment" to
-- "Industrial Refrigeration Insulation" and did not touch its description,
-- which still read:
--
--   "Cabinet, display case, cold counter or related refrigerated equipment."
--
-- In the same migration I DID rewrite APP-310's description when its meaning
-- changed. Two renames in one artifact, one of them finished. The browser
-- check found it; nothing in the test suite could, because a stale description
-- is valid data.
--
-- WHY IT IS A SCOPE CHANGE, NOT A WORDING FIX
--
-- Commercial refrigeration is retail equipment - display cases, cold counters.
-- Industrial refrigeration is cold stores and built-in cooling cells. Those are
-- different end uses, so the rename changed what the record MEANS. Replacing
-- the description is therefore recording a decision, not tidying prose, and the
-- decision is not mine to invent.
--
-- Stefan, 21 August 2026, who authored the rename: "Industrial Refrigeration is
-- exactly that, cold stores, build-in cooling cells, etc." The text below is
-- his definition.
--
-- (Recorded because I had attributed the rename to Charlie in the R2-WP2
-- return. It appeared in Charlie's ruling document; the content was Stefan's.)
--
-- ZERO ROWS AFFECTED. APP-330 carries no product grades, recipe versions,
-- reference formulations or reference formulation families - checked live
-- before writing this. Nothing is reclassified by the change of meaning; the
-- record has never been used.
--
-- Re-runnable.

update applications
   set description = 'Cold stores, built-in cooling cells and comparable '
                     'industrial refrigeration installations. Distinct from '
                     'retail/commercial refrigerated equipment, which this '
                     'record covered before R2-WP2 renamed it.'
 where controlled_id = 'APP-330';

do $$
declare n integer; used integer;
begin
    select count(*) into n from applications
     where controlled_id = 'APP-330'
       and name = 'Industrial Refrigeration Insulation'
       and description like 'Cold stores, built-in cooling cells%';
    if n <> 1 then
        raise exception 'APP-330 did not take the corrected description (% matching row(s)).', n;
    end if;

    -- The claim above ("zero rows affected") is asserted, not assumed. If a
    -- grade has since been assigned to APP-330, the change of meaning now
    -- reclassifies real data and that needs a decision, not a migration.
    select count(*) into used from (
        select 1 from foam_grades g join applications a on a.id = g.application_id
         where a.controlled_id = 'APP-330'
        union all
        select 1 from recipe_versions rv join applications a on a.id = rv.application_id
         where a.controlled_id = 'APP-330'
    ) x;
    if used > 0 then
        raise exception 'APP-330 now carries % live product record(s). Its meaning '
                        'changed at R2-WP2; reclassifying live data needs a ruling, '
                        'not this migration.', used;
    end if;

    raise notice 'APP-330 description corrected; 0 live records affected.';
end $$;
