import logging
from pathlib import Path
import pandas as pd
from app.core.security import get_password_hash
from app.db.session import Base, SessionLocal, engine
from app.ml.preprocessing import extract_skills, DEFAULT_SKILLS
from app.models.models import CandidateProfile, Company, Job, JobSkill, RecruiterProfile, User

logger = logging.getLogger("inclusive_ats.init_db")


def seed_database():
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Seed Company
        company = db.query(Company).filter(Company.name == "Tech Innovate Global").first()
        if not company:
            company = Company(
                name="Tech Innovate Global",
                description="Global engineering leader driving inclusive AI solutions.",
                website="https://techinnovate.example.com",
                location="San Francisco, CA / Remote",
                industry="Information Technology"
            )
            db.add(company)
            db.flush()

        # 2. Seed Admin User
        admin = db.query(User).filter(User.email == "admin@inclusiveats.org").first()
        if not admin:
            admin = User(
                email="admin@inclusiveats.org",
                hashed_password=get_password_hash("Admin@12345"),
                full_name="System Administrator",
                role="admin",
                is_active=True,
                is_verified=True
            )
            db.add(admin)

        # 3. Seed Recruiter User
        recruiter = db.query(User).filter(User.email == "recruiter@techinnovate.com").first()
        if not recruiter:
            recruiter = User(
                email="recruiter@techinnovate.com",
                hashed_password=get_password_hash("Recruiter@12345"),
                full_name="Sarah Jenkins",
                role="recruiter",
                is_active=True,
                is_verified=True
            )
            db.add(recruiter)
            db.flush()
            rec_profile = RecruiterProfile(
                user_id=recruiter.id,
                company_id=company.id,
                title="Lead Technical Recruiter",
                department="Talent Acquisition"
            )
            db.add(rec_profile)

        # 4. Seed Candidate User
        candidate = db.query(User).filter(User.email == "candidate@example.com").first()
        if not candidate:
            candidate = User(
                email="candidate@example.com",
                hashed_password=get_password_hash("Candidate@12345"),
                full_name="Alex Morgan",
                role="candidate",
                is_active=True,
                is_verified=True
            )
            db.add(candidate)
            db.flush()
            cand_profile = CandidateProfile(
                user_id=candidate.id,
                target_title="Full Stack / Machine Learning Engineer",
                headline="Experienced Software Engineer passionate about inclusive AI systems",
                bio="5+ years experience building cloud-native applications and ML pipelines.",
                years_experience=5.0,
                profile_completion=75.0
            )
            db.add(cand_profile)

        db.commit()

        # 5. Seed Real Jobs from job (1).csv if available
        job_count = db.query(Job).count()
        if job_count < 10:
            csv_candidates = [
                Path("job (1).csv"),
                Path("../job (1).csv"),
                Path("backend/../job (1).csv")
            ]
            job_csv = None
            for p in csv_candidates:
                if p.exists():
                    job_csv = p
                    break

            if job_csv:
                logger.info(f"Loading real job openings from '{job_csv}'...")
                df = pd.read_csv(job_csv, nrows=35)
                for _, row in df.iterrows():
                    job_id_code = str(row.get("job_id", "")).strip()
                    title = str(row.get("job_title", "Software Engineer")).strip()
                    category = str(row.get("category", "Software & Technology")).strip()
                    desc = str(row.get("job_description", "")).strip()
                    if not desc or len(desc) < 30:
                        continue

                    # Avoid duplicate job_code
                    existing = db.query(Job).filter(Job.job_code == job_id_code).first()
                    if existing:
                        continue

                    skills = extract_skills(desc, DEFAULT_SKILLS)
                    new_job = Job(
                        job_code=job_id_code,
                        recruiter_id=recruiter.id,
                        company_id=company.id,
                        title=title[:250],
                        category=category[:100],
                        description=desc,
                        requirements=f"Required skills and competencies: {', '.join(sorted(skills)) if skills else 'Relevant technical experience'}.",
                        location="Remote",
                        job_type="remote",
                        experience_level="Mid to Senior Level",
                        min_salary=90000.0,
                        max_salary=150000.0,
                        salary_currency="USD",
                        status="active"
                    )
                    db.add(new_job)
                    db.flush()

                    for sk in skills:
                        db.add(JobSkill(job_id=new_job.id, skill_name=sk, is_required=True))

                db.commit()
                logger.info("Successfully seeded real job descriptions into database.")

        logger.info("Database initialization and seeding completed successfully!")
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding database: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
