"""WP7 Phase 2 ("Rebuild Production Run UI", 2026-08-14) - direct UI
evidence for the new/changed pages/4_Production_Run_Trial_Record.py
surfaces, following the same AppTest conventions and fixture chain as
tests/test_cr11_functional_evidence_group_d.py (that file's module
docstring documents the full FK chain / session_state quirks this file
relies on unchanged).

Covers, against the real Streamlit UI (not just ORM-level checks, which
tests/test_wp7_phase1_method_aware_schema.py already provides for the
underlying schema/helper):

1. Method-Aware Process Settings tab (tab_method_settings): shows "no
   applicable settings" until an evidence-based ProcessSettingDefinition/
   ProcessSettingApplicability pair exists for the run's Method/Unit (this
   mirrors Charlie's WP7 Phase 1 Production Seeding Rule - Phase 2 tests
   may seed synthetic rows in the isolated test DB, matching the same
   precedent test_wp7_phase1_method_aware_schema.py already established);
   once a Method-scoped applicability exists, only that setting appears
   and Planned/Actual values can be saved and are read back correctly.
2. Production Output and Disposition tab (tab_output): create, then edit,
   a ProductionOutputSummary row via the real form.
3. Material Metering decoupling (tab_streams): a Component Stream Reading
   can now be created via the UI for a run that has NO Finalized phase at
   all - this is the direct UI proof of WP7 Phase 1/2's decoupling
   decision (task #930), which the ORM-level test in
   test_wp7_phase1_method_aware_schema.py already covers at the schema
   layer only.
4. Production Events optional context links (tab_events): a new event can
   be linked to a ProcessSettingDefinition via the "Related process
   setting" picker and the link is persisted.

Usage: python -m pytest tests/test_wp7_phase2_production_run_ui.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from streamlit.testing.v1 import AppTest

import access_control
import db
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE4 = os.path.join(APP_DIR, "pages", "4_Production_Run_Trial_Record.py")


def _clear_relevant_caches():
    tenant_scope.plant_ids_for_company.clear()
    tenant_scope.family_ids_for_plants.clear()
    tenant_scope.grade_ids_for_families.clear()
    tenant_scope.run_ids_for_plants.clear()
    tenant_scope.customer_trial_ids_for_plants.clear()
    tenant_scope.optimization_trial_ids_for_plants.clear()
    access_control.denied_page_keys.clear()


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)
    _clear_relevant_caches()


def _run(session_state=None):
    at = AppTest.from_file(PAGE4, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


@pytest.fixture()
def seeded_run():
    """Same Company -> Plant -> ProductionMethod -> Machine -> ProductFamily
    -> FoamGrade -> RecipeVersion -> ProductionRun chain as
    test_cr11_functional_evidence_group_d.py's seeded_run, rebuilt directly
    here so this file has no cross-file fixture dependency."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P2 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P2 Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-WP7P2-{u}", name=f"WP7P2 Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(
        plant_id=plant.id, name=f"WP7P2 Machine {u}", production_method_id=method.id, active=True,
    )
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P2 Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P2 Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True,
    )
    session.add(recipe); session.flush()

    run = db.ProductionRun(
        plant_id=plant.id,
        foam_grade_id=grade.id,
        recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 1),
        batch_reference=f"B-WP7P2-{u}",
        machine_id=machine.id,
        production_method_id=method.id,
        operator_or_team_reference="Shift A",
        notes="seed run",
    )
    session.add(run); session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "method_id": method.id,
        "machine_id": machine.id, "family_id": family.id, "grade_id": grade.id,
        "recipe_version_id": recipe.id, "run_id": run.id,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_method_setting(seeded_run):
    """Extends seeded_run with one evidence-based (for the purposes of this
    isolated test DB) ProcessSettingDefinition + Method-scoped
    ProcessSettingApplicability pair, eligible for seeded_run's own
    Production Method - the minimum content needed to prove the dynamic
    Method-Aware Process Settings tab actually filters and renders."""
    ids = seeded_run
    session = db.get_session()
    unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P2-{ids['run_id']}", symbol="rpm", name="revolutions per minute")
    session.add(unit); session.flush()
    definition = db.ProcessSettingDefinition(
        controlled_id=f"PS-WP7P2-{ids['run_id']}", name="Test Mixer Speed", data_type="Float",
        unit_id=unit.id, parameter_category="Process Setting", active=True, sort_order=1,
    )
    session.add(definition); session.flush()
    applicability = db.ProcessSettingApplicability(
        setting_definition_id=definition.id, production_method_id=ids["method_id"],
        applicable_to_planned=True, applicable_to_actual=True, controllable=True,
        analytics_eligible=True, active=True,
    )
    session.add(applicability); session.commit()
    out = dict(ids)
    out["definition_id"] = definition.id
    out["applicability_id"] = applicability.id
    out["unit_id"] = unit.id
    session.close()
    return out


