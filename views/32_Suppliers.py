"""Screen: Suppliers (master data)

CR-13 (Split Suppliers into a Standalone Page), implemented 2026-08-12:
Supplier management used to live as a nested "Suppliers" tab inside
views/14_Raw_Materials.py (its own Create/Edit-Delete/Import sub-tabs,
gated by the SAME `page_usable` boolean as the outer Raw Material group,
since both record types shared the single "raw_materials" page_key).
Suppliers are their own record domain, so CR-13 moves that Create/Edit/
Delete/Import functionality here as an independent, directly-navigable
page with its own "suppliers" access_control page_key, in the same
navigation section ("Formulations") Raw Materials already lives in - per
CR-13 section 7, the broader section-label/grouping decision is deferred
to a later navigation CR and is independent of this split.

What did NOT move: views/14_Raw_Materials.py keeps its own
_supplier_picker/_supplier_names/_ensure_supplier_exists helpers and its
"Default supplier" dropdown on every Raw Material Create/Edit/TDS form -
those read/write the same db.Supplier rows this page manages, by name
(RawMaterial.default_supplier is a text snapshot, not a foreign key), so
every existing Raw Material <-> Supplier relationship keeps resolving
exactly as it did before the split with zero data migration. Renaming a
supplier here (see the Edit form below) still cascades onto every
RawMaterial.default_supplier text value that matched the old name, the
same behavior the nested tab had.
"""

import pandas as pd
import streamlit as st

from access_control import can_use_page
from auth import current_user, logout_button, require_login
from db import RawMaterial, Supplier, get_session, init_db
from helpers import (
    clickable_table,
    cr11_function_tab_labels,
    csv_excel_uploader,
    delete_with_confirm,
    page_setup,
    render_data_table,
    render_function_action_intro,
    set_pending_banner,
    show_pending_banner,
    view_only_notice,
)
from tenant_scope import company_picker

SUPPLIER_REQUIRED_COLUMNS = ["name"]
SUPPLIER_OPTIONAL_COLUMNS = ["notes"]

page_setup("Suppliers")
init_db()
require_login()
logout_button()

