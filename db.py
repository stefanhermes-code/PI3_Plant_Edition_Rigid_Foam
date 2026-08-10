"""
PI3 Rigid Foam Edition - forked from PI3 Plant Edition (flexible slabstock
foam). Database layer: SQLAlchemy models.

Connection:
- Production / Streamlit Cloud: set st.secrets["DATABASE_URL"] to a Supabase
  Postgres connection string (Session pooler, e.g.
  postgresql+psycopg2://postgres:<password>@<host>:5432/postgres).
- Local development: falls back to a local SQLite file (pi3_local.db) if
  DATABASE_URL is not set. Do NOT rely on SQLite for the deployed app -
  Streamlit Community Cloud's filesystem is not guaranteed to persist
  across reboots/redeploys.

Schema separation (decided 2026-08-06, see version.py): this app shares the
flexible app's Supabase PROJECT (same database, same connection string) but
NOT its tables. Every table this app defines lives in its own Postgres
schema, "rigid_foam", instead of the flexible app's "public" schema - see
RIGID_FOAM_SCHEMA below. This only applies when the target database is
Postgres; the local SQLite dev fallback has no meaningful schema concept
and keeps using its single default namespace, unchanged.
"""

import datetime as dt
import os

import streamlit as st
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker


class _NoDeepCopyMixin:
    """Mixin applied to every ORM model via declarative_base(cls=...).

    Streamlit's widget-state tracking (session_state.py: register_widget)
    deepcopies a selectbox's option values to detect changes across reruns.
    Several pages pass live ORM objects (Plant, FoamGrade, CustomerTrial, ...)
    directly as selectbox options. Once any bidirectional relationship
    collection reachable from one of those objects becomes non-empty (e.g.
    a trial gets its first physical property result), copy.deepcopy hits a
    known SQLAlchemy/backref-collection incompatibility and raises
    (AttributeError: '...' object has no attribute '_sa_instance_state', or
    'InstanceState' object has no attribute 'obj').

    These are already persistent, identity-mapped objects, so there is no
    good reason to actually duplicate one: returning `self` from
    __deepcopy__ sidesteps the incompatibility entirely and is semantically
    fine here (nothing in this app relies on Streamlit's before/after value
    comparison for these widgets - none of them use on_change=).
    """

    def __deepcopy__(self, memo):
        return self


def _database_url() -> str:
    # 1. Streamlit secrets (Streamlit Cloud deployment)
    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    # 2. Environment variable (local / CI)
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    # 3. Local fallback - SQLite, dev only
    return "sqlite:///pi3_local.db"


DATABASE_URL = _database_url()

# Postgres (Supabase) only: give every table in this app its own schema so
# it can share the flexible app's project/database without colliding with
# or migrating alongside the flexible app's "public"-schema tables. Every
# CREATE TABLE and every generated SELECT/INSERT/UPDATE/DELETE is
# automatically schema-qualified (e.g. "rigid_foam"."production_runs") once
# this is set on the declarative Base's MetaData - no per-model change
# needed, and no DATABASE_URL/search_path trick required either.
#
# SQLite (local dev fallback) has no comparable schema concept worth
# reproducing here, so it keeps using the engine's single default
# namespace - RIGID_FOAM_SCHEMA is None in that case.
RIGID_FOAM_SCHEMA = "rigid_foam" if DATABASE_URL.startswith("postgresql") else None

Base = declarative_base(cls=_NoDeepCopyMixin, metadata=MetaData(schema=RIGID_FOAM_SCHEMA))

# In-memory SQLite ("sqlite://" or "sqlite:///:memory:", the dev-fallback/
# test convention used by tests/test_*.py) defaults to SQLAlchemy's
# SingletonThreadPool, which ties the one in-memory database to whichever
# thread first opens it - a second thread (e.g. Streamlit's AppTest, which
# runs each page script in its own new thread) then gets a connection
# object it can't use, raising "SQLite objects created in a thread can
# only be used in that same thread" the moment that connection is reset or
# closed. StaticPool + check_same_thread=False (SQLAlchemy's own documented
# fix for this exact case) shares the one in-memory connection across every
# thread instead, so a pytest fixture (main thread) and an AppTest page run
# (its own thread) see the same seeded data. Postgres (production/Supabase)
# and file-based SQLite are unaffected - this only changes pooling for the
# in-memory dev/test path.
_engine_kwargs = dict(pool_pre_ping=True, pool_recycle=280)
if DATABASE_URL in ("sqlite://", "sqlite:///:memory:"):
    from sqlalchemy.pool import StaticPool
    _engine_kwargs = dict(poolclass=StaticPool, connect_args={"check_same_thread": False})

ENGINE = create_engine(DATABASE_URL, **_engine_kwargs)
# expire_on_commit=False: keep already-loaded attributes readable after a
# commit, since the session below is reused across Streamlit reruns rather
# than recreated each time.
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Confidence / status vocabularies (shared across entities)
# ---------------------------------------------------------------------------
CONFIDENCE_LEVELS = ["Confirmed", "Likely", "Unconfirmed", "Rejected"]
APPROVAL_STATUSES = ["Draft", "Pending Review", "Approved", "Rejected"]
TRIAL_STATUSES = ["Open", "Pending Closure", "Closed"]
# Process-data capture vocabularies (Mandatory-tier taxonomy, see
# "Expanding PI3 Plant Edition Production-Trial Data Capture" report).
# Limited to two snapshots deliberately: without a live PLC/OPC UA/MQTT link
# or a machine data export/import, there is no honest way to capture the
# in-between phases (start-up, stabilization, steady-state, adjustment) as
# anything more than guesses. "Setup" is what was planned/configured before
# or at the start of the run; "Finalized" is what was actually used, entered
# at shutdown/completion. Recording the same fields at both points gives the
# plan-vs-actual comparison for free, without needing a separate setpoint
# column next to every actual column.
PHASE_NAMES = [
    "Setup",
    "Finalized",
]
EVENT_TYPES = [
    "Alarm",
    "Intervention",
    "Grade Change",
    "Planned Pause",
    "Unplanned Pause",
    "Other",
]
SEVERITIES = ["Low", "Medium", "High"]

# How the foam is laid down onto the conveyor. Controlled vocabulary (was a
# free-text "laydown mode" field until 2026-08-03): LLD (liquid laydown
# device - pours directly), Trough, or Traverse (a moving/oscillating LLD
# head). Deliberately just these three - anything else is genuinely rare
# enough on the lines this app targets that it isn't worth an "Other" escape
# hatch yet.
FOAMING_MODES = ["LLD", "Trough", "Traverse"]

RAW_MATERIAL_CATEGORIES = [
    "Polyol",
    "Isocyanate",
    "Blowing agent",
    "Catalyst",
    "Surfactant",
    "Flame retardant",
    "Colorant / Pigment",
    "Cross-linker / Chain extender",
    "Filler",
    "Additive",
    "Other",
]

ZONE_LABELS = ["Top", "Middle", "Bottom", "Whole sample / N/A"]

# A sample/result/issue belongs to exactly one of these three parents -
# never more than one, never none. Enforced at the app level
# (sample_source_fk_field() below, used by pages 5/6/9) rather than a DB CHECK, to keep local SQLite
# dev portable. "Production" is the only one that ever has real machine/
# process settings (ProductionPhase) behind it - CustomerTrial and
# OptimizationTrial are both independent lab-trial flows with no such
# context, per user direction 2026-08-03.
SAMPLE_SOURCE_TYPES = ["Production Run", "Customer Trial", "Optimization Trial"]


def sample_source_fk_field(source_type):
    """Which FK column on Sample/PhysicalPropertyResult/QualityObservation
    corresponds to a SAMPLE_SOURCE_TYPES value - single point of truth so
    pages 5/6/9 never hardcode this mapping three separate times."""
    return {
        "Production Run": "production_run_id",
        "Customer Trial": "customer_trial_id",
        "Optimization Trial": "optimization_trial_id",
    }[source_type]


# ---------------------------------------------------------------------------
# 0. subscription_types / companies / roles / role_page_permissions / users
#
# Multi-tenant access control. A Company is the tenant boundary: it owns a
# subscription (which caps user/plant counts and gates whole feature areas)
# and its own users. Data isolation is "shared database, company_id column"
# rather than one database per customer - plants, raw_materials, and
# suppliers each carry a company_id (everything else already hangs off
# plant_id through the existing hierarchy, so scoping the plant list per
# company scopes everything under it).
#
# Roles are a real table, not a hardcoded list, so the platform owner can
# define any number of default role templates beyond the original three
# (admin/technical/viewer, company_id NULL - cloned into every new company,
# see role_provisioning.py), and a company can define its own custom roles
# on top of its clones.
#
# Per-role, per-page access is a DENY list, not an allow list: a role with
# no RolePagePermission rows has full access to every page (matches every
# role's behavior before this per-page split existed, and needs no rows
# seeded for the common case). Each row can deny in one of two ways:
#   - can_view=False: the page is hidden entirely (nav + direct access).
#   - can_view=True, can_use=False: the page is visible and its data can be
#     read, but its Add/Edit/Delete forms and any action buttons (CSV
#     import, "Ask PI3", approvals, downloads, ...) are hidden - a genuine
#     read-only view, not just a suggestion. can_use=True with no row is
#     the default ("full access"); can_use=True is never combined with
#     can_view=False (using implies being able to view) - the admin UI only
#     ever offers three states (Hidden / View only / Full access) to avoid
#     that nonsensical combination, see access_control.py.
# As of this schema version the MODEL supports view-vs-use everywhere, but
# individual operational pages opting in to actually hiding their own
# write controls when can_use=False is a page-by-page rollout, not yet
# complete for every page - see access_control.py's module docstring for
# which pages currently check it.
# ---------------------------------------------------------------------------
class SubscriptionType(Base):
    __tablename__ = "subscription_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    max_users = Column(Integer)  # NULL = unlimited
    max_plants = Column(Integer)  # NULL = unlimited
    pi3_ai_enabled = Column(Boolean, default=True)  # PI3 Connectivity page - the one real feature differentiator between HTC's two tiers, see access_control.py
    reports_enabled = Column(Boolean, default=True)  # Report page
    # Each subscription type row is now a single fixed billing frequency
    # (2026-08-01 restructure) - "PI3 Plant Edition" and "PI3 Plant Edition
    # - Basic" each became two rows (an "- Annual" one and a "- Monthly"
    # one) instead of one row holding both prices and Company picking which
    # applies. This makes a company's fee AND billing frequency both come
    # from the single subscription_type_id it's assigned - no separate
    # Company.billing_frequency field to keep in sync (removed - see
    # Company docstring), and each frequency's price can be changed
    # independently (e.g. a monthly-only price bump) without touching the
    # other. billing_frequency is "Annual" or "Monthly".
    billing_frequency = Column(String(20), default="Annual")
    price = Column(Float)  # USD/plant, per billing_frequency above
    price_note = Column(String(200))  # free text for anything not captured above (e.g. one-time implementation fee) - no payment processing wired up
    active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    # The formal registered entity name, if different from the (often
    # shorter/trading) name above - e.g. name="Acme Foams", legal_entity_name
    # ="Acme Foam Industries Pte Ltd". Optional: left blank, `name` is used.
    legal_entity_name = Column(String(300))
    vat_number = Column(String(50))
    address = Column(String(300))
    city = Column(String(100))
    postal_code = Column(String(20))
    country = Column(String(100))
    subscription_type_id = Column(Integer, ForeignKey("subscription_types.id"))
    # True only for HTC itself: grants cross-company superadmin scope (see
    # every company, manage subscription types/companies, unrestricted by
    # any single company's plant/user limits).
    is_platform_owner = Column(Boolean, default=False)
    contact_name = Column(String(200))
    contact_email = Column(String(200))
    contact_phone = Column(String(50))
    # billing_frequency used to live here (a separate Annual/Monthly picker
    # a company chose independently of its subscription_type_id). Removed
    # 2026-08-01: SubscriptionType itself is now split one row per
    # frequency (e.g. "PI3 Plant Edition - Annual" vs "- Monthly"), so a
    # company's billing frequency is simply whichever tier row it's
    # assigned to - see SubscriptionType.billing_frequency. One field to
    # pick instead of two that could disagree.
    active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    subscription_type = relationship("SubscriptionType")


class Role(Base):
    """company_id NULL + is_builtin True is a *template* row (exactly 3:
    admin/technical/viewer) - never assigned to a User directly, and never
    shown outside the Default User Roles page (platform-owner-only). Every
    real company gets its own company_id-scoped CLONE of those 3 roles,
    seeded from the templates at company-creation time (see
    role_provisioning.clone_builtin_roles_for_company) - that clone is what
    Users actually get assigned to, and what a company's own admin narrows
    on the User Roles page. This exists because RolePagePermission is keyed
    by role_id alone: if built-in roles stayed a single shared row per
    company, one company narrowing "viewer" would silently narrow every
    other company's viewer role too (a real cross-tenant leak, caught and
    fixed 2026-07-31 before any second real customer existed to be bitten
    by it). Non-builtin (custom) roles are always company_id-scoped from
    creation and were never affected by this - "shared across every
    company" custom roles are deliberately not offered in the UI anymore,
    for the same reason."""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_builtin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class RolePagePermission(Base):
    """A row only ever exists to deny something - see the module docstring
    above the Role class for the full Hidden / View only / Full access
    semantics. can_view=False hides the page outright; can_view=True with
    can_use=False is the new (2026-07-31) view-only state."""

    __tablename__ = "role_page_permissions"

    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    page_key = Column(String(100), nullable=False)  # see access_control.PAGE_CATALOG
    can_view = Column(Boolean, default=False)
    can_use = Column(Boolean, default=True)  # False = read-only for this page (only meaningful when can_view is True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    # Login identifier as of 2026-08-05 (per user direction) - the login
    # form asks for this, not username. username is kept (mirrored to the
    # same value on every create/edit) purely so every existing username-
    # keyed reference elsewhere in the app (session_state, audit logs)
    # keeps working unchanged - it is never shown or asked for separately
    # on the User Accounts page anymore.
    email = Column(String(255), nullable=False, unique=True)
    username = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(200))
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    active = Column(Boolean, default=True)
    valid_from = Column(Date)  # NULL = no start restriction
    valid_until = Column(Date)  # NULL = indefinite
    # Added 2026-08-01: an unconditional bypass of every RolePagePermission
    # check (access_control.can_use_page/page_visible), independent of
    # is_platform_owner and of whatever role this user happens to carry.
    # Why this exists, given Company.is_platform_owner already exists: that
    # flag is a company-SCOPE marker (which companies' data you can see),
    # not a personal permission bypass - by design (see access_control.
    # can_use_page's docstring) a platform-owner-company user assigned a
    # narrow role (e.g. "viewer") is still meant to be restricted like
    # anyone else, so HTC can give its own staff genuinely limited access
    # too. But that same design means the platform owner's own "Platform
    # Admin" role clone is just an ordinary row in the roles table -
    # reachable and editable from the User Roles page like any other company's role - so
    # a platform-owner admin could accidentally narrow their OWN role out
    # from under themselves with no separate escape hatch. is_super_admin is
    # that escape hatch: a per-person flag, editable only on a platform-
    # owner-company user (see pages/25_User_Accounts.py), that always
    # resolves to full access everywhere no matter what any role's
    # RolePagePermission rows say. Reserve it for the platform owner's own
    # trusted staff, not customers' admins.
    is_super_admin = Column(Boolean, default=False)
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    company = relationship("Company")
    role = relationship("Role")


# ---------------------------------------------------------------------------
# 1. plants
# ---------------------------------------------------------------------------
class Plant(Base):
    __tablename__ = "plants"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    name = Column(String(200), nullable=False)
    plant_code = Column(String(50))
    location = Column(String(200))
    active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    company = relationship("Company")
    product_families = relationship("ProductFamily", back_populates="plant")
    pi3_ai_settings = relationship("PI3AIConnectionSetting", back_populates="plant")
    production_methods = relationship("PlantProductionMethod", back_populates="plant")


# ---------------------------------------------------------------------------
# 1a2. plant_production_methods - Production Method architecture change
# (2026-08-09, flat model finalized 2026-08-10). This is the per-Plant
# "on/off switch" for Charlie's global, shared production_methods
# vocabulary: a Plant activates one or more of the 7 flat methods here,
# and Machine setup/selection for that Plant is filtered to only the
# rows activated in this table - not the raw global list. Enforcing
# "machine's plant has this method activated" is done at the application
# layer (helpers.py), matching this codebase's existing convention of
# app-level enforcement for cross-table consistency rules rather than a
# DB CHECK constraint (e.g. RecipeVersion.is_active's exclusivity).
# ---------------------------------------------------------------------------
class PlantProductionMethod(Base):
    __tablename__ = "plant_production_methods"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    production_method_id = Column(Integer, ForeignKey("production_methods.id"), nullable=False)
    active = Column(Boolean, default=True)
    activated_at = Column(DateTime, default=dt.datetime.utcnow)

    plant = relationship("Plant", back_populates="production_methods")
    production_method = relationship("ProductionMethod")


# ---------------------------------------------------------------------------
# 1b. machines (foaming lines) - basic identity, one plant has many machines
#
# Lets process parameters on a production run connect to the actual
# equipment that produced them (OEM vocabulary differs - Laader Berg,
# Hennecke, Cannon, etc. - but PI3 stores the machine-neutral identity here;
# capability/limit fields such as rated conveyor speed or sidewall range can
# be added later without disrupting this).
# ---------------------------------------------------------------------------
MACHINE_OEMS = ["Laader Berg", "Hennecke", "Cannon", "Other"]

# foam_grade_machines - join table for the FoamGrade <-> Machine many-to-many
# assignment (Production Method Hierarchy architecture change, 2026-08-09).
# A plain association table (no extra columns needed yet) rather than a
# mapped class with its own back-populated relationships, since nothing
# today needs to attach data to the assignment itself - if that changes
# (e.g. an assignment-specific status or date), promote this to a full
# class then, same "text field first, promote only if a concrete need shows
# up" precedent as WP5's ProcessingWindow.
#
# Defined here (before Machine/FoamGrade, and referenced below by object,
# not by string) rather than passing secondary="foam_grade_machines" as a
# string: this app sets Base.metadata's own `schema` to RIGID_FOAM_SCHEMA in
# real Postgres use (see near Base's definition), which makes this table's
# real key in Base.metadata.tables "<schema>.foam_grade_machines" - so a
# bare unqualified string here would fail to resolve at mapper-configure
# time against the real Postgres schema (surfaced only in production, where
# RIGID_FOAM_SCHEMA is actually set - local/CI runs against SQLite, where
# RIGID_FOAM_SCHEMA resolves to None, so this bug was invisible to every
# local py_compile/configure_mappers()/pytest check run before release).
# Passing the Table object directly sidesteps name resolution entirely.
foam_grade_machines = Table(
    "foam_grade_machines",
    Base.metadata,
    Column("foam_grade_id", Integer, ForeignKey("foam_grades.id"), primary_key=True),
    Column("machine_id", Integer, ForeignKey("machines.id"), primary_key=True),
)


