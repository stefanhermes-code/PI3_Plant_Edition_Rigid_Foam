"""Phase 8 Decision 3 - controlled chemical role on recipe components (2026-08-19).

Evidence for the closeout list in section 7 of Charlie's Decision 3 Design
Ruling and Implementation Instructions.

WHAT DECISION 3 IS FOR

Decision 2 recorded which physical stream a machine runs a chemical role on.
That is half the A:B ratio answer. This is the other half: what a material IS
in one formulation - Isocyanate Component or Polyol Blend Component.

Neither half may be derived from the other, and neither may be derived from
anything convenient. The temptation is real and the live data shows it: of the
five components on Recipe Version 6, two have a raw material category that
looks decisive (Polyol, Isocyanate) and three do not (Catalyst, Surfactant,
Blowing Agent). A catalyst, a surfactant and a physical blowing agent are
USUALLY carried in the polyol blend. Usually is not evidence - a pre-mixed
blend, a co-catalyst dosed on the isocyanate side, or a third-stream additive
would each break it, and nothing in the data would show that it had.

So a role exists only when a controlled document says so, and the document is
stored with it. The database makes the two inseparable.

Ruling section 7 item -> test:

  five components unchanged, chemical_role NULL after migration
    -> live evidence, recorded in the closeout, plus
       test_the_new_columns_are_additive_and_nullable
  controlled vocabulary enforcement
    -> test_only_the_two_controlled_terms_are_accepted
       test_the_vocabulary_is_the_same_object_decision_2_uses
  all-or-none provenance, including blank source location
    -> test_a_role_without_a_source_is_rejected
       test_a_blank_source_location_is_rejected
       test_a_whitespace_only_source_location_is_rejected
       test_source_fields_cannot_be_stranded_without_a_role
       test_clearing_a_role_clears_its_provenance
  zero inferred backfill
    -> test_no_module_infers_a_chemical_role_from_anything
       test_a_component_whose_category_is_isocyanate_still_reads_unresolved
  correction auditing through the existing controlled-edit path
    -> test_an_assignment_summary_names_the_previous_value
       test_the_audit_path_accepts_a_recipe_component_target
  stream_assignment absent from the controlled paths
    -> test_the_controlled_modules_never_mention_stream_assignment
       test_a_populated_stream_assignment_changes_nothing
  machine-convention independence
    -> test_one_recipe_two_machines_opposite_conventions
  resolver returns A, B or None with no default
    -> test_an_unresolved_component_yields_no_stream
       test_an_unstamped_run_yields_no_stream

Usage: python -m pytest tests/test_phase8_decision3_chemical_role.py -v
"""
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
import sqlalchemy as sa

import component_role
import db
import machine_stream as ms

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ISO = component_role.ISOCYANATE_COMPONENT
POLYOL = component_role.POLYOL_BLEND_COMPONENT

JAN = dt.datetime(2026, 1, 1)
MAR = dt.datetime(2026, 3, 1)


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def fixture(request):
    """A plant, two machines with OPPOSITE conventions, one recipe version.

    The two machines are the point: every resolution test below can then ask
    the same question twice and require different answers.
    """
    db.init_db()
    _reset_schema()
    session = db.get_session()

    plant = db.Plant(name="Rigid Plant 1")
    session.add(plant)
    session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name="Appliance Cavity")
    session.add(family)
    session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name="RG-100")
    session.add(grade)
    session.flush()
    version = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1")
    session.add(version)
    source = db.SourceRegister(
        controlled_id="SRC-900",
        source_type="Internal controlled master",
        reference="Formulation record FR-2026-01",
    )
    line_1 = db.Machine(plant_id=plant.id, name="Line 1")
    line_2 = db.Machine(plant_id=plant.id, name="Line 2")
    session.add_all([source, line_1, line_2])
    session.flush()

    data = {
        "session": session, "plant": plant, "grade": grade, "version": version,
        "source": source, "line_1": line_1, "line_2": line_2,
    }
    yield data
    session.rollback()
    session.close()


def _component(fixture, name, php, role=None, source=True, location="Table 3, row 2",
               category=None, stream_assignment=None, role_in_formulation=None):
    session = fixture["session"]
    component = db.RecipeComponent(
        recipe_version_id=fixture["version"].id,
        raw_material_name=name,
        php=php,
        role_in_formulation=role_in_formulation,
        stream_assignment=stream_assignment,
    )
    if role is not None:
        component.chemical_role = role
        component.chemical_role_source_id = fixture["source"].id if source else None
        component.chemical_role_source_location = location
    session.add(component)
    session.flush()
    return component


