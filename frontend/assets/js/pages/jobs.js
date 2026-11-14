/**
 * Job Opportunities & Skill-Based Discovery Controller
 * Integrates dual-source recommendations (Curated Dataset & Live Vacancies)
 * with interactive editable skill chips, résumé extraction, and ML reranking.
 */
import { Api } from "../api.js";
import { session } from "../session.js";
import { initAppShell } from "../app.js";
import {
  $,
  $$,
  h,
  icon,
  badge,
  chip,
  classificationBadge,
  fmtDate,
  fmtSalary,
  loadingState,
  emptyState,
  errorState,
  openDialog,
  setBusy,
  toast,
  errorMessage,
  debounce,
  notice
} from "../ui.js";

// Active view mode: "recommendations" or "catalog"
let currentMode = "recommendations";

// Skill-Based Recommendations Filter State
let skillFilter = {
  skills: ["Python", "SQL", "Docker", "Machine Learning"],
  preferred_titles: [],
  resume_id: "",
  resume_text: "",
  location: "",
  job_type: "",
  experience_level: "",
  category: "",
  include_external: true,
  limit: 12,
  offset: 0
};

// All Jobs Catalog Filter State
let catalogFilter = {
  q: "",
  category: "",
  job_type: "",
  location: "",
  sort: "newest",
  limit: 12,
  offset: 0
};

let currentUser = null;
let savedJobIds = new Set();
let userResumes = [];

document.addEventListener("DOMContentLoaded", async () => {
  if (session.isSignedIn()) {
    try {
      currentUser = await Api.auth.me();
      session.setUser(currentUser);
    } catch {
      currentUser = null;
    }
  }

  initAppShell({
    user: currentUser,
    activePage: "jobs.html",
    breadcrumbs: [{ label: "Workspace" }, { label: "Job Opportunities" }]
  });

  setupModeSwitcher();
  setupSkillChips();
  setupRecommendationsControls();
  setupCatalogControls();

  await loadUserResumes();
  await loadSavedJobs();

  // Load initial recommendations
  loadSkillRecommendations();
});

/* ==============================================================================
 * Mode Switcher (Recommendations vs All Jobs Catalog)
 * ============================================================================== */
function setupModeSwitcher() {
  const recTabBtn = $("#tab-recommendations-btn");
  const catTabBtn = $("#tab-catalog-btn");
  const recPanel = $("#recommendations-panel");
  const catPanel = $("#catalog-panel");
  const resultsTitle = $("#results-title");
  const resultsSubtitle = $("#results-subtitle");

  recTabBtn?.addEventListener("click", () => {
    currentMode = "recommendations";
    recTabBtn.className = "btn btn--sm btn--primary";
    recTabBtn.setAttribute("aria-selected", "true");
    catTabBtn.className = "btn btn--sm btn--ghost";
    catTabBtn.setAttribute("aria-selected", "false");

    if (recPanel) recPanel.style.display = "block";
    if (catPanel) catPanel.style.display = "none";
    if (resultsTitle) resultsTitle.textContent = "Recommended Opportunities";
    if (resultsSubtitle) resultsSubtitle.textContent = "Ranked by semantic alignment and skill coverage";

    loadSkillRecommendations();
  });

  catTabBtn?.addEventListener("click", () => {
    currentMode = "catalog";
    catTabBtn.className = "btn btn--sm btn--primary";
    catTabBtn.setAttribute("aria-selected", "true");
    recTabBtn.className = "btn btn--sm btn--ghost";
    recTabBtn.setAttribute("aria-selected", "false");

    if (recPanel) recPanel.style.display = "none";
    if (catPanel) catPanel.style.display = "block";
    if (resultsTitle) resultsTitle.textContent = "All Jobs Catalog";
    if (resultsSubtitle) resultsSubtitle.textContent = "Browse verified database postings";

    loadCatalogJobs();
  });
}

/* ==============================================================================
 * Interactive Editable Skill Chips
 * ============================================================================== */
function setupSkillChips() {
  const chipInput = $("#skill-chip-input");

  renderSkillChips();

  chipInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      const val = chipInput.value.trim().replace(/^,+|,+$/g, "");
      if (val) {
        addSkill(val);
        chipInput.value = "";
      }
    } else if (e.key === "Backspace" && !chipInput.value && skillFilter.skills.length > 0) {
      removeSkill(skillFilter.skills[skillFilter.skills.length - 1]);
    }
  });

  // Suggestion buttons
  $$("[data-add-skill]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const skillName = btn.getAttribute("data-add-skill");
      if (skillName) addSkill(skillName);
    });
  });
}

function renderSkillChips() {
  const container = $("#skill-chips-box");
  const chipInput = $("#skill-chip-input");
  const countBadge = $("#skill-count-badge");
  if (!container || !chipInput) return;

  // Clear existing rendered chips except the text input
  Array.from(container.children).forEach((child) => {
    if (child !== chipInput) child.remove();
  });

  skillFilter.skills.forEach((skill) => {
    const chipEl = h("span", {
      class: "chip chip--accent",
      style: {
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "3px 10px",
        borderRadius: "var(--radius-full)",
        background: "rgba(20, 184, 166, 0.15)",
        border: "1px solid rgba(20, 184, 166, 0.4)",
        color: "var(--color-primary)",
        fontSize: "12px",
        fontWeight: "500"
      }
    },
      document.createTextNode(skill),
      h("button", {
        type: "button",
        "aria-label": `Remove ${skill}`,
        style: {
          background: "transparent",
          border: "none",
          cursor: "pointer",
          padding: "0",
          color: "var(--color-primary)",
          display: "flex",
          alignItems: "center",
          fontSize: "14px",
          lineHeight: "1"
        },
        onclick: (e) => {
          e.stopPropagation();
          removeSkill(skill);
        }
      }, "×")
    );
    container.insertBefore(chipEl, chipInput);
  });

  if (countBadge) {
    countBadge.textContent = `${skillFilter.skills.length} ${skillFilter.skills.length === 1 ? "skill" : "skills"}`;
  }
}

function addSkill(name) {
  const trimmed = name.trim();
  if (!trimmed) return;
  const exists = skillFilter.skills.some((s) => s.toLowerCase() === trimmed.toLowerCase());
  if (!exists) {
    skillFilter.skills.push(trimmed);
    renderSkillChips();
  }
}

function removeSkill(name) {
  skillFilter.skills = skillFilter.skills.filter((s) => s.toLowerCase() !== name.toLowerCase());
  renderSkillChips();
}

/* ==============================================================================
 * Flow Stepper & Progress State Helpers
 * ============================================================================== */
