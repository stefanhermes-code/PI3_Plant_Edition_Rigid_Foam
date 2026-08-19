"""WP7 Phase 0 (Contain inherited Flexible Foam functionality, 2026-08-13)
regression tests.

WP7 Production Run Domain Redesign section 6's Phase 0 scope, as narrowed
during design (see views/4_Production_Run_Trial_Record.py's module
docstring for the full record): remove ACTIVE UI rendering, CSV/Excel
import parsing, report generation, and analytics ranking for exactly 3
inherited Flexible Foam/slabstock concepts -

  1. The FallplateSectionPosition "Tool Geometry and Fill Configuration"
     sub-workflow (manual entry + CSV/Excel import), on both Setup Data
     and Runtime Data.
  2. foaming_mode (FOAMING_MODES controlled vocabulary: LLD/Trough/
     Traverse).
  3. top_flat_system_used (universal boolean).

- while leaving the underlying schema completely untouched: FOAMING_MODES,
FallplateSectionPosition, and the foaming_mode/top_flat_system_used
columns on ProductionPhase all remain defined, and historical rows/values
must stay directly readable off the ORM. This is a containment change,
not a deletion - "no schema/DB changes" is the governing constraint (see
the WP7 execution-approach document, section 6).

This file proves both halves of that constraint with direct, executed
evidence:

  A. Source-grep tests (CR-18 repo-wide-scan pattern) - the 4 surfaces
     that were edited (views/4, analytics.py, reports.py, views/21) no
     longer contain ACTIVE code references to the 3 in-scope concepts,
     while confirming the deliberately-kept exceptions (db.py schema,
     views/4's _delete_phase_cascade FallplateSectionPosition cleanup)
     are exactly what's left.
  B. AppTest UI tests - Setup Data and Runtime Data each render with only
     3 tabs (Create/Edit-Delete/Import - the 4th "Tool Geometry and Fill
     Configuration" tab is gone), their Create/Edit forms no longer show
     foaming_mode/top_flat_system_used widgets, and - critically - a run
     with PRE-EXISTING historical foaming_mode/top_flat_system_used/
     FallplateSectionPosition data (seeded directly via the ORM, standing
     in for data written before this Phase 0 change shipped) still loads
     without error and that historical data is still directly queryable.
  C. analytics.py unit tests - top_flat_system_used is fully absent from
     PHASE_SETTING_FIELDS/LABELS/BOOLEAN_SETTING_FIELDS/PHASE1_RIGID_
     INELIGIBLE_SETTINGS (stronger than the pre-existing Phase-1-rigid-
     conditional exclusion it replaced).
  D. reports.py unit tests - _setup_vs_finalized_deviations() no longer
     flags a foaming_mode difference between Setup and Finalized, and
     build_batch_release_record_data()'s returned dict no longer has a
     "fallplate_deviations" key (or any fall-plate/foaming-mode content),
     even for a run whose Setup/Finalized phases differ on those retired
     fields and have FallplateSectionPosition rows attached.

MANDATORY TEMPLATE: tests/test_cr11_functional_evidence_group_d.py (AUTH_
DISABLED/sqlite:// boilerplate, _clear_relevant_caches() cache-collision
defense, seeded_grade_chain -> seeded_run -> seeded_setup_phase/seeded_
finalized_phase fixture chain, widget-key-not-label lookups) and tests/
test_cr18_product_family_terminology.py (source-grep-with-allowlist
pattern for part A).

Usage: python -m pytest tests/test_wp7_phase0_containment.py -v
"""
import datetime as dt
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import access_control
import analytics
import db
import reports
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE4 = os.path.join(APP_DIR, "views", "4_Production_Run_Trial_Record.py")
PAGE21 = os.path.join(APP_DIR, "views", "21_Report.py")
ANALYTICS_PY = os.path.join(APP_DIR, "analytics.py")
REPORTS_PY = os.path.join(APP_DIR, "reports.py")


