"""CR-22 (AF22-01) - direct regression evidence for the frozen semantic
decisions F22-01 through F22-08.

Charlie's Architecture Freeze AF22-01 authorized JC to implement CR-22
directly against 8 frozen decisions and required, per its Section 5,
direct-evidence regression coverage of: Product hierarchy, Location
semantics, Block reference UI/reports, Block reference import, Active
Quality Issue list, Historical readability, Trial behavior, and a semantic
guard against wording regressions. Most of these are already covered by
targeted AppTest-based tests elsewhere (test_cr18_pu_material_family_terminology.py
for F22-01/F22-02's page-level UI, test_cr11_functional_evidence_group_b.py
for F22-03's "Observed location" wording, test_cr11_functional_evidence_group_d.py
for F22-04/F22-05's block_reference UI gating + CSV import validation, and
test_wp7_phase5_a5_08_flexible_inheritance.py's taxonomy-scanning pattern
for F22-06/F22-07's taxonomy content). This file is the CR-22-specific
direct-evidence file that closes the remaining gaps: the two report
builders' (Batch Release Record, Sample Certificate) block_reference
gating at the data-dict level (not just the UI level), the exact
active/quarantined taxonomy counts and names, the historical-readability
"still selectable once already recorded" guarantee, and a semantic guard
that helpers.py's and reports.py's duplicated block_reference_applicable
constants never drift apart.

Usage: python -m pytest tests/test_cr22_semantic_freeze_evidence.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
import helpers
import reports
import quality_issue_taxonomy as qit

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


# ---------------------------------------------------------------------------
# Part 1 - Block reference UI/reports (F22-04) - report-builder level.
# ---------------------------------------------------------------------------

@pytest.fixture()
def two_method_run_chain():
    """Company -> Plant -> two ProductionMethods (real "PM-500" controlled_id
    and a non-PM-500 "PM-100") -> one Machine per method -> one shared
    PUMaterialFamily/FoamGrade/RecipeVersion -> one ProductionRun per method
    (block_reference populated on both, proving the gate is about the
    method, not about whether a value happens to be present) -> one Sample
    per run, so both build_batch_release_record_data() and
    build_sample_certificate_data() can be exercised end to end."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"CR22 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR22 Plant {u}")
    session.add(plant); session.flush()

    method_500 = db.ProductionMethod(controlled_id="PM-500", name=f"CR22 PM-500 {u}")
    method_100 = db.ProductionMethod(controlled_id="PM-100", name=f"CR22 PM-100 {u}")
    session.add_all([method_500, method_100]); session.flush()

    machine_500 = db.Machine(plant_id=plant.id, name=f"CR22 Machine 500 {u}", production_method_id=method_500.id, active=True)
    machine_100 = db.Machine(plant_id=plant.id, name=f"CR22 Machine 100 {u}", production_method_id=method_100.id, active=True)
    session.add_all([machine_500, machine_100]); session.flush()

    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR22 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR22 Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine_500, machine_100]
    session.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()

    run_500 = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference=f"B500-{u}", block_reference=f"BLK500-{u}",
        machine_id=machine_500.id, production_method_id=method_500.id,
    )
    run_100 = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1), batch_reference=f"B100-{u}", block_reference=f"BLK100-{u}",
        machine_id=machine_100.id, production_method_id=method_100.id,
    )
    session.add_all([run_500, run_100]); session.flush()

    sample_500 = db.Sample(production_run_id=run_500.id, sample_ts=dt.datetime(2026, 8, 1, 12, 0))
    sample_100 = db.Sample(production_run_id=run_100.id, sample_ts=dt.datetime(2026, 8, 1, 12, 0))
    session.add_all([sample_500, sample_100]); session.flush()
    session.commit()

    ids = {
        "run_500_id": run_500.id, "run_100_id": run_100.id,
        "sample_500_id": sample_500.id, "sample_100_id": sample_100.id,
        "block_ref_500": run_500.block_reference, "block_ref_100": run_100.block_reference,
    }
    session.close()
    return ids


