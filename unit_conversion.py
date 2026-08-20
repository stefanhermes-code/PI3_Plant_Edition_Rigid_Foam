"""WP4 (Converged Joint Implementation Plan, section 7.5) controlled unit
conversion for rigid-foam property comparisons.

WP3 deliberately deferred this (see wp3_conformance._specs_match_result's
original docstring and WP3 UAT case 06, "wrong unit, conversion deferred") -
a result recorded in a different-but-convertible unit than its
GradeSpecification was simply excluded as a context mismatch. That was the
correct scope for WP3 (Gate 2 was about proving the matching/exclusion
machinery worked at all), but it means a lab that reports thermal
conductivity in mW/(m.K) instead of W/(m.K) - a common, legitimate unit
choice, not a data-entry error - can never be evaluated against a grade
spec written in the other unit. WP4 closes that gap for units this module
knows how to convert; a genuinely unconvertible or unknown unit pair still
falls back to the WP3 behavior (excluded, not guessed at).

Design, deliberately narrow:
- Every unit in a group converts to the group's base unit by a single
  multiplicative factor (value_in_base = value * factor). All the physical
  quantities this app currently records (thermal conductivity, density,
  compressive/tensile/flexural strength, percentages, linear dimensions)
  are linear-scale conversions - no offset term (unlike, say, Celsius to
  Fahrenheit) is needed anywhere converted values are actually compared
  against a spec limit in this app, so a single-factor model is
  intentionally not over-built into a general-purpose units library.
- Unit strings are normalized (case, whitespace, "*"/"." separators)
  before lookup, but the alias list only covers variants actually seen in
  Charlie's WP3 package or realistically expected from lab equipment/TDS
  documents - same "grow the controlled list as real data arrives"
  approach already used for every other controlled vocabulary in this app
  (see db.py's *_id lookup tables), rather than attempting to parse
  arbitrary unit strings.
- A pair of units that both resolve to the same group converts cleanly. A
  pair that doesn't (unknown unit, or units from two different physical
  quantities e.g. "kPa" vs "kg/m3") is NOT convertible - convert() returns
  None and callers must treat that exactly like WP3 treated every unit
  mismatch: an excluded/incomparable context, not a guessed value.
"""

# group_name -> {normalized_unit: factor_to_base_unit}. The base unit is
# simply whichever unit has factor 1.0 - not otherwise privileged.
_UNIT_GROUPS = {
    "thermal_conductivity": {
        "w/(m.k)": 1.0,
        "w/m.k": 1.0,
        "w/mk": 1.0,
        "mw/(m.k)": 0.001,
        "mw/m.k": 0.001,
        "mw/mk": 0.001,
        # 1 W/(m.K) = 6.933471... Btu.in/(hr.ft2.F) - included since US-market
        # insulation TDS sheets commonly report in this unit.
        "btu.in/(hr.ft2.f)": 1.0 / 6.933471,
        "btu.in/(hr.ft^2.f)": 1.0 / 6.933471,
    },
    "density": {
        "kg/m3": 1.0,
        "kg/m^3": 1.0,
        "g/cm3": 1000.0,
        "g/cm^3": 1000.0,
        "lb/ft3": 16.01846337,
        "lb/ft^3": 16.01846337,
        "pcf": 16.01846337,  # "pounds per cubic foot", common shorthand
    },
    "pressure_strength": {
        # Covers compressive/tensile/flexural strength and similar
        # force-per-area properties - all share one unit family.
        "kpa": 1.0,
        "mpa": 1000.0,
        "pa": 0.001,
        "n/mm2": 1000.0,
        "n/mm^2": 1000.0,
        "bar": 100.0,
        "psi": 6.894757293168,
    },
    "percentage": {
        "%": 1.0,
        "pct": 1.0,
        "percent": 1.0,
    },
    "length": {
        "mm": 1.0,
        "cm": 10.0,
        "m": 1000.0,
        "in": 25.4,
        "inch": 25.4,
    },
    # --- R-PRE (2026-08-20). Stefan's ruling: cP is the controlled standard
    # for viscosity, and a value arriving from a supplier data sheet in some
    # other unit is converted into it rather than stored as typed.
    #
    # 1 cP = 1 mPa.s EXACTLY - the same size, not a rounded factor.
    "dynamic_viscosity": {
        "cp": 1.0,
        "centipoise": 1.0,
        "mpa.s": 1.0,
        "mpas": 1.0,
        "p": 100.0,
        "poise": 100.0,
        "pa.s": 1000.0,
        "pas": 1000.0,
        "kg/(m.s)": 1000.0,
        "kg/m.s": 1000.0,
        "n.s/m2": 1000.0,
        "n.s/m^2": 1000.0,
    },
    # KINEMATIC viscosity is a DIFFERENT physical quantity: kinematic =
    # dynamic / density. It gets its own group precisely so that convert()
    # REFUSES a cSt -> cP request, which is the mistake this separation
    # exists to prevent. For a polyol around 1.02 g/cm3 the error from
    # treating them as interchangeable is about 2% - small enough to look
    # like a plausible reading and large enough to matter on a release
    # specification. Crossing between the two needs a density, and there is
    # one function that does it: dynamic_viscosity_cp().
    "kinematic_viscosity": {
        "cst": 1.0,
        "centistokes": 1.0,
        "mm2/s": 1.0,
        "mm^2/s": 1.0,
        "st": 100.0,
        "stokes": 100.0,
        "m2/s": 1000000.0,
        "m^2/s": 1000000.0,
    },
}

