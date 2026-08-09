"""
JC action 7 (Charlie's WP6-S09 sequence, 2026-08-09): "Export one live page
output each for UAT-015 through UAT-019."

Seeds one realistic rigid-grade fixture (Company/Plant/Machine/ProductFamily/
Chemistry/ProductionMethod/FoamGrade/RecipeVersion/RecipeComponent/
GradeSpecification/8 ProductionRuns each with a Finalized ProductionPhase +
Sample + PhysicalPropertyResult + RawMaterialLotUse, plus one QualityObservation
on the last run) into an in-memory SQLite DB, then drives each of the 5
Industrial Intelligence pages via Streamlit's AppTest (AUTH_DISABLED dev
bypass - no password entered, no live OpenAI call made since PI3 sections are
all button-gated) and captures the ACTUAL rendered output - not a
description of what the page should do - as evidence for UAT-015..019.
"""
import datetime as dt
import json
import os
import sys
import uuid

sys.path.insert(0, ".")
os.environ["DATABASE_URL"] = "sqlite://"

import db
from streamlit.testing.v1 import AppTest

OUT = "/sessions/great-clever-goldberg/mnt/outputs/s09_live_pages"
os.makedirs(OUT, exist_ok=True)


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


def seed():
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    s = db.get_session()

    company = db.Company(name=f"WP6S09 Live Co {u}", is_platform_owner=True)
    s.add(company); s.flush()
    plant = db.Plant(company_id=company.id, name=f"WP6S09 Live Plant {u}")
    s.add(plant); s.flush()
    machine = db.Machine(plant_id=plant.id, name=f"WP6S09 Live Machine {u}")
    s.add(machine); s.flush()
    family = db.ProductFamily(plant_id=plant.id, name=f"Cold Room Panels {u}")
    s.add(family); s.flush()
    chem = db.Chemistry(controlled_id=f"CHM-LIVE-{u}", name="Rigid polyurethane foam")
    method = db.ProductionMethod(controlled_id=f"PM-LIVE-{u}", name="Closed-mold panel injection")
    s.add_all([chem, method]); s.flush()

    grade = db.FoamGrade(
        product_family_id=family.id, grade_name=f"RF-LIVE-UAT-{u}",
        chemistry_id=chem.id, production_method_id=method.id, status="UAT_ONLY",
    )
    s.add(grade); s.flush()

    recipe = db.RecipeVersion(foam_grade_id=grade.id, version_label="v1", approval_status="Draft", is_active=True)
    s.add(recipe); s.flush()
    rm_polyol = db.RawMaterial(company_id=company.id, name="Polyol A", category="Polyol", cost_per_kg=2.5)
    rm_iso = db.RawMaterial(company_id=company.id, name="pMDI A", category="Isocyanate", cost_per_kg=3.1)
    s.add_all([rm_polyol, rm_iso]); s.flush()
    comp1 = db.RecipeComponent(recipe_version_id=recipe.id, raw_material_name="Polyol A", php=100.0, role_in_formulation="Base Polyol")
    comp2 = db.RecipeComponent(recipe_version_id=recipe.id, raw_material_name="pMDI A", php=125.0, role_in_formulation="Isocyanate")
    s.add_all([comp1, comp2]); s.flush()

    propdef = db.PhysicalPropertyDefinition(
        name="Thermal conductivity",
        mandatory_context="Record mean test temperature, thickness, orientation, test age and conditioning",
    )
    s.add(propdef); s.flush()
    propmethod = db.PhysicalPropertyMethod(property_definition_id=propdef.id, method_code="ISO 8301", controlled_id=f"MTH-LIVE-{u}")
    s.add(propmethod); s.flush()
    orientation = db.Orientation(controlled_id=f"ORI-LIVE-{u}", name="Through-thickness")
    location = db.Location(controlled_id=f"LOC-LIVE-{u}", name="Core centre")
    condition = db.TestCondition(controlled_id=f"CTX-LIVE-{u}", name="Mean test temperature 10 degC")
    s.add_all([orientation, location, condition]); s.flush()

    spec = db.GradeSpecification(
        foam_grade_id=grade.id, property_definition_id=propdef.id, property_method_id=propmethod.id,
        property_name="Thermal conductivity", target_operator="<=", target_value=0.024, unit="W/(m.K)",
        condition_id=condition.id, orientation_id=orientation.id, location_id=location.id,
    )
    s.add(spec); s.flush()

    base_date = dt.date(2026, 6, 1)
    # 8 runs, mixer_rpm rising, lambda drifting upward with rpm - gives Trend
    # Analysis/Process-Property Correlation/Machine Settings Optimization
    # real, non-flat variation to work with, not just "in control, no trend".
    mixer_rpms = [1400, 1420, 1450, 1470, 1500, 1530, 1560, 1600]
    lambdas =    [0.0215, 0.0217, 0.0219, 0.0220, 0.0222, 0.0224, 0.0227, 0.0231]
    runs = []
    for i in range(8):
        run_date = base_date + dt.timedelta(days=5 * i)
        run = db.ProductionRun(
            plant_id=plant.id, foam_grade_id=grade.id, machine_id=machine.id, recipe_version_id=recipe.id,
            run_date=run_date, batch_reference=f"LIVE-{u}-{i+1}",
        )
        s.add(run); s.flush()
        phase = db.ProductionPhase(
            production_run_id=run.id, phase_name="Finalized",
            mixer_rpm=mixer_rpms[i], conveyor_speed=8.5, air_injection_rate=None,
            air_pressure_bar=None, sidewall_width_mm=1200, top_flat_system_used=(i % 2 == 0),
        )
        s.add(phase); s.flush()
        sample = db.Sample(
            production_run_id=run.id, location_id=location.id, orientation_id=orientation.id,
            thickness_mm=60.0, age_hours=168.0, sample_scope="Core",
            sample_ts=dt.datetime.combine(run_date, dt.time(9, 0)),
        )
        s.add(sample); s.flush()
        result = db.PhysicalPropertyResult(
            production_run_id=run.id, sample_id=sample.id, property_definition_id=propdef.id,
            property_method_id=propmethod.id, property_name="Thermal conductivity",
            actual_value=lambdas[i], target_value=0.024, unit="W/(m.K)", test_method="ISO 8301",
            condition_id=condition.id, orientation_id=orientation.id, location_id=location.id,
            tested_at=run_date,
        )
        s.add(result); s.flush()
        lot1 = db.RawMaterialLotUse(production_run_id=run.id, supplier_lot_no=f"LOT-POL-{i+1}", component_stream_name="Polyol A", mass_kg=100.0 + i)
        lot2 = db.RawMaterialLotUse(production_run_id=run.id, supplier_lot_no=f"LOT-ISO-{i+1}", component_stream_name="pMDI A", mass_kg=125.0 + i * 1.2)
        s.add_all([lot1, lot2]); s.flush()
        runs.append(run)

    # Root-Cause Assistant needs a QualityObservation tied to the LAST run,
    # with an earlier run of the same grade to compare against - runs[0] vs
    # runs[-1] differ in mixer_rpm (1400 -> 1600), which is exactly the kind
    # of real "what changed" signal the page is meant to surface.
    obs = db.QualityObservation(
        production_run_id=runs[-1].id, observation_type="High aged thermal conductivity",
        severity="High", frequency="Isolated", suspected_cause="Blowing-agent loss before dispense",
        observed_at=dt.datetime.combine(runs[-1].run_date, dt.time(11, 0)),
    )
    s.add(obs); s.flush()

    pi3_setting = db.PI3AIConnectionSetting(plant_id=plant.id, pi3_ai_connectivity_enabled=True)
    s.add(pi3_setting); s.flush()

    s.commit()
    info = {
        "grade_id": grade.id, "grade_name": grade.grade_name, "family_id": family.id,
        "plant_id": plant.id, "company_id": company.id, "obs_id": obs.id,
        "run_ids": [r.id for r in runs],
    }
    s.close()
    return info