class Machine(Base):
    __tablename__ = "machines"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    name = Column(String(200), nullable=False)  # e.g. "Line 1", "Maxfoam A"
    machine_code = Column(String(50))
    oem = Column(String(50))  # Laader Berg / Hennecke / Cannon / Other
    model = Column(String(200))
    active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    # --- WP3 additions (2026-08-06): rigid-foam closed-mold metering machine
    # is the same underlying concept as this table's existing flexible-foam
    # foaming line - both are "the equipment that actually ran this
    # production" - so this is extended in place rather than adding a
    # parallel "MeteringMachine" table. production_unit_id links it under a
    # higher-level asset grouping (WP3's ProductionUnit, e.g. "High-pressure
    # metering unit") that has no flexible-foam equivalent and so is
    # nullable; production_method_id records which method-aware family this
    # asset serves (nullable - existing flexible-foam Machine rows have no
    # method concept and are unaffected).
    production_unit_id = Column(Integer, ForeignKey("production_units.id"))
    production_method_id = Column(Integer, ForeignKey("production_methods.id"))

    # --- Machine Data Architecture additions (2026-08-07), per Charlie's
    # "PI3_Plant_Edition_Rigid_Foam_Machine_Data_Design_for_JC" - schema only,
    # manufacturer/model data population deferred (see version.py). This
    # Machine table is Charlie's Layer C, "Plant Installed Equipment
    # Register" (Asset_ID in his document) - the row already representing
    # "the actual equipment installed at this plant". machine_model_id and
    # machine_config_id are nullable links up to the new generic Layers A/B
    # (MachineModel/MachineConfiguration, defined further below in this
    # file - forward FK references resolve fine in SQLAlchemy regardless of
    # class definition order). Existing rows (flexible-foam and WP3 rigid)
    # have neither set and are unaffected.
    machine_model_id = Column(Integer, ForeignKey("machine_models.id"))
    machine_config_id = Column(Integer, ForeignKey("machine_configurations.id"))
    # Section 6 "Identity" fields not already covered above.
    serial_number = Column(String(200))
    asset_tag = Column(String(100))
    year_manufactured = Column(Integer)
    year_installed = Column(Integer)
    status = Column(String(50))  # e.g. "Running", "Idle", "Decommissioned"
    # Deliberately a free-text label, not a new ProductionLine entity - a
    # "production line" in Charlie's document can group several Machine
    # rows (metering unit + mixhead + mold) or map 1:1 to one, and nothing
    # in the app yet needs to query across that grouping. Add a real
    # ProductionLine table later only if a concrete need shows up - same
    # "abstain, don't over-engineer" call as WP5's ProcessingWindow text
    # field.
    production_line_label = Column(String(200))
    # Section 6 "Physical configuration".
    component_count = Column(Integer)
    polyol_pump_type = Column(String(200))
    isocyanate_pump_type = Column(String(200))
    additive_pumps = Column(Text)
    flow_meter_type = Column(String(200))
    mixing_head_model = Column(String(200))
    tank_sizes = Column(Text)
    hose_lengths = Column(Text)
    installed_options = Column(Text)
    # Section 6 "Control configuration".
    plc_type = Column(String(200))
    plc_cpu = Column(String(200))
    hmi = Column(String(200))
    software_version = Column(String(100))
    network_address = Column(String(100))
    data_interface = Column(String(200))
    historian_available = Column(Boolean)
    alarm_history_available = Column(Boolean)
    recipe_management_available = Column(Boolean)
    # Section 6 "Operating envelope".
    design_min_output = Column(Float)
    design_max_output = Column(Float)
    plant_normal_min_output = Column(Float)
    plant_normal_max_output = Column(Float)
    normal_polyol_pressure = Column(Float)
    normal_isocyanate_pressure = Column(Float)
    normal_temperatures = Column(Text)
    ratio_target = Column(Float)
    # Section 6 "Calibration" - deliberately overlaps in concept with the
    # existing, simpler CalibrationRecord table (free-text equipment_type/
    # equipment_label, no asset FK). Not merged/migrated in this schema-only
    # pass - flagged as a known overlap for whoever builds the Machine
    # Maintenance/Calibration UI page, not resolved silently here.
    polyol_calibration_factor = Column(Float)
    isocyanate_calibration_factor = Column(Float)
    other_stream_calibration = Column(Text)
    last_calibration_date = Column(Date)
    calibration_method = Column(String(200))
    calibration_record_link = Column(String(500))
    # Section 6 "Maintenance" (current-state summary; full history lives in
    # MachineMaintenanceRecord, Layer F, below).
    last_pm_date = Column(Date)
    next_pm_date = Column(Date)
    critical_spare_parts = Column(Text)
    current_wear_items = Column(Text)
    open_maintenance_issues = Column(Text)
    service_provider = Column(String(200))
    # Section 6 "Documents" (quick links; full indexed register is
    # MachineDocument, Layer H, below).
    operating_manual_link = Column(String(500))
    electrical_drawing_link = Column(String(500))
    pid_link = Column(String(500))
    spare_parts_list_link = Column(String(500))
    plc_backup_link = Column(String(500))
    commissioning_report_link = Column(String(500))
    service_reports_link = Column(String(500))
    sops_link = Column(String(500))
    # Section 6 "PI3 linkage".
    live_data_link = Column(String(500))
    historian_link = Column(String(500))
    alarm_link = Column(String(500))
    maintenance_link = Column(String(500))
    case_history_link = Column(String(500))
    data_integration_level = Column(Integer)  # 0-5, see section 11

    plant = relationship("Plant")
    production_unit = relationship("ProductionUnit")
    production_method = relationship("ProductionMethod")
    machine_model = relationship("MachineModel")
    machine_config = relationship("MachineConfiguration")
    # Production Method Hierarchy architecture change (2026-08-09): many-to-
    # many with FoamGrade (PU Material) - Charlie's explicit decision that
    # "the same PU Material may legitimately be produced on several
    # machines", via the new foam_grade_machines join table below FoamGrade.
    foam_grades = relationship(
        "FoamGrade", secondary=foam_grade_machines, back_populates="machines"
    )


# ---------------------------------------------------------------------------
# 2. product_families
# ---------------------------------------------------------------------------
class ProductFamily(Base):
    __tablename__ = "product_families"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    name = Column(String(200), nullable=False)
    application = Column(String(200))
    customer_segment = Column(String(200))
    description = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    plant = relationship("Plant", back_populates="product_families")
    foam_grades = relationship("FoamGrade", back_populates="product_family")


# ---------------------------------------------------------------------------
# 3. foam_grades
#
# target_density/target_hardness are dedicated columns rather than entries in
# foam_grade_target_properties below because every grade has them and the
# grade-naming code itself encodes them (e.g. "28170" = 28 kg/m3 density,
# 170 N hardness at 40% ILD) - see grade_name. quality_specification (a
# free-text field) was removed: it only ever restated density/hardness in
# prose and had no other use. Any *other* physical property a grade needs to
# hit (resilience, tensile strength, ...) - optional, and often not yet
# measured/decided - goes in foam_grade_target_properties instead.
# ---------------------------------------------------------------------------
class FoamGrade(Base):
    __tablename__ = "foam_grades"

    id = Column(Integer, primary_key=True)
    product_family_id = Column(Integer, ForeignKey("product_families.id"), nullable=False)
    grade_name = Column(String(200), nullable=False)
    target_density = Column(Float)
    target_hardness = Column(Float)  # Newtons, 40% ILD
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    # --- WP3 additions (2026-08-06): this is Charlie's "ProductGrade"
    # concept - it maps directly onto the grade that already exists here,
    # not a separate table. All four nullable: flexible-foam grades have no
    # chemistry/method/application/construction concept and are unaffected.
    # There is no separate "approved_recipe_id" column - the grade's
    # approved/current recipe is whichever RecipeVersion has is_active=True
    # for this grade (see RecipeVersion.is_active and
    # helpers.activate_recipe_version), the same rule this app already uses
    # everywhere else; duplicating that as a second column here would just
    # create a second place it could go stale.
    chemistry_id = Column(Integer, ForeignKey("chemistries.id"))
    # production_method_id: REMOVED 2026-08-10 per Charlie's "Database
    # Reset and Clean UAT Baseline" instruction, clean-schema decisions
    # section ("Omit FoamGrade.production_method_id from the clean
    # schema. The archived snapshot preserves its historical values; the
    # rebuilt system derives Product Grade methods from assigned
    # Production Units."). This column had already been marked
    # deprecated on 2026-08-10 earlier the same day (Post-G5 flat-PM
    # completion batch) after being identified as a second, competing
    # source of truth alongside the Machine<->FoamGrade many-to-many
    # (foam_grade_machines): a grade's machines can legitimately span
    # more than one flat Production Method, which this single FK could
    # never represent, and nothing enforced agreement between the two.
    # The pre-reset Supabase snapshot (PI3_Rigid_Foam_PreReset_Snapshot_*
    # .zip) preserves every historical value. Use
    # helpers.grade_production_methods(grade) /
    # grade_production_method_label(grade) - which derive a grade's real
    # Production Method(s) from its assigned Machines - as the sole
    # source of truth going forward. See
    # PI3_Rigid_Foam_Edition_Architecture_Correction_FoamGrade_Production_Method.docx
    # for the original assessment.
    application_id = Column(Integer, ForeignKey("applications.id"))
    construction_id = Column(Integer, ForeignKey("product_constructions.id"))
    status = Column(String(50))  # e.g. UAT_ONLY, ACTIVE - controlled-ID grades only; NULL for flexible-foam grades
    production_use = Column(String(200))  # free note, e.g. "No production release" for UAT-only grades

    product_family = relationship("ProductFamily", back_populates="foam_grades")
    recipe_versions = relationship("RecipeVersion", back_populates="foam_grade")
    target_properties = relationship(
        "FoamGradeTargetProperty", back_populates="foam_grade", cascade="all, delete-orphan"
    )
    chemistry = relationship("Chemistry")
    application = relationship("Application")
    construction = relationship("ProductConstruction")
    specifications = relationship(
        "GradeSpecification", back_populates="foam_grade", cascade="all, delete-orphan"
    )
    # Production Method architecture change (2026-08-09, flat model
    # finalized 2026-08-10): the many-to-many counterpart of
    # Machine.foam_grades above. This - NOT production_method_id above -
    # is the authoritative source of which Production Method(s) apply to
    # this PU Material: whichever flat production_method_id values its
    # assigned Machines themselves carry (see
    # helpers.grade_production_methods). A grade may legitimately have
    # machines under more than one method.
    machines = relationship(
        "Machine", secondary=foam_grade_machines, back_populates="foam_grades"
    )


# ---------------------------------------------------------------------------
# 3b. foam_grade_target_properties
#
# Optional additional target specs for a foam grade beyond density/hardness
# (resilience, tensile strength, compression set, ...), reusing the same
# physical_property_definitions master list as physical_property_results so
# names/units stay consistent app-wide. target_value is nullable on purpose:
# a property can be listed as something this grade needs to meet before the
# actual number is known/agreed.
# ---------------------------------------------------------------------------
class FoamGradeTargetProperty(Base):
    __tablename__ = "foam_grade_target_properties"

    id = Column(Integer, primary_key=True)
    foam_grade_id = Column(Integer, ForeignKey("foam_grades.id"), nullable=False)
    property_definition_id = Column(Integer, ForeignKey("physical_property_definitions.id"))
    property_name = Column(String(200), nullable=False)  # snapshot text, auto-filled from the chosen definition
    target_value = Column(Float)
    unit = Column(String(50))
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    foam_grade = relationship("FoamGrade", back_populates="target_properties")


# ---------------------------------------------------------------------------
# 4. recipe_versions
# ---------------------------------------------------------------------------
class RecipeVersion(Base):
    __tablename__ = "recipe_versions"

    id = Column(Integer, primary_key=True)
    foam_grade_id = Column(Integer, ForeignKey("foam_grades.id"), nullable=False)
    version_label = Column(String(100), nullable=False)
    effective_date = Column(Date)
    change_note = Column(Text)
    approval_status = Column(String(50), default="Draft")
    created_by = Column(String(200))
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    # Separate from approval_status on purpose: approval_status tracks the
    # Draft/Review/Approved/Rejected workflow for THIS version; is_active
    # tracks whether it's the version currently in production use for its
    # foam grade. A version can be Approved but no longer active (it was
    # superseded by a later revision) - only one version per foam grade
    # should be active at a time. Enforced in application code (see
    # helpers.activate_recipe_version) AND, since 2026-08-01 (PI3_Gaps_and_
    # Ambiguities.docx finding 1.5), at the database level too: a partial
    # unique index (ux_recipe_version_one_active_per_grade, on
    # (foam_grade_id) WHERE is_active) means a direct SQL write that would
    # leave a grade with two active versions now fails outright rather than
    # silently succeeding. Zero active versions per grade is still allowed.
    is_active = Column(Boolean, default=True)

    # Stoichiometric ratio/index - moved here from ProductionPhase on
    # 2026-08-03. It is a formulation constant that determines the
    # isocyanate php in this recipe, not something set or measured per
    # production run: every run of this recipe version uses the same
    # ratio/index, so it belongs on the recipe, not duplicated on each
    # Setup/Finalized phase snapshot. See ProductionPhase.ratio_index below
    # for the (now-legacy, read-only) per-phase field this replaced.
    ratio_index = Column(Float)

    # --- WP3 additions (2026-08-06). All nullable - existing flexible-foam
    # recipes have none of this and are unaffected.
    #
    # chemistry/method/application/construction: normally the same as the
    # parent FoamGrade's (a recipe is formulated FOR that grade's context),
    # repeated here because a reference/UAT recipe can exist and be
    # evaluated before a grade is finalized around it - see
    # RCP-UAT-DCP-EX1-V1 in the WP3 package, which carries its own context.
    chemistry_id = Column(Integer, ForeignKey("chemistries.id"))
    production_method_id = Column(Integer, ForeignKey("production_methods.id"))
    application_id = Column(Integer, ForeignKey("applications.id"))
    construction_id = Column(Integer, ForeignKey("product_constructions.id"))
    # Free-text description of the formula basis, e.g. "100 parts formulated
    # polyol blend plus 13 parts cyclopentane and 136 parts pMDI" - needed
    # because ratio_index alone doesn't say what's counted in each side of
    # the ratio (see RCP-UAT-DCP-EX1-V1's A:B calculation).
    recipe_basis = Column(Text)
    # Separate from approval_status (the Draft/Review/Approved/Rejected
    # workflow above): validation_status tracks whether this recipe's DATA
    # is real plant data or a locked external/UAT reference, e.g.
    # REFERENCE_LOCKED or APPROVED_UAT_ONLY. A recipe can be
    # "Approved" (workflow-wise) while still being REFERENCE_LOCKED
    # (content-wise) - those are two different questions.
    validation_status = Column(String(50))
    # e.g. "Plant validation required before production use" - shown
    # wherever this recipe is surfaced, so a UAT/reference recipe is never
    # mistaken for something ready to run.
    production_use_rule = Column(Text)
    source_id = Column(Integer, ForeignKey("source_registers.id"))

    # --- WP5 Wave 1 additions (2026-08-07, Converged Joint Implementation
    # Plan section 7.6, workbook sheet 05_Recipe_Header_Fields). All
    # nullable. Deliberately NOT added: RHF-003 "Recipe status" (Draft/
    # Reference/UAT/Trial/Approved/Retired) - this app already carries two
    # status fields covering that ground from WP3 (approval_status for the
    # Draft/Review/Approved/Rejected workflow, validation_status for the
    # reference/UAT-locked-content question), and this project has been
    # burned before by parallel status fields with unclear precedence (see
    # the "pass/fail must be live-computed, never stored" lesson elsewhere
    # in this schema's history) - a third overlapping status column would
    # repeat that mistake. RHF-003's states map onto that existing pair
    # instead. Also deliberately NOT added at the time: RHF-015 "Reference
    # formulation ID" (the target ReferenceFormulation table was WP5 Wave
    # 4's own deliverable, not issued yet then - added below now that
    # Wave 4 exists) and RHF-014 "Approved processing window ID" as a real
    # linked entity (no ProcessingWindow table exists; a free-text
    # reference is recorded instead for now, same "add the real entity
    # later only if a real need shows up" precedent as the Supplier
    # model's own docstring - still deferred, Wave 4's sheets don't cover
    # it either).
    target_ab_mass_ratio = Column(Float)  # RHF-010
    blowing_agent_system = Column(String(300))  # RHF-011, e.g. "Water, Cyclopentane" - free text list
    target_free_rise_density_kgm3 = Column(Float)  # RHF-012
    target_molded_core_density_kgm3 = Column(Float)  # RHF-013
    processing_window_reference = Column(Text)  # RHF-014, text reference (see docstring above)
    plant_validation_status = Column(String(100))  # RHF-016
    safety_review_status = Column(String(100))  # RHF-017
    technical_approver = Column(String(200))  # RHF-018

    # --- WP5 Wave 4 addition (2026-08-07, RHF-015 "Reference formulation
    # ID"). Nullable, optional - most recipes have no public reference at
    # all. "Reference only, never silent copying": this FK records that a
    # recipe was informed by / compared against a locked public parameter
    # summary, it never substitutes for the recipe's own real component
    # rows above.
    reference_formulation_id = Column(Integer, ForeignKey("reference_formulations.id"))  # RHF-015

    foam_grade = relationship("FoamGrade", back_populates="recipe_versions")
    components = relationship("RecipeComponent", back_populates="recipe_version")
    production_runs = relationship("ProductionRun", back_populates="recipe_version")
    chemistry = relationship("Chemistry")
    production_method = relationship("ProductionMethod")
    application = relationship("Application")
    construction = relationship("ProductConstruction")
    source = relationship("SourceRegister")
    reference_formulation = relationship("ReferenceFormulation")


# ---------------------------------------------------------------------------
# Suppliers (master data)
#
# A short, curated list of supplier names so RawMaterial.default_supplier can
# be picked from a dropdown instead of retyped (and mistyped/duplicated -
# "Yiahua" vs "Jiahua") every time. Deliberately just a name + free-text
# notes: this is a lookup list for data entry, not a full vendor-management
# record (no address/contact fields - add those later only if a real need
# shows up).
# ---------------------------------------------------------------------------
class Supplier(Base):
    __tablename__ = "suppliers"
    # Uniqueness is scoped per company, not global - two different customer
    # companies can each have their own "BASF" entry without colliding.
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_supplier_company_name"),)

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    name = Column(String(200), nullable=False)
    notes = Column(Text)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    company = relationship("Company")


# ---------------------------------------------------------------------------
# Raw materials (master data)
# ---------------------------------------------------------------------------
class RawMaterial(Base):
    """Master list of raw materials, so recipes can be built from a dropdown
    instead of retyping (and mistyping) the same material name every time.

    raw_material_name stays on RecipeComponent as the field of record (it is
    what every existing page/report reads), but recipe components now also
    carry raw_material_id so the same material can be traced/reported on
    across every recipe that uses it. A component can still name a material
    that isn't in this master list yet (free-text override), matching the
    same dropdown-plus-custom-entry pattern used for streams and
    conditioning types elsewhere in the app.
    """

    __tablename__ = "raw_materials"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    name = Column(String(200), nullable=False)
    category = Column(String(100))
    default_supplier = Column(String(200))
    cost_per_kg = Column(Float)
    notes = Column(Text)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    # --- WP3 additions (2026-08-06). Nullable, additive: category (free
    # text above) is untouched and still what every existing page reads;
    # category_id is the controlled-vocabulary equivalent (Charlie's RMC-*
    # rows) for rigid-foam data going forward. source_id records where this
    # material's master data (e.g. its TDS) came from.
    category_id = Column(Integer, ForeignKey("raw_material_categories.id"))
    source_id = Column(Integer, ForeignKey("source_registers.id"))

    # --- WP5 Wave 1 additions (2026-08-07, Converged Joint Implementation
    # Plan section 7.6, workbook sheet 04_RM_Reference_Fields RMF-004,
    # RMF-012/013, RMF-014/015, RMF-016/017, RMF-025). All nullable -
    # existing flexible-foam and WP1-4 rigid-foam materials carry none of
    # this and are unaffected. Storage/handling fields are stored directly
    # on RawMaterial (material-level, not lot-level) since the workbook
    # itself lists their Entity_or_Level as "Material" - RawMaterialLot
    # above only gained the two fields the workbook actually scopes to Lot
    # (manufacture_date, country_of_origin).
    manufacturing_site = Column(String(200))  # RMF-004, conditional qualification-scope field
    storage_temp_min_c = Column(Float)  # RMF-012
    storage_temp_max_c = Column(Float)  # RMF-013
    recirculation_requirement = Column(Text)  # RMF-014, e.g. frequency/shear restriction
    agitation_requirement = Column(Text)  # RMF-015, e.g. min/max settings
    moisture_sensitivity_class = Column(String(50))  # RMF-016, controlled class (free text for now)
    flammability_handling_class = Column(String(50))  # RMF-017, controlled class (free text for now)
    technical_validation_note = Column(Text)  # RMF-025, plant-specific validation evidence/limits

    company = relationship("Company")
    material_category = relationship("RawMaterialCategory")
    source = relationship("SourceRegister")


# ---------------------------------------------------------------------------
# 5. recipe_components
# ---------------------------------------------------------------------------
class RecipeComponent(Base):
    __tablename__ = "recipe_components"

    id = Column(Integer, primary_key=True)
    recipe_version_id = Column(Integer, ForeignKey("recipe_versions.id"), nullable=False)
    raw_material_id = Column(Integer, ForeignKey("raw_materials.id"))
    raw_material_name = Column(String(200), nullable=False)
    supplier = Column(String(200))
    php = Column(Float)  # parts per hundred (polyol)
    role_in_formulation = Column(String(200))
    notes = Column(Text)

    # --- WP3 addition (2026-08-06). Nullable: where this component's php
    # figure came from (supplier TDS, internal trial, the WP3 UAT package,
    # ...) - separate from RecipeVersion.source_id, since two components of
    # the same recipe can each trace back to a different document.
    source_id = Column(Integer, ForeignKey("source_registers.id"))

    # --- WP5 Wave 1 additions (2026-08-07, Converged Joint Implementation
    # Plan section 7.6, workbook sheet 06_Recipe_Component_Fields). All
    # nullable except substitution_allowed (RCF-016 specifies a default of
    # FALSE, not merely "no value yet" - a component's substitution
    # permission is a real yes/no control, not an unanswered question).
    # source_location (RCF-019) is deliberately separate from source_id
    # above: source_id says WHICH document/dataset a component's data came
    # from, source_location says WHERE inside it (e.g. "Table 3, Example
    # 2") - source_id without source_location still answers "where did
    # this come from" at the document level, so this is a refinement, not
    # a duplicate.
    stream_assignment = Column(String(50))  # RCF-004, e.g. "A-side" / "B-side" / "Auxiliary"
    dosage_tolerance_lower = Column(Float)  # RCF-006, same basis as php
    dosage_tolerance_upper = Column(Float)  # RCF-007
    reactive_hydrogen_flag = Column(Boolean)  # RCF-008
    reactive_hydrogen_equivalent_source = Column(String(300))  # RCF-009
    nco_equivalent_flag = Column(Boolean)  # RCF-010
    nco_equivalent_source = Column(String(300))  # RCF-011
    premix_group = Column(String(100))  # RCF-012
    addition_sequence = Column(Integer)  # RCF-013
    blend_temperature_window = Column(String(100))  # RCF-014, e.g. "18-24 degC"
    mixing_aging_instruction = Column(Text)  # RCF-015
    substitution_allowed = Column(Boolean, default=False)  # RCF-016
    approved_substitute_group = Column(String(100))  # RCF-017
    provenance_class = Column(String(100))  # RCF-018, e.g. "Public reference" / "Internal UAT" / "Validated plant"
    source_location = Column(String(300))  # RCF-019, see docstring note above
    release_note = Column(Text)  # RCF-020

    recipe_version = relationship("RecipeVersion", back_populates="components")
    raw_material = relationship("RawMaterial")
    source = relationship("SourceRegister")


