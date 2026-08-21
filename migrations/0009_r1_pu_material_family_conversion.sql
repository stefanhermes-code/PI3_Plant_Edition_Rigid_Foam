-- R1-WP1, WP2, WP4, WP5. Redesign Migration Plan v3, Package B.
--
-- The DATA half of the Product Family to PU Material Family conversion. The
-- object rename is 0010; dropping the free-text Application column is 0011.
-- Split that way so each step is independently re-runnable and so nothing is
-- destroyed before the text it holds has been written down.
--
-- ============================================================================
-- R1-WP1  CAPTURE BEFORE DESTROYING
-- ============================================================================
-- These values exist nowhere else. 0011 drops the column that holds the first
-- three; this migration deletes the row that holds the fourth. Recorded here
-- verbatim so the artifact itself is the record, not a document beside it.
--
--   product_families.application (free text) - the only Application Area
--   content in the system before R2 creates the controlled field:
--     id 3  Cold Room Panels  -> "Cold-room wall/ceiling panel"
--     id 4  Insulation        -> "Refrigerator "        (trailing space is in
--                                                        the data; preserved)
--     id 5  Rigid PIR foam    -> "Insulation panel / board reference chemistry"
--
--   product_families.customer_segment - one non-empty value in the database:
--     id 5  Rigid PIR foam    -> "Insulated panel / board manufacturing"
--
-- ============================================================================
-- R1-WP5  THE ORPHANED CUSTOMER SEGMENT - DISPOSITION RECORDED
-- ============================================================================
-- Stefan's ruling moves Customer Segment down to Product Grade: within one
-- Application Area there can be several grades serving different segments.
--
-- That works for every row except one. The only populated value sits on id 5,
-- the row this migration DELETES, and id 5 carries zero product grades. There
-- is no destination to move it to.
--
-- Charlie's ruling allows either disposition provided it is recorded: assign
-- it to RF-COLDROOM-001 "when semantically correct", or retire it.
--
-- DECISION: RETIRE, value preserved in this artifact.
--
-- Reasoning. The value belonged to "Rigid PIR foam", a row named after a
-- chemistry, and describes who buys insulated panel and board. RF-COLDROOM-001
-- is a cold-room panel grade under a different family row that never carried a
-- customer segment. Moving the text across would not be migrating a fact - it
-- would be asserting one about a grade nobody has said it applies to, and it
-- would look like migrated data ever after. Losing a fact is recoverable from
-- this file; inventing one is not.
--
-- If PTU or HTC Global say the segment does apply to that grade, it is one
-- UPDATE, made deliberately, with a reason.
--
-- ============================================================================
-- R1-WP2  THE CONTROLLED VOCABULARY
-- ============================================================================
-- Seven values, Stefan's final list. Enforced as a CHECK constraint with the
-- vocabulary inline rather than a separate master table - the same shape
-- Decision 3 used for chemical_role, which Charlie accepted. A fixed list of
-- seven that changes only by ruling does not need a table to administer it.
--
-- Flexible slabstock is deliberately absent: that is the Flexible Foam
-- Edition, a separate application.
--
-- Re-runnable throughout.

-- --- WP4: convert the three rows to their controlled value ------------------
update product_families set name = 'Rigid'
 where name in ('Cold Room Panels', 'Insulation', 'Rigid PIR foam');

-- --- WP4: merge the two rows that belong to the same plant ------------------
-- Renaming both to "Rigid" would leave one plant holding two identical
-- families. The application already treats (plant_id, lower(name)) as the
-- identity of a family - its import path de-duplicates on exactly that pair -
-- so this is a merge, not a rename. "Rigid PIR foam" carries zero product
-- grades, so nothing has to be re-pointed first; the guard below proves that
-- rather than trusting it.
do $$
declare survivor_id integer; doomed_id integer; grades integer;
begin
    select id into doomed_id from product_families
     where plant_id = 3 and id = 5;
    if doomed_id is null then
        return;  -- already merged
    end if;
    select id into survivor_id from product_families
     where plant_id = 3 and id = 3;
    if survivor_id is null then
        raise exception 'R1-WP4: expected surviving family id 3 on plant 3, not found';
    end if;
    select count(*) into grades from foam_grades where product_family_id = doomed_id;
    if grades <> 0 then
        raise exception 'R1-WP4: family % carries % product grade(s); re-point them before merging', doomed_id, grades;
    end if;
    delete from product_families where id = doomed_id;
end $$;

-- --- WP2: constrain the name to the controlled vocabulary -------------------
alter table product_families drop constraint if exists ck_pumf_controlled_vocabulary;
alter table product_families
    add constraint ck_pumf_controlled_vocabulary check (
        name in ('Molded Foam', 'Rigid', 'Coatings', 'Adhesives',
                 'Sealants', 'Elastomers', 'TPU')
    );

-- --- WP5: Customer Segment moves down to Product Grade ----------------------
alter table foam_grades add column if not exists customer_segment varchar(200);

-- Migrate every value that HAS a destination grade. The one that does not is
-- retired by the merge above, per the recorded disposition.
update foam_grades g
   set customer_segment = f.customer_segment
  from product_families f
 where g.product_family_id = f.id
   and f.customer_segment is not null
   and btrim(f.customer_segment) <> ''
   and g.customer_segment is null;

alter table product_families drop column if exists customer_segment;