function updateStepper(step) {
  const steps = [
    { pill: $("#step-pill-1"), num: $("#step-num-1") },
    { pill: $("#step-pill-2"), num: $("#step-num-2") },
    { pill: $("#step-pill-3"), num: $("#step-num-3") },
    { pill: $("#step-pill-4"), num: $("#step-num-4") },
    { pill: $("#step-pill-5"), num: $("#step-num-5") }
  ];

  steps.forEach((s, idx) => {
    if (!s.pill || !s.num) return;
    const stepIdx = idx + 1;
    if (stepIdx < step) {
      s.pill.style.color = "var(--color-success)";
      s.pill.style.fontWeight = "500";
      s.num.style.background = "var(--color-success)";
      s.num.style.color = "#fff";
      s.num.innerHTML = "✓";
    } else if (stepIdx === step) {
      s.pill.style.color = "var(--color-primary)";
      s.pill.style.fontWeight = "600";
      s.num.style.background = "var(--color-primary)";
      s.num.style.color = "#fff";
      s.num.textContent = String(stepIdx);
    } else {
      s.pill.style.color = "var(--text-muted)";
      s.pill.style.fontWeight = "500";
      s.num.style.background = "var(--bg-surface-3)";
      s.num.style.color = "var(--text-secondary)";
      s.num.textContent = String(stepIdx);
    }
  });
}

function setProgressState(show, title = "", desc = "") {
  const banner = $("#search-progress-banner");
  const titleEl = $("#search-progress-title");
  const descEl = $("#search-progress-desc");
  if (!banner) return;
  if (!show) {
    banner.style.display = "none";
    return;
  }
  banner.style.display = "block";
  if (titleEl) titleEl.textContent = title;
  if (descEl) descEl.textContent = desc;
}

function fmtRetrievalTime(isoStr) {
  if (!isoStr) return null;
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return String(isoStr);
    const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
    if (diffSec < 60) return "just now";
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return null;
  }
}

/* ==============================================================================
 * Résumé Extraction & Recommendations Controls
 * ============================================================================== */
async function loadUserResumes() {
  const select = $("#rec-resume-select");
  if (!select) return;

  if (!session.isSignedIn()) {
    select.replaceChildren(h("option", { value: "" }, "Sign in to extract from stored résumé"));
    return;
  }

  try {
    userResumes = await Api.resumes.list();
    if (userResumes.length > 0) {
      select.replaceChildren(
        h("option", { value: "" }, "— Choose a stored résumé —"),
        ...userResumes.map((r) => h("option", { value: r.id, selected: r.is_active }, `${r.file_name} (${r.ats_score}% ATS)`))
      );
      // If there's an active resume, pre-select it
      const active = userResumes.find((r) => r.is_active);
      if (active) skillFilter.resume_id = active.id;
    } else {
      select.replaceChildren(h("option", { value: "" }, "No saved résumés found (add skills above)"));
    }
  } catch {
    select.replaceChildren(h("option", { value: "" }, "Unable to load saved résumés"));
  }
}

function setupRecommendationsControls() {
  const findBtn = $("#find-matches-btn");
  const resetBtn = $("#reset-recommendations-btn");
  const extractBtn = $("#extract-skills-btn");
  const resumeSelect = $("#rec-resume-select");
  const uploadBtn = $("#rec-upload-file-btn");
  const fileInput = $("#rec-resume-file-input");
  const uploadText = $("#rec-upload-file-btn-text");
  const togglePasteBtn = $("#toggle-paste-resume-btn");
  const pasteContainer = $("#rec-resume-paste-container");
  const pasteTextEl = $("#rec-resume-paste-text");
  const prefTitlesInput = $("#rec-preferred-titles-input");
  const locInput = $("#rec-location-input");
  const arrSelect = $("#rec-arrangement-select");
  const expSelect = $("#rec-experience-select");
  const catSelect = $("#rec-category-select");
  const extCheck = $("#include-external-checkbox");

  updateStepper(1);

  resumeSelect?.addEventListener("change", () => {
    skillFilter.resume_id = resumeSelect.value;
    if (resumeSelect.value) {
      updateStepper(2);
    }
  });

  // Direct File Upload handler
  uploadBtn?.addEventListener("click", () => {
    fileInput?.click();
  });

  fileInput?.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (uploadText) uploadText.textContent = `Uploading ${file.name}…`;
    setProgressState(true, "Reading résumé…", `Uploading and parsing ${file.name}…`);
    updateStepper(2);
    try {
      const uploaded = await Api.resumes.upload(file);
      userResumes.push(uploaded);
      if (resumeSelect) {
        const opt = h("option", { value: uploaded.id, selected: true }, `${uploaded.file_name} (${uploaded.ats_score}% ATS)`);
        resumeSelect.appendChild(opt);
        resumeSelect.value = uploaded.id;
      }
      skillFilter.resume_id = uploaded.id;
      if (uploadText) uploadText.textContent = file.name;
      toast(`Uploaded ${file.name}. Summarizing profile…`, { type: "success" });
      await handleProfileSummaryExtraction();
    } catch (err) {
      if (uploadText) uploadText.textContent = "Upload File (.pdf/.docx)";
      toast(errorMessage(err, "Failed to upload résumé file."), { type: "error" });
    } finally {
      setProgressState(false);
    }
  });

  // Toggle Plain-Text Paste Container
  togglePasteBtn?.addEventListener("click", () => {
    if (pasteContainer) {
      const isHidden = pasteContainer.style.display === "none";
      pasteContainer.style.display = isHidden ? "block" : "none";
      if (isHidden) pasteTextEl?.focus();
    }
  });

  // Preferred Titles input change
  prefTitlesInput?.addEventListener("input", () => {
    skillFilter.preferred_titles = prefTitlesInput.value
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    updateStepper(3);
  });

  locInput?.addEventListener("input", () => updateStepper(3));
  arrSelect?.addEventListener("change", () => updateStepper(3));
  expSelect?.addEventListener("change", () => updateStepper(3));
  catSelect?.addEventListener("change", () => updateStepper(3));

  // Extract & Profile Summary Button
  extractBtn?.addEventListener("click", async () => {
    await handleProfileSummaryExtraction();
  });

  findBtn?.addEventListener("click", () => {
    if (prefTitlesInput) {
      skillFilter.preferred_titles = prefTitlesInput.value
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
    }
    skillFilter.location = locInput ? locInput.value.trim() : "";
    skillFilter.job_type = arrSelect ? arrSelect.value : "";
    skillFilter.experience_level = expSelect ? expSelect.value : "";
    skillFilter.category = catSelect ? catSelect.value : "";
    skillFilter.include_external = extCheck ? extCheck.checked : true;
    skillFilter.offset = 0;
    loadSkillRecommendations();
  });

  resetBtn?.addEventListener("click", () => {
    skillFilter.skills = ["Python", "SQL", "Docker", "Machine Learning"];
    skillFilter.preferred_titles = [];
    skillFilter.resume_id = "";
    skillFilter.resume_text = "";
    skillFilter.location = "";
    skillFilter.job_type = "";
    skillFilter.experience_level = "";
    skillFilter.category = "";
    skillFilter.include_external = true;
    skillFilter.offset = 0;

    renderSkillChips();
    if (locInput) locInput.value = "";
    if (arrSelect) arrSelect.value = "";
    if (expSelect) expSelect.value = "";
    if (catSelect) catSelect.value = "";
    if (extCheck) extCheck.checked = true;
    if (resumeSelect) resumeSelect.value = "";
    if (prefTitlesInput) prefTitlesInput.value = "";
    if (pasteTextEl) pasteTextEl.value = "";
    const previewContainer = $("#profile-summary-preview");
    if (previewContainer) previewContainer.style.display = "none";
    const alertContainer = $("#resume-recovery-alert");
    if (alertContainer) {
      alertContainer.style.display = "none";
      alertContainer.replaceChildren();
    }

    updateStepper(1);
    loadSkillRecommendations();
  });

  // Quick location tags (Kolkata, Delhi, Bengaluru, Remote)
  $$("[data-set-location]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const loc = btn.getAttribute("data-set-location");
      if (locInput) {
        locInput.value = loc;
        skillFilter.location = loc;
        skillFilter.offset = 0;
        updateStepper(3);
        loadSkillRecommendations();
      }
    });
  });

  // External API status badge click -> modal
  const apiBadge = $("#external-api-badge");
  apiBadge?.addEventListener("click", () => {
    openProviderSetupDialog();
  });
}