# ---------------------------------------------------------------------------
# 6. production_runs
# ---------------------------------------------------------------------------
class ProductionRun(Base):
    __tablename__ = "production_runs"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    foam_grade_id = Column(Integer, ForeignKey("foam_grades.id"), nullable=False)
    recipe_version_id = Column(Integer, ForeignKey("recipe_versions.id"), nullable=False)
    run_date = Column(Date)
    batch_reference = Column(String(200))
    block_reference = Column(String(200))
    machine_id = Column(Integer, ForeignKey("machines.id"))  # which foaming line actually ran this
    operator_or_team_reference = Column(String(200))
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    # Production Method architecture change (2026-08-09, flat model
    # finalized 2026-08-10): an IMMUTABLE snapshot, not a live-derived
    # value - deliberately breaking from this app's usual "compute live,
    # never duplicate" discipline (e.g. wp3_conformance's pass/fail). Set
    # once at run creation from the selected Machine's production_method
    # (flat, no hierarchy resolution needed) and never auto-updated
    # afterward. Per Stefan/Charlie's explicit confirmation on JC's
    # impact assessment:
    # this is required so a run's historical method context survives a
    # later correction/reclassification of the Machine master record -
    # if that snapshot behavior were live-derived instead, correcting a
    # Machine's method tag would silently rewrite every past run made on
    # it, which is exactly what Charlie's traceability requirement rules
    # out. Nullable at the DB level only so existing rows can be backfilled
    # by migration; every new row going forward must set it at creation.
    production_method_id = Column(Integer, ForeignKey("production_methods.id"))

    plant = relationship("Plant")
    foam_grade = relationship("FoamGrade")
    machine = relationship("Machine")
    production_method = relationship("ProductionMethod")
    recipe_version = relationship("RecipeVersion", back_populates="production_runs")
    runtime_records = relationship("RuntimeDataRecord", back_populates="production_run")
    # Note: phases/events/lot_uses/samples are deliberately NOT exposed as
    # back-populated collections here. All page code queries those tables
    # directly by production_run_id instead of via a run.phases-style
    # relationship. Adding a bidirectional collection here made ProductionRun
    # (and therefore any FoamGrade/ProductFamily selectbox reachable via
    # RecipeVersion.production_runs) carry a live, non-empty backref
    # collection once rows existed - and Streamlit's widget-state tracking
    # deepcopies selectbox option objects, which crashes on SQLAlchemy
    # InstrumentedList backref collections (AttributeError: '...' object has
    # no attribute '_sa_instance_state'). Keeping these one-directional
    # (see production_run = relationship(...) on each child model below)
    # avoids that entirely.


# ---------------------------------------------------------------------------
# 6b. production_phases (two snapshots: Setup = planned, Finalized = actual)
#
# Each machine-setting field is recorded once per phase row. Because there
# are only two phases, comparing the Setup row to the Finalized row for the
# same production run IS the setpoint-vs-actual comparison - no separate
# _setpoint/_actual column pair needed on top of that.
# ---------------------------------------------------------------------------
class ProductionPhase(Base):
    __tablename__ = "production_phases"

    id = Column(Integer, primary_key=True)
    production_run_id = Column(Integer, ForeignKey("production_runs.id"), nullable=False)
    phase_name = Column(String(50), nullable=False)  # "Setup" or "Finalized"
    phase_start = Column(DateTime)
    phase_end = Column(DateTime)

    # Machine-level settings for this phase.
    mixer_rpm = Column(Float)
    conveyor_speed = Column(Float)  # m/min
    air_injection_rate = Column(Float)  # NL/min or % command
    air_pressure_bar = Column(Float)
    # Controlled vocabulary (FOAMING_MODES) since 2026-08-03 - renamed from
    # "laydown_mode" (incorrect/confusing wording) and converted from free
    # text to LLD / Trough / Traverse. Column name kept as foaming_mode.
    foaming_mode = Column(String(100))
    # Whether the top-flat system is in use for this phase - a distinct
    # yes/no equipment-configuration question, not part of foaming_mode.
    # Nullable (not a plain default-False Boolean): NULL means "not
    # recorded", not "confirmed not in use" - important for legacy rows
    # entered before this field existed.
    top_flat_system_used = Column(Boolean)
    # RETIRED 2026-08-03: replaced by the structured FallplateSectionPosition
    # rows below (section_number/position_mm/angle_deg), which now cover
    # fall-plate geometry directly. Column kept, unread/unwritten by the app,
    # so historical free-text notes already entered are never destroyed -
    # same precedent as RuntimeDataRecord further down this file.
    section_positions_note = Column(Text)
    # Displayed in the UI as "Tunnel width" since 2026-08-05 - "sidewall
    # width" wasn't a term plant-floor users recognized. Column name kept
    # as-is (no migration) - only every user-facing label was changed, via
    # analytics.PHASE_SETTING_LABELS and each page's widget label/caption
    # text.
    sidewall_width_mm = Column(Float)
    # RETIRED FROM THE SETUP TAB 2026-08-03: foam height is a measured
    # outcome of the foaming process, not something planned/configured at
    # Setup - it no longer appears on the Setup form. Still recorded on the
    # Finalized/Runtime Data phase, where it belongs as an observed result.
    foam_height_mm = Column(Float)

    # Ambient plant-floor conditions at the time this phase was recorded -
    # measured, not set. RETIRED FROM THE SETUP TAB 2026-08-03: ambient
    # conditions are environmental, not something planned/configured before
    # a run starts, so they no longer appear on the Setup form - only on
    # Runtime Data (Finalized), which is the actual/observed snapshot.
    ambient_temperature_c = Column(Float)
    ambient_humidity_pct = Column(Float)

    # RETIRED 2026-08-03: ratio/index is a recipe-level formulation constant
    # (it determines the isocyanate php in a recipe), not something that
    # varies per production phase - moved to RecipeVersion.ratio_index (see
    # db.py's RecipeVersion class). This column is no longer read or written
    # by the app; kept only so historical per-phase values already recorded
    # are never destroyed, same precedent as RuntimeDataRecord.
    ratio_index = Column(Float)

    # Length of foam actually produced during this phase, in metres - added
    # 2026-08-05 per user request, Runtime Data (Finalized) only, same
    # precedent as foam_height_mm above (a measured outcome, not a Setup
    # setting - never shown on the Setup form). Optional: when left blank,
    # the Runtime Data tab calculates it instead from conveyor_speed x the
    # phase_start/phase_end duration - see pages/4's _compute_runtime_output().
    # Combined with sidewall_width_mm and foam_height_mm this gives the
    # produced volume (m3), and with the foam grade's target_density, the
    # produced weight (kg).
    meters_produced = Column(Float)

    # Rise time - moved here from the now-retired RuntimeDataRecord table on
    # 2026-08-02, so it lives on the same ProductionPhase row as everything
    # else instead of a separate loose runtime log. See RuntimeDataRecord
    # below. Like foam_height_mm/ambient_temperature_c/ambient_humidity_pct,
    # this is a measured reaction-time OUTCOME, not a configured setting -
    # removed from analytics.PHASE_SETTING_FIELDS on 2026-08-05 for that
    # reason (see that list's docstring), so it no longer appears in the
    # Machine Settings correlation/optimization rankings, only wherever a
    # page genuinely wants the observed value.
    #
    # curing_notes (a free-text "curing/cutting timing notes" box) removed
    # 2026-08-03 per user direction - not a real, reliably-captured field in
    # practice. RuntimeDataRecord.curing_notes below is untouched (already
    # retired/unread by the app, kept only so its historical rows aren't
    # destroyed) - this only removes the live, actively-used copy.
    rise_time = Column(Float)

    notes = Column(Text)
    source_file_reference = Column(String(300))  # "manual entry" or CSV filename
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    production_run = relationship("ProductionRun")


# ---------------------------------------------------------------------------
# 6c. component_stream_readings (per raw-material stream, per Setup/Finalized phase)
# ---------------------------------------------------------------------------
class ComponentStreamReading(Base):
    __tablename__ = "component_stream_readings"

    id = Column(Integer, primary_key=True)
    production_phase_id = Column(Integer, ForeignKey("production_phases.id"), nullable=False)
    stream_name = Column(String(200), nullable=False)  # e.g. Polyol A, TDI 80/20, Water blend, Catalyst
    flow_unit = Column(String(20), default="kg/min")
    flow = Column(Float)
    pump_speed = Column(Float)  # metering pump setting for this stream (RPM/Hz/% depending on OEM) - the
    # control input, distinct from flow (the resulting/measured output). Every chemical line has its own
    # pump, so this lives per stream reading, not as a single Runtime Data field.
    flow_total_qty = Column(Float)  # total delivered this phase - same base unit as flow_unit (kg or L, not per-minute)
    pressure_bar = Column(Float)
    temperature_c = Column(Float)
    calibration_status = Column(String(50))  # Valid / Expired / Failed / Not Verified
    calibration_note = Column(Text)
    notes = Column(Text)
    source_file_reference = Column(String(300))

    phase = relationship("ProductionPhase")


# ---------------------------------------------------------------------------
# 6h. fallplate_section_positions (structured laydown geometry per phase)
#
# Replaces free-text-only section_positions_note with actual per-point
# values, since fall-plate lines commonly have 4-6 independently adjustable
# joints/supports that materially affect density profile and bun squareness.
#
# Field shape follows how a Laader Berg Maxfoam actually defines a fall-plate
# profile (2026-08-03, per user-supplied machine reference): NOT one overall
# plate angle, but a series of vertical positions at the plate joints/
# support points between the trough outlet and the horizontal conveyor -
#
#   Trough outlet (FP start) -> FP1 -> FP2 -> FP3 -> ... -> horizontal conveyor
#
# - each point's height above the conveyor datum (or its raw actuator/
# encoder position, on older machines that don't report a calculated
# height) is the setting actually entered on the machine; because plate
# lengths and horizontal spacing are mechanically fixed, the angle of each
# individual plate section can be derived from the adjacent points' heights
# - so angle_deg is recorded as a calculated-or-recorded value, not the
# primary setting. section_number is this point's position in that
# sequence (1 = closest to the trough outlet); MAXFOAM_FALLPLATE_SECTION_
# COUNTS below gives the expected number of adjustable points for known
# Maxfoam models, purely as an entry-form guide (nothing here enforces it -
# other OEMs/models, or a Maxfoam generation not in that table, just use as
# many rows as the machine actually has).
# ---------------------------------------------------------------------------
class FallplateSectionPosition(Base):
    __tablename__ = "fallplate_section_positions"

    id = Column(Integer, primary_key=True)
    production_phase_id = Column(Integer, ForeignKey("production_phases.id"), nullable=False)
    section_number = Column(Integer, nullable=False)  # point ID along the fall profile, 1 = nearest the trough outlet
    distance_from_trough_mm = Column(Float)  # horizontal distance from the trough outlet to this point
    position_mm = Column(Float)  # vertical height above the conveyor datum (the primary machine setting)
    actuator_position = Column(Float)  # raw actuator/encoder/screw position, for machines that don't report a calculated height
    angle_deg = Column(Float)  # this plate section's angle - calculated from adjacent points' heights, or recorded directly
    notes = Column(Text)

    phase = relationship("ProductionPhase")


# Expected adjustable fall-plate section count per Laader Berg Maxfoam
# model - an entry-form guide only (see FallplateSectionPosition above),
# not a validation rule. Sourced from user-supplied machine reference,
# 2026-08-03; not independently verified against a Laader Berg operating
# manual (none was publicly available), so treat as indicative and correct
# it here if a real HMI/manual says otherwise for a given generation.
MAXFOAM_FALLPLATE_SECTION_COUNTS = {
    "Maxfoam 5010": 4,
    "Maxfoam 5020": 5,
    "Maxfoam 5025": 6,
    "Maxfoam 5035": 6,
}

# Sentinel for "the machine is a Laader Berg but not one of the known Maxfoam
# generations above" - lets the Machine setup form offer a controlled
# dropdown for Laader Berg (so expected_fallplate_section_count reliably
# matches instead of depending on free text) while still allowing any
# generation not yet in MAXFOAM_FALLPLATE_SECTION_COUNTS to be recorded via
# a free-text fallback.
OTHER_LAADER_BERG_MODEL = "Other Laader Berg model (specify below)"
MAXFOAM_MODELS = list(MAXFOAM_FALLPLATE_SECTION_COUNTS.keys()) + [OTHER_LAADER_BERG_MODEL]


def expected_fallplate_section_count(machine):
    """Best-effort lookup of MAXFOAM_FALLPLATE_SECTION_COUNTS for a given
    Machine row (matches if its `model` text contains one of the known
    Maxfoam model keys) - returns None (no guidance available) for any
    other OEM/model/generation, or if machine is None."""
    if machine is None or not machine.model:
        return None
    model_text = machine.model.strip().lower()
    for key, count in MAXFOAM_FALLPLATE_SECTION_COUNTS.items():
        if key.lower() in model_text:
            return count
    return None


# ---------------------------------------------------------------------------
# 6d. production_events (Mandatory-tier: alarms / interventions / grade changes)
# ---------------------------------------------------------------------------
class ProductionEvent(Base):
    __tablename__ = "production_events"

    id = Column(Integer, primary_key=True)
    production_run_id = Column(Integer, ForeignKey("production_runs.id"), nullable=False)
    production_phase_id = Column(Integer, ForeignKey("production_phases.id"))
    event_ts = Column(DateTime, nullable=False)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20))
    description = Column(Text)
    action_taken = Column(Text)
    source_file_reference = Column(String(300))

    production_run = relationship("ProductionRun")
    phase = relationship("ProductionPhase")


# ---------------------------------------------------------------------------
# 6e. raw_material_lot_uses (Mandatory-tier: supplier lot actually consumed)
# ---------------------------------------------------------------------------
class RawMaterialLotUse(Base):
    __tablename__ = "raw_material_lot_uses"

    id = Column(Integer, primary_key=True)
    production_run_id = Column(Integer, ForeignKey("production_runs.id"), nullable=False)
    component_stream_name = Column(String(200), nullable=False)
    supplier_lot_no = Column(String(200), nullable=False)
    notes = Column(Text)
    source_file_reference = Column(String(300))

    # --- WP3 addition (2026-08-06). Nullable: supplier_lot_no (above) stays
    # the field of record every existing page reads/writes; this optionally
    # links the same row to a real RawMaterialLot entity (task #543) when
    # one exists, so a lot's full receipt/CoA data can be traced from here
    # without retyping it.
    raw_material_lot_id = Column(Integer, ForeignKey("raw_material_lots.id"))

    # --- WP4 addition (2026-08-07). This table originally had no
    # quantity/dosage column at all - only which lot of which material was
    # used, never how much - which made it impossible to correlate an
    # ingredient's actual consumption with a rigid-foam production run's
    # outcome (the rigid equivalent of the flexible app's
    # ComponentStreamReading.flow_total_qty). Nullable: a lot-traceability-
    # only entry (lot number recorded without a metered quantity) is still
    # a valid, complete row - see wp3_conformance.rigid_actual_usage_dataframe,
    # which simply skips rows/runs with no mass_kg recorded rather than
    # guessing. A run can draw from more than one supplier lot for the same
    # material, so mass_kg is per LOT USE, not per material-per-run - callers
    # needing a material's total for a run sum across that run's rows.
    mass_kg = Column(Float)

    production_run = relationship("ProductionRun")
    raw_material_lot = relationship("RawMaterialLot")


# ---------------------------------------------------------------------------
# 6f. samples (Mandatory-tier: sample-to-lab traceability backbone)
# ---------------------------------------------------------------------------
class Sample(Base):
    __tablename__ = "samples"

    id = Column(Integer, primary_key=True)
    # Exactly one of these three is set (see SAMPLE_SOURCE_TYPES /
    # sample_source_fk_field() above) - production_run_id for real
    # production-batch QC samples, customer_trial_id / optimization_trial_id
    # for the two independent lab-trial flows added 2026-08-03. All three
    # nullable; enforced at the app level, not a DB CHECK.
    production_run_id = Column(Integer, ForeignKey("production_runs.id"))
    customer_trial_id = Column(Integer, ForeignKey("customer_trials.id"))
    optimization_trial_id = Column(Integer, ForeignKey("optimization_trials.id"))
    sample_ts = Column(DateTime)
    zone_label = Column(String(50))  # Top / Middle / Bottom / Whole sample - N/A (see ZONE_LABELS)
    # cure_age_hours removed 2026-08-03 per user direction (the other
    # "curing time" field that isn't really a thing in practice).
    notes = Column(Text)

    # --- WP3 additions (2026-08-06). All nullable - existing flexible-foam
    # samples use zone_label above and are unaffected. Rigid-foam properties
    # like thermal conductivity are direction- and location-sensitive in a
    # way flexible slabstock sampling never needed to capture.
    location_id = Column(Integer, ForeignKey("locations.id"))
    orientation_id = Column(Integer, ForeignKey("orientations.id"))
    sample_scope = Column(String(50))  # e.g. "Bulk", "Core", "Skin"
    thickness_mm = Column(Float)
    age_hours = Column(Float)  # time between demold/cut and this sample being tested, if tracked

    production_run = relationship("ProductionRun")
    customer_trial = relationship("CustomerTrial")
    optimization_trial = relationship("OptimizationTrial")
    location = relationship("Location")
    orientation = relationship("Orientation")


# ---------------------------------------------------------------------------
# 6g. conditioning_segments - REMOVED 2026-08-04 per user direction ("drop
# conditioning, it is irrelevant, eliminate it from the functionality").
# The conditioning_segments table itself was also dropped from Supabase in
# the same batch (no migration system in this app - tables are created via
# Base.metadata.create_all(), so there was no migration file to delete
# either; the DROP TABLE was run directly). If conditioning history is ever
# wanted again, it would need to be rebuilt from scratch, not restored from
# here - unlike RuntimeDataRecord/MaintenanceAndLicenseRecord elsewhere in
# this file, this model wasn't left in place, since the user explicitly
# asked for the data itself to be gone, not just unused.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 7. runtime_data_records
#
# RETIRED 2026-08-02: the Production Run page's old "Process Phases" +
# standalone "Runtime Data" tabs did overlapping work (line_speed duplicated
# ProductionPhase.conveyor_speed, temperature/pressure text fields duplicated
# structured fields elsewhere), so the page was restructured into two
# dedicated tabs - "Setup" and "Runtime Data" - both backed by ProductionPhase
# (phase_name "Setup"/"Finalized"). The two genuinely unique fields this table
# had, rise_time and curing_notes, moved onto ProductionPhase alongside
# ambient_temperature_c/ambient_humidity_pct (see above). The model/table
# stays here, unread and unwritten by the app, purely so the historical rows
# already in production are never destroyed - same precedent as
# MaintenanceAndLicenseRecord elsewhere in this file.
# ---------------------------------------------------------------------------
class RuntimeDataRecord(Base):
    __tablename__ = "runtime_data_records"

    id = Column(Integer, primary_key=True)
    production_run_id = Column(Integer, ForeignKey("production_runs.id"), nullable=False)
    line_speed = Column(Float)
    pump_speed_or_flow_data = Column(String(200))
    temperature_data = Column(String(200))
    pressure_data = Column(String(200))
    rise_time = Column(Float)
    curing_notes = Column(Text)
    source_file_reference = Column(String(300))
    imported_at = Column(DateTime, default=dt.datetime.utcnow)

    production_run = relationship("ProductionRun", back_populates="runtime_records")


# ---------------------------------------------------------------------------
# 8c. customer_trials (lab trial made for a customer/sales opportunity)
#
# Added 2026-08-03, per user correction: this is NOT a production run with a
# "purpose" flag - it's a genuinely independent flow. A customer trial is
# typically a small lab-scale box made to answer a specific sales
# opportunity, with no machine/process settings behind it at all (no
# ProductionPhase, no Setup/Runtime Data - that structure only exists for a
# real production run). It still targets a foam grade and, usually, a
# formulation - hence foam_grade_id (required, so this flows into the same
# foam-grade-keyed Intelligence pipeline as production data) and
# recipe_version_id (optional - a trial formulation isn't always a saved
# recipe version). Samples, quality test results, and quality issues attach
# here via their own nullable customer_trial_id FK (see Sample,
# PhysicalPropertyResult, QualityObservation below) - never via
# production_run_id, which stays NULL for every row tied to a trial.
# ---------------------------------------------------------------------------
class CustomerTrial(Base):
    __tablename__ = "customer_trials"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    foam_grade_id = Column(Integer, ForeignKey("foam_grades.id"), nullable=False)
    recipe_version_id = Column(Integer, ForeignKey("recipe_versions.id"))

    customer_name = Column(String(200), nullable=False)
    sales_opportunity_reference = Column(String(200))
    requested_by = Column(String(200))
    trial_objective = Column(Text)  # what the customer wants evaluated, and why
    responsible_person = Column(String(200))
    trial_date = Column(Date)
    batch_reference = Column(String(200))  # this trial's own box/batch identifier
    status = Column(String(50), default="Open")  # Open / Pending Closure / Closed

    # closeout
    outcome = Column(Text)
    customer_feedback = Column(Text)
    follow_up_action = Column(Text)
    reviewed_by = Column(String(200))
    date_closed = Column(Date)

    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    plant = relationship("Plant")
    foam_grade = relationship("FoamGrade")
    recipe_version = relationship("RecipeVersion")

    # Closeout enforced app-level only (no DB-level CHECK constraint, to
    # limit migration scope for this batch).
    REQUIRED_CLOSEOUT_FIELDS = ["outcome", "reviewed_by", "date_closed"]

    def missing_closeout_fields(self):
        return [f for f in self.REQUIRED_CLOSEOUT_FIELDS if not getattr(self, f)]

    def can_close(self):
        return len(self.missing_closeout_fields()) == 0


