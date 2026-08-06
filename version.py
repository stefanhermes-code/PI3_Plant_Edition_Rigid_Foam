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

WP0 (Converged Joint Implementation Plan, section 7.1) closed 2026-08-06:
tests/test_schema_migration.py proves upgrade, rollback, and repeatable
rebuild of this exact schema, run both locally (SQLite) and against the
real Supabase Postgres 17 server via a disposable "rigid_foam_migration_
test" schema (created and dropped within the same run - the real
rigid_foam schema is never touched by the test). Migration procedure
(no separate migrations-file framework; db.py is the source of truth,
changes are proven via the test script, then applied as reviewed SQL
against Supabase) documented in README.md. Gate 0 evidence satisfied.

WP3 (Converged Joint Implementation Plan, section 7.3 - the Thermal
Conductivity Vertical Slice) engineering build started 2026-08-06 by JC,
after confirming Charlie's WP3 content deliverable was complete but the
schema/app engineering side had not yet begun. Added 24 new tables plus
extension columns on 11 existing tables (Machine, FoamGrade, RecipeVersion,
RecipeComponent, RawMaterial, RawMaterialLotUse, PhysicalPropertyDefinition,
PhysicalPropertyMethod, PhysicalPropertyUOM, Sample, PhysicalPropertyResult) -
see db.py's "WP3 - Thermal Conductivity Vertical Slice" section for the
controlled-vocabulary lookups (Chemistry, ProductionMethod, Application,
ProductConstruction, Orientation, Location, TestCondition,
RawMaterialCategory, UnitOfMeasure, SourceRegister), the equipment/tooling
hierarchy (ProductionUnit, Mixhead, Tool, Cavity, FillPoint,
VentConfiguration, CalibrationRecord), GradeSpecification (generalizes
FoamGradeTargetProperty with an explicit operator/limits/test-context
model), the cycle/shot/output-item structure (ProductionCycle,
ProductionShot, OutputItem), and the method-aware process-settings EAV pair
(ProcessSettingDefinition, ProcessParameterValue). Proven via
tests/test_schema_migration.py (64 tables, SQLite) and, since the sandbox
has no DATABASE_URL, via an equivalent disposable-schema pass run directly
against the real Supabase Postgres server through the Supabase MCP - same
WP0 discipline. Applied to the real rigid_foam schema 2026-08-06 (64 tables
total); RLS enabled on all 24 new tables, matching the existing 40 tables'
posture (enabled, no policies - the app's own Postgres role bypasses RLS
regardless). wp3_conformance.py adds live-computed conformance/report/
analytics functions (Gate 2 items G2-06/G2-11) - a deliberate deviation
from Charlie's literal build pack, which specifies stored
ConformanceEvaluation/ReportRecord/AnalyticsRecord tables; this app's own
"pass/fail computed live, never stored" lesson (see the flexible app's
history) applies here too, and was flagged to Charlie/Stefan rather than
decided silently. Application-layer work (import of Charlie's WP2/WP3
controlled-vocabulary data, UI pages, and the 10 UAT test cases) is the
next step, tracked separately - this version covers the schema/backend
build only.
"""

APP_VERSION = "0.3.0"