/* ==============================================================================
 * Résumé Profile Extraction & Summary Handler
 * ============================================================================== */
async function handleProfileSummaryExtraction() {
  const extractBtn = $("#extract-skills-btn");
  const resumeSelect = $("#rec-resume-select");
  const pasteTextEl = $("#rec-resume-paste-text");
  const alertContainer = $("#resume-recovery-alert");
  const previewContainer = $("#profile-summary-preview");
  const prefTitlesInput = $("#rec-preferred-titles-input");
  const titlesPills = $("#detected-titles-pills");
  const employmentList = $("#profile-employment-list");
  const tenureBadge = $("#profile-tenure-badge");
  const locInput = $("#rec-location-input");

  const pastedText = pasteTextEl ? pasteTextEl.value.trim() : "";
  const selectedResumeId = resumeSelect ? resumeSelect.value : skillFilter.resume_id;

  if (!pastedText && !selectedResumeId) {
    toast("Please select a stored résumé, upload a file, or paste résumé text.", { type: "info" });
    return;
  }

  setBusy(extractBtn, true, "Analyzing Profile…");
  setProgressState(true, "Reading résumé & parsing profile…", "Extracting canonical skills, detecting role titles, and calculating non-overlapping tenure…");
  try {
    const payload = {
      resume_id: selectedResumeId || undefined,
      resume_text: pastedText || undefined
    };

    const res = await Api.recommendations.profileSummary(payload);

    // Scanned or unreadable document recovery check
    if (res.is_scanned || res.recovery_needed) {
      if (alertContainer) {
        alertContainer.style.display = "block";
        alertContainer.replaceChildren(
          notice(
            "warning",
            "Scanned / Image-Based PDF Detected",
            res.recovery_message || "This résumé lacks a searchable text layer. To get accurate match recommendations, please paste your résumé text below or upload a text-searchable PDF/DOCX.",
            h("div", { style: { marginTop: "var(--space-2)" } },
              h("button", {
                type: "button",
                class: "btn btn--sm btn--secondary",
                onclick: () => {
                  const pasteBox = $("#rec-resume-paste-container");
                  if (pasteBox) {
                    pasteBox.style.display = "block";
                    pasteTextEl?.focus();
                  }
                }
              }, "Paste Plain Text")
            )
          )
        );
      }
      if (previewContainer) previewContainer.style.display = "none";
      toast("Scanned document detected. Please paste text or upload a searchable file.", { type: "warning" });
      return;
    }

    // Document is readable and parsed
    if (alertContainer) {
      alertContainer.style.display = "none";
      alertContainer.replaceChildren();
    }

    // Save extracted text for neural matching
    skillFilter.resume_text = res.raw_text || pastedText;
    if (selectedResumeId) skillFilter.resume_id = selectedResumeId;

    // Merge extracted canonical skills into chips
    if (res.skills && res.skills.length > 0) {
      res.skills.forEach((s) => addSkill(s));
    }

    // Update non-overlapping tenure badge
    if (tenureBadge) {
      tenureBadge.textContent = `Experience: ${res.total_experience_years.toFixed(1)} yrs (non-overlapping)`;
    }

    // Update role titles
    const titles = res.detected_titles || [];
    if (res.primary_role && !titles.includes(res.primary_role)) {
      titles.unshift(res.primary_role);
    }
    skillFilter.preferred_titles = titles;

    if (prefTitlesInput) {
      prefTitlesInput.value = titles.join(", ");
    }

    // Render detected titles pills
    if (titlesPills) {
      titlesPills.replaceChildren(
        ...titles.map((t) => {
          return h("button", {
            type: "button",
            class: "btn-tag",
            onclick: () => {
              const current = (prefTitlesInput?.value || "").split(",").map((x) => x.trim()).filter(Boolean);
              if (!current.includes(t)) {
                current.push(t);
                if (prefTitlesInput) prefTitlesInput.value = current.join(", ");
                skillFilter.preferred_titles = current;
                updateStepper(3);
              }
            }
          }, `+ ${t}`);
        })
      );
    }

    // Render non-overlapping employment history list
    if (employmentList) {
      if (res.employment_history && res.employment_history.length > 0) {
        employmentList.replaceChildren(
          h("ul", { style: { margin: 0, paddingLeft: "1.2rem", listStyle: "disc" } },
            ...res.employment_history.map((e) => {
              const dates = `${e.start_date || "N/A"} – ${e.end_date || (e.is_current ? "Present" : "N/A")}`;
              const dur = e.duration_months ? ` (${e.duration_months} mos)` : "";
              return h("li", { style: { marginBottom: "2px" } },
                h("strong", {}, e.title || "Role"),
                document.createTextNode(` at ${e.company || "Organization"} • ${dates}${dur}`)
              );
            })
          )
        );
      } else {
        employmentList.replaceChildren(
          document.createTextNode(`Evaluated overall technical profile (${res.total_experience_years.toFixed(1)} yrs calculated tenure).`)
        );
      }
    }

    // Autofill detected location if input is empty
    if (res.detected_location && locInput && !locInput.value.trim()) {
      locInput.value = res.detected_location;
      skillFilter.location = res.detected_location;
    }

    if (previewContainer) {
      previewContainer.style.display = "block";
    }

    updateStepper(3);
    toast(`Profile extracted! Verified ${res.skills.length} skills and ${res.total_experience_years.toFixed(1)} yrs experience.`, { type: "success" });
  } catch (err) {
    toast(errorMessage(err, "Failed to analyze résumé profile."), { type: "error" });
  } finally {
    setBusy(extractBtn, false);
    setProgressState(false);
  }
}

/* ==============================================================================
 * Broadening Suggestions Handler (Explicit User-Controlled Broadening)
 * ============================================================================== */