# ---------------------------------------------------------------------------
# 8d. optimization_trials (lab trial stemming from a Performance Improvement
# initiative, related to but independent of the Industrial Intelligence
# section's own analysis - see CustomerTrial above for the shared reasoning
# on why this doesn't go through Production Run).
# ---------------------------------------------------------------------------
class OptimizationTrial(Base):
    __tablename__ = "optimization_trials"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    foam_grade_id = Column(Integer, ForeignKey("foam_grades.id"), nullable=False)
    recipe_version_id = Column(Integer, ForeignKey("recipe_versions.id"))

    improvement_initiative_reference = Column(String(200))
    hypothesis = Column(Text)
    what_changed = Column(Text)
    responsible_person = Column(String(200))
    trial_date = Column(Date)
    batch_reference = Column(String(200))
    status = Column(String(50), default="Open")  # Open / Pending Closure / Closed

    # closeout
    result_against_target = Column(Text)
    conclusion = Column(Text)
    reuse_recommendation = Column(Text)
    reviewed_by = Column(String(200))
    approved_by = Column(String(200))
    date_closed = Column(Date)

    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    plant = relationship("Plant")
    foam_grade = relationship("FoamGrade")
    recipe_version = relationship("RecipeVersion")

    REQUIRED_CLOSEOUT_FIELDS = ["conclusion", "reuse_recommendation", "reviewed_by", "approved_by", "date_closed"]

    def missing_closeout_fields(self):
        return [f for f in self.REQUIRED_CLOSEOUT_FIELDS if not getattr(self, f)]

    def can_close(self):
        return len(self.missing_closeout_fields()) == 0


# ---------------------------------------------------------------------------
# 8b. physical_property_definitions / methods / uoms
#
# Master reference list (84 properties) supplied by the business as
# Flexible_PU_Foam_Physical_Properties_Master.xlsx. Each property can have
# several valid measuring-method standards (ISO/ASTM/etc. are alternatives,
# not interchangeable) and several valid units, hence the separate
# one-to-many reference tables rather than flat columns.
#
# No back-populated collections are defined here (methods/uoms are always
# queried directly by property_definition_id from page code) - see the
# _NoDeepCopyMixin note above and the ProductionRun/ProductionPhase
# precedent: a bidirectional collection here would make every
# PhysicalPropertyDefinition selectbox option carry a live, non-empty
# backref list once methods/uoms exist, which is exactly the shape that
# breaks Streamlit's widget-state deepcopy even with the mixin in place
# for *this* object - simplest to avoid the collection entirely.
# ---------------------------------------------------------------------------
class PhysicalPropertyDefinition(Base):
    __tablename__ = "physical_property_definitions"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    what_it_measures = Column(Text)
    category = Column(String(20))  # Comfort / Technical / Both
    is_common = Column(Boolean, default=False)
    sort_order = Column(Integer)
    # --- WP3 addition (2026-08-06). Nullable: Charlie's PROP-* controlled ID
    # for rigid-foam properties (e.g. "PROP-005" for thermal conductivity).
    # Flexible-foam's existing 84 property rows have none and are unaffected.
    controlled_id = Column(String(50), unique=True)
    # --- WP5 Wave 2 additions (2026-08-07, 09_Property_Master). All nullable -
    # existing rows (flexible + WP3 rigid) are unaffected. "Extend generic
    # property model" per the wave's own JC_Engineering_Action, rather than a
    # separate PropertyMaster table, since PhysicalPropertyDefinition already
    # is that master and every page already queries it by property_definition_id.
    default_uom = Column(String(50))  # e.g. "kg/m3"
    scope = Column(String(300))  # e.g. "Core or finished product"
    allowed_target_type = Column(String(100))  # e.g. "Nominal/Range", "Minimum/Range" - free text, values vary per property
    mandatory_context = Column(Text)  # what must be recorded alongside a result for this property to be interpretable
    source_ids = Column(String(300))  # semicolon-separated SRC-* controlled IDs, e.g. "SRC-ISO-845;SRC-ASTM-D1622"
    phase_status = Column(String(50))  # e.g. "Phase 1", "Phase 1 conditional", "Conditional market-specific"


class PhysicalPropertyMethod(Base):
    __tablename__ = "physical_property_methods"

    id = Column(Integer, primary_key=True)
    # --- WP5 Wave 2 (2026-08-07): relaxed from nullable=False. A handful of
    # WP5 methods (MTH-090 "Internal validated method", MTH-099
    # "Customer-specified method") apply broadly across "Multiple" properties
    # rather than one specific property - existing rows all still set this,
    # so no data migration needed.
    property_definition_id = Column(Integer, ForeignKey("physical_property_definitions.id"))
    method_code = Column(String(300), nullable=False)  # e.g. "ASTM D3574 Test A"
    sort_order = Column(Integer)
    # --- WP3 addition (2026-08-06). Nullable: Charlie's MTH-* controlled ID
    # (e.g. "MTH-016").
    controlled_id = Column(String(50), unique=True)
    # --- WP5 Wave 2 additions (2026-08-07, 10_Test_Methods). All nullable.
    # Mirrors RMA-025/026's "one primary plus multiple secondary" precedent:
    # property_definition_id above stays the single primary property this
    # method row is queried against (unchanged existing pattern - one row per
    # method, e.g. MTH-003 keyed to PROP-007), while applicable_property_ids
    # preserves the workbook's full "this method also covers..." list as
    # traceable text rather than fragmenting one method into several rows.
    standard_reference = Column(String(200))  # e.g. "ISO 844:2026", distinct from the descriptive method_code/name
    method_category = Column(String(100))  # e.g. "Compression", "Thermal", "Fire"
    applicable_property_ids = Column(String(300))  # semicolon-separated PROP-* IDs, full list from the workbook
    implementation_rule = Column(Text)
    source_id = Column(Integer, ForeignKey("source_registers.id"))

    source = relationship("SourceRegister")


class PhysicalPropertyUOM(Base):
    __tablename__ = "physical_property_uoms"

    id = Column(Integer, primary_key=True)
    property_definition_id = Column(Integer, ForeignKey("physical_property_definitions.id"), nullable=False)
    unit_label = Column(String(50), nullable=False)
    sort_order = Column(Integer)
    # --- WP3 addition (2026-08-06). Nullable: optional cross-reference from
    # this per-property unit label to the general UnitOfMeasure master
    # (unit_label stays the field of record every page reads/writes).
    unit_id = Column(Integer, ForeignKey("units_of_measure.id"))

    unit = relationship("UnitOfMeasure")


# ---------------------------------------------------------------------------
# 9. physical_property_results
#
# Keyed to exactly one of a production run, a customer trial, or an
# optimization trial - see SAMPLE_SOURCE_TYPES above.
# ---------------------------------------------------------------------------
class PhysicalPropertyResult(Base):
    __tablename__ = "physical_property_results"

    id = Column(Integer, primary_key=True)
    # Exactly one of these three is set - see SAMPLE_SOURCE_TYPES above.
    production_run_id = Column(Integer, ForeignKey("production_runs.id"))
    customer_trial_id = Column(Integer, ForeignKey("customer_trials.id"))
    optimization_trial_id = Column(Integer, ForeignKey("optimization_trials.id"))
    sample_id = Column(Integer, ForeignKey("samples.id"))  # nullable: older rows predate sample tracking
    property_definition_id = Column(Integer, ForeignKey("physical_property_definitions.id"))  # nullable for legacy/"Other"
    property_method_id = Column(Integer, ForeignKey("physical_property_methods.id"))  # nullable
    property_name = Column(String(200), nullable=False)  # snapshot text, auto-filled from the chosen definition
    target_value = Column(Float)
    actual_value = Column(Float)
    unit = Column(String(50))
    pass_fail = Column(String(20))  # Pass / Fail
    test_method = Column(String(300))  # snapshot text, auto-filled from the chosen method
    method_revision = Column(String(50))
    replicate_no = Column(Integer)
    tested_at = Column(Date)
    notes = Column(Text)

    # --- WP3 additions (2026-08-06). All nullable - existing flexible-foam
    # results are unaffected. Needed because a rigid-foam property result
    # (e.g. thermal conductivity) isn't fully specified by test_method
    # alone - which edition of the standard, under what aging/temperature
    # condition, and at what orientation/location, all change the number.
    method_edition = Column(String(50))  # e.g. "2017" for an ISO/ASTM edition year
    condition_id = Column(Integer, ForeignKey("test_conditions.id"))
    orientation_id = Column(Integer, ForeignKey("orientations.id"))
    location_id = Column(Integer, ForeignKey("locations.id"))
    source_id = Column(Integer, ForeignKey("source_registers.id"))

    # WP6-S09 closure (2026-08-09, per Charlie's technical closure
    # instructions section 3.2): specimen-level thickness for this specific
    # test specimen/result. One parent Sample can feed several lab
    # specimens with different geometry, so dimension belongs here, not
    # (only) on Sample.thickness_mm - that field is now parent-sample
    # context only. See wp3_conformance.validate_result_completeness.
    thickness_mm = Column(Float)

    sample = relationship("Sample")
    production_run = relationship("ProductionRun")
    customer_trial = relationship("CustomerTrial")
    optimization_trial = relationship("OptimizationTrial")
    condition = relationship("TestCondition")
    orientation = relationship("Orientation")
    location = relationship("Location")
    source = relationship("SourceRegister")
    # --- WP6-S09 addition (2026-08-09). property_definition_id has existed
    # on this table since WP3 (2026-08-06) but had no ORM relationship - the
    # FK column already exists, so this is a pure additive mapping, no
    # migration needed. Added so wp3_conformance.validate_result_completeness
    # can look up this result's own PhysicalPropertyDefinition.mandatory_context
    # (Charlie's controlled per-property text describing what must be
    # recorded for that property to be interpretable) and scope its
    # thickness/orientation requirement to properties that actually need it,
    # rather than requiring both for every property regardless - see that
    # function's docstring for the full rationale.
    property_definition = relationship("PhysicalPropertyDefinition")


# ---------------------------------------------------------------------------
# 10. quality_observations  (NOT "defects" - approved terminology)
#
# Keyed to exactly one of a production run, a customer trial, or an
# optimization trial - see SAMPLE_SOURCE_TYPES above.
# ---------------------------------------------------------------------------
class QualityObservation(Base):
    __tablename__ = "quality_observations"

    id = Column(Integer, primary_key=True)
    # Exactly one of these three is set - see SAMPLE_SOURCE_TYPES above.
    production_run_id = Column(Integer, ForeignKey("production_runs.id"))
    customer_trial_id = Column(Integer, ForeignKey("customer_trials.id"))
    optimization_trial_id = Column(Integer, ForeignKey("optimization_trials.id"))
    observation_type = Column(String(200), nullable=False)  # e.g. shrinkage, hardness drift, collapse, splitting
    severity = Column(String(50))  # Low / Medium / High
    frequency = Column(String(50))  # One-off / Recurring
    location_in_block = Column(String(200))
    suspected_cause = Column(Text)
    confidence_level = Column(String(50), default="Unconfirmed")
    product_impact = Column(Text)
    customer_impact = Column(Text)
    notes = Column(Text)
    observed_at = Column(Date)
    # WP5 Wave 3 addition (2026-08-07): optional link to Charlie's
    # controlled QI-* taxonomy, alongside the existing free-text
    # observation_type field (not a replacement - see the QualityIssueType
    # class docstring above for why). Nullable, defaults unset: existing
    # rows and any future free-text-only entry remain valid.
    issue_type_id = Column(Integer, ForeignKey("quality_issue_types.id"))

    production_run = relationship("ProductionRun")
    customer_trial = relationship("CustomerTrial")
    optimization_trial = relationship("OptimizationTrial")
    issue_type = relationship("QualityIssueType")


# ---------------------------------------------------------------------------
# 13. expert_notes
# ---------------------------------------------------------------------------
class ExpertNote(Base):
    __tablename__ = "expert_notes"

    id = Column(Integer, primary_key=True)
    linked_entity_type = Column(String(100), nullable=False)  # e.g. "production_run", "foam_grade"
    linked_entity_id = Column(Integer, nullable=False)
    note_text = Column(Text, nullable=False)
    confidence_level = Column(String(50), default="Unconfirmed")
    author = Column(String(200))
    # OpenAI file id for this note's copy in the PI3/AI vector store (see
    # ai_assistant.py), so an edit/delete here can resync/remove that file
    # instead of leaving a stale copy searchable. Null if PI3/AI wasn't
    # enabled for the relevant plant when the note was saved.
    vector_store_file_id = Column(String(200))
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    # Provenance fields for notes captured via a "Save to Expert Notes"
    # button on a PI3 answer (see helpers.render_save_to_expert_notes_button)
    # rather than typed by hand. Kept on the same table/model as manual notes
    # - deliberately, since both are meant to be searchable side by side and
    # both get pushed into PI3's vector store the same way - but tagged so
    # the Expert Notes screen can show where each one came from and, for
    # PI3-sourced notes, regenerate the original Word report on demand.
    source = Column(String(20), default="Manual")  # "Manual" or "PI3"
    pi3_question = Column(Text)  # the question/label PI3 was answering, null for manual notes
    pi3_tool_log_json = Column(Text)  # JSON-serialized tool_log (free-form Ask PI3 only), null otherwise


# ---------------------------------------------------------------------------
# 15. pi3_ai_connection_settings
# ---------------------------------------------------------------------------
class PI3AIConnectionSetting(Base):
    __tablename__ = "pi3_ai_connection_settings"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    pi3_ai_connectivity_enabled = Column(Boolean, default=False)
    pi3_ai_status = Column(String(50), default="Disabled")
    pi3_ai_annual_fee = Column(Float)
    enabled_by = Column(String(200))
    enabled_at = Column(DateTime)

    plant = relationship("Plant", back_populates="pi3_ai_settings")