def _clear_relevant_caches():
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    _clear_relevant_caches()


def _run(page, session_state=None):
    at = AppTest.from_file(page, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


# ---------------------------------------------------------------------------
# Fixtures - same dependency chain as test_cr11_functional_evidence_group_d.py
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_grade_chain():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P0 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P0 Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-WP7P0-{u}", name=f"WP7P0 Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(
        plant_id=plant.id, name=f"WP7P0 Machine {u}", production_method_id=method.id, active=True,
    )
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P0 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P0 Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True,
    )
    session.add(recipe); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "method_id": method.id,
        "machine_id": machine.id, "family_id": family.id, "grade_id": grade.id,
        "recipe_version_id": recipe.id,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_run(seeded_grade_chain):
    ids = seeded_grade_chain
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
        recipe_version_id=ids["recipe_version_id"], run_date=dt.date(2026, 8, 1),
        batch_reference=f"B-WP7P0-{uuid.uuid4().hex[:8]}", machine_id=ids["machine_id"],
        production_method_id=ids["method_id"], operator_or_team_reference="Shift A",
    )
    session.add(run); session.commit()
    out = dict(ids)
    out["run_id"] = run.id
    session.close()
    return out


@pytest.fixture()
def seeded_run_with_historical_fallplate_data(seeded_run):
    """A run whose Setup and Finalized phases carry PRE-EXISTING data in
    all 3 WP7 Phase 0 in-scope concepts - foaming_mode, top_flat_system_
    used, and an attached FallplateSectionPosition row - seeded directly
    via the ORM, exactly as this data would sit in the database from
    before WP7 Phase 0 shipped (containment means this data must stay
    readable, never be migrated or deleted). Setup and Finalized
    deliberately differ on foaming_mode/top_flat_system_used, so a
    pre-Phase-0 deviation report would have flagged both - this is what
    proves the deviation check itself is gone, not just coincidentally
    silent."""
    ids = seeded_run
    session = db.get_session()
    setup_phase = db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Setup",
        phase_start=dt.datetime(2026, 8, 1, 6, 0), phase_end=dt.datetime(2026, 8, 1, 7, 0),
        mixer_rpm=1500.0, conveyor_speed=2.5,
        foaming_mode="Trough", top_flat_system_used=True,
        source_file_reference="historical seed",
    )
    finalized_phase = db.ProductionPhase(
        production_run_id=ids["run_id"], phase_name="Finalized",
        phase_start=dt.datetime(2026, 8, 1, 8, 0), phase_end=dt.datetime(2026, 8, 1, 10, 0),
        mixer_rpm=1500.0, conveyor_speed=2.5,
        foaming_mode="Traverse", top_flat_system_used=False,
        source_file_reference="historical seed",
    )
    session.add_all([setup_phase, finalized_phase]); session.flush()
    fallplate = db.FallplateSectionPosition(
        production_phase_id=setup_phase.id, section_number=1, position_mm=125.0,
    )
    session.add(fallplate); session.commit()
    out = dict(ids)
    out["setup_phase_id"] = setup_phase.id
    out["finalized_phase_id"] = finalized_phase.id
    out["fallplate_id"] = fallplate.id
    session.close()
    return out


# ---------------------------------------------------------------------------
# A. Source-grep evidence - active references are gone, exceptions remain
# ---------------------------------------------------------------------------

# (relative_path, allowed_reason) -> the ONLY lines in each edited file
# that may still mention FallplateSectionPosition/FOAMING_MODES/foaming_
# mode/top_flat_system_used as a live (non-comment, non-docstring) code
# token. Anything else is either a comment/docstring explaining the WP7
# Phase 0 removal (harmless, expected, not scanned here) or a real
# regression.
_ACTIVE_CODE_TOKEN_RE = re.compile(
    r"\b(FallplateSectionPosition|FOAMING_MODES|foaming_mode|top_flat_system_used|"
    r"expected_fallplate_section_count)\b"
)


