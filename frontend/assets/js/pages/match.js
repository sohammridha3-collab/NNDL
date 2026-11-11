/**
 * Resume-Job Matching Controller
 * Deep integration with real PyTorch MatchNetwork (770 features) & SentenceTransformer.
 */
import { Api } from "../api.js";
import { requireAuth } from "../auth.js";
import { initAppShell } from "../app.js";
import {
  $,
  h,
  icon,
  badge,
  chip,
  classificationBadge,
  fmtPct100,
  setBusy,
  toast,
  errorMessage,
  loadingState
} from "../ui.js";

let userResumes = [];
let availableJobs = [];

document.addEventListener("DOMContentLoaded", async () => {
  const user = await requireAuth();
  if (!user) return;

  initAppShell({
    user,
    activePage: "match.html",
    breadcrumbs: [{ label: "Workspace" }, { label: "AI Matching" }]
  });

  setupMatchInputs();
  await loadSelectOptions();

  // Check URL parameters for pre-selected job or resume
  const urlParams = new URLSearchParams(window.location.search);
  const paramJobId = urlParams.get("job_id");
  const paramResumeId = urlParams.get("resume_id");
  const jobSelect = $("#match-job-select");
  const resumeSelect = $("#match-resume-select");

  if (paramJobId && jobSelect) {
    jobSelect.value = paramJobId;
  }
  if (paramResumeId && resumeSelect) {
    resumeSelect.value = paramResumeId;
  }
});

async function loadSelectOptions() {
  const resumeSelect = $("#match-resume-select");
  const jobSelect = $("#match-job-select");

  try {
    userResumes = await Api.resumes.list();
    if (resumeSelect) {
      if (userResumes.length > 0) {
        resumeSelect.replaceChildren(
          h("option", { value: "" }, "— Choose an uploaded resume —"),
          ...userResumes.map(r => h("option", { value: r.id, selected: r.is_active }, `${r.file_name} (${r.ats_score}% ATS)`))
        );
      } else {
        resumeSelect.replaceChildren(
          h("option", { value: "" }, "— No saved resumes on file (paste text below) —")
        );
      }
    }
  } catch {
    if (resumeSelect) {
      resumeSelect.replaceChildren(
        h("option", { value: "" }, "— Paste resume text below —")
      );
    }
  }

  try {
    const jobs = await Api.jobs.list({ limit: 100 });
    availableJobs = jobs || [];
    if (jobSelect) {
      if (availableJobs.length > 0) {
        jobSelect.replaceChildren(
          h("option", { value: "" }, "— Choose a posted job —"),
          ...availableJobs.map(j => h("option", { value: j.id }, `${j.title} (${j.company_name})`))
        );
      } else {
        jobSelect.replaceChildren(
          h("option", { value: "" }, "— No posted jobs available (paste text below) —")
        );
      }
    }
  } catch {
    if (jobSelect) {
      jobSelect.replaceChildren(
        h("option", { value: "" }, "— Paste job description below —")
      );
    }
  }
}

function setupMatchInputs() {
  const form = $("#match-form");
  const analyzeBtn = $("#analyze-match-btn");
  const resumeSelect = $("#match-resume-select");
  const resumeTextarea = $("#match-resume-text");
  const jobSelect = $("#match-job-select");
  const jobTextarea = $("#match-job-text");
  const sampleBtn = $("#load-sample-btn");

  // Sample data button for quick testing
  if (sampleBtn) {
    sampleBtn.addEventListener("click", () => {
      resumeTextarea.value = `Senior Machine Learning & Backend Engineer with 6 years of experience building scalable microservices and predictive pipelines.
Skills: Python, PyTorch, Docker, Kubernetes, SQL, PostgreSQL, REST API, Git, Linux, AWS, Machine Learning.
Experience:
- Designed and maintained high-throughput inference services using PyTorch and FastAPI.
- Built containerized deployment pipelines using Docker, Kubernetes, and AWS ECS.
- Automated relational database migrations and queries in PostgreSQL.`;

      jobTextarea.value = `Lead AI / ML Systems Engineer
We are seeking an experienced Machine Learning and Backend Engineer to develop production inference architectures.
Required Skills: Python, PyTorch, Docker, Kubernetes, PostgreSQL, REST API, Machine Learning.
Qualifications:
- 5+ years of production experience in Python and machine learning deployment.
- Strong knowledge of container orchestration (Docker, Kubernetes) and cloud infrastructure.
- Experience with relational databases and RESTful API design.`;

      if (resumeSelect) resumeSelect.value = "";
      if (jobSelect) jobSelect.value = "";
      toast("Sample pair loaded! Click 'Analyze Match' below.", { type: "info" });
    });
  }

  // Mutual synchronization: typing in textarea clears select dropdown; selecting clears textarea
  if (resumeSelect && resumeTextarea) {
    resumeSelect.addEventListener("change", () => {
      if (resumeSelect.value) resumeTextarea.value = "";
    });
    resumeTextarea.addEventListener("input", () => {
      if (resumeTextarea.value.trim().length > 0) resumeSelect.value = "";
    });
  }

  if (jobSelect && jobTextarea) {
    jobSelect.addEventListener("change", () => {
      if (jobSelect.value) jobTextarea.value = "";
    });
    jobTextarea.addEventListener("input", () => {
      if (jobTextarea.value.trim().length > 0) jobSelect.value = "";
    });
  }

  // Prevent accidental form submissions & browser page reloads
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      e.stopPropagation();
      runMatch();
      return false;
    });
  }

  if (analyzeBtn) {
    analyzeBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      runMatch();
    });
  }
}

