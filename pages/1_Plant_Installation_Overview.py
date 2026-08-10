"""Screen 2: Plants

CR-01 (UI Navigation and Rigid-Foam Terminology for UAT), implemented
2026-08-10: this page used to be "Plant & Foam Equipment Overview" and
carried both Plant CRUD and Machine/foaming-line CRUD in one script. Per
CR-01's approved sidebar structure, Plant stays a pure location/identity
concept under its own "Plant Setup" section (this page, retitled "Plants"),
while equipment now resolves inside the selected Production Method's own
context - moved to the new "Production Methods" section as
pages/31_Production_Equipment.py. Production Method activation for a plant
(the checkbox list that used to live here) moved to the new
pages/30_Production_Methods.py for the same reason: it's a Production
Method concern, not a Plant-identity one, and the new page is where a user
now goes to manage/select a plant's active methods.

page_key stays "plant_overview" (unchanged) - no permission-matrix migration
needed for this rename; RolePagePermission rows keyed to the old key remain
valid for the same page under its new title.
"""

import streamlit as st

from access_control import can_use_page
from auth import current_user, logout_button, require_login
from cascades import delete_plant_cascade, plant_dependency_counts, unlink_machine_dependents
from db import Company, Machine, Plant, get_session, init_db
from helpers import (
    clickable_table,
    delete_with_confirm,
    page_setup,
    render_function_action_intro,
    view_only_notice,
)
from tenant_scope import clear_scope_cache, company_picker

page_setup("Plants")
init_db()
require_login()
logout_button()