function applyBroadeningSuggestion(sug) {
  const locInput = $("#rec-location-input");
  const arrSelect = $("#rec-arrangement-select");
  const expSelect = $("#rec-experience-select");
  const catSelect = $("#rec-category-select");

  const sugLower = (sug || "").toLowerCase();
  if (sugLower.includes("clear location") || sugLower.includes("any location")) {
    if (locInput) locInput.value = "";
    skillFilter.location = "";
  } else if (sugLower.includes("remote")) {
    if (arrSelect) arrSelect.value = "remote";
    skillFilter.job_type = "remote";
  } else if (sugLower.includes("arrangement")) {
    if (arrSelect) arrSelect.value = "";
    skillFilter.job_type = "";
  } else if (sugLower.includes("experience")) {
    if (expSelect) expSelect.value = "";
    skillFilter.experience_level = "";
  } else if (sugLower.includes("category")) {
    if (catSelect) catSelect.value = "";
    skillFilter.category = "";
  } else if (sugLower.includes("skill") || sugLower.includes("broaden")) {
    if (catSelect) catSelect.value = "";
    skillFilter.category = "";
  }
  skillFilter.offset = 0;
  updateStepper(3);
  loadSkillRecommendations();
  toast(`Applied suggestion: "${sug}"`, { type: "info" });
}

/* ==============================================================================
 * Load Skill-Based Recommendations
 * ============================================================================== */
