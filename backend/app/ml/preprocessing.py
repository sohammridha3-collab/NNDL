import re
from typing import Any, Dict, List, Optional, Set, Tuple

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


def extract_requirements_breakdown(
    job_text: str,
    vocabulary: Optional[Dict[str, List[str]]] = None,
    resume_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Parses job text into Essential (minimum/required) versus Preferred (nice-to-have)
    competencies and correlates them against the candidate's resume skills.
    """
    vocab = DEFAULT_SKILLS if vocabulary is None else vocabulary
    all_job_skills = extract_skills(job_text, vocab)
    resume_skills = extract_skills(resume_text, vocab) if resume_text else set()

    # Identify essential vs preferred sections
    lines = job_text.splitlines()
    essential_text = []
    preferred_text = []
    current_mode = "essential"

    for line in lines:
        lower = line.lower().strip()
        if re.search(r'\b(preferred|nice to have|bonus|plus|desired|optional|would be great)\b', lower):
            current_mode = "preferred"
        elif re.search(r'\b(required|requirements|must have|minimum|essential|basic qualifications|what you need)\b', lower):
            current_mode = "essential"
        
        if current_mode == "preferred":
            preferred_text.append(line)
        else:
            essential_text.append(line)

    pref_joined = " ".join(preferred_text)
    ess_joined = " ".join(essential_text)

    preferred_skills = extract_skills(pref_joined, vocab) & all_job_skills
    # Essential skills are all job skills not explicitly isolated in the preferred section
    essential_skills = all_job_skills - preferred_skills

    # Fallback if everything fell into preferred
    if not essential_skills and all_job_skills:
        essential_skills = all_job_skills
        preferred_skills = set()

    matched_essential = sorted(list(essential_skills & resume_skills))
    missing_essential = sorted(list(essential_skills - resume_skills))
    matched_preferred = sorted(list(preferred_skills & resume_skills))
    missing_preferred = sorted(list(preferred_skills - resume_skills))

    return {
        "essential_skills": sorted(list(essential_skills)),
        "preferred_skills": sorted(list(preferred_skills)),
        "matched_essential": matched_essential,
        "missing_essential": missing_essential,
        "matched_preferred": matched_preferred,
        "missing_preferred": missing_preferred
    }


# Practical project suggestions for skill gap remediation
SKILL_PRACTICE_PROJECTS: Dict[str, Dict[str, str]] = {
    "kubernetes": {
        "topic": "Container Orchestration with Kubernetes",
        "project": "Deploy a multi-service containerized architecture using Kubernetes manifests, ConfigMaps, and cluster Ingress controllers."
    },
    "docker": {
        "topic": "Production Microservice Containerization",
        "project": "Build an optimized multi-stage Dockerfile adhering to non-root execution and minimal attack surface."
    },
    "pytorch": {
        "topic": "Deep Learning Pipeline in PyTorch",
        "project": "Implement and train a custom PyTorch neural classifier with torch.utils.data DataLoaders and GPU inference benchmarks."
    },
    "python": {
        "topic": "Asynchronous Backend API Architecture",
        "project": "Develop high-throughput RESTful microservices with FastAPI, Pydantic type validation, and pytest test coverage."
    },
    "sql": {
        "topic": "Relational Database Performance Optimization",
        "project": "Write optimized relational schemas with composite indexing, transaction boundaries, and complex join queries."
    },
    "postgresql": {
        "topic": "PostgreSQL Advanced Queries & Migrations",
        "project": "Implement Alembic database migrations, connection pooling, and JSONB analytical queries."
    },
    "mysql": {
        "topic": "MySQL Data Store & Stored Procedures",
        "project": "Construct transactional workflows and benchmark query execution plans using EXPLAIN."
    },
    "react": {
        "topic": "Component-Driven Frontend Application",
        "project": "Create a responsive, accessible dashboard with state management, strict TypeScript interfaces, and REST integration."
    },
    "typescript": {
        "topic": "Strict Type Safety in Enterprise JavaScript",
        "project": "Refactor vanilla or untyped modules to TypeScript with generics, discriminated unions, and strict null checks."
    },
    "aws": {
        "topic": "Cloud Infrastructure & Container Deployment",
        "project": "Automate containerized service deployments to AWS ECS/EKS with IAM least-privilege security policies."
    },
    "azure": {
        "topic": "Microsoft Azure Cloud Services",
        "project": "Configure Azure App Services with Container Registry integration and Key Vault secrets management."
    },
    "machine learning": {
        "topic": "End-to-End Predictive Modeling",
        "project": "Build an end-to-end ML pipeline with cross-validation, feature normalization, and ROC-AUC evaluation metrics."
    },
    "pandas": {
        "topic": "Tabular Data Analytics & Feature Engineering",
        "project": "Conduct automated data cleaning, aggregation, and outlier detection on multi-gigabyte CSV datasets."
    },
    "git": {
        "topic": "Enterprise Git Workflows & CI/CD",
        "project": "Set up automated GitHub Actions pipelines with linting, security audits, and branch protection rules."
    },
    "linux": {
        "topic": "Linux Systems Administration & Shell Automation",
        "project": "Write Bash automation scripts for system monitoring, service health checks, and log rotation."
    },
    "communication": {
        "topic": "Technical Documentation & Architecture Decisions",
        "project": "Write structured Architecture Decision Records (ADRs) and comprehensive API specifications."
    },
    "project management": {
        "topic": "Agile Sprint Planning & Milestone Tracking",
        "project": "Develop a product delivery roadmap with user story estimation and risk mitigation plans."
    }
}


def generate_learning_checklist(missing_skills: List[str]) -> List[Dict[str, str]]:
    """
    Generates actionable learning checklist items and practice projects
    for detected missing competencies.
    """
    checklist = []
    for skill in missing_skills[:6]:
        norm = skill.lower().strip()
        info = SKILL_PRACTICE_PROJECTS.get(norm)
        if info:
            topic = info["topic"]
            project = info["project"]
        else:
            topic = f"Competency in {skill.title()}"
            project = f"Build a focused portfolio project demonstrating practical application of {skill} in a production-like environment."

        checklist.append({
            "skill": skill,
            "topic": topic,
            "project": project,
            "practice_project": project,
            "guidance": "Recommended for self-directed portfolio practice to strengthen alignment with this role's listed qualifications."
        })
    return checklist