def test_batch_release_record_shows_block_reference_only_for_pm500(two_method_run_chain):
    """build_batch_release_record_data()'s own returned dict carries a
    block_reference_applicable flag that is True for the PM-500 run and
    False for the PM-100 run, even though both runs have a populated
    block_reference value - proving the gate is the run's Production
    Method, not merely whether a value is present (F22-04)."""
    ids = two_method_run_chain
    session = db.get_session()
    try:
        data_500 = reports.build_batch_release_record_data(session, ids["run_500_id"])
        data_100 = reports.build_batch_release_record_data(session, ids["run_100_id"])
    finally:
        session.close()

    assert data_500["block_reference_applicable"] is True
    assert data_500["block_reference"] == ids["block_ref_500"]
    assert data_100["block_reference_applicable"] is False, (
        "PM-100 run's block_reference_applicable flag should be False even "
        "though a block_reference value is populated on the row"
    )


def test_sample_certificate_header_fields_include_block_reference_only_for_pm500(two_method_run_chain):
    """build_sample_certificate_data()'s header_fields list (rendered
    verbatim by both render_sample_certificate_pdf/docx) contains a "Block
    reference" tuple for a sample drawn from the PM-500 run and omits it
    entirely for a sample drawn from the PM-100 run (F22-04)."""
    ids = two_method_run_chain
    session = db.get_session()
    try:
        data_500 = reports.build_sample_certificate_data(session, ids["sample_500_id"])
        data_100 = reports.build_sample_certificate_data(session, ids["sample_100_id"])
    finally:
        session.close()

    labels_500 = [label for label, _ in data_500["header_fields"]]
    labels_100 = [label for label, _ in data_100["header_fields"]]
    assert "Block reference" in labels_500
    block_ref_value = dict(data_500["header_fields"])["Block reference"]
    assert block_ref_value == ids["block_ref_500"]
    assert "Block reference" not in labels_100, (
        "Sample Certificate header_fields for a PM-100-sourced sample must "
        "not carry a Block reference row (F22-04)"
    )


def test_helpers_and_reports_block_reference_gates_stay_in_sync():
    """helpers.block_reference_applicable() and reports.py's local
    _block_reference_applicable() are two independent copies of the same
    rule (duplicated only because of the helpers<->reports circular-import
    constraint documented at both definition sites) - this is the semantic
    guard proving they can never silently drift apart: same controlled_id
    constant, and identical True/False verdict across a representative
    matrix of methods including None (no method recorded)."""
    assert helpers.BLOCK_REFERENCE_METHOD_CONTROLLED_ID == reports._BLOCK_REFERENCE_METHOD_CONTROLLED_ID == "PM-500"

    class _FakeMethod:
        def __init__(self, controlled_id):
            self.controlled_id = controlled_id

    for controlled_id in ["PM-500", "PM-100", "PM-200", "PM-800", None]:
        method = _FakeMethod(controlled_id) if controlled_id is not None else None
        assert helpers.block_reference_applicable(method) == reports._block_reference_applicable(method), (
            f"helpers/reports block_reference_applicable disagree for controlled_id={controlled_id!r}"
        )
    assert helpers.block_reference_applicable(None) is False
    assert helpers.block_reference_applicable(_FakeMethod("PM-500")) is True
    assert helpers.block_reference_applicable(_FakeMethod("PM-100")) is False


# ---------------------------------------------------------------------------
# Part 2 - Active Quality Issue list + Historical readability (F22-06/F22-07).
# ---------------------------------------------------------------------------