async function loadSkillRecommendations() {
  const container = $("#jobs-grid-container");
  const paginationContainer = $("#jobs-pagination-container");
  const countBadge = $("#results-count-badge");
  const apiBadge = $("#external-api-badge");
  const findBtn = $("#find-matches-btn");
  const resetBtn = $("#reset-recommendations-btn");
  const extractBtn = $("#extract-skills-btn");
  const uploadBtn = $("#rec-upload-file-btn");
  if (!container) return;

  // Prevent duplicate submissions by locking action buttons
  setBusy(findBtn, true, "Finding Matches…");
  if (resetBtn) resetBtn.disabled = true;
  if (extractBtn) extractBtn.disabled = true;
  if (uploadBtn) uploadBtn.disabled = true;

  updateStepper(4);
  setProgressState(true, "Searching connected sources…", "Querying platform catalog and live authorized API feeds…");
  container.replaceChildren(loadingState("Searching connected sources & evaluating candidate fit…"));

  try {
    const payload = {
      skills: skillFilter.skills,
      preferred_titles: skillFilter.preferred_titles,
      resume_id: skillFilter.resume_id || undefined,
      resume_text: skillFilter.resume_text || undefined,
      location: skillFilter.location || undefined,
      job_type: skillFilter.job_type || undefined,
      experience_level: skillFilter.experience_level || undefined,
      category: skillFilter.category || undefined,
      include_external: skillFilter.include_external,
      limit: skillFilter.limit,
      offset: skillFilter.offset
    };

    setProgressState(true, "Ranking results…", "Evaluating semantic alignment, qualification overlap, and neural model compatibility…");
    const res = await Api.recommendations.bySkills(payload);

    // Update API provider badge
    if (apiBadge && res.api_status) {
      if (res.api_status.configured) {
        apiBadge.className = "badge badge--success";
        apiBadge.textContent = "Live Vacancies: Adzuna (India) Active";
      } else {
        apiBadge.className = "badge badge--warning";
        apiBadge.textContent = "Live Vacancies: Setup Required (India)";
      }
      apiBadge.title = res.api_status.message || "Click for details and configuration guide";
    }

    // Inform user if searching Indian cities while Adzuna API is unconfigured
    const noticeBanner = $("#provider-notice-banner");
    const locLower = (skillFilter.location || "").toLowerCase();
    const isIndianCity = ["kolkata", "delhi", "bengaluru", "bangalore", "mumbai", "pune", "hyderabad", "chennai", "india"].some(c => locLower.includes(c));

    if (noticeBanner) {
      if (isIndianCity && res.api_status && !res.api_status.configured) {
        noticeBanner.style.display = "block";
        noticeBanner.replaceChildren(
          notice(
            "info",
            `Live Indian Vacancies Setup Required (${skillFilter.location})`,
            `Live search across ${skillFilter.location} requires free Adzuna API credentials (ADZUNA_APP_ID / ADZUNA_APP_KEY in backend/.env). Currently showing verified dataset postings and Remotive remote tech vacancies. No fake vacancies are substituted.`,
            h("div", { style: { marginTop: "var(--space-2)" } },
              h("button", {
                type: "button",
                class: "btn btn--sm btn--primary",
                onclick: () => openProviderSetupDialog()
              }, "View 2-Min Adzuna Setup Steps")
            )
          )
        );
      } else {
        noticeBanner.style.display = "none";
        noticeBanner.replaceChildren();
      }
    }

    if (countBadge) {
      countBadge.textContent = `${res.total} ${res.total === 1 ? "listing" : "listings"} found`;
    }

    if (!res.items || res.items.length === 0) {
      const suggestions = res.broadening_suggestions || [];
      const emptyCard = h("div", {
        class: "card",
        style: {
          textAlign: "center",
          padding: "var(--space-6) var(--space-4)",
          maxWidth: "680px",
          margin: "0 auto"
        }
      },
        h("div", { style: { marginBottom: "var(--space-2)", color: "var(--text-muted)" } }, icon("search", { size: 36 })),
        h("h3", { style: { fontSize: "var(--font-size-base)", fontWeight: "600", marginBottom: "var(--space-2)" } },
          "No Matching Vacancies Found"
        ),
        h("p", { style: { fontSize: "var(--font-size-sm)", color: "var(--text-secondary)", marginBottom: "var(--space-4)", lineHeight: "1.5" } },
          res.empty_reason || "No vacancies match all your current skills and filters."
        ),
        suggestions.length > 0 ? h("div", {
          style: {
            background: "var(--bg-surface-2)",
            padding: "var(--space-3) var(--space-4)",
            borderRadius: "var(--radius-md)",
            textAlign: "left",
            marginBottom: "var(--space-4)",
            border: "1px solid var(--border-subtle)"
          }
        },
          h("div", { style: { fontSize: "11px", fontWeight: "600", color: "var(--text-primary)", marginBottom: "var(--space-2)", textTransform: "uppercase" } },
            "Suggested Options to Broaden Search (No Silent Relaxation):"
          ),
          h("div", { style: { display: "flex", flexWrap: "wrap", gap: "var(--space-2)" } },
            ...suggestions.map((sug) => {
              return h("button", {
                type: "button",
                class: "btn btn--sm btn--secondary",
                onclick: () => applyBroadeningSuggestion(sug)
              }, sug);
            })
          )
        ) : null,
        h("p", { style: { fontSize: "11px", color: "var(--text-muted)", margin: 0 } },
          "Preferences are strictly respected. We never silently relax your filters without your confirmation."
        )
      );

      container.replaceChildren(emptyCard);
      if (paginationContainer) paginationContainer.replaceChildren();
      updateStepper(5);
      return;
    }

    renderJobCards(container, res.items, true);
    renderPagination(paginationContainer, res.total, skillFilter.limit, skillFilter.offset, (newOffset) => {
      skillFilter.offset = newOffset;
      loadSkillRecommendations();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    updateStepper(5);
  } catch (err) {
    const isRateLimited = err?.status === 429 || (err?.message && /rate.limit|quota/i.test(err.message));
    const displayErr = isRateLimited
      ? "API Provider Quota Limit Reached: External job provider's rate limit reached for today. Displaying verified platform postings."
      : err;
    container.replaceChildren(
      errorState(displayErr, {
        title: isRateLimited ? "Quota limit reached" : undefined,
        onRetry: () => loadSkillRecommendations()
      })
    );
  } finally {
    setBusy(findBtn, false);
    if (resetBtn) resetBtn.disabled = false;
    if (extractBtn) extractBtn.disabled = false;
    if (uploadBtn) uploadBtn.disabled = false;
    setProgressState(false);
  }
}

/* ==============================================================================
 * All Jobs Catalog Controller
 * ============================================================================== */
function setupCatalogControls() {
  const searchInput = $("#job-search-input");
  const categorySelect = $("#job-category-select");
  const typeSelect = $("#job-type-select");
  const sortSelect = $("#job-sort-select");
  const clearBtn = $("#clear-filters-btn");

  searchInput?.addEventListener("input", debounce(() => {
    catalogFilter.q = searchInput.value.trim();
    catalogFilter.offset = 0;
    loadCatalogJobs();
  }, 350));

  categorySelect?.addEventListener("change", () => {
    catalogFilter.category = categorySelect.value;
    catalogFilter.offset = 0;
    loadCatalogJobs();
  });

  typeSelect?.addEventListener("change", () => {
    catalogFilter.job_type = typeSelect.value;
    catalogFilter.offset = 0;
    loadCatalogJobs();
  });

  sortSelect?.addEventListener("change", () => {
    catalogFilter.sort = sortSelect.value;
    catalogFilter.offset = 0;
    loadCatalogJobs();
  });

  clearBtn?.addEventListener("click", () => {
    catalogFilter.q = "";
    catalogFilter.category = "";
    catalogFilter.job_type = "";
    catalogFilter.sort = "newest";
    catalogFilter.offset = 0;

    if (searchInput) searchInput.value = "";
    if (categorySelect) categorySelect.value = "";
    if (typeSelect) typeSelect.value = "";
    if (sortSelect) sortSelect.value = "newest";
    if (clearBtn) clearBtn.style.display = "none";

    loadCatalogJobs();
  });
}

async function loadCatalogJobs() {
  const container = $("#jobs-grid-container");
  const paginationContainer = $("#jobs-pagination-container");
  const countBadge = $("#results-count-badge");
  const clearBtn = $("#clear-filters-btn");
  if (!container) return;

  const hasFilters = Boolean(catalogFilter.q || catalogFilter.category || catalogFilter.job_type || catalogFilter.sort !== "newest");
  if (clearBtn) clearBtn.style.display = hasFilters ? "inline-flex" : "none";

  container.replaceChildren(loadingState("Loading opportunities from database…"));

  try {
    const jobs = await Api.jobs.list({
      q: catalogFilter.q || undefined,
      category: catalogFilter.category || undefined,
      job_type: catalogFilter.job_type || undefined,
      sort: catalogFilter.sort,
      limit: catalogFilter.limit,
      offset: catalogFilter.offset
    });

    if (countBadge) {
      countBadge.textContent = `${jobs.length} postings displayed`;
    }

    if (!jobs || jobs.length === 0) {
      container.replaceChildren(
        emptyState("No job postings matched your search criteria.", () => {
          if (clearBtn) clearBtn.click();
        })
      );
      if (paginationContainer) paginationContainer.replaceChildren();
      return;
    }

    renderJobCards(container, jobs, false);
    if (paginationContainer) paginationContainer.replaceChildren();
  } catch (err) {
    container.replaceChildren(
      errorState(err, {
        title: "Failed to load jobs",
        onRetry: () => loadCatalogJobs()
      })
    );
  }
}

/* ==============================================================================
 * Unified Job Card Rendering
 * ============================================================================== */
function renderJobCards(container, jobs, isRecommendationMode = false) {
  const grid = h("div", { class: "grid grid--cols-3", style: { gap: "var(--space-4)" } });

  jobs.forEach((j) => {
    const isSaved = savedJobIds.has(j.id) || j.is_saved;
    const isExternal = j.source_type === "live_vacancy" || (j.id && (j.id.startsWith("adzuna_") || j.id.startsWith("remotive_")));

    // Source Badge
    const sourceBadge = isExternal
      ? h("span", { class: "badge badge--accent", style: { fontSize: "11px", fontWeight: "600" } },
          icon("globe", { size: 12 }),
          document.createTextNode(` ${j.source_label || "Live Vacancy"}`)
        )
      : h("span", { class: "badge badge--neutral", style: { fontSize: "11px" } },
          icon("database", { size: 12 }),
          document.createTextNode(" Curated Dataset")
        );

    // Cached Badge
    const cachedBadge = j.is_cached
      ? h("span", { class: "badge badge--neutral", style: { fontSize: "10px" }, title: "Served from rate-limit cache" },
          icon("clock", { size: 10 }),
          document.createTextNode(" Cached")
        )
      : null;

    // Freshness Badge (Distinguish "Retrieved recently" from "Confirmed active")
    const freshnessText = j.freshness_label || (isExternal ? "Retrieved recently" : "Confirmed active");
    const isConfirmedActive = freshnessText.toLowerCase().includes("confirmed active");
    const freshnessBadge = h("span", {
      class: `badge ${isConfirmedActive ? "badge--success" : "badge--neutral"}`,
      style: { fontSize: "10px" },
      title: isConfirmedActive ? "Verified listing currently active in database" : "Retrieved from provider feed; listings may expire"
    }, freshnessText);

    const badgeGroup = h("div", { style: { display: "flex", flexWrap: "wrap", alignItems: "center", gap: "4px" } },
      sourceBadge,
      cachedBadge,
      freshnessBadge
    );

    // Score Badge (for recommendations)
    let scoreBadgeEl = null;
    if (isRecommendationMode) {
      if (j.score_type === "model_probability_percent") {
        const isStrong = /strong|high/i.test(j.classification || "") || j.score >= 60;
        scoreBadgeEl = h("div", {
          style: {
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            padding: "2px 8px",
            borderRadius: "var(--radius-full)",
            fontSize: "11px",
            fontWeight: "600",
            background: isStrong ? "rgba(16, 185, 129, 0.15)" : "rgba(59, 130, 246, 0.15)",
            color: isStrong ? "var(--color-success)" : "var(--color-primary)",
            border: `1px solid ${isStrong ? "rgba(16, 185, 129, 0.3)" : "rgba(59, 130, 246, 0.3)"}`
          },
          title: "Evaluated using full PyTorch neural match network"
        },
          icon("sparkles", { size: 11 }),
          document.createTextNode(`AI Résumé Match: ${j.score}%`)
        );
      } else if (j.score_type === "skills_only_relevance") {
        scoreBadgeEl = h("div", {
          style: {
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            padding: "2px 8px",
            borderRadius: "var(--radius-full)",
            fontSize: "11px",
            fontWeight: "600",
            background: "rgba(245, 158, 11, 0.15)",
            color: "var(--color-warning)",
            border: "1px solid rgba(245, 158, 11, 0.3)"
          },
          title: "Calculated based solely on skill chip overlap & semantic relevance"
        },
          icon("sparkles", { size: 11 }),
          document.createTextNode(`Skills Relevance: ${j.score}%`)
        );
      } else if (j.score_type === "unranked_sparse_description") {
        scoreBadgeEl = h("div", {
          class: "badge badge--neutral",
          style: { fontSize: "10px" },
          title: "Posting description too short for deep neural compatibility analysis"
        }, "Unranked (Brief Description)");
      } else if (j.score_type === "unranked_inference_unavailable") {
        scoreBadgeEl = h("div", {
          class: "badge badge--neutral",
          style: { fontSize: "10px" },
          title: "Neural inference unavailable; preserved as genuine unranked vacancy"
        }, "Unranked (Inference Unavailable)");
      } else if (j.score !== undefined) {
        scoreBadgeEl = h("div", {
          class: "badge badge--neutral",
          style: { fontSize: "11px" }
        }, `${j.score_label || "Score"}: ${j.score}%`);
      }
    }

    // Skills Display
    const matchedSkills = j.matched_skills || [];
    const missingSkills = j.missing_skills || [];
    const generalSkills = j.skills || [];

    const card = h("div", {
      class: "card",
      style: {
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        height: "100%",
        padding: "var(--space-4)",
        transition: "all var(--transition-fast)"
      }
    },
      // Header Section
      h("div", {},
        h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "var(--space-2)", marginBottom: "var(--space-2)" } },
          badgeGroup,
          h("div", { style: { display: "flex", alignItems: "center", gap: "var(--space-2)" } },
            scoreBadgeEl,
            // Bookmark Button
            h("button", {
              type: "button",
              class: "icon-btn icon-btn--sm",
              "aria-label": isSaved ? "Remove from saved jobs" : "Save job",
              style: { color: isSaved ? "var(--color-primary)" : "var(--text-muted)" },
              onclick: async (e) => {
                e.stopPropagation();
                await handleSaveJob(j, card);
              }
            }, icon(isSaved ? "bookmark" : "bookmark", { size: 16 }))
          )
        ),

        // Job Title & Company
        h("h3", {
          style: {
            fontSize: "var(--font-size-base)",
            fontWeight: "var(--font-weight-semibold)",
            color: "var(--text-primary)",
            marginBottom: "var(--space-1)"
          }
        }, j.title),

        h("div", {
          style: {
            fontSize: "var(--font-size-xs)",
            color: "var(--text-secondary)",
            marginBottom: "var(--space-2)",
            display: "flex",
            alignItems: "center",
            gap: "var(--space-3)",
            flexWrap: "wrap"
          }
        },
          h("span", { style: { fontWeight: "var(--font-weight-medium)", color: "var(--text-primary)" } }, j.company_name),
          h("span", { style: { display: "flex", alignItems: "center", gap: "2px" } }, icon("mapPin", { size: 12 }), ` ${j.location || "Remote"}`),
          h("span", { class: "badge badge--neutral", style: { fontSize: "10px" } }, (j.job_type || "remote").toUpperCase()),
          j.posted_date ? h("span", { style: { color: "var(--text-muted)" } }, `• ${j.posted_date}`) : null,
          j.retrieved_at ? h("span", { style: { color: "var(--text-muted)" }, title: `Retrieved: ${j.retrieved_at}` }, `• Retrieved ${fmtRetrievalTime(j.retrieved_at) || j.retrieved_at}`) : null
        ),

        // Experience Requirements (if available)
        j.experience_requirements ? h("div", {
          style: {
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            fontSize: "11px",
            color: "var(--color-primary)",
            fontWeight: "500",
            marginBottom: "var(--space-2)"
          }
        }, icon("briefcase", { size: 12 }), document.createTextNode(` ${j.experience_requirements}`)) : null,

        // Relevance Explanation (if recommendation)
        j.relevance_explanation ? h("div", {
          style: {
            padding: "var(--space-2) var(--space-3)",
            borderRadius: "var(--radius-sm)",
            background: "var(--bg-surface-2)",
            borderLeft: "3px solid var(--color-primary)",
            fontSize: "11px",
            color: "var(--text-secondary)",
            marginBottom: "var(--space-2)",
            lineHeight: "1.4"
          }
        }, j.relevance_explanation) : null,

        // Qualification Breakdown (Required vs Preferred)
        isRecommendationMode && j.qualification_breakdown && (j.qualification_breakdown.required?.length || j.qualification_breakdown.preferred?.length) ? h("div", {
          style: {
            fontSize: "11px",
            background: "var(--bg-surface-2)",
            padding: "var(--space-2)",
            borderRadius: "var(--radius-sm)",
            marginBottom: "var(--space-2)"
          }
        },
          j.qualification_breakdown.required?.length ? h("div", { style: { marginBottom: j.qualification_breakdown.preferred?.length ? "4px" : "0" } },
            h("strong", { style: { color: "var(--text-primary)" } }, "Required: "),
            document.createTextNode(j.qualification_breakdown.required.slice(0, 3).join(", ") + (j.qualification_breakdown.required.length > 3 ? ` +${j.qualification_breakdown.required.length - 3} more` : ""))
          ) : null,
          j.qualification_breakdown.preferred?.length ? h("div", {},
            h("strong", { style: { color: "var(--text-muted)" } }, "Preferred: "),
            document.createTextNode(j.qualification_breakdown.preferred.slice(0, 3).join(", ") + (j.qualification_breakdown.preferred.length > 3 ? ` +${j.qualification_breakdown.preferred.length - 3} more` : ""))
          ) : null
        ) : null,

        // Skills Breakdown Chips
        isRecommendationMode ? h("div", { style: { marginBottom: "var(--space-3)" } },
          matchedSkills.length > 0 ? h("div", { style: { display: "flex", flexWrap: "wrap", gap: "4px", marginBottom: "4px" } },
            ...matchedSkills.slice(0, 4).map((s) => chip(s, "matched"))
          ) : null,
          missingSkills.length > 0 ? h("div", { style: { display: "flex", flexWrap: "wrap", gap: "4px" } },
            ...missingSkills.slice(0, 3).map((s) => chip(s, "missing"))
          ) : null
        ) : (generalSkills.length > 0 ? h("div", { class: "chip-list", style: { marginBottom: "var(--space-3)" } },
          ...generalSkills.slice(0, 5).map((s) => chip(s))
        ) : null),

        // Hiring Disclaimer
        isRecommendationMode ? h("p", {
          style: {
            fontSize: "10px",
            color: "var(--text-muted)",
            margin: "var(--space-2) 0 0 0",
            fontStyle: "italic",
            lineHeight: "1.3"
          }
        }, j.disclaimer || "This score estimates résumé–job compatibility according to the model’s training labels. It is not the probability of being hired.") : null
      ),

      // Footer Actions
      const targetAppUrl = j.application_url || j.source_url || j.external_url;

      const saveJobBtn = h("button", {
        type: "button",
        class: "btn btn--secondary btn--sm",
        "data-action": "save-job",
        style: {
          display: "inline-flex",
          alignItems: "center",
          gap: "4px",
          color: isSaved ? "var(--color-primary)" : "inherit",
          borderColor: isSaved ? "var(--color-primary)" : "var(--border-subtle)"
        },
        onclick: async (e) => {
          e.stopPropagation();
          await handleSaveJob(j, card);
        }
      },
        icon("bookmark", { size: 13 }),
        document.createTextNode(isSaved ? " Saved" : " Save Job")
      );

      const analyseMatchBtn = h("button", {
        type: "button",
        class: "btn btn--primary btn--sm",
        style: { display: "inline-flex", alignItems: "center", gap: "4px", flex: 1 },
        onclick: () => startJobAnalysis(j)
      },
        icon("sparkles", { size: 13 }),
        document.createTextNode(" Analyse Match")
      );

      const applySourceBtn = h("button", {
        type: "button",
        class: "btn btn--secondary btn--sm",
        style: { display: "inline-flex", alignItems: "center", gap: "4px" },
        title: targetAppUrl ? `Open authentic posting on ${j.source_label || "provider"}` : "View specifications",
        onclick: () => {
          if (targetAppUrl) {
            window.open(targetAppUrl, "_blank", "noopener,noreferrer");
          } else {
            viewJobDetails(j);
          }
        }
      },
        icon(targetAppUrl ? "external" : "eye", { size: 13 }),
        document.createTextNode(targetAppUrl ? " Apply on Source" : " Details")
      );

      h("div", {
        style: {
          display: "flex",
          gap: "var(--space-2)",
          paddingTop: "var(--space-3)",
          borderTop: "1px solid var(--border-subtle)",
          marginTop: "var(--space-2)",
          alignItems: "center",
          flexWrap: "wrap"
        }
      },
        saveJobBtn,
        analyseMatchBtn,
        applySourceBtn
      )
    );

    grid.appendChild(card);
  });

  container.replaceChildren(grid);
}

