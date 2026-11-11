import io
import re
from typing import Dict, List, Tuple
from pypdf import PdfReader
import docx

SECTION_PATTERNS = {
    "summary": r"\b(professional summary|summary|profile|about me|objective)\b",
    "experience": r"\b(work experience|experience|employment history|work history|professional experience)\b",
    "education": r"\b(education|academic background|qualifications|academic history)\b",
    "skills": r"\b(skills|technical skills|competencies|core competencies|technologies)\b",
    "projects": r"\b(projects|personal projects|key projects|academic projects)\b",
    "certifications": r"\b(certifications|certificates|licenses|courses)\b",
}


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts raw text from PDF file bytes."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text = []
    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            pages_text.append(txt)
    return "\n".join(pages_text).strip()


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
    """Parses text based on file extension."""
    ext = file_name.split(".")[-1].lower()
    if ext == "pdf":
        text = extract_text_from_pdf(file_bytes)
    elif ext in ["docx", "doc"]:
        text = extract_text_from_docx(file_bytes)
    elif ext == "txt":
        text = extract_text_from_txt(file_bytes)
    else:
        raise ValueError(f"Unsupported file format '.{ext}'. Supported formats: PDF, DOCX, TXT.")
    
    if not text or len(text.strip()) < 30:
        raise ValueError("The uploaded document contains insufficient or empty text.")
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
        
        # Check if line matches a known section header
        found_section = None
        remaining_content = None
        for sec_name, pattern in SECTION_PATTERNS.items():
            # Check standalone header e.g. "Skills" or "Skills:"
            if re.match(f"^{pattern}[:\\s-]*$", stripped, re.IGNORECASE):
                found_section = sec_name
                break
            # Check inline header e.g. "Skills: Python, SQL..."
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

    strengths = []
    if "skills" in sections:
        strengths.append("Dedicated Skills section identified with clear technical terminology.")
    if "experience" in sections:
        strengths.append("Professional Work Experience is chronologically structured.")
    if "education" in sections:
        strengths.append("Academic qualifications and degrees properly outlined.")
    if word_count >= 300:
        strengths.append("Resume provides sufficient depth of career history and accomplishments.")

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
