"""Screen: Expert Notes

Captures qualitative expert knowledge - the kind of thing that lives in a
technical person's head or a stray email, not a structured measurement -
linked to a production run (the common case), a product grade, a product
family (added 2026-08-02, alongside "analyze by foam family" on Trend
Analysis/Process-Property Correlation/Process Parameter Optimization - see
helpers.analysis_unit_picker), a commercial trial, or an optimization
trial (both added CR-15, 2026-08-13). This is the raw material
PI3 needs: when PI3 connectivity is enabled for the relevant plant, saving
a note here also feeds it into PI3 so future Root-Cause Assistant reasoning
can retrieve it.

Also shows PI3-sourced notes - insights a reviewer explicitly chose to
keep via a "Save to Expert Notes" button on Recipe Optimization, Trend
Analysis, Process Parameters vs Product Properties Correlation, or
Root-Cause Assistant (both
their fixed-prompt sections and free-form Ask PI3 boxes). These are
tagged with their originating question and can be re-exported as the
same Word report the reviewer originally saw.

CR-11 (Standardize Record Create, Edit/Delete and CSV/Excel Import
Functions, 2026-08-12): this page used to be a single "Add an expert note"
form followed by the notes list/report/edit-delete section, with no
CSV/Excel import at all. Restructured into the mandated 3 tabs
(Create/Edit-Delete/Import) via cr11_function_tab_labels("Expert Note"),
with the pre-existing "Expert Notes Report" (page-specific, an aggregate
breakdown rather than a record-creation function) retained as a 4th tab,
same pattern as views/9_Samples_Conditioning.py's "Sample Report" tab.
CSV/Excel import is net-new here: each row creates one note linked to an
existing production run/product grade/product family/commercial trial/
optimization trial (validated against the same scoped id sets the manual
Create tab already uses) and, exactly like a manually-added note, gets
pushed into PI3's vector store when PI3 connectivity is enabled for the
relevant plant.

CR-15 (Standardize Expert Notes Product Family Terminology and Add Trial
Links, 2026-08-13): replaced every customer-facing "Foam Family" string
in this page (and in the shared helpers it calls - see
helpers.expert_note_link_label) with "Product Family" - internal
identifiers such as the linked_entity_type value "product_family" and
CSV import's documented accepted values are unchanged, since those are
internal/compatibility identifiers, not customer-facing wording. Also
added Commercial Trial (internal linked_entity_type "customer_trial",
the existing CustomerTrial table from views/11_Customer_Trials.py) and
Optimization Trial (internal linked_entity_type "optimization_trial",
the existing OptimizationTrial table from views/12_Optimization_Trials.py)
as two new "Link to" targets, positioned after Product Family per CR-15
section 4's required order. Neither trial page's own navigation or name
was changed by this CR - only Expert Notes' ability to link to them."""

import json

import pandas as pd
import streamlit as st

import ai_assistant
import reports
from access_control import can_use_page
from auth import current_user, logout_button, require_login
from db import (
    CONFIDENCE_LEVELS,
    CustomerTrial,
    ExpertNote,
    FoamGrade,
    OptimizationTrial,
    ProductionRun,
    get_session,
    init_db,
)
from helpers import (
    clickable_table,
    company_id_for_plant,
    cr11_function_tab_labels,
    csv_excel_uploader,
    delete_with_confirm,
    expert_note_foam_grade_id_for_link,
    expert_note_link_label,
    expert_note_plant_id_for_link,
    log_export_click,
    page_setup,
    render_data_table,
    render_function_action_intro,
    set_pending_banner,
    show_pending_banner,
    view_only_notice,
)
from tenant_scope import (
    apply_scope,
    company_picker,
    customer_trial_ids_for_company,
    grade_ids_for_company,
    optimization_trial_ids_for_company,
    run_ids_for_company,
)

NOTE_REQUIRED_COLUMNS = ["linked_entity_type", "linked_entity_id", "note_text"]
NOTE_OPTIONAL_COLUMNS = ["confidence_level", "author"]

page_setup("Expert Notes")
init_db()
require_login()
logout_button()

