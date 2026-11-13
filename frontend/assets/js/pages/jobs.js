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
  resume_id: "",
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
  const locInput = $("#rec-location-input");
  const arrSelect = $("#rec-arrangement-select");
  const expSelect = $("#rec-experience-select");
  const catSelect = $("#rec-category-select");
  const extCheck = $("#include-external-checkbox");

  resumeSelect?.addEventListener("change", () => {
    skillFilter.resume_id = resumeSelect.value;
  });

  extractBtn?.addEventListener("click", async () => {
    const resumeId = resumeSelect?.value || skillFilter.resume_id;
    if (!resumeId) {
      toast("Please select a stored résumé first to extract skills.", { type: "info" });
      return;
    }
    setBusy(extractBtn, true, "Extracting…");
    try {
      const res = await Api.recommendations.extractSkills({ resume_id: resumeId });
      if (res.skills && res.skills.length > 0) {
        res.skills.forEach((s) => addSkill(s));
        toast(`Extracted ${res.count} canonical skills from résumé!`, { type: "success" });
      } else {
        toast("No recognizable technical skills found in this résumé.", { type: "info" });
      }
    } catch (err) {
      toast(errorMessage(err, "Failed to extract skills from résumé."), { type: "error" });
    } finally {
      setBusy(extractBtn, false);
    }
  });

  findBtn?.addEventListener("click", () => {
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
    skillFilter.resume_id = "";
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
 * Load Skill-Based Recommendations
 * ============================================================================== */
async function loadSkillRecommendations() {
  const container = $("#jobs-grid-container");
  const paginationContainer = $("#jobs-pagination-container");
  const countBadge = $("#results-count-badge");
  const apiBadge = $("#external-api-badge");
  if (!container) return;

  container.replaceChildren(loadingState("Matching opportunities against canonical skills & neural embeddings…"));

  try {
    const payload = {
      skills: skillFilter.skills,
      resume_id: skillFilter.resume_id || undefined,
      location: skillFilter.location || undefined,
      job_type: skillFilter.job_type || undefined,
      experience_level: skillFilter.experience_level || undefined,
      category: skillFilter.category || undefined,
      include_external: skillFilter.include_external,
      limit: skillFilter.limit,
      offset: skillFilter.offset
    };

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
      container.replaceChildren(
        emptyState("No matching vacancies found for these skills and filters. Try adding more skills or broadening location.")
      );
      if (paginationContainer) paginationContainer.replaceChildren();
      return;
    }

    renderJobCards(container, res.items, true);
    renderPagination(paginationContainer, res.total, skillFilter.limit, skillFilter.offset, (newOffset) => {
      skillFilter.offset = newOffset;
      loadSkillRecommendations();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  } catch (err) {
    container.replaceChildren(
      errorState("Failed to retrieve skill recommendations. Please check server connectivity.", () => loadSkillRecommendations())
    );
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
      errorState("Failed to load jobs from catalog.", () => loadCatalogJobs())
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

    // Score Badge (for recommendations)
    let scoreBadgeEl = null;
    if (isRecommendationMode && j.score !== undefined) {
      const isStrong = /strong|high/i.test(j.classification || "");
      scoreBadgeEl = h("div", {
        style: {
          display: "inline-flex",
          alignItems: "center",
          gap: "4px",
          padding: "2px 8px",
          borderRadius: "var(--radius-full)",
          fontSize: "11px",
          fontWeight: "600",
          background: isStrong ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
          color: isStrong ? "var(--color-success)" : "var(--color-warning)",
          border: `1px solid ${isStrong ? "rgba(16, 185, 129, 0.3)" : "rgba(245, 158, 11, 0.3)"}`
        }
      },
        icon("sparkles", { size: 11 }),
        document.createTextNode(`${j.score_label || "Match Fit"}: ${j.score}%`)
      );
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
          sourceBadge,
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
            marginBottom: "var(--space-3)",
            display: "flex",
            alignItems: "center",
            gap: "var(--space-3)",
            flexWrap: "wrap"
          }
        },
          h("span", { style: { fontWeight: "var(--font-weight-medium)", color: "var(--text-primary)" } }, j.company_name),
          h("span", { style: { display: "flex", alignItems: "center", gap: "2px" } }, icon("mapPin", { size: 12 }), ` ${j.location || "Remote"}`),
          h("span", { class: "badge badge--neutral", style: { fontSize: "10px" } }, (j.job_type || "remote").toUpperCase()),
          j.posted_date ? h("span", { style: { color: "var(--text-muted)" } }, `• ${j.posted_date}`) : null
        ),

        // Relevance Explanation (if recommendation)
        j.relevance_explanation ? h("div", {
          style: {
            padding: "var(--space-2) var(--space-3)",
            borderRadius: "var(--radius-sm)",
            background: "var(--bg-surface-2)",
            borderLeft: "3px solid var(--color-primary)",
            fontSize: "11px",
            color: "var(--text-secondary)",
            marginBottom: "var(--space-3)",
            lineHeight: "1.4"
          }
        }, j.relevance_explanation) : null,

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
        ) : null)
      ),

      // Footer Actions
      h("div", {
        style: {
          display: "flex",
          gap: "var(--space-2)",
          paddingTop: "var(--space-3)",
          borderTop: "1px solid var(--border-subtle)",
          marginTop: "var(--space-2)"
        }
      },
        // Analyse Match Button -> flows into AI Match Engine
        h("button", {
          type: "button",
          class: "btn btn--primary btn--sm",
          style: { flex: 1 },
          onclick: () => startJobAnalysis(j)
        },
          icon("sparkles", { size: 14 }),
          document.createTextNode(" Analyse Match")
        ),

        // View Original Posting or Details
        h("button", {
          type: "button",
          class: "btn btn--secondary btn--sm",
          onclick: () => viewJobDetails(j)
        },
          j.external_url ? icon("external", { size: 14 }) : icon("eye", { size: 14 }),
          document.createTextNode(j.external_url ? " Vacancy" : " Details")
        )
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

    // Update bookmark icon in card
    const btn = cardEl.querySelector(".icon-btn");
    if (btn) {
      btn.style.color = res.saved ? "var(--color-primary)" : "var(--text-muted)";
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