def test_taxonomy_active_and_quarantined_counts_match_af22_01():
    """AF22-01 Section 4 froze the taxonomy resolution at 42 total entries:
    32 ACTIVE, 10 QUARANTINED (the exact quarantined name list Charlie's
    document specified). Quarantined entries must never appear in
    active_issue_types_for_category()'s output for any category."""
    all_names = qit.all_issue_names()
    assert len(all_names) == 42

    expected_quarantined = {
        "Bottom cavitation", "Bottom skin densification", "Gross splits", "Heavy skin",
        "Low block density", "Splits - abnormal fine/broken cell structure",
        "Splits - normal cell structure, open cells", "Stratification",
        "Tacky block surface", "Zigzag (tin) splits",
    }
    active_count = 0
    quarantined_count = 0
    active_names_seen = set()
    for category in qit.categories():
        for entry in qit.QUALITY_ISSUE_TAXONOMY[category]:
            if entry["state"] == qit.STATE_ACTIVE:
                active_count += 1
            else:
                quarantined_count += 1
        for entry in qit.active_issue_types_for_category(category):
            active_names_seen.add(entry["name"])

    assert active_count == 32
    assert quarantined_count == 10
    assert active_names_seen.isdisjoint(expected_quarantined), (
        f"Quarantined name(s) leaked into active_issue_types_for_category() output: "
        f"{active_names_seen & expected_quarantined}"
    )


def test_quarantined_entry_still_selectable_when_already_recorded_on_a_row():
    """Historical readability (F22-06/F22-07, AF22-01): a quarantined entry
    must never be offered as a fresh pick, but a row that already has one
    recorded must still be able to keep/display it via the include_names
    escape hatch - proving "deprecate in place, never touch history" holds
    at the taxonomy-function level (the same guarantee views/6's
    _issue_type_picker() relies on for its category and issue-name
    dropdowns)."""
    category = "Density, shape & dimensional"
    quarantined_name = "Low block density"
    entry = qit.lookup_case_insensitive(quarantined_name)
    assert entry is not None and entry["state"] == qit.STATE_QUARANTINED

    fresh_names = {e["name"] for e in qit.active_issue_types_for_category(category)}
    assert quarantined_name not in fresh_names, "Quarantined entry must not be offered as a fresh pick"

    kept_names = {e["name"] for e in qit.active_issue_types_for_category(category, include_names={quarantined_name})}
    assert quarantined_name in kept_names, (
        "Quarantined entry must remain selectable when its name is passed via include_names "
        "(the pattern used to keep an already-recorded quarantined value visible while editing that row)"
    )

    # lookup_active_case_insensitive() is the CSV import / canonical-name
    # resolution path (F22-05's sibling for quality issues) - it must
    # return None for a quarantined name so a re-import of an old CSV can
    # never silently re-select a retired issue type.
    assert qit.lookup_active_case_insensitive(quarantined_name) is None


# ---------------------------------------------------------------------------
# Part 3 - Semantic guard: "Foam scope" wording must be fully retired.
# ---------------------------------------------------------------------------

def test_no_customer_facing_foam_scope_wording_remains():
    """F22-01 (AF22-01): the "Foam scope" filter control was renamed to
    "Product scope" on pages 5 and 6, and in the two report builders that
    echo its selection back in report headers (Quality Test Result Report,
    Quality Issues Report). This is a source-level guard against the label
    string ever reappearing verbatim."""
    for relpath in (
        os.path.join("views", "5_Physical_Property_Result.py"),
        os.path.join("views", "6_Quality_Observation.py"),
    ):
        with open(os.path.join(APP_DIR, relpath), encoding="utf-8") as f:
            source = f.read()
        assert '"Foam scope"' not in source, f"{relpath} still has a customer-facing 'Foam scope' widget label"
        assert '"Product scope", ["All product grades", "Product family", "Product grade"]' in source, (
            f"{relpath}'s Product scope radio is not in the frozen order "
            f"'All product grades / Product family / Product grade' (F22-02)"
        )

    with open(os.path.join(APP_DIR, "reports.py"), encoding="utf-8") as f:
        reports_source = f.read()
    assert 'f"Foam scope: ' not in reports_source, "reports.py still renders a 'Foam scope:' label into a report"