st.title("Expert Notes")
render_function_action_intro(
    function_text=(
        "Captures qualitative expert knowledge that doesn't fit a structured field - a hunch "
        "about why a batch behaved oddly, a supplier quirk, a process tip - linked to a "
        "production run, a product grade, a product family, a commercial trial, or an "
        "optimization trial. It also shows the PI3-sourced notes "
        "a reviewer chose to keep from Recipe Optimization, Trend Analysis, Process-Property "
        "Correlation, Root-Cause Assistant, or Process Parameter Optimization, each tagged with "
        "its originating question and re-exportable as the same Word report the reviewer "
        "originally saw. When PI3 connectivity is enabled for the relevant plant, a note saved "
        "here also feeds PI3 so future free-form Ask PI3 questions and Root-Cause Assistant "
        "comparisons can retrieve it. An aggregate report further down breaks all notes in scope "
        "down by confidence level, source, and linked-entity type."
    ),
    action_text=(
        "Pick what the note is about (a production run, product grade, product family, commercial "
        "trial, or optimization trial), write it, set a "
        "confidence level, and save - there's no other structured field to fill in, so use this "
        "for anything worth remembering that the rest of the app has no place for. Use CSV/Excel "
        "import to bulk-load notes referencing existing production runs/product grades/product "
        "families/commercial trials/optimization trials from a spreadsheet. Click a PI3-sourced "
        "note to re-download its original Word report, or edit/delete any note the same way as "
        "elsewhere in the app."
    ),
)
session = get_session()
user = current_user()
page_usable = can_use_page("expert_notes", role_id=user["role_id"], session=session, is_super_admin=user["is_super_admin"])
if not page_usable:
    view_only_notice()
company, _all_companies = company_picker(
    st, session, user["is_platform_owner"], user["company_id"], key="expert_notes_company_filter"
)
active_company_id = company.id if company else None
scoped_run_ids = run_ids_for_company(session, active_company_id)
scoped_grade_ids = grade_ids_for_company(session, active_company_id)
scoped_customer_trial_ids = customer_trial_ids_for_company(session, active_company_id)
scoped_optimization_trial_ids = optimization_trial_ids_for_company(session, active_company_id)

# CR-15 (2026-08-13): required order is Production Run, Product Grade,
# Product Family, Commercial Trial, Optimization Trial. "Foam Family" is
# renamed to "Product Family" here - the customer-facing label only; the
# internal linked_entity_type value stays "product_family" (an existing
# identifier documented for CSV import, out of this CR's terminology
# scope per section 3). Commercial Trial/Optimization Trial map to the
# existing CustomerTrial/OptimizationTrial tables (internal
# linked_entity_type "customer_trial"/"optimization_trial") - CR-15 does
# not rename or restructure either trial page itself.
LINK_TYPES = {
    "Production Run": "production_run",
    "Product Grade": "foam_grade",
    "Product Family": "product_family",
    "Commercial Trial": "customer_trial",
    "Optimization Trial": "optimization_trial",
}


runs = (
    apply_scope(session.query(ProductionRun), ProductionRun.id, scoped_run_ids)
    .order_by(ProductionRun.created_at.desc())
    .all()
)
grades = (
    apply_scope(session.query(FoamGrade), FoamGrade.id, scoped_grade_ids)
    .order_by(FoamGrade.grade_name)
    .all()
)
# Product families offered here are derived from this same scoped grades
# list (any family with at least one in-scope grade), not a separate
# company scope query - keeps "what's offered to link to" consistent with
# the Product Grade option above rather than a second, possibly-diverging
# notion of company scope for families specifically.
families = sorted({g.product_family for g in grades if g.product_family}, key=lambda f: f.name)
customer_trials = (
    apply_scope(session.query(CustomerTrial), CustomerTrial.id, scoped_customer_trial_ids)
    .order_by(CustomerTrial.created_at.desc())
    .all()
)
optimization_trials = (
    apply_scope(session.query(OptimizationTrial), OptimizationTrial.id, scoped_optimization_trial_ids)
    .order_by(OptimizationTrial.created_at.desc())
    .all()
)