def _configuration(fixture, machine, roles):
    session = fixture["session"]
    configuration = db.MachineStreamConfiguration(
        controlled_id=ms.next_controlled_id(session),
        machine_id=machine.id,
        revision=ms.next_revision(session, machine.id),
        effective_from=JAN,
        status=ms.STATUS_DRAFT,
        source_reference="Commissioning report",
        approved_by="Plant Engineering",
        approved_at=JAN,
    )
    session.add(configuration)
    session.flush()
    for label, role in roles.items():
        session.add(db.MachineStreamAssignment(
            machine_stream_configuration_id=configuration.id,
            stream_label=label, chemical_role=role))
    session.flush()
    session.refresh(configuration)
    ms.activate(session, configuration)
    return configuration


def _run(fixture, machine, stamp=True):
    session = fixture["session"]
    run = db.ProductionRun(
        plant_id=fixture["plant"].id,
        foam_grade_id=fixture["grade"].id,
        recipe_version_id=fixture["version"].id,
        run_date=MAR.date(),
        run_start=MAR,
        machine_id=machine.id,
    )
    session.add(run)
    session.flush()
    if stamp:
        ms.stamp_run(session, run)
    return run


# ---------------------------------------------------------------------------
# Controlled vocabulary
# ---------------------------------------------------------------------------

def test_only_the_two_controlled_terms_are_accepted(fixture):
    _component(fixture, "Lupranate M20", 145, role=ISO)
    _component(fixture, "Lupranol 3300", 100, role=POLYOL)

    bad = db.RecipeComponent(
        recipe_version_id=fixture["version"].id,
        raw_material_name="Mystery",
        chemical_role="A-side",
        chemical_role_source_id=fixture["source"].id,
        chemical_role_source_location="Table 3",
    )
    fixture["session"].add(bad)
    with pytest.raises(sa.exc.IntegrityError):
        fixture["session"].flush()
    fixture["session"].rollback()


def test_the_vocabulary_is_the_same_object_decision_2_uses(fixture):
    """Not merely equal - the same tuple.

    Two independent copies of a controlled vocabulary is how a controlled
    vocabulary stops being controlled: one gets extended, the other does not,
    and nothing fails until a role that the formulation side accepts cannot be
    mapped by the machine side.
    """
    assert component_role.CHEMICAL_ROLES is ms.CHEMICAL_ROLES
    assert component_role.ISOCYANATE_COMPONENT is ms.ISOCYANATE_COMPONENT
    assert component_role.POLYOL_BLEND_COMPONENT is ms.POLYOL_BLEND_COMPONENT


# ---------------------------------------------------------------------------
# All-or-none provenance
# ---------------------------------------------------------------------------

def test_a_role_without_a_source_is_rejected(fixture):
    component = db.RecipeComponent(
        recipe_version_id=fixture["version"].id,
        raw_material_name="Lupranate M20",
        chemical_role=ISO,
    )
    fixture["session"].add(component)
    with pytest.raises(sa.exc.IntegrityError):
        fixture["session"].flush()
    fixture["session"].rollback()


def test_a_blank_source_location_is_rejected(fixture):
    component = db.RecipeComponent(
        recipe_version_id=fixture["version"].id,
        raw_material_name="Lupranate M20",
        chemical_role=ISO,
        chemical_role_source_id=fixture["source"].id,
        chemical_role_source_location="",
    )
    fixture["session"].add(component)
    with pytest.raises(sa.exc.IntegrityError):
        fixture["session"].flush()
    fixture["session"].rollback()


def test_a_whitespace_only_source_location_is_rejected(fixture):
    """Charlie's ruling says non-empty AFTER trimming. A space is not a
    citation, and it is exactly what gets typed to get past a required field."""
    component = db.RecipeComponent(
        recipe_version_id=fixture["version"].id,
        raw_material_name="Lupranate M20",
        chemical_role=ISO,
        chemical_role_source_id=fixture["source"].id,
        chemical_role_source_location="   ",
    )
    fixture["session"].add(component)
    with pytest.raises(sa.exc.IntegrityError):
        fixture["session"].flush()
    fixture["session"].rollback()


