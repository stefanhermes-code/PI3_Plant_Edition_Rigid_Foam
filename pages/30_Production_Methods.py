"""Production Methods (new page, CR-01 - UI Navigation and Rigid-Foam
Terminology for UAT, implemented 2026-08-10).

Per CR-01 section on the new sidebar structure: Production Method becomes a
first-class navigation section, not a picker buried inside another form.
This page:

1. Shows the Production Methods activated for a selected plant (moved here
   from the old "Plant & Foam Equipment Overview" page - see
   pages/1_Plant_Installation_Overview.py's docstring for why: activation is
   a Production Method concern, not a Plant-identity one).
2. Lets a user select one activated method as the "operating context" for
   this browser tab - stored in st.session_state under
   "pm_context_plant_id" / "pm_context_method_id". Production Equipment
   (pages/31_Production_Equipment.py) reads this context to default its own
   Plant/Production Method filters, without gating - a user can still pick
   a different plant/method there directly.
3. Shows concise counts per activated method: Production Units (Machines at
   this plant tagged with this method), Product Grades (grades whose
   DERIVED Production Method set - see helpers.grade_production_methods,
   the architecture-correction batch immediately before this CR - includes
   this method), and Recipes (RecipeVersion rows under those grades). Kept
   deliberately concise per CR-01 - no per-run/per-sample counts here, that
   detail lives on the operational pages themselves.

Controlled-ID-to-customer-name mapping: ProductionMethod.name already IS the
customer-facing name (e.g. "Discontinuous Factory Foaming"); controlled_id
(e.g. "PM-100") is shown alongside it for traceability, matching the same
existing pattern already used everywhere else in the app.  Per CR-01's
explicit "keeps dev-phase numbers internal only" requirement, no
Phase-1..7 label is ever shown here - the phase mapping is JC/Charlie's own
internal engineering scoping reference and has no customer-facing purpose.
"""

import streamlit as st

from access_control import can_use_page
from auth import current_user, logout_button, require_login
from db import FoamGrade, Machine, Plant, PlantProductionMethod, RecipeVersion, get_session, init_db
from helpers import all_production_methods, page_setup, render_function_action_intro, view_only_notice
from tenant_scope import apply_scope, company_picker, plant_ids_for_company

page_setup("Production Methods")
init_db()
require_login()
logout_button()