# ---------------------------------------------------------------------------
# 17. performance_logs
# ---------------------------------------------------------------------------
# Added 2026-08-02, in response to a reported "app feels slow in general".
# Records one row every time one of analytics.py's three shared, cached
# data-loading functions (run_settings_dataframe, property_results_dataframe,
# actual_usage_dataframe) actually has to hit the database - i.e. a cache
# MISS, not every call. A cache hit never re-executes the function body, so
# it never reaches the logging call either; that's deliberate, not an
# oversight - the whole point of this table is to show how expensive the
# real work is and how often it actually happens, not to log the (much more
# frequent, and near-instant) cache hits too. See analytics._log_performance.
#
# grade_ids stores foam_grade_id as text (comma-joined) rather than a proper
# FK, since that parameter is sometimes a single id and sometimes a list (a
# foam family's pooled grade ids - see analytics._grade_id_list) - this
# table is a lightweight operational log, not a normalized relationship, so
# a denormalized text snapshot is the right amount of structure here.
#
# Logging itself must never be able to break a page: analytics._log_performance
# wraps this insert in a try/except and swallows any failure silently, so a
# logging problem (e.g. this table not yet migrated on some environment)
# degrades to "no data on the Performance admin page", never a crashed
# Intelligence page.
class PerformanceLog(Base):
    __tablename__ = "performance_logs"

    id = Column(Integer, primary_key=True)
    function_name = Column(String(100), nullable=False)
    grade_ids = Column(String(200))  # comma-joined foam_grade_id(s), or NULL for "no grade filter"
    property_name = Column(String(200))
    row_count = Column(Integer)
    duration_ms = Column(Float, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# 17b. page_load_logs
# ---------------------------------------------------------------------------
# Added 2026-08-05, alongside the v2.0 performance audit's caching batch, to
# answer the actual original complaint directly ("a simple screen-build
# takes 15-20 seconds") rather than only the narrower PerformanceLog metric
# above (which only covers 3 shared data-loading functions, and only on a
# cache miss). This instead records the FULL page-script execution time,
# logged once per Streamlit rerun of ANY page - both a fresh navigation and
# every widget-triggered rerun on that same page, since a rerun re-executes
# the whole page script top to bottom under Streamlit's model. Measured
# around app_rigid_foam.py's single pg.run() call (see st.navigation()) - the one
# choke point every page's script runs through - so this fires for every
# page with no change needed to any of the ~27 individual page files.
#
# Much higher volume than PerformanceLog (every rerun, not just cache
# misses), so it gets the same 30-day trim housekeeping - see
# audit_log.log_page_load().
class PageLoadLog(Base):
    __tablename__ = "page_load_logs"

    id = Column(Integer, primary_key=True)
    page_name = Column(String(200), nullable=False)
    duration_ms = Column(Float, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# 16a-16g. Audit / usage / pilot-learning logging package
#
# Added 2026-08-03 for Gate 6, Items 47-56 of the Duroflex pilot readiness
# list (see PI3_Application_Changes_Needed.docx, section 3.2) - before this,
# none of the ten items existed: no login history, no page-usage tracking,
# only one of the six PI3 call sites optionally persisted its Q&A (and only
# if the reviewer chose to save it to Expert Notes), no token/cost or
# response-time capture, no error log, no export/access log, no role-change
# history, no PI3 answer feedback, and no HTC review page. All seven tables
# below are deliberately append-only (application code only ever INSERTs -
# see audit_log.py, the shared module every logging call goes through) and
# all seven use nullable user_id/company_id: a login FAILURE has no user_id
# yet (the username may not even exist), and any of these could in principle
# fire from a legacy/dev session (AUTH_DISABLED) with no real User row
# behind it - a NOT NULL FK would silently break logging in exactly the
# cases most worth capturing (e.g. a failed login attempt).
# ---------------------------------------------------------------------------
class LoginEvent(Base):
    """Item 47 - append-only login/logout history. One row per attempt,
    not per session: a failed login (bad password, deactivated account,
    outside its valid_from/valid_until window - see auth._check_db_login)
    is just as important to retain as a success. username_attempted is
    kept separately from user_id because a failed attempt against a
    username that doesn't exist at all has no User row to link to."""
    __tablename__ = "login_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    username_attempted = Column(String(150))
    company_id = Column(Integer, ForeignKey("companies.id"))
    event_type = Column(String(20), nullable=False)  # login_success / login_failure / logout
    detail = Column(String(300))  # e.g. "invalid password", "account deactivated", "outside valid window"
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User")
    company = relationship("Company")


class PageViewEvent(Base):
    """Item 48 - page/module usage tracking. One row per NAVIGATION to a
    page, not per Streamlit rerun (a rerun fires on every widget
    interaction within the same page - see audit_log.log_page_view_if_new
    for how a duplicate row per click is avoided)."""
    __tablename__ = "page_view_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    page_name = Column(String(200), nullable=False)
    viewed_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User")
    company = relationship("Company")


class PI3InteractionLog(Base):
    """Items 49-51 - every PI3 question and response, across all call
    sites (the 5 fixed-prompt Intelligence-page sections AND every
    free-form 'Ask PI3' box - see ai_assistant.ask_assistant() /
    ask_plant_question(), which both write here directly so no call site
    can be missed), plus OpenAI token usage/estimated cost and response
    time for each call. call_site is a short stable label identifying
    which page/section asked (see ai_assistant.py's callers) - not a
    controlled vocabulary at the DB level, since new call sites will keep
    being added as the app grows."""
    __tablename__ = "pi3_interaction_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    plant_id = Column(Integer, ForeignKey("plants.id"))
    call_site = Column(String(100), nullable=False)
    question_text = Column(Text)
    response_text = Column(Text)
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)
    estimated_cost_usd = Column(Float)
    response_time_ms = Column(Float)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User")
    company = relationship("Company")
    plant = relationship("Plant")


class PI3Feedback(Base):
    """Item 55 - user feedback (thumbs up/down + optional comment) on one
    specific PI3 answer, linked back to the PI3InteractionLog row it's
    reacting to - see helpers.render_pi3_feedback_control."""
    __tablename__ = "pi3_feedback"

    id = Column(Integer, primary_key=True)
    pi3_interaction_log_id = Column(Integer, ForeignKey("pi3_interaction_logs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    rating = Column(String(10), nullable=False)  # 'up' / 'down'
    comment = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    interaction = relationship("PI3InteractionLog")
    user = relationship("User")


class ErrorLog(Base):
    """Item 52 - application errors and failed operations that would
    otherwise only ever reach the user via a transient st.error()/
    st.warning() and then vanish with the next rerun. Not exhaustive of
    every possible exception in the app (that would mean wrapping every
    single try/except) - covers the highest-value points where a real
    failure has historically shown up (PI3 API calls, DB session
    recovery) - see audit_log.log_error()."""
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    page_name = Column(String(200))
    error_message = Column(Text, nullable=False)
    traceback_text = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User")
    company = relationship("Company")


class ExportLog(Base):
    """Item 53 - recipe/report/PI3-answer export and access events.
    Logged via st.download_button's on_click callback (see
    audit_log.log_export and its call sites in pages/21_Report.py and
    helpers.render_pi3_docx_download) - fires exactly when the reviewer
    actually clicks Download, not merely when the button is rendered."""
    __tablename__ = "export_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    export_type = Column(String(100), nullable=False)
    description = Column(String(300))
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    user = relationship("User")
    company = relationship("Company")


class RoleChangeLog(Base):
    """Item 54 - user and role/permission change history. Logs a
    human-readable summary of what changed rather than a full per-field
    old/new diff (the User Roles page access grid alone has one entry per
    page x 3 access levels - a full diff would be a lot of machinery for
    a pilot-scale audit trail); target_type is 'user', 'role', or
    'permission' (page-access grid saves)."""
    __tablename__ = "role_change_logs"

    id = Column(Integer, primary_key=True)
    changed_by_user_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    target_type = Column(String(20), nullable=False)  # user / role / permission
    target_id = Column(Integer)
    target_label = Column(String(200))
    change_summary = Column(Text, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    changed_by = relationship("User")
    company = relationship("Company")


# ===========================================================================
# WP3 - Thermal Conductivity Vertical Slice (Converged Joint Implementation
# Plan, section 7.3; see PI3_Rigid_Foam_Edition_WP3_Technical_Build_Pack_and_
# Gate_2_Specification.docx and the accompanying WP3 Excel package). Added
# 2026-08-06. Every table/column below is new to this rigid_foam schema only
# - nothing here touches the flexible app's public-schema tables.
#
# Charlie's WP1/WP2 deliverables use a controlled-ID vocabulary (CHM-010,
# PM-120, APP-210, PC-140, PROP-005, MTH-016, UOM-002, CTX-THERM-INIT-10C-7D,
# RMC-*, PS-*, LOC-*, ORI-*, SRC-*, ...) throughout. Every lookup table below
# carries a `controlled_id` column so those IDs are real, importable,
# FK-referenceable rows - not free text - which is what lets WP4's
# comparability/analytics logic eventually join on them reliably.
# ===========================================================================


# ---------------------------------------------------------------------------
# WP3a. Controlled-vocabulary lookup tables (task list #542)
#
# All follow the same shape deliberately: id / controlled_id / name /
# description / sort_order. Kept as separate tables per concept (rather than
# one shared "lookup_values" table with a type discriminator) so each can be
# a normal FK target and a normal picker dropdown, matching how every other
# controlled vocabulary in this app already works (Supplier, MACHINE_OEMS-
# style constants, etc.) - not a generic EAV-of-lookups pattern.
# ---------------------------------------------------------------------------
class Chemistry(Base):
    """Charlie's CHM-* vocabulary, e.g. "Polyurethane - Polyol/pMDI",
    "Polyisocyanurate". What a grade/recipe is chemically built from -
    distinct from ProductionMethod (how it's processed)."""

    __tablename__ = "chemistries"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "CHM-010"
    name = Column(String(200), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer)


class ProductionMethod(Base):
    """Charlie's PM-* vocabulary - the controlled, customer-facing
    Production Method identities (PM-100 through PM-700). Drives which
    ProcessSettingDefinition rows apply (method-aware settings, see WP3e
    below) and which equipment hierarchy makes sense for a given
    Machine/ProductionUnit.

    Flat Production Method model (2026-08-10, per Charlie's technical
    completion instruction, superseding the 2026-08-09 parent/child
    hierarchy design): Production Method is one flat level directly
    under Plant - no parent/child levels. The 2026-08-09 batch had
    briefly introduced a self-referencing parent_method_id column (4
    new top-level PM-400/410/420/430 identities with legacy PM-120/130/
    200/210 nested under them as more granular sub-classifications);
    Charlie's explicit instruction the next day reversed that design
    ("This is a flat Production Method level under Plant. Do not create
    parent/child Production Method levels.") and supplied the
    permanent 7-code controlled vocabulary below. parent_method_id was
    dropped from the schema and every row was replaced/remapped - see
    version.py's changelog entry for this batch for the full old-code
    to new-code mapping. Process variants (what the old leaf codes
    captured) now live as method-specific configuration/data beneath
    the relevant flat Production Method, not as separate controlled
    IDs. The 7 permanent codes: PM-100 Discontinuous Factory Foaming,
    PM-200 Continuous Panel & Board Production, PM-300 Field Cavity
    Foaming, PM-400 Spray Foam Application, PM-500 Free-Rise Rigid
    Block Production, PM-600 Pre-Insulated Pipe & Vessel Foaming,
    PM-700 Structural & Composite Rigid Foam Processing.

    maturity_status / is_released (added 2026-08-10, per Charlie's
    "Database Reset and Clean UAT Baseline" instruction, item 5 and
    execution step 6/CR-04): distinguishes Production Methods that
    exist in this controlled master from those actually released and
    available for a real customer to activate. maturity_status is the
    free-text label shown to engineering/Charlie ("Released",
    "Defined / planned", "Placeholder"); is_released is the boolean
    gate the UI actually enforces. At the Phase 1 baseline only PM-100
    has is_released=True; PM-200 through PM-700 are defined/placeholder
    and NOT customer-activatable until a future release decision. The
    platform-owner company (Company.is_platform_owner) is exempt from
    this gate for its own UAT/reference activation - see
    pages/30_Production_Methods.py."""

    __tablename__ = "production_methods"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "PM-100"
    name = Column(String(200), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer)
    maturity_status = Column(String(50))  # "Released" | "Defined / planned" | "Placeholder"
    is_released = Column(Boolean, default=False, nullable=False)


class Application(Base):
    """Charlie's APP-* vocabulary, e.g. "Building Insulation - Wall Panel",
    "Refrigeration", "Pipe Insulation" - the end-use the grade is designed
    for."""

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "APP-210"
    name = Column(String(200), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer)


# ---------------------------------------------------------------------------
# Machine Data Architecture (2026-08-07)
#
# Per Charlie's "PI3_Plant_Edition_Rigid_Foam_Machine_Data_Design_for_JC" -
# a separate initiative from Charlie, outside the Converged Joint
# Implementation Plan's WP0-WP5 numbering, proposing an 8-layer machine
# knowledge architecture: generic Machine Knowledge Master (A) ->
# Configuration Master (B) -> Plant Installed Equipment / Asset (C,
# already the existing Machine table above, extended) -> Operating
# Parameter Register (D) -> Alarm & Fault Register (E) -> Maintenance &
# Calibration Register (F) -> Troubleshooting Case Register (G) ->
# Document Register (H). This pass is schema only (Stefan's direction,
# 2026-08-07): tables/relationships/IDs built and migrated, but the
# open-ended manufacturer/model research and population task (Charlie's
# deliverables 01-02, section 13-14 of his document) is deliberately
# paused pending a separate scope/ownership decision - not started here.
#
# MachineCategory (section 3's 17-row taxonomy) is content Charlie already
# fully specified, not something requiring external research, so it is
# seeded now alongside the schema - same "seed what's already given,
# defer what needs research" split used throughout WP5.
#
# Deliberately a separate vocabulary from ProductionMethod (WP3) - that
# table classifies how a foam GRADE is processed (e.g. "Discontinuous
# Panel (DCP)"); this one classifies equipment TYPE, and covers many
# categories (raw-material storage, utilities, QC/lab, ...) that have no
# ProductionMethod equivalent at all.
# ---------------------------------------------------------------------------
class MachineCategory(Base):
    __tablename__ = "machine_categories"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)
    name = Column(String(200), nullable=False)
    typical_scope = Column(Text)  # e.g. "High-pressure metering units, low-pressure units, component pumps, flow meters, dosing modules."
    sort_order = Column(Integer)


class MachineModel(Base):
    """Layer A - Machine Knowledge Master. Generic, commercially verified
    information for one manufacturer model/variant, independent of any
    customer plant - deliberately NOT company/plant-scoped, same as
    Chemistry/ProductionMethod/RawMaterialCategory above. Population rule
    per Charlie's document: use actual verified commercial models/variants,
    never a generic placeholder row - so this table starts empty in this
    schema-only pass and is populated only once the research task is
    scoped and started."""

    __tablename__ = "machine_models"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "MCH-0001"

    # --- Identity ---
    manufacturer = Column(String(200))
    brand = Column(String(200))
    model = Column(String(200))
    model_variant = Column(String(200))
    machine_category_id = Column(Integer, ForeignKey("machine_categories.id"))
    machine_subcategory = Column(String(200))
    lifecycle_status = Column(String(50))  # current / legacy / discontinued / unknown
    manufacturer_country = Column(String(100))

    # --- Process applicability ---
    # rigid_foam_process was originally typed Boolean in the schema-only pass
    # (2026-08-07) on the assumption it was a yes/no flag. Charlie's Wave 1
    # research package (2026-08-07) actually populates it with a specific
    # process-category description per row (e.g. "Sandwich panels",
    # "Refrigeration appliances", "Spray polyurethane foam") - this is a
    # schema design gap on JC's side, not a Charlie content error, so it is
    # corrected here directly rather than raised as a findings-doc item.
    rigid_foam_process = Column(String(300))
    pur_pir = Column(String(50))
    application = Column(String(200))
    continuous_discontinuous = Column(String(50))
    high_low_pressure = Column(String(50))
    # component_count is String, not Integer: Charlie's Wave 1 research
    # (2026-08-07) includes qualifier values like "2+" (Cannon Afros mixhead
    # rows) alongside clean integers - preserved verbatim rather than
    # truncated to a number. maximum_components stays Integer since every
    # populated value in this wave is a clean whole number.
    component_count = Column(String(20))
    maximum_components = Column(Integer)

    # --- Capacity and operating design ---
    nominal_output_kg_min = Column(Float)
    minimum_output_kg_min = Column(Float)
    maximum_output_kg_min = Column(Float)
    # --- Charlie Wave 1 research import addition (2026-08-07). Some source
    # documents state output as a range or in a unit other than kg/min (e.g.
    # Cannon LN5's "20-140 cc/s total") - these two fields preserve the
    # manufacturer's own stated figure verbatim instead of forcing a lossy
    # conversion into nominal/minimum/maximum_output_kg_min.
    source_output_value = Column(String(100))
    source_output_uom = Column(String(100))
    # mixing_pressure_bar and tank_capacity_l are String, not Float, for the
    # same reason as component_count above: Charlie's Wave 1 data includes
    # ranges ("100-200" bar, "40/60" L for a dual-tank system) that a Float
    # column would either reject or silently truncate.
    mixing_pressure_bar = Column(String(50))
    tank_capacity_l = Column(String(50))
    temperature_range_c = Column(String(100))
    mixing_head_type = Column(String(200))

    # --- Chemistry / blowing agent compatibility ---
    pentane_compatible = Column(Boolean)
    cyclopentane_compatible = Column(Boolean)
    hfo_hcfo_compatible = Column(Boolean)
    water_blown_compatible = Column(Boolean)
    other_blowing_agent_compatibility = Column(Text)

    # --- Controls and connectivity ---
    control_system = Column(String(200))
    plc_type = Column(String(200))
    hmi_type = Column(String(200))
    opc_ua = Column(Boolean)
    modbus = Column(Boolean)
    ethernet_ip = Column(Boolean)
    historical_data_available = Column(Boolean)
    alarm_data_available = Column(Boolean)
    recipe_data_available = Column(Boolean)
    maintenance_data_available = Column(Boolean)

    # --- Regional availability (section 5 - APAC evidence rules) ---
    apac_availability_status = Column(String(100))  # Confirmed | Distributor/Agent | Available on request | Manufacturer support from outside APAC | Historical only | Unknown
    apac_subregions = Column(String(300))  # semicolon list: SEA;China;India;Japan;Korea;Australia/NZ;Other APAC
    thailand_availability = Column(String(100))  # Confirmed local sales/service | Regional support | Import only | Unknown
    apac_service_support = Column(String(100))  # Local service | Regional travelling service | Remote support | Third-party service | Unknown
    spare_parts_apac = Column(String(100))  # Local stock | Regional stock | Factory supply | Unknown
    availability_confidence = Column(String(20))  # High | Medium | Low
    availability_evidence_url = Column(String(500))  # must NOT be an inferred global-presence URL, per Charlie's rule

    # --- PI3 knowledge support ---
    troubleshooting_data_available = Column(Boolean)
    alarm_code_database = Column(Boolean)
    known_failure_modes = Column(Text)
    critical_parameters = Column(Text)
    recommended_maintenance_intervals = Column(Text)
    critical_spare_parts = Column(Text)
    calibration_requirements = Column(Text)
    pi3_data_integration_level = Column(Integer)  # 0-5, see section 11

    # --- Documents ---
    manufacturer_url = Column(String(500))
    product_page_url = Column(String(500))
    tds_url = Column(String(500))
    manual_url = Column(String(500))
    brochure_url = Column(String(500))
    source_verified_date = Column(Date)
    # --- Charlie Wave 1 research import addition (2026-08-07). Free text,
    # not an enum - Charlie's own research package uses varied phrasing
    # here ("Verified", "Verified product; APAC local support unverified",
    # "Verified family names; model-level rigid data incomplete") to convey
    # how complete/certain a given row's research is, distinct from
    # availability_confidence (which is specifically about APAC evidence
    # strength, not general research completeness).
    research_status = Column(Text)
    notes = Column(Text)

    machine_category = relationship("MachineCategory")


class MachineConfiguration(Base):
    """Layer B - Machine Configuration Master. A configuration variant of a
    MachineModel that materially changes process capability (e.g. a
    3-component vs. 2-component option on the same base model) - per
    Charlie's import rule, used instead of duplicating unstructured model
    rows for every option combination."""

    __tablename__ = "machine_configurations"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "MCFG-0001"
    machine_model_id = Column(Integer, ForeignKey("machine_models.id"), nullable=False)
    config_name = Column(String(300), nullable=False)
    config_description = Column(Text)
    differentiating_fields = Column(Text)  # free text: which fields/capabilities this variant changes vs. the base model
    notes = Column(Text)

    machine_model = relationship("MachineModel")


# ---------------------------------------------------------------------------
# WP5 Wave 1. Facers and substrates (Converged Joint Implementation Plan
# section 7.6, workbook sheet 07_Facers_Substrates - 20 controlled facer/
# substrate families: metal facers, paper facers, mineral-fibre facers,
# composite laminates, thermoplastic liners, wood/mineral boards, process
# auxiliaries). key_attributes/primary_risks are carried as the workbook's
# own semicolon-separated descriptive text rather than a further EAV
# breakout - unlike raw-material attributes (RawMaterialAttributeValue,
# above), which are per-material MEASURED values feeding real calculations,
# these are per-SUBSTRATE-TYPE reference guidance ("what to watch for"),
# so the lighter text representation matches their actual use.
# ---------------------------------------------------------------------------
class Substrate(Base):
    """Charlie's SUB-* vocabulary. Linked from ProductConstruction below
    (top/bottom facer) rather than from RecipeComponent - a facer is a
    construction choice for the finished product, not a reactive recipe
    ingredient with a php dosage."""

    __tablename__ = "substrates"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "SUB-001"
    name = Column(String(200), nullable=False)
    substrate_class = Column(String(100))  # e.g. "Metal facer", "Paper facer", "Thermoplastic liner"
    typical_form = Column(String(100))  # e.g. "Coil/sheet", "Roll", "Board"
    key_attributes = Column(Text)  # workbook's semicolon-separated attribute list, kept verbatim
    primary_risks = Column(Text)  # workbook's semicolon-separated risk list, kept verbatim
    phase_status = Column(String(50))
    sort_order = Column(Integer)


class ProductConstruction(Base):
    """Charlie's PC-* vocabulary, e.g. "Metal-faced sandwich panel",
    "Unfaced board", "Sprayed-in-place layer" - the physical form the
    finished product takes.

    top_facer_substrate_id/bottom_facer_substrate_id: WP5 Wave 1 addition
    (2026-08-07) linking a construction to its controlled Substrate rows
    (07_Facers_Substrates) - both nullable, since not every construction
    has two distinct facers (e.g. "Unfaced board" has neither, "Sprayed-
    in-place layer" typically has none at all)."""

    __tablename__ = "product_constructions"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "PC-140"
    name = Column(String(200), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer)
    top_facer_substrate_id = Column(Integer, ForeignKey("substrates.id"))
    bottom_facer_substrate_id = Column(Integer, ForeignKey("substrates.id"))

    top_facer_substrate = relationship("Substrate", foreign_keys=[top_facer_substrate_id])
    bottom_facer_substrate = relationship("Substrate", foreign_keys=[bottom_facer_substrate_id])


class Orientation(Base):
    """Charlie's ORI-* vocabulary for sample/test orientation relative to
    the foam rise direction, e.g. "Parallel to rise", "Perpendicular to
    rise" - thermal conductivity and mechanical properties are directional
    in rigid foam, unlike flexible slabstock, so this has no equivalent in
    the flexible app's schema."""

    __tablename__ = "orientations"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "ORI-010"
    name = Column(String(200), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer)


class Location(Base):
    """Charlie's LOC-* vocabulary for where in the part/panel a sample was
    taken, e.g. "Core", "Skin", "Top face", "Bottom face" - distinct from
    Sample.zone_label (Top/Middle/Bottom/Whole, the flexible-foam bun-slicing
    convention), which is left untouched for flexible-foam use."""

    __tablename__ = "locations"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "LOC-020"
    name = Column(String(200), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer)

    # --- WP5 Wave 3 additions (2026-08-07, 13_Sample_Locations). All
    # nullable. location_category groups entries by kind of position (e.g.
    # "Through-thickness", "Plan position", "Orientation") -
    # coordinate_or_axis is the workbook's own axis/coordinate label (Z,
    # X/Y, Axis, ...); applicable_object is which product form the location
    # applies to (Panel, Block/part, Sandwich panel, ...).
    location_category = Column(String(100))
    coordinate_or_axis = Column(String(100))
    applicable_object = Column(String(200))
    # governance_note: used to record a data-quality correction directly on
    # the row (e.g. a duplicate-ID resolution), per this project's standing
    # practice - see LOC-040/041/042 in the Wave 3 findings document.
    governance_note = Column(Text)


class TestCondition(Base):
    """Charlie's CTX-* vocabulary, e.g. "CTX-THERM-INIT-10C-7D" -
    conditioning/test context (mean temperature, aging duration, etc.) that
    a physical-property result was measured under. Structured fields below
    are populated where the controlled_id encodes them; description always
    carries the full human-readable text regardless."""

    __tablename__ = "test_conditions"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(100), unique=True)  # e.g. "CTX-THERM-INIT-10C-7D"
    name = Column(String(200), nullable=False)
    mean_temperature_c = Column(Float)
    duration_days = Column(Float)
    description = Column(Text)
    sort_order = Column(Integer)
    # --- WP5 Wave 2 additions (2026-08-07, 11_Test_Conditions). All nullable -
    # existing WP3 condition rows (e.g. CTX-THERM-INIT-10C-7D) are unaffected.
    condition_category = Column(String(100))  # e.g. "Conditioning", "Test age", "Orientation", "Specimen scope"
    required_fields = Column(String(300))  # semicolon-separated field names this condition must be recorded with
    data_rule = Column(Text)
    source_ids = Column(String(300))  # semicolon-separated SRC-* controlled IDs


class RawMaterialCategory(Base):
    """Charlie's RMC-* vocabulary, e.g. "Polyol", "Isocyanate", "Blowing
    Agent", "Catalyst", "Surfactant", "Flame Retardant" - a controlled
    replacement for RawMaterial.category's free text (kept as-is for
    flexible-foam/back-compat; see RawMaterial.category_id below)."""

    __tablename__ = "raw_material_categories"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "RMC-030"
    name = Column(String(200), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer)


class UnitOfMeasure(Base):
    """Charlie's UOM-* general unit master, e.g. "W/m*K" (thermal
    conductivity), "kg/m3" (density), "%" (percentage). Deliberately
    separate from PhysicalPropertyUOM (the existing per-property picklist
    further down this file, e.g. only the units valid for "Compression
    set") - this is the flat, general-purpose master those per-property
    rows can optionally reference (see PhysicalPropertyUOM.unit_id below),
    and the general unit FK target for WP3 tables (ProcessSettingDefinition,
    GradeSpecification, ...) that aren't tied to one specific property."""

    __tablename__ = "units_of_measure"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "UOM-002"
    symbol = Column(String(50), nullable=False)  # e.g. "W/m*K"
    name = Column(String(200))  # e.g. "Watts per metre-Kelvin"
    quantity_type = Column(String(100))  # e.g. "Thermal conductivity", "Density"
    sort_order = Column(Integer)
    # --- WP5 Wave 2 additions (2026-08-07, 08_UOM_Additions). Nullable -
    # existing WP2/WP3 UOM rows are unaffected.
    unit_system = Column(String(50))  # e.g. "SI", "SI derived", "Operational"
    data_rule = Column(Text)


class SourceRegister(Base):
    """Charlie's SRC-* provenance vocabulary - where a piece of reference
    data (a UAT recipe, a grade specification limit, a test condition
    definition, ...) actually came from: supplier TDS, internal lab,
    published literature, a UAT/reference dataset, etc. Every WP3 table that
    can trace back to a specific documented source carries a nullable
    source_id FK to this table, so "where did this number come from" is
    always answerable, not just asserted in a docstring."""

    __tablename__ = "source_registers"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "SRC-005"
    source_type = Column(String(100))  # e.g. "Supplier TDS", "Internal Lab", "Literature", "UAT Dataset"
    reference = Column(String(500))  # document/report/dataset name
    retrieved_date = Column(Date)
    description = Column(Text)
    notes = Column(Text)


# ---------------------------------------------------------------------------
# WP3b. Raw materials + lots (task list #543)
# ---------------------------------------------------------------------------
class RawMaterialLot(Base):
    """A specific supplier-lot delivery of a raw material, with its own
    certificate-of-analysis / receipt data - distinct from
    RawMaterialLotUse (which raw_material_lot_uses.supplier_lot_no already
    records as free text per production run). This table is the actual lot
    ENTITY (one row per lot received), so RawMaterialLotUse can optionally
    point at a real lot row via raw_material_lot_id below instead of only
    ever repeating the lot number as text."""

    __tablename__ = "raw_material_lots"

    id = Column(Integer, primary_key=True)
    raw_material_id = Column(Integer, ForeignKey("raw_materials.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"))
    lot_number = Column(String(200), nullable=False)
    coa_reference = Column(String(300))  # certificate of analysis document/filename
    received_date = Column(Date)
    expiry_date = Column(Date)
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    raw_material = relationship("RawMaterial")
    supplier = relationship("Supplier")

    # --- WP5 Wave 1 addition (2026-08-07, Converged Joint Implementation
    # Plan section 7.6, workbook sheet 04_RM_Reference_Fields RMF-010/RMF-011
    # "Country of origin" / "Shelf life... store manufacture and expiry
    # dates on lot"). expiry_date already existed; manufacture_date and
    # country_of_origin are the two lot-level fields the workbook adds that
    # weren't already covered.
    manufacture_date = Column(Date)
    country_of_origin = Column(String(10))  # ISO country code, per RMF-010's governance rule


# ---------------------------------------------------------------------------
# WP5 Wave 1. Raw-material attribute EAV (Converged Joint Implementation
# Plan section 7.6, workbook sheet 03_RM_Attributes - 60 controlled
# attributes: hydroxyl number, NCO content, viscosity, flash point, GWP,
# shelf life, cost per kg, and so on).
#
# Mirrors ProcessSettingDefinition/ProcessParameterValue's existing generic
# EAV pattern rather than inventing a new one: RawMaterial's own fixed
# columns (cost_per_kg, category, ...) stay as they are for backward
# compatibility, and every WP5 attribute - numeric, text, or controlled-ID
# valued - is recorded as one RawMaterialAttributeValue row against a
# RawMaterialAttributeDefinition, the same "definition once, many typed
# values" split PhysicalPropertyDefinition/PhysicalPropertyResult and
# ProcessSettingDefinition/ProcessParameterValue already use elsewhere in
# this schema. A material can carry any subset of the 60 attributes - most
# apply only to some material categories (Applicable_Categories in the
# workbook is descriptive guidance for data entry, not an enforced
# constraint here, matching this schema's existing convention of not
# hard-coding category-to-property restrictions - see GradeSpecification).
# ---------------------------------------------------------------------------
class RawMaterialAttributeDefinition(Base):
    """Charlie's RMA-* attribute dictionary (workbook sheet 03_RM_Attributes).
    default_uom/value_type/primary_source/data_rule are carried as
    descriptive text straight from the workbook rather than re-modeled as
    controlled FKs (e.g. into UnitOfMeasure) - these are guidance for the
    person entering a value, not inputs to a live calculation the way
    GradeSpecification's operator/limit fields are, so the lighter-weight
    text representation is deliberate, not an oversight."""

    __tablename__ = "raw_material_attribute_definitions"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "RMA-001"
    name = Column(String(200), nullable=False)
    default_uom = Column(String(50))
    applicable_categories = Column(String(300))  # descriptive guidance, e.g. "Polyols and polyol blends"
    value_type = Column(String(50))  # e.g. "Numeric", "Text", "Controlled text", "Numeric/Text"
    primary_source = Column(String(200))  # e.g. "TDS/COA", "SDS"
    data_rule = Column(Text)
    sort_order = Column(Integer)


class RawMaterialAttributeValue(Base):
    """One recorded value of one RawMaterialAttributeDefinition, for one
    RawMaterial - the read side of RMF-025's "every technical value carries
    provenance" governance rule (source_id) plus RMF-022's effective-dating
    (so a superseded TDS value isn't silently overwritten, matching
    RecipeVersion's own "new version, not a silent edit" convention)."""

    __tablename__ = "raw_material_attribute_values"

    id = Column(Integer, primary_key=True)
    raw_material_id = Column(Integer, ForeignKey("raw_materials.id"), nullable=False)
    attribute_definition_id = Column(Integer, ForeignKey("raw_material_attribute_definitions.id"), nullable=False)
    value_numeric = Column(Float)
    value_text = Column(String(500))
    unit = Column(String(50))  # snapshot text, auto-filled from the definition's default_uom at entry time
    source_id = Column(Integer, ForeignKey("source_registers.id"))
    effective_date = Column(Date)
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    raw_material = relationship("RawMaterial")
    attribute_definition = relationship("RawMaterialAttributeDefinition")
    source = relationship("SourceRegister")


# ---------------------------------------------------------------------------
# WP5 Wave 1. Raw-material documents and qualification (Converged Joint
# Implementation Plan section 7.6, workbook sheet 04_RM_Reference_Fields
# RMF-006/007/008 document tracking and RMF-018 through RMF-023
# qualification control).
# ---------------------------------------------------------------------------
class RawMaterialDocument(Base):
    """One TDS/SDS/specification revision for a material (RMF-006/007/008).
    file_reference is a filename/link, not a stored binary - this app has
    no document-attachment storage elsewhere either (Sample/PhysicalProperty
    Result don't attach files, just record text references), so the same
    convention is used here rather than introducing a new capability."""

    __tablename__ = "raw_material_documents"

    id = Column(Integer, primary_key=True)
    raw_material_id = Column(Integer, ForeignKey("raw_materials.id"), nullable=False)
    document_type = Column(String(50), nullable=False)  # "TDS" / "SDS" / "Specification"
    revision = Column(String(100))
    revision_date = Column(Date)
    file_reference = Column(String(500))
    source_id = Column(Integer, ForeignKey("source_registers.id"))
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    raw_material = relationship("RawMaterial")
    source = relationship("SourceRegister")


class RawMaterialQualification(Base):
    """Whether/where a material is cleared for use (RMF-018 through
    RMF-023) - "one material can be approved for one recipe while remaining
    blocked for another" per the WP5 handover doc. approved_recipe_scope/
    approved_process_scope are recorded as descriptive text (e.g. a recipe-
    version label or method name) rather than a full many-to-many link
    table for this first wave - a real link table is a reasonable v2 step
    if a page ever needs to hard-block a specific recipe from using a
    specific unqualified material at data-entry time, but nothing in this
    app enforces that yet, so the lighter representation avoids building
    relational structure with no reader. qualification_status is the
    single source of truth for release ("Draft"/"Trial"/"Approved"/
    "Blocked"/"Obsolete") - deliberately its own status, not folded into
    RawMaterial.active (a material can be Approved for one recipe and
    Blocked for another at the same time, which a single active flag on
    RawMaterial itself could never express)."""

    __tablename__ = "raw_material_qualifications"

    id = Column(Integer, primary_key=True)
    raw_material_id = Column(Integer, ForeignKey("raw_materials.id"), nullable=False)
    qualification_status = Column(String(50), default="Draft")  # Draft/Trial/Approved/Blocked/Obsolete
    approved_recipe_scope = Column(Text)
    approved_process_scope = Column(Text)
    substitution_group = Column(String(100))
    effective_date = Column(Date)
    end_date = Column(Date)
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    raw_material = relationship("RawMaterial")


# ---------------------------------------------------------------------------
# WP3c. Equipment / tooling hierarchy (task list #545)
#
# Rigid closed-mold/panel production has an equipment concept with no
# flexible-foam-slabstock equivalent: a metering unit feeds a mixhead, which
# fills a tool (mold), which has one or more cavities, each with its own
# fill point(s) and vent configuration. None of this maps onto the
# flexible app's single "Machine = foaming line" model, so it is new here
# rather than an extension of an existing table (unlike Machine/FoamGrade
# above, which ARE the same underlying concept re-used).
# ---------------------------------------------------------------------------
class ProductionUnit(Base):
    """A higher-level asset grouping above Machine, e.g. "High-pressure
    metering unit #2" - already referenced by Machine.production_unit_id
    above. One production unit can serve more than one Machine row over
    its life (e.g. re-piped to a different line), so this is its own table
    rather than a column on Machine."""

    __tablename__ = "production_units"

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    controlled_id = Column(String(50))
    name = Column(String(200), nullable=False)
    unit_type = Column(String(200))  # e.g. "High-pressure metering unit"
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    plant = relationship("Plant")


class Mixhead(Base):
    __tablename__ = "mixheads"

    id = Column(Integer, primary_key=True)
    production_unit_id = Column(Integer, ForeignKey("production_units.id"), nullable=False)
    name = Column(String(200), nullable=False)
    controlled_id = Column(String(50))
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    production_unit = relationship("ProductionUnit")


class Tool(Base):
    """A mold/tool - fed by a mixhead, contains one or more cavities."""

    __tablename__ = "tools"

    id = Column(Integer, primary_key=True)
    production_unit_id = Column(Integer, ForeignKey("production_units.id"))
    name = Column(String(200), nullable=False)
    controlled_id = Column(String(50))
    tool_type = Column(String(100))  # e.g. "Panel mold", "Block mold"
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    production_unit = relationship("ProductionUnit")


class Cavity(Base):
    __tablename__ = "cavities"

    id = Column(Integer, primary_key=True)
    tool_id = Column(Integer, ForeignKey("tools.id"), nullable=False)
    cavity_number = Column(Integer, nullable=False)
    name = Column(String(200))
    volume_l = Column(Float)
    notes = Column(Text)

    tool = relationship("Tool")


class FillPoint(Base):
    __tablename__ = "fill_points"

    id = Column(Integer, primary_key=True)
    cavity_id = Column(Integer, ForeignKey("cavities.id"), nullable=False)
    fill_point_number = Column(Integer, nullable=False)
    name = Column(String(200))
    notes = Column(Text)

    cavity = relationship("Cavity")


class VentConfiguration(Base):
    __tablename__ = "vent_configurations"

    id = Column(Integer, primary_key=True)
    cavity_id = Column(Integer, ForeignKey("cavities.id"), nullable=False)
    vent_count = Column(Integer)
    vent_type = Column(String(100))
    notes = Column(Text)

    cavity = relationship("Cavity")


class CalibrationRecord(Base):
    """Deliberately simple and NOT polymorphically FK'd to a specific
    equipment table (mixheads/tools/etc.) - equipment_type + equipment_label
    are free text identifying what was calibrated. A metering-pump-level
    calibration_status/calibration_note already exists per stream reading
    (see ComponentStreamReading above, unchanged); this table is for
    equipment-level calibration events (mixhead, tool, scale, ...) that
    aren't tied to one specific production run."""

    __tablename__ = "calibration_records"

    id = Column(Integer, primary_key=True)
    equipment_type = Column(String(100), nullable=False)  # e.g. "Mixhead", "Tool", "Metering pump"
    equipment_label = Column(String(200), nullable=False)  # free-text identifier of the specific asset
    calibration_date = Column(Date)
    next_due_date = Column(Date)
    status = Column(String(50))  # Valid / Expired / Failed / Not Verified
    certificate_reference = Column(String(300))
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)


# ---------------------------------------------------------------------------
# Machine Data Architecture, Layers D-H (2026-08-07)
#
# Continuation of the block above MachineCategory/MachineModel/
# MachineConfiguration (Layers A/B) and the extended Machine table
# (Layer C) - see that comment for full context. These five tables are
# per-asset registers, all linked by Machine.id (Charlie's "Asset_ID"),
# matching this codebase's established EAV/registry pattern (e.g.
# ProcessSettingDefinition/ProcessParameterValue, RawMaterialDocument).
#
# Known, deliberately unresolved overlap: MachineMaintenanceRecord below
# covers everything CalibrationRecord (above) does, plus an asset_id FK
# and richer fields - not merged/migrated in this schema-only pass since
# that's a data decision, not a schema one, and no page reads either
# table yet. Flagged for whoever builds the Machine Maintenance UI.
# ---------------------------------------------------------------------------
class MachineOperatingParameter(Base):
    """Layer D - Operating Parameter Register. One row per monitored or
    controlled parameter per Machine (Asset_ID) - avoids hardcoding machine
    settings into the asset table itself, since parameters vary by machine
    type."""

    __tablename__ = "machine_operating_parameters"

    id = Column(Integer, primary_key=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    parameter_name = Column(String(200), nullable=False)
    parameter_category = Column(String(50))  # Flow | pressure | temperature | ratio | speed | timing | level | alarm | other
    unit = Column(String(50))
    normal_target = Column(Float)
    normal_min = Column(Float)
    normal_max = Column(Float)
    warning_low = Column(Float)
    warning_high = Column(Float)
    design_low = Column(Float)
    design_high = Column(Float)
    source = Column(String(100))  # Manufacturer manual | commissioning | plant standard | empirical plant baseline
    data_tag = Column(String(200))  # PLC / historian tag if available
    readable_by_pi3 = Column(Boolean, default=False)
    # Default False, per Charlie's rule: "Any future write capability
    # requires separate governance" - never set True by import/seed code.
    writable_by_pi3 = Column(Boolean, default=False)
    last_verified = Column(Date)

    machine = relationship("Machine")


class MachineAlarm(Base):
    """Layer E - Alarm and Fault Register. Can be defined at the generic
    model level (machine_model_id set, applies to every asset of that
    model) or at one specific plant asset (machine_id set) - Charlie's
    document allows either "Machine_ID or Asset_ID"."""

    __tablename__ = "machine_alarms"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50))  # e.g. "ALM-0001" - not globally unique since the same alarm code can recur per model
    machine_model_id = Column(Integer, ForeignKey("machine_models.id"))
    machine_id = Column(Integer, ForeignKey("machines.id"))
    alarm_code = Column(String(100), nullable=False)  # exact code shown by machine/PLC
    alarm_text = Column(String(500))
    severity = Column(String(50))  # Info | Warning | Trip | Safety interlock
    immediate_effect = Column(Text)
    likely_causes = Column(Text)
    checks = Column(Text)
    corrective_action = Column(Text)
    reset_logic = Column(Text)
    safety_restriction = Column(Text)
    source = Column(String(300))  # Manual, OEM service record, plant SOP or validated solved case

    machine_model = relationship("MachineModel")
    machine = relationship("Machine")