/* ==============================================================================
 * Saved Jobs Management
 * ============================================================================== */
async function loadSavedJobs() {
  if (!session.isSignedIn()) return;
  try {
    const list = await Api.jobs.saved();
    savedJobIds = new Set((list || []).map((j) => j.id));
  } catch {
    savedJobIds = new Set();
  }
}

async function handleSaveJob(job, cardEl) {
  if (!session.isSignedIn()) {
    toast("Please sign in to save and bookmark jobs.", { type: "info" });
    return;
  }

  const isExternal = job.source_type === "live_vacancy" || (job.id && (job.id.startsWith("adzuna_") || job.id.startsWith("remotive_")));

  try {
    let res;
    if (isExternal) {
      res = await Api.jobs.saveExternal({
        id: job.id,
        job_code: job.job_code || job.id,
        title: job.title,
        company_name: job.company_name,
        location: job.location,
        job_type: job.job_type,
        experience_level: job.experience_level,
        category: job.category,
        description: job.description,
        requirements: job.requirements,
        min_salary: job.min_salary,
        max_salary: job.max_salary,
        salary_currency: job.salary_currency
      });
      if (res.saved) savedJobIds.add(job.id);
      else savedJobIds.delete(job.id);
    } else {
      res = await Api.jobs.toggleSave(job.id);
      if (res.saved) savedJobIds.add(job.id);
      else savedJobIds.delete(job.id);
    }

    toast(res.message || (res.saved ? "Job saved!" : "Job removed."), { type: "success" });

    // Update bookmark icon in card header
    const btn = cardEl.querySelector(".icon-btn");
    if (btn) {
      btn.style.color = res.saved ? "var(--color-primary)" : "var(--text-muted)";
    }

    // Update footer Save Job button
    const footerSaveBtn = cardEl.querySelector('[data-action="save-job"]');
    if (footerSaveBtn) {
      footerSaveBtn.replaceChildren(
        icon("bookmark", { size: 13 }),
        document.createTextNode(res.saved ? " Saved" : " Save Job")
      );
      footerSaveBtn.style.color = res.saved ? "var(--color-primary)" : "inherit";
      footerSaveBtn.style.borderColor = res.saved ? "var(--color-primary)" : "var(--border-subtle)";
    }
  } catch (err) {
    toast(errorMessage(err, "Could not update saved job."), { type: "error" });
  }
}

