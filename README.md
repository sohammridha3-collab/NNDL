# Inclusive Resume and Job Matching System
### UN SDG 10: Reduced Inequalities

An enterprise-grade, production-ready AI-powered recruitment platform combining state-of-the-art NLP, semantic similarity matching, neural classification, ATS resume parsing, and counterfactual fairness auditing to eliminate hiring bias.

---

## 1. Architectural Highlights

- **Real PyTorch Neural Matcher:** Uses the trained 770-dimensional multi-feature classifier (`Linear(770, 256) -> ReLU -> Dropout(0.3) -> Linear(256, 64) -> ReLU -> Dropout(0.2) -> Linear(64, 1)`) with Sigmoid output.
- **Trained Decision Threshold:** Calibrated threshold `0.9032` (derived from precision-recall optimization on validation sets for precision $\ge 0.94$, recall $\ge 0.91$).
- **Sentence Transformer Encoder:** `sentence-transformers/all-MiniLM-L6-v2` with chunk token-weighted normalized pooling (chunk size: 240) and 384-dimensional dense semantic vectors.
- **770-Dimensional Feature Composition:**
  1. Cosine similarity: $(a \cdot b)$ (1 feature)
  2. Absolute difference: $|a - b|$ (384 features)
  3. Element-wise product: $a \odot b$ (384 features)
  4. Skill coverage ratio: $|matched\_skills| / |required\_skills|$ (1 feature)
  5. Scaled with fitted `StandardScaler`.
- **UN SDG 10 Bias Mitigation:** Automatic regex-based demographic anonymization of names, gender pronouns, age indicators, dates of birth, emails, and phone numbers prior to feature extraction.
- **Skill-Based Recommendations & Live Vacancies:**
  - Interactive skill chips with real-time extraction from uploaded or stored résumés.
  - Dual-source job aggregation: Remotive Open API + Adzuna API with fallback to verified local database listings.
  - Zero Candidate PII Transmission: External job providers receive search keywords only; candidate personal data and résumé texts remain strictly on the local platform.
  - Requirements breakdown into Essential vs Preferred qualifications.
  - Personalized practice project learning checklist for identified missing skills with educational guidance.
- **Thread-Safe Model Lifecycle:** Non-blocking background warmup during startup (`ModelState.LOADING -> ModelState.READY`). Inference requests return retryable HTTP 503 (`Retry-After: 5`) while warmup completes, preventing server hangs and race conditions.
- **Canonical Launcher & Port Safety:** Single entrypoint `main.py` defaults to `127.0.0.1:8001`. Non-destructively checks port availability and aborts with a clear diagnostic message if occupied, without terminating unrelated processes.

---

## 2. Directory Structure