async function runMatch() {
  const resumeSelect = $("#match-resume-select");
  const resumeTextarea = $("#match-resume-text");
  const jobSelect = $("#match-job-select");
  const jobTextarea = $("#match-job-text");
  const analyzeBtn = $("#analyze-match-btn");
  const resultsContainer = $("#match-results-container");

  const pastedResume = resumeTextarea ? resumeTextarea.value.trim() : "";
  const selectedResumeId = resumeSelect ? resumeSelect.value.trim() : "";

  const pastedJob = jobTextarea ? jobTextarea.value.trim() : "";
  const selectedJobId = jobSelect ? jobSelect.value.trim() : "";

  // 1. Validation with clear, actionable user messages
  if (!pastedResume && !selectedResumeId) {
    toast("Please select an uploaded resume or paste your resume text.", { type: "error" });
    if (resumeSelect) resumeSelect.focus();
    return;
  }

  if (!pastedJob && !selectedJobId) {
    toast("Please select a posted job or paste the job description.", { type: "error" });
    if (jobSelect) jobSelect.focus();
    return;
  }

  // 2. Define input precedence clearly:
  // If custom text is pasted in the textarea, prioritize it. Otherwise use the selected ID.
  const payload = {};
  if (pastedResume.length >= 20) {
    payload.resume_text = pastedResume;
  } else if (selectedResumeId) {
    payload.resume_id = selectedResumeId;
  } else {
    toast("Pasted resume text is too short. Please provide at least 20 characters.", { type: "error" });
    if (resumeTextarea) resumeTextarea.focus();
    return;
  }

  if (pastedJob.length >= 20) {
    payload.job_text = pastedJob;
  } else if (selectedJobId) {
    payload.job_id = selectedJobId;
  } else {
    toast("Pasted job text is too short. Please provide at least 20 characters.", { type: "error" });
    if (jobTextarea) jobTextarea.focus();
    return;
  }

  setBusy(analyzeBtn, true, "Running Neural Inference…");
  resultsContainer.replaceChildren(
    loadingState("Encoding text via SentenceTransformers & computing 770-dim feature vector…")
  );

  try {
    const result = await Api.matching.predict(payload);
    renderMatchResults(resultsContainer, result);
    resultsContainer.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    resultsContainer.replaceChildren(
      h("div", { class: "notice notice--error" },
        icon("alert", { size: 20 }),
        h("div", {},
          h("strong", { class: "notice__title", text: "Match Analysis Failed" }),
          h("p", { text: errorMessage(err, "Model inference could not be completed.") })
        )
      )
    );
  } finally {
    // Always restore the button after completion
    setBusy(analyzeBtn, false);
  }
}

