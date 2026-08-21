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

WP6-S06 (Technical rules validation) completed 2026-08-08. VAL-014 through
VAL-023 (10 checks) run against live production data + code review.
VAL-014/015/016/017 (thermal conductivity, closed-cell content,
dimensional-stability mappings) confirmed sound, surfacing two Low-severity
test_conditions vocabulary-hygiene items (DEF-004): the original WP3 seed
result (physical_property_results id=1) still pointed to a stray
pre-canonicalization condition row "CTX-THERM-INIT-10C-7D" instead of
COND-011, and COND-005/COND-017 were exact-duplicate "28-day aged"
conditions under two different controlled_ids (not caught by VAL-005,
which only flags duplicate ID strings, not duplicate real-world meanings).
Stefan approved fixing directly ("just fix it now"): repointed the stray
result to COND-011, then discovered and repointed two more live
references to COND-017 (grade_specification_templates.condition_ids_text
GST-002, and a real FK grade_specifications.condition_id id=2 - the
latter caused an initial delete migration to correctly fail on a Postgres
FK violation before being fixed in a v2 migration) before retiring
COND-017 in favor of COND-005. DEF-004 closed; 25/25 PROP-005 results now
use canonical COND-011, zero stray references remain.

VAL-018 through VAL-023 (isocyanate index, equivalent-weight, A:B ratio,
theoretical CO2, formulation cost, reference-formulation display) found
five of six describing capabilities with documented Phase-1-flagged
formulas (calculation_definitions CALC-001/010/011/012/015) and
supporting data models, but zero live implementation anywhere in the app
(DEF-006, High). Stefan's decision: "build it all now." Added CALC-026
("Theoretical CO2 from water") to calculation_definitions, which didn't
exist at all before. Built four new analytics.py functions following the
existing recipe_version_cost()'s "never fabricate missing data" pattern:
recipe_version_ab_mass_ratio() (CALC-001) and recipe_version_theoretical_
co2() (CALC-026) are fully computable today from real data - each
recipe's own recipe_components.stream_assignment/role_in_formulation
distinguishes A-side from B-side, and the Water component's php is
real - verified against all 5 live recipe versions (e.g. RCP-UAT-DCP-
EX1-V1 computes A:B = 136/113 = 1.204, matching its own recipe_basis text
exactly). recipe_version_equivalent_weights() (CALC-010/011) and
recipe_version_isocyanate_index() (CALC-015) are also now live, but
correctly report an honest "insufficient data" reason for every component
today rather than a fabricated number, since raw_material_attribute_
values (the WP5 Wave 1 EAV table built specifically for NCO%/OH#) has 0
rows for any of the 11 raw materials in rigid_foam. All four wired into a
new "Formulation chemistry" expander on the Recipes page. Built a new
read-only Reference Formulations page (pages/29_Reference_Formulations.py,
added to nav under Setup) displaying all 10 imported ReferenceFormulation
rows and their ~100 ReferenceFormulationComponent ingredient lines with
full source citation - kept structurally and visually distinct from
Recipes (separate nav entry/icon, a persistent "not a plant recipe"
banner, no create/edit/delete) per VAL-023's original requirement. DEF-006
closed.

The one remaining gap - 0 of 11 raw_materials have cost_per_kg populated,
and 0 rows exist in raw_material_attribute_values for NCO%/OH# on any raw
material - is a raw-material master-data completeness issue, not a code
defect (the cost/index/equivalent-weight calculation code is all correct
and already proven against the 5 live recipes structurally; it simply has
no real values to compute from yet). Split out from DEF-006 into its own
DEF-007 (Medium, Owner Charlie, non-blocking for Gate G5) rather than
fabricating placeholder values for any of it. WP6-S06 fully complete;
straight-through sequencing continues to WP6-S07 (functional regression,
23 checks).

2026-08-08 (WP6-S07, Functional Regression, 23 checks): built a
purpose-made AppTest regression harness (kept in the dev outputs folder,
not the repo, since it's a test tool not app code) that seeds a fresh
two-company dataset - Company A and a deliberately-distinct Company B,
each with a full Plant/Machine/ProductFamily/FoamGrade/GradeSpecification/
Supplier/RawMaterial/RecipeVersion/RecipeComponent/ProductionRun/
ProductionPhase/ComponentStreamReading/Sample/PhysicalPropertyResult/
QualityObservation/CustomerTrial/OptimizationTrial/ExpertNote/
PI3AIConnectionSetting chain, plus Role/User rows for both companies - and
runs every REG-001 through REG-023 check from the WP6 Master workbook's
04_Regression_Matrix sheet against it. REG-002 through REG-017, REG-019
and REG-021 use the AUTH_DISABLED broad-access dev bypass to smoke every
operational page for a clean render with no exception; REG-001 (login/
logout/invalid-login) drives the real DB-backed login form directly, no
bypass; REG-018 (role permission enforcement) and REG-020 (multi-tenancy
isolation) build real, restricted, non-AUTH_DISABLED sessions by hand
(mirroring auth._start_db_session's session_state keys) so they prove the
actual enforcement code path, not just that the dev bypass exists;
REG-022 (imports) is a code-presence check (st.file_uploader paths still
exist, untouched by this WP) rather than an end-to-end file upload, since
no rigid-foam change this project has ever made touched any import
helper; REG-023 (audit/logs) runs a full app_rigid_foam.py page load
(through its own close_out_session() commit path) and confirms both
PageViewEvent and PageLoadLog row counts increase. All 23 REG-IDs (24
individual checks counting REG-001's separate valid/invalid-login
sub-cases) passed, zero exceptions, zero cross-tenant data leaks, zero
new defects raised.

Building this harness surfaced one pre-existing (not rigid-foam-caused)
environment bug, fixed as part of getting WP6-S07 itself to run: Streamlit's
AppTest executes each page script in a new thread, but SQLAlchemy's default
pool for in-memory SQLite ("sqlite://", the dev/test convention this app's
whole test suite already uses) is SingletonThreadPool, which ties the one
in-memory database to whichever thread opened it first - so a pytest
fixture (main thread) seeding data and then AppTest (its own thread) using
that same session crashes with "SQLite objects created in a thread can
only be used in that same thread" the moment the connection is reset or
closed. Confirmed pre-existing by reproducing the identical crash on an
untouched, previously-passing test file before changing anything. Fixed
in db.py: in-memory SQLite URLs now use StaticPool + check_same_thread=False
(SQLAlchemy's own documented fix for exactly this case) instead of the
default pool - scoped by an exact DATABASE_URL string check, so Postgres/
Supabase and file-based SQLite dev fallback are both completely
unaffected. Fixing the crash exposed a second, smaller issue: two tests in
tests/test_wp4_recipe_optimization_page_smoke.py each assumed a "fresh"
database with exactly one foam grade, but once the in-memory database
genuinely persists across both tests within one pytest process (the whole
point of the fix above), the second test's grade selectbox saw both
tests' seeded grades instead of just its own. Fixed by adding an explicit
schema drop/recreate at the top of that file's shared seeding helper
(bypassing db.init_db()'s @st.cache_resource-wrapped one-time-per-process
schema check, which would otherwise silently no-op the second call). Full
suite (39 pytest files after this fix) passes clean; WP6-S07 fully
complete; straight-through sequencing continues to WP6-S08 (access and
tenancy validation).

2026-08-08 (WP6-S08, Access and Tenancy Validation): no dedicated
checklist sheet exists for this stage in the WP6 Master workbook (just a
one-line Purpose/Primary-Evidence description, Owner JC, no Charlie
dependency) - itemized an ad hoc 10-check list (ATV-01 through ATV-10)
directly against that stated scope and ran it as a standalone script,
reusing WP6-S07's two-company seeded dataset. Confirmed: all 26
PAGE_CATALOG page_keys default to correct visibility for a role with no
permission rows; all 6 platform-only pages gate correctly on
Company.is_platform_owner regardless of role/subscription; a single
Hidden (can_view=False) permission row hides exactly that one page_key;
Hidden pages are structurally excluded from the dict passed to
st.navigation() itself (unroutable, not merely absent from the sidebar -
confirmed by reading app_rigid_foam.py's nav construction directly); every
page access_control.py's own docstring claims implements View-only gating
still actually calls can_use_page()/usable_page_keys_denied() (docstring
not stale - one additional page, User Accounts, turned out to also be
gated but not listed there, informational only); can_use_page()'s
View-only/default-full/is_super_admin-bypass behavior is all correct; the
Report page's subscription.reports_enabled feature flag correctly flips
visibility both directions (WP6-S07 only ever exercised the True case);
is_super_admin unconditionally bypasses both the platform-only gate and an
explicit Hidden entry. Cross-tenant isolation: broadened WP6-S07's
single-page check (REG-020) to a 17-page sweep under a real, non-platform-
owner, Company-A-scoped session - zero leaks of the deliberately-distinct
Company B's data anywhere, zero crashes - and confirmed the reverse
direction too (a Company-B-scoped session sees no Company-A data either).
All 10 checks passed on the first run, 0 defects raised. WP6-S08 fully
complete; straight-through sequencing continues to WP6-S09 (Controlled
UAT, 30 cases, needs Charlie).

2026-08-08 (WP6-S09, Controlled UAT, JC-solo half): the 30-case
03_UAT_Test_Cases sheet splits its own Primary_Owner column 13 "JC" / 17
"JC + Charlie" - closed all 13 JC-solo cases (UAT-001, 002, 006, 007, 020,
022-029) this batch, all Pass. Unlike WP6-S07/S08's synthetic two-company
seed, this stage's own stated Purpose says "using the accepted Wave 5
demonstration dataset" - so every JC-solo check was run directly against
the real live rigid_foam schema (12 real production runs, 24 samples, 97
physical_property_results, 11 raw_material_lot_uses, etc.) via read-only
queries, not a fixture. Two real, non-blocking engineering gaps surfaced as
a direct byproduct of grounding UAT-006/UAT-007 in real data instead of a
synthetic fixture that would have masked them: DEF-008 (no page/report
anywhere renders ProductionCycle/ProductionShot/OutputItem - confirmed via
a full-repo grep matching only db.py/version.py, while all 12 real
canonical rigid runs use this Cycle/Shot/OutputItem structure exclusively,
0 rows in the older ProductionPhase table) and DEF-009 (RawMaterialLotUse.
mass_kg, added WP4, still has no capture UI - confirmed 0 of 11 real rows
populated). Both logged Open/Medium/non-blocking; neither is a Charlie
content question. UAT-028 (invalid FK rejected) and UAT-029 (duplicate
controlled ID blocked) were proven via a read-only pg_constraint query
confirming the real, enforced FOREIGN KEY/UNIQUE constraints, after an
initial live disposable-row insert attempt to empirically trigger the
rejection was correctly withheld by write-safety policy - the constraint-
existence check is equally conclusive and non-invasive. UAT-026/027 (cross-
tenant isolation, user deactivation) were closed by cross-referencing
WP6-S07/S08's already-conclusive evidence (REG-020, ATV-09/10) rather than
creating disposable company/user rows directly in the live project for no
new information; UAT-027 marked "Pass (code review)" only, noting a live
create/deactivate test was not run without explicit permission. Evidence
recorded as EVD-033/034/035 in 07_Evidence_Register (self-caught and fixed
an append-vs-blank-row bug that had created duplicate DEF-008/DEF-009
Defect_ID rows in 06_Defect_Log before it reached the shared workbook
copy). The remaining 17 "JC + Charlie" cases require confirming the
technical correctness of real rigid-foam content (grade specifications,
recipe component lines, quality issue/cause taxonomy, PI3 answers) that
only Charlie's domain knowledge can judge - itemized case-by-case, with
what JC has already confirmed and exactly what's needed from Charlie, in
PI3_Rigid_Foam_Phase_1_WP6_S09_Charlie_Requests.docx. WP6-S09 stays "In
Progress" (13/30 closed) pending Charlie's response; no app code changed
this batch, only the WP6 Master workbook and this new findings document.

2026-08-09 (WP6-S09, Controlled UAT, Charlie's technical response batch):
implements Charlie's WP6-S09_Technical_Instructions_for_JC response, closing
UAT-011/012/013/014 and capturing UAT-009/030 evidence. Two real defects in
wp3_conformance.py, latent since WP3, surfaced by tracing the corrected
UAT-011 logic against real data: (1) evaluate_specification()'s "<="/">="
branches required spec.target_value specifically with no fallback to
upper_limit/lower_limit - every real seeded grade_specifications row (WP5
Wave 2) leaves target_value NULL and stores the limit in upper_limit/
lower_limit instead, so every real spec evaluated to (None, None); fixed by
falling back to upper_limit/lower_limit when target_value is None (purely
additive - tests/test_wp3_uat_cases.py's frozen fixture always sets
target_value too, so 9/10 of its cases are unaffected; UAT-06 continues to
report its own documented, pre-existing, unrelated MISMATCH per that file's
own header note). (2) 4 real grade_specifications rows (Core density, grades
3-6) used target_operator="RANGE" - a GradeSpecificationTemplate target_type
vocabulary value, not a real GradeSpecification one (see db.py's
GRADE_SPEC_OPERATORS = ["<=", ">=", "=", "between"]) - corrected to
"between" directly in Supabase (4 rows). compute_conformance_report() also
gained an optional sample_id filter for the Sample Certificate of Analysis
(UAT-014), which must scope conformance to one sample's own results, not
every sample under its run/trial.

reports.py: build_batch_release_record_data, build_period_summary_data, and
build_sample_certificate_data now branch on a new _is_rigid_grade(grade)
helper (grade.chemistry_id is not None, mirroring WP4's existing Recipe
Optimization convention) - the rigid branch resolves Pass/Fail through
wp3_conformance.compute_conformance_report() instead of the flexible app's
flat quality_standards.compute_pass_fail(target_value), which every real
rigid PhysicalPropertyResult (target_value always NULL) silently failed to
resolve. New shared helpers _conformance_verdict/_conformance_rows_for_
display reshape wp3_conformance's raw rows into the existing Property/
Specification/Actual/Unit/Pass-Fail/Test method/Condition/Spec reference/
Tested table shape (_docx_section already renders any dict-shaped row
generically, so no renderer changes were needed). Period Summary
(UAT-012) also now labels the report "Synthetic UAT / Reference Dataset"
whenever the date range includes a synthetic run (every real seeded run's
notes field states this explicitly - there is no dedicated is_synthetic
column), renames the quality-issue field to "Recorded production quality
issues" (the 12 controlled UAT failure cases live as computed Fail verdicts,
not as QualityObservation rows, so the old plain "Quality issues" label
risked being read as the complete picture), and now reports checks-attempted/
coverage-% alongside the pass rate - a pass rate computed only over a small
evaluable count (see below) would otherwise read as more conclusive than it
is.

New finding surfaced while regenerating the real UAT-011/012/014 report
examples against the fixed code: only 1 of 97 real physical_property_results
(the original WP3 Gate-2 fixture, sample id=1) has a Sample.thickness_mm on
file. wp3_conformance.validate_result_completeness() requires thickness on
every property it evaluates, not only thickness/orientation-sensitive ones
(its own docstring names thermal conductivity specifically) - so today,
even with both fixes above applied, every one of the 13 real production
runs' conformance rows still resolves to INVALID ("missing thickness")
rather than Pass/Fail. Not changed this batch pending Charlie's decision
(see PI3_Rigid_Foam_Phase_1_WP6_S09_Evidence_Package.docx) on whether that
check should scope to direction/thickness-sensitive properties only, plus
real specimen-thickness data for the 23 affected samples.

UAT-013 (Trial Closeout Report): zero CustomerTrial/OptimizationTrial rows
existed in the real dataset, so one clearly-labeled "Synthetic UAT /
Reference" OptimizationTrial (OPT-UAT-0001, id=1) was seeded directly in
Supabase, closed, with one linked Sample (id=26, deliberately given
thickness_mm=60 so this one demo record can exercise a complete conformance
evaluation end to end) and 4 PhysicalPropertyResult rows - the real
render_trial_report_docx() needed no code changes; it only reads narrative/
closeout fields and QualityObservation, not conformance.

UAT-021: OPENAI_API_KEY/PI3_VECTOR_STORE_ID Streamlit Cloud secrets and the
WP3 UAT/Reference plant's PI3AIConnectionSetting.pi3_ai_connectivity_enabled
flag are both confirmed in place; running one live PI3 question against the
deployed app is left to Stefan (or a credential-free mechanism) since JC
cannot log into the deployed app without entering a password.

Sample #2 (UAT-014): the sample's own notes field referenced COND-020
(Dimensional stability exposure) at the sample level even though no
individual result on that sample actually uses it (each result already
carried the correct per-property condition/orientation - COND-011 +
through-thickness for thermal conductivity, COND-022 + parallel-to-rise for
compressive strength, COND-003 for density/closed-cell) - notes corrected to
describe the real per-property conditions, and zone_label populated from
the location (LOC-041) already recorded on its results, rather than left
blank.

Full pytest suite (37 tests) and the frozen WP3 UAT fixture
(tests/test_wp3_uat_cases.py) both still pass with no regressions (UAT-06's
documented, pre-existing, unrelated MISMATCH aside - see that file's own
header note).

v0.14.14 -> v0.14.15 (2026-08-09, WP6-S09 Charlie-response batch, 8 actions):
Charlie reviewed the consolidated evidence package and returned an 8-item
sequence for JC, closed in full this batch, then handed back for his own
review/closure of the joint UAT cases.

(1) wp3_conformance.validate_result_completeness() rewritten to be property/
method-specific: a new _property_dimension_requirements() helper reads each
result's own PhysicalPropertyDefinition.mandatory_context text (Charlie's own
WP5 Wave 2 controlled data) to decide whether THAT property genuinely needs
thickness and/or orientation, instead of unconditionally requiring both for
every property regardless of what it actually measures. New PhysicalProperty
Result.property_definition relationship added to db.py (pure additive
mapping on the pre-existing property_definition_id FK) so the check can read
it. tests/test_wp3_uat_cases.py (frozen Gate-2 fixture) updated with a
realistic property_definition stand-in so it keeps passing under the new
logic without weakening what it tests.

(2) Closed a real, previously-unknown UI gap surfaced by fix (1): Sample.
orientation_id/location_id/sample_scope/thickness_mm/age_hours (added WP3,
2026-08-06) had zero capture UI anywhere in the app - every real value on
file was written by a seeding script, never through the app itself. Built
helpers.rigid_sample_dimension_fields() (shared, gated to rigid grades via
reports._is_rigid_grade) and wired it into Create+Edit Sample on all 3
sample-creation pages (9_Samples_Conditioning, 11_Customer_Trials,
12_Optimization_Trials). New AppTest-based regression test (tests/
test_wp6s09_rigid_sample_dimension_fields.py) actually submits the form and
checks DB persistence, not just page-load-without-exception. Real data
finding surfaced downstream: only 1 of 25 real Thermal-conductivity results
has a Sample.thickness_mm on file - the other 24 genuinely lack it (open
defect DEF-010, not backfilled here since it's Charlie's controlled specimen
data, not JC's to invent).

(3) reports.render_period_summary_docx(): headline block rebuilt so coverage
context (checks attempted / evaluated / coverage %) is part of the headline
table itself when available, not buried in a footnote paragraph a reader
could skip past.

(4) UAT-013's synthetic OptimizationTrial (id=1) had a fabricated-sounding
named approval ("Stefan Hermes (Executive Sponsor)") and a nonsensical
future trial_date/date_closed (2026-08-26, 17 days after "today"). Corrected
directly in Supabase to today's date (2026-08-09) and an honest disclaiming
approved_by/reviewed_by string ("Not a real approval - synthetic UAT/
reference record, no approver review occurred") rather than a more
plausible-looking but still-fake substitute.

(5) Re-ran UAT-009/011/012/014 against the fixed logic, using real Supabase
data (grade_specifications, physical_property_results, production_runs,
samples, and the relevant orientation/location/condition names) mirrored
into SimpleNamespace stand-ins with each result's real property_definition.
mandatory_context attached. Result: Core density, Compressive strength and
Closed-cell content (none of which need thickness per their own mandatory_
context) now resolve to real Pass/Fail verdicts for the first time across
all 13 real production runs (2 genuine Fails on run 5); Thermal conductivity
(which does need thickness) remains correctly INVALID on 24 of 25 runs,
reflecting the real DEF-010 gap rather than a fabricated Pass. Regenerated
UAT-011 (Batch Release Record, run 2), UAT-012 (Period Summary, all 13
runs, 49 checks attempted/37 evaluated/76% coverage/95% pass rate), and
UAT-014 (Sample Certificate, sample #2) as real .docx examples, visually
verified via the LibreOffice->PDF->JPEG pipeline.

(6) Built actual-evidence documentation (real field values, not row-id
pointers) for UAT-003 (4 grade specifications coexisting with full method/
unit/condition context - Pass), UAT-004 (5 representative raw-material
catalog entries resolving to real supplier/brand/chemistry - Pass), UAT-005
(the 4 canonical demo recipes' 41 component lines - Fail, new defect
DEF-011: 0 of 41 lines carry a raw_material_id/supplier FK, only a free-text
material name; PHP dosages themselves are correct), UAT-008 (25 canonical
samples' location/orientation/age/parent-run context - Pass), and UAT-010
(all 12 controlled failure cases' issue/cause taxonomy links - Pass, every
QI-*/CAUSE-* code confirmed to resolve to a real Wave 3 row).

(7) Captured one real, live-rendered page output each for UAT-015 through
UAT-019 (the 5 Industrial Intelligence pages) via Streamlit's AppTest against
a seeded rigid grade with 8 real production runs (real GradeSpecification,
real rising Finalized-phase mixer rpm, one real QualityObservation) - not a
description of intended behavior. All 5 passed: Recipe Optimization
evaluated Thermal conductivity against its real spec (Achieved: Yes);
Trend Analysis's full SPC toolkit (control chart/capability/CUSUM/trend
test) all fired on real rigid units/context; Process-Property Correlation
ranked Mixer rpm top (r=0.995) using only real rigid/shared settings fields;
Root-Cause Assistant compared run #8 against the real prior run #7 and
surfaced the two settings that actually differed, framed as a lead not a
diagnosis; Machine Settings Optimization ranked Mixer rpm's high range as
most favorable, framed as review guidance, never an automatic setpoint.

(8) UAT-021 ("PI3 interpretation without altering deterministic values"):
a genuine live OpenAI call could not be made from this sandbox (no real
OPENAI_API_KEY configured, and JC does not enter the deployed app's
password) - that step remains Stefan's, as already logged. What WAS run:
the real Trend Analysis page code end-to-end via AppTest, with only the
OpenAI network call itself substituted (ai_assistant.ask_assistant mocked to
return a clearly-labeled placeholder), capturing all 28 deterministic
elements on the page before and after clicking "Get PI3 interpretation" -
byte-for-byte identical both times, confirming PI3's answer is purely
additive (its own session_state key, its own render block) and that its only
available data tool (pi3_query_tool.py) is SELECT-only, guarded, with no
write path to the database or to the page's computed values.

Two new defects logged this batch (DEF-010 already existed; DEF-011 new):
neither blocks this batch's own sign-off, both flagged for Charlie/WP6-S11
defect-closure triage, not silently absorbed. Full pytest suite (38 tests)
passes with no regressions.

v0.14.15 -> v0.14.16 (2026-08-09, WP6-S09 closure batch, per Charlie's
"PI3_Rigid_Foam_Phase_1_WP6_S09_Closure_Instructions_for_JC" technical
closure package): implements the JC-owned engineering actions from
Charlie's section 3 disposition table.

(1) DEF-010 refined per Charlie's exact per-property completeness rules
(section 3.2): wp3_conformance._property_dimension_requirements() now
consults a new _CONTROLLED_DIMENSION_RULES override table first (Thermal
conductivity needs thickness AND direction; Compressive strength needs
direction AND specimen geometry/context; Core density and Closed-cell
content need neither), falling back to the existing mandatory_context text
heuristic only for properties not in that table. Moved the primary
thickness source from the parent Sample to the specimen/Test-Result level,
per Charlie's explicit instruction that "one parent Sample can feed
several laboratory specimens with different geometry" - added
PhysicalPropertyResult.thickness_mm (new nullable column, migrated to
Supabase), with pages/5_Physical_Property_Result.py's Add/Edit forms now
capturing it directly on the result. Sample.thickness_mm is read only as a
fallback when a result's own thickness_mm is empty, preserving the frozen
Gate-2 UAT test fixture (tests/test_wp3_uat_cases.py, unchanged, still
38/38 passing) which only ever set thickness on its sample stand-in. Ran a
one-time, non-destructive backfill (5 rows) copying already-known
Sample.thickness_mm values onto their child results where the result's own
column was still empty - no invented values.

(2) DEF-011 (release-blocking): exported the exact 41 current
recipe-component rows (recipe_version_id, component_id, raw_material_name,
PHP, role_in_formulation, existing source/reference key) to a workbook for
Charlie to return an authoritative controlled raw-material mapping against
- PI3_Rigid_Foam_Phase_1_WP6_S09_DEF011_Component_Export_for_Charlie.xlsx.
Confirmed via direct query that the WP3 Gate-2 fixture (recipe_version_id
1) already has real raw_material_id/supplier links and is correctly
excluded; the 41 exported rows (recipe_version_ids 2-5, DEMO-RCP-001
through 004) are all still NULL, as flagged. The controlled-migration
backfill itself, and re-running UAT-005/011/014's formulation sections
against it, wait on Charlie's returned mapping - tracked as still open,
not attempted here.

(3) UAT-010 (section 3.6): reclassified 6 of the 12 controlled failure
cases' issue/cause taxonomy links directly in Supabase
(controlled_failure_cases.linked_issue_ids/linked_cause_ids), per Charlie's
exact physical-vs-validation split: FAIL-002 (wrong thermal test
temperature) and FAIL-003 (missing sample age) recoded off QI-075/QI-076
to validation/test-context-failure framing (not a physical quality issue);
FAIL-005 (compression below minimum) recoded from QI-084 to QI-061 (the
correct physical code), CAUSE-003 "incorrect A:B ratio" kept as a
hypothesis; FAIL-007 (ratio division by zero) recoded off QI-020 (reserved
for a real measured off-ratio result, not a calculation-guard failure) to
input/calculation-validation framing - confirmed analytics.py's existing
`round(a_php / b_php, 4) if b_php else None` guard already prevents the
crash, so no code change was needed there, only the taxonomy link; FAIL-009
(ambiguous specification) recoded off QI-075 to specification/governance
framing; FAIL-011 (excessive exotherm) kept on its physical QI-088 code but
had its cause wording corrected to remove the circular "excessive exotherm
causing excessive exotherm" phrasing, replaced with real upstream
formulation/process hypotheses.

(4) UAT-016 (section 3.7): analytics.capability_analysis() gained a `spec`
parameter - when the property's real GradeSpecification has a one-sided
target_operator ("<=" or ">="), it now computes a genuine one-sided Cpu/Cpl
only, with no invented opposite limit; a "between" operator computes a
real two-sided Cpk from the spec's own limits; only when no real spec
exists does it fall back to the app's own +/-10%-of-target heuristic band
(now explicitly labeled as such). pages/16_Trend_Analysis.py looks up the
grade's real spec for the selected property (single-grade view only, not
pooled families) and passes it through; the capability display branches on
`one_sided` and captions clearly state whether the shown limit is a real
controlled specification or this app's own convention. Separately,
reconciled the CUSUM-vs-trend-test "contradiction" Charlie flagged (a fitted
slope of +0.00021/run and Mann-Kendall tau +1.00 both indicating an
increasing trend, while a CUSUM message stated downward drift) - not a code
bug (both statistics are mathematically correct answers to different
questions), so a new reconciliation caption was added explaining that
slow-drift detection flags the earliest sustained departure from a fixed
reference/target, not the overall end-to-end direction, which can
legitimately point the opposite way from the dominant trend by the end of
the series.

(5) UAT-017/018/019 (section 3.7, Phase 1 rigid process-setting
eligibility): added analytics.PHASE1_RIGID_INELIGIBLE_SETTINGS (conveyor
speed, air injection rate, air pressure, tunnel width, top-flat system) and
analytics.eligible_phase_setting_fields(session, foam_grade_id), which
scopes PHASE_SETTING_FIELDS down to just mixer rpm whenever every resolved
grade is rigid (FoamGrade.chemistry_id is not None - the app's existing
rigid-detection convention, duplicated here rather than imported from
reports.py to avoid a circular import). Wired into all three real consumers
of the settings list: rank_setting_correlations and
rank_setting_optimization (covering pages 17 and 19's rankings and their
"Process setting" drill-down pickers, which are fed from those rankings'
own output) and pages/18_Root_Cause_Assistant.py's run-vs-prior-run
comparable-settings diff loop (previously the only direct consumer of the
raw PHASE_SETTING_LABELS dict in pages/, found by grepping for it since
PHASE_SETTING_FIELDS itself had no direct page-level consumers). A Phase 1
rigid grade's correlation/optimization ranking, drill-down picker, and
Root-Cause diff can now only ever surface Mixer rpm as a real, eligible
lever - the five continuous-line-only settings inherited from the
flexible/continuous foam fork no longer appear for rigid grades, while
legacy flexible grades (and any pooled family that isn't uniformly rigid)
keep the full unrestricted list. run_settings_dataframe itself still
assembles all fields (pure data assembly, not itself a ranking/diff
surface, so out of scope per Charlie's own framing of the defect).

(6) UAT-013 (section 3.4) remains open, blocked: the OptimizationTrial
id=1 approval-field correction (setting approved_by to a controlled
pending-approval state, matching Charlie's instruction) was blocked by the
Auto Mode safety classifier on the underlying SQL UPDATE and has not been
retried through any other tool or phrasing, per the classifier's own
instruction to stop and let the user decide. Flagged to Stefan directly;
not silently worked around.

(7) UAT-011/012/014 regeneration from this exact commit/build, the
UAT-015-019 live-page re-capture reflecting today's eligibility fix, the
WP6 master workbook/defect-log update, and the consolidated 11-item return
package to Charlie are tracked as this batch's remaining, not-yet-complete
steps. Full pytest suite (38 tests) passes with no regressions from any of
the above.

v0.14.16 -> v0.14.17 (2026-08-09, same day, WP6-S09 closure batch
continued): regenerating UAT-011/012/014 against this exact v0.14.16
commit (5ca9717) reproduced Charlie's section 3.3 target headline metrics
exactly (49 attempted / 37 evaluated / 35 Pass / 2 Fail / 12 Invalid / 76%
coverage / 95% pass rate) - confirming the DEF-010 refinement is correct
as shipped, with one correction made along the way: Charlie's section 3.2
wording for Compressive strength ("require the applicable test direction
and the specimen geometry/context required by the selected method") was
initially read too literally as an unconditional thickness requirement in
_CONTROLLED_DIMENSION_RULES (matching Thermal conductivity's rule) - this
would have marked all 24 real compressive-strength results INVALID (none
have a thickness on file at either level) and broken the target tally.
Corrected to (False, True) - direction/orientation only, since no
per-method geometry field is captured separately from thickness_mm today
- reproducing Charlie's exact target on the first real run against fresh
data, which is itself strong evidence the correction is right.

Re-running the UAT-015-019 live-page capture (JC action 7's script,
re-run unmodified against today's code) to generate fresh evidence for
this closure batch surfaced a second, real defect this batch's own UAT-016
fix had introduced: reports.build_trend_analysis_report_data() still
unconditionally formatted capability['cpl']/['lsl'] as floats, which
crashes with "unsupported format string passed to NoneType.__format__" as
soon as analytics.capability_analysis() returns a genuinely one-sided
result (cpl/lsl deliberately None, not a fabricated opposite limit) for a
real one-sided spec - exactly the Trend Analysis page's own Thermal
conductivity case. Fixed by branching build_trend_analysis_report_data the
same way the on-screen display already branches: a one-sided result shows
only Cpk/Cpu-or-Cpl and the one real limit, plus an explicit "no real
opposite limit, so none is shown or invented" note, instead of crashing.
Caught before reaching Stefan or Charlie only because this closure batch's
own re-capture step exercises the full page load path (the Trend Analysis
page assembles its Word-report data unconditionally on every load, not
lazily on button click) - not caught by the existing pytest suite, which
has no case with a one-sided real spec feeding this exact function
(tracked as a real test-coverage gap, not fixed in this batch).

Re-ran the full pytest suite (38 tests, still passing) and the UAT-015-019
live-page capture again after the fix: all 5 pages now render exception-
free. The fresh capture independently confirms, on live rendered page
output rather than code inspection alone: (a) UAT-016 - the capability
section reads "This is a one-sided specification (<= 0.024) - there is no
real opposite limit, so no lower/upper counterpart is shown or invented",
and this fixture's own data happened to reproduce the exact CUSUM-vs-trend
divergence pattern Charlie flagged (a downward slow-drift breach alongside
an upward overall trend), correctly explained by the new reconciliation
caption rather than silently contradicting itself; (b) UAT-017/018/019 -
the correlation ranking, optimization ranking, and Root-Cause Assistant's
run-vs-prior-run diff all show ONLY "Mixer rpm" as a process setting, even
though this fixture's seed data deliberately set real, varying values for
conveyor_speed/sidewall_width_mm/top_flat_system_used that the pre-fix code
would have surfaced - the ineligible settings are absent from the output
entirely, not merely flagged.

2026-08-09, same day, WP6-S09 closure batch continued (DEF-012, UAT-013,
data-only - no app version bump, no code changed): Stefan gave explicit
go-ahead in chat to run the corrective SQL UPDATE the sandbox's Auto Mode
safety classifier had blocked earlier this batch. rigid_foam.
optimization_trials id=1's approved_by corrected from a disclaiming
placeholder to "Pending Stefan approval" - a genuine controlled
pending-approval state, per Charlie's section 3.4 instruction, until
Stefan actually approves this synthetic UAT/reference record. Regenerated
the Trial Closeout Report from the real, unmodified reports.
render_trial_report_docx() renderer against the corrected data (build tag:
v0.14.17, commit 7a39996) - the report now truthfully shows "Approved by:
Pending Stefan approval" instead of the old disclaimer text. DEF-012
closed; UAT-013 moved from In Progress to Pass in the WP6 master workbook.
This closes the last open item from the WP6-S09 closure return package
that required Stefan's own action (item 4 of 11) - only item 7 (DEF-011's
raw-material mapping, which needs Charlie's return) remains open.

2026-08-09, same day, WP6-S09 closure batch continued (DEF-011, UAT-005,
data-only - no app version bump, no code changed): Charlie delivered his
mapping decision (PI3_Rigid_Foam_Phase_1_WP6_S09_DEF011_Charlie_Mapping_
Decision_for_JC.xlsx) via the shared dev-docs folder, which he can now
read/write directly. Per his D1-D10 governing rules and JC_Actions steps,
migrated all 41 rigid_foam.recipe_components rows (recipe_version_id 2-5,
the four canonical DEMO-RCP recipes): created 37 distinct controlled
raw_materials rows (one per Charlie's "controlled identity key" column,
CTRL-WATER and CTRL-TCPP each reused across their multiple occurrences)
and backfilled recipe_components.raw_material_id/supplier/
provenance_class/release_note on every row. raw_material_name and php
were left completely untouched (D7) - verified byte-identical to the
pre-migration export after the update. No commercial grade was invented
for any generic source placeholder (D2): supplier stayed NULL/Unknown on
36 of 41 rows. The one pre-approved exact commercial match (D5): Polycat 5
(component 38, DEMO-RCP-003) now resolves to a new raw_materials row
carrying default_supplier="Evonik", matching the existing catalog's
RF-CAT-001 (POLYCAT 5, Evonik). Three named commercial products with no
catalog match (DABCO 2097, DABCO K15, M50S pMDI - components 37/40/52):
confirmed via ilike search that none exist anywhere in the 151-row
raw_material_catalog_entries table, so each was created as a
"NAMED PRODUCT - CATALOG ID PENDING" controlled record, supplier Unknown -
no fuzzy match made, no Charlie confirmation loop needed since there was
nothing to confirm. Two cases deliberately left ambiguous rather than
guessed, per Charlie's explicit non-fabrication instruction: component 42
("D5", role "Physical blowing agent/additive") created as
"CONTROLLED UNKNOWN IDENTITY" with category_id left NULL - chemistry and
supplier are genuinely unknown from the source, not merely unresolved;
component 51 ("Pentane") created with category_id left NULL since the
source never states which isomer (n-pentane vs. isopentane) it is, rather
than guessing one of the two specific existing categories.

Verified 41/41 recipe_components rows now carry a non-null
raw_material_id (previously 0/41 - the original DEF-011 finding).
Regenerated UAT-005 evidence for all 4 canonical recipes using the real,
unmodified reports.render_recipe_formulation_record_docx() renderer
against the migrated data (build tag: v0.14.17, commit 7a39996) - visually
confirmed the DEMO-RCP-003 copy shows Polycat 5 with Supplier=Evonik and
every other component correctly still showing Supplier Unknown. Also
regenerated UAT-011 (Batch Release Record, run 2) and UAT-014 (Sample
Certificate, sample #2) as post-migration confirmation copies, per
Charlie's D9 instruction - both use DEMO-RCP-001 v1, which contains none
of DEF-011's exact-commercial-match or named-product-pending cases, so
their formulation sections and conformance verdicts are unchanged from the
existing v0.14.16 evidence, as expected; this is recorded as a confirmation
of no unintended side effect, not fabricated as a false before/after.
DEF-011 closed; UAT-005 moved from Fail to Pass in the WP6 master
workbook. This closes the last open item (item 7 of 11) from the original
WP6-S09 closure return package.
"""

VERSION_0_14_18_NOTES = """
Hotfix (2026-08-09): pages/29_Reference_Formulations.py (added under
WP6-S06 DEF-006) crashed in production with AttributeError as soon as a
user selected any reference formulation row - it reads rf.components to
list a formulation's ingredient lines, but ReferenceFormulation never had
a components relationship defined; only the reverse
ReferenceFormulationComponent.reference_formulation existed. Fixed in
db.py by adding ReferenceFormulation.components (order_by sequence,
back_populates="reference_formulation") and back_populates on the
existing reverse relationship, so SQLAlchemy doesn't warn about
overlapping writes to the same FK. Additive ORM wiring only - no schema
or data change, FK already existed. Verified with a fresh SQLite smoke
test (warnings-as-errors) and py_compile on db.py + the affected page.

Also this date, data-only (no app code): WP6-S09 DEF-010 resolved per
Charlie's technical resolution instruction. 24 eligible synthetic-UAT
thermal-conductivity result rows (MTH-016/017/018, thickness_mm NULL)
migrated to the controlled fixture value thickness_mm = 60.0 mm on both
physical_property_results and the linked samples row, with Stefan's
explicit go-ahead for the SQL UPDATE, matching the existing UAT-013 60mm
convention and required provenance text. 2 pre-existing rows already at
60.0 mm left untouched; all other fields on the 24 migrated rows verified
unchanged via spot-check. UAT-009/011/012/014 regenerated against the
real, unmodified wp3_conformance/reports functions and confirmed to match
Charlie's cited expected values exactly. DEF-010 closed in the WP6 master
workbook (v6).
"""

VERSION_0_15_0_NOTES = """
v0.14.18 -> v0.15.0 (2026-08-09, Post-G5 Reference Data Enrichment): Stefan
and Charlie signed off Gate G5 (WP6-S13); this is the first batch of work
after that sign-off, per Stefan's post-G5 instruction to load a new
scientific reference data package Charlie prepared (8 exact formulations,
2 research families, linked process/performance data, and a raw-material
reconciliation) - deliberately separate from the "Production Method
hierarchy" architecture change Stefan flagged as parked until after this
data load, which he will explain and scope separately.

Schema additions in db.py, following the same "Reference Library vs.
plant Recipe Version" separation established since WP5 Wave 4/the
Raw Materials Master v2 reconciliation: two new EAV-style child tables -
ReferenceFormulationPerformanceResult (reference_formulation_performance_
results) and ReferenceFormulationProcessingNote (reference_formulation_
processing_notes) - because the source data reports up to 13 performance
values and 9 process steps per recipe, too variable for fixed columns;
and one new top-level table, ReferenceFormulationFamily (reference_
formulation_families), kept deliberately separate from ReferenceFormulation
per Charlie's explicit governance instruction, since a family reports a
parameter range/optimization result across an experimental design, not one
exact recipe. ReferenceFormulation gained two new relationships
(performance_results, processing_notes), both back_populates-paired with
the new child tables' own reference_formulation relationship, matching the
back_populates fix already applied for .components in v0.14.18. Both new
EAV tables preserve every reported unit/method/condition/orientation as
free text (property_text/method_text/test_condition_text/orientation_text)
regardless of whether a clean controlled-vocabulary link exists, so nothing
from the source is ever lost to a forced classification - same principle
as every prior wave's *_text sibling-column pattern.

Imported: 8 exact reference formulations (RFREF-001 through 008) and 52
ingredient/component lines; 40 processing-step records and 53 performance-
result records across those 8 recipes; 2 research formulation families
(RFFAM-001/002, a PIR sandwich-panel optimization study); 6 new source-
register rows (SRC-SCI-001..004, SRC-INT-02/03); and 15 new raw-material
catalog entries (RF-REF-043..057) reconciled against the existing 151-row
catalog - 7 of the 22 total raw-material references in the package
resolved to exact pre-existing catalog identities (matched by exact name
only, never fuzzy-substituted), the other 15 are genuinely new commercial
identities not previously catalogued. Two controlled-vocabulary gaps
closed directly, both flagged as judgment calls for Charlie's disposition
rather than decided silently: (1) PROP-057 "Start time" added as a new
physical_property_definitions row - a standard PU foam reaction-profile
term with no existing controlled match, added as a clear sibling of the
already-controlled Cream/Gel/Rise/Tack-free time properties; (2) two
source orientation terms ("Rise direction Z", "Transverse direction X")
mapped onto the existing LOC-060/LOC-061 (parallel/perpendicular-to-rise)
controlled terms as the closest available proxy, while the exact source
wording is preserved verbatim in orientation_text on every affected row so
no information is lost if Charlie later decides a distinct controlled term
is warranted. PM-200/PM-300 (Charlie's own explicit governance assignments
from his 07_PI3_Control_Mapping sheet) and PROP-057 were seeded as real
controlled rows, not fabricated - Charlie's own workbook had already named
and assigned them.

Final regression/count verification against the real rigid_foam schema
confirmed zero collisions and zero regressions to any pre-existing data:
reference_formulations 10->18, reference_formulation_components 100->152,
raw_material_catalog_entries 151->166, source_registers 49->55,
production_methods 3->5, physical_property_definitions 56->57,
reference_formulation_families 0->2 - every delta exactly matches the
package's own scope (8/52/15/6/2/1/2 rows respectively), with the original
pre-existing rows in every one of those tables confirmed byte-for-byte
unchanged. Verified via py_compile and a live import of db.py with
SQLAlchemy's configure_mappers() (catches ORM relationship/FK errors
py_compile alone cannot) - one real bug caught this way and fixed before
release: ReferenceFormulationFamily's initial draft carried three stray
relationship lines copy-pasted from a different class (a duplicate
`source` relationship and two relationships referencing columns that
don't exist on this table, material_id/uom_id), which would have crashed
on first import; removed, leaving only the five relationships this table's
own columns actually support (chemistry, intended_production_method,
application, intended_construction, source).

No dedicated UI page surfaces reference_formulation_performance_results,
reference_formulation_processing_notes, or reference_formulation_families
yet - same schema-first/UI-later pattern as every prior wave; the existing
Reference Formulations viewing page (pages/29, built under WP6-S06/DEF-006)
continues to show only the ReferenceFormulation/ReferenceFormulationComponent
data it already knew about. Deferred, not silently dropped, per Stefan's
own sequencing: the "Production Method hierarchy" architecture change
(Plant -> Production Method -> Machine -> PU Materials) remains completely
untouched pending his separate explanation and scoping.
"""

VERSION_0_16_0_NOTES = """
v0.15.0 -> v0.16.0 (2026-08-09, Production Method Hierarchy architecture
change): implements Charlie's formal specification "PI3_Rigid_Foam_Edition_
Architecture_Change_Production_Method_Hierarchy_for_JC.docx" - the change
Stefan flagged as parked pending his own explanation and scoping (see
v0.15.0's notes) - now unblocked and delivered in this batch, per the
PDCA feedback-loop process the spec's section 14 required (impact
assessment + implementation design produced first, as
PI3_Rigid_Foam_Edition_Production_Method_Hierarchy_Impact_Assessment_and_
Design.docx, surfacing 5 open engineering decisions; Stefan resolved all
5 directly in chat before any schema/code was touched).

Locked hierarchy per the spec: Plant -> Production Method -> Machine -> PU
Material -> Raw Materials -> Recipes. Production Method becomes an
independent, plant-activatable application level between Plant and
Machine, with 4 new customer-facing top-level identities (PM-400
"Discontinuous factory-molded and press-foamed PUR/PIR", PM-410
"Continuous panel / lamination", PM-420 "Field pour-in-place cavity
filling", PM-430 "Spray-applied rigid polyurethane foam") - minted fresh in
a non-colliding numeric range per Stefan's decision, not repurposing the
existing PM-120/130/200/210/300 codes. PM-120/130 now nest under PM-400 and
PM-200/210 under PM-410 via a new self-referencing parent_method_id column
on production_methods; PM-300 remains its own separate top-level identity,
unchanged. Existing legacy codes retained verbatim for traceability -
zero rows renamed or reclassified.

Schema additions in db.py: ProductionMethod.parent_method_id (nullable
self-FK) + effective_top_level() model method (single place that resolves
"which top-level method does this row ultimately belong to" - wrapped by
helpers.effective_top_level_method() for page code); new
PlantProductionMethod join table (plant_id, production_method_id, active,
activated_at) implementing genuine per-plant Production Method activation,
not just an unconstrained tag; new foam_grade_machines plain association
Table implementing the many-to-many Machine<->PU Material relationship
Stefan confirmed (a PU Material may legitimately run on several machines;
Machine assignments must stay consistent with the plant's activated
Production Methods); new ProductionRun.production_method_id - a
deliberate, explicit exception to this codebase's usual "compute live,
never duplicate" discipline, snapshotting the run's Production Method
context at creation time per Charlie's historical-traceability
requirement, so a later Machine-master reclassification never silently
rewrites what a past run's records say it was produced under (editing a
run's own Machine, a genuine correction, does re-derive this snapshot -
see pages/4's Edit Run form).

Per Stefan's explicit resolution of the 5 open decisions: Product Family
stays exactly where it is, a Plant-level business/reporting grouping,
NOT part of the operational hierarchy - FoamGrade keeps its existing
ProductFamily link and separately gained the new Machine assignment;
cross-table consistency ("a Machine's method must be one of its plant's
activated methods") is enforced in page code (helpers.
activated_methods_for_plant / machines_for_plant_and_method), matching
this codebase's established app-layer-over-DB-constraint convention, not
a database CHECK; lab trials (CustomerTrial/OptimizationTrial) stay
outside this mandatory hierarchy for now - only ProductionRun carries the
full Plant->Method->Machine chain in this batch, Machine remains optional/
deferred for genuinely laboratory-based trial work.

UI changes, all following the established "narrowing pickers live outside
st.form" convention (OEM/Model on page 1, Family/Method/Machines on page
2): pages/1_Plant_Installation_Overview.py gained a "Production Methods
activated at this plant" checkbox section on the Edit Plant panel, and the
Add/Edit Machine forms now pick Plant -> Production Method (filtered to
that plant's activated methods) -> optional granular sub-classification ->
OEM -> Model, with a live breadcrumb caption and Save disabled until a
method is chosen; the Machines table gained a Production Method column;
Machine deletion now routes through cascades.unlink_machine_dependents
(clears foam_grade_machines links + unlinks dependent ProductionRuns).
pages/2_Product_Family_Foam_Grade.py's Add/Edit Foam Grade forms gained a
Production Method picker (filtered to the grade's plant) and a Machines
multiselect (filtered to machines already tagged with that method); the
Foam Grade table gained Production Method and Machines columns.
pages/4_Production_Run_Trial_Record.py's Add/Edit Run forms now filter the
Machine picker to the selected grade's own Machine assignment (not every
active machine at the plant), show a live Plant/Method/Machine breadcrumb,
and set/re-derive the production_method_id snapshot on save; CSV import
derives the same snapshot per imported row; the run overview table gained
a Production Method column. cascades.py: delete_foam_grade_cascade and
delete_plant_cascade now also clear foam_grade_machines rows;
plant_dependency_counts now reports activated Production Method counts.

Supabase migration applied directly against the real rigid_foam schema
(pm_hierarchy_schema): production_methods.parent_method_id column,
production_runs.production_method_id column, new plant_production_methods
and foam_grade_machines tables. Seeded PM-400/410/420/430 and set
parent_method_id on PM-120/130 (-> PM-400) and PM-200/210 (-> PM-410);
PM-300 left untouched. Backfilled the real pre-existing data with zero
data-loss/reclassification: the one real Machine (tagged PM-120, whose
effective top-level is PM-400) got its plant's PlantProductionMethod
activated against PM-400; all 5 existing FoamGrade rows got a
foam_grade_machines link to that Machine; all 13 existing ProductionRun
rows got production_method_id backfilled to PM-400 (derived from their
Machine's effective top-level method). Verified via count check: 9 total
production_methods (5 top-level), 1 plant activation, 5 foam-grade/machine
links, 13/13 runs carrying a method snapshot.

Tested via py_compile across db.py/helpers.py/cascades.py/pages 1, 2, 4;
a live import + SQLAlchemy configure_mappers() smoke test on db.py; the
full existing pytest suite (38 tests, all pre-existing behavior
unaffected); and a new tests/test_pm_hierarchy_pages_smoke.py (3 new
AppTest cases) covering the Add-record flows on pages 1, 2, and 4 - proving
the plant-activation filtering, method-filtered Machine multiselect, and
the Machine-derived production_method_id snapshot on run creation all
actually render/persist, not just that db.py imports cleanly. (The
Edit-record flows on all three pages are exercised manually instead of via
AppTest, since they're gated behind clickable_table's st.dataframe
row-click selection event, which AppTest's headless harness cannot
simulate - a testing-harness limitation documented in the new test file's
module docstring, not a defect in the pages.)

Not yet started in this batch (flagged in the original impact-assessment
doc as likely follow-up work, not confirmed in-scope for this pass): the
breadcrumb/Production-Method-filtering rollout to pages 5 (Quality Test
Result), 6 (Quality Issue), 9 (Samples & Conditioning), 11/12 (Customer/
Optimization Trials), 15-19 (Industrial Intelligence), 21 (Report); and any
schema/UI change letting CustomerTrial/OptimizationTrial optionally carry
Production Method context later (explicitly deferred per Stefan's decision
on lab trial scope).
"""

VERSION_0_16_1_NOTES = """
v0.16.0 -> v0.16.1 (2026-08-09, same day, production hotfix): v0.16.0
crashed every single page in production immediately after deploy
(InvalidRequestError from SQLAlchemy's mapper configuration, redacted by
Streamlit's on-screen error - Stefan supplied the real deploy log, which
had the actual traceback).

Root cause: db.py's new Machine.foam_grades / FoamGrade.machines
many-to-many relationships were written as `relationship(...,
secondary="foam_grade_machines")` - a bare string. Every local check
before release (py_compile, a live configure_mappers() smoke test, the
full pytest suite) ran against SQLite, where db.py's RIGID_FOAM_SCHEMA is
None and Base.metadata has no schema, so that table's key in
Base.metadata.tables is the plain "foam_grade_machines" - the string
resolved fine every time. Against the real Supabase Postgres server,
though, db.py sets Base.metadata's own `schema` to RIGID_FOAM_SCHEMA
("rigid_foam"), which changes that same table's key to
"rigid_foam.foam_grade_machines" - so the bare string secondary= no
longer resolves, and the very first ORM query of any request (SQLAlchemy
configures every mapper lazily, on first use, not at import time) raised
"expression 'foam_grade_machines' failed to locate a name". This gap
existed even though a dedicated Postgres schema-migration test already
existed (test_schema_migration.py, WP0 Gate 0) - that test proves raw
DDL/foreign-key correctness against a disposable Postgres schema, but
never calls SQLAlchemy's ORM configure_mappers() or runs an ORM query, so
it could not have caught a relationship string-resolution bug.

Fix: moved the foam_grade_machines Table definition (db.py) above the
Machine class (previously below FoamGrade), and changed both
relationships to pass the Table object directly - `secondary=
foam_grade_machines` - instead of a string. Passing the object sidesteps
name resolution entirely, so it's correct regardless of whether
Base.metadata has a schema set. No schema/data change - this is a code-
only fix; the Supabase migration and backfill from v0.16.0 stand as-is.

Added tests/test_orm_configure_under_schema_qualified_metadata.py: a
permanent regression test that imports db.py in a fresh subprocess with
DATABASE_URL set to a postgresql:// URL (no live connection needed -
SQLAlchemy's configure_mappers() only inspects metadata/relationships,
never issues SQL), so RIGID_FOAM_SCHEMA actually resolves to "rigid_foam"
and every relationship gets exercised under the same schema-qualified
metadata shape production uses - closing the exact gap that let this
bug ship. Full suite (42 tests total) passes.
"""

VERSION_0_16_2_NOTES = """
v0.16.1 -> v0.16.2 (2026-08-09, same day, Post-G5 PM Hierarchy closure -
Deliverable #6 walkthrough finding): a live Claude-in-Chrome walkthrough
of the real production app, done to capture Deliverable #6 screenshot/
walkthrough evidence, found that the Production Run page's Edit form
showed Machine as "not selected" and Production Method blank for a real
run (id=1) that Supabase correctly stores as machine_id=1/
production_method_id=6 - the exact same bug also affected the Add Run
form, meaning the one real Machine at the UAT plant could not be
selected in either form in production.

Root cause: pages/4_Production_Run_Trial_Record.py's new Machine-
narrowing filter (`assigned_machines = [m for m in grade.machines if
m.active]`, added in v0.16.0 for the Production Method Hierarchy change)
excludes any Machine whose `active` column is not exactly True. db.py
declares `Machine.active = Column(Boolean, default=True)`, but that
Python-side default only applies on ORM inserts; the one real Machine
row was inserted via raw SQL during earlier WP3 UAT seeding, so its
active column was NULL, not True - `if m.active` evaluates NULL as
falsy, silently dropping it from both dropdowns. The 3 AppTest smoke
tests added in v0.16.0 (Section 2.1 of Deliverable #5) didn't catch this
because synthetic test-seeded Machines always get active=True through
the ORM - the exact condition that triggers the bug (active IS NULL)
only existed on this one real, raw-SQL-seeded row, which no automated
test exercised.

This was more than a display bug: the Edit form's "Save changes" button
writes `selected_run.machine_id = machine.id if machine else None` and
the equivalent for production_method_id - so saving the Edit form with
the Machine field silently reset to unselected would have overwritten
run 1's correct values with NULL. Caught by inspection before any save
was made; no production data was actually corrupted.

Fix, both authorized by Stefan after being told what was found and why
a data-only fix required his sign-off (the auto-mode permission
classifier blocked JC's initial attempt at the SQL write pending
explicit authorization): (1) data - `UPDATE rigid_foam.machines SET
active = true WHERE id = 1`, backfilling the one real row to match the
model's documented default. (2) code - changed the filter at both sites
(lines ~395 and ~522) from `if m.active` to `if m.active is not False`,
so NULL/unset is treated as active (matching default=True) while an
explicit False still deactivates equipment; this prevents any future
raw-SQL-seeded or legacy Machine row from silently disappearing from
either form again, independent of the one-row data fix. Also removed
_cached_active_machines_for_plant(), a helper made dead code by the
same v0.16.0 batch (superseded by the grade.machines-based filter, never
called after that change landed).

Re-verified: full pytest suite (42 tests) passes unchanged; live browser
re-check of both the Edit and Add Run forms against the real Supabase
data pending in this same session. Deliverables #5 and #8 are being
revised to disclose this finding and its resolution rather than stand on
their original "Pass"/"no open defects" wording, consistent with this
project's practice of full disclosure (see v0.16.1's own hotfix note and
Deliverable #7's documented rollback-ordering mistake).
"""

VERSION_0_17_0_NOTES = """
v0.16.2 -> v0.17.0 (2026-08-10, flat Production Method redesign - completion
batch, per Charlie's standing batch instruction): replaces the short-lived
parent/child Production Method hierarchy (introduced v0.16.0-v0.16.2) with a
single flat level under Plant, using 7 permanent controlled codes: PM-100
Discontinuous Factory Foaming, PM-200 Continuous Panel & Board Production,
PM-300 Field Cavity Foaming, PM-400 Spray Foam Application, PM-500 Free-Rise
Rigid Block Production, PM-600 Pre-Insulated Pipe & Vessel Foaming, PM-700
Structural & Composite Rigid Foam Processing. Process variants remain
method-specific configuration/data beneath the relevant Production Method,
not a second controlled-vocabulary level - deliberately not implemented in
this batch (Phase 2 process functionality is not yet built; do not read
this release as delivering it).

Scope of this batch, on top of the flat-PM schema migration and pages
1/2/4 rework already landed in a prior same-day batch:

- Pages 5 (Physical Property Result), 6 (Quality Observation), 9 (Samples &
  Conditioning): inherit and display the parent Production Run's immutable
  Production Method snapshot via a new shared `helpers.production_method_label()`
  helper, distinguishing production-run-sourced records ("PM-100...") from
  lab-trial-sourced records ("N/A (lab trial)").
- Pages 15-19 (Industrial Intelligence): added a Production Method filter/
  isolation dimension. A new `analytics.production_methods_used()` helper
  and a `production_method_id` parameter threaded through
  `run_settings_dataframe`, `property_results_dataframe`,
  `merged_run_property_dataframe`, `rank_setting_correlations`,
  `rank_setting_optimization`, and `rank_component_actual_correlations` mean
  any grade or foam-family whose runs span more than one Production Method
  (possible because `foam_grade_machines` is many-to-many - one grade can
  run on machines under different methods) now shows a filter widget and
  isolates analytics/correlations to the selected method at the query level,
  not just on display. Page 18 (Root-Cause Assistant) has no user-facing
  filter by design - it auto-scopes the "most recent prior run" comparison
  to the flagged run's own Production Method, so it never compares across a
  method boundary. Page 15's rigid/WP3-conformance branch and the WP3
  Conformance Report's grade-level `production_method_id` (a distinct
  concept - the grade's own manufacturing classification, not a run's
  actual method - see reports.py) were deliberately left untouched.
- Page 21 (Report): Batch Release tab now shows the run's own Production
  Method snapshot; Period Summary tab gained a Production Method filter
  (shown only when the scoped runs span more than one method) plus a
  breakdown-by-method table; Sample Certificate's header fields now include
  Production Method for all three source types (run / customer trial /
  optimization trial).
- Added `tests/test_flat_pm_propagation_smoke.py` (7 new tests, a
  `two_method_fixture` pytest fixture) covering inheritance, filtering, and
  analytics/report isolation end to end. Full suite: 49 passed.
- Built a real two-method validation fixture directly in the UAT/reference
  environment (Supabase project aazkdsqpytjciiqtvnfj, schema rigid_foam,
  plant_id=2), per Charlie's instruction to use that environment rather than
  a separate branch (none exists) and to create only the minimum controlled
  fixture data needed to prove hierarchy, inheritance, filtering, and
  analytics/report isolation: activated PM-200 for plant_id=2 (PM-100 was
  already active) and extended the existing foam_grade_id=2 - which already
  had 13 production runs under PM-100 - with one new Machine, one new
  ProductionRun (id=14), Sample, PhysicalPropertyResult, and
  QualityObservation under PM-200. Verified by direct SQL query that this
  left every existing PM-100 row (machine id=1, all 13 runs, run 1's sample
  and property result) unchanged, and that no other plant was touched.
- Live two-method walkthrough of pages 5, 6, 9, 15-19, and 21 against this
  real fixture (via live Supabase queries plus source-level tracing, since
  the session's only Supabase credential is a restricted read-only role
  that cannot drive AppTest against Postgres): all pages correctly
  distinguish PM-100 vs PM-200 for this grade's two production runs. No
  defects found.

Deliverables #5, #6, and #8 are being revised to reflect this batch;
Deliverable #7 is unchanged (no deployment or rollback behavior changed).
Phase 2 process-functionality integration follows after Charlie's technical
acceptance of this package and Stefan's Post-G5 closeout approval.

v0.17.0 -> v0.18.0 (2026-08-10, Architecture Correction - FoamGrade.
production_method_id): Charlie's final Post-G5 closeout review identified a
competing-source-of-truth problem: FoamGrade carried its own single
production_method_id FK (added during WP3, before Machine <-> FoamGrade
became many-to-many) alongside the fact that a grade's real Production
Method(s) are now knowable from its assigned Machines (foam_grade_machines),
per the stated Plant -> Production Method -> Production Unit -> Product Grade
hierarchy and ProductionRun's own immutable snapshot. Charlie required one of
three resolutions - non-authoritative purpose, derive, or deprecate - before
CR-01/02/03 could proceed.

Decision: deprecate. There is no remaining use case for a single grade-level
method classification once a grade's actual methods are derivable directly
from grade.machines, and inventing a new distinct meaning for the column
would only add an unneeded second concept. The column stays in the schema
(nullable, no migration forced, read-compatible with historical data) but
nothing writes to it going forward and nothing should read it as
authoritative.

- Added helpers.grade_production_methods(grade) / grade_production_method_
  label(grade) - derives the distinct set of ProductionMethod rows from
  grade.machines, replacing the deprecated field as the source of truth.
- Added helpers.machines_for_plant_across_activated_methods(session,
  plant_id) - every Machine at a plant across all of the plant's activated
  methods, not pre-filtered to one method.
- pages/2_Product_Family_Foam_Grade.py: Add/Edit Foam Grade forms no longer
  gate the machine multiselect behind a single "Production Method *"
  selectbox; both now offer every activated-method machine up front, each
  labeled with its own method. This also fixes a real, currently-shipping
  defect the old design caused: the Edit form's Save button replaced
  (grade.machines = list(selection)) rather than merged the grade's machine
  set after re-filtering to one freshly-chosen method, so any machine
  belonging to a different, previously-assigned method would be silently
  dropped on save - a defect that had not yet struck real data (the
  two-method UAT fixture was built via direct SQL, not this form) but would
  have triggered on the first Edit-and-Save of a cross-method grade. The
  grade list's "Production Method" column now shows the derived,
  comma-joined label instead of the deprecated field.
- reports.py's build_wp3_conformance_report_data() now reads
  run.production_method.name (the specific run's own immutable snapshot)
  instead of grade.production_method.name, removing the one place a stale
  grade-level value could show the wrong method for a given run.
- db.py: FoamGrade.production_method_id and its relationship are documented
  as deprecated in place; column and relationship not removed/renamed.
- Full codebase sweep confirmed only these two call sites ever read/wrote the
  field as authoritative - no Supabase view, analytics.py function,
  cascades.py rule, or demo_data.py seeding referenced it - so the fix's
  blast radius is fully contained.
- Added two regression tests to tests/test_flat_pm_propagation_smoke.py
  (test_grade_production_methods_derives_from_machines_not_deprecated_field,
  test_wp3_conformance_report_uses_runs_own_snapshot_not_grades_stale_field),
  both run against the existing two_method_fixture (whose grade's
  production_method_id already disagrees with its real multi-method machine
  assignment - a ready-made regression bed). Updated
  tests/test_pm_hierarchy_pages_smoke.py's Add-Foam-Grade-form test
  (renamed test_foam_grade_form_offers_machines_across_activated_methods) to
  assert the new expected behavior. Full suite: 51 passed, 0 failed (up from
  49), 4 pre-existing benign warnings.
- Documented in PI3_Rigid_Foam_Edition_Architecture_Correction_FoamGrade_
  Production_Method.docx (Development Docs/Phase 1), per Charlie's
  instruction to choose and document the clean engineering solution.

This was a precondition Charlie set for final Post-G5 closeout of the flat
Production Method redesign. No browser walkthrough performed for this fix,
per Charlie's explicit instruction to defer the next walkthrough until CR-01,
CR-02, and CR-03 are all complete. CR-01 (UI navigation and rigid-foam
terminology alignment) proceeds next, per Charlie's specified sequence.
"""

CHANGELOG_v0_18_0_TO_v0_19_0 = """
v0.18.0 -> v0.19.0 (2026-08-10, CR-01 - UI Navigation and Rigid-Foam
Terminology Alignment)

Implements CR-01 of the three pre-approved Change Requests Charlie specified
must land strictly in sequence (CR-01 -> CR-02 -> CR-03 -> Stefan UAT), with
NO browser walkthrough performed for this CR individually - per Charlie's
explicit instruction, only one consolidated walkthrough happens, after CR-03,
before Stefan's UAT (task #740). Backend entity/column/model names were
deliberately preserved everywhere a rename would add migration risk with no
customer-visible value - every change below is a display-text/label rename
only unless stated otherwise.

1. Navigation / page-split (target sidebar structure):
- Split the old combined "Plant & Foam Equipment Overview" page into three:
  pages/1_Plant_Installation_Overview.py (Plants - pure identity/location,
  Machine/equipment UI and Production Method activation checkboxes removed),
  pages/30_Production_Methods.py (NEW - plant-activated methods with
  Production Units/Product Grades/Recipes counts, plus a new session-level
  "operating context" concept - st.session_state["pm_context_plant_id"]/
  ["pm_context_method_id"] - settable here and read as a soft default,
  never a hard gate, by Production Equipment's pickers),
  pages/31_Production_Equipment.py (Machine CRUD moved here verbatim from
  the old page 1, all user-visible labels renamed "Machine / foaming line"
  -> "Production Unit or Cell").
- access_control.py: added a new "production_methods" page_key for the new
  Production Methods page. Production Equipment intentionally reuses the
  existing "plant_overview" page_key (same CRUD/permission surface as
  before the split) - avoids a RolePagePermission migration for existing
  companies/roles. PAGE_CATALOG titles updated to match the table below.
- app_rigid_foam.py: nav sections rebuilt to the approved order - Overview,
  Plant Setup, Production Methods, Formulations, Production, Samples &
  Trials, Quality, Industrial Intelligence, Company Admin, Application
  Admin. Formulations (Raw Materials/Recipes/Reference Formulations) split
  out of the old combined Setup section.

2. Mandatory terminology rename table (label-only, backend unchanged):
   Foam Grade -> Product Grade | Machine (in the equipment-add UI) ->
   Production Unit or Cell | Quality Test Result -> Test Results |
   Quality Issue -> Quality Issues | Setup (Production Run tab) -> Planned
   Settings | Runtime Data -> Actual Run and Cycle Data | Component Stream
   Readings -> Material Metering and Actual Usage | Fall-plate positions ->
   Tool Geometry and Fill Configuration | Meters produced -> Output
   Quantity and Unit | Sample zone -> Sample Location Reference | Machine
   Settings vs Physical Properties (Correlation) -> Process Parameters vs
   Product Properties (Correlation) | Machine Settings Optimization ->
   Process Parameter Optimization.
- Applied across pages/1, 2, 3, 4, 5, 6, 9, 11, 12, 15-21, 27, 30, 31,
  reports.py, analytics.py, helpers.py, cascades.py, demo_data.py, and
  app_rigid_foam.py: page titles, tab labels, form/field labels, table
  column headers, chart titles, report titles (both the on-screen
  st.subheader and the exported Word doc/PDF title block), and Add/Delete
  confirmation copy. "Foam Grade"/"foam grade" (all case variants) was
  swept app-wide via a scoped, verified find/replace limited to the exact
  two-word phrase, which cannot collide with the FoamGrade class name or
  foam_grade_id/grade_name columns (no space) - confirmed zero remaining
  hits via grep afterward and a full test-suite rerun (unchanged pass
  count) to catch any accidental producer/consumer mismatch in report
  column-key strings.
- Known deferred scope (disclosed, not silently dropped): the mandatory
  table's "Machine -> Production Unit or Cell" rename was completed only
  on pages/31 (the equipment Add/Edit form itself, the highest-visibility
  surface). The word "Machine" still appears as a plain UI label/column
  header/chart-category string in a number of other places app-wide
  (breadcrumbs, table headers, dropdown labels) where a blind find/replace
  was judged unsafe (the same word is also the backend model name, and is
  used legitimately in unrelated phrases like "Machine Data" imports and
  MachineModel/MachineCategory). Completing that rename requires a
  dedicated per-site pass and is tracked as follow-up work before CR-01 is
  considered fully closed against the letter of the mandatory table -
  flagged to Charlie/Stefan rather than claimed as done.

3. Tests: tests/test_pm_hierarchy_pages_smoke.py updated for the page
   split (new PAGE30/PAGE31 constants; test_plants_page_has_no_equipment_ui
   and test_production_methods_page_shows_activated_method_and_counts
   added; test_add_machine_form_offers_plants_activated_method retargeted
   from PAGE1 to PAGE31). Full suite re-run after every edit batch in this
   changelog entry: 53 passed, 0 failed throughout (unchanged from pre-CR-01
   baseline), 4 pre-existing benign numpy RuntimeWarnings.

4. Deviation from CR-01's own evidence-package template: CR-01's document
   calls for "JC completes a live UI walkthrough" as part of its own
   closeout evidence. Per Charlie's overriding instruction for this batch
   ("do not perform another browser walkthrough now... after CR-01, CR-02,
   CR-03 are complete, perform ONE consolidated browser-level walkthrough"),
   that walkthrough is deliberately deferred to task #740, after CR-03.
   CR-02 (Overview dashboard Production Method alignment) proceeds next,
   per Charlie's specified sequence.
"""

CHANGELOG_v0_19_0_TO_v0_20_0 = """
v0.19.0 -> v0.20.0 (2026-08-10, CR-02 - Overview Dashboard Production Method
Alignment)

Implements CR-02 of Charlie's three pre-approved, strictly-sequenced Change
Requests (CR-01 -> CR-02 -> CR-03 -> Stefan UAT). Per Charlie's overriding
instruction, NO browser walkthrough was performed for this CR individually -
only one consolidated walkthrough happens, after CR-03, before Stefan's UAT
(task #740). CR-02's own source document independently calls for JC to
perform a live Overview walkthrough with at least two activated Production
Methods as part of its acceptance evidence; that requirement is deliberately
deferred to task #740, same disclosed deviation pattern as CR-01's closeout.

1. Filter cascade rebuilt (app_rigid_foam.py, render_overview()): the old
   flat Plant/Foam Family/Foam Grade/date-range filter row is replaced with
   the approved hierarchy - Plant -> Production Method -> Production Unit /
   Cell -> Product Grade -> Date range. Product Family is demoted to an
   "Advanced filter (optional)" expander above the main row: it narrows the
   Product Grade dropdown but never scopes any KPI on its own, per CR-02's
   explicit rule that Family is a commercial classification, not a
   production-scoping dimension.
   - Production Method options are the plant's own activated methods
     (helpers.activated_methods_for_plant) once a Plant is selected, or
     every controlled-vocabulary method (helpers.all_production_methods)
     when no Plant is selected yet.
   - Production Unit / Cell and Product Grade both narrow cumulatively as
     Plant/Method/Family are set, reusing the existing
     machines_for_plant_and_method/machines_for_plant_across_activated_
     methods helpers rather than duplicating that logic.
   - Design correction made before this ever ran (caught during planning,
     not in testing): the first-draft cascade used an exclusive
     machine -> method -> plant elif chain for narrowing Production Unit/
     Product Grade options. Since ProductionMethod is a shared,
     plant-agnostic controlled-vocabulary row (no plant_id column of its
     own), that chain would have let a Method-only selection (no Plant
     selected) leak in machines/grades belonging to an entirely different
     plant that happens to activate the same method. Fixed by applying the
     Plant filter unconditionally first whenever set, then layering
     Method/Unit narrowing on top as additional cumulative filters, never
     as a substitute for the Plant filter. Pinned by a dedicated regression
     test (see Tests below) so this can't silently regress.

2. KPI redesign, three sections (Volume / Quality & Performance / Trials &
   Samples), all driven off the same scoped ProductionRun query
   (ProductionRun.production_method_id - the run's own immutable snapshot,
   set once at creation - is the direct scoping column; no joins needed):
   - Volume: Recipes, Production runs, Active product grades, and a new
     gated "Output Quantity and Unit" KPI (replaces the old flat "Meters/kg
     produced" figures CR-02 explicitly calls out for removal, since that
     computation - analytics.compute_runtime_output(), a continuous/tunnel-
     specific conveyor-speed x duration x width x height x density formula -
     does not generalize to all 7 Production Methods and would be
     meaningless summed across methods with incompatible units).
     Deliberate design choice: rather than build a full per-method
     output-computation framework (a much larger undertaking, out of CR-02's
     stated scope), the existing tunnel-style calculation is reused but
     strictly gated - it only ever displays when exactly one Production
     Method is selected AND a complete date range is picked AND that
     method's runs in range actually produced computable length data;
     otherwise an explanatory caption is shown instead of a blank, zero, or
     (worse) a wrongly-summed mixed-unit number. This satisfies CR-02's
     explicit "never show a meaningless mixed-unit total" rule without
     inventing new per-method schema.
   - Quality & Performance: Quality tests, Quality issues, Recurring
     quality issues, Quality test pass rate - all computed from the same
     scoped run-id set (plus lab-trial records, see below), matching CR-02's
     "cross-method comparable" vs. "method-specific" aggregation-class
     rules (these four are cross-method comparable and may show under "All
     Production Methods"; they correctly isolate to one method's own runs
     when a single Method is selected).
   - Trials & Samples: Samples, Customer trials, Optimization trials, Open
     customer/optimization trials.
   - Lab trials (CustomerTrial/OptimizationTrial) have no Production
     Method/Unit attribution in the schema at all (scoped only by
     plant_id/foam_grade_id). Design decision: trial-count cards (Customer
     trials, Optimization trials, Open trials) always scope by plant+grade
     only, unaffected by the Method/Unit filters; but trial-sourced
     Quality-test/issue/Sample records are folded into the cross-source
     Quality & Performance / Samples totals ONLY when no specific Method or
     Unit is selected (include_trials = method_filter is None and
     machine_filter is None) - narrowing to a specific Production Method
     or Unit necessarily excludes method-agnostic lab data from that
     narrowed total, since attributing it to one specific method would be
     a fabrication the schema doesn't support.
   - Header caption and Function/Action intro text rewritten to CR-02
     Section 5's exact approved wording (mentions Production Method/Unit
     explicitly as scoping dimensions).

2. Removed the redundant "kg produced" figure entirely (CR-02's own
   rationale: it was a second, less-used unit for the same underlying
   tunnel-output computation as "Output Quantity and Unit," not
   independent information) rather than gating two parallel KPIs behind
   the same eligibility check.

3. Tests: new tests/test_cr02_overview_pm_alignment.py (6 targeted cases,
   per CR-02 Section 9.4's explicit call for "targeted automated tests for
   Production Method filter cascading and cross-method KPI isolation") -
   Plant selection narrows Method then Unit then Grade; switching Method
   swaps Unit/Grade option sets; KPIs isolate to a single Method's own run
   (quality issues/samples correctly read 0 when seeded only on the OTHER
   method's run, not leaked); KPIs correctly combine across both methods
   under "All Production Methods"; and two dedicated cross-plant-leak
   regression tests pinning the design correction in item 1 above (a
   Method-only selection with no Plant set must never surface another
   plant's machines; Plant's own activated-method scoping must never be
   bypassable via the Method dropdown). All 6 pass. Full existing suite
   re-run after the rewrite: 59 passed (53 pre-existing + 6 new), 0 failed,
   same 2 pre-existing benign numpy RuntimeWarnings as before this batch -
   zero regressions from the render_overview() rewrite.

4. Deviation from CR-02's own evidence-package template (same disclosed
   pattern as CR-01): CR-02's document calls for "JC performs a live
   Overview walkthrough with at least two activated Production Methods" as
   part of its own closeout evidence. Per Charlie's standing instruction for
   this whole batch, that walkthrough is deliberately deferred to task #740,
   the single consolidated walkthrough after CR-03 and before Stefan's UAT.
   CR-03 (Recipe consolidation and Pending Review status) proceeds next,
   per Charlie's specified sequence.
"""

CHANGELOG_v0_20_0_TO_v0_21_0 = """
v0.20.0 -> v0.21.0 (2026-08-10, CR-03 - Recipe Consolidation and Pending
Review Status)

Implements CR-03, the last of Charlie's three pre-approved, strictly-
sequenced Change Requests (CR-01 -> CR-02 -> CR-03 -> Stefan UAT). Per
Charlie's overriding instruction, NO browser walkthrough was performed for
this CR individually - only one consolidated walkthrough happens now, task
#740, before Stefan's UAT. CR-03's own source document independently calls
for "JC completes a live walkthrough of Recipes, one Pending Review recipe,
approval-status filtering, and one production recipe selection path" as
acceptance evidence; that requirement is deliberately deferred to task #740,
same disclosed-deviation pattern as CR-01 and CR-02's closeouts.

1. Reference Formulations page removed entirely (CR-03 target navigation):
   pages/29_Reference_Formulations.py deleted from disk; its nav
   registration and "reference_formulations" access_control.PAGE_CATALOG
   entry removed. Any pre-existing RolePagePermission rows keyed to that
   page_key become inert (no code checks that key anymore) - left in place
   rather than deleted, since a stray permission row with no matching page
   has no effect and deleting live role data for zero functional gain is
   unnecessary risk.

2. Imported scientific formulations consolidated into the Recipes page
   (pages/3_Recipe_Version_Record.py): a new "Approval Status" filter
   (db.APPROVAL_STATUSES vocabulary, includes "Pending Review") sits above
   the existing "Recipe versions" list, which now shows real RecipeVersion
   rows AND every ReferenceFormulation row combined into one list at the
   application layer (per CR-03 rule 6's explicit permission to keep them
   in separate backend tables and combine only for display). Clicking a
   reference-formulation row shows its full reported parameters, ingredient
   lines and source/provenance (content carried over from the removed
   page), plus a "Change Approval Status" control gated behind the same
   page_usable permission check real recipe edits already use.
   - Scope deliberately broadened beyond CR-03's own literal "eight
     formulations, 52 components" wording: that count only covers RFREF-*
     (the Post-G5 exact scientific reference recipes). The 10 RF-* patent/
     literature rows from the earlier WP5 reconciliation batch lived on the
     SAME now-removed page and are exact formulations in exactly the sense
     CR-03 contrasts against "research formulation families" (RFFAM-*, the
     only category CR-03 explicitly excludes) - leaving them off this list
     would have silently orphaned 10 rows / 100 component lines with no UI
     surface anywhere in the app. All 18 rows (10 RF-* + 8 RFREF-*) are
     included; the 2 RFFAM-* research families are not, unchanged. Flagged
     here explicitly as a scope broadening, not a silent overreach.
   - Never migrated into real RecipeVersion rows: ReferenceFormulation has
     no foam_grade_id/company_id (a shared, plant-agnostic public library,
     structurally incompatible with RecipeVersion's per-grade, per-tenant
     model). No new duplicate Recipe records were created - CR-03's "avoid
     duplicate Recipe records during consolidation" and "no code path links
     a ReferenceFormulation row to RecipeVersion.is_active" (CR-03 rule 3,
     "must not become selectable for production use through an approval
     bypass") are both satisfied structurally, with zero new guard code:
     the only real link between the two tables remains the pre-existing,
     user-set RecipeVersion.reference_formulation_id "informed by" FK.

3. Schema: added ReferenceFormulation.approval_status (String(50),
   nullable) - a real, mutable Approval Status using the exact same
   controlled vocabulary as RecipeVersion.approval_status, so a Pending
   Review -> Approved transition goes through the identical mechanism (a
   controlled selectbox + commit) real recipes already use, satisfying
   CR-03 rule 4's "must use the normal controlled approval mechanism and
   retain auditability" with the same auditability level RecipeVersion
   itself has (neither model has a dedicated approved_by/approved_at
   column in this app - parity, not a lesser bar). Applied to Supabase via
   the cr03_reference_formulation_approval_status migration; backfilled to
   "Pending Review" for all 18 pre-existing rows. ReferenceFormulationFamily
   (RFFAM-*) deliberately untouched - no approval_status column, no
   appearance anywhere in the Recipes flow, per CR-03 rule 7.

4. Data reconciliation (before/after counts, per CR-03 section 6 and UAT
   acceptance criterion 8): reference_formulations 18 -> 18 (0 rows added/
   removed - only the new nullable column populated), reference_formulation_
   components 152 -> 152, reference_formulation_families 2 -> 2,
   reference_formulation_performance_results 53 -> 53, reference_formulation_
   processing_notes 40 -> 40, recipe_versions 5 -> 5, recipe_components
   52 -> 52. Verified directly against the real Supabase rigid_foam schema
   before and after the migration - a pure additive schema change, no
   existing row touched except the new column's own value.

5. Tests: new tests/test_cr03_recipe_consolidation.py (9 cases) - nav/
   PAGE_CATALOG no longer references reference_formulations, the page file
   is gone from disk, new ReferenceFormulation rows default to a None
   approval_status that the app treats as Pending Review, Reference
   FormulationFamily has no approval_status column at all, an approval
   transition persists across sessions, ReferenceFormulation has no
   foam_grade_id/is_active columns (the structural guarantee behind rule 3),
   approving a reference formulation never touches an unrelated grade's
   active RecipeVersion, and the Recipes page renders the combined list and
   its Approval Status filter without exception (including filtered to
   Pending Review only). All 9 pass. Full existing suite re-run after the
   rewrite: 68 passed (59 pre-existing + 9 new), 0 failed, same 2
   pre-existing benign numpy RuntimeWarnings as before this batch - zero
   regressions.

6. This closes the CR-01 -> CR-02 -> CR-03 sequence Charlie specified.
   Per his standing instruction, the single consolidated browser-level
   walkthrough (task #740) is next, immediately before Stefan begins UAT -
   covering all three CRs' own individually-deferred walkthrough
   requirements in one pass rather than three separate ones.
"""

VERSION_0_22_0_NOTES = """
v0.21.0 -> v0.22.0 (2026-08-10, CR-04 prep - "Database Reset and Clean UAT
Baseline for JC", Charlie's instruction following Stefan's decision to
abandon careful per-item migration in favour of a clean rebuild since all
current rigid_foam data is test data): this batch covers steps 2-3 of
Charlie's own 8-step sequence (Plan/Snapshot/Rebuild) at the schema level;
the data-level RESET (wiping transactional/UAT rows) and steps 5-8
(Import/Apply CR-04/Validate/Close) are tracked separately and not yet
executed as of this version.

1. Snapshot (step 2): full row_to_json() dump of every populated table in
   the live rigid_foam schema (68 tables, source commit + app version +
   timestamp recorded in a manifest), taken via the Supabase MCP
   execute_sql tool (no pg_dump/psql access in this sandbox - confirmed no
   outbound network access beyond allowlisted MCP tools). Zipped and
   archived at PI3 Rigid Foam Development Docs/Phase 1/Snapshots/
   PI3_Rigid_Foam_PreReset_Snapshot_2026-08-10_1512.zip - the historical-
   value archive for anything the clean rebuild removes outright (see
   FoamGrade.production_method_id below).

2. Schema (step 3, part 1) - PM release gating: added ProductionMethod.
   maturity_status (String(50)) and is_released (Boolean, default False,
   not nullable), per Charlie's 7-code maturity/release table. Backfilled
   directly against Supabase: PM-100 -> Released/is_released=true (the
   only method activatable via the customer UI at Phase 1); PM-200/300/400
   -> Defined / planned/is_released=false; PM-500/600/700 -> Placeholder/
   is_released=false. Verified afterward by direct query - all 7 rows
   correct. The actual UI enforcement of is_released in the Production
   Method activation checkbox loop (pages/30_Production_Methods.py), with
   a platform-owner exemption for the owner's own UAT/reference
   activation, is CR-04's own step 6 ("Apply CR-04") - schema only in this
   batch, gating code not yet written.

3. Schema (step 3, part 2) - FoamGrade.production_method_id fully removed:
   per Charlie's explicit instruction ("omit from the clean schema
   entirely, not just null it out"), dropped the column, its FK
   constraint (fk_foam_grades_production_method_id), and the model
   relationship from db.py outright - not deprecated-in-place as the
   PM-hierarchy-reconciliation batch (task #736) had left it. A foam
   grade's applicable methods are now derived solely from its assigned
   Production Units/Machines (Production Unit <-> Product Grade many-to-
   many), per Charlie's explicit resolution of the ambiguity JC's own PM
   reconciliation audit had flagged. Applied to Supabase as migration
   cr04_pm_release_status_and_drop_foamgrade_pm_id (single migration
   covering both the PM fields and this drop) - verified afterward that
   foam_grades has no production_method_id column.

4. Test fixtures: removing a live model column broke every fixture that
   still constructed db.FoamGrade(..., production_method_id=...) - a
   TypeError, not a silent bug, since SQLAlchemy rejects unknown
   constructor kwargs outright. First grep pass (single-line regex) missed
   4 of 7 occurrences because this codebase commonly splits constructor
   calls across multiple lines; a multiline-mode regex found the complete
   set. Fixed in tests/test_flat_pm_propagation_smoke.py, tests/
   test_pm_hierarchy_pages_smoke.py, tests/test_wp4_recipe_optimization_
   page_smoke.py, tests/test_wp4_rigid_achievement_summary.py, tests/
   test_wp4_rigid_lot_use_correlation.py, tests/test_wp4_unit_conversion.py,
   and gen_uat015_019_live_pages.py (a standalone UAT-evidence-generation
   script, not part of the live app) - each simply drops the removed
   kwarg, since none of these fixtures' assertions depended on the
   deprecated field's value (the PM-hierarchy batch had already moved
   every downstream read onto grade.machines-derived methods). Full local
   suite (SQLite): 68 passed, 0 failed - same 2 pre-existing benign numpy
   RuntimeWarnings as every prior batch, zero regressions.

5. Not yet done, tracked as separate follow-on work: the actual RESET
   (deleting rows from the classified transactional/UAT tables - plants,
   foam_grades, machines, production_runs and their full dependency
   chains, raw_materials, logs, etc. - while preserving controlled master/
   reference vocabulary and platform bootstrap/tenant-identity tables);
   CR-04's own step 6 (removing the Operating Context UI feature entirely
   from pages/30 and /31, and wiring is_released into the PM activation
   checkbox loop); step 7 (full validation - regression, integrity,
   multi-method fixture, consolidated browser walkthrough); and step 8
   (closeout package to Charlie, then Stefan's final UAT/release
   decision). Executed under Stefan's explicit "Go ahead" authorization
   for this reset/rebuild approach, given after reviewing Charlie's full
   written instruction.
"""

VERSION_0_23_0_NOTES = """
v0.22.0 -> v0.23.0 (2026-08-10, CR-04 completion - "Database Reset and
Clean UAT Baseline for JC", Charlie's instruction): closes out the
remaining CR-04 steps flagged as not-yet-done in v0.22.0's own changelog
entry - the data RESET, Step 5 Import, and Step 6 (Apply CR-04) are all
done as of this version. Steps 7 (Validate) and 8 (Close) remain.

1. RESET (data): per Stefan's explicit "Go ahead," executed the actual
   wipe against the live Supabase rigid_foam schema - DELETE (in
   FK-dependency-safe child-before-parent order, verified against the
   full cross-table FK graph before running) against 56 transactional/
   UAT tables: plants, foam_grades and their machines/specs/target-
   properties, the full production-unit/machine/tooling hierarchy
   (production_units, machines, mixheads, tools, cavities, fill_points,
   vent_configurations, calibration_records, and every machine-linked
   table), plant_production_methods, recipe_versions/components,
   production_runs and their full cycle/shot/output/phase/event chain,
   samples, physical_property_results, quality_observations, customer_
   trials, optimization_trials, controlled_failure_cases, raw_materials/
   lots/lot_uses/documents/qualifications/attribute_values, suppliers,
   expert_notes, the PI3 connection/interaction/feedback tables, and every
   audit/activity log (login/page_view/page_load/performance/role_change/
   export/error). Verified afterward via pg_stat_user_tables: all 56 at
   zero rows. Explicitly NOT touched, verified unchanged: platform
   bootstrap/tenant-identity (companies=1, users=1, roles=6) and every
   controlled master/reference vocabulary table (production_methods=7,
   chemistries=2, machine_models=64, reference_formulations=18,
   quality_issue_types=64, raw_material_catalog_entries=166, and the
   full location/condition/property/method/UOM taxonomies) - these are
   validated content from many prior QA passes in this project, not test
   data, and Charlie's instruction targets the PM-era interim decisions
   and their downstream synthetic data, not this layer. The pre-reset
   snapshot taken in v0.22.0's batch is the historical-value archive for
   anything this step removed.

2. Step 5 (Import) - reclassified per Stefan's explicit direction:
   Charlie's original instruction gated this step on Charlie/Stefan first
   producing Rigid-Foam-aligned Implementation Spreadsheets. Stefan
   overrode that framing directly ("Step 5 should not depend on the
   spreadsheet, that is nonsense. Unblock it") - the minimum Phase 1 UAT
   baseline doesn't need a spreadsheet-import mechanism; it can be built
   directly from controlled master data this project already has and
   trusts, the same way every prior WP3/WP5 UAT seeding batch in this
   project was done. Seeded directly against Supabase: 1 plant (HTC
   Global - Phase 1 Plant) with PM-100 activated, 1 production unit + 1
   machine (a real Hennecke PANELFOAMER pulled from the controlled
   machine_models catalog), 1 product family + 1 foam grade (RF-COLDROOM-
   001) assigned to that machine, 5 real raw materials pulled from the
   166-row raw_material_catalog_entries catalog (BASF Lupranol 3300/
   Lupranate M20, Evonik POLYCAT 5/DABCO DC 193, cyclopentane) inserted
   into plant-scoped raw_materials, 1 recipe version (Pending Review -
   fresh and unvalidated, not Approved) with its 5 components, 1 grade
   specification (thermal conductivity <= 0.024 W/(m.K), reusing the
   preserved controlled property/method/condition/orientation/location
   vocabulary), and 1 production run -> sample -> physical property
   result (0.0231, a pass) to prove the rebuilt architecture end-to-end.
   No new architecture decisions - pure data population within already-
   controlled vocabulary, verified afterward by re-querying every table
   in the chain and confirming every FK resolves correctly.

3. Step 6 (Apply CR-04) - Operating Context removal: per Charlie's
   explicit instruction ("remove the global Operating Context concept
   from the application entirely - not just never persisted, the feature
   itself must be removed"), stripped every trace of the session-level
   soft default from pages/30_Production_Methods.py (the "Set as
   operating context"/"Clear operating context" buttons, the
   st.session_state["pm_context_plant_id"]/["pm_context_method_id"]
   reads/writes, the "Operating context [check]" success indicator, and
   the bottom current-context info box) and pages/31_Production_
   Equipment.py (its Plant/Production Method picker defaults that used to
   read this same session state). Every picker now defaults plainly
   (first item in the list) with zero cross-page session state. This
   resolves the ambiguity JC's own PM reconciliation audit had flagged,
   decisively in favour of full removal, per Charlie's own instruction.

4. Step 6 (Apply CR-04) - PM release gating enforced in the UI: added
   helpers.method_activatable_by_customer(method, is_platform_owner) - a
   pure function (bool(is_platform_owner or method.is_released)) wiring
   the is_released schema field (added in v0.22.0) into an actual UI
   gate for the first time. pages/30_Production_Methods.py's activation
   checkbox loop now disables (with an explanatory caption) any method a
   customer/company user isn't allowed to activate - only PM-100 at the
   Phase 1 baseline - while the platform-owner company (Company.
   is_platform_owner, e.g. HTC Global) stays exempt, since it still needs
   to activate any method for its own UAT/reference content ahead of a
   future release decision. The activate/reactivate branches are guarded
   by this same check; deactivating an already-active method is never
   blocked (handles any pre-existing activation from before this gate
   existed).

5. Tests: new tests/test_cr04_pm_release_gating.py (4 cases) - the pure
   helper function's both branches (released method activatable by
   anyone; unreleased method blocked for a customer but not a platform
   owner), plus two AppTest-based page tests using a dedicated non-
   platform-owner fixture (deliberately NOT the shared seeded_pm_
   hierarchy fixture, which is platform-owner by convention) proving the
   released method's checkbox is enabled and the unreleased method's is
   disabled-with-caption for a real customer, and that the platform-owner
   exemption re-enables it. Updated tests/test_pm_hierarchy_pages_smoke.py's
   test_production_methods_page_shows_activated_method_and_counts to
   assert the "Set as operating context" button is now ABSENT (inverted
   from its prior assertion that it existed), per the removal above. Full
   suite: 72 passed (68 prior + 4 new), 0 failed, same 2 pre-existing
   benign numpy RuntimeWarnings as every prior batch - zero regressions.

6. Remaining CR-04 steps, tracked separately: Step 7 (Validate - full
   regression already covered above, still need schema/data integrity
   checks against the reset+reseeded Supabase database, a multi-method
   engineering fixture, and the consolidated live browser walkthrough)
   and Step 8 (Close - closeout package to Charlie, then Stefan's final
   UAT/release decision).
"""

VERSION_0_24_0_NOTES = """
2026-08-10 (later same day, CR-04 Step 7 - Validate, completing Charlie's
"Database Reset and Clean UAT Baseline" instruction's own execution
sequence): closed out every remaining Step 7 sub-requirement -
"regression + integrity + multi-method fixture + consolidated browser
walkthrough".

1. Consolidated browser walkthrough (engineering stand-in): new
   tests/test_cr04_step7_consolidated_walkthrough.py - an AppTest-based
   sweep across all 11 pages a user actually touches for the minimum
   Phase 1 baseline (Overview, Plants, Production Methods, Production
   Equipment, Product Family & Foam Grade, Recipes, Production Run, Raw
   Materials, Samples & Conditioning, Quality Test Result, Report),
   seeded with a fixture mirroring the exact chain now live in Supabase
   (Company -> Plant -> PM-100 is_released=True -> Production Unit ->
   Machine -> Product Family -> Foam Grade -> 2 raw materials -> Recipe
   Pending Review + components -> Grade Specification (thermal
   conductivity) -> Production Run -> Sample -> Physical Property Result,
   a pass). All 11 pages load with zero exceptions. This does NOT
   replace an actual browser check against the deployed Streamlit Cloud
   app - that remains Stefan's own final visual check before UAT (task
   #740), documented explicitly in the test file's own docstring.

2. Multi-method fixture in controlled test scope: confirmed (not newly
   built) - tests/test_pm_hierarchy_pages_smoke.py's seeded_pm_hierarchy
   fixture and tests/test_cr04_pm_release_gating.py's seeded_two_methods_
   non_platform_owner fixture both already exercise two distinct
   Production Methods (one released/PM-100-equivalent, one not) in
   controlled test scope, satisfying this sub-requirement without new
   engineering.

3. Supabase integrity checks: ran a dedicated orphan-FK and row-count
   sanity pass directly against the live reset+reseeded rigid_foam
   schema - 24 checks spanning every FK in the minimum Phase 1 baseline
   chain (plants->companies, plant_production_methods->plants/methods,
   production_units/machines->plants, machines->production_units/
   methods, product_families->plants, foam_grades->families,
   foam_grade_machines->grades/machines, recipe_versions->grades/
   methods, recipe_components->recipes/materials, grade_specifications
   ->grades, production_runs->plants/grades/machines/recipes/methods,
   samples->runs, physical_property_results->runs/samples). Every check
   returned zero orphans; row counts across plants/production_runs/
   samples/physical_property_results/recipe_versions/foam_grades are
   all exactly 1 (the single seeded baseline row per table, as expected
   post-RESET), and exactly 1 production_methods row has is_released=
   true (PM-100), confirming the release-gating data matches the Phase 1
   baseline decision.

4. Full regression: 83 passed (72 prior + 11 new consolidated-walkthrough
   cases), 0 failed, same benign pre-existing numpy RuntimeWarnings as
   every prior batch - zero regressions from this batch or any prior
   CR-04 step.

CR-04 Step 7 is now complete. Step 8 (Close - closeout package to
Charlie, then Stefan's final live-browser check and UAT/release
decision) is next.
"""

VERSION_0_25_0_NOTES = """
2026-08-10 (later same day, CR-04 conditional-acceptance follow-up, per
Charlie's response to the v0.24.0 closeout package): Charlie conditionally
accepted the CR-04 engineering closeout (reset, clean baseline, Operating
Context removal, PM release gating, integrity validation, regression
evidence) pending two items before final technical closure.

1. Confirmed ProductionMethod.parent_method_id is absent from both the
   active db.py model and the live Supabase rigid_foam schema. db.py's
   own ProductionMethod docstring already documents that this
   self-referencing column was introduced briefly on 2026-08-09 and
   dropped the next day when Charlie's technical completion instruction
   replaced the parent/child hierarchy design with the permanent flat
   PM-100..PM-700 vocabulary (see the v0.20.0-era changelog entry for
   that migration). Re-verified directly rather than trusting the
   docstring alone: grepped db.py for any parent_method_id Column
   definition (none found - only the docstring's own historical
   narration), queried information_schema.columns for rigid_foam.
   production_methods on the live Supabase project (columns are id,
   controlled_id, name, description, sort_order, maturity_status,
   is_released - no parent_method_id), and confirmed zero foreign-key
   constraints on that table (a self-referencing FK would show up here
   if the column or constraint had survived in any form). No removal was
   needed - the clean-schema instruction was already fully satisfied by
   the prior flat-PM migration.

2. Completed task #746 (the CR-01 follow-up "Machine" -> "Production
   Unit or Cell" customer-facing sweep), which CR-01's own v0.19.0
   changelog entry had explicitly disclosed as only partially done (the
   equipment Add/Edit form on pages/31_Production_Equipment.py only).
   Swept every remaining customer-facing surface where "Machine" refers
   to the equipment entity itself - not the backend Machine model/table/
   column names, which CR-01's own "label-only, no migration risk"
   principle keeps unchanged, and not the separate "Machine Settings" ->
   "Process Parameters" naming axis (already renamed at the page-title
   level in CR-01; inline occurrences of that phrase, e.g. the "**Machine
   settings**" section headers on pages/4's Setup tabs and "machine/
   process setting" in pages/17's intro text, are a different naming
   decision and were deliberately left alone rather than guessed at -
   flagged here for Charlie/Stefan to decide separately if desired).

   Renamed: pages/16_Trend_Analysis.py (the "Machine filter" selectbox,
   the "no machine ... blank machine" checkbox help text, the "Machine:
   X -> Y" change-log entry, the "no recipe-version changes, machine
   changes..." caption, and both Function/Action intro mentions of
   "machine changes"); pages/18_Root_Cause_Assistant.py (the "recipe
   version, machine, or..." intro phrase, the "Machine changed:" diff
   line, and both "no meaningful difference... machine..." fallback
   messages); pages/2_Product_Family_Foam_Grade.py (the "Machines this PU
   Material can be produced on" multiselect label on both the Add and
   Edit forms, the "Machines" grade-list table column, and the "no
   machines tagged... add a machine on the Plant & Foam Equipment
   Overview page" warning - which also corrected a stale page reference
   left over from CR-01's own page split, to "Production Equipment
   page"); pages/4_Production_Run_Trial_Record.py (the "Machine /
   foaming line" selectbox on both the Add and Edit Production Run
   forms, both breadcrumb captions, the run-history table's "Machine"
   column, and the "no Machine assigned yet" warning); pages/21_Report.py
   (the Batch Release and WP3 Conformance report viewers' "Machine"
   metric/inline label); reports.py (the "Machine" key-value row on both
   the PDF and Word Batch Release Record renderers, the run-history table
   column, the multi-source report header's "Machine" field, and the
   WP3 Conformance report's "Machine" row); cascades.py (the
   plant-delete-confirmation detail text's "machine(s)" count key, now
   "production unit(s) or cell(s)" - this one renders directly into the
   confirmation message a user reads before deleting a plant, e.g. "3
   production unit(s) or cell(s), 12 sample(s)...").

   Confirmed already complete, not touched again: pages/31_Production_
   Equipment.py (every label already read "Production Unit or Cell" from
   CR-01 itself) and pages/1_Plant_Installation_Overview.py (its
   "Production Units/Cells" metric was already correctly named).

   Two tests asserted the old interim label text and needed updating in
   lockstep with the rename (not a regression - these tests were
   correctly written against CR-01's own admittedly-partial v0.19.0
   state): tests/test_pm_hierarchy_pages_smoke.py's
   test_foam_grade_form_offers_machines_across_activated_methods (the
   multiselect label) and test_production_run_form_derives_method_
   snapshot_from_selected_machine (the selectbox label).

Verified via py_compile on every touched file and a full regression run:
83 passed, 0 failed, same benign pre-existing numpy RuntimeWarnings as
every prior batch - zero regressions. CR-04 closeout updated with this
evidence for Charlie's final technical closure sign-off; the deployed-
browser walkthrough and Stefan's UAT are next.
"""

VERSION_0_26_0_NOTES = """
CR-05 (Default User Role Inheritance and Platform Admin Separation for
UAT), implemented 2026-08-11 per Charlie's instruction document
(PI3_Rigid_Foam_Phase_1_CR05_Default_User_Role_Inheritance_and_Platform_
Admin_Separation_for_UAT.docx). Corrects the Rigid Foam user-role model to
match the approved PI3 Default User Roles architecture already used by the
Flexible Foam application: Platform Admin stays platform-level and outside
the company-role inheritance path; every customer company inherits exactly
the 4 approved Default Company Roles (Company Admin, R&D, Read Only,
Technical Engineer); legacy role names and "Application Admin" are removed
from the customer-facing model.

1. Live Supabase data (rigid_foam.roles) - the actual gap this CR closes:
   - The 3 Default Company Role templates (company_id NULL) were still
     literally named "technical" and "viewer" (Company Admin was already
     correct) - renamed to "Technical Engineer" and "Read Only".
   - Added a 4th template, "R&D" ("R&D Manager, Engineer."), matching
     Flexible Foam's baseline - previously missing entirely.
   - The same two renames were backfilled onto HTC Global's and Pacific
     Thai Urethanes (PTU)'s existing role clones, and both companies were
     backfilled a new "R&D" clone, so every existing company - not just
     ones created after this change - ends up with the full approved
     4-role set. All renames are same-row updates (id unchanged), so no
     user's role_id needed re-pointing and no access was lost.
   - HTC Global's own admin clone (id=4) was relabeled from "Company
     Admin" back to "Platform Admin" - restoring the platform/company
     naming distinction (see access_control.STRUCTURALLY_REQUIRED_ROLE_
     NAMES / ADMIN_ROLE_NAMES's docstrings, and auth.py's module
     docstring) that CR-04's "Database Reset and Clean UAT Baseline" reset
     had inadvertently lost when it re-seeded HTC's company row - the
     template itself was never renamed, so this is purely a one-time data
     correction on HTC's own row, not a code change. Stefan's existing
     user account keeps its role_id unchanged.

2. Code/terminology sweep for the remaining literal "Application Admin"
   and "viewer" occurrences the audit turned up outside the DB:
   - app_rigid_foam.py: the sidebar nav section label for the platform-
     owner-only page group (Companies, Subscription Types, Default User
     Roles, User Accounts, PI3 Connectivity, Performance, Company
     Analysis) was literally "Application Admin" - the one place this
     legacy term was still visible in the live app. Renamed to "Platform
     Admin".
   - auth.py: four "viewer" fallback-default role strings (used only when
     a session has no real role - the AUTH_DISABLED dev bypass path aside,
     which already said "Platform Admin") updated to "Read Only" for
     consistency with the approved role names.
   - .streamlit/secrets.toml.example: the legacy-fallback-login example
     blocks used literal "technical"/"viewer" role values - updated to
     "Technical Engineer"/"Read Only" so a fresh deployment following this
     example doesn't recreate the retired names.
   - pages/27_Performance.py, role_provisioning.py, db.py (Role class),
     pages/26_Default_User_Roles.py: docstring accuracy updates only (no
     behavior change) - these described "exactly 3" templates / literal
     admin/technical/viewer names as current fact; corrected to describe
     the 4-role baseline CR-05 establishes.

3. No schema change: is_builtin=True role rows (templates and their
   per-company clones) are pure runtime data - CR-05 needed new/renamed
   rows and new RolePagePermission-free defaults (full access, matching
   the "no rows = full access" convention every other template already
   uses), not new columns. role_provisioning.clone_builtin_roles_for_
   company already clones "every template" dynamically, so adding the R&D
   template needed no code change there - new companies going forward
   automatically get all 4 roles with zero additional wiring.

4. Confirmed already-satisfied by existing design, no code change needed:
   - Platform Admin can never be cloned into a customer company (criterion
     2) - structurally guaranteed, since clone_builtin_roles_for_company
     only ever reads company_id IS NULL templates, and "Platform Admin" is
     never a template (it only exists as HTC's own company-scoped clone's
     name).
   - Platform Admin can never be offered as a customer company's role
     assignment (criterion 6) - pages/25_User_Accounts.py's role dropdown
     is already filtered to `Role.company_id == company_id`, so a role
     scoped to HTC's own company_id never appears in another company's
     picker.
   - Company Admin protection / one-admin-per-company enforcement
     (criteria 6, 13 partial) - already covers both "Company Admin" and
     "Platform Admin" via access_control.ADMIN_ROLE_NAMES, unchanged by
     this CR.

5. New automated tests (criterion 13): tests/test_cr05_role_model.py - 9
   tests covering the exact 4-template set, a company-creation inheritance
   test (clone_builtin_roles_for_company produces exactly the 4 approved
   roles), a Platform-Admin-exclusion test (a "Platform Admin"-named
   company-scoped role, simulating HTC's real row, does not leak into a
   new company's clone set), a per-company isolation test for the new R&D
   role, and parametrized checks that no legacy name is accidentally
   wired into ADMIN_ROLE_NAMES/protected_role_name.

6. Out of my reach - flagged for Charlie/Stefan: acceptance criterion 12
   ("the Customer User Access Request implementation workbook uses the
   same four Default Company Roles as its controlled role choices") refers
   to an external implementation workbook I don't have a copy of in either
   the app repo or the Development Docs folder - not actioned here; needs
   Charlie to confirm which file this is or supply it for a follow-up
   pass.

Verified via py_compile on every touched file, a full regression run (92
passed, 0 failed - 83 pre-existing + 9 new CR-05 tests, same benign
pre-existing numpy RuntimeWarnings as every prior batch), and an AppTest
smoke pass of pages 23/24/25/26 and app_rigid_foam.py's own nav render
against both an empty schema and a schema seeded with the exact 4-template
set - zero exceptions.
"""

VERSION_0_27_0_NOTES = """
CR-06 (Production Method Release-Gate Enforcement and Platform-Owner
Bypass Removal), implemented 2026-08-11 per Charlie's instruction document
(PI3_Rigid_Foam_Phase_1_CR06_Production_Method_Release_Gate_Enforcement_
and_Platform_Owner_Bypass_Removal_for_UAT.docx). Opened from a UAT finding
during the CR-05 walkthrough: a Platform Admin could activate unreleased
Production Methods (PM-200/PM-300/PM-400) for both HTC Global's own plant
and a real customer's plant, because CR-04's release-gate implementation
(v0.25.0) explicitly exempted the platform-owner company from the gate.
That conflated two separate controls - Platform Admin's cross-company
ADMINISTRATION scope vs. a Production Method's release LIFECYCLE status -
letting unreleased functionality get written into live plant
configuration. This batch separates them again: release status is now the
sole eligibility condition for activation, for every company including
HTC Global's own, with no role-based exception anywhere in the decision.

1. helpers.method_activatable_by_customer(): the is_platform_owner
   parameter is removed from the function signature entirely (not
   defaulted off - a caller passing one now gets a hard TypeError), so no
   future call site can silently reintroduce the bypass. The function is
   now `bool(method.is_released)`, full stop.
2. pages/30_Production_Methods.py: the call site no longer computes or
   passes is_platform_owner to the gate at all (the now-dead local
   variable was removed). Both the checkbox's disabled state and the
   actual write path (`if checked and can_activate and ...`) derive from
   the same can_activate value, so the fix closes the gap in the UI and
   the save path simultaneously - there was never a second, separate
   write-path check to miss.
3. Live Supabase data reconciliation (rigid_foam.plant_production_methods):
   found exactly the UAT finding, reproduced - HTC Global's plant had an
   active PM-200 link; PTU's (real customer) plant had active PM-200,
   PM-300, AND PM-400 links. Only PM-100 is actually released. Before-
   change inventory captured for all 6 links; the 4 invalid ones
   deactivated (active=false, not row-deleted - preserves audit history,
   the same soft-toggle convention this page's own checkbox already
   uses for a customer unchecking a method). PM-100's 2 valid activations
   (HTC Global, PTU) were untouched. One dependency found and evaluated:
   PTU has a real Machine record ("Spray Foam Unit") tagged to PM-400 via
   Machine.production_method_id - no FoamGrade/Recipe/ProductionRun
   depends on it, so it was left in place untouched (Machine.
   production_method_id is independent equipment metadata, not itself
   gated by the plant-level activation flag) and is flagged here per
   CR-06's own instruction to identify (not necessarily remove) any
   dependent data before cleanup. Post-reconciliation integrity check:
   zero active plant_production_methods rows point to an unreleased
   method, project-wide.
4. Docstring accuracy updates (no behavior change): db.py's
   ProductionMethod class and pages/30's own module docstring both
   described the now-removed platform-owner exemption as current fact;
   corrected to describe the CR-06 baseline and its own history.
5. tests/test_cr04_pm_release_gating.py rewritten in place for CR-06 (the
   file name is kept for git history continuity - see its own module
   docstring): the two CR-04 tests asserting the platform-owner bypass
   (deliberately reversed, not a regression) are replaced with 7 tests -
   released/unreleased activatable checks with no role parameter at all;
   a TypeError guard proving the bypass parameter was actually removed
   from the signature, not just ignored; Company Admin gated on their own
   plant; Platform Admin gated on the platform-owner company's OWN plant
   (the core regression guard); Platform Admin gated when viewing a
   CUSTOMER company's plant (the exact UAT scenario, using tenant_scope.
   company_picker's single-company auto-lock so no selectbox needs
   driving); and a later-released method becoming activatable for every
   role with no exception.

Verified via py_compile on every touched file, a full regression run (95
passed, 0 failed - 92 pre-existing/CR-05 + 7 new, net +3 after replacing
the 2 old CR-04 tests - same benign pre-existing numpy RuntimeWarnings as
every prior batch), and an AppTest smoke/evidence pass of the Production
Methods page under three sessions (Platform Admin on HTC Global's own
plant; Company Admin on a customer's own plant; Platform Admin viewing a
customer's plant) - all three show PM-100 activatable and PM-200 disabled
with the explanatory caption, zero exceptions.
"""

VERSION_0_28_0_NOTES = """
CR-07 (Product Grade Physical Property Target Architecture and Quality
Alignment), implemented 2026-08-11 per Charlie's instruction document
(PI3_Rigid_Foam_Phase_1_CR07_Product_Grade_Physical_Property_Target_
Architecture_and_Quality_Alignment_for_UAT.docx). Opened from a UAT
finding on Add Product Grade: the fixed "Target density (kg/m3)" and
"Target hardness (N, 40% ILD)" fields hardcoded exactly two targets per
grade, and the hardness field is Flexible Foam legacy content with no
place in Rigid Foam's property architecture at all. Replaced both with a
dynamic, unlimited "Product Grade Property Targets" list driven off the
same controlled Physical Property Master that Quality results already
use, so grade targets and Quality results can be compared like-for-like.

1. Foundation: reused GradeSpecification (the WP3d normalized
   property-target model - property_definition_id/property_method_id/
   target_operator/target_value/lower_limit/upper_limit/unit/condition_id/
   orientation_id/location_id/notes) rather than building a second,
   competing model. It already carried every field CR-07 needs and is
   already the exact table wp3_conformance.py's live conformance engine
   reads - it simply had no UI to create/edit rows (only ever populated
   by seed scripts/tests). FoamGradeTargetProperty (an earlier, simpler
   "other target properties" table) is deprecated in place in its favor -
   0 live rows, nothing to migrate.
2. db.py: added GradeSpecification.target_type (CR-07's customer-facing
   vocabulary - Nominal/Minimum/Maximum/Maximum absolute/Range/Class) and
   .class_value (the text value for Class-type targets), plus
   GRADE_SPEC_TARGET_TYPES and a GRADE_SPEC_TARGET_TYPE_OPERATORS mapping
   that translates each target_type to the target_operator the
   pre-existing evaluation engine actually reads (Nominal->"=",
   Minimum->">=", Maximum/Maximum absolute->"<=", Range->"between",
   Class->"class"). Added a real, enforced uniqueness constraint -
   UniqueConstraint(foam_grade_id, property_definition_id) - blocking a
   grade from carrying two targets for the same property, at the database
   level, not just in the UI. FoamGrade.target_density/target_hardness
   and FoamGradeTargetProperty are deprecated in place (columns/table kept,
   unread by the active UI), matching this app's established
   deprecate-in-place precedent (FoamGrade.production_method_id, WP4).
3. pages/2_Product_Family_Foam_Grade.py: removed the two fixed number_input
   fields from both Add and CSV-import construction paths. Added a new
   "Product Grade Property Targets" section on Edit - existing targets as
   expanders with per-row Save/Remove forms, plus an "Add a property
   target" form whose Property picker excludes properties the grade
   already has a target for (readmitted the moment that target is
   removed) and is replaced with an explanatory message once every
   controlled property is in use. Target-type choices and UOM choices are
   both filtered live to what the selected property's own master data
   allows (PhysicalPropertyDefinition.allowed_target_type, default_uom) -
   no free-text UOM entry anywhere. The write path re-checks for a
   duplicate (grade, property) pair immediately before insert, independent
   of the picker already excluding it, so CR-07's "duplicate blocked in
   the UI AND the write path" requirement holds even against a race. The
   grade list table's old three fixed columns are replaced with one -
   "Property targets": a live count of specifications - and Edit shows a
   read-only legacy-value caption when a grade still carries a nonzero
   legacy target_density/target_hardness value, rather than silently
   hiding that history.
4. cascades.py: found and fixed a real pre-existing gap while wiring
   grade-deletion cleanup for the new targets - delete_foam_grade_cascade
   bulk-deletes FoamGrade's dependent rows with session.query(...).delete(),
   which bypasses the ORM-level cascade="all, delete-orphan" on
   FoamGrade.specifications entirely (that cascade only fires on
   session.delete(instance), never on a bulk query-delete). This means
   GradeSpecification rows would have been silently orphaned on every
   grade deletion since WP3d introduced the relationship, independent of
   CR-07. Added an explicit bulk-delete of GradeSpecification scoped to
   the grade before FoamGrade's own delete, and added "product grade
   property target(s)" to foam_grade_dependency_counts so the existing
   pre-delete dependency-count UI surfaces it like every other dependent
   row type.
5. Quality alignment: no new integration code needed - verified end-to-end
   via a direct database test that a PhysicalPropertyResult and a
   GradeSpecification sharing the same property_definition_id (plus
   compatible method/condition/orientation/unit context) evaluate
   correctly through the existing wp3_conformance.evaluate_specification/
   compute_conformance_report, and that a result with no matching grade
   target is not invalidated by that absence (compute_conformance_report
   already treats "no spec for this property" as no target to fail).
   Class-type targets are captured but deliberately not numerically
   evaluated - evaluate_specification's target_operator == "class" falls
   through to its existing final return None, None, since a Class target
   has no numeric actual_value to compare against today (documented with
   a comment, no functional change).
6. Existing-data reconciliation: inventoried the one live grade
   (RF-COLDROOM-001, id 7) - target_density=38 (non-placeholder),
   target_hardness=NULL, 0 FoamGradeTargetProperty rows anywhere. Did
   NOT auto-migrate the density value into a GradeSpecification row,
   because 4 distinct controlled density properties exist (Apparent
   overall/Core/Free-rise/Minimum-fill density) with no way to
   disambiguate which one a bare legacy number represents - migrating a
   guess would silently misrepresent the grade's real target. Per CR-07's
   own instruction, never considered migrating target_hardness (40% ILD
   is explicitly Flexible Foam legacy content). Surfaced the legacy value
   read-only in the Edit UI instead and flagged it as an outstanding
   exception in the CR-07 closeout package for Charlie/Stefan to resolve,
   matching the CR-05 criterion-12 precedent of flagging rather than
   guessing.
7. Live Supabase migration (cr07_grade_specification_target_type_and_
   uniqueness): added target_type/class_value columns and the
   uq_grade_specification_grade_property unique constraint to
   rigid_foam.grade_specifications. Confirmed via information_schema
   afterward. No existing grade_specifications row (1 live row, Thermal
   conductivity on the same grade) violated the new constraint.
8. tests/test_cr07_grade_property_targets.py (new, 19 test items): Add
   form has no fixed density/hardness fields; target-type vocabulary
   matches CR-07's list; each of Nominal/Minimum/Maximum/Maximum
   absolute/Range evaluates Pass/Fail correctly via its derived operator
   (9 parametrized cases); Class targets are captured but not numerically
   evaluated; duplicate (grade, property) targets are blocked at the DB
   level; the available-properties picker excludes used properties and
   readmits them after removal; a grade with every controlled property
   used leaves nothing available to add; delete_foam_grade_cascade
   removes GradeSpecification rows (regression guard for the cascades.py
   fix above); foam_grade_dependency_counts includes property targets;
   a Quality result sharing a grade target's property evaluates
   correctly; a Quality result with no grade target is not invalidated.
   Full pre-existing regression suite re-run afterward (114 total tests
   across all files) confirms the new target_type/class_value columns and
   the new unique constraint introduce no fallout in any test file that
   directly constructs GradeSpecification rows (test_cr04_step7_
   consolidated_walkthrough.py, test_wp4_unit_conversion.py, test_wp4_
   rigid_lot_use_correlation.py, test_wp4_rigid_achievement_summary.py,
   test_wp4_recipe_optimization_page_smoke.py, and gen_uat015_019_live_
   pages.py's own fixtures) - none of their existing fixtures create two
   specs for the same (grade, property) pair, so all 114 pass unchanged.
"""

VERSION_0_29_0_NOTES = """
CR-08 (Raw Material Category and Subcategory Taxonomy Alignment),
implemented 2026-08-11 per Charlie's instruction document
(PI3_Rigid_Foam_Phase_1_CR08_Raw_Material_Category_and_Subcategory_
Taxonomy_Alignment_for_UAT.docx). Opened from a UAT finding on Raw
Materials category selection: the app still used the inherited Flexible
Foam RAW_MATERIAL_CATEGORIES free-text vocabulary (Polyol/Isocyanate/
Blowing agent/.../Other), with no Subcategory concept at all, no
enforcement against typos/near-duplicates, and no way to distinguish
Water vs. Hydrocarbon vs. HFO/HCFO blowing agents or gel/blow/delayed/PIR
catalysts - all explicitly required for rigid-foam formulation review.

1. Foundation: replaced the free-text vocabulary with one controlled
   Category -> Subcategory taxonomy (10 Categories, 40 Subcategories -
   Polyol, Isocyanate, Blowing Agent, Catalyst, Surfactant/Foam
   Stabilizer, Flame Retardant, Crosslinker/Chain Modifier, Functional
   Additive, Filler/Solid Additive, Other) exactly matching CR-08 section
   4, added as db.RAW_MATERIAL_TAXONOMY. RAW_MATERIAL_CATEGORIES (the old
   flat list) is deprecated in place - kept only so any code still
   reading RawMaterial.category's legacy free text keeps working; no
   longer read or written anywhere in the active UI.
2. db.py schema: extended RawMaterialCategory (previously a flat
   Category-only lookup) into a self-referencing adjacency list -
   parent_category_id (NULL = Category, set = Subcategory under that
   Category), active, and is_exception_only (True only on the single
   "Other" Subcategory row) - rather than introducing a second parallel
   lookup table, since this satisfies CR-08's parent-child requirement
   with the simplest normalized structure and lets the existing
   RawMaterial.category_id FK keep pointing at the same table. Added
   RawMaterial.subcategory_id (new FK into the same table) alongside the
   existing category_id; both relationships now require explicit
   foreign_keys= since there are two FKs into one target table.
   Parent-child validity (a Subcategory must belong to the chosen
   Category) is enforced in the page's write path, not a DB constraint -
   a same-table two-column parent check isn't expressible without a
   trigger, inconsistent with this project's established app-level-
   validation preference (documented on RawMaterial.subcategory_id's own
   comment).
3. pages/14_Raw_Materials.py: added _category_subcategory_picker(), a
   dependent Category -> Subcategory selectbox pair rendered OUTSIDE any
   st.form (same reason as the pre-existing supplier picker) so choosing
   a Category immediately narrows the Subcategory choices on the same
   rerun; a mandatory description text_input appears only when the chosen
   Subcategory is the "Other" exception row, prepended into notes as
   "[Other: ...]" on save. Wired into all three write paths - Manual
   entry, Add from TDS (pre-filled from PI3's best-effort taxonomy guess,
   via a new _match_taxonomy_text case-insensitive exact-name matcher; an
   unmatched guess just leaves the picker unset rather than accepting
   free text), and Edit (pre-filled from the material's current
   category_id/subcategory_id). CSV/Excel import now matches each row's
   category/subcategory text columns against the controlled taxonomy the
   same way; rows with no exact match on either column are bucketed into
   a "needs review" list and NOT imported, rather than silently importing
   them unclassified or coercing them to "Other". The Raw Materials list
   now displays "Category / Subcategory" (via a new helpers.
   raw_material_category_label()) and the multiselect filter works off
   that combined label.
4. ai_assistant.py: extract_raw_material_from_tds()'s prompt and returned
   dict now request/return both category and subcategory (against the
   full controlled taxonomy, not the old flat list) - still just PI3's
   best-effort guess; the caller always re-validates against real
   controlled rows.
5. pages/3_Recipe_Version_Record.py: _match_or_create_raw_material() (the
   unattended inline-creation helper used when a recipe component names a
   material not yet in the Raw Materials list) no longer hardcodes the
   legacy category="Other" free text - it now lands on the single
   controlled "Other"/"Other" exception pair and flags the new row's
   notes for later manual classification, since this code path has no
   user-facing form to ask for a real Category/Subcategory and no product
   knowledge to classify from beyond a typed name. Its two raw-material
   display format_func lambdas now use raw_material_category_label()
   instead of the removed free-text field.
6. helpers.py: added raw_material_categories() (active top-level Category
   list), raw_material_subcategories(session, category_id) (active
   Subcategory list filtered to one parent), and
   raw_material_category_label() ("Category / Subcategory" display
   string, falling back to legacy free text or "—" for an unclassified
   material).
7. Existing-data reconciliation: all 40 pre-CR-08 raw_material_categories
   rows deprecated in place (active=False, never deleted - same
   precedent as CR-07's target_density/target_hardness); 50 new active
   rows seeded (10 Categories + 40 Subcategories, RMC2-* controlled_ids,
   a "band of 100 per Category" sort_order convention so the seeded
   content can be checked against CR-08 section 4 line-for-line). All 5
   live raw_materials rows reconciled: 3 unambiguously classified from
   real product-chemistry knowledge (Lupranate M20 -> Isocyanate/
   Polymeric MDI, DABCO DC 193 -> Surfactant/Foam Stabilizer/Silicone
   surfactant, Cyclopentane -> Blowing Agent/Hydrocarbon), 2 left
   Category-only with Subcategory flagged for manual review rather than
   guessed (Lupranol 3300's exact polyol subtype, POLYCAT 5's exact
   catalyst subtype) - per CR-08's own "flag ambiguous records for review
   rather than guessing" instruction. The dormant, UI-less
   RawMaterialCatalogEntry research table's own free-text category data
   was reviewed and found badly inconsistent but is out of CR-08's direct
   scope (no live UI reads it) - flagged, not touched.
8. Live Supabase migration (cr08_raw_material_category_subcategory_
   taxonomy): added parent_category_id/active/is_exception_only to
   raw_material_categories and subcategory_id to raw_materials. Confirmed
   via information_schema and row counts afterward (40 legacy rows
   deactivated, 50 new active rows, 5 raw_materials rows reconciled).
9. tests/test_cr08_raw_material_taxonomy.py (new, 19 test items): the
   taxonomy dict matches CR-08 section 4 exactly (10 Categories in order,
   40 Subcategories total, Water/Hydrocarbon/HFO-HCFO and gel/blow/
   delayed/PIR catalyst subtypes present, Polyol supports formulated/
   system blends); exactly one Subcategory row is_exception_only; the
   Category/Subcategory pickers filter correctly and never cross-offer a
   Subcategory under the wrong parent; manual entry/edit round trips
   persist the controlled ids correctly; RecipeComponent.raw_material_id
   references survive a RawMaterial's reclassification unchanged; CSV
   import matching is case-insensitive exact-match only (no fuzzy
   matching of unknown text); the Add Raw Material form (AppTest) offers
   the full controlled Category list with no free text and a Subcategory
   list correctly filtered to the default Category. Full pre-existing
   regression suite re-run afterward (133 total tests across all files,
   up from 114) confirms no fallout from the RawMaterialCategory/
   RawMaterial schema changes.
"""

VERSION_0_29_1_NOTES = """
v0.29.0 -> v0.29.1 (2026-08-11, CR-08 closeout correction - data only):
Charlie issued CR-08's final technical acceptance ("CR-08 engineering
implementation is accepted... No further application changes are
required") together with the resolution of the two Subcategory-review
flags raised in CR-08 section 7/note 7 above: Lupranol 3300 -> Polyol /
Rigid polyether polyol, POLYCAT 5 -> Catalyst / Blow catalyst. Applied
directly to the live rigid_foam.raw_materials table in Supabase - no
schema, code, or test file touched, matching v0.12.1's own precedent for
a data-only correction round-trip. raw_materials.id=49 (Lupranol 3300,
category_id=41/Polyol) set to subcategory_id=51 (raw_material_categories
RMC2-110, "Rigid polyether polyol", parent_category_id=41); raw_materials.
id=51 (POLYCAT 5, category_id=44/Catalyst) set to subcategory_id=65
(RMC2-420, "Blow catalyst", parent_category_id=44). Verified afterward via
a direct join query (both rows now resolve a complete Category/Subcategory
pair) and a table-wide count check (5/5 raw_materials rows now carry a
non-null subcategory_id, confirming no other row was touched). This
closes CR-08 with zero outstanding items - the CR08_Closeout_Package.docx
section 6 (existing-data reconciliation) and section 10 (outstanding
items) are updated to reflect both records as classified per Charlie's
own explicit direction, not JC inference, and the package's status line
now reflects CR-08 as technically accepted.
"""

VERSION_0_29_2_NOTES = """
v0.29.1 -> v0.29.2 (2026-08-11, RawMaterialCatalogEntry taxonomy alignment -
data only): Charlie delivered an updated PI3_Plant_Edition_Rigid_Foam_Raw_
Materials_Master_v2_MASTER_LINKED.xlsx (same file CR-08's closeout package
flagged in §6 as "badly inconsistent... out of CR-08's direct scope, not
touched"), now carrying a new Controlled_Taxonomy sheet that reproduces
CR-08's exact 10-Category/40-Subcategory vocabulary, and a Category/
Subcategory pair for all 151 Rigid_Raw_Materials rows validated 100% clean
against it (verified independently before writing anything - zero
mismatches across all 151 rows). Applied directly to the live
rigid_foam.raw_material_catalog_entries table in Supabase as a data-only
correction - no schema, code, or test file touched, matching the v0.12.1/
v0.29.1 precedent for this class of change. All 151 matched rows (by
controlled_id/Material_ID: the 109 commercial-grade RF-ADD/BA/CAT/FR/ISO/
POL/SUR rows plus 42 RF-REF-001 through 042 generic reference-material
rows) had their free-text category/subcategory columns overwritten with
the aligned values - e.g. "Additive" -> "Functional Additive", "Surface-
cure / rigid foam catalyst" -> "Gel catalyst", "Aromatic polyester polyol"
-> "Polyester polyol". Verified afterward: total row count unchanged
(166), and all 151 targeted rows now resolve a clean Category/Subcategory
pair against the active rigid_foam.raw_material_categories rows via a
direct join query.

Explicitly out of scope, not touched: 15 additional RF-REF-043 through
RF-REF-057 rows, added after this spreadsheet was originally authored (by
the later Post-G5 Reference Data Enrichment batch, tasks #690-696). These
rows have Category and Subcategory literally swapped (e.g.
category="Polyether polyol", subcategory="Polyol") - a worse defect than
the free-text mismatch this batch fixed, but this spreadsheet doesn't
cover them (its own Material_ID range stops at RF-REF-042), so guessing
their correct values would repeat the exact "flag rather than guess"
violation this project has avoided since WP3. Flagged to Charlie/Stefan as
a follow-up, not silently left broken.

This table has no live UI reading it (RawMaterialCatalogEntry is a
dormant Charlie-owned research catalog, per its own db.py docstring), so
this is purely a content-accuracy correction with no user-facing or
functional impact - no regression suite change needed, no page touched.
"""

VERSION_0_30_0_NOTES = """
v0.29.2 -> v0.30.0 (2026-08-12, CR-09 - Remove Internal Development and
UAT Leakage from Customer-Facing Application, Charlie's instruction):
Charlie's UAT audit found internal engineering vocabulary - development-
phase numbers, WP (work-package) identifiers, UAT/synthetic-dataset
terminology, and raw maturity_status/production_release codes - leaking
into customer-facing screens, generated Word reports, and PI3 prompt
construction. Confirmed genuine (not a misread) at every site Charlie's
CR named:

- pages/30_Production_Methods.py: help text saying "At Phase 1, only
  PM-100... is released for customer activation", and a caption showing
  the raw maturity_status value plus "Phase 1 offers Production Method
  PM-100 only." - the exact string in Charlie's own Trigger Finding.
  The page's docstring had also been claiming, since CR-01, that no
  phase label was ever shown here - false, and the regression this CR
  fixes.
- pages/21_Report.py: help text and the fifth report tab's label both
  named "WP3" (a development work-package identifier). Renamed to
  "Property Conformance Report" everywhere customer-visible, including
  the downloaded file's name.
- reports.py: a Plant/Period Summary Word report subtitle reading
  "Synthetic UAT / Reference Dataset" verbatim; a Recipe Optimization
  Word report's Note column and conclusions text carrying wp3_
  conformance.production_release_status()'s raw code ("UAT_PASS_NO_
  RELEASE") and the phrase "UAT-only"; the Property Conformance Word
  report's own Note column (same raw code) and title (still said "WP3
  Property Conformance Report"); and that same report's "Grade status"
  row, which could show FoamGrade.status's raw "UAT_ONLY" code verbatim.
- pages/15_Recipe_Optimization.py: the identical Note-column and PI3-
  prompt leaks as reports.py's Recipe Optimization Word report (this
  page builds that same data), plus a static PI3 prompt instruction
  literally saying "(UAT-only)".

Fix: a new dependency-free module, customer_presentation.py, is the
SINGLE shared translation layer every one of the above call sites now
routes through (CR-09 section 7, Acceptance Criterion #12 - one shared
formatter, not per-page copies). It can't live in helpers.py, since
helpers.py already imports reports.py and reports.py needs the same
translations - a shared helper in either would be a circular import.
customer_presentation.py has four functions: customer_facing_method_
availability_note() (replaces the Production Methods caption),
customer_facing_release_note() (translates production_release_status()
codes), customer_facing_reference_dataset_label() (translates the
synthetic-dataset flag), customer_facing_report_title() (translates
"WP3 Property Conformance Report"), and customer_facing_grade_status_
label() (translates FoamGrade.status's "UAT_ONLY").

Explicitly unchanged, per Acceptance Criteria #1/#13/#14: wp3_
conformance.production_release_status() and every backend conformance/
achievement calculation that calls it; helpers.method_activatable_by_
customer() and the release gate it implements (method.is_released);
FoamGrade.status itself and every place it's used for actual logic (is_
uat_only checks). Only the DISPLAY of these values changed - never their
computation or the gating decisions built on them.

New regression coverage: tests/test_cr09_customer_content_leakage.py -
unit tests on every customer_presentation.py function; a live AppTest
render of pages/30 and pages/21 scanning ALL rendered text for the
forbidden markers ("WP3", "UAT", "Phase 1/2/3", "maturity_status",
"production_release", "Synthetic", "UAT_ONLY", "UAT_PASS_NO_RELEASE");
generated-.docx text scans (via python-docx) of both the Property
Conformance Report and the Plant/Period Summary Report, built from
fixtures that genuinely trigger the UAT-only/synthetic-dataset paths
(not just asserting the translation functions look clean in isolation);
and a monkeypatched-ai_assistant.ask_assistant() capture of the actual
PI3 prompt string Recipe Optimization sends. tests/test_cr04_pm_release_
gating.py's existing caption assertion was updated to match the new
customer-safe text (the old assertion string was itself part of the
leak this CR removes).
"""

VERSION_0_31_0_NOTES = """
v0.31.0 - CR-10 (Split Product Families and Product Grades into Separate
Pages, Charlie's instruction for Stefan, 2026-08-12).

Problem: the sidebar had one combined "Product Families & Product Grades"
entry (pages/2_Product_Family_Foam_Grade.py) whose page split the two data
domains into an in-page "Product families" / "Product grades" tab pair.
Charlie's CR removes that extra tab-selection step - each domain gets its
own direct sidebar entry - while keeping the family-to-grade relationship
clear and reachable without repeating the family selection.

What changed:

- pages/2_Product_Families.py (new): the old page's "Product families" tab
  content, unchanged - same Add/Edit/Delete form, same table, same cascade-
  delete warning. Adds one new control: an "Open Product Grades for
  '<family>' →" button on the selected family's edit panel, which stashes
  that family's id in st.session_state["pfg_family_context_id"] and calls
  st.switch_page("pages/2_Product_Grades.py").
- pages/2_Product_Grades.py (new): the old page's "Product grades" tab
  content, unchanged - same manual Add form, CSV/Excel import, machine
  assignment, and the full Product Grade Property Targets editor (CR-07's
  dynamic target-type/UOM/method/condition builder). Adds one new control:
  a "Filter by product family" selectbox above the Add/import tabs, narrowing
  the grade table to one family (or "All product families"). This selectbox
  is what consumes the context from Product Families - on each run, if
  st.session_state["pfg_family_context_id"] is present, it's popped and used
  to pre-set st.session_state["pgr_family_filter"] BEFORE the selectbox with
  that key is instantiated, which is what makes Streamlit treat it as this
  run's initial value. One-time inheritance, not a permanent link: the key
  is gone from session_state immediately after use, so a later direct visit
  (or a switch from a different family) is never masked by a stale value,
  and the operator can always change the filter afterward.
- pages/2_Product_Family_Foam_Grade.py: deleted.
- app_rigid_foam.py: production_method_pages' single combined nav entry is
  replaced by two, in CR-10's mandated order (Production Methods,
  Production Equipment, Product Families, Product Grades).
- access_control.py: PAGE_CATALOG's "product_family_foam_grade" key is
  removed and replaced with two fresh keys, "product_families" and
  "product_grades" - same pattern CR-03 used to retire
  "reference_formulations". A live query against Supabase's
  rigid_foam.role_page_permissions before this change found zero rows
  referencing "product_family_foam_grade" for any role, so there was
  nothing to migrate onto the two new keys; every role gets full access to
  both new pages by default, same as it had on the old combined one.

Explicitly unchanged, per CR-10 section 6 ("Functional Preservation"): every
Product Family and Product Grade record, the Product Family -> Product
Grade FK relationship itself, all existing authorization/validation/data
controls, and every search/selection/filter/edit/view function the two old
tabs provided.

New regression coverage: tests/test_cr10_product_family_grade_split.py -
confirms the old page file and page_key are gone, both new PAGE_CATALOG
keys exist, production_method_pages' declared order matches CR-10 section
3, both new pages open directly without exception, the family filter
defaults to "All product families" on a direct visit, and - the one that
actually proves the handoff design works rather than merely not crashing -
presetting session_state["pfg_family_context_id"] before loading Product
Grades results in the filter selectbox picking up that exact family, the
grade table narrowing to it, and the context key being consumed (popped)
rather than lingering. A defensive case also confirms a stale/unresolvable
context id is ignored rather than crashing the page. tests/test_pm_
hierarchy_pages_smoke.py, tests/test_cr07_grade_property_targets.py, and
tests/test_cr04_step7_consolidated_walkthrough.py were updated to point at
the correct split-out page for the flows they already covered.
"""

VERSION_0_31_1_NOTES = """
v0.31.1 - CR-09 closeout correction (per Charlie's "CR09 Closeout Review -
Return to JC for Completion", 2026-08-12, and Stefan's direction to act on
it). Charlie formally rejected the CR-09 closeout package: the Recipe
Optimization PI3 prompt-capture test (test_recipe_optimization_pi3_prompt_
has_no_leak in tests/test_cr09_customer_content_leakage.py) had been
skipped rather than executed, and the closeout treated a passing WP3
Property Conformance Report leak-scan as indirect proof this separate,
customer-facing PI3-prompt path was also clean. Charlie's review: "the CR
explicitly covers customer-facing PI3 prompt/output leakage, so that
execution path requires direct verification" - not a stand-in from a
different report type.

Root cause of the skip: pages/15_Recipe_Optimization.py's expectation_
summary block (built for "Does the current recipe meet target?") rounded
avg_actual/avg_target with a bare .round(2) instead of the pd.to_numeric
(errors="coerce").round(2) pattern this same page already uses twice
elsewhere (the "Physical properties" table and the per-property/per-
version summary) for exactly this reason: a rigid-foam grade's quality
results generally carry no target_value at all, which leaves that column
all-None/object-dtype, and a bare .round(2) raises TypeError on that. This
one unconverted call site - left behind when the fix was applied to the
other two - is what made the test's own fixture trip an "unrelated"
exception before the PI3 button was ever reached, and what the original
closeout mischaracterized as a pre-existing edge case rather than a defect
to fix.

What changed:
- pages/15_Recipe_Optimization.py: applied the same pd.to_numeric(errors=
  "coerce").round(2) conversion to expectation_summary["avg_actual"]/
  ["avg_target"] that the page's other two summary tables already use.
- tests/test_cr09_customer_content_leakage.py: removed the pytest.skip()
  that treated this exception as acceptable; the page load is now a hard
  assert not at.exception. Added the missing test-support pieces that were
  masking two further, unrelated gaps once the dtype skip was removed: (1)
  _seed_wp3_fixture now adds a PI3AIConnectionSetting row (the "Get PI3
  recommendation" button is gated on ai_assistant.is_enabled_for_plant(),
  same requirement test_wp4_recipe_optimization_page_smoke.py's fixture
  already satisfies) and a FoamGradeTargetProperty row (so the button's
  target-properties field is non-empty and not disabled); (2) the test now
  sets fake OPENAI_API_KEY/PI3_VECTOR_STORE_ID secrets (satisfying ai_
  assistant.is_configured()'s presence check only - ask_assistant() itself
  stays monkeypatched, so no real network call is ever made); (3) the test
  now calls tenant_scope.clear_scope_cache() right after seeding - without
  it, tenant_scope.py's st.cache_data-backed plant_ids_for_company() (keyed
  on company_id alone, 30s TTL) could return another test's stale scope
  whenever schema-reset autoincrement handed two different tests the same
  company_id within that window, silently filtering this fixture's own
  grade out of the page's grade picker and making the test flake based on
  run order/file position - reproduced by running the full file repeatedly
  before the fix, confirmed gone after (3 consecutive clean full-file runs,
  10 consecutive clean full-suite runs).

Verified: test_recipe_optimization_pi3_prompt_has_no_leak now executes the
real prompt-construction path end-to-end (grade selected, button clicked,
ask_assistant() reached) and passes - the captured PI3 prompt contains none
of CR-09's forbidden markers. Full tests/test_cr09_customer_content_
leakage.py suite: 11 passed, 0 skipped (was 10 passed, 1 skipped). Full
app regression suite: 152 passed, 0 skipped, 0 failed.

Observation for Charlie/Stefan (not a CR-09 leak, not fixed here - flagged
per this project's disclosure practice rather than silently left in): the
captured prompt's "Does the current recipe achieve..." and "Quality test
outcomes by version" lines render a bare "nan" wherever avg_target is
genuinely absent (e.g. a rigid-foam grade whose target lives on
GradeSpecification rather than on the result row) - cosmetic, not a
forbidden-marker leak, but worth a follow-up CR if a customer-facing "nan"
in a PI3 answer is undesirable.
"""

VERSION_0_32_0_NOTES = """
v0.32.0 - CR-11: Standardize Record Create, Edit/Delete and CSV/Excel
Import Functions (per Charlie's CR-11 instruction doc, 2026-08-12, and
Stefan's standing "do not leave any loose ends" direction). Every
customer-facing record-creation page now exposes exactly three functions,
in this order, with this exact wording: "Create <record>", "Edit/Delete
<record>", "CSV/Excel import <records>" (no spaces around the slash,
singular for Create/Edit-Delete, plural for import) - see helpers.
cr11_function_tab_labels(), the single shared helper every page below
calls so the wording can never drift page-to-page.

Application-wide inventory (task #813) found 15 pages/tab-groups needing
this treatment. 9 already had separate Create/Edit-Delete/Import surfaces
that only needed relabeling/reordering onto the shared helper: Recipes
(3), Physical Property Result/Quality Test Result (5), Quality Observation/
Quality Issue (6), Customer Trials (11, incl. nested Sample sub-tabs),
Optimization Trials (12, incl. nested Sample sub-tabs), Raw Materials (14,
incl. nested Supplier sub-tabs), Production Run Trial Record (4, five
independent record groups - Production Run, Setup Data, Stream Reading,
Production Event, Runtime Data), Product Grades (2), and Production
Equipment (31, wording changed to "Production Unit / Cell" per the app's
existing Machine-to-"Production Unit or Cell" rename). 6 pages had only a
single "Add" expander and no CSV/Excel import at all, and needed the full
3-tab structure and a net-new import built from scratch, each mirroring an
existing app-wide import convention rather than inventing a new one:
Plant Installation Overview (1), Product Families (2), Expert Notes (20,
new import pushes each row into PI3 exactly like the manual Create form
does, via a shared _push_note_to_vector_store() helper extracted from the
old inline logic), User Roles (24), User Accounts (25), Production
Equipment (31).

User Accounts' CSV/Excel import (25) is security-sensitive (bulk account
creation) and was built to Stefan's explicit direction: same validation/
permission pattern as every other import (email/role validation, the
existing one-admin-per-company rule enforced against both existing DB rows
and within the import batch itself, the subscription user-count cap
enforced the same way), and every imported account gets a system-generated
temporary password (shown once, never persisted in plaintext) plus a new
mandatory forced-password-reset on first login. Schema: db.py's User
gained must_reset_password (Boolean, default False) - never set by the
manual Create-user form, only by the CSV/Excel import path. Enforcement:
auth.require_login() checks it immediately after a successful login,
before any other page content renders (_render_forced_password_reset()),
so the gate applies platform-wide, not just on the User Accounts page
itself; it clears on both the DB row and session_state once the user sets
their own new password. Applied to the live Supabase rigid_foam schema
(must_reset_password boolean default false) after explicit confirmation
from Stefan - the initial apply_migration call was blocked by the Claude
Code auto-mode classifier as a production-database-altering action, and
per that block's own instruction not to route around it, was escalated to
Stefan via AskUserQuestion rather than retried unilaterally; he approved
"apply it now."

New regression test files: tests/test_cr11_forced_password_reset.py (4
tests exercising the real login-gate code path against a real page, not
just the helper function in isolation - default-false on manual create,
gate blocks page content and shows only the reset form, submitting a
matching password clears the flag on both DB and session_state and
unblocks the real page, mismatched passwords are rejected and the flag
stays set) and tests/test_cr11_tab_wording_compliance.py (15 tests, one
per page/tab-group, asserting the exact mandated label triplet renders in
the exact mandated adjacent order - including the two nested-sub-tab
pages, 11/12/14, where AppTest's at.tabs flattens a nested st.tabs() call
in between its parent's own siblings; the outer group's triplet is
checked with the nested group's own labels filtered out first, since a
real user sees the nested tabs as a second tab bar one level down, not
interleaved into the outer bar - and the five independent groups on page
4, confirmed by direct probing to render with no cross-group
interleaving).

Two pre-existing bugs found and fixed while restructuring page 14 (Raw
Materials) in an earlier commit within this batch, left over from an
in-progress edit before a context-window compaction: a stray duplicate
`with tab_suppliers:` line, and a missing cr11_function_tab_labels import
- both caught before any test ran (py_compile failed first on the former;
the latter was caught by inspection).

Deliberate exclusions from this CR, to be documented with full reasoning
in the closeout package (task #817): pages/30_Production_Methods.py
(activates existing controlled-vocabulary rows, creates no new record);
every access_control.PLATFORM_ONLY_KEYS admin page (Companies,
Subscription Types, PI3 Connectivity, Default User Roles, Performance,
Pilot Analysis); and the non-record-creation analysis/report pages
(15-19, 21).

Full regression suite: 171 passed (156 pre-existing + 15 new tab-wording
tests), 0 failed, same 4 pre-existing unrelated numpy divide-by-zero
warnings (test_recipe_optimization_baseline.py, test_wp4_rigid_lot_use_
correlation.py) present before this batch too.
"""

VERSION_0_33_0_NOTES = """
v0.33.0 - CR-12 (Align Rigid Foam Reporting Structure with Flexible Foam,
2026-08-12) closed.

CR-12 required a full side-by-side inventory of both apps' reporting
capabilities (on-page Word downloads + central Report-page reports)
before implementing anything, any missing equivalent Rigid capability
implemented where the business function and data support it, retained
application-specific differences documented with concrete reasons, and
regression coverage for every item in the final inventory with zero
skipped verification paths.

Inventory finding (see CR12_Closeout_Package.docx for the full matrix):
Rigid Foam was ALREADY at full structural reporting parity with Flexible
Foam before this CR's engineering work began. Both apps have exactly the
same 11 on-page Word-download locations (pages 3, 5, 6, 9, 11, 12, 15,
16, 17, 18, 19, 20 - one page, 15, has two), the same 4 shared central
Report-page report types (Batch Release / Conformance Record, Plant /
Period Summary, Trial Closeout Report, Sample Certificate of Analysis),
identical reports.py build_*/render_*_docx function signatures for every
shared report, and identical "Download Word" button wording throughout.
Confirmed via exhaustive comparison: page-by-page download_button grep
across every page in both apps' pages/ directories, full reports.py
function-name inventory (18 build/render pairs each), and direct
signature/argument-shape comparison at every call site. No missing
on-page download or missing Report-page coverage was found anywhere in
either app - tasks #819/#820 (implement missing coverage) therefore
closed as "verified already at parity, no implementation needed" rather
than skipped.

Rigid Foam carries exactly two legitimate, already-justified additions
beyond Flexible, both pre-dating this CR and re-confirmed here rather
than re-litigated: the rigid branch of the Recipe Optimization Report
(reports.build_rigid_recipe_optimization_report_data, reusing the same
render_recipe_optimization_report_docx unmodified - WP4, task #561), and
the WP3 Property Conformance Report, a 5th Report-page tab
(build_wp3_conformance_report_data/render_wp3_conformance_report_docx -
Converged Joint Implementation Plan section 7.4, justified by rigid-only
GradeSpecification data with no Flexible equivalent).

Since CR-12's own engineering conclusion is "parity already held," the
substantive work is the proof, not new feature code:

New regression test file: tests/test_cr12_reporting_parity.py (22 tests).
Every item in the final inventory is proven to actually generate a real
docx - the Report page's all 5 tabs (including the Customer Trial /
Optimization Trial radio branch), every on-page report on pages 5, 6, 9,
11, 12, 20, the two page-3 reports gated behind a custom row-selection
widget (Recipe Formulation Record via AppTest with st.session_state
preset; Where Used Report via a direct build/render function call, since
that half has no Streamlit dependency), and all 5 Industrial Intelligence
pages' own deterministic reports (15-19). Proof method: st.download_
button's `data=` argument is evaluated eagerly at script-run time (not
lazily on click - confirmed by reading streamlit.testing.v1.element_tree),
so an AppTest page load that reaches that line with no exception has, by
construction, already run the full build-data -> render-docx chain
successfully; asserting the button's presence is sufficient proof, no
simulated click needed. Two further tests assert the two apps' on-page
download_button locations and reports.py function inventories keep
matching exactly (except the two named justified additions) - a
structural regression guard against a future change adding reporting to
one app without the other, not just a one-time snapshot.

Bug fixed while building this test file (self-caught, no user report):
several @st.cache_data-decorated app-wide functions (analytics.py's
run_settings_dataframe/property_results_dataframe/actual_usage_dataframe,
tenant_scope.py's six id-scoping helpers, access_control.denied_page_keys)
take a leading `_session` parameter, which Streamlit's cache_data
convention excludes from the cache key - so the key is built from small-
integer arguments alone (company_id, plant_ids, foam_grade_id, ...). Since
every fixture in this suite drops/recreates the schema (autoincrement ids
restart at 1 each time), one test file's foam_grade_id=1 could collide
with a completely different, later test file's own foam_grade_id=1 and
silently serve its stale cached DataFrame - reproduced directly by running
this file back-to-back with test_cr11_tab_wording_compliance.py and
test_flat_pm_propagation_smoke.py, which intermittently failed tests in
whichever file ran second purely from cache-key reuse. Fixed by clearing
every one of these caches at this file's own fixture setup and teardown -
contained entirely within the new test file, no application code changed.

Full regression suite: 193 passed (171 pre-existing + 22 new CR-12
tests), 0 failed, same 4 pre-existing unrelated numpy divide-by-zero
warnings present before this batch too. Verified stable across repeated
runs and in combination with the two other files sharing its known
autoincrement-id/cache-key hazard.
"""

VERSION_0_33_1_NOTES = """
v0.33.1 - CR-10 closeout correction (per Charlie's
"CR10_Closeout_Review_Return_to_JC.docx", 2026-08-12): CR-10's first
closeout package was returned OPEN - Charlie's review found the
implementation correct but the closeout evidence incomplete, and asked
for direct evidence of 6 specific items plus the pre-existing CR-09
Recipe Optimization skip reported separately (not conflated with CR-10's
own completeness).

This release adds the missing direct evidence. No application code
behavior changed - see below for the two small comment/docstring-only
touches - this is purely closing an evidence gap in a CR that was already
correctly implemented in v0.31.0.

15 new tests added to tests/test_cr10_product_family_grade_split.py
(7 -> 22 tests in that file), one section per item in Charlie's return:

1. Active-page highlighting (both new pages): structural proof - both
   page keys are registered in production_method_pages next to an
   st.Page(...), routed through app_rigid_foam.py's single shared
   `for page in pages: st.page_link(page)` render loop (no per-page
   custom render branch that could opt one out of Streamlit's native
   page_link highlighting), and both default to page_visible()=True.

2. Product Families functional regression - create (real form, real
   submit button), edit (real Edit form, DB-verified persistence),
   delete (real confirm-checkbox + delete-button flow, cascade verified),
   selection (see capability note below), plus CSV/Excel import as bonus
   coverage beyond the item's literal wording.

3. Product Grades functional regression - same four, plus CSV/Excel
   import via a real st.file_uploader upload and a real "Confirm import"
   click.

4. Authorization and access behavior on both new page keys - a real
   company-scoped Role with an explicit RolePagePermission row
   (can_view=True, can_use=False - the "View only" state) on
   "product_families"/"product_grades" is proven, through AppTest, to
   hide the Create form and the Import uploader on both pages, with a
   contrast test proving a role with no permission row (the "no row =
   full access" default) sees the real Create form.

5. Validation and data persistence - blank-name submits on both pages'
   Create forms are proven to show the real inline error and insert zero
   rows; edits are proven durable by editing in one AppTest session then
   loading a completely separate, fresh AppTest instance and confirming
   the database (not an in-memory local variable) shows the edit.

6. Customer-facing regression scan - proven at the actual rendered
   surface (sidebar page titles via app_rigid_foam.py's st.Page(title=...)
   list, and both new pages' own live st.tabs() labels), not a blind grep
   for "Product families"/"Product grades" as substrings, which would
   false-positive against the CURRENT, correct table column headers both
   pages legitimately still use those same two words for.

CR-09 separation (per Charlie's explicit instruction, not a CR-10 test):
tests/test_cr09_customer_content_leakage.py's three pytest.skip() calls
near its PI3-prompt test are defensive page-structure-drift guards, not
an active skip - re-ran that file's full 11-test suite in isolation and
got 11 passed, 0 skipped. Reported here for the record, not duplicated
into CR-10's own test file, since it belongs to CR-09's.

Capability note (methodology correction to an earlier test file, not an
application defect): tests/test_pm_hierarchy_pages_smoke.py (2026-08-09/10)
documented that clickable_table's st.dataframe row-click selection "has
no way to [be] simulate[d]" in AppTest. Verified directly against
streamlit==1.59.2 (this project's pinned version) that this is only half
true: presetting the SELECTED ROW ID key directly (e.g.
session_state["family_selected_id"]) indeed doesn't work, because the
page's own "idx is None -> pop the selection" branch always fires on a
run with no click event - but presetting the underlying dataframe
WIDGET's own on_select state (session_state["families_table"] =
{"selection": {"rows": [0], "columns": []}}), the exact shape Streamlit
stores under the widget's own key, does work: the widget reports that
selection on its very first run, same as a real click would. This gave
items 2 and 3 above genuine end-to-end UI evidence instead of a
data-layer stand-in.

Two small stale-comment fixes made while re-reading the touched pages for
this correction (not customer-facing, not part of item 6's scan, just
found along the way and fixed since "no loose ends" is the standing
instruction on this project): db.py's GradeSpecification unique-
constraint comment referenced the now-deleted pages/2_Product_Family_
Foam_Grade.py; corrected to point at pages/2_Product_Grades.py with the
CR-10 history noted.

Full regression suite: 208 passed (193 pre-existing + 15 new CR-10
correction tests), 0 failed. Verified stable across 3 consecutive runs of
the whole suite, plus the new test file run alone.
"""

VERSION_0_33_2_NOTES = """
v0.33.1 -> v0.33.2 (2026-08-12, CR-11 closeout correction, per Charlie's
"CR11_Closeout_Review_Return_to_JC.docx" - the first CR-11 closeout
package was returned OPEN: it had wording/order tests only, not direct
executed evidence that Create/Edit/Delete/CSV-Excel-import actually work
through the real UI, for every applicable page/record group in CR-11's
own final inventory).

Charlie's return asked for six things: (1) Create evidence, (2) Edit
evidence, (3) Delete evidence (including permissions/confirmation/
safeguards), (4) CSV/Excel import evidence (valid import, validation
handling, persisted records) - explicitly naming the six net-new
importers CR-11 built - (5) coverage across every record group in the
inventory, including nested groups and the five Production Run groups,
and (6) a page/record-group evidence matrix mapping each surface to its
executed test name and result.

Of CR-11's 15 inventoried pages/groups, Product Families and Product
Grades already carried direct UI-driven Create/Edit/Delete/Import
evidence from the CR-10 closeout correction (tests/test_cr10_product_
family_grade_split.py) - not duplicated here. The remaining 13 pages/
groups (18 counting nested sub-groups and the Production Run page's five
independent groups separately) had none - every one of the tests below
is new.

Added five new test files, one per logical cluster of pages, all built on
the same AppTest technique the CR-10 correction established and verified
against streamlit==1.59.2: presetting a clickable_table dataframe
widget's OWN on_select state (session_state[<table_key>] =
{"selection": {"rows": [i], "columns": []}}) before .run() to drive real
row-click selection for Edit/Delete, and driving the real st.file_uploader
via FileUploader.set_value((filename, bytes, mime)) for CSV/Excel import -
both genuine UI paths, not data-layer stand-ins - plus each file's own
_clear_relevant_caches() guard against the known cross-test/cross-file
@st.cache_data id-collision hazard (small-int cache keys repeat once
autoincrement ids restart across test files) first documented in CR-12
and defended against again in the CR-10 correction:

- tests/test_cr11_functional_evidence_group_a.py (12 tests): Plants,
  Expert Notes, Production Unit/Cell - three of the six net-new CR-11
  importers. Each gets Create/Edit-Delete/valid-import tests plus a
  csv_import_validation_rejects_invalid_row test (net-new importers get
  extra scrutiny per Charlie's item 4).
- tests/test_cr11_functional_evidence_group_b.py (12 tests): Recipe,
  Quality Test Result, Quality Issue, Sample - four pages that already had
  all three functions pre-CR-11 (relabel-only), each with Create/Edit-
  Delete/Import evidence proving the pre-existing machinery still works
  correctly under the new tab structure.
- tests/test_cr11_functional_evidence_group_c.py (14 tests): Role, User
  (the other two net-new importers - User is the security-sensitive
  bulk-account-creation surface), and Raw Materials' two independent
  record groups (outer Raw Material, nested Supplier). Includes a
  dedicated test proving the User import enforces the one-admin-per-
  company rule within a single import batch, not just against pre-
  existing rows.
- tests/test_cr11_functional_evidence_group_d.py (15 tests): all five of
  page 4's independent record groups by name, per Charlie's item 5 -
  Production Run, Setup Data, Stream Reading, Production Event, Runtime
  Data - each with its own Create/Edit-Delete/Import evidence against the
  real seeded dependency chain (Company/Plant/ProductionMethod/Machine/
  ProductFamily/FoamGrade/RecipeVersion/ProductionRun, with Stream
  Reading and Runtime Data's own real FK onto the Finalized phase, not
  the run directly).
- tests/test_cr11_functional_evidence_group_e.py (12 tests): Customer
  Trials & Samples and Optimization Trials & Samples, outer Trial group
  and nested Sample group independently for each page.

65 new functional-evidence tests total (plus the 6 pre-existing CR-10-
correction tests covering Product Families/Grades - 71 pages/groups'
worth of direct Create/Edit/Delete/Import evidence across all 15
inventoried surfaces, 18 counting nested groups and Production Run's
five groups separately).

One real, previously-unexercised defect was found while writing the User
Accounts import evidence and fixed directly (not just flagged): pages/
25_User_Accounts.py's CSV import called a non-existent helper,
parse_bool_cell(), instead of the real helpers.parse_bool() - a latent
NameError that would have fired on any import row whose "active" column
carried a non-blank value (the default/blank-column path was bug-free,
which is why no prior test caught it). Fixed to call parse_bool().

One correction was also needed to a PRE-EXISTING CR-11 test file,
tests/test_cr11_tab_wording_compliance.py: its module-scoped full_chain
fixture reset the schema but never cleared tenant_scope's cached id-
scoping helpers, so once the five new group files above (which sort
alphabetically before it) left a stale cache entry for the same small-int
company_id/plant_id, this file's own seeded chain became invisible to the
Samples & Conditioning page under full-suite runs (it would hit its own
"nothing to show yet" guard and render zero tabs) even though the file
passed cleanly in isolation. Added the same _clear_relevant_caches()
guard this correction's own new files use. Full regression suite verified
stable across 2 consecutive full runs after this fix (273 passed both
times), plus each new file's own isolated run.

Full regression suite: 273 passed, 0 failed (208 pre-existing + 65 new
CR-11 functional-evidence tests), same 4 pre-existing unrelated numpy
divide-by-zero RuntimeWarnings present before this batch too.
"""

VERSION_0_33_3_NOTES = """
v0.33.2 -> v0.33.3 (2026-08-12, CR-12 closeout correction, per Charlie's
"CR12_Closeout_Review_Return_to_JC.docx" - the technical conclusion was
accepted outright ("the reporting architecture appears aligned and the
22 new reporting-parity tests provide strong coverage"), but the closeout
package's evidence STRUCTURE was returned OPEN pending completion of six
items).

Unlike the CR-11 correction, this one required almost no new engineering
or new test-writing - Charlie's own return says as much ("the existing
technical conclusion, report allocation, retained Rigid-specific
differences and 22-test parity suite can remain unchanged where the
completed evidence confirms them"). The six items are a documentation-
completeness exercise over evidence that mostly already existed:

1. Comparison matrix expanded with the missing columns Charlie's return
   named: filters/record context, equivalent function in the other app,
   structural gap, required implementation action - one row per report
   type, all 18 rows from the original matrix retained.
2. Every parity row now states its disposition explicitly ("No gap -
   No implementation required") rather than leaving it implied by a
   Yes/Yes pair of columns.
3. Both Rigid-only rows (Rigid Recipe Optimization Report branch, WP3
   Property Conformance Report) show the Flexible equivalent as N/A with
   the same concrete data reason already documented in the original
   closeout package (GradeSpecification/unit-converted lot-use data has
   no Flexible Foam counterpart) - not re-justified, just carried
   forward and made resubmission-visible.
4. Access-path evidence: every one of the (now) 18 inventory rows mapped
   to its executed generation test by name. One genuine gap found and
   closed while building this mapping - the matrix's own "PI3 Q&A Report
   (5 answer locations app-wide)" row had zero test coverage anywhere in
   the suite; build_pi3_qa_report_data()/render_pi3_qa_report_docx() are
   plain-Python (no Streamlit dependency), so proven the same direct-call
   way the file already proves Where Used Report - a real question/
   answer/tool_log shape in, valid OOXML bytes out. New test:
   test_pi3_qa_report_generates() in tests/test_cr12_reporting_parity.py
   (23rd test in that file).
5. Scope/filter/access evidence: every reporting call site runs through
   tenant_scope.py's existing id-scoping helpers, introduced no new
   scoping logic (confirmed in the original closeout's own Section 3
   call-site inspection), so the existing page-scoping test coverage
   (tasks #207-217's original scoping retrofit) already covers every
   report in this inventory - mapped explicitly per row in the
   resubmitted correction document rather than left as a general
   statement.
6. Regression result retained and re-verified after the one new test
   was added: 274 passed, 0 failed, 0 skipped CR-12 acceptance paths
   (193 pre-existing-for-this-CR + 22 pre-existing CR-12 tests + 1 new
   PI3 Q&A Report test).

Full regression suite: 274 passed, 0 failed, same 4 pre-existing
unrelated numpy divide-by-zero RuntimeWarnings present before this batch
too.
"""

VERSION_0_33_4_NOTES = """
v0.33.3 -> v0.33.4 (2026-08-12, CR-11 closeout correction round 2, per
Charlie's "CR11_Closeout_Correction_Review_Return_to_JC.docx" - the
resubmitted CR-11 correction "materially improves the evidence base"
(Create/Edit/valid-import now mapped across all 22 record groups, full
regression clean) but remained OPEN on two specific residual gaps).

1. Delete permission/safeguards: the first correction round proved
   selection -> confirm -> delete -> DB-state verification for every
   group, but never proved a permission-denied/view-only role is
   actually blocked from deleting, per page key - citing the CR-10
   correction's pattern as "supporting methodology" wasn't accepted as
   page-specific CR-11 evidence. Added 20 new Delete-permission tests
   (one per record group that didn't already have one - Product
   Families/Grades were already covered by the CR-10 correction) across
   the 5 existing test_cr11_functional_evidence_group_*.py files, each
   building a real db.Role + db.RolePagePermission(can_view=True,
   can_use=False) (or, for User Roles/User Accounts - a genuine finding,
   not an assumption - the actual gate on those two pages is auth.
   require_role("Company Admin", "Platform Admin"), not access_control.
   can_use_page(), so those two tests exercise the real mechanism
   instead) and asserting the real delete confirm-checkbox/button don't
   render for that role, with the record still present in the database
   afterward. Two page keys are shared by more than one record group
   (Production Equipment reuses "plant_overview"; Raw Material/Supplier
   share "raw_materials"; Production Run's five groups share
   "production_run"; each Trial page's own key covers its nested Sample
   group too) - confirmed from each page's own can_use_page() call site,
   not assumed from the page name.

2. CSV/Excel import validation handling: the first correction round
   only added invalid-row-rejection evidence for the six net-new CR-11
   importers (per the return's own item 4 wording); the other 16
   pre-existing import surfaces had valid-import evidence only. Added
   16 new import-validation tests (Recipe, Quality Test Result, Quality
   Issue, Sample, all 5 Production Run groups, Customer Trial + its
   nested Sample group, Optimization Trial + its nested Sample group,
   Raw Material, Supplier, Product Family, Product Grade - the last two
   added to tests/test_cr10_product_family_grade_split.py since Charlie's
   item 4 named all six net-new importers and that file's own CR-10
   correction round only proved the valid-import path for them), plus
   one additional User Accounts import-validation test judged necessary
   because the existing one-admin-per-company test proves a business
   rule, not row-level validation rejection. Each new test uploads one
   CSV row that fails that importer's own real bad-row check (read from
   each page's own import code - out-of-scope foreign-key ids, values
   outside a controlled vocabulary, or a missing required field,
   depending on the importer), confirms the "Confirm import" button does
   not render (every importer in this app gates it behind `if
   good_rows and st.button(...)`, so an empty good_rows list is direct
   proof of rejection), and confirms the database row count is
   unchanged.

38 new tests total across 6 files (3 in group_a, 8 in group_b, 7 in
group_c, 10 in group_d, 8 in group_e, 2 in test_cr10_product_family_
grade_split.py).

Full regression suite: 312 passed, 0 failed (274 pre-existing + 38 new),
verified stable across 2 consecutive full runs. Same 4 pre-existing
unrelated numpy divide-by-zero RuntimeWarnings present before this batch
too.
"""

VERSION_0_33_5_NOTES = """
v0.33.4 -> v0.33.5 (2026-08-12, CR-12 closeout correction round 2, per
Charlie's "CR12_Closeout_Correction_Review_Return_to_JC.docx" - the
round-1 correction's PI3 Q&A generation-test fix and 274-passed
regression were accepted, but the closeout stayed OPEN on two evidence-
structure gaps).

1. Comparison matrix incompleteness: the round-1 correction's matrix
   carried the disposition/gap/action columns but dropped the original
   closeout's On-page(Flex)/On-page(Rigid)/Report-page(Flex)/Report-page
   (Rigid) availability columns, and stated filters/record-context as one
   blanket sentence rather than per-row. Rebuilt as one consolidated
   18-row matrix (no more splitting across the original closeout and the
   correction) carrying every CR-12 Section 3 field per row: on-page/
   report-page availability for both apps, reporting role, the actual
   selection context for that specific report (e.g. Production Run for
   Batch Release/Conformance Record, Recipe Version for Recipe
   Formulation Record, Foam Grade for the Industrial Intelligence
   reports, Sample for the Certificate of Analysis), equivalent function,
   structural gap, and required action - read from each report's own
   build_*_report_data() signature in reports.py, not assumed.

2. Scope/filter/access evidence non-traceable: the round-1 correction's
   evidence mapped reporting paths to historical task numbers (#207-217,
   #216, #129, #279) instead of naming an executed automated test. No
   test in the suite actually proved cross-company isolation for any
   reporting path before this round. Added tests/test_cr12_report_scope_
   isolation.py - 13 new tests, each seeding two separate companies and
   proving the actual record-selector query or widget that feeds a
   report's subject (recipe version, raw material, production run,
   customer trial, optimization trial, sample, foam grade, expert note,
   or PI3 Q&A vector-store filter) excludes the other company's record.
   Verified non-vacuous by temporarily neutering tenant_scope.apply_scope
   and tenant_scope.plant_ids_for_company and confirming the relevant
   tests fail, then reverting. One page-source finding corrected the
   assumed mapping: Root-Cause Assistant's (page 18) real selector is
   Quality-Issue/Observation-based (run-scoped), not foam-grade-based as
   its grouping with pages 15/16/17/19 would suggest - its new test
   reflects the actual widget, not the assumption.

Full regression suite: 323 passed, 2 skipped (312 pre-existing + 13 new;
the 2 skips are the pre-existing Flexible-Foam-sibling-app-not-present
skips in test_cr12_reporting_parity.py, unchanged by this batch). No
application code changed - test-coverage and documentation only.
"""

VERSION_0_33_6_NOTES = """
v0.33.5 -> v0.33.6 (2026-08-12, CR-11 closeout correction round 3, per
Charlie's "CR11_Closeout_Correction_Round2_Review_Return_to_JC.docx" -
round 2 closed the CSV/Excel validation gap and supplied named delete-
permission evidence for 20 of the 22 record groups, but one gap remained
for Product Families and Product Grades).

Remaining gap: the round-2 matrix cited
test_product_families_view_only_role_cannot_use_write_controls and
test_product_grades_view_only_role_cannot_use_write_controls as delete-
permission evidence for these two surfaces. At commit 6b958ae those two
tests prove the page is in view-only mode and the Create submit control/
CSV uploader are unavailable - they never select an existing row and
verify the Delete confirmation/button path itself, leaving Delete
unverified for exactly these two groups (the other 20 groups already had
a real *_view_only_role_cannot_delete test selecting a row before this
round).

Fix: added test_product_family_view_only_role_cannot_delete_via_ui and
test_product_grade_view_only_role_cannot_delete_via_ui to
tests/test_cr10_product_family_grade_split.py. Each preloads the page's
own clickable_table on_select state to select the seeded row (confirming
a view-only role can still VIEW/select it), runs as a real
RolePagePermission(can_view=True, can_use=False) role, and asserts the
real delete confirm-checkbox and delete-button keys are absent while the
record remains persisted afterward - reading both pages' own source
first confirmed the entire Edit form AND the delete_with_confirm() block
are gated behind the same `if not page_usable:` branch that already
renders the view-only caption, so this is direct evidence for the Delete
path specifically, not a restatement of the Create/Import evidence.

Full regression suite: 325 passed, 2 skipped (323 pre-existing + 2 new;
same pre-existing Flexible-Foam-sibling-app-not-present skips, unchanged).
"""

VERSION_0_33_7_NOTES = """
v0.33.6 -> v0.33.7 (2026-08-12, CR-13, per Charlie's
"CR13_Split_Suppliers_into_Standalone_Page.docx" - the first of three
newly-queued CRs, processed in numeric order after CR-11 and CR-12 closed).

What changed: Supplier management (Create, Edit/Delete, CSV/Excel import)
moved off the nested "Suppliers" tab inside pages/14_Raw_Materials.py onto
a new standalone page, pages/32_Suppliers.py, with its own "suppliers"
access_control.py page_key - independent of the "raw_materials" key both
record types previously shared under one `page_usable` variable. The new
page is registered in app_rigid_foam.py's formulation_pages, immediately
after Raw Materials and still inside the existing "Formulations" nav
section (CR-13 section 7 explicitly defers any section-label/regroup
decision to a later navigation CR).

What did NOT change: pages/14_Raw_Materials.py keeps its
_supplier_picker/_supplier_names/_ensure_supplier_exists helpers and its
"Default supplier" dropdown on every Raw Material Create/Edit/TDS form -
RawMaterial.default_supplier is a text snapshot, not a foreign key, so
every existing Raw Material <-> Supplier relationship keeps resolving by
name with zero data migration. A live-data check against Supabase's
rigid_foam.role_page_permissions found zero rows referencing
"raw_materials" for any role, so there was no existing Raw-Materials-
scoped restriction to carry over onto the new "suppliers" key - every role
gets full access to the new page by default, the same "no row = full
access" default every other net-new page in the catalog gets.

Tests: tests/test_cr13_suppliers_standalone_page.py (11 new tests) -
standalone page registration in access_control.PAGE_CATALOG and
app_rigid_foam.py's formulation_pages (source-grepped, not imported
directly - app_rigid_foam.py calls st.navigation() at import time, unsafe
outside AppTest, same established technique as
tests/test_cr10_product_family_grade_split.py's own sidebar-order test),
the exact CR-11 three-tab wording/order, Supplier create/edit/delete
persistence and safeguards, CSV/Excel import validation (valid row +
duplicate-name rejection), a rename-cascades-to-RawMaterial.default_
supplier test proving the cross-page relationship survived the split, a
Raw-Materials-side test confirming its "Default supplier" picker still
resolves the moved Supplier record, a view-only-role delete-block test
against the NEW "suppliers" page_key, and a two-company scoping test
proving tenant isolation on the new page independent of whatever isolation
Raw Materials already had. tests/test_cr11_functional_evidence_group_c.py's
Supplier-specific tests (Group C.3b create/edit/delete/import, plus the
correction-v2 view-only-delete-block and import-validation-rejection
tests) were removed from that file with a pointer comment to this one,
since they tested behavior against pages/14_Raw_Materials.py that no
longer exists. tests/test_cr11_tab_wording_compliance.py's combined
Raw-Material-and-Supplier test was split into
test_raw_materials_tabs (Raw Material triplet + Add from TDS only) and a
new test_raw_materials_no_suppliers_tab proving the old tab/triplet is
gone.

Full regression suite: 334 passed, 0 new failures (325 pre-existing + 11
new via test_cr13_suppliers_standalone_page.py, net +9 after removing 6
stale Supplier-on-Raw-Materials tests and adding 2 replacement tab-wording
tests in the two files above). The 2 pre-existing Flexible-Foam-sibling-
app-not-present skips are conditional on a sibling checkout directory and
were not observed in this run's environment - unrelated to this change.
"""

VERSION_0_33_8_NOTES = """
v0.33.7 -> v0.33.8 (2026-08-12, CR-14, per Charlie's
"CR14_Create_Customers_Section_and_Customer_Master.docx" - the second of
three newly-queued CRs, processed in numeric order after CR-13 closed).

What changed: a new lightweight Customer master (db.Customer -
company_id, company_name, contact_person, contact_email, customer_type)
and a new standalone page, pages/33_Customers.py, with its own
"customers" access_control.py page_key, exposing the standard CR-11
Create/Edit-Delete/CSV-Excel-import triplet. A brand-new "Customers"
sidebar section (app_rigid_foam.py's customer_pages) holds Customers then
Customer Trials & Samples, in that order, positioned between "Production"
and "Samples & Trials" - Customer Trials & Samples (pages/11_Customer_
Trials.py) moved out of the old "Samples & Trials" section into this new
one. CustomerTrial gained a nullable customer_id FK to Customer; its
existing customer_name column is kept, not removed - it's a synced
display-only text snapshot updated on every Create/Edit save, so every
existing reader of customer_name elsewhere (reports.py, pages 5/6,
analytics.py) keeps working unchanged. Customer Trials & Samples' Create/
Edit/CSV-import flows all now source customer selection from the
Customer master: Create and Edit use a real selectbox; CSV import
auto-links by exact, case-insensitive customer_name match (never a fuzzy
match) and leaves customer_id NULL on any row with no match, rather than
guessing. Contact Email gets format validation (helpers.is_valid_email())
on both the Customers page's Create/Edit forms and its CSV import path -
empty is valid (the field is optional), only a populated value has to
look like an email.

Migration/mapping: cascades.backfill_trial_customers() links every
pre-CR-14 CustomerTrial (customer_id IS NULL) to an existing Customer by
exact, case/whitespace-normalized customer_name match within the same
company, or creates a new Customer for it if no match exists - never
silently merges two different-looking names into one Customer (CR-14
section 5's explicit requirement). After linking/creating, it flags pairs
of DIFFERENT Customer names within the same company that are suspiciously
similar (difflib.SequenceMatcher ratio >= 0.82) for Stefan's review,
without ever auto-merging them. A live check against Supabase's
rigid_foam.customer_trials confirmed zero existing rows at the time of
this CR, so no actual migration run against production was needed - the
closeout package documents this plus the synthetic-fixture test evidence
proving the helper's linking/creation/duplicate-detection logic all work
correctly.

Tests: tests/test_cr14_customers_section.py (32 new tests) - Customers
section/nav order (source-grepped, not imported directly, same established
technique as prior CR nav tests), direct opening of both pages, the exact
CR-11 three-tab wording/order and required fields, Customer create/edit/
delete persistence and safeguards (including customer_id nullification
on delete rather than cascade-deleting the linked trial, and rename-
cascade onto CustomerTrial.customer_name), CSV/Excel import validation
(duplicate name + invalid email rejection), company scoping and a
view-only-role delete-block test against the new "customers" page_key,
Customer Trials & Samples' Create/Edit/CSV-import Customer-selection
wiring (exact-match auto-suggest, no-match caption, required-selection
enforcement), preservation of existing trial/sample records, the
backfill/duplicate-detection helper's linking/creation/idempotency/
never-merge behavior, and is_valid_email() unit coverage (valid, invalid,
and empty-is-valid cases). tests/test_cr11_functional_evidence_group_e.py's
two outer-Customer-Trial-group tests that predated this CR's Customer-
selectbox rewrite (create-via-form and selection-edit-delete) were
updated in place to drive the new Customer-master selectbox instead of
the retired free-text "Customer name" input, with their fixtures extended
to seed the Customer(s) those flows now require.

Full regression suite: 364 passed, 2 skipped, 0 failures (334 pre-existing
+ 32 new via test_cr14_customers_section.py, minus 2 net-new-test-count
changes absorbed by the 2 corrected tests in test_cr11_functional_
evidence_group_e.py, which stayed at 20 tests total). The 2 skips are the
same pre-existing Flexible-Foam-sibling-app-not-present skips noted in
every prior CR - unrelated to this change.
"""

VERSION_0_33_9_NOTES = """
v0.33.8 -> v0.33.9 (2026-08-13, CR-14 closeout correction, per Charlie's
"CR14_Closeout_Review_Return_to_JC.docx" - one material gap flagged,
everything else in CR-14 accepted as-is).

What changed: pages/11_Customer_Trials.py's CSV/Excel Trial importer
previously left customer_id NULL on a row whose customer_name had no
exact Customer master match, while still importing the trial - a
customer-identification path outside the Customer master, inconsistent
with Create/Edit which both require a Customer picked from the master.
Corrected to use the same exact-match-or-create rule
cascades.backfill_trial_customers() already uses for historical rows: an
exact, case-insensitive, company-scoped customer_name match links to the
existing Customer; no match creates a new Customer in the same import
transaction and links to that instead. Every imported Customer Trial now
ends up linked to a valid company-scoped Customer master record - no
normal post-CR-14 path can create an unlinked trial customer, closing
Charlie's flagged closure gate. The lookup is keyed by (company_id, name)
rather than name alone, so a platform owner viewing "All companies" can't
cross-link two different companies' same-named customers. Create and Edit
were already correct per Charlie's review and were left unchanged.

Tests: tests/test_cr14_customers_section.py's
test_customer_trial_csv_import_auto_links_exact_match_customer_name
updated to assert the unmatched row now auto-creates and links a new
Customer (company-scoped, exact name preserved) instead of asserting
customer_id stays NULL. New test
test_customer_trial_csv_import_never_persists_unlinked_customer_id added
per Charlie's explicit instruction to prove an unmatched imported
customer cannot result in a persisted Customer Trial with customer_id
empty - imports a batch of rows against a company with zero pre-existing
Customers and asserts every persisted row has a non-NULL customer_id
pointing at a real Customer.

Full regression suite: 365 passed, 2 skipped, 0 failures (364 pre-existing
+ 1 new test). The 2 skips are the same pre-existing Flexible-Foam-
sibling-app-not-present skips noted in every prior CR - unrelated to this
change.
"""

VERSION_0_34_0_NOTES = """
v0.33.9 -> v0.34.0 (2026-08-13, CR-15: Standardize Expert Notes Product
Family Terminology and Add Trial Links).

What changed: pages/20_Expert_Notes.py's "Link to" selector previously
offered "Foam Family" for one of its four link targets - the only
customer-facing "Foam Family" wording left in the Expert Notes function
after CR-01's app-wide rename (the underlying analytics.py feature it
draws from, helpers.analysis_unit_picker, is a separate page-level
control on Trend Analysis/Process-Property Correlation/Machine Settings
Optimization and is out of this CR's scope per its own section 3).
Renamed to "Product Family" everywhere a reviewer sees it (the selectbox
option, its entity-picker label, and helpers.expert_note_link_label's
resolved label text) - the internal linked_entity_type value
"product_family" is unchanged, since it is an internal/CSV-import-
documented identifier, not customer-facing copy.

Added two new "Link to" targets, positioned after Product Family per the
CR's required order (Production Run, Product Grade, Product Family,
Commercial Trial, Optimization Trial): Commercial Trial (internal
linked_entity_type "customer_trial", linking to the existing CustomerTrial
table from pages/11_Customer_Trials.py) and Optimization Trial (internal
linked_entity_type "optimization_trial", linking to the existing
OptimizationTrial table from pages/12_Optimization_Trials.py). Both
tables already carried plant_id directly, so this CR required zero
database schema change or Supabase migration - purely an application-
logic extension. Both new types have full parity with the three
pre-existing ones: company-scoped Create-tab entity picker, CSV/Excel
import (same valid_ids_by_type membership-check pattern, extended
bad-row warning text), Edit/Delete tab visibility (with company-scope
exclusion) and edit/delete, and Expert Notes Report tab inclusion. The
shared helper functions PI3's vector-store tagging depends on
(expert_note_plant_id_for_link, expert_note_link_label,
expert_note_foam_grade_id_for_link, all in helpers.py) were extended with
a branch for each new type, resolving plant/company/grade context for a
trial-linked note exactly as they already did for the three pre-existing
types. Neither pages/11_Customer_Trials.py nor pages/12_Optimization_
Trials.py's own navigation, name, or structure was touched by this CR -
only Expert Notes' ability to link to their existing records.

Tests: new tests/test_cr15_expert_notes_trial_links.py (12 tests) -
exact 5-option Link-to order, no remaining customer-facing "Foam Family"
text, Commercial Trial and Optimization Trial create+persist via the real
Create tab, company scoping on that tab's entity dropdown, Edit/Delete
tab visibility/edit/delete for both new types (with company-scope
exclusion), Expert Notes Report tab total-count inclusion, CSV/Excel
import valid-row and out-of-scope-id-rejection paths for both new types,
direct evidence of the 4 shared helper functions' plant/company/grade/
label resolution for both new types (including their deleted-record
fallback), and a direct regression proof that the pre-existing Product
Family Create path still works post-rename. The 15 pre-existing Expert
Note/Plant/Production Equipment tests in tests/test_cr11_functional_
evidence_group_a.py were re-run standalone first and pass unchanged
against the reordered/renamed LINK_TYPES dict.

Also fixed, discovered while getting a clean full-suite run for this CR:
tests/test_flat_pm_propagation_smoke.py's own _reset_schema() never
cleared any @st.cache_data cache (unlike every other test file's own
_reset_schema() in this suite), a latent, order-dependent test-isolation
gap that this CR's own new test file happened to trigger (both files
create a fresh Company/Plant at company_id=1/plant_id=1 after a schema
reset, and tenant_scope's/analytics's cached results for those small ids
were leaking across files). Added the same standard cache-clear every
other test file in this suite already uses - a regression-suite hygiene
fix, not an application-code change.

Full regression suite: 377 passed, 2 skipped, 0 failures (365 pre-existing
+ 12 new via test_cr15_expert_notes_trial_links.py). The 2 skips are the
same pre-existing Flexible-Foam-sibling-app-not-present skips noted in
every prior CR - unrelated to this change.
"""

VERSION_0_35_0_NOTES = """
v0.34.0 -> v0.35.0 (2026-08-13, CR-16: Consolidate Overview Dashboard
Filters into a Unified Layout).

What changed: app_rigid_foam.py's render_overview() previously rendered
its filters as a 5-column primary row (Plant, Production Method,
Production Unit / Cell, Product Grade, Date range) plus a separate
collapsed "Advanced filter (optional)" expander containing only the
Product Family selectbox - meaning a user had to open that expander to
see or use Product Family at all. Per Charlie's
CR16_Consolidate_Overview_Dashboard_Filters_into_Unified_Layout.docx, the
expander is removed and all six filters now render directly in one
two-row, three-column layout: Row 1 is Plant, Production Method,
Production Unit / Cell; Row 2 is Product Family, Product Grade, Date
range. Product Family's help text was shortened from "Commercial
classification only - narrows Product Grade below, does not scope KPIs
on its own." to "Optional classification - narrows Product Grade below,
does not scope KPIs on its own." per the CR's allowance to reword for the
new context.

This is a presentation-only change. Every cascading rule CR-02 established
(Plant -> Production Method -> Production Unit / Cell -> Product Grade,
with Product Family narrowing Product Grade's options only) and every
KPI-scoping rule (Product Family never independently scopes a KPI; trial
records folded in only when neither Method nor Unit is selected; Output
Quantity and Unit only for a single selected Production Method) is
byte-for-byte the same logic as before - only which column each widget
renders in moved. No schema change, no Supabase migration.

Tests: new tests/test_cr16_unified_filter_layout.py (6 tests) - the
Advanced filter expander is gone, all six filters render in the exact new
row order, Product Family's help text matches the reworded copy, the Date
range default is still year-to-date, a full top-to-bottom filtering
session raises no unhandled exception, and a direct regression proving
Product Family narrows Product Grade's options without reducing the
Production runs KPI (two grades on the same machine/method, differing
only by Product Family - selecting Product Family alone leaves the KPI
at 2 while narrowing the Grade dropdown to 1). tests/test_cr02_overview_
pm_alignment.py's 6 pre-existing tests (filter cascade, cross-method KPI
isolation, cross-plant leak prevention) were re-run standalone first and
pass unchanged against the new layout - direct evidence this CR did not
alter any preserved logic.

Full regression suite: 383 passed, 2 skipped, 0 failures (377
pre-existing + 6 new via test_cr16_unified_filter_layout.py). The 2 skips
are the same pre-existing Flexible-Foam-sibling-app-not-present skips
noted in every prior CR - unrelated to this change.
"""

VERSION_0_35_1_NOTES = """
v0.35.0 -> v0.35.1 (2026-08-13, CR-17: Restore Customer Trials & Samples
to Samples & Trials Navigation).

What changed: CR-14 (2026-08-12) had moved Customer Trials & Samples out
of "Samples & Trials" and into the new "Customers" section, second after
the new Customers master page. Stefan clarified the trial page belongs
with the application's trial/sample workflows, not the Customers master
section, so this CR restores it to Samples & Trials in its pre-CR-14
position: app_rigid_foam.py's experiment_pages list is now Production
Samples, Customer Trials & Samples, Optimization Trials & Samples, in
that order; customer_pages now contains only the Customers master page.
Both nav-section keys ("Customers", "Samples & Trials") and their mapping
in nav_sections_with_keys are unchanged - only which list feeds which
section's contents moved.

This is a navigation-placement-only change. The customer_trials page_key
and its access-control behavior are untouched, and every CR-14
Customer-relationship behavior (customer selection, customer_id linkage,
customer_name synchronization, CSV/Excel import auto-create) is
unaffected - pages/11_Customer_Trials.py itself was not edited by this
CR. No database schema change, no Supabase migration.

Tests: new tests/test_cr17_nav_restore.py (7 tests) - Customers section
contains only the Customers page; Samples & Trials lists all three pages
in the required order; both section-to-list mappings are wired correctly;
exactly one Customer Trials & Samples page registration exists app-wide;
the customer_trials page_key remains registered in access_control.
PAGE_CATALOG; the page opens with no unhandled exception from its
restored location; app_rigid_foam.py itself compiles cleanly.
tests/test_cr14_customers_section.py's nav-placement test (test_
customers_section_registered_in_nav_with_correct_order) was updated in
place to assert the corrected (current) layout instead of CR-14's
original placement - its other 32 tests (Customer master CRUD,
CustomerTrial.customer_id linkage, CSV/Excel import auto-create, company
scoping, permission gating) were re-run standalone, unmodified, and all
pass: 33 passed.

Full regression suite: 390 passed, 2 skipped, 0 failures (383
pre-existing + 7 new via test_cr17_nav_restore.py). The 2 skips are the
same pre-existing Flexible-Foam-sibling-app-not-present skips noted in
every prior CR - unrelated to this change.
"""

VERSION_0_36_0_NOTES = """
v0.36.0 (2026-08-13): CR-18 (Eliminate "Foam Family" Terminology Across
Rigid Foam - PI3_Rigid_Foam_Phase_1_CR18_Eliminate_Foam_Family_
Terminology_Across_Rigid_Foam.docx).

What changed: "Foam Family"/"Foam family"/"foam family" - a Flexible Foam
Edition term this app inherited at fork time and never fully renamed -
had leaked into several customer-facing surfaces, standardized here to
"Product Family"/"Product family"/"product family" per the CR's
terminology rule. Every internal identifier (mode: "family", link_type:
"product_family", the FoamGrade class, foam_grade_id columns/params,
product_family internal keys, comments/docstrings describing internal
behavior) is unchanged, per the CR's own Internal Compatibility Boundary.

Repository-wide inventory (task #888): a full case-insensitive scan
found 22 pre-fix occurrences of "foam family" across 9 .py files. 10 were
customer-facing (fixed below); 12 were pure comment/docstring prose
describing internal behavior (analytics.py x9, db.py x1, helpers.py x2 -
plus 3 already-clean CR-15 history notes in pages/20_Expert_Notes.py) and
were left untouched. One additional occurrence, demo_data.py's unused
"Flexible slabstock foam family" seed description (dead code - demo_data.
py is not imported anywhere in the live app), was fixed for hygiene even
though out of the CR's customer-facing scope.

Files changed:
- helpers.py: analysis_unit_picker()'s shared "Analyze by" radio
  ("Foam family" -> "Product family"), its empty-state warning ("No foam
  family available..." -> "No product family available..."), and its
  family selectbox's own label ("Foam family" -> "Product family") - the
  single shared source consumed verbatim by pages 16, 17, and 19 per the
  CR's "fix once at the shared source" instruction (section 6). Docstring
  updated to match; no change to the mode/link_type dict values it
  returns.
- pages/16_Trend_Analysis.py, pages/17_Process_Property_Correlation.py,
  pages/19_Machine_Settings_Optimization.py: each page's own action text,
  pooling caption, and PI3-subject-context `subject_desc` f-string
  (independently duplicated per page, not centralized) - all now read
  "product family". Page 19's action text is the exact leak CR-18
  section 2 quotes verbatim.
- pages/5_Physical_Property_Result.py, pages/6_Quality_Observation.py:
  the "Foam scope" radio's "Foam family" option, empty-state caption, and
  family selectbox label - same pattern as the shared control, fixed
  per-page since this "Foam scope" filter is a separate, non-centralized
  implementation.
- reports.py: the same `subject_desc` f-string pattern, duplicated in 3
  report-building functions (Trend Analysis, Process-Property
  Correlation, Machine Settings Optimization Word reports); and the
  Expert Notes aggregate report's link-type label dict ("product_family":
  "Foam Family" -> "Product Family").
- demo_data.py: one unused seed description string, for hygiene (not
  customer-facing - see above).

ai_assistant.py was checked directly and has zero "foam family"
occurrences - the PI3-prompt leak mechanism is entirely the `subject_desc`
strings above (3 pages + 3 report functions), not a hardcoded prompt
template.

Tests: new tests/test_cr18_product_family_terminology.py (11 tests) -
a repository-wide scan asserting every remaining "foam family" hit is on
one of a fixed, reviewed set of internal comment/docstring lines (and a
second test confirming none of those lines actually construct a
customer-facing string); live AppTest scans of all 3 Industrial
Intelligence pages and both Quality pages for the leaked wording; a
direct check of Process Parameter Optimization's action text and shared
radio (the CR's own quoted example); helpers.analysis_unit_picker()'s
family mode driven live through Trend Analysis, proving the pooling
caption reads "product family" AND still pools the correct grade_ids
(business logic unchanged) while the picker's internal mode/link_type
dict values are unchanged; and generated Word report text checks
(build_trend_analysis_report_data's subject_desc, and the Expert Notes
aggregate report's link-type label) both confirmed clean.

Full regression suite: 403 passed, 0 failures, 0 skipped (392
pre-existing + 11 new via test_cr18_product_family_terminology.py). The 2
Flexible-Foam-sibling-app-comparison tests that were conditionally
skipped in every prior CR now run and pass in this environment.
"""

VERSION_0_37_0_NOTES = """
v0.37.0 (2026-08-13): CR-19 (Correct Recipe Version, Product Grade, and
Reference Formulation Display -
CR19_Correct_Recipe_Version_Product_Grade_and_Reference_Formulation_
Display.docx).

What changed: pages/3_Recipe_Version_Record.py's ("Recipes") combined
"Recipe versions" table (built by CR-03, 2026-08-10) put every imported
ReferenceFormulation row's own name inside the column labeled "Product
grade" - prefixed "- <name> (imported reference)". That created a false
semantic relationship: the value shown under "Product grade" for those
rows never came from the Product Grade master at all, it came from the
Reference Formulation library. Confirmed Current Condition in the CR
matches exactly what this app showed.

Fix: the single combined table (still one list, still one Approval Status
filter - the combined-list concept itself is unchanged) now carries three
separate fields instead of one: Type, Product Grade, and Reference
Formulation.
- Plant Recipe rows: Type = "Plant Recipe"; Product Grade = the row's
  real linked FoamGrade.grade_name (resolves exclusively via
  RecipeVersion.foam_grade - never anything else, never "-"); Reference
  Formulation = the linked reference formulation's name if this
  RecipeVersion's pre-existing, optional reference_formulation_id
  ("informed by" FK, added WP5 Wave 4/RHF-015) is set, else "-". That
  link is supplemental context only - Product Grade identity stays
  primary, per CR-19 section 3's row-semantics rule.
- Imported Reference rows: Type = "Imported Reference"; Product Grade =
  "N/A" (literal, always); Reference Formulation = the
  ReferenceFormulation's own name.

No schema change. No change to which RecipeVersion or ReferenceFormulation
records exist, how they're queried, their approval-status governance, or
the structural rule that a ReferenceFormulation can never become an
active production recipe (CR-03 rule 3, still enforced the same way - no
code path links one to RecipeVersion.is_active). Every other page
behavior - Create/Edit/Delete/CSV-Excel-import Recipe, single-active-
recipe-per-grade, row selection and detail rendering for both record
types, Reference Formulation detail/provenance/governance controls - is
untouched; this is purely the version_rows list-comprehension's column
mapping in pages/3_Recipe_Version_Record.py.

Files changed:
- pages/3_Recipe_Version_Record.py: version_rows dict comprehension
  rebuilt with Type/Product Grade/Reference Formulation as distinct
  fields (previously one conflated "Product grade" field); "Recipe
  versions" section caption reworded to state the Product Grade / N/A
  distinction explicitly (CR-19 section 6); module docstring gained a
  CR-19 paragraph documenting the correction and why it was needed,
  alongside the existing CR-03 paragraph it corrects.

Customer-facing consistency (CR-19 section 6): the Recipes page's
combined "Recipe versions" table is the only place in the app where
RecipeVersion and ReferenceFormulation rows are presented together -
confirmed by a repo-wide grep for reference_formulation/
ReferenceFormulation outside db.py, this page, and tests/. No other page
needed a matching fix.

Tests: new tests/test_cr19_recipe_product_grade_reference_display.py (11
tests) - column-structure check (Type/Product Grade/Reference Formulation
present, old "Product grade" gone); a seeded Product Grade master +
linked plant Recipe Version proving the table's Product Grade value
resolves to that exact master record (cross-checked directly against the
FoamGrade row, not just the fixture's own copy of the name); Type mapping
for both Plant Recipe and Imported Reference rows; preservation of an
existing RecipeVersion.reference_formulation_id link, verified both in
the rendered table and at the ORM level; Imported Reference rows showing
"N/A" in Product Grade and their own name in Reference Formulation;
a direct assertion (both against every Imported Reference row's rendered
Product Grade value AND the page's own source text) that Product Grade
never resolves from anything but the FoamGrade relationship; Approval
Status filtering proven to still isolate the correct rows of both types
after the column change; and row selection/detail rendering for both a
plant recipe and an imported reference driven via session_state (AppTest
can't drive the dataframe's own on_select click - same documented
limitation as test_cr03_recipe_consolidation.py). tests/
test_cr03_recipe_consolidation.py's own 9 tests were re-run unmodified
and still pass, confirming CR-03's governance/removal/approval-transition
guarantees are untouched by this display-only correction.

Full regression suite: 412 passed, 2 skipped, 0 failures (401 pre-existing
+ 11 new via test_cr19_recipe_product_grade_reference_display.py). The 2
skips are the pre-existing, environment-conditional Flexible-Foam-
sibling-app-comparison tests in test_cr12_reporting_parity.py (the
sibling app checkout isn't present in this session) - unrelated to CR-19,
zero CR-19 acceptance paths skipped.
"""

VERSION_0_38_0_NOTES = """
v0.38.0 (2026-08-13): WP7 Phase 0 (Contain inherited Flexible Foam
functionality) - the first of six sequential phases of WP7, Production
Run Domain Redesign (per WP7_Production_Run_Domain_Redesign_Converged_
Execution_Approach_for_JC.docx, section 6).

Scope (narrowed during design to 3 concrete concepts, all confirmed to be
structural inheritance from the Flexible Foam/slabstock sibling app's
2026-08-03 fork baseline, not Rigid-relevant controls):
1. The FallplateSectionPosition "Tool Geometry and Fill Configuration"
   sub-workflow (manual entry + CSV/Excel import), on both Setup Data and
   Runtime Data.
2. foaming_mode (FOAMING_MODES controlled vocabulary: LLD/Trough/
   Traverse - a slabstock line-configuration concept).
3. top_flat_system_used (universal boolean).

Governing principle: "Contain, don't delete" - zero schema/DB changes.
FOAMING_MODES, FallplateSectionPosition, and the foaming_mode/
top_flat_system_used columns on ProductionPhase all remain fully defined
in db.py; existing rows and column values are untouched and stay directly
readable off the ORM. Only ACTIVE UI rendering, CSV/Excel import parsing,
report generation, and analytics ranking were removed.

Files changed:
- pages/4_Production_Run_Trial_Record.py: removed the "Foaming mode"
  dropdown, the "Top-flat system in use?" checkbox, and the entire "Tool
  Geometry and Fill Configuration" fall-plate sub-tab from both Setup
  Data's and Runtime Data's Create/Edit forms and CSV import parsing;
  each group's st.tabs() collapsed from 4 tabs to the standard CR-11
  3-tab (Create/Edit-Delete/Import) form. FallplateSectionPosition import
  kept for _delete_phase_cascade's legitimate cascade-delete cleanup of
  historical rows - the only surviving live reference.
- analytics.py: top_flat_system_used removed from PHASE_SETTING_FIELDS,
  PHASE_SETTING_LABELS, BOOLEAN_SETTING_FIELDS (now empty), and
  PHASE1_RIGID_INELIGIBLE_SETTINGS - stronger than the pre-existing
  Phase-1-rigid-conditional exclusion it replaced, since it's now
  out of scope for every grade, not just confirmed-rigid ones.
- reports.py: _setup_vs_finalized_deviations() no longer flags a
  foaming_mode difference between Setup and Finalized; the
  _fallplate_deviations() function and its "fallplate_deviations"
  data-dict key, story/_docx_section render calls were removed entirely
  from the Batch Release report.
- pages/21_Report.py: removed the on-screen "Tool geometry and fill
  configuration changes" table render tied to the removed data key.

Out of scope, confirmed and left untouched (flagged for later WP7
phases or as pre-existing, unrelated findings): conveyor_speed,
air_injection_rate, air_pressure_bar, sidewall_width_mm, mixer_rpm;
demo_data.py's two ProductionPhase(...) seed calls still passing
foaming_mode=/top_flat_system_used= kwargs (dead/unused per CR-18
precedent, columns still exist so no runtime error); quality_issue_
taxonomy.py; pages/31_Production_Equipment.py; gen_uat011_014_reports_v4.py;
gen_uat015_019_live_pages.py.

Tests: new tests/test_wp7_phase0_containment.py (14 tests) - source-grep
evidence that the 4 edited surfaces have zero live (non-comment) code
references to FallplateSectionPosition/FOAMING_MODES/foaming_mode/
top_flat_system_used outside the one confirmed exception
(_delete_phase_cascade); Setup Data and Runtime Data st.tabs() call
sites confirmed collapsed to the 3-tab form; AppTest evidence that
neither tab renders a foaming-mode or top-flat-system widget; a Create-
via-form test and a CSV-import test (using a CSV that still has the two
retired columns, simulating an old template) both confirming the active
path no longer populates those columns; analytics.py unit tests
confirming all four field/label collections exclude top_flat_system_used,
including against a phase that has the value populated; reports.py unit
tests confirming _setup_vs_finalized_deviations() and
build_batch_release_record_data() no longer surface foaming-mode/fall-
plate content, run against a fixture engineered to differ on exactly
those retired fields. The core containment proof
(test_historical_run_with_fallplate_and_foaming_mode_data_still_loads_
and_is_readable) seeds a run with pre-existing foaming_mode/
top_flat_system_used values and an attached FallplateSectionPosition row
directly via the ORM (standing in for real data written before this
change shipped), confirms the live page loads with no exception, and
confirms every one of those values is still directly readable and
unaltered off the ORM afterward.

Also fixed in this batch: tests/test_cr18_product_family_terminology.py's
hardcoded ALLOWED_FOAM_FAMILY_HITS allowlist had 7 stale analytics.py
line numbers (295/309/340/608/683/1169/1334), made stale by this same
batch's explanatory comment insertions shifting every subsequent line in
that file by a consistent +7. Updated to the correct current line numbers
(302/316/347/615/690/1176/1341) - same allowlisted comment text, new
positions, not a new finding.

Full regression suite: 426 passed, 2 skipped, 0 failures (412 pre-existing
+ 14 new via test_wp7_phase0_containment.py). The 2 skips are the same
pre-existing, environment-conditional Flexible-Foam-sibling-app-
comparison tests noted in prior version-notes blocks - unrelated to WP7
Phase 0.
"""

VERSION_0_39_0_NOTES = """
v0.39.0 (2026-08-13) - WP7 Phase 1: Add method-aware schema

JC delivered 6 design artifacts for technical review before writing any
Phase 1 production code (per WP7 governing doc section 10) - see
PI3_Rigid_Foam_Development_Docs/Phase 1/WP7_Phase1_Design_Deliverables.docx.
Charlie's review (WP7_Phase1_Design_Review_Architecture_Decision_for_JC.docx,
2026-08-13) approved the central recommendation - reuse and extend the
dormant WP3f method-aware EAV schema (ProcessSettingDefinition,
ProcessParameterValue, ProductionCycle, ProductionShot, OutputItem) rather
than build a parallel Production Run parameter model - but required 6
structural corrections before/within Phase 1. This release implements
Charlie's corrected architecture, not JC's original (superseded) Phase 1
design proposal.

Schema changes in db.py (all additive - nullable columns or brand-new
tables, zero impact on existing rows; there were zero rows in every WP3f
table in production before this change):

  - ProcessSettingDefinition: added parameter_category (see the new
    PROCESS_PARAMETER_CATEGORIES controlled list) and active. Stays the
    canonical SEMANTIC master only (what a parameter means) -
    production_method_id is now DEPRECATED/DORMANT on this table per
    Charlie's decision doc section 3.1 (left in place, not dropped, but
    no longer authoritative).
  - New ProcessSettingApplicability table (process_setting_
    applicabilities): setting_definition_id, production_method_id
    (nullable), machine_id (nullable), applicable_to_planned/actual,
    controllable, analytics_eligible, min/max override, active. A single
    definition can now legitimately apply to several Production Methods
    and several Production Units/Cells without duplicating the
    definition - this table carries WHERE a parameter applies, separate
    from the definition's WHAT-it-means. NULL/NULL = Global, method set/
    machine NULL = Method-specific, machine set = Unit/Cell-specific.
  - ProcessParameterValue: added source and captured_at (unchanged from
    JC's original proposal, confirmed by Charlie).
  - New ProductionOutputSummary table (production_output_summaries):
    run-level Planned/Actual output quantity and disposition, retaining
    OutputItem as optional item-level detail. Corrected from JC's
    original two-free-text-unit-field proposal to a single controlled
    unit_id (FK to UnitOfMeasure) governing both Planned and Actual, plus
    a controlled disposition (see the new PRODUCTION_OUTPUT_DISPOSITIONS
    list) - per Charlie's decision doc section 3.3.
  - ProductionEvent: added setting_definition_id, raw_material_lot_use_id
    (JC's original proposal) plus quality_observation_id and
    physical_property_result_id (Charlie's addition, decision doc section
    3.5) - all 4 nullable, optional context links, existing event
    behavior unchanged.
  - ComponentStreamReading: production_phase_id is now nullable and a new
    production_run_id FK was added directly (decision doc section 3.4,
    "Decouple Material Metering from ProductionPhase") - Phase 2 will
    write new metering records against ProductionRun; Phase 3 backfills
    production_run_id on historical rows via their existing
    ProductionPhase link; Phase 5 can then drop the active dependency on
    ProductionPhase (which Phase 5 retires) without breaking Material
    Metering history. Every existing row keeps its production_phase_id
    unchanged.

analytics.py: new eligible_process_settings(session, production_method_id,
machine_id=None) helper. Queries ProcessSettingApplicability (not the
deprecated ProcessSettingDefinition.production_method_id) and applies
deterministic precedence for the same setting_definition_id -
Machine-specific > Method-specific > Global - returning exactly one
eligible row per definition. No name-matching, no supersedes_id mechanism
(closes the open question from JC's Phase 1 design deliverables per
Charlie's explicit decision: "Applicability specificity provides
deterministic precedence without duplicate semantic definitions").

Tests: new tests/test_wp7_phase1_method_aware_schema.py (15 tests),
covering Charlie's Phase 1 closeout gate (decision doc section 6) point by
point - one definition serving multiple Methods without duplication via
applicability rows; the Machine > Method > Global precedence proof (3
scenarios) plus a retired-row-never-surfaces guard; Planned/Actual
ProcessParameterValue distinctness with source/captured_at; a structural
assertion that ProcessParameterValue has no independent unit_id (UOM stays
definition-controlled); ProductionOutputSummary's single controlled
unit_id and controlled disposition; ComponentStreamReading's direct
ProductionRun link coexisting with legacy ProductionPhase-linked rows;
ProductionEvent's 4 optional context links resolving correctly while a
legacy-style event with none of them set is unaffected; and a source-grep
proof (parametrized over pages/4, reports.py, and pages 15-19) that none
of the new Phase 1 schema/helper symbols are yet wired into live UI/
report/Intelligence code - Phase 1 stays schema-only, per Charlie's
acceptance item 8 ("No Production Run UI, report, PI3 or Industrial
Intelligence behavior is cut over in Phase 1").

Also corrected in this batch: tests/test_cr18_product_family_terminology.py's
ALLOWED_FOAM_FAMILY_HITS allowlist needed its analytics.py/db.py line
numbers updated again, shifted by this batch's own additions (new
imports, the ProcessSettingApplicability/ProductionOutputSummary comment
blocks, and the eligible_process_settings() function) - same allowlisted
comment/docstring text, new positions, verified against the actual scan
output rather than an arithmetic shift guess.

Full regression suite: 441 passed, 2 skipped, 0 failures (426 pre-existing
+ 15 new via test_wp7_phase1_method_aware_schema.py). The 2 skips are the
same pre-existing, environment-conditional Flexible-Foam-sibling-app-
comparison tests noted in prior version-notes blocks - unrelated to WP7
Phase 1.

Not in this release (still pending): the Supabase migration applying
these schema changes to the shared rigid_foam schema, and the Phase 1
closeout package for Charlie/Stefan.
"""

VERSION_0_40_0_NOTES = """
v0.40.0 (2026-08-14) - WP7 Phase 2: Rebuild Production Run UI

Phase 2 ("Rebuild Production Run UI") has no separate pre-coding design-
artifact review gate under the WP7 governing document (section 10's
"JC Design Deliverables Before Phase 1 Coding" is scoped only to Phase 1),
so this release implements Phase 2 directly against the governing doc's
section 4 (Target Production Run Page Structure) and section 6 (Phase 2
scope/closeout gate: "Implement context-first run creation/editing,
dynamic Planned/Actual process grid, conditional process modules,
environment/observations, normalized material metering, events/
deviations, output and disposition... Close when users can create and
manage runs with only parameters applicable to the selected Method/Unit").

pages/4_Production_Run_Trial_Record.py changes - two new tabs, plus
targeted changes to two existing tabs, additive alongside every existing
legacy Setup/Runtime Data field (none of the fixed mixer_rpm/conveyor_
speed/etc. columns were touched or removed - Phase 4 is when those become
non-authoritative, per Charlie's decision doc section 7):

  - New "Method-Aware Process Settings" tab (governing doc section 4,
    sections C/D "Planned/Actual Process Data, conditional by Method/
    Unit"): driven entirely by analytics.eligible_process_settings(),
    which resolves the WP7 Phase 1 ProcessSettingDefinition/
    ProcessSettingApplicability schema with Machine>Method>Global
    precedence. Shows only the settings applicable to the selected run's
    Production Method/Unit; captures Planned and Actual values as
    ProcessParameterValue rows (source="Manual entry", captured_at set on
    save); shows "no applicable settings" until real definitions/
    applicabilities exist for that Method/Unit, rather than inventing
    content - see the open item below.
  - New "Production Output and Disposition" tab (governing doc section 4,
    section I): create/edit/delete against the WP7 Phase 1
    ProductionOutputSummary table - single controlled unit_id, controlled
    disposition (Released/Quarantined/Rejected/Rework). Additive
    alongside the legacy Runtime Data "Calculated output"
    (compute_runtime_output) section, which stays in place; the governing
    doc's section 8 note that the universal slab/line geometry
    calculation should eventually retire for methods it doesn't apply to
    is a later-phase concern, not addressed by removal here.
  - Material Metering and Actual Usage tab: decoupled from requiring a
    Runtime Data (Finalized) phase to exist first, per Charlie's WP7
    Phase 1 decision doc section 3.4. Component Stream Reading create/
    edit/CSV-import now write production_run_id directly; a Finalized
    phase, if one already exists for the run, is still also linked for
    continuity with the legacy Setup/Runtime Data comparison, but is no
    longer a precondition. The stream-reading listing query and CSV
    import's duplicate-detection were both updated to match on either
    linkage style.
  - Production Events tab: added 4 optional context-link pickers (Related
    process setting / raw material lot use / quality issue / quality test
    result), wired to ProductionEvent's WP7 Phase 1 setting_definition_id/
    raw_material_lot_use_id/quality_observation_id/
    physical_property_result_id columns, on both the Create and Edit
    forms.

cascades.py: delete_production_run_cascade() and
production_run_dependency_counts() updated to also cover
ProcessParameterValue, ProductionOutputSummary, and directly-run-linked
ComponentStreamReading rows (previously only phase-linked stream readings
were covered) - a genuine gap found while implementing the decoupling
above, not explicitly called out in the governing doc, but required so
deleting a run cannot orphan rows created through the new tabs.

Tests: new tests/test_wp7_phase2_production_run_ui.py (5 tests, real
Streamlit AppTest evidence, not just ORM-level checks) - the Method-Aware
Process Settings tab correctly shows nothing until an evidence-based
ProcessSettingDefinition/ProcessSettingApplicability pair is seeded, then
correctly filters to only that setting and saves Planned/Actual values;
Production Output create-then-edit round trip through the real form;
direct UI proof that a Component Stream Reading can be created for a run
with zero ProductionPhase rows (the decoupling, previously only provable
at the ORM layer); a Production Event created with a "Related process
setting" link persists that link. Also updated: test_wp7_phase1_method_
aware_schema.py's test_phase1_schema_not_yet_wired_into_live_surfaces no
longer parametrizes over pages/4 (Phase 2 now legitimately wires that
schema in - it still holds for reports.py and the Industrial Intelligence
pages, which remain Phase 4 territory), and test_cr11_functional_
evidence_group_d.py's stream-reading CSV-import-rejection test was
updated for the new "unknown production_run_id" rejection reason (no
longer "no Finalized phase").

Full regression suite: 445 passed, 2 skipped, 0 failures (440 pre-existing
+ 5 new via test_wp7_phase2_production_run_ui.py). The 2 skips are the
same pre-existing, environment-conditional Flexible-Foam-sibling-app-
comparison tests noted in prior version-notes blocks - unrelated to WP7
Phase 2.

Still open, not resolved by this release: no approved, evidence-based
ProcessSettingDefinition/ProcessSettingApplicability catalogue exists in
production yet - Charlie's WP7 Phase 1 decision doc section 5 explicitly
deferred content like the mixer-rpm-to-Method mapping to a later
evidence-based migration, and that item is still open. Until real
definitions/applicabilities are seeded in production, the Method-Aware
Process Settings tab will correctly show "no applicable settings" for
every real run - this is expected, not a defect, and is called out
explicitly in the WP7 Phase 2 closeout package.

Not in this release (still pending): no schema changes were made in this
release (Phase 2 is UI-only, built entirely on the WP7 Phase 1 schema
already migrated to Supabase), so no new Supabase migration is required;
the WP7 Phase 2 closeout package for Charlie/Stefan.
"""

VERSION_0_41_0_NOTES = """
WP7 Phase 1 Closeout Correction (2026-08-14). Charlie's WP7 Phase 1
Closeout Review (WP7_Phase1_Closeout_Review_Return_to_JC.docx, 14 August
2026) returned Phase 1 as OPEN - structurally close to the approved
architecture, but three material acceptance gaps required completion
before closure, since Phase 2's UI/imports would otherwise build on
data-layer conventions the schema itself did not yet enforce:

2.1 Applicability precedence needs same-scope integrity. Fixed: added
ix_psa_unique_active_scope, a partial/functional unique index on
ProcessSettingApplicability (setting_definition_id, coalesce(production_
method_id, -1), coalesce(machine_id, -1)) WHERE active = true - one
active applicability row per definition per scope (Global, a given
Method, or a given Machine), enforced identically on SQLite (tests) and
Postgres (production) since both support expression-based partial unique
indexes. Retired (active=false) rows are excluded, so the normal soft-
retire-then-replace workflow is unaffected - proven by a direct test.
analytics.eligible_process_settings() also gained a deterministic ORDER
BY as defense-in-depth, so tie-break behavior no longer depends on
unordered database row order even in a hypothetical bypass.

2.2 Controlled categories and output disposition need enforced
validation. Fixed: added SQLAlchemy @validates hooks on
ProcessSettingDefinition.parameter_category and ProductionOutputSummary.
disposition that reject any value outside PROCESS_PARAMETER_CATEGORIES /
PRODUCTION_OUTPUT_DISPOSITIONS through the accepted write path (any ORM
attribute assignment), backed by matching Postgres CHECK constraints
(ck_process_setting_definitions_parameter_category,
ck_production_output_summaries_disposition) for defense-in-depth and
database parity.

2.3 ProcessParameterValue UOM snapshot needs controlled derivation.
Fixed: added a before_insert/before_update SQLAlchemy mapper event that
re-derives (overwrites) ProcessParameterValue.unit from the linked
ProcessSettingDefinition's controlled unit_id immediately before every
flush, regardless of what value was assigned - a caller-supplied
conflicting unit is ignored in favor of the controlled definition, one of
the three resolutions Charlie's review explicitly accepted. Pure
application logic; no schema change needed for this item.

Migration: applied directly to the live rigid_foam Postgres schema
(Supabase project PI3_Plant_Edition) as migration
wp7_phase1_closeout_correction. Pre-migration audit confirmed zero
existing rows in process_setting_applicabilities and
production_output_summaries and zero out-of-vocabulary parameter_category
values, so no dedup/backfill was required before adding the constraints.

Tests: 9 new direct tests added to tests/test_wp7_phase1_method_aware_
schema.py's new section 10 (duplicate Global/Method/Machine applicability
rejected, soft-retire-then-replace still works, eligibility stays
deterministic, invalid parameter_category/disposition rejected, valid
values still accepted, conflicting ProcessParameterValue.unit is
overwritten, and unit derives correctly per-definition when multiple
definitions with different units coexist on one run). tests/
test_cr18_product_family_terminology.py's line-number allowlist was
updated for the line shifts these edits caused in analytics.py/db.py (no
behavior change, same comment/docstring text).

Full regression: 458 passed, 0 skipped, 0 failed (the full suite; this
run also happened to pick up the two normally-skipped Flexible Foam
sibling-app tests as passing, which is environment-dependent and outside
WP7 acceptance either way).

Scope note: this correction batch and the already-implemented WP7 Phase
2 UI (v0.40.0) were both completed in this session before Charlie's
Phase 1 closeout review was read - the "continue with next phase"
instruction predated the review being returned. Phase 2's implementation
was checked against this correction and requires no changes of its own:
it only calls eligible_process_settings() (read-only) and constructs
ProductionOutputSummary/ProcessParameterValue rows through the same ORM
write path these fixes now govern, so it inherits the corrected behavior
automatically. See the WP7 Phase 1 Closeout Correction package and the
WP7 Phase 2 closeout package (delivered together) for the full
reconciliation.
"""

VERSION_0_42_0_NOTES = """
WP7 Phase 2 Closeout Correction (2026-08-14). Charlie's WP7 Phase 2
Closeout Review (WP7 Phase 2 Closeout Review, 14 August 2026) returned
Phase 2 as OPEN with 3 material gaps requiring a targeted correction
package before Phase 2 can close:

Material Gap 1 - numeric zero treated as blank. Fixed: the Method-Aware
Process Settings tab's Planned/Actual number fields for Float/Integer
ProcessSettingDefinitions each gained a companion "Record a ... value"
checkbox, rendered as an independent widget (not wired to the number
field's disabled= state - Streamlit forms don't rerun on a widget
interaction until submit, so a disabled= driven by another form widget's
just-toggled state could never reflect that toggle within one
submission). The checkbox alone determines whether a value is persisted
at save time; the number field's contents are read only when its
checkbox is checked. Planned = 0 / Actual = 0 now save as a real
numeric_value == 0.0 for both Float and Integer, and typing a number
without checking its checkbox leaves that value unset (no row created,
or the existing row deleted) - proven directly for both data types.

Material Gap 2 - legacy Run Context shape. Fixed: ProductionRun gained
run_start/run_end (DateTime), status (String, backed by a new
PRODUCTION_RUN_STATUSES controlled list + CheckConstraint + @validates),
and order_item_reference (String). The Create and Edit Production Run
forms were both rebuilt to walk the corrected operational hierarchy
Plant -> Production Method -> Production Unit or Cell -> Product Grade
(replacing the legacy Grade-first order), with Plant/Method/Unit living
outside their respective st.form(...) blocks (same reasoning as the
checkbox note above - Product Grade's choices depend on the selected
Unit, and forms can't react to an earlier-in-form selection within one
submission). run_start/run_end use the same explicit-checkbox pattern as
Gap 1's numeric fields, decoupled from combine_date_time()'s own
rendering.

Material Gap 3 - absent Cycle/Shot UI. Charlie explicitly rejected the
prior closeout package's "schema support alone is sufficient" reasoning.
Fixed: added ProductionMethod.uses_cycle_shot_operation (Boolean, default
False) and Machine.cycle_shot_operation_override (Boolean, nullable -
None means inherit the Method's default; an explicit True/False overrides
it per-Machine), plus helpers.run_uses_cycle_shot_operation(run) to
resolve the two into one answer for a given run - never inferred from a
Method's or Machine's name, and never seeded True on any live row without
an evidence-based confirmation (same Phase 1 Production Seeding Rule
already governing ProcessSettingApplicability). A new "Cycle / Shot Data"
tab on the Production Run page conditionally renders: a plain explanatory
message (no Create form) when the run's resolved Method/Unit isn't
configured for it, and a real Create-cycle-then-create-shot workflow
(ProductionCycle: cycle_number/Tool/Mixhead/cycle_start/cycle_end/notes;
nested ProductionShot: shot_number/Cavity/Fill point/shot_ts/notes, both
optional-equipment pickers) when it is. cascades.py gained the first-ever
cascade-delete coverage for ProductionCycle/ProductionShot (previously a
pre-existing, undetected gap since no UI had ever written to them).

Migration: applied directly to the live rigid_foam Postgres schema
(Supabase project PI3_Plant_Edition) as migration
wp7_phase2_closeout_correction - ProductionRun.run_start/run_end/status/
order_item_reference + ck_production_runs_status, ProductionMethod.
uses_cycle_shot_operation (NOT NULL DEFAULT false), Machine.
cycle_shot_operation_override (nullable). Verified live via
information_schema.columns after applying.

Tests: 7 new direct AppTest tests added in tests/
test_wp7_phase2_closeout_correction.py - Planned/Actual = 0 persists as
numeric zero for both Float and Integer, an unchecked "Record a value"
checkbox leaves a typed number unset, Create Run persists run_start/
run_end/status/order_item_reference with Product Grade's choices proven
to follow the selected Production Unit or Cell, Edit Run persists the
same 4 fields, and the Cycle/Shot tab both stays absent-with-message for
an unconfigured Method and exposes a real functional create-cycle-then-
create-shot flow for a configured one. One pre-existing test (tests/
test_pm_hierarchy_pages_smoke.py::test_production_run_form_derives_
method_snapshot_from_selected_machine) needed updating for the Create
form's Production Unit or Cell label gaining a "*" (standardizing with
every other required-field label on this form) and its picker moving
outside st.form("add_run") - no behavior regression, same collateral-fix
pattern as this session's prior CR corrections.

Full regression: 465 passed, 0 skipped, 0 failed (full suite).
"""

VERSION_0_43_0_NOTES = """
WP7 Phase 2 Closeout Correction v2 (2026-08-14). Charlie's technical
review of the v0.42.0 correction package (WP7_Phase2_Closeout_Correction_
Review_Return_to_JC.docx) found 2 remaining Material Completion Items
before Phase 2 can close:

Material Completion Item 1 - Edit Run's Plant/Production Method/
Production Unit or Cell pickers did not reactively cascade the way
Create Run's already did. Fixed: moved all three selectboxes (Plant,
Production Method, Production Unit or Cell) out of
st.form(f"edit_run_form_{run.id}") to render as ordinary widgets above
it, mirroring Create Run's existing layout exactly - a change to any one
of them now triggers an immediate rerun, so each downstream picker's
option set (and Product Grade, still inside the form) is always freshly
computed against the current upstream selection before the run is saved,
rather than a user being able to submit a new Plant together with stale
Method/Unit/Grade selections carried over from a previously rendered
chain. Proven directly: a new test switches an existing run's Plant to a
second, fully independent Plant -> Method -> Unit -> Grade chain,
asserts each downstream selectbox's options are scoped to the new chain
only (never contain the original chain's Method/Unit/Grade names) at
each step, and asserts the saved run's plant_id/production_method_id/
machine_id/foam_grade_id all end up on the new chain with none left over
from the original one.

Material Completion Item 2 - Production Output's Planned/Actual quantity
fields collapsed a real zero to NULL. Fixed: applied the same "Record a
... quantity" checkbox pattern already used for Gap 1's process settings
to both the Create and Edit Production Output forms - a companion
checkbox, independent of the number_input's own state, is now the sole
source of truth for whether planned_quantity/actual_quantity is
persisted (value if checked else None), replacing the previous `value or
None` expression that treated a typed 0.0 as blank.

No schema/migration impact - both fixes are Streamlit UI/application-
logic changes only (widget placement and save-handler logic); confirmed
via diff that db.py is unchanged in this correction.

Tests: 1 new direct AppTest test added in tests/
test_wp7_phase2_closeout_correction.py proving the Edit Run reactive
cascade end-to-end across two independent chains; tests/
test_wp7_phase2_production_run_ui.py's existing Production Output
create/edit test updated for the new checkboxes.

Full regression: 466 passed, 0 skipped, 0 failed (full suite).
"""

VERSION_0_44_0_NOTES = """
WP7 Phase 3 (2026-08-14) - Legacy data reconciliation, per the WP7 Phase
1 Design Deliverables doc's section 5/6.3 and Charlie's WP7 Phase 1
Design Review and Architecture Decision, section 3.4/4.

Live-data finding: the rigid_foam Supabase schema currently has ZERO
production_phases rows (confirmed by direct count query before any code
was written) - the CR-04/WP6-S02 database reset left only the minimal
Phase 1 UAT baseline (1 ProductionRun, 0 phases). Phase 3's "migrate
every legacy row" mandate is therefore trivially satisfied for live data
today (nothing to migrate), so this release's real content is building
and proving the reconciliation LOGIC itself - ready and correct for
whenever real legacy data exists - plus completing the schema-level
disposition Charlie's decision doc calls for regardless of data volume.

New module legacy_migration.py implements the WP7 Phase 1 design doc's
"no ambiguity" migration classes only:

Environment mapping - ambient_temperature_c/ambient_humidity_pct reuse
the existing dormant WP3f PS-008/PS-009 ProcessSettingDefinition rows
(categorized parameter_category="Environment" rather than duplicated)
plus a new Global ProcessSettingApplicability row each (controllable=
False, analytics_eligible=False).

Outcome/observation - foam_height_mm/rise_time get new
ProcessSettingDefinition rows PS-078/PS-079 (parameter_category=
"Outcome"), same Global/non-controllable applicability pattern.

Both classes' ProcessParameterValue backfill (Setup phase -> Planned
snapshot, Finalized phase -> Actual) explicitly preserves NULL-vs-zero:
only a genuinely None field is skipped; a recorded 0.0 migrates as a
real numeric_value == 0.0 - proven directly (see Tests below).

ComponentStreamReading.production_run_id backfill - per decision doc
section 3.4, backfills production_run_id on any historical reading that
has a production_phase_id but no production_run_id yet, via its
existing ProductionPhase relationship. Zero live rows needed it.

Quarantine report - air_injection_rate/air_pressure_bar remain
explicitly un-migrated (Charlie's decision doc section 4: "Remain
quarantined for semantic review. No automatic mapping.");
quarantine_air_settings_report() surfaces non-null values for review
only. Zero live rows exist to report.

Explicitly NOT touched by this release, per Charlie's decision doc
section 4 ("Deferred to evidence-based migration" / "Remain under
Method-specific review" - do not seed speculative PM-* mappings):
mixer_rpm, conveyor_speed, sidewall_width_mm (need an evidenced,
approved Production Method mapping that does not exist yet - and there
is currently zero production data to derive that evidence from either),
and ProductionRun.block_reference (needs Charlie's confirmation of its
per-method meaning - a documentation question, not a schema migration).
These remain open items for Charlie in the WP7 Phase 3 closeout package.

Master data added to the live rigid_foam schema (data only, no DDL):
4 new units_of_measure rows (UOM-038 second, UOM-039 millimetre, UOM-040
degree Celsius, UOM-041 percent - none of these plain units existed
before; only compound/domain-specific units did, e.g. UOM-031 "wt%").
PS-008/PS-009 categorized and given controlled units; PS-078/PS-079
created. All 4 given Global ProcessSettingApplicability rows. Applied
directly via SQL (data only, no ALTER TABLE - db.py/schema unchanged in
this release) and verified live via a join query immediately after.

Tests: 7 new direct unit tests in tests/test_wp7_phase3_reconciliation.py
- UOM creation + idempotency, PS-008/PS-009 reuse-not-duplicate,
NULL-vs-zero preservation across both Setup/Planned and
Finalized/Actual snapshots, ComponentStreamReading backfill +
idempotency, quarantine report correctness (report-only, zero
ProcessParameterValue rows created), and the orchestration summary
(both the honest-zero case and a populated case).

Full regression: 473 passed, 0 skipped, 0 failed (full suite).
"""

VERSION_0_45_0_NOTES = """
WP7 Phase 3 Closeout Correction (2026-08-14) - targeted fix for a defect
Charlie found in his v0.44.0/af23f8a review: Environment/Outcome
measurements (PS-008 Ambient temperature, PS-009 Relative humidity,
PS-078 Foam height, PS-079 Rise time) were incorrectly appearing as
enterable "Planned" process settings in the live Method-Aware Process
Settings form, because their Global ProcessSettingApplicability rows had
applicable_to_planned=True and pages/4's rendering had no category
filter - violating the architecture principle that measured outcomes
remain outcomes, separate from controllable process levers.

Charlie's review also clarified that 5 of the 6 legacy classes I had
marked "OPEN" in the original Phase 3 closeout (mixer_rpm, conveyor_speed,
sidewall_width_mm, air_injection_rate, air_pressure_bar) are in fact
properly disposed for closure purposes: zero live values, an explicit
deferred/quarantine policy, and a tested mechanism together satisfy the
Phase 3 gate even with no real data yet - no further action was needed on
those 5. Only ProductionRun.block_reference's live count needed reporting
(1 total run, 0 non-null - closes immediately) and the UI leak needed
fixing.

legacy_migration.py, ensure_environment_outcome_definitions(): new
Global applicability rows for PS-008/009/078/079 now set
applicable_to_planned=False, applicable_to_actual=True (actual-only
capture - these are recorded facts, never planned in advance). A new
correction branch self-heals any pre-existing row created by the
original release (applicable_to_planned=True -> False), reported via a
new applicabilities_corrected count. Idempotent both ways.

legacy_migration.py, backfill_environment_outcome_values(): a legacy
Setup-phase value for one of these 4 fields is no longer migrated as a
"Planned" ProcessParameterValue - it is quarantined (counted in a new
values_quarantined_setup return key, left for manual review) per
Charlie's instruction that Setup-side Environment/Outcome values must
remain observations or enter quarantine, never be reclassified as
Planned settings. Only Finalized-phase values migrate, always as
"Actual". NULL-vs-zero preservation still holds on the Finalized side.

pages/4_Production_Run_Trial_Record.py, tab_method_settings: the eligible
list from analytics.eligible_process_settings() is now filtered to
exclude parameter_category in ("Environment", "Outcome") before
rendering, so these definitions can never appear as Planned/Actual
process-setting inputs even though they remain eligible by
Machine>Method>Global precedence - true Process Setting definitions are
unaffected and continue to render normally.

Live Supabase (rigid_foam schema): the 4 pre-existing Global
applicability rows for PS-008/009/078/079 were corrected directly
(applicable_to_planned: true -> false), verified via a live join query
immediately after. No DDL - data-only correction.
ProductionRun.block_reference: confirmed 1 total run, 0 non-null live -
this class closes per Charlie's "a zero count closes the class
immediately" rule.

Tests: tests/test_wp7_phase3_reconciliation.py - added
test_ensure_definitions_corrects_pre_existing_planned_true_applicability
(self-heal proof), extended the PS-008/009 reuse test with
applicable_to_planned/actual assertions, rewrote the NULL-vs-zero
backfill test for the new Setup-side quarantine behavior (no values ever
migrate as "Planned"), and added a direct AppTest UI regression -
test_method_settings_tab_excludes_environment_outcome_but_shows_process_setting
- proving PS-008/PS-078 never render as process-setting inputs on the
real Streamlit form while an ordinary Process Setting definition renders
normally with both Planned and Actual inputs (Charlie's acceptance
criterion #2, evidenced directly against the UI, not just the ORM).

Full regression: 473 passed, 2 skipped, 0 failed (full suite).
"""

VERSION_0_46_0_NOTES = """
WP7 Phase 4 hybrid reader (2026-08-14) - Phase 4's literal closure gate
(WP7 Phase 1 Design Deliverables, section 6.4: "Close when every active
consumer uses the new architecture as its single source of truth")
cannot be met yet: a live Supabase query confirmed zero 'Process Setting'
category ProcessSettingApplicability rows exist for any of the 5 legacy
fields (mixer_rpm, conveyor_speed, air_injection_rate, air_pressure_bar,
sidewall_width_mm) - Charlie's own WP7 Phase 3 closeout review left their
PM-code/controllability mapping deferred pending his decision and real
production evidence. Per Stefan's direction ("Flag it to Charlie with a
short message, then go hybrid"), this release does two things: flags the
blocker to Charlie (WP7_Phase4_Flag_for_Charlie.docx), and makes the new
architecture an additive second source in the meantime, so nothing
regresses and no further engineering pass is needed once Charlie's
decisions land.

analytics.py: eligible_phase_setting_fields() and run_settings_dataframe()
gained an optional production_method_id-scoped hybrid path. The 5 legacy
fields' behavior is completely unchanged - same list, same order, same
ProductionPhase-column source. New: dynamic_process_setting_field_key()
and _dynamic_process_setting_fields() discover any live, evidence-based
'Process Setting' category ProcessSettingDefinition for one unambiguous
production_method_id (controllable=True, analytics_eligible=True,
data_type in Float/Integer only for this first pass), and append their
field keys (ps_<definition_id>) after the legacy 5. run_settings_dataframe
populates their values from ProcessParameterValue (Actual preferred,
Planned fallback - mirrors the existing Finalized/Setup fallback
pattern). rank_setting_correlations()/rank_setting_optimization() now
pass production_method_id through and resolve a dynamic field's label
from the live definition's own name, not the static PHASE_SETTING_LABELS
dict. A pooled/unscoped caller (production_method_id=None) gets no
dynamic fields at all - matches this function's own pre-existing "don't
guess" convention for the Phase-1-rigid-ineligibility restriction.
reports.py's Batch Release deviation table iterates PHASE_SETTING_FIELDS
directly (not this dynamic helper) and is unaffected, as designed - its
Setup-vs-Finalized paradigm has no natural equivalent in the new model's
Planned-vs-Actual and is deliberately out of scope for this pass.

pages/18_Root_Cause_Assistant.py: fixed a real landmine found during this
work - line ~152 did direct PHASE_SETTING_LABELS[field] indexing inside a
loop over eligible_phase_setting_fields(), which would KeyError the
instant any dynamically-discovered field (not pre-registered in the
static dict) was ever returned. Changed to .get(field, field), matching
the safe pattern pages 17/19 already used. Also now passes
production_method_id=run.production_method_id through to
eligible_phase_setting_fields(), consistent with how it already scopes
run_settings_dataframe() on the line above.

Tests: new tests/test_wp7_phase4_hybrid.py (17 cases) proves (a) nothing
changes today - zero live dynamic data means eligible_phase_setting_fields()/
run_settings_dataframe() are byte-for-byte identical to before this
change, with or without production_method_id passed; (b) the wiring is
real - once a synthetic evidence-based Process Setting definition/
applicability/value is seeded, it surfaces correctly and automatically in
eligible_phase_setting_fields(), run_settings_dataframe() (Actual
preferred, Planned fallback, both proven directly), and rank_setting_
correlations()/rank_setting_optimization()'s label column; (c) correct
exclusion when not controllable, not analytics_eligible, wrong category
(Environment/Outcome), or wrong data_type (String/Boolean); (d) no
guessing when the caller doesn't scope to one production_method_id, even
after live data exists. tests/test_cr18_product_family_terminology.py's
line-number-pinned "foam family" allowlist updated for analytics.py's
new line positions (verified exact hit list, not an arithmetic guess).

Full regression: 490 passed, 2 skipped, 0 failed (full suite) - the 2
skips are pre-existing and unrelated to this change.
"""

VERSION_0_47_0_NOTES = """
WP7 Phase 4 correction (2026-08-14) - Charlie's Architecture Clarification
and Direction to JC rejected the v0.46.0 hybrid outright: "The v0.46.0
hybrid reader keeps the five fixed ProductionPhase fields as an active
source ... That structure conflicts with the frozen Phase 4 source-of-
truth rule and cannot be the Phase 4 end state." His verdict on the
blocker flagged in v0.46.0: Phase 4 is NOT blocked - an empty live
Process Setting catalogue is a valid, honest state, not a reason to keep
a legacy fallback active. This release replaces the hybrid with the pure
method-aware shared reader his execution instruction specifies, and
reverts every consumer the hybrid touched back to pre-hybrid legacy
behavior as a stable interim state while the full page-by-page cutover
(a separate, substantial body of work - see Not yet done, below)
proceeds incrementally.

analytics.py: eligible_phase_setting_fields(), run_settings_dataframe(),
rank_setting_correlations(), and rank_setting_optimization() are reverted
to their exact pre-hybrid behavior - PHASE_SETTING_FIELDS/LABELS/
PHASE1_RIGID_INELIGIBLE_SETTINGS again retain zero active-reader
authority, with no dynamic Process Setting discovery of any kind.
eligible_phase_setting_fields() keeps its production_method_id parameter
(now a harmless, documented no-op) only so existing call sites don't need
a signature change mid-cutover.

New: production_run_process_parameters(session, production_run) - the
canonical single-run shared reader every Phase 4 consumer must read
through going forward. Resolves eligible ProcessSettingDefinition rows
via the existing eligible_process_settings() helper (unchanged Machine >
Method > Global precedence, resolved fresh per run via that run's own
production_method_id/machine_id - never a Method/Global-only shortcut).
An empty live catalogue correctly returns [] - not an error, and never a
ProductionPhase fallback, per Charlie's "allow the live Process Setting
result to be empty" instruction. Returns one dict per eligible
definition: definition_id, controlled_id, name, parameter_category,
data_type, unit_id, unit_symbol (always the definition's own controlled
unit, never caller-supplied), controllable, analytics_eligible,
planned_value, actual_value (typed - numeric/text/boolean, NULL vs zero
preserved correctly), delta (Float/Integer only, both values present),
planned_source/actual_source, planned_captured_at/actual_captured_at.
Actual is the production fact; Planned is separate plan/target context
and never substitutes for a missing Actual. New:
production_run_parameter_dataframe(session, run_ids) - the multi-run
form, calling the single-run reader once per run (genuine per-run Machine
resolution, so two runs on different Units/Cells under the same method
can see different eligible definitions). Returns (values_by_run,
definitions_by_field) - Actual-only values keyed by
dynamic_process_setting_field_key(definition_id) (unchanged from
v0.46.0), plus a union of encountered definitions' metadata for column
labeling/filtering.

Tests: tests/test_wp7_phase4_hybrid.py (17 cases, tested the now-rejected
hybrid) removed and replaced with tests/test_wp7_phase4_shared_reader.py
(28 cases) covering the new reader directly: empty-catalogue honest state,
reader source isolation (legacy ProductionPhase values never leak in,
even when deliberately conflicting), Machine > Method > Global precedence
resolved per-run, NULL vs zero preservation (numeric 0 and boolean False
both preserved, never coerced to None), Planned-never-substitutes-for-
Actual, UOM control (unit_symbol always from the definition's own
relationship), category/eligibility metadata passthrough, and the
multi-run dataframe shape contract. tests/test_cr18_product_family_
terminology.py's line-number-pinned "foam family" allowlist re-verified
against analytics.py's new line positions (exact hit list from the test's
own failure output, not an arithmetic guess).

Full regression: 503 passed, 0 skipped, 0 failed (full suite).

Not yet done (tracked as separate Phase 4 work): the 8 remaining consumer
cutovers (Overview/output KPIs to ProductionOutputSummary, Batch Release/
Conformance report, generated reports, PI3 Production Run context, Root
Cause Assistant, Trend Analysis, Process-Property Correlation, Process
Parameter Optimization, shared CSV/Excel exports), a static dependency
scan classifying every remaining legacy reference, the consumer-specific
gates of Charlie's 11-gate test suite (output source via
ProductionOutputSummary, PI3 context, report row generation), and the
Phase 4 closeout package - proceeding incrementally, matching how every
prior WP7 phase was actually delivered.
"""

VERSION_0_48_0_NOTES = """
WP7 Phase 4: cut over Overview/output KPIs to ProductionOutputSummary
(2026-08-14), per Charlie's Downstream Reader Cutover Execution
Instruction section 6: "ProductionOutputSummary becomes the active output
fact. Overview, reports and PI3 read its Actual quantity and controlled
UOM." analytics.compute_runtime_output() (the conveyor-speed x
tunnel-width x foam-height geometry formula) loses universal KPI
authority as of this release - it remains only as the Production Run
page's own legacy "Calculated output" display in the Runtime Data tab
(unaffected, not in the Phase 4 consumer matrix, still explicitly
labeled as legacy there).

analytics.py: added ProductionOutputSummary/UnitOfMeasure to the db
import block. New production_run_output_summary(session, production_run)
- the single-run shared reader (accepts a ProductionRun instance or id;
returns None for a nonexistent run or one with no recorded output row,
never inferred from geometry; otherwise planned_quantity, actual_quantity,
unit_id, unit_symbol, disposition, disposition_notes). New
production_output_totals(session, run_ids) - the multi-run aggregator
Overview reads: sums actual_quantity across runs grouped by unit_id
(never combined across different units, per CR-02 section 8's existing
"no meaningless mixed-unit total" rule, now enforced generically instead
of relying on one formula implying one unit), and separately reports how
many of the requested runs have no ProductionOutputSummary row at all
versus one with no Actual quantity recorded yet (both read as "missing",
neither ever backfilled from Planned or geometry).

app_rigid_foam.py: the Overview page's "Output Quantity and Unit" KPI
card now reads analytics.production_output_totals() instead of looping
compute_runtime_output() over each scoped run's Finalized phase. This
also lifts the old CR-02 restriction requiring a single Production Method
to be selected before any figure would show - that restriction existed
only because the retired geometry formula could only ever produce a
value for continuous, tunnel-based production; ProductionOutputSummary
rows can exist for any method's runs. The card still explains itself
instead of guessing when the scoped runs' recorded output spans more than
one unit, and shows nothing (with an explanatory caption) when no output
has been recorded yet for the period. Dropped the now-unused
ProductionPhase import from app_rigid_foam.py.

Tests: new tests/test_wp7_phase4_overview_output_cutover.py (14 cases) -
production_run_output_summary()'s None-safe behavior for a missing run/
row, production_output_totals()'s empty-input/single-unit-sum/multi-unit-
separation/missing-vs-Planned-only-row/sort-by-run-count behavior, and
live AppTest evidence that the Overview KPI card reads the new source,
no longer requires a single Production Method selected, and explains a
mixed-unit period instead of summing across units.
tests/test_cr18_product_family_terminology.py's line-number-pinned "foam
family" allowlist re-verified against analytics.py's new line positions.

Full regression: 517 passed, 0 skipped, 0 failed (full suite; one
transient failure seen under a parallel/xdist run was a shared-database
worker collision, not a real regression - confirmed by an isolated rerun
of that exact test passing clean).

Not yet done: the 8 remaining consumer cutovers (Batch Release/
Conformance report, generated reports, PI3 Production Run context, Root
Cause Assistant, Trend Analysis, Process-Property Correlation, Process
Parameter Optimization, shared CSV/Excel exports), a static dependency
scan, the remaining Charlie 11-gate test coverage, and the Phase 4
closeout package - proceeding incrementally.
"""

VERSION_0_49_0_NOTES = """
WP7 Phase 4: cut over Batch Release/Conformance report to the shared
reader (2026-08-14), per Charlie's Downstream Reader Cutover Execution
Instruction section 6 ("Overview, reports and PI3 read [Production
OutputSummary's] Actual quantity and controlled UOM").

reports.py: replaced the retired _setup_vs_finalized_deviations(session,
setup_phase, finalized_phase) - which diffed PHASE_SETTING_FIELDS between
the Setup and Finalized ProductionPhase rows - with
_process_parameter_deviations(session, run_id), which reads exclusively
through analytics.production_run_process_parameters(): an empty live
Process Setting catalogue now correctly yields no deviations (never
falling back to the retired phase-field list), a Float/Integer Planned-
vs-Actual difference within the existing epsilon tolerance is still
skipped, a one-sided value (only Planned or only Actual recorded) is
still surfaced, and the returned dict keys are now "Setting"/"Planned"/
"Actual" (previously "Setting"/"Setup (planned)"/"Finalized (actual)" -
no existing test or caller depended on the old names). build_batch_
release_record_data() now also calls the new production_run_output_
summary(session, run_id) reader unconditionally (not gated by has_flags,
since disposition is a core release decision this report exists to
surface) and returns it under a new "output_summary" key - None when the
run has no ProductionOutputSummary row, never inferred from the retired
compute_runtime_output() geometry formula.

render_batch_release_record_pdf()/render_batch_release_record_docx() and
pages/21_Report.py's Batch Release tab now render this new "Production
output" section (Planned/Actual quantity with unit, disposition,
disposition notes; an honest "not recorded yet" message when the run has
no summary row) - previously the report showed no output-quantity
information at all.

Tests: new tests/test_wp7_phase4_batch_release_cutover.py (12 cases) -
_process_parameter_deviations()'s empty-catalogue/epsilon-skip/real-
deviation/one-sided-value behavior and its "Setting"/"Planned"/"Actual"
keys, build_batch_release_record_data()'s new output_summary field (None
when unrecorded, populated and shown regardless of has_flags), and live
AppTest + direct PDF/Word render evidence for both the "no output
recorded" and "output recorded" states. Corrected tests/
test_wp7_phase0_containment.py::test_setup_vs_finalized_deviations_no_
longer_flags_foaming_mode, which called the now-retired function by name
- it now calls _process_parameter_deviations(session, run_id) instead,
preserving the same foaming-mode/top-flat assertion (structurally
guaranteed by the shared reader, which only ever returns catalogued
ProcessSettingDefinition rows).

Full regression: 529 passed, 0 skipped, 0 failed (full suite, run via
pytest-xdist).

Not yet done: the 7 remaining consumer cutovers (generated reports, PI3
Production Run context, Root Cause Assistant, Trend Analysis, Process-
Property Correlation, Process Parameter Optimization, shared CSV/Excel
exports), a static dependency scan, the remaining Charlie 11-gate test
coverage, and the Phase 4 closeout package - proceeding incrementally.
"""

VERSION_0_50_0_NOTES = """
WP7 Phase 4: cut over PI3 Production Run context to the shared reader
(2026-08-14), plus a pre-existing cross-product data-scoping defect
discovered and corrected along the way, per Charlie's Downstream Reader
Cutover Execution Instruction section 6.

Generated reports (task #974): grepped every report builder in
reports.py for the retired ProductionPhase / PHASE_SETTING_FIELDS /
PHASE_SETTING_LABELS / PHASE1_RIGID_INELIGIBLE_SETTINGS /
compute_runtime_output() readers. The Batch Release/Conformance report
(cut over in v0.49.0) was the only one that ever referenced them - Period
Summary, Trial Closeout, Recipe Formulation, Where Used, Sample, Quality
Test, Quality Issue, PI3 Q&A, Recipe Optimization, Trend Analysis,
Correlation, Root Cause, Machine Settings, Expert Notes and WP3
Conformance never touched them. No code changes required; task closed as
satisfied by v0.49.0.

PI3 Production Run context (task #975): while reviewing the 5 curated
Supabase views backing PI3's free-form "Ask PI3" SQL tool
(v_pi3_production_runs, v_pi3_property_results, v_pi3_recipe_composition,
v_pi3_stream_readings, v_pi3_quality_issues - see pi3_query_tool.py),
found all 5 were still querying unqualified table names (production_runs,
foam_grades, recipe_versions, machines, etc.) that resolve to the
flexible-foam app's tables in Postgres' public schema, not this app's own
rigid_foam schema - leftover from the app this project was cloned from,
never rebuilt when the rigid_foam schema was created. Confirmed via
information_schema.tables that parallel tables exist in both schemas, so
this was a real cross-product data-scoping defect (wrong/empty results
for rigid-foam PI3 users, not just a stale-formula issue), not merely a
Phase 4 cutover gap. Flagged to Stefan, who approved rebuilding the views
immediately.

Rebuilt all 5 views directly in Supabase (project aazkdsqpytjciiqtvnfj) to
query rigid_foam.* tables. v_pi3_production_runs now also carries
planned_quantity, actual_quantity, output_unit_symbol, disposition and
disposition_notes from rigid_foam.production_output_summaries (left-
joined, so a run with no ProductionOutputSummary row still appears with
those columns null) - giving PI3 the same "read ProductionOutputSummary's
Actual quantity and controlled UOM" behavior Charlie's instruction
requires of every consumer, never the retired compute_runtime_output()
geometry formula. The other 4 views were updated to join through the
rebuilt v_pi3_production_runs and rigid_foam.* tables instead of their
public-schema counterparts, preserving their existing column sets.
GRANT SELECT on all 5 views and GRANT USAGE on the rigid_foam schema to
the restricted pi3_readonly role were re-applied as part of the same
migration.

Verified via row-count and content queries against all 5 rebuilt views
(production_runs: 1 row; property_results: 1; quality_issues: 0;
recipe_composition: 5; stream_readings: 0 - consistent with the current
sparse UAT baseline). Could not verify via SET ROLE pi3_readonly (the
migration tool's connection isn't a superuser or role member and got a
permission-denied error attempting it) - this is a verification-tooling
gap, not a defect: the GRANT statements executed successfully as part of
the same transaction the row-count checks confirmed, and the app's real
PI3_READONLY_DATABASE_URL connection authenticates as pi3_readonly
directly rather than via SET ROLE.

pi3_query_tool.py: updated the module docstring's description of the 5
views to document the defect and the fix (previously said the views
"mirror the same joins analytics.py already gets right" - true of the
join shape but silent on which schema they hit). No other code in this
module changed: ALLOWED_VIEWS, _validate_select(), _recompute_live_pass_
fail() and run_plant_query() are all schema-agnostic (they operate on
view names and returned column names, never on which underlying schema a
view's definition queries), so none of them carried the defect or needed
a fix themselves. No new pytest coverage was added for this specific fix
- the existing suite runs against local SQLite with no live-Supabase test
path for this module, and the correction is entirely in the Supabase view
definitions; verification is the row-count evidence above plus this
changelog entry.

Full regression: 529 passed, 0 skipped, 0 failed (full suite, run via
pytest-xdist) - unchanged from v0.49.0 since no application logic changed,
confirming the docstring-only edit didn't disturb anything.

Not yet done: Root Cause Assistant, Trend Analysis, Process-Property
Correlation, Process Parameter Optimization and shared CSV/Excel export
cutovers, a static dependency scan, the remaining Charlie 11-gate test
coverage, and the Phase 4 closeout package - proceeding incrementally.
"""

VERSION_0_51_0_NOTES = """
WP7 Phase 4: cut over Root-Cause Assistant to the shared reader
(2026-08-14), per Charlie's Downstream Reader Cutover Execution
Instruction.

pages/18_Root_Cause_Assistant.py: the run-vs-prior-run "What was
different" diff's process-setting comparison now reads through
analytics.production_run_parameter_dataframe(session, [run_id, prior_id])
- the shared reader's multi-run form - instead of the retired
PHASE_SETTING_FIELDS / eligible_phase_setting_fields() /
PHASE_SETTING_LABELS combination, which read ProductionPhase directly and
retained zero active-reader authority under Phase 4. analytics.
run_settings_dataframe() is still used, unchanged, for identity/candidate-
selection columns only (run_id, run_date, recipe_version, machine,
production_method) - that was never a legacy-reader concern, since those
columns come from ProductionRun itself, not ProductionPhase's process-
setting fields.

The new comparison loop is scoped to parameter_category == "Process
Setting" only - the same Environment/Outcome exclusion pages/4's own
Method-Aware Process Settings tab already applies (WP7 Phase 3
correction) - so a measured ambient/outcome reading can never be reported
here as a "setting that shifted", only a genuine controllable process
lever. Only Actual values are compared (production_run_parameter_
dataframe's values_by_run only ever carries Actual - Charlie's "Planned
never substitutes for missing Actual" rule), matching the retired loop's
implicit reliance on Finalized-phase (i.e. actual) values. Each run's
eligible catalogue is resolved through its own Machine > Method > Global
precedence, already apples-to-apples here since both runs come from
settings_df, itself scoped to the flagged run's own Production Method
(the pre-existing isolation rule, unaffected by this cutover).

New capability, not present in the retired PHASE_SETTING_FIELDS list
(numeric/boolean-only): the loop now branches on the live catalogue's own
data_type - Float/Integer keeps the existing percentage-change wording
and 2% threshold; Boolean reports a plain "changed: No -> Yes"/"Yes ->
No"; String reports "changed: <old> -> <new>". reports.py's
build_root_cause_report_data()/render_root_cause_report_docx() needed no
changes - they already consumed the page's own changes/setting_shifts
lists generically, never re-deriving them from PHASE_SETTING_FIELDS
themselves.

Tests: new tests/test_wp7_phase4_root_cause_cutover.py (7 cases) - a
genuine Float Process Setting shift is reported with correct percentage
wording from the shared reader; an Environment-category definition that
also differs between the two runs is proven excluded (not merely
untested); Boolean and String Process Setting changes are reported via
the new non-numeric branches; the Root-Cause Comparison Report's Word
download renders end-to-end (the page calls render_root_cause_report_docx()
eagerly to populate its download_button, so a clean page load already
proves the full pipeline); identical settings still yield the existing
"No meaningful difference" message; and the pre-existing Production
Method isolation rule (a prior run under a different method is never
offered as the comparison baseline) still holds after the reader swap.
Re-ran the 3 pre-existing tests that already exercise this page
(test_cr12_reporting_parity.py, test_cr12_report_scope_isolation.py,
test_flat_pm_propagation_smoke.py) unchanged and green.

Full regression: 536 passed, 0 skipped, 0 failed (full suite, run via
pytest-xdist).

Not yet done: Trend Analysis, Process-Property Correlation, Process
Parameter Optimization and shared CSV/Excel export cutovers, a static
dependency scan, the remaining Charlie 11-gate test coverage, and the
Phase 4 closeout package - proceeding incrementally.
"""

VERSION_0_52_0_NOTES = """
WP7 Phase 4: cut over Process-Property Correlation (#978) and Process
Parameter Optimization (#979) to the shared reader (2026-08-14), per
Charlie's Downstream Reader Cutover Execution Instruction. Trend Analysis
(#977) was reviewed and confirmed already out of scope in v0.51.0 - it has
no process-parameter read path at all (pure PhysicalPropertyResult-based
SPC), so no code changed there this batch.

analytics.py: merged_run_property_dataframe(), rank_setting_correlations(),
and rank_setting_optimization() rewritten to source process-setting facts
exclusively through analytics.production_run_parameter_dataframe(), never
through ProductionPhase or the retired PHASE_SETTING_FIELDS/
PHASE_SETTING_LABELS/BOOLEAN_SETTING_FIELDS/eligible_phase_setting_fields()
combination, which retain zero active-reader authority under Phase 4.
merged_run_property_dataframe() now returns a
(merged_dataframe, definitions_by_field) tuple instead of a bare
DataFrame - definitions_by_field is the live, method-aware
{field_key: {"label", "data_type", "parameter_category", ...}} map sourced
from the shared reader, filtered to parameter_category == "Process
Setting" and data_type in (Float, Integer, Boolean) (String excluded - no
numeric meaning for correlation/optimization). rank_setting_correlations()
and rank_setting_optimization() both unpack that tuple and iterate
definitions_by_field for their field/label/data_type columns instead of
the old static dicts, so a dynamic "ps_<definition_id>" field key (which
has no entry in any static dict) now resolves correctly everywhere. Both
ranking functions gained an explicit empty-columns-DataFrame return path
for the no-data case (previously implicit). format_setting_range()'s
signature changed from (field, series) to (is_boolean, series) - the
Boolean/non-Boolean branch is now decided by the caller from the live
data_type map, not a static field-name set membership test.

pages/17_Process_Property_Correlation.py and pages/19_Machine_Settings_
Optimization.py: removed the PHASE_SETTING_LABELS / BOOLEAN_SETTING_
FIELDS imports; both pages now build a field_labels (and, on page 19,
field_data_types) dict from the ranked DataFrame's own "field"/"label"/
"data_type" columns immediately after computing `ranked`, and use that for
every selectbox format_func, chart axis label, and Boolean-branch check
that previously read the static dicts. Both pages' merged_run_property_
dataframe() call sites updated for the new tuple return. reports.py needed
no changes - build_correlation_report_data() and build_machine_settings_
report_data() already consumed only label/n/correlation/best_range/*
columns from the ranked DataFrame passed in, never "field" or the two
retired static dicts.

Fixture gap found and fixed: tests/test_cr12_reporting_parity.py's shared
rich_fixture (used by every CR-12 reporting-parity test in that file) only
ever seeded process settings through the legacy ProductionPhase columns
(mixer_rpm/conveyor_speed/air_pressure_bar), never through the dynamic
ProcessSettingDefinition/ProcessParameterValue catalogue the shared reader
now exclusively reads - so after this cutover, pages 17/19's ranked
correlation table came back empty against that fixture and both pages
st.stop()'d before reaching their Word-download button, failing
test_process_property_correlation_report_generates and
test_machine_settings_optimization_report_generates. Fixed by seeding one
Process Setting ProcessSettingDefinition (mirroring the existing mixer_rpm
values, scoped to the fixture's Production Method via
ProcessSettingApplicability) alongside the existing ProductionPhase row for
each of the fixture's 10 runs, per the seeding pattern already established
in tests/test_wp7_phase4_root_cause_cutover.py's _seed_definition/
_add_actual helpers. The legacy ProductionPhase seeding was left in place
unchanged (other, still-legacy-reading fixtures/tests in the same file
depend on it).

Tests: re-ran the full 6-file targeted subset (test_cr18_product_family_
terminology.py, test_cr12_reporting_parity.py, test_wp7_phase4_shared_
reader.py, test_flat_pm_propagation_smoke.py, test_cr12_report_scope_
isolation.py, test_wp7_phase4_root_cause_cutover.py) - 91 passed, 0
failed. tests/test_cr18_product_family_terminology.py's ALLOWED_FOAM_
FAMILY_HITS allowlist updated for the line-number shift this batch's
analytics.py/pages 17/19 edits caused (mechanical maintenance step, no
behavior change - see that test file's own comments for the running
history of this shift).

Full regression: 536 passed, 0 skipped, 0 failed (full suite, run via
pytest-xdist).

Not yet done: shared CSV/Excel export cutover, a static dependency scan,
the remaining Charlie 11-gate test coverage, and the Phase 4 closeout
package - proceeding incrementally.
"""

VERSION_0_53_0_NOTES = """
WP7 Phase 4 (2026-08-14): shared CSV/Excel export scoping (#980) and the
static dependency scan (#981), which found and fixed a real gap in the
Process-Property Correlation / Process Parameter Optimization cutover.

#980 finding: this app has no CSV/Excel EXPORT (download) path anywhere -
grepped app-wide (pages/, helpers.py, reports.py) for to_csv(, to_excel(,
text/csv, spreadsheetml: zero matches outside tests/. The v0.31.0-era
Excel-removal batch (#478/#479) already removed every Download-Excel
button app-wide; every remaining export is Word-only. The only surviving
CSV/Excel functionality is IMPORT (upload), which writes legacy
ProductionPhase columns directly - a capture/write path, never a
downstream reader, so out of Charlie's Downstream Reader Cutover scope.
No code changed for #980, same "confirmed out of scope" pattern as #977
Trend Analysis.

#981 static dependency scan: grepped every remaining reference to
PHASE_SETTING_FIELDS/PHASE_SETTING_LABELS/PHASE1_RIGID_INELIGIBLE_
SETTINGS/eligible_phase_setting_fields/compute_runtime_output/
BOOLEAN_SETTING_FIELDS across the whole app (excluding tests/version.py).
Every hit outside analytics.py's own definitions is either a comment/
docstring documenting the cutover history, or one of two deliberately-
retained non-reader exceptions Charlie's execution instruction and the
WP7 Phase 2 governing doc already classify as out of scope: pages/4's own
legacy Setup/Runtime Data capture UI (still the write path for
ProductionPhase.mixer_rpm/etc, CSV imports included) and its "Calculated
output" display (analytics.compute_runtime_output(), explicitly flagged
"for eventual retirement" but not removed by Phase 2, never a KPI/report
authority since #972). run_settings_dataframe() itself still iterates
PHASE_SETTING_FIELDS internally, but its only two live callers
(analytics.merged_run_property_dataframe() and pages/18's Root Cause
Assistant) were verified to read ONLY its identity columns (run_id,
run_date, recipe_version, machine, production_method), never its legacy
settings columns - confirmed by re-reading both call sites line-by-line,
not just by test coverage.

Real gap found and fixed during this scan: merged_run_property_dataframe()
(analytics.py, cut over in v0.52.0) filtered its definitions_by_field by
parameter_category and data_type only - it never checked the winning
applicability's controllable/analytics_eligible flags. Charlie's execution
instruction section 3 requires both Process-Property Correlation and
Process Parameter Optimization to use "Actual ProcessParameterValue rows
whose winning applicability is controllable=True and analytics_
eligible=True", and section 11's "Optimization eligibility" required test
gate states explicitly: "A definition with analytics_eligible=False or
controllable=False is excluded from optimization/correlation even when
values exist." Before this fix, a definition with either flag False would
still have appeared in both pages' rankings if it had recorded Actual
values - the shared reader passes both flags through as metadata (by
design, so different consumers can apply different rules) but never
pre-filters on them, and the original v0.52.0 filter never added that
check. Fixed by adding `meta["controllable"] and meta["analytics_
eligible"]` to merged_run_property_dataframe()'s definitions_by_field
filter, so the fix applies to both rank_setting_correlations() and
rank_setting_optimization() (both consume this shared helper).

New tests: tests/test_wp7_phase4_correlation_optimization_cutover.py (5
cases) - a Process Setting with analytics_eligible=False is excluded from
both rankings despite having recorded values; a Process Setting with
controllable=False is excluded the same way; an Environment-category
definition is excluded (category isolation); the merged dataframe's
dynamic field-key columns never carry a legacy ProductionPhase value
(reader source isolation, direct proof beyond the existing shared-reader-
level test); both pages 17 and 19 load cleanly and show only the eligible
setting's label, with their Word-download buttons rendering. tests/
test_cr18_product_family_terminology.py's ALLOWED_FOAM_FAMILY_HITS
allowlist updated for the resulting analytics.py line-number shift
(mechanical maintenance, no behavior change).

Full regression: 540 passed (536 + 4 new tests app-wide net; the 5th new
test replaces coverage already counted), 0 skipped, 0 failed via plain
pytest. Under pytest-xdist (-n 4) one unrelated, pre-existing test
(tests/test_wp6s09_rigid_sample_dimension_fields.py) intermittently fails
- confirmed via git stash that this batch's changes are not the cause
(the pre-existing v0.52.0 commit alone is clean under -n 4; adding this
batch's new test file shifts pytest-xdist's file-to-worker assignment
and exposes a cross-file st.cache_data key collision between two
otherwise-unrelated test files, seeded database IDs colliding across
worker processes - the same class of flake test_cr12_reporting_parity.py's
own module docstring already documents and works around for its own
fixture). The failing test passes cleanly every time when run alone, and
when run serially (no -n flag) alongside its actual neighbors and this
batch's new file. Not a functional regression; flagged here for
visibility rather than silently ignored.

Not yet done: the remaining Charlie 11-gate test coverage audit (this
batch closed gate 7 "Optimization eligibility" and strengthened gates 1
"Reader source isolation" and 6 "Category isolation" for pages 17/19
specifically; a full gate-by-gate matrix across every Phase 4 consumer is
still open) and the Phase 4 closeout package - proceeding incrementally.
"""

VERSION_0_54_0_NOTES = """
WP7 Phase 4 targeted completion, Item 1 (2026-08-14) - per Charlie's
"WP7 Phase 4 Closeout Review Return to JC" (the delivered Phase 4 closeout
package was returned "OPEN - targeted completion only", not accepted;
3 material items required before Phase 4 can formally close). This batch
closes Item 1: the Batch Release Record / generated report's process-data
contract.

1.1 Definition-driven, not deviations-only: the retired
_process_parameter_deviations() only emitted a row when Planned != Actual
for a recorded pair - an eligible ProcessSettingDefinition with no
recorded value at all, or with an unchanged Planned/Actual pair, was
silently omitted. Charlie's review called this out directly: the section
must be definition-driven, showing every eligible definition regardless of
whether a value was ever recorded. Replaced with
_process_parameter_report_rows(), which iterates every row
production_run_process_parameters() returns and buckets by category
(Process Setting / Environment / Outcome) rather than filtering on
Planned != Actual. Each row now carries Parameter, Category, Planned,
Actual, numeric Delta, canonical UOM, Limit, and Conformance - the full
column set Charlie's review specified. Environment and Outcome are now
separate report sections from Process Settings (previously Environment/
Outcome parameters had no dedicated section in this report at all).

1.2 Controlled acceptance limits: previously the report carried no
Pass/Fail signal against any approved limit at all. Added
_effective_limit() (ProcessSettingApplicability.min_value_override/
max_value_override win over ProcessSettingDefinition.min_value/max_value
when populated, per Charlie's explicit override-beats-default rule) and
_conformance_text() (Pass/Fail only computed when an effective limit
exists and an Actual value is recorded; "Informational (no approved
limit)" when no limit exists at either level, so the absence of a
controlled limit is never silently read as a Pass; "No Actual value
recorded" when a limit exists but nothing was captured, so that state is
never silently read as a Pass either).

1.3 Removed the live ProductionPhase dependency from Material Metering:
build_batch_release_record_data()'s stream-reading query previously
located a Finalized ProductionPhase for the run and queried
ComponentStreamReading by production_phase_id - Batch Release's last
direct live read of the structure WP7 Phase 5 retires. Replaced with a
direct query on ComponentStreamReading.production_run_id (the Phase 1
run-anchor column), matching Phase 2's own Material Metering capture UI
which already writes against production_run_id. New direct-evidence test
proves this: writes a ComponentStreamReading with production_phase_id
left NULL for a run that has zero ProductionPhase rows at all, and
confirms it still surfaces in the report.

New/updated tests: tests/test_wp7_phase4_batch_release_cutover.py - 8 new
tests on _process_parameter_report_rows() (definition-driven inclusion,
near-equal pairs no longer epsilon-skipped, full column set, one-sided
Actual-only values, informational-when-no-limit, override-beats-default,
Pass when within limit, "no Actual recorded" not silently Pass) plus 1 new
direct-evidence test for the ProductionPhase-free metering read.
tests/test_wp7_phase0_containment.py updated for the renamed function and
the 3-bucket return shape. tests/test_cr18_product_family_terminology.py's
ALLOWED_FOAM_FAMILY_HITS allowlist updated for the resulting analytics.py
line-number shift (mechanical maintenance, no behavior change).

Full regression: 545 passed, 0 skipped, 0 failed (pytest-xdist -n 4).

Not yet done: Item 2 (Root Cause Assistant context - Environment/Outcome
sections, run-linked metering/events/QC as investigation facts) and Item 3
(method-aware Trend Analysis acceptance path, wrongly marked out of scope
in the original closeout) - proceeding incrementally per Charlie's
targeted closure gate.
"""

VERSION_0_55_0_NOTES = """
WP7 Phase 4 targeted completion, Item 2 (2026-08-14) - per Charlie's
"WP7 Phase 4 Closeout Review Return to JC". This batch closes Item 2:
Root-Cause Assistant context. Charlie's exact requirement: "must add
Environment/Outcome as separate context sections (excluded from
controllable-setting ranking but visible), and include run-linked
material usage/metering, Production Events, and QC context as
investigation facts separated from inferred hypotheses."

2.1 Environment/Outcome context, excluded from ranking: added
reports.environment_outcome_context_rows(), which reuses the shared
reader's already-computed definitions_by_field/current_values/
prior_values (the same data the page's "What was different" comparison
already builds) and buckets Environment- and Outcome-category parameters
into their own display rows. The existing "What was different" loop is
untouched and stays scoped to parameter_category == "Process Setting"
only - Environment/Outcome never enter the controllable-setting ranking
or hypothesis logic, but now render in a dedicated "Environment / Outcome
context" section on the page, captioned as recorded context, not a
counted change.

2.2 Investigation facts, separated from PI3's inferred hypothesis: added
reports.root_cause_investigation_facts(), which reads material usage/
metering (ComponentStreamReading, via production_run_id only - the same
Item 1.3 pattern, proven again here with a direct-evidence test writing a
reading with production_phase_id=None against a run with zero
ProductionPhase rows), Production Events, and QC context (other quality
test results plus quality issues logged on the run, including the
flagged one) for the flagged run. Reuses reports._is_rigid_grade()/
compute_conformance_report()/compute_pass_fail() unchanged, so QC
Pass/Fail reads identically to Batch Release for the same run. Rendered
in a dedicated "Investigation facts" section on the page, positioned
before the deterministic Root-Cause Comparison Report and the "Use PI3"
hypothesis button, and captioned "recorded data ... not inferred, not
hypotheses."

2.3 PI3 prompt integration: the "Use PI3 to reason about this" prompt now
appends a facts summary (counts/lines drawn from the same investigation
facts data, not re-derived) with an explicit instruction that these are
facts, not hypotheses, and must not be presented as a cause on their own.

2.4 build_root_cause_report_data() extended with optional env_outcome_rows/
investigation_facts kwargs (default to empty structures, per the project's
existing never-re-derive convention) and 6 new keys so both the PDF and
DOCX Root-Cause report carry the same 2 new sections as the on-screen
page.

New/updated tests: tests/test_wp7_phase4_root_cause_cutover.py - 6 new
tests (Environment/Outcome bucketing and category-separation, on-page
rendering as context not a setting change, metering-via-production_run_id-
only direct evidence, Production Events + QC context facts, on-page
Investigation-facts/Report-section separation, empty-facts render as
"no data" rather than crashing) plus 1 pre-existing test updated for the
new Environment/Outcome section's on-page presence (scoped its assertion
to the portion of the page before the new section, since the category is
now legitimately visible there while still staying out of the setting-
change ranking it asserts against).

Full regression: 550 passed, 0 skipped, 1 failed under pytest-xdist -n 4
(tests/test_wp6s09_rigid_sample_dimension_fields.py - confirmed a
pre-existing parallel-worker isolation flake, unrelated to this batch:
passes standalone both before and after this change, and touches no file
this batch modified).

Not yet done: Item 3 (method-aware Trend Analysis acceptance path) and
the targeted closure gate (re-run dependency scan + full regression +
corrected closeout package) - proceeding per Charlie's targeted closure
gate.
"""

VERSION_0_56_0_NOTES = """
WP7 Phase 4 targeted completion, Item 3 (2026-08-14) - per Charlie's
WP7 Phase 4 Closeout Review Return to JC. This batch closes Item 3: Trend
Analysis acceptance path. Charlie's exact requirement: "The closeout
package classifies Trend Analysis as out of scope because the current
page is property-result SPC only. The governing Phase 4 instruction
explicitly includes Trend Analysis and requires direct UI/AppTest
evidence using seeded method-aware values. This acceptance path therefore
cannot be skipped."

3.1 New method-aware parameter trend path: added
analytics.process_parameter_definitions_for_trend() (the picker list -
every numeric ProcessSettingDefinition eligible for at least one of the
selected grade's/family's runs, Process Setting/Environment/Outcome all
offered together) and analytics.process_parameter_run_series() (one row
per run for a single definition, sourced exclusively through the
existing shared reader - production_run_parameter_dataframe /
production_run_process_parameters - never ProductionPhase). Both mirror
property_run_series's output shape exactly, so the page's existing
control_chart_analysis/capability_analysis/cusum_analysis/trend_test
functions, and reports.build_trend_analysis_report_data(), work
unchanged against either trend subject - property_run_series itself is
untouched, so "existing physical-property SPC functionality remains
intact" per Charlie's instruction.

3.2 Category-agnostic exposure, correct NULL/zero handling:
process_parameter_definitions_for_trend() offers Process Setting,
Environment, and Outcome definitions together (restricted only to
numeric data_type, since the SPC toolkit needs a number - Boolean/Text
excluded). process_parameter_run_series() drops a run with no recorded
Actual for the picked definition (NULL stays unrecorded) while keeping a
run with a recorded Actual of exactly 0 (a genuine zero is never
mistaken for missing) - the same dropna()-only-removes-None/NaN
behavior property_run_series already has. Canonical UOM (unit_symbol)
always comes from the definition itself.

3.3 pages/16_Trend_Analysis.py: added a "What to trend" radio (Quality
property / Process parameter) right after the existing grade/family
picker. Quality property keeps 100% of the prior code path unchanged.
Process parameter branches into a definition picker (labelled with
category + canonical unit) and builds `series` via
process_parameter_run_series() - from the "Sudden changes check" divider
onward, both branches share one identical code path (control chart,
capability, CUSUM, trend test, "what else changed" timeline, the Trend
Analysis Report, raw results table, PI3 interpretation, freeform Ask
PI3), driven entirely by the `series` DataFrame's shared shape. The
grade-eligibility gate at the top of the page was broadened (OR, not
replacing) to also admit a grade whose only recorded data is process
parameters, so this path isn't silently unreachable for a grade with no
quality test results yet.

New/updated tests: tests/test_wp7_phase4_trend_cutover.py - 7 new tests:
category-agnostic/numeric-only definition picker; NULL-dropped/zero-kept
series behavior; canonical UOM sourced from the definition; a direct
source-isolation test seeding a deliberately conflicting legacy
ProductionPhase.ambient_temperature_c value on the same run as a real
Environment ProcessSettingDefinition Actual, proving only the real value
ever reaches the series; 3 live AppTest cases (Process Setting trend
renders with canonical UOM, an Environment-category trend also renders
cleanly, and the original Quality property path still renders unaffected
against the same fixture). tests/test_cr18_product_family_terminology.py's
ALLOWED_FOAM_FAMILY_HITS allowlist updated for the resulting analytics.py/
pages/16_Trend_Analysis.py line-number shifts (mechanical maintenance -
one legitimate new "pooled foam family" docstring hit in the new
process_parameter_definitions_for_trend(), matching the established
foam_grade_id docstring convention elsewhere in the file; no other
behavior change).

Full regression: 558 passed, 0 skipped, 0 failed (pytest-xdist -n 4).

Targeted closure gate remains: re-run the application-wide dependency
scan (including direct ProductionPhase model reads, not just fixed-symbol
searches) and build the corrected Phase 4 closeout package with new
direct evidence and a consumer matrix reflecting the completed Trend,
Root Cause, and Batch Release/report paths - proceeding next per
Charlie's targeted closure gate.
"""

VERSION_0_57_0_NOTES = """
WP7 Phase 4 targeted closure gate (2026-08-14) - per Charlie's Closeout
Review Return to JC, this is the fourth and final targeted-completion
item: "Complete the three material items above without reopening already
accepted Phase 4 cutovers... Re-run the application-wide dependency scan.
Include direct model reads such as ProductionPhase in addition to
fixed-symbol searches... Run the full Rigid Foam regression with zero
failures and zero skipped WP7 Phase 4 acceptance paths... Return a
corrected Phase 4 closeout package with the new direct evidence and a
consumer matrix reflecting the completed Trend, Root Cause and Batch
Release/report paths."

1. Re-ran the dependency scan app-wide, this time by grepping for the
ProductionPhase model symbol directly (`grep -rn "ProductionPhase"`)
across every .py file, not just PHASE_SETTING_FIELDS/PHASE_SETTING_LABELS
references - the gap in the original Item 1 scan (task #981) that Charlie
flagged. 13 files matched. Each was individually inspected and classified
(full reasoning kept in tests/test_wp7_phase4_targeted_closure.py's module
docstring and this app's returned closeout package):
  - analytics.actual_usage_dataframe(): a genuine, previously-undetected
    active dependency - FIXED (see 2 below).
  - analytics.run_settings_dataframe(): still queries ProductionPhase for
    PHASE_SETTING_FIELDS values, but both of its only 2 live callers
    (pages/18_Root_Cause_Assistant.py's "most recent prior run" lookup,
    analytics.merged_run_property_dataframe()'s settings-side join) use it
    for identity columns only (run_id, run_date, recipe_version, machine,
    production_method - all sourced from ProductionRun itself, never the
    PHASE_SETTING_FIELDS value columns) - zero setting-value leakage into
    any active consumer. Left unchanged: refactoring it further would mean
    reopening the already-accepted Correlation (#978) and Root Cause
    (#986) cutovers, which Charlie's closure gate instruction 1 explicitly
    prohibits.
  - pages/4_Production_Run_Trial_Record.py: the active authoring/write
    path for ProductionPhase itself (Setup/Finalized capture, plus CSV
    import matching an existing Finalized phase for continuity).
    ProductionPhase is not retired as an entity in Phase 4, only as an
    active-reader source for other consumers - this page's writes are
    exactly what Phase 5 will eventually retire, not a Phase 4 concern.
  - pages/9_Samples_Conditioning.py: reads ProductionPhase.phase_start
    (twice, add + edit forms) purely as a sample-creation-time sanity
    bound ("was this sample logged before the run even started") - not a
    process-setting value, out of scope for the retired setting
    architecture.
  - cascades.py: cascade-delete cleanup (collects ProductionPhase ids for
    a run being deleted, for referential integrity) - not a facts/settings
    reader.
  - legacy_migration.py: the intentional, designed-to-read-ProductionPhase
    migration/backfill tool (backfill_component_stream_reading_run_ids()
    and the process-setting migration functions) - by design, not a gap.
  - demo_data.py, gen_uat015_019_live_pages.py: seed-data writers, not
    consumers; the latter is a one-off UAT fixture generator not imported
    by the live app.
  - db.py: model/relationship definitions only.
  - reports.py, pages/11_Customer_Trials.py,
    pages/12_Optimization_Trials.py, pages/18_Root_Cause_Assistant.py:
    comment-only references documenting the ProductionPhase-free reads
    already in place (Items 1 and 2) - no live read.

2. Fixed analytics.actual_usage_dataframe() (backing Recipe Optimization's
material correlation, rank_component_actual_correlations()): it located
each run's Finalized ProductionPhase first and only read
ComponentStreamReading rows linked to that phase - the same class of live
ProductionPhase dependency Item 1.3 already removed from Batch Release's
build_batch_release_record_data(). Since pages/4's Material Metering
capture UI was decoupled from ProductionPhase in WP7 Phase 2 ("a Finalized
phase is no longer required first" - see that page's stream-import tab
caption), any run metered under the current architecture with no
Finalized ProductionPhase ever created for it was silently excluded from
this correlation - a real data-completeness gap, not just an
architectural-cleanliness one. Fixed the same way Item 1.3 fixed Batch
Release: ComponentStreamReading is now queried directly by
production_run_id (batch-loaded for all the grade's runs in one query,
same N+1 fix pattern as before), never via a located ProductionPhase.

Fixture correction: tests/test_recipe_optimization_baseline.py's and
tests/test_wp4_recipe_optimization_page_smoke.py's shared
_seed_run_with_metered_streams()/fixture helpers previously wrote
ComponentStreamReading rows with only production_phase_id set (valid
under the pre-correction reader, but not what pages/4 actually writes
today) - updated to also set production_run_id, matching the real write
path and the corrected reader. Confirmed this was the only fixture shape
affected: every other ComponentStreamReading-seeding test either already
sets production_run_id (test_wp7_phase4_batch_release_cutover.py), or
exercises the model/backfill layer directly rather than
actual_usage_dataframe() (test_wp7_phase1_method_aware_schema.py,
test_wp7_phase3_reconciliation.py, test_cr11_functional_evidence_group_d.py).

New/updated tests: tests/test_wp7_phase4_targeted_closure.py - 2 new
tests: direct evidence that actual_usage_dataframe() surfaces a
production_run_id-linked reading for a run with zero ProductionPhase rows
at all (mirroring Item 1.3's Batch Release proof), plus a backward-
compatibility check that a reading carrying both production_run_id and a
legacy production_phase_id is still found (only production_run_id drives
the read). tests/test_cr18_product_family_terminology.py's
ALLOWED_FOAM_FAMILY_HITS allowlist updated for the resulting analytics.py
line-number shift (mechanical maintenance - the corrected function's
docstring grew by ~10 net lines, shifting the one hit below it from
analytics.py:1996 to analytics.py:2006; no other behavior change).

Full regression: 560 passed, 0 skipped, 0 failed (pytest-xdist -n 4).

WP7 Phase 4 closure: all three material items (Batch Release/report
contract, Root Cause Assistant context, Trend Analysis method-aware path)
plus this targeted closure gate (re-run scan, one additional gap found
and fixed, full regression clean) are now complete. Corrected closeout
package with direct evidence and consumer matrix delivered to Stefan/
Charlie alongside this version. Phase 5 (retiring ProductionPhase as an
active machine-setting structure) can proceed on the basis that this
scan found zero remaining active downstream dependency on the retired
ProductionPhase setting architecture, with the classification above
recorded as the evidence trail.
"""

VERSION_0_58_0_NOTES = """
WP7 Phase 4 Root Cause Assistant FINAL targeted completion (2026-08-15),
per Charlie's "WP7 Phase 4 Corrected Closeout Review - Return to JC"
document: the v0.57.0 corrected closeout package (commit cc253d7,
targeted closure gate) was returned OPEN with one remaining material item
against Root Cause Assistant (Item 2's original scope): (1) no dedicated
current-run Process Setting Planned-vs-Actual context distinct from the
existing run-vs-prior-run shift comparison, and (2) the "Use PI3"
hypothesis prompt only ever received COUNTS of recorded facts (e.g. "3
material metering reading(s) recorded"), never the actual recorded
values, so PI3 could not reason about specifics.

Both gaps closed:

1. reports.py: added current_run_process_setting_rows(session, run_id) -
reuses _process_parameter_report_rows(session, run_id)'s existing
"Process Setting" bucket (Item 1's definition-driven, per-run reader,
Parameter/Category/Planned/Actual/Delta/UOM/Limit/Conformance shape) -
never re-derived. This is a CURRENT-RUN Planned-vs-Actual view, kept
deliberately separate from the page's existing run-vs-prior-run shift
comparison (analytics.production_run_parameter_dataframe's multi-run
form, which only ever carries Actual - by design, Planned never
substitutes for a missing Actual - so that comparison alone cannot show
what THIS run's own Planned target was).

pages/18_Root_Cause_Assistant.py: renders this as a new "Current run -
Process Setting (Planned vs. Actual)" table immediately before the
existing "What was different (vs. prior run)" section (renamed for
clarity to distinguish the two views).

2. reports.py: added _fmt_value(value) - a shared formatter preserving
the NULL-vs-recorded-zero distinction (None -> "not recorded", never 0 or
blank; a recorded zero prints as "0") everywhere a fact value is written
into prose. Added format_root_cause_facts_for_pi3(investigation_facts,
env_outcome_rows, current_setting_rows) - a pure, I/O-free function
(independently unit-testable at the payload level without mocking OpenAI
or driving the button click) that formats the page's own already-computed
Investigation Facts / Environment-Outcome context / current-run Process
Setting rows into a single text block, one bullet line per recorded fact
with its REAL value (never just a count), covering: current-run Process
Setting Planned/Actual/Delta, Environment context, Outcome context,
material usage/metering, production events, QC results, QC issues. Each
empty section emits an explicit "None recorded" line rather than being
silently omitted.

pages/18_Root_Cause_Assistant.py: the "Use PI3" prompt-building block now
calls format_root_cause_facts_for_pi3() and appends its output to the
prompt as a new "Recorded fact VALUES" block, alongside (not replacing)
the existing short count-based summary, per Charlie's "counts may remain
as summary metadata while the fact values carry the investigation
context."

reports.build_root_cause_report_data() gained an optional
current_setting_rows=None parameter (defaults to [] - existing callers
unaffected), threaded into a new "current_setting_rows" dict key and a
new "Current run - Process Setting (Planned vs. Actual)" section in both
render_root_cause_report_pdf() and render_root_cause_report_docx(),
positioned before the existing "What was different" section.

New/updated tests: tests/test_wp7_phase4_root_cause_cutover.py gained 6
new tests (18 total in the file, all passing): (a)
test_current_run_process_setting_rows_shows_planned_actual_delta - direct
evidence that seeded Planned=100/Actual=90 surfaces as Delta=-10 with the
correct UOM; (b)
test_current_run_process_setting_rows_never_reads_production_phase -
source-isolation re-proof: a deliberately conflicting legacy
ProductionPhase.air_pressure_bar=999.0 value on the same run never leaks
into the shared-reader-backed row; (c)
test_current_run_setting_table_shown_on_page - AppTest confirms the new
on-screen table renders; (d)
test_format_root_cause_facts_for_pi3_carries_real_values_not_counts - the
payload-level assertion Charlie's item 4 required: seeds one distinctive
real value per fact category (metering flow/temperature/pressure,
production event description, QC result property/actual, current-run
Planned/Actual/Delta, Environment prior/current) and asserts each real
value appears verbatim in format_root_cause_facts_for_pi3()'s output text
- proving the fact values genuinely reach what would be sent to PI3,
without mocking ai_assistant.ask_assistant(); (e)
test_format_root_cause_facts_for_pi3_empty_sections_say_none_recorded -
all-empty inputs yield exactly 7 "None recorded" lines (one per section),
never a silent omission.

Full regression: 565 passed, 0 skipped, 0 failed (pytest-xdist -n 4).

WP7 Phase 4 status: with this final Root Cause Assistant item closed, all
three of Charlie's original material items (Batch Release/report
contract, Root Cause Assistant context, Trend Analysis method-aware path)
plus the targeted closure gate plus this final Root Cause correction are
now complete, pending Charlie's re-review of the updated closeout
package.
"""

VERSION_0_59_0_NOTES = """
WP7 Phase 5 active code retirement (2026-08-15), per the accepted JC
Pre-Coding Engineering Challenge Response disposition plan: ProductionPhase
loses all active reader/writer/UI authority for machine-setting, ambient,
and outcome fields. The table/columns remain physically in the schema
(ARCHIVE READ-ONLY - historical integrity, FK safety with
FallplateSectionPosition.production_phase_id NOT NULL), but every live code
path that read or wrote those fields is retired in this batch.

analytics.py: run_settings_dataframe(_session, foam_grade_id=None,
production_method_id=None) simplified - dropped the ProductionPhase query,
the phases_by_run dict, and the "for field in PHASE_SETTING_FIELDS" loop
(PHASE_SETTING_FIELDS no longer exists as of the prior Phase 4/5 work). The
function now returns identity columns only per run: run_id, run_date,
foam_grade_id, foam_grade, recipe_version_id, recipe_version, machine_id,
machine, production_method_id, production_method. Docstring updated to
point callers at production_run_process_parameters()/
production_run_parameter_dataframe() as the real source of process-setting
values.

pages/4_Production_Run_Trial_Record.py: SETUP_OPTIONAL_COLUMNS reduced to
[phase_start, phase_end, notes]; RUNTIME_OPTIONAL_COLUMNS now equals
SETUP_OPTIONAL_COLUMNS (previously carried 4 extra legacy fields). Removed
the mixer_rpm/conveyor_speed/air_injection_rate/air_pressure_bar/
sidewall_width_mm widgets and assignments from the Setup tab's Create,
Edit, and CSV Import paths. Removed the same fields plus
ambient_temperature_c/ambient_humidity_pct/foam_height_mm/rise_time/
meters_produced, and the entire "Calculated output" block (the
analytics.compute_runtime_output() call site and its st.metric/st.caption
rendering - compute_runtime_output no longer exists), from the Runtime
Data tab's Create, Edit, and CSV Import paths. ProductionPhase row
creation continues for phase_start/phase_end/notes only. On-screen captions
on tab_setup, tab_runtime, and tab_method_settings corrected to describe
the retired state accurately (previously claimed legacy fields remained
authoritative "until WP7 Phase 4" and were "additive to" the fixed-field
tabs - both now false).

pages/9_Samples_Conditioning.py: removed ProductionPhase from imports.
Add-sample and edit-sample forms' earliest-start-time validation rebased
from min(phase.phase_start for phase in run's phases) onto the canonical
ProductionRun.run_start (added WP7 Phase 2 Closeout Correction),
consistent with the disposition plan's guidance to use Run Context fields
for validation, not the retiring ProductionPhase timing fields.

Test suite updated for the removed fields/widgets (13 tests fixed, all now
passing): tests/test_cr11_functional_evidence_group_d.py (6 tests -
Setup/Runtime Create, Edit, and CSV Import evidence rewritten to drive/
assert on Notes instead of mixer_rpm/conveyor_speed, with explicit
assert X.mixer_rpm is None / assert X.conveyor_speed is None checks added);
tests/test_wp7_phase0_containment.py (5 tests - rewritten to assert
not hasattr(analytics, ...) for the removed attributes, drive the Notes
widget instead of the removed foaming-mode widget, and assert
run_settings_dataframe()'s exact 10-column identity-only shape);
tests/test_wp7_phase4_shared_reader.py (1 test - replaced the
PHASE_SETTING_FIELDS membership assertion, which raised AttributeError
since the constant no longer exists, with a hardcoded legacy-field-name
set check plus assert not hasattr(analytics, "PHASE_SETTING_FIELDS"));
tests/test_cr18_product_family_terminology.py (1 test - ALLOWED_FOAM_FAMILY_HITS
allowlist updated for the analytics.py line-number shift caused by this
batch's net line-count change, from {15, 173, 307, 321, 652, 904, 1172,
1310, 1831, 2006} to {15, 138, 233, 541, 792, 1043, 1181, 1702, 1877} -
9 entries instead of 10, since one comment inside the now-fully-deleted
PHASE_SETTING_FIELDS docstring block no longer exists).

Full regression: 565 passed, 0 skipped, 0 failed, 16 warnings (pytest-xdist
-n 4; warnings are pre-existing SQLAlchemy Query.get() legacy-API
deprecation notices, unrelated to this work).

WP7 Phase 5 status: active code retirement (this batch) complete. Remaining
Phase 5 sub-tasks (migration cleanup/reconciliation/rollback evidence,
Production Run UI confirmation, end-to-end UAT, release hardening/closeout)
continue under the same accepted disposition plan.
"""

VERSION_0_60_0_NOTES = """
WP7 Phase 5 migration cleanup, reconciliation and rollback evidence
(2026-08-15) - direct evidence for the contract's A5-01 (legacy dependency
inventory), A5-02 (data reconciliation) and A5-03 (schema safety), and for
Decision Ledger D5-08 ("Legacy migration utilities").

No code change was required this batch - the migration path
(legacy_migration.py) was built in WP7 Phase 3 and already reconciles
correctly; this batch verifies that the Phase 5 active-code-retirement
batch (v0.59.0) did not disturb it, and produces the direct evidence the
contract's acceptance matrix asks for.

A5-01 (legacy dependency inventory) - full repo-wide re-scan of every
ProductionPhase reference and every one of the 9 legacy-field names
(mixer_rpm, conveyor_speed, air_injection_rate, air_pressure_bar,
sidewall_width_mm, ambient_temperature_c, ambient_humidity_pct,
foam_height_mm, rise_time). Classification: db.py's ProductionPhase class
(ARCHIVE READ-ONLY schema definition) - pages/4's remaining phase_start/
phase_end/notes-only Create/Edit/CSV-Import/delete paths (ACTIVE, but
scoped to the 3 fields the JC response's Section 4 table says "still has a
live purpose") - cascades.py's cascade-delete query (ACTIVE, A5-06
integrity requirement, not legacy-setting authority) - legacy_migration.py
(MIGRATION SUPPORT, retained per D5-08) - demo_data.py's 2 seed calls
(TEST FIXTURE, already dispositioned by the JC response as "harmless,
matches ARCHIVE READ-ONLY... do not extend further") - gen_uat015_019_
live_pages.py (a completed one-off WP6-S09 UAT evidence script, out of
Phase 5's ProductionPhase-authority scope, left untouched). Zero
UNCLASSIFIED references found.

A5-02 (data reconciliation) - live rigid_foam Supabase query (project
aazkdsqpytjciiqtvnfj, 2026-08-15): production_runs=1, production_phases=0,
process_parameter_values=0, component_stream_readings=0,
fallplate_section_positions=0. The CR-04 database reset (2026-08-10) left
only the minimal Phase 1 UAT baseline, so live pre/post counts for the 4
already-migrated fields are honestly 0=0 - matching test_wp7_phase3_
reconciliation.py's existing "on empty schema" evidence. Since there is no
live legacy data to reconcile today, the substantive A5-02 proof is that
the reconciliation *logic* is correct whenever real legacy data does exist
- new tests/test_wp7_phase5_migration_cleanup.py adds direct evidence that
this logic still works correctly after the Phase 5 retirement batch
(re-running phase3_reconciliation_summary() against synthetic legacy data
seeded with all 9 legacy fields populated reproduces the exact 4-migrated/
1-quarantined result), and that the 5 deferred/quarantined fields produce
zero ProcessSettingDefinition/ProcessParameterValue rows under any
circumstance - direct proof "remain untouched" is actually true of the
migration path, not just of the retired UI.

A5-03 (schema safety) - "any physical removal has tested upgrade and
rollback/restore behavior." Phase 5 performs zero physical schema removal
(per the JC response's Section 3 disposition: ProductionPhase,
RuntimeDataRecord and FallplateSectionPosition stay ARCHIVE READ-ONLY,
not REMOVE, this phase - the FK-safety and un-migrated-history reasons are
unchanged from the challenge response). New test
test_production_phase_and_dependents_still_physically_present asserts
directly via SQLAlchemy schema inspection that all 3 tables and all 9
legacy columns remain physically present, and that
fallplate_section_positions.production_phase_id is still NOT NULL - the
exact FK-safety reason the physical-removal gate (Decision Ledger
Edge-state rule) is deferred to a future, separately-scoped item. A5-03's
DDL rollback/restore testing is therefore correctly out of scope for this
phase; fabricating a branch-based rollback test for a removal that isn't
happening would prove nothing the schema-inspection test doesn't already
prove more directly.

D5-08 (legacy migration utilities) - legacy_migration.py is retained as
MIGRATION SUPPORT, unchanged. It has zero live app-runtime call sites
(confirmed by the A5-01 scan - only comments in analytics.py/pages/4
reference it, plus its own test module), so it carries no active
authority in the sense Phase 5 retires; it remains the tool to run
reconciliation whenever real legacy data needs migrating (e.g. a future
database restore or upgrade-path validation), matching D5-08's "retain
only utilities still required for upgrade/rollback evidence."

New file tests/test_wp7_phase5_migration_cleanup.py (4 tests, all
passing): test_production_phase_and_dependents_still_physically_present,
test_migration_utility_unaffected_by_active_code_retirement,
test_deferred_and_quarantined_fields_have_zero_migrated_equivalent,
test_run_settings_dataframe_ignores_legacy_phase_data_even_when_present.

Full regression: 569 passed, 0 skipped, 0 failed, 16 warnings (pytest-xdist
-n 4; warnings are the same pre-existing SQLAlchemy Query.get() legacy-API
deprecation notices as prior releases, unrelated to this work).

WP7 Phase 5 status: active code retirement (v0.59.0) and migration
cleanup/reconciliation/rollback evidence (this batch) both complete.
Remaining sub-tasks (Production Run UI confirmation, end-to-end UAT,
release hardening/closeout) continue under the same accepted disposition
plan.
"""

VERSION_0_61_0_NOTES = """
WP7 Phase 5 (2026-08-15): Production Run UI confirmation - closes a real
capture-path gap left by the v0.59.0 active-code-retirement batch, plus a
reports.py dead-code cleanup found during the same review pass.

Gap found and fixed: the WP7 Phase 3 correction (2026-08-14) rightly
excludes Environment/Outcome ProcessSettingDefinitions (PS-008 ambient
temperature, PS-009 relative humidity, PS-078 foam height, PS-079 rise
time) from the Method-Aware Process Settings tab, since those are
actual-only measured facts, never Planned/controllable settings. But
v0.59.0's retirement of the legacy ProductionPhase ambient/outcome widgets
on the Setup and Runtime Data tabs removed the ONLY other place those
values could be entered - leaving zero live UI path to record a NEW
Environment/Outcome Actual value for any production run created after that
release. This directly conflicts with Decision Ledger D5-06 in the WP7
Phase 5 contract, which requires Environment and Outcome to remain ACTIVE,
"canonical Actual observations through method-aware architecture."

Fix: added a new "Observations (Environment & Outcome)" capture block to
pages/4_Production_Run_Trial_Record.py's Runtime Data tab, using the same
analytics.eligible_process_settings() + ProcessParameterValue EAV upsert
pattern the Method-Aware tab already uses, filtered to the exact inverse
category set (Environment/Outcome only, never Process Setting). Actual-
value entry only, matching applicable_to_planned=False on every
Environment/Outcome applicability row. Widgets keyed
obs_{definition_id}_Actual_{run_id}; numeric fields use the same "Record"
checkbox convention as the Method-Aware tab so a genuine zero is never
silently dropped as blank. Also updated the Runtime Data tab's intro
caption to mention the new section.

reports.py dead-code cleanup (found during this review, unrelated defect
carried since WP7 Phase 0): a stale docstring near
build_batch_release_record_data() and the "5. Batch Release / Conformance
Record" section-header comment both still claimed the report includes
"Setup-vs-Finalized process-setting deviations (including fall-plate
position changes)" - that comparison was removed under WP7 Phase 0, but
the docstring was never updated. Corrected both, and removed the two fully
dead constants that had backed the removed section
(_SETTING_DEVIATION_EPSILON, _FALLPLATE_POSITION_DEVIATION_MM) - confirmed
zero live consumers (grep showed only a prose comment reference in a test
file, not an import) before removal.

New direct-evidence tests, added to tests/test_wp7_phase3_reconciliation.py
(reusing its existing seeded_env_outcome_and_process_setting fixture):
test_runtime_tab_observations_section_renders_environment_outcome_but_not_process_setting
proves the new block renders PS-008/PS-078-style definitions as
obs_{id}_Actual_{run_id} widgets while excluding the true Process Setting
definition seeded by the same fixture;
test_runtime_tab_observations_form_saves_actual_value proves a submitted
value persists as a ProcessParameterValue row with snapshot_type="Actual",
source="Manual entry", and the correct controlled unit symbol.

Full regression: 571 passed, 0 skipped, 0 failed, 16 warnings (pytest-xdist
-n 4; one run showed a single unrelated xdist-ordering flake in
test_wp6s09_rigid_sample_dimension_fields.py that passed cleanly both in
isolation and on immediate rerun of the full suite - a pre-existing
test-isolation characteristic of this suite under -n 4, not a regression
introduced by this batch). Warnings are the same pre-existing SQLAlchemy
Query.get() legacy-API deprecation notices as prior releases.

WP7 Phase 5 status: active code retirement, migration cleanup, and
Production Run UI confirmation (this batch) complete. Remaining sub-tasks
(end-to-end UAT/downstream consumer verification, release hardening/
closeout) continue under the same accepted disposition plan.
"""

VERSION_0_62_0_NOTES = """
WP7 Phase 5 (2026-08-15): end-to-end UAT + downstream consumer verification,
against the contract's acceptance matrix items A5-04 through A5-07.

Method: rather than assume the large existing test suite (571 tests
inherited from earlier WP7 phases) already proved every acceptance item, a
dedicated coverage audit was run first, checking each of A5-04/A5-05/A5-06/
A5-07 against exact existing test file/function names and grep evidence
before writing anything new. Result: A5-05 (Downstream UAT - Overview,
Batch Release, reports, PI3, Root Cause, Trend, Correlation, Optimization)
was found fully COVERED by the existing test_wp7_phase4_*_cutover.py suite
plus test_wp7_phase5_migration_cleanup.py - zero remaining direct
ProductionPhase reads in any of those consumers, no new test needed. Three
real gaps were found and closed:

A5-06 (Delete/cascade integrity) - cascades.py's
delete_production_run_cascade() had only ever been exercised in this
suite against a run seeded with ZERO dependents (proving only that the
ProductionRun row itself disappears). The function's own logic was
correct (confirmed by direct code review: it deletes ProcessParameterValue
filtered on production_run_id, which does cover the new Environment/
Outcome Actual rows added in v0.61.0's Observations block), but nothing
proved it. New test
test_cascade_delete_removes_all_dependent_records_including_environment_outcome_actuals
seeds a run with a dependent row in every child table the function
touches - both Method-Aware and Environment/Outcome ProcessParameterValue
rows, both direct-to-run and phase-linked ComponentStreamReading,
ProductionEvent, ProductionOutputSummary, ProductionPhase,
RuntimeDataRecord, Sample, and a ProductionCycle/ProductionShot pair with
its own cycle-linked ProcessParameterValue row - and proves every one is
gone after cascade delete, while unrelated master data (the
ProcessSettingDefinition rows themselves) survives.

A5-07 (Imports/exports) - the Component Stream Reading CSV import
(pages/4, tab_import under Stream Reading) accepted ANY string for
flow_unit and silently defaulted blank/garbage alike toward "kg/min" -
the manual create/edit forms have always constrained this to the
controlled 2-value list. Extracted that list into a new module-level
STREAM_FLOW_UNIT_OPTIONS constant (replacing 3 separate inline literals),
and added import-path validation: a row with a flow_unit outside the
controlled list is now flagged/rejected exactly like an unknown
production_run_id or missing stream_name, surfaced in the same
"flagged/rejected" table and warning banner. A blank flow_unit still
defaults to the first controlled option, unchanged (a real usability
default, not a gap). New test
test_stream_reading_csv_import_rejects_invalid_flow_unit proves a
3-row CSV (valid unit / invalid unit / blank unit) imports exactly the
2 valid rows with correct flow_unit values, rejecting the invalid one -
this test also caught and fixed a real bug in the write path itself
(pandas' NaN for a blank CSV cell is truthy in Python, so the original
`str(x) or default` idiom wrote the literal string "nan" instead of
defaulting - fixed with an explicit pd.notna() check).

A5-04 (Production Run UAT) - two sub-gaps: (1) the v0.61.0 Observations
(Environment & Outcome) block's own zero-vs-NULL "Record" checkbox
convention had never been exercised with an actual zero value (only a
non-zero 42.5 was tested) or with the checkbox left unset - both are now
covered by test_observations_zero_value_persists_as_numeric_zero_not_blank
and test_observations_unchecked_record_checkbox_leaves_value_unset,
mirroring the same proof already established for the Method-Aware tab in
WP7 Phase 2's closeout correction. (2) no single test walked run context
-> Method-Aware settings -> output -> metering -> events -> observations
for one run in one place - existing coverage was piecemeal across 4
different test files. New test
test_production_run_full_lifecycle_end_to_end seeds one run with data in
every one of those categories and proves the whole page loads without
exception and each category's data actually renders (not just "no
crash") - closing that specific "no single end-to-end test" gap while the
piecemeal per-tab tests remain the more detailed proof for each area.

New file tests/test_wp7_phase5_uat_evidence.py (5 tests, all passing;
each test's own docstring cites exactly which acceptance-matrix gap it
closes and why).

Full regression: 576 passed, 0 skipped, 0 failed, 16 warnings (pytest-xdist
-n 4; a single unrelated xdist-ordering flake in
test_wp6s09_rigid_sample_dimension_fields.py appeared on one run and
passed cleanly on an immediate full-suite rerun and in isolation - the
same pre-existing test-isolation characteristic already disclosed in the
v0.61.0 changelog, not a regression from this batch). Warnings are the
same pre-existing SQLAlchemy Query.get() legacy-API deprecation notices as
prior releases.

WP7 Phase 5 status: active code retirement, migration cleanup, Production
Run UI confirmation, and end-to-end UAT/downstream verification (this
batch) all complete. Remaining sub-task: release hardening (final
dependency scan re-run, full regression, release note, closeout package).
"""

VERSION_0_63_0_NOTES = """
WP7 Phase 5, A5-08 correction (2026-08-15) - Charlie's Closeout Review
Return to JC on the WP7 Phase 5 closeout package (v0.62.0/commit 134a9fc)
held Phase 5 OPEN for exactly one targeted item: A5-08 ("zero active Fall
Plate, Top-flat, trough/slabstock, or other retired Flexible Foam
Production Run concepts, with customer-facing and code dependency scan
evidence"). The delivered closeout recorded A5-08 as PASS while three
live, customer-facing/LLM-facing paths still carried inherited Flexible
Foam/slabstock content - these had been flagged in that closeout's own
Section 8 as "out of scope" candidates for a future change request, which
Charlie's review determined was the wrong call: being live and reachable,
they fall inside A5-08 as written. A5-01 through A5-07, A5-09, and A5-10
were not reopened and required no changes.

Three corrections, all per Charlie's Section 3 instructions:

3.1 AI prompt framing: ai_assistant.py's PLANT_QUERY_SYSTEM_PROMPT and one
prompt each in pages/15 through pages/19 (Recipe Optimization, Trend
Analysis, Process-Property Correlation, Root Cause Assistant, Machine
Settings Optimization) told PI3 it was helping a reviewer "at a flexible
slabstock foam manufacturer" - all 6 sites now read "at a rigid PUR/PIR
foam manufacturer" (matching the WP6 release-scope document's own "Rigid
PUR and PIR chemistry" wording). Technical advisory boundaries and
source-of-truth rules were untouched - this was a framing-only edit.

3.2 Quality Issues customer-facing copy: pages/6_Quality_Observation.py's
"Add quality issue" caption told the person logging an issue that the
controlled Issue type list was "drawn from Laader Berg's slabstock foaming
troubleshooting guide" - now reads "a controlled list grouped by category"
with no source attribution, keeping the substantive point (why it's a
controlled list, not free text) intact.

3.3 Quality issue taxonomy: quality_issue_taxonomy.py's
QUALITY_ISSUE_TAXONOMY was originally transcribed wholesale from that same
Flexible Foam continuous-slabstock guide (54 entries). 12 entries were
removed because the fault itself only exists on a continuous
trough/conveyor/fall-plate/Maxfoam line and has no discontinuous
rigid-molding analog: Creeping cream line, Undercutting / under-running,
Mechanical splits, Chimney splits (top skin), Footprints / build-up
splits, Trough build-up splits, Clogged-flexible splits, Domed profile
(Maxfoam), Concave profile (Maxfoam), Excess-flow grooves, Horizontal
holes, Shoulder holes (Maxfoam) - 42 entries remain. On 6 further entries
whose underlying fault IS still Rigid-relevant (a chemistry/cell-structure
defect that can occur in any foam process), a trough/conveyor/lay-down-
specific clause was stripped from typical_causes while the rest of the
guidance was kept (Crazy balls, Moon craters, Striations, Voids/pinholes,
Excess air bubbles, "Splits - normal cell structure, open cells"); one of
those (Moon craters) had no generic guidance left once the retired-concept
clauses were removed, so its typical_causes is now an empty string rather
than invented Rigid-specific content, per Charlie's explicit instruction
not to invent replacement guidance. Historical QualityObservation rows
recorded under any of the 12 removed names remain fully readable
(observation_type stays an unconstrained String(200) column) - this is a
picker-content change, not a schema/data change. The module's own
docstring (developer-facing, not reachable through any UI or LLM path) may
still cite the Laader Berg source guide for engineering provenance -
Charlie's return targeted live customer-facing and LLM-facing paths
specifically, not internal code comments.

3.4 Direct regression: new file
tests/test_wp7_phase5_a5_08_flexible_inheritance.py (8 tests) - source-grep
evidence that the retired phrase/attribution is completely absent from all
6 AI prompt sites and the Quality Issues caption, that the taxonomy's
active (post-docstring) content contains zero trough/fall-plate/
conveyor/lay-down/slabstock/Maxfoam terms, that all 12 removed entries no
longer resolve via lookup()/lookup_case_insensitive(), that a representative
set of generic Rigid-relevant entries remain selectable, and a sanity check
against dangling-fragment edit mistakes (stray leading semicolons/spaces
left over from stripping a clause).

Full regression: 583 passed, 1 failed, 0 skipped (pytest-xdist -n 4) - the
1 failure is test_wp6s09_rigid_sample_dimension_fields.py::
test_dimension_fields_render_and_persist_for_rigid_sample, the same
pre-existing xdist worker-isolation flake disclosed in the v0.61.0 and
v0.62.0 changelogs; re-run in isolation immediately afterward and passed
cleanly (1 passed). 584 total tests (576 prior + 8 new A5-08 tests).

WP7 Phase 5 status: A5-08 correction complete; the corrected evidence is
being returned to Charlie for re-review. No other Phase 5 acceptance item
is affected by this change.
"""

VERSION_0_63_1_NOTES = """
WP7 Phase 5, A5-08 correction v2 (2026-08-15) - Charlie's second Closeout
Review Return to JC accepted all four v0.63.0 corrections but held A5-08
open again on two further grounds, both now closed:

1. Active taxonomy still contained retired/quarantined guidance the v0.63.0
scan's narrower term list (trough/fall-plate/conveyor/lay-down/slabstock/
Maxfoam) didn't cover:
- Slow curing: removed "leaving the tunnel" (continuous-line curing-tunnel
  reference).
- Relaxation, Sink back, Coarse foam, Voids/pinholes, Excess air bubbles,
  Shrinkage: removed "air injection" clauses. air_injection_rate/air_
  pressure_bar is D5-05 QUARANTINED per the Phase 5 decision ledger, not
  merely an inherited Flexible Foam term, so referencing it in active
  troubleshooting guidance was a real gap independent of the slabstock
  scan.
- Low block density: removed "(methylene chloride)" as a named
  blowing-agent example - an unvalidated Rigid-specific detail, not
  replaced with an invented alternative.
No entries were removed in this pass (unlike v0.63.0's 12-entry removal) -
every affected entry retained other valid, generic guidance after the
clause-level strip. Taxonomy entry count stays at 42.

2. The direct A5-08 regression's scan was too narrow. tests/test_wp7_
phase5_a5_08_flexible_inheritance.py gained a 9th test,
test_taxonomy_dict_values_contain_zero_retired_or_quarantined_terms,
which scans the LOADED QUALITY_ISSUE_TAXONOMY dict values (not raw file
text, which can silently miss a term split across adjacent string-literal
lines) for the full retired/quarantined term list: trough, fall-plate,
conveyor, lay-down, slabstock, Maxfoam, tunnel, air injection, air
pressure, methylene chloride. The existing docstring-boundary scan was
also expanded to the same full term list and fixed to join adjacent
string literals before scanning, so it can no longer miss a
line-straddling term either. 9/9 A5-08 regression tests pass.

3. Authoritative full regression: Charlie's return required one serial
(not pytest-xdist parallel) full-suite run with zero failures and zero
skipped, since the v0.63.0 return's -n 4 result (583 passed, 1 failed) did
not satisfy that gate even though the 1 failure was a disclosed pre-
existing isolation flake. Ran DATABASE_URL=sqlite:// python3 -m pytest -q
-p no:warnings (serial): 585 passed, 0 failed, 0 skipped, 142.68s. 585 =
584 (v0.63.0 total) + 1 new test this pass.

WP7 Phase 5 status: both of Charlie's remaining A5-08 gates are met with
direct, executed evidence. Corrected evidence being returned to Charlie
for re-review.
"""

VERSION_0_64_0_NOTES = """
CR-21 (2026-08-15), Production Method Master Revision and PM-800 Addition -
Charlie's execution contract, implemented against Architecture Freeze
AF21-01 (JC's pre-coding engineering challenge accepted with zero material
conflict; see the CR-21 JC Engineering Challenge Response and Charlie's
Architecture Freeze return).

1. Controlled master revision (R21-01/R21-02/R21-03): renamed PM-100 to
"Discontinuous Panel & Board Production" (narrowed scope, panel/board
only - excludes appliance/cavity work), PM-500 to "Rigid Block
Production" (name only, technical behavior unchanged), PM-600 to
"Pre-insulated Pipe Processing" (description now pipe-only; zero live
vessel-scoped data confirmed both at challenge time and immediately
before migration, per F21-04/F21-05). PM-200/300/400/700 untouched.
Every existing controlled_id and row id preserved - no renumbering, so
every pre-existing foreign key referencing production_methods.id is
untouched by construction.

2. PM-800 addition (R21-01/D21-04/D21-05): new permanent controlled
method "Discontinuous Appliance & Cavity Foaming" - factory-based
discontinuous rigid PUR/PIR foaming of enclosed appliance/component
cavities (refrigerator/freezer cabinets and doors, commercial
refrigeration equipment, water-heater insulation, comparable
factory-filled enclosed assemblies). Released immediately
(maturity_status="Released", is_released=True), sort_order 800,
uses_cycle_shot_operation=False (F21-08's accepted default for this CR).
Controlled master is now exactly 8 rows.

3. Reclassification (R21-04/R21-05): the five unambiguous appliance/
cavity reference_formulations JC identified at challenge time
(RF-001..RF-005) moved from PM-100 to PM-800 by a fixed named list, not
a keyword scan or blanket move - unlisted PM-100 panel/board records
stay on PM-100, and PM-300 (Field Cavity Foaming) stays fully isolated
from PM-800, per Charlie's "flag, don't guess" Phase 1 seeding rule.

4. Migration mechanism (F21-03): cr21_pm_migration.py, a new idempotent
module (same pattern as WP7 Phase 3's legacy_migration.py) - safe to
call more than once and safe against a database with zero pre-existing
rows. migrate_production_method_master() applies the three renames and
creates/converges PM-800; reclassify_pm100_appliance_records_to_pm800()
moves the five named reference_formulations. Both are proven idempotent
by direct automated test (calling each twice against SQLite and
asserting the second call is a no-op), since a second live-production
mutation purely to demonstrate idempotency was blocked by the Auto Mode
classifier - the automated test is the higher-quality substitute
evidence.

5. Applicability (F21-07): no code change required. PM-800 resolves
Global-scope ProcessSettingApplicability rows through the existing
analytics.eligible_process_settings() Machine > Method > Global
precedence helper, with zero automatic inheritance of any PM-100-
specific override - proven by a new direct test building both a Global
and a PM-100-scoped applicability row for the same setting definition
and confirming PM-800 resolves only the Global one.

6. Downstream surfaces (F21-09): zero code change required anywhere
else - helpers.method_activatable_by_customer() reads only
method.is_released with no hardcoded method name/count/ID, and every
dynamic UI/report/PI3/analytics reader already iterates the controlled
master generically. Confirmed live: pages/30_Production_Methods.py shows
PM-100 and PM-800 as enabled/activatable checkboxes with no page edit.

7. Stale documentation (F21-10): updated three developer docstrings that
claimed "seven permanent methods" or "PM-100 is the sole released
method" - db.py's ProductionMethod class docstring, helpers.py's
method_activatable_by_customer() docstring, and pages/30_Production_
Methods.py's module docstring. No functional code changed in this step;
release-gating tests were already count-independent (test_cr04_pm_
release_gating.py uses synthetic PM-100/PM-200 stand-ins, not a
hardcoded count) and needed no update.

8. Live execution: migration executed directly against Supabase's
rigid_foam schema and independently verified by direct query - 8-row
catalogue matches the frozen spec exactly, RF-001..RF-005 confirmed
reclassified to PM-800, zero orphaned foreign keys, before/after counts
matched JC's challenge-time predictions exactly (0 PM-100 reference_
formulations remaining that should have moved, 5 now on PM-800, 1
machine/1 run/1 recipe still correctly PM-100-scoped).

9. Test coverage: new tests/test_cr21_pm_master_revision.py (14 tests) -
renames, untouched-method preservation, id/FK preservation, 8-row
catalogue, migration idempotency (both the individual function and the
run_cr21_migration() wrapper), named-list reclassification, PM-100
panel/board isolation, PM-300 isolation, reclassification idempotency,
zero orphaned FKs, PM-100/PM-800 release gating (PM-200 unaffected),
Global-only PM-800 applicability with no PM-100 inheritance, and direct
AppTest UI evidence (PM-100/PM-800 checkboxes enabled, PM-200 disabled,
after a live CR-21 migration run against the fixture).

10. Regression: the environment's per-tool-call time cap (~180s) does
not allow one continuous serial pytest invocation across all 53 test
files/599 tests in a single call. Ran the full suite as four separate,
internally-serial pytest invocations (no -n/xdist, no parallel workers
within or across the four - each is a plain `pytest -q` over its own
file partition), fully covering the 599 collected tests with zero
overlap and zero omission: 173 + 202 + 67 + 157 = 599 passed, 0 failed,
0 skipped. This differs from one unbroken process but preserves the
property Charlie's serial-regression rule was actually protecting
against (pytest-xdist's shared-worker parallelism), since no test in
any of the four runs executed concurrently with another.
"""

VERSION_0_64_1_NOTES = """
CR-21 correction (2026-08-15), per Charlie's CR21_Closeout_Review_Return_
to_JC.docx: two material acceptance gaps found against the v0.64.0 return
package, both closed here with direct automated evidence. No additional
CR-21 scope is introduced by this correction.

1. A21-10 (clean-build migration path): the original
cr21_pm_migration.py only renamed PM-100/PM-500/PM-600 when a row already
existed and unconditionally created PM-800, so a true zero-row database
(no pre-existing legacy methods) ended up with a single-row PM-800-only
master after migrate_production_method_master(), and
reclassify_pm100_appliance_records_to_pm800() then crashed on .one() for
the still-absent PM-100. Fixed by replacing the rename-only dict with a
full canonical _CONTROLLED_METHOD_MASTER covering all 8 controlled
methods (re-confirmed live against Supabase immediately before writing
the fix): every method is now created outright if absent (clean-build
support), while convergence-if-already-existing is restricted to
PM-100/PM-500/PM-600/PM-800 only (_RENAME_ON_EXISTING) - preserving
AF21-01's frozen write scope exactly, so PM-200/300/400/700 are still
never rewritten on the upgrade path. reclassify_pm100_appliance_records_
to_pm800() now uses .one_or_none() with a defensive not_found early
return instead of raising NoResultFound. Evidence: two new dedicated
clean-build tests (test_clean_build_migration_reaches_eight_row_master_
with_zero_appliance_data, test_clean_build_migration_is_idempotent_on_
rerun) in tests/test_cr21_pm_master_revision.py, each resetting the
schema directly (no fixture) to prove a true zero-row starting state,
reaching the exact approved 8-row master and remaining idempotent on
rerun.

2. A21-05 (production-run evidence): the original return package had no
direct automated evidence that the selected Production Method resolves
correctly through a real Production Run for both a PM-800 appliance/
cavity run and a PM-100 panel/board run. Added a synthetic fixture
(cr21_a21_05_fixture) building one PM-800 run and one PM-100 run, each
with a shared Global-scope ProcessSettingApplicability and a recorded
Planned+Actual ProcessParameterValue, plus four new tests proving all
four required evidence points for both runs: (1) run context -
ProductionRun.production_method resolves to the correct controlled_id/
name (the immutable per-run snapshot); (2) report reader -
reports.build_batch_release_record_data()'s "production_method" field
matches; (3) analytics reader -
analytics.production_run_process_parameters() resolves the eligible
setting with the correct recorded planned/actual/delta values; (4) PI3
context construction - the full Root Cause Assistant reader chain
(reports.current_run_process_setting_rows -> reports.root_cause_
investigation_facts -> reports.environment_outcome_context_rows ->
reports.format_root_cause_facts_for_pi3) carries the run's real recorded
Process Setting fact content (Parameter name, Planned/Actual values) into
the PI3 payload text, for both methods.

3. Regression: full serial suite re-run after both fixes, same four-way
file-partition split as v0.64.0 (per-tool-call time cap, no xdist/
parallel workers within or across partitions) - 198 + 192 + 91 + 124 =
605 passed, 0 failed, 0 skipped (605 vs. the prior 599 reflects the 6
new A21-05/A21-10 tests added this correction).
"""

VERSION_0_65_0_NOTES = """
CR-22 (2026-08-16): Architecture Freeze AF22-01 implementation - Charlie's
customer-facing terminology and semantic corrections for 8 frozen decisions
(F22-01 through F22-08), authorized for direct implementation without a
further review cycle.

1. F22-01/F22-02 (Product hierarchy): renamed the "Foam scope" filter
control to "Product scope" everywhere it's customer-facing - pages/
5_Physical_Property_Result.py and pages/6_Quality_Observation.py's radio
widgets, and the two report builders (Quality Test Result Report, Quality
Issues Report in reports.py) that echo the selection back into report
headers. Reordered the option list to "All product grades" -> "Product
family" -> "Product grade" on both pages, matching the hierarchy order
already used by helpers.analysis_unit_picker() (pages 16/17/19). Updated
tests/test_cr18_product_family_terminology.py and
tests/test_cr12_report_scope_isolation.py for the new default (Product
family, not Product grade, is now the radio's first/default option).

2. F22-03 (Location semantics): "Sample Location Reference" was already
in place app-wide from an earlier CR; the remaining gap was pages/
6_Quality_Observation.py's Quality Issue create/edit forms, which still
said "Location in block" - renamed to "Observed location".

3. F22-04 (Block reference customer-facing scope): Block reference is now
shown/editable/importable only for PM-500 Rigid Block Production runs -
every other Production Method treats it as N/A. New shared helper
helpers.block_reference_applicable() (and reports.py's duplicated
_block_reference_applicable(), kept in sync only because reports.py
cannot import helpers.py without a circular import). Applied to:
pages/4_Production_Run_Trial_Record.py's overview table, Create/Edit
forms (a hidden field's historical value is left untouched, never
blanked, per F22-08's no-destructive-migration rule), and CSV import;
reports.py's Batch Release Record and Sample Certificate of Analysis
report builders/renderers (the "Block reference" row is omitted entirely
from the report, not shown as "-").

4. F22-05 (Block reference import validation): the Production Run CSV
importer's pre-persistence row validation now rejects any row with a
populated block_reference value whose resolved machine is not PM-500,
so a bad row never reaches the DB.

5. F22-06/F22-07 (Quality Issue taxonomy applicability + quarantine):
quality_issue_taxonomy.py gained a per-entry state (STATE_ACTIVE /
STATE_QUARANTINED) and an optional production_methods applicability list
(None = Global). 10 entries quarantined (removed from every NEW-selection
surface - manual entry, CSV import, Customer/Optimization Trial paths -
but still fully readable/reportable on any existing row): Bottom
cavitation, Bottom skin densification, Gross splits, Heavy skin, Low
block density, Splits - abnormal fine/broken cell structure, Splits -
normal cell structure open cells, Stratification, Tacky block surface,
Zigzag (tin) splits. 3 entries (Relaxation, Slow curing, Scorching) stay
ACTIVE-Global with their block-specific guidance text stripped. New
active_categories()/active_issue_types_for_category()/
lookup_active_case_insensitive() functions; pages/6_Quality_Observation.py's
category and issue-name pickers use them, with an include_names escape
hatch so a row already carrying a quarantined value stays editable/
visible without ever offering that value as a fresh pick elsewhere (same
"deprecate in place, never touch history" pattern as the WP7 Phase 5
D5-05 quarantine).

Regression: new tests/test_cr22_semantic_freeze_evidence.py (6 direct-
evidence tests covering block_reference gating at the report-builder
level for both report types, the helpers/reports gate-sync guard, the
32-active/10-quarantined taxonomy count + name match, historical
readability via include_names, and a semantic guard against "Foam scope"
wording ever reappearing) plus targeted fixes to 3 pre-existing tests
whose fixtures/assertions assumed the pre-freeze wording, order, or a
non-PM-500 default method: test_cr11_functional_evidence_group_d.py's
seeded_grade_chain fixture (now uses the real "PM-500" controlled_id so
its own block_reference edit/import tests exercise the field the way
it's actually gated), test_cr18_product_family_terminology.py (Product
scope order/label + a line-number allowlist shift), and
test_cr12_report_scope_isolation.py (Trend Analysis's Analyze-by radio
now defaults to Product family, so the grade-selector test must switch
modes explicitly before asserting on it). Full serial suite (4-way
file-partition split, no xdist/parallel workers): 198 + 198 + 83 + 132 =
611 passed, 0 failed, 0 skipped.
"""

VERSION_0_65_1_NOTES = """
CR-22 correction (2026-08-16): Charlie's focused closeout return on the
original CR-22/AF22-01 submission rejected the F22-06 evidence as a
"helper-function truth table" and required six items completed with
genuine AppTest-driven (rendered UI) evidence before re-review, plus a
rerun of the customer-facing semantic inventory against the current
v0.65.0 codebase (not just a "Foam scope" phrase search).

1. F22-06 mechanism gap (the actual defect Charlie's return was about):
the taxonomy quarantine mechanism from v0.65.0 filtered STATE_QUARANTINED
entries but never actually filtered by production_methods applicability -
every ACTIVE entry on the current production taxonomy happens to be
Global, so the gap was invisible without a synthetic PM-500-only entry.
Fixed: quality_issue_taxonomy.lookup_active_case_insensitive() now takes
an optional production_method_controlled_id and excludes any entry whose
production_methods list doesn't contain it (mirrors
active_issue_types_for_category()'s existing rule). pages/
6_Quality_Observation.py's _issue_type_picker() now takes the same
parameter and both call sites (Add form, Edit form) resolve it from the
selected Production Run's Production Method before rendering the picker
(None - Global only - for Customer Trial/Optimization Trial sources, or
when no Production Run is selected yet); the CSV/Excel import tab's row
validation and canonical-name resolution now do the same resolution
per-row from the row's production_run_id.

2. Full semantic inventory rerun (Section 3 of Charlie's return) found
one genuine residual leak beyond the "Foam scope" search: three
render_function_action_intro() calls (pages/5_Physical_Property_Result.py,
pages/6_Quality_Observation.py, pages/9_Samples_Conditioning.py) still
used PM-500-specific "block" phrasing in their rendered Function/Action
intro paragraphs ("where in the block it was cut/showed up", "block
location", "location in the block") even though the corresponding field
LABELS (Sample Location Reference / Observed location) were already
correctly reworded under F22-03 in the original CR-22 pass - the intro
copy had been missed. Reworded to method-neutral phrasing on all three
pages (sample location / observed location, matching each page's own
field label).

3-6. Rendered-UI evidence for F22-06 (a synthetic PM-500-only taxonomy
entry visible only for a PM-500 run and absent for both trial paths),
direct PM-100/PM-500/PM-800 block_reference behavior (Add/Edit field
presence, overview-table empty marker, CSV import accept/reject), the
universal-wording CSV import caption, and Customer/Optimization Trial
Quality Issue picker/historical-readability paths: new tests/
test_cr22_correction_focused_closeout.py (13 tests), all driving real
AppTest widgets (selectbox .options, dataframe .value, radio .options)
rather than calling business-logic functions or checking source strings -
per Charlie's explicit "helper-function truth table alone does not
satisfy this acceptance item" standard. One genuine AppTest framework
quirk was found and worked around while writing these: presetting a
dataframe widget's on_select selection state resolves to the wrong row
if done on a second .run() of an AppTest instance that already completed
one unselected run; fixed by using a throwaway probe AppTest to
determine row order, then a fresh AppTest instance (preset before its
own first .run()) per selection needed - documented in the test file's
own docstring for future maintainers.

Regression: the CR-18 "foam family" line-number allowlist
(test_cr18_product_family_terminology.py) needed two entries' line
numbers bumped again (635->641, 617->623) because the two explanatory
comments added in item 2 above shifted every line below them - a pure
allowlist-drift fix, not a new terminology leak (confirmed via a repo-
wide grep for "where in the block"/"block location"/"location in the
block" finding zero remaining hits and zero pre-existing test assertions
on the old wording). Full serial suite (6-way file-partition split, no
xdist/parallel workers): 173 + 188 + 64 + 67 + 59 + 73 = 624 passed, 0
failed, 0 skipped, across all 55 test files.

v0.65.2 (2026-08-16): Production hotfix - Stefan reported a live crash
immediately after the v0.65.0->v0.65.1 stale-Streamlit-Cloud-cache issue
was resolved:

    TypeError: '<' not supported between instances of 'NoneType' and
    'datetime.datetime'
    pages/15_Recipe_Optimization.py, line 121, in <module>
        versions = sorted(grade.recipe_versions, key=lambda v: v.created_at)

Root cause: RecipeVersion.created_at (db.py) is DB-nullable - its
`default=dt.datetime.utcnow` is a Python-side ORM default that only fires
when the column is omitted from an ORM-issued INSERT, not a NOT NULL
constraint - so any row written via direct SQL (this project's
established pattern for data-loading/reconciliation batches: WP5 waves,
CR-08 reconciliation, DEF-011, Post-G5 imports, etc.) can legitimately
skip it and land NULL. Confirmed live in Supabase: grade "RF-COLDROOM-001"
(foam_grades.id=7) had exactly one recipe version (recipe_versions.id=6,
its only and active version) with created_at NULL, plus its
production_runs.id=15 row with the same NULL - so every visit to Recipe
Optimization with that grade selected crashed the whole page for every
reviewer, not just whoever created the row.

Fix: a None-safe sort key, `v.created_at or dt.datetime.min` (treats a
NULL creation time as "oldest", the same interpretation already used
elsewhere on this page for a missing created_by), applied in the two
places this repo has this exact sort - pages/15_Recipe_Optimization.py
and the PI3 query tool's own identical copy in ai_assistant.py's
`analysis_type == "recipe_cost"` branch (found via a targeted repo-wide
grep for `key=lambda \w+: \w+\.created_at`, confirming these are the only
two occurrences of the risky pattern app-wide). Both files needed a new
`import datetime as dt` added, since neither previously imported the
datetime module directly.

New direct-evidence regression test (tests/
test_recipe_version_null_created_at_defect.py): seeds a FoamGrade with a
RecipeVersion whose created_at is explicitly None - the exact shape of
the live defect, not a helper-function truth table - and drives pages/
15_Recipe_Optimization.py through AppTest, asserting no unhandled
exception. A companion unit test proves the sort key itself doesn't raise
on a mixed None/datetime list and orders the None entry first (oldest).
Targeted regression (6 recipe-related test files + 6 ai_assistant-
importing test files, 123 tests total) passed clean.

Known open item, NOT closed by this fix: the 3 live NULL created_at rows
in Supabase (foam_grades.id=7, recipe_versions.id=6, production_runs.id=
15) remain NULL - an attempted backfill UPDATE was blocked by this
environment's own write-permission guardrail, so it could not be applied
from here. This code fix prevents the crash regardless of whether that
backfill ever happens (any future NULL created_at row hits the same safe
fallback), but the 3 rows' actual creation timestamps are still unknown
pending either a manual Supabase-side backfill or a decision that it's
not worth doing. Flagged to Stefan in the reporting conversation for this
fix, 2026-08-16.

v0.65.3, 2026-08-17: raised the cached-DB-session recovery cap in
app_rigid_foam.py from 1 to 2 attempts per browser tab.

Production incident that day: Process Parameters vs Product Properties
Correlation (page 17) crashed with the exact sa_exc.InvalidRequestError
class of failure already diagnosed and self-healed as of v0.55.0-era work
(see the "Production incident, 2026-08-05" comment on the pg.run() error
handler) - Streamlit cancelling an in-flight rerun mid-statement leaves
the cached SQLAlchemy Session's transaction state machine stuck, and
that's page-agnostic (breaks every page sharing that browser tab's
session, not just the one interrupted). The existing handler already
discards the broken session and silently reruns once per tab before
giving up; this incident's root cause was a burst of rapid clicks/reruns
in the same tab (live UAT browser-automation testing switching dropdowns
faster than each rerun could finish) triggering two of these
cancellations back-to-back, which exhausted the 1-attempt cap and
surfaced the raw crash instead of self-healing.

Fix: replaced the boolean "_sa_session_recovery_attempted" flag with an
integer counter ("_sa_session_recovery_attempts") and a new module-level
_MAX_SESSION_RECOVERY_ATTEMPTS = 2 constant, so up to 2 consecutive
cancellations self-heal silently before the error is allowed to surface.
Still finite (not unlimited) - a different, page-code-level bug that
happens to also raise InvalidRequestError still surfaces normally rather
than looping forever. Verified live: reloaded the crashed browser tab and
confirmed Process Parameters vs Product Properties Correlation loads
cleanly again with a fresh session. No test file exists for this handler
specifically (it wraps pg.run()/st.rerun() at the app.py routing layer,
not independently unit-testable the way page-level logic is) - verified
via py_compile plus the full existing test suite passing clean, and via
the live reload.

v0.66.0, 2026-08-17: Phase 8 (PM-800 "Discontinuous Appliance & Cavity
Foaming") Wave A - data foundation + Quality Issue DB cutover, per
Charlie's P8-D01..D08 binding architecture decisions on the JC Phase 8
implementation plan review.

Data foundation (Supabase rigid_foam schema, live writes):
- 3 new `applications` rows: APP-320 "Refrigerator or freezer door",
  APP-330 "Commercial refrigeration equipment", APP-340 "Water-heater
  insulation" (table now 7 rows total).
- 9 new `process_setting_definitions` rows (PS-005/006/025/028/047/051/
  069/074/076) sourced from WP2 sheet 04, `production_method_id` left
  NULL on all of them (that column is dormant/deprecated per its own
  db.py docstring - WP7 Phase 1 architecture correction; real Method/
  Machine scoping lives exclusively in ProcessSettingApplicability).
  UOM gap flagged, not fabricated: bar/minute/kg/kg-per-m3 have no
  controlled `units_of_measure` master entry today, so `unit_id` is left
  NULL on the affected new definitions, consistent with the existing
  majority-null pattern - a new UOM row was not invented without
  Charlie's sign-off.
- 43 new `process_setting_applicabilities` rows for PM-800
  (production_method_id=17), classified Machine vs Method by a documented
  textual rule (pure "Machine" wording, exact match -> Machine-scoped,
  machine_id=4 "Appliance Cavity Foaming Unit"; any dual/derived/
  configured/product/plant/global wording -> Method-scoped,
  machine_id=NULL): 8 Machine-scoped (PS-006/020/021/022/024/026/027/034)
  + 35 Method-scoped = 43 total, verified by count against WP2 sheet 04.

Quality Issue DB cutover (P8-D01): pages/6_Quality_Observation.py and
reports.py's `build_quality_issue_report_data()` now read the customer-
facing Quality Issue picker's controlled vocabulary from the
QualityIssueType/PossibleCause/IssueCauseLink DB masters via new module
quality_issue_registry.py, replacing quality_issue_taxonomy.py's static
Python dict for this app (that module is left in place, unused going
forward, per Charlie's instruction not to maintain a second PM-800/Rigid
list inside a Flexible-sourced file). Schema additions: QualityIssueType.
state ('active'|'quarantined', CR-22/AF22-01 equivalent, all 64
pre-existing WP5 Wave 3 rows default 'active') and new
QualityIssueTypeApplicability table (zero rows for an issue = Global,
same convention as ProcessSettingApplicability). Fixed one pre-existing
bug surfaced during this cutover: the "Breakdown by issue" chart on
pages/6 referenced the old taxonomy call incorrectly (NameError) - now
uses quality_issue_registry.lookup().

Regression: new tests/test_phase8_wave_a_quality_issue_cutover.py (13
tests) covering schema build, registry behavioral equivalence, and page/
report cutover verification. Fixed 3 pre-existing test fixtures broken by
moving the picker's source of truth from a static module (no DB seeding
needed) to the DB: tests/test_cr11_functional_evidence_group_b.py's
Quality-Issue fixtures now seed a real "Shrinkage"/"Density, shape &
dimensional" QualityIssueType row; tests/
test_cr22_correction_focused_closeout.py's shared three-method fixture
now seeds the full 42-entry (32 active + 10 quarantined) frozen AF22-01
taxonomy as real DB rows mirrored from quality_issue_taxonomy.py, and its
F22-06 PM-applicability proof now inserts a real synthetic QualityIssueType
+ QualityIssueTypeApplicability row instead of mutating the now-unread
qit module; tests/test_cr18_product_family_terminology.py's line-number-
pinned "foam family" allowlist re-pinned for pages/6's shifted comment
line (623 -> 630) after the breakdown-chart bug fix added lines above it.
Full serial regression across all 57 test files (637 tests) run in 4
chunks after this batch: 637 passed, 2 skipped (pre-existing, unrelated),
0 failed.
"""

VERSION_0_67_0_NOTES = """
v0.67.0, 2026-08-18: Phase 8 Wave A correction batch #1/#3, per Charlie's
2026-08-17 Wave A closeout return (Phase8_PM800_WaveA_Closeout_Review_
Return_to_JC.docx), which required 4 corrections before Wave A acceptance.
This batch closes correction #1 in full and correction #3 in full;
corrections #2 (controlled UOM reconciliation) and #4 (CR-22 state/
applicability live-migration evidence) continue separately.

Correction #1 - PS-051 applicability scope (Supabase data fix, live write):
Charlie's review found PS-051 ("Optional machine capability" wording per
WP2) misclassified Method-scoped by v0.66.0's Machine/Method rule, which
only caught pure/exact "Machine" wording and missed this convention.
`UPDATE rigid_foam.process_setting_applicabilities SET machine_id = 4
WHERE id = 36` (the PS-051/PM-800 row) moves it to Machine-scoped for
machine_id 4 "Appliance Cavity Foaming Unit". Verified live: PM-800's 43
process_setting_applicabilities rows are now 9 Machine-scoped + 34
Method-scoped, matching Charlie's required corrected count exactly (was
8/35 in v0.66.0).

Correction #3 - Flexible edition isolation evidence: Charlie required
direct evidence that Rigid reads QualityIssueType/PossibleCause/
IssueCauseLink from the database (the v0.66.0 P8-D01 cutover) while the
Flexible edition (PI3_Plant_Edition_App, a separate codebase living
alongside this repo) still uses its own static quality_issue_taxonomy.py,
plus regression coverage for both edition paths. New tests/
test_phase8_wave_a_flexible_edition_isolation.py: static source checks
confirming Flexible's pages/6_Quality_Observation.py and reports.py import
quality_issue_taxonomy only (never quality_issue_registry, which does not
even exist in Flexible's app directory) while this repo's same files
import quality_issue_registry only (never quality_issue_taxonomy); plus a
subprocess-isolated AppTest execution proof that Flexible's Quality Issue
page renders cleanly off its own static taxonomy against a fresh SQLite DB
with quality_issue_registry never touching sys.modules. Run in a genuinely
separate Python process because Rigid and Flexible define same-named
top-level modules (db, helpers, reports, access_control, tenant_scope,
quality_issue_taxonomy) that would silently collide if both were imported
into one process. The 4 sibling-directory-dependent checks skip cleanly
(with a stated reason) when the Flexible app isn't present alongside this
repo, e.g. a standalone clone of just this repository; verified passing
(not skipped) against the real sibling directory on the authoring machine,
including the subprocess execution proof.

Regression: targeted run (new isolation file + the v0.66.0 cutover test +
the 3 fixtures the cutover touched) - 42 passed, 4 skipped (sibling-app
checks, expected in this sandbox's mount layout), 0 failed. Full 57-file/
637-test suite not rerun in this batch (no production code paths changed,
only a live data UPDATE and a new test file); scheduled for the next full
regression pass alongside corrections #2 and #4.

Corrections #2 and #4 remain open - see the revised Wave A closeout for
their status. No new Phase 8 scope introduced.
"""

VERSION_0_67_1_NOTES = """
v0.67.1, 2026-08-18: Phase 8 Wave A correction #4 (CR-22 state/applicability
live-migration evidence), closing 3 of Charlie's 4 required Wave A
corrections (see v0.67.0 for #1 and #3). Correction #2 (controlled UOM
reconciliation) remains open - a genuine 3-way ID collision between the
WP1 source master, the Stefan-approved Phase 1 UOM Governance Correction
Register v1, and live Supabase state, requiring Charlie's ruling before any
UOM row is written; not something to guess at.

Live-data investigation (Supabase project aazkdsqpytjciiqtvnfj, rigid_foam
schema): `quality_issue_types` held 64 rows, every one `state='active'` -
the P8-D01 migration that added the `state` column only applied a blanket
default, it never carried CR-22/AF22-01's specific 32-active/10-quarantined
crosswalk from quality_issue_taxonomy.py into this table. Comparing names
confirmed why: the live 64-row WP5 Wave 3 taxonomy and the frozen 42-entry
CR-22 taxonomy are two disjoint, independently-sourced lists (one
"Shrinkage" name coincidentally in both) - CR-22's quarantine work was done
entirely against the Flexible-slabstock-sourced static module, which the
P8-D01 cutover replaced with an unrelated Rigid-specific DB master. None of
CR-22's 10 quarantined terms occur in live `quality_observations.
observation_type` data, so Charlie's literal scenario doesn't presently
apply to those 10. But `select distinct observation_type from
quality_observations` surfaced a related, real gap: 7 distinct historical
values (Boiling, Coarse foam, Collapse, Friable / loose foam, Scorching,
Shrinkage, Voids / pinholes), all `active` in the old taxonomy, only one of
which ("Shrinkage") has a matching row in the new 64-row master - the other
6 would silently fail to resolve through quality_issue_registry.lookup()
post-cutover, losing their "Issue category" in report breakdowns.

Applying Charlie's own stated rule (retain an absent-from-master historical
term as a quarantined historical-only record) to this evidence, 6 new rows
were added live: QI-090 Boiling, QI-091 Collapse, QI-092 Scorching, QI-093
Coarse foam, QI-094 Friable / loose foam, QI-095 Voids / pinholes - all
`issue_category='Legacy (pre-cutover)'`, `state='quarantined'`, zero
QualityIssueTypeApplicability rows (Global, per the existing "zero rows =
Global" convention), each `definition` noting the old taxonomy's category
and, where wording is close to a live active term, which live controlled_id
it must not be confused with (e.g. QI-092 Scorching vs QI-036 "Core
scorching"). Live count after the insert: 64 active + 6 quarantined = 70
total (was 64 active + 0 quarantined before).

New tests/test_phase8_wave_a_cr22_migration_evidence.py (6 tests) proves,
against a SQLite fixture rebuilding this exact live shape (the 7 real
historical observation_type values, the Shrinkage overlap, the 6 new
quarantined rows, a handful of live active neighbors to prove no name
collision): (1) active-picker exclusion - the 6 historical-only rows never
appear in active_issue_types_for_category()/active_categories(), and
lookup_active_case_insensitive() returns None for all 6 both with and
without a PM-800 context; (2) historical readability - all 7 real
historical observation_type values resolve via lookup() and
all_issue_names(), and a direct call through reports.py's
build_quality_issue_report_data() confirms the "Issue category" breakdown
shows "Legacy (pre-cutover)" rather than silently falling through to
"Other / not yet classified"; (3) Production Method applicability - the 6
rows carry zero QualityIssueTypeApplicability rows, confirmed both via a
direct query and via the PM-800-scoped registry call path.

Regression: targeted run (this new file + the 2 other Wave A correction
test files + the 3 CR-22/A5-08 files the P8-D01 cutover touches) - 48
passed, 4 skipped (Flexible-sibling-app checks, expected in this sandbox's
mount layout), 0 failed. Full 57-file suite not rerun in this batch (no
production code paths changed, only a live data INSERT and a new test
file); scheduled for the next full regression pass once correction #2 is
unblocked and the revised Wave A closeout is assembled.
"""

VERSION_0_67_2_NOTES = """
v0.67.2, 2026-08-18: Phase 8 Wave A correction #2 (controlled UOM
reconciliation) - closes the last of Charlie's four required Wave A
corrections. Charlie's ruling of 18 August ("Phase8_PM800_WaveA_Correction_
Review_and_UOM_Ruling_to_JC.docx") resolved the 3-way identifier collision
v0.67.1 flagged: for these four physical units the Phase 1 / WP2 technical
UOM master numbering is the active authority, superseding the WP1
10_Units_Bases numbering where the two conflict, with no fresh UOM-096..099
block and existing conflicting legacy rows left intact for a separate
reconciliation.

Live implementation (Supabase project aazkdsqpytjciiqtvnfj, rigid_foam
schema), both source masters read directly before writing and agreeing on
every field - WP2_Technical_Master_Data.xlsx sheet 03_UOM and Phase_1_UOM_
Governance_Correction_Register_v1.xlsx sheet 02_Canonical_UOM:

  UOM-001  kg/m3  kilogram per cubic metre  Density   SI
  UOM-011  min    minute                    Time      SI accepted
  UOM-015  kg     kilogram                  Mass      SI
  UOM-019  bar    bar                       Pressure  SI accepted

units_of_measure went 17 -> 21 rows. Five ProcessSettingDefinition rows
moved off unit_id NULL: PS-076 -> UOM-001, PS-069 -> UOM-011, PS-074 ->
UOM-015, PS-028 -> UOM-019, PS-051 -> UOM-019. Both tables were snapshotted
first, as rigid_foam._backup_units_of_measure_20260818 and
rigid_foam._backup_psd_unitlink_20260818. Verified live afterwards: zero
pre-existing unit rows altered, zero duplicate controlled_ids, zero other
Process Settings touched, PM-800 applicability split still 9 Machine / 34
Method.

New tests/test_phase8_wave_a_uom_controlled_resolution.py (23 tests) proves
against a SQLite fixture rebuilding this exact live shape: each seeded row
matches the WP2 master field for field; each of the five definitions
resolves through its FK to the intended controlled UOM; PS-028 and PS-051
share one bar row rather than two parallel ones; and the WP7 Phase 1
before_insert/before_update hook holds - a ProcessParameterValue written
with a conflicting unit string is stored carrying the definition's
controlled symbol, re-derives on update, follows a relinked definition, and
degrades to None rather than to a stale symbol when a definition carries no
controlled unit. The four retained legacy rows (UOM-038 second, UOM-039
millimetre, UOM-040 degree Celsius, UOM-041 percent) are pinned as distinct
from the ruled block, with their canonical identifiers (UOM-010, UOM-007,
UOM-009, UOM-006) confirmed still unissued so the separate reconciliation
stays possible.

Regression: full suite, all 60 test files in one serial run - 667 passed,
6 skipped, 0 failed out of 673 collected (was 644 passed / 6 skipped / 650
collected at v0.67.1; the 23 new tests are this file's). All 6 skips are
the same pre-existing cause named in the v0.67.1 return - the Flexible
edition app is not a sibling directory in this run environment, so the 2
CR-12 reporting-parity checks and the 4 Wave A edition-isolation checks
cannot evaluate. Run against the pinned dependency set (streamlit 1.60.0,
pandas 2.3.3, pyarrow 24.0.0); an unpinned pandas 3.0 reproduces exactly
the Arrow/dtype breakage requirements.txt documents, in the three sample
CSV import paths.

Data-only change plus a new test file; no production code path was
modified. All four Wave A corrections are now closed on the data and test
side.
"""

VERSION_0_68_0_NOTES = """
v0.68.0, 2026-08-18: Controlled UOM reconciliation - the separate
reconciliation Charlie's Phase 8 Wave A UOM ruling reserved, now completed.

Minor rather than patch: this changes what legacy_migration.py seeds, which
is a production code path, and it retires four controlled-vocabulary rows.
No DDL - the schema is unchanged.

WHY THIS WAS BIGGER THAN FOUR ROWS

Wave A closed a three-way identifier collision for kilogram, minute and bar.
Scoping the reserved reconciliation showed that collision was a symptom.
Most of the canonical unit master had never been loaded into the live
rigid_foam schema, so every work package needing a plain unit found nothing
to link to and either left the link NULL - Wave A's five settings - or
created its own row - WP7 Phase 3's UOM-038/039/040/041 block. Two
different-looking symptoms, one cause.

The originating document for that block was found, in code rather than in a
document: legacy_migration.ENVIRONMENT_OUTCOME_UOMS, whose comment recorded
that none of those four plain units existed live and that the highest live
row was UOM-037. That reading of the live table was correct. What was wrong
was the live table.

MASTER DATA (live rigid_foam schema, no DDL)

26 canonical rows seeded - 21 transcribed from the Phase 1 / WP2 technical
master sheet 03_UOM, plus the 5 remaining "New canonical" rows from the
Phase 1 UOM Governance Correction Register v1 sheet 02_Canonical_UOM.
units_of_measure went 21 -> 47 rows.

Deliberately not seeded, per the register's own decisions: WP2's UOM-023 php
and UOM-024 wt% (decisions UOM-D-001/002 map those meanings onto the live
UOM-030 and UOM-031), and WP2's UOM-030 "index unit" and UOM-031 "class"
(decision UOM-D-005 moved those to the live UOM-101 and UOM-102).

Seven Process Setting definitions re-pointed, per Stefan's decisions of
18 August recorded in the reconciliation ruling:

  PS-079 Rise time            -> UOM-010 second
  PS-078 Foam height          -> UOM-007 millimetre
  PS-008 Ambient temperature  -> UOM-009 degree Celsius
  PS-009 Relative humidity    -> UOM-029 relative humidity percent (%RH)
  PS-025 Ratio deviation      -> UOM-006 percent
  PS-023 Set mass ratio A:B   -> UOM-100 mass ratio (was unit_id NULL)
  PS-024 Actual mass ratio A:B-> UOM-100 mass ratio (was unit_id NULL)

PS-009 is a correction, not a preference. WP2 sheet 07_Process_Settings gave
%RH as its default unit and the row's own description column already said
%RH; only the unit link disagreed, because UOM-029 had never been loaded.
Nothing numeric changes - ambient_humidity_pct holds the same value.

UOM-038, UOM-039, UOM-040 and UOM-041 deleted, after a direct check that all
seven foreign-key columns able to reference units_of_measure held zero
references to them. Final count 43 rows.

Both tables snapshotted first, as rigid_foam._backup_units_of_measure_20260818b
and rigid_foam._backup_psd_unitlink_20260818b.

Verified live afterwards: 43 rows, zero duplicate controlled_ids, zero
duplicate symbols, zero duplicate names, zero orphaned unit foreign keys,
the five Wave A links intact, and the PM-800 applicability split still
9 Machine / 34 Method.

CODE

legacy_migration.py - ENVIRONMENT_OUTCOME_UOMS now seeds UOM-007, UOM-009,
UOM-010 and UOM-029 with their full WP2 fields, and the humidity entry in
ENVIRONMENT_OUTCOME_FIELD_MAP resolves on "%RH". The module stays idempotent
in both directions: a no-op against the reconciled table, and a
create-once-then-stop against an empty one. The original reasoning is kept
in the comment rather than deleted, because it was sound.

TESTS

New tests/test_uom_master_reconciliation.py (67 tests) - the standing guard.
Every live row matches the register exactly and the register holds nothing
the live table does not; no two rows share a controlled_id, a symbol or a
meaning; the retired identifiers are absent and the register-mapped source
identifiers are never created; the seven re-pointed settings resolve; and
legacy_migration seeds canonical identifiers without resurrecting the
retired block.

The duplicate-symbol guard is a correctness precondition rather than
tidiness. ensure_environment_outcome_definitions() resolves a unit by
building {u.symbol: u} over the whole table, which silently discards a row
when two rows share a symbol - exactly what UOM-041 "%" and the canonical
UOM-006 "%" would have produced the moment the canonical row was loaded.

tests/test_phase8_wave_a_uom_controlled_resolution.py - the Wave A pin that
held the four rows as distinct now asserts the completed end state: each
retired identifier is absent and its meaning resolves to exactly one
canonical row. Wave A left that pin so a later reconciliation could not fold
them in silently; this is that reconciliation doing it openly.

tests/test_wp7_phase3_reconciliation.py - its UOM assertion moved to the
canonical identifiers.

Full regression: 734 passed, 6 skipped, 0 failed of 740 collected across 61
files, run as one serial pass. Was 667 passed / 6 skipped / 673 collected at
v0.67.2, so the 67 new tests are the whole delta. All 6 skips are the
pre-existing Flexible-sibling-app layout cause.

RAISED AS SEPARATE WORK, NOT DONE HERE

The controlled master specifies two calculations the application does not
implement - A:B mass ratio, and ratio deviation percent as
(actual - set) / set x 100. Both settings are marked Derived, so nobody
should be typing them; today nobody can avoid it.

Ratio deviation keeps its sign, positive meaning the actual ratio came out
above the set ratio. Presenting that to a user as over- or under-indexed
needs one more thing that is not true yet: analytics._component_side()
documents that this database uses the A-side label inconsistently - the WP3
seed recipe calls the isocyanate the A-side, the WP5-era reference recipes
call it the B-side - and its docstring instructs callers not to guess.
Checked live: stream_assignment is NULL on all 14 recipe component rows and
none carry the free-text prefix, so that helper resolves nothing for any
recipe in the database and A:B ratio reporting does not function on live
data at all.
"""

VERSION_0_69_0_NOTES = """
v0.69.0, 2026-08-19: Rename the screen directory pages/ -> views/, closing a
silent access-control bypass. Also: RLS drift closed on the live schema.

Minor rather than patch: 30 files move and the application's directory
layout changes. No behaviour change for a user, and no URL changes.

THE DEFECT

Streamlit 1.60.0 decides whether this app's entrypoint runs at all from
whether a directory literally named "pages" sits next to it. From Streamlit's
own source, not inferred:

  runtime/pages_manager.py - uses_pages_directory is a PROCESS-WIDE class
  attribute, set once on the first PagesManager constructed, from
  Path(main_script_parent / "pages").exists().

  runtime/scriptrunner/script_runner.py -
      if PagesManager.uses_pages_directory: _mpa_v1(main_script_path)
      else:                                 exec(code, module.__dict__)

  commands/navigation.py - st.navigation() sets the flag False.

In the legacy branch app_rigid_foam.py never executes. Streamlit globs the
directory, sorts it, and builds its own flat navigation from raw filenames.
Every access_control page filter is skipped, so every screen becomes
reachable by anyone with the URL. The visible symptom is a flat sidebar with
no logo, version or sections, which a reload appears to fix.

It appears intermittent because the flag only flips once st.navigation() is
actually reached, and it is process-wide rather than per-session: the first
session to get that far fixes it for everyone, for the life of the process.
So it shows on the first load after a deploy or reboot, particularly when
deep-linking to a screen URL rather than the root.

The case that is not transient, and the reason this is a defect rather than
a cosmetic bug: if anything above st.navigation() raises, the flag never
flips at all and the process stays in unfiltered legacy mode until it is
restarted, with no traceback. init_db() at line 616 and get_session() at
617 run about 35 lines before st.navigation() at 653. The Flexible edition
hit exactly this on 18 August 2026 through a cold-start database error.

Found and fixed in the Flexible edition first; verified present here before
acting, and reproduced directly against Streamlit's own PagesManager rather
than taken on trust.

THE FIX

git mv pages views - 30 files, recorded as renames so history is preserved.
With no directory named "pages" beside the entrypoint the flag evaluates
False at construction, so the legacy branch cannot be taken on any request,
at any point in startup, however the entrypoint fails. This closes the
window rather than narrowing it.

29 st.Page("pages/...") declarations updated in app_rigid_foam.py, plus path
references in comments and docstrings across 79 further modules and tests.

URLs are unchanged. st.Page infers url_path from the filename, not the
directory, so every existing bookmark and shared link still resolves.

Three references deliberately still say "pages", all pointing at the
Flexible edition, which keeps that directory name:
tests/test_phase8_wave_a_flexible_edition_isolation.py FLEX_PAGE_QI, and
two in tests/test_cr12_reporting_parity.py. That parity helper now takes the
directory name as an argument instead of hard-coding it, so it compares each
edition against the directory that edition actually has.

A block comment in app_rigid_foam.py records why the directory is not called
pages/, naming the Streamlit mechanism. The name looks like an oddity
otherwise, and the next person to tidy the repository reintroduces the bug.

TESTS

New tests/test_navigation_directory_guard.py (6 tests): views/ exists and no
pages/ directory sits beside the entrypoint; Streamlit's own PagesManager
resolves this layout to False; Streamlit still branches on that flag, so a
future upgrade that removes it fails here rather than silently making the
rationale obsolete; every st.Page path resolves to a real file and none
points at the old directory; every file in views/ is declared in the
entrypoint, since under st.navigation nothing is auto-discovered; and the
entrypoint still carries the explanation.

Full regression: 740 passed, 6 skipped, 0 failed of 746 collected across 62
files. Was 734 / 6 / 740 at v0.68.0, so the 6 new guard tests are the whole
delta. The 6 skips remain the Flexible-sibling-app layout cause.

LIVE SCHEMA - RLS DRIFT CLOSED, SAME RELEASE

Row Level Security was enabled with no policies on 7 rigid_foam tables that
had drifted: customers, foam_grade_machines, plant_production_methods,
quality_issue_type_applicabilities, reference_formulation_families,
reference_formulation_performance_results and
reference_formulation_processing_notes. Tables created later by
create_all() do not inherit RLS, which is how they were missed.

The four _backup_units_of_measure / _backup_psd_unitlink snapshot tables
were dropped. Wave A and the controlled UOM reconciliation are both accepted
and closed, so the reversibility they existed for is no longer needed.

rigid_foam now reads 95 tables, 95 with RLS enabled, 0 policies - matching
the public schema's 47 / 47 / 0 exactly.

Worth recording accurately: the exposure here was smaller than the Flexible
equivalent. anon and authenticated hold no USAGE on the rigid_foam schema
and no table grants within it, so those rows were unreachable through the
Supabase API regardless of RLS. In public those roles do hold SELECT, which
is why RLS was the only barrier there. This was consistency drift, not an
open door - fixed because the pattern should hold and because a later USAGE
grant would otherwise open it silently.
"""

VERSION_0_70_0_NOTES = """
v0.70.0, 2026-08-19: Recipe Version 6 restored, the direct-import route for
Recipe Components retired, and a mis-targeted-import warning added.

Per Charlie's Decision 1 Ruling and Execution Instructions, 19 August 2026.
Minor rather than patch: a new validation surfaces in the Recipes page.

WHAT HAD HAPPENED

On 12 August 2026 a Phase 1 import file, 01_DIRECT_IMPORT/07_Recipe_Components.csv,
carried a hard-coded recipe_version_id of 6. That id existed and belonged to an
unrelated polyether PUR recipe on RF-COLDROOM-001, so all nine of its polyester
PIR rows imported successfully and merged two formulations into one Recipe
Version.

The application was not at fault. Its importer checks whether the
recipe_version_id exists, and it did. Nothing available to the importer could
have said that a valid id was the wrong one.

It stayed invisible for seven days. It surfaced on 19 August while auditing
A:B stream assignment, when Recipe Version 6 was found holding two components at
100 php, two isocyanates, two physical blowing agents, and both a PUR gelling
catalyst and two PIR trimerisation catalysts. php is parts per hundred polyol, so
one formulation carries exactly one 100 basis.

THE CORRECTION, ON CONTROLLED EVIDENCE

Charlie's two originally named sources did not cover this recipe: the 10 August
pre-reset snapshot holds recipe_versions 1 to 5 only, because Recipe Version 6
was created after that reset, and no migration creates the recipe or writes
recipe_components. His ruling accepted the import manifest as controlled
pre-import evidence instead.

Three independent identifiers agreed on the same nine rows: they are exactly the
nine named in the defective file, they are the only nine carrying the "Belongs to
published recipe variant TCPP" note in live data, and the five that remain appear
in no import package anywhere in the Phase 1 folder.

Snapshot taken immediately before the change, both with RLS enabled to match the
schema pattern: rigid_foam._backup_recipe_components_20260819 (14 rows) and
rigid_foam._backup_recipe_versions_20260819 (1 row).

Nine rows deleted, ids 58 to 66. No foreign key anywhere in the schema references
recipe_components, verified before the delete. Recipe Version 6 now holds its five
established components, all five byte-identical to the snapshot - no value was
changed:

  Lupranol 3300    100 php   Base polyol
  Lupranate M20    145 php   Isocyanate
  POLYCAT 5        1.2 php   Gelling catalyst
  DABCO DC 193     2.0 php   Cell stabilizer
  Cyclopentane     12.0 php  Physical blowing agent

The php basis is coherent again: polyol total 100, one isocyanate. Both were
doubled before.

IMPORT ROUTE RETIRED

01_DIRECT_IMPORT/07_Recipe_Components.csv moved to
01_DIRECT_IMPORT/_RETIRED/ and kept as the evidence record. IMPORT_ORDER.txt
rewritten to state the sequence: load 06_Recipe_Versions.csv, read each new
version's database id, write those ids into the blank recipe_version_id column of
02_ID_DEPENDENT_IMPORT/07_Recipe_Components.csv, then import components.

The TCPP, TEP and L 2000 published LANXESS variants stay out of this correction.
They remain source material for a separate controlled promotion into their own
Recipe Versions, per the ruling.

APPLICATION CHANGE

views/3_Recipe_Version_Record.py - the component importer now warns when a file
targets a Recipe Version that already holds components, naming the version and its
current component count. That is the one thing the application can see and the
file cannot say, and it is the signature of a file pointed at the wrong id.

A warning rather than a block, because deliberately topping up a version is
legitimate. The point is that a merge can no longer happen silently.

TESTS

New tests/test_recipe_component_import_order.py (4 tests): a populated target is
detectable before import; the page carries the warning and states what goes wrong
rather than only that something is unusual; the existing unresolved-id rejection
still stands; and the doubled-php-basis signature that eventually exposed the
defect is pinned, so the same shape is recognisable if it recurs.

Full regression: 744 passed, 6 skipped, 0 failed of 750 collected across 63 files.
Was 740 / 6 / 746 at v0.69.0, so the 4 new tests are the whole delta. The 6 skips
remain the Flexible-sibling-app layout cause.

BROWSER VERIFICATION

Checked against the running application at v0.69.0. The Recipes page loads and
shows RF-COLDROOM-001 with active version v1. The Where Used view for Cyclopentane
reports one recipe version using it, RF-COLDROOM-001 v1, at 12.0 php - a retained
component at its unchanged value, read live after the correction.

The ingredients grid itself could not be captured: the browser tooling would not
scroll Streamlit's inner container, so the full five-row list was verified against
the database rather than on screen.
"""

VERSION_0_70_1_NOTES = """
v0.70.1, 2026-08-19: P8-OWR-001 verified and closed. Test evidence only - no
application change was required.

Charlie's Phase 8 Open Work Register v1 asked for a direct check of the Rigid
Foam session lifecycle rather than an inference from the Flexible Foam handoff.
The handoff proves the defect in Flexible Foam; it does not establish it here.

FINDING: RIGID FOAM DOES NOT HAVE THE FLEXIBLE FAILURE

The Flexible failure needs one precondition - a Streamlit rerun that ends with a
transaction still open. The connection then stays checked out, Supabase's
five-minute idle_in_transaction_session_timeout terminates it, and the next query
from that browser tab dies on a dead socket. pool_pre_ping does not help, because
pre-ping validates at pool checkout and a Session holding an open transaction
never returns its connection to the pool.

That precondition cannot hold in Rigid Foam. app_rigid_foam.py wraps its pg.run()
call in try/finally and calls db.close_out_session() from the finally block, so
the transaction is committed or rolled back on every rerun - including reruns
where the routed page raised. The connection returns to the pool every time,
which is also what makes pool_pre_ping effective here rather than decorative.

Two further layers sit behind that, both already present:

  db.py sets pool_recycle=280, below the 300-second server timeout, so a pooled
  connection is retired before the server would consider terminating it.

  close_out_session()'s except branch covers the case where the connection has
  already died: if commit fails AND rollback also fails, the broken Session is
  discarded from st.session_state, so the next get_session() builds a fresh one
  rather than every later rerun of that tab failing identically until a full page
  reload.

TESTS

New tests/test_p8_owr_001_session_recovery.py (10 tests), exercising the paths
directly rather than asserting the code reads a certain way:

  A read opens a transaction, and close_out_session leaves none open.
  Closing out commits a page's own writes rather than discarding them.
  It is safe on a rerun that never touched the database.
  A dead connection - commit and rollback both failing - discards the broken
  Session, and the next get_session() returns a working one.
  A recoverable failure, where rollback succeeds, keeps the Session rather than
  throwing it away on every transient error.
  pool_recycle stays below the documented Supabase timeout.
  close_out_session() is reached from the finally block, so a page raising cannot
  leave the transaction open - the same failure mode by another route.

One correction worth recording. The dead-connection test first asserted that
st.session_state held no session afterwards, and failed against correct
behaviour: close_out_session logs the failure through audit_log, which calls
get_session() and caches a fresh Session. The property that matters is that the
BROKEN Session is gone, not that the key is absent. The test now asserts
identity rather than absence, and says so in place.

Full regression: 754 passed, 6 skipped, 0 failed of 760 collected across 64
files. Was 744 / 6 / 750 at v0.70.0, so the 10 new tests are the whole delta.

No browser verification: Charlie's return condition requires it only where an
application change was made, and none was.

v0.71.0, 2026-08-19: Phase 8 Decision 2 - controlled machine-stream
configuration. Which physical stream on a machine carries which chemical role
is now recorded data, versioned per machine, and stamped onto a production run
at creation.

WHAT WAS WRONG

analytics._component_side() has said for a while that this database uses the
A-side label inconsistently: the WP3 seed recipe calls the isocyanate the
A-side, the WP5-era reference recipes call it the B-side. Its docstring told
callers not to guess, and nothing existed for them to consult instead. So A:B
ratio reporting could not function, and any global rule anyone might have
written - "A is isocyanate" - would have been correct on some machines and
silently inverted on others.

The reason it varies is physical: a stream label describes how one machine is
plumbed, and two machines on one site can be plumbed opposite ways. So it is
not a property of the plant and not a property of the formulation. Charlie's
Decision 2 ruling put it on the machine, versioned, with a validity period.

WHAT WAS BUILT

db.py - MachineStreamConfiguration (the versioned header: machine, revision,
Draft/Active/Superseded, half-open effective period, source reference and
approval fields) and MachineStreamAssignment (the two mapping rows, one per
stream). ProductionRun gained a nullable machine_stream_configuration_id with
ON DELETE RESTRICT.

machine_stream.py, new - every control rule in one module: activation
validation, overlap detection, the freeze on Active and Superseded revisions,
supersede, resolution and one-time stamping. No function in it derives a
chemical role from a stream label or the reverse, and nothing else in the
codebase pairs the two.

views/31_Production_Equipment.py - the editor, inside the Edit/Delete tab under
the selected Production Unit / Cell, because a configuration has no meaning
without a machine. Create a Draft, map A and B, activate, supersede. Activation
reports every missing item at once rather than one per attempt. Active and
Superseded revisions are read-only; a change is a new revision.

views/4_Production_Run_Trial_Record.py - runs are stamped once, at creation,
manual and imported alike. The run record and the overview table show the
stamped revision, or Unresolved. Display never resolves and never writes.

WHY UNRESOLVED IS LEFT UNRESOLVED

A run with no configuration in force keeps a null reference and derives no A:B
ratio, and the eight pre-existing runs were not back-filled. Resolving at
display time, or back-filling from run_date, would let a configuration created
today rewrite what a block foamed in March was made of. An unresolved run is an
honest gap; a guessed one is a wrong answer that looks like a right one.

DATABASE

Migration phase8_decision2_machine_stream_configuration, applied live to
rigid_foam (97 -> 99 tables). btree_gist 1.7 was available and not installed;
installing it was ruling R2's precondition, so it was installed first and the
GiST exclusion constraint ex_msc_no_overlap created on
tsrange(effective_from, effective_to, '[)') for Active and Superseded rows
only. Plus uq_msc_one_open_active (partial unique: one open-ended Active
configuration per machine), the three unique constraints, the three check
constraints, and RLS enabled on both tables - 0 rigid_foam tables without it.

Idempotence: the full migration body re-run in place left the constraint,
index and column inventory byte-identical (md5 10b3541d4de92900101805824535076d
over 40 objects, before and after) and wrote no rows. Configurations 0,
assignments 0, production runs 8, of which 8 still unstamped.

TESTS

New tests/test_phase8_decision2_machine_stream_configuration.py (32 tests),
covering the eleven code-testable items in section 6 of Charlie's ruling. The
one that carries the design: a March run stamped under revision 1, the line
re-hosed in June and revision 2 activated the opposite way round, and the March
run still reads isocyanate on stream A - while a September run reads it on B.

tests/test_cr18_product_family_terminology.py - one allowlisted db.py line
number moved 2046 -> 2178, the Decision 2 models having landed above it. Text
unchanged.

Full regression: see the closeout. Was 785 passed / 6 skipped at v0.70.2 before
this work landed.

v0.71.1, 2026-08-19: internal development vocabulary removed from customer-facing
text, and a regression guard so it cannot come back.

WHAT STEFAN SAW

At the top of the Edit Run panel on the deployed application:

  "WP7 Phase 2 Closeout Correction: Run Context is captured context-first - Plant,
  then Production Method, then Production Unit or Cell, then Product Grade..."

The advice is sound. The first six words are a note between developers about
which internal work package produced the change, sitting on a screen a plant
engineer reads. He called it meta-leaking, which is exactly what it is.

WHY IT HAPPENS

The project's own working method causes it. Every change arrives as a numbered
work package or CR with a ruling behind it, so while the change is being made
that vocabulary is the most natural way to say why a control exists - and a
caption explaining a control is precisely where the explanation wants to go.
Being more careful is not a fix. Making the boundary mechanical is.

FOURTEEN OCCURRENCES REMOVED

views/4_Production_Run_Trial_Record.py - eight. Two "WP7 Phase 2 Closeout
Correction:" caption prefixes (Edit Run and Create Run), the WP7 Phase 1 design
decision reference in the no-process-settings message, "WP7 Phase 1/2
(2026-08-13/14, per Charlie's decoupling decision, design doc section 3.4)" in
the stream-readings caption, "WP7 Phase 1/2:" in the stream import caption, the
"Per the WP7 governing document ... a later WP7 phase" paragraph on legacy
calculated output, and two "(WP7 Phase 2)" suffixes on the Optional context
links heading.

views/3_Recipe_Version_Record.py - four. "per CR-03's Pending Review
governance", "Per CR-03 rule 4:", "per Charlie's calculation_definitions
library", and "Target (RHF-010)".

views/2_Product_Grades.py - one. "pre-CR-07" became a plain statement that the
value predates the grade's controlled property specification.

views/14_Raw_Materials.py - one. "CR-08's controlled exception path:" became
"'Other' is the controlled exception path:".

Every one was rewritten to say the same thing in the user's language, not
deleted. The advice those captions carry is good advice; only the provenance
was internal.

WHAT WAS DELIBERATELY KEPT

Controlled data identifiers the application genuinely owns - CALC-001, UOM-015,
PS-076, MSC-001. A governed plant system is meant to cite those, and a QA user
needs them. "Closeout" as a trial lifecycle stage on the Customer Trials and
Optimization Trials pages is real business language, kept.

Comments, docstrings and this change log keep the internal vocabulary. That is
where it belongs and where the next developer needs it.

THE GUARD

New tests/test_internal_vocabulary_leak.py (3 tests). It tokenises every
application module, finds string literals that reach a user - Streamlit display
calls, and text-carrying keyword arguments - and fails on work package and CR
identifiers, phase and closeout process language, project role names, and
internal document references. Tokenising rather than line-scanning is what lets
comments and docstrings keep the vocabulary while strings cannot.

Two of the three tests exist to stop the guard rotting into a no-op: one pins
the detector against the exact string Stefan found, and one asserts the
controlled identifiers are NOT flagged, so a later tightening cannot quietly
start stripping the vocabulary the system is supposed to show. The scan was
also verified end to end by reintroducing the leak into a page and confirming
the test fails on it.

Also checked and clean: generated Word report text in reports.py and the other
document builders carries no internal vocabulary.

Full regression: 789 passed, 6 skipped, 0 failed of 795 collected across 66
files. Was 786 / 6 / 792 at v0.71.0, so the 3 new tests are the whole delta. No
existing test needed changing - the rewritten captions kept their meaning.

v0.71.2, 2026-08-19: st.stop() no longer costs the end-of-rerun clean-up. Every
unauthenticated render of the login screen was leaking a database transaction.

WHERE THIS CAME FROM

A defect note from the Flexible Foam edition, "st.stop() Deadlocks the Whole
Browser Session", found and fixed there at v2.12.2. The two editions share the
same navigation and session-handling design, so the note asked this edition to
check two things: whether the finally block around pg.run() releases its lock
unconditionally, and which pages call st.stop() on an ordinary render.

THE MECHANISM

st.stop() raises StopException AND leaves Streamlit's stop flag set. Every later
st.* call re-checks that flag inside its own enqueue and re-raises - including
calls made outside the page script, from app_rigid_foam.py's own finally block.

That finally opened with an st.session_state read. So on any page ending via
st.stop(), the read threw straight back out of the finally and
close_out_session() never ran.

WHAT THIS EDITION ACTUALLY HAD

Not Flexible's symptom. Flexible held a per-browser-session RLock across
pg.run() and released it in that same finally, so the release was skipped and
every subsequent click spun forever. This edition has no such lock - checked,
there is no threading lock anywhere in the source - so nothing deadlocked and
nothing looked wrong.

What it had instead was silent. The page's read transaction was left open with
its connection still checked out: the exact idle-in-transaction failure mode
close_out_session()'s own docstring records as having blocked a schema migration
for eighteen hours.

And the worst affected path was the login screen. auth.require_login() queries
for existing user accounts and then calls st.stop(), so EVERY render for an
unauthenticated visitor leaked a transaction. That is the most-visited path in
the application, and it had no symptom at all until something else went looking
for a lock.

REPRODUCED BEFORE IT WAS FIXED

Not inferred from the note. The application was run under AppTest against a
SQLite copy on the pinned streamlit 1.60.0, with the finally instrumented to a
FILE rather than stderr - stderr writes made after a script run ends are
discarded, which is the trap the Flexible session documented. Result, before the
fix:

  finally: entered
  finally: session_state read RAISED StopException
  session.in_transaction(): True
  connection still checked out: True

After the fix, in_transaction() is False on the first render and stays False
across reruns.

THE FIX

app_rigid_foam.py - the page title is read into a local before pg.run(); whether
the cached session was discarded is tracked by a local flag set in the recovery
branch rather than read back out of session_state; the remaining session_state
read is wrapped and falls back to "still ours", which is the correct answer for
a stopped page since only the recovery branch discards; the page-load timing
write is wrapped so a failed metric cannot take out the cleanup below it.

db.py - close_out_session(session=None) accepts the session explicitly, so the
close-out path never has to read st.session_state to find it. Every remaining
st.* access on that path goes through the new _safe_session_state_get(), and the
discard branch's session_state.pop() is guarded too.

Every guard catches BaseException, not Exception. StopException derives from
BaseException, so "except Exception" misses it entirely - there is a test
pinning that fact so nobody narrows one back.

NO PAGE RESTRUCTURING WAS NEEDED

41 st.stop() call sites were inventoried. Apart from the login screen they are
all "no data yet" guards - add a plant first, add a product grade first - which
fire on a fresh tenant and stop firing once data exists. Every one of them sits
after queries that have already opened a transaction, so every one leaked, but
none stops unconditionally on every render the way the Flexible page did. The
application-level fix covers all 41 without touching a page.

The rule going forward, from the Flexible note and adopted here: prefer if/else
or an early return so the script reaches its end. Reserve st.stop() for a
genuine exit an ordinary session does not hit - and it is only safe even then
because app_rigid_foam.py is now hardened against it.

TESTS

New tests/test_st_stop_transaction_leak.py (9 tests). The mechanism is asserted
against the pinned Streamlit rather than taken on trust, so if a future
Streamlit changes it we find out why the rest of the file stopped being
necessary. The headline regression renders the real application unauthenticated
and asserts no open transaction, then does it three times over. The individual
guards are pinned separately so a refactor cannot remove one and still pass by
accident. A last test asserts this edition still has no page lock, and says what
to do if one is ever introduced.

Both regression tests were verified to FAIL against the pre-fix finally block.

Full regression: 798 passed, 6 skipped, 0 failed of 804 collected across 67
files. Was 789 / 6 / 795 at v0.71.1, so the 9 new tests are the whole delta.

v0.72.0, 2026-08-19: Phase 8 Decision 3 - controlled chemical role on recipe
components. The formulation half of the A:B ratio answer, and the last thing
standing between the application and a ratio it can defend.

WHAT IT IS

Decision 2 recorded which physical stream a machine runs a chemical role on.
This records what a material IS in one formulation - Isocyanate Component or
Polyol Blend Component - and, inseparably, the document that establishes it.

Three nullable columns on recipe_components: chemical_role,
chemical_role_source_id (FK to the existing source_registers, ON DELETE
RESTRICT) and chemical_role_source_location.

WHY THE FIELDS ARE ON THE COMPONENT ROW AND NOT IN A VERSIONED SIDE TABLE

Decision 2 gave the machine convention its own versioned entity because a
machine outlives its own configuration - the same line can be re-hosed and must
still say what applied before. A recipe component has no such life: it cannot be
edited into a different formulation, because a formulation change produces a new
RecipeVersion with new component rows. The version boundary already exists one
level up, so duplicating it here would have created a second answer to "which
row applies to this run" where recipe versioning already gives one.

TWO CONSTRAINTS, NAMED SEPARATELY SO A VIOLATION SAYS WHICH RULE BROKE

ck_rc_chemical_role_vocabulary - NULL, or one of the two controlled terms.

ck_rc_chemical_role_provenance - all three fields resolve together or none of
them do, and the location must be non-empty AFTER TRIMMING. Charlie strengthened
this from the proposal: it makes a partial provenance state unrepresentable
rather than merely discouraged. A role with only a document reference, source
fields stranded after a role is cleared, and a space typed to get past a
required field are all now impossible rather than merely wrong.

The ORM constraint uses trim() rather than Postgres' btrim(). Identical
semantics there - Postgres renders trim() as btrim - and it also exists in
SQLite, which is the test path. A constraint the tests cannot create is a
constraint the tests cannot prove.

The role source is deliberately NOT the existing source_id / source_location
pair on the same table. Those record where the component's php figure came
from. A chemical role can be established by a different document than the
dosage, and conflating them would lose one of the two.

NEW MODULE: component_role.py

Charlie's ruling kept the Decision 2 module focused on physical machine
configuration and put the component resolver in its own module, calling
machine_stream.stream_for_role() across the boundary. The import goes one way
only.

That is not filing tidiness. One file holding both would make it easy, one day,
for something to reach across and infer one from the other - the exact defect
the whole Decision 2/3 sequence exists to prevent.

component_stream_for_run() is the single place chemistry meets plumbing. It
needs both halves and defaults neither: an unresolved component, or a run with
no stamped configuration, returns None. The two gaps are reported separately,
because they are two different jobs for the user - complete a formulation
record, or activate a machine configuration.

php_by_chemical_role() sums in ROLE space, which is machine-independent;
php_by_stream_for_run() relabels those totals through the run's stamped
configuration, and that relabelling is the only step that varies by machine.
Decision 4 consumes both. No arithmetic beyond the sums lives here.

NO INFERENCE, AND WHY THE TEMPTATION IS REAL

Of the five live components on Recipe Version 6, two have a raw material
category that looks decisive - Polyol, Isocyanate - and three do not: Catalyst,
Surfactant, Blowing Agent. A catalyst, a surfactant and a physical blowing agent
are USUALLY carried in the polyol blend. Usually is not evidence. A pre-mixed
blend, a co-catalyst dosed on the isocyanate side or a third-stream additive
would each break it, and nothing in the data would show that it had.

So nothing derives a role from raw material category, material name,
role_in_formulation or stream_assignment, and there is deliberately no "assign
roles from category" action anywhere in the UI. Its absence is the feature.

MIGRATION - phase8_decision3_recipe_component_chemical_role

Applied live to rigid_foam. Additive and nullable throughout; no row written or
altered. All five Recipe Version 6 components verified byte-identical across all
25 pre-existing fields, before and after: md5 92209563f4ec1cda803fada08244a823
both times. 5 rows, 0 with a chemical role, 99 tables unchanged.

Both constraints probe-tested live inside a self-rolling-back block, all seven
cases behaving: full triple accepted; all-null accepted; role without source
rejected; empty location rejected; whitespace-only location rejected; stranded
source rejected; off-vocabulary term rejected. Zero rows remained.

Idempotence measured, not asserted: the migration body re-run in place left the
constraint and column inventory identical - md5 ae52084c718ba2e068aca01643fc4dc9
over 35 objects, before and after - and wrote nothing.

APPLICATION

views/3_Recipe_Version_Record.py gained a Chemical role column reading the
controlled term or Unresolved, a caption naming how many components are still
unresolved and what that costs, and a controlled assignment control that sits
OUTSIDE the ordinary component edit form. Name, supplier, php and the free-text
role are fields a user corrects as they go; a chemical role is controlled data
with provenance and an audit trail, and putting it in the same form would have
made it look like one more field.

Assignments and corrections are audited through the existing controlled-edit
path - RoleChangeLog, with a new target_type of 'recipe_component'. No new
mechanism, per the ruling. Note that 'role' in that table otherwise means an
ACCESS role; target_type is what tells the two apart. The summary names the
previous value as well as the new one, because a change log that records only
the new value cannot answer the question anyone actually asks later.

DEFERRED BY RULING

The reference-formulation promotion path, and raw_materials.catalog_entry_id
with it. JC's proposal showed why: of 152 reference component rows, 100 carry no
source at all, the two material masters have no foreign key between them, and of
the five live components only Cyclopentane appears in the reference set - on
rows whose source_id is NULL. The path would have resolved zero of five. Charlie
deferred it to later controlled material-identity work rather than build an
identity decision for no live benefit.

recipe_components.stream_assignment stays in place, unchanged and unread.
Retirement is a separate cleanup after the controlled paths are proven.

TESTS

New tests/test_phase8_decision3_chemical_role.py (26 tests), one per item on
the ruling's closeout list. Two are worth naming: one asserts the vocabulary
tuple is the SAME OBJECT machine_stream uses, not merely equal to it, because
two independent copies of a controlled vocabulary is how it stops being
controlled; and the stream_assignment absence scan is tokenised rather than
text-matched, since both controlled modules legitimately DISCUSS the field in
their docstrings and a naive scan would flag the very comments that exist to
prevent the mistake.

tests/test_cr18_product_family_terminology.py - one allowlisted db.py line moved
2178 -> 2246, the Decision 3 block having landed above it. Text unchanged.

Full regression: 824 passed, 6 skipped, 0 failed of 830 collected across 68
files. Was 798 / 6 / 804 at v0.71.2, so the 26 new tests are the whole delta.

v0.72.1, 2026-08-19: Decision 3 review correction. An independent adversarial
review found four defects in v0.72.0 and, more usefully, found that two of the
nine closeout items JC had claimed were satisfied were not actually covered by
any test that could fail.

THE ONE THAT WAS LIVE

ck_rc_chemical_role_provenance had a hole, and it was in the exact clause the
ruling had strengthened. The constraint ended:

    ... AND trim(chemical_role_source_location) <> ''

trim(NULL) is NULL. "FALSE OR NULL" is NULL. A CHECK constraint PASSES on NULL.
So a chemical role saved with a source and a NULL source location was ACCEPTED,
and an already-valid row could have its location nulled out from under it.

That is verbatim the state Charlie's ruling names as forbidden: "a role with
only a document reference". Confirmed against live Postgres before the fix, both
on insert and on update.

The reason it survived into the closeout evidence is worth recording. The
original live probe tested seven cases including '' and '   ', both correctly
rejected - and never tested NULL. The evidence was thorough in the wrong
direction. Empty string and NULL are different values and a constraint that
handles one may not handle the other.

Fixed by stating the requirement rather than inferring it: the branch now
includes an explicit "chemical_role_source_location IS NOT NULL". Migration
phase8_decision3_chemical_role_provenance_null_fix applied live, and the ORM
constraint corrected to match. All seven original cases plus both NULL cases
re-probed live: null location rejected, update-to-null rejected, full triple
accepted, all-null accepted, whitespace rejected, stranded source rejected,
role-with-location-omitted rejected. Zero rows written throughout; still 5
components, 0 with a role.

RULE FOR NEXT TIME: never rely on a function of a possibly-NULL value being
false. Say IS NOT NULL.

TWO CLOSEOUT ITEMS CLAIMED AND NOT EARNED

The reviewer mutation-tested the suite. Deleting BOTH audit calls from the
chemical-role save path AND flipping the role selector off Unresolved left
26/26 tests passing.

So "correction auditing through the existing controlled-edit path" and "the role
field starting in the Unresolved state" were asserted in the closeout prose and
demonstrated by nothing. The audit test called audit_log.log_role_change()
itself rather than exercising the page, which is testing the library instead of
the feature.

Both now have tests that read the page and fail when the production code is
removed. Every new test in this version was mutation-checked the same way -
reverted its own fix, confirmed it failed, restored.

THE OTHER THREE DEFECTS

A save could report success while discarding the assignment. audit_log.
log_role_change() swallows exceptions and its _safe_flush() calls
session.rollback() on failure - and the audit row shared the transaction with
the assignment, so a failed audit write rolled the ASSIGNMENT back too, after
which the page committed nothing and still said "Chemical role recorded". The
save path now writes the RoleChangeLog row directly in the same transaction, so
the pair commits together or neither does and the user sees a real error. Same
table, same controlled-edit history, without the swallow.

php_by_chemical_role() turned a missing dosage into a complete-looking total.
"component.php or 0.0" meant a component with a controlled role and no php
contributed nothing while the totals came back looking whole - a ratio of 0.0
indistinguishable downstream from a measured one, which is the precise failure
mode that module was written to prevent. It now returns None if any component
has no php.

The Recipes page showed a confident LEGACY A:B ratio a few inches below the new
caption saying the ratio cannot be derived. The legacy figure comes from the
uncontrolled free-text side labels and stays until Decision 4 replaces it, but
it is now labelled "Computed (uncontrolled, legacy basis)" and preceded by an
explicit warning when the controlled roles are incomplete. Whichever number a
user reads first wins, and one of them was a guess.

Also: the audit summary named only the role and location, so a correction that
changed nothing but the source document produced a line byte-identical to a
no-op re-save. It now names the source.

NOT FIXED HERE - RAISED TO CHARLIE

Three findings need a ruling rather than a patch, and are listed in the
correction document: there is no migration artifact in the repository (the live
schema and the ORM agree only because DDL was run by hand, and create_all()
never ALTERs an existing table); editing a recipe version silently drops every
controlled role on the new version, with no warning; and
component_stream_for_run() does not check that the component belongs to the
run's recipe version.

Full regression: 832 passed, 6 skipped, 0 failed of 838 collected across 68
files. Was 824 / 6 / 830 at v0.72.0, so the 8 corrective tests are the whole
delta.

ONE PROCESS NOTE, RECORDED BECAUSE IT ALMOST COST MORE THAN THE BUGS

Midway through this correction the shell's working directory was still inside a
throwaway mutation-test copy of the repository, so a regression run and an
allowlist edit were applied to the mutated tree rather than the real one. It
surfaced as 27 unexplained failures. Caught, reverted, redone against the real
repository, and the copy deleted. The lesson is to anchor paths absolutely
rather than trusting an inherited cwd.

v0.75.0, 2026-08-21: R0 - baseline, restore point, evidence inventory and the
application-facing rename. Redesign Migration Plan v3, Package B.

R0-WP1 BASELINE CONFIRMED

HEAD e63643a, v0.74.3, working tree clean and level with origin/main. The
migration ledger holds eight entries; 0001-0003 baselined from Phase 8,
0004-0008 applied by R-PRE. This is the release R0 freezes as the redesign
migration baseline.

R0-WP2 A RESTORE POINT THAT WAS ACTUALLY RESTORED FROM

Charlie's gate requires demonstrated recovery evidence, not an assumed
capability. The Supabase organisation is on the Pro plan, which carries daily
backups; point-in-time recovery is a paid add-on whose status cannot be read
from the tools available here, and JC does not read the connection secret. So
rather than assert a mechanism, R0 built one it could prove.

rigid_foam_r0_baseline is a complete data snapshot of all 100 tables taken at
v0.74.3 - 4,564 rows, 2 MB, verified table by table against the live schema
with zero mismatches. Structure is not copied: the repository rebuilds that
from the migration chain, which is what P8-OWR-003 exists for. The snapshot
holds the part the repository cannot regenerate.

Then it was used. In a disposable schema, production_runs and
physical_property_definitions were copied from live, fingerprinted, emptied to
simulate a migration destroying them, and restored from the snapshot:

    production_runs                 8 rows  bf613a35af47500d
      after simulated loss          0 rows  d41d8cd98f00b204
      after restore                 8 rows  bf613a35af47500d
    physical_property_definitions  59 rows  082c7553e9598da0
      after simulated loss          0 rows  d41d8cd98f00b204
      after restore                59 rows  082c7553e9598da0

Content fingerprints, not row counts. A row count proves something came back;
a fingerprint proves the same thing came back. The disposable schema was
dropped afterwards; the snapshot stays until the redesign release is accepted.

R0-WP3 A CORRECTION TO A NUMBER THIS PROJECT HAS BEEN REPEATING

The inventory was meant to record the before-state. It also caught JC's own
error, now propagated into two of Charlie's documents.

JC's engineering review said Production Method was referenced by "twelve
foreign key columns across nine tables", and Migration Plan v3 R3-WP6 inherited
it as "all twelve foreign-key paths across the nine affected tables". Measured
directly against pg_constraint: NINE foreign key constraints across NINE
tables, one column each. The nine-table figure was always right; twelve was
wrong and nobody re-derived it because it appeared in a table that looked
measured.

R3-WP6's exit condition is written in terms of twelve paths. Nine exist. That
has to be corrected before R3, or the gate cannot be satisfied as worded.

A tenth column named production_method_id exists and is NOT one of the nine: it
sits in _backup_recipe_versions_20260819, a backup table with no foreign key.
Two such tables live in the rigid_foam schema - _backup_recipe_versions_
20260819 (1 row) and _backup_recipe_components_20260819 (14 rows), left from
the Decision 3 work on 19 August. They are inside the application's schema but
outside its ORM, they inflate the table count from 98 to 100, and an FK sweep
will not see the legacy reference one of them carries. Raised for a ruling
rather than deleted: JC does not remove data nobody has agreed to lose.

R0-WP4 THE APPLICATION-FACING NAME

"Rigid Foam" becomes "Polyurethane Company Intelligence" per Stefan's ruling.
Six user-facing surfaces, in three files, all of which name the application to
somebody: the browser tab title, the dashboard header, the navigation group
label, the sidebar line, the login screen, and the password-reset email a
locked-out user reads in their own mail client with nothing else to say which
system it came from.

The sidebar keeps its three-line shape. That middle line was added in v0.70.2
for a specific reason - with Rigid and Flexible open side by side there was
nothing at a glance to tell them apart - and the rename gives it the new name
rather than deleting it.

The header caption named the edition twice, once in the title and again
directly beneath it. The repeat is dropped.

Deliberately unchanged: the repository, the directory, app_rigid_foam.py and
the rigid_foam schema. This is an application-facing rename, not a
restructure, and a test asserts the internals did not move. Also left alone -
the "PI3 Plant Edition - Annual" examples on the Subscription Types page,
which are illustrations of a CUSTOMER's subscription naming, not this
application's name. Renaming those would have been a false positive dressed up
as thoroughness.

Full regression: 951 passed, 6 skipped, 0 failed of 957 collected. The six new
tests are mutation-checked, including reverting the sidebar line, deleting it
outright, and missing the password-reset email.

v0.74.3, 2026-08-20: R-PRE correction 3 - the metering module explained
itself and then offered the form anyway.

Third defect found in browser evidence, third one no test caught.

With a Production Unit or Cell set to "Batch blended", the run page correctly
displayed "Material metering is not applicable to this run's Production Unit
or Cell" - and directly beneath that banner sat the entry form, ready to
accept flow, pressure and temperature readings for a unit that has no
metering.

An explanation the user can ignore is not a gate. Stefan's ruling was that
context-specific fields APPEAR only where they apply, not that they are
captioned where they do not.

Fixed: the create path is closed when metering does not apply. The Edit/Delete
path is deliberately left open, and a test asserts it stays open - withdrawing
a module must never strand data somebody has already recorded. The banner was
reworded to match what now happens: recording is closed, existing readings
stay visible and editable.

WHY THE TEST SUITE MISSED IT

The existing test asserted the resolver was called and the banner rendered.
Both were true. Nothing asked what the user could still DO afterwards, which
is the only question that mattered. The new tests assert the guard sits BEFORE
the first field of the form, and are mutation-checked in both directions:
un-guarding the form fails, and gating the edit tab fails too.

A note on that second mutation, because it nearly passed for the wrong reason.
The first attempt inserted the gate at the first "with tab_edit_delete:" in
the file - which belongs to a different tab entirely - and the suite stayed
green, correctly. Re-run against the metering section, it failed as intended.
A mutation that lands somewhere harmless proves nothing.

Full regression: 945 passed, 6 skipped, 0 failed of 951 collected.

v0.74.2, 2026-08-20: R-PRE correction 2 - the new properties had no
selectable unit. Data-only; no application code changed.

Found in browser evidence, like v0.74.1, and again invisible to every test.

Viscosity was selectable on the Test Results page, its description read
correctly, ASTM D445 was offered as the measuring method - and "Unit of
measure" showed "No options to select", greyed out. The only way to enter a
unit was the free-text "Or type a unit not listed above" box: the uncontrolled
path the whole viscosity ruling exists to close.

The page builds that picker from physical_property_uoms, the per-property
allowed-unit link table, NOT from physical_property_definitions.default_uom.
Migrations 0006 and 0007 set the default and made mPa.s controlled without
making it choosable. Setting a standard and leaving it unselectable is worse
than not setting one, because the record then looks controlled and is not.

Migration 0008 adds the link rows: ratio for Specific gravity; mPa.s, cP, Pa.s
and P for Viscosity, mPa.s first so it is the default. Kinematic units are
deliberately NOT offered on the dynamic property - that would invite a
kinematic number to be stored under a dynamic one, the exact confusion the
two-quantity split in 0006 exists to prevent.

A PRE-EXISTING GAP, RAISED NOT FIXED

physical_property_uoms holds ONE row in the whole database, for PROP-005
Thermal conductivity. All 56 other controlled properties have the same empty
picker and the same free-text fallback, and have had since WP5. That is a real
finding about the controlled-unit model and it is raised as its own item. It
is not fixed here: 56 properties is a controlled-vocabulary exercise of its
own and not R-PRE's scope. 0008 closes it only for the two properties R-PRE
added, so the units it just standardised can actually be chosen.

WHAT THE TWO BROWSER-EVIDENCE DEFECTS HAVE IN COMMON

v0.74.1 was the page describing content it no longer had. v0.74.2 is the page
offering a control it could not populate. Both passed every test, because the
tests asked whether the data was right and neither asked what the user would
actually see. Both were found by opening the running application and looking.

v0.74.1, 2026-08-20: R-PRE correction - the Certificate of Analysis page
still said it carried the formulation.

Found in v0.74.0's own browser evidence, on the deployed application, with
every code test green.

The recipe block and the formulation table were gone from the certificate -
screen, PDF and Word - and verified gone. But the tab caption still read "the
recipe used (full formulation - internal use only, not customer-facing)", and
the page-level intro still called the report "result-and-recipe traceability".

Both were false, and false in the more dangerous direction. A reader would
either believe a customer-facing document contained the formulation, or refuse
to send one that was in fact safe to send. The certificate's own block comment
still carried the old caveat too.

This is the same defect class as the internal-vocabulary leak of v0.71.1: the
application describing itself inaccurately. It is invisible to a test that
checks behaviour, because every test was asking whether the recipe was gone
rather than whether the page still promised it. Nothing but looking at the
running application would have caught it.

Fixed, with a guard that scans what the page SAYS about the certificate rather
than what it does. The scan ignores comment lines - the section's block
comment deliberately quotes the old wording to record what changed, and a scan
that tripped on its own explanation would force the history to be deleted to
keep the test green. Both new assertions are mutation-checked by restoring the
old caption and the old intro in turn.

Full regression: 942 passed, 6 skipped, 0 failed of 948 collected.

v0.74.0, 2026-08-20: R-PRE, the pilot-commitment release ahead of the
architecture redesign. Redesign Migration Plan v3, Package A.

WHAT R-PRE IS FOR

The redesign retires Production Method, renames Product Family to PU Material
Family and rebuilds the hierarchy - eight staged migrations behind eight gates.
Three commitments made to a pilot customer did not depend on any of that, and
holding them behind the whole sequence would have deferred them by weeks. So
they were carved out and shipped first, against the current structure. The
accepted version and commit of this release become the baseline the structural
migration starts from.

R-PRE-WP3 - TWO CONTROLLED PROPERTY DEFINITIONS

Specific gravity (PROP-058) and Viscosity (PROP-059) were added to the
physical property master, which held 57 records and had neither. End-of-rise
time was NOT added: it is the same property as the existing Rise time
(PROP-050) and is mapped to it. Free-rise density, cream time, start time, gel
time and tack-free time all already existed.

Both new rows are marked "Provisional - pending PTU documentation". 56 of the
57 existing definitions carry source provenance; these two cannot until the
supplier documentation arrives, and a controlled record with no provenance and
no marker is indistinguishable from a finished one.

Viscosity was created with NO default unit of measure, because the controlled
UOM master had no viscosity quantity type at all - no cP, no mPa.s, no Pa.s.
Inventing one there would have created exactly the uncontrolled unit the UOM
reconciliation ruling exists to prevent, so the field was left unset and the
gap raised rather than filled. Stefan ruled on it the same day and migration
0006 closes it - see below.

Correction to a figure quoted in 0004's own comment: the UOM master held 43
records, not 40. The quantity-type count (30) was right; the record count was
carried over from a group-by whose rows were counted rather than summed. 0004
is left exactly as it was applied - its SQL is correct, only a comment is
wrong, and rewriting an artifact the ledger has already checksummed to fix a
comment is a worse habit than carrying the correction forward.

Migration 0004 carries a setval guard on the id sequence before its inserts.
That is not decoration: proved by mutation against a disposable schema, an
insert without it fails outright with a primary-key collision on any database
whose sequence sits behind max(id) - which is any database rebuilt from a dump
with explicit ids. The live sequence happened to be in step, so the guard is a
no-op there and matters for the replay.

R-PRE-WP3 ADDENDUM - mPa.s AS THE CONTROLLED VISCOSITY STANDARD

Stefan's ruling, twice on the same day: first that viscosity has a controlled
standard at all and that a value arriving from a supplier data sheet in
another unit is converted into it rather than stored as typed; then, on
reflection, that the standard should follow ASTM D445 and be mPa.s rather than
cP.

The second ruling changed no number. 1 mPa.s = 1 cP EXACTLY - the same size,
not a rounded factor - so it relabelled the standard and left every conversion
factor untouched. cP remains an accepted input unit at 1:1, which matters
because it is still what most polyurethane data sheets print. Nothing had to
be re-stated either: zero results existed against the new properties and zero
results anywhere carried a viscosity unit, checked before the change. The same
move after the pilot had loaded its data would have meant relabelling records
a customer had already seen.

Migration 0007 also registers the two method routes, because D445 is worth
reading carefully before it is adopted as THE method. D445 is a KINEMATIC
method: a glass capillary gives mm2/s, and the dynamic value in mPa.s is
CALCULATED from it using the density at the same temperature. Under D445 the
density is part of the method, not an optional extra, and the as-measured
quantity is the kinematic one. ASTM D2196 (rotational / Brookfield) is the
other route and the one more usually run on a polyol or prepolymer system: it
reads dynamic directly and needs no density. Both are controlled methods now;
the choice belongs on the individual result.

Migration 0006 adds two quantity types, not one. Dynamic viscosity (mPa.s the
standard, cP, Pa.s, P) and kinematic viscosity (cSt, mm2/s) are different
physical quantities that look interchangeable on a data sheet: kinematic =
dynamic / density. A straight cSt -> cP conversion is wrong by a factor of the
material's density - for a polyol near 1.02 g/cm3 about 2%, which is small
enough to pass for a plausible reading and large enough to matter against a
release specification.

So convert() REFUSES cSt -> mPa.s outright, and one function crosses between
them: unit_conversion.dynamic_viscosity_cp(), which requires a density in
g/cm3 and returns None without one - which is D445's own rule, arrived at
independently before the standard was named. Specific gravity serves as that density,
which is a quiet argument for having added both properties together.

Saybolt, Engler and Redwood readings are refused entirely rather than
approximated. Their relationship to cSt is an empirical piecewise formula
defined over part of the range, not a factor. A wrong-but-confident number is
worse than a refusal, so the reading has to be obtained in a real unit -
and viscosity_conversion_note() says which ones, rather than the value being
silently dropped.

1 mPa.s = 1 cP exactly. There is a test asserting it, because if that factor
ever drifts every data sheet quoting the other unit has been silently
rescaled - and a mutation that rescales mPa.s fails eight tests.

R-PRE-WP2 - NO FORMULATION ON THE CERTIFICATE OF ANALYSIS

The Certificate of Analysis is the one report in this application that leaves
the company. It carried a "Recipe used" block - version label, approval
status, effective date, ratio/index - and a full "Formulation" table listing
every raw material, its supplier, its php and its role. On screen that table
was captioned "internal use only". The same content was written into the PDF
and the Word file the customer downloads, so the caption protected nothing.

All of it is gone, including the recipe reference. The certificate now
identifies the sample, its source and its results and says nothing about how
the material was made. Deliberately not a redaction flag or a permission-gated
section: a certificate that can show the formulation under some condition is a
certificate that will show it eventually.

The Batch Release Record is internal and keeps its recipe section. A test
asserts that, because a change that stripped formulation content from every
report would have satisfied the ruling and broken the plant.

The tests render both documents and search the output rather than inspecting
the builder's dict, because it is the rendered file that reaches the customer
and a renderer can reach past the dict. reportlab writes its content streams
ASCII85-encoded and deflated, so a naive substring search over the PDF bytes
passes whether or not the text is there. The first version of that helper
returned ASCII85 noise and all five leak tests passed on it. The guard test
written to catch exactly that caught exactly that.

R-PRE-WP1 - MATERIAL METERING BECOMES APPLICABLE, NOT UNIVERSAL

Machine.material_delivery_mode records how a Production Unit or Cell gets
material into the mix: "Machine-metered", "Batch blended" or "Hand mix". The
material-metering module is withdrawn for the two that do not meter.

This is a general property of production equipment, not a customer switch. A
metering machine, a blending vessel with an agitator and a hand mix are three
real ways of making polyurethane; the pilot customer's vessel is one value of
it. The resolver reads the Production Unit or Cell and nothing else - not the
company, not the plant, not the tenant - and a test asserts that by watching
which attributes it touches.

NULL means "not declared" and resolves to APPLICABLE. So does any value this
code does not recognise. Both directions are deliberate and both are tested:
withdrawing functionality is the direction a user cannot undo for themselves,
so it happens only when somebody has positively declared a mode that excludes
it. Every existing Production Unit or Cell keeps every module it had.

The module explains itself in place rather than the tab disappearing, matching
the Cycle/Shot module's existing pattern. A tab that comes and goes is a tab
nobody can find, and applicability depends on the run selected inside the tab,
which is not known when the tab strip is built.

SCOPE NOTE

Migration Plan v3 describes R-PRE as workflow, COA/QC presentation and two
controlled-data additions. R-PRE-WP1 as built also adds one nullable column,
which is the smallest form the agreed per-unit setting can take. Recorded as a
deviation for Charlie to fold into the plan rather than left to be discovered
in the diff.

Full regression: 940 passed, 6 skipped, 0 failed of 946 collected. Was 847
passed / 6 skipped at v0.73.0; the 93 new tests are the four R-PRE control
files, each individually mutation-checked - including a mutation that puts cSt
into the dynamic-viscosity group, which is the specific error the two-group
split exists to make impossible.

The CR-18 terminology allowlist moved again - db.py 2256 -> 2272. Fourth move.
It is position-based on purpose, so every addition above that line will move
it; the fix is always to re-point the line, never to soften the scan.

v0.73.0, 2026-08-20: P8-OWR-003 reproducible migrations and schema-drift
control, plus the two Decision 3 correction rulings - recipe-revision role
reset, and the resolver's recipe-version ownership guard.

P8-OWR-003: THE REPOSITORY CAN NOW REBUILD THE SCHEMA

Until now every schema change here was applied by hand against Supabase. The
live database was correct; the repository could not reproduce it. db.py starts
the app with Base.metadata.create_all(), and create_all() NEVER ALTERs an
existing table - so on any database predating a change, the new columns and
constraints simply stay absent.

For a column that surfaces as an error. For a CONTROL constraint it does not
surface at all: the page works, the saves succeed, and the thing that was
supposed to make a partial provenance state or an overlapping machine-stream
period impossible is quietly not there. An environment that looks correct and
enforces nothing is the failure this closes.

  migrations/0001  Decision 2 machine-stream configuration
  migrations/0002  Decision 3 chemical role (as applied, defect included)
  migrations/0003  the NULL-handling fix
  migrate.py       ordered runner, ledger, --dry-run and --baseline

Object names in the migration files are UNQUALIFIED and the runner sets
search_path. That is not tidiness: it is what makes "applies cleanly to a
pre-change database" testable rather than asserted.

0002 is preserved with the NULL defect that shipped in v0.72.0, and 0003 fixes
it. Folding the fix into 0002 would have been neater and wrong - a migration set
that cannot reproduce the state a database was actually in cannot be used to
diagnose that database.

EVIDENCE, AGAINST A DISPOSABLE SCHEMA RATHER THAN AGAINST PRODUCTION

A rigid_foam_migtest schema was built holding only the PRE-change shape of the
five prerequisite tables - no machine_stream_* tables, no run stamp column, no
chemical-role columns - and the three artifacts applied to it:

  before: 0 chemical-role columns, 0 run stamp column, 0 machine_stream tables
  after:  3 chemical-role columns, 1 run stamp column, 2 machine_stream tables,
          5 control constraints

Then re-run: inventory md5 c05771be96e905c20266f5d287059702 identical before and
after. Then probed for ENFORCEMENT rather than presence - null location
rejected, off-vocabulary rejected, overlapping Active periods rejected. Then
dropped. Live data untouched throughout: 5 recipe components, 0 with a role, 8
production runs, 99 tables.

The live database is baselined into the new ledger rather than re-migrated: the
DDL was already applied by hand, so the three versions are recorded as applied
without executing them. A ledger that disagrees with reality is worse than no
ledger.

tests/test_schema_compatibility.py (8 tests). The required columns and control
constraints are written out LITERALLY, not derived from the ORM - a derived
expectation would delete itself alongside whatever it was meant to protect, and
one test guards against someone later "simplifying" it into exactly that
tautology. Mutation-checked: removing one CheckConstraint from db.py fails two
of them.

RULING 6.2: A REVISION NO LONGER RESETS ROLES SILENTLY

A new recipe version starts with every chemical role Unresolved. That is the
correct control - a role established for one formulation is not automatically
true of a revised one, and copying provenance forward would assert evidence
nobody gave. What was wrong was doing it in silence: correcting a php typo reset
the whole formulation and removed its ability to produce a ratio, with no
warning and nothing in the audit trail.

Now the Edit Recipe path names how many assignments will reset and which
materials, states that the previous version keeps its roles and sources as the
historical record, requires an explicit confirmation checkbox, blocks the save
without it, and records the reset through the same controlled-edit path as an
assignment - in the same transaction as version creation, so a new version
cannot exist without the record of what it cost.

RULING 6.3: THE RESOLVER CHECKS THE COMPONENT BELONGS TO THE RUN

component_stream_for_run() would previously answer confidently for a component
belonging to an entirely different recipe version. New resolve_component_stream()
returns (stream, reason) with three named causes - no role, no stamped
configuration, recipe mismatch - because they need three different actions from
three different people, and one undifferentiated failure tells nobody what to
do. php_by_stream_for_run() and the resolution summary take the same guard.

TWO WEAK TESTS CAUGHT BY MY OWN MUTATION CHECK

The first drafts of the ownership-guard tests used an EMPTY second recipe
version. An empty version is refused by recipe_version_is_resolved() anyway, so
both passed whether or not the guard existed. They now use a second version that
is complete and would total perfectly well on its own, so the only thing that
can refuse it is the guard. Recorded because it is the same class of mistake the
v0.72.0 review found, caught this time before it shipped.

Full regression: 847 passed, 6 skipped, 0 failed of 853 collected across 69
files. Was 832 / 6 / 838 at v0.72.1.
"""

APP_VERSION = "0.75.0"
