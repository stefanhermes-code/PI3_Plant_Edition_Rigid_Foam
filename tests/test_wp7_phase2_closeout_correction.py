"""WP7 Phase 2 Closeout Correction (2026-08-14) - direct AppTest evidence for
Charlie's 3 Material Gaps from the WP7 Phase 2 Closeout Review, against the
real Streamlit UI (views/4_Production_Run_Trial_Record.py), following the
same AppTest conventions and fixture chain as
tests/test_wp7_phase2_production_run_ui.py (that file's own docstring/
fixtures document the full FK chain this file reuses, rebuilt locally here
so this file has no cross-file fixture dependency, per that same file's own
precedent).

Covers:

1. Material Gap 1 (numeric zero treated as blank): Planned = 0 and Actual =
   0 persist as a real recorded numeric zero (not blank/absent) for both
   Float and Integer ProcessSettingDefinition types, when the "Record a
   ... value" checkbox is explicitly checked. Conversely, typing a non-zero
   number into the field WITHOUT checking its checkbox leaves that value
   unset/blank (no row persisted) - proving the checkbox, not the number
   field's contents, is the sole source of truth.
2. Material Gap 2 (legacy Run Context shape): the Create Production Run and
   Edit Production Run forms both persist the new run_start/run_end/status/
   order_item_reference fields, and both forms walk the corrected
   Plant -> Production Method -> Production Unit or Cell -> Product Grade
   selection order (proven by the Product Grade choices actually changing
   when a different Production Unit or Cell is picked).
3. Material Gap 3 (absent Cycle/Shot UI): the Cycle / Shot Data tab shows a
   plain, non-error explanatory message (no Create form) for a run whose
   Production Method has uses_cycle_shot_operation=False, and exposes a
   real, functional Create-cycle-then-create-shot workflow for a run whose
   Production Method has it explicitly set True - proving the module is
   config-driven and conditionally rendered, not schema-support-only.

Usage: python -m pytest tests/test_wp7_phase2_closeout_correction.py -v
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
PAGE4 = os.path.join(APP_DIR, "views", "4_Production_Run_Trial_Record.py")


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


def _submit_key(at, form_key, label):
    return next(b for b in at.button if b.key == f"FormSubmitter:{form_key}-{label}")


@pytest.fixture()
def base_chain():
    """Company -> Plant -> ProductionMethod -> Machine -> ProductFamily ->
    FoamGrade -> RecipeVersion chain, WITHOUT a pre-created ProductionRun -
    the minimum content the Create Production Run tab needs (Gap 2 tests
    exercise creation itself, so no run should exist yet)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P2C Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P2C Plant {u}")
    session.add(plant); session.flush()

    method = db.ProductionMethod(controlled_id=f"PM-WP7P2C-{u}", name=f"WP7P2C Method {u}")
    session.add(method); session.flush()
    session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
    session.flush()

    machine = db.Machine(
        plant_id=plant.id, name=f"WP7P2C Unit {u}", production_method_id=method.id, active=True,
    )
    session.add(machine); session.flush()

    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P2C Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P2C Grade {u}")
    session.add(grade); session.flush()
    grade.machines = [machine]
    session.flush()

    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True,
    )
    session.add(recipe); session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "method_id": method.id,
        "machine_id": machine.id, "family_id": family.id, "grade_id": grade.id,
        "recipe_version_id": recipe.id,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_run(base_chain):
    """base_chain plus one real ProductionRun - the fixture the Edit Run
    (Gap 2) and Cycle/Shot (Gap 3) tests need."""
    ids = base_chain
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"],
        foam_grade_id=ids["grade_id"],
        recipe_version_id=ids["recipe_version_id"],
        run_date=dt.date(2026, 8, 1),
        batch_reference=f"B-WP7P2C-{ids['plant_id']}",
        machine_id=ids["machine_id"],
        production_method_id=ids["method_id"],
        operator_or_team_reference="Shift A",
        notes="seed run",
    )
    session.add(run); session.commit()
    out = dict(ids)
    out["run_id"] = run.id
    session.close()
    return out