st.title("Suppliers")
render_function_action_intro(
    function_text=(
        "Maintains the master list of suppliers offered in the 'Default supplier' dropdown on the "
        "Raw Materials page. Keeping this list curated avoids near-duplicate entries (e.g. 'Jiahua' "
        "vs a mistyped 'Yiahua') across raw materials, and every existing Raw Material's supplier "
        "link keeps working from here exactly as it did when this was a tab on Raw Materials."
    ),
    action_text=(
        "Add a supplier manually, or use CSV/Excel import to bulk-load a supplier list from an ERP "
        "or purchasing export. Renaming a supplier here updates every Raw Material that currently "
        "lists it as the default supplier."
    ),
)
session = get_session()
user = current_user()
is_platform_owner = user["is_platform_owner"]
own_company_id = user["company_id"]
page_usable = can_use_page("suppliers", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()

company_filter, all_companies = company_picker(
    st, session, is_platform_owner, own_company_id, key="supplier_company_filter"
)
if not is_platform_owner and not company_filter:
    st.warning("Your account isn't linked to a company yet - contact the platform administrator.")
    st.stop()


def _target_company(key):
    """Company a new supplier should be created under. Locked to the
    user's own company for non-platform-owners; for the platform owner,
    uses the current company filter if one is picked, otherwise asks
    which company this new record belongs to (required when viewing 'All
    companies') - identical logic to Raw Materials' own _target_company,
    duplicated here rather than shared since the two pages have no other
    coupling left after the split."""
    if not is_platform_owner:
        return company_filter
    if company_filter is not None:
        return company_filter
    return st.selectbox("Company *", all_companies, format_func=lambda c: c.name, key=key)


tab_create, tab_edit_delete, tab_import = st.tabs(cr11_function_tab_labels("Supplier"))

with tab_create:
    if not page_usable:
        st.caption("View-only access - adding a supplier is restricted for your role.")
    else:
        supplier_target_company = _target_company("add_supplier_company")
        with st.form("add_supplier"):
            new_supplier_name = st.text_input("Supplier name *")
            new_supplier_notes = st.text_area("Notes", help="Optional - e.g. the actual distributor purchases go through.")
            if st.form_submit_button("Add supplier"):
                if not new_supplier_name.strip():
                    st.error("Supplier name is required.")
                elif not supplier_target_company:
                    st.error("Pick a company for this supplier.")
                elif (
                    session.query(Supplier)
                    .filter(Supplier.name == new_supplier_name.strip(), Supplier.company_id == supplier_target_company.id)
                    .first()
                ):
                    st.error(f"'{new_supplier_name.strip()}' is already in the list.")
                else:
                    session.add(
                        Supplier(
                            company_id=supplier_target_company.id,
                            name=new_supplier_name.strip(),
                            notes=new_supplier_notes,
                        )
                    )
                    session.commit()
                    st.success(f"Supplier '{new_supplier_name}' added.")
                    st.rerun()

with tab_edit_delete:
    st.divider()
    suppliers_query = session.query(Supplier)
    if company_filter is not None:
        suppliers_query = suppliers_query.filter(Supplier.company_id == company_filter.id)
    suppliers = suppliers_query.order_by(Supplier.name).all()
    if not suppliers:
        st.info("No suppliers recorded yet.")
    else:
        supplier_df = pd.DataFrame(
            [
                {
                    **({"Company": s.company.name if s.company else "—"} if is_platform_owner else {}),
                    "Name": s.name,
                    "Notes": s.notes or "",
                    "Active": s.active,
                }
                for s in suppliers
            ]
        )
        st.caption(f"{len(suppliers)} supplier(s). Click a row to edit or delete.")
        sidx = clickable_table(supplier_df.to_dict("records"), key="supplier_table")
        if sidx is not None and sidx < len(suppliers):
            st.session_state["supplier_selected_id"] = suppliers[sidx].id
        else:
            st.session_state.pop("supplier_selected_id", None)

        sel_supplier_id = st.session_state.get("supplier_selected_id")
        sel_supplier = next((s for s in suppliers if s.id == sel_supplier_id), None)

        if sel_supplier:
            st.subheader(f"Edit: {sel_supplier.name}")
            if not page_usable:
                st.caption("View-only access - editing and deleting is restricted for your role.")
            else:
                with st.form(f"edit_supplier_{sel_supplier.id}"):
                    if is_platform_owner:
                        es_company = st.selectbox(
                            "Company *", all_companies,
                            index=next((i for i, c in enumerate(all_companies) if c.id == sel_supplier.company_id), 0),
                            format_func=lambda c: c.name, key=f"edit_supplier_company_{sel_supplier.id}",
                        )
                    else:
                        es_company = company_filter
                    es_name = st.text_input("Supplier name *", value=sel_supplier.name, key=f"edit_supplier_name_{sel_supplier.id}")
                    es_notes = st.text_area("Notes", value=sel_supplier.notes or "", key=f"edit_supplier_notes_{sel_supplier.id}")
                    es_active = st.checkbox("Active", value=sel_supplier.active, key=f"edit_supplier_active_{sel_supplier.id}")
                    if st.form_submit_button("Save changes"):
                        if not es_name.strip():
                            st.error("Supplier name is required.")
                        else:
                            old_name = sel_supplier.name
                            old_company_id = sel_supplier.company_id
                            sel_supplier.company_id = es_company.id if es_company else sel_supplier.company_id
                            sel_supplier.name = es_name.strip()
                            sel_supplier.notes = es_notes
                            sel_supplier.active = es_active
                            if old_name != sel_supplier.name:
                                # Keep existing raw materials (same company) pointed
                                # at this supplier consistent with the rename, since
                                # default_supplier is a text snapshot, not an FK -
                                # identical cross-page consistency behavior the
                                # nested tab had before the CR-13 split.
                                session.query(RawMaterial).filter(
                                    RawMaterial.default_supplier == old_name,
                                    RawMaterial.company_id == old_company_id,
                                ).update({"default_supplier": sel_supplier.name}, synchronize_session="fetch")
                            session.commit()
                            st.success("Supplier updated.")
                            st.rerun()

                linked_rawmats = (
                    session.query(RawMaterial)
                    .filter(
                        RawMaterial.default_supplier == sel_supplier.name,
                        RawMaterial.company_id == sel_supplier.company_id,
                    )
                    .count()
                )
                if linked_rawmats:
                    warning = (
                        f"{linked_rawmats} raw material(s) currently list this as their default supplier. "
                        "Deleting it only removes it from the dropdown - those raw materials keep the supplier "
                        "name as free text."
                    )
                else:
                    warning = "No raw materials currently use this supplier - deleting it is safe."

                def _do_delete_supplier(_session=session, _id=sel_supplier.id):
                    _session.query(Supplier).filter(Supplier.id == _id).delete(synchronize_session=False)
                    _session.commit()
                    st.session_state.pop("supplier_selected_id", None)

                delete_with_confirm(
                    sel_supplier.name, _do_delete_supplier, key_prefix=f"supplier_{sel_supplier.id}", extra_warning=warning
                )

            if st.button("Clear selection", key="clear_supplier_selection"):
                st.session_state.pop("supplier_selected_id", None)
                st.rerun()

with tab_import:
    if not page_usable:
        st.caption("View-only access - importing suppliers is restricted for your role.")
    else:
        import_supplier_company = _target_company("import_supplier_company")
        show_pending_banner("supplier_import_msg")
        sdf, sfilename = csv_excel_uploader(SUPPLIER_REQUIRED_COLUMNS, SUPPLIER_OPTIONAL_COLUMNS, key="supplier_upload")
        if sdf is not None and not import_supplier_company:
            st.error("Pick a company above before importing.")
        elif sdf is not None:
            existing_supplier_query = session.query(Supplier).filter(Supplier.company_id == import_supplier_company.id)
            existing_supplier_names = {s.name.strip().lower() for s in existing_supplier_query.all()}
            new_supplier_rows, dup_supplier_rows = [], []
            for _, srow in sdf.iterrows():
                sname_val = str(srow.get("name", "") or "").strip()
                if not sname_val:
                    continue
                if sname_val.lower() in existing_supplier_names:
                    dup_supplier_rows.append(srow)
                    continue
                new_supplier_rows.append(srow)
                existing_supplier_names.add(sname_val.lower())

            st.write(
                f"Rows ready to import: **{len(new_supplier_rows)}** | "
                f"Rows flagged as duplicates: **{len(dup_supplier_rows)}**"
            )
            if dup_supplier_rows:
                st.warning("These rows match a supplier name already in the list and were skipped.")
                render_data_table(pd.DataFrame(dup_supplier_rows), max_height="400px")

            if new_supplier_rows and st.button("Confirm import", key="confirm_supplier_import"):
                for srow in new_supplier_rows:
                    session.add(
                        Supplier(
                            company_id=import_supplier_company.id,
                            name=str(srow["name"]).strip(),
                            notes=str(srow.get("notes", "") or ""),
                        )
                    )
                session.commit()
                set_pending_banner(
                    "supplier_import_msg", f"Imported {len(new_supplier_rows)} supplier(s) from {sfilename}."
                )
                st.rerun()
