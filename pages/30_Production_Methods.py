"""Production Methods (new page, CR-01 - UI Navigation and Rigid-Foam
Terminology for UAT, implemented 2026-08-10).

Per CR-01 section on the new sidebar structure: Production Method becomes a
first-class navigation section, not a picker buried inside another form.
This page:

1. Shows the Production Methods activated for a selected plant (moved here
   from the old "Plant & Foam Equipment Overview" page - see
   pages/1_Plant_Installation_Overview.py's docstring for why: activation is
   a Production Method concern, not a Plant-identity one).
2. Shows concise counts per activated method: Production Units (Machines at
   this plant tagged with this method), Product Grades (grades whose
   DERIVED Production Method set - see helpers.grade_production_methods,
   the architecture-correction batch immediately before this CR - includes
   this method), and Recipes (RecipeVersion rows under those grades). Kept
   deliberately concise per CR-01 - no per-run/per-sample counts here, that
   detail lives on the operational pages themselves.
3. Gates which methods any user may activate at all, per Charlie's Phase 1
   maturity/release table: only is_released methods (PM-100 and PM-800 as
   of CR-21, 2026-08-15) are activatable via this checkbox - read live from
   ProductionMethod.is_released, never a hardcoded name or count, so this
   page needed no code change when CR-21 added PM-800. CR-04 step 6 (2026-08-10)
   originally exempted the platform-owner company from this gate; CR-06
   (2026-08-11) removed that exemption after a UAT finding showed it let a
   Platform Admin write unreleased methods into live plant configuration -
   every plant, including HTC Global's own, is gated identically now. See
   helpers.method_activatable_by_customer.

REMOVED 2026-08-10 (CR-04 step 6, per Charlie's explicit instruction to
remove the global Operating Context concept from the application
entirely, not merely stop persisting it): this page used to let a user
"Set as operating context" one activated method for the browser tab
(st.session_state["pm_context_plant_id"]/["pm_context_method_id"]), which
pages/31_Production_Equipment.py read back to default its own Plant/
Production Method pickers. That session-level soft default is gone -
every page's pickers now default plainly (first plant/method in the list)
with no cross-page session state at all. This resolves the ambiguity
flagged in JC's PM reconciliation audit decisively in favour of full
removal, per Charlie's own instruction.

Controlled-ID-to-customer-name mapping: ProductionMethod.name already IS the
customer-facing name (e.g. "Discontinuous Panel & Board Production", the
CR-21/2026-08-15 approved name for PM-100); controlled_id (e.g. "PM-100")
is shown alongside it for traceability, matching the same existing pattern
already used everywhere else in the app.

CR-09 correction (2026-08-12, Remove Internal Development and UAT Leakage
from Customer-Facing Application): this docstring used to claim, per
CR-01's "keeps dev-phase numbers internal only" requirement, that no
Phase-1..7 label was ever shown here - that claim was false. The
not-yet-released caption below used to read the method's raw internal
maturity_status string and literally say "Phase 1 offers Production
Method PM-100 only.", a genuine regression CR-09's UAT audit caught. It
now routes through customer_presentation.customer_facing_method_
availability_note(), the single shared translation function every
customer-facing surface in the app uses for this - see that module's
docstring. The release gate itself (method.is_released,
helpers.method_activatable_by_customer) is unchanged; only the caption
shown when a method fails that gate is different.
"""

import streamlit as st

import customer_presentation
from access_control import can_use_page
from auth import current_user, logout_button, require_login
from db import FoamGrade, Machine, Plant, PlantProductionMethod, RecipeVersion, get_session, init_db
from helpers import (
    all_production_methods,
    method_activatable_by_customer,
    page_setup,
    render_function_action_intro,
    view_only_notice,
)
from tenant_scope import apply_scope, company_picker, plant_ids_for_company

page_setup("Production Methods")
init_db()
require_login()
logout_button()

st.title("Production Methods")
render_function_action_intro(
    function_text=(
        "This shows which Production Methods are activated at a plant. Each activated method's "
        "card shows a concise count of Production Units, Product Grades, and Recipes within that "
        "method - a Product Grade can legitimately span more than one method (via its Production "
        "Unit assignments), so a grade may be counted under more than one method here."
    ),
    action_text=(
        "Pick a plant, then activate every Production Method it actually runs using the checkboxes "
        "below. Only Production Methods that have been released for customer activation can be "
        "checked - the other methods are shown for visibility but stay disabled until released."
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

selected_plant = st.selectbox(
    "Plant *", plants, index=0, format_func=lambda p: p.name, key="pm_plant_picker"
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

if not all_methods:
    st.info("No controlled Production Methods are defined yet.")
else:
    for method in all_methods:
        already_active = method.id in activated_ids
        # CR-06 (2026-08-11): no is_platform_owner exception here anymore -
        # see helpers.method_activatable_by_customer's docstring. HTC
        # Global's own plants are gated exactly like a customer's.
        can_activate = method_activatable_by_customer(method)
        checked = st.checkbox(
            f"{method.name} ({method.controlled_id})",
            value=already_active,
            key=f"pm_activate_{selected_plant.id}_{method.id}",
            disabled=not page_usable or (not can_activate and not already_active),
        )
        if not can_activate and not already_active:
            st.caption(customer_presentation.customer_facing_method_availability_note())
        existing_row = existing_rows_by_method.get(method.id)
        if checked and can_activate and not existing_row:
            session.add(PlantProductionMethod(plant_id=selected_plant.id, production_method_id=method.id, active=True))
            session.commit()
            st.rerun()
        elif checked and can_activate and existing_row and not existing_row.active:
            existing_row.active = True
            session.commit()
            st.rerun()
        elif not checked and existing_row and existing_row.active:
            existing_row.active = False
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
            c1, c2, c3 = st.columns(3)
            c1.metric("Production Units", units_count)
            c2.metric("Product Grades", len(grade_ids_for_method))
            c3.metric("Recipes", recipes_count)
            st.divider()
