"""Screen 3b: Product Grade Profile

CR-10 (Split Product Families and Product Grades into Separate Pages,
Charlie's instruction, 2026-08-12): this page is the Product Grades half
of what used to be one combined page (views/2_Product_Family_Foam_Grade.py,
"Product Families & Product Grades", two tabs) - see
views/2_Product_Families.py for the other half and the shared design notes
(context handoff, access_control page_key retirement) that apply to both.

Every Product Grade read/write/cascade-delete behavior below - manual add,
CSV/Excel import, machine assignment, and the full Product Grade Property
Targets editor - is carried over unchanged from the old combined page's
"Product grades" tab (CR-10 section 6, "Functional Preservation"). The one
genuinely new thing this page adds is the "Filter by product family"
selectbox just below (CR-10 acceptance criterion 11, "Direct entry to
Product Grades supports normal family selection or filtering") - the old
combined page had no equivalent, since the "Product family" column on its
grades table was the only family-facing context previously available here.

Context handoff FROM Product Families (CR-10 acceptance criteria 10/11):
if st.session_state["pfg_family_context_id"] is present (set by that page's
"Open Product Grades for ..." button right before switching here), it is
popped and used to seed the filter selectbox's initial value for this run
- a one-time inheritance, not a permanent link, so navigating from a
different family later always re-targets the filter, and the user is
always free to change it (or pick "All product families") once they're
here, exactly like a direct visit to this page would allow."""

import pandas as pd
import streamlit as st

from access_control import can_use_page
from auth import current_user, logout_button, require_login
from cascades import delete_foam_grade_cascade, foam_grade_dependency_counts
from db import (
    FoamGrade,
    GRADE_SPEC_TARGET_TYPE_OPERATORS,
    GRADE_SPEC_TARGET_TYPES,
    GradeSpecification,
    Orientation,
    PhysicalPropertyDefinition,
    PhysicalPropertyMethod,
    PhysicalPropertyUOM,
    ProductFamily,
    TestCondition,
    get_session,
    init_db,
)
from helpers import (
    clickable_table,
    cr11_function_tab_labels,
    csv_excel_uploader,
    dedupe_import_rows,
    delete_with_confirm,
    grade_production_method_label,
    machines_for_plant_across_activated_methods,
    page_setup,
    render_data_table,
    render_function_action_intro,
    set_pending_banner,
    show_pending_banner,
    view_only_notice,
)
from tenant_scope import apply_scope, clear_scope_cache, company_picker, family_ids_for_plants, plant_ids_for_company

GRADE_REQUIRED_COLUMNS = ["product_family_id", "grade_name"]
# CR-07 (2026-08-11, Product Grade Physical Property Target Architecture and
# Quality Alignment): target_density/target_hardness dropped from the CSV
# import's optional columns along with the manual Add/Edit form fields below
# - see db.py's FoamGrade docstring. A batch import shouldn't write into a
# deprecated fixed field any more than the manual form should.
GRADE_OPTIONAL_COLUMNS = ["notes"]

page_setup("Product Grades")
init_db()
require_login()
logout_button()

