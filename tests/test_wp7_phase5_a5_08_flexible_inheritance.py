"""WP7 Phase 5, A5-08 correction (2026-08-15, two review passes) - direct
regression evidence.

PASS 1 - Charlie's Closeout Review Return to JC on the WP7 Phase 5
closeout package (WP7_Phase5_Closeout_Package.docx, v0.62.0/commit
134a9fc) held A5-08 ("zero active Fall Plate, Top-flat, trough/slabstock,
or other retired Flexible Foam Production Run concepts, with
customer-facing and code dependency scan evidence") OPEN: the delivered
closeout recorded A5-08 as PASS while three live, customer-facing/
LLM-facing paths still carried inherited Flexible Foam/slabstock content -

  1. Six PI3 system/user prompt strings (ai_assistant.py's
     PLANT_QUERY_SYSTEM_PROMPT, plus one prompt each in pages 15-19) that
     framed PI3 as helping a reviewer "at a flexible slabstock foam
     manufacturer".
  2. views/6_Quality_Observation.py's Quality Issue "Add" caption, which
     told the person logging an issue that the controlled list came from
     "Laader Berg's slabstock foaming troubleshooting guide".
  3. quality_issue_taxonomy.py's active QUALITY_ISSUE_TAXONOMY content,
     which (being sourced wholesale from that same Flexible Foam
     continuous-slabstock guide) still contained trough/conveyor/
     fall-plate/lay-down/Maxfoam-specific fault names and troubleshooting
     guidance in the live Quality Issue picker.

PASS 2 - Charlie's second Closeout Review Return (responding to
v0.63.0/commit 47d4005) accepted the pass-1 corrections but held A5-08
open again on two further grounds: (a) the pass-1 scan's term list
(trough/fall-plate/conveyor/lay-down/slabstock/Maxfoam) was too narrow -
it missed "leaving the tunnel" in Slow curing, "air injection" in six
other entries (air_injection_rate/air_pressure_bar is D5-05 QUARANTINED,
not just an inherited Flexible term), and "methylene chloride" as a named
blowing-agent example in Low block density; (b) the closure gate requires
one authoritative full SERIAL regression with zero failures and zero
skipped after the correction, not the pytest-xdist parallel run reported
in the v0.63.0 return. This file's scan was expanded accordingly (see
part 3 below); the serial regression requirement is satisfied by the run
recorded in this correction's release notes/return package, not by a test
in this file (a test file cannot assert about its own invocation mode).

This file is the "direct A5-08 regression that scans the live
customer-facing and LLM-facing paths and proves zero active Flexible
Foam/slabstock inheritance" both returns required. It does NOT reopen
A5-01 through A5-07, A5-09, or A5-10 - those remain accepted per both
returns' scope-discipline sections.

Scan technique: for AI prompts and the Quality Issues caption, the same
source-grep-with-allowlist pattern as test_wp7_phase0_containment.py /
test_cr18_product_family_terminology.py - walk the file's raw text and
assert the retired term is entirely absent from the live surface. For the
taxonomy module, part 3 below scans the LOADED QUALITY_ISSUE_TAXONOMY
dict values (not raw file text) - the module's typical_causes strings are
built from adjacent Python string-literal concatenation split across
physical lines (e.g. "...air " + "injection..."), so a raw-text substring
search across single lines would silently miss real matches; scanning the
post-concatenation dict content is both more robust and matches Charlie's
instruction to "target active dictionary content" directly. A separate
raw-text check confirms the module's docstring (developer-facing, never
reachable through the UI or an LLM prompt) is where the only remaining
mentions of retired terms live.

Usage: python -m pytest tests/test_wp7_phase5_a5_08_flexible_inheritance.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import ai_assistant
import quality_issue_taxonomy as qit

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI_ASSISTANT_PY = os.path.join(APP_DIR, "ai_assistant.py")
PAGE6 = os.path.join(APP_DIR, "views", "6_Quality_Observation.py")
TAXONOMY_PY = os.path.join(APP_DIR, "quality_issue_taxonomy.py")
PI3_PAGES = [
    os.path.join(APP_DIR, "views", "15_Recipe_Optimization.py"),
    os.path.join(APP_DIR, "views", "16_Trend_Analysis.py"),
    os.path.join(APP_DIR, "views", "17_Process_Property_Correlation.py"),
    os.path.join(APP_DIR, "views", "18_Root_Cause_Assistant.py"),
    os.path.join(APP_DIR, "views", "19_Machine_Settings_Optimization.py"),
]

# The 12 taxonomy entries removed under this correction because the fault
# itself only exists on a continuous slabstock/Maxfoam line and has no
# discontinuous rigid-molding analog - see quality_issue_taxonomy.py's
# module docstring, A5-08 note, for the full rationale per entry.
_REMOVED_TAXONOMY_NAMES = [
    "Creeping cream line",
    "Undercutting / under-running",
    "Mechanical splits",
    "Chimney splits (top skin)",
    "Footprints / build-up splits",
    "Trough build-up splits",
    "Clogged-flexible splits",
    "Domed profile (Maxfoam)",
    "Concave profile (Maxfoam)",
    "Excess-flow grooves",
    "Horizontal holes",
    "Shoulder holes (Maxfoam)",
]

# A representative sample of generic, chemistry/cell-structure-driven fault
# names that are still Rigid-relevant and must remain selectable.
_RETAINED_TAXONOMY_NAMES = [
    "Boiling", "Collapse", "Shrinkage", "Low block density",
    "Poor tensile strength / weak foam", "No issue found - routine check",
]


# ---------------------------------------------------------------------------
# 1. AI prompt framing (ai_assistant.py + pages 15-19) - item 3.1
# ---------------------------------------------------------------------------

def test_no_flexible_slabstock_manufacturer_framing_anywhere_in_ai_prompts():
    """Zero occurrences of the retired framing phrase across the 6 known
    prompt-string call sites, scanned by raw source text (not just the
    loaded constant) so a second, un-migrated copy would still be caught."""
    hit_files = []
    for path in [AI_ASSISTANT_PY] + PI3_PAGES:
        text = open(path, encoding="utf-8").read()
        if "flexible slabstock foam manufacturer" in text:
            hit_files.append(path)
    assert not hit_files, (
        f"Retired 'flexible slabstock foam manufacturer' framing still present in: {hit_files}"
    )


def test_ai_prompts_now_use_rigid_framing():
    """Positive-side check: the replacement framing is actually present at
    every site (not just that the old string is gone - confirms the edit
    landed, not that the sentence was deleted outright)."""
    assert "rigid PUR/PIR foam manufacturer" in ai_assistant.PLANT_QUERY_SYSTEM_PROMPT
    for path in PI3_PAGES:
        text = open(path, encoding="utf-8").read()
        assert "rigid PUR/PIR foam manufacturer" in text, (
            f"{path} missing the corrected Rigid Foam framing"
        )


# ---------------------------------------------------------------------------
# 2. Quality Issues customer-facing caption (views/6) - item 3.2
# ---------------------------------------------------------------------------

def test_quality_issue_page_caption_has_no_slabstock_guide_attribution():
    text = open(PAGE6, encoding="utf-8").read()
    assert "Laader Berg" not in text
    assert "slabstock" not in text.lower()
    # The caption itself must still exist and explain the controlled-list
    # rationale in neutral terms (confirms this is an edit, not a deletion
    # of the whole caption).
    assert "controlled list" in text
    assert "counted/trended" in text
    assert "reliably" in text


# ---------------------------------------------------------------------------
# 3. Quality issue taxonomy content (quality_issue_taxonomy.py) - item 3.3
# ---------------------------------------------------------------------------

# Full retired/quarantined-term list per both of Charlie's returns: pass 1
# (Flexible-line/slabstock geometry terms) + pass 2 (tunnel, air injection,
# air pressure, methylene chloride - D5-05 QUARANTINED and other
# already-retired WP7 concepts the pass-1 scan didn't cover).
_ALL_RETIRED_TERMS = [
    "trough", "fall-plate", "fall plate", "conveyor", "lay-down",
    "laydown", "slabstock", "maxfoam",
    "tunnel", "air injection", "air pressure", "methylene chloride",
]


def test_taxonomy_module_docstring_may_cite_source_but_active_data_may_not():
    """The module docstring (developer-facing, not reachable through any
    UI or LLM-facing path) is allowed to keep citing the Laader Berg source
    guide and naming the retired terms it removed, for engineering
    provenance/traceability - both of Charlie's returns targeted live
    customer-facing and LLM-facing paths specifically (see this file's
    module docstring). Everything BELOW the docstring - the actual
    QUALITY_ISSUE_TAXONOMY dict literal and helper functions that the
    Quality Issue page and its CSV import actually read from - must be
    completely clean of every retired/quarantined term from both passes.

    Raw-text scan (not the loaded dict) so this also catches a term
    reintroduced outside the dict literal itself (a stray comment, a
    default value, anything else below the docstring)."""
    text = open(TAXONOMY_PY, encoding="utf-8").read()
    quote_positions = [i for i in range(len(text)) if text.startswith('"""', i)]
    assert len(quote_positions) >= 2, "quality_issue_taxonomy.py has no closed module docstring"
    active_text = text[quote_positions[1] + 3:]
    # Adjacent Python string literals split across physical lines (the
    # taxonomy's own formatting style) must be joined before scanning, or a
    # term straddling a line break (e.g. "...air " + "injection...") would
    # be silently missed by a single-line substring search.
    import re as _re
    active_joined = _re.sub(r'"\s*\n\s*"', "", active_text)

    hits = [t for t in _ALL_RETIRED_TERMS if t in active_joined.lower()]
    assert not hits, f"Retired/quarantined terms still present in active taxonomy content: {hits}"


