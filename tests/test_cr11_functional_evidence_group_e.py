"""CR-11 (Standardize Record Create, Edit/Delete and CSV/Excel Import
Functions, 2026-08-12) closeout correction - Group E.

Charlie returned the CR-11 closeout package OPEN because it only had
wording/order tests (tab labels, tab counts) proving
helpers.cr11_function_tab_labels() was wired in, not direct executed
evidence that Create/Edit/Delete/Import actually work through the real UI
- including nested record groups, which several CR-11 pages have. This
file supplies that missing direct evidence for the two "independent
lab-trial" pages, each of which has BOTH an outer group and a nested
group:

  views/11_Customer_Trials.py    - outer "Trial" (CustomerTrial),
                                    nested "Sample" ("Manage samples").
  views/12_Optimization_Trials.py - outer "Trial" (OptimizationTrial),
                                    nested "Sample" ("Manage samples").

Per tenant_scope.py's own module docstring, both CustomerTrial and
OptimizationTrial hang directly off Plant - "independent lab-trial flow,
no ProductionRun underneath" - so unlike a production-run-backed page,
seeding a trial needs nothing beyond Plant -> PUMaterialFamily -> FoamGrade
-> CustomerTrial/OptimizationTrial. Both pages' own "Manage samples"
workspace lives INSIDE the outer "Create Trial" tab body (not a separate
top-level tab): a trial is picked via a selectbox ("Trial *", key
"ct_manage_trial" / "ot_manage_trial"), and only then do the nested
Sample sub-tabs (cr11_function_tab_labels("Sample")) render underneath
it, each with its own per-trial-id table/uploader/button keys. Both pages
also keep a page-specific "Sample Report" 4th tab beyond the CR-11
standard three, which CR-11 explicitly allows and which this file does
not touch.

Conventions copied deliberately from
tests/test_cr10_pu_material_family_grade_split.py (the template Charlie
already accepted for this exact kind of evidence, for PU Material Families /
Product Grades):

  - os.environ.setdefault("DATABASE_URL", "sqlite://") + sys.path
    boilerplate near the top.
  - _clear_relevant_caches(), called from every _reset_schema(), clearing
    every tenant_scope id-list cache (including
    customer_trial_ids_for_plants / optimization_trial_ids_for_plants -
    directly in this file's own scoping path, since both pages call
    customer_trial_ids_for_company()/optimization_trial_ids_for_company(),
    which wrap those two) plus access_control.denied_page_keys.
  - db.init_db() + Base.metadata.drop_all/create_all schema reset per
    fixture, seeded via SQLAlchemy ORM objects with a uuid.uuid4().hex[:8]
    suffix for uniqueness.
  - The dataframe-widget's-own-selection-state technique for
    clickable_table row selection: presetting
    at.session_state[<table_key>] = {"selection": {"rows": [i],
    "columns": []}} BEFORE .run() - confirmed against streamlit==1.59.2 -
    drives a real row click. The outer Trial table (key
    "customer_trials_table" / "optimization_trials_table", derived
    selection "ct_selected_id" / "ot_selected_id") and the nested Sample
    table (key f"ct_samples_table_{trial_id}" /
    f"ot_samples_table_{trial_id}", derived selection
    f"ct_sample_selected_id_{trial_id}" / f"ot_sample_selected_id_{trial_id}")
    are each independent widget state, exactly as the brief for this file
    anticipated.
  - at.file_uploader[...].set_value((name, bytes, mime)) for CSV import,
    each group's uploader keyed independently (fixed key "ct_trial_upload"
    /"ot_trial_upload" for the outer Trial import tab; per-managed-trial
    key f"ct_sample_upload_{trial_id}" / f"ot_sample_upload_{trial_id}"
    for the nested Sample import sub-tab), each with its own "Confirm
    import" button key.
  - at.secrets["AUTH_DISABLED"] = True on every AppTest run.

Both seeded grades in this file are left with chemistry_id=None (a
legacy/flexible-style grade, per reports._is_rigid_grade's own
docstring), so helpers.rigid_sample_dimension_fields() renders nothing
extra on the Sample create/edit forms - deliberate, to keep every form
in this file to its minimal real required-widget set.

CORRECTION v2 (2026-08-12, per Charlie's CR11_Closeout_Correction_
Review_Return_to_JC.docx): the round above closed out create/edit/
selection/valid-import evidence for all 4 record groups (outer Customer
Trial, nested Customer Trial Sample, outer Optimization Trial, nested
Optimization Trial Sample), but Charlie's review found two further gaps,
both cutting across all 4 groups:

  1. Delete permission/safeguards - no direct evidence a role denied
     "use" access (can_view=True, can_use=False) is actually blocked from
     deleting a record through the real UI, for each applicable page key.
     Added below: a view_only_ct_role_fixture / view_only_ot_role_fixture
     pair (one company-scoped db.Role + db.RolePagePermission per outer
     page, reused for that page's nested Sample group too, since both
     verified from source to share the exact same page_key/page_usable
     gating - see the fixtures' own docstrings) and 4 new tests, one per
     record group, each presetting the relevant clickable_table's own
     selection state for a real view-only-role run and asserting the
     delete confirm-checkbox/button don't render, plus that the record
     survives.
  2. Import validation handling - all 4 of this file's importers
     pre-existed CR-11 (only relabeled by it, not among CR-11's six
     net-new importers) and so far only had successful-import evidence.
     Added below: 4 new tests, one per record group, each uploading a CSV
     row that fails that exact importer's own bad-row check (read from
     source, not assumed - see each new test's own docstring for the
     precise condition) and asserting the "Confirm import" button doesn't
     render and the row count is unchanged.

Usage: python -m pytest tests/test_cr11_functional_evidence_group_e.py -v
"""
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
PAGE_CUSTOMER_TRIALS = os.path.join(APP_DIR, "views", "11_Customer_Trials.py")
PAGE_OPTIMIZATION_TRIALS = os.path.join(APP_DIR, "views", "12_Optimization_Trials.py")


def _clear_relevant_caches():
    """Every fixture below creates a fresh Company/Plant/FoamGrade (and
    usually a CustomerTrial/OptimizationTrial) right after _reset_schema()
    restarts autoincrement ids at 1 - the same cross-test cache-key
    collision hazard test_cr10_pu_material_family_grade_split.py's own
    _clear_relevant_caches() documents (tenant_scope's id-scoping helpers
    and access_control.denied_page_keys are @st.cache_data'd with a
    leading _session param st.cache_data excludes from the hash key, so
    the cache key is small integers alone - company_id, plant_ids - which
    repeat across tests/files once ids restart). Cleared here, at every
    _reset_schema() call in this file, so this file's fixtures can never
    serve another test's stale cached scope - especially important here
    since customer_trial_ids_for_plants/optimization_trial_ids_for_plants
    are directly in both pages' own scoping path
    (customer_trial_ids_for_company/optimization_trial_ids_for_company
    wrap them)."""
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


