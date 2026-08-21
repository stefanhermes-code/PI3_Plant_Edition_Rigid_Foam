-- R2-WP2 correction. Redesign Migration Plan v5, Package C.
--
-- APP-210 and APP-330 overlapped after 0013 gave APP-330 its industrial
-- refrigeration meaning. Both descriptions then covered a cold store, so a
-- panel for a cold room could be classified either way and two people would
-- classify it differently.
--
-- Carried forward rather than corrected in place; 0011 and 0013 are applied
-- and ledgered.
--
-- THE DISTINCTION, AND IT IS NOT A MATTER OF WORDING
--
-- Stefan, 21 August 2026: "APP-210 is a wall, where APP-330 is a room. So the
-- end product for APP-210 is a sandwich panel, and the end product for APP-330
-- is a chemical being put in a room in a building. Totally different."
--
-- The two records sit on the END PRODUCT, not on the market they serve:
--
--   APP-210  the foam is the core of a discrete component. A panel is made in
--            a plant, leaves it, and is installed later by somebody else. The
--            deliverable is the panel.
--
--   APP-330  the foam is applied into the fabric of a room or building. There
--            is no component to ship - the deliverable is the insulated room,
--            and the material is delivered as chemical.
--
-- That is why both can serve a cold store and still be different records. It
-- also decides which is correct without judgement: ask what leaves the plant.
--
-- ZERO ROWS RECLASSIFIED. APP-330 carries nothing. APP-210 carries
-- RF-COLDROOM-001 and one recipe version, and both stay where they are - a
-- cold-room panel is a panel. This artifact changes description text only, and
-- the guard below refuses to run if APP-330 has acquired live records since,
-- because at that point the sharper line reclassifies real data.
--
-- Re-runnable.

update applications
   set description = 'A manufactured sandwich panel for cold rooms, refrigerated '
                     'warehouses and controlled-temperature enclosures. The foam is '
                     'the core of a discrete component that leaves the plant as a '
                     'panel. The end product is the panel, not the room it is later '
                     'installed in - contrast APP-330.'
 where controlled_id = 'APP-210';

update applications
   set description = 'Cold stores, built-in cooling cells and comparable industrial '
                     'refrigeration installations, where the material is applied into '
                     'the fabric of a room or building. The end product is the '
                     'insulated room and the material is delivered as chemical, not '
                     'as a component - contrast APP-210, which is the panel itself. '
                     'Distinct from retail/commercial refrigerated equipment, which '
                     'this record covered before R2-WP2 renamed it.'
 where controlled_id = 'APP-330';

do $$
declare n integer; used integer;
begin
    select count(*) into n from applications
     where (controlled_id = 'APP-210' and description like 'A manufactured sandwich panel%')
        or (controlled_id = 'APP-330' and description like 'Cold stores, built-in cooling cells%'
            and description like '%contrast APP-210%');
    if n <> 2 then
        raise exception 'Expected both descriptions corrected, matched % row(s).', n;
    end if;

    select count(*) into used from (
        select 1 from foam_grades g join applications a on a.id = g.application_id
         where a.controlled_id = 'APP-330'
        union all
        select 1 from recipe_versions rv join applications a on a.id = rv.application_id
         where a.controlled_id = 'APP-330'
    ) x;
    if used > 0 then
        raise exception 'APP-330 now carries % live product record(s). Sharpening the '
                        'boundary against APP-210 would reclassify them; that needs a '
                        'ruling, not this migration.', used;
    end if;

    raise notice 'APP-210 / APP-330 boundary recorded; 0 records reclassified.';
end $$;
