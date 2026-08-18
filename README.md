# PI3 Rigid Foam Edition

## Status (read this first)

This repository is a **fork of PI3 Plant Edition** (the flexible slabstock
foam application), created 2026-08-05 from the flexible app's v2.0.1 commit,
with the v2.0.2 fix ported in by hand on 2026-08-06 (see `version.py`). It
has its **own version history starting at 0.1.x** and its own GitHub repo
(`stefanhermes-code/PI3_Plant_Edition_Rigid_Foam`) — pushing here never
touches the flexible-foam app or its repo, and vice versa.

**As of v0.1.1, every screen, table, and piece of business logic in this
repo is still the flexible-slabstock-foam version, unchanged.** Nothing
here has been adapted for rigid foam yet. This is deliberate: forking gave
the rigid-foam build a working starting point (auth, multi-tenancy, PI3/AI,
reports, the Industrial Intelligence pages) without risk to the flexible
app's live pilot customer — see the two planning documents below for what
changes and in what order.

Planning documents (in the parent `15. PI3 Plant Edition` folder, not
inside this repo):

- `PI3_Rigid_Foam_Edition_Change_Impact_Assessment.docx` — engineering-side
  scoping: what carries over unchanged vs. what needs new design work.
- `PI3_Rigid_Foam_Edition_Technical_Research_and_Data_Population_Plan.docx`
  — the technical content/data plan (chemistry, process settings, property
  specs, defect taxonomy) that will replace the flexible-foam-specific data
  model described below.
- `PI3_Rigid_Foam_Plan_Feedback_for_Charlie.docx` — engineering feedback on
  that plan (scope-to-timeline sizing, recommended build sequence, the
  baseline-version note resolved in this README/`version.py`).

Everything below this point describes the **flexible-foam content this
fork currently still contains** and the **mechanics of the app itself**
(structure, local dev, deployment, troubleshooting) — the mechanics stay
true regardless of foam type; the content (screens, schema, terminology)
is exactly what's scheduled to change.

## Structure

- `app_rigid_foam.py` — Dashboard (Screen 1, entry point)
- `pages/` — the remaining screens (see below)
- `db.py` — SQLAlchemy models: the flexible-foam operational schema, plus
  the multi-tenant layer (`Company`, `SubscriptionType`, `Role`,
  `RolePagePermission`, `User`) — the multi-tenant layer is expected to
  carry over as-is; the operational schema is what the rigid-foam data
  plan replaces.
- `auth.py` — database-backed login (hashed passwords, per-user validity
  window), falling back to `secrets.toml` only on a fresh/unmigrated
  deployment with no `users` rows yet
- `access_control.py` — shared page-visibility rules: which pages a role
  can see, and which a company's subscription gates
- `helpers.py` — shared UI helpers, advisory disclaimer text
- `analytics.py` — shared data-assembly helpers behind the five Industrial
  Intelligence pages; `PHASE_SETTING_FIELDS`/`PHASE_SETTING_LABELS` here
  is the flexible-foam machine-settings list the rigid plan's "method-aware
  settings" work replaces
- `demo_data.py` — seeds the flexible-foam internal demonstration case (no
  real client data); call `seed_demo_data(session)` directly for a
  throwaway local/dev database

## Screens (still flexible-foam content, unchanged from the fork point)

Covers plant/equipment setup, product family & foam grade profiles,
recipes, production runs (with runtime data entry + CSV import), quality
test results, quality issues, samples & trials (Production Samples,
Customer Trials & Samples, Optimization Trials & Samples), the five
Industrial Intelligence pages (Trend Analysis, Process-Property
Correlation, Recipe Optimization, Root-Cause Assistant, Machine Settings
Optimization), Expert Notes, Reports, and the platform-admin pages
(Companies, Subscription Types, User Roles, User Accounts, PI3
Connectivity, Performance). Treat `app_rigid_foam.py`'s own nav-section lists as the
source of truth for the exact current screen set, not a fixed count here —
this list will be rewritten once rigid-foam screens replace or extend
these.

## Trial data model (current, flexible-foam)

A quality test result or quality issue always belongs to exactly one of
three parents: a Production Run, a Customer Trial, or an Optimization
Trial (`db.SAMPLE_SOURCE_TYPES`). Customer Trials and Optimization Trials
are their own independent lab-trial flows (`pages/11_Customer_Trials.py`,
`pages/12_Optimization_Trials.py`) — they don't hang off a Production Run.
Whether this same shape fits rigid foam's sample/trial patterns is one of
the open questions in the technical research plan.

## Deploying to Streamlit Community Cloud

**This repo IS deployed**, at

    https://pi3planteditionrigidfoam-main.streamlit.app/

on Streamlit Community Cloud, from this repo's `main` branch with
`app_rigid_foam.py` as the main file. It has its own app, separate from the
flexible edition's — the two share a Supabase project but nothing at runtime.

