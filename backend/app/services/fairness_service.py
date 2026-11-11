import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.ml.inference import MLInferenceService
from app.models.models import FairnessAudit

logger = logging.getLogger("inclusive_ats.fairness_service")


class FairnessService:
    @staticmethod
    def run_sdg10_fairness_audit(db: Session, audit_name: str = "SDG 10 Counterfactual Fairness Audit") -> Dict[str, Any]:
        """
        Executes counterfactual fairness testing across demographic variants
        (name ethnicity/gender markers, gender pronouns, and age markers)
        with and without SDG 10 privacy masking.
        Directly measures model score invariance and decision flip rates.
        """
        inference_service = MLInferenceService.get_instance()
        
        skill_sets = [
            "Python SQL Docker Machine Learning",
            "Java Git MySQL REST API",
            "JavaScript Node.js React AWS",
            "Excel Accounting Budgeting Communication"
        ]

        variants = {
            "name": [
                ("Name: Alex Morgan\n", "Name: Priya Sen\n"),
                ("Name: John Smith\n", "Name: Fatima Al-Mansoor\n"),
                ("Name: David Miller\n", "Name: Mei-Ling Chen\n")
            ],
            "pronoun": [
                ("Pronouns: he/him\n", "Pronouns: she/her\n"),
                ("Pronouns: he/him\n", "Pronouns: they/them\n"),
                ("Pronouns: she/her\n", "Pronouns: they/them\n")
            ],
            "age": [
                ("Age: 24\n", "Age: 56\n"),
                ("22 years old\n", "58 years old\n"),
                ("Date of birth: 15/04/1999\n", "Date of birth: 15/04/1965\n")
            ]
        }

        audit_records = []

        for skill in skill_sets:
            body = f"Skills: {skill}\nExperience: 5 years delivering production software projects."
            job = f"Senior Engineer. Required skills: {skill}. 5+ years experience required."

            for attribute, pair_list in variants.items():
                for a_prefix, b_prefix in pair_list:
                    resume_a = a_prefix + body
                    resume_b = b_prefix + body

                    for mask in [False, True]:
                        pred_a = inference_service.predict_pair(resume_a, job, mask=mask)
                        pred_b = inference_service.predict_pair(resume_b, job, mask=mask)

                        score_a = pred_a["compatibility_score"]
                        score_b = pred_b["compatibility_score"]
                        change = abs(score_a - score_b)
                        flip = int(pred_a["classification"] != pred_b["classification"])

                        audit_records.append({
                            "attribute": attribute,
                            "masked": mask,
                            "score_a": score_a,
                            "score_b": score_b,
                            "change": change,
                            "flip": flip
                        })

        df = pd.DataFrame(audit_records)
        grouped = df.groupby(["attribute", "masked"]).agg(
            mean_change=("change", "mean"),
            p95_change=("change", lambda x: float(np.percentile(x, 95))),
            max_change=("change", "max"),
            flip_rate=("flip", "mean"),
            total_pairs=("change", "count")
        ).reset_index()

        results_list = grouped.to_dict(orient="records")

        # Summarize impact of masking
        unmasked_mean_change = float(df[~df["masked"]]["change"].mean()) if not df[~df["masked"]].empty else 0.0
        masked_mean_change = float(df[df["masked"]]["change"].mean()) if not df[df["masked"]].empty else 0.0
        bias_reduction_pct = (
            ((unmasked_mean_change - masked_mean_change) / max(unmasked_mean_change, 1e-6)) * 100
            if unmasked_mean_change > 0 else 100.0
        )

        summary = {
            "unmasked_mean_score_deviation": round(unmasked_mean_change, 3),
            "masked_mean_score_deviation": round(masked_mean_change, 3),
            "demographic_bias_reduction_percentage": round(max(0.0, bias_reduction_pct), 1),
            "decision_flip_rate_with_masking": float(df[df["masked"]]["flip"].mean()),
            "evaluation_sample_pairs": len(audit_records)
        }

        recommendations = [
            "Maintain automated regex-based PII and demographic masking prior to feature generation (SDG 10 compliance).",
            "Prohibit recruiters from viewing unmasked demographic tokens during preliminary AI ranking.",
            "Mandate human-in-the-loop review for hiring decisions; never automate rejections based strictly on threshold scores."
        ]

        # Save to database
        db_audit = FairnessAudit(
            name=audit_name,
            audit_type="counterfactual_sensitivity",
            total_pairs=len(audit_records),
            metrics={
                "summary": summary,
                "breakdown": results_list
            },
            model_version=inference_service.model_type,
            notes="Evaluated under UN SDG 10 standards for demographic invariance and fairness."
        )
        db.add(db_audit)
        db.commit()
        db.refresh(db_audit)

        # Factual, data-derived summary (no certification claim).
        verdict = (
            f"Synthetic paired test over {len(audit_records)} comparisons: "
            f"mean score change {summary['masked_mean_score_deviation']} pts with masking vs "
            f"{summary['unmasked_mean_score_deviation']} pts without; "
            f"decision flip rate with masking {summary['decision_flip_rate_with_masking']:.1%}. "
            "Covers only the tested name, pronoun and age variants."
        )

        return {
            "audit_id": db_audit.id,
            "name": db_audit.name,
            "model_version": db_audit.model_version,
            "timestamp": db_audit.created_at,
            "demographic_parity_summary": summary,
            "counterfactual_sensitivity_results": results_list,
            "overall_fairness_verdict": verdict,
            "recommendations": recommendations
        }

    @staticmethod
    def get_fairness_reports(db: Session, limit: int = 10) -> List[FairnessAudit]:
        return db.query(FairnessAudit).order_by(FairnessAudit.created_at.desc()).limit(limit).all()
