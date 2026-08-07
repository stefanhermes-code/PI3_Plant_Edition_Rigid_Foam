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
"""

APP_VERSION = "0.9.0"
