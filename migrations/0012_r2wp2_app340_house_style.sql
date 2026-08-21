-- R2-WP2 correction. Redesign Migration Plan v5, Package C.
--
-- One controlled name. Carried forward rather than corrected in place, because
-- 0011 is applied and ledgered and Charlie's rule is that an applied artifact
-- is immutable - corrections travel in later artifacts so the record of what
-- actually ran on a given day stays true.
--
-- WHAT 0011 SAYS, AND WHY IT IS WRONG
--
-- 0011 contains a comment explaining that APP-340 was deliberately NOT
-- renamed. The reasoning was that the ruling said "Keep APP-340 as
-- Water-Heater Insulation" while the stored name read "Water-heater
-- insulation" - the same words in different case - and that "keep" meant
-- leave it alone.
--
-- Stefan's response: the meaning was obvious and raising it was making work
-- out of nothing. He is right. The ruling's own list of the refrigeration
-- group reads "Refrigerator/Freezer Insulation, Industrial Refrigeration
-- Insulation, Cool Box Insulation and Water-Heater Insulation", and 0011
-- applied that spelling to the first three while leaving the fourth
-- inconsistent with its own siblings.
--
-- The comment in 0011 stands as written. This artifact is the correction.
--
-- APP-100 and APP-210 are NOT touched. The ruling says retain them unchanged
-- and their sentence-case names are the ones it retained.
--
-- Re-runnable.

update applications
   set name = 'Water-Heater Insulation'
 where controlled_id = 'APP-340'
   and name <> 'Water-Heater Insulation';

do $$
declare n integer;
begin
    select count(*) into n from applications
     where controlled_id = 'APP-340' and name = 'Water-Heater Insulation';
    if n <> 1 then
        raise exception 'APP-340 did not take the corrected name (% matching row(s)).', n;
    end if;
    raise notice 'APP-340 -> Water-Heater Insulation.';
end $$;
