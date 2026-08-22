-- 0025  R3 - continuous versus shot-by-shot, at Production Unit / Cell level
--
-- Charlie's R3 handover v3, section 3: "Production Unit properties: Capture
-- continuous versus shot-by-shot at Production Unit / Cell level as specified
-- in Migration Plan v5. Equipment remains linked to the relevant unit."
--
-- WHAT THIS PROPERTY JOINS
--
-- The application already resolves cycle/shot operation, and it already has a
-- two-tier answer: Machine.cycle_shot_operation_override wins, otherwise
-- ProductionMethod.uses_cycle_shot_operation. The comment on that machine
-- override says what it was standing in for - "a plant running the same
-- Production Method on one cycle/shot cell and one continuous cell". Cell.
-- The property always belonged to the unit; there was nowhere to put it.
--
-- So this adds the middle tier: Machine override, then Production Unit / Cell,
-- then Production Method default.
--
-- NO VALUE IS SET FOR ANY LIVE UNIT, AND THAT IS A RULE RATHER THAN A GAP
--
-- Charlie's WP7 Phase 2 closeout explicitly rejected inferring this from a
-- name - "PM-100 sounds discontinuous, so infer True" - and required
-- evidence-based confirmation per record. Both live Production Methods happen
-- to be named "Discontinuous", which is exactly the trap that ruling was
-- written about. How a real line runs is plant fact, so the column is added
-- and left NULL until somebody who knows the line fills it in. NULL means "not
-- characterised - inherit the Production Method", not "continuous".
--
-- The controlled vocabulary is enforced by a CHECK constraint rather than left
-- to the application, matching ck_pumf_controlled_vocabulary (0009) and
-- ck_applications_pumf_vocabulary (0011).

alter table production_units
    add column if not exists operation_mode varchar(20);

do $$
begin
    if not exists (
        select 1 from pg_constraint con
          join pg_class cl on cl.oid = con.conrelid
         where cl.relname = 'production_units'
           and cl.relnamespace = current_schema()::regnamespace
           and con.conname = 'ck_production_units_operation_mode'
    ) then
        alter table production_units
            add constraint ck_production_units_operation_mode
            check (operation_mode is null
                   or operation_mode in ('Continuous', 'Shot-by-shot'));
    end if;
end $$;

do $$
declare n integer; offenders text;
begin
    select count(*) into n from information_schema.columns
     where table_schema = current_schema() and table_name = 'production_units'
       and column_name = 'operation_mode' and is_nullable = 'YES';
    if n <> 1 then
        raise exception 'production_units.operation_mode is missing or not nullable.';
    end if;

    select count(*) into n from pg_constraint con
      join pg_class cl on cl.oid = con.conrelid
     where cl.relname = 'production_units'
       and cl.relnamespace = current_schema()::regnamespace
       and con.conname = 'ck_production_units_operation_mode';
    if n <> 1 then
        raise exception 'ck_production_units_operation_mode is missing.';
    end if;

    -- Nothing characterised by this migration. Asserted rather than assumed,
    -- because "added the column, invented no facts" is the whole claim.
    select string_agg(controlled_id, ', ' order by controlled_id) into offenders
      from production_units where operation_mode is not null;
    if offenders is not null then
        raise exception 'Unit(s) % already carry an operation mode. 0025 characterises nothing.', offenders;
    end if;

    raise notice 'R3: production unit operation mode added in %. No unit characterised.', current_schema();
end $$;
