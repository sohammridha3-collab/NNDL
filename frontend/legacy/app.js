/**
 * Application Controller for Inclusive ATS Frontend
 */

let currentAuthMode = "login"; // 'login' or 'register'
let registerRole = "candidate"; // 'candidate' or 'recruiter'

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  renderAuthBadge();
  setupDropZone();
  loadSampleMatchData(1);
  lucide.createIcons();
});

// Toast notification helper
function showToast(msg, isSuccess = true) {
  const toast = document.getElementById("toast");
  const toastMsg = document.getElementById("toastMsg");
  const toastIcon = document.getElementById("toastIcon");

  toastMsg.textContent = msg;
  toastIcon.setAttribute("data-lucide", isSuccess ? "check-circle" : "alert-triangle");
  toastIcon.className = `w-5 h-5 ${isSuccess ? "text-emerald-400" : "text-amber-400"}`;
  lucide.createIcons();

  toast.classList.remove("translate-y-24", "opacity-0", "pointer-events-none");
  setTimeout(() => {
    toast.classList.add("translate-y-24", "opacity-0", "pointer-events-none");
  }, 3500);
}

// Tab Switching
function switchTab(tabName) {
  document.querySelectorAll(".tab-pane").forEach(el => el.classList.add("hidden"));
  document.querySelectorAll(".nav-btn").forEach(el => {
    el.classList.remove("text-brand-700", "bg-white", "shadow-sm");
    el.classList.add("text-slate-600");
  });

  const activeTab = document.getElementById(`tab-${tabName}`);
  const activeBtn = document.getElementById(`tabBtn-${tabName}`);
  if (activeTab) activeTab.classList.remove("hidden");
  if (activeBtn) {
    activeBtn.classList.add("text-brand-700", "bg-white", "shadow-sm");
    activeBtn.classList.remove("text-slate-600");
  }

  // Load contextual data
  if (tabName === "candidate") loadCandidatePortal();
  if (tabName === "recruiter") loadRecruiterHub();
  if (tabName === "fairness") loadFairnessView();

  lucide.createIcons();
}

// Render User Auth State
function renderAuthBadge() {
  const user = window.api ? window.api.getUser() : null;
  const container = document.getElementById("authSection");
  if (!container) return;

  if (user) {
    container.innerHTML = `
      <div class="flex items-center space-x-2">
        <div class="h-9 w-9 rounded-xl bg-emerald-100 text-emerald-800 font-bold flex items-center justify-center text-sm">
          ${user.full_name ? user.full_name.charAt(0).toUpperCase() : "U"}
        </div>
        <div class="hidden sm:block text-left">
          <p class="text-xs font-bold text-slate-800 leading-none">${user.full_name || user.email}</p>
          <span class="text-[10px] text-emerald-700 font-semibold uppercase tracking-wider">${user.role}</span>
        </div>
        <button onclick="handleLogout()" title="Log Out" class="text-slate-400 hover:text-slate-700 p-1.5 rounded-lg hover:bg-slate-100 transition">
          <i data-lucide="log-out" class="w-4 h-4"></i>
        </button>
      </div>
    `;
  } else {
    container.innerHTML = `
      <button onclick="openAuthModal('login')" class="text-sm font-semibold text-slate-700 hover:text-brand-600 px-3 py-1.5 transition">
        Sign In
      </button>
      <button onclick="openAuthModal('register')" class="bg-slate-900 text-white hover:bg-slate-800 text-sm font-semibold px-4 py-2 rounded-xl shadow-sm transition flex items-center gap-1.5">
        Get Started
      </button>
    `;
  }
  lucide.createIcons();
}