def run_page(page_filename):
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "pages", page_filename
    )
    at = AppTest.from_file(path, default_timeout=60)
    at.secrets["AUTH_DISABLED"] = True
    at.secrets["OPENAI_API_KEY"] = "sk-test-not-real"
    at.secrets["PI3_VECTOR_STORE_ID"] = "vs-test-not-real"
    at.run()
    return at


def dump_page(at, name, fh):
    fh.write(f"\n{'='*100}\nPAGE: {name}\n{'='*100}\n")
    if at.exception:
        fh.write(f"EXCEPTION: {at.exception}\n")
        for e in at.exception:
            fh.write(f"  {e}\n")
        return
    fh.write("(no exception - page rendered cleanly)\n\n")
    for el in at.main:
        try:
            t = el.type
        except Exception:
            t = "?"
        if t in ("markdown", "caption", "subheader", "header", "title", "text", "info", "warning", "success", "error", "metric"):
            val = getattr(el, "value", None) or getattr(el, "body", None)
            fh.write(f"[{t}] {val}\n")
        elif t == "dataframe":
            fh.write(f"[dataframe]\n{el.value}\n")
        elif t == "altair_chart":
            fh.write("[altair_chart] (chart rendered)\n")
        elif t == "selectbox":
            fh.write(f"[selectbox] label={el.label!r} options={el.options}\n")
        elif t == "download_button":
            fh.write(f"[download_button] label={el.label!r}\n")


if __name__ == "__main__":
    info = seed()
    print("Seed info:", json.dumps(info, indent=2))

    pages = [
        ("UAT-015", "15_Recipe_Optimization.py"),
        ("UAT-016", "16_Trend_Analysis.py"),
        ("UAT-017", "17_Process_Property_Correlation.py"),
        ("UAT-018", "18_Root_Cause_Assistant.py"),
        ("UAT-019", "19_Machine_Settings_Optimization.py"),
    ]
    with open(f"{OUT}/live_page_output.txt", "w") as fh:
        fh.write(f"Seed: grade_id={info['grade_id']} grade_name={info['grade_name']}\n")
        fh.write(f"run_ids={info['run_ids']} obs_id={info['obs_id']}\n")
        for uat_id, fname in pages:
            print("Running", uat_id, fname)
            at = run_page(fname)
            dump_page(at, f"{uat_id} - {fname}", fh)
            print("  exception:", at.exception)
    print("done - see", f"{OUT}/live_page_output.txt")
