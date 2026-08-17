"""Phase 8 Wave A (2026-08-17) - direct evidence for the Quality Issue DB
cutover Charlie's P8-D01 mandated ("Add the Rigid Quality Issue cutover to
the database master as an engineering task. Remove the option to
duplicate PM-800 entries into quality_issue_taxonomy.py").

Covers:
  1. Schema: QUALITY_ISSUE_STATES / QualityIssueType.state (default +
     CHECK constraint + @validates) and the new
     QualityIssueTypeApplicability table build cleanly on a fresh SQLite
     schema (proves the migration is structurally sound, independent of
     the live Supabase data it was actually applied against).
  2. quality_issue_registry.py behavioral equivalence to
     quality_issue_taxonomy.py's old contract: categories/active_categories,
     lookup/lookup_case_insensitive/lookup_active_case_insensitive (incl.
     quarantine exclusion and PM-restriction filtering via
     QualityIssueTypeApplicability - zero rows for an issue = Global,
     matching AF22-01's "absence means Global" convention), the "Other"
     escape hatch, and typical_causes text built from real
     IssueCauseLink -> PossibleCause rows.
  3. pages/6_Quality_Observation.py no longer imports quality_issue_taxonomy
     at all (the live NameError risk this Wave A work fixed) and loads
     cleanly via AppTest against a registry-backed taxonomy.
  4. reports.py's build_quality_issue_report_data "Issue category" grouping
     resolves through quality_issue_registry (session-aware), not the
     retired module.

quality_issue_taxonomy.py itself is untouched and still used by its own
existing tests (test_cr22_*, test_cr11_functional_evidence_group_b.py,
test_wp7_phase5_a5_08_flexible_inheritance.py) - this file does not
duplicate those; it proves the NEW registry path only.

Usage: python -m pytest tests/test_phase8_wave_a_quality_issue_cutover.py -v
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import db
import quality_issue_registry as qir
import reports
import tenant_scope
import access_control

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_QI = os.path.join(APP_DIR, "pages", "6_Quality_Observation.py")


def _clear_relevant_caches():
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    access_control.denied_page_keys.clear()


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    _clear_relevant_caches()


def _run(page_path, session_state=None):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


# ---------------------------------------------------------------------------
# 1. Schema-level proof: fresh SQLite create_all succeeds with the new
#    column/table/constraint in place, defaults/validation behave.
# ---------------------------------------------------------------------------

def test_quality_issue_state_column_and_applicability_table_build_clean():
    db.init_db()
    _reset_schema()
    session = db.get_session()
    u = uuid.uuid4().hex[:8]

    method = db.ProductionMethod(controlled_id="PM-800", name=f"Wave A PM800 {u}")
    session.add(method); session.flush()

    issue = db.QualityIssueType(
        controlled_id=f"QI-{u}", name=f"Wave A issue {u}", issue_category="Wave A category",
    )
    session.add(issue); session.flush()
    assert issue.state == db.QUALITY_ISSUE_STATES[0] == "active"

    issue.state = "quarantined"
    session.flush()
    assert issue.state == "quarantined"

    with pytest.raises(ValueError):
        issue.state = "not-a-real-state"

    link = db.QualityIssueTypeApplicability(quality_issue_type_id=issue.id, production_method_id=method.id)
    session.add(link); session.flush()
    assert link.id is not None
    assert link.quality_issue_type.name == f"Wave A issue {u}"
    assert link.production_method.controlled_id == "PM-800"


# ---------------------------------------------------------------------------
# 2. quality_issue_registry.py behavioral equivalence fixture: 2 categories,
#    3 active + 1 quarantined issue, 1 PM-800-restricted issue (via
#    QualityIssueTypeApplicability), 1 Global issue, plus PossibleCause/
#    IssueCauseLink rows for the typical-causes derivation.
# ---------------------------------------------------------------------------

@pytest.fixture()
def registry_fixture():
    db.init_db()
    _reset_schema()
    session = db.get_session()
    u = uuid.uuid4().hex[:6]

    pm800 = db.ProductionMethod(controlled_id="PM-800", name=f"Wave A PM800 {u}")
    pm100 = db.ProductionMethod(controlled_id="PM-100", name=f"Wave A PM100 {u}")
    session.add_all([pm800, pm100]); session.flush()

    global_issue = db.QualityIssueType(
        controlled_id=f"QI-G-{u}", name=f"Global issue {u}", issue_category="Cat A", state="active",
    )
    restricted_issue = db.QualityIssueType(
        controlled_id=f"QI-R-{u}", name=f"PM800-only issue {u}", issue_category="Cat A", state="active",
    )
    quarantined_issue = db.QualityIssueType(
        controlled_id=f"QI-Q-{u}", name=f"Quarantined issue {u}", issue_category="Cat B", state="quarantined",
    )
    other_active_issue = db.QualityIssueType(
        controlled_id=f"QI-O-{u}", name=f"Cat B active issue {u}", issue_category="Cat B", state="active",
    )
    session.add_all([global_issue, restricted_issue, quarantined_issue, other_active_issue])
    session.flush()

    session.add(db.QualityIssueTypeApplicability(
        quality_issue_type_id=restricted_issue.id, production_method_id=pm800.id,
    ))
    session.flush()

    cause = db.PossibleCause(controlled_id=f"CAUSE-{u}", name=f"Wave A cause {u}")
    session.add(cause); session.flush()
    session.add(db.IssueCauseLink(issue_type_id=global_issue.id, cause_id=cause.id))
    session.flush()

    return {
        "session": session, "u": u, "pm800": pm800, "pm100": pm100,
        "global_issue": global_issue, "restricted_issue": restricted_issue,
        "quarantined_issue": quarantined_issue, "other_active_issue": other_active_issue,
        "cause": cause,
    }


def test_categories_and_active_categories(registry_fixture):
    session = registry_fixture["session"]
    cats = qir.categories(session)
    assert "Cat A" in cats and "Cat B" in cats and qir.OTHER_CATEGORY in cats
    # Cat B has an active entry (other_active_issue) even though its other
    # entry is quarantined - active_categories() must still include it.
    active_cats = qir.active_categories(session)
    assert "Cat A" in active_cats and "Cat B" in active_cats


def test_active_issue_types_excludes_quarantined_by_default(registry_fixture):
    session = registry_fixture["session"]
    names = {e["name"] for e in qir.active_issue_types_for_category(session, "Cat B")}
    assert registry_fixture["other_active_issue"].name in names
    assert registry_fixture["quarantined_issue"].name not in names


def test_active_issue_types_include_names_keeps_quarantined_visible(registry_fixture):
    session = registry_fixture["session"]
    q_name = registry_fixture["quarantined_issue"].name
    names = {
        e["name"]
        for e in qir.active_issue_types_for_category(session, "Cat B", include_names={q_name})
    }
    assert q_name in names


def test_method_applicability_global_vs_restricted(registry_fixture):
    session = registry_fixture["session"]
    r_name = registry_fixture["restricted_issue"].name
    g_name = registry_fixture["global_issue"].name

    # PM-800: both Global and the PM-800-restricted entry are offered.
    names_800 = {
        e["name"]
        for e in qir.active_issue_types_for_category(session, "Cat A", production_method_controlled_id="PM-800")
    }
    assert r_name in names_800 and g_name in names_800

    # PM-100: only the Global entry is offered; the PM-800-restricted one is not.
    names_100 = {
        e["name"]
        for e in qir.active_issue_types_for_category(session, "Cat A", production_method_controlled_id="PM-100")
    }
    assert g_name in names_100 and r_name not in names_100

    # No method context at all: still Global-only (restricted stays excluded).
    names_none = {e["name"] for e in qir.active_issue_types_for_category(session, "Cat A")}
    assert g_name in names_none and r_name not in names_none


def test_lookup_and_case_insensitive_variants(registry_fixture):
    session = registry_fixture["session"]
    g = registry_fixture["global_issue"]
    q = registry_fixture["quarantined_issue"]

    assert qir.lookup(session, g.name)["category"] == "Cat A"
    assert qir.lookup(session, "not a real issue") is None
    assert qir.lookup(session, qir.OTHER_ISSUE_NAME)["category"] == qir.OTHER_CATEGORY

    # Case-insensitive/whitespace-trimmed, matches regardless of state.
    assert qir.lookup_case_insensitive(session, f"  {q.name.upper()}  ") is not None

    # active_case_insensitive: quarantined returns None (new-selection surfaces only).
    assert qir.lookup_active_case_insensitive(session, q.name) is None
    assert qir.lookup_active_case_insensitive(session, g.name) is not None


def test_lookup_active_case_insensitive_respects_method_restriction(registry_fixture):
    session = registry_fixture["session"]
    r = registry_fixture["restricted_issue"]
    assert qir.lookup_active_case_insensitive(session, r.name, production_method_controlled_id="PM-800") is not None
    assert qir.lookup_active_case_insensitive(session, r.name, production_method_controlled_id="PM-100") is None


def test_typical_causes_built_from_issue_cause_link(registry_fixture):
    session = registry_fixture["session"]
    g = registry_fixture["global_issue"]
    entry = qir.lookup(session, g.name)
    assert entry["typical_causes"] is not None
    assert registry_fixture["cause"].name in entry["typical_causes"]
    assert "Possible causes to check" in entry["typical_causes"]

    # No linked causes -> None, not a crash.
    r_entry = qir.lookup(session, registry_fixture["restricted_issue"].name)
    assert r_entry["typical_causes"] is None


def test_all_issue_names(registry_fixture):
    session = registry_fixture["session"]
    names = qir.all_issue_names(session)
    assert registry_fixture["quarantined_issue"].name in names  # historical/quarantined still listed
    assert registry_fixture["global_issue"].name in names


# ---------------------------------------------------------------------------
# 3. pages/6_Quality_Observation.py: no residual quality_issue_taxonomy
#    import (the NameError risk this Wave A work fixed), page loads clean.
# ---------------------------------------------------------------------------

def test_quality_observation_page_has_no_taxonomy_import():
    with open(PAGE_QI, encoding="utf-8") as f:
        src = f.read()
    assert "import quality_issue_taxonomy" not in src
    # Executable call sites only - comments/docstrings may still name the
    # retired module.py file for historical context (e.g. "see
    # quality_issue_taxonomy.py"), which is fine; a live call would read
    # "quality_issue_taxonomy.<function>(" with no ".py" suffix.
    assert "quality_issue_taxonomy.lookup(" not in src
    assert "quality_issue_taxonomy.categories(" not in src
    assert "quality_issue_taxonomy.active_categories(" not in src
    assert "quality_issue_taxonomy.active_issue_types_for_category(" not in src
    assert "quality_issue_taxonomy.lookup_active_case_insensitive(" not in src
    assert "quality_issue_taxonomy.OTHER_" not in src
    assert "import quality_issue_registry" in src


@pytest.fixture()
def minimal_run_fixture():
    db.init_db()
    _reset_schema()
    session = db.get_session()
    u = uuid.uuid4().hex[:6]

    company = db.Company(name=f"Wave A Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"Wave A Plant {u}")
    session.add(plant); session.flush()
    method = db.ProductionMethod(controlled_id="PM-800", name=f"Wave A PM800 {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    machine = db.Machine(plant_id=plant.id, name=f"Wave A Machine {u}", production_method_id=method.id, active=True)
    session.add(machine); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"Wave A Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"Wave A Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()
    run = db.ProductionRun(
        plant_id=plant.id, machine_id=machine.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        production_method_id=method.id,
    )
    session.add(run); session.flush()

    issue = db.QualityIssueType(controlled_id=f"QI-{u}", name=f"Wave A page issue {u}", issue_category="Wave A cat")
    session.add(issue); session.flush()

    return {"session": session, "company": company, "plant": plant, "run": run, "issue": issue}


def test_quality_observation_page_loads_registry_backed(minimal_run_fixture):
    at = _run(PAGE_QI, session_state={
        "company_id": minimal_run_fixture["company"].id,
        "plant_id": minimal_run_fixture["plant"].id,
    })
    assert not at.exception


# ---------------------------------------------------------------------------
# 4. reports.py Quality Issue Report "Issue category" grouping - session-aware,
#    resolves through quality_issue_registry, never raises NameError.
# ---------------------------------------------------------------------------

def test_reports_uses_quality_issue_registry_not_taxonomy():
    src_path = os.path.join(APP_DIR, "reports.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    assert "import quality_issue_taxonomy" not in src
    assert "import quality_issue_registry" in src


def test_build_quality_issue_report_data_category_grouping(minimal_run_fixture):
    session = minimal_run_fixture["session"]
    run = minimal_run_fixture["run"]
    issue = minimal_run_fixture["issue"]

    obs = db.QualityObservation(
        production_run_id=run.id, observation_type=issue.name, severity="Minor",
        frequency="One-off", confidence_level="Confirmed",
    )
    session.add(obs); session.flush()

    data = reports.build_quality_issue_report_data(
        session, [obs.id], {"group_by_label": "Issue category"},
    )
    labels = {row["Issue category"] for row in data["issue_breakdown"]}
    assert "Wave A cat" in labels
