"""
pdf_processor.py
Multi-method PDF extraction with quality validation.
Solves the garbled-text problem from SOPSentinel.
"""

import io
import logging
import re
from dataclasses import dataclass, field

import pdfplumber
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)


@dataclass
class PageContent:
    page_number: int
    text: str
    tables: list = field(default_factory=list)
    quality_score: float = 0.0


@dataclass
class ExtractionResult:
    county_name: str
    state_name: str
    plan_title: str
    pages: list
    full_text: str
    section_map: dict
    metadata: dict = field(default_factory=dict)
    extraction_quality: float = 0.0


_GARBLE_PATTERN = re.compile(r"[^\x20-\x7E\n\r\t]")
_WORD_PATTERN = re.compile(r"[a-zA-Z]{3,}")
_DOT_FILL = re.compile(r"\.{4,}")


def _text_quality(text: str) -> float:
    if not text or len(text.strip()) < 20:
        return 0.0
    cleaned = _GARBLE_PATTERN.sub(" ", text)
    tokens = cleaned.split()
    if not tokens:
        return 0.0
    good = sum(1 for token in tokens if _WORD_PATTERN.search(token))
    return round(good / len(tokens), 3)


def _clean_text(text: str) -> str:
    text = _DOT_FILL.sub(" ", text)
    text = _GARBLE_PATTERN.sub(" ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_COUNTY_PATTERNS = [
    re.compile(
        r"(?:^|\s)([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+County\s+(?:Multi[- ]?Jurisdictional\s+)?Hazard\s+Mitigation\s+Plan",
        re.MULTILINE,
    ),
    re.compile(r"County\s*:\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)", re.MULTILINE),
    re.compile(
        r"(?:^|\s)([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+County,?\s+(?:NC|North Carolina|SC|TX|FL|CA|GA|AL|MS|LA|TN|VA|NY|OH|PA|IL)",
        re.MULTILINE,
    ),
    re.compile(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+County\s+Hazard", re.MULTILINE),
]

_STATE_ABBREVS = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


def _detect_county(text: str) -> str:
    for pattern in _COUNTY_PATTERNS:
        match = pattern.search(text[:5000])
        if match:
            return match.group(1).strip()
    return "Unknown"


def _detect_state(text: str) -> str:
    chunk = text[:5000]
    for _, full in _STATE_ABBREVS.items():
        if full in chunk:
            return full
    match = re.search(r"County,?\s+(" + "|".join(_STATE_ABBREVS.keys()) + r")\b", chunk)
    if match:
        return _STATE_ABBREVS.get(match.group(1), match.group(1))
    return "Unknown"


_SECTION_HEADERS = [
    ("Planning Process", r"(?:section\s*\d*[:\.]?\s*)?planning\s+process"),
    ("Community Profile", r"(?:section\s*\d*[:\.]?\s*)?community\s+profile"),
    ("Hazard Identification", r"(?:section\s*\d*[:\.]?\s*)?hazard\s+identification"),
    ("Hazard Profiles", r"(?:section\s*\d*[:\.]?\s*)?hazard\s+profiles?"),
    (
        "Risk Assessment",
        r"(?:section\s*\d*[:\.]?\s*)?(?:risk|vulnerability)\s+assessment",
    ),
    ("Capability Assessment", r"(?:section\s*\d*[:\.]?\s*)?capability\s+assessment"),
    ("Mitigation Strategy", r"(?:section\s*\d*[:\.]?\s*)?mitigation\s+strategy"),
    ("Mitigation Action Plan", r"(?:section\s*\d*[:\.]?\s*)?mitigation\s+action\s+plan"),
    ("Plan Maintenance", r"(?:section\s*\d*[:\.]?\s*)?plan\s+maintenance"),
    ("Plan Adoption", r"(?:section\s*\d*[:\.]?\s*)?plan\s+adoption"),
    ("Introduction", r"(?:section\s*\d*[:\.]?\s*)?introduction"),
]


def _detect_sections(pages: list) -> dict:
    found = {}
    for section_name, section_pattern in _SECTION_HEADERS:
        pattern = re.compile(section_pattern, re.IGNORECASE)
        for page in pages:
            if pattern.search(page.text):
                if section_name not in found:
                    found[section_name] = [page.page_number, page.page_number]
                else:
                    found[section_name][1] = page.page_number
    return {key: tuple(value) for key, value in found.items()}


def _extract_with_pdfplumber(pdf_bytes: bytes) -> list:
    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            raw = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            tables = page.extract_tables() or []
            cleaned = _clean_text(raw)
            quality = _text_quality(cleaned)
            pages.append(
                PageContent(
                    page_number=i + 1,
                    text=cleaned,
                    tables=tables,
                    quality_score=quality,
                )
            )
    return pages


def _extract_with_pypdf2(pdf_bytes: bytes) -> list:
    pages = []
    reader = PdfReader(io.BytesIO(pdf_bytes))
    for i, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        cleaned = _clean_text(raw)
        quality = _text_quality(cleaned)
        pages.append(
            PageContent(
                page_number=i + 1,
                text=cleaned,
                tables=[],
                quality_score=quality,
            )
        )
    return pages


def extract_hmp(pdf_bytes: bytes) -> ExtractionResult:
    try:
        pages = _extract_with_pdfplumber(pdf_bytes)
        avg_q = sum(page.quality_score for page in pages) / max(len(pages), 1)
        logger.info("pdfplumber extraction: %s pages, avg quality %.2f", len(pages), avg_q)
    except Exception as exc:
        logger.warning("pdfplumber failed: %s", exc)
        pages = []
        avg_q = 0.0

    if avg_q < 0.4:
        try:
            pages_fallback = _extract_with_pypdf2(pdf_bytes)
            avg_q_fallback = sum(page.quality_score for page in pages_fallback) / max(
                len(pages_fallback), 1
            )
            logger.info("PyPDF2 fallback: %s pages, avg quality %.2f", len(pages_fallback), avg_q_fallback)
            if avg_q_fallback > avg_q:
                pages = pages_fallback
                avg_q = avg_q_fallback
        except Exception as exc:
            logger.warning("PyPDF2 also failed: %s", exc)

    full_text = "\n\n".join(f"[PAGE {page.page_number}]\n{page.text}" for page in pages if page.text.strip())

    county = _detect_county(full_text)
    state = _detect_state(full_text)
    title_match = re.search(
        r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*\s+County\s+(?:Multi[- ]?Jurisdictional\s+)?Hazard\s+Mitigation\s+Plan)",
        full_text[:5000],
    )
    plan_title = title_match.group(1) if title_match else f"{county} County Hazard Mitigation Plan"

    section_map = _detect_sections(pages)

    return ExtractionResult(
        county_name=county,
        state_name=state,
        plan_title=plan_title,
        pages=pages,
        full_text=full_text,
        section_map=section_map,
        metadata={
            "total_pages": len(pages),
            "extraction_method": "pdfplumber" if avg_q >= 0.4 else "PyPDF2",
        },
        extraction_quality=avg_q,
    )