def _push_note_to_vector_store(entity_type, entity_id, note_text, confidence_level, author):
    """Shared push-to-PI3 logic used by both the manual Create form and the
    CSV/Excel import, so an imported note feeds PI3 exactly the same way a
    manually-added one does."""
    plant_id = expert_note_plant_id_for_link(entity_type, entity_id, session)
    if not ai_assistant.is_enabled_for_plant(session, plant_id):
        return None, plant_id
    link_label = expert_note_link_label(entity_type, entity_id, session)
    doc_text = (
        f"Expert note on {link_label}\n"
        f"Confidence: {confidence_level}\nAuthor: {author or '—'}\n\n{note_text.strip()}"
    )
    file_id = ai_assistant.push_document_to_vector_store(
        link_label,
        doc_text,
        metadata={"plant_id": plant_id, "company_id": company_id_for_plant(plant_id, session)} if plant_id else None,
    )
    return file_id, plant_id


tab_create, tab_edit_delete, tab_import, tab_report = st.tabs(
    [*cr11_function_tab_labels("Expert Note"), "Expert Notes Report"]
)

with tab_create:
    # The "Link to" selector lives outside the form on purpose: widgets inside
    # an st.form don't trigger a rerun until the form is submitted, so with it
    # inside the form, switching from "Production Run" to "Product Family"
    # would leave the wrong entity dropdown (still "Production run") showing
    # until the reviewer hit Save - by then it's too late to pick the right
    # one. Keeping it outside means the entity dropdown below updates
    # immediately.
    link_type_choice = st.selectbox("Link to *", list(LINK_TYPES.keys()), key="new_note_link_type")
    entity_type = LINK_TYPES[link_type_choice]

    with st.form("add_expert_note"):
        if entity_type == "production_run":
            if not runs:
                st.warning("No production runs yet - create one on the Production Run page first.")
            entity = st.selectbox(
                "Production run *", runs,
                format_func=lambda r: f"Run #{r.id} — {r.foam_grade.grade_name} · {r.run_date}",
            )
        elif entity_type == "foam_grade":
            if not grades:
                st.warning("No product grades yet - create one on the Product Grades page first.")
            entity = st.selectbox("Product grade *", grades, format_func=lambda g: g.grade_name)
        elif entity_type == "product_family":
            if not families:
                st.warning("No product families yet - create one on the Product Families page first.")
            entity = st.selectbox("Product family *", families, format_func=lambda f: f.name)
        elif entity_type == "customer_trial":
            if not customer_trials:
                st.warning(
                    "No commercial trials yet - create one on the Customer Trials & Samples page first."
                )
            entity = st.selectbox(
                "Commercial trial *", customer_trials,
                format_func=lambda t: f"#{t.id} — {t.customer_name} ({t.foam_grade.grade_name}, {t.status})",
            )
        else:
            if not optimization_trials:
                st.warning(
                    "No optimization trials yet - create one on the Optimization Trials & Samples page first."
                )
            entity = st.selectbox(
                "Optimization trial *", optimization_trials,
                format_func=lambda t: f"#{t.id} — {t.foam_grade.grade_name}"
                + (f" ({t.improvement_initiative_reference})" if t.improvement_initiative_reference else ""),
            )
        note_text = st.text_area("Note *")
        confidence_level = st.selectbox("Confidence level", CONFIDENCE_LEVELS, index=2)
        author = st.text_input("Author", value=user["display_name"])
        submitted = st.form_submit_button("Save note", disabled=not page_usable)
        if submitted and page_usable:
            if not entity:
                st.error("Nothing to link to - add a record of the selected type first.")
            elif not note_text.strip():
                st.error("Note text is required.")
            else:
                file_id, _plant_id = _push_note_to_vector_store(
                    entity_type, entity.id, note_text, confidence_level, author
                )
                note = ExpertNote(
                    linked_entity_type=entity_type,
                    linked_entity_id=entity.id,
                    note_text=note_text.strip(),
                    confidence_level=confidence_level,
                    author=author,
                    source="Manual",
                    vector_store_file_id=file_id,
                )
                session.add(note)
                session.commit()
                st.success("Expert note saved." + (" Fed into PI3." if file_id else ""))
                st.rerun()

