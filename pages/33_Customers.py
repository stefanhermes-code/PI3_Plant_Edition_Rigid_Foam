"""Screen: Customers (master data)

CR-14 (Create Customers Section and Lightweight Customer Master,
implemented 2026-08-12): a dedicated, standalone Customers page - a new
nav section ("Customers") together with Customer Trials & Samples, which
moves into it from the old "Samples & Trials" section (see
app_rigid_foam.py). This page is deliberately lightweight per CR-14
section 3 - "a practical application reference rather than a full CRM":
Company Name, Contact Person, Contact Email, and an optional free-text
Customer Type. Advanced CRM functions (multiple contacts, sales pipeline,
commercial history, customer-category governance) are explicitly out of
scope (CR-14 section 6).

Customer Trials & Samples (pages/11_Customer_Trials.py) now sources its
customer selection from this master via CustomerTrial.customer_id - see
that page's own module docstring, and cascades.backfill_trial_customers()
for how pre-CR-14 customer_name text values are mapped onto Customer
records without ever silently merging two different-looking names into
one (CR-14 section 5).
"""

import pandas as pd
import streamlit as st

from access_control import can_use_page
from auth import current_user, logout_button, require_login
from db import Customer, CustomerTrial, get_session, init_db
from helpers import (
    clickable_table,
    cr11_function_tab_labels,
    csv_excel_uploader,
    delete_with_confirm,
    is_valid_email,
    page_setup,
    render_data_table,
    render_function_action_intro,
    set_pending_banner,
    show_pending_banner,
    view_only_notice,
)
from tenant_scope import company_picker

CUSTOMER_REQUIRED_COLUMNS = ["company_name"]
CUSTOMER_OPTIONAL_COLUMNS = ["contact_person", "contact_email", "customer_type"]

page_setup("Customers")
init_db()
require_login()
logout_button()