```text
RESUME_AND_JOB_MATCHING/
├── main.py                             # Canonical application launcher (Port 8001)
├── run_backend.py                      # Compatibility script delegating to main.py
├── start_backend.bat                   # Windows one-click launcher
├── .env.example                        # Template environment variables
├── .gitignore                          # Protects .env, databases, and uploaded resumes
├── inclusive_ats.db                    # Primary SQLite database (untracked)
├── backend/
│   ├── run.py                          # Backend-folder delegate launcher
│   ├── app/
│   │   ├── main.py                     # FastAPI application, lifespan & CORS
│   │   ├── core/
│   │   │   ├── config.py               # Explicit path anchors & environment settings
│   │   │   ├── security.py             # Password hashing (bcrypt) & JWT tokens
│   │   │   └── logging.py              # Structured application logging
│   │   ├── db/
│   │   │   ├── session.py              # Explicit SQLAlchemy engine (no silent fallbacks)
│   │   │   └── init_db.py              # Schema creation and job seeding script
│   │   ├── models/
│   │   │   └── models.py               # Normalized database entities
│   │   ├── schemas/
│   │   │   └── schemas.py              # Pydantic schemas (matching, recommendations)
│   │   ├── ml/
│   │   │   ├── preprocessing.py        # Anonymization, skills & checklist generator
│   │   │   ├── embeddings.py           # MiniLM encoder with chunk pooling
│   │   │   ├── inference.py            # Thread-safe MLInferenceService (770-dim)
│   │   │   └── artifacts/
│   │   │       └── model.pkl           # Trained model bundle
│   │   ├── utils/
│   │   │   └── file_extractor.py       # PDF/DOCX/TXT parsers & ATS scoring
│   │   ├── services/
│   │   │   ├── external_job_service.py # Adzuna & Remotive job fetching with caching
│   │   │   ├── recommendation_service.py # Dual-mode (neural match & skills overlap)
│   │   │   ├── matching_service.py
│   │   │   ├── fairness_service.py
│   │   │   └── dashboard_service.py
│   │   └── api/
│   │       ├── auth.py                 # Registration & JWT endpoints
│   │       ├── resumes.py              # Resume upload & ATS analysis
│   │       ├── jobs.py                 # Job catalog, posting & save-external
│   │       ├── recommendations.py      # Skill-based & resume-based recommendations
│   │       ├── matching.py             # Neural match compatibility & explanation
│   │       └── fairness.py             # Counterfactual sensitivity audit
│   └── tests/                          # Automated unit, integration & regression tests
├── frontend/
│   ├── index.html                      # Homepage & 3D visualization
│   ├── dashboard.html                  # Candidate overview & metrics
│   ├── jobs.html                       # Skill recommendations & job catalog
│   ├── match.html                      # AI compatibility analysis & checklists
│   ├── resumes.html                    # Resume upload & ATS analysis
│   ├── fairness.html                   # Counterfactual fairness audits
│   ├── env.js                          # Runtime public API origin configuration
│   └── assets/
│       ├── css/                        # Design tokens & styles
│       └── js/                         # API client & page controllers
└── render.yaml                         # Blueprint for cloud deployment on Render
```

---

## 3. Quick Start & Setup

### Prerequisites
- Python 3.10+ (tested on Python 3.10 and 3.11)
- Modern web browser (Chrome, Edge, Firefox, Safari)

### Step 1: Clone Repository
```bash
git clone https://github.com/sohammridha3-collab/NNDL.git
cd NNDL
```

### Step 2: Set Up Virtual Environment & Dependencies
```bash
python -m venv venv

# Windows:
.\venv\Scripts\activate

# Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### Step 3: Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
> [!IMPORTANT]
> Change `SECRET_KEY` in `.env` to a secure 32-byte secret before deploying to production.
> External job aggregation (Remotive) works out-of-the-box without credentials. To enable Adzuna, register for a free developer key at developer.adzuna.com and set `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`.

### Step 4: Launch Backend Server
Run the canonical launcher:
```bash
python main.py
```
*(On Windows, you can also double-click `start_backend.bat`)*

Verify backend status:
- **Interactive Documentation (Swagger):** `http://127.0.0.1:8001/docs`
- **Liveness Probe:** `http://127.0.0.1:8001/health`
- **Readiness Probe:** `http://127.0.0.1:8001/ready`

### Step 5: Launch Frontend Client
Serve the `frontend/` folder using any static HTTP server or VS Code Live Server:
```bash
# Using Python HTTP server:
python -m http.server 5500
```
Open `http://127.0.0.1:5500/frontend/index.html` in your browser.

---

## 4. Diagnostic Commands

If troubleshooting connectivity or startup:

```powershell
# Check liveness:
Invoke-RestMethod http://127.0.0.1:8001/health

# Check readiness and model state:
Invoke-RestMethod http://127.0.0.1:8001/ready

# Check port 8001 listener:
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
```

---

## 5. Running Automated Tests

Run the full pytest suite including unit, integration, and regression tests:
```bash
python -m pytest backend/tests -v
```

---

## 6. Model & Ethical Disclaimer

The match score produced by the PyTorch neural network reflects statistical compatibility against historical training labels. It is not an absolute determination or guarantee of candidate hiring probability. In alignment with UN Sustainable Development Goal 10 (Reduced Inequalities), all evaluations incorporate demographic anonymization, counterfactual sensitivity checks, and actionable skill checklists for self-guided career development.
