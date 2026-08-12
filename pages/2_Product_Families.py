"""Screen 3a: Product Family Profile

CR-10 (Split Product Families and Product Grades into Separate Pages,
Charlie's instruction, 2026-08-12): this page is the Product Families half
of what used to be one combined page (pages/2_Product_Family_Foam_Grade.py,
"Product Families & Product Grades", two tabs). Charlie's CR gives each
data domain its own direct sidebar entry and removes the extra in-page tab
click - see pages/2_Product_Grades.py for the other half.

Every Product Family read/write/cascade-delete behavior below is carried
over unchanged from the old combined page's "Product families" tab - this
split is presentation/navigation only (CR-10 section 6, "Functional
Preservation"). The Product Family -> Product Grade relationship itself
lives entirely in the data model (FoamGrade.product_family_id) and was
never inside the old page's tab structure, so nothing about that
relationship needed to change to split the UI in two.

Context handoff to Product Grades (CR-10 acceptance criteria 10/11): the
"Open this family's Product Grades" button below stashes the selected
family's id in st.session_state["pfg_family_context_id"] and switches page.
pages/2_Product_Grades.py pops that key on its next run and uses it to
seed its own family-filter selectbox's initial value - a one-time
inheritance, not a permanent link, so the user lands straight on the right
family's grades without repeating the selection, but can still change the
filter (or come back to "All product families") from there exactly like a
direct visit would allow.

access_control page_key: this page is new plumbing over an existing
CRUD surface, but CR-10 splits ONE page into TWO independent ones, so a
single shared key could no longer describe "can this role see/use this
screen" correctly for both. A fresh key ("product_families") is used
here; see pages/2_Product_Grades.py for its own new key
("product_grades"). The old combined key ("product_family_foam_grade") is
retired from access_control.PAGE_CATALOG entirely (2026-08-12 live-data
check found zero role_page_permissions rows referencing it, so - same as
CR-03's removal of "reference_formulations" - no migration was needed;
every role defaults to full access on both new keys until explicitly
restricted, same as it would have on the old combined one)."""

import streamlit as st

from access_control import can_use_page
from auth import current_user, logout_button, require_login
from cascades import delete_product_family_cascade, product_family_dependency_counts
from db import Plant, ProductFamily, get_session, init_db
from helpers import clickable_table, delete_with_confirm, page_setup, render_function_action_intro, view_only_notice
from tenant_scope import apply_scope, clear_scope_cache, company_picker, plant_ids_for_company

page_setup("Product Families")
init_db()
require_login()
logout_button()