st.title("Production Methods")
render_function_action_intro(
    function_text=(
        "This is the operating-context home for Production Method: it shows which Production "
        "Methods are activated at a plant, and lets you set one as the working context for this "
        "session so Production Equipment, Product Grades, data entry, and reporting can default to "
        "it. Each activated method's card shows a concise count of Production Units, Product "
        "Grades, and Recipes within that method - a Product Grade can legitimately span more than "
        "one method (via its Production Unit assignments), so a grade may be counted under more "
        "than one method here."
    ),
    action_text=(
        "Pick a plant, then activate every Production Method it actually runs using the checkboxes "
        "below. Once at least one method is activated, click 'Set as operating context' on the "
        "method you're working in - Production Equipment and other pages will default to it. Clear "
        "the context at any time to go back to seeing everything for the plant."
    ),
)
session = get_session()
user = current_user()
page_usable = can_use_page("production_methods", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()

company_filter, _all_companies = company_picker(
    st, session, user["is_platform_owner"], user["company_id"], key="pm_company_filter"
)
company_id = company_filter.id if company_filter else None
plant_ids = plant_ids_for_company(session, company_id)

plants = apply_scope(session.query(Plant), Plant.id, plant_ids).order_by(Plant.name).all()

if not plants:
    st.warning("Add a plant first (Plants page) before activating Production Methods.")
    st.stop()

# Default the plant picker to the current operating context's plant, if one
# is already set for this browser tab, so returning here doesn't lose it.
_context_plant_id = st.session_state.get("pm_context_plant_id")
_default_plant_index = next((i for i, p in enumerate(plants) if p.id == _context_plant_id), 0)
selected_plant = st.selectbox(
    "Plant *", plants, index=_default_plant_index, format_func=lambda p: p.name, key="pm_plant_picker"
)

st.divider()
st.subheader(f"Production Methods activated at {selected_plant.name}")
if not page_usable:
    st.caption("View-only access - activating/deactivating Production Methods is restricted for your role.")

all_methods = all_production_methods(session)
existing_rows_by_method = {
    r.production_method_id: r
    for r in session.query(PlantProductionMethod)
    .filter(PlantProductionMethod.plant_id == selected_plant.id)
    .all()
}
activated_ids = {mid for mid, row in existing_rows_by_method.items() if row.active}

_context_method_id = (
    st.session_state.get("pm_context_method_id")
    if st.session_state.get("pm_context_plant_id") == selected_plant.id
    else None
)

if not all_methods:
    st.info("No controlled Production Methods are defined yet.")
else:
    for method in all_methods:
        checked = st.checkbox(
            f"{method.name} ({method.controlled_id})",
            value=method.id in activated_ids,
            key=f"pm_activate_{selected_plant.id}_{method.id}",
            disabled=not page_usable,
        )
        existing_row = existing_rows_by_method.get(method.id)
        if checked and not existing_row:
            session.add(PlantProductionMethod(plant_id=selected_plant.id, production_method_id=method.id, active=True))
            session.commit()
            st.rerun()
        elif checked and existing_row and not existing_row.active:
            existing_row.active = True
            session.commit()
            st.rerun()
        elif not checked and existing_row and existing_row.active:
            existing_row.active = False
            # Clear the operating context if the method being deactivated
            # was the one currently selected - an inactive method shouldn't
            # stay silently selected as everyone's working context.
            if _context_method_id == method.id:
                st.session_state.pop("pm_context_method_id", None)
                st.session_state.pop("pm_context_plant_id", None)
            session.commit()
            st.rerun()

        if checked:
            # --- Concise per-method counts ------------------------------
            units_count = (
                session.query(Machine)
                .filter(Machine.plant_id == selected_plant.id, Machine.production_method_id == method.id)
                .count()
            )
            # Grades whose DERIVED method set includes this method - i.e.
            # any grade with at least one Machine at this plant tagged with
            # this method. A grade can appear under more than one method,
            # per the architecture correction (grade_production_methods).
            grade_ids_for_method = {
                g.id
                for g in session.query(FoamGrade)
                .join(FoamGrade.machines)
                .filter(Machine.plant_id == selected_plant.id, Machine.production_method_id == method.id)
                .all()
            }
            recipes_count = (
                session.query(RecipeVersion).filter(RecipeVersion.foam_grade_id.in_(grade_ids_for_method)).count()
                if grade_ids_for_method
                else 0
            )
            c1, c2, c3, c4 = st.columns([1, 1, 1, 1.4])
            c1.metric("Production Units", units_count)
            c2.metric("Product Grades", len(grade_ids_for_method))
            c3.metric("Recipes", recipes_count)
            with c4:
                st.markdown("")
                is_context = (
                    st.session_state.get("pm_context_plant_id") == selected_plant.id
                    and st.session_state.get("pm_context_method_id") == method.id
                )
                if is_context:
                    st.success("Operating context ✓")
                elif st.button("Set as operating context", key=f"pm_set_context_{selected_plant.id}_{method.id}"):
                    st.session_state["pm_context_plant_id"] = selected_plant.id
                    st.session_state["pm_context_method_id"] = method.id
                    st.rerun()
            st.divider()

if st.session_state.get("pm_context_method_id"):
    _ctx_method = next((m for m in all_methods if m.id == st.session_state["pm_context_method_id"]), None)
    _ctx_plant = next((p for p in plants if p.id == st.session_state.get("pm_context_plant_id")), None)
    if _ctx_method and _ctx_plant:
        st.info(
            f"Current operating context: **{_ctx_plant.name} → {_ctx_method.name} "
            f"({_ctx_method.controlled_id})**. Production Equipment and other pages default to this."
        )
        if st.button("Clear operating context"):
            st.session_state.pop("pm_context_plant_id", None)
            st.session_state.pop("pm_context_method_id", None)
            st.rerun()
