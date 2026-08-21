"""R1 (Product Family -> PU Material Family, Charlie's Migration Plan v3,
2026-08-21) label and Customer Segment coverage.

WHY THIS FILE EXISTS AT ALL. R1-WP3's rename sweep renamed every internal
identifier (ProductFamily -> PUMaterialFamily, product_family_id ->
pu_material_family_id, the page_key, the nav entry) and both dedicated
pages, then shipped. The post-deploy browser check found the sweep had
missed nine files' worth of *customer-facing labels*: the Product Grades
create and edit forms still said "Product family *", and so did Reports,
Physical Property Result, Quality Observation, Expert Notes, the Plant
Overview metric, the shared analysis_unit_picker control in helpers, and
five report field labels. Every test in the suite stayed green through
all of it.

The reason it stayed green is worth recording, because it is the actual
defect: CR-18's terminology scanner
(tests/test_cr18_product_family_terminology.py) scans for the *Flexible
Foam* term "foam family". "Product family" was the term CR-18 renamed
things TO, so it was, by construction, the one term that scanner could
never flag. When R1 moved the goalposts again, nothing was watching the
new line. A renamed term needs its own scanner at the moment of the
rename, not the previous rename's scanner.

Section 1 is that scanner: a repository-wide scan of customer-facing
string literals for "product famil", with an allowlist limited to
historical prose (changelog entries, CR docstrings describing what a past
CR did) which must stay verbatim.

Section 2 is R1-WP5. The same browser check found customer_segment had
been added to foam_grades in migration 0009 and to the FoamGrade model -
and then surfaced nowhere. It could be neither entered, edited, imported,
nor seen. A column that exists only in the schema is not a moved field,
it is a dropped one with a hole left where it used to be. These tests
drive the real create and edit forms and assert a value round-trips.

Usage: python -m pytest tests/test_r1_pu_material_family_labels.py -v
"""
import ast
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import access_control
import db
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_GRADES = os.path.join(APP_DIR, "views", "2_Product_Grades.py")
PAGE_FAMILIES = os.path.join(APP_DIR, "views", "2_Product_Families.py")


# ---------------------------------------------------------------------------
# Section 1 - the scanner R1-WP3 should have had
# ---------------------------------------------------------------------------

# Files whose "product famil" occurrences are historical prose that must NOT
# be rewritten: version.py is the changelog (rewriting a past release note to
# use today's term makes the record lie about what shipped that day), and the
# CR-10/CR-18 test and page docstrings quote the CR titles and wording that
# were correct when those CRs ran. Charlie's standing rule - an applied
# artifact is immutable, corrections carry forward - is the same principle.
_HISTORICAL_PROSE_FILES = {
    "version.py",
}

# Source files are scanned for USED string literals only, via the AST.
# Comments never reach the AST at all. Docstrings and bare string statements
# are prose - they are allowed, and required, to say "Product family" when
# they are recording what a past CR renamed. Only a string that is passed
# somewhere - a widget label, a dict key, a returned value - can reach a
# customer's eyes, and that is exactly what ast.walk() minus the prose nodes
# leaves behind.


def _customer_facing_python_files():
    for name in sorted(os.listdir(APP_DIR)):
        if name.endswith(".py") and name not in _HISTORICAL_PROSE_FILES:
            yield os.path.join(APP_DIR, name)
    views_dir = os.path.join(APP_DIR, "views")
    for name in sorted(os.listdir(views_dir)):
        if name.endswith(".py"):
            yield os.path.join(views_dir, name)


def _prose_string_node_ids(tree):
    """Ids of every string node written as prose rather than used as a value:
    module/class/function docstrings, and any bare string statement."""
    prose = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                prose.add(id(first.value))
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            prose.add(id(node.value))
    return prose


def _string_literals_with_lines(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    prose = _prose_string_node_ids(tree)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in prose):
            yield node.lineno, node.value


# Hits that are string literals but are NOT customer-facing labels: import
# header names (the wire format, deliberately kept for one compatibility
# release - see GRADE_COLUMN_ALIASES), and docstring lines that quote a
# historical label to explain what changed.
_ALLOWED_LITERAL_SUBSTRINGS = (
    "product_family_id",           # legacy CSV header alias, R1-WP3 comment
    "product_family_foam_grade",   # retired CR-10 page key, asserted absent
    "2_Product_Family",            # historical file name in docstrings
)


def test_no_customer_facing_product_family_labels_remain():
    """R1-WP3 exit condition, stated as a test rather than as a sweep.

    Every customer-facing string literal in the app must say "PU Material
    Family" (or "PU Material Families"), never "Product family". This is
    the check that would have caught all nine files before deploy."""
    offenders = []
    for path in _customer_facing_python_files():
        rel = os.path.relpath(path, APP_DIR)
        for lineno, literal in _string_literals_with_lines(path):
            if "product famil" not in literal.lower():
                continue
            if any(allowed in literal for allowed in _ALLOWED_LITERAL_SUBSTRINGS):
                continue
            offenders.append(f"{rel}:{lineno}: {literal!r}")
    assert not offenders, (
        "Customer-facing 'Product family' labels survived the R1-WP3 rename:\n  "
        + "\n  ".join(offenders)
    )


def test_page_catalog_and_nav_use_the_new_term():
    """The two places the term is load-bearing rather than decorative."""
    assert access_control.PAGE_CATALOG.get("pu_material_families") == "PU Material Families"
    with open(os.path.join(APP_DIR, "app_rigid_foam.py"), encoding="utf-8") as f:
        source = f.read()
    assert 'title="PU Material Families"' in source
    assert 'title="Product Families"' not in source


