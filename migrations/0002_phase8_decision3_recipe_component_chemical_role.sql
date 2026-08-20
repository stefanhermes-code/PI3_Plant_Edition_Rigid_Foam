-- Phase 8 Decision 3: controlled chemical role on recipe components.
-- Applied live to rigid_foam on 2026-08-19.
--
-- NOTE: ck_rc_chemical_role_provenance below carries the NULL-handling defect
-- that shipped in v0.72.0. It is preserved here as applied, and corrected by
-- 0003. See migrations/README.md - a migration set that cannot reproduce the
-- state a database was actually in cannot be used to diagnose that database.

alter table recipe_components add column if not exists chemical_role varchar(40);
alter table recipe_components add column if not exists chemical_role_source_id integer;
alter table recipe_components add column if not exists chemical_role_source_location varchar(300);

do $$
begin
    if not exists (select 1 from pg_constraint
                   where conname = 'fk_recipe_components_chemical_role_source'
                     and connamespace = current_schema()::regnamespace) then
        alter table recipe_components
            add constraint fk_recipe_components_chemical_role_source
            foreign key (chemical_role_source_id)
            references source_registers(id) on delete restrict;
    end if;

    if not exists (select 1 from pg_constraint
                   where conname = 'ck_rc_chemical_role_vocabulary'
                     and connamespace = current_schema()::regnamespace) then
        alter table recipe_components
            add constraint ck_rc_chemical_role_vocabulary check (
                chemical_role is null
                or chemical_role in ('Isocyanate Component','Polyol Blend Component')
            );
    end if;

    if not exists (select 1 from pg_constraint
                   where conname = 'ck_rc_chemical_role_provenance'
                     and connamespace = current_schema()::regnamespace) then
        alter table recipe_components
            add constraint ck_rc_chemical_role_provenance check (
                (chemical_role is null
                 and chemical_role_source_id is null
                 and chemical_role_source_location is null)
                or (chemical_role is not null
                    and chemical_role_source_id is not null
                    and btrim(chemical_role_source_location) <> '')
            );
    end if;
end $$;
