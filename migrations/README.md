# Migrations

Phase 8 P8-OWR-003, per Charlie's Decision 3 Correction Ruling (20 August 2026).

## Why this exists

Until now every schema change on this project was applied by hand against
Supabase. That worked, and the live database is correct — but it meant the
repository could not rebuild the accepted schema. `db.py` starts the app with
`Base.metadata.create_all()`, and `create_all()` **never ALTERs an existing
table**: on any database that predates a change, the new columns and
constraints simply stay absent and the application fails on the page that needs
them.

That is tolerable for a column. It is not tolerable for the Decision 2 and
Decision 3 constraints, because those carry control meaning: they are what make
a partial provenance state or an overlapping machine-stream period impossible.
A restored environment missing them would look identical and enforce nothing.

So: the repository is now the reproducible source for rebuilding the schema.
Manual DDL in Supabase remains the evidence of what was applied to the current
live database.

## The convention

* One file per change, `NNNN_short_name.sql`, applied in filename order.
* **Unqualified object names.** The runner sets `search_path`, so the same file
  applies to `rigid_foam` or to a disposable test schema unchanged. That is what
  makes "apply cleanly to a pre-change schema" testable rather than asserted.
* **Every statement guarded** (`IF NOT EXISTS`, or a `DO $$` block that checks
  `pg_constraint` first). A file must be safe to run twice on its own, quite
  apart from the ledger.
* Applied files are recorded in a `schema_migrations` ledger table, so the
  runner skips them. Belt and braces: the ledger stops re-running, the guards
  make re-running harmless anyway.

## Running

    python migrate.py --schema rigid_foam --dry-run   # show what would apply
    python migrate.py --schema rigid_foam             # apply
    python migrate.py --schema rigid_foam --baseline  # record as already applied

`--baseline` is for the live database, where these changes were already applied
by hand. It writes the ledger without executing the SQL.

## These files are a history, not a tidy story

`0002` creates the chemical-role provenance constraint with the NULL-handling
defect that shipped in v0.72.0, and `0003` fixes it. It would have been neater
to fold the fix into `0002` — and wrong. A migration set that cannot reproduce
the state a database was actually in cannot be used to diagnose that database.
