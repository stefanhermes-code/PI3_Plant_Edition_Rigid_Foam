"""Screen 4: Recipes (formulation memory)

Each product grade has exactly one ACTIVE recipe at a time - a new version
replaces the previous one in production, they don't coexist. This page
leads with that: "Create Recipe" starts a brand new formulation for a
grade, "Edit Recipe" revises the current one (saving records it as a new
version automatically and retires the one it replaces). Full version
history - every retired version, its ingredients, who approved what and
when - stays fully intact below, it's just not the first thing you have
to manage by hand.

CR-03 (Recipe Consolidation and Pending Review Status), implemented
2026-08-10: the "Recipe versions" list below now also shows every imported
scientific formulation from the reference_formulations table (RF-001..010,
the WP5-reconciliation patent/literature examples, AND RFREF-001..008, the
Post-G5 exact scientific reference recipes - 18 rows total) alongside real
plant RecipeVersion rows, tagged with Approval Status = "Pending Review"
until a plant-authorized review changes it via the same "Edit details"
control real recipes already use. The standalone Reference Formulations
page/nav entry (formerly views/29) is removed entirely per CR-03's target
navigation - this is now the only place those rows are visible in the app.

Deliberately scoped WIDER than CR-03's own literal "eight formulations, 52
components" wording (which only covers RFREF-*, the Post-G5 batch): the
document's stated objective is "presenting exact imported scientific
formulations in the normal Recipes list" and only ever excludes "the two
research formulation families" (RFFAM-*, a genuinely different kind of
record - a parameter range/optimization study, not one exact recipe). The
10 RF-* patent/literature rows are exact formulations in exactly the same
sense RFREF-* rows are (contrasted with RFFAM-*'s ranges), and were the
only thing living on the now-removed Reference Formulations page besides
RFREF-* - leaving them off this list would silently orphan 10 rows and 100
component lines with no UI surface anywhere in the app. Flagged to Charlie/
Stefan in the CR-03 closeout note as a scope broadening, not hidden.

Never migrated into real RecipeVersion rows (no foam_grade_id, no
company_id - ReferenceFormulation is a shared, plant-agnostic public
library, structurally incompatible with RecipeVersion's per-grade,
per-tenant model). Per CR-03 rule 6 ("JC may preserve backend table names
or relationships... the customer-facing Recipes page may combine the
records at the application layer"), they stay in their own table and are
combined here only for display/filtering - see _reference_formulation_rows()
and the combined-list building code below the "Recipe versions" heading.
They can never become an active production recipe for any grade (no code
path links a ReferenceFormulation row to RecipeVersion.is_active at all;
the only real link is the pre-existing, user-set RecipeVersion.
reference_formulation_id "informed by" FK) - satisfying CR-03 rule 3
structurally, with no extra guard code needed.

CR-19 (Correct Recipe Version, Product Grade, and Reference Formulation
Display), implemented 2026-08-13: CR-03's combined "Recipe versions" table
put the imported ReferenceFormulation's own name inside the "Product
grade" column (prefixed "— ... (imported reference)"), which falsely
implied that value came from the Product Grade master. The combined table
still shows both record types together, but now with separate Type,
Product Grade, and Reference Formulation columns: Plant Recipe rows show
their real linked FoamGrade.grade_name in Product Grade (and, if the row
has a reference_formulation_id set, that linked reference formulation's
name as supplemental context in Reference Formulation); Imported Reference
rows show "N/A" in Product Grade and the reference formulation's own name
in Reference Formulation. Product Grade never resolves to anything but a
true FoamGrade master relationship. No schema change, no change to which
records exist or how they're queried - purely a display/column-mapping
correction in the version_rows list comprehension below.
"""

import datetime as dt

import pandas as pd
import streamlit as st
from sqlalchemy import func

import analytics
import component_role
from access_control import can_use_page
from auth import current_user, logout_button, require_login
from cascades import delete_recipe_version_cascade, recipe_version_dependency_counts
from db import (
    APPROVAL_STATUSES,
    FoamGrade,
    RawMaterial,
    RawMaterialCategory,
    RecipeComponent,
    RecipeVersion,
    ReferenceFormulation,
    RoleChangeLog,
    SourceRegister,
    get_session,
    init_db,
)
from helpers import (
    activate_recipe_version,
    clickable_table,
    cr11_function_tab_labels,
    csv_excel_uploader,
    dedupe_import_rows,
    delete_with_confirm,
    log_export_click,
    next_version_label,
    page_setup,
    raw_material_category_label,
    recipe_component_sort_index,
    render_data_table,
    render_function_action_intro,
    set_pending_banner,
    show_pending_banner,
    summarize_recipe_component_changes,
    view_only_notice,
)
from tenant_scope import apply_scope, company_picker, grade_ids_for_company
import reports

RECIPE_VERSION_REQUIRED_COLUMNS = ["foam_grade_id", "version_label"]
RECIPE_VERSION_OPTIONAL_COLUMNS = ["effective_date", "change_note", "approval_status", "created_by", "ratio_index"]

COMPONENT_REQUIRED_COLUMNS = ["recipe_version_id", "raw_material_name"]
COMPONENT_OPTIONAL_COLUMNS = ["supplier", "php", "role_in_formulation", "notes"]

page_setup("Recipes")
init_db()
require_login()
logout_button()

