"""Production Equipment (new page, CR-01 - UI Navigation and Rigid-Foam
Terminology for UAT, implemented 2026-08-10).

Moved here from the old "Plant & Foam Equipment Overview" page (see
views/1_Plant_Installation_Overview.py's docstring) per CR-01's approved
sidebar structure: Production Equipment now resolves inside the selected
Production Method's own context, under the new "Production Methods" nav
section, rather than sitting under Plant Setup.

Terminology per CR-01's mandatory table: "Machine / foaming line" ->
"Production Unit or Cell" in every user-visible label on this page. The
backend entity name (db.Machine) and its columns are unchanged - only
labels/captions change, per CR-01's "implementation note: backend entity
name may stay" guidance for this exact rename.

REMOVED 2026-08-10 (CR-04 step 6, per Charlie's instruction to remove the
global Operating Context concept entirely): this page used to default its
Plant/Production Method pickers to the session-level context set on
views/30_Production_Methods.py. That cross-page session state is gone -
pickers here now default plainly to the first plant/method in the list.

CR-11 (Standardize Record Create, Edit/Delete and CSV/Excel Import
Functions, 2026-08-12): this page used to be a single "Add Production
Unit / Cell" expander followed by the equipment table/edit panel, with no
CSV/Excel import at all. Restructured into the mandated 3 tabs
(Create/Edit-Delete/Import) via cr11_function_tab_labels("Production Unit
/ Cell", "Production Units / Cells"). The net-new CSV/Excel import
requires plant_id and production_method_id columns (validated the same
way the manual Create tab's pickers narrow: the method must be one this
row's plant has actually activated - see activated_methods_for_plant) -
importing bulk equipment is still subject to the same plant/method
prerequisite the manual form enforces, just expressed as numeric ids
instead of two dependent dropdowns.

Phase 8 Decision 2 (Machine-Stream Configuration, 2026-08-19): this page
gained the controlled A/B-stream editor. It sits inside the Edit/Delete
tab under the selected Production Unit / Cell rather than as a fourth
CR-11 tab, because a configuration has no meaning without a machine - it
is a versioned attribute of one machine, not a record type of its own.
See the block comment above _render_machine_stream_configuration."""

import datetime as dt

import pandas as pd
import streamlit as st

from access_control import can_use_page
from auth import current_user, logout_button, require_login
from cascades import unlink_machine_dependents
from db import (
    MACHINE_OEMS,
    MAXFOAM_MODELS,
    OTHER_LAADER_BERG_MODEL,
    Machine,
    MachineStreamAssignment,
    MachineStreamConfiguration,
    Plant,
    ProductionRun,
    get_session,
    init_db,
)
from helpers import (
    MATERIAL_DELIVERY_MODES,
    activated_methods_for_plant,
    clickable_table,
    cr11_function_tab_labels,
    csv_excel_uploader,
    dedupe_import_rows,
    delete_with_confirm,
    page_setup,
    parse_bool,
    render_data_table,
    render_function_action_intro,
    set_pending_banner,
    show_pending_banner,
    view_only_notice,
)
import machine_stream as ms
from tenant_scope import apply_scope, company_picker, plant_ids_for_company

MACHINE_REQUIRED_COLUMNS = ["plant_id", "production_method_id", "name"]
MACHINE_OPTIONAL_COLUMNS = ["machine_code", "oem", "model", "active", "notes"]

page_setup("Production Equipment")
init_db()
require_login()
logout_button()

