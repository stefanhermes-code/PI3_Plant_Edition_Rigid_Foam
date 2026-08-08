"""Screen 29: Reference Formulations

Read-only view of Charlie's RF-* locked public parameter summaries (patent
and literature examples, imported in the WP5 reconciliation as
PI3_Rigid_Foam_Reference_Formulations_10_MASTER_LINKED.xlsx - 10 rows, ~100
ingredient lines). Added 2026-08-08 for WP6-S06 DEF-006 ("reference
formulation provenance" had no live display anywhere despite the data
existing since the WP5 reconciliation, see VAL-023).

Deliberately view-only, with no Add/Edit/Delete anywhere on this page: per
ReferenceFormulation.plant_use_rule ("Reference only; local material
matching, safety review and validation required") and db.py's own module
note, these rows are a locked external reference, never a plant recipe -
this app already has a real create/edit workflow for actual formulations
(the Recipes page). A reference formulation only ever gets INTO a real
recipe via RecipeVersion.reference_formulation_id, an explicit "informed
by" link a user sets on the Recipes page - never by editing or copying a
row here. Kept visually distinct from Recipes on purpose (separate nav
entry, separate icon, no version/approval workflow, an explicit provenance
caption on every card) so it can never be mistaken for a plant recipe.

Not company-scoped: these are Charlie's shared public-reference library,
not any one tenant's data - every company sees the same 10 rows, the same
way every company sees the same controlled vocabulary tables.
"""

import pandas as pd
import streamlit as st

from auth import logout_button, require_login
from db import ReferenceFormulation, get_session, init_db
from helpers import clickable_table, render_data_table, render_function_action_intro, page_setup

page_setup("Reference Formulations")
init_db()
require_login()
logout_button()

st.title("Reference Formulations")
render_function_action_intro(
    function_text=(
        "A read-only library of locked public reference formulations (patent and literature "
        "examples) with their reported ingredient lines, index, blowing system, and where "
        "available reported density/thermal/timing values - each with its own source citation. "
        "These are never a plant recipe: they exist purely as external comparison points."
    ),
    action_text=(
        "Browse the list below and select one to see its full ingredient breakdown and reported "
        "parameters. To use a reference formulation as a starting point for a real recipe, link it "
        "explicitly from the Recipes page ('Reference formulation' field) - it is never copied or "
        "edited here."
    ),
)

session = get_session()

formulations = session.query(ReferenceFormulation).order_by(ReferenceFormulation.sort_order, ReferenceFormulation.controlled_id).all()

if not formulations:
    st.info("No reference formulations recorded yet.")
    st.stop()

st.warning(
    "🔒 Locked public reference data - not a plant recipe. Local material matching, safety review "
    "and validation are required before any of this informs production, per each record's own "
    "plant_use_rule.",
    icon="🔒",
)

list_rows = [
    {
        "ID": rf.controlled_id,
        "Name": rf.name,
        "Chemistry": rf.chemistry.name if rf.chemistry else (rf.chemistry_label or "—"),
        "Index": rf.reported_isocyanate_index if rf.reported_isocyanate_index is not None else rf.target_index,
        "A:B ratio": rf.reported_ab_mass_ratio,
        "Source": rf.source.controlled_id if rf.source else (rf.source_number or "—"),
        "Status": rf.record_status or "—",
    }
    for rf in formulations
]
idx = clickable_table(list_rows, key="reference_formulations_table")
if idx is not None and idx < len(formulations):
    st.session_state["ref_formulation_selected_id"] = formulations[idx].id
elif st.session_state.get("ref_formulation_selected_id") not in {rf.id for rf in formulations}:
    st.session_state.pop("ref_formulation_selected_id", None)

selected_id = st.session_state.get("ref_formulation_selected_id")
rf = next((x for x in formulations if x.id == selected_id), None)

if rf is None:
    st.caption("Select a row above to view its full ingredient breakdown and reported parameters.")
else:
    st.divider()
    st.markdown(f"### {rf.controlled_id} — {rf.name}")
    st.caption(
        f"Source: {rf.source.controlled_id if rf.source else (rf.source_number or 'not recorded')}"
        + (f" ({rf.source_organisation})" if rf.source_organisation else "")
        + (f", {rf.source_location}" if rf.source_location else "")
    )
    if rf.plant_use_rule:
        st.caption(f"Use rule: {rf.plant_use_rule}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Reported isocyanate index", rf.reported_isocyanate_index if rf.reported_isocyanate_index is not None else (rf.target_index if rf.target_index is not None else "—"))
    m2.metric("Reported A:B mass ratio", rf.reported_ab_mass_ratio if rf.reported_ab_mass_ratio is not None else "—")
    m3.metric("Free-rise density (kg/m3)", rf.reported_free_rise_density_kg_m3 if rf.reported_free_rise_density_kg_m3 is not None else "—")
    m4.metric("Thermal conductivity (mW/m.K)", rf.reported_thermal_conductivity_mw_mk if rf.reported_thermal_conductivity_mw_mk is not None else "—")

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
    components = sorted(rf.components, key=lambda c: (c.sequence if c.sequence is not None else 999))
    if not components:
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
            for c in components
        ]
        render_data_table(pd.DataFrame(comp_rows))