def test_analysis_unit_picker_family_option_is_renamed_without_breaking_its_branch():
    """helpers.analysis_unit_picker()'s radio is string-keyed: the grade
    branch tests `== "Product grade"` and the family branch is the
    fall-through. Renaming the family option is therefore safe - but only
    as long as it stays the fall-through, so assert both halves."""
    import helpers
    source = open(os.path.join(APP_DIR, "helpers.py"), encoding="utf-8").read()
    start = source.index("def analysis_unit_picker")
    body = source[start:source.index("\ndef ", start + 10)]
    assert '["PU Material Family", "Product grade"]' in body
    assert 'mode_choice == "Product grade"' in body, (
        "The grade branch must stay the string-keyed one - if it ever tests for "
        "the family option instead, renaming that option silently changes behavior."
    )


# ---------------------------------------------------------------------------
# Section 2 - R1-WP5: customer_segment is actually usable on Product Grade
# ---------------------------------------------------------------------------

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


@pytest.fixture()
def seeded_family():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"R1 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"R1 Plant {u}")
    session.add(plant); session.flush()
    # A real controlled value, not a made-up one - the database CHECK added
    # in migration 0009 only accepts the seven.
    family = db.PUMaterialFamily(plant_id=plant.id, name="Rigid")
    session.add(family); session.flush()
    grade = db.FoamGrade(
        pu_material_family_id=family.id,
        grade_name=f"R1-GRADE-{u}",
        customer_segment="Cold-store panel contractors",
    )
    session.add(grade); session.flush()
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "family_id": family.id, "grade_id": grade.id,
        "grade_name": grade.grade_name,
    }
    session.close()
    return ids


def _run(page_path, session_state=None):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def _labels(at):
    out = []
    for collection in (at.text_input, at.text_area, at.selectbox, at.radio, at.multiselect):
        for widget in collection:
            if widget.label:
                out.append(widget.label)
    return out


def test_product_grade_create_form_offers_customer_segment(seeded_family):
    """R1-WP5: the field moved DOWN to the grade, so the grade's own create
    form is where it must appear. Before this test it appeared nowhere."""
    at = _run(PAGE_GRADES)
    assert not at.exception
    labels = _labels(at)
    assert "Customer segment" in labels, (
        f"Product Grades create form has no Customer segment field. Labels found: {labels}"
    )
    assert "PU Material Family *" in labels
    assert "Product family *" not in labels


def test_creating_a_product_grade_persists_its_customer_segment(seeded_family):
    """End-to-end through the real form: fill it, click the real Save
    button, read the row back from the database."""
    at = _run(PAGE_GRADES)
    assert not at.exception
    new_name = "R1-NEW-GRADE"
    for widget in at.text_input:
        if widget.label == "Grade name / code *":
            widget.set_value(new_name)
        elif widget.label == "Customer segment":
            widget.set_value("Refrigerated transport OEM")
    for button in at.button:
        if button.label == "Save product grade":
            button.click()
            break
    at.run()
    assert not at.exception

    session = db.get_session()
    saved = session.query(db.FoamGrade).filter_by(grade_name=new_name).one()
    assert saved.customer_segment == "Refrigerated transport OEM", (
        "The create form accepted a Customer segment and then dropped it on the floor."
    )
    session.close()


def test_editing_a_product_grade_shows_and_updates_its_customer_segment(seeded_family):
    """The stored value must come back into the edit form (not silently
    blank, which would erase it on the next unrelated save) and must be
    writable."""
    at = _run(PAGE_GRADES, session_state={
        "grades_table": {"selection": {"rows": [0], "columns": []}},
    })
    assert not at.exception

    edit_key = f"edit_grade_customer_segment_{seeded_family['grade_id']}"
    matching = [w for w in at.text_input if w.key == edit_key]
    assert matching, (
        f"Edit panel has no Customer segment input (looked for key {edit_key!r}). "
        f"Keys present: {[w.key for w in at.text_input]}"
    )
    field = matching[0]
    assert field.value == "Cold-store panel contractors", (
        "The stored Customer segment did not come back into the edit form - saving "
        "any other change on this form would have wiped it."
    )

    field.set_value("Sandwich panel OEM")
    for button in at.button:
        if button.label == "Save changes":
            button.click()
            break
    at.run()
    assert not at.exception

    session = db.get_session()
    saved = session.get(db.FoamGrade, seeded_family["grade_id"])
    assert saved.customer_segment == "Sandwich panel OEM"
    session.close()


def test_customer_segment_is_shown_in_the_grade_table(seeded_family):
    """A field that can be entered but never displayed is only half moved."""
    at = _run(PAGE_GRADES)
    assert not at.exception
    assert at.dataframe, "Product Grades Edit/Delete tab rendered no table at all."
    columns = []
    for element in at.dataframe:
        frame = element.value
        columns.extend(list(getattr(frame, "columns", [])))
    assert "Customer segment" in columns, (
        f"Product Grades table does not surface Customer segment. Columns: {columns}"
    )


def test_customer_segment_is_an_importable_column():
    """CSV/Excel import must carry it too, or a bulk-loaded catalog silently
    loses the field the migration went to the trouble of moving."""
    source = open(PAGE_GRADES, encoding="utf-8").read()
    assert '"customer_segment"' in source
    start = source.index("GRADE_OPTIONAL_COLUMNS")
    assert "customer_segment" in source[start:start + 200]


def test_customer_segment_is_gone_from_the_pu_material_family_page():
    """The other half of the move: it must not still be enterable upstream,
    or the same fact gets recorded in two places that can disagree."""
    source = open(PAGE_FAMILIES, encoding="utf-8").read()
    for lineno, line in enumerate(source.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        assert "customer_segment" not in line, (
            f"views/2_Product_Families.py:{lineno} still references customer_segment: {line.strip()!r}"
        )
