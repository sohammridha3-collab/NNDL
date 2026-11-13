"""
Resume and document text extractor, section analyzer, and profile parser.
Handles PDF/DOCX parsing, scanned file detection with recovery guidance,
non-overlapping employment history calculation, role title detection,
and qualification classification (required vs. preferred).
"""
from datetime import datetime, timezone
import io
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from pypdf import PdfReader
import docx

from app.ml.preprocessing import DEFAULT_SKILLS, extract_skills

SECTION_PATTERNS = {
    "summary": r"\b(professional summary|summary|profile|about me|objective|career objective)\b",
    "experience": r"\b(work experience|experience|employment history|work history|professional experience|career history)\b",
    "education": r"\b(education|academic background|qualifications|academic history|degrees)\b",
    "skills": r"\b(skills|technical skills|competencies|core competencies|technologies|tools & technologies)\b",
    "projects": r"\b(projects|personal projects|key projects|academic projects|technical projects)\b",
    "certifications": r"\b(certifications|certificates|licenses|courses|accreditations)\b",
}

MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12
}

COMMON_ROLE_PATTERNS = [
    r"\b(?:senior|lead|principal|staff|junior|associate|chief)?\s*(?:full\s*stack|frontend|front-end|backend|back-end|software|web|mobile|ios|android|python|java|cloud|devops|data|ml|ai|machine learning|deep learning|qa|test|automation|site reliability|sre|security|systems?)\s+(?:developer|engineer|architect|programmer|specialist|consultant|analyst)\b",
    r"\b(?:data scientist|data analyst|business analyst|product manager|project manager|scrum master|technical lead|tech lead|engineering manager|solution architect|database administrator|dba)\b",
]


class ScannedDocumentError(ValueError):
    """Raised when an uploaded document appears to be a scanned image with no selectable text."""
    def __init__(self, message: str, recovery_message: str):
        super().__init__(message)
        self.recovery_message = recovery_message
        self.is_scanned = True


def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, bool]:
    """
    Extracts raw text from PDF file bytes.
    Returns (extracted_text, is_scanned_flag).
    Detects scanned or image-only documents where pages exist but extractable text is absent.
    """
    reader = PdfReader(io.BytesIO(file_bytes))
    num_pages = len(reader.pages)
    pages_text = []

    for page in reader.pages:
        txt = page.extract_text() or ""
        if txt.strip():
            pages_text.append(txt.strip())

    combined_text = "\n".join(pages_text).strip()

    # Scanned document detection: PDF has pages, but text is virtually empty (< 35 chars across entire file)
    is_scanned = num_pages > 0 and len(combined_text) < 35
    return combined_text, is_scanned


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extracts raw text from DOCX file bytes."""
    doc = docx.Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                paragraphs.append(row_text)
    return "\n".join(paragraphs).strip()


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Extracts raw text from TXT file bytes."""
    try:
        return file_bytes.decode("utf-8").strip()
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1", errors="ignore").strip()


def extract_resume_text(file_bytes: bytes, file_name: str) -> str:
    """
    Parses text based on file extension.
    Detects unreadable/scanned files and raises ScannedDocumentError with actionable recovery options.
    """
    ext = file_name.split(".")[-1].lower()
    is_scanned = False
    text = ""

    if ext == "pdf":
        text, is_scanned = extract_text_from_pdf(file_bytes)
    elif ext in ["docx", "doc"]:
        text = extract_text_from_docx(file_bytes)
    elif ext == "txt":
        text = extract_text_from_txt(file_bytes)
    else:
        raise ValueError(f"Unsupported file format '.{ext}'. Supported formats: PDF, DOCX, TXT.")

    if is_scanned:
        raise ScannedDocumentError(
            message="The uploaded PDF appears to be a scanned image with no selectable text.",
            recovery_message=(
                "Your document appears to be a scanned image or non-selectable PDF. "
                "Please upload a searchable text-based PDF/DOCX file, or paste your résumé text "
                "directly into the text area below to continue."
            )
        )

    if not text or len(text.strip()) < 30:
        raise ValueError(
            "The uploaded document contains insufficient or empty text. "
            "Please paste your résumé text directly into the text box."
        )

    return text


