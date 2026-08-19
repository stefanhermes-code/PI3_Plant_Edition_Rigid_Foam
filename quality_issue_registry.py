"""Phase 8 P8-D01 (17 Aug 2026, Charlie's binding architecture decision on
the JC Phase 8 implementation plan review): the customer-facing controlled
vocabulary for the Quality Issue picker, sourced from the
QualityIssueType / PossibleCause / IssueCauseLink database masters -
replacing quality_issue_taxonomy.py's Python dict as the source for this
(Rigid Foam) app. quality_issue_taxonomy.py is left in place, unused by
this app going forward, per Charlie's instruction to keep the Flexible
edition's own path separate and not maintain a second PM-800 (or any
Rigid) list inside it.

Every function here mirrors quality_issue_taxonomy.py's contract
(categories / active_categories / active_issue_types_for_category /
lookup / lookup_case_insensitive / lookup_active_case_insensitive /
OTHER_ISSUE_NAME) so views/6_Quality_Observation.py's call sites only
needed a `session` argument threaded through, not a behavior redesign -
content now lives in the DB, so every function takes the SQLAlchemy
`session` as its first argument instead of reading a module-level
constant.

State (QualityIssueType.state, added by this same Phase 8 migration):
'active' | 'quarantined' - identical semantics to the old module's
STATE_ACTIVE / STATE_QUARANTINED (CR-22 / AF22-01): a quarantined entry
is excluded from every NEW-selection surface (manual entry, CSV/Excel
import) but stays valid/readable on any QualityObservation row that
already carries it. All 64 pre-existing WP5 Wave 3 rows default to
'active' - Charlie's WP5 Wave 3 seeding never flagged any of them for
quarantine (unlike the Flexible-sourced Laader Berg content the old
Python module had to filter under A5-08), so this is a pure default, not
a reclassification of real content.

Method applicability (QualityIssueTypeApplicability, new table): zero
rows for a given issue = Global (offered for every Production Method) -
same "absence means Global" convention as
quality_issue_taxonomy.py's `production_methods=None` and
ProcessSettingApplicability's NULL/NULL row. No live WP5 Wave 3 data
structurally restricts any issue to specific methods
(QualityIssueType.applicable_methods is free descriptive text, e.g.
"Faced panels/products" - not a controlled_id list), so every issue is
Global on cutover - this reproduces the old module's actual behavior
("every active entry today is Global") exactly, while leaving the
mechanism in place for a future validated method-specific restriction
(same reasoning AF22-01 Section 4 used).

"Other / not yet classified": kept as a synthetic, non-DB category/entry
(OTHER_CATEGORY / OTHER_ISSUE_NAME) - Rigid's controlled QI-* vocabulary
is not meant to be extended ad hoc by end users, so the free-text
fallback for a genuinely novel issue is preserved exactly as before.

Typical-causes guidance: the DB has no free-text "typical causes"
paragraph the way the old Laader Berg-derived module did. Built here
instead from the issue's real linked PossibleCause rows via
IssueCauseLink - a "Possible causes to check" list of controlled cause
names. This is more precise than free prose (it reuses real WP2/WP5
structured data, the same masters WP4/WP5's root-cause logic uses) even
though it's a different shape than the old guidance text.
"""

from sqlalchemy import func

OTHER_ISSUE_NAME = "Other (not yet in this list)"
OTHER_CATEGORY = "Other / not yet classified"
STATE_ACTIVE = "active"
STATE_QUARANTINED = "quarantined"


def _resolve_method_id(session, production_method_controlled_id):
    if not production_method_controlled_id:
        return None
    from db import ProductionMethod
    pm = (
        session.query(ProductionMethod)
        .filter(ProductionMethod.controlled_id == production_method_controlled_id)
        .first()
    )
    return pm.id if pm else None


def _applicable_method_ids(session, quality_issue_type_id):
    """Set of production_method_id this issue is restricted to, or None
    for Global (no restriction rows exist) - see module docstring."""
    from db import QualityIssueTypeApplicability
    rows = (
        session.query(QualityIssueTypeApplicability.production_method_id)
        .filter(QualityIssueTypeApplicability.quality_issue_type_id == quality_issue_type_id)
        .all()
    )
    return {r[0] for r in rows} if rows else None


def _typical_causes_text(session, issue_type):
    """'Possible causes to check: ...' built from the issue's real
    IssueCauseLink -> PossibleCause rows, or None if this issue has no
    linked causes yet. Deduplicated and sorted for stable display."""
    from db import IssueCauseLink
    links = (
        session.query(IssueCauseLink)
        .filter(IssueCauseLink.issue_type_id == issue_type.id)
        .all()
    )
    cause_names = sorted({link.cause.name for link in links if link.cause})
    if not cause_names:
        return None
    return (
        f"Possible causes to check: {', '.join(cause_names)}. "
        "Candidate only - confirm with run/item evidence and review."
    )


def _entry_dict(session, issue_type):
    return {
        "category": issue_type.issue_category or OTHER_CATEGORY,
        "name": issue_type.name,
        "typical_causes": _typical_causes_text(session, issue_type),
    }


