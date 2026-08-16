"""Controlled vocabulary for the Quality Issue page's "Issue type" field.

Added 2026-08-01, replacing a bare free-text field (previously any string
was accepted, e.g. "hardness drift", "shrinkage", "collapse", "splitting" -
whatever the person typing happened to call it that day, with no way to
later group/count/trend issues reliably since two people describing the
same fault would use different words).

QUALITY_ISSUE_TAXONOMY below was originally sourced in full from Laader
Berg's "Troubleshooting Guide For Slabstock Foaming" (Revision 2010,
Release 2014-01-01) - the FAULT column of that guide's fault/recommendation
tables became the `name` here, and the RECOMMENDATION column (condensed to
plain language) became `typical_causes`, shown to the person logging the
issue as reference/guidance once they pick a type, not as instructions to
follow blindly - it's the same "reference for human judgement, not a
directive" posture the rest of this app uses for PI3 output.

WP7 Phase 5, A5-08 filtering (2026-08-15): the source guide is a Flexible
Foam continuous-slabstock document, and per Charlie's Phase 5 closeout
review this module - being a live, customer-facing/UI-reachable path - is
in scope for "zero active Flexible Foam/slabstock inheritance" the same
way the retired ProductionPhase fields and fall-plate/top-flat schema were.
Two categories of change were applied to the set below:

1. Entries removed entirely, because the fault itself only exists on a
   continuous slabstock/Maxfoam line and has no discontinuous
   rigid-molding analog: "Creeping cream line" and "Undercutting /
   under-running" (both describe a moving cream line relative to a
   conveyor pour point), "Mechanical splits" (continuously-running side
   paper liner friction), "Chimney splits (top skin)", "Footprints /
   build-up splits", "Trough build-up splits", "Clogged-flexible splits"
   (all defined by trough dwell time/geometry), and "Domed profile
   (Maxfoam)", "Concave profile (Maxfoam)", "Excess-flow grooves",
   "Horizontal holes", "Shoulder holes (Maxfoam)" (all defined by
   fall-plate/Maxfoam block-forming geometry). Removing an entry here does
   not touch history - see the "Historical rows" note below.
2. `typical_causes` text edited on entries whose underlying fault is
   still Rigid-relevant (a chemistry/cell-structure defect that can occur
   in any foam process) but whose guidance text named a
   trough/conveyor/lay-down-specific check alongside otherwise-generic
   guidance: the retired-concept clause was removed and the rest of the
   guidance kept as-is. Per Charlie's instruction, no replacement
   guidance was invented for the removed clauses - where stripping left
   nothing generic behind, `typical_causes` is left as an empty string
   (the picker's "Typical causes/checks" caption simply does not render
   for that entry, rather than showing invented Rigid-specific content).

WP7 Phase 5, A5-08 correction v2 (2026-08-15, Charlie's second closeout
review return): the first A5-08 pass above scanned for
trough/fall-plate/conveyor/lay-down/slabstock/Maxfoam terms only, which
missed guidance content tied to OTHER already-retired-or-quarantined WP7
concepts still present in a handful of entries: "leaving the tunnel" in
Slow curing (a continuous-line curing-tunnel reference), "air injection"
in Relaxation/Sink back/Coarse foam/Voids-pinholes/Excess air
bubbles/Shrinkage (air_injection_rate/air_pressure_bar is D5-05
QUARANTINED per the Phase 5 decision ledger, not just an inherited
Flexible Foam term), and "methylene chloride" as a named blowing-agent
example in Low block density. All of these clauses were removed the same
way as pass one - clause-level strip, no invented replacement guidance,
empty typical_causes only where nothing generic was left (not needed
here; every affected entry retained other valid guidance). No entries
were removed in this pass, only clauses edited - the 42-entry count from
pass one is unchanged.

Consolidation note: the source guide lists several splits/cracks faults
that differ mainly by WHERE on the block they appear (bottom corner,
shoulder, centre, small side, inclined, chimney over the trough inlets,
...) rather than by distinct underlying mechanism. Encoding each of those
as its own taxonomy entry would just duplicate the "Location in block"
field this page already has. Split-type entries below are consolidated by
mechanism/appearance instead; the reviewer captures the specific position
in "Location in block" and "Notes" as before.

Structure: an ordered dict of category -> list of issue-type dicts, each
with `name` (the controlled value actually stored in
QualityObservation.observation_type - unchanged column, still a plain
string, just no longer free-typed) and `typical_causes` (guidance text,
may be "" - see A5-08 note above). The last category, "Routine / No
Issue", also carries the escape hatch for a genuine one-off that doesn't
match anything here yet ("Other").

No schema/migration needed: QualityObservation.observation_type stays a
String(200) column exactly as before - this module only changes what the
UI lets a person choose to put into it. Historical rows already in the
database (demo data, UAT data, or anything imported before this taxonomy
existed, or anything recorded under a name later removed here in the
A5-08 filtering pass) that don't match any `name` below still display and
edit fine - see pages/6_Quality_Observation.py's handling of a
legacy/unmatched value.

CR-22 / F22-06, F22-07 (AF22-01, 2026-08-16): two new per-entry attributes,
both optional and defaulted by _normalize_entries() below so most literal
dicts don't need to spell them out:

- `state`: STATE_ACTIVE (default) or STATE_QUARANTINED. A QUARANTINED
  entry is removed from every NEW-selection surface (manual entry, CSV/
  Excel import, Customer Trial and Optimization Trial paths) but remains
  a valid, fully readable/reportable value on any QualityObservation row
  already carrying it - the same "deprecate in place, never touch
  history" posture as D5-05's air_injection_rate/air_pressure_bar
  quarantine. See active_issue_types_for_category()'s `include_names`
  parameter for how an already-quarantined value stays visible/editable
  on its own row without being offered as a fresh pick.
- `production_methods`: None (default) means Global - the entry is
  offered for every Production Method and both trial paths, same as
  every entry today. A list of ProductionMethod.controlled_id strings
  (e.g. ["PM-500"]) would restrict the entry to matching Production Runs
  only; see active_issue_types_for_category()'s
  `production_method_controlled_id` parameter. AF22-01 Section 4 froze
  this mechanism into the module even though the post-freeze active set
  contains zero method-specific entries, so a future validated
  method-specific issue can be activated later without another schema
  redesign.

AF22-01 Section 4 ruling applied below: ten entries inherited from the
Flexible slabstock source guide move to STATE_QUARANTINED (the four
"Splits & cracks" entries, Tacky block surface, Low block density,
Bottom cavitation, Bottom skin densification, Stratification, Heavy
skin) because their current definition/cause text is either slabstock/
block-process-based or pending a validated Rigid Block definition in the
approved Rigid master. Three entries stay STATE_ACTIVE but had their
remaining block/tunnel-specific wording stripped per Charlie's explicit
per-entry direction (Relaxation, Slow curing, Scorching) - no replacement
guidance was invented, same policy as the A5-08 passes above. This
yields a 32-entry active baseline on the v0.64.1 challenge baseline (42
total entries unchanged - quarantine does not remove an entry, only its
new-selection eligibility).
"""

