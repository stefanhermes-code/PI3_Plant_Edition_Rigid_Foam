"""Phase 8 Decision 3: controlled chemical role on recipe components (2026-08-19).

Per Charlie's Decision 3 Design Ruling and Implementation Instructions.

WHY THIS IS A SEPARATE MODULE FROM machine_stream.py

Charlie's ruling section 6: keep the Decision 2 module focused on physical
machine configuration, and put the component resolver here, calling Decision 2's
stream_for_role() across the boundary.

That is not filing tidiness. The two modules answer questions that must never
merge:

    machine_stream.py   WHICH PHYSICAL STREAM carries a given chemical role on
                        one machine, at one point in time. A fact about
                        plumbing. Versioned per machine, stamped onto a run.

    component_role.py   WHAT A MATERIAL IS in one formulation - Isocyanate
                        Component or Polyol Blend Component. A fact about
                        chemistry. Recorded per recipe component, with the
                        document that establishes it.

Keeping them in one file would make it easy, one day, for something to reach
across and infer one from the other - which is the exact defect the whole
Decision 2/3 sequence exists to prevent. The import goes one way only: this
module imports machine_stream, never the reverse.

THE ONE PLACE THEY MEET

component_stream_for_run(). It needs BOTH halves and defaults NEITHER:

    role   comes from the recipe component  (Decision 3)
    stream comes from the run's STAMPED configuration  (Decision 2)

If either is missing the answer is None. Not "A", not a guess, not the
convention that happens to be most common. A missing half is reported as a
missing half, and the two are reported separately so a user can tell which one
to go and fix.

WHAT IS NOT HERE

No arithmetic. The A:B mass ratio, its target, and the signed deviation are
Decision 4, and Decision 4 consumes this resolver rather than reimplementing
it. What this module provides is the mapping and the honest None.

recipe_components.stream_assignment is not read anywhere in this module, or
anywhere on the ratio path. It stays outside the controlled path by ruling, it
holds no live data, and tests assert its absence from these code paths.
"""
import machine_stream

# Deliberately re-exported from machine_stream rather than restated. One
# controlled vocabulary, one definition. If it is ever extended, both the
# machine side and the formulation side move in the same change - two
# independent copies of a controlled vocabulary is how it stops being
# controlled.
ISOCYANATE_COMPONENT = machine_stream.ISOCYANATE_COMPONENT
POLYOL_BLEND_COMPONENT = machine_stream.POLYOL_BLEND_COMPONENT
CHEMICAL_ROLES = machine_stream.CHEMICAL_ROLES