class MachineMaintenanceRecord(Base):
    """Layer F - Maintenance and Calibration Register. Charlie's Task_Type
    enum includes "calibration" as one task type among several, so
    calibration events belong here rather than a separate table - see the
    module-level note above re: the pre-existing simpler CalibrationRecord."""

    __tablename__ = "machine_maintenance_records"

    id = Column(Integer, primary_key=True)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    task_type = Column(String(50))  # Preventive | corrective | inspection | calibration | replacement
    component = Column(String(200))  # Pump, seal, filter, mixing head, valve, flow meter, sensor, etc.
    interval_note = Column(String(200))  # e.g. "500 hours", "6 months" - hours/cycles/days/months, kept as text since the unit varies per task
    last_completed = Column(Date)
    next_due_date = Column(Date)
    next_due_note = Column(String(200))  # operating-hour/cycle threshold, when the due point isn't a calendar date
    measured_value = Column(Float)
    acceptance_criteria = Column(Text)
    parts_used = Column(Text)
    service_report_link = Column(String(500))
    result = Column(String(50))  # Pass | Monitor | Action required
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    machine = relationship("Machine")


class MachineTroubleshootingCase(Base):
    """Layer G - Troubleshooting Case Register. Links a solved case's
    symptom/machine-state/context to the asset it happened on. process_
    context/formulation_context are free text (case narrative) - recipe_
    version_id/production_run_id are added as real FKs alongside them so a
    case can also be linked relationally to an actual recipe/run when one
    exists, rather than only described in prose."""

    __tablename__ = "machine_troubleshooting_cases"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "CASE-0001"
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=False)
    recipe_version_id = Column(Integer, ForeignKey("recipe_versions.id"))
    production_run_id = Column(Integer, ForeignKey("production_runs.id"))
    symptom = Column(Text)
    machine_state = Column(Text)
    process_context = Column(Text)
    formulation_context = Column(Text)
    root_cause = Column(Text)
    corrective_action = Column(Text)
    verification_evidence = Column(Text)
    outcome = Column(String(100))
    source_id = Column(Integer, ForeignKey("source_registers.id"))
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    machine = relationship("Machine")
    recipe_version = relationship("RecipeVersion")
    production_run = relationship("ProductionRun")
    source = relationship("SourceRegister")


class MachineDocument(Base):
    """Layer H - Document Register. Indexed to Machine_ID (generic model)
    and/or Asset_ID (specific plant machine), per section 10's link-level
    table - e.g. an OEM brochure links to machine_model_id only, while a
    commissioning report links to machine_id only, and an operating manual
    can link to both if the plant's copy differs from the generic one."""

    __tablename__ = "machine_documents"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50))
    machine_model_id = Column(Integer, ForeignKey("machine_models.id"))
    machine_id = Column(Integer, ForeignKey("machines.id"))
    document_type = Column(String(100), nullable=False)  # OEM brochure | Operating manual | Electrical drawings | P&ID | Spare-parts book | PLC/HMI backup | Commissioning report | Calibration record | Service report | Plant SOP | Risk assessment/ATEX | Troubleshooting case report
    file_reference = Column(String(500))
    revision = Column(String(100))
    revision_date = Column(Date)
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    machine_model = relationship("MachineModel")
    machine = relationship("Machine")


# ---------------------------------------------------------------------------
# WP3d. Product grade specification (task list #546)
#
# Generalizes FoamGradeTargetProperty (kept as-is, unchanged, for
# flexible-foam-style simple target+unit specs) with an explicit comparison
# operator, upper/lower limits, and full test context (method/condition/
# orientation/location) - what WP3's Gate 2 conformance check (task #549)
# actually needs to evaluate a rigid-foam grade spec correctly, since
# "meets spec" for thermal conductivity depends on orientation and aging
# condition, not just a single target number.
# ---------------------------------------------------------------------------
GRADE_SPEC_OPERATORS = ["<=", ">=", "=", "between"]


class GradeSpecification(Base):
    __tablename__ = "grade_specifications"

    id = Column(Integer, primary_key=True)
    foam_grade_id = Column(Integer, ForeignKey("foam_grades.id"), nullable=False)
    property_definition_id = Column(Integer, ForeignKey("physical_property_definitions.id"))
    property_method_id = Column(Integer, ForeignKey("physical_property_methods.id"))
    property_name = Column(String(200), nullable=False)  # snapshot text, auto-filled from the chosen definition
    target_operator = Column(String(20), default="<=")  # see GRADE_SPEC_OPERATORS
    target_value = Column(Float)
    lower_limit = Column(Float)  # used when target_operator == "between"
    upper_limit = Column(Float)  # used when target_operator == "between", or as the pass/fail ceiling for "<="
    unit = Column(String(50))
    condition_id = Column(Integer, ForeignKey("test_conditions.id"))
    orientation_id = Column(Integer, ForeignKey("orientations.id"))
    location_id = Column(Integer, ForeignKey("locations.id"))
    source_id = Column(Integer, ForeignKey("source_registers.id"))
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    foam_grade = relationship("FoamGrade", back_populates="specifications")
    condition = relationship("TestCondition")
    orientation = relationship("Orientation")
    location = relationship("Location")
    source = relationship("SourceRegister")


# ---------------------------------------------------------------------------
# WP5 Wave 2 addition (2026-08-07, 12_Grade_Spec_Templates)
#
# A reusable specification *pattern* (property + method + condition(s) +
# orientation + scope), deliberately separate from GradeSpecification (which
# is always tied to one real foam_grade_id and carries an operational limit).
# Per Charlie's own package note - "Templates contain no operational limit
# unless approved" - most template rows here have no lower/upper limit at
# all (limit is filled in only when a real grade adopts the template); the
# few that do (UAT-GST-*) are explicitly-flagged synthetic software-test
# thresholds, not approved product specifications. No foam_grade_id on this
# table by design - turning a template into a real spec means creating a
# GradeSpecification row, not linking to this one.
#
# Condition_IDs in the workbook can list more than one condition at once
# (e.g. "COND-002;COND-020" - both an aging condition and a test-temperature
# condition apply together) - stored as flat semicolon text rather than a
# join table, since nothing in the app yet reads/enforces multi-condition
# combinations (same "abstain, don't over-engineer" call as Wave 1's
# blowing_agent_system/approved_recipe_scope text fields).
# ---------------------------------------------------------------------------
class GradeSpecificationTemplate(Base):
    __tablename__ = "grade_specification_templates"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "GST-001", "UAT-GST-001"
    name = Column(String(300), nullable=False)
    property_definition_id = Column(Integer, ForeignKey("physical_property_definitions.id"))
    target_type = Column(String(50))  # e.g. "MAXIMUM", "MINIMUM", "RANGE", "MAX_ABSOLUTE" - broader vocabulary than GRADE_SPEC_OPERATORS, kept separate deliberately
    nominal_value = Column(Float)
    lower_limit = Column(Float)
    upper_limit = Column(Float)
    unit = Column(String(50))
    property_method_id = Column(Integer, ForeignKey("physical_property_methods.id"))
    condition_ids_text = Column(String(200))  # semicolon-separated CTX/COND controlled IDs - see class docstring
    orientation_id = Column(Integer, ForeignKey("orientations.id"))
    specimen_or_product_scope = Column(String(300))
    status = Column(String(50))  # "Template" or "Synthetic UAT"
    governance_note = Column(Text)
    sort_order = Column(Integer)

    property_definition = relationship("PhysicalPropertyDefinition")
    property_method = relationship("PhysicalPropertyMethod")
    orientation = relationship("Orientation")


# ---------------------------------------------------------------------------
# WP5 Wave 3 additions (2026-08-07, Converged Joint Implementation Plan
# section 7.6, workbook sheets 14_Quality_Issues, 15_Possible_Causes,
# 16_Issue_Cause_Links) - Charlie's controlled troubleshooting taxonomy.
#
# QualityIssueType and PossibleCause are global controlled-vocabulary
# tables, same posture as Chemistry/ProductionMethod/RawMaterialCategory
# above. IssueCauseLink is Charlie's own "many-to-many investigation map"
# (sheet 16's own subtitle: "Links never confirm root cause automatically")
# - it records a *plausible* issue-to-cause hypothesis, not a diagnosis, so
# it carries no confidence/confirmed flag of its own; a real confirmed
# root-cause finding belongs on QualityObservation.suspected_cause (free
# text) or a future dedicated finding record, not here.
#
# QualityObservation gets one new nullable issue_type_id FK to
# QualityIssueType, added deliberately alongside the existing free-text
# observation_type field rather than replacing it - same "extend, don't
# replace" precedent as WP5 Wave 1's RawMaterialAttributeValue duo and
# WP5 Wave 2's PhysicalPropertyMethod.applicable_property_ids. Per this
# wave's own JC_Engineering_Action ("Import and expose in issue/root-cause
# workflows"), only the schema hook is added in this pass - wiring the
# Quality Issue page's picker and the Root-Cause Assistant's use of
# IssueCauseLink is deferred, matching every prior WP5 wave's schema-first,
# UI-later pattern.
# ---------------------------------------------------------------------------
class QualityIssueType(Base):
    """Charlie's QI-* vocabulary, e.g. "Short shot or incomplete fill",
    "Facer delamination"."""

    __tablename__ = "quality_issue_types"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "QI-001"
    name = Column(String(300), nullable=False)
    issue_category = Column(String(100))  # e.g. "Filling/Flow", "Bonding", "Performance"
    definition = Column(Text)
    default_severity = Column(String(50))  # workbook's own text, e.g. "Major/Critical" - not squeezed into a single-value enum
    applicable_methods = Column(String(300))  # e.g. "All Phase 1", "Sandwich panel"
    sort_order = Column(Integer)


