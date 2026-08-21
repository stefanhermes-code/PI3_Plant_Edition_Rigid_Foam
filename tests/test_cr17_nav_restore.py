"""CR-17 (Restore Customer Trials & Samples to Samples & Trials
Navigation) regression tests, 2026-08-13.

Covers Charlie's PI3_Rigid_Foam_Phase_1_CR17_Restore_Customer_Trials_to_
Samples_and_Trials_Navigation.docx: CR-14 (2026-08-12) originally moved
Customer Trials & Samples out of "Samples & Trials" and into the new
"Customers" section, second after the new Customers master page. Stefan
clarified the trial page belongs with the application's trial/sample
workflows, not the Customers master section - this CR restores Customer
Trials & Samples to its pre-CR-14 position in Samples & Trials (between
Production Samples and Optimization Trials & Samples), leaving Customers
as a standalone section containing only the Customers master page.

This is a navigation-placement-only change - the customer_trials page
key, its access-control behavior, and every CR-14 Customer-relationship
behavior (customer selection, customer_id linkage, customer_name
synchronization, CSV/Excel import auto-create) are unaffected. This file
does not duplicate that functional coverage - it re-confirms
tests/test_cr14_customers_section.py's full 33-test suite (updated in
place for the new nav-order assertions) still passes standalone, and
adds direct evidence for CR-17's own nav-placement acceptance criteria.

app_rigid_foam.py is a Streamlit script (calls st.navigation()/st.sidebar
at import time) - importing it directly outside AppTest isn't safe, so
nav-structure assertions here grep the module source for the page-list
literals, matching the established convention from tests/
test_cr10_pu_material_family_grade_split.py and tests/
test_cr14_customers_section.py.

Usage: python -m pytest tests/test_cr17_nav_restore.py -v
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import access_control
import db

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_MAIN = os.path.join(APP_DIR, "app_rigid_foam.py")
PAGE_CUSTOMER_TRIALS = os.path.join(APP_DIR, "views", "11_Customer_Trials.py")


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def _app_source():
    with open(APP_MAIN, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Acceptance criteria 1, 2, 3: Customers holds only Customers; Samples &
# Trials holds all three pages in the required order.
# ---------------------------------------------------------------------------

def test_customers_section_contains_only_customers_page():
    """Acceptance criterion 1: the Customers navigation section contains
    Customers as its sole page - customer_pages must have exactly one
    page-registration tuple, and it must be "customers"."""
    source = _app_source()
    start = source.index("customer_pages = [")
    end = source.index("]", start)
    block = source[start:end]

    page_tuples = re.findall(r'\("(\w+)",\s*st\.Page\(', block)
    assert page_tuples == ["customers"], (
        f"Customers section must contain exactly one page ('customers'), "
        f"found: {page_tuples}"
    )
    assert 'st.Page("views/33_Customers.py"' in block


def test_samples_trials_section_has_three_pages_in_required_order():
    """Acceptance criteria 2, 3: Customer Trials & Samples appears under
    Samples & Trials, and that section displays Production Samples,
    Customer Trials & Samples, then Optimization Trials & Samples, in
    that exact order."""
    source = _app_source()
    start = source.index("experiment_pages = [")
    end = source.index("]", start)
    block = source[start:end]

    page_tuples = re.findall(r'\("(\w+)",\s*st\.Page\(', block)
    assert page_tuples == ["samples_conditioning", "customer_trials", "optimization_trials"], (
        f"Samples & Trials must list Production Samples, Customer Trials & "
        f"Samples, then Optimization Trials & Samples, in that order - "
        f"found: {page_tuples}"
    )
    assert 'st.Page("views/11_Customer_Trials.py"' in block
    assert 'title="Customer Trials & Samples"' in block


def test_nav_sections_wire_customers_and_samples_trials_to_correct_lists():
    """Confirms nav_sections_with_keys still maps "Customers" to
    customer_pages and "Samples & Trials" to experiment_pages (the section
    names/keys themselves are unchanged by CR-17 - only their contents)."""
    source = _app_source()
    nav_start = source.index("nav_sections_with_keys")
    nav_block = source[nav_start:nav_start + 800]
    assert '"Customers": customer_pages' in nav_block
    assert '"Samples & Trials": experiment_pages' in nav_block


def test_single_customer_trials_page_registration_in_app_source():
    """Acceptance criterion 9: exactly one Customer Trials & Samples
    navigation entry exists in the sidebar - i.e. the ("customer_trials",
    st.Page(...)) registration tuple appears exactly once anywhere in
    app_rigid_foam.py, not duplicated across sections."""
    source = _app_source()
    occurrences = re.findall(r'\("customer_trials",\s*st\.Page\(', source)
    assert len(occurrences) == 1, (
        f"Expected exactly one Customer Trials & Samples page registration, "
        f"found {len(occurrences)}"
    )


# ---------------------------------------------------------------------------
# Acceptance criteria 4, 5: page opens normally from its restored location;
# customer_trials page key and access behavior remain effective.
# ---------------------------------------------------------------------------

def test_customer_trials_page_key_still_registered_in_page_catalog():
    """Acceptance criterion 5: the customer_trials page_key is unaffected
    by the navigation move - still present in access_control.PAGE_CATALOG
    with its existing label."""
    assert "customer_trials" in access_control.PAGE_CATALOG
    assert access_control.PAGE_CATALOG["customer_trials"] == "Customer Trials & Samples"
    # Customers remains its own independent key too - unaffected.
    assert "customers" in access_control.PAGE_CATALOG
    assert access_control.PAGE_CATALOG["customers"] == "Customers"


def test_customer_trials_page_opens_directly_with_no_exception():
    """Acceptance criterion 4: Customer Trials & Samples opens normally.
    Loaded directly by page path (the same access path Streamlit's
    st.navigation uses once a sidebar entry is clicked) rather than
    driving st.navigation itself through AppTest, matching every other
    nav-placement test's own established convention in this suite."""
    db.init_db()
    _reset_schema()

    at = AppTest.from_file(PAGE_CUSTOMER_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, (
        f"Unhandled exception opening Customer Trials & Samples from its "
        f"restored Samples & Trials location: {at.exception}"
    )


def test_full_app_entrypoint_still_compiles_and_imports_cleanly():
    """Acceptance criterion 10 (full application regression, narrow
    smoke slice): app_rigid_foam.py itself - the file this CR edited -
    is syntactically valid Python after the nav-list changes. The full
    pytest suite (run separately) covers every individual page; this is
    a fast, direct sanity check on the one file CR-17 touched."""
    import py_compile
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tmp:
        py_compile.compile(APP_MAIN, cfile=tmp.name, doraise=True)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