(Until 18 Aug 2026 this section said the repo had not been deployed anywhere
and that doing so was future work. That was true when it was written on
6 August and then went stale, which cost real time when someone went looking
for the app and concluded from this file that it did not exist. If the
deployment changes again, change this section in the same commit.)

The mechanics below are the same as the flexible app's, except for the
database step.

### 1. Database — Supabase Postgres, same project, separate schema

This app reuses the **same Supabase project/database as the flexible
app** (project `aazkdsqpytjciiqtvnfj`) — it does not get its own project.
Rigid-foam tables live in their **own Postgres schema** (e.g. `rigid_foam`),
kept separate from the flexible app's `public` schema, so there's no
table-name collision and a migration for one app can't touch the other
app's tables. Tenants/users are still separate: a company with access to
the flexible app does not automatically get access to the rigid app —
that's governed by the app-level `Company`/`User`/`Role` rows, which this
schema-level separation does not by itself grant or deny.

**Implemented as of v0.2.0.** `db.py` scopes every model to the `rigid_foam`
schema automatically (`RIGID_FOAM_SCHEMA`, set whenever `DATABASE_URL` is
Postgres) — no `search_path` tricks or per-connection setup needed, since
SQLAlchemy schema-qualifies every generated statement once this is set.
The `rigid_foam` schema and all 40 tables already exist in the shared
Supabase project, created directly ahead of first deploy so the fork has
its own real table structure in place now. `init_db()` will just find
them already there on first app run (and create anything new the same
way, going forward, as the schema evolves).

Row Level Security is **enabled** on all 40 `rigid_foam` tables, matching
the flexible app's `public`-schema tables exactly (enabled, no policies
defined on either side). This app talks to Postgres directly over
`psycopg2` using the project's owner-level connection role, which bypasses
RLS regardless — so, same as on the flexible app, this has no effect on
how the app functions. It only matters for Supabase's own client-library
access (anon/authenticated keys via PostgREST), which this app doesn't
use.

### Migration procedure (WP0 — engineering baseline and migration foundation)

**Framework decision:** no Alembic (or any migration-file framework) in
this repo, by design — this continues the same lightweight practice the
flexible app has used for every schema change in its history: the model
lives in `db.py`, and structural changes are applied directly to Supabase
as reviewed SQL, tracked by Supabase's own migration history rather than
a local `migrations/` folder.

**The actual procedure, as practiced (and now proven):**

1. Change the model in `db.py` first — this is always the source of
   truth for the current schema, not the SQL that was run to get there.
2. Before anything touches the real `rigid_foam` schema, run
   `tests/test_schema_migration.py`. It proves the change can be built
   from nothing (upgrade), fully torn down again (rollback), and rebuilt
   identically (repeatable) — against a **disposable** schema on the same
   Postgres server, never against the real `rigid_foam` schema. Run it
   with no `DATABASE_URL` set for a quick SQLite-only check, or with the
   real Supabase connection string set for a check against the actual
   server/Postgres version this app deploys to.