class PossibleCause(Base):
    """Charlie's CAUSE-* vocabulary, e.g. "Insufficient shot mass",
    "Excess release agent"."""

    __tablename__ = "possible_causes"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "CAUSE-001"
    name = Column(String(300), nullable=False)
    cause_category = Column(String(100))  # e.g. "Metering", "Formulation", "Substrate"
    definition = Column(Text)
    sort_order = Column(Integer)


class IssueCauseLink(Base):
    """Charlie's IC-* investigation map - one plausible issue-to-cause
    hypothesis. Not a confirmed diagnosis (see class docstring above)."""

    __tablename__ = "issue_cause_links"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "IC-0001"
    issue_type_id = Column(Integer, ForeignKey("quality_issue_types.id"), nullable=False)
    cause_id = Column(Integer, ForeignKey("possible_causes.id"), nullable=False)
    relationship_type = Column(String(100))  # workbook currently uses one value: "Plausible investigation lead"
    governance_rule = Column(Text)  # workbook's own caveat text, e.g. "Hypothesis only; confirm with run data..."

    issue_type = relationship("QualityIssueType")
    cause = relationship("PossibleCause")


# ---------------------------------------------------------------------------
# WP5 Wave 4 additions (2026-08-07, Converged Joint Implementation Plan
# section 7.6, workbook sheets 17_Calculations, 18_Reference_Formulations,
# 19_Ref_Formulation_Components) - "Derived calculations and public
# reference formulation summaries".
#
# Wave-boundary note: 01_Wave_Control's own Primary_Sheets for Wave 4 says
# "16-18", but sheet 16 is 16_Issue_Cause_Links (Wave 3's own hypothesis-
# link sheet, already imported in that wave) and Wave 4's actual content
# runs 17-19 (Calculations, Reference_Formulations, and their components).
# Same off-by-one pattern already flagged to Charlie for the Wave 2/Wave 3
# boundary (sheet 13) - raised again here, see the Wave 4 findings doc.
#
# CalculationDefinition is a controlled formula-specification library
# (Charlie's CALC-* vocabulary) - stored as data (formula text, required
# inputs, validation rule), not compiled/executed by this pass. Per this
# wave's own JC_Engineering_Action ("Implement calculations and
# reference-lock controls"), actual live computation of any CALC-* formula
# against real production data is deferred, matching every prior WP5
# wave's schema-first, UI-later pattern - there is no page or analytics
# function yet that evaluates these formulas.
#
# ReferenceFormulation and ReferenceFormulationComponent hold Charlie's
# locked, provenance-controlled public patent parameter summaries (RF-*),
# structured per the Converged Plan's section 8 reference-formulation
# policy (source identity, formulation context, parameter summary,
# status, plant-recipe separation) - never the plant's own recipe data.
# chemistry is stored as free text (the sheet's own "PUR"/"PIR" values)
# rather than a Chemistry FK, because the frozen WP2 Implementation Slice
# only ever controlled PUR (CHM-010) - PIR has no controlled Chemistry row
# yet, and force-mapping half the rows would misrepresent the other half.
# source_id links to the real SourceRegister row for each patent (added
# below) - unlike the Machine Data batch's Source_Register sheet, these
# Source_IDs are genuinely cross-referenced by real rows here, so
# importing them is real traceability, not a disconnected bibliography.
#
# RecipeVersion.reference_formulation_id closes RHF-015 ("Reference
# formulation ID... Reference only, never silent copying"), explicitly
# deferred in Wave 1's own changelog pending this table's existence.
# RHF-014 ("Approved processing window ID") remains deferred as free text
# - no ProcessingWindow entity is part of this wave's sheets either.
# ---------------------------------------------------------------------------
class CalculationDefinition(Base):
    """Charlie's CALC-* formula-specification library, e.g. "A:B mass
    ratio", "Actual isocyanate index". Data only - no engine in this app
    evaluates these formulas yet (see module note above)."""

    __tablename__ = "calculation_definitions"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "CALC-001"
    name = Column(String(300), nullable=False)
    formula_specification = Column(Text)  # e.g. "A_mass / B_mass"
    output_uom = Column(String(100))  # workbook's own text, e.g. "kg/m3", "%", "ratio" - not FK'd to UnitOfMeasure since several values ("ratio", "index", "count/basis") aren't real units
    required_inputs = Column(Text)  # semicolon-separated list, workbook's own format
    validation_rule = Column(Text)
    phase_status = Column(String(50))  # e.g. "Phase 1", "WP5"
    sort_order = Column(Integer)


class ReferenceFormulation(Base):
    """Charlie's RF-* locked public parameter summaries (patent/literature
    examples), never a plant recipe. See module note above for the
    provenance and separation rules.

    Reconciliation note (2026-08-08): this table was originally seeded from
    the WP5 workbook's own smaller 18_Reference_Formulations sheet (6 rows,
    free-text chemistry/context only). Charlie subsequently issued a
    dedicated, more heavily linked package -
    PI3_Rigid_Foam_Reference_Formulations_10_MASTER_LINKED.xlsx (10 rows,
    43 columns) - per its own Import_Guide sheet, "the single source of
    truth" for reference formulations, superseding the original 6. The
    original 6 rows (and their components) were deleted and replaced with
    these 10 (safe: nothing referenced them yet - RecipeVersion.
    reference_formulation_id was null everywhere per Wave 4's own QA).
    Every column below chemistry_id onward is new in this reconciliation;
    the columns above it (chemistry_label, production_or_test_context,
    application_context, target_index, blowing_system, source_location,
    record_status, plant_use_rule) are the original Wave 4 fields, kept and
    re-populated from the new package's richer data for continuity (extend,
    don't replace - same pattern used throughout WP5).

    basis_uom_id / water_uom_id / blowing_agent_uom_id: the new package's
    own 98_Controlled_Lookups sheet declares UOM-023 ("php") and UOM-024
    ("wt%"), but WP1's own 10_Units_Bases master already assigns those exact
    units to UOM-030 and UOM-031 - a cross-workbook numbering collision
    (flagged to Charlie separately). Per Stefan's decision, WP1's UOM-030/
    031 are treated as canonical and the package's UOM-023/024 references
    are mapped onto them at import time rather than loaded as a second,
    parallel pair of rows.
    """

    __tablename__ = "reference_formulations"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "RF-001"
    name = Column(String(300), nullable=False)
    chemistry_label = Column(String(50))  # free text "PUR"/"PIR" - see module note
    production_or_test_context = Column(Text)
    application_context = Column(Text)
    target_index = Column(Float)  # nullable - not every reported example states an index
    blowing_system = Column(String(300))
    source_id = Column(Integer, ForeignKey("source_registers.id"))
    source_location = Column(String(300))  # e.g. "Example 21C"
    record_status = Column(String(100))  # e.g. "Locked public parameter summary"
    plant_use_rule = Column(Text)  # e.g. "Reference only; local material matching, safety review and validation required"

    # CR-03 addition (2026-08-10, Recipe Consolidation and Pending Review
    # Status): a real, mutable Approval Status - same controlled vocabulary
    # as RecipeVersion.approval_status (db.APPROVAL_STATUSES) - so every row
    # here can be shown, filtered and transitioned on the consolidated
    # Recipes page instead of the now-removed standalone Reference
    # Formulations page. Backfilled to "Pending Review" for all 18
    # pre-existing rows (10 RF-* patent examples + 8 RFREF-* exact
    # scientific reference recipes) via the cr03_reference_formulation_
    # approval_status migration. Deliberately NOT added to
    # ReferenceFormulationFamily (RFFAM-*) - CR-03 rule 7 keeps research
    # formulation families out of the Recipe/approval workflow entirely.
    approval_status = Column(String(50))
    sort_order = Column(Integer)

    # --- Reconciliation additions (2026-08-08, Reference_Formulations_10 package) ---
    chemistry_id = Column(Integer, ForeignKey("chemistries.id"))
    production_method_id = Column(Integer, ForeignKey("production_methods.id"))
    method_phase = Column(String(50))  # e.g. "Phase 1", "Future"
    application_id = Column(Integer, ForeignKey("applications.id"))
    construction_id = Column(Integer, ForeignKey("product_constructions.id"))
    formulation_basis = Column(String(300))  # e.g. "100 parts polyol"
    basis_uom_id = Column(Integer, ForeignKey("units_of_measure.id"))
    reported_isocyanate_index = Column(Float)
    index_basis = Column(Text)
    reported_ab_mass_ratio = Column(Float)
    water_level = Column(Float)
    water_uom_id = Column(Integer, ForeignKey("units_of_measure.id"))
    physical_blowing_agent_description = Column(String(300))
    physical_blowing_agent_level = Column(Float)
    blowing_agent_uom_id = Column(Integer, ForeignKey("units_of_measure.id"))
    reported_free_rise_density_kg_m3 = Column(Float)
    reported_minimum_fill_density_kg_m3 = Column(Float)
    reported_molded_core_density_kg_m3 = Column(Float)
    reported_cream_time_s = Column(Float)
    reported_gel_or_string_time_s = Column(Float)
    reported_rise_time_s = Column(Float)
    reported_demold_time_min = Column(Float)
    reported_mold_temp_c = Column(Float)
    reported_thermal_conductivity_mw_mk = Column(Float)
    reported_open_cell_content_pct = Column(Float)
    reference_status = Column(String(100))  # e.g. "Locked reference"
    validation_status = Column(String(100))  # e.g. "Pending technical validation"
    local_rm_matching_status = Column(String(100))
    safety_review_status = Column(String(100))
    regulatory_review_status = Column(String(100))
    release_to_plant_recipe = Column(Boolean, default=False)
    source_class = Column(String(100))  # e.g. "Public patent", "Supplier technical presentation"
    source_number = Column(String(100))  # e.g. "US7183330B2"
    source_organisation = Column(String(200))
    source_url = Column(String(500))
    technical_notes = Column(Text)

    source = relationship("SourceRegister")
    chemistry = relationship("Chemistry")
    production_method = relationship("ProductionMethod")
    application = relationship("Application")
    construction = relationship("ProductConstruction")
    basis_uom = relationship("UnitOfMeasure", foreign_keys=[basis_uom_id])
    water_uom = relationship("UnitOfMeasure", foreign_keys=[water_uom_id])
    blowing_agent_uom = relationship("UnitOfMeasure", foreign_keys=[blowing_agent_uom_id])
    # Added 2026-08-09 (production hotfix): pages/29_Reference_Formulations.py
    # reads rf.components to list each formulation's ingredient lines - this
    # relationship was missing entirely (only the reverse
    # ReferenceFormulationComponent.reference_formulation existed), causing an
    # AttributeError on every reference-formulation detail view. FK already
    # exists (ReferenceFormulationComponent.reference_formulation_id); this is
    # additive ORM wiring only, no schema/data change.
    components = relationship(
        "ReferenceFormulationComponent",
        order_by="ReferenceFormulationComponent.sequence",
        back_populates="reference_formulation",
    )
    # Added 2026-08-09 (Post-G5 Reference Data Enrichment, Charlie/JC scientific
    # reference package): the 8 new RFREF-* rows carry a much richer, variable
    # per-recipe property set (up to 13 performance rows and 9 process steps for
    # a single recipe) than ReferenceFormulation's own fixed reported_* columns
    # can hold - those columns still carry one "headline" value per property
    # where a single clean value exists (e.g. reported_free_rise_density_kg_m3),
    # but the full granular dataset (uncertainty, method, test condition,
    # orientation, every process step) lives in these two EAV-style child
    # tables instead of forcing new fixed columns for each one-off property.
    performance_results = relationship(
        "ReferenceFormulationPerformanceResult",
        order_by="ReferenceFormulationPerformanceResult.sequence",
        back_populates="reference_formulation",
    )
    processing_notes = relationship(
        "ReferenceFormulationProcessingNote",
        order_by="ReferenceFormulationProcessingNote.step_no",
        back_populates="reference_formulation",
    )


class ReferenceFormulationComponent(Base):
    """One structured ingredient line extracted from a public reference
    formulation - patent text itself is not reproduced, only the
    structured values (see sheet 19's own subtitle).

    Reconciliation note (2026-08-08): extended for the
    Reference_Formulations_10 package's own 10A_Reference_Components sheet
    (100 rows, 16 columns), which - per its own subtitle and the Raw
    Materials Master's "Recipe linkage rule" - links every ingredient line
    to a real Material_ID rather than the free-text-only source_component_term
    used by the original Wave 4 import. material_id is therefore mandatory
    for this reconciled batch (100% exact-link, verified: 0 missing links
    across all 100 rows, see 23_Master_Link_Check/99_QC in that package).
    """

    __tablename__ = "reference_formulation_components"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "RF-001-C01"
    reference_formulation_id = Column(Integer, ForeignKey("reference_formulations.id"), nullable=False)
    sequence = Column(Integer)
    source_component_term = Column(String(300))  # e.g. "Polyol 2", "pMDI"
    controlled_category_or_role = Column(String(200))  # e.g. "Rigid polyol", "Isocyanate", "Physical blowing agent"
    reported_amount = Column(Float)
    amount_basis = Column(String(100))  # e.g. "parts", "wt% total raw material"
    source_id = Column(Integer, ForeignKey("source_registers.id"))
    source_location = Column(String(300))
    interpretation_note = Column(Text)

    # --- Reconciliation additions (2026-08-08, 10A_Reference_Components) ---
    material_id = Column(Integer, ForeignKey("raw_material_catalog_entries.id"))
    material_name = Column(String(300))  # workbook's own Material_Name, kept for direct display without a join
    component_side = Column(String(50))  # e.g. "Polyol Blend Component", "Isocyanate Component"
    amount_text = Column(String(100))  # rare rows where amount is reported as text, not a number
    uom_id = Column(Integer, ForeignKey("units_of_measure.id"))  # UOM-023/024 mapped to canonical UOM-030/031, see ReferenceFormulation note
    dosage_basis = Column(String(200))  # e.g. "Per 100 parts polyol"
    reported_wt_pct = Column(Float)
    oh_number_mgkoh_g = Column(Float)
    master_link_status = Column(String(50))  # e.g. "EXACT MASTER LINK"
    notes = Column(Text)

    reference_formulation = relationship("ReferenceFormulation", back_populates="components")


class ReferenceFormulationPerformanceResult(Base):
    """One reported performance/property value for an exact scientific
    reference formulation (RFREF-*) - Post-G5 Reference Data Enrichment,
    2026-08-09, from Charlie/JC's scientific reference package
    (04_Performance_Data sheet, 53 rows across RFREF-003..008).

    EAV by design: the source properties vary per recipe (some report only
    reactivity times, others add cell-structure and compressive data), so a
    fixed-column model would need a new column for every one-off property.
    property_definition_id/method_id/test_condition_id/orientation_id link to
    the existing WP2/WP5 controlled masters where a clean match exists;
    property_text/method_text/test_condition_text/orientation_text always
    hold the exact source term regardless, so nothing is lost when a
    controlled link isn't available (see PROP-057 "Start time", added for
    this batch as a standard sibling of Cream/Gel/Rise/Tack-free time).
    reported_uom is free text on purpose - preserves the exact source unit
    (e.g. mW/(m*K) vs W/(m*K) for thermal conductivity) rather than forcing
    every row through a single UOM master conversion.
    """

    __tablename__ = "reference_formulation_performance_results"

    id = Column(Integer, primary_key=True)
    reference_formulation_id = Column(Integer, ForeignKey("reference_formulations.id"), nullable=False)
    sequence = Column(Integer)
    record_type = Column(String)  # e.g. "Exact scientific reference recipe"
    property_definition_id = Column(Integer, ForeignKey("physical_property_definitions.id"))
    property_text = Column(String, nullable=False)  # exact source property name
    result_value = Column(Float)
    result_value_text = Column(String)  # non-numeric results, if ever needed
    uncertainty_or_range = Column(String)  # e.g. "+/- 2"
    reported_uom = Column(String)
    method_id = Column(Integer, ForeignKey("physical_property_methods.id"))
    method_text = Column(String)  # e.g. "ISO 8301"
    test_condition_id = Column(Integer, ForeignKey("test_conditions.id"))
    test_condition_text = Column(String)
    orientation_id = Column(Integer, ForeignKey("orientations.id"))
    orientation_text = Column(String)  # e.g. "Rise direction Z" - kept verbatim even when orientation_id maps to a close but not identical controlled term
    sample_age = Column(String)
    source_id = Column(Integer, ForeignKey("source_registers.id"))
    source_url = Column(String)
    notes = Column(Text)

    reference_formulation = relationship("ReferenceFormulation", back_populates="performance_results")
    property_definition = relationship("PhysicalPropertyDefinition")
    method = relationship("PhysicalPropertyMethod")
    test_condition = relationship("TestCondition")
    orientation = relationship("Orientation")
    source = relationship("SourceRegister")


class ReferenceFormulationProcessingNote(Base):
    """One reported process step/parameter for an exact scientific reference
    formulation (RFREF-*) - Post-G5 Reference Data Enrichment, 2026-08-09,
    from Charlie/JC's scientific reference package (03_Processing_Data
    sheet, 40 rows across all 8 RFREF-001..008).

    value_text always holds the exact source value (including ranges like
    "30-60" or qualitative text like "Open-mold free rise"); value_numeric is
    populated only when the source value is a clean number, for any future
    calculation/filtering use without re-parsing text.
    """

    __tablename__ = "reference_formulation_processing_notes"

    id = Column(Integer, primary_key=True)
    reference_formulation_id = Column(Integer, ForeignKey("reference_formulations.id"), nullable=False)
    step_no = Column(Integer)
    process_phase = Column(String)  # e.g. "Metering and dispensing"
    parameter = Column(String, nullable=False)  # e.g. "Final mix time after pMDI addition"
    value_text = Column(String)
    value_numeric = Column(Float)
    unit = Column(String)
    condition_or_context = Column(Text)
    source_id = Column(Integer, ForeignKey("source_registers.id"))
    source_url = Column(String)
    notes = Column(Text)

    reference_formulation = relationship("ReferenceFormulation", back_populates="processing_notes")
    source = relationship("SourceRegister")


class ReferenceFormulationFamily(Base):
    """A research formulation family/optimization result (RFFAM-*) -
    deliberately a separate table from ReferenceFormulation, per Charlie's
    explicit governance instruction: exact scientific reference recipes and
    research formulation families must never be confused with each other or
    with a plant recipe. A family reports a parameter range/optimization
    result across an experimental design, not one exact recipe - see
    record_status ("RESEARCH FAMILY ONLY") and import_action, both always
    more restrictive than a locked exact reference.

    Post-G5 Reference Data Enrichment, 2026-08-09: 2 rows (RFFAM-001/002)
    from Charlie/JC's scientific reference package (06_Formulation_Families
    sheet), a PIR sandwich-panel optimization study. Ingredient composition
    is captured as fixed pbw columns (mirroring the source sheet exactly)
    rather than a child components table, since every row in this study
    reports the same fixed set of components (low/high-functionality polyol,
    TEP, silicone surfactant, water, blowing catalyst, trimerization
    catalyst, n-pentane, pMDI) - unlike RFREF-*'s variable ingredient lists,
    which do need a real child table.
    """

    __tablename__ = "reference_formulation_families"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True, nullable=False)  # e.g. "RFFAM-001"
    variant_name = Column(String)
    record_type = Column(String)  # e.g. "Scientific formulation family / optimization result"
    rigid_foam_type = Column(String)
    chemistry_id = Column(Integer, ForeignKey("chemistries.id"))
    isocyanate_index = Column(Float)
    low_functionality_polyol_pbw = Column(Float)
    high_functionality_polyol_pbw = Column(Float)
    hf_polyol_value_status = Column(String)  # e.g. "Derived by balance to 100 total polyol"
    tep_pbw = Column(Float)
    silicone_surfactant_pbw = Column(Float)
    water_pbw = Column(Float)
    blowing_catalyst_pbw = Column(Float)
    trimerization_catalyst_pbw = Column(Float)
    n_pentane_pbw = Column(Float)
    pmdi_status = Column(String)
    pmdi_study_range_pbw = Column(String)  # e.g. "230-255" - a range, not one value
    experimental_method = Column(String)
    intended_production_method_id = Column(Integer, ForeignKey("production_methods.id"))
    application_id = Column(Integer, ForeignKey("applications.id"))
    intended_construction_id = Column(Integer, ForeignKey("product_constructions.id"))
    study_optimized_performance = Column(Text)
    record_status = Column(String)  # e.g. "RESEARCH FAMILY ONLY"
    import_action = Column(String)  # e.g. "Reference Library only; do not convert directly to plant Recipe Version"
    source_id = Column(Integer, ForeignKey("source_registers.id"))
    source_url = Column(String)
    mapping_confidence = Column(String)
    caution = Column(Text)
    notes = Column(Text)
    sort_order = Column(Integer)

    chemistry = relationship("Chemistry")
    intended_production_method = relationship("ProductionMethod")
    application = relationship("Application")
    intended_construction = relationship("ProductConstruction")
    source = relationship("SourceRegister")