st.title("Recipes")
render_function_action_intro(
    function_text=(
        "Maintains the formulation history for each product grade: the raw-material list with php "
        "dosage, supplier, and role for the currently active recipe, plus every retired version "
        "before it with who approved it and when. A product grade has exactly one active recipe in "
        "production at a time - a new version replaces it rather than running alongside it - so "
        "this is the single source of truth Recipe Optimization, cost, and correlation pages all "
        "read from. The recipe list below also includes imported scientific reference formulations "
        "(patent and literature examples) with Approval Status = Pending Review - they are visible "
        "for technical review and comparison, but can never become an active production recipe for "
        "any grade until a real recipe is created that draws on them."
    ),
    action_text=(
        "Use 'Create Recipe' to start a brand-new formulation for a product grade that doesn't have "
        "one yet, or 'Edit/Delete Recipe' to revise the currently active one - saving automatically "
        "records it as a new version and retires the one it replaces, so you don't have to manage "
        "version numbers or active flags by hand. Add raw materials to a recipe by name (typing a "
        "new one creates it in Raw Materials automatically) with its php and role in the "
        "formulation, or import a full component list via CSV/Excel for bulk loading. Older "
        "versions, their ingredient lists, and approval status stay available further down for "
        "audit - use the Approval Status filter there to isolate Pending Review formulations."
    ),
)
session = get_session()
user = current_user()
page_usable = can_use_page("recipes", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()
company, _all_companies = company_picker(
    st, session, user["is_platform_owner"], user["company_id"], key="recipes_company_filter"
)
active_company_id = company.id if company else None
grade_ids = grade_ids_for_company(session, active_company_id)

grades = apply_scope(session.query(FoamGrade), FoamGrade.id, grade_ids).all()
if not grades:
    st.warning("Add a product grade first (Product Family & Product Grade page).")
    st.stop()


def _match_or_create_raw_material(name, supplier=None):
    """Look up a RawMaterial by name (case-insensitive); create one if it
    doesn't exist yet, so anything typed as a "new" material during recipe
    entry becomes available in the master list (and future dropdowns)
    immediately, not just a one-off string on this one component.

    Scoped to the company currently in view (the platform owner's company
    filter, or the logged-in user's own company) - without this, a case-
    insensitive name match could silently link a recipe component to a
    different company's raw material row (and its cost_per_kg), which
    would leak proprietary data across the tenant boundary."""
    name = (name or "").strip()
    if not name:
        return None
    match_query = session.query(RawMaterial).filter(RawMaterial.name.ilike(name))
    if active_company_id is not None:
        match_query = match_query.filter(RawMaterial.company_id == active_company_id)
    match = match_query.first()
    if match:
        return match
    # CR-08: this is an unattended inline creation (no form asking the user
    # for a real Category/Subcategory), so it can never write free text into
    # the now-controlled category_id/subcategory_id fields. It lands on the
    # single controlled "Other"/"Other" exception pair (RMC2-1000/RMC2-1010)
    # instead, with a note flagging it for later manual classification -
    # same "flag rather than guess" rule CR-08 uses everywhere else, since
    # this code path has no product knowledge to classify from beyond a name
    # string typed into a recipe component.
    other_category = (
        session.query(RawMaterialCategory)
        .filter(RawMaterialCategory.active.is_(True), RawMaterialCategory.parent_category_id.is_(None))
        .filter(RawMaterialCategory.name.ilike("Other"))
        .first()
    )
    other_subcategory = (
        session.query(RawMaterialCategory)
        .filter(RawMaterialCategory.active.is_(True), RawMaterialCategory.is_exception_only.is_(True))
        .first()
    )
    new_rm = RawMaterial(
        company_id=active_company_id,
        name=name,
        category_id=other_category.id if other_category else None,
        subcategory_id=other_subcategory.id if other_subcategory else None,
        default_supplier=supplier or "",
        notes="[Other: auto-created from recipe component entry - needs manual Category/Subcategory review]",
        active=True,
    )
    session.add(new_rm)
    session.flush()
    return new_rm


# ---------------------------------------------------------------------------
# Phase 8 Decision 3: the controlled chemical-role assignment (2026-08-19)
#
# Separate from the ordinary component edit form above it, on purpose. Raw
# material name, supplier, php and the free-text role are ordinary fields a
# user corrects as they go. A chemical role is controlled data: it is the
# formulation half of the A:B ratio answer, it cannot exist without the
# document that establishes it, and every assignment and correction is
# audited. Putting it in the same form would have made it look like one more
# field to fill in.
#
# The role field starts Unresolved and stays Unresolved until somebody chooses
# a term deliberately. There is no "assign roles from material category"
# action anywhere on this page, and its absence is the point: a catalyst, a
# surfactant and a physical blowing agent are USUALLY carried in the polyol
# blend, and usually is not evidence. A convenience button would be that
# inference with a human click on top of it.
# ---------------------------------------------------------------------------

def _source_register_label(source):
    if source is None:
        return "— none selected —"
    bits = [source.controlled_id or f"Source {source.id}"]
    if source.source_type:
        bits.append(source.source_type)
    if source.reference:
        bits.append(source.reference)
    return " · ".join(bits)


def _record_chemical_role_change(session, component, summary, user):
    """Write the controlled-edit audit row for a chemical-role assignment.

    Deliberately NOT audit_log.log_role_change() on this path, even though that
    is the same table and the same model. That helper swallows exceptions and
    its _safe_flush() calls session.rollback() on failure - and because the
    audit row shares this transaction with the assignment itself, a failed
    audit write silently rolled the ASSIGNMENT back too, after which the page
    committed nothing and still reported success. Found in review.

    Here the row is added to the same transaction and any failure propagates,
    so the assignment and its audit record commit together or neither does, and
    the user sees an error rather than a false success. Same path in the sense
    that matters - same table, same controlled-edit history - without the
    swallow.
    """
    session.add(
        RoleChangeLog(
            changed_by_user_id=user["id"],
            company_id=user["company_id"],
            target_type="recipe_component",
            target_id=component.id,
            target_label=component.raw_material_name,
            change_summary=summary,
        )
    )


def _render_chemical_role_control(session, component, user):
    st.markdown("**Controlled chemical role**")
    st.caption(
        "Which component of the formulation this material is. This is what the A:B ratio is "
        "built from, together with the machine's own A/B stream configuration — the two are "
        "recorded separately because which physical stream carries which role varies by "
        "machine. A role is only recorded from a controlled document; it is never inferred."
    )

    current_role = component_role.role_of(component)
    if current_role:
        st.success(f"Assigned: **{current_role}**")
        st.caption(
            f"Source: {_source_register_label(component.chemical_role_source)} · "
            f"Location: {component.chemical_role_source_location}"
        )
    else:
        st.warning(
            "**Unresolved.** No controlled chemical role recorded for this component, so no A:B "
            "ratio is derived for this recipe version."
        )

    sources = session.query(SourceRegister).order_by(SourceRegister.controlled_id).all()
    if not sources:
        st.caption(
            "No entries in the source register yet. A chemical role cannot be recorded without "
            "the document that establishes it."
        )
        return

    role_options = ["— Unresolved —"] + list(component_role.CHEMICAL_ROLES)
    role_index = role_options.index(current_role) if current_role in role_options else 0
    source_options = [None] + sources
    source_index = next(
        (i for i, s in enumerate(source_options)
         if s is not None and s.id == component.chemical_role_source_id),
        0,
    )

    with st.form(f"chemical_role_{component.id}"):
        chosen_role = st.selectbox(
            "Chemical role", role_options, index=role_index,
            key=f"cr_role_{component.id}",
        )
        chosen_source = st.selectbox(
            "Source document *", source_options, index=source_index,
            format_func=_source_register_label, key=f"cr_src_{component.id}",
            help="The controlled document that establishes this role. Source quality follows "
                 "what the source register records; describing it differently here does not "
                 "change what it is.",
        )
        chosen_location = st.text_input(
            "Source location *",
            value=component.chemical_role_source_location or "",
            key=f"cr_loc_{component.id}",
            help="Where inside that document, e.g. 'Table 3, row 2'.",
        )
        saved = st.form_submit_button("Save chemical role")

        if saved:
            if chosen_role == role_options[0]:
                # Clearing back to Unresolved. All three fields go together -
                # leaving the source behind would create exactly the stranded
                # provenance state the database constraint forbids.
                if current_role is None:
                    st.info("Already unresolved — nothing to change.")
                else:
                    summary = (
                        f"Chemical role for '{component.raw_material_name}': "
                        f"{current_role} -> Unresolved (cleared)"
                    )
                    component_role.clear_role(component)
                    _record_chemical_role_change(session, component, summary, user)
                    session.commit()
                    st.success("Chemical role cleared. This component is Unresolved again.")
                    st.rerun()
            else:
                problems = component_role.validate_assignment(
                    chosen_role,
                    chosen_source.id if chosen_source else None,
                    chosen_location,
                )
                if problems:
                    for problem in problems:
                        st.error(problem)
                else:
                    summary = component_role.describe_assignment(
                        component, chosen_role, chosen_location.strip(),
                        source_label=_source_register_label(chosen_source),
                    )
                    component_role.assign_role(
                        component, chosen_role, chosen_source.id, chosen_location
                    )
                    _record_chemical_role_change(session, component, summary, user)
                    session.commit()
                    st.success(f"Chemical role recorded: {chosen_role}.")
                    st.rerun()


def _active_version(grade):
    return next((v for v in grade.recipe_versions if v.is_active), None)


# ---------------------------------------------------------------------------
# Recipe versions (header record)
# ---------------------------------------------------------------------------
# CR-11 (Standardize Record Create, Edit/Delete and CSV/Excel Import
# Functions, 2026-08-12): tab wording/order aligned to the app-wide standard
# via helpers.cr11_function_tab_labels() - "Edit Recipe" -> "Edit/Delete
# Recipe" (delete already lives inside this tab, via delete_with_confirm()
# further down - only the label was stale), and "CSV / Excel import" ->
# "CSV/Excel import Recipes" (no spaces around the slash, plural record
# name appended).
tab_create, tab_edit, tab_import = st.tabs(cr11_function_tab_labels("Recipe"))

with tab_create:
    if not page_usable:
        st.caption("View-only access - creating a recipe is restricted for your role.")
    else:
        st.caption(
            "Start a brand new formulation for a product grade. If this grade already has an active "
            "recipe, it will be retired the moment this one is saved."
        )
        with st.form("create_recipe"):
            grade = st.selectbox(
                "Product grade *", grades, format_func=lambda g: g.grade_name, key="create_recipe_grade"
            )
            version_label = st.text_input("Version label * (e.g. 28-MH-05)")
            effective_date = st.date_input("Effective date", value=dt.date.today())
            change_note = st.text_area("Change note (why this recipe exists) *")
            approval_status = st.selectbox("Approval status", APPROVAL_STATUSES)
            created_by = st.text_input("Created by")
            ratio_index = st.number_input(
                "Ratio / index", min_value=0.0, step=0.01, format="%.3f",
                help="Stoichiometric ratio/index for this formulation - determines the isocyanate php. "
                "A property of the recipe, not of any single production run.",
            )
            submitted = st.form_submit_button("Save recipe")
            if submitted:
                if not version_label or not change_note:
                    st.error("Version label and change note are required.")
                else:
                    new_version = RecipeVersion(
                        foam_grade_id=grade.id,
                        version_label=version_label,
                        effective_date=effective_date,
                        change_note=change_note,
                        approval_status=approval_status,
                        created_by=created_by,
                        ratio_index=ratio_index or None,
                        # Explicitly False at creation, not the column's own
                        # True default: the DB now enforces at most one
                        # active version per product grade (see db.py's
                        # RecipeVersion.is_active comment), so this row must
                        # not be flushed as active while the grade's current
                        # version is still active too - activate_recipe_
                        # version() below deactivates that one first, then
                        # flips this one on.
                        is_active=False,
                    )
                    session.add(new_version)
                    session.flush()
                    activate_recipe_version(session, grade.id, new_version)
                    session.commit()
                    st.success(
                        f"Recipe '{version_label}' created and set as {grade.grade_name}'s active recipe. "
                        "Add its ingredients below in the recipe version list."
                    )
                    st.rerun()

with tab_edit:
    if not page_usable:
        st.caption("View-only access - editing a recipe is restricted for your role.")
    else:
        grades_with_active = [g for g in grades if _active_version(g)]
        if not grades_with_active:
            st.info("No product grade has an active recipe yet - use 'Create Recipe' to start one.")
        else:
            grade_rows = [
                {
                    "Product grade": g.grade_name,
                    "Active version": _active_version(g).version_label,
                    "Status": _active_version(g).approval_status,
                    "Effective date": _active_version(g).effective_date,
                }
                for g in grades_with_active
            ]
            edit_idx = clickable_table(grade_rows, key="edit_recipe_grade_table")
            if edit_idx is not None and edit_idx < len(grades_with_active):
                st.session_state["edit_recipe_grade_id"] = grades_with_active[edit_idx].id
            elif st.session_state.get("edit_recipe_grade_id") not in {g.id for g in grades_with_active}:
                st.session_state.pop("edit_recipe_grade_id", None)

            selected_grade_id = st.session_state.get("edit_recipe_grade_id")
            edit_grade = next((g for g in grades_with_active if g.id == selected_grade_id), None)

            if edit_grade is None:
                st.caption("Select a product grade above to edit its recipe.")
            else:
                active_version = _active_version(edit_grade)

                ordered_components = sorted(
                    active_version.components,
                    key=lambda c: recipe_component_sort_index(c.role_in_formulation, c.raw_material_name),
                )
                components_df = (
                    pd.DataFrame(
                        [
                            {
                                "Raw material": c.raw_material_name,
                                "Supplier": c.supplier or "",
                                "php": c.php,
                                "Role": c.role_in_formulation or "",
                                "Notes": c.notes or "",
                            }
                            for c in ordered_components
                        ]
                    )
                    if active_version.components
                    else pd.DataFrame(columns=["Raw material", "Supplier", "php", "Role", "Notes"])
                )

                st.markdown("**Ingredients** — edit values directly, or use the row controls to add or remove ingredients.")
                edited_df = st.data_editor(
                    components_df,
                    num_rows="dynamic",
                    use_container_width=True,
                    key=f"edit_recipe_components_{edit_grade.id}_{active_version.id}",
                    column_config={
                        "php": st.column_config.NumberColumn("php", min_value=0.0, step=0.1, format="%.2f"),
                    },
                )

                suggested_label = next_version_label(active_version.version_label, len(edit_grade.recipe_versions))
                st.caption(f"Saving creates version **{suggested_label}** and retires the current one.")
                with st.form(f"edit_recipe_{edit_grade.id}"):
                    new_effective = st.date_input("Effective date", value=dt.date.today())
                    new_status = st.selectbox("Approval status", APPROVAL_STATUSES, index=0)
                    new_ratio_index = st.number_input(
                        "Ratio / index", min_value=0.0, step=0.01, format="%.3f",
                        value=float(active_version.ratio_index or 0.0),
                        help="Stoichiometric ratio/index for this formulation - determines the isocyanate "
                        "php. Carried over from the version being replaced; adjust if this revision changes it.",
                    )
                    save_edit = st.form_submit_button("Save as new version")
                    if save_edit:
                        clean_rows = [
                            row for _, row in edited_df.iterrows() if str(row.get("Raw material") or "").strip()
                        ]
                        if not clean_rows:
                            st.error("At least one ingredient is required.")
                        else:
                            new_label = suggested_label
                            new_change_note = summarize_recipe_component_changes(
                                active_version.components, clean_rows
                            )
                            new_created_by = user["display_name"] or user["username"] or ""
                            new_version = RecipeVersion(
                                foam_grade_id=edit_grade.id,
                                version_label=new_label,
                                effective_date=new_effective,
                                change_note=new_change_note,
                                approval_status=new_status,
                                created_by=new_created_by,
                                ratio_index=new_ratio_index or None,
                                # See the identical note in the Create tab above:
                                # must not flush as active while this grade's
                                # current version still is - the DB now enforces
                                # at most one active version per grade.
                                is_active=False,
                            )
                            session.add(new_version)
                            session.flush()
                            for row in clean_rows:
                                name = str(row["Raw material"]).strip()
                                supplier = str(row.get("Supplier") or "")
                                rm = _match_or_create_raw_material(name, supplier)
                                session.add(
                                    RecipeComponent(
                                        recipe_version_id=new_version.id,
                                        raw_material_id=rm.id if rm else None,
                                        raw_material_name=name,
                                        supplier=supplier,
                                        php=row.get("php") if pd.notna(row.get("php")) else None,
                                        role_in_formulation=str(row.get("Role") or ""),
                                        notes=str(row.get("Notes") or ""),
                                    )
                                )
                            activate_recipe_version(session, edit_grade.id, new_version)
                            session.commit()
                            st.success(
                                f"'{new_label}' saved and is now the active recipe for {edit_grade.grade_name}."
                            )
                            st.rerun()

with tab_import:
    if not page_usable:
        st.caption("View-only access - importing recipes is restricted for your role.")
    else:
        st.caption(
            "Bulk-create recipe version HEADER records only (e.g. migrating a formulation library) - "
            "not the ingredients/components inside each version. For that, see 'Bulk import recipe "
            "components' further down this page - it's a separate upload with its own Confirm import "
            "button. A grade with no active recipe yet gets its first imported row for that grade "
            "marked active automatically; anything after that is imported as historical/inactive - use "
            "'Edit Recipe' or the recipe version list at the bottom of this page to change which one is "
            "active."
        )
        show_pending_banner("recipe_version_import_msg")
        df, filename = csv_excel_uploader(
            RECIPE_VERSION_REQUIRED_COLUMNS, RECIPE_VERSION_OPTIONAL_COLUMNS, key="recipe_version_upload"
        )
        if df is not None:
            valid_grade_ids = {g.id for g in grades}
            good_rows, bad_rows = [], []
            for _, row in df.iterrows():
                if row.get("foam_grade_id") in valid_grade_ids and str(row.get("version_label", "")).strip():
                    good_rows.append(row)
                else:
                    bad_rows.append(row)

            st.write(f"Rows ready to import: **{len(good_rows)}** | Rows flagged/rejected: **{len(bad_rows)}**")
            if bad_rows:
                st.warning("Flagged rows reference an unknown foam_grade_id or have no version_label.")
                render_data_table(pd.DataFrame(bad_rows), max_height="300px")

            if good_rows and st.button("Confirm import (recipe versions)", key="confirm_recipe_version_import"):
                existing_keys = {
                    (r.foam_grade_id, r.version_label.strip().lower())
                    for r in apply_scope(session.query(RecipeVersion), RecipeVersion.foam_grade_id, grade_ids).all()
                }
                new_rows, dup_rows = dedupe_import_rows(
                    good_rows,
                    existing_keys,
                    key_func=lambda row: (int(row["foam_grade_id"]), str(row["version_label"]).strip().lower()),
                )
                grades_with_active_ids = {
                    gid
                    for (gid,) in apply_scope(
                        session.query(RecipeVersion.foam_grade_id), RecipeVersion.foam_grade_id, grade_ids
                    )
                    .filter(RecipeVersion.is_active.is_(True))
                    .all()
                }
                activated_this_batch = set()
                for row in new_rows:
                    status = str(row.get("approval_status", "") or "").strip()
                    eff_date = pd.to_datetime(row.get("effective_date"), errors="coerce")
                    gid = int(row["foam_grade_id"])
                    make_active = gid not in grades_with_active_ids and gid not in activated_this_batch
                    if make_active:
                        activated_this_batch.add(gid)
                    session.add(
                        RecipeVersion(
                            foam_grade_id=gid,
                            version_label=str(row["version_label"]).strip(),
                            effective_date=eff_date.date() if not pd.isna(eff_date) else None,
                            change_note=str(row.get("change_note", "") or ""),
                            approval_status=status if status in APPROVAL_STATUSES else "Draft",
                            created_by=str(row.get("created_by", "") or ""),
                            is_active=make_active,
                            ratio_index=row.get("ratio_index") if pd.notna(row.get("ratio_index")) else None,
                        )
                    )
                session.commit()
                msg = f"Imported {len(new_rows)} recipe version(s) from {filename}."
                if dup_rows:
                    msg += f" Skipped {len(dup_rows)} row(s) already recorded for their product grade + version label (likely a repeat click)."
                set_pending_banner("recipe_version_import_msg", msg)
                st.rerun()

# Queried once here (rather than inside the "Recipe versions" section below)
# because "Bulk import recipe components" also needs it for valid_version_ids
# - and that section now renders first, with "Recipe versions" moved to the
# bottom of the page.
versions = (
    apply_scope(session.query(RecipeVersion), RecipeVersion.foam_grade_id, grade_ids)
    .order_by(RecipeVersion.created_at.desc())
    .all()
)
version_ids = [v.id for v in versions]

# ---------------------------------------------------------------------------
# Bulk import recipe components (ingredients)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("🧪 Bulk import recipe components (ingredients)")
if not page_usable:
    st.caption("View-only access - importing recipe components is restricted for your role.")
else:
    st.caption(
        "A separate import from 'CSV / Excel import' above - that one creates recipe version "
        "headers, this one fills in the raw materials/php/role inside a version that already "
        "exists. Each row needs the recipe_version_id it belongs to (see the recipe version list "
        "at the bottom of this page for IDs) and a raw material name — unmatched raw material "
        "names are automatically added to the Raw Materials master list."
    )
    show_pending_banner("recipe_component_import_msg")
    comp_df, comp_filename = csv_excel_uploader(
        COMPONENT_REQUIRED_COLUMNS, COMPONENT_OPTIONAL_COLUMNS, key="component_upload"
    )
    if comp_df is not None:
        valid_version_ids = {v.id for v in versions}
        good_rows, bad_rows = [], []
        for _, row in comp_df.iterrows():
            if row.get("recipe_version_id") in valid_version_ids and str(row.get("raw_material_name", "")).strip():
                good_rows.append(row)
            else:
                bad_rows.append(row)

        st.write(f"Rows ready to import: **{len(good_rows)}** | Rows flagged/rejected: **{len(bad_rows)}**")
        if bad_rows:
            st.warning("Flagged rows reference an unknown recipe_version_id or have no raw_material_name.")
            render_data_table(pd.DataFrame(bad_rows), max_height="300px")

        # --- Mis-targeted-file warning (v0.70.0, Charlie's Decision 1 ruling,
        # 2026-08-19). The id check above only asks whether a recipe_version_id
        # EXISTS. On 12 August a Phase 1 import file carried a hard-coded
        # recipe_version_id of 6, which existed and belonged to an unrelated
        # polyether PUR recipe, so all nine of its polyester PIR rows passed
        # validation and merged two formulations into one version. Nothing in
        # the app was wrong; it imported exactly what the file asked for.
        #
        # What the file could not say, and the app can see, is that the target
        # version ALREADY HAS components. A bulk component import into a
        # populated version is the signature of a file pointed at the wrong id.
        # It is a warning rather than a block because deliberately topping up a
        # version is legitimate - the point is that it can no longer happen
        # without the person importing being told.
        populated_targets = {}
        for row in good_rows:
            populated_targets.setdefault(int(row["recipe_version_id"]), 0)
        if populated_targets:
            for vid, existing_count in (
                apply_scope(
                    session.query(RecipeComponent.recipe_version_id, func.count(RecipeComponent.id)),
                    RecipeComponent.recipe_version_id,
                    version_ids,
                )
                .filter(RecipeComponent.recipe_version_id.in_(list(populated_targets)))
                .group_by(RecipeComponent.recipe_version_id)
                .all()
            ):
                populated_targets[vid] = existing_count
        merge_targets = {vid: n for vid, n in populated_targets.items() if n}
        if merge_targets:
            version_labels = {v.id: v.version_label for v in versions}
            detail = ", ".join(
                f"id {vid} ({version_labels.get(vid, 'unknown')}) already has {n} component(s)"
                for vid, n in sorted(merge_targets.items())
            )
            st.warning(
                "This file adds components to a recipe version that already has some: "
                f"{detail}. Confirm the recipe_version_id in the file is the version you mean. "
                "Importing a component list into the wrong existing version merges two "
                "formulations into one and is not visible afterwards without comparing php totals."
            )

        if good_rows and st.button("Confirm import (recipe components)", key="confirm_component_import"):
            existing_keys = {
                (c.recipe_version_id, c.raw_material_name.strip().lower())
                for c in apply_scope(
                    session.query(RecipeComponent), RecipeComponent.recipe_version_id, version_ids
                ).all()
            }
            new_rows, dup_rows = dedupe_import_rows(
                good_rows,
                existing_keys,
                key_func=lambda row: (int(row["recipe_version_id"]), str(row["raw_material_name"]).strip().lower()),
            )
            for row in new_rows:
                name_val = str(row["raw_material_name"]).strip()
                supplier_val = str(row.get("supplier", "") or "")
                rm = _match_or_create_raw_material(name_val, supplier_val)
                session.add(
                    RecipeComponent(
                        recipe_version_id=int(row["recipe_version_id"]),
                        raw_material_id=rm.id if rm else None,
                        raw_material_name=name_val,
                        supplier=supplier_val,
                        php=row.get("php") if not pd.isna(row.get("php")) else None,
                        role_in_formulation=str(row.get("role_in_formulation", "") or ""),
                        notes=str(row.get("notes", "") or ""),
                    )
                )
            session.commit()
            msg = f"Imported {len(new_rows)} recipe component(s) from {comp_filename}."
            if dup_rows:
                msg += f" Skipped {len(dup_rows)} row(s) already recorded for their recipe version (likely a repeat click)."
            set_pending_banner("recipe_component_import_msg", msg)
            st.rerun()

# ---------------------------------------------------------------------------
# Recipe versions (full history + detail/edit/delete) - kept at the bottom of
# the page on purpose: Create/Edit Recipe above cover the day-to-day flow,
# this is the audit trail underneath it.
#
# CR-03 (2026-08-10): combined at the application layer with every imported
# scientific reference formulation (see module docstring above) - one list,
# one Approval Status filter, per CR-03's "the user should experience one
# Recipe list" requirement. ReferenceFormulation rows stay in their own
# table/query; nothing here writes a RecipeVersion row for them.
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Recipe versions")
st.caption(
    "Full formulation history across every product grade, plus imported scientific reference "
    "formulations (Approval Status: Pending Review until reviewed). Product Grade always reflects "
    "the actual product grade master; imported reference rows show \"N/A\" there and carry their "
    "own name under Reference Formulation instead. Click a row to view or manage details, "
    "ingredients, or delete/approve it."
)

ref_formulations = (
    session.query(ReferenceFormulation)
    .order_by(ReferenceFormulation.sort_order, ReferenceFormulation.controlled_id)
    .all()
)

status_filter = st.selectbox(
    "Approval Status",
    ["All"] + APPROVAL_STATUSES,
    key="recipe_status_filter",
    help="Filters both real recipes and imported scientific reference formulations below. "
    "Reference formulations start at Pending Review until a plant-authorized review approves them.",
)

combined = [("version", cv) for cv in versions] + [("reference", rf) for rf in ref_formulations]
if status_filter != "All":
    combined = [
        (kind, obj)
        for kind, obj in combined
        if (obj.approval_status or "Pending Review") == status_filter
    ]

if not combined:
    st.info("No recipe versions or reference formulations match this filter.")
else:
    # CR-19: Type/Product Grade/Reference Formulation are kept as distinct
    # fields so "Product Grade" can never resolve to anything but the real
    # FoamGrade master relationship. Plant Recipe rows may additionally carry
    # a linked reference formulation (the pre-existing, optional
    # RecipeVersion.reference_formulation_id "informed by" FK) as
    # supplemental context - that link is shown here, never in place of the
    # row's own Product Grade identity.
    version_rows = [
        {
            "Version": obj.version_label if kind == "version" else obj.controlled_id,
            "Type": "Plant Recipe" if kind == "version" else "Imported Reference",
            "Product Grade": (
                (obj.foam_grade.grade_name if obj.foam_grade else "—") if kind == "version" else "N/A"
            ),
            "Reference Formulation": (
                (obj.reference_formulation.name if obj.reference_formulation else "—")
                if kind == "version"
                else obj.name
            ),
            "Active": "Yes" if (kind == "version" and obj.is_active) else "No",
            "Status": obj.approval_status or ("Draft" if kind == "version" else "Pending Review"),
            "Effective date": obj.effective_date if kind == "version" else "—",
            "Created by": obj.created_by if kind == "version" else "Imported (see provenance)",
        }
        for kind, obj in combined
    ]
    idx = clickable_table(version_rows, key="recipe_versions_table")
    if idx is not None and idx < len(combined):
        sel_kind, sel_obj = combined[idx]
        st.session_state["rv_selected_kind"] = sel_kind
        st.session_state["rv_selected_id"] = sel_obj.id
    elif st.session_state.get("rv_selected_id") not in {obj.id for _, obj in combined}:
        st.session_state.pop("rv_selected_id", None)
        st.session_state.pop("rv_selected_kind", None)

    selected_id = st.session_state.get("rv_selected_id")
    selected_kind = st.session_state.get("rv_selected_kind")
    v = next((x for x in versions if x.id == selected_id), None) if selected_kind == "version" else None
    rf = next((x for x in ref_formulations if x.id == selected_id), None) if selected_kind == "reference" else None

    if v is None and rf is None:
        st.caption("Select a row above to view or manage that recipe version.")
    elif rf is not None:
        st.markdown(f"### {rf.controlled_id} — {rf.name}")
        st.warning(
            "🔒 Imported scientific reference formulation - not a plant recipe. Local material "
            "matching, safety review and validation are required before this informs production, "
            "per this record's own plant_use_rule. Visible here for technical review, comparison "
            "and PI3 reasoning only, while it stays in Pending Review.",
            icon="🔒",
        )
        st.caption(
            f"Source: {rf.source.controlled_id if rf.source else (rf.source_number or 'not recorded')}"
            + (f" ({rf.source_organisation})" if rf.source_organisation else "")
            + (f", {rf.source_location}" if rf.source_location else "")
        )
        if rf.plant_use_rule:
            st.caption(f"Use rule: {rf.plant_use_rule}")
        st.caption(f"Approval Status: `{rf.approval_status or 'Pending Review'}`")

        rf1, rf2, rf3, rf4 = st.columns(4)
        rf1.metric(
            "Reported isocyanate index",
            rf.reported_isocyanate_index if rf.reported_isocyanate_index is not None else (rf.target_index if rf.target_index is not None else "—"),
        )
        rf2.metric("Reported A:B mass ratio", rf.reported_ab_mass_ratio if rf.reported_ab_mass_ratio is not None else "—")
        rf3.metric("Free-rise density (kg/m3)", rf.reported_free_rise_density_kg_m3 if rf.reported_free_rise_density_kg_m3 is not None else "—")
        rf4.metric("Thermal conductivity (mW/m.K)", rf.reported_thermal_conductivity_mw_mk if rf.reported_thermal_conductivity_mw_mk is not None else "—")

        with st.expander("Full reported parameters"):
            detail_rows = [
                {"Field": "Chemistry", "Value": rf.chemistry.name if rf.chemistry else (rf.chemistry_label or "—")},
                {"Field": "Production method", "Value": rf.production_method.name if rf.production_method else "—"},
                {"Field": "Application", "Value": rf.application.name if rf.application else "—"},
                {"Field": "Construction", "Value": rf.construction.name if rf.construction else "—"},
                {"Field": "Formulation basis", "Value": rf.formulation_basis or "—"},
                {"Field": "Index basis", "Value": rf.index_basis or "—"},
                {"Field": "Water level", "Value": f"{rf.water_level} {rf.water_uom.name}" if rf.water_level is not None and rf.water_uom else rf.water_level},
                {"Field": "Physical blowing agent", "Value": rf.physical_blowing_agent_description or "—"},
                {"Field": "Physical blowing agent level", "Value": f"{rf.physical_blowing_agent_level} {rf.blowing_agent_uom.name}" if rf.physical_blowing_agent_level is not None and rf.blowing_agent_uom else rf.physical_blowing_agent_level},
                {"Field": "Minimum fill density (kg/m3)", "Value": rf.reported_minimum_fill_density_kg_m3},
                {"Field": "Molded core density (kg/m3)", "Value": rf.reported_molded_core_density_kg_m3},
                {"Field": "Cream time (s)", "Value": rf.reported_cream_time_s},
                {"Field": "Gel/string time (s)", "Value": rf.reported_gel_or_string_time_s},
                {"Field": "Rise time (s)", "Value": rf.reported_rise_time_s},
                {"Field": "Demold time (min)", "Value": rf.reported_demold_time_min},
                {"Field": "Mold temperature (C)", "Value": rf.reported_mold_temp_c},
                {"Field": "Open-cell content (%)", "Value": rf.reported_open_cell_content_pct},
                {"Field": "Validation status", "Value": rf.validation_status or "—"},
                {"Field": "Local material matching status", "Value": rf.local_rm_matching_status or "—"},
                {"Field": "Safety review status", "Value": rf.safety_review_status or "—"},
                {"Field": "Released to plant recipe", "Value": "Yes" if rf.release_to_plant_recipe else "No"},
            ]
            render_data_table(pd.DataFrame(detail_rows))
            if rf.technical_notes:
                st.caption(rf.technical_notes)

        st.write("**Ingredient lines**")
        rf_components = sorted(rf.components, key=lambda c: (c.sequence if c.sequence is not None else 999))
        if not rf_components:
            st.caption("No ingredient lines recorded for this reference formulation.")
        else:
            comp_rows = [
                {
                    "#": c.sequence,
                    "Material": c.material_name or c.source_component_term,
                    "Category / role": c.controlled_category_or_role or "—",
                    "Side": c.component_side or "—",
                    "Amount": c.amount_text or c.reported_amount,
                    "Basis": c.amount_basis or (c.uom.name if c.uom else "—"),
                    "Source location": c.source_location or "—",
                }
                for c in rf_components
            ]
            render_data_table(pd.DataFrame(comp_rows))

        with st.expander("Change Approval Status"):
            if not page_usable:
                st.caption("View-only access - changing approval status is restricted for your role.")
            else:
                st.caption(
                    "Any transition away from Pending Review must go through the same controlled "
                    "mechanism real recipes use - there is no separate bypass. This "
                    "never makes the formulation selectable as a grade's active production recipe; "
                    "that only ever happens by creating a real Recipe that draws on it."
                )
                with st.form(f"edit_rf_status_{rf.id}"):
                    new_rf_status = st.selectbox(
                        "Approval status", APPROVAL_STATUSES,
                        index=APPROVAL_STATUSES.index(rf.approval_status) if rf.approval_status in APPROVAL_STATUSES else APPROVAL_STATUSES.index("Pending Review"),
                        key=f"rf_status_{rf.id}",
                    )
                    if st.form_submit_button("Save approval status"):
                        rf.approval_status = new_rf_status
                        session.commit()
                        st.success(f"'{rf.controlled_id}' approval status updated to {new_rf_status}.")
                        st.rerun()
    else:
        st.markdown(
            f"### {v.version_label} — {v.foam_grade.grade_name if v.foam_grade else '—'} "
            + ("🟢 Active" if v.is_active else "")
        )
        st.caption(f"Effective {v.effective_date or '—'} | Created by {v.created_by or '—'} | Status `{v.approval_status}`")
        st.caption(
            f"Ratio / index: **{v.ratio_index:.3f}**" if v.ratio_index is not None else "Ratio / index: not set"
        )
        st.write(v.change_note)

        if not v.is_active and page_usable:
            if st.button("Set as active recipe", key=f"activate_{v.id}"):
                activate_recipe_version(session, v.foam_grade_id, v)
                session.commit()
                st.success(f"'{v.version_label}' is now the active recipe for {v.foam_grade.grade_name}.")
                st.rerun()

        with st.expander("📄 Recipe / Formulation Record report"):
            st.caption(
                "Internal-use record for this recipe version - the formulation itself, quality specs "
                "vs. actual results over a date range you choose, and cost per kg. Not for external/"
                "customer use, since it includes the formulation."
            )
            frc1, frc2 = st.columns(2)
            report_date_from = frc1.date_input(
                "Quality results from", value=dt.date.today() - dt.timedelta(days=180), key=f"formrec_from_{v.id}"
            )
            report_date_to = frc2.date_input("to", value=dt.date.today(), key=f"formrec_to_{v.id}")
            report_data = reports.build_recipe_formulation_record_data(
                session, v.id, date_from=report_date_from, date_to=report_date_to
            )

            st.write("**Formulation**")
            render_data_table(pd.DataFrame(report_data["components"] or [{"—": "No data recorded"}]))
            st.write("**Quality specs vs. results**")
            render_data_table(pd.DataFrame(report_data["quality_rows"] or [{"—": "No data recorded"}]))
            if report_data["cost_per_kg"] is not None:
                st.metric("Cost per kg", report_data["cost_per_kg"])
            else:
                st.caption("No priced components yet - cost per kg cannot be calculated.")

            st.download_button(
                "Download Word", data=reports.render_recipe_formulation_record_docx(report_data),
                file_name=f"recipe_{v.id}_formulation_record.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key=f"formrec_docx_{v.id}",
                on_click=log_export_click, args=("recipe_formulation_record_docx",),
                kwargs={"description": f"Recipe version #{v.id} ({v.version_label})"},
            )

        with st.expander("🧮 Formulation chemistry (A:B ratio, theoretical CO2, isocyanate index)"):
            st.caption(
                "Calculated from this version's own components (php dosage), using the controlled "
                "calculation definitions CALC-001, CALC-026, CALC-010/011 and CALC-015. "
                "Never guesses a missing input - a result shows 'insufficient data' with the "
                "specific reason instead of a number when something needed isn't recorded."
            )
            ab_result = analytics.recipe_version_ab_mass_ratio(session, v)
            co2_result = analytics.recipe_version_theoretical_co2(session, v)
            index_result = analytics.recipe_version_isocyanate_index(session, v)

            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                st.markdown("**A:B mass ratio**")
                # This is the LEGACY calculation. It resolves a component's side
                # from the free-text stream_assignment / role_in_formulation
                # prefix - which is uncontrolled, varies between recipes, and is
                # outside the controlled ratio path. It is left in place because
                # replacing it belongs to Decision 4, but it must not be shown
                # as if it were the controlled answer: review found it printing a
                # confident ratio a few inches below the caption saying the ratio
                # cannot be derived. Whichever number a user reads first wins,
                # and one of them is a guess.
                _controlled_roles_complete = component_role.recipe_version_is_resolved(v)
                if not _controlled_roles_complete:
                    st.warning(
                        "**No controlled A:B ratio for this version.** The components do not all "
                        "carry a controlled chemical role yet, so which side each material belongs "
                        "to is not established."
                    )
                if ab_result["computed_ratio"] is not None:
                    st.metric(
                        "Computed (uncontrolled, legacy basis)"
                        if not _controlled_roles_complete else "Computed",
                        f"{ab_result['computed_ratio']:.3f}",
                    )
                    st.caption(f"A-side {ab_result['a_side_php']:.2f} php : B-side {ab_result['b_side_php']:.2f} php")
                    if not _controlled_roles_complete:
                        st.caption(
                            "Derived from the legacy free-text side labels, not from controlled "
                            "chemical roles. Shown for reference only - do not use it as the "
                            "controlled ratio."
                        )
                else:
                    st.warning("Insufficient data - no B-side components resolved.")
                if ab_result["target_ratio"] is not None:
                    st.caption(f"Target: {ab_result['target_ratio']:.3f}")
                if ab_result["unassigned_components"]:
                    st.caption(
                        "Not assigned to a side: " + ", ".join(ab_result["unassigned_components"])
                    )

            with fc2:
                st.markdown("**Theoretical CO2 (from water)**")
                if co2_result["co2_per_100_parts"] is not None:
                    st.metric("Per 100 parts", f"{co2_result['co2_per_100_parts']:.3f}")
                    st.caption(f"Water content: {co2_result['water_php']:.3f} php")
                else:
                    st.warning(f"Insufficient data - {co2_result['reason']}")

            with fc3:
                st.markdown("**Isocyanate index**")
                st.caption(
                    f"Recorded (production): {index_result['recorded_ratio_index']:.1f}"
                    if index_result["recorded_ratio_index"] is not None
                    else "Recorded (production): not set"
                )
                if index_result["blocked"]:
                    st.warning("Cannot independently verify - see reasons below.")
                else:
                    st.metric("Re-derived from equivalent weights", f"{index_result['computed_index']:.1f}")

            if index_result["blocked"] and index_result["blocking_reasons"]:
                st.caption("Why the index can't be re-derived from equivalent weights yet:")
                for reason in index_result["blocking_reasons"]:
                    st.caption(f"- {reason}")

            st.write("**Per-component equivalent weights (CALC-010 / CALC-011)**")
            eq_rows_display = [
                {
                    "Component": r["component"],
                    "Side": r["side"],
                    "NCO %": r["nco_pct"],
                    "OH number": r["oh_number"],
                    "Equivalent weight (g/eq)": r["equivalent_weight_g_eq"],
                    "Status": r["missing_reason"] or "OK",
                }
                for r in index_result["components"]
            ]
            render_data_table(pd.DataFrame(eq_rows_display or [{"—": "No components recorded"}]))

        with st.expander("Edit details / delete this recipe version"):
            if not page_usable:
                st.caption("View-only access - editing and deleting is restricted for your role.")
            else:
                st.caption(
                    "This edits this version's own header details in place (for example, fixing a typo "
                    "or updating its approval status) - it does not create a new version. To revise the "
                    "actual formulation, use the 'Edit Recipe' tab above instead."
                )
                with st.form(f"edit_version_{v.id}"):
                    e_grade = st.selectbox(
                        "Product grade *", grades,
                        index=next((i for i, g in enumerate(grades) if g.id == v.foam_grade_id), 0),
                        format_func=lambda g: g.grade_name, key=f"edit_version_grade_{v.id}",
                    )
                    e_label = st.text_input("Version label *", value=v.version_label, key=f"edit_version_label_{v.id}")
                    e_effective = st.date_input(
                        "Effective date", value=v.effective_date or dt.date.today(), key=f"edit_version_eff_{v.id}"
                    )
                    e_change_note = st.text_area("Change note *", value=v.change_note or "", key=f"edit_version_note_{v.id}")
                    e_status = st.selectbox(
                        "Approval status", APPROVAL_STATUSES,
                        index=APPROVAL_STATUSES.index(v.approval_status) if v.approval_status in APPROVAL_STATUSES else 0,
                        key=f"edit_version_status_{v.id}",
                    )
                    e_created_by = st.text_input("Created by", value=v.created_by or "", key=f"edit_version_by_{v.id}")
                    e_ratio_index = st.number_input(
                        "Ratio / index", min_value=0.0, step=0.01, format="%.3f",
                        value=float(v.ratio_index or 0.0), key=f"edit_version_ratio_{v.id}",
                        help="Stoichiometric ratio/index for this formulation - determines the isocyanate php.",
                    )
                    if st.form_submit_button("Save changes"):
                        if not e_label.strip() or not e_change_note.strip():
                            st.error("Version label and change note are required.")
                        else:
                            v.foam_grade_id = e_grade.id
                            v.version_label = e_label.strip()
                            v.effective_date = e_effective
                            v.change_note = e_change_note
                            v.approval_status = e_status
                            v.created_by = e_created_by
                            v.ratio_index = e_ratio_index or None
                            session.commit()
                            st.success("Recipe version updated.")
                            st.rerun()

                counts = recipe_version_dependency_counts(session, v.id)
                total_related = sum(counts.values())
                if total_related:
                    detail = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
                    warning = f"Deleting this recipe version will also permanently delete {total_related} related record(s): {detail}."
                else:
                    warning = "This recipe version has no related records — deleting it is safe."

                def _do_delete_version(_session=session, _id=v.id):
                    delete_recipe_version_cascade(_session, _id)
                    _session.commit()
                    st.session_state.pop("rv_selected_id", None)

                delete_with_confirm(
                    f"Recipe version '{v.version_label}'", _do_delete_version, key_prefix=f"version_{v.id}",
                    extra_warning=warning,
                )

        with st.expander(f"Recipe components ({len(v.components)})"):
            if v.components:
                ordered_version_components = sorted(
                    v.components,
                    key=lambda c: recipe_component_sort_index(c.role_in_formulation, c.raw_material_name),
                )
                comp_rows = [
                    {
                        "Raw material": c.raw_material_name,
                        "Supplier": c.supplier,
                        "php": f"{c.php:.2f}" if c.php is not None else "",
                        "Role": c.role_in_formulation,
                        # Phase 8 Decision 3: the CONTROLLED chemical role, which
                        # is a different thing from the free-text "Role" beside
                        # it. That column says what a material does ("Gelling
                        # catalyst"); this one says which component of the
                        # formulation it is, and only when a controlled document
                        # establishes it.
                        "Chemical role": component_role.role_of(c) or "Unresolved",
                        "Notes": c.notes,
                    }
                    for c in ordered_version_components
                ]
                _unresolved = component_role.unresolved_components(v)
                if _unresolved:
                    st.caption(
                        f"{len(_unresolved)} of {len(v.components)} component(s) have no controlled "
                        "chemical role yet, so the A:B ratio cannot be derived for this version. A "
                        "role is only recorded from a controlled document - it is never inferred "
                        "from the material's category, its name or its role in the formulation."
                    )
                st.caption("Click a row to edit (and optionally delete) that component.")
                comp_idx = clickable_table(comp_rows, key=f"components_table_{v.id}")
                if comp_idx is not None and comp_idx < len(ordered_version_components):
                    st.session_state["comp_selected_id"] = ordered_version_components[comp_idx].id
                elif st.session_state.get("comp_selected_id") in {c.id for c in v.components}:
                    # a component belonging to THIS version was selected before, but the
                    # table no longer reports a selection - clear the stale reference
                    # rather than leaving a phantom edit form. Scoped to this version's
                    # own component ids so it doesn't clobber a different version's
                    # live selection elsewhere in this same loop.
                    st.session_state.pop("comp_selected_id", None)

                selected_comp_id = st.session_state.get("comp_selected_id")
                selected_comp = next((c for c in v.components if c.id == selected_comp_id), None)

                if selected_comp:
                    st.markdown(f"**Edit component: {selected_comp.raw_material_name}**")
                    if not page_usable:
                        st.caption("View-only access - editing and deleting is restricted for your role.")
                    else:
                        with st.form(f"edit_component_{selected_comp.id}"):
                            ec1, ec2, ec3 = st.columns(3)
                            e_name = ec1.text_input(
                                "Raw material name", value=selected_comp.raw_material_name, key=f"edit_comp_name_{selected_comp.id}"
                            )
                            e_supplier = ec2.text_input(
                                "Supplier", value=selected_comp.supplier or "", key=f"edit_comp_sup_{selected_comp.id}"
                            )
                            e_php = ec3.number_input(
                                "php", min_value=0.0, step=0.1, format="%.2f",
                                value=float(selected_comp.php or 0.0), key=f"edit_comp_php_{selected_comp.id}",
                            )
                            e_role = st.text_input(
                                "Role in formulation", value=selected_comp.role_in_formulation or "", key=f"edit_comp_role_{selected_comp.id}"
                            )
                            e_notes = st.text_input("Notes", value=selected_comp.notes or "", key=f"edit_comp_notes_{selected_comp.id}")
                            if st.form_submit_button("Save changes"):
                                if not e_name.strip():
                                    st.error("Raw material name is required.")
                                else:
                                    if e_name.strip() != selected_comp.raw_material_name:
                                        rm = _match_or_create_raw_material(e_name, e_supplier)
                                        selected_comp.raw_material_id = rm.id if rm else None
                                    selected_comp.raw_material_name = e_name.strip()
                                    selected_comp.supplier = e_supplier
                                    selected_comp.php = e_php or None
                                    selected_comp.role_in_formulation = e_role
                                    selected_comp.notes = e_notes
                                    session.commit()
                                    st.success("Component updated.")
                                    st.rerun()

                        def _do_delete_comp(_session=session, _id=selected_comp.id):
                            _session.query(RecipeComponent).filter(RecipeComponent.id == _id).delete(synchronize_session=False)
                            _session.commit()
                            st.session_state.pop("comp_selected_id", None)

                        _render_chemical_role_control(session, selected_comp, user)

                        delete_with_confirm(
                            f"component '{selected_comp.raw_material_name}'", _do_delete_comp,
                            key_prefix=f"comp_{selected_comp.id}",
                            extra_warning="This is a leaf record — deleting it has no other effects.",
                        )

                    if st.button("Clear selection", key=f"clear_comp_selection_{v.id}"):
                        st.session_state.pop("comp_selected_id", None)
                        st.rerun()

            if not page_usable:
                st.caption("View-only access - adding a component is restricted for your role.")
            else:
                rm_query = session.query(RawMaterial)
                if active_company_id is not None:
                    rm_query = rm_query.filter(RawMaterial.company_id == active_company_id)
                active_raw_materials = (
                    rm_query
                    .filter(RawMaterial.active.is_(True))
                    .order_by(RawMaterial.name)
                    .all()
                )
                raw_material_choice = st.selectbox(
                    "Raw material",
                    [None] + active_raw_materials,
                    format_func=lambda m: "— type a new one below —"
                    if m is None
                    else f"{m.name} ({raw_material_category_label(m)})",
                    key=f"rm_select_{v.id}",
                )
                with st.form(f"add_component_{v.id}"):
                    c1, c2, c3 = st.columns(3)
                    raw_material_other = c1.text_input(
                        "Or a new raw material not in the list above", key=f"rm_other_{v.id}"
                    )
                    supplier_default = raw_material_choice.default_supplier if raw_material_choice else ""
                    supplier = c2.text_input("Supplier", value=supplier_default or "", key=f"sup_{v.id}")
                    php = c3.number_input("php", min_value=0.0, step=0.1, format="%.2f", key=f"php_{v.id}")
                    role = st.text_input(
                        "Role in formulation (e.g. polyol, TDI, catalyst, surfactant)", key=f"role_{v.id}"
                    )
                    notes = st.text_input("Notes", key=f"notes_{v.id}")
                    add_component = st.form_submit_button("Add component")
                    if add_component:
                        final_name = raw_material_other.strip() or (
                            raw_material_choice.name if raw_material_choice else ""
                        )
                        if not final_name:
                            st.error("Pick a raw material from the list, or type a new one.")
                        else:
                            if raw_material_other.strip():
                                rm = _match_or_create_raw_material(final_name, supplier)
                            else:
                                rm = raw_material_choice
                            session.add(
                                RecipeComponent(
                                    recipe_version_id=v.id,
                                    raw_material_id=rm.id if rm else None,
                                    raw_material_name=final_name,
                                    supplier=supplier,
                                    php=php or None,
                                    role_in_formulation=role,
                                    notes=notes,
                                )
                            )
                            session.commit()
                            st.success("Component added.")
                            st.rerun()

# ---------------------------------------------------------------------------
# Where Used Report - reverse lookup: which recipes use a given raw material.
# Kept at the very bottom since it's scoped by raw material, not by any
# recipe version selected above.
# ---------------------------------------------------------------------------
st.divider()
st.subheader("📄 Where Used Report")
st.caption(
    "Pick a raw material to see every recipe version - active and retired - that uses it, the "
    "target properties of the product grades affected, and any Customer/Optimization Trial precedent "
    "tied to those recipes. Useful before considering a material substitution."
)
wu_rm_query = session.query(RawMaterial)
if active_company_id is not None:
    wu_rm_query = wu_rm_query.filter(RawMaterial.company_id == active_company_id)
wu_materials = wu_rm_query.order_by(RawMaterial.name).all()

if not wu_materials:
    st.info("No raw materials recorded yet.")
else:
    wu_material = st.selectbox(
        "Raw material", wu_materials,
        format_func=lambda m: f"{m.name} ({raw_material_category_label(m)})",
        key="where_used_material_select",
    )
    wu_data = reports.build_where_used_report_data(session, wu_material.id)

    wc1, wc2, wc3 = st.columns(3)
    wc1.metric("Recipe versions using it", wu_data["recipe_version_count"])
    wc2.metric("Product grades affected", wu_data["foam_grade_count"])
    wc3.metric("Product families affected", wu_data["product_family_count"])

    st.write("**Recipes using this material**")
    render_data_table(pd.DataFrame(wu_data["usage_rows"] or [{"—": "No data recorded"}]))
    st.write("**Target properties of affected product grades**")
    render_data_table(pd.DataFrame(wu_data["target_rows"] or [{"—": "No data recorded"}]))
    st.write("**Trial precedent**")
    render_data_table(pd.DataFrame(wu_data["trial_rows"] or [{"—": "No data recorded"}]))

    st.download_button(
        "Download Word", data=reports.render_where_used_report_docx(wu_data),
        file_name=f"where_used_{wu_data['raw_material_id']}_report.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key="where_used_docx",
        on_click=log_export_click, args=("where_used_report_docx",),
        kwargs={"description": wu_data["raw_material_name"]},
    )