// Auth Modal
function openAuthModal(mode = "login") {
  currentAuthMode = mode;
  const modal = document.getElementById("authModal");
  const title = document.getElementById("authModalTitle");
  const submitBtn = document.getElementById("authSubmitBtn");
  const toggleBtn = document.getElementById("authToggleBtn");
  const nameField = document.getElementById("authNameField");
  const companyField = document.getElementById("authCompanyField");
  const roleSelector = document.getElementById("registerRoleSelector");

  if (mode === "login") {
    title.textContent = "Sign In to Inclusive ATS";
    submitBtn.textContent = "Sign In";
    toggleBtn.textContent = "Don't have an account? Create one";
    nameField.classList.add("hidden");
    companyField.classList.add("hidden");
    roleSelector.classList.add("hidden");
  } else {
    title.textContent = "Create Account";
    submitBtn.textContent = "Register";
    toggleBtn.textContent = "Already have an account? Sign In";
    nameField.classList.remove("hidden");
    roleSelector.classList.remove("hidden");
    setRegisterRole(registerRole);
  }
  modal.classList.remove("hidden");
  lucide.createIcons();
}

function closeAuthModal() {
  document.getElementById("authModal").classList.add("hidden");
}

function toggleAuthMode() {
  openAuthModal(currentAuthMode === "login" ? "register" : "login");
}

function setRegisterRole(role) {
  registerRole = role;
  const btnCand = document.getElementById("btnRoleCand");
  const btnRec = document.getElementById("btnRoleRec");
  const compField = document.getElementById("authCompanyField");

  if (role === "candidate") {
    btnCand.className = "py-2 rounded-lg bg-white shadow-sm text-slate-900 font-bold transition";
    btnRec.className = "py-2 rounded-lg text-slate-500 hover:text-slate-900 transition";
    compField.classList.add("hidden");
  } else {
    btnRec.className = "py-2 rounded-lg bg-white shadow-sm text-slate-900 font-bold transition";
    btnCand.className = "py-2 rounded-lg text-slate-500 hover:text-slate-900 transition";
    compField.classList.remove("hidden");
  }
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const email = document.getElementById("authEmail").value;
  const password = document.getElementById("authPassword").value;

  try {
    if (currentAuthMode === "login") {
      await window.api.login(email, password);
      showToast("Signed in successfully!");
    } else {
      const full_name = document.getElementById("authFullName").value;
      const company_name = document.getElementById("authCompany").value;
      await window.api.register({
        email,
        password,
        full_name,
        role: registerRole,
        company_name: registerRole === "recruiter" ? company_name : undefined
      });
      showToast("Account created successfully!");
    }
    closeAuthModal();
    renderAuthBadge();
  } catch (err) {
    showToast(err.message, false);
  }
}

function handleLogout() {
  window.api.logout();
  renderAuthBadge();
  showToast("Logged out successfully.");
}

// Sample Pair Loaders for Testing
function loadSampleMatchData(sampleIdx) {
  const resumeBox = document.getElementById("matcherResumeText");
  const jobBox = document.getElementById("matcherJobText");

  if (sampleIdx === 1) {
    resumeBox.value = `Alex Morgan\nSoftware Engineer\nSummary: 5+ years experience building machine learning services and backend microservices.\nSkills: Python, PyTorch, SQL, Docker, AWS, Git, Scikit-learn, Linux.\nExperience: Senior Engineer at DataAI Corp. Built real-time inference pipelines with FastAPI and deployed containers to AWS ECS.\nEducation: B.S. in Computer Science.`;
    jobBox.value = `Senior Machine Learning Engineer\nOverview: We are looking for an ML Engineer to develop state-of-the-art NLP and matching models.\nRequired Skills: Python, SQL, Docker, Machine Learning, PyTorch, AWS.\nQualifications: 4+ years delivering scalable production AI applications.`;
  } else {
    resumeBox.value = `Priya Sen\nFull Stack Developer\nSummary: Frontend and full-stack engineer with expertise in JavaScript web applications.\nSkills: JavaScript, TypeScript, React, HTML, CSS, Node.js, Git, MySQL.\nExperience: 3 years developing responsive web dashboards with React and Node REST APIs.\nEducation: B.S. in Information Systems.`;
    jobBox.value = `Lead Cloud Architect\nOverview: Looking for a Principal Cloud Architect to direct infrastructure migration to Kubernetes and Azure.\nRequired Skills: Kubernetes, Azure, Linux, Terraform, Go.\nQualifications: 8+ years architecting enterprise distributed cloud platforms.`;
  }
}

