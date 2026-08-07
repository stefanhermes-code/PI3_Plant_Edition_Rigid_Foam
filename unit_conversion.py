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
}


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
