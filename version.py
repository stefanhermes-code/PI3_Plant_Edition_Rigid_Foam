"""Single source of truth for the app version shown in the navigation bar.

Convention: bump this on every commit that gets pushed to GitHub.
- Patch (x.y.Z) for fixes, small tweaks, content/data changes.
- Minor (x.Y.0) for new features/pages/schema additions.
- Major (X.0.0) reserved for breaking changes to the data model or workflow.

PI3 Rigid Foam Edition - forked from PI3 Plant Edition (flexible slabstock
foam) at v2.0.1 on 2026-08-05, one day before the flexible app's v2.0.2
fix (removing a mislabeled "Ratio / index" entry from the machine-settings
correlation/optimization pages - see analytics.py). That fix was ported
into this fork by hand on 2026-08-06, so this fork's true content baseline
is flexible-foam v2.0.2, not v2.0.1 - resolving the version-reference
mismatch flagged in the Technical Research and Data Population Plan
(section 2D). Starts its own version history from 0.1.0; see
PI3_Rigid_Foam_Edition_Change_Impact_Assessment.docx for what carries over
unchanged vs. what needs rework for rigid foam manufacturing.

Database: shares the flexible app's Supabase project/database (no separate
project) - decided 2026-08-06. As of v0.2.0, db.py scopes every model to
its own Postgres schema, "rigid_foam" (RIGID_FOAM_SCHEMA), instead of the
flexible app's "public" schema - no name collisions, one project/one bill.
The schema and all 40 tables were created directly against the shared
Supabase project (aazkdsqpytjciiqtvnfj) the same day, ahead of first
deploy, from this exact ORM metadata (see the "create_rigid_foam_schema"
and "create_rigid_foam_tables" migrations in Supabase's migration history -
there is no separate migrations-file convention in this repo, matching
the flexible app's own established practice). Row Level Security is
enabled on all 40 rigid_foam tables (matching the flexible app's
public-schema tables exactly - enabled, no policies on either side; the
app's own connection uses the project's owner-level role, which bypasses
RLS regardless, same as the flexible app). WP0's migration-framework
question (Alembic vs. hand-rolled) is resolved the same way: continue the
project's existing lightweight practice (SQLAlchemy models + ad-hoc SQL
applied directly to Supabase) rather than introducing Alembic, consistent
with how every schema change has been made across this whole project.
See README.md, "Deploying to Streamlit Community Cloud" section.
"""

APP_VERSION = "0.2.1"
