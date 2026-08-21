"""Control for R0-WP4 - the application-facing name.
Redesign Migration Plan v3, Package B.

WHAT THIS CHECKS

Charlie's Package B instruction: change every user-visible reference to the
application name to the redesign name, keep the repository and directory names
unchanged, and verify before gate R-G0 closes that the OLD title is absent from
normal user-facing surfaces.

The second half is the half a rename usually fails on. Changing the header is
easy; the login screen, the browser tab, the navigation group label, the
sidebar and a password-reset email are all separate strings in separate files,
and missing one leaves the application introducing itself by two different
names depending on where you look.

The expected strings are written out literally rather than derived from a
constant, so that renaming the constant cannot silently rename the expectation
with it.

WHAT IT DELIBERATELY DOES NOT CHECK

The repository name, the directory name, the rigid_foam schema and the
app_rigid_foam.py module name are all UNCHANGED by design. This is an
application-facing rename, not a restructure. Tests that policed those would
fail the moment the rename was done correctly.

Subscription-type examples on the Companies and Subscription Types pages read
"PI3 Plant Edition - Annual" and similar. Those are illustrative DATA values
for a customer's own subscription naming, not this application's name, and are
correctly left alone.

Usage: python -m pytest tests/test_r0_application_name.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEW_NAME = "Polyurethane Company Intelligence"

# Every user-facing surface that names the application, written out.
EXPECTED = [
    ("app_rigid_foam.py", 'page_title="PI3 - Polyurethane Company Intelligence"'),
    ("app_rigid_foam.py", 'st.title("PI3 — Polyurethane Company Intelligence")'),
    ("app_rigid_foam.py", '"PI3 Plant Edition - Polyurethane Company Intelligence": top_pages'),
    ("app_rigid_foam.py", 'st.markdown("Polyurethane Company Intelligence")'),
    ("auth.py", 'st.title("PI3 Plant Edition - Polyurethane Company Intelligence")'),
]

# The old name, in every form it took.
RETIRED = [
    "Rigid Foam Intelligence",
    "PI3 Plant Edition - Rigid Foam",
    "PI3 Plant Edition, Rigid Foam",
]

USER_FACING_FILES = ["app_rigid_foam.py", "auth.py"]


def _read(name):
    with open(os.path.join(APP_DIR, name), encoding="utf-8") as handle:
        return handle.read()


def _user_visible(source):
    """Comment lines removed - a comment recording what the name used to be is
    history, not something a user reads."""
    return "\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))


def test_every_named_surface_carries_the_new_name():
    for filename, expected in EXPECTED:
        assert expected in _read(filename), f"{filename} is missing: {expected}"


def test_the_old_name_is_gone_from_user_facing_surfaces():
    """Gate R-G0's explicit condition."""
    for filename in USER_FACING_FILES:
        source = _user_visible(_read(filename))
        for retired in RETIRED:
            assert retired not in source, f"{filename} still shows the old name: {retired!r}"


def test_the_sidebar_still_distinguishes_this_application():
    """The edition line exists because with Rigid and Flexible open side by
    side there was nothing at a glance to say which was which (v0.70.2). The
    rename must not quietly delete it - it carries the new name instead."""
    source = _read("app_rigid_foam.py")
    sidebar = source[source.index("with st.sidebar:"):]
    assert 'st.markdown("**PI3 Plant Edition**")' in sidebar, "the platform name was dropped"
    assert f'st.markdown("{NEW_NAME}")' in sidebar, "the application line was dropped"
    assert 'st.caption(f"v{APP_VERSION}")' in sidebar, "the version line was dropped"


def test_the_password_reset_email_names_the_application_correctly():
    """A user locked out reads this in their own mail client, outside the app,
    where there is nothing else to tell them which system it came from."""
    source = _read("auth.py")
    assert f"PI3 Plant Edition - {NEW_NAME} - password reset request" in source
    assert f"locked out of my PI3 Plant Edition - {NEW_NAME} account" in source


def test_the_rename_did_not_touch_internals():
    """Repository, module and schema names are deliberately unchanged. If this
    fails, an application-facing rename has become a restructure."""
    assert os.path.exists(os.path.join(APP_DIR, "app_rigid_foam.py"))
    import db
    assert db.Base.metadata.schema in ("rigid_foam", None)


def test_subscription_examples_are_left_alone():
    """"PI3 Plant Edition - Annual" on the Subscription Types page is an
    example of a CUSTOMER's subscription name, not this application's name.
    Renaming it would be a false positive dressed up as thoroughness."""
    source = _read(os.path.join("views", "22_Subscription_Types.py"))
    assert "PI3 Plant Edition - Annual" in source