@pytest.fixture()
def seeded_typed_settings(seeded_run):
    """Extends seeded_run with one Float and one Integer
    ProcessSettingDefinition, each with a Method-scoped
    ProcessSettingApplicability (Planned + Actual) - the minimum content
    needed to exercise the Gap 1 zero-vs-blank fix across both numeric
    data types the correction requires."""
    ids = seeded_run
    session = db.get_session()
    unit = db.UnitOfMeasure(controlled_id=f"UOM-WP7P2C-{ids['run_id']}", symbol="kg", name="kilograms")
    session.add(unit); session.flush()

    float_def = db.ProcessSettingDefinition(
        controlled_id=f"PS-FLOAT-{ids['run_id']}", name="Test Float Setting", data_type="Float",
        unit_id=unit.id, parameter_category="Process Setting", active=True, sort_order=1,
    )
    session.add(float_def); session.flush()
    session.add(db.ProcessSettingApplicability(
        setting_definition_id=float_def.id, production_method_id=ids["method_id"],
        applicable_to_planned=True, applicable_to_actual=True, controllable=True,
        analytics_eligible=True, active=True,
    ))

    int_def = db.ProcessSettingDefinition(
        controlled_id=f"PS-INT-{ids['run_id']}", name="Test Integer Setting", data_type="Integer",
        unit_id=unit.id, parameter_category="Process Setting", active=True, sort_order=2,
    )
    session.add(int_def); session.flush()
    session.add(db.ProcessSettingApplicability(
        setting_definition_id=int_def.id, production_method_id=ids["method_id"],
        applicable_to_planned=True, applicable_to_actual=True, controllable=True,
        analytics_eligible=True, active=True,
    ))
    session.commit()
    out = dict(ids)
    out["float_def_id"] = float_def.id
    out["int_def_id"] = int_def.id
    session.close()
    return out


@pytest.fixture()
def cycle_shot_enabled_run(seeded_run):
    """seeded_run's Production Method flipped to
    uses_cycle_shot_operation=True - explicit, evidence-based (per this
    isolated test fixture standing in for Charlie's confirmation), never
    inferred from a name."""
    ids = seeded_run
    session = db.get_session()
    method = session.get(db.ProductionMethod, ids["method_id"])
    method.uses_cycle_shot_operation = True
    session.commit()
    session.close()
    return ids


# ---------------------------------------------------------------------------
# 1. Material Gap 1 - numeric zero vs blank
# ---------------------------------------------------------------------------

