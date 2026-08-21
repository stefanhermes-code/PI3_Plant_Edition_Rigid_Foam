"""R2-WP2 and R2-WP3 (Application Area consolidation) coverage.
Redesign Migration Plan v5, Package C.

WHAT R2 DECIDED, AND WHY THESE TESTS LOOK LIKE THIS

R2-WP1 asked whether a Product Grade serving two applications needs a
many-to-many relationship. Stefan confirmed PTU's system fills both a
refrigerator cabinet and a door. Charlie did not add a join table and did not
promote an umbrella record: he judged the classification too fine. Cabinet and
door became ONE Application Area - APP-310 renamed "Refrigerator/Freezer
Insulation" - and APP-320 was retired.

So foam_grades.application_id stays singular, and section 4 of that ruling is
explicit: "No Product Grade/Application Area association table is to be
created." test_no_grade_to_application_association_table below is the standing
guard on that, because the pressure to add one will come back the next time a
grade looks like it serves two things.

The second decision worth encoding: the APP- numbers are a controlled
identifier and an ordering convention, NOT a parent-child hierarchy (ruling
section 6). APP-300 is retired rather than treated as the parent of the
refrigeration group. Nothing in the code may start inferring a hierarchy from
the numbers.

WHAT R1 TAUGHT THAT IS APPLIED HERE IN ADVANCE

Three defects in R1 reached the deployed application and none was caught by
the suite. Two of their lessons are built into this file rather than
rediscovered:

  1. A controlled vocabulary collapses a uniqueness the rest of the app was
     relying on. R1 made every plant's family "Rigid" and nine pickers went
     ambiguous. R2 tags Application Areas with that same vocabulary, so the
     selectors get their context requirement tested from the start - Charlie
     made it a ruling: "Application Area selectors must display enough context
     to prevent ambiguous choices."
  2. A field that reaches the schema and not the screen has not been moved,
     it has been deleted with the schema left behind. R1-WP5 shipped
     customer_segment that way. Before this work there was NO Application Area
     picker anywhere in the application - the column existed and no user could
     set it. The round-trip tests below exist so that cannot ship again.

Usage: python -m pytest tests/test_r2_application_area_master.py -v
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
import helpers
import tenant_scope

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_GRADES = os.path.join(APP_DIR, "views", "2_Product_Grades.py")
PAGE_AREAS = os.path.join(APP_DIR, "views", "34_Application_Areas.py")
MIGRATION = os.path.join(APP_DIR, "migrations", "0011_r2wp2_application_area_master.sql")

# The active master after R2-WP2, from Charlie's ruling section 4.
EXPECTED_ACTIVE = {
    "APP-100": "Building insulation",
    "APP-210": "Cold-room wall or ceiling panel",
    "APP-310": "Refrigerator/Freezer Insulation",
    "APP-330": "Industrial Refrigeration Insulation",
    "APP-340": "Water-Heater Insulation",
    "APP-350": "Cool Box Insulation",
}
EXPECTED_RETIRED = {"APP-300", "APP-320"}

# A retired area that is STILL TAGGED Rigid. Migration 0011 deliberately leaves
# APP-300 and APP-320 untagged, which means a picker filtering only by family
# would exclude them for the wrong reason and look correct while doing it -
# that is exactly what happened here: removing the is_active filter from
# selectable_application_areas() passed the whole suite. This row makes the two
# filters independently observable, and it is not hypothetical: a later
# migration can retire an area that was already tagged.
RETIRED_BUT_TAGGED = "APP-360"


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


@pytest.fixture()
def seeded():
    """The post-0011 master, plus a Rigid family and one grade at each plant -
    the live shape after R2-WP2."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    areas = {}
    for i, (cid, name) in enumerate(sorted(EXPECTED_ACTIVE.items())):
        a = db.Application(
            controlled_id=cid, name=name, sort_order=int(cid.split("-")[1]),
            is_active=True, pu_material_family="Rigid",
        )
        session.add(a); areas[cid] = a
    for cid in sorted(EXPECTED_RETIRED):
        a = db.Application(
            controlled_id=cid, name=f"retired {cid}", sort_order=int(cid.split("-")[1]),
            is_active=False, pu_material_family=None,
        )
        session.add(a); areas[cid] = a
    tagged_retired = db.Application(
        controlled_id=RETIRED_BUT_TAGGED, name="Retired but still tagged Rigid",
        sort_order=360, is_active=False, pu_material_family="Rigid",
    )
    session.add(tagged_retired); areas[RETIRED_BUT_TAGGED] = tagged_retired
    # An area belonging to a DIFFERENT family - nothing under a Rigid family
    # may select it. Without this row the family-match tests prove nothing,
    # because there would be no wrong answer available.
    other = db.Application(
        controlled_id="APP-900", name="Shoe sole", sort_order=900,
        is_active=True, pu_material_family="Elastomers",
    )
    session.add(other); areas["APP-900"] = other
    session.flush()

    company = db.Company(name=f"R2 Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"R2 Plant {u}")
    session.add(plant); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name="Rigid")
    session.add(family); session.flush()
    grade = db.FoamGrade(
        pu_material_family_id=family.id, grade_name=f"RF-{u}",
        application_id=areas["APP-210"].id,
    )
    session.add(grade); session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "family_id": family.id,
        "grade_id": grade.id, "grade_name": grade.grade_name,
        "areas": {cid: a.id for cid, a in areas.items()},
    }
    session.close()
    return ids


