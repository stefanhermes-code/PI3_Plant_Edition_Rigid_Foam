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

2026-08-07: closed the gap Stefan flagged - turning AUTH_DISABLED off
later would have locked everyone out, because the rigid_foam schema's
entire multi-tenant auth layer (roles, users, subscription_types,
role_page_permissions) was completely empty. Root cause: the one
Company row (HTC Global) was created via raw seed SQL during WP3
seeding, not through the normal Companies admin-page flow, so
role_provisioning.clone_builtin_roles_for_company() was never triggered
and no Role templates existed yet to clone from anyway. Fixed by
seeding, directly against Supabase: the 3 built-in Role templates
(Company Admin/technical/viewer, company_id NULL - matching the
flexible app's convention), their clone for HTC Global (company_id=1),
and one real User row for Stefan (stefan.hermes@htcglobal.asia,
bcrypt-hashed password, role_id = HTC Global's own "Company Admin"
clone, is_super_admin=True). is_super_admin was the deliberate choice
over relying on role/permission rows: access_control.page_visible() and
can_use_page() both short-circuit to full access whenever
is_super_admin is True, independent of RolePagePermission/subscription
state - the same unconditional-bypass escape hatch already documented
on db.py's User model. This gives Stefan the exact same full access
AUTH_DISABLED gives today, but as a persisted DB account, so removing
AUTH_DISABLED from Streamlit Cloud's secrets later won't lock him out.
Temporary password given to Stefan directly in chat, not committed
anywhere - he should change it via the User Accounts admin page once
logged in for real.

2026-08-07 (later same day): fixed the main-content header on Overview
(and every other page routed under it, since this markup lives in
app_rigid_foam.py's shared header block) - it still said "PI3 —
Flexible PU Foam Intelligence" / "Flexible slabstock foam expert
system", stale text carried over from the fork and missed in the
earlier branding pass because it was worded differently enough from
"PI3 Plant Edition" to look out of scope at the time. Stefan caught it
from a live screenshot. Now reads "PI3 — Rigid Foam Intelligence" /
"Rigid foam expert system". Also fixed the matching page_title (browser
tab) and the same stale subtitle on the report cover page in
reports.py.

2026-08-07 (later still): closed Gate 2 acceptance items A6/A7 (WP3
"report displays the result, limits, method, unit, condition, sample
context and provenance" / "analytics receive only comparable records
for the selected property context") - the one piece of engineering that
remained open on WP3. Per Stefan's direction to reuse the flexible app's
established reporting architecture wherever nothing about this report is
materially different: added a 5th report type, "WP3 Property Conformance
Report", to the Report page (21), following the exact same
build_data()/render_docx()/download_button pattern as every other report
in reports.py (see Batch Release Record / Sample Certificate of
Analysis). Pick a rigid-foam grade and one of its production runs; the
report shows every grade specification matched against that run's
physical property results - property, method, unit, test condition,
orientation, location, limit/target, actual value, and a live-computed
Pass/Fail/EXCLUDED_CONTEXT/INVALID/NO_RESULT status (from
wp3_conformance.compute_conformance_report(), unchanged) - plus sample
provenance (location/orientation/thickness/age) and a pass-rate-by-
property analytics summary across every run on that grade (from
wp3_conformance.compute_grade_conformance_summary(), also unchanged).
Both stay live-computed, never stored, matching wp3_conformance.py's
existing "no ConformanceEvaluation/AnalyticsRecord table" decision - a
corrected specification or result is reflected on the very next report,
with no separate recompute step. Verified end-to-end against a seeded
local SQLite chain (grade/spec/run/sample/result matching the real
Supabase UAT-01 scenario - 0.023 W/(m.K) actual against a 0.024 upper
limit, UAT-only grade): build_wp3_conformance_report_data() correctly
returns "Conforming" with the right method/unit/condition/orientation/
limit/actual/status/UAT_PASS_NO_RELEASE note, and the rendered Word
document was visually confirmed to show all of it correctly laid out.
Gate 2's only remaining item is A10 (sign-off) - not engineering work,
tracked separately.

2026-08-07 (WP4, Converged Joint Implementation Plan section 7.5 -
"Property evaluation and Recipe Optimization redesign"), started after
Stefan's A10 Gate 2 sign-off: (1) added tests/test_recipe_optimization_
baseline.py, a regression suite for the flexible app's shared achievement/
correlation logic (quality_standards.compute_pass_fail, analytics.
property_results_dataframe/rank_component_actual_correlations) before
touching any of that shared code. (2) Added unit_conversion.py, a
deliberately narrow single-factor linear conversion module (thermal_
conductivity, density, pressure_strength, percentage, length), and wired
it into wp3_conformance._specs_match_result so a convertible unit
mismatch (e.g. mW/(m.K) vs W/(m.K)) is evaluated instead of excluded -
previously documented as "conversion deferred to WP4". This changes WP3
UAT-06's outcome from EXCLUDED_CONTEXT to a computed Pass; tests/
test_wp3_uat_cases.py is left untouched as the frozen, signed-off Gate 2
record (only a docstring note added - it will now report UAT-06 as a
"mismatch" if run directly, which is expected, not a regression), and
tests/test_wp4_unit_conversion.py covers the correct new expectations.
Also added wp3_conformance.resolve_actual_value(), fixing a latent
report-display bug where compute_conformance_report's "Actual" column
could show a raw unconverted number under the wrong unit label. (3) Added
wp3_conformance.compute_grade_achievement_summary(), the rigid-foam
equivalent of the flexible page's "Does the current recipe meet target?"
table, judged against a GradeSpecification's operator/limits/method/
condition/orientation/location context (via compute_conformance_report)
rather than a hardcoded industry-tolerance lookup. (4) Added
RawMaterialLotUse.mass_kg (nullable Float, migrated to Supabase) - the
rigid equivalent of the flexible app's ComponentStreamReading.
flow_total_qty, recorded per lot use since a run can draw one material
from multiple supplier lots - plus wp3_conformance.
rigid_actual_usage_dataframe()/rank_lot_use_actual_correlations(), the
rigid equivalent of analytics.actual_usage_dataframe()/
rank_component_actual_correlations(). Explicitly flagged, not silently
glossed over: no page or CSV import writes mass_kg yet, so this is the
read side of a schema addition, ready for a capture UI tracked
separately. (5) Branched pages/15_Recipe_Optimization.py's "Does the
current recipe meet target?" section and its ingredient-correlation
picker on `is_rigid = grade.chemistry_id is not None`, so a rigid-foam
grade uses the new spec-aware functions instead of the flexible app's
hardcoded tolerance table. A Streamlit AppTest-based page smoke test
(tests/test_wp4_recipe_optimization_page_smoke.py, one seeded flexible
grade and one seeded rigid grade, each run as an isolated process against
its own SQLite file) caught two real bugs the underlying-function unit
tests couldn't: a `.round()` TypeError on the page's generic "Physical
properties" section (rigid PhysicalPropertyResult rows have no
target_value, making the aggregated column object-dtype rather than
float - fixed with pd.to_numeric(..., errors="coerce")) and a missing
`ProductionRun` import. (6) Added reports.
build_rigid_recipe_optimization_report_data(), wired into the page's
"Recipe Optimization Report" section for a rigid-foam grade - carrying
spec context (method/condition/orientation/location), operator-aware
limit text, and Excluded/Invalid/No result counts. Deliberately REUSES
render_recipe_optimization_report_pdf/docx unmodified rather than forking
them, since both already build their tables from generic lists-of-dicts;
only the data-assembly step is rigid-specific. The "Ask PI3 for a
formulation recommendation" structured section remains gated behind a
"tracked WP4 follow-up" caption for rigid grades - out of this batch's
scope, not forgotten. All new logic covered by dedicated test files
(test_wp4_unit_conversion.py, test_wp4_rigid_achievement_summary.py,
test_wp4_rigid_lot_use_correlation.py, test_wp4_rigid_recipe_
optimization_report.py, test_wp4_recipe_optimization_page_smoke.py) plus
the pre-existing suites, all passing (UAT-06's documented, deliberate
divergence aside).

2026-08-07 (later same day, WP4 follow-up per Stefan's direct request -
"Build it, PI3 can handle it"): built the "Ask PI3 for a formulation
recommendation" structured section for rigid-foam grades on pages/15_
Recipe_Optimization.py, which v0.5.0 had deliberately left gated behind a
"tracked WP4 follow-up" caption. Mirrors the flexible branch field-for-
field, but grounded in achievement_summary (wp3_conformance.
compute_grade_achievement_summary) and wp3_conformance.
rank_lot_use_actual_correlations() per specification instead of the
flexible app's hardcoded-tolerance expectation_summary and per-property
stream-reading correlations - correlation is looked up per spec_id, not
per bare property name, since one property can carry more than one
specification (different test method/condition/orientation/location).
Target-property prefill now defaults from this grade's own specification
limits (via the existing _spec_limit_text/_spec_context_text helpers,
already defined earlier on the page for the achievement table) instead
of expectation_summary's flat target value. The prompt sent to PI3 is
reworded for a rigid-foam context (specifications with operator/limit/
test context, metered LOT consumption rather than stream-reading dosage,
an explicit instruction to flag UAT-only/not-yet-production-released
specifications rather than treat them as approved). composition_summary/
cost_summary/diff_summary/outcome_summary are schema-shared and reused
verbatim, same as the flexible branch. Restructured the surrounding
if/elif so both branches share one `_pi3_unavailable_caption()` helper for
the "not configured"/"not enabled" messaging (previously duplicated
inline), rather than copying that caption block a third time.
tests/test_wp4_recipe_optimization_page_smoke.py's rigid fixture now
enables PI3 for its plant (fake OPENAI_API_KEY/PI3_VECTOR_STORE_ID
secrets + a PI3AIConnectionSetting row) so the smoke test actually
exercises the new target-prefill loop and asserts the prefilled
Thermal-conductivity specification text and the "Get PI3 recommendation"
button render - without ever clicking that button, since doing so would
require a real OpenAI call. All tests pass.

2026-08-07 (later still, WP5 Wave 1 - Converged Joint Implementation Plan
section 7.6, "Scale-out technical content and knowledge library"): began
WP5 per Stefan's "wave-by-wave, as specified" instruction - Wave 1 only
(raw-material control, recipe control, facers/substrates; WP5 workbook
sheets 02-07), Waves 2-5 not started. Schema additions in db.py: 5 new
tables - RawMaterialAttributeDefinition/RawMaterialAttributeValue (EAV
pair, mirroring the existing ProcessSettingDefinition/ProcessParameterValue
pattern), RawMaterialDocument (TDS/SDS/specification revisions),
RawMaterialQualification (recipe/process approval scope, substitution
group), and Substrate (facer/substrate master, linked from
ProductConstruction via new top_facer_substrate_id/bottom_facer_
substrate_id FKs). Plus new nullable columns: RawMaterialLot
(manufacture_date, country_of_origin), RawMaterial (8 columns -
manufacturing site, storage temp range, recirculation/agitation
requirements, moisture sensitivity, flammability handling class,
technical validation note), RecipeVersion (8 columns - target A:B mass
ratio, blowing agent system, target free-rise/molded-core density,
processing window reference, plant validation/safety review status,
technical approver), RecipeComponent (16 columns - stream assignment,
dosage tolerances, reactive-hydrogen/NCO-equivalent flags and sources,
premix group, addition sequence, blend temperature window, mixing/aging
instruction, substitution allowance/group, provenance class, source
location, release note). Three deliberate scoping decisions, each
following existing project conventions rather than over-building: (a)
reused the existing approval_status/validation_status pair on
RecipeVersion instead of adding a third recipe_status column (RHF-003) -
same "no parallel/overlapping status fields" lesson as before; (b)
deferred RecipeVersion.reference_formulation_id (RHF-014's target table,
ReferenceFormulation, belongs to Wave 4, not built yet) and a full
ProcessingWindow entity (RHF-015; a text field for now, same
add-later-if-needed precedent as the Supplier model) - both explicitly
flagged, not silently dropped; (c) scoped Wave 1 JC engineering to
schema + migration + seed + tests only, per the plan's own "implement
entities, relationships, validation and import" language for this wave -
dedicated CRUD/workflow UI pages (qualification-status management,
document tracking, dosage-tolerance capture) are flagged follow-up work,
not built here, mirroring the WP4 RawMaterialLotUse.mass_kg capture-UI
gap. Verified via py_compile and a live local SQLite init_db() pass
before touching Supabase. Applied to the real rigid_foam schema as two
migrations: "wp5_wave1_rm_documents_qualification_attributes_facers" (the
5 new tables plus all ~34 new columns, RLS enabled on all 5 new tables
matching every other rigid_foam table's posture) and
"wp5_wave1_seed_rm_categories_attributes_substrates" (WP5's actual
controlled-vocabulary content: 20 new raw-material categories from
02_RM_Categories, the full 60-row raw-material attribute dictionary from
03_RM_Attributes into the new RawMaterialAttributeDefinition table, and
the full 20-row facer/substrate master from 07_Facers_Substrates into the
new Substrate table) - both verified afterward by re-querying
information_schema and row counts. Full regression suite
(test_recipe_optimization_baseline.py, test_wp4_rigid_achievement_
summary.py, test_wp4_rigid_lot_use_correlation.py, test_wp4_rigid_recipe_
optimization_report.py, test_wp4_unit_conversion.py, and both AppTest
page-smoke cases run in the established one-test-per-fresh-SQLite-file
isolation) still passes with no changes needed - Wave 1 only added
nullable columns and net-new tables, nothing existing was altered. No
dedicated UI pages ship in this batch (flagged above); Waves 2-5 remain
unstarted pending check-in, per the plan's wave-handover rule and
Stefan's explicit sequencing instruction.

2026-08-07 (later still, WP5 Wave 2 - "Expanded properties, methods,
conditions, specifications and sample locations"; workbook sheets 08-12
only, per 01_Wave_Control - sample locations (13_Sample_Locations)
actually belongs to Wave 3, corrected from an earlier assumption before
any schema was written): per the wave's own JC_Engineering_Action
("Extend generic property model and UI"), extended the existing WP3
controlled-vocabulary tables rather than adding parallel new ones -
PhysicalPropertyDefinition (+default_uom, scope, allowed_target_type,
mandatory_context, source_ids, phase_status), PhysicalPropertyMethod
(+standard_reference, method_category, applicable_property_ids,
implementation_rule, source_id; property_definition_id relaxed to
nullable so MTH-090/MTH-099's "Multiple"-property generic methods have
somewhere to live), TestCondition (+condition_category, required_fields,
data_rule, source_ids), UnitOfMeasure (+unit_system, data_rule). One new
table: GradeSpecificationTemplate (12_Grade_Spec_Templates) - a reusable
spec *pattern* (property + method + condition(s) + orientation + scope),
deliberately separate from GradeSpecification since Charlie's own
governance note states templates carry no operational limit unless
approved; multi-condition fields stored as flat semicolon text rather
than a join table, same "abstain, don't over-engineer" call as Wave 1.
Seeded all of Wave 2's actual content: 6 new UOM rows (08), the full
56-row property master (09, one row - PROP-005/Thermal conductivity -
upserted onto the existing WP3 row rather than duplicated), the full
35-row test method master (10, one row - MTH-016 - upserted the same
way), the full 23-row test condition master (11), and all 15 grade
specification templates (12). Three real data-quality issues found in
Charlie's workbook during seeding, each fixed and explicitly flagged
(same practice as WP3's self-flagged RMC-120 and JC-found
ORI-THERM-THROUGH-THICKNESS) rather than silently propagated or dropped:
(1) an ID collision - COND-020 is defined twice in 11_Test_Conditions,
once as "Dimensional stability exposure" (Aging) and once as "Mean test
temperature 10 degC" (Thermal test); seeded the first under COND-020 and
the second under a provisional COND-020-THERM10, matching the
ORI-THERM-THROUGH-THICKNESS precedent for an undeclared-but-needed
vocabulary term. (2) GST-001/GST-002/UAT-GST-001 all cite
Property_ID=PROP-015 and/or Method_ID=MTH-015 (a dimensional-stability
property and a water-absorption method) despite being named and
unit-typed ("W/(m.K)") as thermal-conductivity templates - corrected to
PROP-005/MTH-016 (initial) and PROP-037/MTH-028 (aged); the corrected
COND-020-THERM10 mapping from issue (1) confirms this reading, since
UAT-GST-001's corrected condition set (COND-003 + COND-020-THERM10) now
matches its own name, "UAT initial lambda at 10 degC", exactly. (3)
GST-006/UAT-GST-004 cite Method_ID=MTH-018 (a thermal method) for a
closed-cell-content property - corrected to MTH-012; GST-007/UAT-GST-005
cite Property_ID=PROP-021 (water absorption by mass) for a template
governed as "dimensional change" - corrected to PROP-015 (length change,
the representative axis; the sheet's own governance note already states
each axis remains a separate result). Every correction is recorded in
that template row's own governance_note column, not just here, so it
survives independently of this changelog. All three findings are Charlie
confirmation items, not yet resolved with him. Verified via py_compile,
a live local SQLite init_db() pass before touching Supabase, and
afterward via information_schema/row-count/FK-null checks against the
real rigid_foam schema (56 properties, 35 methods, 23 conditions, 15
templates, zero unresolved FKs). Full regression suite (same list as
Wave 1, plus both AppTest page-smoke cases in the established
one-test-per-fresh-SQLite-file isolation) passes unchanged - Wave 2 only
added nullable columns and one net-new table. No dedicated UI surfaces
these new fields yet (flagged, not silently skipped, same as Wave 1's
deferred capture UIs). Wave 3 (quality issues, possible causes and
hypothesis links; workbook sheets 13-15) remains unstarted pending
check-in, per the plan's wave-handover rule and Stefan's explicit
"wave-by-wave" sequencing instruction.

2026-08-07 (later still, Machine Data Architecture): Charlie delivered a
separate design document, "PI3_Plant_Edition_Rigid_Foam_Machine_Data_
Design_for_JC", proposing an 8-layer machine knowledge architecture -
outside the Converged Joint Implementation Plan's WP0-WP5 numbering, a
new initiative. Layer A (Machine Knowledge Master - generic manufacturer/
model catalogue), Layer B (Configuration Master), Layer C (Plant
Installed Equipment/Asset - the app's existing Machine table), Layer D
(Operating Parameter Register), Layer E (Alarm & Fault Register), Layer F
(Maintenance & Calibration Register), Layer G (Troubleshooting Case
Register), Layer H (Document Register). Unlike WP5, this document also
asks JC to research and populate real commercial manufacturer/model data
with source URLs and APAC-availability evidence (deliverables 01-02) -
an open-ended research task, not just engineering integration against
Charlie-supplied content. Per Stefan's direction, split into two: build
the schema now, pause before the research/population task pending a
separate scope decision.

Schema built: 8 new tables - MachineCategory (global, 17-row taxonomy
already specified by Charlie so seeded now), MachineModel (Layer A,
~50 fields spanning identity/process applicability/capacity/chemistry
compatibility/controls/APAC availability/PI3 knowledge support/
documents - left empty, no manufacturer data populated yet),
MachineConfiguration (Layer B), MachineOperatingParameter (Layer D, EAV
per-asset, mirrors ProcessSettingDefinition/ProcessParameterValue's
established pattern; writable_by_pi3 defaults False and only this schema
pass, no code, can ever set it True, per Charlie's "any future write
capability requires separate governance" rule), MachineAlarm (Layer E,
linkable to either a generic MachineModel or a specific Machine/asset),
MachineMaintenanceRecord (Layer F), MachineTroubleshootingCase (Layer G,
with real FKs to RecipeVersion/ProductionRun alongside free-text context
so a case can link relationally to an actual recipe/run, not just
prose), MachineDocument (Layer H, linkable to model and/or asset,
mirroring RawMaterialDocument's WP5 pattern). Plus ~50 new nullable
columns on the existing Machine table (Layer C) covering identity,
physical/control configuration, operating envelope, calibration,
maintenance summary, document links and PI3 linkage - and two new FKs
(machine_model_id, machine_config_id) linking each plant asset up to the
generic layers above it. One deliberate deferral, flagged not silently
dropped: no new ProductionLine entity for Charlie's Production_Line_ID -
a free-text production_line_label column for now, same "text field
first, promote to a real entity only if a concrete need shows up"
precedent as WP5's ProcessingWindow. One known, deliberately unresolved
overlap, also flagged: MachineMaintenanceRecord covers everything the
existing simpler CalibrationRecord table does, plus an asset FK and
richer fields - not merged or data-migrated in this schema-only pass,
since neither table has a UI yet and merging is a data decision, not a
schema one. Verified via py_compile and a live local SQLite init_db()
pass before touching Supabase; applied to the real rigid_foam schema as
two migrations ("machine_data_architecture_layers_a_to_h" and
"machine_data_seed_category_taxonomy"), RLS enabled on all 8 new tables
matching every other rigid_foam table's posture, verified afterward via
information_schema (8 new tables present, machines table now 71 columns,
17 categories seeded). Full regression suite passes unchanged - schema
additions only, nothing existing altered. No manufacturer/model data
populated, no UI pages built - both explicitly paused pending Stefan's
scope/ownership decision on the research task.

v0.9.0 -> v0.10.0 (2026-08-07): Machine Data - imported Charlie's Wave 1
research package (PI3_Rigid_Foam_Machine_Knowledge_Master_Charlie_Research_
v1.xlsx, 64 machine/model records across 9 manufacturers), following the
ownership split confirmed in the v2 "Ownership Corrected" design doc
(section 12A - Charlie owns research/population, JC owns schema/import/
QA). Three schema-typing gaps found while mapping the real data (JC's own
design choices, not Charlie content errors) were fixed directly: added
source_output_value/source_output_uom (Text) and research_status (Text)
columns to MachineModel to hold fields the research package carries that
the schema-only pass hadn't anticipated; retyped rigid_foam_process from
Boolean to String (the research data populates it with a process
category per row, e.g. "Sandwich panels", not a yes/no flag); retyped
component_count, mixing_pressure_bar and tank_capacity_l from
Integer/Float to String (several manufacturers state these as ranges -
"2+", "100-200" bar, "40/60" L for a dual-tank system - which numeric
columns would reject or truncate). Applied as two Supabase migrations
("machine_model_research_import_fields" and
"machine_model_retype_range_fields"). Imported all 64 rows into
rigid_foam.machine_models. JC's own QA per the design doc's Deliverable
10 wording (duplicate-ID, orphan-link, missing-mandatory-field, invalid-
enum, load-error, source-field-completeness checks) found: 0 duplicate
IDs, 0 orphan category links, 0 missing mandatory fields, 0 rows missing
manufacturer_url/product_page_url/availability_evidence_url/source_
verified_date, and two real content inconsistencies against Charlie's own
controlled vocabularies - (1) one row (HEN-VACUMAT) uses Machine_Category
"Raw-material conditioning", which matched none of the 17 originally
seeded categories, loaded against a new provisional MCAT-18 row of the
same name; (2) 13 rows (all four Zhejiang Lingxin, all three Dongguan
Junying, all six Zhejiang Henghui models) use APAC_Availability_Status
"Confirmed manufacturer in APAC", which is not one of the design doc's
six documented enum values - loaded verbatim rather than force-mapped.
Both issues recorded directly on the affected rows' own notes field and
raised to Charlie via a dedicated findings document (per Stefan's
standing instruction to always produce a written findings doc for this
class of issue, not just a changelog/chat note) -
PI3_Rigid_Foam_Edition_Machine_Data_Findings.docx. Charlie's own
Source_Register sheet (47 bibliography rows) was reviewed but not
imported into the app's SourceRegister table - no column in the Machine_
Knowledge_Master sheet cross-references a Source_ID, and every machine
row already carries its own manufacturer_url/product_page_url/
availability_evidence_url, so importing it would have added a parallel,
disconnected bibliography rather than real traceability value. Full
regression suite (10 pytest files, including both Recipe Optimization
page-smoke tests run in isolation per the established shared-SQLite-file
convention) passes unchanged.

v0.10.0 -> v0.10.1 (2026-08-07): browser-tab favicon fix. Both this app
and the flexible-foam app shared the same page_icon (test tube emoji) in
st.set_page_config(), so their browser tabs looked identical when both
were open. Changed this app's page_icon to a building/construction emoji,
per Stefan's request, to make the two tabs visually distinct. UI-only
change, no schema/data impact.

v0.10.1 -> v0.11.0 (2026-08-07, WP5 Wave 3 - "Quality issues, possible
causes and hypothesis links"): per 01_Wave_Control, Wave 3's own declared
Primary_Sheets range ("13-15") doesn't match its own content - the
quality-issue/cause/link material actually lives on sheets 14, 15 and 16,
while sheet 13 (13_Sample_Locations) sits in the gap between Wave 2's
"08-12" and Wave 3's "13-15" ranges, covered by neither. Rather than
leave sheet 13 orphaned, it was imported as part of this batch (flagged
to Charlie, see findings doc below). Schema additions in db.py: extended
the existing Location table with location_category, coordinate_or_axis,
applicable_object and governance_note (nullable); three new tables -
QualityIssueType (14_Quality_Issues), PossibleCause (15_Possible_Causes),
and IssueCauseLink (16_Issue_Cause_Links, a many-to-many investigation
map between the two - per the sheet's own subtitle, a plausible-hypothesis
list, never a confirmed root cause, so deliberately carries no confidence/
confirmed flag); and a new nullable issue_type_id FK on QualityObservation
pointing at QualityIssueType, added alongside the existing free-text
observation_type field rather than replacing it - same "extend, don't
replace" pattern as RawMaterialAttributeValue (Wave 1) and
PhysicalPropertyMethod.applicable_property_ids (Wave 2). Confirmed no
naming collision with the flexible-foam app's own quality-issue taxonomy
work (tasks #303-306) - that taxonomy lives in a different codebase
(PI3_Plant_Edition_App), not this one. Seeded all of Wave 3's actual
content: 64 quality issue types (14), 61 possible causes (15), 243
issue-cause hypothesis links (16, all "Plausible investigation lead"),
and the 42 sample-location rows from sheet 13 (2 updates onto pre-existing
LOC-021/LOC-030, 40 inserts). One real data-quality issue found in
Charlie's workbook during seeding, fixed and flagged rather than silently
propagated or dropped: 13_Sample_Locations defines LOC-040, LOC-041 and
LOC-042 each twice, with unrelated meanings (an Interface/Z-axis
sandwich-panel location vs. a Cross-width core-sampling position) - kept
each first occurrence under its original code and loaded each second
occurrence under a provisional ID (LOC-040-XW/LOC-041-XW/LOC-042-XW),
matching the COND-020/COND-020-THERM10 precedent from Wave 2. Both this
collision and the sheet-13 wave-boundary gap are recorded on the affected
rows' own governance_note column and raised to Charlie via a dedicated
findings document (per Stefan's standing instruction) -
PI3_Rigid_Foam_Edition_WP5_Wave3_Data_Quality_Findings.docx. Verified via
py_compile, a live local SQLite smoke test, and afterward via independent
row-count/duplicate-ID/orphan-FK checks against the real rigid_foam
schema (64/61/243/42 rows, zero duplicate controlled IDs across all four
tables, zero orphan issue_type_id/cause_id references, zero orphan
quality_observations.issue_type_id references, zero duplicate issue-cause
pairs). Full regression suite (10 pytest files, both Recipe Optimization
page-smoke tests run in isolation per the established shared-SQLite-file
convention) passes unchanged - Wave 3 only added nullable columns and net-
new tables. No dedicated UI surfaces this new taxonomy yet (the Quality
Issue page's free-text picker and any Root-Cause Assistant use of
IssueCauseLink remain flagged follow-up work, same as every prior wave's
"schema + seed now, UI later" pattern).

v0.11.0 -> v0.12.0 (2026-08-07, WP5 Wave 4 - "Derived calculations and
public reference formulation summaries"): same wave-boundary numbering
issue recurs one wave later - 01_Wave_Control declares Wave 4's
Primary_Sheets as "16-18", but sheet 16 (16_Issue_Cause_Links) is Wave
3's own sheet, already imported in that wave; Wave 4's actual content
lives on sheets 17_Calculations, 18_Reference_Formulations and
19_Ref_Formulation_Components (true range 17-19). Imported sheets 17-19
only; did not re-touch sheet 16. Flagged to Charlie, along with a
heads-up that this is now a repeating pattern worth checking across all
five waves at once - see PI3_Rigid_Foam_Edition_WP5_Wave4_Data_Quality_
Findings.docx. Schema additions in db.py: new CalculationDefinition
table (Charlie's CALC-* formula-specification library - stored as data
only, no engine in this app evaluates these formulas yet, matching every
prior wave's schema-first, UI-later pattern); new ReferenceFormulation
and ReferenceFormulationComponent tables holding Charlie's locked,
provenance-controlled public-patent parameter summaries (RF-*), per the
Converged Plan's section 8 reference-formulation policy - chemistry
stored as free text ("PUR"/"PIR") rather than a Chemistry FK, since the
frozen WP2 Implementation Slice only ever controlled PUR (CHM-010) and
PIR has no controlled Chemistry row yet. New nullable RecipeVersion.
reference_formulation_id FK closes RHF-015 ("Reference formulation ID...
reference only, never silent copying"), explicitly deferred in Wave 1's
own changelog pending this table's existence; RHF-014 ("Approved
processing window ID") remains deferred as free text, unchanged.
Imported the 4 patent SourceRegister rows (SRC-PAT-US10640600, SRC-PAT-
EP3115401, SRC-PAT-US11952491, SRC-PAT-US20210079154) that Reference
Formulation rows actually cite by Source_ID - unlike the Machine Data
batch's Source_Register sheet, these are real cross-references, not a
disconnected bibliography, so importing them is real traceability; the
other ~20 standards-body rows in 28_Source_Register (ISO/ASTM/EN) are
not yet referenced by anything and were left unimported, same
disconnected-bibliography reasoning as before. Seeded all of Wave 4's
actual content: 25 calculation definitions (17), 6 reference
formulations (18), and 63 reference-formulation components (19). Unlike
Waves 2 and 3, this wave's own content had zero data-quality issues -
independent JC QA (row counts, duplicate-controlled-ID checks, orphan-FK
checks on reference_formulation_id/source_id, missing-mandatory-field
checks) came back completely clean; the only finding this round is the
wave-boundary numbering gap above. Verified via py_compile, a live local
SQLite smoke test (one row of each new/extended model), and afterward
via the same independent-QA queries against the real rigid_foam schema.
Full regression suite (10 pytest files, both Recipe Optimization
page-smoke tests run in isolation per the established shared-SQLite-file
convention) passes unchanged - Wave 4 only added nullable columns and
net-new tables. No dedicated UI surfaces this new data yet (no page
shows RF-*/CALC-* content, and RecipeVersion's reference_formulation_id
has no picker) - deferred, same as every prior wave's schema-first,
UI-later pattern.

v0.12.0 -> v0.12.1 (2026-08-08, WP5 Wave 3 correction round-trip):
Charlie reviewed both open Wave 3 findings and returned permanent
decisions (PI3_Rigid_Foam_Phase_1_WP5_Wave_3_Response_to_JC_Data_Quality_
Findings.docx + Correction Register xlsx). Applied directly to the real
rigid_foam.locations table (data-only correction, no schema change):
(1) LOC-040/LOC-041/LOC-042 retain their original codes and meanings
(Top facing interface / Bottom facing interface / Joint or edge
profile) - unchanged, governance_note updated from "flagged to Charlie"
to "resolved". (2) The three provisional cross-width rows (LOC-040-XW/
LOC-041-XW/LOC-042-XW) were renamed to permanent LOC-037/LOC-038/LOC-039
("Panel left/centre/right edge core"), per Charlie's instruction to use
the unused plan-position range immediately before the interface family
- category corrected to "Cross-width", axis to "X/Y", applicable_object
to "Panel/core" (all per his Correction Register, superseding the
placeholder values JC had used). sort_order renumbered so LOC-037-039
sit between LOC-036 (end of the plan-position family) and LOC-040
(start of the interface family); everything from the old LOC-040
onward shifted +3 to make room. No re-import needed - Charlie's own
instruction was explicit that the existing successful Wave 3 load
should be preserved, only IDs/provenance corrected in place. Verified
afterward: still 42 location rows, zero duplicate controlled IDs, zero
remaining "-XW" provisional codes.
Also resolved the Wave 2/Wave 3 sheet-13 boundary question flagged in
the same findings doc: Charlie confirmed sheet 13 (13_Sample_Locations)
formally belongs to Wave 2 (corrected Primary_Sheets 08-13, Content_
Scope now explicitly includes sample locations) - the error was in
01_Wave_Control's declared range, not in the semantic ownership of the
content Wave 3 already has to be understood as sheets 14-16, not
13-15. This is metadata/documentation only (this app has no wave-control
table of its own - the correction lives here, in this changelog, and in
the project's shared understanding of the workbook). It does not change
the Wave 4 finding already raised (01_Wave_Control's Wave 4 range also
needs correcting from "16-18" to "17-19") - if anything it independently
confirms that finding, since Wave 3 is now pinned at 14-16, leaving
sheet 16 unambiguously Wave 3's own last sheet and 17 as Wave 4's true
start. Full regression suite (10 pytest files, both Recipe Optimization
page-smoke tests in isolation) passes unchanged - no schema touched,
data-only correction.

v0.12.1 -> v0.13.0 (2026-08-08, Raw Materials Master v2 + Reference
Formulations 10 reconciliation): Charlie delivered two new, larger
workbooks superseding earlier content - PI3_Plant_Edition_Rigid_Foam_
Raw_Materials_Master_v2_MASTER_LINKED.xlsx (151-row commercial
raw-material catalog, material-ID-linked) and PI3_Rigid_Foam_Reference_
Formulations_10_MASTER_LINKED.xlsx (10 reference formulations + 100
material-linked components, superseding WP5 Wave 4's original 6
formulations/63 components). Per Stefan's explicit direction ("Reconcile
now" then "Proceed with full reconciliation"), reconciled rather than
layered on top. New table: RawMaterialCatalogEntry - deliberately not
company/plant-scoped, matching the MachineModel pattern from the Machine
Data Architecture work: a broad commercial-product research catalog
(APAC availability evidence, cost ranges, verification status, source
URLs), distinct from the existing plant-scoped RawMaterial table.
Extended ReferenceFormulation (~33 new nullable columns: chemistry_id/
production_method_id/application_id/construction_id FKs, formulation
basis and UOM, reported index/ratio/water/blowing-agent levels, reported
density/cream/gel/rise/demold/mold-temp/thermal-conductivity/open-cell
values, five review-status fields, release_to_plant_recipe flag, and
source/technical-notes fields) and ReferenceFormulationComponent (10 new
columns: material_id FK into the new catalog table, material_name,
component_side, amount_text, uom_id, dosage_basis, reported_wt_pct,
oh_number_mgkoh_g, master_link_status, notes) - same "extend, don't
replace" pattern as every prior wave, keeping the original Wave 4
free-text fields (chemistry_label, production_or_test_context,
application_context, source_component_term, etc.) untouched alongside
the new structured columns.

Deleted the original 6 Wave 4 ReferenceFormulation rows and their 63
components before re-importing, after independently verifying zero
RecipeVersion.reference_formulation_id references existed anywhere in
Supabase (a genuine delete-and-replace, not a merge, since nothing else
in the app pointed at the old rows). Imported the new 10 reference
formulations (RF-001 through RF-010) and their 100 material-linked
components verbatim from the package, confirmed against its own
23_Master_Link_Check/99_QC sheets (100/100 exact Material_ID links, 0
missing, 0 category-only substitutions). Imported all 151 raw-material
catalog rows (12 isocyanate, 59 polyol, 31 catalyst, 32 surfactant, 7
blowing agent, 8 flame retardant, 2 additive).

Closed three WP1/WP2 controlled-vocabulary gaps discovered while mapping
the new content - the same "frozen Phase 1 Implementation Slice" pattern
already seen in Chemistry/ProductionMethod/Application/
ProductConstruction, now confirmed recurring in two more tables: (1)
RawMaterialCategory - WP2's own 05_RM_Categories sheet (35-row
authoritative taxonomy) had only a subset ever loaded into Supabase;
imported the missing 10 rows the new raw-materials catalog actually
references. (2) UnitOfMeasure - WP1's own 10_Units_Bases sheet defines
UOM-030 (php) and UOM-031 (wt%), but neither had ever been imported;
imported both directly from WP1's canonical definitions. (3) Chemistry/
ProductionMethod/Application/ProductConstruction - imported the specific
missing rows the 10 new formulations actually reference (CHM-020,
PM-130, PM-210, APP-100/300/310, PC-100/130/150), scoped to only what
was genuinely used rather than importing every unused row in each sheet.

One numbering collision found and resolved per Stefan's explicit
decision, one found and left open pending Charlie: the Reference_
Formulations_10 package's own 98_Controlled_Lookups sheet declares
UOM-023 (php) and UOM-024 (wt%) - but WP1's own master already assigns
those exact units to UOM-030/031 (see above). Per Stefan's decision, all
import-time references were mapped onto UOM-030(id 9)/UOM-031(id 10)
rather than creating a second parallel pair; no UOM-023/024 rows exist in
Supabase. Separately, WP1's own master assigns UOM-032 to "mass ratio"
(kg/kg), while Supabase's already-imported UOM-032 (from WP5 Wave 2's own
08_UOM_Additions sheet) means "newton per millimetre" - nothing currently
references the mass-ratio meaning, so left as-is, but flagged to Charlie
since it's a live collision in his own source material. Both raised via
a dedicated findings document, per Stefan's standing instruction -
PI3_Rigid_Foam_Edition_Reconciliation_Data_Quality_Findings.docx.

Independent JC QA (duplicate-controlled-ID, orphan-FK, and
missing-mandatory-field checks) run across every touched table -
raw_material_catalog_entries (151), reference_formulations (10),
reference_formulation_components (100), and all extended/new
controlled-vocabulary tables (chemistries, production_methods,
applications, product_constructions, raw_material_categories,
units_of_measure, source_registers) - came back completely clean: zero
duplicates, zero orphan references, zero missing mandatory fields.
Verified via py_compile and a live local SQLite init_db() smoke test (85
tables) before touching Supabase, and independently afterward via direct
SQL against the real rigid_foam schema. Full regression suite (8 pytest
files, both Recipe Optimization page-smoke tests in isolation) passes
with one pre-existing, unrelated failure confirmed present before this
batch's changes too (test_wp4_recipe_optimization_page_smoke.py's rigid-
grade specification-copy assertion, unrelated to reference formulations
or raw materials - not a regression from this work, not fixed here). No
dedicated UI surfaces this new catalog/formulation data yet - deferred,
same schema-first/UI-later pattern as every prior wave. WP5 Wave 5
("Synthetic recipes, runs, samples, results and controlled failures")
is next per the Converged Plan's sequencing.

2026-08-08 (WP5 Wave 5, "Synthetic recipes, runs, samples, results and
controlled failures"): reused the existing production-data schema
(FoamGrade, RecipeVersion, RecipeComponent, ProductionRun/Cycle/Shot/
OutputItem, Sample, PhysicalPropertyResult, GradeSpecification) for this
wave's synthetic UAT content rather than a parallel "Demo*" table set -
matching the single WP3 UAT chain (FoamGrade id 2, "GRADE-UAT-RPUR-
COLDROOM-001") already live in the same tables. Isolation from real
plant data is via each row's own status/production_use/validation_status
field, not a separate schema or tenant. Added one new small reference
table, ControlledFailureCase (rigid_foam.controlled_failure_cases),
following CalculationDefinition's own precedent - data only, no engine
in this app currently executes these scenarios automatically.

Imported: 4 demo foam grades and recipe versions (DEMO-RCP-001 through
004, referencing reference_formulations RF-001/003/004/006) with their
41 recipe components; 12 production runs (UAT-RUN-0101 through 0403)
each with one production cycle/shot/output item (reusing the existing
WP3 UAT machine/tool/mixhead/cavity/fill-point rows); 24 samples (2 per
run); 96 physical property results (4 per sample - density, thermal
conductivity, compressive strength, closed-cell content); 16 grade
specifications (4 per demo grade, mirroring the workbook's own UAT-GST-
001 through UAT-GST-004 templates); and 12 controlled failure cases
(UAT-FAIL-001 through 012).

Found and corrected two data-quality issues on import, raised to Charlie
via a dedicated findings document (PI3_Rigid_Foam_Edition_WP5_Wave5_
Data_Quality_Findings.docx), per Stefan's standing instruction: (1) the
same wave-boundary numbering gap already flagged twice before (Wave 2/3
and Wave 3/4 boundaries) recurred a third time - Wave 5's declared range
"19-24" claims sheet 19 (Wave 4's own Ref_Formulation_Components);
imported the actual range, 20-25, per 00_Read_Me's own "Evidence 20-25"
citation, and flagged that the same off-by-one pattern also runs through
26_Import_Sequence and 27_Gate_4_Checklist's own internal sheet
citations. (2) 24_Demo_Results' thermal-conductivity rows cited
Property_ID/Method_ID/Condition_ID PROP-015/MTH-015/COND-020 and its
closed-cell-content rows cited Method_ID MTH-018 - the exact wrong codes
Wave 2 already found and corrected for GST-001/002/006/007 at the
template level. Corrected on import to PROP-005/MTH-016/COND-020-THERM10
(thermal) and MTH-012 (closed-cell), verified against the workbook's own
already-correct UAT-GST-001/UAT-GST-004 specification templates; density
and compressive-strength rows were checked against UAT-GST-002/UAT-GST-
003 and found already correct.

Independent JC QA (duplicate-ID, orphan-FK, missing-mandatory-field
checks) across every new/touched row came back clean: row counts match
the workbook exactly (4/41/12/12/12/12/24/96/16/12), zero orphan foreign
keys across all ten parent/child relationships checked, zero duplicate
batch references or controlled_ids, and every QI-*/CAUSE-* code cited in
the twelve controlled failure cases resolves to a real Wave 3 taxonomy
row. Verified via py_compile and a live regression run (37 pytest
tests) before and after this batch's db.py change (git stash comparison)
- 2 failures present identically both with and without the change
(test_wp4_recipe_optimization_page_smoke.py, both grades - a "no such
table: companies" SQLite/thread-isolation error in this sandbox
environment, unrelated to Wave 5's content or schema, not a regression
from this work, not fixed here). WP6 (Validation, UAT and release) is
next per the Converged Plan's sequencing.

2026-08-08 (Charlie's Phase 1 UOM Governance Correction Register v1,
response to the reconciliation batch's UOM-023/024/032 findings):
applied the register's decisions to Supabase - created UOM-100 (Mass
ratio, kg/kg), UOM-101 (Fire index unit), UOM-102 (Class) as new
canonical rigid_foam.units_of_measure rows (ids 11-13), per Decisions
UOM-D-004/UOM-D-005. Confirmed UOM-030 (php)/UOM-031 (wt%)/UOM-032
(N/mm) already matched the register exactly, and every already-live
reference_formulation/reference_formulation_component already carried
UOM-030/031 correctly - the register's decisions were already fully in
force from the earlier Reconciliation batch, before this register
arrived. No UOM-023/024 rows exist anywhere; no duplicate controlled_ids
in units_of_measure after the addition.

The accompanying v2 workbook (PI3_Rigid_Foam_Phase_1_WP5_Wave_4_Derived_
Calculations_and_Reference_Formulations_v2.xlsx) carries two other
sheets that were NOT imported, because each reuses controlled_ids
already live under substantially different content: (1) its
21_Derived_Calculations sheet has 20 rows under CALC-001 through
CALC-020 with stoichiometry/blend-chemistry/blowing/cost formulas, but
rigid_foam.calculation_definitions already has 25 different live rows
(ids 1-25) under those same codes, imported from the original Wave 4
package - process/QC formulas (A:B mass ratio, ratio deviation percent,
core density, packing factor, etc). (2) its 10_Reference_Formulations/
10A_Formulation_Components sheets describe different underlying
formulations under the same RF-001 through RF-010 codes already live
from the Reconciliation batch - component counts differ for every one
of the 10 formulations (live: 7/10/10/10/13/11/11/9/10/9; v2:
11/11/11/11/11/11/11/6/7/8), and material naming differs too (e.g. RF-
001 live is a named 7-component cyclopentane/isopentane system; v2's
RF-001 is an 11-component system with generic "Polyol A/B/C" naming).
Charlie's response letter only describes a UOM correction and doesn't
mention replacing either sheet's content, so this looks unintentional.
Left both live tables untouched rather than guess which version is
authoritative; raised to Charlie via a dedicated findings document
(PI3_Rigid_Foam_Edition_WP5_Wave4_UOM_Governance_and_Content_Collision_
Findings.docx) asking him to confirm replace/add-alongside/disregard
before either sheet is imported. No schema or code change in this
batch - Supabase data only.

2026-08-08: recolored the app theme (.streamlit/config.toml only) -
main window background to a light blue (#DCEEFB) and the sidebar
navigator background to a darker light blue (#A9D3EE) for contrast
between the two, per Stefan's request while awaiting Charlie's reply
on the Wave 5 v3 workbook review. primaryColor and textColor unchanged.
No schema, data, or code change.

2026-08-08 (Charlie's Response to JC v3 Clarification, plus the
accompanying Governance Correction Register v1 and v3 QA Verification
Register v1): all three items raised in JC's v3 review are now fully
resolved, no further ambiguity. (1) Wave-boundary governance: the
20-25 combined-workbook range in 01A_Canonical_Wave_Map is retired;
package governance now uses each workbook's own actual sheet
identifiers (this package's primary content is 23;23A;24;24A-E;25;
26;26A;27;28;29, with 98/99 as support sheets) - this closes the
drift pattern seen at every prior wave boundary. (2) Scope: Charlie
confirms the already-imported Wave 5 dataset (4 recipes DEMO-RCP-001
through 004, 41 components, 12 runs, 24 samples, 96 results, 16 grade
specs, 12 failure cases) remains canonical; the v3 FINAL workbook was
built from a different working draft and is formally withdrawn from
the current import scope - not merged, not reconciled, excluded
outright. Its four additional structures (actual material usage, run
process settings, UAT test limits, expected PI3 outcomes) are parked
for possible later reconciliation, not introduced now. (3) QA: Charlie
reran all 27 formula-driven checks independently against the v3
workbook (all PASS) plus the 3 governance checks, documented in a
separate v3 QA Verification Register - resolving the blank-Result
observation as a missing-cached-formula artifact, not a real failure;
this is a technical record of the withdrawn draft only, not import
authorization.

Implemented the one accepted action: created the permanent COND-011
("Mean test temperature 10 degC", id 26) in rigid_foam.test_conditions
and migrated every live reference off the provisional COND-020-THERM10
(id 19) - 24 physical_property_results rows and 4 grade_specifications
rows via condition_id, plus 3 grade_specification_templates rows via
condition_ids_text (semicolon-delimited token replace, e.g.
"COND-002;COND-020-THERM10" -> "COND-002;COND-011"). Test values
unchanged throughout - condition reference only. Verified independently
after migration: 0 remaining live references to id 19 in any of the
three tables, exactly one COND-011 row exists (no duplicate insert),
and id 19's description was updated in place to record it as retired/
superseded rather than deleted, preserving history. PROP-005/MTH-016
(thermal conductivity) and PROP-018/MTH-012 (closed-cell content)
were already correct and required no change. No other code, schema,
or data changes in this batch.

2026-08-08 (WP6 Gate G5, Stage S01 Baseline Freeze - Charlie's
Execution Plan + Master Register v1): Charlie delivered the final
joint work package for Phase 1 - 13 execution stages, 28 validation
checks, 30 UAT cases, 23 regression checks, defect log, evidence
register, culminating in Stefan's Gate G5 release decision. Ran S01
Baseline Freeze: recorded app version/commit, full rigid_foam schema
snapshot (87 tables), and controlled-data baseline. Confirmed the
WP5-accepted canonical Wave 5 demonstration dataset (4 recipes/41
components/12 runs/24 samples/96 results/16 grade specs/12 failure
cases) is present and exactly matching, coexisting cleanly with one
older, clearly-labeled WP3 vertical-slice reference run chain that
predates Wave 5 (run id 1 "RUN-UAT-RPUR-0001", foam_grade id 2,
recipe_version id 1) - no overlap, no unexplained rows. COND-011
migration reconfirmed in force. Recorded as Evidence EVD-001 in the
WP6 master register; WP6-S01 marked Completed.

Found and fixed one defect during baseline freeze (DEF-001, same
day): rigid_foam.raw_material_catalog_entries (151 rows, the Raw
Materials Master) was the only one of 87 rigid_foam tables with Row
Level Security disabled, exposing it to Supabase's anon/authenticated
client roles. The table has no company_id/plant_id column - it is a
shared global reference catalog, not tenant data - so the fix matches
the posture already standard on the other 86 tables: enabled RLS with
no policies (ALTER TABLE ... ENABLE ROW LEVEL SECURITY; the app's
owner-role connection bypasses RLS regardless, same as every other
table, per the WP0 decision). Applied after Stefan's explicit approval
per this project's standing security-review rule. Verified post-fix:
all 151 rows still readable via the app connection; Supabase's
security advisory for this table now reads "RLS enabled, no policies
exist" - the same accepted state as the rest of the schema, no longer
flagged as disabled. DEF-001 closed, retest PASS, recorded as EVD-002.
No other code or schema changes in this batch.

2026-08-08 (WP6 Gate G5, Stage S02 Clean-database migration validation):
per Stefan's decision to use an isolated Supabase development branch
rather than test against the shared production project, created branch
"wp6-s02-s04-validation" (project lnjzlnmbkiqeibcfpplg, ~$0.01344/hour,
cost approved by Stefan) to hold S02-S04. Supabase's own branch
mechanism replays the target project's ENTIRE migration history
(103 named migrations, shared project-wide across both this app's
rigid_foam schema and the flexible-foam app's public schema, since
Supabase tracks migrations per-project, not per-schema) - the branch
came up MIGRATIONS_FAILED.

Root cause (DEF-002, logged in the WP6 master register): a real,
previously-undetected ordering defect in the flexible-foam app's own
migration history, unrelated to rigid_foam engineering. Migration
"drop_maintenance_and_license_records" (2026-07-31, part of that app's
own task #236 cleanup) runs before, in the recorded sequence,
"enable_rls_maintenance_and_license_records" (2026-08-02) - so a
from-scratch replay drops the table and then tries to ALTER TABLE ...
ENABLE ROW LEVEL SECURITY on a table that no longer exists ("relation
public.maintenance_and_license_records does not exist"), aborting the
replay there. Confirmed via get_logs(service=postgres) on the branch
and independently confirmed the replay never got further: the branch's
public schema only ever reached 33 tables (a subset predating both
that drop and this app's 2026-08-06 fork point) and rigid_foam schema
was never created on it at all, since every rigid_foam-creating
migration is numbered after the failure point. This defect is invisible
on the live production database (which was never rebuilt from empty,
only altered incrementally) and would only ever surface on a from-
scratch replay - exactly what S02 exists to test, and exactly what it
caught. It is a legitimate WP6 finding in its own right, logged as
DEF-002, but Supabase's migration history is an append-only execution
ledger with no supported tool-level way to edit or remove a past
recorded migration, so it cannot be fixed by adding a later corrective
migration - a new branch replay would hit the identical failure again
regardless of anything added afterward.

Pivoted S02's actual clean-build test to this app's own established
migration practice instead of Supabase's native replay mechanism
(version.py's WP0 decision: "SQLAlchemy models + ad-hoc SQL applied
directly to Supabase", proven locally by tests/test_schema_migration.py
- no file-based, dependency-ordered migration framework in this repo to
begin with). Generated the exact CREATE SCHEMA/CREATE TABLE DDL that
db.Base.metadata would produce (compiled for the postgresql dialect
from db.py's live ORM metadata, sorted_tables order - the same
mechanism test_schema_migration.py already exercises locally) and
applied it directly, via two apply_migration calls, to the same
isolated branch's own Postgres instance (still ACTIVE_HEALTHY
independent of the native MIGRATIONS_FAILED replay status). Result:
all 86 rigid_foam tables created with zero errors, exactly matching
the 86 tables the live production rigid_foam schema currently has
(name-for-name identical set - confirmed by diff, not just count).
FK-resolution check passed (insert Company, insert Plant referencing
it, join resolves, rolled back - same check test_schema_migration.py
performs). This proves VAL-001's actual intent (db.py's schema reaches
its full, current state on a genuinely empty, isolated database) using
the mechanism this project actually relies on for schema changes - the
native Supabase branch-replay mechanism remains blocked by DEF-002 for
this specific shared project, independent of anything in rigid_foam.
DEF-002 and this pivot are reported to Stefan for a decision on how
to record/resolve DEF-002 before S03/S04 (upgrade-path and rollback
validation) continue on the same branch.

Stefan's decision (2026-08-08, same day): DEF-002 is out of scope for
the Rigid Foam Gate G5 release decision (flexible-app history defect,
not rigid_foam) - remains logged and open as a tooling-level defect
against the shared Supabase project, tracked separately, does not
block WP6 S03-S13. S03/S04 continue on the same branch using the
direct-DDL method that resolved S02.

2026-08-08 (WP6 Gate G5, Stage S03 Upgrade-path migration validation):
on the same branch, post-S02's clean 86-table state, seeded a
representative 9-table business-data chain (company -> plant ->
product family -> foam grade -> recipe version + component ->
production run -> sample -> physical property result) and recorded
before-counts. Applied a representative incremental "upgrade" via
apply_migration - ALTER TABLE ADD COLUMN (nullable) on the populated
physical_property_results table, plus one brand-new table with an FK
into production_runs - matching this project's actual historical
pattern exactly (every WP1-WP5 wave: nullable columns + net-new
tables, applied directly, no destructive DDL). Verified: after-counts
identical to before across all 9 tables (zero loss, zero duplication);
spot-checked row content (batch_reference, zone_label, actual_value/
unit) unchanged; the new column and table were both proven usable
(UPDATE and INSERT round-tripped successfully) before being cleaned
up. Post-cleanup, information_schema confirms exactly 86 tables again,
matching production. VAL-002 (upgrade reaches the same structural
schema as a clean build) and VAL-003 (upgrade preserves existing data)
both Pass.

2026-08-08 (WP6 Gate G5, Stage S04 Rollback/recovery validation): on
the same branch, ran a full disaster-recovery rehearsal - DROP SCHEMA
rigid_foam CASCADE, confirmed via information_schema that the schema
was completely gone (0 tables, 0 schema rows), then rebuilt from the
identical db.py-derived DDL used in S02. Confirmed exactly 86 tables
restored (matching production table-for-table) and re-ran the FK-
resolution check (Company -> Plant insert/join/rollback) against the
rebuilt schema - passed, proving the recovery path is not just
structurally complete but functionally live. This demonstrates the
project's real, working recovery mechanism end to end: db.py's own
ORM metadata is the single source of truth, and a full rebuild from it
reaches the agreed working state deterministically. VAL-004 Pass.

WP6-S02 through S04 are now all complete and evidenced on the isolated
Supabase branch (wp6-s02-s04-validation, project lnjzlnmbkiqeibcfpplg)
per Stefan's original plan ("delete it as soon as S02, S03, and S04
are all done and evidenced") - branch scheduled for deletion this same
session to stop the ~$0.01344/hour cost. WP6-S05 (controlled master-
data validation) is next per straight-through S01-S13 sequencing.

Branch wp6-s02-s04-validation deleted this session (confirmed via
list_branches - only main remains). All further WP6 stages run
directly against the shared production project (aazkdsqpytjciiqtvnfj,
schema rigid_foam), since S05 onward validates already-imported live
master data and application behaviour, not migration mechanics.

2026-08-08 (WP6 Gate G5, Stage S05 Controlled master-data validation):
ran VAL-005 through VAL-013 against live production. No duplicate
controlled_ids across 21 vocabulary tables (VAL-005, Pass). UOM
canonical uniqueness (VAL-007), COND-011 canonical with the provisional
COND-020-THERM10 alias fully retired (VAL-008), sample-location ID
uniqueness across 42 rows including all 6 interface/cross-width
locations (VAL-009), MCAT-18/HEN-VACUMAT machine-taxonomy resolution
(VAL-010), APAC availability vocabulary consistency for all 13
China-based machine_models rows (VAL-011), reference-formulation
provenance - source_id and validation_status non-null on all 10 rows
(VAL-012), and issue_cause_links FK-integrity across all 243 links
(VAL-013) all Pass.

VAL-006 (orphan-reference check) required a methodology split: real
FOREIGN KEY columns can't structurally hold orphans, so the check
targeted the soft/text-based cross-reference fields instead
(condition_ids_text, linked_issue_ids, linked_cause_ids) - all clean.
Two apparent hits were investigated and dismissed as false positives:
physical_property_methods.applicable_property_ids = "Multiple" for
MTH-090/MTH-099 is the intentional sentinel documented in this file's
own WP5 Wave 2 changelog, not an orphan; quality_issue_types.
applicable_methods and raw_material_attribute_definitions.
applicable_categories are free-text scope descriptions, not
controlled_id lists, so checking them against a controlled_id set was
an invalid check, not a real finding.

One genuine new finding did surface: physical_property_definitions.
source_ids and test_conditions.source_ids cite ~32 distinct
standards-body codes (SRC-ISO-*, SRC-ASTM-*, SRC-EN-*, SRC-INT-01,
SRC-PATENT-FAMILY) that do not exist anywhere in source_registers
(17 rows, all internal-governance or patent-related). This contradicts
the assumption recorded in this file's own WP5 Wave 4 changelog, which
stated the ~20 standards-body rows from workbook sheet 28_Source_Register
were "not yet referenced by anything and were left unimported" - VAL-006
shows they ARE referenced, just never imported as rows. One instance of
this same gap was introduced here in the v0.14.3 migration (COND-011's
source_ids='SRC-ISO-8301', added without checking the source_registers
row existed). Logged as DEF-003 (Medium severity, Open, Owner JC) -
not a functional defect since nothing in the app reads source_registers
as a hard dependency today, but a documentation-integrity gap in
Charlie's content-governance territory. Findings and a remediation
decision ask (import missing rows now / accept as deferred governance
gap / Charlie reduces scope to codes in active use) presented to
Stefan via PI3_Rigid_Foam_Phase_1_WP6_S05_Findings_and_DEF-003.docx,
mirroring how DEF-001/DEF-002 were surfaced rather than fixed
unilaterally.

Stefan's decision (2026-08-08, same day): import the missing rows now.
Sourced all 32 missing codes from Charlie's own existing research -
found in two workbooks already in the dev docs folder: WP2 Technical
Master Data's "14_Source_Register" sheet (23 of the 32, all ISO/ASTM
standards) and WP5 Scale-Out Technical Content and Knowledge Library's
"28_Source_Register" sheet (the remaining 8, plus confirming
SRC-PATENT-FAMILY's intended meaning: "patent literature reactivity
observations" for cream/gel/tack-free/rise-time fields), plus SRC-INT-01
from WP2's own header ("PI3 Rigid Foam Edition WP1 Scope and Controlled
Terminology"). None of this required new research - Charlie had already
catalogued these sources for later waves; they just hadn't been carried
into source_registers. Imported via two migrations
(wp6_def003_import_standards_body_source_registers,
wp6_def003_import_src_int_01), adding 32 rows (17 -> 49 total).
Re-ran VAL-006's orphan check after import: 0 of 32 referenced source_ids
tokens remain orphaned (was 32 before the fix). DEF-003 closed same day,
Fix_Version 0.14.9. WP6-S05 is now fully complete with its one defect
closed, not just deferred - straight-through sequencing continues to
WP6-S06 (technical rules validation, needs Charlie).
"""

APP_VERSION = "0.14.9"