/* ==============================================================================
 * Analysis Flow & Job Details Dialog
 * ============================================================================== */
function startJobAnalysis(job) {
  // If external job, cache description in sessionStorage so match.html can populate text
  if (job.source_type === "live_vacancy" || (job.id && (job.id.startsWith("adzuna_") || job.id.startsWith("remotive_")))) {
    sessionStorage.setItem("target_job_analysis", JSON.stringify({
      id: job.id,
      title: job.title,
      company: job.company_name,
      description: job.description,
      requirements: job.requirements
    }));
    window.location.href = `match.html?external=1&title=${encodeURIComponent(job.title)}`;
  } else {
    window.location.href = `match.html?job_id=${encodeURIComponent(job.id)}`;
  }
}

function viewJobDetails(job) {
  if (job.external_url) {
    // Open authentic external application URL in a new tab safely
    window.open(job.external_url, "_blank", "noopener,noreferrer");
    return;
  }

  // Database job details modal
  const content = h("div", {},
    h("div", { style: { marginBottom: "var(--space-3)" } },
      h("h3", { style: { fontSize: "var(--font-size-lg)", color: "var(--text-primary)" } }, job.title),
      h("p", { style: { fontSize: "var(--font-size-sm)", color: "var(--text-secondary)" } }, `${job.company_name} • ${job.location} • ${(job.job_type || "remote").toUpperCase()}`),
      job.min_salary ? h("p", { style: { fontSize: "var(--font-size-xs)", color: "var(--color-primary)", fontWeight: "600", marginTop: "2px" } },
        fmtSalary(job.min_salary, job.max_salary, job.salary_currency)
      ) : null
    ),
    h("div", { style: { marginBottom: "var(--space-4)" } },
      h("h4", { style: { fontSize: "var(--font-size-xs)", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "4px" } }, "Description"),
      h("div", { style: { fontSize: "var(--font-size-sm)", color: "var(--text-primary)", whiteSpace: "pre-line", maxHeight: "250px", overflowY: "auto", padding: "var(--space-2)", background: "var(--bg-surface-2)", borderRadius: "var(--radius-sm)" } },
        job.description
      )
    ),
    job.requirements ? h("div", { style: { marginBottom: "var(--space-4)" } },
      h("h4", { style: { fontSize: "var(--font-size-xs)", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "4px" } }, "Requirements"),
      h("div", { style: { fontSize: "var(--font-size-sm)", color: "var(--text-secondary)", whiteSpace: "pre-line" } }, job.requirements)
    ) : null,
    h("div", { style: { display: "flex", justifyContent: "flex-end", gap: "var(--space-2)", marginTop: "var(--space-4)" } },
      h("button", {
        type: "button",
        class: "btn btn--primary btn--sm",
        onclick: () => startJobAnalysis(job)
      }, icon("sparkles", { size: 14 }), document.createTextNode(" Analyze Match Fit"))
    )
  );

  openDialog({
    title: "Job Opening Specifications",
    content
  });
}

