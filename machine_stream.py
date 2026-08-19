"""Phase 8 Decision 2: controlled machine-stream configuration (2026-08-19).

Per Charlie's Decision 2 Schema Ruling and Implementation Instructions.

WHAT THIS MODULE EXISTS TO KEEP APART

  CHEMICAL ROLE   what a material IS - Isocyanate Component or Polyol Blend
                  Component. A property of the formulation.
  MACHINE STREAM  which physical stream carries it on one machine - A or B.
                  A property of how that machine is plumbed.

No function here derives one from the other, and nothing anywhere may assume
that stream A carries isocyanate. The A-side label is a plant convention and
it varies. analytics._component_side() records that this database has used it
inconsistently, and its docstring already instructed callers not to guess;
this module is what they use instead.

THE RULES, AND WHERE THEY ARE ENFORCED

Draft configurations may be incomplete and may overlap while being prepared.
Everything is checked at ACTIVATION - see validate_activation(). Once Active,
the header and its assignments are frozen; a later change is a new revision.
That freeze is what makes a Production Run's stamp trustworthy: the revision
it points at cannot be edited underneath it.

Overlapping validity periods for Active/Superseded configurations on one
machine are rejected by the database (GiST exclusion constraint on
tsrange(effective_from, effective_to, '[)'), requiring btree_gist). The
validator here gives the same answer earlier and with a readable message, and
covers the SQLite test path where that constraint does not exist.

Resolution never writes during a read. A run is stamped once, at run start.
A run with no resolvable configuration stays Unresolved and its A:B ratio is
not derived - the gap is surfaced rather than filled with a default.
"""
import datetime as dt

from db import (
    MachineStreamAssignment,
    MachineStreamConfiguration,
    ProductionRun,
)

ISOCYANATE_COMPONENT = "Isocyanate Component"
POLYOL_BLEND_COMPONENT = "Polyol Blend Component"

# The controlled vocabulary already in use by
# reference_formulation_components.component_side, carried across unchanged.
CHEMICAL_ROLES = (ISOCYANATE_COMPONENT, POLYOL_BLEND_COMPONENT)

STREAM_LABELS = ("A", "B")

STATUS_DRAFT = "Draft"
STATUS_ACTIVE = "Active"
STATUS_SUPERSEDED = "Superseded"
STATUSES = (STATUS_DRAFT, STATUS_ACTIVE, STATUS_SUPERSEDED)

# Statuses whose validity periods are controlled and must not overlap.
CONTROLLED_STATUSES = (STATUS_ACTIVE, STATUS_SUPERSEDED)


class ConfigurationFrozen(Exception):
    """Raised on an attempt to edit an Active or Superseded configuration."""