st.title("Plants")
render_function_action_intro(
    function_text=(
        "This is where you set up and maintain the plants that every Production Method, product "
        "family, recipe, production run, and quality result in the system is ultimately traced "
        "back to. It records each plant's name, code, and location, and shows at a glance how many "
        "product families and Production Units/Cells sit under each plant. Activating Production "
        "Methods for a plant and setting up its Production Equipment now live on the Production "
        "Methods and Production Equipment pages (Production Methods section) - this page is "
        "location/identity only."
    ),
    action_text=(
        "Add a plant before adding anything else under it, since Production Methods, product "
        "families, recipes, and production runs all key off it eventually. Once a plant exists, go "
        "to Production Methods to activate the methods it runs, then Production Equipment to add "
        "its Production Units/Cells. Click a row in the table below to edit or delete a plant - "
        "deleting one permanently removes everything recorded under it (the count is shown before "
        "you confirm)."
    ),
)
session = get_session()
user = current_user()
is_platform_owner = user["is_platform_owner"]
own_company_id = user["company_id"]
page_usable = can_use_page("plant_overview", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()

company_filter, all_companies = company_picker(
    st, session, is_platform_owner, own_company_id, key="plant_company_filter"
)
if not is_platform_owner and not company_filter:
    st.warning("Your account isn't linked to a company yet - contact the platform administrator.")
    st.stop()

subscription = company_filter.subscription_type if company_filter else None
max_plants = subscription.max_plants if subscription else None
plant_count_for_company = (
    session.query(Plant).filter(Plant.company_id == company_filter.id).count() if company_filter else None
)
limit_reached = (
    company_filter is not None and max_plants is not None and plant_count_for_company >= max_plants
)

with st.expander("Add plant", expanded=False):
    if not page_usable:
        st.caption("View-only access - adding a plant is restricted for your role.")
    else:
        if limit_reached:
            st.warning(
                f"{company_filter.name} is at its subscription's plant limit ({max_plants} plants). "
                "Upgrade the subscription or remove an unused plant before adding another."
            )
        with st.form("add_plant"):
            if is_platform_owner:
                plant_company = st.selectbox(
                    "Company *", all_companies, format_func=lambda c: c.name,
                    index=(all_companies.index(company_filter) if company_filter in all_companies else 0),
                )
            else:
                plant_company = company_filter
                st.caption(f"Company: {plant_company.name if plant_company else '—'}")
            name = st.text_input("Plant name *")
            plant_code = st.text_input("Plant code")
            location = st.text_input("Location")
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Save plant", disabled=limit_reached and not is_platform_owner)
            if submitted:
                if not name:
                    st.error("Plant name is required.")
                elif not plant_company:
                    st.error("A company is required.")
                else:
                    session.add(
                        Plant(
                            company_id=plant_company.id,
                            name=name,
                            plant_code=plant_code,
                            location=location,
                            notes=notes,
                        )
                    )
                    session.commit()
                    clear_scope_cache()
                    st.success(f"Plant '{name}' added.")
                    st.rerun()

st.divider()
st.subheader("Plants")

plants_query = session.query(Plant)
if company_filter is not None:
    plants_query = plants_query.filter(Plant.company_id == company_filter.id)
plants = plants_query.all()
if not plants:
    st.info("No plants recorded yet.")
else:
    plant_rows = [
        {
            **({"Company": plant.company.name if plant.company else "—"} if is_platform_owner else {}),
            "Name": plant.name,
            "Code": plant.plant_code or "—",
            "Location": plant.location or "—",
            "Product families": len(plant.product_families),
            "Production Units/Cells": session.query(Machine).filter(Machine.plant_id == plant.id).count(),
            "Notes": plant.notes or "",
        }
        for plant in plants
    ]
    st.caption("Click a row to edit (and optionally delete) that plant.")
    idx = clickable_table(plant_rows, key="plants_table")
    if idx is not None and idx < len(plants):
        st.session_state["plant_selected_id"] = plants[idx].id
    else:
        st.session_state.pop("plant_selected_id", None)

    selected_plant_id = st.session_state.get("plant_selected_id")
    selected_plant = next((p for p in plants if p.id == selected_plant_id), None)

    if selected_plant:
        st.markdown(f"**Edit plant: {selected_plant.name}**")
        if not page_usable:
            st.caption("View-only access - editing and deleting is restricted for your role.")
        else:
            with st.form(f"edit_plant_{selected_plant.id}"):
                if is_platform_owner:
                    e_company = st.selectbox(
                        "Company *", all_companies,
                        index=next((i for i, c in enumerate(all_companies) if c.id == selected_plant.company_id), 0),
                        format_func=lambda c: c.name, key=f"edit_plant_company_{selected_plant.id}",
                    )
                else:
                    e_company = company_filter
                e_name = st.text_input("Plant name *", value=selected_plant.name, key=f"edit_plant_name_{selected_plant.id}")
                e_code = st.text_input("Plant code", value=selected_plant.plant_code or "", key=f"edit_plant_code_{selected_plant.id}")
                e_location = st.text_input("Location", value=selected_plant.location or "", key=f"edit_plant_loc_{selected_plant.id}")
                e_notes = st.text_area("Notes", value=selected_plant.notes or "", key=f"edit_plant_notes_{selected_plant.id}")
                if st.form_submit_button("Save changes"):
                    if not e_name.strip():
                        st.error("Plant name is required.")
                    else:
                        selected_plant.company_id = e_company.id if e_company else selected_plant.company_id
                        selected_plant.name = e_name.strip()
                        selected_plant.plant_code = e_code
                        selected_plant.location = e_location
                        selected_plant.notes = e_notes
                        session.commit()
                        st.success("Plant updated.")
                        st.rerun()

            st.caption(
                "Manage this plant's activated Production Methods on the **Production Methods** "
                "page, and its Production Units/Cells on the **Production Equipment** page "
                "(both under the Production Methods nav section)."
            )

            counts = plant_dependency_counts(session, selected_plant.id)
            total_related = sum(counts.values())
            if total_related:
                detail = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
                warning = f"Deleting this plant will also permanently delete {total_related} related record(s): {detail}."
            else:
                warning = "This plant has no related records — deleting it is safe."

            def _do_delete_plant(_session=session, _id=selected_plant.id):
                delete_plant_cascade(_session, _id)
                _session.commit()
                clear_scope_cache()
                st.session_state.pop("plant_selected_id", None)

            delete_with_confirm(
                f"'{selected_plant.name}'", _do_delete_plant, key_prefix=f"plant_{selected_plant.id}",
                extra_warning=warning,
            )

        if st.button("Clear selection", key="clear_plant_selection"):
            st.session_state.pop("plant_selected_id", None)
            st.rerun()
