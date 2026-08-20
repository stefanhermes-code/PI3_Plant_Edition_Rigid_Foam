-- Phase 8 Decision 2: controlled machine-stream configuration.
-- Applied live to rigid_foam on 2026-08-19 as
-- "phase8_decision2_machine_stream_configuration". Transcribed here verbatim
-- in behaviour, with object names unqualified so the runner's search_path
-- decides the schema.
--
-- btree_gist is a cluster-level extension and is created in the public schema
-- by Supabase; the GiST exclusion constraint below is ruling R2's precondition
-- and will fail without it.

create extension if not exists btree_gist;

create table if not exists machine_stream_configurations (
    id serial primary key,
    controlled_id varchar(50) unique,
    machine_id integer not null references machines(id),
    revision integer not null,
    effective_from timestamp not null,
    effective_to timestamp,
    status varchar(20) not null default 'Draft',
    source_reference text,
    approved_by varchar(200),
    approved_at timestamp,
    notes text,
    created_at timestamp default (now() at time zone 'utc'),
    constraint uq_msc_machine_revision unique (machine_id, revision),
    constraint ck_msc_status check (status in ('Draft','Active','Superseded')),
    constraint ck_msc_period check (effective_to is null or effective_to > effective_from)
);

create table if not exists machine_stream_assignments (
    id serial primary key,
    machine_stream_configuration_id integer not null
        references machine_stream_configurations(id) on delete cascade,
    stream_label varchar(1) not null,
    chemical_role varchar(40) not null,
    notes text,
    constraint ck_msa_stream_label check (stream_label in ('A','B')),
    constraint ck_msa_chemical_role
        check (chemical_role in ('Isocyanate Component','Polyol Blend Component')),
    constraint uq_msa_config_stream unique (machine_stream_configuration_id, stream_label),
    constraint uq_msa_config_role unique (machine_stream_configuration_id, chemical_role)
);

alter table production_runs
    add column if not exists machine_stream_configuration_id integer;

do $$
begin
    if not exists (select 1 from pg_constraint
                   where conname = 'fk_production_runs_machine_stream_configuration'
                     and connamespace = current_schema()::regnamespace) then
        alter table production_runs
            add constraint fk_production_runs_machine_stream_configuration
            foreign key (machine_stream_configuration_id)
            references machine_stream_configurations(id) on delete restrict;
    end if;

    -- No two Active/Superseded configurations may claim overlapping time on
    -- one machine. Half-open [from, to) so an end instant and the next start
    -- instant are a clean handover, not a conflict. Drafts are excluded: they
    -- may overlap while being prepared.
    if not exists (select 1 from pg_constraint
                   where conname = 'ex_msc_no_overlap'
                     and connamespace = current_schema()::regnamespace) then
        alter table machine_stream_configurations
            add constraint ex_msc_no_overlap exclude using gist (
                machine_id with =,
                tsrange(effective_from, effective_to, '[)') with &&
            ) where (status in ('Active','Superseded'));
    end if;
end $$;

create unique index if not exists uq_msc_one_open_active
    on machine_stream_configurations (machine_id)
    where status = 'Active' and effective_to is null;

alter table machine_stream_configurations enable row level security;
alter table machine_stream_assignments enable row level security;
