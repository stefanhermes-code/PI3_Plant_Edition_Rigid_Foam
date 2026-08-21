"""Application Areas - the global controlled master.

R2-WP2 (Redesign Migration Plan v5, Package C, 2026-08-21) promoted the
existing applications table into the single Application Area master. The
promotion happened in migration 0011 and the LINK to it appeared on Product
Grades in the same release - and nothing else. There was no page for the
master itself, which Stefan caught: an Application Area is a thing in the
architecture, not a field on another record, and once Production Method
retires in R3 it is one of the records that takes over that role.

WHY THIS PAGE IS READ-MOSTLY

Every other master in the application is edited freely. This one is not, and
the difference is deliberate.

PU Material Family is plant-scoped: a plant's families are its own, and a
tenant editing them affects nobody else. Application Area is GLOBAL - one row
here is shared by every company, every plant and every tenant in the database.
An edit is a change to everyone's vocabulary at once, and a delete can strand
another tenant's grades.

So the page shows the master in full, lets a platform owner correct a
description, and does NOT offer create or delete. New Application Areas and
retirements arrive through a controlled change with migration evidence, the
same route APP-350 and the APP-300/APP-320 retirements took. That is Charlie's
standing rule for controlled masters and it is what keeps this table
auditable.

WHERE THE HIERARCHY ACTUALLY LIVES, IN FULL

    Company -> Plant -> Production Unit -> PU Material Family
                                        -> Application Area -> Product Grade

Stefan's ordering, 21 August 2026. Read as depth rather than as a single
parent chain, because the Plant branches: Production Unit carries the
operational side (equipment, route), and PU Material Family carries the
product side. v5 keeps the family plant-scoped and says in terms that "a plant
may manufacture the same PU Material Family on more than one unit" - so a
family cannot have one unit as its parent, and the two branches meet again at
Product Grade, which names the units that can make it.

Settled with Stefan on 21 August by asking both directions rather than one.
A Production Unit can make more than one PU Material Family - his example is a
mixing vessel used for several. And a PU Material Family can be made on more
than one unit: the plain case is a plant with two identical panel lines, both
making Rigid. Both directions many, so neither record is the other's parent and
the six levels are depth, not a single chain.

Stefan also ruled, same day, that Production Units PARTITION equipment: a
specific machine - vessel A - belongs to exactly one unit and cannot appear in
two. The schema already matches that, machines.production_unit_id being single
valued with no link table, so R3 needs nothing extra to enforce it.

One consequence survives the ruling. production_runs records machine_id and no
unit, so a run's unit is derived from its machine. That is unambiguous now that
units partition, but it is not stable: machines.production_unit_id is mutable,
and ProductionUnit's own docstring anticipates a machine being re-piped to a
different line. Re-point a machine and every past run through it silently
reports the new unit. v5's migration rules require the opposite - "keep
completed production-run history immutable", and a completed run retains the
Application Area that applied when it completed.

The precedent is already in the table: production_runs carries its own
production_method_id rather than reading the machine's. The unit wants the same
treatment, and that is an R3 item.

Every level is owned by somebody except one. Company, Plant and
PU Material Family are tenant data - a plant's families are its own. Product
Grade inherits its ownership through the family. Application Area is the
exception: it is a single GLOBAL master shared by every company, plant and
tenant in the database.

That one exception is the reason the hierarchy is enforced by validation
rather than by parentage. Row-level access runs down Company -> Plant, and a
Product Grade reaches its plant through its PU Material Family. Re-parent the
grade onto an Application Area and the chain is cut: a global record has no
plant to key on, and the permission path has nothing to follow. Plan v5's
first controlling decision says exactly this - PU Material Family stays
plant-scoped, "avoiding a security-relevant re-parenting of the family".

So the middle level is expressed by two things together: this master's
pu_material_family tag, and the rule on Product Grades that a grade may only
select an Application Area carrying its own family's value. The link on the
grade is what places it under an area; the tag is what keeps that placement
inside its own family's branch.

This page is where that level becomes visible: which areas exist, which family
each belongs to, and how many grades sit under each.

access_control page_key: "application_areas".
"""

import pandas as pd
import streamlit as st
from sqlalchemy import func

from access_control import can_use_page
from auth import current_user, logout_button, require_login
from db import Application, FoamGrade, get_session, init_db
from helpers import (
    application_area_label,
    clickable_table,
    page_setup,
    render_data_table,
    render_function_action_intro,
    view_only_notice,
)
from helpers import PU_MATERIAL_FAMILIES
from tenant_scope import apply_scope, grade_ids_for_company

