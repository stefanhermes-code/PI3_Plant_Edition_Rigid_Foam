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
decided silently. tests/test_wp3_uat_cases.py runs Charlie's real 10 WP3
Gate 2 UAT test cases (from the WP3 package's "19_UAT_Test_Cases" sheet)
against wp3_conformance.py's logic directly (SimpleNamespace stand-ins,
no live DB needed) - all 10 pass. Two real logic gaps were found and
fixed while making these pass: _specs_match_result() was missing method/
unit checks (so a wrong-method or wrong-unit result would have been
wrongly evaluated instead of excluded), and there was no
validate_result_completeness() check at all (so a result missing
orientation or sample thickness would have been wrongly evaluated
instead of marked invalid). Seeding the actual WP2/WP3 controlled-
vocabulary and UAT record-chain data into the live Supabase rigid_foam
schema, and the application UI/report page, remain the next steps,
tracked separately - this version covers the schema/backend/conformance-
logic build only.

2026-08-06 (later same day): renamed the app's Streamlit entry point from
app.py to app_rigid_foam.py (and the local launcher .bat to
Start_PI3_Rigid_Foam_Edition.bat) - both were identical in name to the
flexible-foam app's own files, which made the two apps hard to tell apart
in Streamlit Community Cloud's app list and in any editor with both repos
open. No functional change. Anyone with an existing Streamlit Community
Cloud deployment of this app needs to update that app's "Main file path"
setting from app.py to app_rigid_foam.py (Settings > General) - Streamlit
Cloud does not pick this up automatically from a git rename.

2026-08-06 (later still): seeded the real WP2/WP3 controlled-vocabulary
and UAT record chain into the live Supabase rigid_foam schema - the one
complete "raw material through report" chain the WP3 package specifies
(00_Read_Me / 02_Record_Chain): 1 chemistry/method/application/
construction, 5 orientations (LOC-060 through LOC-063 plus the flagged
ORI-THERM-THROUGH-THICKNESS provisional row - see below), 2 locations,
1 test condition, 10 raw material categories, 2 units of measure, 5
source registers, 1 property definition/method/UOM (Thermal
conductivity/ISO 8301/W-per-mK), 11 raw materials + lots + lot uses (lot
use masses computed proportionally from the recipe's 249-part formula
basis against the actual 2.376 kg core mass), 1 product family/grade/
recipe version/11 recipe components, 1 grade specification, the full
equipment/tooling hierarchy (production unit, mixhead, tool, cavity,
fill point, vent configuration, calibration record, machine), 1
production run/cycle/shot/output item, 39 process setting definitions +
64 process parameter values (several - cavity volume, core density,
A:B flows, dispense duration/end-time, yield - computed from the
workbook's own stated formulas against its given inputs, not
fabricated), and 1 sample + physical property result (0.023 W/(m.K),
matching UAT-01/UAT-10's measured value). Verified by re-querying the
seeded rows directly: the result's method/condition/orientation/unit
match the spec exactly, thickness and orientation are both present, and
0.023 <= the spec's 0.024 upper limit - reproducing UAT-01's PASS and
UAT-10's UAT_PASS_NO_RELEASE against real database rows, not just the
SimpleNamespace stand-ins in tests/test_wp3_uat_cases.py. Two controlled-
vocabulary findings from this pass, both to raise with Charlie: RMC-120
(already self-flagged by Charlie in 01_Controlled_Delta) and
ORI-THERM-THROUGH-THICKNESS (found by JC - used throughout WP2's own
SPEC-UAT-THERM-001/SCTX-THERM-001 and all of WP3, but never declared in
any WP1/WP2 orientation-vocabulary sheet; added here as a provisional
row pending his confirmation). The application UI/report page remains
the next step.

2026-08-06 (later still): appended "- Rigid Foam" to every user-visible
"PI3 Plant Edition" branding string (login title, sidebar branding,
forgot-password email subject/body) so this deployment is clearly
distinguishable from the flexible-foam app in Streamlit Cloud - same
motivation as the app_rigid_foam.py filename rename above. Also fixed
the login page's caption, which still said "Flexible slabstock foam
expert system" (stale, carried over from the fork). Documented the
existing AUTH_DISABLED dev-bypass secret (auth.py already had this from
the flexible app) in secrets.toml.example - no code change, since the
bypass logic was already there; only needed setting AUTH_DISABLED = true
in this deployment's own Streamlit Cloud secrets, which Stefan does
directly since it's a Cloud dashboard setting, not a repo file.
"""

APP_VERSION = "0.3.3"