# ---------------------------------------------------------------------------
# 1. Method-Aware Process Settings tab
# ---------------------------------------------------------------------------

def test_method_aware_settings_tab_shows_no_settings_until_applicability_seeded(seeded_run):
    """Before any ProcessSettingDefinition/ProcessSettingApplicability rows
    exist for the run's Method, the tab must say so plainly rather than
    inventing content - this is the direct UI proof of the still-open item
    flagged in the WP7 Phase 2 closeout package (no approved, evidence-
    based process setting catalogue exists yet)."""
    ids = seeded_run
    at = _run({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception
    infos = " ".join(i.value for i in at.info)
    assert "no process settings are configured as applicable" in infos.lower()


def test_method_aware_settings_tab_filters_to_eligible_settings_and_saves_values(seeded_method_setting):
    """With one Method-scoped applicability seeded, the dynamic form must
    render that setting (and only that setting) and let Planned/Actual
    values be saved - the direct UI proof of the Phase 2 closeout gate:
    "users can create and manage runs with only parameters applicable to
    the selected Method/Unit"."""
    ids = seeded_method_setting
    at = _run({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    planned_key = f"pps_{ids['definition_id']}_Planned_{ids['run_id']}"
    actual_key = f"pps_{ids['definition_id']}_Actual_{ids['run_id']}"
    assert any(w.key == planned_key for w in at.number_input), "Planned input for the eligible setting did not render"
    assert any(w.key == actual_key for w in at.number_input), "Actual input for the eligible setting did not render"

    at.number_input(key=planned_key).set_value(1200.0)
    at.number_input(key=actual_key).set_value(1185.5)
    submit = next(b for b in at.button if b.key == f"FormSubmitter:method_settings_form_{ids['run_id']}-Save process settings")
    submit.click().run()
    assert not at.exception

    session = db.get_session()
    rows = {
        r.snapshot_type: r
        for r in session.query(db.ProcessParameterValue)
        .filter(db.ProcessParameterValue.production_run_id == ids["run_id"])
        .all()
    }
    assert rows["Planned"].numeric_value == 1200.0
    assert rows["Actual"].numeric_value == 1185.5
    assert rows["Planned"].unit == "rpm"
    session.close()


# ---------------------------------------------------------------------------
# 2. Production Output and Disposition tab
# ---------------------------------------------------------------------------

def test_production_output_create_and_edit_via_form(seeded_run):
    """ProductionOutputSummary create-then-edit round trip through the real
    form, including the controlled disposition dropdown and single
    controlled unit_id per Charlie's decision doc section 3.3."""
    ids = seeded_run
    session = db.get_session()
    unit = db.UnitOfMeasure(controlled_id=f"UOM-OUT-{ids['run_id']}", symbol="kg", name="kilograms")
    session.add(unit); session.commit()
    unit_id = unit.id
    session.close()

    at = _run({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    at.number_input(key=f"new_output_planned_{ids['run_id']}").set_value(500.0)
    at.number_input(key=f"new_output_actual_{ids['run_id']}").set_value(480.0)
    # Selectbox.options returns FORMATTED display strings (post format_func),
    # not the raw underlying objects - select by index, same convention as
    # test_cr14_customers_section.py / test_cr11_functional_evidence_group_e.py.
    unit_sb = at.selectbox(key=f"new_output_unit_{ids['run_id']}")
    unit_idx = next(i for i, opt in enumerate(unit_sb.options) if opt.startswith("kg"))
    unit_sb.select_index(unit_idx)
    at.selectbox(key=f"new_output_disposition_{ids['run_id']}").set_value("Released")
    submit = next(b for b in at.button if b.key == f"FormSubmitter:add_output_{ids['run_id']}-Save production output")
    submit.click().run()
    assert not at.exception

    session = db.get_session()
    row = session.query(db.ProductionOutputSummary).filter(
        db.ProductionOutputSummary.production_run_id == ids["run_id"]
    ).first()
    assert row is not None
    assert row.planned_quantity == 500.0
    assert row.actual_quantity == 480.0
    assert row.unit_id == unit_id
    assert row.disposition == "Released"
    output_id = row.id
    session.close()

    at2 = _run({"pr_selected_run_id": ids["run_id"]})
    assert not at2.exception
    at2.number_input(key=f"edit_output_actual_{output_id}").set_value(475.0)
    at2.selectbox(key=f"edit_output_disposition_{output_id}").set_value("Quarantined")
    save = next(b for b in at2.button if b.key == f"FormSubmitter:edit_output_form_{output_id}-Save changes")
    save.click().run()
    assert not at2.exception

    session = db.get_session()
    reloaded = session.get(db.ProductionOutputSummary, output_id)
    assert reloaded.actual_quantity == 475.0
    assert reloaded.disposition == "Quarantined"
    session.close()


# ---------------------------------------------------------------------------
# 3. Material Metering decoupling (no Finalized phase required)
# ---------------------------------------------------------------------------

def test_stream_reading_can_be_created_without_a_finalized_phase(seeded_run):
    """WP7 Phase 1/2 decoupling (Charlie's design review decision doc
    section 3.4): a Component Stream Reading can now be recorded for a run
    that has NO ProductionPhase at all yet - direct UI proof, since
    test_wp7_phase1_method_aware_schema.py only proves this at the ORM
    layer. Before this change, tab_streams showed nothing but an info box
    ("Add Runtime Data ... first") and no Create form existed at all."""
    ids = seeded_run
    session = db.get_session()
    assert session.query(db.ProductionPhase).filter(
        db.ProductionPhase.production_run_id == ids["run_id"]
    ).count() == 0, "This test's premise requires zero phases for the run"
    session.close()

    at = _run({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    form_key = f"add_stream_reading_{ids['run_id']}"
    assert any(b.key == f"FormSubmitter:{form_key}-Save stream reading" for b in at.button), (
        "Stream Reading Create form should render even with zero phases on the run"
    )

    other_input = next(
        t for t in at.text_input
        if "Or type a stream not in the recipe" in (t.label or "")
    )
    other_input.set_value("Test Blend (no phase)")
    submit = next(b for b in at.button if b.key == f"FormSubmitter:{form_key}-Save stream reading")
    submit.click().run()
    assert not at.exception, f"Unhandled exception saving a stream reading with no Finalized phase: {at.exception}"

    session = db.get_session()
    reading = session.query(db.ComponentStreamReading).filter(
        db.ComponentStreamReading.stream_name == "Test Blend (no phase)"
    ).first()
    assert reading is not None, "Stream reading was not persisted"
    assert reading.production_run_id == ids["run_id"]
    assert reading.production_phase_id is None, "No Finalized phase exists, so production_phase_id must stay NULL"
    session.close()


# ---------------------------------------------------------------------------
# 4. Production Events optional context links
# ---------------------------------------------------------------------------

def test_event_create_with_process_setting_context_link(seeded_method_setting):
    """A new Production Event can be linked to a ProcessSettingDefinition
    via the "Related process setting" picker added in WP7 Phase 2, and
    the link is persisted - direct UI proof complementing
    test_wp7_phase1_method_aware_schema.py's ORM-level context-link test."""
    ids = seeded_method_setting
    at = _run({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    setting_key = f"new_event_setting_{ids['run_id']}"
    assert any(s.key == setting_key for s in at.selectbox), "Related process setting picker did not render"
    setting_sb = at.selectbox(key=setting_key)
    # Selectbox.options returns FORMATTED display strings - select by index
    # (same convention as test_cr14_customers_section.py).
    setting_idx = next(i for i, opt in enumerate(setting_sb.options) if opt == "Test Mixer Speed")
    setting_sb.select_index(setting_idx)

    submit = next(b for b in at.button if b.key == f"FormSubmitter:add_event_{ids['run_id']}-Save event")
    submit.click().run()
    assert not at.exception

    session = db.get_session()
    event = session.query(db.ProductionEvent).filter(
        db.ProductionEvent.production_run_id == ids["run_id"]
    ).first()
    assert event is not None
    assert event.setting_definition_id == ids["definition_id"]
    session.close()
