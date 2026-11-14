from enum import Enum
import logging
import os
import pickle
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
import numpy as np

from app.core.config import settings
from app.ml.preprocessing import (
    clean,
    calculate_skill_overlap,
    extract_requirements_breakdown,
    generate_learning_checklist,
    DEFAULT_SKILLS
)

logger = logging.getLogger("inclusive_ats.ml.inference")


class ModelState(str, Enum):
    UNINITIALIZED = "uninitialized"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


_MatchNetworkCls = None


def _get_match_network_class():
    global _MatchNetworkCls
    if _MatchNetworkCls is None:
        import torch
        from torch import nn

        class MatchNetwork(nn.Module):
            """
            Trained PyTorch Neural Classifier Architecture.
            Matches the exact architecture defined and trained in RESUME_AND_JOB.ipynb.
            """

            def __init__(self):
                super().__init__()
                self.layers = nn.Sequential(
                    nn.Linear(770, 256),
                    nn.ReLU(),
                    nn.Dropout(0.3),
                    nn.Linear(256, 64),
                    nn.ReLU(),
                    nn.Dropout(0.2),
                    nn.Linear(64, 1),
                )

            def forward(self, matrix: torch.Tensor) -> torch.Tensor:
                return self.layers(matrix).squeeze(-1)

        _MatchNetworkCls = MatchNetwork
    return _MatchNetworkCls


def _create_match_network():
    return _get_match_network_class()()