st.title("Product Grades")
render_function_action_intro(
    function_text=(
        "A product grade is a specific product within a product family, and it's where a new grade "
        "starts its life in the system. Each grade carries its own Product Grade Property Targets - a "
        "dynamic list you build from the same controlled Physical Property Master Quality results are "
        "recorded against, so a grade can be specified by exactly the properties that matter for it "
        "(thermal, mechanical, dimensional, fire, ...), with no fixed field forcing every grade through "
        "the same two numbers. Every recipe version, production run, and quality result recorded "
        "downstream is tied to one of these product grades."
    ),
    action_text=(
        "Use the family filter below to work within one product family at a time, or leave it on 'All "
        "product families' to see everything. Add each product grade one at a time, or bring in a "
        "batch through the CSV/Excel import tab if you're loading many grades at once. On the edit "
        "screen, use 'Add a property target' to pick a controlled property and set its target type, "
        "value, and unit - repeat for every property this grade needs to hit; a property already added "
        "drops out of the picker until you remove it. Click a row in the table to edit or delete it - "
        "deleting a product grade cascades to everything recorded under it, with the count shown before "
        "you confirm. Need a new product family first? Use the Product Families page."
    ),
)
session = get_session()
user = current_user()
page_usable = can_use_page("product_grades", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()
company, _all_companies = company_picker(
    st, session, user["is_platform_owner"], user["company_id"], key="pgr_company_filter"
)
company_id = company.id if company else None
plant_ids = plant_ids_for_company(session, company_id)
family_ids = family_ids_for_plants(session, plant_ids)

families = apply_scope(session.query(ProductFamily), ProductFamily.plant_id, plant_ids).all()
property_defs = (
    session.query(PhysicalPropertyDefinition)
    .order_by(PhysicalPropertyDefinition.is_common.desc(), PhysicalPropertyDefinition.sort_order)
    .all()
)
if not families:
    st.warning("Add a product family first, on the Product Families page.")
else:
    # CR-10 acceptance criterion 11 ("Direct entry to Product Grades
    # supports normal family selection or filtering") - the old combined
    # page had no equivalent of this; a grade's "Family" column on the
    # table below was the only family-facing context it offered.
    #
    # Context handoff from Product Families (acceptance criteria 10):
    # setting session_state[key] directly, BEFORE the selectbox with that
    # same key is instantiated below, is what makes Streamlit treat it as
    # this widget's current value on this run - popped immediately so it
    # only ever applies once per switch-over, not on every later rerun
    # while the operator keeps working on this page.
    _context_family_id = st.session_state.pop("pfg_family_context_id", None)
    if _context_family_id is not None:
        _context_family = next((f for f in families if f.id == _context_family_id), None)
        if _context_family is not None:
            st.session_state["pgr_family_filter"] = _context_family

    family_filter_options = [None] + families
    selected_family_filter = st.selectbox(
        "Filter by product family", family_filter_options,
        format_func=lambda f: "All product families" if f is None else f.name,
        key="pgr_family_filter",
    )
    if selected_family_filter is not None:
        st.caption(
            f"Showing product grades for **{selected_family_filter.name}** only. "
            "Choose 'All product families' above to see every grade."
        )

    # CR-11 (Standardize Record Create, Edit/Delete and CSV/Excel Import
    # Functions, 2026-08-12): wording/order aligned via
    # cr11_function_tab_labels(). The Edit/Delete content (previously a
    # below-the-tabs browse/edit/delete section) is now the middle
    # sibling tab - see tab_edit_delete below.
    tab_create, tab_edit_delete, tab_import = st.tabs(cr11_function_tab_labels("Product Grade"))

    with tab_create:
        with st.expander("Add product grade", expanded=False):
            if not page_usable:
                st.caption("View-only access - adding a product grade is restricted for your role.")
            else:
                # Family (and therefore Plant) and the Machine-assignment
                # multiselect live outside the st.form below, same as
                # before. Unlike the earlier design, there is no
                # separate "Production Method *" gate here: a Product
                # Grade's Production Method(s) are simply whichever
                # methods its assigned Machines carry (many-to-many -
                # see helpers.grade_production_methods), so every
                # machine across every one of the plant's activated
                # methods is offered up front, labeled by its own
                # method, rather than forcing one method choice before
                # any machine can be picked.
                family = st.selectbox("Product family *", families, format_func=lambda f: f.name, key="add_grade_family")
                assignable_machines = machines_for_plant_across_activated_methods(session, family.plant_id)
                if not assignable_machines:
                    st.warning(
                        "This product family's plant has no activated Production Methods (or no "
                        "production units or cells tagged with one) yet. Enable a Production "
                        "Method and add a production unit or cell on the Production Equipment "
                        "page first."
                    )
                assigned_machines = st.multiselect(
                    "Production Units or Cells this PU Material can be produced on",
                    assignable_machines,
                    format_func=lambda m: f"{m.name} ({m.production_method.name if m.production_method else '—'})",
                    key="add_grade_machines",
                ) if assignable_machines else []
                # CR-07 (2026-08-11): no Target density / Target hardness
                # fields here any more - see db.py's FoamGrade docstring.
                # A grade's property targets are added afterward, on the
                # edit screen's "Product Grade Property Targets" section,
                # from the same controlled Physical Property Master
                # Quality results use.
                with st.form("add_grade"):
                    grade_name = st.text_input("Grade name / code *")
                    notes = st.text_area("Notes")
                    submitted = st.form_submit_button("Save product grade")
                    if submitted:
                        if not grade_name:
                            st.error("Grade name is required.")
                        else:
                            new_grade = FoamGrade(
                                product_family_id=family.id,
                                grade_name=grade_name,
                                notes=notes,
                            )
                            new_grade.machines = list(assigned_machines)
                            session.add(new_grade)
                            session.commit()
                            clear_scope_cache()
                            st.success(f"Product grade '{grade_name}' added. Add its property targets "
                                       "from the section below.")
                            st.rerun()

    with tab_import:
        if not page_usable:
            st.caption("View-only access - importing product grades is restricted for your role.")
        else:
            show_pending_banner("grade_import_msg")
            df, filename = csv_excel_uploader(GRADE_REQUIRED_COLUMNS, GRADE_OPTIONAL_COLUMNS, key="grade_upload")
            if df is not None:
                valid_family_ids = {f.id for f in families}
                good_rows, bad_rows = [], []
                for _, row in df.iterrows():
                    if row.get("product_family_id") in valid_family_ids and str(row.get("grade_name", "")).strip():
                        good_rows.append(row)
                    else:
                        bad_rows.append(row)

                st.write(f"Rows ready to import: **{len(good_rows)}** | Rows flagged/rejected: **{len(bad_rows)}**")
                if bad_rows:
                    st.warning("Flagged rows reference an unknown product_family_id or have no grade_name.")
                    render_data_table(pd.DataFrame(bad_rows), max_height="300px")

                if good_rows and st.button("Confirm import", key="confirm_grade_import"):
                    existing_keys = {
                        (g.product_family_id, g.grade_name.strip().lower())
                        for g in apply_scope(
                            session.query(FoamGrade), FoamGrade.product_family_id, family_ids
                        ).all()
                    }
                    new_rows, dup_rows = dedupe_import_rows(
                        good_rows,
                        existing_keys,
                        key_func=lambda row: (int(row["product_family_id"]), str(row["grade_name"]).strip().lower()),
                    )
                    for row in new_rows:
                        session.add(
                            FoamGrade(
                                product_family_id=int(row["product_family_id"]),
                                grade_name=str(row["grade_name"]).strip(),
                                notes=str(row.get("notes", "") or ""),
                            )
                        )
                    session.commit()
                    clear_scope_cache()
                    msg = f"Imported {len(new_rows)} product grade(s) from {filename}."
                    if dup_rows:
                        msg += f" Skipped {len(dup_rows)} row(s) already recorded for their product family (likely a repeat click)."
                    set_pending_banner("grade_import_msg", msg)
                    st.rerun()


    with tab_edit_delete:
        st.divider()
        grades = apply_scope(session.query(FoamGrade), FoamGrade.product_family_id, family_ids).all()
        if selected_family_filter is not None:
            grades = [g for g in grades if g.product_family_id == selected_family_filter.id]
        if not grades:
            st.info("No product grades recorded yet.")
        else:
            grade_rows = [
                {
                    "Grade": grade.grade_name,
                    "Family": grade.product_family.name,
                    # Derived from the grade's assigned Machines (many-to-many),
                    # never from the deprecated FoamGrade.production_method_id -
                    # see helpers.grade_production_method_label().
                    "Production Method": grade_production_method_label(grade),
                    "Production Units or Cells": len(grade.machines),
                    # CR-07 (2026-08-11): one unified property-target count,
                    # replacing the separate Target density/Target hardness
                    # columns and the "Other target properties" count - see
                    # db.py's FoamGrade/FoamGradeTargetProperty docstrings.
                    "Property targets": len(grade.specifications),
                }
                for grade in grades
            ]
            st.caption("Click a row to edit (and optionally delete) that product grade.")
            idx = clickable_table(grade_rows, key="grades_table")
            if idx is not None and idx < len(grades):
                st.session_state["grade_selected_id"] = grades[idx].id
            else:
                st.session_state.pop("grade_selected_id", None)

            selected_grade_id = st.session_state.get("grade_selected_id")
            selected_grade = next((g for g in grades if g.id == selected_grade_id), None)

            if selected_grade:
                st.markdown(f"**Edit product grade: {selected_grade.grade_name}**")
                if not page_usable:
                    st.caption("View-only access - editing and deleting is restricted for your role.")
                else:
                    e_family = st.selectbox(
                        "Product family *", families,
                        index=next((i for i, f in enumerate(families) if f.id == selected_grade.product_family_id), 0),
                        format_func=lambda f: f.name, key=f"edit_grade_family_{selected_grade.id}",
                    )
                    # No Production Method gate here either (see Add form
                    # above and helpers.machines_for_plant_across_activated_methods
                    # docstring) - offering every machine across every
                    # activated method up front, defaulted to the grade's
                    # CURRENT full machine set, is what stops saving this
                    # form from silently dropping a cross-method machine
                    # assignment the way the single-method-filtered
                    # version used to.
                    e_assignable_machines = machines_for_plant_across_activated_methods(session, e_family.plant_id)
                    # A machine the grade is already assigned to might not
                    # be in e_assignable_machines if its Production Method
                    # was since deactivated for this plant, or the grade
                    # was just reassigned to a different family/plant -
                    # include it anyway so it isn't silently dropped just
                    # for appearing in this list.
                    e_machine_options = list(e_assignable_machines)
                    for m in selected_grade.machines:
                        if m not in e_machine_options:
                            e_machine_options.append(m)
                    if not e_machine_options:
                        st.caption(
                            "This product family's plant has no activated Production Methods (or no "
                            "production units or cells tagged with one) yet."
                        )
                    e_assigned_machines = st.multiselect(
                        "Production Units or Cells this PU Material can be produced on",
                        e_machine_options, default=list(selected_grade.machines),
                        format_func=lambda m: f"{m.name} ({m.production_method.name if m.production_method else '—'})",
                        key=f"edit_grade_machines_{selected_grade.id}",
                    ) if e_machine_options else []
                    with st.form(f"edit_grade_{selected_grade.id}"):
                        e_grade_name = st.text_input(
                            "Grade name / code *", value=selected_grade.grade_name, key=f"edit_grade_name_{selected_grade.id}"
                        )
                        e_notes = st.text_area("Notes", value=selected_grade.notes or "", key=f"edit_grade_notes_{selected_grade.id}")
                        if st.form_submit_button("Save changes"):
                            if not e_grade_name.strip():
                                st.error("Grade name is required.")
                            else:
                                selected_grade.product_family_id = e_family.id
                                selected_grade.grade_name = e_grade_name.strip()
                                selected_grade.notes = e_notes
                                # production_method_id intentionally left untouched -
                                # deprecated, see db.py's FoamGrade model.
                                selected_grade.machines = list(e_assigned_machines)
                                session.commit()
                                st.success("Product grade updated.")
                                st.rerun()

                    # CR-07 (2026-08-11): a pre-CR-07 legacy target_density/
                    # target_hardness value is surfaced read-only (never
                    # editable, never migrated automatically - see db.py's
                    # FoamGrade docstring) so it isn't silently lost from
                    # view; re-enter it below as a proper property target
                    # once the correct controlled density property is
                    # confirmed.
                    if selected_grade.target_density is not None or selected_grade.target_hardness is not None:
                        legacy_bits = []
                        if selected_grade.target_density is not None:
                            legacy_bits.append(f"density {selected_grade.target_density:g} kg/m3")
                        if selected_grade.target_hardness is not None:
                            legacy_bits.append(f"hardness {selected_grade.target_hardness:g} N (40% ILD)")
                        st.caption(
                            "⚠️ Older value on file, recorded before this grade's controlled property "
                            "specification existed (not part of the specification below): "
                            + ", ".join(legacy_bits)
                            + ". Add it as a proper property target below once confirmed."
                        )

                    st.markdown("**Product Grade Property Targets**")
                    st.caption(
                        "The controlled properties this grade must hit - each one sourced from the same "
                        "Physical Property Master Quality results are recorded against, so PI3 can compare "
                        "an actual result to this target automatically. A property already added here is "
                        "removed from the picker below until you remove it."
                    )

                    existing_specs = (
                        session.query(GradeSpecification)
                        .filter(GradeSpecification.foam_grade_id == selected_grade.id)
                        .order_by(GradeSpecification.property_name)
                        .all()
                    )
                    used_property_ids = {s.property_definition_id for s in existing_specs if s.property_definition_id}

                    def _uom_choices_for_property(prop_def):
                        rows = (
                            session.query(PhysicalPropertyUOM)
                            .filter(PhysicalPropertyUOM.property_definition_id == prop_def.id)
                            .order_by(PhysicalPropertyUOM.sort_order)
                            .all()
                            if prop_def
                            else []
                        )
                        labels = [r.unit_label for r in rows]
                        if prop_def and prop_def.default_uom and prop_def.default_uom not in labels:
                            labels.insert(0, prop_def.default_uom)
                        return labels or ["—"]

                    def _target_type_choices_for_property(prop_def):
                        # CR-07: "Use the target type allowed for the
                        # selected property" - Physical Property Master's own
                        # allowed_target_type (e.g. "Minimum/Range") is a
                        # slash-separated subset of GRADE_SPEC_TARGET_TYPES;
                        # fall back to the full controlled list when a
                        # property hasn't had this WP5 field populated yet,
                        # rather than blocking target entry on missing
                        # master-data richness.
                        raw = (prop_def.allowed_target_type or "").strip() if prop_def else ""
                        if not raw:
                            return list(GRADE_SPEC_TARGET_TYPES)
                        allowed = [part.strip() for part in raw.split("/") if part.strip()]
                        ordered = [t for t in GRADE_SPEC_TARGET_TYPES if t in allowed]
                        return ordered or list(GRADE_SPEC_TARGET_TYPES)

                    def _render_target_value_inputs(target_type, key_prefix, defaults=None):
                        """Returns (target_value, lower_limit, upper_limit, class_value)
                        for the value input(s) matching this target type -
                        CR-07 section 5: Range needs lower+upper, Class needs
                        a text value, everything else needs one number."""
                        defaults = defaults or {}
                        if target_type == "Range":
                            c1, c2 = st.columns(2)
                            lo = c1.number_input(
                                "Lower limit", step=0.1, value=float(defaults.get("lower_limit") or 0.0),
                                key=f"{key_prefix}_lower",
                            )
                            hi = c2.number_input(
                                "Upper limit", step=0.1, value=float(defaults.get("upper_limit") or 0.0),
                                key=f"{key_prefix}_upper",
                            )
                            return None, lo, hi, None
                        if target_type == "Class":
                            cv = st.text_input(
                                "Class value (e.g. Class B)", value=defaults.get("class_value") or "",
                                key=f"{key_prefix}_class",
                            )
                            return None, None, None, cv
                        tv = st.number_input(
                            "Target value", step=0.1, value=float(defaults.get("target_value") or 0.0),
                            key=f"{key_prefix}_value",
                        )
                        return tv, None, None, None

                    if not existing_specs:
                        st.caption("No property targets added yet.")
                    for spec in existing_specs:
                        with st.expander(
                            f"{spec.property_name}"
                            f"{' — ' + spec.target_type if spec.target_type else ''}",
                            expanded=False,
                        ):
                            prop_def = spec.property_definition
                            type_choices = _target_type_choices_for_property(prop_def)
                            uom_choices = _uom_choices_for_property(prop_def)
                            methods_for_property = (
                                session.query(PhysicalPropertyMethod)
                                .filter(PhysicalPropertyMethod.property_definition_id == spec.property_definition_id)
                                .order_by(PhysicalPropertyMethod.sort_order)
                                .all()
                                if spec.property_definition_id
                                else []
                            )
                            conditions = session.query(TestCondition).order_by(TestCondition.sort_order).all()
                            orientations = session.query(Orientation).order_by(Orientation.sort_order).all()

                            with st.form(f"edit_spec_{spec.id}"):
                                s_type = st.selectbox(
                                    "Target type *", type_choices,
                                    index=type_choices.index(spec.target_type) if spec.target_type in type_choices else 0,
                                    key=f"spec_{spec.id}_type",
                                )
                                s_value, s_lower, s_upper, s_class = _render_target_value_inputs(
                                    s_type, f"spec_{spec.id}",
                                    defaults={
                                        "target_value": spec.target_value, "lower_limit": spec.lower_limit,
                                        "upper_limit": spec.upper_limit, "class_value": spec.class_value,
                                    },
                                )
                                s_uom = st.selectbox(
                                    "Unit of measure", uom_choices,
                                    index=uom_choices.index(spec.unit) if spec.unit in uom_choices else 0,
                                    key=f"spec_{spec.id}_uom",
                                )
                                s_method = st.selectbox(
                                    "Test method (optional)", [None] + methods_for_property,
                                    format_func=lambda m: "— not specified —" if m is None else m.method_code,
                                    index=(
                                        ([None] + methods_for_property).index(spec.property_method)
                                        if spec.property_method in methods_for_property else 0
                                    ),
                                    key=f"spec_{spec.id}_method",
                                )
                                s_condition = st.selectbox(
                                    "Condition (optional)", [None] + conditions,
                                    format_func=lambda c: "— not specified —" if c is None else c.name,
                                    index=(
                                        ([None] + conditions).index(spec.condition)
                                        if spec.condition in conditions else 0
                                    ),
                                    key=f"spec_{spec.id}_condition",
                                )
                                s_orientation = st.selectbox(
                                    "Orientation (optional)", [None] + orientations,
                                    format_func=lambda o: "— not specified —" if o is None else o.name,
                                    index=(
                                        ([None] + orientations).index(spec.orientation)
                                        if spec.orientation in orientations else 0
                                    ),
                                    key=f"spec_{spec.id}_orientation",
                                )
                                s_notes = st.text_area("Notes", value=spec.notes or "", key=f"spec_{spec.id}_notes")
                                c_save, c_remove = st.columns(2)
                                save_clicked = c_save.form_submit_button("Save")
                                remove_clicked = c_remove.form_submit_button("Remove this property target")
                                if save_clicked:
                                    spec.target_type = s_type
                                    spec.target_operator = GRADE_SPEC_TARGET_TYPE_OPERATORS.get(s_type, "<=")
                                    spec.target_value = s_value
                                    spec.lower_limit = s_lower
                                    spec.upper_limit = s_upper
                                    spec.class_value = s_class
                                    spec.unit = None if s_uom == "—" else s_uom
                                    spec.property_method_id = s_method.id if s_method else None
                                    spec.condition_id = s_condition.id if s_condition else None
                                    spec.orientation_id = s_orientation.id if s_orientation else None
                                    spec.notes = s_notes
                                    session.commit()
                                    st.success(f"{spec.property_name} target updated.")
                                    st.rerun()
                                if remove_clicked:
                                    session.delete(spec)
                                    session.commit()
                                    st.success(f"{spec.property_name} target removed.")
                                    st.rerun()

                    available_properties = [p for p in property_defs if p.id not in used_property_ids]
                    if not available_properties:
                        st.caption(
                            "Every controlled property already has a target on this grade - nothing left to add."
                        )
                    else:
                        with st.expander("Add a property target", expanded=False):
                            add_prop = st.selectbox(
                                "Property *", available_properties,
                                format_func=lambda p: f"⭐ {p.name}" if p.is_common else p.name,
                                key=f"add_spec_property_{selected_grade.id}",
                            )
                            if add_prop:
                                st.caption(f"{add_prop.what_it_measures or ''} — category: {add_prop.category or '—'}")
                            add_type_choices = _target_type_choices_for_property(add_prop)
                            add_uom_choices = _uom_choices_for_property(add_prop)
                            add_methods = (
                                session.query(PhysicalPropertyMethod)
                                .filter(PhysicalPropertyMethod.property_definition_id == add_prop.id)
                                .order_by(PhysicalPropertyMethod.sort_order)
                                .all()
                                if add_prop
                                else []
                            )
                            add_conditions = session.query(TestCondition).order_by(TestCondition.sort_order).all()
                            add_orientations = session.query(Orientation).order_by(Orientation.sort_order).all()

                            with st.form(f"add_spec_{selected_grade.id}"):
                                a_type = st.selectbox("Target type *", add_type_choices, key=f"add_spec_type_{selected_grade.id}")
                                a_value, a_lower, a_upper, a_class = _render_target_value_inputs(
                                    a_type, f"add_spec_{selected_grade.id}",
                                )
                                a_uom = st.selectbox("Unit of measure", add_uom_choices, key=f"add_spec_uom_{selected_grade.id}")
                                a_method = st.selectbox(
                                    "Test method (optional)", [None] + add_methods,
                                    format_func=lambda m: "— not specified —" if m is None else m.method_code,
                                    key=f"add_spec_method_{selected_grade.id}",
                                )
                                a_condition = st.selectbox(
                                    "Condition (optional)", [None] + add_conditions,
                                    format_func=lambda c: "— not specified —" if c is None else c.name,
                                    key=f"add_spec_condition_{selected_grade.id}",
                                )
                                a_orientation = st.selectbox(
                                    "Orientation (optional)", [None] + add_orientations,
                                    format_func=lambda o: "— not specified —" if o is None else o.name,
                                    key=f"add_spec_orientation_{selected_grade.id}",
                                )
                                a_notes = st.text_area("Notes", key=f"add_spec_notes_{selected_grade.id}")
                                if st.form_submit_button("Add property target"):
                                    # Write-path duplicate guard (CR-07
                                    # acceptance criterion) - belt-and-
                                    # suspenders alongside the DB's own
                                    # uq_grade_specification_grade_property
                                    # constraint and the picker above already
                                    # excluding used properties.
                                    already = (
                                        session.query(GradeSpecification)
                                        .filter(
                                            GradeSpecification.foam_grade_id == selected_grade.id,
                                            GradeSpecification.property_definition_id == add_prop.id,
                                        )
                                        .first()
                                    )
                                    if already:
                                        st.error(f"{add_prop.name} already has a target on this grade.")
                                    else:
                                        session.add(
                                            GradeSpecification(
                                                foam_grade_id=selected_grade.id,
                                                property_definition_id=add_prop.id,
                                                property_method_id=a_method.id if a_method else None,
                                                property_name=add_prop.name,
                                                target_type=a_type,
                                                target_operator=GRADE_SPEC_TARGET_TYPE_OPERATORS.get(a_type, "<="),
                                                target_value=a_value,
                                                lower_limit=a_lower,
                                                upper_limit=a_upper,
                                                class_value=a_class,
                                                unit=None if a_uom == "—" else a_uom,
                                                condition_id=a_condition.id if a_condition else None,
                                                orientation_id=a_orientation.id if a_orientation else None,
                                                notes=a_notes,
                                            )
                                        )
                                        session.commit()
                                        st.success(f"{add_prop.name} added as a property target.")
                                        st.rerun()

                    counts = foam_grade_dependency_counts(session, selected_grade.id)
                    total_related = sum(counts.values())
                    if total_related:
                        detail = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
                        warning = f"Deleting this product grade will also permanently delete {total_related} related record(s): {detail}."
                    else:
                        warning = "This product grade has no related records — deleting it is safe."

                    def _do_delete_grade(_session=session, _id=selected_grade.id):
                        delete_foam_grade_cascade(_session, _id)
                        _session.commit()
                        clear_scope_cache()
                        st.session_state.pop("grade_selected_id", None)

                    delete_with_confirm(
                        f"'{selected_grade.grade_name}'", _do_delete_grade, key_prefix=f"grade_{selected_grade.id}",
                        extra_warning=warning,
                    )

                if st.button("Clear selection", key="clear_grade_selection"):
                    st.session_state.pop("grade_selected_id", None)
                    st.rerun()
