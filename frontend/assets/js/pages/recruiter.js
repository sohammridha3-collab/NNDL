/**
 * Recruiter Hub & Pipeline Controller
 */
import { Api } from "../api.js";
import { requireAuth } from "../auth.js";
import { initAppShell } from "../app.js";
import {
  $,
  $$,
  h,
  icon,
  badge,
  chip,
  fmtDate,
  loadingState,
  emptyState,
  errorState,
  openDialog,
  confirmDialog,
  setBusy,
  toast,
  errorMessage,
  downloadCsv,
  barList
} from "../ui.js";

let recruiterJobs = [];
let selectedJobId = null;

document.addEventListener("DOMContentLoaded", async () => {
  const user = await requireAuth(["recruiter", "admin"]);
  if (!user) return;

  initAppShell({
    user,
    activePage: "recruiter.html",
    breadcrumbs: [{ label: "Workspace" }, { label: "Recruiter Hub" }]
  });

  const urlParams = new URLSearchParams(window.location.search);
  selectedJobId = urlParams.get("job_id");

  setupPostJobButton();
  loadRecruiterDashboard();
});

function setupPostJobButton() {
  const postBtn = $("#post-job-btn");
  if (!postBtn) return;

  postBtn.addEventListener("click", () => {
    openPostJobModal();
  });
}

async function loadRecruiterDashboard() {
  const container = $("#recruiter-content");
  if (!container) return;

  container.replaceChildren(loadingState("Loading recruiter dashboard & hiring pipeline…"));

  try {
    const data = await Api.dashboard.recruiter();
    recruiterJobs = await Api.jobs.mine();
    renderRecruiterDashboard(container, data);
  } catch (err) {
    container.replaceChildren(
      errorState(err, {
        title: "Could not load recruiter workspace",
        onRetry: () => loadRecruiterDashboard()
      })
    );
  }
}

function renderRecruiterDashboard(container, data) {
  container.replaceChildren();

  // 1. Metric Tiles Row
  const metrics = h("div", { class: "grid grid--stats", style: { marginBottom: "var(--space-6)" } },
    renderMetricCard("Active Postings", `${data.total_active_jobs}`, "briefcase", "Live job listings"),
    renderMetricCard("Total Applicants", `${data.total_applicants}`, "users", "Across all openings"),
    renderMetricCard("Under Review", `${data.pipeline_stages_count.under_review || 0}`, "eye", "Pending recruiter evaluation"),
    renderMetricCard("Shortlisted", `${data.pipeline_stages_count.shortlisted || 0}`, "check", "Candidates in consideration")
  );
  container.appendChild(metrics);

  // 2. Hiring Pipeline Breakdown Card
  const pipelineCard = h("div", { class: "card", style: { marginBottom: "var(--space-6)" } },
    h("h3", { class: "card__title", style: { marginBottom: "var(--space-4)" } }, icon("gauge", { size: 18 }), " Applicant Pipeline Stages"),
    barList([
      { label: "Applied", value: data.pipeline_stages_count.applied || 0, tone: "neutral" },
      { label: "Under Review", value: data.pipeline_stages_count.under_review || 0, tone: "accent" },
      { label: "Shortlisted", value: data.pipeline_stages_count.shortlisted || 0, tone: "success" },
      { label: "Interviewed", value: data.pipeline_stages_count.interviewed || 0, tone: "ai" },
      { label: "Offered", value: data.pipeline_stages_count.offered || 0, tone: "success" },
      { label: "Rejected", value: data.pipeline_stages_count.rejected || 0, tone: "warning" }
    ], { label: "Hiring Pipeline" })
  );
  container.appendChild(pipelineCard);

  // 3. Job Selector & Applicants Management
  const jobsSection = h("div", { class: "card" },
    h("div", { class: "card__header" },
      h("h3", { class: "card__title" }, icon("briefcase", { size: 18 }), " Job Postings & Candidate Pipeline"),
      h("button", { class: "btn btn--primary btn--sm", onclick: () => openPostJobModal() }, icon("plus", { size: 14 }), " Post Opening")
    ),

    recruiterJobs.length > 0
      ? h("div", {},
          h("div", { class: "field", style: { maxWidth: "360px", marginBottom: "var(--space-4)" } },
            h("label", { class: "field__label", for: "recruiter-job-select", text: "Select Job to Review Applicants" }),
            h("select", {
              class: "select",
              id: "recruiter-job-select",
              onchange: (e) => {
                selectedJobId = e.target.value;
                loadJobApplicants(selectedJobId);
              }
            },
              recruiterJobs.map(j => h("option", { value: j.id, selected: j.id === selectedJobId }, `${j.title} (${j.applicant_count} applicants)`))
            )
          ),
          h("div", { id: "applicants-table-container" })
        )
      : emptyState({
          title: "No jobs posted yet",
          message: "Create your first job opening to start receiving candidates and AI compatibility scores.",
          action: h("button", { class: "btn btn--primary btn--sm", onclick: () => openPostJobModal() }, "Create Job Opening"),
          iconName: "briefcase"
        })
  );
  container.appendChild(jobsSection);

  // Auto-load applicants for the first job if none selected
  if (recruiterJobs.length > 0) {
    if (!selectedJobId) selectedJobId = recruiterJobs[0].id;
    loadJobApplicants(selectedJobId);
  }
}

