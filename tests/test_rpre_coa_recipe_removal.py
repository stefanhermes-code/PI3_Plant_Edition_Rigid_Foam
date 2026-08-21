"""Control for R-PRE-WP2 - no formulation content on the Certificate of Analysis.
Redesign Migration Plan v3, Package A.

WHAT PROBLEM THIS SOLVES

The Certificate of Analysis is the one report in this application that leaves
the company. It used to carry the recipe version, its approval status and
effective date, the ratio/index, and a full table of every raw material, its
supplier, its php and its role. On screen that table was captioned "internal
use only" - but the same content was written into the PDF and the Word file
the customer downloads, so the caption protected nothing.

Stefan's ruling of 20 August 2026: remove all of it, including the recipe
reference.

WHY THE TEST RENDERS THE DOCUMENTS RATHER THAN INSPECTING THE DICT ALONE

A dict-level check proves the builder stopped returning the keys. It does not
prove the renderers stopped writing the values, because a renderer can reach
past the dict - and it is the rendered file, not the dict, that reaches the
customer. So the material name, the supplier name and the dosage are planted
in the fixture with values that could not occur by accident, both documents
are generated, and the bytes are searched. The PDF's content streams are
zlib-compressed, so they are decompressed first; searching the raw bytes would
pass whether or not the text was there, which is a test that cannot fail.

There is also an over-reach guard. The Batch Release Record is an INTERNAL
document and legitimately keeps its recipe section. A change that stripped
formulation content from every report would satisfy the ruling and break the
plant.

Usage: python -m pytest tests/test_rpre_coa_recipe_removal.py -v
"""
import datetime as dt
import base64
import io
import os
import re
import sys
import uuid
import zipfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

import db
import reports

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Values that cannot appear in a certificate by coincidence. If any of these
# turns up in a rendered document, formulation content leaked.
SECRET_MATERIAL = "ZZTESTPOLYOL-RPRE"
SECRET_SUPPLIER = "ZZTESTSUPPLIER-RPRE"
SECRET_ROLE = "ZZTESTROLE-RPRE"
SECRET_NOTE = "ZZTESTNOTE-RPRE"
SECRET_VERSION = "ZZTESTRECIPEVERSION-RPRE"

# Section headings that must no longer be emitted.
REMOVED_HEADINGS = ["Recipe used", "Formulation", "Ratio / index", "Approval status", "Effective date"]

# What the certificate must still say. Removing too much is also a failure.
REQUIRED_HEADINGS = ["Sample source", "Sample", "Quality test results"]


def _reset_schema():
    db.Base.metadata.drop_all(db.ENGINE)
    db.Base.metadata.create_all(db.ENGINE)


@pytest.fixture()
def certificate_chain():
    """Company -> Plant -> Machine -> PUMaterialFamily -> FoamGrade ->
    RecipeVersion WITH a component carrying the planted values -> ProductionRun
    -> Sample. The recipe is fully populated on purpose: the point is that the
    data exists and the certificate still does not show it."""
    db.init_db()
    _reset_schema()
    u = uuid.uuid4().hex[:8]
    session = db.get_session()

    company = db.Company(name=f"RPRE Co {u}", is_platform_owner=True)
    session.add(company); session.flush()
    plant = db.Plant(company_id=company.id, name=f"RPRE Plant {u}")
    session.add(plant); session.flush()
    machine = db.Machine(plant_id=plant.id, name=f"RPRE Machine {u}", active=True)
    session.add(machine); session.flush()
    family = db.PUMaterialFamily(plant_id=plant.id, name=f"RPRE Family {u}")
    session.add(family); session.flush()
    grade = db.FoamGrade(pu_material_family_id=family.id, grade_name=f"RPRE Grade {u}")
    session.add(grade); session.flush()

    recipe = db.RecipeVersion(
        foam_grade_id=grade.id, version_label=SECRET_VERSION,
        approval_status="Approved", is_active=True, ratio_index=109.5,
    )
    session.add(recipe); session.flush()
    session.add(db.RecipeComponent(
        recipe_version_id=recipe.id, raw_material_name=SECRET_MATERIAL,
        supplier=SECRET_SUPPLIER, php=42.4242, role_in_formulation=SECRET_ROLE,
        notes=SECRET_NOTE,
    ))
    session.flush()

    run = db.ProductionRun(
        plant_id=plant.id, foam_grade_id=grade.id, recipe_version_id=recipe.id,
        run_date=dt.date(2026, 8, 20), batch_reference=f"RPRE-B-{u}", machine_id=machine.id,
    )
    session.add(run); session.flush()
    sample = db.Sample(production_run_id=run.id, sample_ts=dt.datetime(2026, 8, 20, 9, 0))
    session.add(sample); session.flush()
    session.commit()
    ids = {"sample_id": sample.id, "run_id": run.id}
    session.close()
    return ids