// Real AI Matching Execution
async function runAiPrediction() {
  const resumeText = document.getElementById("matcherResumeText").value;
  const jobText = document.getElementById("matcherJobText").value;

  if (!resumeText.trim() || !jobText.trim()) {
    showToast("Please provide both resume text and job description.", false);
    return;
  }

  const btn = document.getElementById("btnRunPrediction");
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader" class="w-5 h-5 animate-spin"></i><span>Running Neural Inference...</span>`;
  lucide.createIcons();

  try {
    const res = await window.api.predictMatch({
      resume_text: resumeText,
      job_text: jobText
    });

    // Populate Results
    document.getElementById("matcherResultCard").classList.remove("hidden");
    document.getElementById("resCompatibilityScore").textContent = `${res.compatibility_score}%`;
    document.getElementById("resSemanticScore").textContent = res.semantic_similarity.toFixed(3);
    document.getElementById("resSkillCoverage").textContent = `${Math.round(res.required_skill_coverage * 100)}%`;
    document.getElementById("resThreshold").textContent = res.decision_threshold.toFixed(4);
    document.getElementById("resModelVersion").textContent = res.model_version;

    const badge = document.getElementById("resClassificationBadge");
    if (res.classification === "Strong Match") {
      badge.textContent = "Strong Match";
      badge.className = "px-4 py-1.5 rounded-full text-sm font-extrabold bg-emerald-100 text-emerald-800";
    } else {
      badge.textContent = "Weaker Match";
      badge.className = "px-4 py-1.5 rounded-full text-sm font-extrabold bg-amber-100 text-amber-800";
    }

    // Skills
    const matchedContainer = document.getElementById("resMatchedSkillsContainer");
    matchedContainer.innerHTML = (res.matched_skills && res.matched_skills.length)
      ? res.matched_skills.map(s => `<span class="bg-emerald-50 text-emerald-700 border border-emerald-200 px-3 py-1 rounded-lg text-xs font-bold uppercase tracking-wider">${s}</span>`).join("")
      : `<span class="text-xs text-slate-400">None detected</span>`;

    const missingContainer = document.getElementById("resMissingSkillsContainer");
    missingContainer.innerHTML = (res.missing_skills && res.missing_skills.length)
      ? res.missing_skills.map(s => `<span class="bg-amber-50 text-amber-700 border border-amber-200 px-3 py-1 rounded-lg text-xs font-bold uppercase tracking-wider">${s}</span>`).join("")
      : `<span class="text-xs text-emerald-600 font-semibold">100% of recognized job skills matched!</span>`;

    // Recommendations
    const recList = document.getElementById("resRecommendationsList");
    recList.innerHTML = (res.recommendations && res.recommendations.length)
      ? res.recommendations.map(r => `<li>${r}</li>`).join("")
      : `<li>Resume profile aligns strongly with role criteria.</li>`;

    showToast("AI inference completed successfully!");
  } catch (err) {
    showToast(err.message, false);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
    lucide.createIcons();
  }
}

// Drag & Drop Setup
function setupDropZone() {
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("resumeFileInput");
  if (!dropZone || !fileInput) return;

  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("dragover", e => {
    e.preventDefault();
    dropZone.classList.add("border-brand-500", "bg-brand-50");
  });
  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("border-brand-500", "bg-brand-50");
  });
  dropZone.addEventListener("drop", e => {
    e.preventDefault();
    dropZone.classList.remove("border-brand-500", "bg-brand-50");
    if (e.dataTransfer.files.length) {
      handleResumeFileSelected(e.dataTransfer.files[0]);
    }
  });
}

