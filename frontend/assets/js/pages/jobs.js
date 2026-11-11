/**
 * Job Search & Exploration Controller
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
  fmtDate,
  fmtSalary,
  loadingState,
  emptyState,
  errorState,
  openDialog,
  setBusy,
  toast,
  errorMessage,
  debounce
} from "../ui.js";

let currentFilter = {
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

document.addEventListener("DOMContentLoaded", async () => {
  // Can be viewed when signed in or publicly
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
    breadcrumbs: [{ label: "Workspace" }, { label: "Browse Jobs" }]
  });

  setupFilters();
  await loadSavedJobs();
  loadJobs();
});

function setupFilters() {
  const searchInput = $("#job-search-input");
  const categorySelect = $("#job-category-select");
  const typeSelect = $("#job-type-select");
  const sortSelect = $("#job-sort-select");
  const clearBtn = $("#clear-filters-btn");

  if (searchInput) {
    searchInput.addEventListener("input", debounce(() => {
      currentFilter.q = searchInput.value.trim();
      currentFilter.offset = 0;
      loadJobs();
    }, 350));
  }

  if (categorySelect) {
    categorySelect.addEventListener("change", () => {
      currentFilter.category = categorySelect.value;
      currentFilter.offset = 0;
      loadJobs();
    });
  }

  if (typeSelect) {
    typeSelect.addEventListener("change", () => {
      currentFilter.job_type = typeSelect.value;
      currentFilter.offset = 0;
      loadJobs();
    });
  }

  if (sortSelect) {
    sortSelect.addEventListener("change", () => {
      currentFilter.sort = sortSelect.value;
      currentFilter.offset = 0;
      loadJobs();
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      resetFilters();
    });
  }
}

function resetFilters() {
  currentFilter.q = "";
  currentFilter.category = "";
  currentFilter.job_type = "";
  currentFilter.sort = "newest";
  currentFilter.offset = 0;

  const searchInput = $("#job-search-input");
  const categorySelect = $("#job-category-select");
  const typeSelect = $("#job-type-select");
  const sortSelect = $("#job-sort-select");

  if (searchInput) searchInput.value = "";
  if (categorySelect) categorySelect.value = "";
  if (typeSelect) typeSelect.value = "";
  if (sortSelect) sortSelect.value = "newest";

  updateFilterBarUI([]);
  loadJobs();
}

function updateFilterBarUI(jobs = []) {
  const clearBtn = $("#clear-filters-btn");
  const statusText = $("#filter-status-text");

  const hasFilter = Boolean(currentFilter.q || currentFilter.category || currentFilter.job_type || currentFilter.sort !== "newest");

  if (clearBtn) {
    clearBtn.style.display = hasFilter ? "inline-flex" : "none";
  }

  if (statusText) {
    const pageNum = Math.floor(currentFilter.offset / currentFilter.limit) + 1;
    const parts = [];
    if (currentFilter.q) parts.push(`keyword "${currentFilter.q}"`);
    if (currentFilter.category) parts.push(`category "${currentFilter.category}"`);
    if (currentFilter.job_type) parts.push(`type "${currentFilter.job_type}"`);
    if (currentFilter.sort !== "newest") parts.push(`sort: ${currentFilter.sort}`);

    const filterDesc = parts.length > 0 ? ` [Filtered by ${parts.join(", ")}]` : "";
    const countDesc = jobs.length === 0 
      ? `0 jobs found${filterDesc}`
      : `Showing ${jobs.length} jobs (Page ${pageNum})${filterDesc}`;
    statusText.textContent = countDesc;
  }
}

async function loadSavedJobs() {
  if (!currentUser) return;
  try {
    const saved = await Api.jobs.saved();
    savedJobIds = new Set((saved || []).map((j) => j.id));
  } catch {
    savedJobIds = new Set();
  }
}

async function loadJobs() {
  const container = $("#jobs-grid-container");
  if (!container) return;

  container.replaceChildren(loadingState("Searching available job openings…"));

  try {
    const jobs = await Api.jobs.list(currentFilter);
    updateFilterBarUI(jobs);
    renderJobsGrid(container, jobs);
    renderPagination(jobs.length);
  } catch (err) {
    updateFilterBarUI([]);
    renderPagination(0);
    container.replaceChildren(
      errorState(err, {
        title: "Could not load jobs from server",
        message: (err.kind === "unavailable" || err.status === 0)
          ? "Unable to reach the backend at http://127.0.0.1:8001. Please verify that the API server is active."
          : (err.message || "An unexpected error occurred while fetching jobs."),
        onRetry: () => loadJobs()
      })
    );
  }
}

function renderJobsGrid(container, jobs) {
  container.replaceChildren();

  if (!jobs || jobs.length === 0) {
    const hasFilter = Boolean(currentFilter.q || currentFilter.category || currentFilter.job_type || currentFilter.sort !== "newest");
    container.appendChild(
      emptyState({
        title: hasFilter ? "No jobs match your filter criteria" : "No job openings available",
        message: hasFilter
          ? "No jobs matched the selected keywords or filter parameters. Try clicking 'Clear Filters' to view all postings."
          : "Check back soon for new openings from our inclusive employer partners.",
        iconName: "briefcase",
        action: hasFilter
          ? h("button", {
              class: "btn btn--secondary btn--sm",
              onclick: () => resetFilters()
            }, icon("refresh", { size: 14 }), " Reset Filters")
          : null
      })
    );
    return;
  }

  const grid = h("div", { class: "grid grid--cards" });

  jobs.forEach((j) => {
    const isSaved = savedJobIds.has(j.id);
    const card = h("div", { class: "card", style: { display: "flex", flexDirection: "column", height: "100%" } },
      // Header
      h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "var(--space-2)", marginBottom: "var(--space-2)" } },
        h("div", {},
          h("h3", { style: { fontSize: "var(--font-size-base)", fontWeight: "var(--font-weight-semibold)", marginBottom: "var(--space-1)" }, text: j.title }),
          h("p", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }, text: j.company_name })
        ),
        currentUser && currentUser.role === "candidate"
          ? h("button", {
              class: "icon-btn",
              title: isSaved ? "Remove from bookmarks" : "Save job",
              "aria-label": isSaved ? "Remove from bookmarks" : "Save job",
              onclick: async (e) => {
                e.stopPropagation();
                await toggleSave(j.id, e.currentTarget);
              }
            }, icon("bookmark", { size: 18, className: isSaved ? "icon-saved" : "" }))
          : null
      ),

      // Tags Row
      h("div", { style: { display: "flex", flexWrap: "wrap", gap: "var(--space-1)", marginBottom: "var(--space-3)" } },
        badge(j.job_type || "Remote", "accent"),
        j.category ? badge(j.category, "neutral") : null,
        badge(j.experience_level || "Mid-Level", "neutral")
      ),

      // Description excerpt
      h("p", { style: { fontSize: "var(--font-size-sm)", color: "var(--text-secondary)", flex: 1, marginBottom: "var(--space-4)", display: "-webkit-box", WebkitLineClamp: "3", WebkitBoxOrient: "vertical", overflow: "hidden" }, text: j.description }),

      // Salary & Location
      h("div", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)", marginBottom: "var(--space-3)", display: "flex", flexDirection: "column", gap: "2px" } },
        h("span", {}, icon("mapPin", { size: 12 }), ` ${j.location || "Remote"}`),
        (j.min_salary || j.max_salary)
          ? h("span", { style: { fontWeight: "var(--font-weight-semibold)", color: "var(--color-primary)" } }, fmtSalary(j.min_salary, j.max_salary, j.salary_currency))
          : null
      ),

      // Skills preview
      j.skills && j.skills.length > 0
        ? h("div", { class: "chip-list", style: { marginBottom: "var(--space-4)" } },
            j.skills.slice(0, 4).map(s => chip(s, "neutral"))
          )
        : null,

      // Action Footer
      h("div", { style: { borderTop: "1px solid var(--border-subtle)", paddingTop: "var(--space-3)", display: "flex", gap: "var(--space-2)" } },
        h("button", {
          class: "btn btn--secondary btn--sm",
          style: { flex: 1 },
          onclick: () => viewJobDetails(j.id)
        }, "Details"),
        currentUser && currentUser.role === "candidate"
          ? h("button", {
              class: "btn btn--primary btn--sm",
              style: { flex: 1 },
              onclick: () => openApplyModal(j)
            }, "Apply")
          : currentUser && currentUser.role === "recruiter"
            ? h("a", {
                class: "btn btn--ai btn--sm",
                href: `recruiter.html?job_id=${encodeURIComponent(j.id)}`
              }, "Applicants")
            : null
      )
    );

    grid.appendChild(card);
  });

  container.appendChild(grid);
}

function renderPagination(jobCount) {
  const container = $("#jobs-pagination-container");
  if (!container) return;

  const pageNum = Math.floor(currentFilter.offset / currentFilter.limit) + 1;
  const canGoPrev = currentFilter.offset > 0;
  const canGoNext = jobCount === currentFilter.limit;

  if (!canGoPrev && !canGoNext) {
    container.replaceChildren();
    return;
  }

  const paginationNav = h("div", {
    class: "card",
    style: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      padding: "var(--space-3) var(--space-4)",
      marginTop: "var(--space-6)"
    }
  },
    h("button", {
      class: "btn btn--secondary btn--sm",
      disabled: !canGoPrev,
      onclick: () => {
        if (!canGoPrev) return;
        currentFilter.offset = Math.max(0, currentFilter.offset - currentFilter.limit);
        loadJobs();
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    }, icon("chevronLeft", { size: 14 }), " Previous Page"),

    h("div", { style: { fontSize: "var(--font-size-sm)", color: "var(--text-secondary)", fontWeight: "var(--font-weight-medium)" } },
      `Page ${pageNum}`
    ),

    h("button", {
      class: "btn btn--secondary btn--sm",
      disabled: !canGoNext,
      onclick: () => {
        if (!canGoNext) return;
        currentFilter.offset += currentFilter.limit;
        loadJobs();
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    }, "Next Page ", icon("chevronRight", { size: 14 }))
  );

  container.replaceChildren(paginationNav);
}

async function viewJobDetails(jobId) {
  try {
    const job = await Api.jobs.get(jobId);

    const content = h("div", { style: { display: "flex", flexDirection: "column", gap: "var(--space-4)" } },
      // Meta row
      h("div", { style: { display: "flex", flexWrap: "wrap", gap: "var(--space-2)" } },
        badge(job.job_type, "accent"),
        badge(job.category || "Technology", "neutral"),
        badge(job.experience_level, "neutral"),
        h("span", { class: "badge badge--neutral", text: `${job.applicant_count} applicants` })
      ),

      // Location & Salary
      h("div", { class: "card", style: { padding: "var(--space-3) var(--space-4)" } },
        h("div", { style: { fontSize: "var(--font-size-sm)", color: "var(--text-secondary)" } },
          h("strong", { text: "Location: " }), job.location || "Remote", " • ",
          h("strong", { text: "Compensation: " }), fmtSalary(job.min_salary, job.max_salary, job.salary_currency) || "Competitive"
        )
      ),

      // Description
      h("div", {},
        h("h4", { style: { fontSize: "var(--font-size-sm)", marginBottom: "var(--space-1)" }, text: "Job Description" }),
        h("div", { style: { fontSize: "var(--font-size-sm)", color: "var(--text-secondary)", whiteSpace: "pre-line", lineHeight: "var(--line-height-relaxed)" }, text: job.description })
      ),

      // Requirements if present
      job.requirements
        ? h("div", {},
            h("h4", { style: { fontSize: "var(--font-size-sm)", marginBottom: "var(--space-1)" }, text: "Role Requirements" }),
            h("div", { style: { fontSize: "var(--font-size-sm)", color: "var(--text-secondary)", whiteSpace: "pre-line" }, text: job.requirements })
          )
        : null,

      // Skills
      job.skills && job.skills.length > 0
        ? h("div", {},
            h("h4", { style: { fontSize: "var(--font-size-sm)", marginBottom: "var(--space-2)" }, text: "Required Technical Skills" }),
            h("div", { class: "chip-list" }, job.skills.map(s => chip(s, "accent")))
          )
        : null
    );

    const actions = [{ label: "Close", variant: "secondary" }];
    if (currentUser && currentUser.role === "candidate") {
      actions.push({
        label: "Apply for this Position",
        variant: "primary",
        onClick: (e, close) => {
          close();
          openApplyModal(job);
        }
      });
    }

    openDialog({
      title: job.title,
      description: `${job.company_name} • Posted on ${fmtDate(job.created_at)}`,
      body: content,
      size: "lg",
      actions
    });
  } catch (err) {
    toast(errorMessage(err, "Could not fetch job details."), { type: "error" });
  }
}

async function toggleSave(jobId, btn) {
  try {
    const res = await Api.jobs.toggleSave(jobId);
    if (res.saved) {
      savedJobIds.add(jobId);
      toast("Job saved to bookmarks.", { type: "success" });
      btn.querySelector(".icon").classList.add("icon-saved");
    } else {
      savedJobIds.delete(jobId);
      toast("Job removed from bookmarks.", { type: "info" });
      btn.querySelector(".icon").classList.remove("icon-saved");
    }
  } catch (err) {
    toast(errorMessage(err, "Failed to update bookmark."), { type: "error" });
  }
}

async function openApplyModal(job) {
  let resumes = [];
  try {
    resumes = await Api.resumes.list();
  } catch {
    resumes = [];
  }

  const form = h("form", { id: "apply-form", style: { display: "flex", flexDirection: "column", gap: "var(--space-4)" } },
    resumes.length > 0
      ? h("div", { class: "field" },
          h("label", { class: "field__label", for: "apply-resume-select", text: "Select Resume for Application" }),
          h("select", { class: "select", id: "apply-resume-select", name: "resume_id" },
            resumes.map(r => h("option", { value: r.id, selected: r.is_active }, `${r.file_name} (${r.ats_score}% ATS score)`))
          )
        )
      : h("div", { class: "notice notice--warning" },
          h("p", { text: "You have no uploaded resumes. Please upload a resume first in 'My Resumes' before applying." })
        ),
    h("div", { class: "field" },
      h("label", { class: "field__label", for: "apply-cover-note", text: "Optional Cover Note to Recruiter" }),
      h("textarea", { class: "textarea", id: "apply-cover-note", name: "cover_note", rows: 3, placeholder: "Briefly highlight your key competencies for this position…" })
    )
  );

  openDialog({
    title: `Apply to ${job.title}`,
    description: job.company_name,
    body: form,
    size: "md",
    actions: [
      { label: "Cancel", variant: "secondary" },
      {
        label: "Submit Application",
        variant: "primary",
        onClick: async (e, close) => {
          if (resumes.length === 0) {
            toast("Upload a resume first before applying.", { type: "error" });
            return;
          }
          const submitBtn = e.target;
          setBusy(submitBtn, true, "Submitting…");
          const resume_id = form.resume_id.value;
          const cover_note = form.cover_note.value.trim();

          try {
            await Api.jobs.apply(job.id, { resume_id, cover_note: cover_note || undefined });
            toast("Application submitted successfully! Your AI match score has been recorded.", { type: "success" });
            close();
          } catch (err) {
            setBusy(submitBtn, false);
            toast(errorMessage(err, "Failed to submit application."), { type: "error" });
          }
        }
      }
    ]
  });
}

