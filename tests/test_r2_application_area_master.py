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
import ast
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
from migration_sql_helpers import set_targets as _set_targets

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE_GRADES = os.path.join(APP_DIR, "views", "2_Product_Grades.py")
PAGE_AREAS = os.path.join(APP_DIR, "views", "34_Application_Areas.py")
MIGRATIONS_DIR = os.path.join(APP_DIR, "migrations")
MIGRATION = os.path.join(MIGRATIONS_DIR, "0011_r2wp2_application_area_master.sql")

# The active master after R2-WP2, from Charlie's ruling section 4.
# The controlled master after R2-WP2 completed and R2-WP4 removed the two
# retired records. Ten end uses, each named for WHAT LEAVES THE PLANT rather
# than for how the foam is made - Stefan's test, and the one that caught the
# original mapping proposing "Sprayed insulation" and "Field-installed cavity
# insulation" as if a method were an application.
EXPECTED_ACTIVE = {
    "APP-100": "Building insulation",
    "APP-110": "Roof Spray Foam",
    "APP-210": "Cold-room wall or ceiling panel",
    "APP-220": "Block and Cut-to-Shape",
    "APP-310": "Refrigerator/Freezer Insulation",
    "APP-330": "Industrial Refrigeration Insulation",
    "APP-340": "Water-Heater Insulation",
    "APP-350": "Cool Box Insulation",
    "APP-410": "Pre-insulated Pipe",
    "APP-510": "Mining Rock Stabilisation",
}

# Deleted by R2-WP4 (migration 0016). They must not come back: APP-300 was an
# umbrella with no end product of its own, and APP-320 (door) was merged into
# APP-310 when cabinet and door became one Application Area.
DELETED_BY_R2WP4 = {"APP-300", "APP-320"}

# Retired-but-present records no longer exist in the live master, but the
# application still has to handle one correctly - R2-WP2 retires before R2-WP4
# deletes, so the state is real for the length of a work package, and any
# future retirement passes through it again. The fixture therefore keeps two
# synthetic ones rather than dropping the coverage with the live rows.
SYNTHETIC_RETIRED = {"APP-800", "APP-810"}

RETIRED_BUT_TAGGED = "APP-360"

# Charlie's ruled APP-110 wording, migration 0018. Held here as a constant and
# checked against the artifact by test_seeded_app110_wording_matches_0018, so
# the fixture cannot drift away from what the migration actually writes.
APP100_RULED_DESCRIPTION = (
    "Rigid PU insulation for manufactured building-envelope products such as "
    "insulation boards and panels. Use APP-210 for cold-room wall or ceiling "
    "panels and APP-110 for roof spray foam."
)

APP110_RULED_DESCRIPTION = (
    "Rigid polyurethane foam spray-applied in place to roofs or comparable "
    "building surfaces for thermal insulation. Use APP-110 when the intended "
    "downstream application is site-applied roof or building-surface "
    "insulation. Manufactured board and panel products for the building "
    "envelope remain under APP-100."
)