async function handleResumeFileSelected(file) {
  if (!file) return;
  if (!window.api.getToken()) {
    showToast("Please sign in or register to upload resumes.", false);
    openAuthModal("login");
    return;
  }

  showToast(`Uploading and analyzing ${file.name}...`);
  try {
    const res = await window.api.uploadResume(file);
    showToast("Resume uploaded & parsed successfully!");
    renderActiveResumeCard(res);
    loadRecommendedJobs(5);
  } catch (err) {
    showToast(err.message, false);
  }
}

function renderActiveResumeCard(res) {
  const card = document.getElementById("activeResumeCard");
  if (!card) return;
  card.classList.remove("hidden");
  document.getElementById("cardFileName").textContent = res.file_name;
  document.getElementById("cardAtsBadge").textContent = `ATS ${Math.round(res.ats_score)}%`;
  document.getElementById("cardCompleteness").textContent = `${Math.round(res.completeness_score)}%`;
  document.getElementById("cardSkillsCount").textContent = res.skills ? res.skills.length : 0;
  window.currentActiveResumeId = res.id;
  lucide.createIcons();
}

async function runDeepResumeAnalysis() {
  if (!window.currentActiveResumeId) return;
  try {
    const data = await window.api.analyzeResume(window.currentActiveResumeId);
    alert(
      `ATS READABILITY REPORT\n` +
      `-------------------------\n` +
      `Readability Rating: ${data.readability_rating}\n` +
      `ATS Score: ${data.ats_score}%\n` +
      `Completeness: ${data.completeness_score}%\n\n` +
      `Identified Sections: ${data.identified_sections.join(", ")}\n` +
      `Missing Sections: ${data.missing_critical_sections.join(", ") || "None"}\n\n` +
      `Key Recommendations:\n- ${data.improvement_recommendations.join("\n- ")}`
    );
  } catch (err) {
    showToast(err.message, false);
  }
}

// Candidate Portal Data
async function loadCandidatePortal() {
  if (!window.api.getToken()) return;
  try {
    const dash = await window.api.getCandidateDashboard();
    if (dash.active_resume) {
      renderActiveResumeCard(dash.active_resume);
    }
    const appsList = document.getElementById("myApplicationsList");
    if (dash.applications && dash.applications.length) {
      appsList.innerHTML = dash.applications.map(a => `
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-100 flex items-center justify-between text-xs">
          <div>
            <span class="font-bold text-slate-800 block">${a.job_title}</span>
            <span class="text-slate-400">${a.company_name}</span>
          </div>
          <span class="font-bold px-2 py-0.5 rounded-full ${a.status === 'shortlisted' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-700'}">
            ${a.stage || a.status}
          </span>
        </div>
      `).join("");
    } else {
      appsList.innerHTML = `<p class="text-xs text-slate-400">No active applications yet.</p>`;
    }
    loadRecommendedJobs(5);
  } catch (err) {
    console.error(err);
  }
}

async function loadRecommendedJobs(limit = 5) {
  const container = document.getElementById("recommendedJobsContainer");
  if (!container) return;
  container.innerHTML = `<div class="p-8 text-center text-slate-400">Computing AI job matches & reranking...</div>`;

  try {
    const res = await window.api.getRecommendedJobs({ limit });
    if (!res.recommendations || !res.recommendations.length) {
      container.innerHTML = `<div class="p-8 text-center text-slate-400 bg-white rounded-2xl border border-slate-200">Upload a resume to view personalized matching job recommendations.</div>`;
      return;
    }

    container.innerHTML = res.recommendations.map(j => `
      <div class="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition space-y-3">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="flex items-center gap-2">
              <h4 class="font-bold text-slate-900 text-base">${j.title}</h4>
              <span class="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-md text-[11px] font-semibold">${j.job_type}</span>
            </div>
            <p class="text-xs text-slate-500 mt-0.5">${j.company_name} • ${j.location}</p>
          </div>
          <div class="text-right">
            <span class="text-lg font-extrabold ${j.compatibility_score >= 80 ? 'text-emerald-600' : 'text-slate-800'}">
              ${j.compatibility_score}% Match
            </span>
            <span class="text-[10px] text-slate-400 block">${j.classification}</span>
          </div>
        </div>

        <p class="text-xs text-slate-600 line-clamp-2">${j.recommendation_reason}</p>

        <div class="flex flex-wrap gap-1.5">
          ${j.matched_skills.map(s => `<span class="bg-emerald-50 text-emerald-700 text-[10px] font-bold px-2 py-0.5 rounded-md border border-emerald-100">${s}</span>`).join("")}
          ${j.missing_skills.map(s => `<span class="bg-amber-50 text-amber-700 text-[10px] font-semibold px-2 py-0.5 rounded-md border border-amber-100">+ ${s}</span>`).join("")}
        </div>

        <div class="pt-2 flex justify-end">
          <button onclick="applyJobDirectly('${j.job_id}')" class="bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold px-4 py-2 rounded-xl transition">
            Apply Now
          </button>
        </div>
      </div>
    `).join("");
    lucide.createIcons();
  } catch (err) {
    container.innerHTML = `<div class="p-8 text-center text-slate-400">${err.message}</div>`;
  }
}