def test_source_fields_cannot_be_stranded_without_a_role(fixture):
    """The other direction: provenance left behind after a role is cleared."""
    component = db.RecipeComponent(
        recipe_version_id=fixture["version"].id,
        raw_material_name="Lupranate M20",
        chemical_role_source_id=fixture["source"].id,
        chemical_role_source_location="Table 3",
    )
    fixture["session"].add(component)
    with pytest.raises(sa.exc.IntegrityError):
        fixture["session"].flush()
    fixture["session"].rollback()


def test_an_unresolved_component_carries_none_of_the_three(fixture):
    component = _component(fixture, "Cyclopentane", 12)
    assert component.chemical_role is None
    assert component.chemical_role_source_id is None
    assert component.chemical_role_source_location is None
    assert component_role.is_resolved(component) is False


def test_clearing_a_role_clears_its_provenance(fixture):
    component = _component(fixture, "Lupranate M20", 145, role=ISO)
    assert component_role.is_resolved(component) is True

    component_role.clear_role(component)
    fixture["session"].flush()

    assert component.chemical_role is None
    assert component.chemical_role_source_id is None
    assert component.chemical_role_source_location is None


def test_validate_assignment_reports_every_problem_at_once(fixture):
    problems = component_role.validate_assignment("A-side", None, "  ")
    assert len(problems) == 3


def test_assign_role_refuses_an_incomplete_assignment(fixture):
    component = _component(fixture, "Lupranate M20", 145)
    with pytest.raises(component_role.RoleAssignmentRefused):
        component_role.assign_role(component, ISO, None, "Table 3")
    assert component.chemical_role is None


# ---------------------------------------------------------------------------
# Zero inferred backfill
# ---------------------------------------------------------------------------

def test_a_component_whose_category_is_isocyanate_still_reads_unresolved(fixture):
    """The behavioural half of the no-inference rule.

    Everything that could be used to guess is present and populated - a
    material named like an isocyanate, a role_in_formulation saying so, and a
    stream_assignment. The component still reads Unresolved, because none of
    those is the document that establishes it.
    """
    session = fixture["session"]
    category = db.RawMaterialCategory(name="Isocyanate", controlled_id="RMC2-200")
    session.add(category)
    session.flush()
    material = db.RawMaterial(name="Lupranate M20", category="Isocyanate", category_id=category.id)
    session.add(material)
    session.flush()

    component = _component(
        fixture, "Lupranate M20", 145,
        role_in_formulation="Isocyanate",
        stream_assignment="A-side",
    )
    component.raw_material_id = material.id
    session.flush()

    assert component_role.role_of(component) is None
    assert component_role.is_resolved(component) is False


def test_no_module_infers_a_chemical_role_from_anything(fixture):
    """The source half.

    Flags any line in the two controlled modules that assigns chemical_role
    from one of the excluded bases. The behavioural test above proves today's
    behaviour; this one stops a later contributor adding a helpful default.
    """
    excluded = re.compile(
        r"chemical_role\s*=\s*[^=]*(category|raw_material_name|role_in_formulation|stream_assignment)"
    )
    offenders = []
    for name in ("component_role.py", "machine_stream.py"):
        path = os.path.join(REPO_ROOT, name)
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if line.lstrip().startswith("#"):
                    continue
                if excluded.search(line):
                    offenders.append(f"{name}:{number}: {line.strip()}")
    assert not offenders, "chemical_role inferred from an excluded basis:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# stream_assignment stays outside the controlled paths
# ---------------------------------------------------------------------------

def test_the_controlled_modules_never_mention_stream_assignment(fixture):
    """Ruling section 5: the controlled role and ratio paths rely exclusively
    on chemical_role plus the stamped configuration.

    Tokenised rather than line-scanned. Both modules DISCUSS stream_assignment
    in their docstrings - explaining why it is deliberately not used is part of
    the record - and a naive text scan would flag exactly the comments that
    exist to prevent the mistake. What matters is that no executable code
    touches it.
    """
    import io
    import tokenize

    offenders = []
    for name in ("component_role.py", "machine_stream.py"):
        path = os.path.join(REPO_ROOT, name)
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            if token.type == tokenize.NAME and token.string == "stream_assignment":
                offenders.append(f"{name}:{token.start[0]}: {token.line.strip()}")
    assert not offenders, (
        "stream_assignment is referenced in executable code on a controlled path:\n"
        + "\n".join(offenders)
    )