def identify_sections(text: str) -> Dict[str, str]:
    """Identifies and splits major resume sections."""
    lines = text.splitlines()
    sections: Dict[str, List[str]] = {}
    current_section = "header"
    sections[current_section] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        found_section = None
        remaining_content = None
        for sec_name, pattern in SECTION_PATTERNS.items():
            if re.match(f"^{pattern}[:\\s-]*$", stripped, re.IGNORECASE):
                found_section = sec_name
                break
            m = re.match(f"^({pattern})[:\\s-]+(.*)$", stripped, re.IGNORECASE)
            if m:
                found_section = sec_name
                remaining_content = m.group(2).strip()
                break

        if found_section:
            current_section = found_section
            if current_section not in sections:
                sections[current_section] = []
            if remaining_content:
                sections[current_section].append(remaining_content)
        else:
            sections[current_section].append(stripped)

    return {sec: "\n".join(content) for sec, content in sections.items() if content}


def evaluate_resume_completeness(text: str, sections: Dict[str, str]) -> Tuple[float, float, List[str], List[str], List[str]]:
    """
    Evaluates ATS score, completeness score, identified sections, missing sections, and suggestions.
    """
    critical_sections = ["experience", "education", "skills"]
    optional_sections = ["summary", "projects", "certifications"]

    present_critical = [s for s in critical_sections if s in sections and len(sections[s].strip()) > 5]
    present_optional = [s for s in optional_sections if s in sections and len(sections[s].strip()) > 5]
    missing_critical = [s for s in critical_sections if s not in present_critical]

    # Completeness calculation
    completeness = (len(present_critical) * 25.0) + (len(present_optional) * 8.33)
    completeness = min(100.0, round(completeness, 1))

    # ATS formatting readability check
    ats_score = 50.0  # Base score for valid parsable text
    word_count = len(text.split())
    if 250 <= word_count <= 1200:
        ats_score += 20.0
    elif word_count > 40:
        ats_score += 15.0

    ats_score += len(present_critical) * 8.0
    ats_score += len(present_optional) * 2.0
    ats_score = min(100.0, round(ats_score, 1))

    recommendations = []
    for miss in missing_critical:
        recommendations.append(f"Add a distinct '{miss.capitalize()}' section to ensure ATS parser recognition.")
    if "projects" not in sections:
        recommendations.append("Consider adding a 'Projects' section showcasing real-world technical impact.")
    if "summary" not in sections:
        recommendations.append("Add a 2-3 line Professional Summary highlighting your career focus.")
    if word_count < 250:
        recommendations.append("Resume length is under 250 words; consider detailing project achievements.")

    return ats_score, completeness, list(sections.keys()), missing_critical, recommendations


def parse_month_year(date_str: str) -> Optional[int]:
    """
    Converts a date string (e.g. 'Jan 2020', '03/2021', '2019', 'Present')
    into a continuous month index (year * 12 + month).
    """
    cleaned = date_str.strip().lower()
    if not cleaned:
        return None

    now = datetime.now(timezone.utc)
    if cleaned in ("present", "current", "now", "till date", "till today", "ongoing"):
        return now.year * 12 + now.month

    # Pattern: "Jan 2020" or "January 2020"
    m_txt = re.search(r'([a-z]+)\.?\s+(\d{4})', cleaned)
    if m_txt:
        month_name = m_txt.group(1)[:3]
        year = int(m_txt.group(2))
        month = MONTH_MAP.get(month_name, 6)
        if 1970 <= year <= now.year + 2:
            return year * 12 + month

    # Pattern: "2020-01" or "2020/01" (Year-Month)
    m_ym = re.search(r'\b(\d{4})[/\-\.](\d{1,2})\b', cleaned)
    if m_ym:
        year = int(m_ym.group(1))
        month = max(1, min(12, int(m_ym.group(2))))
        if 1970 <= year <= now.year + 2:
            return year * 12 + month

    # Pattern: "01/2020" or "1-2020" (Month-Year)
    m_num = re.search(r'\b(\d{1,2})[/\-\.](\d{4})\b', cleaned)
    if m_num:
        month = max(1, min(12, int(m_num.group(1))))
        year = int(m_num.group(2))
        if 1970 <= year <= now.year + 2:
            return year * 12 + month

    # Pattern: Year only e.g. "2020"
    m_yr = re.search(r'\b(19\d{2}|20\d{2})\b', cleaned)
    if m_yr:
        year = int(m_yr.group(1))
        return year * 12 + 6  # Mid-year approximation

    return None


