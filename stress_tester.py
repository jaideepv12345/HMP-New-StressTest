"""
stress_tester.py
Runs realistic disaster scenarios against the HMP to identify
where the plan would fail under pressure.
"""

import re
from dataclasses import dataclass


@dataclass
class StressScenario:
    id: str
    name: str
    category: str
    narrative: str
    checks: list
    severity: str


SCENARIOS = [
    StressScenario(
        id="S1",
        name="Compound Flood + Infrastructure Failure",
        category="compound",
        severity="severe",
        narrative="A 500-year rainfall event overwhelms stormwater systems with cascading failures.",
        checks=[
            ("Dam/levee failure addressed", [r"dam\s+(?:failure|breach|break)", r"levee\s+(?:failure|breach|overtop)"], 15, "Plan has no protocol for dam/levee breach concurrent with flooding"),
            ("Critical infrastructure dependencies mapped", [r"(?:critical|essential)\s+(?:infrastructure|facilit)", r"(?:infrastructure|lifeline)\s+(?:dependenc|interdependenc)"], 20, "Plan does not map infrastructure interdependencies"),
            ("Backup power / generator strategy", [r"(?:backup|emergency|generator|standby)\s+(?:power|generator|electric)"], 15, "No backup power strategy for critical facilities"),
        ],
    ),
    StressScenario(
        id="S2",
        name="Climate-Accelerated Wildfire + Drought",
        category="climate",
        severity="severe",
        narrative="Extended drought creates extreme fire conditions.",
        checks=[
            ("Wildfire risk assessed", [r"wildfire", r"(?:wild|brush|forest)\s*fire"], 20, "Wildfire risk not assessed despite climate trends"),
            ("Drought-wildfire compound risk", [r"drought.*(?:fire|wildfire)", r"(?:fire|wildfire).*drought"], 15, "No analysis of drought-wildfire compound risk"),
            ("Climate projections for fire season", [r"(?:fire\s+season|fire\s+weather)\s+(?:lengthen|extend|increas|chang|project)"], 20, "No climate projections for future fire risk"),
        ],
    ),
]


@dataclass
class ScenarioResult:
    scenario_id: str
    scenario_name: str
    category: str
    severity: str
    narrative: str
    overall_score: int
    grade: str
    checks_passed: int
    checks_total: int
    findings: list
    failures: list
    survival_assessment: str


def _check_patterns(text: str, patterns: list) -> dict:
    matches = []
    for pat_str in patterns:
        pat = re.compile(pat_str, re.IGNORECASE)
        for m in pat.finditer(text):
            start = max(0, m.start() - 100)
            end = min(len(text), m.end() + 100)
            context = text[start:end].replace("\n", " ").strip()
            matches.append({"match": m.group(), "context": f"...{context}..."})
    return {"found": len(matches) > 0, "count": len(matches), "evidence": matches[:3]}


def run_stress_test(full_text: str, scenario: StressScenario) -> ScenarioResult:
    total_weight = sum(c[2] for c in scenario.checks)
    earned = 0
    findings = []
    failures = []
    passed = 0

    for label, patterns, weight, fail_consequence in scenario.checks:
        check = _check_patterns(full_text, patterns)
        score = min(100, check["count"] * 25) if check["found"] else 0
        earned += weight * (score / 100)
        findings.append({"label": label, "passed": check["found"], "score": score, "weight": weight, "evidence_count": check["count"], "evidence": check["evidence"]})

        if check["found"]:
            passed += 1
        else:
            failures.append({"check": label, "consequence": fail_consequence, "weight": weight})

    overall_score = round((earned / total_weight) * 100) if total_weight else 0
    grade = "PASS" if overall_score >= 70 else ("MARGINAL" if overall_score >= 40 else "FAIL")

    if overall_score >= 80:
        survival = "The plan would likely perform adequately under this scenario."
    elif overall_score >= 50:
        survival = f"The plan would experience significant stress under this scenario. {len(failures)} critical response elements are missing."
    else:
        survival = f"THE PLAN WOULD LIKELY FAIL under this scenario. {len(failures)} out of {len(scenario.checks)} checks were not met."

    return ScenarioResult(scenario.id, scenario.name, scenario.category, scenario.severity, scenario.narrative, overall_score, grade, passed, len(scenario.checks), findings, failures, survival)


def run_all_stress_tests(full_text: str) -> list:
    return [run_stress_test(full_text, scenario) for scenario in SCENARIOS]