def test_a_populated_stream_assignment_changes_nothing(fixture):
    """Belt and braces: even with the legacy field filled in and contradicting
    the controlled configuration, resolution follows the controlled path."""
    iso = _component(fixture, "Lupranate M20", 145, role=ISO, stream_assignment="B-side")
    _component(fixture, "Lupranol 3300", 100, role=POLYOL, stream_assignment="A-side")
    _configuration(fixture, fixture["line_1"], {"A": ISO, "B": POLYOL})
    run = _run(fixture, fixture["line_1"])

    assert component_role.component_stream_for_run(fixture["session"], run, iso) == "A"


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------

def test_one_recipe_two_machines_opposite_conventions(fixture):
    """The property the whole Decision 2/3 pair exists to give.

    One formulation. Two machines plumbed opposite ways. The role-space totals
    are identical because they are a property of the formulation; only the
    stream labels differ, and they differ correctly.
    """
    iso = _component(fixture, "Lupranate M20", 145, role=ISO)
    polyol = _component(fixture, "Lupranol 3300", 100, role=POLYOL)
    _configuration(fixture, fixture["line_1"], {"A": ISO, "B": POLYOL})
    _configuration(fixture, fixture["line_2"], {"A": POLYOL, "B": ISO})

    run_1 = _run(fixture, fixture["line_1"])
    run_2 = _run(fixture, fixture["line_2"])
    session = fixture["session"]
    version = fixture["version"]

    assert component_role.component_stream_for_run(session, run_1, iso) == "A"
    assert component_role.component_stream_for_run(session, run_1, polyol) == "B"
    assert component_role.component_stream_for_run(session, run_2, iso) == "B"
    assert component_role.component_stream_for_run(session, run_2, polyol) == "A"

    # Role space is machine-independent...
    roles = component_role.php_by_chemical_role(version)
    assert roles == {ISO: 145.0, POLYOL: 100.0}

    # ...and only the relabelling differs.
    assert component_role.php_by_stream_for_run(session, run_1, version) == {"A": 145.0, "B": 100.0}
    assert component_role.php_by_stream_for_run(session, run_2, version) == {"A": 100.0, "B": 145.0}


def test_an_unresolved_component_yields_no_stream(fixture):
    unresolved = _component(fixture, "Cyclopentane", 12)
    _configuration(fixture, fixture["line_1"], {"A": ISO, "B": POLYOL})
    run = _run(fixture, fixture["line_1"])

    assert component_role.component_stream_for_run(fixture["session"], run, unresolved) is None


def test_an_unstamped_run_yields_no_stream(fixture):
    iso = _component(fixture, "Lupranate M20", 145, role=ISO)
    _configuration(fixture, fixture["line_1"], {"A": ISO, "B": POLYOL})
    run = _run(fixture, fixture["line_1"], stamp=False)

    assert run.machine_stream_configuration_id is None
    assert component_role.component_stream_for_run(fixture["session"], run, iso) is None


def test_one_unresolved_component_blocks_the_whole_version(fixture):
    """A partial sum is a smaller number that looks like a real one."""
    _component(fixture, "Lupranate M20", 145, role=ISO)
    _component(fixture, "Lupranol 3300", 100, role=POLYOL)
    _component(fixture, "Cyclopentane", 12)

    version = fixture["version"]
    fixture["session"].refresh(version)
    assert component_role.recipe_version_is_resolved(version) is False
    assert component_role.php_by_chemical_role(version) is None
    assert [c.raw_material_name for c in component_role.unresolved_components(version)] == ["Cyclopentane"]


def test_an_empty_recipe_version_is_not_resolved(fixture):
    """Nothing to sum is not the same as everything resolved."""
    version = fixture["version"]
    fixture["session"].refresh(version)
    assert component_role.recipe_version_is_resolved(version) is False


def test_the_resolution_summary_says_which_half_is_missing(fixture):
    """Two different jobs for the user - complete a formulation record, or
    activate a machine configuration - so they are reported separately."""
    _component(fixture, "Lupranate M20", 145, role=ISO)
    _component(fixture, "Cyclopentane", 12)
    run = _run(fixture, fixture["line_1"], stamp=False)

    session = fixture["session"]
    version = fixture["version"]
    session.refresh(version)
    summary = component_role.run_component_resolution(session, run, version)

    assert summary["resolved"] is False
    assert summary["machine_stream_resolved"] is False
    assert [c.raw_material_name for c in summary["unresolved_components"]] == ["Cyclopentane"]