# WHY THE FIXTURE CARRIES DESCRIPTIONS AT ALL
#
# It did not, until 0018. Every seeded Application Area had description=None,
# so test_no_active_area_description_teaches_the_overruled_rule scanned ten
# rows of NULL and found no offender - not because the master was clean, but
# because there was no text in it. The test had never been able to fail.
#
# That is the R1 lesson restated: a check whose fixture cannot produce the
# state it is checking for is not a check. Every active record now gets text
# phrased the ruled way, and test_the_overruled_rule_scanner_can_fail plants
# an offender to prove the scanner still bites.
def _seed_description(controlled_id, name):
    if controlled_id == "APP-100":
        return APP100_RULED_DESCRIPTION
    if controlled_id == "APP-110":
        return APP110_RULED_DESCRIPTION
    return (
        f"Rigid polyurethane foam for {name.lower()}. Use {controlled_id} when "
        f"the intended downstream application is {name.lower()}."
    )


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
            description=_seed_description(cid, name),
        )
        session.add(a); areas[cid] = a
    for cid in sorted(SYNTHETIC_RETIRED):
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
        description=_seed_description("APP-900", "Shoe sole"),
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
        for cid in DELETED_BY_R2WP4:
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
    assert not (offered_ids & SYNTHETIC_RETIRED), "a retired area was offered"
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
    _point_grade_at(seeded["grade_id"], "APP-800")
    at, errors = _save_changes_and_collect_errors(seeded["grade_id"])

    assert "retired" in errors.lower(), (
        f"A retired Application Area was not refused on save. Errors: {errors!r}"
    )
    assert "Nothing was saved" in errors

    session = db.get_session()
    grade = session.get(db.FoamGrade, seeded["grade_id"])
    assert grade.application.controlled_id == "APP-800"
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
    for retired in SYNTHETIC_RETIRED:
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
    retired = session.query(db.Application).filter_by(controlled_id="APP-800").one()
    grade = session.get(db.FoamGrade, seeded["grade_id"])
    grade.application_id = retired.id
    session.commit(); session.close()
    _clear_relevant_caches()

    at = _run(PAGE_AREAS)
    assert not at.exception
    errors = " ".join(e.value for e in at.error)
    assert "APP-800" in errors, (
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


# ---------------------------------------------------------------------------
# Section 7 - R2-WP4, the destructive step
# ---------------------------------------------------------------------------
#
# Two things go away and neither can be undone from the file that removed them:
# pu_material_families.application, the last free-text Application Area content
# in the system, and the two retired records APP-300 and APP-320.
#
# Migration 0016 carries the captured values verbatim - that is the artifact's
# job - and refuses to run if either precondition fails. These tests hold the
# END STATE, so the removals cannot be quietly undone by a later model change.


def test_legacy_family_application_field_is_gone():
    """The free-text field on PU Material Family was what let one family hold
    an application, a market and a chemistry at once - the defect R1 started
    from. R2-WP4 removes the last of it, and the Application Area now lives on
    the Product Grade."""
    cols = {c.name for c in db.PUMaterialFamily.__table__.columns}
    assert "application" not in cols, (
        "pu_material_families.application is back on the model. R2-WP4 dropped it; "
        "the Application Area belongs to the Product Grade."
    )
    assert "customer_segment" not in cols, (
        "customer_segment belongs to FoamGrade since R1-WP5."
    )


def test_r2wp4_migration_captures_before_it_destroys():
    """A capture that lives only in an earlier artifact is a capture someone
    has to know to go looking for. 0016 drops the column, so 0016 records the
    values - including the trailing space that is really in the data."""
    path = os.path.join(MIGRATIONS_DIR, "0016_r2wp4_retire_legacy_application_representations.sql")
    assert os.path.exists(path), "migration 0016 is missing"
    sql = open(path, encoding="utf-8").read()
    for value in ("Cold-room wall/ceiling panel", "Refrigerator "):
        assert value in sql, f"0016 does not record the captured value {value!r}"
    assert "APP-210" in sql and "APP-310" in sql, (
        "0016 must record where each captured value went, not only what it was."
    )
    for guard in ("still referenced by", "have no Application Area of"):
        assert guard in sql, f"0016 is missing its {guard!r} guard"


def _used_string_literals(path):
    """String literals that are USED, excluding prose.

    Same technique and same reason as tests/test_r1_pu_material_family_labels.py:
    a docstring saying "APP-320 was retired" is a record of history and must
    stay, while a literal passed to an insert is a record being recreated.
    Scanning raw text cannot tell them apart - the first version of the test
    below failed on four docstrings, which is exactly the false positive the R1
    scanner was rebuilt on the AST to avoid."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    prose = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                prose.add(id(first.value))
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            prose.add(id(node.value))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in prose):
            yield node.lineno, node.value


def test_deleted_records_are_not_recreated_anywhere():
    """APP-300 and APP-320 are gone. A seeder that recreates one would undo
    R2-WP4 on the next boot, silently."""
    offenders = []
    for name in sorted(os.listdir(APP_DIR)):
        if not name.endswith(".py") or name == "version.py":
            continue
        path = os.path.join(APP_DIR, name)
        for lineno, literal in _used_string_literals(path):
            for cid in DELETED_BY_R2WP4:
                if cid in literal:
                    offenders.append(f"{name}:{lineno}: {literal!r}")
    assert not offenders, (
        "A record deleted by R2-WP4 is referenced in live code:\n  "
        + "\n  ".join(offenders)
    )


def test_the_master_names_end_uses_not_methods():
    """The mapping error, held as a rule.

    R2-WP1 proposed five new Application Areas named after the Production
    Method codes they came from - "Sprayed insulation", "Field-installed
    cavity insulation", "Block and cut-to-shape insulation". Stefan's test
    killed three of them: what leaves the plant? Spraying is how, a roof is
    what.

    This scans the shipped master for names that describe a process. It cannot
    catch every case - naming is a judgement - but it catches the specific
    shape that got through once, which is a method word standing where an end
    product should be."""
    method_words = (
        "sprayed", "spray foam application", "field-installed", "field cavity",
        "cut-to-shape insulation", "discontinuous", "continuous panel",
        "moulding", "molding", "processing",
    )
    offenders = []
    for cid, name in EXPECTED_ACTIVE.items():
        lowered = name.lower()
        for word in method_words:
            if word in lowered:
                offenders.append(f"{cid} {name!r} contains {word!r}")
    assert not offenders, (
        "An Application Area is named for a method rather than an end product:\n  "
        + "\n  ".join(offenders)
        + "\nAsk what leaves the plant."
    )


def test_block_record_deliberately_omits_insulation():
    """Stefan: "Block and Cut to shape is definitely a separate application
    area, it is not always insulation." The name carries that - cut shapes
    serve tooling board, buoyancy and packaging too - so calling the record
    "Block and cut-to-shape insulation", as the mapping proposed, would have
    narrowed it wrongly on day one."""
    assert EXPECTED_ACTIVE["APP-220"] == "Block and Cut-to-Shape"
    assert "insulation" not in EXPECTED_ACTIVE["APP-220"].lower()


def test_roof_spray_is_its_own_record_not_a_rename_of_building_insulation():
    """APP-100 carries eight PIR board/panel reference formulations and two
    families, none of them sprayed. Narrowing it to roofs would mis-describe
    all ten, which is why roof spray foam became APP-110 instead."""
    assert EXPECTED_ACTIVE["APP-100"] == "Building insulation"
    assert EXPECTED_ACTIVE["APP-110"] == "Roof Spray Foam"


# ---------------------------------------------------------------------------
# Section 8 - cross-company leakage
# ---------------------------------------------------------------------------
#
# The first version of the Application Areas page counted product grades across
# the WHOLE database and showed the number to anyone who could open it, with a
# comment arguing that a global master deserves a global count. That was a
# cross-company leak: a user at company A could read how many grades company B
# had assigned to each Application Area, and watch those numbers change.
#
# Stefan, 21 August 2026: "There can be absolutely no leaking between
# companies."
#
# The distinction that version missed. The Application Area LIST is shared
# vocabulary - the same six Rigid records for everyone, like a unit-of-measure
# master, and not company data. How many grades a company has put on each one
# IS company data, and it does not stop being company data because it is
# expressed as an integer.
#
# These tests run with the platform-owner bypass OFF. AUTH_DISABLED sets
# is_super_admin and is_platform_owner True, so a leak test written the easy
# way passes while proving nothing - the viewer would be entitled to see
# everything. The dev bypass only setdefault()s those keys, so presetting them
# before .run() is what makes the test a real one.


def _run_as_company_user(page_path, company_id):
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["is_super_admin"] = False
    at.session_state["is_platform_owner"] = False
    at.session_state["company_id"] = company_id
    at.run()
    return at


@pytest.fixture()
def two_companies_one_area(seeded):
    """Company B puts three grades on APP-350. Company A must not be able to
    count them."""
    session = db.get_session()
    area_id = session.query(db.Application).filter_by(controlled_id="APP-350").one().id

    other = db.Company(name="Other Co", is_platform_owner=False)
    session.add(other); session.flush()
    other_plant = db.Plant(company_id=other.id, name="Other Plant")
    session.add(other_plant); session.flush()
    other_family = db.PUMaterialFamily(plant_id=other_plant.id, name="Rigid")
    session.add(other_family); session.flush()
    for i in range(3):
        session.add(db.FoamGrade(
            pu_material_family_id=other_family.id,
            grade_name=f"OTHER-GRADE-{i}",
            application_id=area_id,
        ))
    session.commit()
    ids = {"other_company_id": other.id, "area_id": area_id}
    session.close()
    _clear_relevant_caches()
    return ids


def test_grade_counts_do_not_leak_another_companys_data(seeded, two_companies_one_area):
    """The leak itself. Company A opens the page; company B's three grades on
    APP-350 must be invisible, as a count as much as as a row."""
    at = _run_as_company_user(PAGE_AREAS, seeded["company_id"])
    assert not at.exception

    text = _page_text(at)
    assert "APP-350" in text, "APP-350 should still be listed - the vocabulary is shared"

    # Find the count metric by its LABEL. The first version of this test
    # scanned every metric's value for the number 3 and failed on the "Retired"
    # count, which is a property of the shared master and not company data - a
    # false positive that would have sent me to fix code that was already
    # correct.
    counts = {m.label: str(m.value) for m in at.metric}
    own = next((v for k, v in counts.items() if "product grades" in k.lower()), None)
    assert own is not None, f"No grade-count metric on the page: {counts}"
    assert own == "1", (
        f"Company A should see only its own 1 grade; saw {own}. Company B's three "
        f"grades on APP-350 are leaking. All metrics: {counts}"
    )
    assert "4" not in counts.values(), (
        f"The global total is on screen for a company user: {counts}"
    )


def test_scoped_count_column_is_labelled_as_the_viewers_own(seeded, two_companies_one_area):
    """A number a viewer cannot verify is worse than no number. If the count
    is their own slice, the column has to say so - otherwise it reads as the
    global total and the page lies quietly."""
    at = _run_as_company_user(PAGE_AREAS, seeded["company_id"])
    assert not at.exception
    text = _page_text(at)
    assert "Your product grades" in text, (
        "A company user's grade count is not labelled as their own."
    )


def _run_as_platform_owner_of(page_path, company_id):
    """A platform owner WITH a company of their own.

    Written this way after a mutation survived. The obvious version used the
    plain AUTH_DISABLED entry point, where company_id is None - and
    tenant_scope.plant_ids_for_company(None) means "unfiltered". So scoping
    the platform owner produced the same result as not scoping them, the
    branch was never observable, and a mutation that scoped EVERYONE passed
    the whole suite. Giving the owner a real company_id is what makes the two
    branches differ: scoped would show 1, global shows 4."""
    at = AppTest.from_file(page_path, default_timeout=30)
    at.secrets["AUTH_DISABLED"] = True
    at.session_state["is_super_admin"] = True
    at.session_state["is_platform_owner"] = True
    at.session_state["company_id"] = company_id
    at.run()
    return at


def test_platform_owner_still_sees_the_true_total(seeded, two_companies_one_area):
    """Scoping must not blind the one role whose job IS cross-company scope.
    Without this, the two tests above would pass just as well against a page
    that showed nobody anything."""
    at = _run_as_platform_owner_of(PAGE_AREAS, seeded["company_id"])
    assert not at.exception
    text = _page_text(at)
    assert "Your product grades" not in text, (
        "The platform owner's column should read as the global total, not a slice."
    )
    counts = {m.label: str(m.value) for m in at.metric}
    total = next((v for k, v in counts.items() if "product grades" in k.lower()), None)
    assert total == "4", (
        f"Platform owner should see all 4 assigned grades (1 seeded + 3 other), "
        f"got {total}. Metrics: {counts}"
    )


def test_no_application_area_is_named_after_a_customer():
    """The one way the shared vocabulary itself could leak.

    The master is global by ruling - "All tenants and plants use this one
    controlled master" - so every company reads every name. That is fine while
    the names are generic end uses. It stops being fine the moment one is
    created for a named customer, because the master then becomes a directory
    of who is doing what.

    Checked against the customers actually in the database rather than against
    a word list, so it keeps working as customers are added."""
    session = db.get_session()
    customer_names = {
        c.company_name.strip().lower()
        for c in session.query(db.Customer).all()
        if c.company_name and c.company_name.strip()
    }
    company_names = {
        c.name.strip().lower()
        for c in session.query(db.Company).all()
        if c.name and c.name.strip()
    }
    session.close()

    offenders = []
    for cid, name in EXPECTED_ACTIVE.items():
        lowered = name.lower()
        for owner in customer_names | company_names:
            if len(owner) > 3 and owner in lowered:
                offenders.append(f"{cid} {name!r} contains the name {owner!r}")
    assert not offenders, (
        "An Application Area is named after a company or customer. The master is "
        "shared by every tenant, so that name is visible to all of them:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Section 9 - the classification rule, after Charlie overruled mine
# ---------------------------------------------------------------------------
#
# Migration 0014 wrote a rule into five descriptions: classify by the END
# PRODUCT, by what leaves the plant. Charlie replaced it in his v3 release:
#
#   "Application Area is the downstream polyurethane application for which a
#    Product Grade or formulation is intended. A system house may ship
#    chemical even when the intended application is refrigerator insulation,
#    roof spray foam, pre-insulated pipe or another downstream use."
#
# He is right, and not as a matter of taste. Applied literally to PTU the old
# rule returns NOTHING - PTU ships chemical, so no end product leaves its plant
# matching any record. RF-Refrigerator-001 is correctly on APP-310 only because
# Stefan told us the intended use is a refrigerator cabinet and door, which is
# the downstream rule, not the leaves-the-plant one.
#
# The descriptions are what the next person reads while classifying a grade, so
# a master carrying the overruled rule teaches it. Migration 0017 corrected the
# five records Charlie listed, using his wording verbatim.

# "end product" is on this list from 0018 onward. It is not a synonym of the
# other two - it is the same overruled rule wearing different words. APP-110
# carried it after 0017 and read as correct, which is exactly the danger: a
# master that explains itself two ways teaches two rules, and the reader picks
# whichever record is in front of them.
OVERRULED_RULE_PHRASES = ("leaves the plant", "leaving the plant", "end product")


def test_no_active_area_description_teaches_the_overruled_rule(seeded):
    """Scanned across the whole active master rather than the five corrected
    records, because the point is that the rule must not come back on a sixth.

    Takes the fixture explicitly. It used to run on whatever database the
    previous test happened to leave behind, which is how it went a whole work
    package scanning NULL descriptions and reporting a clean master."""
    session = db.get_session()
    offenders = [
        f"{a.controlled_id}: {a.description!r}"
        for a in session.query(db.Application).filter(db.Application.is_active.is_(True)).all()
        if a.description and any(p in a.description.lower() for p in OVERRULED_RULE_PHRASES)
    ]
    session.close()
    assert not offenders, (
        "An Application Area description still teaches the overruled "
        '"what leaves the plant" rule:\n  ' + "\n  ".join(offenders)
    )


def test_correction_migration_changes_descriptions_only():
    """Charlie's scope limit, held as a test: "Do not change Application Area
    IDs, names, PU Material Family tags, Product Grade links or any other
    classification data."

    A migration that quietly renamed or re-tagged a record while correcting
    its prose would be reclassifying the master under cover of a wording fix,
    and the browser evidence would not show it."""
    path = os.path.join(
        MIGRATIONS_DIR, "0017_r2_description_correction_downstream_application.sql"
    )
    assert os.path.exists(path), "migration 0017 is missing"
    sql = open(path, encoding="utf-8").read()

    import re
    # Strip whole-line comments first. Without this the leading comment block
    # is glued to the first UPDATE and the statement count comes out one short
    # - the test failed that way on its first run, which is the same
    # prose-versus-code trap as the R1 terminology scanner.
    code = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    statements = [x.strip() for x in code.split(";") if x.strip().lower().startswith("update applications")]
    assert len(statements) == 5, f"Expected exactly 5 UPDATE statements, found {len(statements)}"
    for stmt in statements:
        # Shared parser, not a local regex. The obvious re.findall(r"set\s+(\w+)\s*=")
        # only ever sees the FIRST assignment - a second one arrives as ", name = ..."
        # with no "set" in front of it - so a widened UPDATE passed this check
        # unnoticed in R3-WP1. See tests/migration_sql_helpers.py.
        assigned = _set_targets(stmt)
        assert assigned == ["description"], (
            f"An UPDATE in 0017 writes something other than description: {assigned}"
        )
    for forbidden in ("alter table", "insert into applications", "delete from"):
        assert forbidden not in code.lower(), (
            f"0017 contains {forbidden!r} - it must change description text only"
        )


def test_0017_left_app110_alone_and_said_why():
    """0017's scope, held as a historical fact about an applied artifact.

    Charlie listed five records to correct and APP-110 was not among them.
    Correcting a sixth record on a controlled master without authority is
    scope creep, so 0017 left it and raised it for his ruling instead. He
    then ruled it in, and 0018 carries the correction - but 0017 is applied
    and ledgered and does not change. This test guards that boundary: the
    reason APP-110 sat out of 0017 must stay readable in 0017.
    """
    path = os.path.join(
        MIGRATIONS_DIR, "0017_r2_description_correction_downstream_application.sql"
    )
    sql = open(path, encoding="utf-8").read()
    assert "APP-110 IS NOT TOUCHED" in sql, (
        "0017 must record why APP-110 was left alone, not simply omit it."
    )
    code = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    statements = [x for x in code.split(";") if x.strip().lower().startswith("update applications")]
    assert not any("APP-110" in x for x in statements), (
        "APP-110 was modified by 0017; Charlie authorised five records and this is not one."
    )


def test_0018_aligns_app110_and_changes_nothing_else():
    """Charlie's APP-110 ruling, 21 August 2026:

        "Bring APP-110 into the same wording standard. Its current description
         points to the correct application, but still explains the distinction
         through physical end product and delivery form. The controlled master
         should use one rule throughout."

    Scope was explicit - description only, ID, name, PU Material Family tag,
    active state and links unchanged. That is what is asserted here, from the
    artifact rather than from the outcome, because an outcome check alone
    cannot tell a narrow migration from a wide one that happened to land in
    the same place.
    """
    path = os.path.join(MIGRATIONS_DIR, "0018_r2_app110_description_alignment.sql")
    assert os.path.exists(path), "migration 0018 is missing"
    sql = open(path, encoding="utf-8").read()

    import re as _re
    code = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    statements = [
        x.strip() for x in code.split(";")
        if x.strip().lower().startswith("update applications")
    ]
    assert len(statements) == 1, (
        f"0018 must contain exactly one UPDATE, found {len(statements)}"
    )
    stmt = statements[0]
    assert "APP-110" in stmt, "0018's UPDATE does not target APP-110"
    assigned = _set_targets(stmt)
    assert assigned == ["description"], (
        f"0018 writes something other than description: {assigned}"
    )
    for forbidden in ("alter table", "insert into applications", "delete from"):
        assert forbidden not in code.lower(), (
            f"0018 contains {forbidden!r} - it must change description text only"
        )


# Deliberately a duplicate of OVERRULED_RULE_PHRASES, not a reference to it.
#
# The negative control below first read the list under test and planted
# whatever was in it. That made it self-referential: a mutation deleting
# "end product" from OVERRULED_RULE_PHRASES deleted its own coverage in the
# same stroke, and all 42 tests stayed green. A control that takes its input
# from the thing it is controlling is not a control.
#
# These are the three phrasings of the rule Charlie overruled - two from his
# v3 release, "end product" added by his APP-110 ruling of 21 August 2026.
# Removing one from the list under test now fails here, loudly.
PHRASES_THAT_MUST_BE_CAUGHT = ("leaves the plant", "leaving the plant", "end product")


# A source tag answers "where did this record come from". A description
# answers "should I classify this grade here". APP-100 carried the first in
# place of the second until Charlie ruled on it, 21 Aug 2026: "The current
# source tag is useful as provenance, but it should not serve as the
# user-facing description of a controlled Application Area."
#
# Provenance lives in the migration record. These markers must not come back
# into the master's user-facing text - the import that put one there will run
# again the next time a vocabulary is loaded from a spreadsheet.
PROVENANCE_MARKERS = ("WP1 Controlled Master Data", "04_Applications", "Controlled Master Data")


def test_no_active_description_is_a_provenance_tag(seeded):
    session = db.get_session()
    offenders = [
        f"{a.controlled_id}: {a.description!r}"
        for a in session.query(db.Application).filter(db.Application.is_active.is_(True)).all()
        if a.description and any(m in a.description for m in PROVENANCE_MARKERS)
    ]
    session.close()
    assert not offenders, (
        "An Application Area description is a source tag rather than a "
        "description:\n  " + "\n  ".join(offenders)
    )


def test_the_provenance_scanner_can_fail(seeded):
    """Negative control, with its planted text written as an independent
    literal rather than read from PROVENANCE_MARKERS - Charlie's rule after
    the phrase-list control was found reading the list it was controlling."""
    session = db.get_session()
    area = session.query(db.Application).filter(
        db.Application.controlled_id == "APP-100").one()
    original = area.description
    area.description = (
        "Thermal insulation products used in the building envelope or building "
        "services. (WP1 Controlled Master Data, 04_Applications)"
    )
    session.commit()
    caught = [
        a.controlled_id
        for a in session.query(db.Application).filter(db.Application.is_active.is_(True)).all()
        if a.description and any(m in a.description for m in PROVENANCE_MARKERS)
    ]
    area.description = original
    session.commit()
    session.close()
    assert "APP-100" in caught, (
        "APP-100's original source-tag description was planted and the scanner "
        "did not see it."
    )


def test_every_active_area_has_a_description(seeded):
    """The condition that made the phrase scanner vacuous, held as a check in
    its own right. A master with an empty description is not merely untidy -
    it is a record that teaches nothing and a scan that finds nothing."""
    session = db.get_session()
    blank = [
        a.controlled_id
        for a in session.query(db.Application).filter(db.Application.is_active.is_(True)).all()
        if not (a.description or "").strip()
    ]
    session.close()
    assert not blank, "Active Application Areas with no description: " + ", ".join(blank)


def test_0020_aligns_app100_and_changes_nothing_else():
    """Charlie's APP-100 ruling, 21 August 2026, section 3. Scope read off the
    artifact for the same reason as 0018.

    Note the number. He wrote "expected to be 0019 if still free"; it was not -
    R3-WP1's Production Unit inventory had taken it - so this is 0020 under his
    standing rule that an existing artifact is never renumbered."""
    path = os.path.join(MIGRATIONS_DIR, "0020_r3_app100_description_alignment.sql")
    assert os.path.exists(path), "migration 0020 is missing"
    sql = open(path, encoding="utf-8").read()

    code = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    statements = [x.strip() for x in code.split(";")
                  if x.strip().lower().startswith("update applications")]
    assert len(statements) == 1, f"0020 must contain exactly one UPDATE, found {len(statements)}"
    stmt = statements[0]
    assert "APP-100" in stmt, "0020's UPDATE does not target APP-100"
    assert _set_targets(stmt) == ["description"], (
        f"0020 writes something other than description: {_set_targets(stmt)}"
    )
    for forbidden in ("alter table", "insert into applications", "delete from"):
        assert forbidden not in code.lower(), (
            f"0020 contains {forbidden!r} - it must change description text only"
        )
    assert "0019" in sql, (
        "0020 must record why it is not 0019 - a migration number that moves "
        "without explanation reads as an error later."
    )


def test_seeded_app100_wording_matches_0020(seeded):
    from_artifact = _description_written_by(
        "0020_r3_app100_description_alignment.sql", "APP-100"
    )
    assert from_artifact == APP100_RULED_DESCRIPTION, (
        "The APP-100 wording in this test file has drifted from migration 0020.\n"
        f"  artifact: {from_artifact!r}\n"
        f"  fixture:  {APP100_RULED_DESCRIPTION!r}"
    )
    session = db.get_session()
    app100 = session.query(db.Application).filter(
        db.Application.controlled_id == "APP-100").one()
    name, active, tag, desc = (
        app100.name, app100.is_active, app100.pu_material_family, app100.description)
    session.close()
    assert name == "Building insulation", "0020 was scoped to description; the name moved"
    assert active is True, "0020 was scoped to description; the active state moved"
    assert tag == "Rigid", "0020 was scoped to description; the family tag moved"
    assert desc == APP100_RULED_DESCRIPTION


def test_the_overruled_rule_scanner_can_fail(seeded):
    """Negative control for the test above.

    Plants each overruled phrase on a live-shaped record and asserts the scan
    catches it. Without this, the scanner passing means either "the master is
    clean" or "the scanner is looking at nothing", and those are not the same
    result.
    """
    for phrase in PHRASES_THAT_MUST_BE_CAUGHT:
        session = db.get_session()
        area = (
            session.query(db.Application)
            .filter(db.Application.controlled_id == "APP-100")
            .one()
        )
        original = area.description
        area.description = f"Classify by what {phrase} - the {phrase} decides."
        session.commit()

        offenders = [
            a.controlled_id
            for a in session.query(db.Application)
            .filter(db.Application.is_active.is_(True))
            .all()
            if a.description
            and any(p in a.description.lower() for p in OVERRULED_RULE_PHRASES)
        ]

        area.description = original
        session.commit()
        session.close()

        assert "APP-100" in offenders, (
            f"The scanner missed a planted {phrase!r}. Either it is not capable "
            "of failing, or the phrase has been dropped from "
            "OVERRULED_RULE_PHRASES - both let the overruled rule back into the "
            "controlled master."
        )


def _description_written_by(migration_filename, controlled_id):
    """Recover the description text a controlled migration writes.

    Postgres adjacent-string-literal concatenation, so the value is spread over
    several quoted chunks; they are joined in order."""
    import re as _re
    path = os.path.join(MIGRATIONS_DIR, migration_filename)
    sql = open(path, encoding="utf-8").read()
    code = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    for stmt in code.split(";"):
        if not stmt.strip().lower().startswith("update applications"):
            continue
        if controlled_id not in stmt:
            continue
        body = stmt.split("where", 1)[0]
        chunks = _re.findall(r"'([^']*)'", body)
        return "".join(chunks)
    raise AssertionError(
        f"{migration_filename} has no UPDATE targeting {controlled_id}"
    )


def test_seeded_app110_wording_matches_0018(seeded):
    """The suite runs on SQLite; the controlled master lives in Postgres and is
    written by migration files this suite never executes. So the strongest
    thing assertable here is that the wording the fixture (and therefore every
    picker and page test below) uses is byte-identical to what 0018 writes.

    Deployment itself is verified in the browser, per Charlie's instruction to
    "verify the deployed wording in the Application Areas page" - a test file
    cannot stand in for that, and should not pretend to.
    """
    from_artifact = _description_written_by(
        "0018_r2_app110_description_alignment.sql", "APP-110"
    )
    assert from_artifact == APP110_RULED_DESCRIPTION, (
        "The APP-110 wording in this test file has drifted from migration 0018.\n"
        f"  artifact: {from_artifact!r}\n"
        f"  fixture:  {APP110_RULED_DESCRIPTION!r}"
    )

    session = db.get_session()
    app110 = (
        session.query(db.Application)
        .filter(db.Application.controlled_id == "APP-110")
        .one()
    )
    name, active, tag, desc = (
        app110.name, app110.is_active, app110.pu_material_family, app110.description
    )
    session.close()

    assert name == "Roof Spray Foam", "0018 was scoped to description; the name moved"
    assert active is True, "0018 was scoped to description; the active state moved"
    assert tag == "Rigid", "0018 was scoped to description; the family tag moved"
    assert desc == APP110_RULED_DESCRIPTION
    assert "intended downstream application" in desc, (
        "APP-110's description must state the downstream rule explicitly, "
        "not merely be compatible with it."
    )
