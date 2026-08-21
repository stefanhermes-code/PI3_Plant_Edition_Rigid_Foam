"""Screen 3a: PU Material Family Profile

CR-10 (Split Product Families and Product Grades into Separate Pages,
Charlie's instruction, 2026-08-12): this page is the PU Material Families half
of what used to be one combined page (views/2_Product_Family_Foam_Grade.py,
"PU Material Families & Product Grades", two tabs). Charlie's CR gives each
data domain its own direct sidebar entry and removes the extra in-page tab
click - see views/2_Product_Grades.py for the other half.

Every PU Material Family read/write/cascade-delete behavior below is carried
over unchanged from the old combined page's "Product families" tab - this
split is presentation/navigation only (CR-10 section 6, "Functional
Preservation"). The PU Material Family -> Product Grade relationship itself
lives entirely in the data model (FoamGrade.pu_material_family_id) and was
never inside the old page's tab structure, so nothing about that
relationship needed to change to split the UI in two.

Context handoff to Product Grades (CR-10 acceptance criteria 10/11): the
"Open this family's Product Grades" button below stashes the selected
family's id in st.session_state["pfg_family_context_id"] and switches page.
views/2_Product_Grades.py pops that key on its next run and uses it to
seed its own family-filter selectbox's initial value - a one-time
inheritance, not a permanent link, so the user lands straight on the right
family's grades without repeating the selection, but can still change the
filter (or come back to "All PU Material Families") from there exactly like a
direct visit would allow.

access_control page_key: this page is new plumbing over an existing
CRUD surface, but CR-10 splits ONE page into TWO independent ones, so a
single shared key could no longer describe "can this role see/use this
screen" correctly for both. A fresh key ("pu_material_families") is used
here; see views/2_Product_Grades.py for its own new key
("product_grades"). The old combined key ("product_family_foam_grade") is
retired from access_control.PAGE_CATALOG entirely (2026-08-12 live-data
check found zero role_page_permissions rows referencing it, so - same as
CR-03's removal of "reference_formulations" - no migration was needed;
every role defaults to full access on both new keys until explicitly
restricted, same as it would have on the old combined one)."""

import pandas as pd
import streamlit as st

from access_control import can_use_page
from auth import current_user, logout_button, require_login
from cascades import delete_pu_material_family_cascade, pu_material_family_dependency_counts
from db import Plant, PUMaterialFamily, get_session, init_db
from helpers import (
    clickable_table,
    cr11_function_tab_labels,
    csv_excel_uploader,
    dedupe_import_rows,
    delete_with_confirm,
    page_setup,
    render_data_table,
    render_function_action_intro,
    set_pending_banner,
    show_pending_banner,
    view_only_notice,
)
from tenant_scope import apply_scope, clear_scope_cache, company_picker, plant_ids_for_company
from helpers import PU_MATERIAL_FAMILIES

FAMILY_REQUIRED_COLUMNS = ["plant_id", "name"]
# R1 (2026-08-21): "application" moved to the controlled Application Area
# master in R2 and "customer_segment" moved down to Product Grade, so neither
# is a column of this record any more. "name" is now a controlled value - the
# import still takes it as text and the database CHECK refuses anything
# outside the seven.
FAMILY_OPTIONAL_COLUMNS = ["description"]

page_setup("PU Material Families")
init_db()
require_login()
logout_button()