with tab_import:
    if not page_usable:
        st.caption("View-only access - importing expert notes is restricted for your role.")
    else:
        show_pending_banner("expert_note_import_msg")
        # CR-15 (2026-08-13): added "customer_trial" (Commercial Trial) and
        # "optimization_trial" (Optimization Trial) as valid linked_entity_type
        # import values, alongside the 3 pre-existing types - same scoped-id
        # membership check pattern as every other type here, so an
        # out-of-scope or unknown trial id is rejected exactly like an
        # out-of-scope grade/run id always was.
        valid_ids_by_type = {
            "production_run": {r.id for r in runs},
            "foam_grade": {g.id for g in grades},
            "product_family": {f.id for f in families},
            "customer_trial": {t.id for t in customer_trials},
            "optimization_trial": {t.id for t in optimization_trials},
        }
        ndf, nfilename = csv_excel_uploader(NOTE_REQUIRED_COLUMNS, NOTE_OPTIONAL_COLUMNS, key="expert_note_upload")
        if ndf is not None:
            good_rows, bad_rows = [], []
            for _, row in ndf.iterrows():
                etype = str(row.get("linked_entity_type", "") or "").strip()
                eid = row.get("linked_entity_id")
                text_val = str(row.get("note_text", "") or "").strip()
                if etype in valid_ids_by_type and eid in valid_ids_by_type.get(etype, set()) and text_val:
                    good_rows.append(row)
                else:
                    bad_rows.append(row)

            st.write(f"Rows ready to import: **{len(good_rows)}** | Rows flagged/rejected: **{len(bad_rows)}**")
            if bad_rows:
                st.warning(
                    "Flagged rows have an unrecognized linked_entity_type (must be production_run, "
                    "foam_grade, product_family, customer_trial, or optimization_trial), reference an "
                    "id not in scope, or have no note_text."
                )
                render_data_table(pd.DataFrame(bad_rows), max_height="300px")

            if good_rows and st.button("Confirm import", key="confirm_expert_note_import"):
                imported = 0
                fed_into_pi3 = 0
                for row in good_rows:
                    etype = str(row["linked_entity_type"]).strip()
                    eid = int(row["linked_entity_id"])
                    text_val = str(row["note_text"]).strip()
                    confidence = str(row.get("confidence_level", "") or "").strip()
                    if confidence not in CONFIDENCE_LEVELS:
                        confidence = CONFIDENCE_LEVELS[2]
                    author_val = str(row.get("author", "") or "").strip() or user["display_name"]
                    file_id, _plant_id = _push_note_to_vector_store(etype, eid, text_val, confidence, author_val)
                    if file_id:
                        fed_into_pi3 += 1
                    session.add(
                        ExpertNote(
                            linked_entity_type=etype,
                            linked_entity_id=eid,
                            note_text=text_val,
                            confidence_level=confidence,
                            author=author_val,
                            source="Manual",
                            vector_store_file_id=file_id,
                        )
                    )
                    imported += 1
                session.commit()
                msg = f"Imported {imported} expert note(s) from {nfilename}."
                if fed_into_pi3:
                    msg += f" {fed_into_pi3} fed into PI3."
                set_pending_banner("expert_note_import_msg", msg)
                st.rerun()

