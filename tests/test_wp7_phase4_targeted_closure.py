"""WP7 Phase 4 targeted closure gate (2026-08-14) regression tests.

Charlie's Closeout Review Return to JC, targeted closure gate instruction 2:
"Re-run the application-wide dependency scan. Include direct model reads
such as ProductionPhase in addition to fixed-symbol searches." Re-running
that scan with attention to direct ProductionPhase model reads (not just
PHASE_SETTING_FIELDS/PHASE_SETTING_LABELS symbol references) surfaced one
genuine remaining gap that the original Item-1/fixed-symbol scan missed:
analytics.actual_usage_dataframe() (used by Recipe Optimization's actual-
usage correlation, analytics.rank_component_actual_correlations()) still
located each run's Finalized ProductionPhase first and only read
ComponentStreamReading rows linked to that phase - the exact same class of
live ProductionPhase dependency Item 1.3 already removed from Batch
Release's build_batch_release_record_data(). Since views/4's Material
Metering capture UI was decoupled from ProductionPhase back in WP7 Phase 2
("a Finalized phase is no longer required first"), any run metered under
the current architecture with no Finalized ProductionPhase ever created for
it was silently excluded from this correlation - a real data-completeness
gap, not just an architectural cleanliness concern.

Fixed the same way Item 1.3 fixed Batch Release: ComponentStreamReading is
now queried directly by production_run_id, never via a located
ProductionPhase. This file's one test is the direct-evidence proof,
mirroring tests/test_wp7_phase4_batch_release_cutover.py::
test_material_metering_reads_via_production_run_id_with_no_production_phase.

This is the only material-code finding from the re-run scan; every other
direct ProductionPhase model read found (grep -n "ProductionPhase" across
the repo, not just PHASE_SETTING_FIELDS/LABELS) is a legitimate, in-scope
use classified as follows and left unchanged:
  - analytics.run_settings_dataframe(): still queries ProductionPhase for
    PHASE_SETTING_FIELDS values, but its only 2 live callers (views/18's
    identity-only lookup, analytics.merged_run_property_dataframe()'s
    identity-only lookup) never consume those value columns - zero
    setting-value leakage into any active consumer, documented pre-existing
    state.
  - views/4_Production_Run_Trial_Record.py: the active authoring/write path
    for ProductionPhase itself (Setup/Finalized capture) - ProductionPhase
    is not retired as an entity in Phase 4, only as an active-reader source
    for other consumers.
  - views/9_Samples_Conditioning.py: reads ProductionPhase.phase_start only
    for a sample-timestamp sanity bound (not a process-setting value).
  - cascades.py: cascade-delete cleanup (referential integrity), not a
    settings/facts reader.
  - legacy_migration.py: the intentional migration/backfill tool.
  - demo_data.py, gen_uat015_019_live_pages.py: seed-data writers, not
    consumers.
  - db.py, reports.py (comment-only), views/11, views/12, views/18
    (comment-only), version.py (changelog-only): no live read.

Usage: python -m pytest tests/test_wp7_phase4_targeted_closure.py -v
"""
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import analytics
import db


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def seeded_grade_chain():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"WP7P4TC Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"WP7P4TC Plant {u}")
    session.add(plant); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"WP7P4TC Machine {u}")
    session.add(machine); session.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"WP7P4TC Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(product_family_id=family.id, grade_name=f"WP7P4TC Grade {u}")
    session.add(grade); session.flush()
    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Approved", is_active=True)
    session.add(recipe); session.flush()
    session.add(db.RecipeComponent(
        recipe_version_id=recipe.id, raw_material_name="Polyol A", role_in_formulation="Base Polyol", php=100,
    ))
    session.add(db.RecipeComponent(
        recipe_version_id=recipe.id, raw_material_name="TDI 80/20", role_in_formulation="Isocyanate", php=45,
    ))
    session.flush()
    session.commit()

    ids = {
        "company_id": company.id, "plant_id": plant.id, "machine_id": machine.id,
        "family_id": family.id, "grade_id": grade.id, "recipe_version_id": recipe.id,
    }
    session.close()
    return ids