st.title("PU Material Families")
render_function_action_intro(
    function_text=(
        "A PU Material Family groups your product grades by market segment or application under a "
        "plant (e.g. cold-room panel core, pipe insulation). It's the top level of your product "
        "catalog - every product grade belongs to exactly one family, and every recipe version, "
        "production run, and quality result recorded downstream traces back to one of those grades."
    ),
    action_text=(
        "Add a PU Material Family under the right plant, then continue straight to that family's "
        "product grades using the button on its edit panel below - or open the Product Grades "
        "page directly if you'd rather add grades under a different family or see every grade at "
        "once. Use CSV/Excel import to bulk-load families (referencing an existing plant_id) from "
        "a spreadsheet. Click a row in the Edit/Delete tab's table to edit or delete that product "
        "family - deleting one cascades to every product grade recorded under it, with the count "
        "shown before you confirm."
    ),
)
session = get_session()
user = current_user()
page_usable = can_use_page("pu_material_families", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()
company, _all_companies = company_picker(
    st, session, user["is_platform_owner"], user["company_id"], key="pf_company_filter"
)
company_id = company.id if company else None
plant_ids = plant_ids_for_company(session, company_id)

plants = apply_scope(session.query(Plant), Plant.id, plant_ids).all()
if not plants:
    st.warning("Add a plant first (Plants page) before creating PU Material Families.")
    st.stop()

tab_create, tab_edit_delete, tab_import = st.tabs(cr11_function_tab_labels("PU Material Family", "PU Material Families"))

with tab_create:
    if not page_usable:
        st.caption("View-only access - adding a PU Material Family is restricted for your role.")
    else:
        with st.form("add_family"):
            plant = st.selectbox("Plant *", plants, format_func=lambda p: p.name)
            # R1-WP2: the seven controlled values. Typed names are how this
            # record ended up holding an application, a market and a chemistry
            # in three rows - see the R1 migration for what had to be undone.
            name = st.selectbox("PU Material Family *", PU_MATERIAL_FAMILIES)
            description = st.text_area("Description")
            submitted = st.form_submit_button("Save PU Material Family")
            if submitted:
                if not name:
                    st.error("PU Material Family is required.")
                else:
                    session.add(
                        PUMaterialFamily(
                            plant_id=plant.id,
                            name=name,
                            description=description,
                        )
                    )
                    session.commit()
                    clear_scope_cache()
                    st.success(f"PU Material Family '{name}' added.")
                    st.rerun()

with tab_import:
    if not page_usable:
        st.caption("View-only access - importing PU Material Families is restricted for your role.")
    else:
        show_pending_banner("family_import_msg")
        fdf, ffilename = csv_excel_uploader(FAMILY_REQUIRED_COLUMNS, FAMILY_OPTIONAL_COLUMNS, key="family_upload")
        if fdf is not None:
            valid_plant_ids = {p.id for p in plants}
            good_rows, bad_rows = [], []
            for _, row in fdf.iterrows():
                if row.get("plant_id") in valid_plant_ids and str(row.get("name", "")).strip():
                    good_rows.append(row)
                else:
                    bad_rows.append(row)

            st.write(f"Rows ready to import: **{len(good_rows)}** | Rows flagged/rejected: **{len(bad_rows)}**")
            if bad_rows:
                st.warning("Flagged rows reference an unknown plant_id or have no name.")
                render_data_table(pd.DataFrame(bad_rows), max_height="300px")

            if good_rows and st.button("Confirm import", key="confirm_family_import"):
                existing_keys = {
                    (f.plant_id, f.name.strip().lower())
                    for f in apply_scope(session.query(PUMaterialFamily), PUMaterialFamily.plant_id, plant_ids).all()
                }
                new_rows, dup_rows = dedupe_import_rows(
                    good_rows,
                    existing_keys,
                    key_func=lambda row: (int(row["plant_id"]), str(row["name"]).strip().lower()),
                )
                for row in new_rows:
                    session.add(
                        PUMaterialFamily(
                            plant_id=int(row["plant_id"]),
                            name=str(row["name"]).strip(),
                            description=str(row.get("description", "") or ""),
                        )
                    )
                session.commit()
                clear_scope_cache()
                msg = f"Imported {len(new_rows)} PU Material Family/families from {ffilename}."
                if dup_rows:
                    msg += f" Skipped {len(dup_rows)} row(s) already recorded for their plant (likely a repeat click)."
                set_pending_banner("family_import_msg", msg)
                st.rerun()

with tab_edit_delete:
    st.divider()
    families = apply_scope(session.query(PUMaterialFamily), PUMaterialFamily.plant_id, plant_ids).all()
    if not families:
        st.info("No PU Material Families recorded yet.")
    else:
        family_rows = [
            {
                "Name": fam.name,
                "Plant": fam.plant.name,
                "Product grades": len(fam.foam_grades),
            }
            for fam in families
        ]
        st.caption("Click a row to edit (and optionally delete) that PU Material Family.")
        idx = clickable_table(family_rows, key="families_table")
        if idx is not None and idx < len(families):
            st.session_state["family_selected_id"] = families[idx].id
        else:
            st.session_state.pop("family_selected_id", None)

        selected_family_id = st.session_state.get("family_selected_id")
        selected_family = next((f for f in families if f.id == selected_family_id), None)

        if selected_family:
            st.markdown(f"**Edit PU Material Family: {selected_family.name}**")

            # CR-10 acceptance criteria 10/11: hand this family's context to the
            # Product Grades page rather than making the user re-pick it there.
            # Not gated behind page_usable - opening a filtered view of Product
            # Grades isn't a write action, so a view-only role should get it too.
            if st.button(
                f"Open Product Grades for '{selected_family.name}' →",
                key=f"family_to_grades_{selected_family.id}",
            ):
                st.session_state["pfg_family_context_id"] = selected_family.id
                st.switch_page("views/2_Product_Grades.py")

            if not page_usable:
                st.caption("View-only access - editing and deleting is restricted for your role.")
            else:
                with st.form(f"edit_family_{selected_family.id}"):
                    e_plant = st.selectbox(
                        "Plant *", plants,
                        index=next((i for i, p in enumerate(plants) if p.id == selected_family.plant_id), 0),
                        format_func=lambda p: p.name, key=f"edit_family_plant_{selected_family.id}",
                    )
                    # An unrecognised stored value stays selectable rather than
                    # being silently reset - the same historical-readability
                    # rule the rest of the app follows. The database CHECK
                    # means one should not exist, but a picker that quietly
                    # rewrites data it does not recognise is worse than one
                    # that shows it.
                    _family_options = list(PU_MATERIAL_FAMILIES)
                    if selected_family.name and selected_family.name not in _family_options:
                        _family_options.append(selected_family.name)
                    e_name = st.selectbox(
                        "PU Material Family *", _family_options,
                        index=_family_options.index(selected_family.name) if selected_family.name in _family_options else 0,
                        key=f"edit_family_name_{selected_family.id}",
                    )
                    e_description = st.text_area(
                        "Description", value=selected_family.description or "", key=f"edit_family_desc_{selected_family.id}"
                    )
                    if st.form_submit_button("Save changes"):
                        if not e_name.strip():
                            st.error("PU Material Family is required.")
                        else:
                            selected_family.plant_id = e_plant.id
                            selected_family.name = e_name.strip()
                            selected_family.description = e_description
                            session.commit()
                            st.success("PU Material Family updated.")
                            st.rerun()

                counts = pu_material_family_dependency_counts(session, selected_family.id)
                total_related = sum(counts.values())
                if total_related:
                    detail = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
                    warning = f"Deleting this PU Material Family will also permanently delete {total_related} related record(s): {detail}."
                else:
                    warning = "This PU Material Family has no related records — deleting it is safe."

                def _do_delete_family(_session=session, _id=selected_family.id):
                    delete_pu_material_family_cascade(_session, _id)
                    _session.commit()
                    clear_scope_cache()
                    st.session_state.pop("family_selected_id", None)

                delete_with_confirm(
                    f"'{selected_family.name}'", _do_delete_family, key_prefix=f"family_{selected_family.id}",
                    extra_warning=warning,
                )

            if st.button("Clear selection", key="clear_family_selection"):
                st.session_state.pop("family_selected_id", None)
                st.rerun()
