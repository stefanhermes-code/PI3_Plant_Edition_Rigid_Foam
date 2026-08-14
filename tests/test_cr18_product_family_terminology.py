"""CR-18 (Eliminate "Foam Family" Terminology Across Rigid Foam Edition,
Charlie's instruction, 2026-08-13) regression coverage.

Charlie's CR found that "Foam Family"/"Foam family"/"foam family" - a
Flexible Foam Edition term - had leaked into several customer-facing
surfaces of the Rigid Foam app, most visibly the shared "Analyze by:
Product Grade / Foam Family" control (helpers.analysis_unit_picker(),
consumed verbatim by pages/16_Trend_Analysis.py, pages/
17_Process_Property_Correlation.py, and pages/
19_Machine_Settings_Optimization.py), each of those three pages' own
action text and pooling captions, the same "Foam scope" pattern on
pages/5_Physical_Property_Result.py and pages/6_Quality_Observation.py,
the PI3-subject-context `subject_desc` string duplicated in those three
pages AND three report-building functions in reports.py, and a report
link-type label dict in reports.py's Expert Notes aggregate report. The
fix standardizes every one of those customer-facing occurrences to
"Product Family"/"Product family"/"product family", while leaving every
internal identifier (`mode: "family"`, `link_type: "product_family"`,
`FoamGrade`, `foam_grade_id`, comments/docstrings describing internal
behavior) untouched, per CR-18's own Internal Compatibility Boundary.

This file is the regression-scanning test CR-18 section 9 requires. It
covers, in order:

  1. A repository-wide case-insensitive scan for "foam family" - every
     hit is classified: it must live in one of a fixed, reviewed set of
     files/line numbers, and it must NOT be inside a Streamlit widget
     call, docx-writing call, or other customer-visible string
     construction (i.e. it really is the internal
     comment/docstring prose it claims to be).
  2. Live-rendered AppTest scans of the three Industrial Intelligence
     pages plus the two Quality pages for the shared control/warning/
     caption/action-text wording.
  3. A direct Process Parameter Optimization (page 19) check of its own
     Action text and the shared Analyze-by radio - the exact leak CR-18
     section 2 quotes.
  4. helpers.analysis_unit_picker()'s own family-mode behavior, driven
     live through Trend Analysis: the customer-facing control/warning/
     label text reads "Product family" while the internal `mode`/
     `link_type` dict values and the pooled `grade_ids` list (business
     logic) are unchanged from before CR-18.
  5. Generated Word report text (reports.build_trend_analysis_report_data
     + render_trend_analysis_report_docx, and the Expert Notes aggregate
     report's link-type label) - the PI3-subject-context `subject_desc`
     string and the link-type label are both clean of "Foam Family".

Deliberately NOT re-scanned here: pages/20_Expert_Notes.py's own
customer-facing text, which CR-15 already fixed and this CR's inventory
confirmed has no new leaks (its 3 remaining "foam family" mentions are
all comments/docstrings documenting CR-15's own completed fix).

Usage: python -m pytest tests/test_cr18_product_family_terminology.py -v
"""
import datetime as dt
import io
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from docx import Document
from streamlit.testing.v1 import AppTest

