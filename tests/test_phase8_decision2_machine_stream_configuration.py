"""Phase 8 Decision 2 - controlled machine-stream configuration (2026-08-19).

Direct evidence for the eleven code-testable items in section 6 of
"Phase8_PM800_Decision2_Schema_Ruling_and_Implementation_Instructions_to_
JC_v1.docx" (19 Aug 2026). The remaining two items in that section -
browser evidence and full regression - are recorded in the closeout, not
here.

Section 6 item -> test:

  1  same recipe on two machines, opposite conventions
     -> test_opposite_conventions_on_two_machines_both_resolve_correctly
  2  no code path globally equates A with isocyanate
     -> test_no_module_hard_codes_a_side_as_isocyanate
        test_the_same_stream_label_means_different_things_per_machine
  3  overlapping controlled periods rejected
     -> test_overlapping_controlled_periods_are_rejected
        test_adjacent_half_open_periods_are_not_an_overlap
  4  draft overlap allowed, activation still rejects the conflict
     -> test_drafts_may_overlap_while_being_prepared
        test_activation_rejects_a_draft_that_conflicts_with_a_controlled_period
  5  active header and assignment rows immutable
     -> test_an_active_configuration_is_frozen
        test_a_superseded_configuration_is_frozen
  6  superseding leaves an already stamped run unchanged
     -> test_superseding_leaves_a_stamped_run_reading_exactly_what_it_read
  7  a new run stamps the Active configuration at run start
     -> test_a_new_run_stamps_the_configuration_in_force_at_its_start
  8  a run with no Active configuration stays unresolved, no derived ratio
     -> test_a_run_with_no_active_configuration_is_unresolved
        test_an_unresolved_run_yields_no_stream_for_either_chemical_role
  9  pre-migration null runs stay null after normal reads
     -> test_reading_a_historical_null_run_does_not_stamp_it
        test_stamp_run_refuses_to_restamp_an_already_stamped_run
  10 activation completeness
     -> test_activation_requires_every_controlled_field
        test_activation_requires_both_streams_and_both_roles
  11 migration clean and idempotent
     -> test_schema_creation_is_idempotent
        test_both_models_are_registered_for_migration

Usage: python -m pytest tests/test_phase8_decision2_machine_stream_configuration.py -v

WHY THE MACHINE AND NOT THE PLANT

Two machines on one site can be plumbed in opposite directions, and a
machine can be re-hosed. So the mapping is per machine and per validity
period, and a Production Run is stamped once with the revision in force
when it was created. Test 6 is the one that proves the point: after the
plant swaps its convention and supersedes the old revision, the run that
already ran still reads the old convention, because reinterpreting it
would silently rewrite a physical fact about a block that has already
been foamed.
"""
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
import sqlalchemy as sa

import db
import machine_stream as ms

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ISO = ms.ISOCYANATE_COMPONENT
POLYOL = ms.POLYOL_BLEND_COMPONENT

JAN = dt.datetime(2026, 1, 1, 0, 0)
MAR = dt.datetime(2026, 3, 1, 0, 0)
JUN = dt.datetime(2026, 6, 1, 0, 0)
SEP = dt.datetime(2026, 9, 1, 0, 0)


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def session():
    db.init_db()
    _reset_schema()
    s = db.get_session()
    yield s
    s.close()


@pytest.fixture()
def plant_fixture(session):
    """Two machines in one plant, one recipe version they both run.

    Deliberately one plant: the ruling put the convention on the machine
    precisely because a plant-level answer would be wrong here.
    """
    plant = db.Plant(name="Rigid Plant 1")
    session.add(plant)
    session.flush()

    family = db.ProductFamily(plant_id=plant.id, name="Appliance Cavity")
    session.add(family)
    session.flush()

    grade = db.FoamGrade(product_family_id=family.id, grade_name="RG-100")
    session.add(grade)
    session.flush()

    version = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1")
    session.add(version)

    line_1 = db.Machine(plant_id=plant.id, name="Line 1")
    line_2 = db.Machine(plant_id=plant.id, name="Line 2")
    session.add_all([line_1, line_2])
    session.flush()

    return {
        "plant": plant,
        "grade": grade,
        "version": version,
        "line_1": line_1,
        "line_2": line_2,
    }


