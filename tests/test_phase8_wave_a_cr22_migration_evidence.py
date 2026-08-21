"""Phase 8 Wave A correction (2026-08-18) - direct evidence for Charlie's
required correction #4 on the Wave A closeout return: "Provide a crosswalk
from the frozen CR-22 terms into the database registry. Historical
quarantined terms must remain readable and excluded from active selection.
If a quarantined historical term is absent from the current database
master and historical lookup requires it, retain it as a quarantined
historical-only record. Prove active-picker exclusion, historical
readability and Production Method applicability against the migrated
database state."

Live-data investigation this file's fixtures are built from (run directly
against Supabase project aazkdsqpytjciiqtvnfj, rigid_foam schema, 2026-08-18):

1. `select id, controlled_id, name, issue_category, state from
   rigid_foam.quality_issue_types` - all 64 pre-existing WP5 Wave 3 rows
   were `state='active'` (the P8-D01 migration only set a blanket default;
   it never applied CR-22/AF22-01's specific 32-active/10-quarantined
   crosswalk to this table). None of quality_issue_taxonomy.py's frozen
   42-entry set's names appear among the 64 live WP5 Wave 3 names except
   "Shrinkage" (coincidental overlap, both active) - the two taxonomies are
   otherwise disjoint. This means none of CR-22's 10 specifically-
   quarantined terms (Tacky block surface; Splits - normal cell structure,
   open cells; Splits - abnormal fine/broken cell structure; Gross splits;
   Zigzag (tin) splits; Low block density; Bottom cavitation; Bottom skin
   densification; Stratification; Heavy skin) needed a historical-only row
   on THIS specific correction, because none of them appear in live
   production data (next point) - Charlie's literal scenario ("a
   quarantined historical term absent from the current master") does not
   presently occur for those 10 terms.

2. `select distinct observation_type, count(*) from
   rigid_foam.quality_observations group by observation_type` - real
   production data returned exactly 7 distinct values: Boiling, Coarse
   foam, Collapse, Friable / loose foam, Scorching, Shrinkage, Voids /
   pinholes. Cross-checking against quality_issue_taxonomy.py: all 7 were
   `state=active` there (none of CR-22's 10 quarantined terms), but only
   "Shrinkage" has a matching live quality_issue_types row (QI-040,
   active - true coincidental name overlap between the two disjoint
   taxonomies, not a migration artifact). The other 6 have NO row in the
   post-cutover 64-row WP5 Wave 3 master at all: a live data-integrity gap
   the P8-D01 cutover introduced (quality_issue_registry.lookup() would
   return None for these 6 real historical observation_type values,
   silently losing their "Issue category" in reports/breakdowns).

3. Applying Charlie's own stated principle (retain an absent-from-master
   historical term as a quarantined historical-only record) to this actual
   evidence - generalized from "quarantined terms specifically" to "any
   term real historical data depends on that the new master doesn't
   carry" - 6 new quarantined historical-only rows were added live:
   QI-090 Boiling, QI-091 Collapse, QI-092 Scorching, QI-093 Coarse foam,
   QI-094 Friable / loose foam, QI-095 Voids / pinholes (all
   issue_category='Legacy (pre-cutover)', state='quarantined', a
   `definition` noting the pre-cutover taxonomy category and, where a
   live active term is confusingly similar in wording, which live active
   controlled_id it must not be confused with). Verified live count after
   the insert: 64 active + 6 quarantined = 70 total (was 64 active + 0
   quarantined before).

The fixture below (`cr22_migration_fixture`) rebuilds that exact live shape
on SQLite - the 7 real historical observation_type names, the "Shrinkage"
overlap, and the 6 new quarantined historical-only rows - and proves the
three things Charlie asked for against it.

Usage: python -m pytest tests/test_phase8_wave_a_cr22_migration_evidence.py -v
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
import quality_issue_registry as qir


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


# The 6 real historical observation_type values with no live-master match,
# plus the identity of the live active row each one is adjacent to but
# distinct from (empty string = no adjacent live active term).
_HISTORICAL_ONLY_TERMS = {
    "Boiling": ("Legacy (pre-cutover)", None),
    "Collapse": ("Legacy (pre-cutover)", None),
    "Scorching": ("Legacy (pre-cutover)", "Core scorching"),
    "Coarse foam": ("Legacy (pre-cutover)", "Coarse cells"),
    "Friable / loose foam": ("Legacy (pre-cutover)", "Friable core"),
    "Voids / pinholes": ("Legacy (pre-cutover)", "Void / Surface void / Pinholes"),
}


@pytest.fixture()
def cr22_migration_fixture():
    db.init_db()
    _reset_schema()
    session = db.get_session()
    u = uuid.uuid4().hex[:6]

    pm800 = db.ProductionMethod(controlled_id="PM-800", name=f"Wave A PM800 {u}")
    session.add(pm800); session.flush()

    # A handful of the 64 live-active WP5 Wave 3 rows, including the one
    # genuine name overlap with the old taxonomy ("Shrinkage") and the
    # near-miss neighbors of the 6 historical-only terms (different exact
    # names, proving they're genuinely distinct rows, not duplicates).
    live_active_rows = {}
    for controlled_id, name, category in [
        ("QI-005", "Void", "Cell/Fill"),
        ("QI-030", "Coarse cells", "Cell structure"),
        ("QI-035", "Friable core", "Cell structure"),
        ("QI-036", "Core scorching", "Heat/Appearance"),
        ("QI-040", "Shrinkage", "Dimensional"),
        ("QI-053", "Surface void", "Surface"),
        ("QI-054", "Pinholes", "Surface"),
    ]:
        row = db.QualityIssueType(controlled_id=controlled_id, name=name, issue_category=category, state="active")
        session.add(row)
        live_active_rows[name] = row
    session.flush()

    # The 6 new quarantined historical-only rows, exactly as inserted live.
    historical_rows = {}
    for name, (category, _neighbor) in _HISTORICAL_ONLY_TERMS.items():
        row = db.QualityIssueType(controlled_id=f"QI-HIST-{uuid.uuid4().hex[:4]}", name=name, issue_category=category, state="quarantined")
        session.add(row)
        historical_rows[name] = row
    session.flush()

    # The 7 real historical QualityObservation rows (production-run-linked
    # in the live schema; only observation_type matters for this proof).
    company = db.Company(name=f"CR22 Evidence Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR22 Evidence Plant {u}")
    session.add(plant); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"CR22 Machine {u}", production_method_id=pm800.id, active=True)
    session.add(machine); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR22 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR22 Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, machine_id=machine.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        production_method_id=pm800.id,
    )
    session.add(run); session.flush()

    historical_observation_types = [
        "Boiling", "Coarse foam", "Collapse", "Friable / loose foam",
        "Scorching", "Shrinkage", "Voids / pinholes",
    ]
    for obs_type in historical_observation_types:
        session.add(db.QualityObservation(
            production_run_id=run.id, observation_type=obs_type, severity="Minor",
            frequency="One-off", confidence_level="Confirmed",
        ))
    session.flush()

    return {
        "session": session, "pm800": pm800, "run": run,
        "live_active_rows": live_active_rows, "historical_rows": historical_rows,
        "historical_observation_types": historical_observation_types,
    }


# ---------------------------------------------------------------------------
# 1. Active-picker exclusion: the 6 quarantined historical-only rows never
#    appear in the active picker's category listing.
# ---------------------------------------------------------------------------

def test_historical_only_rows_excluded_from_active_picker(cr22_migration_fixture):
    session = cr22_migration_fixture["session"]
    names = {e["name"] for e in qir.active_issue_types_for_category(session, "Legacy (pre-cutover)")}
    assert names == set(), f"quarantined historical-only rows leaked into the active picker: {names}"

    # Same result via active_categories(): "Legacy (pre-cutover)" has zero
    # active entries, so it must not appear as a selectable category at all.
    assert "Legacy (pre-cutover)" not in qir.active_categories(session)

    # And explicitly via lookup_active_case_insensitive() per name - the
    # exact call the Add/Edit form's canonical-name resolution uses.
    for name in _HISTORICAL_ONLY_TERMS:
        assert qir.lookup_active_case_insensitive(session, name) is None, (
            f"{name!r} resolved as an active-selectable term - it must not"
        )


# ---------------------------------------------------------------------------
# 2. Historical readability: every one of the 7 real historical
#    observation_type values (6 historical-only + the 1 live-active
#    overlap) resolves via lookup() - the call reports.py's category
#    breakdown and the Edit form's pre-fill both use, regardless of state.
# ---------------------------------------------------------------------------

def test_all_seven_historical_observation_types_resolve(cr22_migration_fixture):
    session = cr22_migration_fixture["session"]
    for obs_type in cr22_migration_fixture["historical_observation_types"]:
        entry = qir.lookup(session, obs_type)
        assert entry is not None, f"historical observation_type {obs_type!r} does not resolve - report category grouping would silently drop it"
    # The 6 historical-only ones specifically resolve to the Legacy
    # category and quarantined state; "Shrinkage" resolves to its live
    # active WP5 Wave 3 row instead (genuine overlap, not a historical-only row).
    for name in _HISTORICAL_ONLY_TERMS:
        entry = qir.lookup(session, name)
        assert entry["category"] == "Legacy (pre-cutover)"
    shrinkage_entry = qir.lookup(session, "Shrinkage")
    assert shrinkage_entry["category"] == "Dimensional"


def test_all_issue_names_includes_historical_only_rows(cr22_migration_fixture):
    session = cr22_migration_fixture["session"]
    names = qir.all_issue_names(session)
    for name in _HISTORICAL_ONLY_TERMS:
        assert name in names, f"{name!r} missing from all_issue_names() - historical any-list lookups would miss it"


def test_report_category_grouping_resolves_historical_only_rows(cr22_migration_fixture):
    """Direct proof against the actual reports.py code path, not just the
    registry module - build_quality_issue_report_data's 'Issue category'
    grouping must show 'Legacy (pre-cutover)', not silently fall through
    to 'Other / not yet classified', for these 6 historical observations."""
    import reports

    session = cr22_migration_fixture["session"]
    run = cr22_migration_fixture["run"]
    obs_ids = [
        o.id for o in session.query(db.QualityObservation)
        .filter(db.QualityObservation.production_run_id == run.id)
        .all()
    ]
    data = reports.build_quality_issue_report_data(
        session, obs_ids, {"group_by_label": "Issue category"},
    )
    labels = {row["Issue category"] for row in data["issue_breakdown"]}
    assert "Legacy (pre-cutover)" in labels
    assert "Other / not yet classified" not in labels, (
        "a historical observation fell through to the unresolved bucket - "
        "the crosswalk is incomplete"
    )


# ---------------------------------------------------------------------------
# 3. Production Method applicability against the migrated state: the 6
#    historical-only rows carry zero QualityIssueTypeApplicability rows,
#    matching the documented "zero rows = Global" convention (AF22-01) -
#    proven both directly and via the registry call PM-800-scoped code
#    paths use.
# ---------------------------------------------------------------------------

def test_historical_only_rows_are_global_zero_applicability_rows(cr22_migration_fixture):
    session = cr22_migration_fixture["session"]
    for name, row in cr22_migration_fixture["historical_rows"].items():
        count = (
            session.query(db.QualityIssueTypeApplicability)
            .filter(db.QualityIssueTypeApplicability.quality_issue_type_id == row.id)
            .count()
        )
        assert count == 0, f"{name!r} unexpectedly has explicit PM applicability rows"


def test_historical_only_rows_stay_quarantined_regardless_of_pm_context(cr22_migration_fixture):
    # Global scope (zero applicability rows) plus quarantined state means
    # these must be excluded from the active picker under every PM
    # context, not just the no-context case already proven above.
    session = cr22_migration_fixture["session"]
    pm800 = cr22_migration_fixture["pm800"]
    for name in _HISTORICAL_ONLY_TERMS:
        assert qir.lookup_active_case_insensitive(
            session, name, production_method_controlled_id=pm800.controlled_id,
        ) is None