function renderMetricCard(title, value, iconName, subtext) {
  return h("div", { class: "metric-card" },
    h("div", { class: "metric-card__header" },
      h("span", { text: title }),
      icon(iconName, { size: 16 })
    ),
    h("div", { class: "metric-card__value", text: value }),
    h("div", { class: "metric-card__subtext", text: subtext })
  );
}

async function loadJobApplicants(jobId) {
  const container = $("#applicants-table-container");
  if (!container) return;

  container.replaceChildren(loadingState("Loading and ranking applicants…"));

  try {
    const applicants = await Api.jobs.applicants(jobId);
    renderApplicantsTable(container, jobId, applicants);
  } catch (err) {
    container.replaceChildren(
      errorState(err, {
        title: "Could not load applicants",
        onRetry: () => loadJobApplicants(jobId)
      })
    );
  }
}

function renderApplicantsTable(container, jobId, applicants) {
  container.replaceChildren();

  // Export CSV button & count header
  const topActions = h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-3)" } },
    h("span", { class: "field__hint", text: `${applicants.length} applicants ranked by AI match score (Human-in-the-loop review)` }),
    applicants.length > 0
      ? h("button", {
          class: "btn btn--secondary btn--sm",
          onclick: () => {
            const rows = [
              ["Candidate Name", "Email", "Status", "Stage", "AI Match Score", "Date Applied", "Notes"],
              ...applicants.map(a => [
                a.candidate_name,
                a.candidate_email,
                a.status,
                a.stage,
                a.match_score ? `${a.match_score}%` : "N/A",
                a.created_at,
                a.recruiter_note || ""
              ])
            ];
            downloadCsv(`applicants_${jobId}.csv`, rows);
          }
        }, icon("download", { size: 14 }), " Export CSV")
      : null
  );
  container.appendChild(topActions);

  if (!applicants || applicants.length === 0) {
    container.appendChild(
      emptyState({
        title: "No candidates have applied to this position yet",
        message: "When candidates apply, their anonymized profiles and neural match scores will be displayed here.",
        iconName: "users"
      })
    );
    return;
  }

  const tableWrapper = h("div", { class: "table-wrapper" },
    h("table", { class: "table" },
      h("thead", {},
        h("tr", {},
          h("th", { text: "Candidate" }),
          h("th", { text: "AI Match Score" }),
          h("th", { text: "Current Stage" }),
          h("th", { text: "Status" }),
          h("th", { text: "Applied" }),
          h("th", { text: "Actions" })
        )
      ),
      h("tbody", {},
        applicants.map(a =>
          h("tr", {},
            h("td", {},
              h("strong", { style: { display: "block" }, text: a.candidate_name }),
              h("span", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }, text: a.candidate_email })
            ),
            h("td", {},
              a.match_score !== null && a.match_score !== undefined
                ? h("span", { class: "badge badge--accent", style: { fontWeight: "var(--font-weight-bold)" }, text: `${Number(a.match_score).toFixed(1)}%` })
                : h("span", { style: { color: "var(--text-muted)" }, text: "—" })
            ),
            h("td", {},
              h("select", {
                class: "select",
                style: { padding: "0.25rem 0.5rem", fontSize: "var(--font-size-xs)", width: "auto" },
                onchange: async (e) => {
                  const newStage = e.target.value;
                  try {
                    await Api.jobs.updateApplicant(jobId, a.id, { stage: newStage });
                    toast(`Stage updated to '${newStage}'.`, { type: "success" });
                  } catch (err) {
                    toast(errorMessage(err, "Failed to update stage."), { type: "error" });
                  }
                }
              },
                ["Applied", "Under Review", "Shortlisted", "Interviewed", "Offered", "Rejected"].map(s =>
                  h("option", { value: s, selected: a.stage === s }, s)
                )
              )
            ),
            h("td", {}, badge(a.status)),
            h("td", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }, text: fmtDate(a.created_at) }),
            h("td", {},
              h("button", {
                class: "btn btn--secondary btn--sm",
                onclick: () => openApplicantDetailModal(jobId, a)
              }, "Review")
            )
          )
        )
      )
    )
  );

  container.appendChild(tableWrapper);
}