import db
import helpers
import reports
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE16 = os.path.join(APP_DIR, "pages", "16_Trend_Analysis.py")
PAGE17 = os.path.join(APP_DIR, "pages", "17_Process_Property_Correlation.py")
PAGE19 = os.path.join(APP_DIR, "pages", "19_Machine_Settings_Optimization.py")
PAGE5 = os.path.join(APP_DIR, "pages", "5_Physical_Property_Result.py")
PAGE6 = os.path.join(APP_DIR, "pages", "6_Quality_Observation.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def _extract_docx_text(docx_bytes):
    doc = Document(io.BytesIO(docx_bytes))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 1. Repository-wide "foam family" scan (CR-18 section 9, item 1) - every
#    hit must be one of these exact, reviewed (file, line) pairs, and must
#    not look like a customer-visible string construction.
# ---------------------------------------------------------------------------

ALLOWED_FOAM_FAMILY_HITS = {
    # analytics.py/db.py line numbers shifted again by the WP7 Phase 1
    # Closeout Correction (2026-08-14, Charlie's review items 2.1-2.3):
    # db.py gained new imports (CheckConstraint, Index, event, func,
    # select, validates) plus the applicability same-scope unique index,
    # controlled-vocabulary @validates hooks, and the ProcessParameterValue
    # controlled-UOM-derivation event listener; analytics.py gained a
    # deterministic ORDER BY + comment in eligible_process_settings() -
    # same unchanged comment/docstring text elsewhere, new line positions.
    # db.py shifted again by the WP7 Phase 2 Closeout Correction (same
    # date, Charlie's Material Gap 2): PRODUCTION_RUN_STATUSES constant +
    # ProductionRun.run_start/run_end/status/order_item_reference columns
    # and their CheckConstraint/@validates pair. Shifted a third time by
    # the same Closeout Correction's Material Gap 3 fix:
    # ProductionMethod.uses_cycle_shot_operation and
    # Machine.cycle_shot_operation_override columns (config-driven
    # cycle/shot declaration, never inferred from a name). The set below
    # is the verified, current, exact hit list, not an arithmetic shift
    # guess.
    ("analytics.py", 15), ("analytics.py", 170), ("analytics.py", 304),
    ("analytics.py", 318), ("analytics.py", 423), ("analytics.py", 691),
    ("analytics.py", 766), ("analytics.py", 1252), ("analytics.py", 1417),
    ("db.py", 2046),
    ("helpers.py", 86), ("helpers.py", 87), ("helpers.py", 157),
    ("pages/16_Trend_Analysis.py", 184), ("pages/16_Trend_Analysis.py", 319),
    ("pages/17_Process_Property_Correlation.py", 110),
    ("pages/19_Machine_Settings_Optimization.py", 107),
    ("pages/20_Expert_Notes.py", 6), ("pages/20_Expert_Notes.py", 38),
    ("pages/20_Expert_Notes.py", 146),
    ("pages/5_Physical_Property_Result.py", 632),
    ("pages/6_Quality_Observation.py", 515),
}

# A hit whose line contains any of these is a live customer-facing string
# construction, not comment/docstring prose - CR-18 forbids "foam family"
# here regardless of which file it's in.
_CUSTOMER_FACING_MARKERS = [
    "st.radio(", "st.selectbox(", "st.warning(", "st.caption(", "st.error(",
    "st.info(", "st.success(", "st.markdown(", "st.write(", "st.title(",
    "st.subheader(", "cellPara(", "add_run(", "add_paragraph(",
]
FOAM_FAMILY_RE_SOURCE = "foam family|foam_family"


def _repo_python_files():
    import re
    pattern = re.compile(FOAM_FAMILY_RE_SOURCE, re.IGNORECASE)
    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "tests")]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            if fname == "version.py":
                continue  # append-only changelog, never edited/scanned (established convention)
            path = os.path.join(root, fname)
            relpath = os.path.relpath(path, APP_DIR).replace(os.sep, "/")
            with open(path, encoding="utf-8") as f:
                for lineno, line in enumerate(f, start=1):
                    if pattern.search(line):
                        yield relpath, lineno, line


def test_repo_wide_foam_family_scan_only_hits_known_internal_lines():
    unexpected = []
    seen = set()
    for relpath, lineno, line in _repo_python_files():
        seen.add((relpath, lineno))
        if (relpath, lineno) not in ALLOWED_FOAM_FAMILY_HITS:
            unexpected.append((relpath, lineno, line.strip()))
    assert not unexpected, (
        f"Unreviewed 'foam family' hit(s) found outside the CR-18 internal-comment "
        f"allowlist - these need a customer-facing fix or an explicit allowlist "
        f"update: {unexpected}"
    )
    # Also assert the allowlist itself isn't stale (every entry still present) -
    # catches the allowlist silently going out of sync with the code.
    missing = ALLOWED_FOAM_FAMILY_HITS - seen
    assert not missing, f"Allowlisted 'foam family' line(s) no longer present in source: {missing}"


def test_allowed_foam_family_lines_are_not_customer_facing_strings():
    """Every allowlisted hit must be internal comment/docstring prose, not a
    live widget/docx string construction - guards against the allowlist ever
    being used to paper over a real leak."""
    offenders = []
    for relpath, lineno, line in _repo_python_files():
        if (relpath, lineno) in ALLOWED_FOAM_FAMILY_HITS:
            if any(marker in line for marker in _CUSTOMER_FACING_MARKERS):
                offenders.append((relpath, lineno, line.strip()))
    assert not offenders, f"Allowlisted line(s) actually construct a customer-facing string: {offenders}"