STATE_ACTIVE = "active"
STATE_QUARANTINED = "quarantined"

OTHER_ISSUE_NAME = "Other (not yet in this list)"

QUALITY_ISSUE_TAXONOMY = {
    "Rise & cure behavior": [
        {
            "name": "Boiling",
            "typical_causes": "Large bubbles appear and burst at the surface. Check silicone quality/output "
            "and tin catalyst quality/output; reduce amine catalyst; check for contamination with silicone "
            "or grease lubricants.",
        },
        {
            "name": "Collapse",
            "typical_causes": "Foam rises and then falls. Check silicone and tin catalyst quality/output; "
            "reduce amine catalyst; look for contaminants in the foam system.",
        },
        {
            "name": "Crazy balls",
            "typical_causes": "Small bubbles moving rapidly under the foam surface. Increase mixer speed.",
        },
        {
            "name": "Flashing / sparklers",
            "typical_causes": "Excessive effervescence on the top surface of rising foam. Decrease TDI, "
            "silicone, and amine catalyst; increase tin catalyst; check for metering errors; decrease "
            "component temperatures.",
        },
        {
            "name": "Smoking",
            "typical_causes": "Excessive TDI vapours from the surface of the foam. Check metering of TDI, "
            "polyol, and water; reduce TDI output.",
        },
        {
            "name": "Sticky spots",
            "typical_causes": "Local areas of wet, imperfectly mixed ingredients. Check for lead/lag "
            "conditions; increase mixing efficiency; check component tank level; look for system "
            "contaminants.",
        },
        {
            "name": "Relaxation",
            # CR-22 / F22-07 (AF22-01): "Block rises..." -> "Foam rises..." -
            # the fault description no longer names the PM-500-only "block"
            # concept (F22-04). No other clause changed; nothing generic
            # was invented.
            "typical_causes": "Foam rises to maximum height, then settles back. Increase silicone and tin "
            "catalyst (check output); reduce amine catalyst; reduce stirrer speed.",
        },
        {
            "name": "Sink back",
            "typical_causes": "Excessive sink-back of the foam after cell opening. Check tin catalyst pump "
            "output and activity; if the structure is abnormally fine/open, check stirrer speed; check the "
            "tertiary amine catalyst blend.",
        },
        {
            "name": "Slow curing",
            # CR-22 / F22-07 (AF22-01): dropped "cut" (a block-specific
            # handling operation) and the leading "block" in "block
            # dimensionally unstable" - kept the rest, which is generic
            # curing chemistry/process guidance.
            "typical_causes": "Polymer strength builds too slowly; foam too weak/sticky to handle; "
            "dimensionally unstable. Increase amine and/or tin catalyst; check metering "
            "of water/TDI/polyol/tin; check for catalyst deactivation; raise component temperatures; "
            "improve mixer efficiency.",
        },
        {
            "name": "Scorching",
            # CR-22 / F22-07 (AF22-01): "reduce the block size" clause
            # removed (block-specific guidance) with no replacement
            # invented - the remaining generic guidance stands on its own.
            "typical_causes": "Discoloration and loss of properties in the foam core; high internal "
            "temperature during curing. Check TDI/water/polyol outputs; check for contaminants.",
        },
        {
            "name": "Odour",
            "typical_causes": "Finished foam has an undesirable odour. Try a different amine catalyst; use "
            "less-odorous formulation additives; give the foam more time to degas.",
        },
        {
            # CR-22 / F22-07 (AF22-01): QUARANTINED - the term itself is
            # explicitly block-specific (inherited Flexible guidance).
            "name": "Tacky block surface",
            "state": STATE_QUARANTINED,
            "typical_causes": "Surface of the foam block remains sticky for a prolonged time. Increase "
            "total catalyst levels; check block storage conditions; see also Slow curing.",
        },
    ],
    "Cell structure & surface texture": [
        {
            "name": "Moon craters",
            "typical_causes": "",
        },
        {
            "name": "Coarse foam",
            "typical_causes": "Foam is composed of large cells. Check silicone level/activity; increase "
            "mixing speed.",
        },
        {
            "name": "Dead foam",
            "typical_causes": "Foam has low resiliency and closed cells. Reduce tin catalyst and silicone "
            "level; try running a finer cell size.",
        },
        {
            "name": "Friable / loose foam",
            "typical_causes": "Foam is crumbly and does not build polymer strength. Check metering of "
            "tin/polyol/TDI/water; decrease TDI output; check for reduced tin activity or polyol "
            "reactivity; increase mixing speed/efficiency.",
        },
        {
            "name": "Friable skin",
            "typical_causes": "Skin is soft and flakes off at the touch. Increase, change, or check amine "
            "catalyst activity; increase component temperatures; look for contaminants in the system.",
        },
        {
            "name": "Striations",
            "typical_causes": "A distinct line of unusual cell structure. Increase mixing; check the "
            "injection needle and pigment distribution; check for foam build-up/contamination; clean the "
            "mixing head.",
        },
        {
            "name": "Closed cells / low air penetration",
            "typical_causes": "Closed cells with shrinkage, with either normal or abnormally coarse foam "
            "structure. Reduce tin catalyst; check polyol/TDI temperature; check the amine catalyst blend; "
            "on mixed-isomer TDI feed systems check the blend ratio; adjust stirrer speed or mixer nozzle "
            "diameter as needed.",
        },
        {
            "name": "Voids / pinholes",
            "typical_causes": "Small voids randomly distributed throughout the foam. Increase tin catalyst "
            "and cell size; reduce mixer speed; check silicone activity; check for "
            "contamination and clean pump filters, mixer chamber, manifold, and tube.",
        },
        {
            "name": "Air holes",
            "typical_causes": "Cross-section covered with smaller or larger air holes. Check for excess air "
            "in polyol or TDI; check for air leakage through the mixing head, seals, or flexible hoses; "
            "check for build-up material; check mixing head pressure and blowing agent temperature.",
        },
        {
            "name": "Excess air bubbles",
            "typical_causes": "Too much air in the mix. Increase mixer pressure; remove build-up material "
            "from the mixing head/hoses; check for blocked filters causing under-pressure; check polyol pipe sizing/routing "
            "for trapped air.",
        },
        {
            "name": "Ruptured foam",
            "typical_causes": "Foam with low tensile strength; a line of ruptured, easily split material "
            "near the bottom or top corners. Foam is extremely open - increase the tin level.",
        },
        {
            "name": "Poor fingernail recovery",
            "typical_causes": "Foam recovers slowly when indented with a sharp object. Improve foam air "
            "flow by decreasing tin catalyst and/or silicone levels; try a finer cell size; improve curing "
            "conditions.",
        },
    ],
    "Splits & cracks": [
        {
            # CR-22 / F22-07 (AF22-01): QUARANTINED - inherited from the
            # non-Rigid source guide's continuous-line process, requires
            # separate technical validation before Rigid Block
            # reactivation. Guidance text left as-is (historical display
            # only, not offered for new selection).
            "name": "Splits - normal cell structure, open cells",
            "state": STATE_QUARANTINED,
            "typical_causes": "Splits associated with a normal cell size and open cells. Tin catalyst too "
            "low or deactivated - check output; polyol/TDI temperature too low - check and adjust; "
            "silicone level too low - lab-test and adjust; incorrect amine catalyst blend ratio - compare "
            "against standard in the lab.",
        },
        {
            "name": "Splits - abnormal fine/broken cell structure",
            "state": STATE_QUARANTINED,
            "typical_causes": "Splits associated with an abnormally fine, broken cell structure. Excessive "
            "air in the mix - check for entrained air/leaks; stirrer speed too high - reduce in stages; "
            "mixer exit nozzle too large - reduce diameter in stages.",
        },
        {
            "name": "Gross splits",
            "state": STATE_QUARANTINED,
            "typical_causes": "Large vertical or horizontal separation in the block. Increase tin catalyst "
            "(check activity); decrease amine catalyst; increase silicone (check activity); decrease water "
            "level; check mechanical factors.",
        },
        {
            "name": "Zigzag (tin) splits",
            "state": STATE_QUARANTINED,
            "typical_causes": "Crumbly zigzag splits throughout the block or on the sides. Increase tin "
            "catalyst concentration; check for reduced tin reactivity/output; check TDI and water output; "
            "increase silicone level.",
        },
    ],
    "Density, shape & dimensional": [
        {
            "name": "Shrinkage",
            "typical_causes": "Block shrinks during curing. Decrease tin catalyst and silicone level; "
            "increase mixer speed; check for contaminants; decrease TDI index; increase amine "
            "catalyst; lower component temperatures; enlarge the mixer outlet nozzle.",
        },
        {
            # CR-22 / F22-07 (AF22-01): QUARANTINED - pending a validated
            # Rigid Block issue definition; density remains available
            # through the Rigid property/test model in the meantime.
            "name": "Low block density",
            "state": STATE_QUARANTINED,
            "typical_causes": "Reduced block height, associated with high curing temperature/scorching or "
            "increased TDI vapour at cut-off. Check for a shortage of blowing agent or "
            "water for primary blowing; check output, temperature, and feed tank/filter/valve condition.",
        },
        {
            "name": "Bottom cavitation",
            "state": STATE_QUARANTINED,
            "typical_causes": "Closed cells with the bottom of the block eaten away. Reduce tin catalyst; "
            "check for metering errors.",
        },
        {
            "name": "Bottom skin densification",
            "state": STATE_QUARANTINED,
            "typical_causes": "A layer of denser foam at the bottom of the block. Increase silicone level "
            "or check for reduced activity.",
        },
        {
            # AF22-01: the approved Rigid master already contains "Density
            # gradient" as the controlled Rigid concept for this fault - no
            # automatic remapping performed (CR-22 does no destructive
            # migration), so the legacy name is simply quarantined.
            "name": "Stratification",
            "state": STATE_QUARANTINED,
            "typical_causes": "Irregular density throughout the block. Look for errors in component "
            "metering; check mechanical factors.",
        },
        {
            # AF22-01: the approved Rigid master defines "Skin" and "Poor
            # skin formation" - "Heavy skin" has no validated Rigid issue
            # definition in the current master.
            "name": "Heavy skin",
            "state": STATE_QUARANTINED,
            "typical_causes": "Thick skin of high density. Increase total system catalysis and TDI content; "
            "heat the block surface.",
        },
        {
            "name": "Low catalyst tolerance",
            "typical_causes": "Foam shows excessive sensitivity to small changes in tin catalyst "
            "concentration. Use a diluted catalyst for finer metering control; check metering accuracy of "
            "all components; decrease amine catalyst; use a lower-activity silicone.",
        },
    ],
    "Physical property deviation": [
        {
            "name": "Poor tensile strength / weak foam",
            "typical_causes": "Tensile values lower than normal. Check TDI/water/polyol output; reduce cell "
            "size (see Coarse foam); check for a low TDI index; check catalyst filters.",
        },
        {
            "name": "Poor elongation",
            "typical_causes": "Elongation values lower than normal. Check TDI/water/polyol output; check "
            "for a low TDI index.",
        },
        {
            "name": "High compression set",
            "typical_causes": "Compression set values higher than 10%. Decrease tin and silicone levels; "
            "keep the TDI index between 105-108; use a co-catalyst system; improve curing conditions.",
        },
        {
            "name": "Low load-bearing / hardness values",
            "typical_causes": "Formulation produces lower load-bearing (IFD/hardness) values than desired. "
            "Increase TDI index; check for errors in water/TDI/polyol output.",
        },
        {
            "name": "High load-bearing / hardness values",
            "typical_causes": "Formulation produces higher load-bearing (IFD/hardness) values than desired. "
            "Check for errors in water/TDI/polyol output; decrease TDI index.",
        },
    ],
    "Routine / no issue": [
        {
            "name": "No issue found - routine check",
            "typical_causes": "Logged for traceability on a routine batch where nothing abnormal was "
            "observed. No action needed.",
        },
    ],
    "Other / not yet classified": [
        {
            "name": OTHER_ISSUE_NAME,
            "typical_causes": "Use only when the issue genuinely doesn't match any entry above - describe "
            "it in Notes, and consider suggesting it be added to this list.",
        },
    ],
}