def test_taxonomy_dict_values_contain_zero_retired_or_quarantined_terms():
    """Charlie's second return: 'the scan should target active dictionary
    content'. This scans the LOADED, already-concatenated
    QUALITY_ISSUE_TAXONOMY dict values directly - the most direct possible
    proof that nothing a user or CSV import can actually read out of this
    module (every `name` and `typical_causes` string) contains a retired
    Flexible-line term or a D5-05-quarantined process concept (air
    injection/air pressure), a retired continuous-line reference (tunnel),
    or an unvalidated blowing-agent example (methylene chloride)."""
    hits = []
    for category, entries in qit.QUALITY_ISSUE_TAXONOMY.items():
        for entry in entries:
            haystack = f"{entry['name']} {entry['typical_causes']}".lower()
            for term in _ALL_RETIRED_TERMS:
                if term in haystack:
                    hits.append((category, entry["name"], term))
    assert not hits, f"Active taxonomy dict entries still contain retired/quarantined terms: {hits}"


def test_twelve_flexible_only_taxonomy_entries_are_removed():
    for name in _REMOVED_TAXONOMY_NAMES:
        assert qit.lookup(name) is None, (
            f"{name!r} should have been removed from the active taxonomy under A5-08"
        )
    # Legacy rows already recorded under a retired name must still resolve
    # to no controlled match (not raise) - the module's own historical-data
    # contract, confirmed here rather than assumed.
    assert qit.lookup_case_insensitive("chimney splits (top skin)") is None


