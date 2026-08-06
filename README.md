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

- `app.py` — Dashboard (Screen 1, entry point)
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
Connectivity, Performance). Treat `app.py`'s own nav-section lists as the
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

This repo has **not been deployed anywhere yet** — no Streamlit Cloud app
of its own. It currently shares nothing at runtime with the flexible app's
deployment; setting up its own deployment is future work, not something
already configured. When that's ready, the mechanics are the same as the
flexible app's, except for the database step below.

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

This is not yet implemented — `db.py`'s SQLAlchemy models and `init_db()`
still create everything in the default `public` schema, same as the
flexible app. Wiring the models to a dedicated schema (and choosing the
migration framework, per WP0) is upcoming work, not done yet.

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
5. Once the schema-separation work lands, the rigid app's connection will
   set its SQLAlchemy models/session to target the `rigid_foam` schema
   (e.g. via `-csearch_path=rigid_foam` on the connection string, or
   per-table `schema=` args) — same URL, same database, different schema.

### 2. This repo

Already created and pushed:
`https://github.com/stefanhermes-code/PI3_Plant_Edition_Rigid_Foam`, branch
`main`. Future changes just need the normal `git add` / `git commit` /
`git push` — no `git init`/`remote add` needed again.

(`.streamlit/secrets.toml.example` is safe to commit. Never commit a real
`secrets.toml`.)

### 3. Deploy on Streamlit Community Cloud

1. Go to share.streamlit.io and create a new app from this repo, branch
   `main`, main file `app.py`.
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
streamlit run app.py
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
headers, and no icons — as if `app.py`'s custom navigation code doesn't
exist.

This is not a code regression (check `app.py` still has `st.navigation(...,
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
