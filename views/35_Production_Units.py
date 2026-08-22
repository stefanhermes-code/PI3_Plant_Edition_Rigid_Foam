"""Production Units / Cells (new page, R3-WP1 follow-up, 2026-08-21).

WHY THIS PAGE DID NOT EXIST, AND WHY IT DOES NOW

db.ProductionUnit has been in the schema since 2026-08-06 (WP3) and has never
had a screen. Two rows lived in it, both created by migration, and no user
could see or maintain either one. That went unnoticed for a fortnight for a
specific reason: views/31_Production_Equipment.py labels db.Machine records
"Production Unit / Cell", so the level LOOKED present in the navigation. It was
not - that page edits equipment.

R3-WP1's inventory found the collision and Charlie ruled on it (his
"R3-WP1 Production Unit / Equipment Naming Ruling", 21 August 2026, option A):

  - db.Machine        -> "Equipment / Machine" on every user-visible surface.
                         Never "Production Unit" in any form.
  - db.ProductionUnit -> "Production Unit / Cell".

and required this page before R3-WP4 adds production_runs.production_unit_id,
because a run cannot record a Production Unit that no user can see.

The two structures below Plant, from the same ruling:

  Operational   Company -> Plant -> Production Unit / Cell -> Equipment/Machine
  Product       Company -> Plant -> PU Material Family -> Application Area
                                 -> Product Grade -> Formulation -> Version

This page is the operational branch's missing level. Equipment stays on the
Production Equipment page; what shows here is which equipment is assigned to
which unit, which is the relationship R3-WP4's run snapshot resolves through.

WHAT IS DELIBERATELY NOT HERE

No new master-data fields. Charlie: "Do not invent new master-data fields to
fill the page." The form offers exactly the columns db.ProductionUnit already
has and nothing else.

R3 (2026-08-22) added one of those columns: operation_mode, continuous versus
shot-by-shot, per Charlie's R3 handover. It appears here now because migration
0025 created it and helpers.run_uses_cycle_shot_operation() reads it - which is
the standard v0.80.0 held for. A field arrives when something reads it, not
before.

It is left EMPTY for both live units, and that is the rule rather than an
oversight. Charlie's WP7 Phase 2 closeout rejected inferring cycle/shot from a
name; both live Production Methods are called "Discontinuous", which is exactly
the trap. Empty means "not characterised - inherit the Production Method", and
the picker offers no third value saying so, because a "Not specified" option
looks like an answer and gets stored as one.

No CSV/Excel import tab, so this page carries two of CR-11's three tabs rather
than three. A Production Unit has four fields and a plant; the two live rows
were created by migration because there was no page, not because there were
too many to type. An import path is a validation surface, and one gets built
when a customer actually has units to bulk-load.

PAGE KEY

Reuses "plant_overview", the key views/31_Production_Equipment.py already uses.
A Production Unit and the equipment inside it are one operational structure,
and a role that may maintain the equipment must be able to maintain the unit
that holds it - splitting the key would let an administrator grant one and not
the other, which is a permission state with no meaning. It also means no
existing role silently loses access to a page key it has never seen.
"""

import streamlit as st

from access_control import can_use_page
from auth import current_user, logout_button, require_login
from db import Machine, Mixhead, Plant, ProductionUnit, Tool, get_session, init_db
from helpers import (
    PRODUCTION_UNIT_OPERATION_MODES,
    clickable_table,
    delete_with_confirm,
    page_setup,
    render_function_action_intro,
    view_only_notice,
)
from tenant_scope import apply_scope, company_picker, plant_ids_for_company

page_setup("Production Units / Cells")
init_db()
require_login()
logout_button()

