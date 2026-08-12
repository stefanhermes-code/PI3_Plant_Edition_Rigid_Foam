"""Customer-presentation translation layer.

CR-09 (Remove Internal Development and UAT Leakage from Customer-Facing
Application, Charlie's instruction, 2026-08-12): every customer-facing
surface - Streamlit page text, generated Word reports, and PI3
prompts/responses - must translate internal engineering vocabulary
(development-phase numbers, WP identifiers, UAT/synthetic-dataset
terminology, raw maturity_status/production_release codes) into
customer-safe language through ONE shared mechanism, not per-page
copies of the same mapping (CR-09 section 7, Acceptance Criterion #12).
This module is that mechanism.

Deliberately dependency-free (no db.py, no session, no other app module)
so every layer can import it with zero risk of a circular import -
helpers.py already imports reports.py, so a translation helper living in
either of those could not be imported by the other. pages/*.py,
reports.py, and any future PI3-prompt-building code can all import this
module directly.

This module contains presentation strings ONLY. No backend logic,
release-gating, or conformance calculation lives here or is changed by
it - wp3_conformance.production_release_status() and
helpers.method_activatable_by_customer() remain the sole source of truth
their callers already use (CR-09 Acceptance Criteria #1, #13, #14).
Functions here only relabel that output for display, and every one
degrades to `None` (or passes the value through) when there is nothing
that needs translating, so existing "or '—'" / truthy-check call sites
keep working unmodified.
"""


def customer_facing_method_availability_note():
    """Caption for a Production Method a customer cannot yet activate
    (helpers.method_activatable_by_customer(method) is False). Replaces a
    caption that used to read the method's raw internal maturity_status
    string and name the internal rollout phase verbatim - e.g. "Not yet
    released for customer activation (Defined / planned) - Phase 1 offers
    Production Method PM-100 only." Deliberately one fixed sentence with
    no maturity_status/phase substitution, so a future change to internal
    status vocabulary can't leak through here again. The release gate
    itself (method.is_released, method_activatable_by_customer) is
    unaffected - this only changes what is displayed when it's False."""
    return (
        "Not yet available for activation at your plant. Production Methods "
        "are enabled here as each one completes validation."
    )


def customer_facing_release_note(internal_release_code):
    """Translates wp3_conformance.production_release_status()'s raw
    internal code (currently only "UAT_PASS_NO_RELEASE") into
    customer-safe language, for every customer-facing Note/annotation
    column and PI3 prompt that surfaces a conformance or achievement
    row's release status. production_release_status() itself, and every
    backend conformance/achievement calculation that calls it
    (wp3_conformance.compute_conformance_report,
    compute_grade_achievement_summary), is completely unchanged - only
    how the returned code is DISPLAYED, or passed into a PI3 prompt that
    could otherwise echo it back to a customer, changes here.

    Returns None when there's nothing to say, so every call site's
    existing "row['production_release'] or '—'" / "if row['production_
    release']" pattern keeps working unmodified."""
    if not internal_release_code:
        return None
    return "Passing result under internal review - not yet cleared for production release"


def customer_facing_reference_dataset_label(is_reference_dataset):
    """Translates reports.py's internal synthetic/reference-dataset
    signal (a production run's notes field mentioning "synthetic" - see
    reports.build_period_summary_report_data) into a customer-safe report
    subtitle fragment. Replaces a label that used to read "Synthetic UAT
    / Reference Dataset" verbatim - both "Synthetic" and "UAT" are
    internal engineering terms with no customer-facing meaning. Returns
    None when the report covers real production data."""
    if not is_reference_dataset:
        return None
    return "Reference Dataset (demonstration data, not live production history)"


def customer_facing_report_title(internal_title):
    """Translates an internal report title that names a development
    work-package (currently only "WP3 Property Conformance Report") into
    its customer-facing equivalent. A small fixed lookup, not a general
    string-replace, so it can never accidentally rewrite unrelated text
    that happens to contain a WP identifier."""
    mapping = {
        "WP3 Property Conformance Report": "Property Conformance Report",
    }
    return mapping.get(internal_title, internal_title)


def customer_facing_grade_status_label(internal_status):
    """Translates FoamGrade.status (db.py: "e.g. UAT_ONLY, ACTIVE -
    controlled-ID grades only") into customer-safe report/UI text.
    "UAT_ONLY" is JC/Charlie's internal controlled-grade lifecycle
    vocabulary and must never reach a customer report verbatim. Any
    status this mapping doesn't recognise is passed through unchanged,
    since FoamGrade.status is a free-text field and only "UAT_ONLY" is
    currently known to be internal-only (flag rather than guess, per this
    project's established data-correction convention)."""
    if not internal_status:
        return None
    mapping = {
        "UAT_ONLY": "Reference specification - not yet released for production use",
    }
    return mapping.get(internal_status, internal_status)