class RawMaterialCatalogEntry(Base):
    """Layer analogous to MachineModel above, but for raw materials: a
    generic, commercially-verified research catalog of supplier
    products - deliberately NOT company/plant-scoped, and deliberately
    distinct from the existing plant-scoped RawMaterial table above (that
    one is the plant's own already-approved material list built from a
    dropdown as recipes are entered; this one is Charlie's broader
    "commercial-grade knowledge master... broader than an approved vendor
    list", per the source workbook's own Import_Guide sheet).

    Added 2026-08-08 to hold
    PI3_Plant_Edition_Rigid_Foam_Raw_Materials_Master_v2_MASTER_LINKED.xlsx's
    Rigid_Raw_Materials sheet (151 rows) - the single source of truth the
    Reference_Formulations_10 package's own ingredient lines (see
    ReferenceFormulationComponent.material_id above) link to by Material_ID.
    A commercial product listed here remains unapproved for plant use until
    "TDS/SDS review, formulation compatibility, plant trial and procurement
    qualification are completed" (Import_Guide's own "Plant approval" rule)
    - this table is a research/reference catalog, not an approved-vendor
    list, matching MachineModel's own separation from the plant's live
    equipment records.

    generic_class_id resolves the workbook's own PI3_Generic_Class_ID field
    to a real FK against the existing RawMaterialCategory (RMC-*) table -
    confirmed a genuine, resolvable link (all 17 distinct class codes used
    across the 151 rows already exist among the 30 RMC-* rows loaded back
    in WP3), not a new controlled-vocabulary gap.
    """

    __tablename__ = "raw_material_catalog_entries"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # Material_ID, e.g. "RF-ISO-001"

    # --- Identity ---
    category = Column(String(100))
    subcategory = Column(String(200))
    supplier = Column(String(200))
    brand = Column(String(200))
    product_name = Column(String(300))
    chemistry_or_type = Column(String(300))
    primary_function = Column(String(300))
    rigid_foam_applications = Column(Text)
    pur_pir = Column(String(50))  # free text "PUR"/"PIR"/blank

    # --- APAC sourcing evidence ---
    apac_availability_status = Column(String(300))
    apac_subregions = Column(String(300))
    thailand_availability = Column(String(300))
    availability_confidence = Column(String(100))
    availability_evidence_url = Column(String(500))
    local_stock_or_lead_time = Column(String(300))

    # --- Technical properties ---
    oh_number_mgkoh_g = Column(Float)
    functionality = Column(Float)
    nco_content_pct = Column(Float)
    viscosity_mpa_s_25c = Column(Float)
    typical_use_note = Column(Text)

    # --- Cost (indicative, category-level budgeting only - see Import_Guide) ---
    indicative_cost_low_usd_kg = Column(Float)
    indicative_cost_high_usd_kg = Column(Float)
    indicative_cost_mid_usd_kg = Column(Float)
    cost_basis = Column(String(200))
    cost_date = Column(String(50))

    # --- Verification / provenance ---
    product_verification_status = Column(String(200))
    product_source_url = Column(String(500))
    price_source_url = Column(String(500))
    pi3_notes = Column(Text)

    # --- PI3 alignment ---
    generic_class_id = Column(Integer, ForeignKey("raw_material_categories.id"))
    generic_class_label = Column(String(200))  # workbook's own PI3_Generic_Class text
    reference_formulation_count = Column(Integer)
    reference_alignment_note = Column(Text)

    generic_class = relationship("RawMaterialCategory")


# ---------------------------------------------------------------------------
# WP5 Wave 5 (2026-08-08) - "Synthetic recipes, runs, samples, results and
# controlled failures". Per 01_Wave_Control this wave is declared as sheets
# "19-24", but sheet 19 (Ref_Formulation_Components) is Wave 4's own sheet,
# already imported there - the same recurring wave-boundary off-by-one
# already flagged after the Wave 3/4 boundary. This wave's actual content
# (per the workbook's own 00_Read_Me, "Demo data ... Evidence 20-25") lives
# on sheets 20_Demo_Recipes through 25_Demo_Failure_Cases - imported that
# range, did not re-touch sheet 19.
#
# Everything except the controlled failure-case registry below reuses the
# existing production-data schema (FoamGrade, RecipeVersion,
# RecipeComponent, ProductionRun/Cycle/Shot/OutputItem, Sample,
# PhysicalPropertyResult, GradeSpecification) rather than a parallel set of
# "Demo*" tables - matching the WP3 UAT chain precedent already live in this
# same schema (FoamGrade id 2, "GRADE-UAT-RPUR-COLDROOM-001", status
# UAT_ONLY / production_use "No production release"). Isolation from real
# plant data is achieved the same way WP3's chain already achieves it: via
# each row's own status/production_use/validation_status/approval_status
# fields, not a separate tenant or schema. Four new FoamGrade rows (one per
# DEMO-RCP-*) were added under the same existing UAT/Reference
# ProductFamily (id 2) and Plant (id 2, "WP3 UAT / Reference (no production
# release)") the WP3 chain already uses.
# ---------------------------------------------------------------------------
class ControlledFailureCase(Base):
    """Charlie's 25_Demo_Failure_Cases registry (WP5 Wave 5) - the expected
    block/fail/issue behaviour for twelve synthetic UAT scenarios (lambda
    above maximum, wrong test condition, missing sample age, density below
    limit, etc). Data only, matching CalculationDefinition's own precedent -
    no engine in this app currently executes these scenarios automatically;
    each one documents what the live conformance/validation logic is
    expected to do, for manual or future automated regression checking
    (Gate 4 criterion G4-16)."""

    __tablename__ = "controlled_failure_cases"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "UAT-FAIL-001"
    scenario = Column(String(300))
    injected_data_condition = Column(Text)
    expected_system_behaviour = Column(Text)
    linked_issue_ids = Column(String(300))  # semicolon-separated QualityIssueType controlled_ids, workbook's own format
    linked_cause_ids = Column(String(300))  # semicolon-separated PossibleCause controlled_ids, workbook's own format
    test_evidence = Column(String(300))
    status = Column(String(50))
    sort_order = Column(Integer)


# ---------------------------------------------------------------------------
# WP3e. Cycle / shot + output item (task list #547, #548)
#
# Rigid discontinuous-panel/closed-mold production runs in discrete cycles
# (one mold-fill-cure-demold cycle can itself contain several shots, e.g.
# a multi-drop pour) rather than the flexible app's continuous-line
# Setup/Finalized phase snapshot model - genuinely new structure, not an
# extension of ProductionPhase. A ProductionRun can still have zero cycles
# recorded (e.g. continuous lamination method, or data not yet captured at
# this granularity) - all links below are nullable/optional.
# ---------------------------------------------------------------------------
class ProductionCycle(Base):
    __tablename__ = "production_cycles"

    id = Column(Integer, primary_key=True)
    production_run_id = Column(Integer, ForeignKey("production_runs.id"), nullable=False)
    cycle_number = Column(Integer, nullable=False)
    tool_id = Column(Integer, ForeignKey("tools.id"))
    mixhead_id = Column(Integer, ForeignKey("mixheads.id"))
    cycle_start = Column(DateTime)
    cycle_end = Column(DateTime)
    notes = Column(Text)

    production_run = relationship("ProductionRun")
    tool = relationship("Tool")
    mixhead = relationship("Mixhead")


class ProductionShot(Base):
    __tablename__ = "production_shots"

    id = Column(Integer, primary_key=True)
    production_cycle_id = Column(Integer, ForeignKey("production_cycles.id"), nullable=False)
    shot_number = Column(Integer, nullable=False)
    shot_ts = Column(DateTime)
    cavity_id = Column(Integer, ForeignKey("cavities.id"))
    fill_point_id = Column(Integer, ForeignKey("fill_points.id"))
    notes = Column(Text)

    production_cycle = relationship("ProductionCycle")
    cavity = relationship("Cavity")
    fill_point = relationship("FillPoint")


class OutputItem(Base):
    """One physical output (panel/board/part) resulting from a cycle - the
    rigid-foam equivalent of the flexible app's "block" concept
    (ProductionRun.block_reference), but as a real row rather than a text
    field, since a single rigid cycle/shot can yield more than one
    discrete item (e.g. several panels demolded from one multi-cavity
    tool)."""

    __tablename__ = "output_items"

    id = Column(Integer, primary_key=True)
    production_run_id = Column(Integer, ForeignKey("production_runs.id"), nullable=False)
    production_cycle_id = Column(Integer, ForeignKey("production_cycles.id"))
    production_shot_id = Column(Integer, ForeignKey("production_shots.id"))
    item_type = Column(String(100))  # e.g. "Panel", "Block", "Part"
    item_reference = Column(String(200))
    quantity = Column(Float)
    unit = Column(String(50))
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    production_run = relationship("ProductionRun")
    production_cycle = relationship("ProductionCycle")
    production_shot = relationship("ProductionShot")


# ---------------------------------------------------------------------------
# WP3f. Method-aware process settings (EAV) (task list #547)
#
# Per the Converged Plan's architecture principle (section 5): "Machines
# carry a production method. Setup and actual values reference controlled
# parameter definitions with data type, unit and validation range." Unlike
# the flexible app's ProductionPhase (a fixed set of named columns, since
# every flexible-foam line has the same handful of settings), rigid-foam
# methods each have their own distinct parameter set (DCP panel lines vs.
# spray vs. RIM), so a fixed-column table would need a different table per
# method or a wide table full of method-specific nulls. A controlled
# definition catalogue (ProcessSettingDefinition, Charlie's PS-* vocabulary)
# plus a generic planned/actual value table (ProcessParameterValue) avoids
# both, at the cost of needing a join to read - an accepted, deliberate
# trade-off for this method-aware part of the schema only. ProductionPhase
# itself is untouched; this is additive, not a replacement.
# ---------------------------------------------------------------------------
PROCESS_SETTING_DATA_TYPES = ["Float", "Integer", "String", "Boolean"]
PROCESS_PARAMETER_SNAPSHOT_TYPES = ["Planned", "Actual"]  # mirrors Setup/Finalized on ProductionPhase


class ProcessSettingDefinition(Base):
    __tablename__ = "process_setting_definitions"

    id = Column(Integer, primary_key=True)
    controlled_id = Column(String(50), unique=True)  # e.g. "PS-070"
    name = Column(String(200), nullable=False)
    data_type = Column(String(20), default="Float")  # see PROCESS_SETTING_DATA_TYPES
    unit_id = Column(Integer, ForeignKey("units_of_measure.id"))
    min_value = Column(Float)  # validation range - nullable, not every setting has known bounds yet
    max_value = Column(Float)
    # Nullable: a method-agnostic setting (e.g. ambient temperature) has no
    # production_method_id; a method-specific setting (e.g. a DCP-only
    # laydown parameter) is scoped to that one ProductionMethod row.
    production_method_id = Column(Integer, ForeignKey("production_methods.id"))
    description = Column(Text)
    sort_order = Column(Integer)

    unit = relationship("UnitOfMeasure")
    production_method = relationship("ProductionMethod")


class ProcessParameterValue(Base):
    """One planned-or-actual value for one setting, on one cycle/shot/run.

    Exactly one of production_run_id / production_cycle_id /
    production_shot_id is expected to be set, matching the same "exactly
    one of N optional FKs" pattern already used by Sample and
    PhysicalPropertyResult above - lets a setting be recorded at whichever
    granularity the method actually operates at (a whole-run setting like
    ambient humidity vs. a per-cycle setting like fill pressure)."""

    __tablename__ = "process_parameter_values"

    id = Column(Integer, primary_key=True)
    setting_definition_id = Column(Integer, ForeignKey("process_setting_definitions.id"), nullable=False)
    production_run_id = Column(Integer, ForeignKey("production_runs.id"))
    production_cycle_id = Column(Integer, ForeignKey("production_cycles.id"))
    production_shot_id = Column(Integer, ForeignKey("production_shots.id"))
    snapshot_type = Column(String(20), default="Actual")  # see PROCESS_PARAMETER_SNAPSHOT_TYPES
    numeric_value = Column(Float)
    text_value = Column(String(500))
    boolean_value = Column(Boolean)
    unit = Column(String(50))  # snapshot text, auto-filled from the definition's unit at entry time
    notes = Column(Text)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    setting_definition = relationship("ProcessSettingDefinition")
    production_run = relationship("ProductionRun")
    production_cycle = relationship("ProductionCycle")
    production_shot = relationship("ProductionShot")


# ---------------------------------------------------------------------------
# 16. maintenance_and_license_records
# ---------------------------------------------------------------------------
# NOTE (corrected 2026-08-01, PI3_Gaps_and_Ambiguities.docx finding 1.1):
# this list previously omitted the entire multi-tenant/access-control layer
# (SubscriptionType, Company, Role, RolePagePermission, User) plus
# FoamGradeTargetProperty - 6 of the app's 34 mapped model classes. Confirmed
# by a repo-wide search that ALL_MODELS is not imported or referenced
# anywhere else in the codebase (init_db()'s Base.metadata.create_all()
# discovers every mapped class automatically via SQLAlchemy's own
# declarative registry, independent of this list), so the omission had zero
# runtime effect - table creation, migrations, and everything else already
# covered all 34 tables regardless. Completed here purely so this list is
# accurate if something is ever built against it later.
ALL_MODELS = [
    SubscriptionType,
    Company,
    Role,
    RolePagePermission,
    User,
    Plant,
    Machine,
    ProductFamily,
    FoamGrade,
    FoamGradeTargetProperty,
    Supplier,
    RawMaterial,
    RecipeVersion,
    RecipeComponent,
    ProductionRun,
    ProductionPhase,
    ComponentStreamReading,
    FallplateSectionPosition,
    ProductionEvent,
    RawMaterialLotUse,
    Sample,
    RuntimeDataRecord,
    CustomerTrial,
    OptimizationTrial,
    PhysicalPropertyDefinition,
    PhysicalPropertyMethod,
    PhysicalPropertyUOM,
    PhysicalPropertyResult,
    QualityObservation,
    ExpertNote,
    PI3AIConnectionSetting,
    PerformanceLog,
    PageLoadLog,
    LoginEvent,
    PageViewEvent,
    PI3InteractionLog,
    PI3Feedback,
    ErrorLog,
    ExportLog,
    RoleChangeLog,
    # --- WP3 vertical-slice additions (2026-08-06) ---
    Chemistry,
    ProductionMethod,
    Application,
    ProductConstruction,
    Orientation,
    Location,
    TestCondition,
    RawMaterialCategory,
    UnitOfMeasure,
    SourceRegister,
    RawMaterialLot,
    ProductionUnit,
    Mixhead,
    Tool,
    Cavity,
    FillPoint,
    VentConfiguration,
    CalibrationRecord,
    GradeSpecification,
    ProductionCycle,
    ProductionShot,
    OutputItem,
    ProcessSettingDefinition,
    ProcessParameterValue,
    # --- WP5 Wave 1 additions (2026-08-07) ---
    RawMaterialAttributeDefinition,
    RawMaterialAttributeValue,
    RawMaterialDocument,
    RawMaterialQualification,
    Substrate,
    # --- WP5 Wave 2 addition (2026-08-07) ---
    GradeSpecificationTemplate,
    # --- Machine Data Architecture additions (2026-08-07) ---
    MachineCategory,
    MachineModel,
    MachineConfiguration,
    MachineOperatingParameter,
    MachineAlarm,
    MachineMaintenanceRecord,
    MachineTroubleshootingCase,
    MachineDocument,
    # --- WP5 Wave 3 additions (2026-08-07) ---
    QualityIssueType,
    PossibleCause,
    IssueCauseLink,
    # --- WP5 Wave 4 additions (2026-08-07) ---
    CalculationDefinition,
    ReferenceFormulation,
    ReferenceFormulationComponent,
    # --- Reconciliation additions (2026-08-08, Raw Materials Master v2 +
    # Reference_Formulations_10 package) ---
    RawMaterialCatalogEntry,
    # --- WP5 Wave 5 additions (2026-08-08) ---
    ControlledFailureCase,
    # --- Post-G5 Reference Data Enrichment additions (2026-08-09) ---
    ReferenceFormulationPerformanceResult,
    ReferenceFormulationProcessingNote,
    ReferenceFormulationFamily,
    # --- Production Method Hierarchy architecture change additions (2026-08-09) ---
    PlantProductionMethod,
]


def init_db():
    """Create all tables if they do not already exist. Safe to call on every
    app start - the actual schema-reflection work now only runs once per
    server process (see _ensure_schema_ready below), not once per call.

    Before 2026-08-05 this called Base.metadata.create_all() directly and
    was invoked from app_rigid_foam.py's module-level code, which reruns on EVERY
    Streamlit widget interaction anywhere in the app (app_rigid_foam.py is the
    st.navigation entry point - its top-level code re-executes on every
    click, not just on navigation). That meant a full schema check
    (Inspector round trip(s) against all ~39 mapped tables) against the
    remote Supabase Postgres on every single click, forever, even though
    the schema only ever needs checking once per process lifetime. This
    was one of the largest fixed-overhead contributors to the "every
    screen build takes 15-20s" performance report - see PROJECT_STATUS.md
    / the v2.0 performance audit."""
    _ensure_schema_ready()


@st.cache_resource
def _ensure_schema_ready():
    """st.cache_resource caches the return value in-process, shared across
    every browser session this server handles - so this body runs exactly
    once per process, not once per rerun. Returns a value (rather than
    None) only so the cache has something to store; callers never use it.

    On Postgres, the "rigid_foam" schema itself (see RIGID_FOAM_SCHEMA
    above) is created here too, before create_all - Postgres does not
    auto-create a schema just because a table definition names one, and
    CREATE TABLE fails with "no schema has been selected" without this."""
    if RIGID_FOAM_SCHEMA:
        with ENGINE.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{RIGID_FOAM_SCHEMA}"'))
    Base.metadata.create_all(bind=ENGINE)
    return True


def get_session():
    """Return a SQLAlchemy session that persists for the lifetime of the
    Streamlit browser session (via st.session_state), rather than a fresh
    session on every script rerun.

    Streamlit widgets (e.g. st.selectbox) can hold onto ORM objects across
    reruns. If each rerun created a brand-new session, the session backing
    an object selected in an earlier rerun would already be gone, and
    accessing a not-yet-loaded (lazy) relationship on it would raise
    sqlalchemy.orm.exc.DetachedInstanceError. Reusing one session per
    browser session keeps those objects attached and loadable.

    IMPORTANT - see close_out_session() below: reusing one session across
    reruns means every read this session does opens a transaction that, if
    never explicitly closed, stays open for as long as that browser tab's
    Streamlit session lives - not just for this rerun. app_rigid_foam.py must call
    close_out_session() once, after routing to whichever page ran, on
    every single rerun. Do not call get_session() from anywhere that isn't
    already covered by that (e.g. a background job), without also arranging
    to close the transaction it opens.
    """
    if "_sa_session" not in st.session_state:
        st.session_state["_sa_session"] = SessionLocal()
    return st.session_state["_sa_session"]


def close_out_session():
    """Commit (or roll back, on failure) whatever transaction the page that
    just ran opened, so no Streamlit rerun ever ends with an open, idle
    transaction left sitting on the database.

    Why this exists: get_session() deliberately reuses ONE session per
    browser tab across every rerun (see its docstring), and every read
    (.query()/.get()/...) under SQLAlchemy's default autocommit=False opens
    a transaction. Pages that only display data - Trend Analysis, Recipe
    Optimization, Root-Cause Assistant, Machine Settings vs Physical
    Properties Correlation, Machine Settings Optimization, Demo Data
    Admin, and any read-only view
    of a page that also supports editing - never call session.commit()
    themselves, since they have nothing to save. Without this function,
    that transaction would sit "idle in transaction" - holding read locks
    on every table it queried - until some later rerun happened to submit a
    form, or forever, if the user only browses and then leaves the tab
    open or closes it.

    This is not a theoretical concern: exactly this happened in production
    - a single read-only page view left a transaction open for roughly 18
    hours, holding locks that blocked an unrelated schema migration until
    the stale connection was manually terminated.

    Safe to call unconditionally after every rerun: every place in this app
    that adds/edits/deletes already calls session.commit() itself within
    the same rerun the change happens in (see cascades.py's docstring - a
    whole master-data delete is deliberately one all-or-nothing
    transaction, committed once by the caller). So by the time this runs,
    there is never a "half-finished" change sitting uncommitted - this only
    ever closes out a transaction that was already left in a fully
    consistent state, whether that's a page's own prior commit or just the
    read-only queries a view-only page issued.
    """
    session = st.session_state.get("_sa_session")
    if session is None:
        return
    try:
        session.commit()
    except Exception as commit_exc:
        # If the underlying connection itself has gone bad (e.g. the server
        # killed it - idle-in-transaction timeout, a restart, ...), rollback()
        # can also fail. In that case don't leave this same broken Session
        # cached in st.session_state: every future rerun of this browser tab
        # would keep reusing it and keep failing the same way until the user
        # did a full page reload. Discard it instead so the next
        # get_session() call builds a fresh Session (and checks out a fresh,
        # pool_pre_ping-verified connection) on the very next rerun.
        discarded = False
        try:
            session.rollback()
        except Exception:
            try:
                session.close()
            except Exception:
                pass
            st.session_state.pop("_sa_session", None)
            discarded = True

        # Item 52 (Gate 6) - this is one of the two highest-value error
        # points in the app (the other being failed PI3 calls - see
        # ai_assistant.py's _record_pi3_error), so it's logged here
        # directly rather than waiting on individual pages to catch it.
        # audit_log is imported locally, not at module level: audit_log.py
        # imports its ORM model classes FROM this module, so a top-level
        # `import audit_log` here would be circular. By the time this
        # function actually runs, db.py has already finished importing (this
        # is a function body, not import-time code), so the deferred import
        # resolves cleanly. A fresh session is used for the write itself,
        # since the original one is either broken or was just discarded.
        try:
            import audit_log

            log_session = get_session()
            audit_log.log_error(
                log_session,
                error_message="Database transaction commit failed" + (" (session discarded)" if discarded else " (rolled back)"),
                exc=commit_exc,
                user_id=st.session_state.get("user_id"),
                company_id=st.session_state.get("company_id"),
                page_name=st.session_state.get("_current_page_title"),
            )
            log_session.commit()
        except Exception:
            pass