def _configuration(session, machine, effective_from, effective_to=None, roles=None,
                   status=ms.STATUS_DRAFT, complete_approval=True):
    """A configuration in whatever state the test needs.

    roles is {stream_label: chemical_role}; omit a label to leave that
    stream unmapped, which a Draft is allowed to be.
    """
    configuration = db.MachineStreamConfiguration(
        controlled_id=ms.next_controlled_id(session),
        machine_id=machine.id,
        revision=ms.next_revision(session, machine.id),
        effective_from=effective_from,
        effective_to=effective_to,
        status=status,
        source_reference="Commissioning report CR-2026-01" if complete_approval else None,
        approved_by="Plant Engineering" if complete_approval else None,
        approved_at=effective_from if complete_approval else None,
    )
    session.add(configuration)
    session.flush()
    for stream_label, chemical_role in (roles or {}).items():
        session.add(
            db.MachineStreamAssignment(
                machine_stream_configuration_id=configuration.id,
                stream_label=stream_label,
                chemical_role=chemical_role,
            )
        )
    session.flush()
    session.refresh(configuration)
    return configuration


def _run(session, fixture, machine, run_start):
    run = db.ProductionRun(
        plant_id=fixture["plant"].id,
        foam_grade_id=fixture["grade"].id,
        recipe_version_id=fixture["version"].id,
        run_date=run_start.date(),
        run_start=run_start,
        machine_id=machine.id,
    )
    session.add(run)
    session.flush()
    return run


# ---------------------------------------------------------------------------
# Item 1 and 2: the mapping is data, per machine
# ---------------------------------------------------------------------------

def test_opposite_conventions_on_two_machines_both_resolve_correctly(session, plant_fixture):
    """One recipe, two machines, opposite plumbing - both read correctly.

    This is the case a single global rule gets wrong: whichever way the
    rule is written, one of these two lines produces an inverted A:B ratio
    and nothing in the data would show it.
    """
    line_1 = _configuration(session, plant_fixture["line_1"], JAN,
                            roles={"A": ISO, "B": POLYOL})
    line_2 = _configuration(session, plant_fixture["line_2"], JAN,
                            roles={"A": POLYOL, "B": ISO})
    ms.activate(session, line_1)
    ms.activate(session, line_2)

    run_1 = _run(session, plant_fixture, plant_fixture["line_1"], MAR)
    run_2 = _run(session, plant_fixture, plant_fixture["line_2"], MAR)
    ms.stamp_run(session, run_1)
    ms.stamp_run(session, run_2)

    summary_1 = ms.run_stream_summary(session, run_1)
    summary_2 = ms.run_stream_summary(session, run_2)

    assert summary_1["resolved"] and summary_2["resolved"]
    assert summary_1["isocyanate_stream"] == "A"
    assert summary_1["polyol_stream"] == "B"
    assert summary_2["isocyanate_stream"] == "B"
    assert summary_2["polyol_stream"] == "A"


def test_the_same_stream_label_means_different_things_per_machine(session, plant_fixture):
    """Stream 'A' carries opposite chemistry on the two machines, at the
    same instant. Any code that answered this from a constant would have
    to return the same value twice."""
    line_1 = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO, "B": POLYOL})
    line_2 = _configuration(session, plant_fixture["line_2"], JAN, roles={"A": POLYOL, "B": ISO})
    ms.activate(session, line_1)
    ms.activate(session, line_2)

    assert ms.role_for_stream(line_1, "A") == ISO
    assert ms.role_for_stream(line_2, "A") == POLYOL
    assert ms.stream_for_role(line_1, ISO) != ms.stream_for_role(line_2, ISO)


