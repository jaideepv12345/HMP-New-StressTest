"""report_generator.py"""

from datetime import datetime


def generate_html_report(analysis, stress_results, extraction) -> str:
    county = analysis.county_name
    state = analysis.state_name
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    stress_items = "".join(
        f"<li><strong>{sr.scenario_id} {sr.scenario_name}</strong>: {sr.overall_score}% ({sr.grade})</li>"
        for sr in stress_results
    ) or "<li>No stress test results available.</li>"

    return f"""<!DOCTYPE html>
<html lang='en'>
<head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>HMP Stress-Test Report</title>
<style>body{{font-family:Arial,sans-serif;margin:2rem;line-height:1.5}}.card{{border:1px solid #ddd;padding:1rem;border-radius:8px;margin-bottom:1rem}}</style>
</head>
<body>
<h1>🛡️ HMP Stress-Test Report</h1>
<div class='card'>
<p><strong>County:</strong> {county} County, {state}</p>
<p><strong>Plan:</strong> {analysis.plan_title}</p>
<p><strong>Generated:</strong> {now}</p>
<p><strong>Overall:</strong> {analysis.overall_score}% ({analysis.overall_grade})</p>
<p><strong>Extraction quality:</strong> {round(extraction.extraction_quality*100)}%</p>
</div>
<div class='card'><h2>Section Scores</h2><ul>{''.join(f'<li>{k}: {v}%</li>' for k,v in analysis.section_scores.items())}</ul></div>
<div class='card'><h2>Critical Gaps</h2><ul>{''.join(f'<li>{g}</li>' for g in analysis.critical_gaps[:15]) or '<li>None</li>'}</ul></div>
<div class='card'><h2>Stress Test Results</h2><ul>{stress_items}</ul></div>
<pre class='card'>{analysis.director_briefing}</pre>
</body></html>"""