async function applyJobDirectly(jobId) {
  if (!window.api.getToken()) {
    showToast("Please sign in to apply for jobs.", false);
    openAuthModal("login");
    return;
  }
  try {
    await window.api.applyToJob(jobId);
    showToast("Application submitted successfully!");
    loadCandidatePortal();
  } catch (err) {
    showToast(err.message, false);
  }
}

// Recruiter Hub Data
async function loadRecruiterHub() {
  if (!window.api.getToken()) {
    showToast("Please sign in as a recruiter to access this portal.", false);
    openAuthModal("login");
    return;
  }
  try {
    const dash = await window.api.getRecruiterDashboard();
    document.getElementById("recActiveJobsCount").textContent = dash.total_active_jobs;
    document.getElementById("recTotalApplicantsCount").textContent = dash.total_applicants;
    document.getElementById("recShortlistedCount").textContent = dash.pipeline_stages_count.shortlisted || 0;
    document.getElementById("recInterviewCount").textContent = dash.pipeline_stages_count.interviewed || 0;

    const list = document.getElementById("recruiterJobsList");
    if (dash.recent_jobs && dash.recent_jobs.length) {
      list.innerHTML = dash.recent_jobs.map(j => `
        <div class="p-4 bg-slate-50 rounded-xl border border-slate-100 flex items-center justify-between">
          <div>
            <h4 class="font-bold text-slate-900 text-sm">${j.title}</h4>
            <span class="text-xs text-slate-400">${j.category} • ${j.applicant_count} applicants</span>
          </div>
          <button onclick="viewJobApplicants('${j.id}')" class="text-xs font-bold text-brand-700 hover:underline">
            View AI Ranked Applicants →
          </button>
        </div>
      `).join("");
    } else {
      list.innerHTML = `<p class="text-xs text-slate-400">No jobs posted yet. Click 'Post New Opening' above.</p>`;
    }
  } catch (err) {
    showToast(err.message, false);
  }
}

function openPostJobModal() {
  document.getElementById("postJobModal").classList.remove("hidden");
}

function closePostJobModal() {
  document.getElementById("postJobModal").classList.add("hidden");
}

async function handlePostJobSubmit(e) {
  e.preventDefault();
  const title = document.getElementById("postJobTitle").value;
  const category = document.getElementById("postJobCategory").value;
  const job_type = document.getElementById("postJobType").value;
  const description = document.getElementById("postJobDesc").value;
  const rawSkills = document.getElementById("postJobSkills").value;
  const skills = rawSkills.split(",").map(s => s.trim().toLowerCase()).filter(Boolean);

  try {
    await window.api.createJob({
      title,
      category,
      job_type,
      description,
      skills
    });
    showToast("Job opening posted successfully!");
    closePostJobModal();
    loadRecruiterHub();
  } catch (err) {
    showToast(err.message, false);
  }
}

