-- 0023  R3 - the Application Area snapshot on a production run
--
-- Charlie's R3 handover v3, section 3: "The authorised one-time migration may
-- backfill the controlled Application Area and Production Unit snapshot
-- fields. Record row-by-row before/after evidence and prove every other
-- completed-run field is unchanged." And his R-G3 exit condition: "each
-- completed run retains a row-by-row verified frozen Application Area."
--
-- WHY THIS COMES BEFORE THE APPLICABILITY MIGRATION
--
-- Process-setting applicability is about to resolve through Application Area
-- as its default tier. A run's Application Area would otherwise be read live
-- through foam_grades.application_id - which is exactly the derivation that
-- migration 0022 removed for the Production Unit / Cell. Re-classify a Product
-- Grade to another Application Area and every finished run would silently
-- start resolving a different rule set than the one it actually ran under.
-- So the run records its own Application Area first, and the applicability
-- work reads that.
--
-- Same shape as 0022 deliberately: nullable column, FK scoped to the current
-- schema, backfill only where the source has a value, and no other column
-- written.

alter table production_runs
    add column if not exists application_id integer;

do $$
begin
    if not exists (
        select 1 from pg_constraint con
          join pg_class cl on cl.oid = con.conrelid
         where cl.relname = 'production_runs'
           and cl.relnamespace = current_schema()::regnamespace
           and con.conname = 'fk_production_runs_application_id'
    ) then
        alter table production_runs
            add constraint fk_production_runs_application_id
            foreign key (application_id) references applications(id);
    end if;
end $$;

-- The snapshot is taken from the run's OWN Product Grade, at this moment.
-- Runs whose grade carries no Application Area are left NULL rather than
-- guessed at - the same treatment 0022 gave equipment with no unit.
update production_runs r
   set application_id = g.application_id
  from foam_grades g
 where g.id = r.foam_grade_id
   and g.application_id is not null
   and r.application_id is distinct from g.application_id;

do $$
declare n integer; m integer; offenders text;
begin
    select count(*) into n from information_schema.columns
     where table_schema = current_schema() and table_name = 'production_runs'
       and column_name = 'application_id' and is_nullable = 'YES';
    if n <> 1 then
        raise exception 'production_runs.application_id is missing or not nullable.';
    end if;

    -- Every run whose grade has an Application Area now carries it.
    select string_agg(r.id::text, ', ' order by r.id) into offenders
      from production_runs r
      join foam_grades g on g.id = r.foam_grade_id
     where g.application_id is not null
       and r.application_id is distinct from g.application_id;
    if offenders is not null then
        raise exception 'Runs whose snapshot does not match their grade''s Application Area: %.', offenders;
    end if;

    -- And nothing was invented: no run carries an area its own grade does not
    -- have. This is the check the backfill could pass vacuously without, since
    -- every live grade happens to be classified.
    select string_agg(r.id::text, ', ' order by r.id) into offenders
      from production_runs r
      left join foam_grades g on g.id = r.foam_grade_id
     where r.application_id is not null
       and (g.id is null or g.application_id is distinct from r.application_id);
    if offenders is not null then
        raise exception 'Runs carrying an Application Area their Product Grade does not have: %.', offenders;
    end if;

    -- The postcondition stated structurally rather than as a count of the
    -- current data: as many snapshots as there are runs on a classified grade.
    select count(*) into n from production_runs where application_id is not null;
    select count(*) into m
      from production_runs r join foam_grades g on g.id = r.foam_grade_id
     where g.application_id is not null;
    if n <> m then
        raise exception 'Snapshot count % does not match the % run(s) on a classified Product Grade.', n, m;
    end if;

    raise notice 'R3: production run Application Area snapshot added and backfilled in %.', current_schema();
end $$;