# ---------------------------------------------------------------------------
# Audit of assignments and corrections
# ---------------------------------------------------------------------------

def test_an_assignment_summary_names_the_previous_value(fixture):
    """A change log that records only the new value cannot answer the question
    anyone actually asks later, which is what it used to say."""
    component = _component(fixture, "Lupranate M20", 145)
    first = component_role.describe_assignment(component, ISO, "Table 3, row 2")
    assert "Unresolved" in first and ISO in first

    component_role.assign_role(component, ISO, fixture["source"].id, "Table 3, row 2")
    correction = component_role.describe_assignment(component, POLYOL, "Table 4, row 1")
    assert ISO in correction and POLYOL in correction and "->" in correction


def test_the_audit_path_accepts_a_recipe_component_target(fixture):
    """Charlie required corrections to be audited through the EXISTING
    controlled-edit path rather than a new mechanism. That path is
    RoleChangeLog, and this asserts a chemical-role row lands in it and is
    distinguishable from the access-role rows that share the table."""
    import audit_log

    session = fixture["session"]
    component = _component(fixture, "Lupranate M20", 145)
    audit_log.log_role_change(
        session,
        target_type="recipe_component",
        change_summary=component_role.describe_assignment(component, ISO, "Table 3, row 2"),
        target_id=component.id,
        target_label=component.raw_material_name,
    )
    session.flush()

    rows = session.query(db.RoleChangeLog).filter(
        db.RoleChangeLog.target_type == "recipe_component"
    ).all()
    assert len(rows) == 1
    assert rows[0].target_id == component.id
    assert "Unresolved" in rows[0].change_summary
    # The column is String(20); "recipe_component" is 16. Pinned because a
    # longer target_type would silently truncate on Postgres and break the
    # only thing distinguishing these rows from access-role changes.
    assert db.RoleChangeLog.__table__.columns["target_type"].type.length >= len("recipe_component")


# ---------------------------------------------------------------------------
# Migration shape
# ---------------------------------------------------------------------------

def test_the_new_columns_are_additive_and_nullable():
    columns = db.RecipeComponent.__table__.columns
    for name in ("chemical_role", "chemical_role_source_id", "chemical_role_source_location"):
        assert columns[name].nullable is True, f"{name} must be nullable - no backfill was performed"


def test_the_role_source_reference_is_restricted():
    """A source register entry cited by a controlled role must not be deletable
    out from under it."""
    column = db.RecipeComponent.__table__.columns["chemical_role_source_id"]
    foreign_key = list(column.foreign_keys)[0]
    assert foreign_key.ondelete.upper() == "RESTRICT"


def test_both_constraints_exist_and_are_named_separately():
    """Named separately so a violation says which rule was broken."""
    names = {c.name for c in db.RecipeComponent.__table__.constraints if c.name}
    assert "ck_rc_chemical_role_vocabulary" in names
    assert "ck_rc_chemical_role_provenance" in names


def test_schema_creation_is_idempotent():
    db.Base.metadata.create_all(db.ENGINE)
    before = sorted(sa.inspect(db.ENGINE).get_table_names())
    db.Base.metadata.create_all(db.ENGINE)
    assert sorted(sa.inspect(db.ENGINE).get_table_names()) == before


# ---------------------------------------------------------------------------
# Review corrections (2026-08-19)
#
# An independent adversarial review found four defects in the first cut of
# Decision 3, and - more usefully - found that two of Charlie's nine closeout
# items were asserted in prose while no test could fail if the production code
# implementing them were deleted. Mutation-checked: removing both audit calls
# from the save path AND flipping the role selector off Unresolved left 26/26
# passing.
#
# The tests below are written against that standard. Each one was verified to
# fail when the specific line it protects is reverted.
# ---------------------------------------------------------------------------

