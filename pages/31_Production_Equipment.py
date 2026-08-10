"""Production Equipment (new page, CR-01 - UI Navigation and Rigid-Foam
Terminology for UAT, implemented 2026-08-10).

Moved here from the old "Plant & Foam Equipment Overview" page (see
pages/1_Plant_Installation_Overview.py's docstring) per CR-01's approved
sidebar structure: Production Equipment now resolves inside the selected
Production Method's own context, under the new "Production Methods" nav
section, rather than sitting under Plant Setup.

Terminology per CR-01's mandatory table: "Machine / foaming line" ->
"Production Unit or Cell" in every user-visible label on this page. The
backend entity name (db.Machine) and its columns are unchanged - only
labels/captions change, per CR-01's "implementation note: backend entity
name may stay" guidance for this exact rename.

Defaults its Plant/Production Method pickers to the operating context set
on pages/30_Production_Methods.py (st.session_state["pm_context_plant_id"]/
["pm_context_method_id"]), if one is set for this browser tab - but doesn't
gate on it; a user can still pick a different plant/method here directly,
same as before.
"""

import streamlit as st

from access_control import can_use_page
from auth import current_user, logout_button, require_login
from cascades import unlink_machine_dependents
from db import MACHINE_OEMS, MAXFOAM_MODELS, OTHER_LAADER_BERG_MODEL, Machine, Plant, ProductionRun, get_session, init_db
from helpers import (
    activated_methods_for_plant,
    clickable_table,
    delete_with_confirm,
    page_setup,
    render_function_action_intro,
    view_only_notice,
)
from tenant_scope import apply_scope, company_picker, plant_ids_for_company

page_setup("Production Equipment")
init_db()
require_login()
logout_button()