with tab_report:
    # ---------------------------------------------------------------------
    # Expert Notes Report (Context / Analysis / Conclusions) - an always-
    # visible aggregate, page-specific and retained per CR-11 (not one of
    # the mandatory 3), distinct from the per-note "Download as Word"
    # button on the Edit/Delete tab (that button re-exports one PI3-sourced
    # note's own original report; this is a standing breakdown across every
    # note in scope).
    # ---------------------------------------------------------------------
    all_notes = session.query(ExpertNote).order_by(ExpertNote.created_at.desc()).all()
    if active_company_id is None:
        notes_for_report = all_notes
    else:
        scoped_run_id_set = set(scoped_run_ids) if scoped_run_ids else set()
        scoped_grade_id_set = set(scoped_grade_ids) if scoped_grade_ids else set()
        scoped_family_id_set = {f.id for f in families}
        # CR-15: scope the two new trial link types the same way every
        # other type here already is - against this same company's own
        # customer_trials/optimization_trials lists computed above.
        scoped_customer_trial_id_set = {t.id for t in customer_trials}
        scoped_optimization_trial_id_set = {t.id for t in optimization_trials}
        notes_for_report = [
            n
            for n in all_notes
            if (n.linked_entity_type == "production_run" and n.linked_entity_id in scoped_run_id_set)
            or (n.linked_entity_type == "foam_grade" and n.linked_entity_id in scoped_grade_id_set)
            or (n.linked_entity_type == "product_family" and n.linked_entity_id in scoped_family_id_set)
            or (n.linked_entity_type == "customer_trial" and n.linked_entity_id in scoped_customer_trial_id_set)
            or (n.linked_entity_type == "optimization_trial" and n.linked_entity_id in scoped_optimization_trial_id_set)
        ]

    st.subheader("Expert Notes Report")
    en_scope_label = company.name if company else "All companies"
    st.caption(f"Context, analysis, and conclusions for expert notes in scope: {en_scope_label}.")
    expert_notes_report_data = reports.build_expert_notes_report_data(session, notes_for_report, en_scope_label)
    en_rc1, en_rc2 = st.columns(2)
    en_rc1.metric("Total notes", expert_notes_report_data["total"])
    en_rc2.metric(
        "Fed into PI3",
        f"{expert_notes_report_data['in_pi3_count']} of {expert_notes_report_data['total']}"
        if expert_notes_report_data["total"] else "—",
    )
    st.download_button(
        "Download Word", data=reports.render_expert_notes_report_docx(expert_notes_report_data),
        file_name="expert_notes_report.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key="expert_notes_report_docx",
        on_click=log_export_click, args=("expert_notes_report_docx",),
        kwargs={"description": en_scope_label},
    )