def test_a_null_source_location_is_rejected(fixture):
    """THE defect. trim(NULL) is NULL, "FALSE OR NULL" is NULL, and a CHECK
    passes on NULL - so a role with a source and a NULL location was accepted
    by both SQLite and live Postgres. Verbatim the partial-provenance state the
    ruling forbids ("a role with only a document reference").

    The original probes tested '' and '   ' and never NULL, which is exactly
    why the gap survived into the closeout evidence.
    """
    component = db.RecipeComponent(
        recipe_version_id=fixture["version"].id,
        raw_material_name="Lupranate M20",
        chemical_role=ISO,
        chemical_role_source_id=fixture["source"].id,
        chemical_role_source_location=None,
    )
    fixture["session"].add(component)
    with pytest.raises(sa.exc.IntegrityError):
        fixture["session"].flush()
    fixture["session"].rollback()


def test_a_source_location_cannot_be_nulled_out_from_under_a_live_role(fixture):
    """The update path of the same defect: a row that was valid on insert must
    not be reducible to a role with no citation."""
    component = _component(fixture, "Lupranate M20", 145, role=ISO)
    fixture["session"].flush()

    component.chemical_role_source_location = None
    with pytest.raises(sa.exc.IntegrityError):
        fixture["session"].flush()
    fixture["session"].rollback()


def test_a_missing_php_blocks_the_role_totals(fixture):
    """A component can carry a perfectly good controlled role and no dosage.
    `php or 0.0` then contributed nothing and the totals came back looking
    complete - a ratio of 0.0 indistinguishable downstream from a measured one.
    """
    _component(fixture, "Lupranate M20", None, role=ISO)
    _component(fixture, "Lupranol 3300", 100, role=POLYOL)
    version = fixture["version"]
    fixture["session"].refresh(version)

    assert component_role.recipe_version_is_resolved(version) is True
    assert component_role.php_by_chemical_role(version) is None


def test_the_audit_summary_names_the_source_document(fixture):
    """A correction that changed only the source register entry used to produce
    a line byte-identical to a no-op re-save. An audit record that cannot show
    the field that changed is not an audit record."""
    component = _component(fixture, "Lupranate M20", 145, role=ISO)

    same_role_new_source = component_role.describe_assignment(
        component, ISO, "Table 3, row 2", source_label="SRC-901 · Patent"
    )
    same_role_old_source = component_role.describe_assignment(
        component, ISO, "Table 3, row 2", source_label="SRC-900 · Internal"
    )
    assert same_role_new_source != same_role_old_source
    assert "SRC-901" in same_role_new_source


def test_the_page_writes_an_audit_row_on_the_save_path(fixture):
    """Closeout item 'correction auditing through the existing controlled-edit
    path', asserted against the PAGE rather than against audit_log.

    The previous version of this file called log_role_change() itself, so it
    passed with the page's audit calls deleted. This reads the page source and
    requires the writer to be invoked on the save path, and requires the writer
    to add a RoleChangeLog row.
    """
    page = os.path.join(REPO_ROOT, "views", "3_Recipe_Version_Record.py")
    with open(page, encoding="utf-8") as handle:
        source = handle.read()

    assert "_record_chemical_role_change(session, component, summary, user)" in source, (
        "the chemical-role save path no longer records a controlled-edit audit row"
    )
    assert source.count("_record_chemical_role_change(session, component, summary, user)") >= 2, (
        "both the assignment and the clear path must be audited"
    )
    assert 'target_type="recipe_component"' in source
    assert "RoleChangeLog(" in source


def test_the_audit_row_is_written_in_the_same_transaction_as_the_assignment(fixture):
    """The save path must not be able to report success while discarding the
    assignment.

    audit_log.log_role_change() swallows exceptions and its _safe_flush() calls
    session.rollback() on failure - and because the audit row shares the
    transaction with the assignment, a failed audit write rolled the ASSIGNMENT
    back too, after which the page committed nothing and still said success.
    The save path must therefore NOT use that helper.
    """
    import io
    import tokenize

    page = os.path.join(REPO_ROOT, "views", "3_Recipe_Version_Record.py")
    with open(page, encoding="utf-8") as handle:
        source = handle.read()

    # Tokenised: the page's docstring legitimately explains WHY the helper is
    # not used here, and a text scan would flag the very comment that exists to
    # stop someone putting it back.
    offenders = []
    previous = None
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        if token.type == tokenize.NAME and token.string == "log_role_change" and previous == "audit_log":
            offenders.append(f"{token.start[0]}: {token.line.strip()}")
        if token.type == tokenize.NAME:
            previous = token.string
    assert not offenders, (
        "the chemical-role path must not use the swallowing audit helper:\n" + "\n".join(offenders)
    )