async function viewJobApplicants(jobId) {
  try {
    const applicants = await window.api.getJobApplicants(jobId);
    let msg = `AI RANKED APPLICANTS (TOTAL: ${applicants.length})\n-------------------------------------\n`;
    applicants.forEach((a, i) => {
      msg += `#${i+1} ${a.candidate_name} | Match Score: ${a.match_score || 0}% | Stage: ${a.stage}\n`;
    });
    alert(msg);
  } catch (err) {
    showToast(err.message, false);
  }
}

// Live SDG 10 Fairness Audit
async function runFairnessAuditLive() {
  const btn = document.getElementById("btnRunFairnessAudit");
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin"></i><span>Auditing Invariance...</span>`;
  lucide.createIcons();

  try {
    const res = await window.api.runFairnessAudit({
      name: "Live SDG 10 Counterfactual Fairness Audit"
    });

    const summary = res.demographic_parity_summary;
    document.getElementById("fAuditReduction").textContent = `${summary.demographic_bias_reduction_percentage}%`;
    document.getElementById("fAuditDev").textContent = `${summary.masked_mean_score_deviation} pts`;
    document.getElementById("fAuditFlips").textContent = `${(summary.decision_flip_rate_with_masking * 100).toFixed(1)}%`;

    const tbody = document.getElementById("fairnessTableBody");
    tbody.innerHTML = res.counterfactual_sensitivity_results.map(r => `
      <tr class="hover:bg-slate-50 transition">
        <td class="p-3.5 font-bold text-slate-900 uppercase">${r.attribute}</td>
        <td class="p-3.5 font-bold ${r.masked ? 'text-emerald-700' : 'text-amber-700'}">${r.masked ? 'Yes (Masked)' : 'No (Raw)'}</td>
        <td class="p-3.5 font-semibold text-slate-800">${r.mean_change.toFixed(2)} pts</td>
        <td class="p-3.5 text-slate-600">${r.p95_change.toFixed(2)} pts</td>
        <td class="p-3.5 font-bold ${r.flip_rate === 0 ? 'text-emerald-600' : 'text-amber-600'}">${(r.flip_rate * 100).toFixed(1)}%</td>
        <td class="p-3.5 text-slate-500">${r.total_pairs} pairs</td>
      </tr>
    `).join("");

    showToast("SDG 10 Fairness Audit completed!");
  } catch (err) {
    showToast(err.message, false);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
    lucide.createIcons();
  }
}

async function loadFairnessView() {
  try {
    const reports = await window.api.getFairnessReports();
    if (reports && reports.length) {
      const latest = reports[0];
      if (latest.metrics && latest.metrics.summary) {
        document.getElementById("fAuditReduction").textContent = `${latest.metrics.summary.demographic_bias_reduction_percentage}%`;
        document.getElementById("fAuditDev").textContent = `${latest.metrics.summary.masked_mean_score_deviation} pts`;
        document.getElementById("fAuditFlips").textContent = `${(latest.metrics.summary.decision_flip_rate_with_masking * 100).toFixed(1)}%`;
      }
      if (latest.metrics && latest.metrics.breakdown) {
        const tbody = document.getElementById("fairnessTableBody");
        tbody.innerHTML = latest.metrics.breakdown.map(r => `
          <tr class="hover:bg-slate-50 transition">
            <td class="p-3.5 font-bold text-slate-900 uppercase">${r.attribute}</td>
            <td class="p-3.5 font-bold ${r.masked ? 'text-emerald-700' : 'text-amber-700'}">${r.masked ? 'Yes (Masked)' : 'No (Raw)'}</td>
            <td class="p-3.5 font-semibold text-slate-800">${r.mean_change.toFixed(2)} pts</td>
            <td class="p-3.5 text-slate-600">${r.p95_change.toFixed(2)} pts</td>
            <td class="p-3.5 font-bold ${r.flip_rate === 0 ? 'text-emerald-600' : 'text-amber-600'}">${(r.flip_rate * 100).toFixed(1)}%</td>
            <td class="p-3.5 text-slate-500">${r.total_pairs} pairs</td>
          </tr>
        `).join("");
      }
    }
  } catch (err) {
    console.error(err);
  }
}