st.title("Product Families")
render_function_action_intro(
    function_text=(
        "A product family groups your product grades by market segment or application under a "
        "plant (e.g. cold-room panel core, pipe insulation). It's the top level of your product "
        "catalog - every product grade belongs to exactly one family, and every recipe version, "
        "production run, and quality result recorded downstream traces back to one of those grades."
    ),
    action_text=(
        "Add a product family under the right plant, then continue straight to that family's "
        "product grades using the button on its edit panel below - or open the Product Grades "
        "page directly if you'd rather add grades under a different family or see every grade at "
        "once. Click a row in the table to edit or delete that product family - deleting one "
        "cascades to every product grade recorded under it, with the count shown before you confirm."
    ),
)
session = get_session()
user = current_user()
page_usable = can_use_page("product_families", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()
company, _all_companies = company_picker(
    st, session, user["is_platform_owner"], user["company_id"], key="pf_company_filter"
)
company_id = company.id if company else None
plant_ids = plant_ids_for_company(session, company_id)

plants = apply_scope(session.query(Plant), Plant.id, plant_ids).all()
if not plants:
    st.warning("Add a plant first (Plant & Foam Equipment Overview) before creating product families.")
    st.stop()

with st.expander("Add product family"):
    if not page_usable:
        st.caption("View-only access - adding a product family is restricted for your role.")
    else:
        with st.form("add_family"):
            plant = st.selectbox("Plant *", plants, format_func=lambda p: p.name)
            name = st.text_input("Product family name *")
            application = st.text_input("Application (e.g. mattress comfort layer)")
            customer_segment = st.text_input("Customer segment")
            description = st.text_area("Description")
            submitted = st.form_submit_button("Save product family")
            if submitted:
                if not name:
                    st.error("Product family name is required.")
                else:
                    session.add(
                        ProductFamily(
                            plant_id=plant.id,
                            name=name,
                            application=application,
                            customer_segment=customer_segment,
                            description=description,
                        )
                    )
                    session.commit()
                    clear_scope_cache()
                    st.success(f"Product family '{name}' added.")
                    st.rerun()

st.divider()
families = apply_scope(session.query(ProductFamily), ProductFamily.plant_id, plant_ids).all()
if not families:
    st.info("No product families recorded yet.")
else:
    family_rows = [
        {
            "Name": fam.name,
            "Plant": fam.plant.name,
            "Application": fam.application or "",
            "Customer segment": fam.customer_segment or "",
            "Product grades": len(fam.foam_grades),
        }
        for fam in families
    ]
    st.caption("Click a row to edit (and optionally delete) that product family.")
    idx = clickable_table(family_rows, key="families_table")
    if idx is not None and idx < len(families):
        st.session_state["family_selected_id"] = families[idx].id
    else:
        st.session_state.pop("family_selected_id", None)

    selected_family_id = st.session_state.get("family_selected_id")
    selected_family = next((f for f in families if f.id == selected_family_id), None)

    if selected_family:
        st.markdown(f"**Edit product family: {selected_family.name}**")

        # CR-10 acceptance criteria 10/11: hand this family's context to the
        # Product Grades page rather than making the user re-pick it there.
        # Not gated behind page_usable - opening a filtered view of Product
        # Grades isn't a write action, so a view-only role should get it too.
        if st.button(
            f"Open Product Grades for '{selected_family.name}' →",
            key=f"family_to_grades_{selected_family.id}",
        ):
            st.session_state["pfg_family_context_id"] = selected_family.id
            st.switch_page("pages/2_Product_Grades.py")

        if not page_usable:
            st.caption("View-only access - editing and deleting is restricted for your role.")
        else:
            with st.form(f"edit_family_{selected_family.id}"):
                e_plant = st.selectbox(
                    "Plant *", plants,
                    index=next((i for i, p in enumerate(plants) if p.id == selected_family.plant_id), 0),
                    format_func=lambda p: p.name, key=f"edit_family_plant_{selected_family.id}",
                )
                e_name = st.text_input("Product family name *", value=selected_family.name, key=f"edit_family_name_{selected_family.id}")
                e_application = st.text_input(
                    "Application", value=selected_family.application or "", key=f"edit_family_app_{selected_family.id}"
                )
                e_segment = st.text_input(
                    "Customer segment", value=selected_family.customer_segment or "", key=f"edit_family_seg_{selected_family.id}"
                )
                e_description = st.text_area(
                    "Description", value=selected_family.description or "", key=f"edit_family_desc_{selected_family.id}"
                )
                if st.form_submit_button("Save changes"):
                    if not e_name.strip():
                        st.error("Product family name is required.")
                    else:
                        selected_family.plant_id = e_plant.id
                        selected_family.name = e_name.strip()
                        selected_family.application = e_application
                        selected_family.customer_segment = e_segment
                        selected_family.description = e_description
                        session.commit()
                        st.success("Product family updated.")
                        st.rerun()

            counts = product_family_dependency_counts(session, selected_family.id)
            total_related = sum(counts.values())
            if total_related:
                detail = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
                warning = f"Deleting this product family will also permanently delete {total_related} related record(s): {detail}."
            else:
                warning = "This product family has no related records — deleting it is safe."

            def _do_delete_family(_session=session, _id=selected_family.id):
                delete_product_family_cascade(_session, _id)
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
