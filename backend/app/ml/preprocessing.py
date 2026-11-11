import re
from typing import Dict, List, Optional, Set, Tuple

# Default canonical skills vocabulary from training notebook
DEFAULT_SKILLS: Dict[str, List[str]] = {
    skill: [skill] for skill in [
        'python', 'java', 'c++', 'c#', '.net', 'sql', 'mysql', 'postgresql',
        'mongodb', 'javascript', 'typescript', 'react', 'angular', 'html', 'css',
        'docker', 'kubernetes', 'git', 'linux', 'aws', 'azure', 'tensorflow',
        'pytorch', 'pandas', 'numpy', 'excel', 'tableau', 'power bi', 'accounting',
        'budgeting', 'recruitment', 'payroll', 'sales', 'marketing', 'communication',
        'project management', 'machine learning', 'data analysis', 'customer service'
    ]
}
DEFAULT_SKILLS.update({
    'node.js': ['node.js', 'nodejs', 'node js'],
    'express': ['express.js', 'expressjs'],
    'rest api': ['rest api', 'restful api', 'rest apis'],
    'scikit-learn': ['scikit-learn', 'sklearn'],
    'aws': ['aws', 'amazon web services'],
})


def clean(text: str, mask: bool = True) -> str:
    """
    Cleans and preprocesses resume and job text.
    If mask=True, strips personal identifying demographic info (SDG 10 fairness)
    exactly matching the training pipeline.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Resume and job text must both be nonempty strings.")
    
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    if mask:
        # Mask candidate name labels
        text = re.sub(r'(?im)^\s*(?:name|candidate name|full name)\s*:[^\n]*', 'PERSON', text)
        # Mask age indicators
        text = re.sub(r'(?i)\b(?:age\s*[:=]?\s*\d{1,3}|\d{1,3}\s*(?:years? old|year-old))\b', 'PERSONAL_DETAIL', text)
        # Mask date of birth
        text = re.sub(r'(?im)\b(?:date of birth|dob)\s*:[^\n,;]*', 'PERSONAL_DETAIL', text)
        # Mask pronouns
        text = re.sub(r'(?im)^\s*pronouns\s*:[^\n]*', 'PERSON', text)
        # Mask emails
        text = re.sub(r'(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b', 'CONTACT', text)
        # Mask URLs and websites
        text = re.sub(r'(?i)https?://\S+|www\.\S+', 'CONTACT', text)
        # Mask phone numbers (at least 10 digits avoids masking year ranges like 2019-2024)
        text = re.sub(
            r'(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)',
            lambda m: 'CONTACT' if len(re.sub(r'\D', '', m[0])) >= 10 else m[0],
            text
        )
        # Mask gender pronouns
        text = re.sub(r'(?i)\b(?:he|she|him|her|his|hers|they|them|their|theirs)\b', 'PERSON', text)
        
        # Mask standalone names on first line if not a title or standard resume heading
        lines = text.splitlines()
        if lines and re.fullmatch(r'[A-Z][a-z]+(?: [A-Z][a-z]+){1,3}', lines[0].strip()):
            if not re.search(r'Engineer|Developer|Manager|Analyst|Resume|Curriculum|Vitae|Skills|Experience', lines[0]):
                lines[0] = 'PERSON'
        text = '\n'.join(lines)

    return re.sub(r'\s+', ' ', text).strip()


def extract_skills(text: str, vocabulary: Optional[Dict[str, List[str]]] = None) -> Set[str]:
    """
    Extracts skills present in text matching canonical vocabulary and aliases.
    Uses regex word boundaries safe for special characters like C++, C#, .NET.
    """
    vocab = DEFAULT_SKILLS if vocabulary is None else vocabulary
    text_lower = text.lower()
    found = {
        skill for skill, aliases in vocab.items()
        if any(
            re.search(r'(?<![\w+#.])' + re.escape(alias) + r'(?![\w+#])', text_lower)
            for alias in aliases
        )
    }
    return found


def calculate_skill_overlap(
    resume_text: str,
    job_text: str,
    vocabulary: Optional[Dict[str, List[str]]] = None
) -> Tuple[List[str], List[str], float]:
    """
    Calculates matched skills, missing skills, and skill coverage ratio.
    """
    required = extract_skills(job_text, vocabulary)
    present = extract_skills(resume_text, vocabulary)
    
    matched = sorted(list(required & present))
    missing = sorted(list(required - present))
    coverage = float(len(matched) / len(required)) if required else 0.0
    
    return matched, missing, coverage