# ---------------------------------------------------------------------------
# 2 & 3. Live-rendered AppTest scans - Industrial Intelligence pages +
#    Quality pages. No fixture data needed: the leaked strings CR-18 found
#    were all static copy (action text, radio options, warning/caption
#    text), rendered on first load before any grade/family is selected.
# ---------------------------------------------------------------------------

def _all_widget_text(at):
    parts = []
    for kind in ("markdown", "caption", "title", "subheader", "warning", "info", "error"):
        parts.extend(w.value for w in getattr(at, kind))
    for r in at.radio:
        parts.extend(str(o) for o in r.options)
    for sb in at.selectbox:
        parts.extend(str(o) for o in sb.options)
    return "\n".join(parts)


@pytest.mark.parametrize("page_path,page_name", [
    (PAGE16, "Trend Analysis"),
    (PAGE17, "Process-Property Correlation"),
    (PAGE19, "Process Parameter Optimization"),
])
def test_industrial_intelligence_page_has_no_foam_family_leak(page_path, page_name):
    db.init_db()
    _reset_schema()
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading {page_name}: {at.exception}"

    text = _all_widget_text(at)
    assert "foam family" not in text.lower(), f"'foam family' leaked on {page_name}: {text!r}"
    assert "foam family" not in " ".join(str(o) for r in at.radio for o in r.options).lower()


def test_process_parameter_optimization_action_text_and_radio_say_product_family():
    """Direct check of the exact leak CR-18 section 2 quotes: page 19's
    Action text and the shared Analyze-by radio."""
    db.init_db()
    _reset_schema()
    at = AppTest.from_file(PAGE19, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Process Parameter Optimization: {at.exception}"

    action_text = "\n".join(w.value for w in at.markdown)
    assert "a product family to pool several grades together" in action_text
    assert "a foam family to pool several grades together" not in action_text


def test_quality_pages_foam_scope_control_says_product_family():
    """pages/5 and pages/6's "Foam scope" radio has the same 'All product
    grades / Product grade / Foam family' -> 'Product family' fix as the
    shared analysis_unit_picker control. Both pages gate their filterable
    table (and this radio) behind "at least one production run/trial
    exists" - reaching it live would require a full run/trial fixture for
    no extra assurance, so this is a direct source check of the exact
    widget-construction lines instead, the same convention tests/
    test_cr17_nav_restore.py uses for nav-list source assertions."""
    for page_path, page_name in ((PAGE5, "Quality Test Result"), (PAGE6, "Quality Issue")):
        with open(page_path, encoding="utf-8") as f:
            source = f.read()
        assert '"Foam scope", ["All product grades", "Product grade", "Product family"]' in source, (
            f"{page_name}'s Foam scope radio options are not "
            f"'All product grades / Product grade / Product family'"
        )
        assert 'st.caption("No product family available for these grades yet.")' in source, (
            f"{page_name}'s empty-state caption is not 'No product family available...'"
        )
        assert '"Product family", families, format_func=lambda f: f.name' in source, (
            f"{page_name}'s family selectbox label is not 'Product family'"
        )
        assert '"Foam family"' not in source, f"{page_name} still constructs a 'Foam family' string"
        assert 'No foam family available' not in source, f"{page_name} still has the old empty-state caption"


# ---------------------------------------------------------------------------
# 4. helpers.analysis_unit_picker() family-mode regression, driven live
#    through Trend Analysis: customer-facing text reads "Product family"
#    while internal identifiers and the pooling business logic (which
#    grade_ids get pooled) are unchanged.
# ---------------------------------------------------------------------------

def _seed_family_with_two_grades():
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR18 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR18 Plant {u}")
    session.add(plant); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"CR18 Family {u}")
    session.add(family); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"CR18 Machine {u}")
    session.add(machine); session.flush()

    grade_ids = []
    grade_names = []
    for i in range(2):
        grade = db.FoamGrade(product_family_id=family.id, grade_name=f"CR18-G{i}-{u}")
        session.add(grade); session.flush()
        recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Draft", is_active=True)
        session.add(recipe); session.flush()
        run = db.ProductionRun(
            plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
            run_date=dt.date(2026, 8, 1 + i), batch_reference=f"CR18-B{i}-{u}",
        )
        session.add(run); session.flush()
        result = db.PhysicalPropertyResult(
            production_run_id=run.id, property_name="Density", actual_value=32.0 + i,
            unit="kg/m3", tested_at=run.run_date,
        )
        session.add(result); session.flush()
        grade_ids.append(grade.id)
        grade_names.append(grade.grade_name)
    session.commit()
    ids = {"company_id": company.id, "grade_ids": sorted(grade_ids), "grade_names": sorted(grade_names)}
    session.close()
    return ids