page_setup("Application Areas")
init_db()
require_login()
logout_button()

st.title("Application Areas")
render_function_action_intro(
    function_text=(
        "An Application Area is the end use a product grade is designed for - a cold-room "
        "panel, a refrigerator, a water heater. It sits near the bottom of the product "
        "structure - Company, Plant and its Production Units / Cells, then PU Material "
        "Family, then Application Area, then Product Grade. Each area belongs to one PU Material "
        "Family, and a product grade may only be assigned an area belonging to its own "
        "family. Unlike the levels above it, this is a single global controlled master "
        "shared by every company and plant, so the records here are the same for everyone."
    ),
    action_text=(
        "Use this page to see which Application Areas exist, which PU Material Family each "
        "belongs to, and how many product grades use each one. Assign an area to a grade on "
        "the Product Grades page. Adding a new Application Area or retiring an existing one "
        "is a controlled change made through a migration with recorded evidence, not an "
        "edit here - ask for one if a real end use has no record. A retired area stays "
        "visible below with its grade count so nothing disappears silently."
    ),
)

session = get_session()
user = current_user()
page_usable = can_use_page(
    "application_areas", role_id=user["role_id"], session=session,
    is_super_admin=user["is_super_admin"],
)
if not page_usable:
    view_only_notice()

areas = (
    session.query(Application)
    .order_by(Application.sort_order, Application.controlled_id)
    .all()
)
if not areas:
    st.warning(
        "No Application Areas are recorded. The controlled master is populated by "
        "migration - see migrations/0011_r2wp2_application_area_master.sql."
    )
    st.stop()

# ---------------------------------------------------------------------------
# GRADE COUNTS ARE SCOPED. THE FIRST VERSION OF THIS PAGE LEAKED.
# ---------------------------------------------------------------------------
# v0.78.0 counted grades across the WHOLE database and showed the number to
# anyone who could open the page, with a comment arguing that a global master
# deserves a global count. That was wrong, and it was a cross-company data
# leak: a user at one company could read how many product grades another
# company had put on each Application Area, and watch those numbers move.
#
# Stefan, 21 August 2026: "There can be absolutely no leaking between
# companies."
#
# The distinction the first version missed. The Application Area LIST is
# shared vocabulary - the same six Rigid records for everyone, like a unit-of-
# measure master. That is not company data. How many grades a company has put
# on each one IS company data, and it does not stop being company data because
# it is expressed as an integer.
#
# So the count is scoped to the plants the viewer can reach, by the same
# Plant -> PU Material Family -> Product Grade path every other page uses.
# A platform owner sees the true total, because cross-company scope is exactly
# what that role is, and the column says which of the two is on screen.
_is_platform_owner = bool(user["is_platform_owner"])
if _is_platform_owner:
    _scoped_grade_ids = None          # apply_scope: None means no filter
    _count_label = "Product grades"
else:
    _scoped_grade_ids = grade_ids_for_company(session, user["company_id"])
    _count_label = "Your product grades"

grade_counts = dict(
    apply_scope(
        session.query(FoamGrade.application_id, func.count(FoamGrade.id)),
        FoamGrade.id,
        _scoped_grade_ids,
    )
    .group_by(FoamGrade.application_id)
    .all()
)

active_areas = [a for a in areas if a.is_active]
retired_areas = [a for a in areas if not a.is_active]

c1, c2, c3 = st.columns(3)
c1.metric("Active Application Areas", len(active_areas))
c2.metric("Retired", len(retired_areas))
c3.metric(f"{_count_label} assigned", sum(grade_counts.get(a.id, 0) for a in areas))


def _rows(rows_in):
    return [
        {
            "Controlled ID": a.controlled_id or "—",
            "Application Area": a.name,
            "PU Material Family": a.pu_material_family or "— not tagged —",
            _count_label: grade_counts.get(a.id, 0),
            "Description": a.description or "—",
        }
        for a in rows_in
    ]


st.subheader("Active")
st.caption(
    "These are the Application Areas a product grade can be assigned to. The picker on "
    "Product Grades shows only those matching that grade's PU Material Family."
)
render_data_table(pd.DataFrame(_rows(active_areas)))

