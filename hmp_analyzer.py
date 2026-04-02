"""
hmp_analyzer.py
Comprehensive HMP analysis against FEMA 44 CFR 201.6, BRIC, equity, and climate criteria.
Uses pattern-based analysis + optional LLM for deep semantic review.
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    county_name: str
    state_name: str
    plan_title: str
    overall_score: int
    overall_grade: str
    fema_compliance: dict = field(default_factory=dict)
    bric_alignment: dict = field(default_factory=dict)
    equity_assessment: dict = field(default_factory=dict)
    climate_assessment: dict = field(default_factory=dict)
    hazard_analysis: dict = field(default_factory=dict)
    stress_test_results: list = field(default_factory=list)
    critical_gaps: list = field(default_factory=list)
    strengths: list = field(default_factory=list)
    prescriptions: list = field(default_factory=list)
    director_briefing: str = ""
    section_scores: dict = field(default_factory=dict)
    extraction_quality: float = 0.0


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


FEMA_REQUIREMENTS = [
    ("A1", "Multi-jurisdictional participation documented", "44 CFR 201.6(a)(3)", [r"multi[- ]?jurisdictional", r"participating\s+jurisdictions?", r"jurisdictions?\s+participat"], 8),
    ("A2", "Planning process description", "44 CFR 201.6(b)(1)", [r"planning\s+process", r"plan\s+development\s+process", r"how\s+the\s+plan\s+was\s+(?:developed|prepared)"], 8),
    ("A3", "Public participation/involvement", "44 CFR 201.6(b)(1)", [r"public\s+(?:participation|involvement|input|comment|meeting|hearing)", r"stakeholder\s+(?:engagement|involvement|input)", r"community\s+(?:meeting|workshop|survey|engagement)"], 8),
    ("A4", "Neighboring community coordination", "44 CFR 201.6(b)(2)", [r"neighbor(?:ing)?\s+(?:communit|jurisdict|count)", r"regional\s+coordination", r"adjacent\s+(?:count|jurisdict)"], 5),
    ("A5", "Review/incorporation of existing plans & studies", "44 CFR 201.6(b)(3)", [r"(?:existing|other|related)\s+(?:plans?|studies|programs?|policies)", r"comprehensive\s+plan", r"land\s+use\s+plan", r"building\s+codes?", r"capital\s+improvement", r"floodplain\s+(?:management|ordinance)"], 7),
    ("B1", "Natural hazards identified", "44 CFR 201.6(c)(2)(i)", [r"(?:natural\s+)?hazards?\s+(?:identified|identification)", r"flood|hurricane|tornado|earthquake|wildfire|drought|winter\s+storm"], 10),
    ("B2", "Hazard descriptions/profiles", "44 CFR 201.6(c)(2)(i)", [r"hazard\s+profile", r"hazard\s+description", r"(?:history|frequency|probability)\s+of\s+(?:occurrence|events?)"], 8),
    ("B3", "Vulnerability assessment", "44 CFR 201.6(c)(2)(ii)", [r"vulnerability\s+assessment", r"(?:types?|number)\s+of\s+(?:existing|future)\s+(?:buildings?|structures?|infrastructure)", r"potential\s+(?:dollar\s+)?loss(?:es)?", r"damage\s+estimates?"], 10),
    ("B4", "Repetitive loss properties identified", "44 CFR 201.6(c)(2)(ii)", [r"repetitive\s+loss", r"severe\s+repetitive\s+loss", r"NFIP\s+(?:claims?|polic)", r"flood\s+insurance\s+claims?"], 7),
    ("B5", "Future development impact on vulnerability", "44 CFR 201.6(c)(2)(ii)", [r"(?:future|projected|planned)\s+(?:development|growth|land\s+use)", r"(?:increase|decrease)\s+(?:in\s+)?vulnerability", r"development\s+trends?", r"growth\s+(?:areas?|patterns?)"], 8),
    ("C1", "Goals and objectives stated", "44 CFR 201.6(c)(3)(i)", [r"(?:mitigation\s+)?(?:goals?|objectives?)\s", r"goal\s*\d", r"objective\s*\d"], 8),
    ("C2", "Comprehensive range of mitigation actions", "44 CFR 201.6(c)(3)(ii)", [r"mitigation\s+(?:actions?|measures?|projects?|activities?)", r"(?:structural|non[- ]?structural)\s+(?:mitigation|measures?)", r"acquisition|elevation|retrofit|drainage|warning\s+system"], 10),
    ("C3", "Actions prioritized / implementation timeline", "44 CFR 201.6(c)(3)(iii)", [r"prioriti[sz](?:ed|ation)", r"implementation\s+(?:timeline|schedule|timeframe)", r"(?:high|medium|low)\s+priority", r"responsible\s+(?:party|department|agency)"], 8),
    ("C4", "Benefit-cost review described", "44 CFR 201.6(c)(3)(iii)", [r"benefit[- ]?cost", r"cost[- ]?(?:benefit|effective)", r"STAPLEE", r"(?:economic|financial)\s+(?:analysis|feasibility)"], 6),
    ("C5", "NFIP participation documented", "44 CFR 201.6(c)(3)(ii)", [r"(?:National\s+)?Flood\s+Insurance\s+Program", r"NFIP", r"(?:flood\s+)?insurance\s+(?:rate\s+map|polic)", r"Community\s+Rating\s+System|CRS"], 7),
    ("D1", "Monitoring/evaluation/update process", "44 CFR 201.6(c)(4)(i)", [r"(?:plan\s+)?(?:monitor|evaluat|update|review)\s+(?:process|method|schedule|procedures?)", r"(?:annual|periodic|regular)\s+(?:review|evaluation|update)", r"five[- ]?year\s+(?:update|cycle|review)"], 8),
    ("D2", "Continued public participation", "44 CFR 201.6(c)(4)(ii)", [r"continued?\s+public\s+(?:participation|involvement)", r"(?:ongoing|future)\s+(?:public|stakeholder)\s+(?:participation|engagement)", r"public\s+(?:access|review|comment)\s+(?:to|on|of)\s+(?:the\s+)?plan"], 5),
    ("D3", "Plan incorporation into other mechanisms", "44 CFR 201.6(c)(4)(iii)", [r"incorporat(?:e|ion|ing)\s+(?:into|with)\s+(?:other|existing)\s+(?:planning|mechanisms?|processes?)", r"(?:comprehensive|land\s+use|capital)\s+plan(?:ning)?", r"building\s+codes?|zoning|subdivision\s+(?:regulations?|ordinances?)"], 7),
    ("E1", "Adoption by governing body", "44 CFR 201.6(d)(1)", [r"adopt(?:ed|ion)", r"(?:resolution|ordinance)\s+(?:number|no\.?|#)", r"(?:board|council|commission)\s+(?:of\s+)?(?:commissioners?|supervisors?)", r"governing\s+body"], 8),
]

BRIC_CRITERIA = {
    "innovation": {"label": "Innovation & Technology", "patterns": [r"innovat(?:ive|ion)", r"(?:new|emerging|advanced)\s+technolog", r"(?:GIS|geospatial|remote\s+sensing|LiDAR)", r"(?:smart|sensor|early\s+warning)", r"nature[- ]?based\s+solution", r"green\s+infrastructure"], "weight": 25},
    "maintenance": {"label": "Plan Maintenance & Implementation", "patterns": [r"(?:plan\s+)?maintenance", r"implementation\s+(?:status|progress|tracking)", r"(?:action|project)\s+(?:status|completion|update)", r"(?:annual|periodic)\s+(?:review|report)", r"progress\s+report"], "weight": 25},
    "climate": {"label": "Climate Change & Future Conditions", "patterns": [r"climate\s+change", r"(?:sea[- ]?level|temperature)\s+(?:rise|increase|projection)", r"(?:future|projected)\s+(?:climate|conditions?|precipitation|rainfall)", r"(?:RCP|SSP|IPCC|climate\s+model|climate\s+scenario|climate\s+projection)", r"(?:compound|cascading|concurrent)\s+(?:hazard|risk|event|disaster)"], "weight": 25},
    "equity": {"label": "Equity & Community Lifelines", "patterns": [r"(?:social\s+)?vulnerab(?:le|ility)\s+(?:index|popul|communit|SVI)", r"(?:environmental|social)\s+justice", r"Justice\s*40", r"(?:disadvantaged|underserved|marginalized|vulnerable)\s+(?:communit|popul|area)", r"(?:limited\s+English|LEP|language\s+access|multilingual)", r"(?:ADA|accessibility|disabled|disabilit)", r"(?:low[- ]?income|poverty|affordable|housing\s+insecur)", r"community\s+lifelines?"], "weight": 25},
}

EQUITY_CHECKS = [
    ("SVI Referenced", [r"Social\s+Vulnerability\s+Index", r"\bSVI\b", r"CDC[/\s]+(?:ATSDR\s+)?SVI"], "Social Vulnerability Index (SVI) helps identify which populations are most at risk."),
    ("Justice40 Framing", [r"Justice\s*40", r"Justice\s+Forty", r"40[- ]?percent\s+(?:of\s+)?benefit"], "Justice40 requires 40% of benefits flow to disadvantaged communities."),
    ("LEP / Multilingual Outreach", [r"(?:limited\s+English|LEP)", r"multilingual", r"(?:Spanish|language)\s+(?:access|translation|interpreter)", r"non[- ]?English\s+speak"], "Plans should address Limited English Proficiency populations."),
    ("ADA / Accessibility", [r"\bADA\b", r"Americans?\s+with\s+Disabilities", r"(?:wheelchair|mobility|hearing|visual)\s+(?:access|impair)", r"accessibility\s+(?:for|of|requirement)"], "Shelter and service accessibility for people with disabilities."),
    ("Low-Income / Poverty Analysis", [r"(?:low[- ]?income|poverty|below\s+poverty)", r"(?:affordable|subsidized)\s+housing", r"(?:economic|financial)\s+(?:hardship|vulnerability|disadvantag)"], "Analysis of how hazards disproportionately affect low-income populations."),
    ("Racial / Ethnic Equity", [r"(?:racial|ethnic)\s+(?:equity|disparit|minorit)", r"(?:African\s+American|Hispanic|Latino|Asian|Native\s+American)", r"(?:people|communities?)\s+of\s+color", r"BIPOC"], "Assessment of how hazards affect racial/ethnic minority communities."),
    ("Elderly / Age-Related Vulnerability", [r"(?:elderly|senior|aging|older\s+adult)", r"(?:nursing\s+home|assisted\s+living|age[- ]?related)", r"(?:65|over\s+65|age\s+65)"], "Special provisions for elderly populations who face elevated hazard risk."),
    ("CEJST / Screening Tool", [r"CEJST", r"Climate\s+(?:and\s+)?Economic\s+Justice\s+Screening", r"(?:environmental|climate)\s+justice\s+(?:screen|tool|map)"], "Use of federal screening tools to identify disadvantaged communities."),
]

CLIMATE_CHECKS = [
    ("Climate Change Acknowledged", [r"climate\s+change", r"global\s+warming", r"changing\s+climate"], True),
    ("Future Projections / Scenarios", [r"(?:climate|future)\s+(?:projection|scenario|model)", r"(?:RCP|SSP|IPCC)", r"(?:2050|2100|mid[- ]?century|end[- ]?of[- ]?century)"], True),
    ("Sea Level Rise (if coastal)", [r"sea[- ]?level\s+(?:rise|change|increase)", r"(?:coastal|tidal)\s+flood(?:ing)?", r"storm\s+surge\s+(?:projection|model)"], False),
    ("Extreme Precipitation Trends", [r"(?:extreme|heavy|intense)\s+(?:precipitation|rainfall)", r"(?:precipitation|rainfall)\s+(?:increase|trend|intensif)", r"(?:100|500)[- ]?year\s+(?:storm|flood|event)"], True),
    ("Temperature / Heat Analysis", [r"(?:extreme|excessive)\s+heat", r"heat\s+(?:wave|island|index|stress)", r"temperature\s+(?:increase|rise|trend|projection)"], False),
    ("Compound / Cascading Risks", [r"(?:compound|cascading|concurrent|simultaneous)\s+(?:hazard|risk|event|disaster)", r"(?:multi[- ]?hazard|complex\s+disaster)", r"(?:systemic|interconnected)\s+risk"], True),
    ("Wildfire-Climate Nexus", [r"(?:wildfire|fire)\s+(?:and|due\s+to|exacerbated\s+by)\s+(?:climate|drought|temperature)", r"(?:fire\s+season|fire\s+weather)\s+(?:lengthen|increas|chang)"], False),
    ("Plan Update Triggers", [r"(?:trigger|threshold|criterion|criteria)\s+(?:for|to)\s+(?:updat|revis|amend)", r"(?:when|conditions?\s+under\s+which)\s+(?:the\s+)?plan\s+(?:will|should|must)\s+be\s+(?:updat|revis)"], True),
]

HAZARD_TYPES = {
    "Flood": [r"\bflood(?:ing|s|plain)?\b", r"flash\s+flood", r"riverine\s+flood"],
    "Hurricane/Tropical": [r"hurricane", r"tropical\s+(?:storm|cyclone|depress)", r"storm\s+surge"],
    "Tornado": [r"tornado(?:es)?", r"funnel\s+cloud", r"twister"],
    "Thunderstorm/Wind": [r"thunderstorm", r"(?:severe|high|damaging)\s+wind", r"straight[- ]?line\s+wind", r"derecho"],
    "Winter Storm": [r"winter\s+storm", r"(?:ice|snow|blizzard|freezing\s+rain|sleet|nor.easter)"],
    "Drought": [r"\bdrought\b", r"water\s+(?:shortage|scarcity)"],
    "Extreme Heat": [r"extreme\s+heat", r"heat\s+(?:wave|advisory|emergency)", r"excessive\s+heat"],
    "Wildfire": [r"wildfire", r"(?:wild|brush|forest)\s*fire", r"wildland[- ]?urban\s+interface"],
    "Earthquake": [r"earthquake", r"seismic\s+(?:activity|risk|zone|hazard)"],
    "Dam Failure": [r"dam\s+(?:failure|break|breach)", r"(?:dam|levee)\s+(?:safety|risk)"],
    "Landslide": [r"landslide", r"(?:mudslide|debris\s+flow|slope\s+failure)"],
    "Haz-Mat": [r"hazardous\s+material", r"haz[- ]?mat", r"(?:chemical|industrial)\s+(?:spill|release|accident)"],
    "Nuclear": [r"nuclear\s+(?:accident|incident|facility|power\s+plant)", r"radiological"],
    "Pandemic": [r"pandemic", r"(?:infectious\s+disease|epidemic|public\s+health\s+emergency)", r"COVID"],
}


def _check_requirement(text: str, patterns: list) -> dict:
    matches = []
    for pattern_str in patterns:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        for match in pattern.finditer(text):
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            context = text[start:end].replace("\n", " ").strip()
            matches.append({"match": match.group(), "context": f"...{context}...", "position": match.start()})
    return {"found": len(matches) > 0, "match_count": len(matches), "evidence": matches[:3]}


def run_fema_compliance(full_text: str) -> dict:
    results = {}
    total_weight = 0
    earned_weight = 0

    for req_id, label, cfr_ref, patterns, weight in FEMA_REQUIREMENTS:
        check = _check_requirement(full_text, patterns)
        score = 100 if check["found"] else 0
        if check["found"] and check["match_count"] == 1:
            score = 60
        elif check["found"] and check["match_count"] == 2:
            score = 80

        results[req_id] = {
            "label": label,
            "cfr_reference": cfr_ref,
            "score": score,
            "found": check["found"],
            "evidence_count": check["match_count"],
            "evidence": check["evidence"],
            "weight": weight,
        }
        total_weight += weight
        earned_weight += weight * (score / 100)

    overall_pct = round((earned_weight / total_weight) * 100) if total_weight else 0
    gaps = [r for r in results.values() if not r["found"]]
    weak = [r for r in results.values() if r["found"] and r["score"] < 80]

    return {
        "overall_score": overall_pct,
        "requirements": results,
        "total_requirements": len(FEMA_REQUIREMENTS),
        "met": sum(1 for r in results.values() if r["found"]),
        "not_met": len(gaps),
        "weak": len(weak),
        "critical_gaps": [{"id": k, "label": v["label"], "cfr": v["cfr_reference"]} for k, v in results.items() if not v["found"]],
    }


def run_bric_analysis(full_text: str) -> dict:
    results = {}
    total = 0
    earned = 0
    for _, criteria in BRIC_CRITERIA.items():
        check = _check_requirement(full_text, criteria["patterns"])
        score = min(100, check["match_count"] * 20) if check["found"] else 0
        results[criteria["label"]] = {
            "label": criteria["label"],
            "score": score,
            "present": check["found"],
            "evidence_count": check["match_count"],
            "evidence": check["evidence"],
        }
        total += criteria["weight"]
        earned += criteria["weight"] * (score / 100)

    return {"overall_score": round((earned / total) * 100) if total else 0, "strands": {k.lower().replace(' & ', '_').replace(' ', '_'): v for k,v in results.items()}}


def run_equity_scan(full_text: str) -> dict:
    signals, gaps = [], []
    for label, patterns, description in EQUITY_CHECKS:
        check = _check_requirement(full_text, patterns)
        entry = {"label": label, "found": check["found"], "evidence_count": check["match_count"], "evidence": check["evidence"], "description": description}
        (signals if check["found"] else gaps).append(entry)
    score = round((len(signals) / len(EQUITY_CHECKS)) * 100) if EQUITY_CHECKS else 0
    return {"overall_score": score, "signals": signals, "gaps": gaps, "total_checks": len(EQUITY_CHECKS)}


def run_climate_assessment(full_text: str) -> dict:
    findings = []
    total_critical = 0
    met_critical = 0
    for label, patterns, is_critical in CLIMATE_CHECKS:
        check = _check_requirement(full_text, patterns)
        findings.append({"label": label, "found": check["found"], "critical": is_critical, "evidence": check["evidence"]})
        if is_critical:
            total_critical += 1
            if check["found"]:
                met_critical += 1
    met_total = sum(1 for f in findings if f["found"])
    score = round((met_total / len(findings)) * 100) if findings else 0
    return {"overall_score": score, "critical_score": round((met_critical / total_critical) * 100) if total_critical else 0, "findings": findings, "met": met_total, "total": len(findings)}


def run_hazard_analysis(full_text: str) -> dict:
    results = {}
    for hazard, patterns in HAZARD_TYPES.items():
        check = _check_requirement(full_text, patterns)
        depth = "Not addressed"
        if check["match_count"] >= 10:
            depth = "Thoroughly profiled"
        elif check["match_count"] >= 4:
            depth = "Adequately addressed"
        elif check["match_count"] >= 1:
            depth = "Briefly mentioned"
        results[hazard] = {"present": check["found"], "depth": depth, "mention_count": check["match_count"], "evidence": check["evidence"][:2]}

    addressed = sum(1 for v in results.values() if v["present"])
    return {"hazards": results, "total_types": len(HAZARD_TYPES), "addressed": addressed, "not_addressed": [k for k, v in results.items() if not v["present"]], "coverage_pct": round((addressed / len(HAZARD_TYPES)) * 100)}


def _build_director_briefing(county, overall, fema, bric, equity, climate, hazards, gaps, prescriptions) -> str:
    grade = _grade(overall)
    lines = [
        f"DIRECTOR'S BRIEFING — {county} County Hazard Mitigation Plan",
        "=" * 60,
        "",
        f"OVERALL ASSESSMENT: {grade} ({overall}/100)",
        "",
        "VITAL SIGNS:",
        f"  • FEMA Compliance:  {fema['overall_score']}%  ({fema['met']}/{fema['total_requirements']} requirements met)",
        f"  • BRIC Readiness:   {bric['overall_score']}%",
        f"  • Equity Readiness: {equity['overall_score']}%  ({len(equity.get('gaps', []))} gaps)",
        f"  • Climate Foresight:{climate['overall_score']}%  ({climate['met']}/{climate['total']} checks met)",
        f"  • Hazard Coverage:  {hazards['coverage_pct']}%  ({hazards['addressed']}/{hazards['total_types']} hazard types)",
        "",
        "TOP 3 CRITICAL GAPS:",
    ]
    for i, gap in enumerate((gaps or ["No critical gaps identified — maintain current trajectory."])[:3], 1):
        lines.append(f"  {i}. {gap}")
    lines.extend(["", "90-DAY ACTION PLAN:"])
    for i, rx in enumerate(prescriptions[:3], 1):
        lines.append(f"  {i}. [{rx['priority']}] {rx['action']} (Timeline: {rx['timeline']})")
    return "\n".join(lines)


def analyze_hmp(extraction) -> AnalysisResult:
    text = extraction.full_text
    fema = run_fema_compliance(text)
    bric = run_bric_analysis(text)
    equity = run_equity_scan(text)
    climate = run_climate_assessment(text)
    hazards = run_hazard_analysis(text)

    overall = round(fema["overall_score"] * 0.35 + bric["overall_score"] * 0.20 + equity["overall_score"] * 0.20 + climate["overall_score"] * 0.15 + hazards["coverage_pct"] * 0.10)

    critical_gaps = [f"FEMA COMPLIANCE: {gap['label']} ({gap['cfr']}) — NOT FOUND in plan text" for gap in fema.get("critical_gaps", [])]
    critical_gaps.extend([f"EQUITY GAP: {gap['label']} — {gap['description']}" for gap in equity.get("gaps", [])])
    critical_gaps.extend([f"CLIMATE GAP: {finding['label']} — Not addressed in plan" for finding in climate.get("findings", []) if finding["critical"] and not finding["found"]])
    critical_gaps.extend([f"HAZARD GAP: {hazard_name} — Not addressed or profiled" for hazard_name in hazards.get("not_addressed", [])])

    strengths = []
    if fema["overall_score"] >= 80:
        strengths.append(f"Strong FEMA compliance ({fema['overall_score']}%) — {fema['met']}/{fema['total_requirements']} requirements met")

    prescriptions = []
    if fema["not_met"] > 0:
        prescriptions.append({"priority": "CRITICAL", "action": f"Close {fema['not_met']} FEMA compliance gaps to maintain grant eligibility", "details": [g["label"] for g in fema.get("critical_gaps", [])[:5]], "timeline": "0-30 days"})
    if equity["overall_score"] < 60:
        prescriptions.append({"priority": "HIGH", "action": "Establish Equity Task Force to address missing equity criteria", "details": [g["label"] for g in equity.get("gaps", [])[:4]], "timeline": "30-60 days"})

    director_briefing = _build_director_briefing(extraction.county_name, overall, fema, bric, equity, climate, hazards, critical_gaps, prescriptions)

    return AnalysisResult(
        county_name=extraction.county_name,
        state_name=extraction.state_name,
        plan_title=extraction.plan_title,
        overall_score=overall,
        overall_grade=_grade(overall),
        fema_compliance=fema,
        bric_alignment=bric,
        equity_assessment=equity,
        climate_assessment=climate,
        hazard_analysis=hazards,
        critical_gaps=critical_gaps,
        strengths=strengths,
        prescriptions=prescriptions,
        director_briefing=director_briefing,
        section_scores={
            "FEMA Compliance": fema["overall_score"],
            "BRIC Readiness": bric["overall_score"],
            "Equity Readiness": equity["overall_score"],
            "Climate Foresight": climate["overall_score"],
            "Hazard Coverage": hazards["coverage_pct"],
        },
        extraction_quality=extraction.extraction_quality,
    )
