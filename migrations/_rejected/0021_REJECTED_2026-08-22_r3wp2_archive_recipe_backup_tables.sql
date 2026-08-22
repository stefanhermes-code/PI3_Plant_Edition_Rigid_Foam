-- R3-WP2. Move the two recipe backup tables out of the runtime schema.
-- Charlie's "Package C Acceptance and Consolidated R3 Release to JC v3",
-- section 3:
--
--   "Backup tables: Before Production Method dependency work, move
--    _backup_recipe_versions_20260819 and _backup_recipe_components_20260819
--    out of rigid_foam into a non-runtime archive schema. Record table names,
--    row counts and fingerprints before and after. Keep the unconstrained
--    production_method_id in the archived recipe-version backup visible in the
--    dependency evidence."
--
-- WHY THIS COMES FIRST
--
-- R3-WP3 re-measures the Production Method dependency inventory and expects
-- nine foreign-key paths across nine runtime tables. These two tables would
-- distort that count in both directions at once, which is the worst kind of
-- distortion:
--
--   - They sit in rigid_foam, so anything that enumerates "runtime tables"
--     counts them.
--   - They carry NO constraints at all - no primary key, no foreign key, no
--     NOT NULL - so _backup_recipe_versions_20260819.production_method_id is
--     an integer holding a live Production Method id with nothing declaring
--     that relationship. An FK-based dependency count cannot see it.
--
-- So a dependency inventory taken with them in place is too high by two tables
-- and blind to a real reference. Moving them out fixes the first and makes the
-- second explicit rather than hidden.
--
-- WHAT WAS MEASURED BEFORE THE MOVE
--
--   rigid_foam._backup_recipe_versions_20260819
--       1 row    fingerprint 67b920085b8aedf9d6a39329b7084a52
--       production_method_id = 10 (PM-100 Discontinuous Panel & Board
--       Production) on the single row, unconstrained
--   rigid_foam._backup_recipe_components_20260819
--       14 rows  fingerprint b4188655a41548cb3c4132931a202bcf
--
--   Zero constraints on either table.
--   Zero foreign keys anywhere pointing AT them.
--   Zero views or rules depending on them.
--   Zero references in application code - the only mentions outside the
--   database are five lines of changelog prose in version.py.
--   rigid_foam_r0_baseline holds a copy of each at the same row counts, so the
--   R0 baseline snapshot is unaffected by this move and is not touched.
--
-- WHY SET SCHEMA RATHER THAN COPY AND DROP
--
-- ALTER TABLE ... SET SCHEMA relocates the table itself. There is no second
-- copy to diverge, no window in which the data exists twice, and nothing is
-- deleted - which matters for a table whose whole purpose is to be a backup.
-- The fingerprints below are therefore expected to be IDENTICAL after the
-- move; a changed fingerprint would mean something other than a relocation
-- happened.
--
-- The archive schema is not the R0 baseline schema. rigid_foam_r0_baseline is
-- a snapshot with its own meaning and nothing is moved into it.
--
-- Re-runnable: each move is guarded on the table still being in rigid_foam.

create schema if not exists rigid_foam_archive;

comment on schema rigid_foam_archive is
    'Non-runtime archive. Tables here are retained evidence, not application '
    'data - db.py never sets search_path to this schema and no model maps to '
    'it. Populated by migration 0021 (R3-WP2).';

do $$
begin
    if to_regclass('rigid_foam._backup_recipe_versions_20260819') is not null then
        alter table rigid_foam._backup_recipe_versions_20260819
            set schema rigid_foam_archive;
    end if;

    if to_regclass('rigid_foam._backup_recipe_components_20260819') is not null then
        alter table rigid_foam._backup_recipe_components_20260819
            set schema rigid_foam_archive;
    end if;
end $$;


-- ============================================================================
-- EXIT CHECK
-- ============================================================================
do $$
declare n integer; fp text; leftover text;
begin
    -- Arrived, intact. Row count AND fingerprint, because a row count alone
    -- cannot tell a relocation from a re-insert.
    select count(*) into n from rigid_foam_archive._backup_recipe_versions_20260819;
    if n <> 1 then
        raise exception 'Archived recipe-version backup has % rows, expected 1.', n;
    end if;
    select md5(string_agg(t::text, '|' order by t.id)) into fp
      from rigid_foam_archive._backup_recipe_versions_20260819 t;
    if fp <> '67b920085b8aedf9d6a39329b7084a52' then
        raise exception 'Archived recipe-version backup fingerprint is %, expected 67b920085b8aedf9d6a39329b7084a52.', fp;
    end if;

    select count(*) into n from rigid_foam_archive._backup_recipe_components_20260819;
    if n <> 14 then
        raise exception 'Archived recipe-component backup has % rows, expected 14.', n;
    end if;
    select md5(string_agg(t::text, '|' order by t.id)) into fp
      from rigid_foam_archive._backup_recipe_components_20260819 t;
    if fp <> 'b4188655a41548cb3c4132931a202bcf' then
        raise exception 'Archived recipe-component backup fingerprint is %, expected b4188655a41548cb3c4132931a202bcf.', fp;
    end if;

    -- Gone from the runtime schema. Checked by name pattern rather than by the
    -- two names, so a third backup table appearing in rigid_foam later is
    -- caught by this migration's own standard rather than slipping past it.
    select string_agg(tablename, ', ') into leftover
      from pg_tables where schemaname = 'rigid_foam' and tablename like '\_backup\_%';
    if leftover is not null then
        raise exception 'Backup tables still in the runtime schema: %.', leftover;
    end if;

    -- The unconstrained production_method_id is PRESERVED and still visible.
    -- Charlie asked for it to stay visible in the dependency evidence, so the
    -- migration asserts it survived the move rather than assuming it did.
    select count(*) into n
      from information_schema.columns
     where table_schema = 'rigid_foam_archive'
       and table_name = '_backup_recipe_versions_20260819'
       and column_name = 'production_method_id';
    if n <> 1 then
        raise exception 'The archived recipe-version backup has lost its production_method_id column.';
    end if;

    select count(*) into n
      from rigid_foam_archive._backup_recipe_versions_20260819
     where production_method_id = 10;
    if n <> 1 then
        raise exception 'The archived production_method_id no longer reads 10 (% rows match).', n;
    end if;

    -- And it is still UNCONSTRAINED. If a later artifact ever adds a foreign
    -- key here, the dependency count changes meaning and this assertion is
    -- where that gets noticed.
    select count(*) into n
      from pg_constraint con
      join pg_class cl on cl.oid = con.conrelid
      join pg_namespace ns on ns.oid = cl.relnamespace
     where ns.nspname = 'rigid_foam_archive'
       and cl.relname = '_backup_recipe_versions_20260819';
    if n <> 0 then
        raise exception 'The archived recipe-version backup now carries % constraint(s); it had none.', n;
    end if;

    raise notice 'R3-WP2: both recipe backup tables archived out of the runtime schema, intact.';
end $$;