# An untagged ACTIVE area cannot be selected by any grade, because the Product
# Grades picker filters on the family tag. It would sit in the master looking
# available and be unreachable - the same shape of defect as a column with no
# field. Surfaced here rather than left to be discovered.
untagged = [a for a in active_areas if not a.pu_material_family]
if untagged:
    st.warning(
        "These active Application Areas carry no PU Material Family tag, so no product "
        "grade can select them: "
        + ", ".join(application_area_label(a) for a in untagged)
        + ". Tag them through a controlled change."
    )

if retired_areas:
    st.subheader("Retired")
    st.caption(
        "Retired areas cannot be assigned to a product grade. They remain listed until "
        "their controlled removal so that anything still pointing at one stays visible."
    )
    render_data_table(pd.DataFrame(_rows(retired_areas)))
    # Scoped like the counts above, and for the same reason: naming another
    # company's stranded grade count in an error message leaks it just as well
    # as putting it in a column.
    stranded = [a for a in retired_areas if grade_counts.get(a.id, 0)]
    if stranded:
        st.error(
            "These retired Application Areas still have product grades assigned: "
            + ", ".join(
                f"{application_area_label(a)} ({grade_counts.get(a.id, 0)})"
                for a in stranded
            )
            + ". Re-assign those grades on the Product Grades page before the area is removed."
        )

st.divider()
st.subheader("Edit an Application Area")

if not page_usable:
    st.caption("View-only access - editing an Application Area is restricted for your role.")
elif not user["is_platform_owner"]:
    st.info(
        "This is a global controlled master shared by every company, so only the platform "
        "owner can change it. Assign an area to a grade on the Product Grades page."
    )
else:
    st.caption(
        "Click a row to edit its description or PU Material Family tag. The controlled ID "
        "and the active/retired state are not editable here - those change through a "
        "migration with recorded evidence, which is what keeps this master auditable."
    )
    idx = clickable_table(_rows(areas), key="application_areas_table")
    if idx is not None and idx < len(areas):
        st.session_state["application_area_selected_id"] = areas[idx].id
    else:
        st.session_state.pop("application_area_selected_id", None)

    selected_id = st.session_state.get("application_area_selected_id")
    selected = next((a for a in areas if a.id == selected_id), None)

    if selected:
        st.markdown(f"**{application_area_label(selected)}**")
        with st.form(f"edit_application_area_{selected.id}"):
            # The tag is what the Product Grades picker filters on, so an
            # unrecognised stored value stays selectable rather than being
            # quietly reset - the same rule the PU Material Family picker
            # follows. "Not tagged" is offered because it is a real state the
            # master can be in and hiding it would make it uneditable.
            family_options = ["— not tagged —"] + list(PU_MATERIAL_FAMILIES)
            current = selected.pu_material_family
            if current and current not in family_options:
                family_options.append(current)
            e_family = st.selectbox(
                "PU Material Family",
                family_options,
                index=family_options.index(current) if current in family_options else 0,
                key=f"edit_area_family_{selected.id}",
                help=(
                    "Which PU Material Family this end use belongs to. A product grade can "
                    "only be assigned an area matching its own family."
                ),
            )
            e_description = st.text_area(
                "Description", value=selected.description or "",
                key=f"edit_area_desc_{selected.id}",
            )
            if st.form_submit_button("Save changes"):
                new_family = None if e_family == "— not tagged —" else e_family
                # Platform-owner only branch, so this count is the true global
                # one - which is the correct number here: re-tagging breaks the
                # family match for EVERY company's grades on that area, not
                # only the ones this viewer can see.
                assigned = grade_counts.get(selected.id, 0)
                # Re-tagging an area that grades already use would break the
                # family-match rule for every one of them at once, and the
                # Product Grades save path would then refuse those grades until
                # someone worked out why. Refuse here instead, where the cause
                # is visible.
                if new_family != selected.pu_material_family and assigned:
                    st.error(
                        f"{assigned} product grade(s) are assigned to "
                        f"'{application_area_label(selected)}'. Changing its PU Material "
                        "Family would leave them mismatched. Re-assign those grades first. "
                        "Nothing was saved."
                    )
                else:
                    selected.pu_material_family = new_family
                    selected.description = e_description
                    session.commit()
                    st.success("Application Area updated.")
                    st.rerun()

        if st.button("Clear selection", key="clear_application_area_selection"):
            st.session_state.pop("application_area_selected_id", None)
            st.rerun()
