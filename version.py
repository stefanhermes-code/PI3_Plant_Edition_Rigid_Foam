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

APP_VERSION = "0.36.0"