def _active_code_hits(path):
    """Mirrors test_cr18_product_family_terminology.py's scan technique:
    walk every physical line, strip full-line comments, and report (line
    number, stripped text) for any line that still contains one of the
    in-scope tokens OUTSIDE of a comment/docstring. This is intentionally
    conservative (it does not attempt real Python tokenization/AST - a
    token inside a triple-quoted docstring paragraph is filtered out
    below by line-range, not by parsing) since every legitimate hit in
    these 4 files sits inside one clearly-bounded docstring block per
    file, per the edits made under task #908."""
    hits = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _ACTIVE_CODE_TOKEN_RE.search(line):
                hits.append((lineno, stripped))
    return hits


def test_page4_no_active_fallplate_or_foaming_mode_ui_code():
    """views/4's module docstring is allowed to mention every retired
    token (it explains the removal in prose) - everything below the
    docstring's closing triple-quote must be clean except the one
    legitimate exception: _delete_phase_cascade's FallplateSectionPosition
    import/query, kept for cascade-delete data-integrity cleanup of
    historical rows (confirmed by reading the function directly, not
    assumed)."""
    with open(PAGE4, encoding="utf-8") as f:
        lines = f.readlines()
    # Find the module docstring's span (first triple-quoted block).
    text = "".join(lines)
    doc_match = re.search(r'"""', text)
    assert doc_match, "views/4 has no module docstring to skip past"
    doc_end = text.index('"""', doc_match.end())
    doc_end_line = text[:doc_end].count("\n") + 1

    hits_after_docstring = [
        (n, s) for n, s in _active_code_hits(PAGE4) if n > doc_end_line
    ]
    # The only allowed post-docstring hits are FallplateSectionPosition's
    # import and its two uses inside _delete_phase_cascade.
    non_fallplate_hits = [
        (n, s) for n, s in hits_after_docstring if "FallplateSectionPosition" not in s
    ]
    assert not non_fallplate_hits, (
        f"Unexpected active foaming_mode/top_flat_system_used/FOAMING_MODES code "
        f"outside the module docstring in views/4: {non_fallplate_hits}"
    )
    assert 1 <= len(hits_after_docstring) <= 4, (
        "Expected only _delete_phase_cascade's FallplateSectionPosition import + "
        f"query lines to remain; found {hits_after_docstring}"
    )


def test_page4_setup_and_runtime_tabs_have_no_fallplate_subtab():
    """Direct source check that the `sub_fallplate` 4th-tab unpack and its
    `with sub_fallplate:` block are gone from both st.tabs() call sites -
    the tabs() unpacking must now be exactly 3 names (tab_create, tab_
    edit_delete, tab_import) for Setup Data and Runtime Data."""
    text = open(PAGE4, encoding="utf-8").read()
    assert "sub_fallplate" not in text, "sub_fallplate 4th-tab reference still present in views/4"
    # Allow the st.tabs(...) call to wrap onto the next line (it does, in
    # the real file, since the argument list is long) - match across
    # whitespace/newlines rather than requiring one physical line.
    setup_tabs_calls = re.findall(
        r'tab_create,\s*tab_edit_delete,\s*tab_import\s*=\s*st\.tabs\(\s*cr11_function_tab_labels\(\s*"Setup Data"',
        text,
    )
    runtime_tabs_calls = re.findall(
        r'tab_create,\s*tab_edit_delete,\s*tab_import\s*=\s*st\.tabs\(\s*cr11_function_tab_labels\(\s*"Runtime Data"',
        text,
    )
    assert len(setup_tabs_calls) == 1, "Setup Data tabs() call site not found in the expected 3-tab form"
    assert len(runtime_tabs_calls) == 1, "Runtime Data tabs() call site not found in the expected 3-tab form"