def test_no_module_hard_codes_a_side_as_isocyanate():
    """Section 6 item 2, as a source scan.

    Flags any line outside machine_stream.py and tests/ that mentions a
    chemical role and a bare 'A'/'B' stream literal together - the shape a
    hard-coded equivalence would take. machine_stream.py is exempt because
    it is where the two vocabularies are legitimately named side by side,
    and even there it never maps one to the other.
    """
    chemical_role = re.compile(r"[Ii]socyanate|[Pp]olyol\s+[Bb]lend")
    stream_literal = re.compile(r"""(?<![A-Za-z0-9_])(['"])([AB])\1""")
    offenders = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", "tests", "_to_delete", ".venv"}]
        for name in files:
            if not name.endswith(".py") or name == "machine_stream.py":
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8", errors="replace") as handle:
                for number, line in enumerate(handle, 1):
                    if chemical_role.search(line) and stream_literal.search(line):
                        offenders.append(f"{os.path.relpath(path, REPO_ROOT)}:{number}: {line.strip()}")
    assert offenders == [], "hard-coded stream/role equivalence:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# Item 3 and 4: overlap
# ---------------------------------------------------------------------------

def test_overlapping_controlled_periods_are_rejected(session, plant_fixture):
    first = _configuration(session, plant_fixture["line_1"], JAN, JUN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, first)

    clashing = _configuration(session, plant_fixture["line_1"], MAR, SEP, roles={"A": POLYOL, "B": ISO})
    problems = ms.validate_activation(session, clashing)
    assert any("overlaps" in problem for problem in problems)
    with pytest.raises(ms.ActivationRefused):
        ms.activate(session, clashing)
    assert clashing.status == ms.STATUS_DRAFT


def test_adjacent_half_open_periods_are_not_an_overlap(session, plant_fixture):
    """Ruling R3 made the period half-open [from, to). A revision ending at
    an instant and the next starting at that same instant is a clean
    handover, not a conflict - otherwise every re-plumbing would need a
    gap in which no configuration applies."""
    first = _configuration(session, plant_fixture["line_1"], JAN, JUN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, first)

    following = _configuration(session, plant_fixture["line_1"], JUN, None, roles={"A": POLYOL, "B": ISO})
    assert ms.validate_activation(session, following) == []
    ms.activate(session, following)
    assert following.status == ms.STATUS_ACTIVE


def test_drafts_may_overlap_while_being_prepared(session, plant_fixture):
    """Ruling R6: a Draft is working material. Two people can be preparing
    competing proposals for the same period without either blocking the
    other; only one of them can ever be activated."""
    draft_a = _configuration(session, plant_fixture["line_1"], JAN, JUN, roles={"A": ISO, "B": POLYOL})
    draft_b = _configuration(session, plant_fixture["line_1"], JAN, JUN, roles={"A": POLYOL, "B": ISO})
    assert draft_a.status == ms.STATUS_DRAFT
    assert draft_b.status == ms.STATUS_DRAFT
    assert ms.overlapping_configurations(session, plant_fixture["line_1"].id, JAN, JUN) == []


def test_activation_rejects_a_draft_that_conflicts_with_a_controlled_period(session, plant_fixture):
    """The second half of item 4: overlap tolerance ends at activation."""
    draft_a = _configuration(session, plant_fixture["line_1"], JAN, JUN, roles={"A": ISO, "B": POLYOL})
    draft_b = _configuration(session, plant_fixture["line_1"], JAN, JUN, roles={"A": POLYOL, "B": ISO})
    ms.activate(session, draft_a)
    with pytest.raises(ms.ActivationRefused):
        ms.activate(session, draft_b)


def test_a_superseded_period_still_blocks_a_new_overlapping_activation(session, plant_fixture):
    """Superseded revisions stay in the controlled set. History has to be
    unambiguous too - two configurations claiming the same past week would
    make the runs stamped in it uninterpretable."""
    first = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, first)
    ms.supersede(session, first, JUN)
    assert first.status == ms.STATUS_SUPERSEDED

    overlapping = _configuration(session, plant_fixture["line_1"], MAR, SEP, roles={"A": POLYOL, "B": ISO})
    problems = ms.validate_activation(session, overlapping)
    assert any("overlaps" in problem for problem in problems)