st.title("Production Units / Cells")
render_function_action_intro(
    function_text=(
        "A Production Unit / Cell is the operational grouping a plant actually produces on - a "
        "panel line, an appliance foaming cell. It sits between the Plant and the individual "
        "Equipment / Machines: Company, then Plant, then Production Unit / Cell, then "
        "Equipment / Machine. Each piece of equipment belongs to one unit at a time, and a unit "
        "may hold more than one. A production run records the equipment used and the unit that "
        "applied at the time of the run."
    ),
    action_text=(
        "Use this page to add each Production Unit / Cell at a plant and to see which "
        "Equipment / Machines are assigned to it. Assign a machine to a unit on the Production "
        "Equipment page - the assignment is a property of the equipment, so it is edited there "
        "and shown here."
    ),
)

session = get_session()
user = current_user()
page_usable = can_use_page(
    "plant_overview", role_id=user["role_id"], session=session,
    is_super_admin=user["is_super_admin"],
)
if not page_usable:
    view_only_notice()

company_filter, _all_companies = company_picker(
    st, session, user["is_platform_owner"], user["company_id"], key="pu_company_filter"
)
# Every read below is scoped to these plant ids. A Production Unit has no
# company of its own - it belongs to a plant, and the plant belongs to a
# company - so plant scope IS company scope here, and there is no branch in
# which an unscoped query is correct. Note plant_ids_for_company(None) means
# UNFILTERED, which is only ever reached for a platform owner viewing all
# companies.
plant_ids = plant_ids_for_company(session, company_filter.id if company_filter else None)
plants = apply_scope(session.query(Plant), Plant.id, plant_ids).order_by(Plant.name).all()

if not plants:
    st.info("Add a plant first (Plants page) before adding Production Units / Cells.")
    st.stop()

_plant_ids_in_scope = [p.id for p in plants]
units = (
    session.query(ProductionUnit)
    .filter(ProductionUnit.plant_id.in_(_plant_ids_in_scope))
    .order_by(ProductionUnit.plant_id, ProductionUnit.controlled_id, ProductionUnit.name)
    .all()
)
# Equipment is read once, scoped the same way, and indexed by unit - one query
# instead of one per unit, and the same scoped set backs both the counts and
# the delete guard below.
machines_in_scope = (
    session.query(Machine)
    .filter(Machine.plant_id.in_(_plant_ids_in_scope))
    .order_by(Machine.name)
    .all()
)
machines_by_unit = {}
for _m in machines_in_scope:
    machines_by_unit.setdefault(_m.production_unit_id, []).append(_m)

c1, c2, c3 = st.columns(3)
c1.metric("Production Units / Cells", len(units))
c2.metric("Equipment / Machines", len(machines_in_scope))
c3.metric("Equipment without a unit", len(machines_by_unit.get(None, [])))

if machines_by_unit.get(None):
    # Not an error. A machine may sit without a unit while master data is
    # being set up, and Charlie's ruling keeps that state legal. It stops
    # being acceptable at R3-WP4, where a run may not be COMPLETED unless its
    # equipment resolves to a unit - so it is surfaced here rather than left
    # for that work package to discover.
    st.info(
        "Equipment not yet assigned to any Production Unit / Cell: "
        + ", ".join(m.name for m in machines_by_unit[None])
        + ". Assign it on the Production Equipment page."
    )

tab_create, tab_edit_delete = st.tabs(
    ["Create Production Unit / Cell", "Edit/Delete Production Unit / Cell"]
)