st.title("Customers")
render_function_action_intro(
    function_text=(
        "Maintains a lightweight master list of customers - Company Name, Contact Person, Contact "
        "Email, and an optional Customer Type - so customer identity has a single, direct home instead "
        "of living only as free text on Customer Trials & Samples. This is a practical reference, not a "
        "full CRM: no sales pipeline, multiple contacts, or commercial history."
    ),
    action_text=(
        "Add a customer manually, or use CSV/Excel import to bulk-load a customer list. Customer Trials "
        "& Samples, below in this section, picks its customer from this list."
    ),
)
session = get_session()
user = current_user()
is_platform_owner = user["is_platform_owner"]
own_company_id = user["company_id"]
page_usable = can_use_page("customers", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()

company_filter, all_companies = company_picker(
    st, session, is_platform_owner, own_company_id, key="customer_company_filter"
)
if not is_platform_owner and not company_filter:
    st.warning("Your account isn't linked to a company yet - contact the platform administrator.")
    st.stop()


def _target_company(key):
    """Identical logic to Suppliers' and Raw Materials' own _target_company
    - company a new customer should be created under. Duplicated rather
    than shared since these pages have no other coupling."""
    if not is_platform_owner:
        return company_filter
    if company_filter is not None:
        return company_filter
    return st.selectbox("Company *", all_companies, format_func=lambda c: c.name, key=key)


tab_create, tab_edit_delete, tab_import = st.tabs(cr11_function_tab_labels("Customer"))

with tab_create:
    if not page_usable:
        st.caption("View-only access - adding a customer is restricted for your role.")
    else:
        customer_target_company = _target_company("add_customer_company")
        with st.form("add_customer"):
            new_company_name = st.text_input("Company Name *")
            new_contact_person = st.text_input("Contact Person")
            new_contact_email = st.text_input("Contact Email")
            new_customer_type = st.text_input(
                "Customer Type", help="Optional free text - no fixed category list yet."
            )
            if st.form_submit_button("Add customer"):
                if not new_company_name.strip():
                    st.error("Company Name is required.")
                elif not customer_target_company:
                    st.error("Pick a company for this customer.")
                elif not is_valid_email(new_contact_email):
                    st.error("Contact Email doesn't look like a valid email address.")
                elif (
                    session.query(Customer)
                    .filter(
                        Customer.company_name == new_company_name.strip(),
                        Customer.company_id == customer_target_company.id,
                    )
                    .first()
                ):
                    st.error(f"'{new_company_name.strip()}' is already in the list.")
                else:
                    session.add(
                        Customer(
                            company_id=customer_target_company.id,
                            company_name=new_company_name.strip(),
                            contact_person=new_contact_person,
                            contact_email=new_contact_email,
                            customer_type=new_customer_type,
                        )
                    )
                    session.commit()
                    st.success(f"Customer '{new_company_name}' added.")
                    st.rerun()

with tab_edit_delete:
    st.divider()
    customers_query = session.query(Customer)
    if company_filter is not None:
        customers_query = customers_query.filter(Customer.company_id == company_filter.id)
    customers = customers_query.order_by(Customer.company_name).all()
    if not customers:
        st.info("No customers recorded yet.")
    else:
        customer_df = pd.DataFrame(
            [
                {
                    **({"Company": c.company.name if c.company else "—"} if is_platform_owner else {}),
                    "Company Name": c.company_name,
                    "Contact Person": c.contact_person or "",
                    "Contact Email": c.contact_email or "",
                    "Customer Type": c.customer_type or "",
                }
                for c in customers
            ]
        )
        st.caption(f"{len(customers)} customer(s). Click a row to edit or delete.")
        cidx = clickable_table(customer_df.to_dict("records"), key="customer_table")
        if cidx is not None and cidx < len(customers):
            st.session_state["customer_selected_id"] = customers[cidx].id
        else:
            st.session_state.pop("customer_selected_id", None)

        sel_customer_id = st.session_state.get("customer_selected_id")
        sel_customer = next((c for c in customers if c.id == sel_customer_id), None)

        if sel_customer:
            st.subheader(f"Edit: {sel_customer.company_name}")
            if not page_usable:
                st.caption("View-only access - editing and deleting is restricted for your role.")
            else:
                with st.form(f"edit_customer_{sel_customer.id}"):
                    if is_platform_owner:
                        ec_company = st.selectbox(
                            "Company *", all_companies,
                            index=next((i for i, c in enumerate(all_companies) if c.id == sel_customer.company_id), 0),
                            format_func=lambda c: c.name, key=f"edit_customer_company_{sel_customer.id}",
                        )
                    else:
                        ec_company = company_filter
                    ec_company_name = st.text_input(
                        "Company Name *", value=sel_customer.company_name, key=f"edit_customer_name_{sel_customer.id}"
                    )
                    ec_contact_person = st.text_input(
                        "Contact Person", value=sel_customer.contact_person or "",
                        key=f"edit_customer_contact_{sel_customer.id}",
                    )
                    ec_contact_email = st.text_input(
                        "Contact Email", value=sel_customer.contact_email or "",
                        key=f"edit_customer_email_{sel_customer.id}",
                    )
                    ec_customer_type = st.text_input(
                        "Customer Type", value=sel_customer.customer_type or "",
                        key=f"edit_customer_type_{sel_customer.id}",
                    )
                    if st.form_submit_button("Save changes"):
                        if not ec_company_name.strip():
                            st.error("Company Name is required.")
                        elif not is_valid_email(ec_contact_email):
                            st.error("Contact Email doesn't look like a valid email address.")
                        else:
                            old_company_name = sel_customer.company_name
                            sel_customer.company_id = ec_company.id if ec_company else sel_customer.company_id
                            sel_customer.company_name = ec_company_name.strip()
                            sel_customer.contact_person = ec_contact_person
                            sel_customer.contact_email = ec_contact_email
                            sel_customer.customer_type = ec_customer_type
                            if old_company_name != sel_customer.company_name:
                                # Keep every linked Customer Trial's own display
                                # snapshot (customer_name) consistent with the
                                # rename - customer_id is the live link, but
                                # customer_name is still what reports.py and
                                # pages 5/6 read for display (see db.py's
                                # CustomerTrial docstring).
                                session.query(CustomerTrial).filter(
                                    CustomerTrial.customer_id == sel_customer.id
                                ).update({"customer_name": sel_customer.company_name}, synchronize_session="fetch")
                            session.commit()
                            st.success("Customer updated.")
                            st.rerun()

                linked_trials = (
                    session.query(CustomerTrial).filter(CustomerTrial.customer_id == sel_customer.id).count()
                )
                if linked_trials:
                    warning = (
                        f"{linked_trials} customer trial(s) currently link to this customer. Deleting it only "
                        "removes the master record - those trials keep their customer name as free text and are "
                        "not deleted."
                    )
                else:
                    warning = "No customer trials currently link to this customer - deleting it is safe."

                def _do_delete_customer(_session=session, _id=sel_customer.id):
                    # customer_id is a real FK (unlike RawMaterial.default_
                    # supplier's plain text) - null it out on every linked
                    # trial FIRST so the delete itself never violates that
                    # foreign key, and the trial's own customer_name text
                    # snapshot (already synced above) is all that remains.
                    _session.query(CustomerTrial).filter(CustomerTrial.customer_id == _id).update(
                        {"customer_id": None}, synchronize_session="fetch"
                    )
                    _session.query(Customer).filter(Customer.id == _id).delete(synchronize_session=False)
                    _session.commit()
                    st.session_state.pop("customer_selected_id", None)

                delete_with_confirm(
                    sel_customer.company_name, _do_delete_customer, key_prefix=f"customer_{sel_customer.id}",
                    extra_warning=warning,
                )

            if st.button("Clear selection", key="clear_customer_selection"):
                st.session_state.pop("customer_selected_id", None)
                st.rerun()

with tab_import:
    if not page_usable:
        st.caption("View-only access - importing customers is restricted for your role.")
    else:
        import_customer_company = _target_company("import_customer_company")
        show_pending_banner("customer_import_msg")
        cdf, cfilename = csv_excel_uploader(CUSTOMER_REQUIRED_COLUMNS, CUSTOMER_OPTIONAL_COLUMNS, key="customer_upload")
        if cdf is not None and not import_customer_company:
            st.error("Pick a company above before importing.")
        elif cdf is not None:
            existing_customer_query = session.query(Customer).filter(Customer.company_id == import_customer_company.id)
            existing_customer_names = {c.company_name.strip().lower() for c in existing_customer_query.all()}
            new_customer_rows, dup_customer_rows, bad_email_rows = [], [], []
            for _, crow in cdf.iterrows():
                cname_val = str(crow.get("company_name", "") or "").strip()
                cemail_val = str(crow.get("contact_email", "") or "").strip()
                if not cname_val:
                    continue
                if not is_valid_email(cemail_val):
                    bad_email_rows.append(crow)
                    continue
                if cname_val.lower() in existing_customer_names:
                    dup_customer_rows.append(crow)
                    continue
                new_customer_rows.append(crow)
                existing_customer_names.add(cname_val.lower())

            st.write(
                f"Rows ready to import: **{len(new_customer_rows)}** | "
                f"Rows flagged as duplicates: **{len(dup_customer_rows)}** | "
                f"Rows flagged for invalid email: **{len(bad_email_rows)}**"
            )
            if dup_customer_rows:
                st.warning("These rows match a customer company name already in the list and were skipped.")
                render_data_table(pd.DataFrame(dup_customer_rows), max_height="300px")
            if bad_email_rows:
                st.warning("These rows have a Contact Email that doesn't look like a valid email address and were skipped.")
                render_data_table(pd.DataFrame(bad_email_rows), max_height="300px")

            if new_customer_rows and st.button("Confirm import", key="confirm_customer_import"):
                for crow in new_customer_rows:
                    session.add(
                        Customer(
                            company_id=import_customer_company.id,
                            company_name=str(crow["company_name"]).strip(),
                            contact_person=str(crow.get("contact_person", "") or ""),
                            contact_email=str(crow.get("contact_email", "") or ""),
                            customer_type=str(crow.get("customer_type", "") or ""),
                        )
                    )
                session.commit()
                msg = f"Imported {len(new_customer_rows)} customer(s) from {cfilename}."
                if dup_customer_rows or bad_email_rows:
                    msg += f" Skipped {len(dup_customer_rows) + len(bad_email_rows)} row(s) (duplicate name or invalid email)."
                set_pending_banner("customer_import_msg", msg)
                st.rerun()