def _run(page_path, session_state=None):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    for key, value in (session_state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


# ---------------------------------------------------------------------------
# Section 1 - the migration artifact says what the ruling says
# ---------------------------------------------------------------------------

def test_migration_exists_and_is_the_only_source_of_the_master():
    """No seeder may recreate a retired record behind the migration's back.

    APP-320 is retired by 0011 and deleted by R2-WP4. If any module still
    creates it at startup, it comes back on the next boot and the retirement
    silently undoes itself."""
    assert os.path.exists(MIGRATION), "migration 0011 is missing"
    sql = open(MIGRATION, encoding="utf-8").read()
    for cid in ("APP-310", "APP-330", "APP-350", "APP-320", "APP-300"):
        assert cid in sql, f"{cid} is not handled by migration 0011"

    offenders = []
    for name in sorted(os.listdir(APP_DIR)):
        if not name.endswith(".py") or name == "version.py":
            continue
        text = open(os.path.join(APP_DIR, name), encoding="utf-8").read()
        for cid in EXPECTED_RETIRED:
            for line in text.splitlines():
                if cid in line and "insert" in line.lower():
                    offenders.append(f"{name}: {line.strip()}")
    assert not offenders, (
        "A retired Application Area is re-created in application code:\n  "
        + "\n  ".join(offenders)
    )


def test_no_grade_to_application_association_table():
    """Charlie's ruling section 4: "No Product Grade/Application Area
    association table is to be created."

    This is a standing guard, not a formality. R2-WP1 argued for exactly such
    a table on the evidence that PTU's system serves a cabinet and a door;
    the ruling settled it the other way by merging the two areas. The next
    grade that looks like it serves two things will produce the same argument,
    so the decision is encoded where it will be tripped over."""
    table_names = set(db.Base.metadata.tables)
    for name in table_names:
        lowered = name.lower()
        assert not ("grade" in lowered and "application" in lowered), (
            f"Table {name!r} looks like a Product Grade/Application Area association "
            "table, which R2 explicitly forbids."
        )
    grade_cols = {c.name for c in db.FoamGrade.__table__.columns}
    assert "application_id" in grade_cols, (
        "The singular foam_grades.application_id relationship must remain."
    )


def test_application_carries_the_r2_columns():
    cols = {c.name for c in db.Application.__table__.columns}
    assert "is_active" in cols
    assert "pu_material_family" in cols


# ---------------------------------------------------------------------------
# Section 2 - the selectable set
# ---------------------------------------------------------------------------

def test_selectable_areas_exclude_retired_and_other_families(seeded):
    """The R2-WP3 family-match rule, enforced by filtering rather than by
    complaining afterwards."""
    session = db.get_session()
    offered = helpers.selectable_application_areas(session, "Rigid")
    offered_ids = {a.controlled_id for a in offered}

    assert offered_ids == set(EXPECTED_ACTIVE), (
        f"Expected exactly the six active Rigid areas, got {sorted(offered_ids)}"
    )
    assert not (offered_ids & EXPECTED_RETIRED), "a retired area was offered"
    assert RETIRED_BUT_TAGGED not in offered_ids, (
        "A retired Application Area that still carries the right family tag was "
        "offered. The is_active filter is what must exclude it - the family "
        "filter cannot, and relying on the tag being absent is luck."
    )
    assert "APP-900" not in offered_ids, "an Elastomers area was offered under Rigid"
    session.close()


def test_selectable_areas_are_ordered_by_sort_order(seeded):
    session = db.get_session()
    offered = helpers.selectable_application_areas(session, "Rigid")
    orders = [a.sort_order for a in offered]
    assert orders == sorted(orders), f"Application Areas out of sort order: {orders}"
    session.close()


def test_sort_order_is_not_read_as_a_hierarchy(seeded):
    """Ruling section 6: the APP numbering is an identifier and an ordering
    convention, not a parent-child relationship.

    A future reader looking at APP-310/320/330/340 will be tempted to treat
    APP-300 as their parent - that is exactly the reading Charlie rejected. If
    a parent column ever appears on this model, this test is where the
    decision gets re-opened deliberately instead of by accident."""
    cols = {c.name for c in db.Application.__table__.columns}
    for suspicious in ("parent_id", "parent_application_id", "band", "level"):
        assert suspicious not in cols, (
            f"Application.{suspicious} implies the APP- numbering is a hierarchy. "
            "Charlie's ruling of 21 August 2026 section 6 says it is not."
        )


# ---------------------------------------------------------------------------
# Section 3 - the label carries context (R1's lesson, applied in advance)
# ---------------------------------------------------------------------------

def test_area_label_carries_the_controlled_identifier(seeded):
    session = db.get_session()
    area = session.query(db.Application).filter_by(controlled_id="APP-310").one()
    label = helpers.application_area_label(area)
    assert "APP-310" in label
    assert "Refrigerator/Freezer Insulation" in label
    assert helpers.application_area_label(area, include_id=False) == \
        "Refrigerator/Freezer Insulation"
    session.close()


def test_area_label_survives_none_and_a_missing_identifier():
    class _Bare:
        name = "Something"
        controlled_id = None

    assert helpers.application_area_label(None) == "—"
    assert helpers.application_area_label(_Bare()) == "Something"


def test_no_two_offered_areas_render_identically(seeded):
    """The R1 collision, checked before it can happen here."""
    session = db.get_session()
    labels = [helpers.application_area_label(a)
              for a in helpers.selectable_application_areas(session, "Rigid")]
    duplicates = {l for l in labels if labels.count(l) > 1}
    assert not duplicates, f"Indistinguishable Application Area options: {sorted(duplicates)}"
    session.close()


# ---------------------------------------------------------------------------
# Section 4 - the picker exists and round-trips (R1-WP5's lesson)
# ---------------------------------------------------------------------------

def test_product_grades_page_offers_an_application_area_field(seeded):
    """Before R2 there was no Application Area picker anywhere in the
    application. The column existed and no user could reach it."""
    at = _run(PAGE_GRADES)
    assert not at.exception
    labels = [w.label for w in at.selectbox if w.label]
    assert "Application Area" in labels, (
        f"Product Grades has no Application Area picker. Selectboxes: {labels}"
    )


def test_creating_a_grade_persists_its_application_area(seeded):
    """AppTest reports a selectbox by its FORMATTED option text, so the label
    helper is on the assertion path here as well as on the screen."""
    at = _run(PAGE_GRADES)
    assert not at.exception
    new_name = "R2-NEW-GRADE"

    picker = next(w for w in at.selectbox if w.label == "Application Area")
    target = next(o for o in picker.options if "APP-310" in str(o))
    picker.set_value(target)
    at.run()
    assert not at.exception

    for widget in at.text_input:
        if widget.label == "Grade name / code *":
            widget.set_value(new_name)
    for button in at.button:
        if button.label == "Save product grade":
            button.click()
            break
    at.run()
    assert not at.exception

    session = db.get_session()
    saved = session.query(db.FoamGrade).filter_by(grade_name=new_name).one()
    assert saved.application is not None, "Application Area was accepted and then dropped"
    assert saved.application.controlled_id == "APP-310"
    session.close()


def test_edit_form_shows_the_stored_area_and_updates_it(seeded):
    at = _run(PAGE_GRADES, session_state={
        "grades_table": {"selection": {"rows": [0], "columns": []}},
    })
    assert not at.exception

    key = f"edit_grade_application_{seeded['grade_id']}"
    picker = next((w for w in at.selectbox if w.key == key), None)
    assert picker is not None, (
        f"Edit panel has no Application Area picker (key {key!r}); "
        f"keys present: {[w.key for w in at.selectbox]}"
    )
    # AppTest returns .options as formatted strings but .value as the raw
    # option object - assert against the object, format against the strings.
    assert getattr(picker.value, "controlled_id", None) == "APP-210", (
        f"The stored Application Area did not come back into the edit form "
        f"(showed {picker.value!r}) - saving any other change would have cleared it."
    )

    target = next(o for o in picker.options if "APP-350" in str(o))
    picker.set_value(target)
    at.run()
    for button in at.button:
        if button.label == "Save changes":
            button.click()
            break
    at.run()
    assert not at.exception

    session = db.get_session()
    grade = session.get(db.FoamGrade, seeded["grade_id"])
    assert grade.application.controlled_id == "APP-350"
    session.close()


def test_grade_table_shows_the_application_area(seeded):
    at = _run(PAGE_GRADES)
    assert not at.exception
    assert at.dataframe
    columns = []
    for element in at.dataframe:
        columns.extend(list(getattr(element.value, "columns", [])))
    assert "Application Area" in columns, (
        f"Product Grades table does not surface Application Area. Columns: {columns}"
    )


# ---------------------------------------------------------------------------
# Section 5 - the family-match rule holds on save, not only in the picker
# ---------------------------------------------------------------------------
#
# The picker cannot offer a wrong answer, so the wrong answer is planted in the
# database instead - which is how it will really arrive. An import can write
# any application_id, and R2-WP2 can re-tag an Application Area to a different
# family after grades are already pointing at it. In both cases the grade is
# sitting on an invalid area before anyone opens the form, and the edit panel
# deliberately keeps the stored value selectable so it stays visible rather
# than being silently rewritten. The save path is therefore the last line, and
# these two tests are what stand on it.


def _point_grade_at(grade_id, controlled_id):
    session = db.get_session()
    area = session.query(db.Application).filter_by(controlled_id=controlled_id).one()
    grade = session.get(db.FoamGrade, grade_id)
    grade.application_id = area.id
    session.commit()
    session.close()
    _clear_relevant_caches()


def _save_changes_and_collect_errors(grade_id):
    at = _run(PAGE_GRADES, session_state={
        "grades_table": {"selection": {"rows": [0], "columns": []}},
    })
    assert not at.exception
    for button in at.button:
        if button.label == "Save changes":
            button.click()
            break
    at.run()
    assert not at.exception
    return at, " ".join(e.value for e in at.error)


def test_save_refuses_an_area_from_another_pu_material_family(seeded):
    _point_grade_at(seeded["grade_id"], "APP-900")
    at, errors = _save_changes_and_collect_errors(seeded["grade_id"])

    assert "Elastomers" in errors, (
        f"A cross-family Application Area was not refused on save. Errors: {errors!r}"
    )
    assert "Nothing was saved" in errors

    session = db.get_session()
    grade = session.get(db.FoamGrade, seeded["grade_id"])
    assert grade.application.controlled_id == "APP-900", (
        "The save was refused, so the row must be untouched - not silently corrected."
    )
    session.close()


def test_save_refuses_a_retired_area(seeded):
    _point_grade_at(seeded["grade_id"], "APP-320")
    at, errors = _save_changes_and_collect_errors(seeded["grade_id"])

    assert "retired" in errors.lower(), (
        f"A retired Application Area was not refused on save. Errors: {errors!r}"
    )
    assert "Nothing was saved" in errors

    session = db.get_session()
    grade = session.get(db.FoamGrade, seeded["grade_id"])
    assert grade.application.controlled_id == "APP-320"
    session.close()


def test_a_valid_area_still_saves(seeded):
    """The two refusals above would pass just as well against a guard that
    refuses everything. This is the test that says it does not."""
    at, errors = _save_changes_and_collect_errors(seeded["grade_id"])
    assert not errors, f"A valid grade was refused on save: {errors!r}"
    session = db.get_session()
    grade = session.get(db.FoamGrade, seeded["grade_id"])
    assert grade.application.controlled_id == "APP-210"
    session.close()


def test_unset_is_allowed(seeded):
    """Not every grade has an Application Area yet, and R2-WP3 does not
    require one. Refusing an empty value would be a different bug."""
    at = _run(PAGE_GRADES, session_state={
        "grades_table": {"selection": {"rows": [0], "columns": []}},
    })
    assert not at.exception
    picker = next(w for w in at.selectbox
                  if w.key == f"edit_grade_application_{seeded['grade_id']}")
    assert "Not set" in [str(o) for o in picker.options], (
        f"The picker offers no way to clear the value: {list(picker.options)}"
    )
    picker.set_value("Not set")
    at.run()
    for button in at.button:
        if button.label == "Save changes":
            button.click()
            break
    at.run()
    assert not at.exception
    session = db.get_session()
    grade = session.get(db.FoamGrade, seeded["grade_id"])
    assert grade.application_id is None
    session.close()


# ---------------------------------------------------------------------------
# Section 6 - the master has a page, and the hierarchy is stated in full
# ---------------------------------------------------------------------------
#
# v0.77.0 shipped the LINK to the Application Area master and no page for the
# master itself. Stefan caught it: an Application Area is a level of the
# architecture, not a field on another record, and once Production Method
# retires in R3 it is one of the records taking over that role.
#
# He also corrected how the hierarchy had been described. It is not
# "PU Material Family -> Application Area -> Product Grade". It is:
#
#     Company -> Plant -> Production Unit -> PU Material Family
#                                         -> Application Area -> Product Grade
#
# Read as depth, not as one parent chain: the Plant branches into the
# operational side (Production Unit) and the product side (PU Material Family),
# and the two meet again at Product Grade, which names the units that can make
# it. v5 keeps the family plant-scoped - "a plant may manufacture the same PU
# Material Family on more than one unit" - so a family cannot have a single
# unit as its parent.
#
# That start matters and is not decoration. Company and Plant are where
# row-level access begins, and a Product Grade reaches its plant through its
# PU Material Family. Application Area is the one level that is global rather
# than tenant-owned, which is exactly why the hierarchy is enforced by
# validation instead of by making the area the grade's parent - a global
# record has no plant for the permission path to follow.


def test_application_areas_page_exists_and_is_registered():
    assert os.path.exists(PAGE_AREAS), "views/34_Application_Areas.py is missing"
    assert access_control.PAGE_CATALOG.get("application_areas") == "Application Areas"


def test_nav_places_the_master_in_hierarchy_order():
    """Between PU Material Families and Product Grades, because that is where
    it sits in the chain. A master filed anywhere else teaches the wrong
    shape."""
    source = open(os.path.join(APP_DIR, "app_rigid_foam.py"), encoding="utf-8").read()
    start = source.index("production_method_pages = [")
    block = source[start:source.index("]", start)]
    order = ["pu_material_families", "application_areas", "product_grades"]
    positions = [block.index(f'"{key}"') for key in order]
    assert positions == sorted(positions), (
        f"Application Areas is out of hierarchy order in the sidebar: {positions} for {order}"
    )
    assert 'title="Application Areas"' in source


def test_the_page_states_the_hierarchy_from_the_top():
    """The chain starts at Company, not at PU Material Family.

    This is a documentation test on purpose. The truncated version - starting
    at PU Material Family - is what made the design look like it had lost a
    level, and the reason re-parenting is refused only makes sense once Company
    and Plant are in the sentence."""
    source = open(PAGE_AREAS, encoding="utf-8").read()
    assert "Company -> Plant -> Production Unit -> PU Material Family" in source, (
        "The page must state the structure from the top, starting at Company and "
        "including Production Unit - Stefan's ordering of 21 August 2026."
    )
    for term in ("Company", "Plant", "Production Unit", "global"):
        assert term in source, f"{term!r} missing from the structure description"


def _page_text(at):
    """helpers.render_data_table() builds its own HTML and emits it through
    st.markdown rather than st.dataframe, so the listing is in the markdown
    stream. Reading the wrong stream is how the first version of this test
    passed while looking at the edit panel's table instead of the listing."""
    parts = [str(el.value) for el in at.markdown]
    parts += [str(el.value) for el in at.subheader]
    parts += [str(el.value) for el in at.caption]
    return " ".join(parts)


def test_application_areas_page_renders_and_lists_the_master(seeded):
    at = _run(PAGE_AREAS)
    assert not at.exception
    text = _page_text(at)
    for cid in EXPECTED_ACTIVE:
        assert cid in text, f"{cid} is not listed on the Application Areas page"
    assert "Refrigerator/Freezer Insulation" in text
    assert "Cool Box Insulation" in text


def test_page_separates_active_from_retired(seeded):
    """A retired area must stay visible rather than vanish - anything still
    pointing at one has to be findable before R2-WP4 removes it."""
    at = _run(PAGE_AREAS)
    assert not at.exception
    headings = [str(el.value) for el in at.subheader]
    assert "Active" in headings and "Retired" in headings, (
        f"Active and retired are not shown as separate sections: {headings}"
    )
    text = _page_text(at)
    for retired in EXPECTED_RETIRED:
        assert retired in text, f"{retired} disappeared from the master page"


def test_page_shows_the_grade_count_per_area(seeded):
    """Retiring an area is only safe if you can see what uses it."""
    at = _run(PAGE_AREAS)
    assert not at.exception
    text = _page_text(at)
    assert "Product grades" in text, "No grade count column on the master page"


def test_page_warns_about_an_active_untagged_area(seeded):
    """An active area with no family tag can be selected by nobody, because
    the Product Grades picker filters on the tag. It would sit in the master
    looking available and be unreachable - the same shape as a column with no
    field, which is the defect this whole work package exists to correct."""
    session = db.get_session()
    session.add(db.Application(
        controlled_id="APP-990", name="Untagged and active",
        sort_order=990, is_active=True, pu_material_family=None,
    ))
    session.commit(); session.close()
    _clear_relevant_caches()

    at = _run(PAGE_AREAS)
    assert not at.exception
    warnings = " ".join(w.value for w in at.warning)
    assert "APP-990" in warnings, (
        f"An active, untagged Application Area was not flagged. Warnings: {warnings!r}"
    )


def test_page_flags_a_retired_area_that_still_has_grades(seeded):
    session = db.get_session()
    retired = session.query(db.Application).filter_by(controlled_id="APP-320").one()
    grade = session.get(db.FoamGrade, seeded["grade_id"])
    grade.application_id = retired.id
    session.commit(); session.close()
    _clear_relevant_caches()

    at = _run(PAGE_AREAS)
    assert not at.exception
    errors = " ".join(e.value for e in at.error)
    assert "APP-320" in errors, (
        f"A retired area still carrying grades was not flagged. Errors: {errors!r}"
    )


def test_page_offers_no_create_or_delete(seeded):
    """A global master is not edited like tenant data. New records and
    retirements arrive as controlled changes with migration evidence - the
    route APP-350, APP-300 and APP-320 all took. A create button here would
    let one tenant change every tenant's vocabulary with no artifact behind
    it."""
    at = _run(PAGE_AREAS)
    assert not at.exception
    labels = [b.label.lower() for b in at.button if b.label]
    for forbidden in ("add", "create", "delete", "remove"):
        assert not any(forbidden in l for l in labels), (
            f"Application Areas offers a {forbidden!r} control: {labels}"
        )