def __getattr__(name: str):
    if name == "MatchNetwork":
        return _get_match_network_class()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class MLInferenceService:
    """
    Thread-safe Singleton ML Inference Service that manages the PyTorch classifier
    and SentenceTransformer encoder with full state lifecycle tracking.
    """
    _instance: Optional["MLInferenceService"] = None
    _lock: threading.Lock = threading.Lock()
    _state: ModelState = ModelState.UNINITIALIZED
    _init_error: Optional[str] = None
    _ready_event: threading.Event = threading.Event()

    def __init__(self, model_path: Optional[str] = None):
        self.device = settings.DEVICE
        self.model_path = model_path or settings.MODEL_PATH
        
        # Verify model artifact exists
        resolved_path = Path(self.model_path)
        if not resolved_path.exists():
            # Check alternative locations
            candidates = [
                Path(settings.MODEL_PATH),
                Path(settings.APP_DIR / "app/ml/artifacts/model.pkl"),
                Path(settings.ROOT_DIR / "backend/app/ml/artifacts/model.pkl"),
                Path(settings.ROOT_DIR / "model (1).pkl"),
                Path("app/ml/artifacts/model.pkl"),
                Path("backend/app/ml/artifacts/model.pkl"),
                Path("model (1).pkl")
            ]
            for cand in candidates:
                if cand.exists():
                    resolved_path = cand
                    break
        
        if not resolved_path.exists():
            raise FileNotFoundError(
                f"Trained model artifact not found at '{self.model_path}'. "
                "Ensure model.pkl is placed in app/ml/artifacts/."
            )

        logger.info(f"Loading trained ML model bundle from '{resolved_path}'...")
        with open(resolved_path, "rb") as f:
            bundle = pickle.load(f)

        self.model_type = bundle.get("model_type", "MiniLM + PyTorch MLP")
        self.architecture = bundle.get("architecture", [770, 256, 64, 1])
        self.threshold = float(bundle.get("threshold", 0.9032))
        self.label_mapping = bundle.get("label_mapping", {0: "weaker match", 1: "strong match"})
        self.chunk_tokens = int(bundle.get("chunk_tokens", 240))
        self.vocabulary = bundle.get("skill_vocabulary", DEFAULT_SKILLS)
        self.scaler = bundle.get("scaler")
        
        if self.scaler is None:
            raise ValueError("StandardScaler missing from model bundle.")

        import torch
        from app.ml.embeddings import EmbeddingEncoder

        self._torch = torch
        # Reconstruct PyTorch MatchNetwork
        self.model = _create_match_network().to(self.device)
        weights = bundle.get("weights", {})
        state_dict = {k: torch.from_numpy(v).to(self.device) for k, v in weights.items()}
        self.model.load_state_dict(state_dict)
        self.model.eval()

        # Initialize Embedding Encoder
        encoder_name = bundle.get("encoder_name", settings.ENCODER_MODEL_NAME)
        self.encoder = EmbeddingEncoder(
            model_name=encoder_name,
            device=self.device,
            chunk_tokens=self.chunk_tokens
        )
        logger.info(
            f"ML Inference Service successfully loaded! "
            f"Threshold: {self.threshold:.4f}, Features: 770, Device: {self.device}"
        )

    @classmethod
    def get_instance(cls, wait_timeout: float = 60.0, block: bool = True) -> "MLInferenceService":
        """
        Thread-safe singleton accessor with non-blocking graceful degradation.
        If the model is currently loading, waits up to wait_timeout. If still warming up,
        raises a clean, retryable HTTP 503.
        """
        if cls._state == ModelState.READY and cls._instance is not None:
            return cls._instance

        if cls._state == ModelState.FAILED:
            raise HTTPException(
                status_code=503,
                detail=f"ML Inference Engine failed to initialize: {cls._init_error}. Please contact system administrator."
            )

        # Trigger initialization if uninitialized
        if cls._state == ModelState.UNINITIALIZED:
            with cls._lock:
                if cls._state == ModelState.UNINITIALIZED:
                    cls._load_model_sync()

        # If currently loading, wait for the background warmup to complete
        if cls._state == ModelState.LOADING:
            if block:
                ready = cls._ready_event.wait(timeout=wait_timeout)
                if ready and cls._state == ModelState.READY and cls._instance:
                    return cls._instance
            raise HTTPException(
                status_code=503,
                detail="ML Inference Engine is currently warming up. Please retry in a few seconds.",
                headers={"Retry-After": "5"}
            )

        if cls._state == ModelState.READY and cls._instance:
            return cls._instance

        raise HTTPException(
            status_code=503,
            detail=f"ML Inference Engine is unavailable (state: {cls._state.value}). Error: {cls._init_error}"
        )

    @classmethod
    def warmup_async(cls):
        """Asynchronously pre-warms the ML model in a background daemon thread."""
        if cls._state in (ModelState.LOADING, ModelState.READY):
            return

        def _worker():
            with cls._lock:
                if cls._state in (ModelState.LOADING, ModelState.READY):
                    return
                cls._load_model_sync()

        thread = threading.Thread(target=_worker, daemon=True, name="ML-Warmup-Worker")
        thread.start()

    @classmethod
    def _load_model_sync(cls):
        cls._state = ModelState.LOADING
        cls._ready_event.clear()
        cls._init_error = None
        try:
            instance = MLInferenceService()
            cls._instance = instance
            cls._state = ModelState.READY
            cls._ready_event.set()
            logger.info("ML Inference Service state changed to READY.")
        except Exception as e:
            cls._state = ModelState.FAILED
            cls._init_error = str(e)
            cls._ready_event.set()
            logger.error(f"ML Inference Service failed to load: {e}", exc_info=True)

    @classmethod
    def is_ready(cls) -> bool:
        return cls._state == ModelState.READY and cls._instance is not None

    @classmethod
    def status_dict(cls) -> Dict[str, Any]:
        return {
            "state": cls._state.value,
            "is_ready": cls._state == ModelState.READY,
            "model_type": cls._instance.model_type if cls._instance else None,
            "threshold": cls._instance.threshold if cls._instance else None,
            "feature_dimension": cls._instance.architecture[0] if (cls._instance and hasattr(cls._instance, 'architecture')) else 770,
            "error": cls._init_error
        }

    def predict(
        self,
        resume_text: str,
        job_text: str,
        mask: bool = True
    ) -> Dict[str, Any]:
        """Convenience alias for predict_pair."""
        return self.predict_pair(resume_text=resume_text, job_text=job_text, mask=mask)


    def build_features(
        self,
        resumes: List[str],
        jobs: List[str],
        mask: bool = True
    ) -> np.ndarray:
        """
        Reconstructs the exact 770-dimensional feature vector:
        1. Cosine similarity: (a * b).sum(axis=1, keepdims=True)  [dim 1]
        2. Absolute difference: abs(a - b)                        [dim 384]
        3. Element-wise product: a * b                            [dim 384]
        4. Skill coverage ratio: coverage                         [dim 1]
        Total = 770 dimensions.
        """
        if len(resumes) != len(jobs) or len(resumes) == 0:
            raise ValueError("Provide equally sized, nonempty resume and job lists.")

        resumes_clean = [clean(r, mask=mask) for r in resumes]
        jobs_clean = [clean(j, mask=mask) for j in jobs]

        # Generate 384-dimensional normalized embeddings
        joined_embeddings = self.encoder.encode(resumes_clean + jobs_clean)
        num_pairs = len(resumes)
        a = joined_embeddings[:num_pairs]
        b = joined_embeddings[num_pairs:]

        # Skill coverage calculation
        coverages = []
        for r_text, j_text in zip(resumes_clean, jobs_clean):
            _, _, cov = calculate_skill_overlap(r_text, j_text, self.vocabulary)
            coverages.append(cov)
        coverage_col = np.array(coverages, dtype=np.float32)[:, None]

        # Construct 770-dim feature matrix
        cosine_sim = (a * b).sum(axis=1, keepdims=True)
        abs_diff = np.abs(a - b)
        prod = a * b
        
        feature_matrix = np.concatenate([cosine_sim, abs_diff, prod, coverage_col], axis=1).astype(np.float32)
        if feature_matrix.shape != (num_pairs, 770) or not np.isfinite(feature_matrix).all():
            raise ValueError(f"Feature vector shape must be ({num_pairs}, 770) with all finite values.")

        return feature_matrix

    def predict_pair(
        self,
        resume_text: str,
        job_text: str,
        mask: bool = True
    ) -> Dict[str, Any]:
        """
        Executes real model inference on a single resume-job pair.
        Returns full structured prediction with calibrated probabilities,
        classifications, threshold, skills, and explainable metrics.
        """
        # Build 770-dim feature vector
        feature_matrix = self.build_features([resume_text], [job_text], mask=mask)
        
        # Apply trained StandardScaler
        torch = getattr(self, "_torch", None)
        if torch is None:
            import torch
            self._torch = torch
        scaled_matrix = self.scaler.transform(feature_matrix).astype(np.float32)
        tensor_input = torch.from_numpy(scaled_matrix).to(self.device)

        # PyTorch classifier inference
        with torch.inference_mode():
            logit = self.model(tensor_input)
            probability = float(torch.sigmoid(logit).cpu().item())

        # Skill extraction & overlap
        clean_resume = clean(resume_text, mask=mask)
        clean_job = clean(job_text, mask=mask)
        matched_skills, missing_skills, coverage = calculate_skill_overlap(
            clean_resume, clean_job, self.vocabulary
        )

        # Essential vs Preferred Requirements Breakdown
        req_breakdown = extract_requirements_breakdown(
            job_text=clean_job,
            vocabulary=self.vocabulary,
            resume_text=clean_resume
        )

        semantic_similarity = float(feature_matrix[0, 0])
        is_strong_match = probability >= self.threshold
        classification = "Strong Match" if is_strong_match else "Weaker Match"
        score_pct = round(probability * 100, 2)

        # Construct transparent, evidence-based recommendations grounded in the actual job
        recommendations = []
        missing_ess = req_breakdown.get("missing_essential", [])
        if missing_ess:
            recommendations.append(
                f"Essential Requirement Gap: The role specifies core competencies ({', '.join(missing_ess[:3])}) not explicitly detected in your resume."
            )
        elif missing_skills:
            recommendations.append(
                f"Preferred Skill Enhancement: Demonstrating familiarity with ({', '.join(missing_skills[:3])}) will strengthen your candidate profile."
            )

        if semantic_similarity < 0.65:
            recommendations.append(
                "Terminology Alignment: Rephrase experience bullets using the technical vocabulary and domain terminology seen in the job responsibilities."
            )
        else:
            recommendations.append(
                "Strong Domain Alignment: Your background demonstrates solid thematic relevance to this team's core responsibilities."
            )

        if is_strong_match:
            recommendations.append(
                f"Competitive Fit: Highlights your demonstrated strength in {', '.join(matched_skills[:3]) if matched_skills else 'core qualifications'}."
            )
        else:
            recommendations.append(
                "Impact Metrics: Quantify key achievements with measurable metrics (e.g. latency reduction, revenue impact, scale) relevant to this role."
            )

        # Skill-gap learning checklist & practice projects
        learning_checklist = generate_learning_checklist(missing_skills)

        disclaimer_text = (
            "This score estimates résumé–job compatibility according to the model’s training labels. "
            "It is not the probability of being hired."
        )

        explanation = {
            "model_architecture": "770-dim Multi-Feature Neural Classifier",
            "decision_rule": f"Probability ({probability:.4f}) {'≥' if is_strong_match else '<'} Threshold ({self.threshold:.4f})",
            "semantic_score_interpretation": (
                "High semantic alignment" if semantic_similarity >= 0.75
                else "Moderate semantic alignment" if semantic_similarity >= 0.55
                else "Low semantic alignment"
            ),
            "skill_coverage_interpretation": (
                f"{coverage * 100:.1f}% of recognized job skills identified in resume"
                if (len(matched_skills) + len(missing_skills)) > 0
                else "No skills from the recognized vocabulary were detected in the job text; coverage is not applicable"
            ),
            "total_job_skills_found": len(matched_skills) + len(missing_skills),
            "bias_masking_applied": mask,
            "disclaimer": disclaimer_text
        }

        return {
            "compatibility_score": score_pct,
            "raw_probability": probability,
            "score_type": "model_probability_percent",
            "classification": classification,
            "decision_threshold": round(self.threshold, 4),
            "semantic_similarity": round(semantic_similarity, 4),
            "required_skill_coverage": round(coverage, 4),
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "requirements_breakdown": req_breakdown,
            "learning_checklist": learning_checklist,
            "recommendations": recommendations,
            "disclaimer": disclaimer_text,
            "explanation": explanation,
            "model_version": "MiniLM + PyTorch MLP v1.0"
        }