3. Apply the reviewed SQL to the real `rigid_foam` schema (via the
   Supabase SQL editor, or the same MCP-based `apply_migration` calls used
   throughout this project's history) — additive changes only get
   auto-created by `init_db()`'s `create_all()`; anything that alters or
   drops an existing column is always done by hand, on purpose,
   `create_all()` never does either.
4. Bump `version.py`, commit, push.

**Environments, honestly stated:** there is currently **one** database
environment — the shared Supabase project's `rigid_foam` schema. The
deployment above is the only one, so there is no physically separate "UAT"
and "production" database today; both terms point at the same schema, and
the deployed app reads and writes it directly. When a real UAT deployment exists, step 2's
disposable-test-schema technique is exactly what should run as a pre-UAT
gate; until then, it already proves every change against the real
project/server before anything touches live data.

**Gate 0 evidence (per the Converged Joint Implementation Plan, §7.1 and
§9):** v2.0.2 correction ported, source commit recorded (v0.1.1/v0.1.2),
migration framework decided and operational (v0.2.0), upgrade/rollback
tests built and passing both locally (SQLite) and against the real
Supabase Postgres 17 server via a disposable schema (v0.2.2), migration
procedure documented above. Gate 0 closed.

1. Reuse the flexible app's existing Supabase project — do **not** create
   a second one.
2. Go to **Project Settings > Database > Connection string > URI**, and copy
   the **Session pooler** connection string (works better than the direct
   connection from serverless/app-hosting environments). This is the same
   connection string the flexible app uses.
3. It will look like:
   `postgresql://postgres.xxxxx:[PASSWORD]@aws-0-xxxx.pooler.supabase.com:5432/postgres`
4. Rewrite the scheme to use the psycopg2 driver explicitly:
   `postgresql+psycopg2://postgres.xxxxx:[PASSWORD]@aws-0-xxxx.pooler.supabase.com:5432/postgres`

### 2. This repo

Already created and pushed:
`https://github.com/stefanhermes-code/PI3_Plant_Edition_Rigid_Foam`, branch
`main`. Future changes just need the normal `git add` / `git commit` /
`git push` — no `git init`/`remote add` needed again.

(`.streamlit/secrets.toml.example` is safe to commit. Never commit a real
`secrets.toml`.)

### 3. Deploy on Streamlit Community Cloud

1. Go to share.streamlit.io and create a new app from this repo, branch
   `main`, main file `app_rigid_foam.py`.
2. In the app's **Settings > Secrets**, paste the contents of
   `.streamlit/secrets.toml.example`, filled in with your real (new,
   rigid-foam-specific) Supabase connection string and real user accounts
   (see below).
3. Deploy. The app will create all tables automatically on first load
   (`init_db()` runs on every page).

### 4. Users, companies, and subscriptions

User accounts are database-backed (hashed passwords, optional validity
window), not config-file entries. On a fresh deployment with no rows yet in
the `users` table, the `[users.<name>]` blocks in Secrets still work as a
bootstrap fallback so you can log in once and create real accounts.

To set up a new customer company: log in as the platform owner (HTC) and
use **Companies** to add the tenant, **Subscription Types** to assign it a
commercial tier (user/plant limits, feature flags), and **User Accounts**
to create its first admin user. That company's own admin can then manage
their own users and any custom roles (**User Roles**) without seeing other
companies' data.

### 5. Load demo data (optional, local/dev only)

To seed the flexible-foam demonstration case into a local/dev database
(useful only for exercising the current, unmodified screens — not
representative of rigid foam), run:

```
python -c "from db import get_session, init_db; from demo_data import seed_demo_data; init_db(); print(seed_demo_data(get_session()))"
```

## Local development

```
pip install -r requirements.txt
streamlit run app_rigid_foam.py
```

Without a `DATABASE_URL` secret or environment variable, the app falls back
to a local SQLite file (`pi3_local.db`) for convenience — do not rely on
this for a deployed app.

## Troubleshooting

The mechanics below are inherited from the flexible-foam app's own
deployment history and apply identically here, since the tech stack
(`requirements.txt`) was copied over unchanged. None of this is rigid-foam
specific.

### Sidebar reverts to a plain page list

Symptom: the sidebar shows a flat, alphabetical/numeric list of page names
straight from the filenames, with no logo, no version number, no section
headers, and no icons — as if `app_rigid_foam.py`'s custom navigation code doesn't
exist.

This is not a code regression (check `app_rigid_foam.py` still has `st.navigation(...,
position="hidden")` and the custom `with st.sidebar:` block first if in
doubt) — it's Streamlit Community Cloud serving a stale cached build. Fix:
open the app on share.streamlit.io, click the **⋮** menu (top right) →
**Clear cache**. A plain reboot does not always clear this.

### ImportError "cannot import name 'X' from 'helpers'" (or any module) after a push

This is a different failure mode from the sidebar issue above: it's not a
stale build, it's a stale **Python process**. Streamlit Community Cloud's
"pull code changes from GitHub" step doesn't always restart the underlying
Python process. **Clear cache does not fix this** (it only clears
`@st.cache_data`/`@st.cache_resource`, not Python's module cache). The fix
is a full **Reboot app**. If no distinct "Reboot app" option is visible,
delete and redeploy the app from the same repo/branch as a fallback.

Check the deploy log (Manage app → logs) for the real traceback first —
Streamlit's on-screen error message is redacted, but the log shows the
exact `ImportError`.

### Sidebar reverts to a plain page list, and Clear cache / Reboot app don't fix it

Check the deploy log's dependency install section for the actual
`streamlit`/`pandas`/`pyarrow` versions installed and the Python version
the container is using. `requirements.txt` pins these exactly (see the
comment block at the top of that file) precisely because an unbound
`>=`-only dependency once silently broke `st.navigation()`'s custom-sidebar
routing on the flexible app — Streamlit Community Cloud forces the Python
version (no `runtime.txt` support), and a too-old Streamlit on a too-new
Python fails this way with no traceback. Don't "roll back" a Streamlit pin
as a first instinct here; check what Python version Cloud is forcing first.

### App shows "Oops" on every load, deploy log full of "GZipResponder.__init__() missing 1 required keyword-only argument: 'thread_minimum_size'"

Different failure mode from the two sidebar cases above — this one crashes
every single request. Cause: an upstream incompatibility between
`streamlit==1.60.0` and `starlette` releases newer than 1.3.1 (see the
comment above the `starlette==1.3.1` pin in `requirements.txt` for the full
root-cause chain). Already pinned correctly in this repo; re-verify the pin
before ever bumping `streamlit` past 1.60.0.

## What this fork deliberately does not do (yet)

No rigid-foam-specific schema, screens, terminology, property master data,
process settings, or defect taxonomy — that's the entire scope of the
planned build (see the planning documents at the top of this file). Beyond
that, the same limits as the flexible app still apply: no ERP integration,
no live machine connection, no autonomous formulation optimization, no
complex billing engine, no customer complaint platform. PI3 never issues
formulation instructions — it only surfaces historical records and
hypotheses for human review.