def test_the_role_selector_starts_unresolved(fixture):
    """Closeout item 'the role field starting in the Unresolved state and
    requiring an explicit user selection'.

    Mutation-checked: flipping the default index off zero must fail this.
    """
    page = os.path.join(REPO_ROOT, "views", "3_Recipe_Version_Record.py")
    with open(page, encoding="utf-8") as handle:
        source = handle.read()

    assert 'role_options = ["— Unresolved —"] + list(component_role.CHEMICAL_ROLES)' in source, (
        "the role selector's first option must be Unresolved"
    )
    assert "role_index = role_options.index(current_role) if current_role in role_options else 0" in source, (
        "an unassigned component must default the selector to Unresolved, not to a chemical role"
    )


def test_the_legacy_ratio_is_not_presented_as_the_controlled_one(fixture):
    """Review found the page printing a confident legacy A:B ratio a few inches
    below the caption saying the ratio cannot be derived. Whichever number a
    user reads first wins, and one of them is a guess."""
    page = os.path.join(REPO_ROOT, "views", "3_Recipe_Version_Record.py")
    with open(page, encoding="utf-8") as handle:
        source = handle.read()

    assert "_controlled_roles_complete = component_role.recipe_version_is_resolved(v)" in source
    assert "Computed (uncontrolled, legacy basis)" in source
    assert "No controlled A:B ratio for this version." in source


# ---------------------------------------------------------------------------
# Charlie's Decision 3 Correction Ruling, sections 4 and 5 (20 August 2026)
# ---------------------------------------------------------------------------

def test_a_component_from_another_recipe_version_does_not_resolve(fixture):
    """Ruling section 5. Without the ownership guard the resolver answered
    confidently for a component belonging to an entirely different recipe - a
    real-looking 'A' to a question that was meaningless."""
    session = fixture["session"]
    other_version = db.RecipeVersion(foam_grade_id=fixture["grade"].id, version_label="v2")
    session.add(other_version)
    session.flush()

    foreign = db.RecipeComponent(
        recipe_version_id=other_version.id,
        raw_material_name="Lupranate M20",
        php=145,
        chemical_role=ISO,
        chemical_role_source_id=fixture["source"].id,
        chemical_role_source_location="Table 3, row 2",
    )
    session.add(foreign)
    session.flush()

    _configuration(fixture, fixture["line_1"], {"A": ISO, "B": POLYOL})
    run = _run(fixture, fixture["line_1"])          # run records fixture["version"]

    stream, reason = component_role.resolve_component_stream(session, run, foreign)
    assert stream is None
    assert reason == component_role.UNRESOLVED_RECIPE_MISMATCH
    assert component_role.component_stream_for_run(session, run, foreign) is None


def test_a_matching_component_still_resolves(fixture):
    """The guard must not break the normal case."""
    own = _component(fixture, "Lupranate M20", 145, role=ISO)
    _configuration(fixture, fixture["line_1"], {"A": ISO, "B": POLYOL})
    run = _run(fixture, fixture["line_1"])

    stream, reason = component_role.resolve_component_stream(fixture["session"], run, own)
    assert stream == "A"
    assert reason is None


def test_each_unresolved_cause_reports_its_own_reason(fixture):
    """Three causes needing three different actions from three different
    people. Reporting one undifferentiated failure would tell nobody what to
    do about it."""
    session = fixture["session"]
    unresolved_component = _component(fixture, "Cyclopentane", 12)
    resolved_component = _component(fixture, "Lupranate M20", 145, role=ISO)

    unstamped = _run(fixture, fixture["line_1"], stamp=False)
    assert component_role.resolve_component_stream(session, unstamped, unresolved_component)[1] == (
        component_role.UNRESOLVED_NO_ROLE
    )
    assert component_role.resolve_component_stream(session, unstamped, resolved_component)[1] == (
        component_role.UNRESOLVED_NO_CONFIGURATION
    )


