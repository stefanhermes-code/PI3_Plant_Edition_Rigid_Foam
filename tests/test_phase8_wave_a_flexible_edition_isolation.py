"""Phase 8 Wave A correction (2026-08-18) - direct evidence for Charlie's
required correction #3 on the Wave A closeout return: "Provide direct
evidence showing Rigid Foam reading QualityIssueType, PossibleCause and
IssueCauseLink from the database, with the Flexible edition still using
its approved path... Add regression coverage for both edition paths."

test_phase8_wave_a_quality_issue_cutover.py already proves the Rigid side
(pages/6_Quality_Observation.py and reports.py import quality_issue_registry,
a database-backed module, and no longer import quality_issue_taxonomy at
all). This file adds the other half: proof the Flexible edition
(PI3_Plant_Edition_App, a separate codebase/app living alongside this repo
under the same "15. PI3 Plant Edition" workspace folder, not part of this
git repository) still reads QualityObservation "issue type" vocabulary from
its own static quality_issue_taxonomy.py module and has no route into this
repo's database-backed registry.

Both editions share the same Supabase project/instance, but Quality Issue
taxonomy was never a shared table for Flexible - Flexible's approved path
per Charlie's P8-D01 scope note is its own static Python module, unchanged
by the Rigid-only Wave A cutover. Two things would break that isolation and
this file catches both:
  1. Flexible's page or reports module starts importing quality_issue_registry
     (the new Rigid-only DB module) - checked directly against Flexible's
     source.
  2. quality_issue_registry.py (or the QualityIssueTypeApplicability/state
     machinery it depends on) gets copied/vendored into the Flexible app
     directory - checked by asserting the file does not exist there.

The Flexible app is not part of this repo/CI and is only reachable as a
sibling directory on the machine this was authored on (same parent folder
as this repo: ".../15. PI3 Plant Edition/{PI3_Rigid_Foam_Edition_App,
PI3_Plant_Edition_App}"). If that sibling isn't present - e.g. a clean git
clone of just this repo - the tests skip with a clear reason rather than
fail, since the isolation they check is a property of the *sibling app's*
source, not of anything in this repository.

The AppTest execution proof (Flexible's Quality Issue page actually renders
off its own static taxonomy) is run in a genuinely separate Python process
via subprocess, not imported in-process - Rigid and Flexible both define
same-named top-level modules (db, helpers, reports, access_control,
tenant_scope, quality_issue_taxonomy, ...), and importing both into one
process's sys.modules would make whichever loads second silently reuse the
first's cached module, producing a false pass/fail.

Usage: python -m pytest tests/test_phase8_wave_a_flexible_edition_isolation.py -v
"""
import os
import subprocess
import sys

import pytest

RIGID_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.dirname(RIGID_APP_DIR)  # ".../15. PI3 Plant Edition"
FLEX_APP_DIR = os.path.join(WORKSPACE_ROOT, "PI3_Plant_Edition_App")
FLEX_PAGE_QI = os.path.join(FLEX_APP_DIR, "pages", "6_Quality_Observation.py")

_flex_present = os.path.isdir(FLEX_APP_DIR) and os.path.isfile(FLEX_PAGE_QI)
skip_if_no_flex = pytest.mark.skipif(
    not _flex_present,
    reason=(
        "Flexible edition app (PI3_Plant_Edition_App) not present as a sibling "
        "directory of this repo - edition-isolation check needs both apps' "
        "source on disk and is skipped outside that workspace layout."
    ),
)


# ---------------------------------------------------------------------------
# 1. Flexible's Quality Issue page and reports module still import the
#    static taxonomy module, and never the Rigid-only DB registry.
# ---------------------------------------------------------------------------

@skip_if_no_flex
def test_flexible_quality_observation_page_uses_static_taxonomy_only():
    with open(FLEX_PAGE_QI, encoding="utf-8") as f:
        src = f.read()
    assert "import quality_issue_taxonomy" in src
    assert "import quality_issue_registry" not in src
    assert "quality_issue_registry." not in src


@skip_if_no_flex
def test_flexible_reports_uses_static_taxonomy_only():
    src_path = os.path.join(FLEX_APP_DIR, "reports.py")
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    assert "quality_issue_taxonomy." in src
    assert "import quality_issue_registry" not in src
    assert "quality_issue_registry." not in src


@skip_if_no_flex
def test_flexible_app_has_no_database_registry_module():
    # quality_issue_registry.py is the Wave A Rigid-only DB cutover module
    # (P8-D01). Its presence in the Flexible app directory would mean the
    # cutover was accidentally vendored/copied across editions.
    assert not os.path.isfile(os.path.join(FLEX_APP_DIR, "quality_issue_registry.py"))


# ---------------------------------------------------------------------------
# 2. Rigid's side of the same boundary, mirrored here for a single
#    one-file record of both edition paths (test_phase8_wave_a_quality_issue_
#    cutover.py already asserts this; kept here too so this file alone is a
#    complete "both edition paths" record for the closeout).
# ---------------------------------------------------------------------------

def test_rigid_quality_observation_page_uses_database_registry_only():
    page_path = os.path.join(RIGID_APP_DIR, "pages", "6_Quality_Observation.py")
    with open(page_path, encoding="utf-8") as f:
        src = f.read()
    assert "import quality_issue_registry" in src
    assert "import quality_issue_taxonomy" not in src


# ---------------------------------------------------------------------------
# 3. Execution proof: Flexible's page 6 actually renders off its own static
#    taxonomy, in a separate process so its same-named modules (db, helpers,
#    reports, ...) never collide with Rigid's already-imported ones in this
#    test process.
# ---------------------------------------------------------------------------

@skip_if_no_flex
def test_flexible_quality_observation_page_renders_standalone_subprocess(tmp_path):
    # Flexible's db.py has no StaticPool/check_same_thread handling for a
    # bare "sqlite://" in-memory URL (it has never needed one - it has no
    # test suite of its own), and AppTest runs the page in a separate
    # thread, so a bare in-memory URL fails with "no such table" / a
    # cross-thread sqlite error that has nothing to do with edition
    # isolation. A temp file-backed sqlite DB sidesteps that.
    db_path = tmp_path / "flex_isolation_check.db"
    probe = r"""
import os, sys
sys.path.insert(0, r"%s")
os.environ["DATABASE_URL"] = r"sqlite:///%s"
import db
db.init_db()
db.Base.metadata.create_all(db.ENGINE)
session = db.get_session()

company = db.Company(name="Flex Isolation Co", is_platform_owner=True)
session.add(company); session.flush()
plant = db.Plant(company_id=company.id, name="Flex Isolation Plant")
session.add(plant); session.flush()
session.commit()

from streamlit.testing.v1 import AppTest
at = AppTest.from_file(r"%s", default_timeout=30)
at.secrets["AUTH_DISABLED"] = True
at.session_state["company_id"] = company.id
at.session_state["plant_id"] = plant.id
at.run()

import quality_issue_taxonomy
assert len(quality_issue_taxonomy.QUALITY_ISSUE_TAXONOMY) > 0
assert "quality_issue_registry" not in sys.modules

if at.exception:
    print("PAGE_EXCEPTION:", at.exception, file=sys.stderr)
    sys.exit(1)
print("FLEX_PAGE_OK")
""" % (FLEX_APP_DIR, str(db_path), FLEX_PAGE_QI)

    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, (
        f"Flexible page 6 subprocess failed.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "FLEX_PAGE_OK" in result.stdout