def categories(session):
    """Ordered list of category names, for the first-level selectbox -
    every distinct issue_category in the DB, plus the synthetic "Other /
    not yet classified" catch-all category, in that order."""
    from db import QualityIssueType
    cats = [
        row[0]
        for row in (
            session.query(QualityIssueType.issue_category)
            .distinct()
            .order_by(QualityIssueType.issue_category)
            .all()
        )
        if row[0]
    ]
    return cats + [OTHER_CATEGORY]


def active_categories(session):
    """Same as categories(), restricted to categories that contain at
    least one STATE_ACTIVE entry (CR-22 / F22-07 equivalent) - "Other /
    not yet classified" always qualifies since its one entry is always
    offered."""
    from db import QualityIssueType
    cats = [
        row[0]
        for row in (
            session.query(QualityIssueType.issue_category)
            .filter(QualityIssueType.state == STATE_ACTIVE)
            .distinct()
            .order_by(QualityIssueType.issue_category)
            .all()
        )
        if row[0]
    ]
    return cats + [OTHER_CATEGORY]


def active_issue_types_for_category(session, category, production_method_controlled_id=None, include_names=None):
    """List of issue-type dicts ({"name", "typical_causes"}) for one
    category, restricted to entries safe to offer for a NEW selection -
    same CR-22 / F22-06, F22-07 rules as the old module:

    - STATE_QUARANTINED entries are excluded, UNLESS their name is in
      `include_names` (keeps an already-recorded quarantined value
      visible/selected while editing that one row).
    - A method-specific entry (has one or more QualityIssueTypeApplicability
      rows) is excluded unless `production_method_controlled_id` resolves
      to one of those methods. A Global entry (zero rows) is always
      included.
    """
    from db import QualityIssueType
    include_names = include_names or set()
    if category == OTHER_CATEGORY:
        return [{
            "name": OTHER_ISSUE_NAME,
            "typical_causes": (
                "Use only when the issue genuinely doesn't match any entry above - "
                "describe it in Notes, and consider suggesting it be added to the "
                "controlled taxonomy."
            ),
        }]
    pm_id = _resolve_method_id(session, production_method_controlled_id)
    result = []
    for it in (
        session.query(QualityIssueType)
        .filter(QualityIssueType.issue_category == category)
        .order_by(QualityIssueType.sort_order, QualityIssueType.controlled_id)
        .all()
    ):
        if it.name in include_names:
            result.append(_entry_dict(session, it))
            continue
        if it.state != STATE_ACTIVE:
            continue
        method_ids = _applicable_method_ids(session, it.id)
        if method_ids is not None and pm_id not in method_ids:
            continue
        result.append(_entry_dict(session, it))
    return result


def lookup(session, name):
    """Exact-name lookup -> {"category", "name", "typical_causes"}, or
    None if `name` isn't a taxonomy entry (e.g. a legacy free-text value
    entered before this taxonomy existed)."""
    from db import QualityIssueType
    if not name:
        return None
    if name == OTHER_ISSUE_NAME:
        return {"category": OTHER_CATEGORY, "name": OTHER_ISSUE_NAME, "typical_causes": None}
    it = session.query(QualityIssueType).filter(QualityIssueType.name == name).first()
    return _entry_dict(session, it) if it else None


def lookup_case_insensitive(session, name):
    """Same as lookup() but case-insensitive/whitespace-trimmed, and
    matches regardless of state (including STATE_QUARANTINED) - for
    resolving/displaying an existing historical row. For CSV/Excel import
    of a NEW row, see lookup_active_case_insensitive() instead."""
    from db import QualityIssueType
    if not name:
        return None
    stripped = name.strip()
    if stripped.lower() == OTHER_ISSUE_NAME.lower():
        return {"category": OTHER_CATEGORY, "name": OTHER_ISSUE_NAME, "typical_causes": None}
    it = (
        session.query(QualityIssueType)
        .filter(func.lower(QualityIssueType.name) == stripped.lower())
        .first()
    )
    return _entry_dict(session, it) if it else None


def lookup_active_case_insensitive(session, name, production_method_controlled_id=None):
    """Same as lookup_case_insensitive(), but returns None for a
    STATE_QUARANTINED entry, or a method-specific entry that doesn't
    include `production_method_controlled_id` - CR-22 / F22-06 equivalent:
    every new-selection surface (manual entry, CSV/Excel import) must
    never expose a quarantined or out-of-method issue type."""
    from db import QualityIssueType
    if not name:
        return None
    stripped = name.strip()
    it = (
        session.query(QualityIssueType)
        .filter(func.lower(QualityIssueType.name) == stripped.lower())
        .first()
    )
    if not it or it.state != STATE_ACTIVE:
        return None
    pm_id = _resolve_method_id(session, production_method_controlled_id)
    method_ids = _applicable_method_ids(session, it.id)
    if method_ids is not None and pm_id not in method_ids:
        return None
    return _entry_dict(session, it)


def all_issue_names(session):
    """Flat list of every controlled issue-type name (active AND
    quarantined), in category/sort order - the full set of values a
    historical QualityObservation row may legitimately carry."""
    from db import QualityIssueType
    return [
        row[0]
        for row in (
            session.query(QualityIssueType.name)
            .order_by(QualityIssueType.issue_category, QualityIssueType.sort_order)
            .all()
        )
    ]