@pytest.fixture()
def family_fixture():
    db.init_db()
    _reset_schema()
    return _seed_family_with_two_grades()


def test_analysis_unit_picker_family_mode_uses_product_family_wording_and_pools_correctly(family_fixture):
    tenant_scope.clear_scope_cache()
    at = AppTest.from_file(PAGE16, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["is_platform_owner"] = True
    at.session_state["company_id"] = family_fixture["company_id"]
    at.run()
    assert not at.exception, f"Unhandled exception loading Trend Analysis: {at.exception}"

    unit_mode = next(r for r in at.radio if r.key == "trend_unit_mode")
    assert unit_mode.options == ["Product grade", "Product family"], (
        f"Analyze-by control's own option text is not 'Product grade'/'Product family': {unit_mode.options}"
    )
    unit_mode.set_value("Product family")
    at.run()
    assert not at.exception, f"Unhandled exception after switching to Product family mode: {at.exception}"

    family_select = next((sb for sb in at.selectbox if sb.key == "trend_family_select"), None)
    assert family_select is not None, "Product family selectbox did not appear after switching modes"
    assert family_select.label == "Product family"

    all_text = "\n".join(w.value for w in list(at.caption) + list(at.markdown))
    assert "foam family" not in all_text.lower(), f"'foam family' leaked once in family mode: {all_text!r}"
    assert f"Pooling {len(family_fixture['grade_ids'])} grade(s) in product family" in all_text, (
        "Pooling caption missing or not using 'product family' wording"
    )
    # Business logic unchanged: both seeded grades are still offered/pooled
    # by name in the caption, proving CR-18 only touched the wording, not
    # which grades a family mode actually pools.
    for name in family_fixture["grade_names"]:
        assert name in all_text, f"Pooled grade {name!r} missing from the pooling caption text"


def test_analysis_unit_picker_internal_dict_identifiers_unchanged():
    """The customer-facing wording changed; the internal contract every
    caller (analytics.py, reports.py, helpers.py's own Expert Notes link
    plumbing) relies on must not have - mode stays "family", link_type
    stays "product_family", per CR-18's Internal Compatibility Boundary."""
    import inspect
    src = inspect.getsource(helpers.analysis_unit_picker)
    assert '"mode": "family"' in src
    assert '"link_type": "product_family"' in src
    assert '"mode": "grade"' in src
    assert '"link_type": "foam_grade"' in src


# ---------------------------------------------------------------------------
# 5. Generated Word report text - subject_desc (reports.py, 3 occurrences)
#    and the Expert Notes aggregate report's link-type label.
# ---------------------------------------------------------------------------

def test_trend_analysis_report_docx_subject_desc_says_product_family():
    fake_unit = {
        "mode": "family", "label": "CR18 Report Family",
        "member_grade_names": ["Grade A", "Grade B"], "grade_ids": [1, 2],
    }
    import pandas as pd
    data = reports.build_trend_analysis_report_data(
        session=None, unit=fake_unit, property_name="Density",
        series=pd.DataFrame({"tested_at": []}), pooling_grades=True,
        chart_result=None, capability=None, cusum=None, trend=None,
        change_rows=[], include_trials=False,
    )
    assert data["subject_desc"] == "product family CR18 Report Family (pooling grades: Grade A, Grade B)"
    docx_bytes = reports.render_trend_analysis_report_docx(data)
    text = _extract_docx_text(docx_bytes)
    assert "product family" in text
    assert "foam family" not in text.lower()


def test_expert_notes_aggregate_report_link_type_label_says_product_family():
    from types import SimpleNamespace
    notes = [
        SimpleNamespace(
            confidence_level="High", source="Manual", linked_entity_type="product_family",
            vector_store_file_id=None,
        ),
    ]
    data = reports.build_expert_notes_report_data(session=None, notes=notes, scope_label="All companies")
    link_labels = [row["Linked to"] for row in data["link_type_rows"]]
    assert "Product Family" in link_labels
    assert "Foam Family" not in link_labels
    docx_bytes = reports.render_expert_notes_report_docx(data)
    text = _extract_docx_text(docx_bytes)
    assert "Product Family" in text
    assert "Foam Family" not in text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