def test_generic_rigid_relevant_taxonomy_entries_are_retained():
    """The correction is a targeted removal, not a wholesale gutting of the
    taxonomy - generic chemistry/cell-structure fault types that generalize
    to Rigid Foam must still be selectable."""
    for name in _RETAINED_TAXONOMY_NAMES:
        assert qit.lookup(name) is not None, f"{name!r} should still be an active taxonomy entry"


def test_taxonomy_entry_count_reflects_the_twelve_item_removal():
    # 54 entries existed pre-correction (14 + 12 + 9 + 12 + 5 + 1 + 1); 12
    # were removed under A5-08, leaving 42.
    assert len(qit.all_issue_names()) == 42


def test_no_taxonomy_entry_has_empty_name_or_stray_removed_fragment():
    """Sanity check on the edit itself: every remaining entry has a
    non-empty name, and none of the surviving typical_causes strings
    accidentally retained a dangling clause fragment (e.g. a leading
    semicolon left over from stripping a retired-concept clause)."""
    for category, entries in qit.QUALITY_ISSUE_TAXONOMY.items():
        for entry in entries:
            assert entry["name"], f"Empty name in category {category!r}"
            causes = entry["typical_causes"]
            assert not causes.startswith(";"), (
                f"{entry['name']!r} typical_causes starts with a dangling ';': {causes!r}"
            )
            assert not causes.startswith(" "), (
                f"{entry['name']!r} typical_causes starts with a stray leading space: {causes!r}"
            )
