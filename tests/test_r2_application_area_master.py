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
MIGRATION = os.path.join(APP_DIR, "migrations", "0011_r2wp2_application_area_master.sql")

# The active master after R2-WP2, from Charlie's ruling section 4.
EXPECTED_ACTIVE = {
    "APP-100": "Building insulation",
    "APP-210": "Cold-room wall or ceiling panel",
    "APP-310": "Refrigerator/Freezer Insulation",
    "APP-330": "Industrial Refrigeration Insulation",
    "APP-340": "Water-heater insulation",
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
