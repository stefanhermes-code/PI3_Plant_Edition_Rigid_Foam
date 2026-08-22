-- 0024  R3 - process-setting applicability gains Application Area and
--            Production Unit / Cell scope
--
-- Charlie's R3 handover v3, section 3: "Resolution order is Machine, then
-- Production Unit / Cell, then Application Area, then Global." Migration Plan
-- v5, R3-WP2: "Extend process_setting_applicabilities with Production Unit /
-- Cell and Application Area references as required."
--
-- THIS MIGRATION MOVES NO ROWS. It is the schema half only.
--
-- The row conversion - 37 method-only rows to Application Area defaults, 9
-- machine-plus-method rows to Machine + Application Area - needs an
-- Application Area destination for every legacy Production Method. 43 of the
-- 50 live rows belong to PM-800 at PTU Korat, whose master data is still being
-- verified, so that destination cannot be evidenced yet. Plan v5 R3-WP1 is
-- explicit about what to do here: "unresolved master-data details are returned
-- as data issues before write." Converting the 7 rows that CAN be evidenced
-- and leaving 43 behind would be worse than converting none, because the
-- resolver would then have to arbitrate between the two tiers on live data.
--
-- So the schema and the resolution order land now, the legacy method rows keep
-- resolving exactly as they do today, and the conversion follows as its own
-- artifact once PTU is verified. The legacy production_method_id column stays
-- either way until Production Method retirement, which Plan v5 already
-- sequences after this.
--
-- THE INDEX IS THE POINT OF THE SCHEMA HALF
--
-- ix_psa_unique_active_scope exists because two active rows at the SAME scope
-- made the winner arbitrary - Charlie's WP7 Phase 1 closeout, item 2.1. Adding
-- two scope columns without widening that index would reopen exactly that
-- defect for the new tiers, so the index is rebuilt over the full scope tuple
-- in the same migration that adds the columns, not in a later one.

alter table process_setting_applicabilities
    add column if not exists application_id integer;
alter table process_setting_applicabilities
    add column if not exists production_unit_id integer;

do $$
begin
    if not exists (
        select 1 from pg_constraint con
          join pg_class cl on cl.oid = con.conrelid
         where cl.relname = 'process_setting_applicabilities'
           and cl.relnamespace = current_schema()::regnamespace
           and con.conname = 'fk_psa_application_id'
    ) then
        alter table process_setting_applicabilities
            add constraint fk_psa_application_id
            foreign key (application_id) references applications(id);
    end if;

    if not exists (
        select 1 from pg_constraint con
          join pg_class cl on cl.oid = con.conrelid
         where cl.relname = 'process_setting_applicabilities'
           and cl.relnamespace = current_schema()::regnamespace
           and con.conname = 'fk_psa_production_unit_id'
    ) then
        alter table process_setting_applicabilities
            add constraint fk_psa_production_unit_id
            foreign key (production_unit_id) references production_units(id);
    end if;
end $$;

-- Rebuilt over the full scope tuple. Dropped by name and recreated rather than
-- altered, because a partial unique index's expression list cannot be changed
-- in place.
drop index if exists ix_psa_unique_active_scope;

create unique index ix_psa_unique_active_scope
    on process_setting_applicabilities (
        setting_definition_id,
        coalesce(application_id, -1),
        coalesce(production_unit_id, -1),
        coalesce(production_method_id, -1),
        coalesce(machine_id, -1)
    )
    where active = true;

do $$
declare n integer; offenders text;
begin
    select count(*) into n from information_schema.columns
     where table_schema = current_schema()
       and table_name = 'process_setting_applicabilities'
       and column_name in ('application_id', 'production_unit_id')
       and is_nullable = 'YES';
    if n <> 2 then
        raise exception 'Both new applicability scope columns must exist and be nullable; found %.', n;
    end if;

    select count(*) into n from pg_class
     where relname = 'ix_psa_unique_active_scope'
       and relnamespace = current_schema()::regnamespace;
    if n <> 1 then
        raise exception 'ix_psa_unique_active_scope is missing after rebuild.';
    end if;

    -- No row moved. Stated as an assertion rather than left implicit, because
    -- "the schema half only" is the whole claim this artifact makes.
    select count(*) into n from process_setting_applicabilities
     where application_id is not null or production_unit_id is not null;
    if n <> 0 then
        raise exception '% applicability row(s) already carry the new scope. 0024 moves no rows.', n;
    end if;

    -- The transitional invariant that makes the two-phase split safe: no
    -- definition may be contested by an active Application Area row and an
    -- active legacy Method row at once. Trivially true now, and it is what
    -- will fail loudly if a later conversion is left half done.
    select string_agg(distinct s.setting_definition_id::text, ', ') into offenders
      from process_setting_applicabilities s
     where s.active
       and s.application_id is not null
       and exists (
            select 1 from process_setting_applicabilities t
             where t.active
               and t.setting_definition_id = s.setting_definition_id
               and t.production_method_id is not null
               and t.application_id is null
       );
    if offenders is not null then
        raise exception 'Definition(s) % have both an Application Area row and a legacy Method row active.', offenders;
    end if;

    raise notice 'R3: applicability Application Area and Production Unit / Cell scope added in %. No rows moved.', current_schema();
end $$;