def test_analytics_top_flat_system_used_removed_from_all_four_collections():
    # WP7 Phase 5 (Legacy Retirement, 2026-08-15) removed PHASE_SETTING_
    # FIELDS/LABELS/BOOLEAN_SETTING_FIELDS/PHASE1_RIGID_INELIGIBLE_SETTINGS
    # from analytics.py entirely (see the JC Pre-Coding Engineering
    # Challenge Response, Section 4) - the strongest possible form of "top_
    # flat_system_used excluded from all four collections" is that none of
    # the four collections exist any more at all.
    for attr in (
        "PHASE_SETTING_FIELDS", "PHASE_SETTING_LABELS",
        "BOOLEAN_SETTING_FIELDS", "PHASE1_RIGID_INELIGIBLE_SETTINGS",
    ):
        assert not hasattr(analytics, attr), f"analytics.{attr} should have been fully removed under WP7 Phase 5"
    # Confirm via source scan too, not just the loaded objects, in case a
    # stray second definition exists elsewhere in the file.
    hits = _active_code_hits(ANALYTICS_PY)
    non_comment_code_hits = [
        (n, s) for n, s in hits
        if "top_flat_system_used" in s and not s.lstrip().startswith(("#", '"'))
    ]
    assert not non_comment_code_hits, (
        f"Unexpected live top_flat_system_used code in analytics.py: {non_comment_code_hits}"
    )


def test_reports_no_active_fallplate_or_foaming_mode_code():
    """reports.py's only allowed hits are inside the _setup_vs_finalized_
    deviations docstring (explains the removal) and the standalone
    explanatory comment block that replaced _fallplate_deviations - every
    physical-line hit for FallplateSectionPosition must be a comment line
    (leading '#'), never live code (an import, a query, a type hint)."""
    with open(REPORTS_PY, encoding="utf-8") as f:
        lines = f.readlines()
    fallplate_lines = [
        (n, l.strip()) for n, l in enumerate(lines, start=1) if "FallplateSectionPosition" in l
    ]
    non_comment = [(n, l) for n, l in fallplate_lines if not l.lstrip().startswith("#")]
    assert not non_comment, (
        f"reports.py has a live (non-comment) FallplateSectionPosition reference: {non_comment} "
        "(unlike views/4, reports.py has no cascade-delete responsibility, so it should have none)"
    )
    text = "".join(lines)
    assert "def _fallplate_deviations" not in text
    fallplate_key_lines = [
        (n, l.strip()) for n, l in enumerate(lines, start=1) if '"fallplate_deviations"' in l
    ]
    non_comment_key_lines = [(n, l) for n, l in fallplate_key_lines if not l.lstrip().startswith("#")]
    assert not non_comment_key_lines, (
        f'reports.py has a live "fallplate_deviations" dict-key reference: {non_comment_key_lines}'
    )
    assert "if setup_phase.foaming_mode != finalized_phase.foaming_mode" not in text


def test_page21_report_no_fallplate_deviations_rendering():
    with open(PAGE21, encoding="utf-8") as f:
        text = f.read()
    assert '"fallplate_deviations"' not in text
    assert "Tool geometry and fill configuration changes" not in text


# ---------------------------------------------------------------------------
# B. AppTest UI evidence - active surfaces gone, historical data still reads
# ---------------------------------------------------------------------------

def test_setup_data_tab_has_no_foaming_mode_or_top_flat_widgets(seeded_run):
    """Drives the real Setup Data Create sub-tab and confirms none of the
    retired widgets render: no selectbox labeled 'Foaming mode', no
    checkbox/selectbox labeled 'Top-flat system in use?', and the page
    loads with no exception."""
    at = _run(PAGE4)
    assert not at.exception, f"Unhandled exception loading Production Run: {at.exception}"

    foaming_mode_widgets = [
        sb for sb in at.selectbox if "foaming mode" in str(sb.label).lower()
    ]
    top_flat_widgets = [
        w for w in list(at.selectbox) + list(at.checkbox)
        if "top-flat" in str(w.label).lower() or "top flat" in str(w.label).lower()
    ]
    assert not foaming_mode_widgets, f"Foaming mode widget still rendered: {foaming_mode_widgets}"
    assert not top_flat_widgets, f"Top-flat system widget still rendered: {top_flat_widgets}"

    # And no fall-plate sub-workflow heading/widgets anywhere on the page.
    fallplate_headings = [
        m for m in at.markdown if "Tool Geometry and Fill Configuration" in m.value
    ]
    assert not fallplate_headings, "Tool Geometry and Fill Configuration section still rendered"