def _fully_resolved_other_version(fixture):
    """A SECOND recipe version that is complete in its own right.

    Deliberately populated and fully resolved. An empty version would be
    refused by recipe_version_is_resolved() anyway, so a test using one would
    pass whether or not the ownership guard existed - which is exactly what the
    first draft of these two tests did.
    """
    session = fixture["session"]
    other = db.RecipeVersion(foam_grade_id=fixture["grade"].id, version_label="v2")
    session.add(other)
    session.flush()
    for name, php, role in (("Other iso", 150, ISO), ("Other polyol", 100, POLYOL)):
        session.add(db.RecipeComponent(
            recipe_version_id=other.id,
            raw_material_name=name,
            php=php,
            chemical_role=role,
            chemical_role_source_id=fixture["source"].id,
            chemical_role_source_location="Table 9, row 1",
        ))
    session.flush()
    session.refresh(other)
    assert component_role.recipe_version_is_resolved(other) is True
    return other


def test_stream_totals_refuse_a_recipe_the_run_did_not_use(fixture):
    """Totalling a formulation that was never on that machine would produce a
    confident number about the wrong thing.

    The other version here is complete and would total perfectly well on its
    own, so the ONLY thing that can refuse it is the ownership guard.
    """
    session = fixture["session"]
    _component(fixture, "Lupranate M20", 145, role=ISO)
    _component(fixture, "Lupranol 3300", 100, role=POLYOL)
    _configuration(fixture, fixture["line_1"], {"A": ISO, "B": POLYOL})
    run = _run(fixture, fixture["line_1"])

    other_version = _fully_resolved_other_version(fixture)
    assert component_role.php_by_chemical_role(other_version) == {ISO: 150.0, POLYOL: 100.0}

    version = fixture["version"]
    session.refresh(version)
    assert component_role.php_by_stream_for_run(session, run, version) == {"A": 145.0, "B": 100.0}
    assert component_role.php_by_stream_for_run(session, run, other_version) is None


def test_the_resolution_summary_flags_a_recipe_mismatch(fixture):
    """Again with a version that is complete on its own, so 'resolved' can only
    be False because of the ownership guard."""
    _component(fixture, "Lupranate M20", 145, role=ISO)
    _configuration(fixture, fixture["line_1"], {"A": ISO, "B": POLYOL})
    run = _run(fixture, fixture["line_1"])

    other_version = _fully_resolved_other_version(fixture)

    summary = component_role.run_component_resolution(fixture["session"], run, other_version)
    assert summary["recipe_version_matches_run"] is False
    assert summary["machine_stream_resolved"] is True
    assert summary["unresolved_components"] == []
    assert summary["resolved"] is False


def test_the_revision_path_warns_confirms_and_audits_the_role_reset(fixture):
    """Ruling section 4, asserted against the PAGE.

    Three separate obligations, and a test for each, because the previous round
    of this work showed that asserting them in prose is worth nothing:
    the warning must name how many assignments reset, the save must be blocked
    until the user confirms, and the reset must reach the audit trail.
    """
    page = os.path.join(REPO_ROOT, "views", "3_Recipe_Version_Record.py")
    with open(page, encoding="utf-8") as handle:
        source = handle.read()

    # names the count
    assert "_roles_to_reset = [" in source
    assert "controlled chemical role assignment(s) will reset" in source
    assert "len(_roles_to_reset)" in source

    # requires explicit confirmation, and blocks the save without it
    assert "_reset_confirmed = st.checkbox(" in source
    assert "elif not _reset_confirmed:" in source

    # records it as part of version creation, on the controlled-edit path
    assert "reset to Unresolved on the new version" in source
    assert source.count("RoleChangeLog(") >= 2, (
        "the version-creation reset must be recorded as well as the assignment"
    )
    # and says the old version keeps its record
    assert "retains" in source and "its assignments and sources" in source


def test_new_version_components_are_created_without_role_fields(fixture):
    """The reset itself: the revision path must not copy provenance forward.

    Carrying a role over would assert that evidence gathered for one
    formulation applies to a revised one, which nobody has established.
    """
    import io
    import tokenize

    page = os.path.join(REPO_ROOT, "views", "3_Recipe_Version_Record.py")
    with open(page, encoding="utf-8") as handle:
        source = handle.read()

    block = source.split("new_version = RecipeVersion(")[1].split("activate_recipe_version(")[0]
    for field in ("chemical_role", "chemical_role_source_id", "chemical_role_source_location"):
        assert field not in block, (
            f"the revision path copies {field} forward - provenance must not be inherited"
        )