st.title("Production Equipment")
render_function_action_intro(
    function_text=(
        "This is where you set up and maintain the Production Units/Cells (foaming lines/metering "
        "machines) at each plant, each tagged with the Production Method it runs under. Process "
        "parameters (conveyor speed, tunnel width, laydown mode, etc.) connect to the specific "
        "equipment that produced them - a production run picks one of these."
    ),
    action_text=(
        "Pick a plant, then add each Production Unit/Cell with its Production Method, OEM, and "
        "model. A plant needs at least one activated Production Method (set on the Production "
        "Methods page) before you can add equipment to it. Use CSV/Excel import to bulk-load "
        "equipment referencing an existing plant_id and one of that plant's activated "
        "production_method_id values. Click a row in the Edit/Delete tab's table to edit or "
        "delete a Production Unit/Cell - deleting one only unlinks it from any production runs "
        "that reference it."
    ),
)
session = get_session()
user = current_user()
page_usable = can_use_page("plant_overview", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()

company_filter, _all_companies = company_picker(
    st, session, user["is_platform_owner"], user["company_id"], key="pe_company_filter"
)
plant_ids = plant_ids_for_company(session, company_filter.id if company_filter else None)
plants = apply_scope(session.query(Plant), Plant.id, plant_ids).order_by(Plant.name).all()

if not plants:
    st.info("Add a plant first (Plants page) before adding Production Equipment.")
    st.stop()

_default_plant_index = 0


def _machine_model_picker(oem, current_model, key_prefix):
    """Model input for the Add/Edit forms below. Called *before* opening
    the surrounding st.form - widgets inside a form don't trigger a rerun
    until submit, so if OEM lived inside the form, switching it wouldn't
    swap this field until after Save - when OEM is Laader Berg this offers
    a controlled dropdown of the known Maxfoam generations, with a
    free-text fallback for any generation not in that list; every other
    OEM stays plain free text as before."""
    if oem == "Laader Berg":
        default_index = MAXFOAM_MODELS.index(current_model) if current_model in MAXFOAM_MODELS else 0
        choice = st.selectbox("Model", MAXFOAM_MODELS, index=default_index, key=f"{key_prefix}_model_choice")
        if choice == OTHER_LAADER_BERG_MODEL:
            other_default = current_model if current_model and current_model not in MAXFOAM_MODELS else ""
            return st.text_input("Model (specify)", value=other_default, key=f"{key_prefix}_model_other")
        return choice
    return st.text_input("Model", value=current_model or "", key=f"{key_prefix}_model_text")


# ---------------------------------------------------------------------------
# Phase 8 Decision 2: machine-stream configuration (2026-08-19)
#
# Charlie's ruling put the A/B-to-chemical-role mapping on the MACHINE, not on
# the plant and not on the recipe, because it is a property of how one machine
# is plumbed. There is no plant-wide rule that stream A carries isocyanate -
# two machines in the same plant can run opposite conventions, and a machine
# can be re-plumbed, which is why the mapping is versioned with a validity
# period instead of being a single column on machines.
#
# The control rules live in machine_stream.py, not here. This section is the
# editor: it collects values, calls that module, and renders what it says. A
# Draft may be incomplete; everything is checked at activation (ruling R6).
# Active and Superseded revisions are frozen - a change is a new revision,
# which is what keeps a production run's stamp meaning what it meant on the
# day it was stamped.
# ---------------------------------------------------------------------------

_MSC_UNSET = "— not set —"


def _msc_label(configuration):
    period = (
        f"{configuration.effective_from:%Y-%m-%d %H:%M} → "
        f"{configuration.effective_to:%Y-%m-%d %H:%M}"
        if configuration.effective_to
        else f"{configuration.effective_from:%Y-%m-%d %H:%M} → open-ended"
    )
    return f"Rev {configuration.revision} · {configuration.status} · {period}"


def _msc_readonly_summary(configuration):
    st.write(
        f"Stream **A** carries: **{ms.role_for_stream(configuration, 'A') or _MSC_UNSET}**  \n"
        f"Stream **B** carries: **{ms.role_for_stream(configuration, 'B') or _MSC_UNSET}**"
    )
    st.caption(
        f"{configuration.controlled_id or '—'} · revision {configuration.revision} · "
        f"{configuration.status} · valid from {configuration.effective_from} to "
        f"{configuration.effective_to or 'open-ended'} (UTC)  \n"
        f"Source reference: {configuration.source_reference or '—'} · "
        f"Approved by: {configuration.approved_by or '—'} · "
        f"Approved at: {configuration.approved_at or '—'}"
    )
    if configuration.notes:
        st.caption(f"Notes: {configuration.notes}")


def _msc_apply_assignments(session, configuration, role_a, role_b):
    """Rewrite both stream assignments in one pass.

    Deliberately clears both before inserting either: swapping A and B would
    otherwise trip the one-role-per-configuration unique constraint halfway
    through, because the old A row still holds the role the new B row wants.
    """
    configuration.assignments.clear()
    session.flush()
    for stream_label, chemical_role in (("A", role_a), ("B", role_b)):
        if chemical_role:
            configuration.assignments.append(
                MachineStreamAssignment(stream_label=stream_label, chemical_role=chemical_role)
            )
    session.flush()


def _render_machine_stream_configuration(session, machine, page_usable):
    st.divider()
    st.markdown("**Machine-stream configuration (A/B streams to chemical roles)**")
    st.caption(
        "Which physical stream on this Production Unit / Cell carries which chemical role. "
        "This is a property of the machine's plumbing, not of the formulation, and it is not "
        "the same on every machine — so it is recorded per machine and per validity period, "
        "and a production run is stamped with the revision that applied when it started. "
        "All times are UTC."
    )

    configurations = (
        session.query(MachineStreamConfiguration)
        .filter(MachineStreamConfiguration.machine_id == machine.id)
        .order_by(MachineStreamConfiguration.revision.desc())
        .all()
    )

    if configurations:
        render_data_table(
            pd.DataFrame(
                [
                    {
                        "Configuration": c.controlled_id or "—",
                        "Rev": c.revision,
                        "Status": c.status,
                        "Effective from (UTC)": c.effective_from,
                        "Effective to (UTC)": c.effective_to or "open-ended",
                        "Stream A carries": ms.role_for_stream(c, "A") or "—",
                        "Stream B carries": ms.role_for_stream(c, "B") or "—",
                        "Source reference": c.source_reference or "—",
                        "Approved by": c.approved_by or "—",
                    }
                    for c in configurations
                ]
            ),
            max_height="260px",
        )
    else:
        st.info(
            "No machine-stream configuration recorded for this Production Unit / Cell yet. "
            "Production runs on it read as Unresolved, and no A:B ratio is derived for them, "
            "until a configuration is activated."
        )

    if not page_usable:
        st.caption("View-only access — creating and activating configurations is restricted for your role.")
        return

    if st.button("New draft revision", key=f"msc_new_{machine.id}"):
        now = dt.datetime.utcnow().replace(microsecond=0)
        draft = MachineStreamConfiguration(
            controlled_id=ms.next_controlled_id(session),
            machine_id=machine.id,
            revision=ms.next_revision(session, machine.id),
            effective_from=now,
            status=ms.STATUS_DRAFT,
        )
        session.add(draft)
        session.commit()
        st.session_state[f"msc_selected_{machine.id}"] = draft.id
        st.rerun()

    if not configurations:
        return

    stored_id = st.session_state.get(f"msc_selected_{machine.id}")
    default_index = next((i for i, c in enumerate(configurations) if c.id == stored_id), 0)
    configuration = st.selectbox(
        "Revision to work on",
        configurations,
        index=default_index,
        format_func=_msc_label,
        key=f"msc_pick_{machine.id}",
    )
    st.session_state[f"msc_selected_{machine.id}"] = configuration.id

    if configuration.status != ms.STATUS_DRAFT:
        _msc_readonly_summary(configuration)
        if configuration.status == ms.STATUS_ACTIVE:
            st.caption(
                "An Active configuration is frozen. To change the mapping, supersede it below "
                "and create a new draft revision."
            )
            with st.form(f"msc_supersede_{configuration.id}"):
                st.markdown("**Supersede this revision**")
                end_date = st.date_input("Effective to (date, UTC) *", key=f"msc_sup_date_{configuration.id}")
                end_time = st.time_input("Effective to (time, UTC) *", key=f"msc_sup_time_{configuration.id}")
                if st.form_submit_button("Supersede"):
                    effective_to = dt.datetime.combine(end_date, end_time)
                    try:
                        ms.supersede(session, configuration, effective_to)
                        session.commit()
                        st.success(
                            f"Revision {configuration.revision} superseded with effect from "
                            f"{effective_to} (UTC). Production runs already stamped against it are unchanged."
                        )
                        st.rerun()
                    except (ms.ConfigurationFrozen, ValueError) as exc:
                        session.rollback()
                        st.error(str(exc))
        else:
            st.caption("A Superseded configuration is a historical record and cannot be edited.")
        return

    role_options = [_MSC_UNSET] + list(ms.CHEMICAL_ROLES)
    current_a = ms.role_for_stream(configuration, "A") or _MSC_UNSET
    current_b = ms.role_for_stream(configuration, "B") or _MSC_UNSET
    now = dt.datetime.utcnow().replace(microsecond=0)
    approved_default = configuration.approved_at or now
    end_default = configuration.effective_to or configuration.effective_from

    with st.form(f"msc_draft_{configuration.id}"):
        st.markdown(f"**Draft {configuration.controlled_id or ''} · revision {configuration.revision}**")
        left, right = st.columns(2)
        with left:
            from_date = st.date_input("Effective from (date, UTC) *", value=configuration.effective_from.date())
            from_time = st.time_input("Effective from (time, UTC) *", value=configuration.effective_from.time())
            open_ended = st.checkbox("Open-ended (no end)", value=configuration.effective_to is None)
            to_date = st.date_input("Effective to (date, UTC)", value=end_default.date())
            to_time = st.time_input("Effective to (time, UTC)", value=end_default.time())
        with right:
            role_a = st.selectbox(
                "Stream A carries", role_options, index=role_options.index(current_a)
            )
            role_b = st.selectbox(
                "Stream B carries", role_options, index=role_options.index(current_b)
            )
            st.caption(
                "There is no default here on purpose. Read it off the machine's commissioning "
                "or calibration record — assuming A is isocyanate is exactly the error this "
                "table exists to prevent."
            )
        source_reference = st.text_input(
            "Source reference *",
            value=configuration.source_reference or "",
            help="The commissioning report, calibration record or approval that establishes this mapping.",
        )
        approved_by = st.text_input("Approved by *", value=configuration.approved_by or "")
        approved_date = st.date_input("Approved at (date, UTC) *", value=approved_default.date())
        approved_time = st.time_input("Approved at (time, UTC) *", value=approved_default.time())
        notes = st.text_area("Notes", value=configuration.notes or "")
        saved = st.form_submit_button("Save draft")
        activate_clicked = st.form_submit_button("Save and activate")

        if saved or activate_clicked:
            chosen_a = None if role_a == _MSC_UNSET else role_a
            chosen_b = None if role_b == _MSC_UNSET else role_b
            if chosen_a is not None and chosen_a == chosen_b:
                st.error(
                    "Stream A and stream B cannot carry the same chemical role — one is the "
                    "isocyanate component and the other is the polyol blend component."
                )
            else:
                configuration.effective_from = dt.datetime.combine(from_date, from_time)
                configuration.effective_to = None if open_ended else dt.datetime.combine(to_date, to_time)
                configuration.source_reference = source_reference.strip()
                configuration.approved_by = approved_by.strip()
                configuration.approved_at = dt.datetime.combine(approved_date, approved_time)
                configuration.notes = notes
                _msc_apply_assignments(session, configuration, chosen_a, chosen_b)
                if activate_clicked:
                    try:
                        ms.activate(session, configuration)
                    except ms.ActivationRefused as refusal:
                        session.rollback()
                        st.error("This revision cannot be activated yet:")
                        for problem in refusal.problems:
                            st.error(f"• {problem}")
                    else:
                        session.commit()
                        st.success(
                            f"Revision {configuration.revision} is now Active. It is frozen — a "
                            "later change is a new revision."
                        )
                        st.rerun()
                else:
                    session.commit()
                    st.success("Draft saved. It is not in force until it is activated.")
                    st.rerun()

    def _discard_draft(_session=session, _id=configuration.id, _machine_id=machine.id):
        _session.query(MachineStreamConfiguration).filter(
            MachineStreamConfiguration.id == _id
        ).delete(synchronize_session=False)
        _session.commit()
        st.session_state.pop(f"msc_selected_{_machine_id}", None)

    delete_with_confirm(
        f"draft revision {configuration.revision}",
        _discard_draft,
        key_prefix=f"msc_draft_{configuration.id}",
        extra_warning="A draft has never been in force, so discarding it affects no production run.",
    )


tab_create, tab_edit_delete, tab_import = st.tabs(
    cr11_function_tab_labels("Production Unit / Cell", "Production Units / Cells")
)

with tab_create:
    if not page_usable:
        st.caption("View-only access - adding Production Equipment is restricted for your role.")
    else:
        # Plant, Production Method, OEM and Model all live outside the
        # st.form below - each one's choice narrows the next, and widgets
        # inside a form don't rerun until submit, so none of that narrowing
        # could happen live if they lived inside it.
        plant_for_machine = st.selectbox(
            "Plant *", plants, index=_default_plant_index, format_func=lambda p: p.name, key="add_machine_plant"
        )
        plant_methods = activated_methods_for_plant(session, plant_for_machine.id)
        if not plant_methods:
            st.warning(
                "This plant has no activated Production Methods yet. Enable one on the Production "
                "Methods page before adding Production Equipment."
            )
            method_choice = None
        else:
            method_choice = st.selectbox(
                "Production Method *", plant_methods, format_func=lambda m: m.name,
                index=0, key="add_machine_method",
            )
        oem = st.selectbox("OEM / manufacturer", MACHINE_OEMS, key="add_machine_oem")
        model = _machine_model_picker(oem, "", "add_machine")
        with st.form("add_machine"):
            name = st.text_input("Production Unit / Cell name * (e.g. Line 1, Maxfoam A)")
            machine_code = st.text_input("Code")
            st.caption(
                f"Plant: **{plant_for_machine.name}** · Production Method: "
                f"**{method_choice.name if method_choice else '—'}** · "
                f"OEM: **{oem}** · Model: **{model or '—'}** (change above, outside this form)"
            )
            # R-PRE-WP1 (2026-08-20): how this unit gets material into the
            # mix. Optional on purpose - "not declared" is the default and
            # keeps every module available, so nobody has to answer this
            # before they can create equipment.
            delivery_mode = st.selectbox(
                "Material delivery mode",
                [""] + list(MATERIAL_DELIVERY_MODES),
                format_func=lambda m: "— not declared —" if m == "" else m,
                help=(
                    "Governs whether the material-metering module applies to runs on this "
                    "unit. Leave undeclared to keep every module available."
                ),
                key="add_machine_delivery_mode",
            )
            active = st.checkbox("Active", value=True)
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Save Production Unit / Cell", disabled=method_choice is None)
            if submitted:
                if not name:
                    st.error("Production Unit / Cell name is required.")
                elif method_choice is None:
                    st.error("Activate a Production Method for this plant first.")
                else:
                    session.add(
                        Machine(
                            plant_id=plant_for_machine.id,
                            name=name,
                            machine_code=machine_code,
                            oem=oem,
                            model=model,
                            active=active,
                            notes=notes,
                            production_method_id=method_choice.id,
                            material_delivery_mode=delivery_mode or None,
                        )
                    )
                    session.commit()
                    st.success(f"Production Unit / Cell '{name}' added.")
                    st.rerun()

with tab_import:
    if not page_usable:
        st.caption("View-only access - importing Production Equipment is restricted for your role.")
    else:
        show_pending_banner("machine_import_msg")
        plants_by_id = {p.id: p for p in plants}
        # activated_methods_for_plant is per-plant, so build the valid
        # (plant_id, production_method_id) pairs across every in-scope
        # plant up front rather than re-querying per row.
        valid_method_ids_by_plant = {
            p.id: {m.id for m in activated_methods_for_plant(session, p.id)} for p in plants
        }
        mdf, mfilename = csv_excel_uploader(MACHINE_REQUIRED_COLUMNS, MACHINE_OPTIONAL_COLUMNS, key="machine_upload")
        if mdf is not None:
            good_rows, bad_rows = [], []
            for _, row in mdf.iterrows():
                plant_id_val = row.get("plant_id")
                method_id_val = row.get("production_method_id")
                name_val = str(row.get("name", "") or "").strip()
                plant_ok = plant_id_val in plants_by_id
                method_ok = plant_ok and method_id_val in valid_method_ids_by_plant.get(plant_id_val, set())
                if plant_ok and method_ok and name_val:
                    good_rows.append(row)
                else:
                    bad_rows.append(row)

            st.write(f"Rows ready to import: **{len(good_rows)}** | Rows flagged/rejected: **{len(bad_rows)}**")
            if bad_rows:
                st.warning(
                    "Flagged rows reference an unknown plant_id, a production_method_id not "
                    "activated for that plant, or have no name."
                )
                render_data_table(pd.DataFrame(bad_rows), max_height="300px")

            if good_rows and st.button("Confirm import", key="confirm_machine_import"):
                existing_keys = {
                    (m.plant_id, m.name.strip().lower())
                    for m in session.query(Machine).filter(Machine.plant_id.in_([p.id for p in plants])).all()
                }
                new_rows, dup_rows = dedupe_import_rows(
                    good_rows,
                    existing_keys,
                    key_func=lambda row: (int(row["plant_id"]), str(row["name"]).strip().lower()),
                )
                for row in new_rows:
                    session.add(
                        Machine(
                            plant_id=int(row["plant_id"]),
                            production_method_id=int(row["production_method_id"]),
                            name=str(row["name"]).strip(),
                            machine_code=str(row.get("machine_code", "") or ""),
                            oem=str(row.get("oem", "") or ""),
                            model=str(row.get("model", "") or ""),
                            active=True if pd.isna(row.get("active")) else parse_bool(row.get("active")),
                            notes=str(row.get("notes", "") or ""),
                        )
                    )
                session.commit()
                msg = f"Imported {len(new_rows)} Production Unit(s)/Cell(s) from {mfilename}."
                if dup_rows:
                    msg += f" Skipped {len(dup_rows)} row(s) already recorded for their plant (likely a repeat click)."
                set_pending_banner("machine_import_msg", msg)
                st.rerun()

with tab_edit_delete:
    st.divider()
    st.subheader("Production Units / Cells")
    st.caption(
        "Process parameters (conveyor speed, tunnel width, laydown mode, etc.) connect to the "
        "specific equipment that produced them. A production run picks one of these."
    )

    machines = (
        session.query(Machine)
        .filter(Machine.plant_id.in_([p.id for p in plants]))
        .order_by(Machine.plant_id, Machine.name)
        .all()
    )
    if not machines:
        st.info("No Production Units/Cells recorded yet.")
    else:
        machine_rows = [
            {
                "Plant": m.plant.name,
                "Production Method": m.production_method.name if m.production_method else "—",
                "Production Unit / Cell": m.name,
                "Code": m.machine_code or "—",
                "OEM": m.oem or "—",
                "Model": m.model or "—",
                "Active": m.active,
                "Notes": m.notes or "",
            }
            for m in machines
        ]
        st.caption("Click a row to edit (and optionally delete) that Production Unit / Cell.")
        idx = clickable_table(machine_rows, key="machines_table")
        if idx is not None and idx < len(machines):
            st.session_state["machine_selected_id"] = machines[idx].id
        else:
            st.session_state.pop("machine_selected_id", None)

        selected_machine_id = st.session_state.get("machine_selected_id")
        selected_machine = next((m for m in machines if m.id == selected_machine_id), None)

        if selected_machine:
            st.markdown(f"**Edit Production Unit / Cell: {selected_machine.name}**")
            if not page_usable:
                st.caption("View-only access - editing and deleting is restricted for your role.")
            else:
                # e_oem/e_model live outside the form, same reason as the
                # Add picker above.
                e_plant = st.selectbox(
                    "Plant *", plants,
                    index=next((i for i, p in enumerate(plants) if p.id == selected_machine.plant_id), 0),
                    format_func=lambda p: p.name, key=f"edit_machine_plant_{selected_machine.id}",
                )
                e_plant_methods = activated_methods_for_plant(session, e_plant.id)
                current_method = selected_machine.production_method
                if not e_plant_methods:
                    st.warning(
                        "This plant has no activated Production Methods yet. Enable one on the "
                        "Production Methods page."
                    )
                    e_method_choice = None
                else:
                    e_method_choice = st.selectbox(
                        "Production Method *", e_plant_methods, format_func=lambda m: m.name,
                        index=next((i for i, m in enumerate(e_plant_methods) if current_method and m.id == current_method.id), 0),
                        key=f"edit_machine_method_{selected_machine.id}",
                    )
                e_oem = st.selectbox(
                    "OEM / manufacturer", MACHINE_OEMS,
                    index=MACHINE_OEMS.index(selected_machine.oem) if selected_machine.oem in MACHINE_OEMS else 0,
                    key=f"edit_machine_oem_{selected_machine.id}",
                )
                e_model = _machine_model_picker(e_oem, selected_machine.model, f"edit_machine_{selected_machine.id}")
                with st.form(f"edit_machine_{selected_machine.id}"):
                    e_name = st.text_input(
                        "Production Unit / Cell name *", value=selected_machine.name, key=f"edit_machine_name_{selected_machine.id}"
                    )
                    e_code = st.text_input(
                        "Code", value=selected_machine.machine_code or "", key=f"edit_machine_code_{selected_machine.id}"
                    )
                    st.caption(
                        f"Plant: **{e_plant.name}** · Production Method: "
                        f"**{e_method_choice.name if e_method_choice else '—'}** · "
                        f"OEM: **{e_oem}** · Model: **{e_model or '—'}** (change above, outside this form)"
                    )
                    _mode_options = [""] + list(MATERIAL_DELIVERY_MODES)
                    _current_mode = selected_machine.material_delivery_mode or ""
                    # An unrecognised stored value is shown rather than
                    # silently reset to "not declared" - the same principle
                    # the historical-readability rule applies elsewhere: a
                    # value already recorded stays selectable.
                    if _current_mode and _current_mode not in _mode_options:
                        _mode_options.append(_current_mode)
                    e_delivery_mode = st.selectbox(
                        "Material delivery mode",
                        _mode_options,
                        index=_mode_options.index(_current_mode),
                        format_func=lambda m: "— not declared —" if m == "" else m,
                        help=(
                            "Governs whether the material-metering module applies to runs on this "
                            "unit. Leave undeclared to keep every module available."
                        ),
                        key=f"edit_machine_delivery_mode_{selected_machine.id}",
                    )
                    e_active = st.checkbox("Active", value=selected_machine.active, key=f"edit_machine_active_{selected_machine.id}")
                    e_notes = st.text_area("Notes", value=selected_machine.notes or "", key=f"edit_machine_notes_{selected_machine.id}")
                    if st.form_submit_button("Save changes", disabled=e_method_choice is None):
                        if not e_name.strip():
                            st.error("Production Unit / Cell name is required.")
                        elif e_method_choice is None:
                            st.error("Activate a Production Method for this plant first.")
                        else:
                            selected_machine.plant_id = e_plant.id
                            selected_machine.name = e_name.strip()
                            selected_machine.machine_code = e_code
                            selected_machine.oem = e_oem
                            selected_machine.model = e_model
                            selected_machine.active = e_active
                            selected_machine.notes = e_notes
                            selected_machine.production_method_id = e_method_choice.id
                            selected_machine.material_delivery_mode = e_delivery_mode or None
                            session.commit()
                            st.success("Production Unit / Cell updated.")
                            st.rerun()

                linked_runs = session.query(ProductionRun).filter(ProductionRun.machine_id == selected_machine.id).count()
                if linked_runs:
                    warning = (
                        f"{linked_runs} production run(s) reference this Production Unit / Cell. Deleting it will "
                        "unlink them (the runs stay, the equipment reference is cleared), not delete those runs."
                    )
                else:
                    warning = "No production runs reference this Production Unit / Cell — deleting it is safe."

                def _do_delete_machine(_session=session, _id=selected_machine.id):
                    unlink_machine_dependents(_session, _id)
                    _session.query(Machine).filter(Machine.id == _id).delete(synchronize_session=False)
                    _session.commit()
                    st.session_state.pop("machine_selected_id", None)

                delete_with_confirm(
                    f"'{selected_machine.name}'", _do_delete_machine, key_prefix=f"machine_{selected_machine.id}",
                    extra_warning=warning,
                )

            _render_machine_stream_configuration(session, selected_machine, page_usable)

            if st.button("Clear selection", key="clear_machine_selection"):
                st.session_state.pop("machine_selected_id", None)
                st.rerun()