function renderMatchResults(container, res) {
  container.replaceChildren();

  const isStrong = /strong/i.test(res.classification);
  const scorePct = Number(res.compatibility_score).toFixed(1);
  const strokeDash = 2 * Math.PI * 45;
  const strokeOffset = strokeDash - (strokeDash * Math.min(100, Math.max(0, res.compatibility_score))) / 100;

  // 1. Hero Score Banner
  const heroCard = h("div", { class: "score-display" },
    // Circular Gauge
    h("div", { class: "score-gauge" },
      h("svg", { viewBox: "0 0 100 100", "aria-label": `Compatibility score: ${scorePct}%` },
        h("circle", { cx: 50, cy: 50, r: 45, class: "score-gauge__bg" }),
        h("circle", {
          cx: 50,
          cy: 50,
          r: 45,
          class: "score-gauge__meter",
          style: {
            strokeDasharray: `${strokeDash}`,
            strokeDashoffset: `${strokeOffset}`,
            stroke: isStrong ? "var(--color-success)" : "var(--color-warning)"
          }
        })
      ),
      h("div", { class: "score-gauge__value" },
        h("span", { class: "score-gauge__number", text: `${scorePct}%` }),
        h("span", { class: "score-gauge__label", text: "Match Fit" })
      )
    ),

    // Details & Rule
    h("div", { class: "score-details" },
      h("div", { style: { display: "flex", alignItems: "center", gap: "var(--space-2)", marginBottom: "var(--space-1)" } },
        classificationBadge(res.classification),
        h("span", { class: "badge badge--neutral", text: res.model_version || "PyTorch MLP v1.0" })
      ),
      h("h3", { style: { fontSize: "var(--font-size-lg)", color: "var(--text-primary)" }, text: isStrong ? "High Compatibility Alignment" : "Partial or Weaker Match" }),
      h("p", { style: { fontSize: "var(--font-size-sm)", color: "var(--text-secondary)" }, text: `Model Probability (${(res.compatibility_score / 100).toFixed(4)}) evaluated against validation decision threshold (${res.decision_threshold}).` }),
      
      // Explicit dataset-label notice
      h("div", { class: "notice notice--info", style: { marginTop: "var(--space-2)", padding: "var(--space-2) var(--space-3)", fontSize: "var(--font-size-xs)" } },
        h("span", { style: { fontWeight: "var(--font-weight-semibold)" }, text: "Notice: " }),
        document.createTextNode("This compatibility score is a neural dataset-label estimate trained on historical recruitment benchmarks. It evaluates technical text alignment and is not a hiring guarantee, hiring decision, or employment qualification assessment.")
      ),

      h("div", { style: { display: "flex", gap: "var(--space-4)", marginTop: "var(--space-3)", fontSize: "var(--font-size-xs)", color: "var(--text-muted)" } },
        h("span", {}, icon("sparkles", { size: 12 }), ` Semantic Similarity: ${(res.semantic_similarity).toFixed(4)}`),
        h("span", {}, icon("check", { size: 12 }), ` Required Skill Coverage: ${(res.required_skill_coverage * 100).toFixed(1)}%`)
      )
    )
  );
  container.appendChild(heroCard);

  // 2. Skills Analysis Breakdown Card
  const skillsCard = h("div", { class: "card", style: { marginBottom: "var(--space-6)" } },
    h("h4", { class: "card__title", style: { marginBottom: "var(--space-3)" } }, icon("layers", { size: 18 }), " Extracted Skill Breakdown"),
    h("div", { class: "grid grid--cols-2", style: { gap: "var(--space-4)" } },
      // Matched Skills
      h("div", {},
        h("h5", { style: { fontSize: "var(--font-size-sm)", color: "var(--color-success-text)", marginBottom: "var(--space-2)", display: "flex", alignItems: "center", gap: "var(--space-1)" } },
          icon("check", { size: 14 }), ` Matched Competencies (${res.matched_skills ? res.matched_skills.length : 0})`
        ),
        res.matched_skills && res.matched_skills.length > 0
          ? h("div", { class: "chip-list" }, res.matched_skills.map(s => chip(s, "matched")))
          : h("p", { class: "field__hint", text: "No overlapping canonical skills identified." })
      ),

      // Missing Skills
      h("div", {},
        h("h5", { style: { fontSize: "var(--font-size-sm)", color: "var(--color-danger-text)", marginBottom: "var(--space-2)", display: "flex", alignItems: "center", gap: "var(--space-1)" } },
          icon("alert", { size: 14 }), ` Missing Job Skills (${res.missing_skills ? res.missing_skills.length : 0})`
        ),
        res.missing_skills && res.missing_skills.length > 0
          ? h("div", { class: "chip-list" }, res.missing_skills.map(s => chip(s, "missing")))
          : h("p", { class: "field__hint", text: "All recognized job skills are present in resume!" })
      )
    )
  );
  container.appendChild(skillsCard);

  // 3. Actionable Recommendations & Explainable Factors
  const recsCard = h("div", { class: "card" },
    h("h4", { class: "card__title", style: { marginBottom: "var(--space-3)" } }, icon("sparkles", { size: 18 }), " Optimization & Recommendations"),
    res.recommendations && res.recommendations.length > 0
      ? h("ul", { style: { paddingLeft: "var(--space-5)", fontSize: "var(--font-size-sm)", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: "var(--space-2)" } },
          res.recommendations.map(r => h("li", { text: r }))
        )
      : h("p", { class: "field__hint", text: "No specific recommendations generated for this pair." }),

    // SDG 10 Compliance Callout
    h("div", { class: "notice notice--info", style: { marginTop: "var(--space-4)", marginBottom: 0 } },
      icon("shield", { size: 16 }),
      h("p", { text: "SDG 10 Ethical Standard: Demographic identifiers (name, pronouns, age, contact details) were neutralized prior to feature extraction to prevent non-merit bias." })
    )
  );
  container.appendChild(recsCard);
}