def _make_run(ids, run_date):
    session = db.get_session()
    run = db.ProductionRun(
        plant_id=ids["plant_id"], foam_grade_id=ids["grade_id"],
        recipe_version_id=ids["recipe_version_id"], run_date=run_date,
        batch_reference=f"B-WP7P4TC-{uuid.uuid4().hex[:8]}", machine_id=ids["machine_id"],
    )
    session.add(run); session.commit()
    run_id = run.id
    session.close()
    return run_id


@pytest.fixture()
def seeded_run(seeded_grade_chain):
    ids = seeded_grade_chain
    run_id = _make_run(ids, dt.date(2026, 8, 1))
    out = dict(ids)
    out["run_id"] = run_id
    return out


def test_actual_usage_dataframe_reads_via_production_run_id_with_no_production_phase(seeded_run):
    """WP7 Phase 4 targeted closure gate - direct evidence requirement,
    mirroring Item 1.3's Batch Release proof: analytics.actual_usage_
    dataframe() (and its only caller, rank_component_actual_correlations(),
    which backs Recipe Optimization's actual-usage material correlation)
    must read ComponentStreamReading exclusively via production_run_id,
    never via a located Finalized ProductionPhase. This writes stream
    readings with production_phase_id left NULL for a run that has zero
    ProductionPhase rows at all (the fixture never creates one) and
    confirms they still surface - proving the read has no live
    ProductionPhase dependency, and therefore no longer silently drops a
    run metered under the current (ProductionPhase-decoupled) Material
    Metering architecture."""
    session = db.get_session()
    assert session.query(db.ProductionPhase).filter(
        db.ProductionPhase.production_run_id == seeded_run["run_id"]
    ).count() == 0  # no ProductionPhase exists for this run at all

    session.add(db.ComponentStreamReading(
        production_run_id=seeded_run["run_id"], production_phase_id=None,
        stream_name="Polyol A", flow_total_qty=100.0,
    ))
    session.add(db.ComponentStreamReading(
        production_run_id=seeded_run["run_id"], production_phase_id=None,
        stream_name="TDI 80/20", flow_total_qty=48.0,
    ))
    session.commit()
    session.close()

    session = db.get_session()
    df = analytics.actual_usage_dataframe(session, foam_grade_id=seeded_run["grade_id"])
    session.close()

    assert not df.empty
    assert set(df["run_id"]) == {seeded_run["run_id"]}
    by_stream = {row["stream_name"]: row["actual_php_equivalent"] for _, row in df.iterrows()}
    assert by_stream["Polyol A"] == pytest.approx(100.0)
    assert by_stream["TDI 80/20"] == pytest.approx(48.0)


def test_actual_usage_dataframe_still_finds_legacy_phase_linked_reading(seeded_run):
    """Backward-compatibility half of the same proof: a reading written the
    OLD way (production_phase_id set, production_run_id also set - the
    real-world shape after legacy_migration.py's backfill_component_
    stream_reading_run_ids() has run against production data) is not
    dropped either. Only production_run_id drives the read; a populated
    production_phase_id is simply along for the ride."""
    session = db.get_session()
    phase = db.ProductionPhase(production_run_id=seeded_run["run_id"], phase_name="Finalized")
    session.add(phase); session.flush()
    session.add(db.ComponentStreamReading(
        production_run_id=seeded_run["run_id"], production_phase_id=phase.id,
        stream_name="Polyol A", flow_total_qty=100.0,
    ))
    session.add(db.ComponentStreamReading(
        production_run_id=seeded_run["run_id"], production_phase_id=phase.id,
        stream_name="TDI 80/20", flow_total_qty=45.0,
    ))
    session.commit()
    session.close()

    session = db.get_session()
    df = analytics.actual_usage_dataframe(session, foam_grade_id=seeded_run["grade_id"])
    session.close()

    assert not df.empty
    assert set(df["run_id"]) == {seeded_run["run_id"]}