def _certificate_data(ids):
    session = db.get_session()
    try:
        return reports.build_sample_certificate_data(session, ids["sample_id"])
    finally:
        session.close()


def _docx_text(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", "", xml)


def _pdf_text(blob):
    """reportlab writes its content streams ASCII85-encoded AND zlib-deflated,
    so the visible text is not in the raw bytes and a naive substring search
    over the file would pass whether or not the text was present. Undo both
    layers, then pull the strings out of the text-showing operators.

    test_pdf_extraction_actually_sees_the_document_text() below exists to prove
    this function still works. It caught this very helper returning ASCII85
    noise on 20 August 2026, while the five leak tests it feeds were all
    passing."""
    chunks = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", blob, re.S):
        raw = match.group(1).strip()
        data = None
        for decode in (_a85_then_inflate, _inflate, _identity):
            data = decode(raw)
            if data is not None:
                break
        if data:
            chunks.append(data)
    body = b"\n".join(chunks).decode("latin-1")
    # Text in a PDF content stream is shown as (literal) Tj or [(a)(b)] TJ.
    shown = re.findall(r"\((?:\\.|[^\\()])*\)", body)
    return "\n".join(s[1:-1].replace("\\(", "(").replace("\\)", ")") for s in shown)


def _a85_then_inflate(raw):
    try:
        return zlib.decompress(base64.a85decode(raw, adobe=True))
    except Exception:
        return None


def _inflate(raw):
    try:
        return zlib.decompress(raw)
    except Exception:
        return None


def _identity(raw):
    return raw


# ---------------------------------------------------------------------------
# 1. The data dict
# ---------------------------------------------------------------------------

def test_builder_returns_no_recipe_keys(certificate_chain):
    data = _certificate_data(certificate_chain)
    leaked = [k for k in data if "recipe" in k.lower() or "formulation" in k.lower()]
    assert leaked == [], f"certificate data still carries {leaked}"


def test_builder_still_returns_what_the_certificate_needs(certificate_chain):
    data = _certificate_data(certificate_chain)
    for key in ("sample_id", "source_type", "header_fields", "foam_grade", "plant",
                "quality_results", "overall_verdict", "pass_count", "fail_count"):
        assert key in data, f"certificate data lost {key}"


# ---------------------------------------------------------------------------
# 2. The rendered documents - the ones that actually reach the customer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("secret", [SECRET_MATERIAL, SECRET_SUPPLIER, SECRET_ROLE, SECRET_NOTE, SECRET_VERSION])
def test_docx_contains_no_formulation_value(certificate_chain, secret):
    text = _docx_text(reports.render_sample_certificate_docx(_certificate_data(certificate_chain)))
    assert secret not in text, f"{secret} leaked into the Word certificate"


@pytest.mark.parametrize("secret", [SECRET_MATERIAL, SECRET_SUPPLIER, SECRET_ROLE, SECRET_NOTE, SECRET_VERSION])
def test_pdf_contains_no_formulation_value(certificate_chain, secret):
    text = _pdf_text(reports.render_sample_certificate_pdf(_certificate_data(certificate_chain)))
    assert secret not in text, f"{secret} leaked into the PDF certificate"


def test_pdf_extraction_actually_sees_the_document_text(certificate_chain):
    """Guards the two tests above. If _pdf_text() returned nothing useful they
    would pass for the wrong reason - the classic test that cannot fail."""
    text = _pdf_text(reports.render_sample_certificate_pdf(_certificate_data(certificate_chain)))
    assert "Certificate of Analysis" in text
    assert "Sample source" in text


@pytest.mark.parametrize("heading", REMOVED_HEADINGS)
def test_docx_no_longer_carries_the_removed_sections(certificate_chain, heading):
    text = _docx_text(reports.render_sample_certificate_docx(_certificate_data(certificate_chain)))
    assert heading not in text, f"the certificate still renders a {heading!r} section"


@pytest.mark.parametrize("heading", REQUIRED_HEADINGS)
def test_docx_still_carries_the_sections_it_must(certificate_chain, heading):
    text = _docx_text(reports.render_sample_certificate_docx(_certificate_data(certificate_chain)))
    assert heading in text, f"the certificate lost its {heading!r} section"


def test_dosage_value_is_absent_from_both_documents(certificate_chain):
    data = _certificate_data(certificate_chain)
    for text in (_docx_text(reports.render_sample_certificate_docx(data)),
                 _pdf_text(reports.render_sample_certificate_pdf(data))):
        assert "42.4242" not in text
        assert "109.5" not in text


# ---------------------------------------------------------------------------
# 3. Over-reach guard - internal reports keep their formulation
# ---------------------------------------------------------------------------

def test_batch_release_record_still_carries_the_recipe(certificate_chain):
    """The Batch Release Record is internal. Stripping formulation content
    from it as well would satisfy the ruling and break the plant."""
    session = db.get_session()
    try:
        data = reports.build_batch_release_record_data(session, certificate_chain["run_id"])
    finally:
        session.close()
    assert "recipe_components" in data
    assert any(c.get("Material") == SECRET_MATERIAL for c in data["recipe_components"])


# ---------------------------------------------------------------------------
# 4. The on-screen copy
# ---------------------------------------------------------------------------

def test_report_page_no_longer_renders_the_formulation_table():
    """The screen mattered less than the download, but a table captioned
    "internal use only" sitting on a customer-facing certificate is exactly
    how the content found its way into the file in the first place."""
    with open(os.path.join(APP_DIR, "views", "21_Report.py"), encoding="utf-8") as handle:
        source = handle.read()
    certificate_section = source[source.index("# 4. Sample Certificate of Analysis"):
                                 source.index("# 5. WP3 Property Conformance Report")]
    for banned in ("recipe_components", "recipe_version_label", "recipe_approval_status",
                   "recipe_effective_date", "recipe_ratio_index"):
        assert banned not in certificate_section, f"{banned} still rendered on the certificate tab"


# ---------------------------------------------------------------------------
# 5. What the page SAYS about the certificate
#
# Found live on 20 August 2026, after the content had already been removed and
# the code tests were green: the page still described the certificate as
# carrying "the recipe used (full formulation - internal use only, not
# customer-facing)", and the page-level action text still called it
# "result-and-recipe traceability".
#
# Both were false, and false in the worst direction - a user reading them
# would believe a customer-facing document contained the formulation, or
# would avoid sending a certificate that was in fact safe to send. Removing
# content and leaving the description behind is the same defect class as the
# internal-vocabulary leak: the application describing itself inaccurately.
# ---------------------------------------------------------------------------

FORMULATION_CLAIMS = [
    "result-and-recipe",
    "the recipe used (full formulation",
    "full recipe formulation",
    "internal use only, not customer-facing",
]


def _user_visible(source):
    """Comment lines removed. The section's block comment deliberately QUOTES
    the old wording to record what changed and why, and a scan that tripped on
    its own explanation would force the history to be deleted to keep the test
    green. What matters is what the user reads on screen."""
    return "\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))


def test_the_report_page_does_not_claim_the_certificate_carries_a_recipe():
    with open(os.path.join(APP_DIR, "views", "21_Report.py"), encoding="utf-8") as handle:
        source = handle.read()
    certificate_section = _user_visible(
        source[source.index("# 4. Sample Certificate of Analysis"):
               source.index("# 5. WP3 Property Conformance Report")]
    )
    for claim in FORMULATION_CLAIMS:
        assert claim not in certificate_section, (
            f"the certificate section still tells the user it carries a recipe: {claim!r}"
        )


def test_the_page_intro_does_not_claim_recipe_traceability():
    """The Function/Action block at the top of the page, which every user sees
    before they pick a tab."""
    with open(os.path.join(APP_DIR, "views", "21_Report.py"), encoding="utf-8") as handle:
        source = handle.read()
    intro = _user_visible(source[:source.index("session = get_session()")])
    assert "result-and-recipe" not in intro