class ActivationRefused(Exception):
    """Raised when validate_activation() found problems and activate() was
    called anyway. Carries the list so a caller can render it."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


# ---------------------------------------------------------------------------
# Reading a configuration
# ---------------------------------------------------------------------------

def role_for_stream(configuration, stream_label):
    """Which chemical role runs on this physical stream. None if unresolved."""
    if configuration is None:
        return None
    for assignment in configuration.assignments:
        if assignment.stream_label == stream_label:
            return assignment.chemical_role
    return None


def stream_for_role(configuration, chemical_role):
    """Which physical stream carries this chemical role. None if unresolved.

    This is the direction the ratio path needs: a recipe component knows its
    role, and the answer to 'is that the A number or the B number' is here and
    only here.
    """
    if configuration is None:
        return None
    for assignment in configuration.assignments:
        if assignment.chemical_role == chemical_role:
            return assignment.stream_label
    return None


def is_resolved(configuration):
    """A configuration usable by the ratio path: Active or Superseded, with
    both streams mapped to the two distinct roles."""
    if configuration is None or configuration.status not in CONTROLLED_STATUSES:
        return False
    labels = {a.stream_label for a in configuration.assignments}
    roles = {a.chemical_role for a in configuration.assignments}
    return labels == set(STREAM_LABELS) and roles == set(CHEMICAL_ROLES)


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------

def _periods_overlap(from_a, to_a, from_b, to_b):
    """Half-open [from, to) comparison. NULL 'to' means open-ended."""
    if to_a is not None and to_a <= from_b:
        return False
    if to_b is not None and to_b <= from_a:
        return False
    return True


def overlapping_configurations(session, machine_id, effective_from, effective_to, exclude_id=None):
    """Controlled configurations on this machine whose period overlaps the
    given one. Drafts are excluded - they may overlap while being prepared."""
    query = session.query(MachineStreamConfiguration).filter(
        MachineStreamConfiguration.machine_id == machine_id,
        MachineStreamConfiguration.status.in_(CONTROLLED_STATUSES),
    )
    if exclude_id is not None:
        query = query.filter(MachineStreamConfiguration.id != exclude_id)
    return [
        other
        for other in query.all()
        if _periods_overlap(effective_from, effective_to, other.effective_from, other.effective_to)
    ]


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

def validate_activation(session, configuration):
    """Everything ruling R6 requires before a configuration becomes Active.

    Returns a list of human-readable problems; empty means activation is
    allowed. Returning problems rather than raising lets the editor show all
    of them at once instead of one per attempt.
    """
    problems = []

    if configuration.status != STATUS_DRAFT:
        problems.append(
            f"Only a Draft can be activated. This configuration is {configuration.status}."
        )

    if not (configuration.source_reference or "").strip():
        problems.append(
            "Source reference is required: the commissioning report, calibration record "
            "or approval that establishes this mapping."
        )
    if not (configuration.approved_by or "").strip():
        problems.append("Approved by is required.")
    if configuration.approved_at is None:
        problems.append("Approved at is required.")

    if configuration.effective_from is None:
        problems.append("Effective from is required.")
    elif configuration.effective_to is not None and configuration.effective_to <= configuration.effective_from:
        problems.append("Effective to must be later than effective from.")

    assignments = list(configuration.assignments)
    if len(assignments) != 2:
        problems.append(
            f"Exactly two stream assignments are required, one A and one B. Found {len(assignments)}."
        )
    else:
        labels = sorted(a.stream_label for a in assignments)
        roles = sorted(a.chemical_role for a in assignments)
        if labels != ["A", "B"]:
            problems.append(f"Streams must be one A and one B. Found {labels}.")
        if roles != sorted(CHEMICAL_ROLES):
            problems.append(
                "Roles must be one Isocyanate Component and one Polyol Blend Component. "
                f"Found {roles}."
            )

    if configuration.effective_from is not None:
        clashes = overlapping_configurations(
            session,
            configuration.machine_id,
            configuration.effective_from,
            configuration.effective_to,
            exclude_id=configuration.id,
        )
        for clash in clashes:
            problems.append(
                f"Validity period overlaps {clash.controlled_id or 'revision %s' % clash.revision} "
                f"({clash.status}), which runs from {clash.effective_from} to "
                f"{clash.effective_to or 'open-ended'}."
            )

    return problems


def activate(session, configuration):
    """Move a Draft to Active after validation. Raises ActivationRefused with
    the full problem list rather than activating a partial configuration."""
    problems = validate_activation(session, configuration)
    if problems:
        raise ActivationRefused(problems)
    configuration.status = STATUS_ACTIVE
    session.flush()
    return configuration


def supersede(session, configuration, effective_to, superseded_by=None):
    """Close an Active configuration. The row keeps its values; only status
    and effective_to change, so a run already stamped against it still reads
    exactly what applied at the time."""
    if configuration.status != STATUS_ACTIVE:
        raise ConfigurationFrozen(
            f"Only an Active configuration can be superseded. This one is {configuration.status}."
        )
    if effective_to is None or effective_to <= configuration.effective_from:
        raise ValueError("Supersede requires an effective_to later than effective_from.")
    configuration.effective_to = effective_to
    configuration.status = STATUS_SUPERSEDED
    session.flush()
    return configuration


def assert_editable(configuration):
    """Guard for the editor. Active and Superseded rows are frozen - a change
    is a new revision, which is what keeps historical runs interpretable."""
    if configuration.status in CONTROLLED_STATUSES:
        raise ConfigurationFrozen(
            f"A {configuration.status} configuration cannot be edited. "
            "Create a new revision instead."
        )


def next_controlled_id(session):
    """Next MSC-nnn. Controlled ids are plant-wide, not per machine, so a
    configuration can be cited in a document without also naming the machine."""
    existing = session.query(MachineStreamConfiguration.controlled_id).all()
    highest = 0
    for (value,) in existing:
        if value and value.startswith("MSC-"):
            tail = value[4:]
            if tail.isdigit():
                highest = max(highest, int(tail))
    return "MSC-%03d" % (highest + 1)


def next_revision(session, machine_id):
    highest = (
        session.query(MachineStreamConfiguration.revision)
        .filter(MachineStreamConfiguration.machine_id == machine_id)
        .order_by(MachineStreamConfiguration.revision.desc())
        .first()
    )
    return (highest[0] + 1) if highest else 1


# ---------------------------------------------------------------------------
# Resolution for a Production Run
# ---------------------------------------------------------------------------

def active_configuration_at(session, machine_id, moment):
    """The Active configuration in force on this machine at this instant, or
    None. Half-open [effective_from, effective_to)."""
    if machine_id is None or moment is None:
        return None
    candidates = (
        session.query(MachineStreamConfiguration)
        .filter(
            MachineStreamConfiguration.machine_id == machine_id,
            MachineStreamConfiguration.status == STATUS_ACTIVE,
            MachineStreamConfiguration.effective_from <= moment,
        )
        .all()
    )
    for candidate in candidates:
        if candidate.effective_to is None or candidate.effective_to > moment:
            return candidate
    return None


def configuration_for_run(session, run):
    """The configuration that applies to this run.

    A stamped run is authoritative and is never recomputed - that is what
    stops a later plant change from reinterpreting history. An unstamped run
    resolves to None here; stamping happens once, explicitly, at run start via
    stamp_run(). This function performs no writes, so displaying a run cannot
    silently modify it.
    """
    if run is None:
        return None
    if run.machine_stream_configuration_id is not None:
        return session.get(MachineStreamConfiguration, run.machine_stream_configuration_id)
    return None


def stamp_run(session, run, moment=None):
    """Record the configuration in force at run start. Called once, when a run
    is created or started.

    Returns the configuration stamped, or None when nothing was in force - in
    which case the run stays Unresolved rather than being given a default.
    Re-stamping an already stamped run is refused, so historical runs cannot be
    back-filled by a later call.
    """
    if run.machine_stream_configuration_id is not None:
        return session.get(MachineStreamConfiguration, run.machine_stream_configuration_id)

    moment = moment or run.run_start or (
        dt.datetime.combine(run.run_date, dt.time.min) if run.run_date else None
    )
    configuration = active_configuration_at(session, run.machine_id, moment)
    if configuration is None:
        return None
    run.machine_stream_configuration_id = configuration.id
    session.flush()
    return configuration


def run_stream_summary(session, run):
    """What the Production Run page shows. Always answers, never guesses."""
    configuration = configuration_for_run(session, run)
    if not is_resolved(configuration):
        return {
            "resolved": False,
            "label": "Unresolved",
            "configuration": configuration,
            "isocyanate_stream": None,
            "polyol_stream": None,
        }
    return {
        "resolved": True,
        "label": configuration.controlled_id or f"Revision {configuration.revision}",
        "configuration": configuration,
        "isocyanate_stream": stream_for_role(configuration, ISOCYANATE_COMPONENT),
        "polyol_stream": stream_for_role(configuration, POLYOL_BLEND_COMPONENT),
    }