# ---------------------------------------------------------------------------
# Item 5: immutability
# ---------------------------------------------------------------------------

def test_an_active_configuration_is_frozen(session, plant_fixture):
    configuration = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, configuration)
    with pytest.raises(ms.ConfigurationFrozen):
        ms.assert_editable(configuration)


def test_a_superseded_configuration_is_frozen(session, plant_fixture):
    configuration = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, configuration)
    ms.supersede(session, configuration, JUN)
    with pytest.raises(ms.ConfigurationFrozen):
        ms.assert_editable(configuration)
    with pytest.raises(ms.ConfigurationFrozen):
        ms.supersede(session, configuration, SEP)


def test_a_draft_is_editable(session, plant_fixture):
    configuration = _configuration(session, plant_fixture["line_1"], JAN)
    ms.assert_editable(configuration)  # must not raise


def test_one_configuration_cannot_map_two_streams_to_the_same_role(session, plant_fixture):
    """Database control, ruling section 4: UNIQUE(configuration, chemical_role).
    Without it a configuration could claim both streams carry isocyanate,
    which is not a plumbing arrangement that exists."""
    configuration = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO})
    session.add(
        db.MachineStreamAssignment(
            machine_stream_configuration_id=configuration.id,
            stream_label="B",
            chemical_role=ISO,
        )
    )
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()


def test_one_configuration_cannot_map_the_same_stream_twice(session, plant_fixture):
    configuration = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO})
    session.add(
        db.MachineStreamAssignment(
            machine_stream_configuration_id=configuration.id,
            stream_label="A",
            chemical_role=POLYOL,
        )
    )
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()


def test_one_machine_cannot_have_two_configurations_at_the_same_revision(session, plant_fixture):
    _configuration(session, plant_fixture["line_1"], JAN)
    duplicate = db.MachineStreamConfiguration(
        controlled_id="MSC-999",
        machine_id=plant_fixture["line_1"].id,
        revision=1,
        effective_from=JAN,
        status=ms.STATUS_DRAFT,
    )
    session.add(duplicate)
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()


# ---------------------------------------------------------------------------
# Item 6 and 7: stamping
# ---------------------------------------------------------------------------

def test_a_new_run_stamps_the_configuration_in_force_at_its_start(session, plant_fixture):
    configuration = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, configuration)

    run = _run(session, plant_fixture, plant_fixture["line_1"], MAR)
    stamped = ms.stamp_run(session, run)

    assert stamped is configuration
    assert run.machine_stream_configuration_id == configuration.id


def test_a_run_before_the_effective_date_is_not_stamped(session, plant_fixture):
    """Half-open [from, to): a run that started before the configuration
    took effect is outside it, so it stays unresolved rather than
    borrowing a convention that was not yet in force."""
    configuration = _configuration(session, plant_fixture["line_1"], JUN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, configuration)

    run = _run(session, plant_fixture, plant_fixture["line_1"], MAR)
    assert ms.stamp_run(session, run) is None
    assert run.machine_stream_configuration_id is None


def test_superseding_leaves_a_stamped_run_reading_exactly_what_it_read(session, plant_fixture):
    """The whole point of the design, in one test.

    March run on the old convention (A carries isocyanate). In June the
    line is re-hosed, revision 1 is superseded and revision 2 activated
    the other way round. The March block was physically foamed with
    isocyanate on stream A and it must keep saying so.
    """
    revision_1 = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, revision_1)

    run = _run(session, plant_fixture, plant_fixture["line_1"], MAR)
    ms.stamp_run(session, run)
    before = ms.run_stream_summary(session, run)
    assert before["isocyanate_stream"] == "A"

    ms.supersede(session, revision_1, JUN)
    revision_2 = _configuration(session, plant_fixture["line_1"], JUN, roles={"A": POLYOL, "B": ISO})
    ms.activate(session, revision_2)

    after = ms.run_stream_summary(session, run)
    assert run.machine_stream_configuration_id == revision_1.id
    assert after["resolved"] is True
    assert after["isocyanate_stream"] == "A"
    assert after["polyol_stream"] == "B"
    assert after["label"] == before["label"]

    later_run = _run(session, plant_fixture, plant_fixture["line_1"], SEP)
    ms.stamp_run(session, later_run)
    assert ms.run_stream_summary(session, later_run)["isocyanate_stream"] == "B"