def test_planned_and_actual_zero_persist_as_numeric_zero_float(seeded_typed_settings):
    """Planned = 0 and Actual = 0, with their 'Record a value' checkboxes
    checked, must persist as a real numeric_value == 0.0 - not None, not a
    deleted/absent row - for a Float ProcessSettingDefinition."""
    ids = seeded_typed_settings
    at = _run({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    planned_key = f"pps_{ids['float_def_id']}_Planned_{ids['run_id']}"
    actual_key = f"pps_{ids['float_def_id']}_Actual_{ids['run_id']}"
    at.checkbox(key=f"{planned_key}_recorded").set_value(True)
    at.checkbox(key=f"{actual_key}_recorded").set_value(True)
    at.number_input(key=planned_key).set_value(0.0)
    at.number_input(key=actual_key).set_value(0.0)
    submit = _submit_key(at, f"method_settings_form_{ids['run_id']}", "Save process settings")
    submit.click().run()
    assert not at.exception

    session = db.get_session()
    rows = {
        r.snapshot_type: r
        for r in session.query(db.ProcessParameterValue)
        .filter(
            db.ProcessParameterValue.production_run_id == ids["run_id"],
            db.ProcessParameterValue.setting_definition_id == ids["float_def_id"],
        ).all()
    }
    assert "Planned" in rows and "Actual" in rows, "Explicitly recorded zero values must not be dropped"
    assert rows["Planned"].numeric_value == 0.0
    assert rows["Actual"].numeric_value == 0.0
    session.close()


def test_planned_and_actual_zero_persist_as_numeric_zero_integer(seeded_typed_settings):
    """Same proof as the Float test above, for an Integer
    ProcessSettingDefinition - Charlie's Material Gap 1 explicitly named
    both data types."""
    ids = seeded_typed_settings
    at = _run({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    planned_key = f"pps_{ids['int_def_id']}_Planned_{ids['run_id']}"
    actual_key = f"pps_{ids['int_def_id']}_Actual_{ids['run_id']}"
    at.checkbox(key=f"{planned_key}_recorded").set_value(True)
    at.checkbox(key=f"{actual_key}_recorded").set_value(True)
    at.number_input(key=planned_key).set_value(0.0)
    at.number_input(key=actual_key).set_value(0.0)
    submit = _submit_key(at, f"method_settings_form_{ids['run_id']}", "Save process settings")
    submit.click().run()
    assert not at.exception

    session = db.get_session()
    rows = {
        r.snapshot_type: r
        for r in session.query(db.ProcessParameterValue)
        .filter(
            db.ProcessParameterValue.production_run_id == ids["run_id"],
            db.ProcessParameterValue.setting_definition_id == ids["int_def_id"],
        ).all()
    }
    assert "Planned" in rows and "Actual" in rows, "Explicitly recorded zero values must not be dropped"
    assert rows["Planned"].numeric_value == 0.0
    assert rows["Actual"].numeric_value == 0.0
    session.close()


def test_unchecked_record_checkbox_leaves_value_unset_despite_number_input_content(seeded_typed_settings):
    """Typing a non-zero number into the Planned field WITHOUT checking its
    'Record a value' checkbox must NOT persist a row - proving the
    checkbox (not the number field's contents) is the sole source of
    truth for whether a value is explicitly recorded, per Charlie's fix
    requirement."""
    ids = seeded_typed_settings
    at = _run({"pr_selected_run_id": ids["run_id"]})
    assert not at.exception

    planned_key = f"pps_{ids['float_def_id']}_Planned_{ids['run_id']}"
    # Deliberately leave the "Record a planned value" checkbox at its
    # default (unchecked, since no existing value) and only type into the
    # number field.
    at.number_input(key=planned_key).set_value(42.0)
    submit = _submit_key(at, f"method_settings_form_{ids['run_id']}", "Save process settings")
    submit.click().run()
    assert not at.exception

    session = db.get_session()
    row = session.query(db.ProcessParameterValue).filter(
        db.ProcessParameterValue.production_run_id == ids["run_id"],
        db.ProcessParameterValue.setting_definition_id == ids["float_def_id"],
        db.ProcessParameterValue.snapshot_type == "Planned",
    ).first()
    assert row is None, "A number typed without checking its 'Record a value' checkbox must stay unset"
    session.close()


# ---------------------------------------------------------------------------
# 2. Material Gap 2 - context-first Run Context
# ---------------------------------------------------------------------------

def test_create_run_persists_new_context_fields_and_grade_choices_follow_unit(base_chain):
    """Create Production Run: the corrected Plant -> Production Method ->
    Production Unit or Cell -> Product Grade order actually drives Product
    Grade's choices (proven by the grade appearing only once the Unit is
    selected), and the new run_start/run_end/status/order_item_reference
    fields all persist on the created run."""
    ids = base_chain
    at = _run()
    assert not at.exception

    # Before a Production Unit or Cell is chosen, no Product Grade is
    # assignable yet - direct proof the grade choice is derived FROM the
    # unit selection, not the legacy Grade-first order.
    at.selectbox(key="create_run_plant").select_index(0).run()
    at.selectbox(key="create_run_method").select_index(0).run()
    assert "none assignable yet" in "".join(
        cb.value or "" for cb in at.caption
    ) or not any(
        sb.label and sb.label.startswith("Product grade") and sb.options for sb in at.selectbox
    ), "Product Grade should not be assignable before a Production Unit or Cell is chosen"

    # machine_options = [None] + active_machines, defaulting to None (index
    # 0) - select the real Production Unit or Cell at index 1.
    at.selectbox(key="create_run_machine").select_index(1).run()

    grade_sb = next(sb for sb in at.selectbox if sb.label and sb.label.startswith("Product grade"))
    grade_sb.select_index(0).run()

    at.selectbox(key="create_run_status").select_index(1)  # first real status (index 0 is "— not set —")
    at.checkbox(key="create_run_start_flag").set_value(True)
    at.date_input(key="create_run_start_date").set_value(dt.date(2026, 8, 5))
    at.time_input(key="create_run_start_time").set_value(dt.time(8, 0))
    at.checkbox(key="create_run_end_flag").set_value(True)
    at.date_input(key="create_run_end_date").set_value(dt.date(2026, 8, 5))
    at.time_input(key="create_run_end_time").set_value(dt.time(16, 30))
    order_ref_input = next(t for t in at.text_input if t.label == "Customer order / order item reference")
    order_ref_input.set_value("SO-2026-0042")

    submit = _submit_key(at, "add_run", "Save production run")
    submit.click().run()
    assert not at.exception

    session = db.get_session()
    run = session.query(db.ProductionRun).filter(db.ProductionRun.plant_id == ids["plant_id"]).first()
    assert run is not None, "Production run was not created"
    assert run.machine_id == ids["machine_id"]
    assert run.production_method_id == ids["method_id"]
    assert run.foam_grade_id == ids["grade_id"]
    assert run.status == db.PRODUCTION_RUN_STATUSES[0]
    assert run.run_start == dt.datetime(2026, 8, 5, 8, 0)
    assert run.run_end == dt.datetime(2026, 8, 5, 16, 30)
    assert run.order_item_reference == "SO-2026-0042"
    session.close()


def test_edit_run_persists_new_context_fields(seeded_run):
    """Edit Production Run: status/run_start/run_end/order_item_reference
    all save correctly through the real Edit form, on top of the
    context-first Plant/Method/Unit/Grade selectors already proven by the
    Create test above.

    tab_runs' own runs_overview_table code unconditionally pops
    pr_selected_run_id whenever the table has no fresh row-click event that
    rerun, so presetting pr_selected_run_id directly in session_state
    doesn't survive the first .run() - the table widget's OWN on_select
    state must be preset instead (same technique as
    test_cr11_functional_evidence_group_d.py's
    test_production_run_selection_edit_and_delete_via_ui, whose module
    docstring documents this wrinkle in full) - the same AppTest instance
    keeps that preset session_state value across the submit-time .run()
    below, so no re-preset is needed before it."""
    ids = seeded_run
    table_state = {"runs_overview_table": {"selection": {"rows": [0], "columns": []}}}
    at = _run(table_state)
    assert not at.exception
    assert at.session_state["pr_selected_run_id"] == ids["run_id"]

    status_sb = at.selectbox(key=f"edit_run_status_{ids['run_id']}")
    real_status_idx = next(i for i, opt in enumerate(status_sb.options) if opt == db.PRODUCTION_RUN_STATUSES[1])
    status_sb.select_index(real_status_idx)
    at.checkbox(key=f"edit_run_start_flag_{ids['run_id']}").set_value(True)
    at.date_input(key=f"edit_run_start_{ids['run_id']}_date").set_value(dt.date(2026, 8, 2))
    at.time_input(key=f"edit_run_start_{ids['run_id']}_time").set_value(dt.time(6, 0))
    at.checkbox(key=f"edit_run_end_flag_{ids['run_id']}").set_value(True)
    at.date_input(key=f"edit_run_end_{ids['run_id']}_date").set_value(dt.date(2026, 8, 2))
    at.time_input(key=f"edit_run_end_{ids['run_id']}_time").set_value(dt.time(14, 0))
    at.text_input(key=f"edit_run_order_ref_{ids['run_id']}").set_value("PO-9981")

    save = _submit_key(at, f"edit_run_form_{ids['run_id']}", "Save changes")
    save.click().run()
    assert not at.exception

    session = db.get_session()
    reloaded = session.get(db.ProductionRun, ids["run_id"])
    assert reloaded.status == db.PRODUCTION_RUN_STATUSES[1]
    assert reloaded.run_start == dt.datetime(2026, 8, 2, 6, 0)
    assert reloaded.run_end == dt.datetime(2026, 8, 2, 14, 0)
    assert reloaded.order_item_reference == "PO-9981"
    session.close()


@pytest.fixture()
def two_chain_run():
    """Two complete, independent Plant -> Production Method -> Machine ->
    Product Grade -> RecipeVersion chains (A and B) under the same Company,
    plus one ProductionRun created under chain A - the minimum content
    needed to prove the Edit Run form's Plant/Method/Unit/Grade pickers
    reactively refresh against each other (WP7 Phase 2 Closeout Correction
    v2, Charlie's material completion item 1) rather than only the
    single-chain fixtures above, which can't distinguish 'the right chain
    happened to already be selected' from 'the cascade actually recomputed
    when Plant changed'."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P2C2 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()

    chains = {}
    for label in ("a", "b"):
        plant = db.Plant(company_id=company.id, name=f"WP7P2C2 Plant {label.upper()} {u}")
        session.add(plant); session.flush()
        method = db.ProductionMethod(controlled_id=f"PM-WP7P2C2-{label}-{u}", name=f"WP7P2C2 Method {label.upper()} {u}")
        session.add(method); session.flush()
        session.add(db.PlantProductionMethod(plant_id=plant.id, production_method_id=method.id, active=True))
        session.flush()
        machine = db.Machine(
            plant_id=plant.id, name=f"WP7P2C2 Unit {label.upper()} {u}",
            production_method_id=method.id, active=True,
        )
        session.add(machine); session.flush()
        family = db.ProductFamily(plant_id=plant.id, name=f"WP7P2C2 Family {label.upper()} {u}")
        session.add(family); session.flush()
        grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P2C2 Grade {label.upper()} {u}")
        session.add(grade); session.flush()
        grade.machines = [machine]
        session.flush()
        recipe = db.RecipeVersion(
            foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True,
        )
        session.add(recipe); session.flush()
        chains[label] = {
            "plant_id": plant.id, "plant_name": plant.name, "method_id": method.id,
            "machine_id": machine.id, "machine_name": machine.name, "grade_id": grade.id,
            "grade_name": grade.name if hasattr(grade, "name") else grade.grade_name,
            "recipe_version_id": recipe.id,
        }

    run = db.ProductionRun(
        plant_id=chains["a"]["plant_id"],
        foam_grade_id=chains["a"]["grade_id"],
        recipe_version_id=chains["a"]["recipe_version_id"],
        run_date=dt.date(2026, 8, 1),
        batch_reference=f"B-WP7P2C2-{u}",
        machine_id=chains["a"]["machine_id"],
        production_method_id=chains["a"]["method_id"],
        operator_or_team_reference="Shift A",
        notes="seed run on chain A",
    )
    session.add(run); session.commit()
    out = {"company_id": company.id, "run_id": run.id, "chain_a": chains["a"], "chain_b": chains["b"]}
    session.close()
    return out


def test_edit_run_reactive_cascade_produces_internally_consistent_chain(two_chain_run):
    """WP7 Phase 2 Closeout Correction v2 (2026-08-14, Charlie's material
    completion item 1): switching Edit Run's Plant selector to a different
    valid chain must reactively refresh the Production Method, Production
    Unit or Cell and Product Grade option sets to that new Plant's own
    chain - not silently carry over stale selections from the previously
    rendered chain - and the persisted run must end up wholly on the new
    chain (no cross-chain mix)."""
    ids = two_chain_run
    chain_b = ids["chain_b"]
    table_state = {"runs_overview_table": {"selection": {"rows": [0], "columns": []}}}
    at = _run(table_state)
    assert not at.exception
    assert at.session_state["pr_selected_run_id"] == ids["run_id"]

    plant_sb = at.selectbox(key=f"edit_run_plant_{ids['run_id']}")
    plant_b_idx = next(i for i, opt in enumerate(plant_sb.options) if opt == chain_b["plant_name"])
    plant_sb.select_index(plant_b_idx).run()
    assert not at.exception, f"Unhandled exception after switching Plant: {at.exception}"

    # Production Method must have reactively refreshed to chain B's own
    # Method - proving the picker actually recomputed against the new
    # Plant rather than still offering (or defaulting to) chain A's Method.
    method_sb = at.selectbox(key=f"edit_run_method_{ids['run_id']}")
    assert all("WP7P2C2 Method A" not in opt for opt in method_sb.options), (
        f"Production Method options should be scoped to the newly selected Plant B, got {method_sb.options}"
    )
    method_b_idx = next(i for i, opt in enumerate(method_sb.options) if "WP7P2C2 Method B" in opt)
    method_sb.select_index(method_b_idx).run()
    assert not at.exception

    # Production Unit or Cell must have reactively refreshed to chain B's
    # own Machine.
    machine_sb = at.selectbox(key=f"edit_run_machine_{ids['run_id']}")
    assert all("WP7P2C2 Unit A" not in opt for opt in machine_sb.options), (
        f"Production Unit or Cell options should be scoped to the newly selected Plant/Method B, got {machine_sb.options}"
    )
    machine_b_idx = next(i for i, opt in enumerate(machine_sb.options) if "WP7P2C2 Unit B" in opt)
    machine_sb.select_index(machine_b_idx).run()
    assert not at.exception

    # Product Grade (still inside the form, same as Create Run) must now
    # only offer chain B's grade.
    grade_sb = next(sb for sb in at.selectbox if sb.label and sb.label.startswith("Product grade"))
    assert all("WP7P2C2 Grade A" not in opt for opt in grade_sb.options), (
        f"Product Grade options should be scoped to the newly selected Production Unit B, got {grade_sb.options}"
    )
    grade_b_idx = next(i for i, opt in enumerate(grade_sb.options) if "WP7P2C2 Grade B" in opt)
    grade_sb.select_index(grade_b_idx)

    save = _submit_key(at, f"edit_run_form_{ids['run_id']}", "Save changes")
    save.click().run()
    assert not at.exception, f"Unhandled exception saving the cross-chain edit: {at.exception}"

    session = db.get_session()
    reloaded = session.get(db.ProductionRun, ids["run_id"])
    assert reloaded.plant_id == chain_b["plant_id"]
    assert reloaded.production_method_id == chain_b["method_id"]
    assert reloaded.machine_id == chain_b["machine_id"]
    assert reloaded.foam_grade_id == chain_b["grade_id"]
    session.close()


# ---------------------------------------------------------------------------
# 3. Material Gap 3 - conditional Cycle / Shot Data module
# ---------------------------------------------------------------------------

def test_cycle_shot_tab_shows_explanatory_message_when_not_configured(seeded_run):
    """A run whose Production Method has NOT been explicitly flagged
    uses_cycle_shot_operation=True must show a plain explanatory message
    and no Create-cycle form - the module stays absent by default, never
    inferred."""
    ids = seeded_run
    at = _run({"pr_selected_run_id": ids["run_id"], "cycles_tab_run_select": ids["run_id"]})
    assert not at.exception
    infos = " ".join(i.value for i in at.info)
    assert "not enabled for this run" in infos.lower()
    assert not any(b.key == f"FormSubmitter:add_cycle_{ids['run_id']}-Save cycle" for b in at.button), (
        "Create-cycle form must not render when the Production Method isn't configured for cycle/shot"
    )


def test_cycle_shot_tab_create_cycle_and_shot_when_configured(cycle_shot_enabled_run):
    """A run whose Production Method IS explicitly flagged
    uses_cycle_shot_operation=True exposes a real, functional Create-cycle
    workflow, and once a cycle exists, a real Create-shot workflow nested
    under it - the direct UI proof Charlie's Material Gap 3 required
    beyond schema support alone."""
    ids = cycle_shot_enabled_run
    at = _run({"pr_selected_run_id": ids["run_id"], "cycles_tab_run_select": ids["run_id"]})
    assert not at.exception
    assert not any(
        "not enabled for this run" in (i.value or "").lower() for i in at.info
    ), "Cycle/Shot module should be usable for a Method explicitly configured for it"

    cycle_submit_key = f"FormSubmitter:add_cycle_{ids['run_id']}-Save cycle"
    assert any(b.key == cycle_submit_key for b in at.button), "Create-cycle form should render when configured"
    at.number_input(key=f"new_cycle_number_{ids['run_id']}").set_value(1)
    cycle_submit = next(b for b in at.button if b.key == cycle_submit_key)
    cycle_submit.click().run()
    assert not at.exception

    session = db.get_session()
    cycle = session.query(db.ProductionCycle).filter(
        db.ProductionCycle.production_run_id == ids["run_id"]
    ).first()
    assert cycle is not None, "Cycle was not persisted"
    assert cycle.cycle_number == 1
    cycle_id = cycle.id
    session.close()

    # Rerun with the run and the newly-created cycle both selected, then
    # create a shot nested under that cycle.
    at2 = _run({
        "pr_selected_run_id": ids["run_id"],
        "cycles_tab_run_select": ids["run_id"],
        f"cycles_tab_cycle_select_{ids['run_id']}": cycle_id,
    })
    assert not at2.exception
    shot_submit_key = f"FormSubmitter:add_shot_{cycle_id}-Save shot"
    assert any(b.key == shot_submit_key for b in at2.button), "Create-shot form should render for an existing cycle"
    at2.number_input(key=f"new_shot_number_{cycle_id}").set_value(1)
    shot_submit = next(b for b in at2.button if b.key == shot_submit_key)
    shot_submit.click().run()
    assert not at2.exception

    session = db.get_session()
    shot = session.query(db.ProductionShot).filter(
        db.ProductionShot.production_cycle_id == cycle_id
    ).first()
    assert shot is not None, "Shot was not persisted"
    assert shot.shot_number == 1
    session.close()