with tab_edit_delete:
    st.divider()
    st.subheader("Expert notes")

    all_notes = session.query(ExpertNote).order_by(ExpertNote.created_at.desc()).all()
    if active_company_id is None:
        notes = all_notes
    else:
        # ExpertNote is polymorphic (linked_entity_type + linked_entity_id can
        # point at a production run, product grade, product family, commercial
        # trial, or optimization trial - the last two added CR-15, 2026-08-13).
        # Scope each kind against the id set already computed above for that
        # company. Missing the product_family branch here would make any note
        # PI3 saved from a "product family" analysis (see analysis_unit_picker,
        # helpers.py) invisible to the very company that created it - not just
        # a cosmetic gap, a real "where did my note go" bug. The same applies
        # to the two trial branches now that they're valid link targets too.
        scoped_run_id_set = set(scoped_run_ids) if scoped_run_ids else set()
        scoped_grade_id_set = set(scoped_grade_ids) if scoped_grade_ids else set()
        scoped_family_id_set = {f.id for f in families}
        scoped_customer_trial_id_set = {t.id for t in customer_trials}
        scoped_optimization_trial_id_set = {t.id for t in optimization_trials}
        notes = [
            n
            for n in all_notes
            if (n.linked_entity_type == "production_run" and n.linked_entity_id in scoped_run_id_set)
            or (n.linked_entity_type == "foam_grade" and n.linked_entity_id in scoped_grade_id_set)
            or (n.linked_entity_type == "product_family" and n.linked_entity_id in scoped_family_id_set)
            or (n.linked_entity_type == "customer_trial" and n.linked_entity_id in scoped_customer_trial_id_set)
            or (n.linked_entity_type == "optimization_trial" and n.linked_entity_id in scoped_optimization_trial_id_set)
        ]

    if not notes:
        st.info("No expert notes recorded yet.")
    else:
        note_rows = [
            {
                "Linked to": expert_note_link_label(n.linked_entity_type, n.linked_entity_id, session),
                "Note": (n.note_text[:120] + "…") if len(n.note_text) > 120 else n.note_text,
                "Source": n.source or "Manual",
                "Confidence": n.confidence_level,
                "Author": n.author or "",
                "Created": n.created_at,
                "In PI3": "Yes" if n.vector_store_file_id else "No",
            }
            for n in notes
        ]
        st.caption("Click a row to edit (and optionally delete) that note.")
        idx = clickable_table(note_rows, key="expert_notes_table")
        if idx is not None and idx < len(notes):
            st.session_state["note_selected_id"] = notes[idx].id
        else:
            st.session_state.pop("note_selected_id", None)

        selected_id = st.session_state.get("note_selected_id")
        selected = next((n for n in notes if n.id == selected_id), None)

        if selected:
            st.markdown(
                f"**Edit note on {expert_note_link_label(selected.linked_entity_type, selected.linked_entity_id, session)}**"
            )
            if selected.source == "PI3":
                st.caption(f"Source: PI3, from the question “{selected.pi3_question or '—'}”")
                grade_id = expert_note_foam_grade_id_for_link(selected.linked_entity_type, selected.linked_entity_id, session)
                grade = session.get(FoamGrade, grade_id) if grade_id else None
                plant_id = expert_note_plant_id_for_link(selected.linked_entity_type, selected.linked_entity_id, session)
                report_data = reports.build_pi3_qa_report_data(
                    question=selected.pi3_question,
                    answer=selected.note_text,
                    tool_log=json.loads(selected.pi3_tool_log_json) if selected.pi3_tool_log_json else [],
                    plant_name=reports.plant_label(session, plant_id),
                    foam_grade_name=grade.grade_name if grade else None,
                    asked_by=selected.author,
                    asked_at=selected.created_at,
                )
                st.download_button(
                    "Download as Word (.docx)",
                    data=reports.render_pi3_qa_report_docx(report_data),
                    file_name=f"pi3_report_expert_note_{selected.id}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"expert_note_{selected.id}_download_docx",
                    on_click=log_export_click, args=("expert_note_pi3_docx",),
                    kwargs={"description": f"Expert Note #{selected.id}"},
                )
            with st.form(f"edit_note_{selected.id}"):
                e_text = st.text_area("Note *", value=selected.note_text, key=f"edit_note_text_{selected.id}")
                e_confidence = st.selectbox(
                    "Confidence level", CONFIDENCE_LEVELS,
                    index=CONFIDENCE_LEVELS.index(selected.confidence_level) if selected.confidence_level in CONFIDENCE_LEVELS else 2,
                    key=f"edit_note_conf_{selected.id}",
                )
                e_author = st.text_input("Author", value=selected.author or "", key=f"edit_note_author_{selected.id}")
                if st.form_submit_button("Save changes", disabled=not page_usable) and page_usable:
                    if not e_text.strip():
                        st.error("Note text is required.")
                    else:
                        plant_id = expert_note_plant_id_for_link(selected.linked_entity_type, selected.linked_entity_id, session)
                        if ai_assistant.is_enabled_for_plant(session, plant_id):
                            if selected.vector_store_file_id:
                                ai_assistant.delete_document_from_vector_store(selected.vector_store_file_id)
                            link_label = expert_note_link_label(selected.linked_entity_type, selected.linked_entity_id, session)
                            doc_text = (
                                f"Expert note on {link_label}\n"
                                f"Confidence: {e_confidence}\nAuthor: {e_author or '—'}\n\n{e_text.strip()}"
                            )
                            selected.vector_store_file_id = ai_assistant.push_document_to_vector_store(
                                link_label,
                                doc_text,
                                metadata={"plant_id": plant_id, "company_id": company_id_for_plant(plant_id, session)}
                                if plant_id
                                else None,
                            )
                        selected.note_text = e_text.strip()
                        selected.confidence_level = e_confidence
                        selected.author = e_author
                        session.commit()
                        st.success("Expert note updated.")
                        st.rerun()

            def _do_delete_note(_session=session, _id=selected.id, _file_id=selected.vector_store_file_id):
                if _file_id:
                    ai_assistant.delete_document_from_vector_store(_file_id)
                _session.query(ExpertNote).filter(ExpertNote.id == _id).delete(synchronize_session=False)
                _session.commit()
                st.session_state.pop("note_selected_id", None)

            if page_usable:
                delete_with_confirm(
                    "this expert note", _do_delete_note, key_prefix=f"note_{selected.id}",
                    extra_warning=(
                        "This is a leaf record — deleting it has no other effects (its copy in "
                        "PI3, if any, is removed too)."
                    ),
                )
            else:
                st.caption("View-only access - deleting is restricted for your role.")

            if st.button("Clear selection", key="clear_note_selection"):
                st.session_state.pop("note_selected_id", None)
                st.rerun()