def test_stamp_run_refuses_to_restamp_an_already_stamped_run(session, plant_fixture):
    revision_1 = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, revision_1)
    run = _run(session, plant_fixture, plant_fixture["line_1"], MAR)
    ms.stamp_run(session, run)

    ms.supersede(session, revision_1, JUN)
    revision_2 = _configuration(session, plant_fixture["line_1"], JUN, roles={"A": POLYOL, "B": ISO})
    ms.activate(session, revision_2)

    assert ms.stamp_run(session, run, moment=SEP) is revision_1
    assert run.machine_stream_configuration_id == revision_1.id


# ---------------------------------------------------------------------------
# Item 8 and 9: unresolved stays unresolved
# ---------------------------------------------------------------------------

def test_a_run_with_no_active_configuration_is_unresolved(session, plant_fixture):
    run = _run(session, plant_fixture, plant_fixture["line_1"], MAR)
    assert ms.stamp_run(session, run) is None

    summary = ms.run_stream_summary(session, run)
    assert summary["resolved"] is False
    assert summary["label"] == "Unresolved"


def test_an_unresolved_run_yields_no_stream_for_either_chemical_role(session, plant_fixture):
    """Item 8's second half: no derived ratio. There is no stream to put
    either side's mass on, and the module returns None rather than a
    default - a defaulted ratio would be indistinguishable from a measured
    one downstream."""
    run = _run(session, plant_fixture, plant_fixture["line_1"], MAR)
    summary = ms.run_stream_summary(session, run)
    assert summary["isocyanate_stream"] is None
    assert summary["polyol_stream"] is None
    assert summary["configuration"] is None


def test_a_draft_never_resolves_a_run(session, plant_fixture):
    """A Draft is not in force, so even a complete one leaves runs
    unresolved and cannot be stamped."""
    draft = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO, "B": POLYOL})
    run = _run(session, plant_fixture, plant_fixture["line_1"], MAR)
    assert ms.stamp_run(session, run) is None
    assert ms.is_resolved(draft) is False


def test_reading_a_historical_null_run_does_not_stamp_it(session, plant_fixture):
    """Item 9. A pre-migration run has a null reference. Activating a
    configuration today and then displaying that run must not back-fill
    it - the ruling requires an explicit controlled action with evidence,
    not a side effect of somebody opening the page.
    """
    historical = _run(session, plant_fixture, plant_fixture["line_1"], JAN)
    assert historical.machine_stream_configuration_id is None

    configuration = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, configuration)
    session.commit()

    for _ in range(3):
        summary = ms.run_stream_summary(session, historical)
        assert summary["resolved"] is False
        assert summary["label"] == "Unresolved"

    session.expire_all()
    reloaded = session.get(db.ProductionRun, historical.id)
    assert reloaded.machine_stream_configuration_id is None


def test_configuration_for_run_performs_no_write(session, plant_fixture):
    configuration = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, configuration)
    session.commit()

    run = _run(session, plant_fixture, plant_fixture["line_1"], MAR)
    session.commit()

    assert ms.configuration_for_run(session, run) is None
    assert not session.dirty
    assert run.machine_stream_configuration_id is None


# ---------------------------------------------------------------------------
# Item 10: activation completeness
# ---------------------------------------------------------------------------

