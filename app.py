"""Main web server for HMP Stress-Test Platform."""

import logging
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from hmp_analyzer import analyze_hmp
from pdf_processor import extract_hmp
from report_generator import generate_html_report
from stress_tester import run_all_stress_tests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HMP Stress-Test Platform", version="2.0")
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

LANDING_HTML = """<!DOCTYPE html><html><head><title>HMP Stress-Test</title></head><body>
<h1>HMP Stress-Test Platform</h1><form action='/analyze' method='post' enctype='multipart/form-data'>
<input type='file' name='file' accept='.pdf' required/><button type='submit'>Analyze</button></form></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def landing():
    return HTMLResponse(content=LANDING_HTML)


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) < 1000:
        raise HTTPException(status_code=400, detail="File appears too small to be a valid HMP.")
    if len(pdf_bytes) > 200 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 200 MB limit.")

    extraction = extract_hmp(pdf_bytes)
    if not extraction.full_text or len(extraction.full_text.strip()) < 200:
        raise HTTPException(status_code=422, detail="Could not extract sufficient text from the PDF.")

    analysis = analyze_hmp(extraction)
    stress_results = run_all_stress_tests(extraction.full_text)
    analysis.stress_test_results = stress_results

    report_html = generate_html_report(analysis, stress_results, extraction)
    return HTMLResponse(content=report_html)


@app.post("/api/analyze")
async def analyze_api(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    extraction = extract_hmp(pdf_bytes)
    analysis = analyze_hmp(extraction)
    stress_results = run_all_stress_tests(extraction.full_text)

    return JSONResponse(
        content={
            "county": analysis.county_name,
            "state": analysis.state_name,
            "plan_title": analysis.plan_title,
            "overall_score": analysis.overall_score,
            "overall_grade": analysis.overall_grade,
            "section_scores": analysis.section_scores,
            "critical_gaps": analysis.critical_gaps[:20],
            "strengths": analysis.strengths[:15],
            "prescriptions": analysis.prescriptions,
            "director_briefing": analysis.director_briefing,
            "fema_compliance": {
                "score": analysis.fema_compliance.get("overall_score"),
                "met": analysis.fema_compliance.get("met"),
                "total": analysis.fema_compliance.get("total_requirements"),
                "gaps": analysis.fema_compliance.get("critical_gaps"),
            },
            "bric_readiness": {
                "score": analysis.bric_alignment.get("overall_score"),
                "strands": {k: v["score"] for k, v in analysis.bric_alignment.get("strands", {}).items()},
            },
            "equity_score": analysis.equity_assessment.get("overall_score"),
            "climate_score": analysis.climate_assessment.get("overall_score"),
            "hazard_coverage": analysis.hazard_analysis.get("coverage_pct"),
            "stress_tests": [
                {
                    "id": sr.scenario_id,
                    "name": sr.scenario_name,
                    "score": sr.overall_score,
                    "grade": sr.grade,
                    "passed": sr.checks_passed,
                    "total": sr.checks_total,
                    "failures": [f["consequence"] for f in sr.failures],
                }
                for sr in stress_results
            ],
            "extraction_quality": extraction.extraction_quality,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