def _run(page_path, session_state=None):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def _run_as_role(page_path, ids, extra_session_state=None):
    """CR-11 correction v2 (2026-08-12, per Charlie's CR11_Closeout_
    Correction_Review_Return_to_JC.docx item 1) - copied from
    tests/test_cr10_pu_material_family_grade_split.py's identical helper (the
    template Charlie already accepted for this exact kind of evidence):
    same AUTH_DISABLED entry point every other test in this file uses, but
    overriding the dev-bypass's own is_super_admin=True default (see
    auth.py's require_login docstring) with a real, restricted role - the
    dev bypass only setdefault()s these session_state keys, so presetting
    them BEFORE .run() makes require_login() leave them alone.
    extra_session_state (e.g. a clickable_table's own on_select state) is
    applied on that SAME first .run() call, since - per this file's module
    docstring - a dataframe widget's own selection state only takes effect
    if it's present before the run in which that widget first executes."""
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["role_id"] = ids["role_id"]
    at.session_state["is_super_admin"] = False
    at.session_state["is_platform_owner"] = False
    at.session_state["company_id"] = ids["company_id"]
    for key, value in (extra_session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


# ---------------------------------------------------------------------------
# Fixtures - Customer Trials
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_ct_grade_only():
    """Company -> Plant -> PUMaterialFamily -> FoamGrade, zero trials yet.
    Both pages st.stop() with 'Add a product grade first' if there is no
    grade in scope, so this is the minimum needed just to open the page;
    used for the outer Trial 'create via form' test and the outer Trial
    CSV import test, neither of which needs a pre-existing trial.

    CR-14 (Create Customers Section and Lightweight Customer Master,
    2026-08-12): the Create Trial form's Customer field is now a
    selectbox sourced from the db.Customer master, not free text - also
    seeds one Customer here (the page's own `elif not customers:` warning
    branch st.stop()s the create form entirely otherwise, same as the
    grade check)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11e CT Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11e CT Plant {u}")
    session.add(plant); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR11e CT Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR11e-CT-Grade-{u}")
    session.add(grade); session.flush()
    customer = db.Customer(company_id=company.id, company_name=f"CR11e-Correction-New-Customer-{u}")
    session.add(customer); session.flush()
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "family_id": family.id, "grade_id": grade.id, "grade_name": grade.grade_name,
        "customer_id": customer.id, "customer_name": customer.company_name,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_ct_trial():
    """Same as seeded_ct_grade_only, plus one CustomerTrial hanging
    directly off the plant (per tenant_scope.py's docstring - no
    PUMaterialFamily/FoamGrade/ProductionRun chain needed beyond the grade
    it targets, and no ProductionRun at all) with zero samples yet - the
    minimum for the outer Trial selection/edit/delete test (unambiguous
    single row) and for the nested Sample 'create via form' test (a
    trial to land 'Manage samples' on, with no existing sample row to
    make a fresh dataframe row-index ambiguous).

    CR-14 (2026-08-12): also seeds a SECOND Customer
    ("customer_2_id"/"customer_2_name") beyond the one the trial links
    to, so the outer Edit test has a real second option to switch the
    Customer selectbox to (rather than only ever re-selecting the same
    one)."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11e CT Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11e CT Plant {u}")
    session.add(plant); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR11e CT Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR11e-CT-Grade-{u}")
    session.add(grade); session.flush()
    customer = db.Customer(company_id=company.id, company_name=f"CR11e CT Customer {u}")
    session.add(customer); session.flush()
    customer_2 = db.Customer(company_id=company.id, company_name=f"CR11e-Correction-Edited-Customer-{u}")
    session.add(customer_2); session.flush()
    trial = db.CustomerTrial(
        plant_id=plant.id, foam_grade_id=grade.id,
        customer_id=customer.id, customer_name=customer.company_name, status="Open",
    )
    session.add(trial); session.flush()
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "family_id": family.id, "grade_id": grade.id, "grade_name": grade.grade_name,
        "trial_id": trial.id,
        "customer_id": customer.id, "customer_name": customer.company_name,
        "customer_2_id": customer_2.id, "customer_2_name": customer_2.company_name,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_ct_trial_with_sample():
    """Same as seeded_ct_trial, plus one Sample already recorded against
    that trial (customer_trial_id set, production_run_id/
    optimization_trial_id left NULL - the mutually-exclusive-FK
    convention db.sample_source_fk_field()/SAMPLE_SOURCE_TYPES document)
    - the minimum for the nested Sample selection/edit/delete test to be
    unambiguous."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11e CT Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11e CT Plant {u}")
    session.add(plant); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR11e CT Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR11e-CT-Grade-{u}")
    session.add(grade); session.flush()
    trial = db.CustomerTrial(
        plant_id=plant.id, foam_grade_id=grade.id,
        customer_name=f"CR11e CT Customer {u}", status="Open",
    )
    session.add(trial); session.flush()
    sample = db.Sample(customer_trial_id=trial.id, zone_label="Top", notes="Seed sample")
    session.add(sample); session.flush()
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "family_id": family.id, "grade_id": grade.id, "grade_name": grade.grade_name,
        "trial_id": trial.id, "sample_id": sample.id,
    }
    session.close()
    return ids


# ---------------------------------------------------------------------------
# Fixtures - Optimization Trials (mirrors the three above exactly, for
# OptimizationTrial instead of CustomerTrial)
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_ot_grade_only():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11e OT Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11e OT Plant {u}")
    session.add(plant); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR11e OT Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR11e-OT-Grade-{u}")
    session.add(grade); session.flush()
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "family_id": family.id, "grade_id": grade.id, "grade_name": grade.grade_name,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_ot_trial():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11e OT Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11e OT Plant {u}")
    session.add(plant); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR11e OT Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR11e-OT-Grade-{u}")
    session.add(grade); session.flush()
    trial = db.OptimizationTrial(
        plant_id=plant.id, foam_grade_id=grade.id,
        improvement_initiative_reference=f"CR11e OT Initiative {u}", status="Open",
    )
    session.add(trial); session.flush()
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "family_id": family.id, "grade_id": grade.id, "grade_name": grade.grade_name,
        "trial_id": trial.id,
    }
    session.close()
    return ids


@pytest.fixture()
def seeded_ot_trial_with_sample():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()
    company = db.Company(name=f"CR11e OT Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"CR11e OT Plant {u}")
    session.add(plant); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"CR11e OT Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"CR11e-OT-Grade-{u}")
    session.add(grade); session.flush()
    trial = db.OptimizationTrial(
        plant_id=plant.id, foam_grade_id=grade.id,
        improvement_initiative_reference=f"CR11e OT Initiative {u}", status="Open",
    )
    session.add(trial); session.flush()
    sample = db.Sample(optimization_trial_id=trial.id, zone_label="Top", notes="Seed sample")
    session.add(sample); session.flush()
    session.commit()
    ids = {
        "company_id": company.id, "plant_id": plant.id,
        "family_id": family.id, "grade_id": grade.id, "grade_name": grade.grade_name,
        "trial_id": trial.id, "sample_id": sample.id,
    }
    session.close()
    return ids


# ---------------------------------------------------------------------------
# CR-11 CLOSEOUT CORRECTION v2 (2026-08-12, per Charlie's CR11_Closeout_
# Correction_Review_Return_to_JC.docx) - fixtures for item 1 (Delete
# permission/safeguards).
#
# Both pages gate their outer Trial group's AND their nested Sample
# group's Create/Edit/Delete write controls off the SAME single
# `page_usable = can_use_page(<page_key>, ...)` call near the top of the
# page (see views/11_Customer_Trials.py's `page_usable` variable, read
# once and reused by both the outer tab_edit_delete block's
# delete_with_confirm(...) call and the nested sub_edit_delete block's own
# delete_with_confirm(...) call) - there is no separate page_key for the
# nested Sample group. Verified directly from source rather than assumed:
#   views/11_Customer_Trials.py:    can_use_page("customer_trials", ...)
#   views/12_Optimization_Trials.py: can_use_page("optimization_trials", ...)
# So one company-scoped Role per page, denied "use" (can_view=True,
# can_use=False) on that page's own page_key, is directly reusable as
# fixture-level evidence for BOTH that page's outer Trial delete test and
# its nested Sample delete test below.
# ---------------------------------------------------------------------------

@pytest.fixture()
def view_only_ct_role_fixture(seeded_ct_trial_with_sample):
    """A real db.Role + db.RolePagePermission(page_key="customer_trials",
    can_view=True, can_use=False) against the seeded_ct_trial_with_sample
    chain (one trial, one sample) - the minimum needed to exercise BOTH
    the outer Trial delete-permission test and the nested Sample
    delete-permission test off a single fixture, exactly as
    tests/test_cr10_pu_material_family_grade_split.py's view_only_role_fixture
    does for its own two page keys."""
    ids = seeded_ct_trial_with_sample
    session = db.get_session()
    role = db.Role(company_id=ids["company_id"], name="CR11e CT Correction View Only", is_builtin=False)
    session.add(role); session.flush()
    session.add(db.RolePagePermission(role_id=role.id, page_key="customer_trials", can_view=True, can_use=False))
    session.commit()
    out = dict(ids)
    out["role_id"] = role.id
    session.close()
    return out


@pytest.fixture()
def view_only_ot_role_fixture(seeded_ot_trial_with_sample):
    """Same as view_only_ct_role_fixture, for optimization_trials /
    seeded_ot_trial_with_sample."""
    ids = seeded_ot_trial_with_sample
    session = db.get_session()
    role = db.Role(company_id=ids["company_id"], name="CR11e OT Correction View Only", is_builtin=False)
    session.add(role); session.flush()
    session.add(db.RolePagePermission(role_id=role.id, page_key="optimization_trials", can_view=True, can_use=False))
    session.commit()
    out = dict(ids)
    out["role_id"] = role.id
    session.close()
    return out


# ---------------------------------------------------------------------------
# Customer Trials - outer "Trial" group
# ---------------------------------------------------------------------------

def test_customer_trial_create_via_form(seeded_ct_grade_only):
    """Drives the real Create Trial form ("add_customer_trial"): the
    Product grade selectbox already defaults to the only seeded grade,
    and the Customer selectbox (key 'ct_add_customer') already defaults
    to the fixture's one seeded Customer - CR-14 (2026-08-12) replaced
    the old free-text 'Customer name *' input with this Customer-master
    selectbox, so create no longer requires typing a name, only picking
    one. Clicks the real 'Save customer trial' submit button, then
    confirms the new CustomerTrial row landed in the database with the
    plant/grade FKs the page itself resolves, AND that customer_id links
    to the picked Customer while customer_name is synced from it."""
    ids = seeded_ct_grade_only
    at = AppTest.from_file(PAGE_CUSTOMER_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Customer Trials: {at.exception}"

    customer_sb = next(sb for sb in at.selectbox if sb.key == "ct_add_customer")
    assert customer_sb.value.id == ids["customer_id"], (
        "With only one Customer seeded, the Create Trial form's Customer selectbox should default to it"
    )
    save_btn = next(b for b in at.button if b.label == "Save customer trial")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new customer trial: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.CustomerTrial)
        .filter(
            db.CustomerTrial.plant_id == ids["plant_id"],
            db.CustomerTrial.customer_id == ids["customer_id"],
        )
        .first()
    )
    assert created is not None, "New customer trial was not persisted"
    assert created.foam_grade_id == ids["grade_id"]
    assert created.customer_name == ids["customer_name"]
    session.close()


def test_customer_trial_selection_edit_and_delete_via_ui(seeded_ct_trial):
    """Presets the outer Trial table's OWN on_select state (dataframe key
    'customer_trials_table', NOT the derived 'ct_selected_id' directly -
    that does not work, see this file's module docstring and the
    CR-10 template it's copied from) to row 0 before .run(), confirming
    clickable_table's row-click selection is genuinely drivable on this
    exact page. With only one trial and zero samples seeded, the nested
    'Manage samples' workspace also renders (it's inside the same
    Create Trial tab body) but shows 'No samples recorded yet' with no
    form of its own, so the single 'Save changes' button on screen is
    unambiguously this outer Edit form's.

    CR-14 (2026-08-12) replaced the old free-text customer-name input
    with a Customer selectbox (key f"ct_edit_customer_{trial_id}") - this
    switches the selection from the fixture's original Customer to its
    second seeded Customer through that real selectbox and confirms both
    customer_id and the synced customer_name persisted, then deletes the
    trial through the real confirm-checkbox + delete-button flow and
    confirms the cascade-delete removed it."""
    ids = seeded_ct_trial
    at = AppTest.from_file(PAGE_CUSTOMER_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["customer_trials_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["ct_selected_id"] == ids["trial_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded trial"
    )

    # --- Edit ---
    customer_sb = next(sb for sb in at.selectbox if sb.key == f"ct_edit_customer_{ids['trial_id']}")
    target_idx = next(i for i, opt in enumerate(customer_sb.options) if opt == ids["customer_2_name"])
    customer_sb.select_index(target_idx)
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the customer trial: {at.exception}"

    session = db.get_session()
    edited = session.get(db.CustomerTrial, ids["trial_id"])
    assert edited.customer_id == ids["customer_2_id"], "Edit did not persist the new customer_id to the database"
    assert edited.customer_name == ids["customer_2_name"], "customer_name was not synced from the newly picked customer"
    session.close()

    # --- Delete ---
    at.session_state["customer_trials_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"ct_{ids['trial_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"ct_{ids['trial_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the customer trial: {at.exception}"

    session = db.get_session()
    assert session.get(db.CustomerTrial, ids["trial_id"]) is None, "Delete did not remove the customer trial"
    session.close()


def test_customer_trial_view_only_role_cannot_delete_via_ui(view_only_ct_role_fixture):
    """CR-11 correction v2 (2026-08-12, per Charlie's CR11_Closeout_
    Correction_Review_Return_to_JC.docx item 1) - Delete permission/
    safeguards evidence for the outer Customer Trial group, page_key
    'customer_trials'. A role denied 'use' (can_view=True, can_use=False)
    via a real db.RolePagePermission row still opens the page (view-only,
    not hidden - can_view stays True) but views/11_Customer_Trials.py's
    outer tab_edit_delete block only calls delete_with_confirm(...) when
    page_usable is True; otherwise it renders the 'View-only access -
    deleting is restricted for your role.' caption instead (see that
    page's `if page_usable: delete_with_confirm(...) else: st.caption(...)`
    branch). Presets the outer Trial table's own on_select state to select
    the seeded trial (the same real-selection technique the create/edit/
    delete test above uses) and confirms neither the delete confirm
    checkbox nor the delete button render for this role, then confirms the
    trial is still in the database - direct UI-level proof the
    permission-denied delete path actually blocks the real controls, not
    just that can_use_page() itself returns False."""
    ids = view_only_ct_role_fixture
    session = db.get_session()
    assert not access_control.can_use_page(
        "customer_trials", role_id=ids["role_id"], session=session, is_super_admin=False
    )
    session.close()

    at = _run_as_role(
        PAGE_CUSTOMER_TRIALS, ids,
        extra_session_state={"customer_trials_table": {"selection": {"rows": [0], "columns": []}}},
    )
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["ct_selected_id"] == ids["trial_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded trial"
    )

    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()
    assert not any(c.key == f"ct_{ids['trial_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the outer Trial delete confirm checkbox"
    )
    assert not any(b.key == f"ct_{ids['trial_id']}_btn" for b in at.button), (
        "View-only role should not see the outer Trial delete button"
    )

    session = db.get_session()
    assert session.get(db.CustomerTrial, ids["trial_id"]) is not None, (
        "The customer trial must remain in the database after a denied delete attempt"
    )
    session.close()


def test_customer_trial_csv_import_validation_rejects_invalid_row(seeded_ct_grade_only):
    """CR-11 correction v2 (item 2): views/11_Customer_Trials.py's outer
    Trial CSV/Excel importer pre-existed CR-11 (only relabeled by it, not
    one of CR-11's six net-new importers) and so far only had
    successful-import evidence (test above). Uploads one row with an
    out-of-scope foam_grade_id (customer_name present and non-blank, so
    the rejection is isolated to the page's own
    `grade_id_val in import_grade_ids` half of its bad-row check) and
    confirms the row is flagged invalid, not silently imported: the
    'Confirm import' button only renders when good_rows is non-empty (see
    that page's `if good_trial_rows and st.button(...)` guard), so its
    absence here is direct proof of rejection."""
    ids = seeded_ct_grade_only
    at = AppTest.from_file(PAGE_CUSTOMER_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    session = db.get_session()
    before_count = session.query(db.CustomerTrial).count()
    session.close()

    csv_bytes = b"foam_grade_id,customer_name\n999999,CR11e-Correction-Bad-Grade-Customer\n"
    uploader = next(u for u in at.file_uploader if u.key == "ct_trial_upload")
    uploader.set_value(("trials_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading an invalid-foam_grade_id CSV: {at.exception}"

    assert not any(b.key == "confirm_ct_trial_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "foam_grade_id" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.CustomerTrial).count()
    session.close()
    assert after_count == before_count, "An out-of-scope foam_grade_id row must not be persisted"


def test_customer_trial_csv_import_via_ui(seeded_ct_grade_only):
    """Drives the real st.file_uploader on the outer Trial CSV/Excel
    import tab (fixed key 'ct_trial_upload') with an in-memory CSV using
    the page's own required columns (foam_grade_id, customer_name), then
    clicks the real 'Confirm import' button (key 'confirm_ct_trial_import')
    and confirms the imported row landed in the database with status
    forced to Open, exactly as views/11_Customer_Trials.py's import
    branch does."""
    ids = seeded_ct_grade_only
    at = AppTest.from_file(PAGE_CUSTOMER_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        f"foam_grade_id,customer_name\n{ids['grade_id']},CR11e-Correction-Imported-Customer\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "ct_trial_upload")
    uploader.set_value(("trials.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_ct_trial_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.CustomerTrial)
        .filter(
            db.CustomerTrial.plant_id == ids["plant_id"],
            db.CustomerTrial.customer_name == "CR11e-Correction-Imported-Customer",
        )
        .first()
    )
    assert imported is not None, "Imported customer trial was not persisted"
    assert imported.status == "Open"
    session.close()


# ---------------------------------------------------------------------------
# Customer Trials - nested "Sample" group (inside the outer Create Trial
# tab's "Manage samples" workspace)
# ---------------------------------------------------------------------------

def test_customer_trial_sample_create_via_form(seeded_ct_trial):
    """Navigation into the nested group: with exactly one trial seeded,
    the 'Manage samples' selectbox (key 'ct_manage_trial') defaults to it
    automatically on page load - no explicit selection needed - which is
    what makes the nested Sample sub-tabs (cr11_function_tab_labels
    ("Sample")) render underneath it in the first place. This then fills
    the real per-trial-id Add Sample form ('add_sample_{trial_id}') -
    the Sample Location Reference selectbox already defaults to the first
    ZONE_LABELS option - and clicks the real 'Save sample' submit button,
    confirming the new Sample row landed in the database tied to this
    trial via customer_trial_id (production_run_id/optimization_trial_id
    left NULL, per the mutually-exclusive-FK convention)."""
    ids = seeded_ct_trial
    at = AppTest.from_file(PAGE_CUSTOMER_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Customer Trials: {at.exception}"

    managed_trial_sb = next(sb for sb in at.selectbox if sb.key == "ct_manage_trial")
    assert managed_trial_sb.value.id == ids["trial_id"], (
        "With only one trial seeded, 'Manage samples' should default to it without an explicit selection"
    )

    save_btn = next(b for b in at.button if b.label == "Save sample")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new sample: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.Sample)
        .filter(db.Sample.customer_trial_id == ids["trial_id"])
        .all()
    )
    assert len(created) == 1, "New sample was not persisted against the managed trial"
    assert created[0].production_run_id is None and created[0].optimization_trial_id is None
    session.close()


def test_customer_trial_sample_selection_edit_and_delete_via_ui(seeded_ct_trial_with_sample):
    """Same dataframe-widget's-own-selection-state technique as the outer
    Trial test above, applied to the NESTED Sample table
    (key f"ct_samples_table_{trial_id}", derived selection
    f"ct_sample_selected_id_{trial_id}") - a completely separate widget
    key/session_state pair from the outer 'customer_trials_table'/
    'ct_selected_id' pair. The outer Trial table's own selection is left
    unset here (so no outer Edit form competes for the single 'Save
    changes' button on screen), which is how this test lands directly in
    the nested Sample sub-group without an explicit outer-to-nested
    navigation step - selecting the seeded sample's row edits it through
    the real per-sample Edit form and confirms persistence, then deletes
    it through the real confirm-checkbox + delete-button flow and
    confirms it was removed."""
    ids = seeded_ct_trial_with_sample
    table_key = f"ct_samples_table_{ids['trial_id']}"
    sel_key = f"ct_sample_selected_id_{ids['trial_id']}"

    at = AppTest.from_file(PAGE_CUSTOMER_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state[table_key] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset nested table selection: {at.exception}"
    assert at.session_state[sel_key] == ids["sample_id"], (
        "Presetting the nested Sample dataframe widget's own selection state should have selected the seeded sample"
    )

    # --- Edit ---
    zone_sb = next(sb for sb in at.selectbox if sb.key == f"edit_ct_sample_zone_{ids['sample_id']}")
    zone_sb.set_value("Middle")
    notes_input = next(t for t in at.text_area if t.key == f"edit_ct_sample_notes_{ids['sample_id']}")
    notes_input.set_value("Edited via CR-11 correction evidence")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the sample: {at.exception}"

    session = db.get_session()
    edited = session.get(db.Sample, ids["sample_id"])
    assert edited.zone_label == "Middle", "Edit did not persist to the database"
    assert edited.notes == "Edited via CR-11 correction evidence"
    session.close()

    # --- Delete ---
    at.session_state[table_key] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"ct_sample_{ids['sample_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"ct_sample_{ids['sample_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the sample: {at.exception}"

    session = db.get_session()
    assert session.get(db.Sample, ids["sample_id"]) is None, "Delete did not remove the sample"
    session.close()


def test_customer_trial_sample_view_only_role_cannot_delete_via_ui(view_only_ct_role_fixture):
    """CR-11 correction v2 (item 1) - Delete permission/safeguards
    evidence for the NESTED Sample group under Customer Trials. Verified
    from source: the nested Sample group has no page_key of its own - its
    sub_edit_delete block gates delete_with_confirm(...) off the exact
    SAME `page_usable` variable (derived from can_use_page("customer_trials",
    ...)) as the outer Trial group, one scope up. Reuses
    view_only_ct_role_fixture (same role, same page_key) rather than a
    second fixture, since that shared gating is the point being evidenced.
    Presets the NESTED Sample table's own on_select state
    (f"ct_samples_table_{trial_id}") to select the seeded sample and
    confirms neither the nested delete confirm checkbox
    (f"ct_sample_{sample_id}_confirm") nor the nested delete button
    (f"ct_sample_{sample_id}_btn") render for this role, then confirms the
    sample is still in the database."""
    ids = view_only_ct_role_fixture
    session = db.get_session()
    assert not access_control.can_use_page(
        "customer_trials", role_id=ids["role_id"], session=session, is_super_admin=False
    )
    session.close()

    table_key = f"ct_samples_table_{ids['trial_id']}"
    sel_key = f"ct_sample_selected_id_{ids['trial_id']}"
    at = _run_as_role(
        PAGE_CUSTOMER_TRIALS, ids,
        extra_session_state={table_key: {"selection": {"rows": [0], "columns": []}}},
    )
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state[sel_key] == ids["sample_id"], (
        "Presetting the nested Sample dataframe widget's own selection state should have selected the seeded sample"
    )

    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()
    assert not any(c.key == f"ct_sample_{ids['sample_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the nested Sample delete confirm checkbox"
    )
    assert not any(b.key == f"ct_sample_{ids['sample_id']}_btn" for b in at.button), (
        "View-only role should not see the nested Sample delete button"
    )

    session = db.get_session()
    assert session.get(db.Sample, ids["sample_id"]) is not None, (
        "The sample must remain in the database after a denied delete attempt"
    )
    session.close()


def test_customer_trial_sample_csv_import_validation_rejects_invalid_row(seeded_ct_trial):
    """CR-11 correction v2 (item 2): views/11_Customer_Trials.py's nested
    Sample CSV/Excel importer (also pre-existing, only relabeled by
    CR-11) so far only had successful-import evidence (test below).
    Navigates into the nested group the same way the create/valid-import
    tests do (the lone seeded trial auto-selects in 'Manage samples'),
    then uploads one row with an out-of-scope source_type ('Bogus Type',
    not in db.SAMPLE_SOURCE_TYPES) - the page's own bad-row check
    (`source_type in SAMPLE_SOURCE_TYPES and source_id_in_scope and
    str(row.get("zone_label", "")).strip()`) rejects it on that first
    clause alone - and confirms the row is flagged invalid: the
    per-trial-id 'Confirm import' button only renders when good_rows is
    non-empty, so its absence here is direct proof of rejection."""
    ids = seeded_ct_trial
    at = AppTest.from_file(PAGE_CUSTOMER_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    session = db.get_session()
    before_count = session.query(db.Sample).count()
    session.close()

    csv_bytes = b"source_type,source_id,zone_label\nBogus Type,1,Top\n"
    uploader = next(u for u in at.file_uploader if u.key == f"ct_sample_upload_{ids['trial_id']}")
    uploader.set_value(("samples_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading an invalid-source_type CSV: {at.exception}"

    assert not any(b.key == f"confirm_ct_sample_import_{ids['trial_id']}" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "source_type" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.Sample).count()
    session.close()
    assert after_count == before_count, "An invalid-source_type row must not be persisted"


def test_customer_trial_sample_csv_import_via_ui(seeded_ct_trial):
    """Navigates into the nested group the same way the create test
    above does (the lone seeded trial is auto-selected in 'Manage
    samples'), then drives the real per-trial-id st.file_uploader on the
    nested Sample CSV/Excel import sub-tab (key
    f"ct_sample_upload_{trial_id}") - this importer is deliberately
    multi-source (source_type/source_id/zone_label, not scoped to the
    trial selected above, per the page's own docstring), so the CSV row
    uses source_type='Customer Trial' + source_id=<this trial's id>, which
    tenant_scope.customer_trial_ids_for_company (via
    customer_trial_ids_for_plants) must resolve as in-scope for the
    import's own tenant-scoping check to accept it. Clicks the real
    per-trial-id 'Confirm import' button and confirms the row landed in
    the database tied to this trial."""
    ids = seeded_ct_trial
    at = AppTest.from_file(PAGE_CUSTOMER_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        f"source_type,source_id,zone_label\nCustomer Trial,{ids['trial_id']},Bottom\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == f"ct_sample_upload_{ids['trial_id']}")
    uploader.set_value(("samples.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == f"confirm_ct_sample_import_{ids['trial_id']}")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.Sample)
        .filter(db.Sample.customer_trial_id == ids["trial_id"], db.Sample.zone_label == "Bottom")
        .first()
    )
    assert imported is not None, "Imported sample was not persisted"
    session.close()


# ---------------------------------------------------------------------------
# Optimization Trials - outer "Trial" group (mirrors Customer Trials above)
# ---------------------------------------------------------------------------

def test_optimization_trial_create_via_form(seeded_ot_grade_only):
    """Drives the real Create Trial form ('add_optimization_trial').
    Unlike Customer Trial, this page has no required-field validation
    branch on create (every field beyond the auto-defaulted Product
    grade selectbox is optional) - so this fills the Improvement
    initiative reference text_input (no key, label-based, disambiguated
    from the Edit form's keyed version by t.key is None) purely so the
    created row is identifiable, then clicks the real 'Save optimization
    trial' submit button and confirms the new OptimizationTrial row
    landed in the database with the plant/grade FKs the page resolves."""
    ids = seeded_ot_grade_only
    at = AppTest.from_file(PAGE_OPTIMIZATION_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Optimization Trials: {at.exception}"

    init_ref_input = next(
        t for t in at.text_input if t.label == "Improvement initiative reference" and t.key is None
    )
    init_ref_input.set_value("CR11e-Correction-New-Initiative")
    save_btn = next(b for b in at.button if b.label == "Save optimization trial")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new optimization trial: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.OptimizationTrial)
        .filter(
            db.OptimizationTrial.plant_id == ids["plant_id"],
            db.OptimizationTrial.improvement_initiative_reference == "CR11e-Correction-New-Initiative",
        )
        .first()
    )
    assert created is not None, "New optimization trial was not persisted"
    assert created.foam_grade_id == ids["grade_id"]
    session.close()


def test_optimization_trial_selection_edit_and_delete_via_ui(seeded_ot_trial):
    """Same technique as the Customer Trial outer test: presets the
    outer Trial table's own on_select state (dataframe key
    'optimization_trials_table') to row 0 before .run(), confirming the
    derived 'ot_selected_id' picks it up. Edits the trial's improvement
    initiative reference through the real Edit form and confirms
    persistence, then deletes it through the real confirm-checkbox +
    delete-button flow and confirms the cascade-delete removed it."""
    ids = seeded_ot_trial
    at = AppTest.from_file(PAGE_OPTIMIZATION_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["optimization_trials_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset table selection: {at.exception}"
    assert at.session_state["ot_selected_id"] == ids["trial_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded trial"
    )

    # --- Edit ---
    init_ref_input = next(t for t in at.text_input if t.key == f"ot_edit_initref_{ids['trial_id']}")
    init_ref_input.set_value("CR11e-Correction-Edited-Initiative")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the optimization trial: {at.exception}"

    session = db.get_session()
    edited = session.get(db.OptimizationTrial, ids["trial_id"])
    assert edited.improvement_initiative_reference == "CR11e-Correction-Edited-Initiative", (
        "Edit did not persist to the database"
    )
    session.close()

    # --- Delete ---
    at.session_state["optimization_trials_table"] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"ot_{ids['trial_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"ot_{ids['trial_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the optimization trial: {at.exception}"

    session = db.get_session()
    assert session.get(db.OptimizationTrial, ids["trial_id"]) is None, "Delete did not remove the optimization trial"
    session.close()


def test_optimization_trial_view_only_role_cannot_delete_via_ui(view_only_ot_role_fixture):
    """CR-11 correction v2 (item 1) - Delete permission/safeguards
    evidence for the outer Optimization Trial group, page_key
    'optimization_trials'. Mirrors
    test_customer_trial_view_only_role_cannot_delete_via_ui exactly:
    views/12_Optimization_Trials.py's outer tab_edit_delete block only
    calls delete_with_confirm(...) when page_usable (derived from
    can_use_page("optimization_trials", ...)) is True; otherwise it shows
    the view-only caption. Presets the outer Trial table's own on_select
    state to select the seeded trial and confirms neither the delete
    confirm checkbox nor the delete button render for this role, then
    confirms the trial is still in the database."""
    ids = view_only_ot_role_fixture
    session = db.get_session()
    assert not access_control.can_use_page(
        "optimization_trials", role_id=ids["role_id"], session=session, is_super_admin=False
    )
    session.close()

    at = _run_as_role(
        PAGE_OPTIMIZATION_TRIALS, ids,
        extra_session_state={"optimization_trials_table": {"selection": {"rows": [0], "columns": []}}},
    )
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state["ot_selected_id"] == ids["trial_id"], (
        "Presetting the dataframe widget's own selection state should have selected the seeded trial"
    )

    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()
    assert not any(c.key == f"ot_{ids['trial_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the outer Trial delete confirm checkbox"
    )
    assert not any(b.key == f"ot_{ids['trial_id']}_btn" for b in at.button), (
        "View-only role should not see the outer Trial delete button"
    )

    session = db.get_session()
    assert session.get(db.OptimizationTrial, ids["trial_id"]) is not None, (
        "The optimization trial must remain in the database after a denied delete attempt"
    )
    session.close()


def test_optimization_trial_csv_import_validation_rejects_invalid_row(seeded_ot_grade_only):
    """CR-11 correction v2 (item 2): views/12_Optimization_Trials.py's
    outer Trial CSV/Excel importer also pre-existed CR-11 (relabeled only).
    Uploads one row with an out-of-scope foam_grade_id - this page's own
    bad-row check is `grade_id_val in import_grade_ids` alone (unlike
    Customer Trial, no customer_name/second column is required) - and
    confirms the row is flagged invalid via the absent 'Confirm import'
    button, exactly as the Customer Trial equivalent test does."""
    ids = seeded_ot_grade_only
    at = AppTest.from_file(PAGE_OPTIMIZATION_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    session = db.get_session()
    before_count = session.query(db.OptimizationTrial).count()
    session.close()

    csv_bytes = b"foam_grade_id,improvement_initiative_reference\n999999,CR11e-Correction-Bad-Grade-Initiative\n"
    uploader = next(u for u in at.file_uploader if u.key == "ot_trial_upload")
    uploader.set_value(("trials_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading an invalid-foam_grade_id CSV: {at.exception}"

    assert not any(b.key == "confirm_ot_trial_import" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "foam_grade_id" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.OptimizationTrial).count()
    session.close()
    assert after_count == before_count, "An out-of-scope foam_grade_id row must not be persisted"


def test_optimization_trial_csv_import_via_ui(seeded_ot_grade_only):
    """Drives the real st.file_uploader on the outer Trial CSV/Excel
    import tab (fixed key 'ot_trial_upload') with an in-memory CSV using
    the page's own required column (foam_grade_id only - unlike Customer
    Trial, this page requires no other column), then clicks the real
    'Confirm import' button (key 'confirm_ot_trial_import') and confirms
    the imported row landed in the database with status forced to Open."""
    ids = seeded_ot_grade_only
    at = AppTest.from_file(PAGE_OPTIMIZATION_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        f"foam_grade_id,improvement_initiative_reference\n"
        f"{ids['grade_id']},CR11e-Correction-Imported-Initiative\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == "ot_trial_upload")
    uploader.set_value(("trials.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == "confirm_ot_trial_import")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.OptimizationTrial)
        .filter(
            db.OptimizationTrial.plant_id == ids["plant_id"],
            db.OptimizationTrial.improvement_initiative_reference == "CR11e-Correction-Imported-Initiative",
        )
        .first()
    )
    assert imported is not None, "Imported optimization trial was not persisted"
    assert imported.status == "Open"
    session.close()


# ---------------------------------------------------------------------------
# Optimization Trials - nested "Sample" group (mirrors Customer Trials
# above exactly)
# ---------------------------------------------------------------------------

def test_optimization_trial_sample_create_via_form(seeded_ot_trial):
    """Navigation into the nested group: with exactly one trial seeded,
    'Manage samples' (selectbox key 'ot_manage_trial') defaults to it
    automatically, rendering the nested Sample sub-tabs underneath.
    Fills the real per-trial-id Add Sample form ('add_sample_{trial_id}')
    and clicks the real 'Save sample' submit button, confirming the new
    Sample row landed in the database tied to this trial via
    optimization_trial_id (production_run_id/customer_trial_id left
    NULL)."""
    ids = seeded_ot_trial
    at = AppTest.from_file(PAGE_OPTIMIZATION_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception, f"Unhandled exception loading Optimization Trials: {at.exception}"

    managed_trial_sb = next(sb for sb in at.selectbox if sb.key == "ot_manage_trial")
    assert managed_trial_sb.value.id == ids["trial_id"], (
        "With only one trial seeded, 'Manage samples' should default to it without an explicit selection"
    )

    save_btn = next(b for b in at.button if b.label == "Save sample")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception saving a new sample: {at.exception}"

    session = db.get_session()
    created = (
        session.query(db.Sample)
        .filter(db.Sample.optimization_trial_id == ids["trial_id"])
        .all()
    )
    assert len(created) == 1, "New sample was not persisted against the managed trial"
    assert created[0].production_run_id is None and created[0].customer_trial_id is None
    session.close()


def test_optimization_trial_sample_selection_edit_and_delete_via_ui(seeded_ot_trial_with_sample):
    """Same technique as the Customer Trial nested test: presets the
    NESTED Sample table's own on_select state (key
    f"ot_samples_table_{trial_id}", derived selection
    f"ot_sample_selected_id_{trial_id}") - independent of the outer
    'optimization_trials_table'/'ot_selected_id' pair, which is left
    unset here so only the nested Edit form's 'Save changes' button is on
    screen. Edits the seeded sample's zone label and notes through the
    real per-sample Edit form and confirms persistence, then deletes it
    through the real confirm-checkbox + delete-button flow and confirms
    it was removed."""
    ids = seeded_ot_trial_with_sample
    table_key = f"ot_samples_table_{ids['trial_id']}"
    sel_key = f"ot_sample_selected_id_{ids['trial_id']}"

    at = AppTest.from_file(PAGE_OPTIMIZATION_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state[table_key] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    assert not at.exception, f"Unhandled exception with a preset nested table selection: {at.exception}"
    assert at.session_state[sel_key] == ids["sample_id"], (
        "Presetting the nested Sample dataframe widget's own selection state should have selected the seeded sample"
    )

    # --- Edit ---
    zone_sb = next(sb for sb in at.selectbox if sb.key == f"edit_ot_sample_zone_{ids['sample_id']}")
    zone_sb.set_value("Middle")
    notes_input = next(t for t in at.text_area if t.key == f"edit_ot_sample_notes_{ids['sample_id']}")
    notes_input.set_value("Edited via CR-11 correction evidence")
    save_btn = next(b for b in at.button if b.label == "Save changes")
    save_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception editing the sample: {at.exception}"

    session = db.get_session()
    edited = session.get(db.Sample, ids["sample_id"])
    assert edited.zone_label == "Middle", "Edit did not persist to the database"
    assert edited.notes == "Edited via CR-11 correction evidence"
    session.close()

    # --- Delete ---
    at.session_state[table_key] = {"selection": {"rows": [0], "columns": []}}
    at.run()
    confirm_box = next(c for c in at.checkbox if c.key == f"ot_sample_{ids['sample_id']}_confirm")
    confirm_box.set_value(True)
    at.run()
    delete_btn = next(b for b in at.button if b.key == f"ot_sample_{ids['sample_id']}_btn")
    delete_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception deleting the sample: {at.exception}"

    session = db.get_session()
    assert session.get(db.Sample, ids["sample_id"]) is None, "Delete did not remove the sample"
    session.close()


def test_optimization_trial_sample_view_only_role_cannot_delete_via_ui(view_only_ot_role_fixture):
    """CR-11 correction v2 (item 1) - Delete permission/safeguards
    evidence for the NESTED Sample group under Optimization Trials.
    Mirrors test_customer_trial_sample_view_only_role_cannot_delete_via_ui
    exactly: verified from source that the nested Sample group here also
    has no page_key of its own - its sub_edit_delete block gates
    delete_with_confirm(...) off the same `page_usable`
    (can_use_page("optimization_trials", ...)) as the outer Trial group.
    Reuses view_only_ot_role_fixture (same role, same page_key). Presets
    the NESTED Sample table's own on_select state
    (f"ot_samples_table_{trial_id}") to select the seeded sample and
    confirms neither the nested delete confirm checkbox nor the nested
    delete button render for this role, then confirms the sample is still
    in the database."""
    ids = view_only_ot_role_fixture
    session = db.get_session()
    assert not access_control.can_use_page(
        "optimization_trials", role_id=ids["role_id"], session=session, is_super_admin=False
    )
    session.close()

    table_key = f"ot_samples_table_{ids['trial_id']}"
    sel_key = f"ot_sample_selected_id_{ids['trial_id']}"
    at = _run_as_role(
        PAGE_OPTIMIZATION_TRIALS, ids,
        extra_session_state={table_key: {"selection": {"rows": [0], "columns": []}}},
    )
    assert not at.exception, f"Unhandled exception for a view-only role: {at.exception}"
    assert at.session_state[sel_key] == ids["sample_id"], (
        "Presetting the nested Sample dataframe widget's own selection state should have selected the seeded sample"
    )

    captions = " ".join(c.value for c in at.caption)
    assert "view-only access" in captions.lower()
    assert not any(c.key == f"ot_sample_{ids['sample_id']}_confirm" for c in at.checkbox), (
        "View-only role should not see the nested Sample delete confirm checkbox"
    )
    assert not any(b.key == f"ot_sample_{ids['sample_id']}_btn" for b in at.button), (
        "View-only role should not see the nested Sample delete button"
    )

    session = db.get_session()
    assert session.get(db.Sample, ids["sample_id"]) is not None, (
        "The sample must remain in the database after a denied delete attempt"
    )
    session.close()


def test_optimization_trial_sample_csv_import_validation_rejects_invalid_row(seeded_ot_trial):
    """CR-11 correction v2 (item 2): views/12_Optimization_Trials.py's
    nested Sample CSV/Excel importer (also pre-existing, only relabeled).
    Mirrors test_customer_trial_sample_csv_import_validation_rejects_invalid_row
    exactly - navigates into the nested group (the lone seeded trial
    auto-selects in 'Manage samples'), uploads one row with an
    out-of-scope source_type ('Bogus Type', not in
    db.SAMPLE_SOURCE_TYPES), and confirms the row is flagged invalid via
    the absent per-trial-id 'Confirm import' button."""
    ids = seeded_ot_trial
    at = AppTest.from_file(PAGE_OPTIMIZATION_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    session = db.get_session()
    before_count = session.query(db.Sample).count()
    session.close()

    csv_bytes = b"source_type,source_id,zone_label\nBogus Type,1,Top\n"
    uploader = next(u for u in at.file_uploader if u.key == f"ot_sample_upload_{ids['trial_id']}")
    uploader.set_value(("samples_bad.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading an invalid-source_type CSV: {at.exception}"

    assert not any(b.key == f"confirm_ot_sample_import_{ids['trial_id']}" for b in at.button), (
        "Confirm import button should not render when every uploaded row is invalid"
    )
    warnings = " ".join(w.value for w in at.warning)
    assert "source_type" in warnings.lower()

    session = db.get_session()
    after_count = session.query(db.Sample).count()
    session.close()
    assert after_count == before_count, "An invalid-source_type row must not be persisted"


def test_optimization_trial_sample_csv_import_via_ui(seeded_ot_trial):
    """Navigates into the nested group the same way the create test
    above does (the lone seeded trial is auto-selected in 'Manage
    samples'), then drives the real per-trial-id st.file_uploader on the
    nested Sample CSV/Excel import sub-tab (key
    f"ot_sample_upload_{trial_id}") with a source_type='Optimization
    Trial' + source_id=<this trial's id> row - tenant_scope.
    optimization_trial_ids_for_company (via
    optimization_trial_ids_for_plants) must resolve this trial as
    in-scope for the import's own tenant-scoping check to accept it.
    Clicks the real per-trial-id 'Confirm import' button and confirms the
    row landed in the database tied to this trial."""
    ids = seeded_ot_trial
    at = AppTest.from_file(PAGE_OPTIMIZATION_TRIALS, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.run()
    assert not at.exception

    csv_bytes = (
        f"source_type,source_id,zone_label\nOptimization Trial,{ids['trial_id']},Bottom\n"
    ).encode()
    uploader = next(u for u in at.file_uploader if u.key == f"ot_sample_upload_{ids['trial_id']}")
    uploader.set_value(("samples.csv", csv_bytes, "text/csv"))
    at.run()
    assert not at.exception, f"Unhandled exception after uploading the CSV: {at.exception}"

    confirm_btn = next(b for b in at.button if b.key == f"confirm_ot_sample_import_{ids['trial_id']}")
    confirm_btn.click()
    at.run()
    assert not at.exception, f"Unhandled exception confirming the import: {at.exception}"

    session = db.get_session()
    imported = (
        session.query(db.Sample)
        .filter(db.Sample.optimization_trial_id == ids["trial_id"], db.Sample.zone_label == "Bottom")
        .first()
    )
    assert imported is not None, "Imported sample was not persisted"
    session.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