def merge_date_intervals(intervals: List[Tuple[int, int]]) -> Tuple[List[Tuple[int, int]], int]:
    """
    Merges overlapping or contiguous month intervals.
    Guarantees mathematically that concurrent or overlapping employment periods
    are NEVER double-counted.
    Returns (merged_intervals, total_non_overlapping_months).
    """
    if not intervals:
        return [], 0

    # Filter invalid
    valid = [iv for iv in intervals if iv[0] is not None and iv[1] is not None and iv[0] <= iv[1]]
    if not valid:
        return [], 0

    valid.sort(key=lambda x: (x[0], x[1]))
    merged = [valid[0]]

    for current in valid[1:]:
        prev_start, prev_end = merged[-1]
        if current[0] <= prev_end + 1:
            merged[-1] = (prev_start, max(prev_end, current[1]))
        else:
            merged.append(current)

    total_months = sum((end - start + 1) for start, end in merged)
    return merged, total_months


def parse_employment_history(experience_text: str, full_text: str) -> Tuple[List[Dict[str, Any]], float]:
    """
    Extracts individual employment history entries and calculates total non-overlapping experience.
    Strictly avoids double-counting overlapping jobs or inventing experience.
    """
    target_text = experience_text if len(experience_text.strip()) > 30 else full_text
    lines = [line.strip() for line in target_text.splitlines() if line.strip()]

    # Date range regex pattern
    date_range_regex = re.compile(
        r'((?:[a-zA-Z]{3,9}\.?\s+)?\d{4}|\d{1,2}[/\-\.]\d{4}|\d{4}[/\-\.]\d{1,2})'
        r'\s*(?:[\-–—]|to|until)\s*'
        r'((?:[a-zA-Z]{3,9}\.?\s+)?\d{4}|\d{1,2}[/\-\.]\d{4}|\d{4}[/\-\.]\d{1,2}|present|current|now|till date)',
        re.IGNORECASE
    )

    entries: List[Dict[str, Any]] = []
    intervals: List[Tuple[int, int]] = []

    for i, line in enumerate(lines):
        match = date_range_regex.search(line)
        if match:
            start_str = match.group(1).strip()
            end_str = match.group(2).strip()

            start_idx = parse_month_year(start_str)
            end_idx = parse_month_year(end_str)

            if start_idx and end_idx and start_idx <= end_idx:
                intervals.append((start_idx, end_idx))
                duration_m = end_idx - start_idx + 1

                # Infer job title and company from surrounding lines
                title = "Software Professional"
                company = "Verified Organization"

                # Check current line without dates
                remainder = date_range_regex.sub('', line).strip(' |-,•–')
                context_lines = []
                if i > 0:
                    context_lines.append(lines[i - 1])
                if remainder:
                    context_lines.append(remainder)
                if i + 1 < len(lines):
                    context_lines.append(lines[i + 1])

                for ctx in context_lines:
                    # Detect title
                    for pat in COMMON_ROLE_PATTERNS:
                        m_role = re.search(pat, ctx, re.IGNORECASE)
                        if m_role and title == "Software Professional":
                            title = m_role.group(0).strip().title()

                    # Detect company pattern e.g. "at Google" or "Company, Inc."
                    m_comp = re.search(r'\bat\s+([A-Z][A-Za-z0-9&., ]+)', ctx)
                    if m_comp:
                        company = m_comp.group(1).strip()
                    elif re.search(r'\b(Inc\.?|Ltd\.?|LLC|Technologies|Solutions|Services|Corp\.?|Infotech|Labs)\b', ctx, re.IGNORECASE):
                        company = ctx.strip(' •-,')

                entries.append({
                    "title": title,
                    "company": company,
                    "start_date": start_str,
                    "end_date": end_str,
                    "duration_months": duration_m,
                    "description": line
                })

    # Non-overlapping tenure calculation
    _, total_months = merge_date_intervals(intervals)
    total_years = round(total_months / 12.0, 1) if total_months > 0 else 0.0

    return entries, total_years


def detect_role_titles(text: str) -> List[str]:
    """Detects candidate job titles mentioned across the resume text."""
    found_titles: Set[str] = set()
    for pat in COMMON_ROLE_PATTERNS:
        matches = re.finditer(pat, text, re.IGNORECASE)
        for m in matches:
            t = m.group(0).strip().title()
            if len(t) > 3 and not any(w in t.lower() for w in ["looking for", "seeking"]):
                found_titles.add(t)

    # Sort by frequency/relevance
    return sorted(list(found_titles), key=lambda x: -len(x))[:5]


