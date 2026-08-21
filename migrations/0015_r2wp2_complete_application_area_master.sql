-- R2-WP2 completion. Redesign Migration Plan v5, Package C.
--
-- The four Application Areas the master was still missing, and the correction
-- of how the earlier five were chosen. Carried forward; 0011, 0013 and 0014
-- are applied and ledgered.
--
-- ============================================================================
-- WHAT WENT WRONG IN THE R2-WP1 MAPPING, AND WHY IT MATTERS BEYOND THIS FILE
-- ============================================================================
-- R2-WP1 required every legacy Production Method code to resolve to an
-- Application Area. Five had no obvious destination, so I proposed creating
-- one per code, each named after the code it came from:
--
--   Field-installed cavity insulation, Sprayed insulation,
--   Block and cut-to-shape insulation, Pre-insulated pipe,
--   Structural and composite element.
--
-- That made the destination list a copy of the list being retired. I had
-- warned Charlie in the same document that production method and application
-- are different axes, and then collapsed them anyway - the error was in my own
-- work, not in his plan.
--
-- Stefan's test is what exposed it: what is the END PRODUCT - what leaves the
-- plant? "Sprayed insulation" has no answer. Spraying is how; a roof is what.
--
-- Applying that test, with Stefan's rulings of 21 August 2026:
--
--   Sprayed insulation      -> the end use is a ROOF. Its own record, and NOT
--                              a rename of APP-100: APP-100 carries eight PIR
--                              board/panel reference formulations and two
--                              families, none of them sprayed. Narrowing
--                              APP-100 to roofs would mis-describe all ten.
--   Field cavity            -> "it can be a room but it can also be in
--                              mining". So not APP-330, and not a field-cavity
--                              record either - the missing END USE was mining.
--                              Stefan: "Just change Field Cavity Insulation
--                              into Mining Rock Stabilisation."
--   Block and cut-to-shape  -> "definitely a separate application area, it is
--                              not always insulation". The name therefore does
--                              NOT carry the word insulation - blocks are cut
--                              for tooling board, buoyancy and packaging as
--                              well as for insulation.
--   Pre-insulated pipe      -> "definitely a separate application area".
--   Structural & composite  -> dropped. Stefan agreed the description is too
--                              vague to classify anything consistently.
--
-- CREATED NOW, NOT ON FIRST USE. Charlie ruled that block and pipe should be
-- created on first genuine use to avoid empty records. Stefan overruled that
-- on 21 August: "On Charlie rule about created on first genuine use is
-- nonsense, we create now." Recorded here because it reverses an accepted
-- ruling and the R-G2 return has to carry it.
--
-- CONTROLLED IDS AND BANDS. Charlie ruled the APP numbering is an identifier
-- and an ordering convention, not a parent-child hierarchy, so these numbers
-- carry no structure - they only decide sort order and give each record a
-- stable name to be referred to by:
--
--   100s  building envelope        APP-100 building, APP-110 roof spray
--   200s  manufactured forms       APP-210 panel,    APP-220 block/cut shape
--   300s  refrigeration/appliance  APP-310/330/340/350
--   400s  pipe and process         APP-410 pre-insulated pipe
--   500s  non-insulation uses      APP-510 mining rock stabilisation
--
-- Every new record is tagged Rigid. Nothing here has a product grade yet, so
-- any tag can still be corrected on the Application Areas page - the page
-- refuses a re-tag only once grades are assigned.
--
-- Re-runnable.

insert into applications (controlled_id, name, description, sort_order, is_active, pu_material_family)
select v.controlled_id, v.name, v.description, v.sort_order, true, 'Rigid'
  from (values
    ('APP-110', 'Roof Spray Foam',
     'Rigid foam sprayed in place onto a roof or comparable building surface. '
     'The end product is the finished roof, and the material is delivered as '
     'chemical rather than as a component - contrast APP-100, which covers '
     'manufactured board and panel products for the building envelope.',
     110),
    ('APP-220', 'Block and Cut-to-Shape',
     'Foam produced as block and cut to shape. Deliberately not named as an '
     'insulation application: cut shapes serve tooling board, buoyancy, '
     'packaging and pattern work as well as insulation, and the end product is '
     'the block or the cut part itself.',
     220),
    ('APP-410', 'Pre-insulated Pipe',
     'Factory-produced pre-insulated pipe. The end product is the pipe, '
     'complete with its insulation and jacket, leaving the plant as one item.',
     410),
    ('APP-510', 'Mining Rock Stabilisation',
     'Material injected into rock or ground for stabilisation, void filling '
     'and consolidation in mining and civil works. Not an insulation '
     'application - the end product is the stabilised ground.',
     510)
  ) as v(controlled_id, name, description, sort_order)
 where not exists (
     select 1 from applications a where a.controlled_id = v.controlled_id
 );

do $$
declare active_n integer; untagged integer; missing text;
begin
    select string_agg(x.cid, ', ') into missing
      from (values ('APP-110'), ('APP-220'), ('APP-410'), ('APP-510')) as x(cid)
     where not exists (select 1 from applications a where a.controlled_id = x.cid);
    if missing is not null then
        raise exception 'R2-WP2 completion did not create: %', missing;
    end if;

    select count(*) into active_n from applications where is_active;
    if active_n <> 10 then
        raise exception 'Expected 10 active Application Areas, found %.', active_n;
    end if;

    select count(*) into untagged from applications
     where is_active and pu_material_family is null;
    if untagged > 0 then
        raise exception '% active Application Area(s) carry no PU Material Family tag.', untagged;
    end if;

    raise notice 'R2-WP2 master complete: 10 active, all tagged.';
end $$;
