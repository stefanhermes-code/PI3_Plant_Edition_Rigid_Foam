-- R3-WP4. The Production Unit / Cell snapshot on a production run.
-- Charlie's "R3-WP4 Historical Run Snapshot Ruling to JC v1", 22 August 2026.
--
-- WHAT THIS RECORDS, AND WHY IT IS A SNAPSHOT
--
-- A run identifies the Equipment / Machine actually used. The Production Unit /
-- Cell is RESOLVED from that equipment and stored here separately, so a later
-- reassignment of the equipment to another unit cannot rewrite what a finished
-- run says happened. Charlie: "the stored Production Unit / Cell is a run
-- record, not a value continuously derived from the machine master."
--
-- That is the whole reason this is a column and not a join.
--
-- THE SET, AND A CORRECTION TO THE EARLIER WORDING
--
-- The R3 handover said "the exact completed-run ID set captured in R0". There
-- is no such set. R0 captured eight production runs, IDs 15 to 22, and every
-- one of them had - and still has - a NULL status. Not one is Completed.
-- Measuring that before building anything is what surfaced it, and Charlie
-- corrected his own instruction:
--
--   "My earlier wording, 'completed-run ID set captured in R0', was therefore
--    wrong. The intended control was the historical run set captured in R0.
--    For this work, the authorised historical backfill set is production run
--    IDs 15 through 22, regardless of their current status. Do not change
--    their status as part of the snapshot migration."
--
-- So this migration backfills all eight and changes no status.
--
-- RE-MEASURED IMMEDIATELY BEFORE APPLICATION, as he required
--
--   Runs 15 to 22, all eight, machine_id = 3 (Panel Foamer 1)
--   Machine 3 resolves to PU-PH1-001 Panel Line 1
--   All eight statuses NULL
--   production_runs table fingerprint bf613a35af47500d82d87c111ce1ce1a,
--   which is the fingerprint R0 recorded - so these are provably the same
--   eight rows R0 captured, unchanged since.
--
-- His stop condition: "If any of those eight run IDs no longer points to
-- machine 3, or machine 3 no longer resolves to PU-PH1-001, stop and return
-- the difference. Do not force the expected value over changed live evidence."
-- Nothing had moved, so the migration proceeds.
--
-- THE BACKFILL RESOLVES; IT DOES NOT ASSUME
--
-- The UPDATE below reads the unit through each run's own machine rather than
-- writing a literal PU-PH1-001. The expected outcome is that all eight land on
-- PU-PH1-001, and the exit check asserts exactly that - but if the data had
-- moved between the re-measurement and the apply, this writes what is true
-- rather than what was expected, and the exit check then fails loudly instead
-- of quietly recording a stale value.
--
-- Re-runnable: the column add is guarded, and the backfill only writes rows
-- whose stored value differs from the resolved one.

alter table production_runs
    add column if not exists production_unit_id integer;

do $$
begin
    -- Scoped to the schema this is running in. Without the namespace filter
    -- the check matches a production_runs in ANY schema, so once live carries
    -- the constraint a probe run would skip creating it and quietly stop
    -- testing the thing it is meant to prove - the artifact would still pass
    -- while exercising less than it did the first time.
    if not exists (
        select 1 from pg_constraint con
          join pg_class cl on cl.oid = con.conrelid
         where cl.relname = 'production_runs'
           and cl.relnamespace = current_schema()::regnamespace
           and con.conname = 'fk_production_runs_production_unit_id'
    ) then
        alter table production_runs
            add constraint fk_production_runs_production_unit_id
            foreign key (production_unit_id) references production_units(id);
    end if;
end $$;

update production_runs r
   set production_unit_id = m.production_unit_id
  from machines m
 where m.id = r.machine_id
   and m.production_unit_id is not null
   and r.production_unit_id is distinct from m.production_unit_id;


-- ============================================================================
-- EXIT CHECK
-- ============================================================================
do $$
declare n integer; offenders text;
begin
    -- The column exists and is nullable. Nullable on purpose: a run created
    -- against equipment with no unit is legal until it is Completed, and the
    -- completion guard - which lives in the application, at the state
    -- transition - is what refuses that case. A NOT NULL here would refuse it
    -- at creation instead, which is not what was ruled.
    select count(*) into n from information_schema.columns
     where table_schema = current_schema() and table_name = 'production_runs'
       and column_name = 'production_unit_id' and is_nullable = 'YES';
    if n <> 1 then
        raise exception 'production_runs.production_unit_id is missing or not nullable.';
    end if;

    -- Every run whose machine resolves to a unit carries that unit. Written as
    -- a comparison against the live relationship rather than against a literal,
    -- so this holds on a probe schema with different ids.
    select string_agg(r.id::text, ', ' order by r.id) into offenders
      from production_runs r
      join machines m on m.id = r.machine_id
     where m.production_unit_id is not null
       and r.production_unit_id is distinct from m.production_unit_id;
    if offenders is not null then
        raise exception 'Runs whose snapshot does not match their equipment''s unit: %.', offenders;
    end if;

    -- Nothing was invented. A run whose machine has no unit keeps a NULL
    -- snapshot rather than being given a guess.
    select string_agg(r.id::text, ', ' order by r.id) into offenders
      from production_runs r
      left join machines m on m.id = r.machine_id
     where r.production_unit_id is not null
       and (m.id is null or m.production_unit_id is distinct from r.production_unit_id);
    if offenders is not null then
        raise exception 'Runs carrying a snapshot their equipment does not support: %.', offenders;
    end if;

    -- Statuses untouched. Charlie: "Do not change their status as part of the
    -- snapshot migration." Asserted rather than assumed, because a backfill
    -- that quietly marked rows Completed would satisfy every check above.
    select count(*) into n from production_runs where status is not null;
    if n <> 0 then
        raise exception '% production run(s) now carry a status; every one was NULL before this migration.', n;
    end if;

    raise notice 'R3-WP4: production run unit snapshot added and backfilled in %.', current_schema();
end $$;
