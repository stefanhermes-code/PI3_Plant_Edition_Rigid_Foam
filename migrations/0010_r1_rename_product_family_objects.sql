-- R1-WP3. Redesign Migration Plan v3, Package B.
--
-- The OBJECT rename. 0009 did the data; this renames the table and the foreign
-- key column so the database says what the application says.
--
-- WHY THIS IS ITS OWN FILE
--
-- 0009 is reversible in principle - values can be re-typed, a deleted row
-- re-created from the text captured in its own comments. A rename is different:
-- it must land together with the ORM and every reader in the application, or the
-- app cannot start. Keeping it separate makes the coupling visible rather than
-- burying it in a data migration.
--
-- WHAT IS DELIBERATELY NOT RENAMED
--
-- The page FILE views/2_Product_Families.py keeps its name, per Charlie's ruling
-- of 21 August. Streamlit derives the page URL from the file name, so renaming it
-- would break every existing bookmark during the compatibility release. All
-- user-visible terminology changes; the route stays until final cleanup, after
-- bookmark impact has been checked.
--
-- The rigid_foam schema, the repository and app_rigid_foam.py are untouched.
--
-- THE COMPATIBILITY ALIAS IS NOT HERE
--
-- The import header accepts both pu_material_family_id and the legacy
-- product_family_id for one release. That is application behaviour, not schema,
-- and lives in the import path with its own regression tests covering both.
--
-- Re-runnable: each rename is guarded on the object still having its old name,
-- so a re-run after a successful apply is a no-op rather than an error.

do $$
begin
    if exists (select 1 from information_schema.tables
                where table_schema = current_schema() and table_name = 'product_families')
       and not exists (select 1 from information_schema.tables
                where table_schema = current_schema() and table_name = 'pu_material_families')
    then
        alter table product_families rename to pu_material_families;
    end if;
end $$;

do $$
begin
    if exists (select 1 from information_schema.columns
                where table_schema = current_schema()
                  and table_name = 'foam_grades' and column_name = 'product_family_id')
       and not exists (select 1 from information_schema.columns
                where table_schema = current_schema()
                  and table_name = 'foam_grades' and column_name = 'pu_material_family_id')
    then
        alter table foam_grades rename column product_family_id to pu_material_family_id;
    end if;
end $$;

-- The constraint 0009 created carries the old table's name in its own name.
-- Rename it too, so nothing in the schema still reads "product family".
do $$
begin
    if exists (select 1 from pg_constraint
                where conname = 'product_families_pkey'
                  and connamespace = current_schema()::regnamespace)
    then
        alter table pu_material_families rename constraint product_families_pkey
            to pu_material_families_pkey;
    end if;
end $$;
