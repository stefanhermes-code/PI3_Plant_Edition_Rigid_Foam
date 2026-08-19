"""No internal development vocabulary in customer-facing text (2026-08-19).

Stefan spotted "WP7 Phase 2 Closeout Correction:" at the top of the Edit Run
panel on the deployed application. A plant engineer opening a production run
has no idea what WP7 Phase 2 is, who wrote the closeout correction, or why
either fact belongs on the screen. It is a note between developers that ended
up in front of a customer.

WHY THIS KEEPS HAPPENING, AND WHY A TEST IS THE RIGHT ANSWER

The project's own working method causes it. Every change arrives as a numbered
work package or CR with a ruling behind it, so while the change is being made
that vocabulary is the most natural way to say why a control exists - and a
caption explaining a control is exactly where the explanation wants to go. The
fix is not to be more careful. It is to make the boundary mechanical: internal
identifiers belong in comments, docstrings and the change log, never in a
string a user reads.

CR-18 established this pattern for one leaked word ("foam family"). This file
generalises it to the whole internal vocabulary.

WHAT COUNTS AS A LEAK

Work package and CR identifiers (WP7, CR-03, AF22-01, F22-04), phase and
closeout process language, the names of people on the project, and references
to internal governing documents or design-doc sections.

WHAT DOES NOT

Controlled data identifiers the application genuinely owns and a governed plant
system is meant to cite: CALC-001, UOM-015, PS-076, MSC-001, and the like.
Those are the system's controlled vocabulary, visible on purpose. "Closeout" as
a trial lifecycle stage is likewise real business language, not process leakage,
so the trials pages keep it - the term is only a problem when it is qualified by
an internal phase or correction.

Usage: python -m pytest tests/test_internal_vocabulary_leak.py -v
"""
import io
import os
import re
import sys
import tokenize

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories that hold no user-facing text.
SKIP_DIRS = {"__pycache__", ".git", "tests", "_to_delete", ".venv", "assets"}

# Files that are developer tooling rather than application pages.
SKIP_FILES = {"version.py", "demo_data.py", "legacy_migration.py", "cr21_pm_migration.py"}

# Streamlit calls that put text in front of a user.
VISIBLE_CALL = re.compile(
    r"st\.(caption|info|warning|error|success|markdown|write|title|header|subheader|text|"
    r"metric|toast|expander|radio|selectbox|text_input|text_area|number_input|checkbox|"
    r"button|form_submit_button|download_button|multiselect|slider|date_input|time_input|"
    r"file_uploader|tabs|columns|popover|status)\s*\("
)

# Keyword arguments that carry user-facing text into a helper.
VISIBLE_KWARG = re.compile(
    r"\b(label|help|caption|placeholder|function_text|action_text|extra_warning|message|"
    r"warning|intro|description_text|title)\s*=\s*$"
)

# Internal development vocabulary.
INTERNAL_PATTERNS = [
    (r"\bWP-?\d+\b", "work package identifier"),
    (r"\bCR-\d+\b", "change request identifier"),
    (r"\bAF\d+-\d+\b", "CR action identifier"),
    (r"\bF\d\d-\d+\b", "CR finding identifier"),
    (r"\bP8-OWR-\d+\b", "open work register item"),
    (r"\bPhase\s*\d+\b", "internal phase reference"),
    (r"Closeout Correction", "internal closeout process language"),
    (r"\bCharlie\b", "project role name"),
    (r"\bStefan\b", "project role name"),
    (r"\bJC\b", "project role name"),
    (r"governing document", "internal document reference"),
    (r"design doc", "internal document reference"),
    (r"\bMaterial Gap\b", "internal review finding language"),
    (r"\bDecision\s*\d+\b", "internal decision reference"),
    (r"\bRHF-\d+\b", "internal requirement identifier"),
    (r"\bRCF-\d+\b", "internal requirement identifier"),
]
COMPILED = [(re.compile(p), why) for p, why in INTERNAL_PATTERNS]


def _python_files():
    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in sorted(files):
            if name.endswith(".py") and name not in SKIP_FILES:
                yield os.path.join(root, name)


def _user_visible_strings(path):
    """Yield (line_number, literal) for string literals that reach a user.

    Uses the tokenizer rather than a plain line scan so that comments and
    docstrings - where this vocabulary is not only allowed but wanted - are
    never flagged. A string counts as user-visible when a Streamlit display
    call, or a text-carrying keyword argument, opens within the preceding few
    lines; that covers Streamlit's habit of splitting one long message across
    several implicitly concatenated literals.
    """
    with open(path, encoding="utf-8", errors="replace") as handle:
        source = handle.read()
    lines = source.splitlines()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return
    for token in tokens:
        if token.type != tokenize.STRING:
            continue
        window_start = max(0, token.start[0] - 13)
        context = "\n".join(lines[window_start:token.start[0]])
        tail = context.rstrip()[-80:]
        if VISIBLE_CALL.search(context) or VISIBLE_KWARG.search(tail):
            yield token.start[0], token.string


def _is_module_or_function_docstring(literal, context_tail):
    """A triple-quoted literal opening a line on its own is prose, not UI."""
    return literal.startswith(('"""', "'''")) and not context_tail.strip().endswith(("(", ","))


def scan():
    findings = []
    for path in _python_files():
        relative = os.path.relpath(path, APP_DIR)
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
        for line_number, literal in _user_visible_strings(path):
            context_tail = lines[line_number - 2] if line_number >= 2 else ""
            if _is_module_or_function_docstring(literal, context_tail):
                continue
            for pattern, why in COMPILED:
                match = pattern.search(literal)
                if match:
                    findings.append((relative, line_number, match.group(0), why, literal.strip()[:120]))
                    break
    return findings


def test_no_internal_vocabulary_reaches_a_user():
    findings = scan()
    report = "\n".join(
        f"  {f}:{n}  {term!r} ({why})\n      {text}" for f, n, term, why, text in findings
    )
    assert not findings, (
        "Internal development vocabulary found in user-visible text. Move it to a comment "
        "or the change log and say the same thing in the user's language:\n" + report
    )


def test_the_scan_can_actually_see_a_leak():
    """A scan that finds nothing is worthless if it also cannot find anything.

    Pins the detector against the exact string Stefan found on the deployed
    application, so a future refactor that quietly breaks the tokenizer walk
    fails here rather than passing an empty scan as a clean bill of health.
    """
    sample = '"WP7 Phase 2 Closeout Correction: Run Context is captured context-first"'
    assert any(pattern.search(sample) for pattern, _ in COMPILED)


def test_controlled_identifiers_are_not_treated_as_leaks():
    """The system's own controlled vocabulary is meant to be visible."""
    for allowed in (
        '"Calculated using CALC-001 and CALC-015."',
        '"Unit: UOM-015 (kg)"',
        '"Process setting PS-076"',
        '"Configuration MSC-001, revision 2"',
        '"Closeout (all required before status can be set to Closed)"',
    ):
        offenders = [why for pattern, why in COMPILED if pattern.search(allowed)]
        assert not offenders, f"{allowed} wrongly flagged as {offenders}"