with tab_create:
    if not page_usable:
        st.caption("View-only access - adding a Production Unit / Cell is restricted for your role.")
    else:
        plant_for_unit = st.selectbox(
            "Plant *", plants, format_func=lambda p: p.name, key="add_unit_plant"
        )
        with st.form("add_unit"):
            u_name = st.text_input("Production Unit / Cell name * (e.g. Panel Line 1)")
            u_code = st.text_input(
                "Unit code",
                help="Your own controlled reference for this unit, e.g. PU-PH1-001.",
            )
            u_type = st.text_input(
                "Unit type",
                help="What kind of unit it is, e.g. Discontinuous panel line.",
            )
            u_mode = st.selectbox(
                "Operation mode",
                [""] + list(PRODUCTION_UNIT_OPERATION_MODES),
                format_func=lambda m: "— not characterised —" if m == "" else m,
                help="How this line runs. Leave it unset until somebody who knows the "
                     "line can say - unset inherits the Production Method's setting, and "
                     "it is what decides whether runs here capture Cycle / Shot data.",
            )
            u_notes = st.text_area("Notes")
            st.caption(f"Plant: **{plant_for_unit.name}** (change above, outside this form)")
            submitted = st.form_submit_button("Save Production Unit / Cell")
            if submitted:
                if not u_name.strip():
                    st.error("Production Unit / Cell name is required.")
                elif u_code.strip() and any(
                    (x.controlled_id or "").strip().lower() == u_code.strip().lower()
                    for x in session.query(ProductionUnit).all()
                ):
                    # Checked across every unit, not just this plant's. A unit
                    # code is a reference somebody quotes - two units answering
                    # to one code is the R1 name-collision defect again, and it
                    # costs one query to refuse it here.
                    st.error(f"Unit code '{u_code.strip()}' is already used by another Production Unit / Cell.")
                else:
                    session.add(
                        ProductionUnit(
                            plant_id=plant_for_unit.id,
                            name=u_name.strip(),
                            controlled_id=u_code.strip() or None,
                            unit_type=u_type.strip() or None,
                            operation_mode=u_mode or None,
                            notes=u_notes or None,
                        )
                    )
                    session.commit()
                    st.success(f"Production Unit / Cell '{u_name.strip()}' added.")
                    st.rerun()