function renderPagination(container, total, limit, offset, onPageChange) {
  if (!container) return;
  if (total <= limit) {
    container.replaceChildren();
    return;
  }

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  const prevBtn = h("button", {
    type: "button",
    class: "btn btn--secondary btn--sm",
    disabled: currentPage === 1,
    onclick: () => onPageChange((currentPage - 2) * limit)
  }, icon("chevronLeft", { size: 14 }), document.createTextNode(" Previous"));

  const pageInfo = h("span", {
    style: { fontSize: "var(--font-size-xs)", color: "var(--text-secondary)", alignSelf: "center" }
  }, `Page ${currentPage} of ${totalPages}`);

  const nextBtn = h("button", {
    type: "button",
    class: "btn btn--secondary btn--sm",
    disabled: currentPage >= totalPages,
    onclick: () => onPageChange(currentPage * limit)
  }, document.createTextNode("Next "), icon("chevronRight", { size: 14 }));

  container.replaceChildren(
    h("div", { style: { display: "flex", justifyContent: "center", alignItems: "center", gap: "var(--space-3)", marginTop: "var(--space-6)" } },
      prevBtn,
      pageInfo,
      nextBtn
    )
  );
}

/* ==============================================================================
 * Live Job Providers Diagnostic & Setup Dialog
 * ============================================================================== */
async function openProviderSetupDialog() {
  let statusInfo = null;
  try {
    statusInfo = await Api.jobs.liveStatus();
  } catch {
    statusInfo = {
      active: true,
      india_live_retrieval_ready: false,
      providers: {
        adzuna: { configured: false, default_country: "in" },
        remotive: { configured: true }
      },
      configuration_guide: {
        setup_steps: [
          "1. Register at https://developer.adzuna.com/signup",
          "2. Copy Application ID & Application Key",
          "3. Add ADZUNA_APP_ID and ADZUNA_APP_KEY to backend/.env",
          "4. Restart backend server."
        ]
      }
    };
  }

  const isConfigured = Boolean(statusInfo?.india_live_retrieval_ready);
  const adzunaData = statusInfo?.providers?.adzuna || {};
  const remotiveData = statusInfo?.providers?.remotive || {};

  const bodyEl = h("div", { style: { display: "flex", flexDirection: "column", gap: "var(--space-4)" } },
    // Adzuna Status Card
    h("div", {
      style: {
        padding: "var(--space-3) var(--space-4)",
        borderRadius: "var(--radius-md)",
        background: isConfigured ? "rgba(16, 185, 129, 0.1)" : "rgba(245, 158, 11, 0.1)",
        border: `1px solid ${isConfigured ? "rgba(16, 185, 129, 0.3)" : "rgba(245, 158, 11, 0.3)"}`
      }
    },
      h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" } },
        h("strong", { style: { color: isConfigured ? "var(--color-success)" : "var(--color-warning)" } },
          isConfigured ? "Adzuna Developer API: Active" : "Adzuna Developer API: Unconfigured"
        ),
        h("span", { class: `badge badge--${isConfigured ? "success" : "warning"}` },
          isConfigured ? "Connected (India Enabled)" : "Credentials Missing"
        )
      ),
      h("p", { style: { fontSize: "var(--font-size-xs)", margin: "0", color: "var(--text-secondary)" } },
        isConfigured
          ? `Live job vacancies for Kolkata, Delhi, Bengaluru, and Indian metro hubs are active (Target Country: ${adzunaData.default_country?.toUpperCase() || "IN"}).`
          : "Free API keys from Adzuna are required to retrieve genuine vacancies across Kolkata, Delhi, Bengaluru and other Indian locations. Training CSV records are strictly excluded from live vacancies."
      )
    ),

    // Remotive Status Card
    h("div", {
      style: {
        padding: "var(--space-3) var(--space-4)",
        borderRadius: "var(--radius-md)",
        background: "var(--bg-surface-2)",
        border: "1px solid var(--border-subtle)"
      }
    },
      h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" } },
        h("strong", {}, "Remotive Open Jobs API: Companion Provider"),
        h("span", { class: "badge badge--success" }, "Active (Public / Keyless)")
      ),
      h("p", { style: { fontSize: "var(--font-size-xs)", margin: "0", color: "var(--text-secondary)" } },
        "Indexes worldwide verified remote technical roles. Available to candidates in India and globally."
      )
    ),

    // Setup Instructions & Documentation Links
    h("div", {},
      h("h4", { style: { fontSize: "var(--font-size-sm)", fontWeight: "600", marginBottom: "var(--space-2)" } },
        "How to Enable Live Indian Vacancies (Adzuna):"
      ),
      h("ol", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-secondary)", paddingLeft: "1.2rem", lineHeight: "1.7" } },
        h("li", {},
          document.createTextNode("Register for a free developer account at "),
          h("a", { href: "https://developer.adzuna.com/signup", target: "_blank", rel: "noopener", style: { color: "var(--color-primary)", textDecoration: "underline" } }, "developer.adzuna.com/signup"),
          document.createTextNode(" (Instant access, free tier with 250+ calls/day).")
        ),
        h("li", {}, "Navigate to your developer dashboard and copy your Application ID and Application Key."),
        h("li", {},
          document.createTextNode("Add the variables to your "),
          h("code", { style: { background: "var(--bg-surface-3)", padding: "2px 4px", borderRadius: "4px" } }, "backend/.env"),
          document.createTextNode(" file:")
        )
      ),
      h("pre", {
        style: {
          background: "var(--bg-surface-3)",
          padding: "var(--space-3)",
          borderRadius: "var(--radius-md)",
          fontSize: "11px",
          color: "var(--color-primary)",
          overflowX: "auto",
          marginTop: "6px"
        }
      }, "ADZUNA_APP_ID=your_adzuna_app_id_here\nADZUNA_APP_KEY=your_adzuna_app_key_here\nADZUNA_COUNTRY=in"),
      h("p", { style: { fontSize: "11px", color: "var(--text-muted)", marginTop: "6px" } },
        "Restart the backend server (python main.py). Real-time vacancies in Kolkata, Delhi, and Indian tech hubs will be fetched on demand."
      )
    ),

    // Documentation Links
    h("div", { style: { display: "flex", gap: "var(--space-3)", flexWrap: "wrap", fontSize: "var(--font-size-xs)", paddingTop: "var(--space-2)", borderTop: "1px solid var(--border-subtle)" } },
      h("a", { href: "https://developer.adzuna.com/docs/search", target: "_blank", rel: "noopener", style: { color: "var(--color-primary)", display: "inline-flex", alignItems: "center", gap: "4px" } },
        icon("globe", { size: 12 }), document.createTextNode("Adzuna API Official Documentation")
      ),
      h("a", { href: "https://remotive.com/api/remote-jobs", target: "_blank", rel: "noopener", style: { color: "var(--color-primary)", display: "inline-flex", alignItems: "center", gap: "4px" } },
        icon("globe", { size: 12 }), document.createTextNode("Remotive API Official Documentation")
      )
    )
  );

  openDialog({
    title: "Live Job Providers & API Configuration",
    size: "md",
    body: bodyEl,
    actions: [
      {
        label: "Close",
        variant: "primary",
        onClick: (e, close) => close()
      }
    ]
  });
}