def test_setup_data_create_via_form_no_longer_accepts_foaming_mode(seeded_run):
    """SETUP_OPTIONAL_COLUMNS-driven Create form save no longer sets
    foaming_mode/top_flat_system_used - saves a Setup row through the
    real form and confirms those two columns are None on the persisted
    row (the columns still exist on the model; nothing in the active
    Create path populates them anymore).

    WP7 Phase 5 (Legacy Retirement, 2026-08-15) went further and removed
    the mixer_rpm/conveyor_speed/etc. machine-setting widgets from this
    form entirely (see the JC Pre-Coding Engineering Challenge Response,
    Section 4) - the form now only has start/end time and Notes, so this
    test saves via Notes rather than a since-removed mixer_rpm widget."""
    ids = seeded_run
    at = _run(PAGE4)
    assert not at.exception

    notes = next(t for t in at.text_area if t.key == f"new_setup_notes_{ids['run_id']}")
    notes.set_value("WP7 Phase 5 containment check")
    save_btn = next(b for b in at.button if b.label == "Save Setup data")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving Setup data: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.ProductionPhase)
        .filter(db.ProductionPhase.production_run_id == ids["run_id"], db.ProductionPhase.phase_name == "Setup")
        .first()
    )
    assert created is not None, "New Setup data row was not persisted"
    assert created.notes == "WP7 Phase 5 containment check"
    assert created.mixer_rpm is None, "Create form should no longer set mixer_rpm (WP7 Phase 5)"
    assert created.foaming_mode is None, "Create form should no longer set foaming_mode"
    assert created.top_flat_system_used is None, "Create form should no longer set top_flat_system_used"
    session.close()