def _normalize_entries():
    """Fills in the two CR-22 attributes (`state`, `production_methods`)
    on every entry that didn't spell them out explicitly above, so the
    ~30 unaffected literal dicts don't all need `"state": STATE_ACTIVE,
    "production_methods": None,` boilerplate. Runs once at import time."""
    for entries in QUALITY_ISSUE_TAXONOMY.values():
        for entry in entries:
            entry.setdefault("state", STATE_ACTIVE)
            entry.setdefault("production_methods", None)


_normalize_entries()


def categories():
    """Ordered list of category names, for the first-level selectbox. All
    categories regardless of active/quarantined content - see
    active_categories() for the CR-22 new-selection-safe subset."""
    return list(QUALITY_ISSUE_TAXONOMY.keys())


def active_categories():
    """Ordered list of category names that contain at least one
    STATE_ACTIVE entry - CR-22 / F22-07 (AF22-01). "Splits & cracks" is
    the one category on the v0.64.1 baseline where every entry was
    quarantined, so it's excluded here even though categories() still
    lists it (needed for historical lookup/display)."""
    return [
        category for category, entries in QUALITY_ISSUE_TAXONOMY.items()
        if any(e["state"] == STATE_ACTIVE for e in entries)
    ]


def issue_types_for_category(category):
    """List of issue-type dicts ({"name", "typical_causes", "state",
    "production_methods"}) for one category, unfiltered (active +
    quarantined) - for reference/historical listing. Empty list for an
    unknown category rather than raising, since this is driven by UI
    state. See active_issue_types_for_category() for the CR-22
    new-selection-safe subset."""
    return QUALITY_ISSUE_TAXONOMY.get(category, [])