function openApplicantDetailModal(jobId, app) {
  const form = h("form", { style: { display: "flex", flexDirection: "column", gap: "var(--space-4)" } },
    h("div", { class: "grid grid--cols-2", style: { gap: "var(--space-4)" } },
      h("div", {},
        h("span", { class: "field__hint", text: "Candidate" }),
        h("strong", { style: { display: "block" }, text: app.candidate_name }),
        h("span", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }, text: app.candidate_email })
      ),
      h("div", {},
        h("span", { class: "field__hint", text: "AI Compatibility Score" }),
        h("strong", { style: { fontSize: "var(--font-size-xl)", color: "var(--color-primary)", display: "block" }, text: app.match_score ? `${app.match_score}%` : "Not Scored" })
      )
    ),

    app.cover_note
      ? h("div", {},
          h("h4", { style: { fontSize: "var(--font-size-sm)", marginBottom: "var(--space-1)" }, text: "Candidate Cover Note" }),
          h("p", { style: { fontSize: "var(--font-size-sm)", color: "var(--text-secondary)", background: "var(--bg-subtle)", padding: "var(--space-3)", borderRadius: "var(--radius-lg)" }, text: app.cover_note })
        )
      : null,

    h("div", { class: "field" },
      h("label", { class: "field__label", for: "recruiter-modal-note", text: "Private Recruiter Notes" }),
      h("textarea", { class: "textarea", id: "recruiter-modal-note", rows: 3, placeholder: "Add private assessment notes for internal recruitment team…" }, app.recruiter_note || "")
    ),

    h("div", { class: "field" },
      h("label", { class: "field__label", for: "recruiter-modal-status", text: "Application Status" }),
      h("select", { class: "select", id: "recruiter-modal-status" },
        ["applied", "under_review", "shortlisted", "interviewed", "offered", "rejected"].map(st =>
          h("option", { value: st, selected: app.status === st }, st)
        )
      )
    )
  );

  openDialog({
    title: `Candidate Review: ${app.candidate_name}`,
    description: `Position: ${app.job_title}`,
    body: form,
    size: "md",
    actions: [
      { label: "Close", variant: "secondary" },
      {
        label: "Save Updates",
        variant: "primary",
        onClick: async (e, close) => {
          const note = form.querySelector("#recruiter-modal-note").value.trim();
          const status = form.querySelector("#recruiter-modal-status").value;
          try {
            await Api.jobs.updateApplicant(jobId, app.id, { recruiter_note: note, status });
            toast("Applicant records updated.", { type: "success" });
            close();
            loadJobApplicants(jobId);
          } catch (err) {
            toast(errorMessage(err, "Failed to save applicant note."), { type: "error" });
          }
        }
      }
    ]
  });
}

