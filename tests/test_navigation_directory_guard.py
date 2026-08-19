"""Guard on the screen-directory name (v0.69.0, 2026-08-19).

Streamlit 1.60.0 decides whether the entrypoint runs at all from whether a
directory literally named "pages" sits next to it. Read out of Streamlit's
own source, not inferred:

  runtime/pages_manager.py         PagesManager.uses_pages_directory is a
                                   class attribute, set once on the first
                                   PagesManager built, from
                                   Path(main_script_parent / "pages").exists()

  runtime/scriptrunner/
  script_runner.py                 if PagesManager.uses_pages_directory:
                                       _mpa_v1(main_script_path)
                                   else:
                                       exec(code, module.__dict__)

  commands/navigation.py           st.navigation() sets the flag False

In the legacy branch the entrypoint never executes. Streamlit globs the
directory, sorts it, and builds its own flat navigation, so app_rigid_foam's
access_control filtering is skipped entirely and every screen becomes
reachable by URL. Because the flag is process-wide and only flips when
st.navigation() is actually reached, any failure above that call - init_db()
and get_session() run roughly 35 lines earlier - leaves the whole process in
unfiltered legacy mode until it is restarted, with no traceback.

Renaming the directory to "views" makes the flag evaluate False at
construction, which closes the window completely rather than narrowing it.

These tests fail if someone renames the directory back, adds a "pages"
directory alongside it, or points a page reference at the old path.

Usage: python -m pytest tests/test_navigation_directory_guard.py -v
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRYPOINT = os.path.join(APP_DIR, "app_rigid_foam.py")
VIEWS_DIR = os.path.join(APP_DIR, "views")


def test_screen_directory_is_views_and_no_pages_directory_exists():
    """The precondition the whole guard rests on."""
    assert os.path.isdir(VIEWS_DIR), "the screen directory must be views/"
    assert not os.path.isdir(os.path.join(APP_DIR, "pages")), (
        "a directory named 'pages' next to the entrypoint puts Streamlit into "
        "legacy auto-discovered-pages mode, in which app_rigid_foam.py - and "
        "therefore all access_control filtering - never runs"
    )


def test_streamlit_evaluates_this_layout_as_not_using_a_pages_directory():
    """The mechanism itself, against Streamlit's own class rather than a
    reimplementation of it. Fails if a future Streamlit changes the rule."""
    from streamlit.runtime.pages_manager import PagesManager

    original = PagesManager.uses_pages_directory
    try:
        PagesManager.uses_pages_directory = None
        PagesManager(ENTRYPOINT, setup_watcher=False)
        assert PagesManager.uses_pages_directory is False, (
            "Streamlit resolved this layout as using a pages directory, so it "
            "would run _mpa_v1() instead of the entrypoint"
        )
    finally:
        PagesManager.uses_pages_directory = original


def test_streamlit_still_branches_on_that_flag():
    """Pins the branch the guard protects against. If a Streamlit upgrade
    removes or renames it, this fails and the rename's rationale needs
    re-checking rather than silently ceasing to matter."""
    import streamlit.runtime.scriptrunner.script_runner as script_runner

    src = open(script_runner.__file__, encoding="utf-8").read()
    assert "uses_pages_directory" in src
    assert "_mpa_v1" in src


def test_no_page_reference_points_at_the_old_directory():
    """Every st.Page path in the entrypoint resolves to a file that exists."""
    src = open(ENTRYPOINT, encoding="utf-8").read()
    paths = re.findall(r'st\.Page\(\s*["\']([^"\']+\.py)["\']', src)
    assert paths, "expected st.Page(...) declarations in the entrypoint"

    missing = [p for p in paths if not os.path.isfile(os.path.join(APP_DIR, p))]
    assert not missing, f"st.Page paths that do not resolve to a file: {missing}"

    stale = [p for p in paths if p.startswith("pages/")]
    assert not stale, f"st.Page paths still pointing at the old directory: {stale}"


def test_every_view_file_is_declared_in_the_entrypoint():
    """Under st.navigation the entrypoint is the only router, so a file in
    views/ that nothing declares is unreachable rather than auto-discovered -
    the opposite of the legacy behaviour, and worth catching."""
    src = open(ENTRYPOINT, encoding="utf-8").read()
    declared = {os.path.basename(p) for p in re.findall(r'st\.Page\(\s*["\']([^"\']+\.py)["\']', src)}
    on_disk = {f for f in os.listdir(VIEWS_DIR) if f.endswith(".py") and f != "__init__.py"}

    undeclared = on_disk - declared
    assert not undeclared, f"files in views/ not declared via st.Page: {sorted(undeclared)}"


def test_entrypoint_records_why_the_directory_is_not_called_pages():
    """The rename looks like an oddity. Without the explanation the next
    person to tidy the repository reintroduces the defect."""
    src = open(ENTRYPOINT, encoding="utf-8").read()
    assert "uses_pages_directory" in src, (
        "the entrypoint must explain why the screen directory is not called "
        "'pages', naming the Streamlit mechanism"
    )