def active_issue_types_for_category(category, production_method_controlled_id=None, include_names=None):
    """List of issue-type dicts for one category, restricted to entries
    that are safe to offer for a NEW selection - CR-22 / F22-06, F22-07
    (AF22-01):

    - STATE_QUARANTINED entries are excluded, UNLESS their name is in
      `include_names` - this is how a picker keeps an already-recorded
      quarantined value visible/selected while editing that one row,
      without offering it as a fresh pick anywhere else (see
      pages/6_Quality_Observation.py's _issue_type_picker()).
    - A method-specific entry (`production_methods` is a non-None list)
      is excluded unless `production_method_controlled_id` is given and
      is a member of that list. A Global entry (`production_methods` is
      None) is always included regardless of this parameter. On the
      v0.64.1 baseline every active entry is Global, so this parameter
      currently has no observable effect - it exists so a future
      validated method-specific entry activates without another schema
      or call-site redesign (AF22-01 Section 4).
    """
    include_names = include_names or set()
    result = []
    for entry in QUALITY_ISSUE_TAXONOMY.get(category, []):
        if entry["name"] in include_names:
            result.append(entry)
            continue
        if entry["state"] != STATE_ACTIVE:
            continue
        methods = entry["production_methods"]
        if methods is not None and production_method_controlled_id not in methods:
            continue
        result.append(entry)
    return result