def test_activation_requires_every_controlled_field(session, plant_fixture):
    configuration = _configuration(session, plant_fixture["line_1"], JAN,
                                   roles={"A": ISO, "B": POLYOL}, complete_approval=False)
    problems = ms.validate_activation(session, configuration)
    joined = " | ".join(problems)
    assert "Source reference" in joined
    assert "Approved by" in joined
    assert "Approved at" in joined
    with pytest.raises(ms.ActivationRefused):
        ms.activate(session, configuration)
    assert configuration.status == ms.STATUS_DRAFT


def test_activation_requires_both_streams_and_both_roles(session, plant_fixture):
    only_one_stream = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO})
    problems = ms.validate_activation(session, only_one_stream)
    assert any("two stream assignments" in problem for problem in problems)
    with pytest.raises(ms.ActivationRefused):
        ms.activate(session, only_one_stream)

    complete = _configuration(session, plant_fixture["line_2"], JAN, roles={"A": ISO, "B": POLYOL})
    assert ms.validate_activation(session, complete) == []
    ms.activate(session, complete)
    assert complete.status == ms.STATUS_ACTIVE


def test_activation_reports_every_problem_at_once(session, plant_fixture):
    """The editor shows the whole list rather than one error per attempt -
    a user filling in a commissioning record should not have to discover
    the requirements one save at a time."""
    configuration = _configuration(session, plant_fixture["line_1"], JAN, complete_approval=False)
    problems = ms.validate_activation(session, configuration)
    assert len(problems) >= 4


def test_only_a_draft_can_be_activated(session, plant_fixture):
    configuration = _configuration(session, plant_fixture["line_1"], JAN, roles={"A": ISO, "B": POLYOL})
    ms.activate(session, configuration)
    problems = ms.validate_activation(session, configuration)
    assert any("Only a Draft can be activated" in problem for problem in problems)


def test_an_end_before_the_start_is_refused(session, plant_fixture):
    """Two layers, both checked: the database CHECK never lets the row
    exist, and the validator gives the same answer in words before a save
    is attempted so the editor can say why."""
    backwards = db.MachineStreamConfiguration(
        controlled_id="MSC-900",
        machine_id=plant_fixture["line_1"].id,
        revision=1,
        effective_from=JUN,
        effective_to=JAN,
        status=ms.STATUS_DRAFT,
    )
    problems = ms.validate_activation(session, backwards)
    assert any("later than effective from" in problem for problem in problems)

    session.add(backwards)
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()
    session.rollback()


# ---------------------------------------------------------------------------
# Item 11: migration
# ---------------------------------------------------------------------------

def test_schema_creation_is_idempotent():
    """create_all is the ORM-side equivalent of re-running the migration:
    it must add nothing and raise nothing the second time."""
    db.Base.metadata.create_all(db.ENGINE)
    inspector = sa.inspect(db.ENGINE)
    before = sorted(inspector.get_table_names())
    db.Base.metadata.create_all(db.ENGINE)
    after = sorted(sa.inspect(db.ENGINE).get_table_names())
    assert before == after
    assert "machine_stream_configurations" in after
    assert "machine_stream_assignments" in after


def test_both_models_are_registered_for_migration():
    """ALL_MODELS drives the schema tooling - a model missing from it
    exists in Python and nowhere else."""
    names = {model.__name__ for model in db.ALL_MODELS}
    assert "MachineStreamConfiguration" in names
    assert "MachineStreamAssignment" in names


def test_production_run_carries_a_nullable_restricted_reference():
    """Nullable, because no backfill was performed and historical runs
    stay unresolved. RESTRICT, because a configuration a run points at
    must not be deletable out from under it."""
    column = db.ProductionRun.__table__.columns["machine_stream_configuration_id"]
    assert column.nullable is True
    foreign_key = list(column.foreign_keys)[0]
    assert foreign_key.ondelete.upper() == "RESTRICT"


def test_assignments_are_removed_with_their_configuration():
    """A configuration's assignments have no independent existence - the
    cascade is what stops a discarded draft leaving orphan rows that a
    later revision could pick up."""
    relationship = db.MachineStreamConfiguration.__mapper__.relationships["assignments"]
    assert "delete-orphan" in relationship.cascade