class RoleAssignmentRefused(Exception):
    """Raised when an assignment does not carry the provenance the controlled
    model requires. Carries the problems so the editor can show all of them
    at once rather than one per attempt."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


# ---------------------------------------------------------------------------
# Reading a component
# ---------------------------------------------------------------------------

def is_resolved(component):
    """A component whose chemical role is established and traceable.

    Checks the provenance too, not just the role. The database constraint
    makes the two inseparable, so in practice a role implies its source - but
    this function is what the ratio path asks, and it should not depend on a
    constraint being present to give the right answer on, say, an in-memory
    object that has not been flushed yet.
    """
    if component is None or component.chemical_role is None:
        return False
    if component.chemical_role not in CHEMICAL_ROLES:
        return False
    if component.chemical_role_source_id is None:
        return False
    return bool((component.chemical_role_source_location or "").strip())


def role_of(component):
    """The controlled chemical role, or None. Never inferred."""
    return component.chemical_role if is_resolved(component) else None


def unresolved_components(recipe_version):
    """Every component on this recipe version that has no controlled role.

    Returned rather than counted, because the point of surfacing a gap is to
    say which rows to go and look at.
    """
    if recipe_version is None:
        return []
    return [c for c in recipe_version.components if not is_resolved(c)]


def recipe_version_is_resolved(recipe_version):
    """A recipe version whose every component carries a controlled role.

    An empty component list is NOT resolved: a formulation with no components
    cannot support a ratio, and answering True here would let an empty recipe
    look complete.
    """
    if recipe_version is None or not recipe_version.components:
        return False
    return not unresolved_components(recipe_version)


# ---------------------------------------------------------------------------
# Assigning - the controlled action
# ---------------------------------------------------------------------------

def validate_assignment(chemical_role, source_id, source_location):
    """Everything the ruling requires before a role becomes controlled data.

    Returns a list of human-readable problems; empty means the assignment is
    allowed. The database enforces the same rules; this exists so the editor
    can say what is missing in the user's language, before a save is attempted,
    and can say all of it at once.
    """
    problems = []
    if chemical_role not in CHEMICAL_ROLES:
        problems.append(
            "Chemical role must be one of: " + ", ".join(CHEMICAL_ROLES) + "."
        )
    if source_id is None:
        problems.append(
            "A source is required: the controlled document that establishes this role."
        )
    if not (source_location or "").strip():
        problems.append(
            "Source location is required: where inside that document the role is "
            "established, for example 'Table 3, row 2'."
        )
    return problems


def describe_assignment(component, chemical_role, source_location):
    """The audit summary for an assignment or a correction.

    Says what it was as well as what it became. A change log that records only
    the new value cannot answer the question anyone actually asks later, which
    is what it used to say.
    """
    previous = component.chemical_role or "Unresolved"
    if previous == chemical_role:
        return (
            f"Chemical role source updated for '{component.raw_material_name}': "
            f"{chemical_role} (source location: {source_location})"
        )
    return (
        f"Chemical role for '{component.raw_material_name}': "
        f"{previous} -> {chemical_role} (source location: {source_location})"
    )


def assign_role(component, chemical_role, source_id, source_location):
    """Set a controlled chemical role together with its provenance.

    All three or nothing - the same rule the database enforces, applied here so
    an incomplete assignment is refused with a readable message rather than an
    IntegrityError.
    """
    problems = validate_assignment(chemical_role, source_id, source_location)
    if problems:
        raise RoleAssignmentRefused(problems)
    component.chemical_role = chemical_role
    component.chemical_role_source_id = source_id
    component.chemical_role_source_location = source_location.strip()
    return component


def clear_role(component):
    """Return a component to Unresolved.

    Clears all three fields together. Leaving the source fields behind would
    create exactly the stranded-provenance state the constraint exists to make
    impossible, and it is easier to get that wrong here than anywhere else.
    """
    component.chemical_role = None
    component.chemical_role_source_id = None
    component.chemical_role_source_location = None
    return component


# ---------------------------------------------------------------------------
# The one place chemistry meets plumbing
# ---------------------------------------------------------------------------

def component_stream_for_run(session, run, component):
    """Which physical stream carried this component on this run. 'A', 'B' or None.

    Both halves are required and neither is defaulted:

      - the component must carry a controlled chemical role (Decision 3);
      - the run must carry a stamped machine-stream configuration whose
        assignments resolve (Decision 2).

    Returns None if either is missing. There is deliberately no fallback: the
    most common convention is still a guess, and a guessed stream produces a
    ratio that is precisely wrong and indistinguishable from a measured one.

    Performs no writes. Reading a run must never stamp it - see
    machine_stream.configuration_for_run().
    """
    role = role_of(component)
    if role is None:
        return None
    configuration = machine_stream.configuration_for_run(session, run)
    if not machine_stream.is_resolved(configuration):
        return None
    return machine_stream.stream_for_role(configuration, role)


def run_component_resolution(session, run, recipe_version):
    """What the application shows, and what Decision 4 will consume.

    Always answers, and when it cannot resolve it says WHICH half is missing
    rather than reporting a single undifferentiated failure. Those are two
    different jobs for the user: one is a formulation record to complete, the
    other is a machine configuration to activate.
    """
    configuration = machine_stream.configuration_for_run(session, run)
    stream_resolved = machine_stream.is_resolved(configuration)
    unresolved = unresolved_components(recipe_version)

    components = []
    for component in (recipe_version.components if recipe_version else []):
        components.append(
            {
                "component": component,
                "chemical_role": role_of(component),
                "stream": component_stream_for_run(session, run, component),
            }
        )

    return {
        "resolved": stream_resolved and bool(components) and not unresolved,
        "configuration": configuration,
        "machine_stream_resolved": stream_resolved,
        "unresolved_components": unresolved,
        "components": components,
    }


def php_by_chemical_role(recipe_version):
    """Sum php per chemical role, in ROLE space.

    This is the shape Decision 4 needs, and the reason it is expressed in role
    space rather than stream space: the totals for a formulation are a property
    of the formulation and do not change with the machine. Relabelling them as
    the A number and the B number happens later, through the run's stamped
    configuration, and is the ONLY step that varies by machine.

    Returns None when any component is unresolved. A partial sum would be a
    smaller number that looks like a real one.
    """
    if not recipe_version_is_resolved(recipe_version):
        return None
    totals = {role: 0.0 for role in CHEMICAL_ROLES}
    for component in recipe_version.components:
        totals[component.chemical_role] += component.php or 0.0
    return totals


def php_by_stream_for_run(session, run, recipe_version):
    """The same totals, relabelled into stream space for one run.

    Requires both halves. Returns None if either is missing, so a caller cannot
    accidentally receive a half-answer shaped like a whole one.
    """
    totals = php_by_chemical_role(recipe_version)
    if totals is None:
        return None
    configuration = machine_stream.configuration_for_run(session, run)
    if not machine_stream.is_resolved(configuration):
        return None
    by_stream = {}
    for role, total in totals.items():
        by_stream[machine_stream.stream_for_role(configuration, role)] = total
    return by_stream