st.title("Production Equipment")
render_function_action_intro(
    function_text=(
        "This is where you set up and maintain the Production Units/Cells (foaming lines/metering "
        "machines) at each plant, each tagged with the Production Method it runs under. Process "
        "parameters (conveyor speed, tunnel width, laydown mode, etc.) connect to the specific "
        "equipment that produced them - a production run picks one of these."
    ),
    action_text=(
        "Pick a plant (defaults to your current Production Methods operating context, if one is "
        "set), then add each Production Unit/Cell with its Production Method, OEM, and model. A "
        "plant needs at least one activated Production Method (set on the Production Methods page) "
        "before you can add equipment to it. Click a row in the table to edit or delete a Production "
        "Unit/Cell - deleting one only unlinks it from any production runs that reference it."
    ),
)
session = get_session()
user = current_user()
page_usable = can_use_page("plant_overview", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()

company_filter, _all_companies = company_picker(
    st, session, user["is_platform_owner"], user["company_id"], key="pe_company_filter"
)
plant_ids = plant_ids_for_company(session, company_filter.id if company_filter else None)
plants = apply_scope(session.query(Plant), Plant.id, plant_ids).order_by(Plant.name).all()

if not plants:
    st.info("Add a plant first (Plants page) before adding Production Equipment.")
    st.stop()

_context_plant_id = st.session_state.get("pm_context_plant_id")
_default_plant_index = next((i for i, p in enumerate(plants) if p.id == _context_plant_id), 0)


def _machine_model_picker(oem, current_model, key_prefix):
    """Model input for the Add/Edit forms below. Called *before* opening
    the surrounding st.form - widgets inside a form don't trigger a rerun
    until submit, so if OEM lived inside the form, switching it wouldn't
    swap this field until after Save - when OEM is Laader Berg this offers
    a controlled dropdown of the known Maxfoam generations, with a
    free-text fallback for any generation not in that list; every other
    OEM stays plain free text as before."""
    if oem == "Laader Berg":
        default_index = MAXFOAM_MODELS.index(current_model) if current_model in MAXFOAM_MODELS else 0
        choice = st.selectbox("Model", MAXFOAM_MODELS, index=default_index, key=f"{key_prefix}_model_choice")
        if choice == OTHER_LAADER_BERG_MODEL:
            other_default = current_model if current_model and current_model not in MAXFOAM_MODELS else ""
            return st.text_input("Model (specify)", value=other_default, key=f"{key_prefix}_model_other")
        return choice
    return st.text_input("Model", value=current_model or "", key=f"{key_prefix}_model_text")


with st.expander("Add Production Unit / Cell", expanded=False):
    if not page_usable:
        st.caption("View-only access - adding Production Equipment is restricted for your role.")
    else:
        # Plant, Production Method, OEM and Model all live outside the
        # st.form below - each one's choice narrows the next, and widgets
        # inside a form don't rerun until submit, so none of that narrowing
        # could happen live if they lived inside it.
        plant_for_machine = st.selectbox(
            "Plant *", plants, index=_default_plant_index, format_func=lambda p: p.name, key="add_machine_plant"
        )
        plant_methods = activated_methods_for_plant(session, plant_for_machine.id)
        if not plant_methods:
            st.warning(
                "This plant has no activated Production Methods yet. Enable one on the Production "
                "Methods page before adding Production Equipment."
            )
            method_choice = None
        else:
            _context_method_id = (
                st.session_state.get("pm_context_method_id")
                if st.session_state.get("pm_context_plant_id") == plant_for_machine.id
                else None
            )
            method_choice = st.selectbox(
                "Production Method *", plant_methods, format_func=lambda m: m.name,
                index=next((i for i, m in enumerate(plant_methods) if m.id == _context_method_id), 0),
                key="add_machine_method",
            )
        oem = st.selectbox("OEM / manufacturer", MACHINE_OEMS, key="add_machine_oem")
        model = _machine_model_picker(oem, "", "add_machine")
        with st.form("add_machine"):
            name = st.text_input("Production Unit / Cell name * (e.g. Line 1, Maxfoam A)")
            machine_code = st.text_input("Code")
            st.caption(
                f"Plant: **{plant_for_machine.name}** · Production Method: "
                f"**{method_choice.name if method_choice else '—'}** · "
                f"OEM: **{oem}** · Model: **{model or '—'}** (change above, outside this form)"
            )
            active = st.checkbox("Active", value=True)
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Save Production Unit / Cell", disabled=method_choice is None)
            if submitted:
                if not name:
                    st.error("Production Unit / Cell name is required.")
                elif method_choice is None:
                    st.error("Activate a Production Method for this plant first.")
                else:
                    session.add(
                        Machine(
                            plant_id=plant_for_machine.id,
                            name=name,
                            machine_code=machine_code,
                            oem=oem,
                            model=model,
                            active=active,
                            notes=notes,
                            production_method_id=method_choice.id,
                        )
                    )
                    session.commit()
                    st.success(f"Production Unit / Cell '{name}' added.")
                    st.rerun()

st.divider()
st.subheader("Production Units / Cells")
st.caption(
    "Process parameters (conveyor speed, tunnel width, laydown mode, etc.) connect to the "
    "specific equipment that produced them. A production run picks one of these."
)

machines = (
    session.query(Machine)
    .filter(Machine.plant_id.in_([p.id for p in plants]))
    .order_by(Machine.plant_id, Machine.name)
    .all()
)
if not machines:
    st.info("No Production Units/Cells recorded yet.")
else:
    machine_rows = [
        {
            "Plant": m.plant.name,
            "Production Method": m.production_method.name if m.production_method else "—",
            "Production Unit / Cell": m.name,
            "Code": m.machine_code or "—",
            "OEM": m.oem or "—",
            "Model": m.model or "—",
            "Active": m.active,
            "Notes": m.notes or "",
        }
        for m in machines
    ]
    st.caption("Click a row to edit (and optionally delete) that Production Unit / Cell.")
    idx = clickable_table(machine_rows, key="machines_table")
    if idx is not None and idx < len(machines):
        st.session_state["machine_selected_id"] = machines[idx].id
    else:
        st.session_state.pop("machine_selected_id", None)

    selected_machine_id = st.session_state.get("machine_selected_id")
    selected_machine = next((m for m in machines if m.id == selected_machine_id), None)

    if selected_machine:
        st.markdown(f"**Edit Production Unit / Cell: {selected_machine.name}**")
        if not page_usable:
            st.caption("View-only access - editing and deleting is restricted for your role.")
        else:
            # e_oem/e_model live outside the form, same reason as the
            # Add picker above.
            e_plant = st.selectbox(
                "Plant *", plants,
                index=next((i for i, p in enumerate(plants) if p.id == selected_machine.plant_id), 0),
                format_func=lambda p: p.name, key=f"edit_machine_plant_{selected_machine.id}",
            )
            e_plant_methods = activated_methods_for_plant(session, e_plant.id)
            current_method = selected_machine.production_method
            if not e_plant_methods:
                st.warning(
                    "This plant has no activated Production Methods yet. Enable one on the "
                    "Production Methods page."
                )
                e_method_choice = None
            else:
                e_method_choice = st.selectbox(
                    "Production Method *", e_plant_methods, format_func=lambda m: m.name,
                    index=next((i for i, m in enumerate(e_plant_methods) if current_method and m.id == current_method.id), 0),
                    key=f"edit_machine_method_{selected_machine.id}",
                )
            e_oem = st.selectbox(
                "OEM / manufacturer", MACHINE_OEMS,
                index=MACHINE_OEMS.index(selected_machine.oem) if selected_machine.oem in MACHINE_OEMS else 0,
                key=f"edit_machine_oem_{selected_machine.id}",
            )
            e_model = _machine_model_picker(e_oem, selected_machine.model, f"edit_machine_{selected_machine.id}")
            with st.form(f"edit_machine_{selected_machine.id}"):
                e_name = st.text_input(
                    "Production Unit / Cell name *", value=selected_machine.name, key=f"edit_machine_name_{selected_machine.id}"
                )
                e_code = st.text_input(
                    "Code", value=selected_machine.machine_code or "", key=f"edit_machine_code_{selected_machine.id}"
                )
                st.caption(
                    f"Plant: **{e_plant.name}** · Production Method: "
                    f"**{e_method_choice.name if e_method_choice else '—'}** · "
                    f"OEM: **{e_oem}** · Model: **{e_model or '—'}** (change above, outside this form)"
                )
                e_active = st.checkbox("Active", value=selected_machine.active, key=f"edit_machine_active_{selected_machine.id}")
                e_notes = st.text_area("Notes", value=selected_machine.notes or "", key=f"edit_machine_notes_{selected_machine.id}")
                if st.form_submit_button("Save changes", disabled=e_method_choice is None):
                    if not e_name.strip():
                        st.error("Production Unit / Cell name is required.")
                    elif e_method_choice is None:
                        st.error("Activate a Production Method for this plant first.")
                    else:
                        selected_machine.plant_id = e_plant.id
                        selected_machine.name = e_name.strip()
                        selected_machine.machine_code = e_code
                        selected_machine.oem = e_oem
                        selected_machine.model = e_model
                        selected_machine.active = e_active
                        selected_machine.notes = e_notes
                        selected_machine.production_method_id = e_method_choice.id
                        session.commit()
                        st.success("Production Unit / Cell updated.")
                        st.rerun()

            linked_runs = session.query(ProductionRun).filter(ProductionRun.machine_id == selected_machine.id).count()
            if linked_runs:
                warning = (
                    f"{linked_runs} production run(s) reference this Production Unit / Cell. Deleting it will "
                    "unlink them (the runs stay, the equipment reference is cleared), not delete those runs."
                )
            else:
                warning = "No production runs reference this Production Unit / Cell — deleting it is safe."

            def _do_delete_machine(_session=session, _id=selected_machine.id):
                unlink_machine_dependents(_session, _id)
                _session.query(Machine).filter(Machine.id == _id).delete(synchronize_session=False)
                _session.commit()
                st.session_state.pop("machine_selected_id", None)

            delete_with_confirm(
                f"'{selected_machine.name}'", _do_delete_machine, key_prefix=f"machine_{selected_machine.id}",
                extra_warning=warning,
            )

        if st.button("Clear selection", key="clear_machine_selection"):
            st.session_state.pop("machine_selected_id", None)
            st.rerun()