function openPostJobModal() {
  const form = h("form", { id: "create-job-form", style: { display: "flex", flexDirection: "column", gap: "var(--space-3)" } },
    h("div", { class: "field" },
      h("label", { class: "field__label", for: "job-title-input", text: "Job Title *" }),
      h("input", { class: "input", id: "job-title-input", name: "title", required: true, minlength: 3, placeholder: "e.g. Senior Machine Learning Engineer" })
    ),
    h("div", { class: "grid grid--cols-2", style: { gap: "var(--space-3)" } },
      h("div", { class: "field" },
        h("label", { class: "field__label", for: "job-category-input", text: "Category" }),
        h("input", { class: "input", id: "job-category-input", name: "category", value: "Software & Technology" })
      ),
      h("div", { class: "field" },
        h("label", { class: "field__label", for: "job-type-input", text: "Work Arrangement" }),
        h("select", { class: "select", id: "job-type-input", name: "job_type" },
          h("option", { value: "remote" }, "Remote"),
          h("option", { value: "hybrid" }, "Hybrid"),
          h("option", { value: "on-site" }, "On-Site")
        )
      )
    ),
    h("div", { class: "grid grid--cols-2", style: { gap: "var(--space-3)" } },
      h("div", { class: "field" },
        h("label", { class: "field__label", for: "job-loc-input", text: "Location" }),
        h("input", { class: "input", id: "job-loc-input", name: "location", value: "Remote / Worldwide" })
      ),
      h("div", { class: "field" },
        h("label", { class: "field__label", for: "job-exp-input", text: "Experience Level" }),
        h("select", { class: "select", id: "job-exp-input", name: "experience_level" },
          h("option", { value: "Entry-Level" }, "Entry-Level"),
          h("option", { value: "Mid-Level", selected: true }, "Mid-Level"),
          h("option", { value: "Senior" }, "Senior"),
          h("option", { value: "Lead / Principal" }, "Lead / Principal")
        )
      )
    ),
    h("div", { class: "field" },
      h("label", { class: "field__label", for: "job-skills-input", text: "Required Skills (comma separated)" }),
      h("input", { class: "input", id: "job-skills-input", name: "skills", placeholder: "Python, Docker, PyTorch, SQL, REST API" })
    ),
    h("div", { class: "field" },
      h("label", { class: "field__label", for: "job-desc-input", text: "Job Description (min 20 characters) *" }),
      h("textarea", { class: "textarea", id: "job-desc-input", name: "description", required: true, rows: 4, placeholder: "Detail the responsibilities, project scope, and daily requirements…" })
    ),
    h("div", { class: "field" },
      h("label", { class: "field__label", for: "job-req-input", text: "Requirements & Qualifications" }),
      h("textarea", { class: "textarea", id: "job-req-input", name: "requirements", rows: 3, placeholder: "Specific degrees, certifications, or years of domain experience…" })
    )
  );

  openDialog({
    title: "Post New Job Opening",
    description: "Publish an opportunity to the verified talent pool",
    body: form,
    size: "lg",
    actions: [
      { label: "Cancel", variant: "secondary" },
      {
        label: "Create Job",
        variant: "primary",
        onClick: async (e, close) => {
          const submitBtn = e.target;
          const title = form.title.value.trim();
          const category = form.category.value.trim();
          const job_type = form.job_type.value;
          const location = form.location.value.trim();
          const experience_level = form.experience_level.value;
          const skillsStr = form.skills.value.trim();
          const description = form.description.value.trim();
          const requirements = form.requirements.value.trim();

          if (!title || description.length < 20) {
            toast("Please provide a title and at least 20 characters of description.", { type: "error" });
            return;
          }

          const skills = skillsStr ? skillsStr.split(",").map(s => s.trim()).filter(Boolean) : [];

          setBusy(submitBtn, true, "Publishing…");
          try {
            await Api.jobs.create({
              title,
              category,
              job_type,
              location,
              experience_level,
              skills,
              description,
              requirements: requirements || undefined
            });
            toast("Job opening created and published successfully!", { type: "success" });
            close();
            loadRecruiterDashboard();
          } catch (err) {
            setBusy(submitBtn, false);
            toast(errorMessage(err, "Failed to create job posting."), { type: "error" });
          }
        }
      }
    ]
  });
}