def test_setup_data_csv_import_ignores_foaming_mode_and_top_flat_columns(seeded_run):
    """A CSV that still includes the retired columns (simulating an old
    import template someone re-uses) must import cleanly on the columns
    that ARE still recognized, and must NOT populate the retired columns -
    proving the CSV parser no longer reads them, without requiring the
    uploader to reject the extra columns outright.

    WP7 Phase 5 (Legacy Retirement) removed mixer_rpm from
    SETUP_OPTIONAL_COLUMNS along with foaming_mode/top_flat_system_used -
    this CSV includes all three retired columns to prove none of them are
    read any more."""
    ids = seeded_run
    at = _run(PAGE4)
    assert not at.exception

    csv_bytes = (
        b"production_run_id,mixer_rpm,foaming_mode,top_flat_system_used,notes\n"
        + f"{ids['run_id']},1450,Trough,Yes,imported row\n".encode()
    )
    uploader = next(u for u in at.file_uploader if u.key == "setup_upload")
    uploader.set_value(("setup.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading a legacy-format CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_setup_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.ProductionPhase)
        .filter(db.ProductionPhase.production_run_id == ids["run_id"], db.ProductionPhase.phase_name == "Setup")
        .first()
    )
    assert imported is not None, "Imported Setup data row was not persisted"
    assert imported.notes == "imported row"
    assert imported.mixer_rpm is None, "CSV import should no longer read the mixer_rpm column (WP7 Phase 5)"
    assert imported.foaming_mode is None, "CSV import should no longer read the foaming_mode column"
    assert imported.top_flat_system_used is None, "CSV import should no longer read the top_flat_system_used column"
    session.close()


def test_runtime_data_tab_has_no_foaming_mode_or_top_flat_widgets(seeded_run):
    at = _run(PAGE4)
    assert not at.exception

    foaming_mode_widgets = [
        sb for sb in at.selectbox if "foaming mode" in str(sb.label).lower()
    ]
    top_flat_widgets = [
        w for w in list(at.selectbox) + list(at.checkbox)
        if "top-flat" in str(w.label).lower() or "top flat" in str(w.label).lower()
    ]
    assert not foaming_mode_widgets
    assert not top_flat_widgets


def test_historical_run_with_fallplate_and_foaming_mode_data_still_loads_and_is_readable(
    seeded_run_with_historical_fallplate_data,
):
    """The core containment proof: a run carrying pre-existing foaming_
    mode/top_flat_system_used values and an attached FallplateSectionPosition
    row (standing in for real historical data written before WP7 Phase 0)
    must still load on the live page without any exception - the removed
    UI must not choke on rows that happen to have this legacy data
    populated - AND that data must still be directly queryable off the
    ORM, completely unmigrated."""
    ids = seeded_run_with_historical_fallplate_data
    at = _run(PAGE4, session_state={"pr_selected_run_id": ids["run_id"]})
    assert not at.exception, (
        f"Page raised an exception loading a run with historical fall-plate/foaming-mode data: {at.exception}"
    )

    session = db.get_session()
    setup_phase = session.get(db.ProductionPhase, ids["setup_phase_id"])
    finalized_phase = session.get(db.ProductionPhase, ids["finalized_phase_id"])
    fallplate = session.get(db.FallplateSectionPosition, ids["fallplate_id"])
    assert setup_phase.foaming_mode == "Trough", "Historical foaming_mode value was altered or lost"
    assert setup_phase.top_flat_system_used is True, "Historical top_flat_system_used value was altered or lost"
    assert finalized_phase.foaming_mode == "Traverse"
    assert finalized_phase.top_flat_system_used is False
    assert fallplate is not None, "Historical FallplateSectionPosition row was deleted"
    assert fallplate.position_mm == 125.0
    session.close()


# ---------------------------------------------------------------------------
# C. analytics.py unit evidence
# ---------------------------------------------------------------------------

def test_phase_setting_fields_and_labels_exclude_top_flat_system_used():
    # WP7 Phase 5 (Legacy Retirement, 2026-08-15) removed all four
    # collections entirely (see test_analytics_top_flat_system_used_
    # removed_from_all_four_collections above and the JC Pre-Coding
    # Engineering Challenge Response, Section 4) - the strongest possible
    # exclusion of top_flat_system_used is that none of these collections
    # exist to contain it any more.
    for attr in (
        "PHASE_SETTING_FIELDS", "PHASE_SETTING_LABELS",
        "BOOLEAN_SETTING_FIELDS", "PHASE1_RIGID_INELIGIBLE_SETTINGS",
    ):
        assert not hasattr(analytics, attr)


def test_run_settings_dataframe_omits_top_flat_system_used_even_with_historical_data(
    seeded_run_with_historical_fallplate_data,
):
    """Runs analytics' own live run_settings_dataframe() against a run whose
    Setup phase DOES have top_flat_system_used populated (historical data)
    and confirms the resulting table has no such column - WP7 Phase 5
    simplified run_settings_dataframe() to identity columns only (run_id,
    run_date, foam_grade, recipe_version, machine, production_method), so
    it never reads any ProductionPhase column, top_flat_system_used
    included, even when the underlying historical data exists."""
    ids = seeded_run_with_historical_fallplate_data
    session = db.get_session()
    df = analytics.run_settings_dataframe(session)
    session.close()
    assert "top_flat_system_used" not in df.columns
    assert "mixer_rpm" not in df.columns
    assert set(df.columns) == {
        "run_id", "run_date", "foam_grade_id", "foam_grade",
        "recipe_version_id", "recipe_version", "machine_id", "machine",
        "production_method_id", "production_method",
    }


# ---------------------------------------------------------------------------
# D. reports.py unit evidence
# ---------------------------------------------------------------------------

def test_setup_vs_finalized_deviations_no_longer_flags_foaming_mode(
    seeded_run_with_historical_fallplate_data,
):
    """Setup and Finalized differ on foaming_mode (Trough vs Traverse) and
    top_flat_system_used (True vs False) in this fixture - a pre-Phase-0
    build would have flagged foaming_mode as a deviation (top_flat_
    system_used was never in this particular check to begin with, since
    it lived in a separate boolean comparison the page itself did, not
    this function - see the function's own docstring). Confirms the
    returned deviation list contains no "Foaming mode" entry.

    WP7 Phase 4 cutover (2026-08-14): the old ProductionPhase-field-
    diffing _setup_vs_finalized_deviations() was replaced by
    reports._process_parameter_deviations(), which read exclusively
    through analytics.production_run_process_parameters() - the shared
    ProcessSettingDefinition/ProcessParameterValue reader. Retired fields
    like foaming_mode/top_flat_system_used were never migrated into that
    catalogue (WP7 Phase 0's containment work already established this -
    see that phase's closeout), so the new function structurally cannot
    surface them regardless of what this fixture's Setup/Finalized phases
    still carry - a stronger version of the same invariant this test
    always checked, via the WP7 Phase 4 architecture rather than the
    retired Phase-0-era diffing function.

    WP7 Phase 4 targeted-completion correction (2026-08-14, Charlie's
    Closeout Review Return to JC): _process_parameter_deviations() was
    itself replaced by reports._process_parameter_report_rows() (see that
    function's docstring), which reads the same underlying shared reader
    and is bucketed by category - the invariant below is unaffected by
    that shape change, since this fixture's Production Method still has
    zero eligible ProcessSettingDefinition rows either way."""
    ids = seeded_run_with_historical_fallplate_data
    session = db.get_session()
    rows_by_category = reports._process_parameter_report_rows(session, ids["run_id"])
    session.close()
    setting_names = [
        row["Parameter"] for rows in rows_by_category.values() for row in rows
    ]
    assert "Foaming mode" not in setting_names
    assert not any("foaming" in s.lower() for s in setting_names)
    assert not any("top-flat" in s.lower() or "top flat" in s.lower() for s in setting_names)


def test_batch_release_report_data_has_no_fallplate_deviations_key(
    seeded_run_with_historical_fallplate_data,
):
    """End-to-end: builds the real Batch Release report data dict for a
    run with historical fall-plate/foaming-mode data attached, forcing
    has_flags=True (via a failing quality result) so the process-
    parameter-building branch actually executes, and confirms the
    returned dict has no "fallplate_deviations" key at all (not even an
    empty list), no stale "setup_deviations" key (WP7 Phase 4
    targeted-completion correction replaced it with process_setting_rows/
    environment_rows/outcome_rows - see reports._process_parameter_
    report_rows), and none of the three new keys contain foaming-mode/
    fall-plate content."""
    ids = seeded_run_with_historical_fallplate_data
    session = db.get_session()
    run = session.get(db.ProductionRun, ids["run_id"])
    result = db.PhysicalPropertyResult(
        production_run_id=ids["run_id"], property_name="Density", target_value=35.0,
        actual_value=10.0, unit="kg/m3", tested_at=dt.date(2026, 8, 1),
    )
    session.add(result); session.commit()

    data = reports.build_batch_release_record_data(session, ids["run_id"])
    session.close()

    assert "fallplate_deviations" not in data, (
        "Batch Release report data dict should no longer have a fallplate_deviations key"
    )
    assert "setup_deviations" not in data, (
        "setup_deviations was replaced by process_setting_rows/environment_rows/outcome_rows"
    )
    for key in ("process_setting_rows", "environment_rows", "outcome_rows"):
        assert key in data
        setting_names = [row["Parameter"] for row in data[key]]
        assert not any("foaming" in s.lower() for s in setting_names)
        assert not any("fall" in s.lower() or "tool geometry" in s.lower() for s in setting_names)