def classify_job_qualifications(job_text: str) -> Dict[str, List[str]]:
    """
    Separates job qualifications into:
    - required: must have, required, essential, minimum years
    - preferred: nice to have, plus, preferred, bonus, optional
    - general: general technical requirements
    """
    required_skills: Set[str] = set()
    preferred_skills: Set[str] = set()
    general_skills: Set[str] = set()

    all_skills = extract_skills(job_text.lower(), DEFAULT_SKILLS)
    lines = [line.strip() for line in job_text.splitlines() if line.strip()]

    req_pattern = re.compile(r'\b(must have|required|essential|minimum|prerequisite|proficiency in|mandatory)\b', re.IGNORECASE)
    pref_pattern = re.compile(r'\b(nice to have|plus|preferred|bonus|optional|advantage|familiarity with)\b', re.IGNORECASE)

    for line in lines:
        line_skills = extract_skills(line.lower(), DEFAULT_SKILLS)
        if not line_skills:
            continue

        if req_pattern.search(line):
            required_skills.update(line_skills)
        elif pref_pattern.search(line):
            preferred_skills.update(line_skills)
        else:
            general_skills.update(line_skills)

    # Clean up overlaps
    general_skills = general_skills - required_skills - preferred_skills

    return {
        "required": sorted(list(required_skills)),
        "preferred": sorted(list(preferred_skills)),
        "general": sorted(list(general_skills or all_skills))
    }


def extract_resume_profile_summary(
    file_bytes: Optional[bytes] = None,
    file_name: Optional[str] = None,
    text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Produces a complete structured candidate profile summary from an uploaded file or text.
    Provides clear scanned document recovery options, detects roles, and non-overlapping tenure.
    """
    raw_text = text or ""
    is_scanned = False
    recovery_needed = False
    recovery_message = None

    if file_bytes and file_name:
        try:
            raw_text = extract_resume_text(file_bytes, file_name)
        except ScannedDocumentError as e:
            is_scanned = True
            recovery_needed = True
            recovery_message = e.recovery_message
            raw_text = ""
        except ValueError as e:
            recovery_needed = True
            recovery_message = str(e)
            raw_text = ""

    if not raw_text or len(raw_text.strip()) < 30:
        return {
            "readable": False,
            "is_scanned": is_scanned,
            "recovery_needed": True,
            "recovery_message": recovery_message or "Document contains insufficient extractable text. Please paste résumé text.",
            "raw_text": raw_text,
            "summary": None,
            "primary_role": None,
            "detected_titles": [],
            "skills": [],
            "total_experience_years": 0.0,
            "employment_history": [],
            "education": [],
            "detected_location": None,
        }

    sections = identify_sections(raw_text)
    exp_text = sections.get("experience", "")
    summary_text = sections.get("summary") or (raw_text.splitlines()[0] if raw_text.splitlines() else None)

    # Skills
    extracted_skills = sorted(list(extract_skills(raw_text.lower(), DEFAULT_SKILLS)))

    # Roles
    detected_titles = detect_role_titles(raw_text)
    primary_role = detected_titles[0] if detected_titles else "Software Engineer"

    # Employment history with non-overlapping tenure calculation
    employment_history, total_experience_years = parse_employment_history(exp_text, raw_text)

    # Education
    edu_text = sections.get("education", "")
    edu_items = [line.strip(' •-,') for line in edu_text.splitlines() if len(line.strip()) > 5][:3]

    # Inferred location
    detected_location = None
    loc_match = re.search(r'\b(Kolkata|Delhi|New Delhi|Bengaluru|Bangalore|Mumbai|Pune|Hyderabad|Chennai|Noida|Gurgaon|London|New York|Remote)\b', raw_text, re.IGNORECASE)
    if loc_match:
        detected_location = loc_match.group(1).title()

    return {
        "readable": True,
        "is_scanned": False,
        "recovery_needed": False,
        "recovery_message": None,
        "raw_text": raw_text,
        "summary": summary_text[:300] if summary_text else None,
        "primary_role": primary_role,
        "detected_titles": detected_titles,
        "skills": extracted_skills,
        "total_experience_years": total_experience_years,
        "employment_history": employment_history,
        "education": edu_items,
        "detected_location": detected_location,
    }
