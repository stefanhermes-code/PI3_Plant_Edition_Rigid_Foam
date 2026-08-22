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
-- THIS IS THE SECOND ATTEMPT
--
-- The first was rejected under Charlie's "R3-WP2 Migration Conformance Ruling
-- to JC v1", 22 August 2026. It qualified the SOURCE schema, which broke the
-- standing rule that migration object names resolve through search_path so the
-- same artifact applies to rigid_foam and to a disposable test schema. It was
-- the only artifact in the repository breaking that rule.
--
-- The rejected artifact, its checksum 7556859e0d27, and the reason it was
-- rejected are preserved in migrations/_rejected/ and are not part of the
-- active set. Charlie: "a migration that fails QA before release may be
-- rejected and fully rolled back under an explicit ruling" - which is what
-- happened here, before commit and before push. An accepted or released
-- migration is still immutable.
--
-- The tell was visible during the first proof and got worked around: because
-- the artifact could only ever address rigid_foam, the disposable-schema run
-- had to use a hand-written equivalent instead of the artifact itself. An
-- artifact that cannot be run against a probe is an artifact that has not been
-- proved. This one can be, and was.
--
-- SOURCE UNQUALIFIED, DESTINATION NAMED
--
-- The source resolves through search_path like every other migration's
-- objects. The destination is written out, because moving an object into
-- rigid_foam_archive necessarily names where it goes.
--
-- WHY THIS COMES BEFORE THE DEPENDENCY WORK
--
-- R3-WP3 re-measures the Production Method dependency inventory and expects
-- nine foreign-key paths across nine runtime tables. These two tables distort
-- that count in both directions at once, which is the worst kind of
-- distortion:
--
--   - they sit in the runtime schema, so anything enumerating runtime tables
--     counts them;
--   - they carry NO constraints at all - no primary key, no foreign key, no
--     NOT NULL - so _backup_recipe_versions_20260819.production_method_id is
--     an integer holding a live Production Method id with nothing declaring
--     that relationship. An FK-based count cannot see it.
--
-- Too high by two tables and blind to a real reference. Moving them out fixes
-- the first and makes the second explicit, which is why Charlie asked for that
-- column to stay visible in the dependency evidence.
--
-- MEASURED BEFORE THE MOVE
--
--   _backup_recipe_versions_20260819     1 row   67b920085b8aedf9d6a39329b7084a52
--       production_method_id = 10 (PM-100), unconstrained
--   _backup_recipe_components_20260819  14 rows  b4188655a41548cb3c4132931a202bcf
--
--   Zero constraints on either table. Zero foreign keys pointing at them. Zero
--   views or rules depending on them. Zero references in application code.
--   rigid_foam_r0_baseline holds a copy of each at the same row counts, is a
--   snapshot with its own meaning, and is not a destination and not touched.
--
-- WHY SET SCHEMA RATHER THAN COPY AND DROP
--
-- ALTER TABLE ... SET SCHEMA relocates the table itself. There is no second
-- copy to diverge, no window in which the data exists twice, and nothing is
-- deleted - which matters most for a table whose whole purpose is to be a
-- backup. The fingerprints are therefore expected to be IDENTICAL after the
-- move; a changed fingerprint would mean something other than a relocation
-- happened.
--
-- Re-runnable: each move is guarded on the table still being in the current
-- schema.

create schema if not exists rigid_foam_archive;

comment on schema rigid_foam_archive is
    'Non-runtime archive. Tables here are retained evidence, not application '
    'data - db.py never sets search_path to this schema and no model maps to '
    'it. Populated by migration 0021 (R3-WP2).';

do $$
begin
    if to_regclass('_backup_recipe_versions_20260819') is not null then
        alter table _backup_recipe_versions_20260819 set schema rigid_foam_archive;
    end if;

    if to_regclass('_backup_recipe_components_20260819') is not null then
        alter table _backup_recipe_components_20260819 set schema rigid_foam_archive;
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

    -- Gone from whatever schema this ran against. current_schema() rather than
    -- a literal, so the same assertion holds on a probe as on the real thing -
    -- which is the whole point of the correction. Checked by name pattern, so
    -- a third backup table appearing later is caught by this same standard.
    select string_agg(tablename, ', ') into leftover
      from pg_tables where schemaname = current_schema() and tablename like '\_backup\_%';
    if leftover is not null then
        raise exception 'Backup tables still in the runtime schema %: %.', current_schema(), leftover;
    end if;

    -- The unconstrained production_method_id is PRESERVED and still visible.
    -- Charlie asked for it to stay visible in the dependency evidence, so this
    -- asserts it survived rather than assuming it did.
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
    -- key here, the dependency count changes meaning and this is where that
    -- gets noticed.
    select count(*) into n
      from pg_constraint con
      join pg_class cl on cl.oid = con.conrelid
      join pg_namespace ns on ns.oid = cl.relnamespace
     where ns.nspname = 'rigid_foam_archive'
       and cl.relname = '_backup_recipe_versions_20260819';
    if n <> 0 then
        raise exception 'The archived recipe-version backup now carries % constraint(s); it had none.', n;
    end if;

    raise notice 'R3-WP2: both recipe backup tables archived out of %, intact.', current_schema();
end $$;
