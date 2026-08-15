"""WP7 Phase 5, A5-08 correction (2026-08-15) - direct regression evidence.

Charlie's Closeout Review Return to JC on the WP7 Phase 5 closeout package
(WP7_Phase5_Closeout_Package.docx, v0.62.0/commit 134a9fc) held A5-08
("zero active Fall Plate, Top-flat, trough/slabstock, or other retired
Flexible Foam Production Run concepts, with customer-facing and code
dependency scan evidence") OPEN: the delivered closeout recorded A5-08 as
PASS while three live, customer-facing/LLM-facing paths still carried
inherited Flexible Foam/slabstock content -

  1. Six PI3 system/user prompt strings (ai_assistant.py's
     PLANT_QUERY_SYSTEM_PROMPT, plus one prompt each in pages 15-19) that
     framed PI3 as helping a reviewer "at a flexible slabstock foam
     manufacturer".
  2. pages/6_Quality_Observation.py's Quality Issue "Add" caption, which
     told the person logging an issue that the controlled list came from
     "Laader Berg's slabstock foaming troubleshooting guide".
  3. quality_issue_taxonomy.py's active QUALITY_ISSUE_TAXONOMY content,
     which (being sourced wholesale from that same Flexible Foam
     continuous-slabstock guide) still contained trough/conveyor/
     fall-plate/lay-down/Maxfoam-specific fault names and troubleshooting
     guidance in the live Quality Issue picker.

This file is the "direct A5-08 regression that scans the live
customer-facing and LLM-facing paths and proves zero active Flexible
Foam/slabstock inheritance" Charlie's return required (item 3.4). It does
NOT reopen A5-01 through A5-07, A5-09, or A5-10 - those remain accepted
per the return's Section 5.

Scan technique: same source-grep-with-allowlist pattern as
test_wp7_phase0_containment.py / test_cr18_product_family_terminology.py -
walk the file's raw text and assert the retired term is entirely absent
from the live surface (not just reworded around), while confirming the
harmless internal-provenance mentions that were deliberately kept (OEM
name lists, module docstrings, changelog history) are exactly what the
scan tolerates and nothing more.

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
PAGE6 = os.path.join(APP_DIR, "pages", "6_Quality_Observation.py")
TAXONOMY_PY = os.path.join(APP_DIR, "quality_issue_taxonomy.py")
PI3_PAGES = [
    os.path.join(APP_DIR, "pages", "15_Recipe_Optimization.py"),
    os.path.join(APP_DIR, "pages", "16_Trend_Analysis.py"),
    os.path.join(APP_DIR, "pages", "17_Process_Property_Correlation.py"),
    os.path.join(APP_DIR, "pages", "18_Root_Cause_Assistant.py"),
    os.path.join(APP_DIR, "pages", "19_Machine_Settings_Optimization.py"),
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
# 2. Quality Issues customer-facing caption (pages/6) - item 3.2
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

def test_taxonomy_module_docstring_may_cite_source_but_active_data_may_not():
    """The module docstring (developer-facing, not reachable through any
    UI or LLM-facing path) is allowed to keep citing the Laader Berg source
    guide for engineering provenance/traceability - Charlie's return
    targeted live customer-facing and LLM-facing paths specifically (see
    this file's module docstring). Everything BELOW the docstring - the
    actual QUALITY_ISSUE_TAXONOMY dict and helper functions that the
    Quality Issue page and its CSV import actually read from - must be
    completely clean of trough/fall-plate/conveyor/lay-down/slabstock/
    Maxfoam content."""
    text = open(TAXONOMY_PY, encoding="utf-8").read()
    quote_positions = [i for i in range(len(text)) if text.startswith('"""', i)]
    assert len(quote_positions) >= 2, "quality_issue_taxonomy.py has no closed module docstring"
    active_text = text[quote_positions[1] + 3:]

    retired_terms = [
        "trough", "fall-plate", "fall plate", "conveyor", "lay-down",
        "laydown", "slabstock", "maxfoam",
    ]
    hits = [t for t in retired_terms if t in active_text.lower()]
    assert not hits, f"Retired Flexible-line terms still present in active taxonomy content: {hits}"


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
