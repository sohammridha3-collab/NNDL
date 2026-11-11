# Inclusive Resume and Job Matching — Frontend Web Portal
**UN Sustainable Development Goal 10: Reduced Inequalities**

A modern, production-grade frontend client built with **semantic HTML5, CSS3, and vanilla JavaScript using modern ES modules**.

---

## 1. Architecture & Design Direction

- **Styling & Theming:**
  - Modern token-based CSS (`assets/css/tokens.css`, `base.css`, `layout.css`, `components.css`, `pages.css`).
  - Palette: Deep navy and slate for navigation (`#0f172a`), crisp neutral content surfaces, vibrant teal/emerald primary accents (`#0d9488`), and restrained violet accents (`#7c3aed`) for AI features.
  - Full Light and Dark themes with persistent local storage preference.
- **Client Architecture:**
  - Native browser ES modules (`import`/`export`), no heavy external frameworks or bloated node_modules required.
  - Central API client (`assets/js/api.js`) featuring single-flight token refresh, timeout handling via `AbortController`, XHR progress tracking for multipart file uploads, and full 422 error translation.
  - Safe DOM generation (`assets/js/ui.js` using `h()` and `textContent`) preventing XSS vulnerabilities from untrusted resume or job text.
  - Real-time model score visualization and counterfactual sensitivity auditing for SDG 10.

---

## 2. Directory Structure

```
frontend/
├── assets/
│   ├── css/
│   │   ├── tokens.css         # Color palettes, typography, spacing, shadows
│   │   ├── base.css           # Global resets, accessibility, focus rings
│   │   ├── layout.css         # Shell, desktop sidebar, mobile drawer, topbar
│   │   ├── components.css     # Buttons, fields, cards, tables, toasts, dialogs
│   │   └── pages.css          # Match gauges, dropzone, metrics, pipeline
│   └── js/
│       ├── config.js          # Central API prefix & endpoints configuration
│       ├── session.js         # JWT bearer & refresh token management
│       ├── api.js             # HTTP/REST engine with error & upload handlers
│       ├── auth.js            # Route guards and role permission checks
│       ├── ui.js              # Safe DOM building, notifications, modals
│       ├── app.js             # Shell coordinator, navigation, themes
│       └── pages/             # Individual page controllers
│           ├── landing.js
│           ├── login.js
│           ├── register.js
│           ├── dashboard.js
│           ├── resumes.js
│           ├── jobs.js
│           ├── match.js
│           ├── applications.js
│           ├── recruiter.js
│           ├── admin.js
│           └── fairness.js
├── index.html                 # Project landing & AI workflow overview
├── login.html                 # Authentication & role routing
├── register.html              # Candidate/Recruiter registration
├── dashboard.html             # Candidate analytics & recommended jobs
├── resumes.html               # PDF/DOCX/TXT drag-and-drop upload & ATS scoring
├── jobs.html                  # Search, filter, bookmark & apply portal
├── match.html                 # 770-dim PyTorch neural match analysis
├── applications.html          # Candidate pipeline tracking & match history
├── recruiter.html             # Recruiter candidate ranking & job creation
├── admin.html                 # System health diagnostics & user management
├── fairness.html              # SDG 10 counterfactual sensitivity center
├── env.js                     # Public runtime backend URL configuration
└── package.json
```

---

## 3. Local Development & Setup

### Step 1: Start the FastAPI Backend (Port 8001)
```powershell
# In a terminal window:
python run_backend.py
# Or:
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```
The backend will be available at: **`http://127.0.0.1:8001`**

### Step 2: Serve the Frontend (Port 5500)
```powershell
# In a second terminal window:
cd frontend
python -m http.server 5500
```
Open your browser and navigate to: **`http://127.0.0.1:5500`**

---

## 4. Test Accounts

| Role | Email Address | Password | Permissions & Workspace |
| :--- | :--- | :--- | :--- |
| **Candidate** | `candidate@example.com` | `Candidate@12345` | Upload resumes, browse jobs, apply, view AI recommendations |
| **Recruiter** | `recruiter@techinnovate.com` | `Recruiter@12345` | Post jobs, review ranked applicants, update stages, export CSV |
| **Administrator** | `admin@inclusiveats.org` | `Admin@12345` | Platform metrics, user moderation, model diagnostics, audit logs |

---

## 5. Production Configuration (Render.com)

1. **Deploying the Backend:**
   Set environment variable:
   ```env
   ALLOWED_ORIGINS=https://YOUR-FRONTEND.onrender.com,http://127.0.0.1:5500,http://localhost:5500
   ```
2. **Deploying the Frontend (Static Site):**
   In `frontend/env.js`, set the production origin:
   ```javascript
   window.APP_CONFIG = {
     API_ORIGIN: "https://inclusive-ats-backend.onrender.com"
   };
   ```