_NAME_TO_ENTRY = {
    entry["name"]: {"category": category, **entry}
    for category, entries in QUALITY_ISSUE_TAXONOMY.items()
    for entry in entries
}
_NAME_TO_ENTRY_LOWER = {name.lower(): entry for name, entry in _NAME_TO_ENTRY.items()}


def lookup(name):
    """Exact-name lookup -> {"category", "name", "typical_causes"}, or None
    if `name` isn't a taxonomy entry (e.g. a legacy free-text value entered
    before this taxonomy existed, or a name retired from the active list -
    see the A5-08 note in the module docstring)."""
    return _NAME_TO_ENTRY.get(name)


def lookup_case_insensitive(name):
    """Same as lookup() but case-insensitive and whitespace-trimmed.
    Matches ANY taxonomy entry regardless of state, including
    STATE_QUARANTINED - used where a quarantined value legitimately needs
    to resolve (e.g. displaying/reporting an existing historical row). For
    CSV/Excel import of a NEW row, see lookup_active_case_insensitive()
    instead - CR-22 / F22-06 (AF22-01) requires new-selection paths to
    reject quarantined names the same way the manual-entry picker does."""
    if not name:
        return None
    return _NAME_TO_ENTRY_LOWER.get(name.strip().lower())


def lookup_active_case_insensitive(name, production_method_controlled_id=None):
    """Same as lookup_case_insensitive(), but returns None for a
    STATE_QUARANTINED entry - CR-22 / F22-06 (AF22-01): "Trial behavior"
    and every other new-selection surface must never expose a quarantined
    issue type, and CSV/Excel import is a new-selection surface the same
    as the manual entry form. Used by pages/6_Quality_Observation.py's
    import tab in place of lookup_case_insensitive().

    CR-22 correction (2026-08-16, Charlie's focused closeout return):
    also returns None for a method-specific entry (`production_methods`
    is a non-None list) whose list doesn't contain
    `production_method_controlled_id` - the same rule
    active_issue_types_for_category() applies for the manual-entry
    picker. Leaving `production_method_controlled_id` at its default
    None only excludes method-specific entries (matches "Global only" for
    Customer Trial / Optimization Trial import rows, which carry no
    Production Method context) - a Global entry (`production_methods` is
    None) is always accepted regardless of this parameter, so behavior
    for every entry on the current production taxonomy (all Global) is
    unchanged."""
    entry = lookup_case_insensitive(name)
    if entry is None or entry["state"] != STATE_ACTIVE:
        return None
    methods = entry["production_methods"]
    if methods is not None and production_method_controlled_id not in methods:
        return None
    return entry


def all_issue_names():
    """Flat list of every controlled issue-type name (active AND
    quarantined), in category order - the full set of values a historical
    QualityObservation row may legitimately carry. NOT the set CSV/Excel
    import will accept for a NEW row - see lookup_active_case_insensitive()
    for that (CR-22 / F22-06, AF22-01)."""
    return list(_NAME_TO_ENTRY.keys())