with tab_edit_delete:
    st.subheader("Production Units / Cells")
    if not units:
        st.info("No Production Units / Cells recorded yet.")
    else:
        unit_rows = [
            {
                "Plant": u.plant.name if u.plant else "—",
                "Unit code": u.controlled_id or "—",
                "Production Unit / Cell": u.name,
                "Unit type": u.unit_type or "—",
                "Operation mode": u.operation_mode or "—",
                "Equipment / Machines": (
                    ", ".join(m.name for m in machines_by_unit.get(u.id, [])) or "—"
                ),
                "Notes": u.notes or "",
            }
            for u in units
        ]
        st.caption("Click a row to edit (and optionally delete) that Production Unit / Cell.")
        idx = clickable_table(unit_rows, key="units_table")
        if idx is not None and idx < len(units):
            st.session_state["unit_selected_id"] = units[idx].id
        else:
            st.session_state.pop("unit_selected_id", None)

        selected_unit_id = st.session_state.get("unit_selected_id")
        selected_unit = next((u for u in units if u.id == selected_unit_id), None)

        if selected_unit:
            st.markdown(f"**Edit Production Unit / Cell: {selected_unit.name}**")
            assigned = machines_by_unit.get(selected_unit.id, [])
            if assigned:
                st.caption(
                    "Equipment / Machines in this unit: "
                    + ", ".join(m.name for m in assigned)
                    + ". Reassign equipment on the Production Equipment page."
                )
            else:
                st.caption("No Equipment / Machine is assigned to this unit yet.")

            if not page_usable:
                st.caption("View-only access - editing and deleting is restricted for your role.")
            else:
                e_plant = st.selectbox(
                    "Plant *", plants,
                    index=next((i for i, p in enumerate(plants) if p.id == selected_unit.plant_id), 0),
                    format_func=lambda p: p.name, key=f"edit_unit_plant_{selected_unit.id}",
                )
                with st.form(f"edit_unit_{selected_unit.id}"):
                    e_name = st.text_input(
                        "Production Unit / Cell name *", value=selected_unit.name,
                        key=f"edit_unit_name_{selected_unit.id}",
                    )
                    e_code = st.text_input(
                        "Unit code", value=selected_unit.controlled_id or "",
                        key=f"edit_unit_code_{selected_unit.id}",
                    )
                    e_type = st.text_input(
                        "Unit type", value=selected_unit.unit_type or "",
                        key=f"edit_unit_type_{selected_unit.id}",
                    )
                    _mode_options = [""] + list(PRODUCTION_UNIT_OPERATION_MODES)
                    e_mode = st.selectbox(
                        "Operation mode", _mode_options,
                        index=(_mode_options.index(selected_unit.operation_mode)
                               if selected_unit.operation_mode in _mode_options else 0),
                        format_func=lambda m: "— not characterised —" if m == "" else m,
                        key=f"edit_unit_mode_{selected_unit.id}",
                        help="Decides whether runs on this unit capture Cycle / Shot data, "
                             "unless a specific Equipment / Machine overrides it.",
                    )
                    e_notes = st.text_area(
                        "Notes", value=selected_unit.notes or "",
                        key=f"edit_unit_notes_{selected_unit.id}",
                    )
                    st.caption(f"Plant: **{e_plant.name}** (change above, outside this form)")
                    e_submitted = st.form_submit_button("Save changes")
                    if e_submitted:
                        _stranded = [m for m in assigned if m.plant_id != e_plant.id]
                        if not e_name.strip():
                            st.error("Production Unit / Cell name is required.")
                        elif e_code.strip() and any(
                            (x.controlled_id or "").strip().lower() == e_code.strip().lower()
                            and x.id != selected_unit.id
                            for x in session.query(ProductionUnit).all()
                        ):
                            st.error(
                                f"Unit code '{e_code.strip()}' is already used by another "
                                "Production Unit / Cell."
                            )
                        elif _stranded:
                            # Moving a unit to another plant would leave its
                            # equipment pointing across a plant - and since a
                            # plant belongs to a company, across a COMPANY.
                            # A label cannot prevent this; a guard can, and a
                            # rerun can resolve a widget with nobody watching.
                            st.error(
                                "Move the Equipment / Machines out of this unit first - "
                                + ", ".join(m.name for m in _stranded)
                                + " would be left in another plant's unit."
                            )
                        else:
                            selected_unit.plant_id = e_plant.id
                            selected_unit.name = e_name.strip()
                            selected_unit.controlled_id = e_code.strip() or None
                            selected_unit.unit_type = e_type.strip() or None
                            selected_unit.operation_mode = e_mode or None
                            selected_unit.notes = e_notes or None
                            session.commit()
                            st.success("Production Unit / Cell updated.")
                            st.rerun()

                _mixheads = (
                    session.query(Mixhead)
                    .filter(Mixhead.production_unit_id == selected_unit.id).count()
                )
                _tools = (
                    session.query(Tool)
                    .filter(Tool.production_unit_id == selected_unit.id).count()
                )
                if _mixheads or _tools:
                    # mixheads.production_unit_id is NOT NULL, so deleting the
                    # unit under one is a foreign-key violation rather than a
                    # tidy unlink. Refused with the reason rather than offered
                    # and then failing at the database.
                    st.warning(
                        "This Production Unit / Cell cannot be deleted while it has "
                        f"{_mixheads} mixhead(s) and {_tools} tool(s) attached."
                    )
                else:
                    def _delete_unit(unit_id=selected_unit.id):
                        for m in machines_by_unit.get(unit_id, []):
                            m.production_unit_id = None
                        session.query(ProductionUnit).filter(
                            ProductionUnit.id == unit_id
                        ).delete()
                        session.commit()
                        st.session_state.pop("unit_selected_id", None)

                    delete_with_confirm(
                        f"Production Unit / Cell '{selected_unit.name}'",
                        _delete_unit,
                        key_prefix=f"delete_unit_{selected_unit.id}",
                        extra_warning=(
                            "Its Equipment / Machines are not deleted - they are left without a "
                            "unit and can be reassigned on the Production Equipment page."
                            if assigned else ""
                        ),
                    )
