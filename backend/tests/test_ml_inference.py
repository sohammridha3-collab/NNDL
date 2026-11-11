import numpy as np
import pytest
from app.ml.inference import MLInferenceService
from app.ml.preprocessing import clean, extract_skills, calculate_skill_overlap


def test_ml_service_initialization():
    service = MLInferenceService.get_instance()
    assert service is not None
    assert service.model is not None
    assert service.encoder is not None
    assert service.scaler is not None
    assert service.threshold > 0.0
    assert service.architecture == [770, 256, 64, 1]


def test_feature_dimensionality():
    service = MLInferenceService.get_instance()
    resume = "Senior Python Developer with expertise in SQL, Docker, and Machine Learning."
    job = "Looking for Senior Python Developer with Docker and SQL knowledge."

    features = service.build_features([resume], [job], mask=True)
    assert isinstance(features, np.ndarray)
    assert features.shape == (1, 770)
    assert np.isfinite(features).all()
    # Feature order: [0] = cosine, [1:385] = abs diff, [385:769] = prod, [769] = skill coverage
    assert -1.0 <= features[0, 0] <= 1.0  # Cosine similarity
    assert 0.0 <= features[0, 769] <= 1.0  # Skill coverage


def test_real_model_prediction():
    service = MLInferenceService.get_instance()
    resume = "Candidate with 5 years experience in Python, SQL, Docker, AWS, and Machine Learning."
    job = "Requires Python, SQL, Docker, and Machine Learning for Senior Engineer position."

    result = service.predict_pair(resume, job, mask=True)
    assert "compatibility_score" in result
    assert "raw_probability" in result
    assert "classification" in result
    assert "decision_threshold" in result
    assert "semantic_similarity" in result
    assert "required_skill_coverage" in result
    assert "matched_skills" in result
    assert "missing_skills" in result
    assert "explanation" in result

    assert 0.0 <= result["compatibility_score"] <= 100.0
    assert 0.0 <= result["raw_probability"] <= 1.0
    assert result["classification"] in ["Strong Match", "Weaker Match"]
    assert "python" in [s.lower() for s in result["matched_skills"]]
    assert "sql" in [s.lower() for s in result["matched_skills"]]


def test_skill_extraction_and_overlap():
    text = "Proficient in Python, C++, MySQL, Node.js, and Docker. Experience with PyTorch and React."
    skills = extract_skills(text)
    assert "python" in skills
    assert "c++" in skills
    assert "mysql" in skills
    assert "node.js" in skills
    assert "docker" in skills
    assert "pytorch" in skills
    assert "react" in skills

    job_text = "Required skills: Python, Docker, Kubernetes."
    matched, missing, coverage = calculate_skill_overlap(text, job_text)
    assert "python" in matched
    assert "docker" in matched
    assert "kubernetes" in missing
    assert coverage == 2.0 / 3.0


def test_sdg10_bias_masking():
    raw_resume = """
    Name: John Doe
    Age: 45 years old
    Pronouns: he/him
    Email: john.doe@example.com
    Phone: +1 (555) 123-4567
    Software Engineer with 8 years experience in Python and SQL.
    """
    masked = clean(raw_resume, mask=True)
    assert "John Doe" not in masked
    assert "45 years old" not in masked
    assert "john.doe@example.com" not in masked
    assert "he/him" not in masked
    assert "Python" in masked
    assert "SQL" in masked