# The controlled standard, per Stefan's ruling of 20 August 2026: follow
# ASTM D445 and hold viscosity in mPa.s.
#
# 1 mPa.s = 1 cP EXACTLY, so this is a label on the same quantity - no factor
# below changed when the standard moved from cP, and cP remains an accepted
# input unit converting 1:1. It is still the unit most polyurethane data
# sheets print.
VISCOSITY_STANDARD_UOM = "mPa.s"

# Saybolt Universal Seconds turns up on older lubricant and some resin data
# sheets. It is deliberately NOT in the kinematic group: the relationship to
# cSt is an empirical piecewise formula, not a factor, and it is only defined
# over part of the range. A wrong-but-confident number is worse here than a
# refusal, so these resolve to "not convertible" and the reading has to be
# obtained in a real unit.
_REFUSED_VISCOSITY_UNITS = ("sus", "ssu", "saybolt", "sfs", "ssf", "engler", "redwood")


def _normalize(unit):
    if not unit:
        return None
    return unit.strip().lower().replace(" ", "").replace("*", ".").replace("·", ".")


def _find_group(normalized_unit):
    for group_name, factors in _UNIT_GROUPS.items():
        if normalized_unit in factors:
            return group_name
    return None


def convert(value, from_unit, to_unit):
    """Converts `value` from from_unit to to_unit, or returns None if the
    two units aren't both recognized members of the same conversion group
    (unknown unit, or units belonging to two different physical
    quantities). Never raises for an unrecognized unit - callers should
    treat None exactly like a WP3-style unit mismatch."""
    if value is None:
        return None
    nf, nt = _normalize(from_unit), _normalize(to_unit)
    if nf is None or nt is None:
        return None
    if nf == nt:
        return value
    group_f, group_t = _find_group(nf), _find_group(nt)
    if group_f is None or group_t is None or group_f != group_t:
        return None
    factors = _UNIT_GROUPS[group_f]
    value_in_base = value * factors[nf]
    return value_in_base / factors[nt]


def convertible(from_unit, to_unit):
    """True if convert() would succeed for this unit pair (without actually
    needing a value in hand) - used by wp3_conformance._specs_match_result
    to decide whether a unit difference is an exclusion or just a
    to-be-converted context."""
    return convert(1.0, from_unit, to_unit) is not None


def dynamic_viscosity_cp(value, from_unit, density_g_per_cm3=None):
    """A viscosity from a supplier data sheet, expressed in the controlled cP
    standard. Returns None when it cannot be done honestly - never a guess.

    Dynamic units (mPa.s, Pa.s, P and their spellings) convert on a factor
    alone. KINEMATIC units (cSt, mm2/s) cannot: kinematic = dynamic / density,
    so a density in g/cm3 must be supplied and the result is
    value_in_cSt * density. Without it this returns None rather than
    pretending the two quantities are the same thing.

    Under ASTM D445 this is not an optional extra: D445 measures the KINEMATIC
    viscosity and calculates the dynamic value from it using the density at
    the same temperature. ASTM D2196 (rotational) reads the dynamic value
    directly and needs no density.

    density_g_per_cm3 may be taken from the material's recorded specific
    gravity, which is numerically the same to well within the precision a
    data sheet quotes - specific gravity is the density relative to water,
    and water is 1.000 g/cm3 at its reference temperature.

    Saybolt, Engler and Redwood readings are refused outright: their
    relationship to cSt is an empirical piecewise formula rather than a
    factor. See _REFUSED_VISCOSITY_UNITS.
    """
    if value is None:
        return None
    normalized = _normalize(from_unit)
    if normalized is None:
        return None
    if any(token in normalized for token in _REFUSED_VISCOSITY_UNITS):
        return None

    group = _find_group(normalized)
    if group == "dynamic_viscosity":
        return convert(value, from_unit, VISCOSITY_STANDARD_UOM)
    if group == "kinematic_viscosity":
        if density_g_per_cm3 is None or density_g_per_cm3 <= 0:
            return None
        in_centistokes = convert(value, from_unit, "cSt")
        if in_centistokes is None:
            return None
        return in_centistokes * density_g_per_cm3
    return None


def viscosity_conversion_note(from_unit, density_g_per_cm3=None):
    """Why a viscosity could not be converted, in words a person can act on -
    so a page can say what is missing instead of silently dropping the value."""
    normalized = _normalize(from_unit)
    if normalized is None:
        return "No unit given for the viscosity reading."
    if any(token in normalized for token in _REFUSED_VISCOSITY_UNITS):
        return (
            f"{from_unit} cannot be converted to {VISCOSITY_STANDARD_UOM}: its relationship to "
            "centistokes is an empirical formula, not a fixed factor. Obtain the reading in "
            "cP, mPa.s, Pa.s or cSt."
        )
    group = _find_group(normalized)
    if group == "kinematic_viscosity" and (density_g_per_cm3 is None or density_g_per_cm3 <= 0):
        return (
            f"{from_unit} is a kinematic viscosity. Converting it to {VISCOSITY_STANDARD_UOM} "
            "needs the material density in g/cm3 (its specific gravity will do). Record that "
            "first."
        )
    if group is None:
        return f"{from_unit} is not a recognised viscosity unit."
    return ""

