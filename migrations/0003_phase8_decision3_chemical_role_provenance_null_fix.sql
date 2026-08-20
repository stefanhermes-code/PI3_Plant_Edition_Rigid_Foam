-- Correction to 0002. Applied live to rigid_foam on 2026-08-19.
--
-- 0002's provenance branch ended:
--     ... AND btrim(chemical_role_source_location) <> ''
-- btrim(NULL) is NULL, "FALSE OR NULL" is NULL, and a CHECK constraint PASSES
-- on NULL. So a chemical role with a source and a NULL source location was
-- ACCEPTED - verbatim the partial-provenance state the Decision 3 ruling
-- forbids - and a valid row could have its location nulled out by an UPDATE.
-- Confirmed against live Postgres before this fix.
--
-- The fix states the requirement rather than inferring it. Never rely on a
-- function of a possibly-NULL value being false; say IS NOT NULL.

alter table recipe_components drop constraint if exists ck_rc_chemical_role_provenance;

alter table recipe_components
    add constraint ck_rc_chemical_role_provenance check (
        (chemical_role is null
         and chemical_role_source_id is null
         and chemical_role_source_location is null)
        or (chemical_role is not null
            and chemical_role_source_id is not null
            and chemical_role_source_location is not null
            and btrim(chemical_role_source_location) <> '')
    );
