/**
 * Candidate Dashboard Controller
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
  fmtDate,
  fmtPct100,
  loadingState,
  emptyState,
  errorState,
  toast
} from "../ui.js";

document.addEventListener("DOMContentLoaded", async () => {
  const user = await requireAuth(["candidate", "admin"]);
  if (!user) return;

  initAppShell({
    user,
    activePage: "dashboard.html",
    breadcrumbs: [{ label: "Workspace" }, { label: "Candidate Dashboard" }]
  });

  loadDashboard();
});

async function loadDashboard() {
  const container = $("#dashboard-content");
  if (!container) return;

  container.replaceChildren(loadingState("Loading dashboard analytics…"));

  try {
    const data = await Api.dashboard.candidate();
    renderDashboard(container, data);
  } catch (err) {
    container.replaceChildren(
      errorState(err, {
        title: "Could not load dashboard",
        onRetry: () => loadDashboard()
      })
    );
  }
}

function renderDashboard(container, data) {
  container.replaceChildren();

  // 1. Metric Tiles Row
  const metricsGrid = h("div", { class: "grid grid--stats", style: { marginBottom: "var(--space-6)" } },
    renderMetricCard("Active Resume", data.active_resume ? `${data.active_resume.file_name}` : "None Uploaded", "file", data.active_resume ? `ATS Score: ${data.active_resume.ats_score}%` : "Upload a resume to begin"),
    renderMetricCard("Applications", `${data.total_applications}`, "list", "Submitted job applications"),
    renderMetricCard("Saved Jobs", `${data.saved_jobs_count}`, "bookmark", "Bookmarked opportunities"),
    renderMetricCard("Profile Progress", `${Math.round(data.profile_completion)}%`, "user", "Resume completeness")
  );
  container.appendChild(metricsGrid);

  // 2. Active Resume Card or First-Use Callout
  if (data.active_resume) {
    const resumeCard = renderActiveResumeCard(data.active_resume);
    container.appendChild(resumeCard);
  } else {
    const emptyNotice = h("div", { class: "notice notice--info", style: { marginBottom: "var(--space-6)" } },
      icon("file", { size: 24 }),
      h("div", { style: { flex: 1 } },
        h("strong", { class: "notice__title", text: "No Active Resume on File" }),
        h("p", { text: "Upload your resume (PDF, DOCX, or TXT) to automatically analyze your ATS score and unlock real AI job matching." })
      ),
      h("a", { class: "btn btn--primary btn--sm", href: "resumes.html" }, icon("upload", { size: 14 }), " Upload Resume")
    );
    container.appendChild(emptyNotice);
  }

  // 3. Two-Column Layout: Applications + Recommended Jobs
  const layout = h("div", { class: "grid grid--cols-2", style: { marginTop: "var(--space-6)" } });

  // Applications Table Card
  const appsCard = h("div", { class: "card" },
    h("div", { class: "card__header" },
      h("h3", { class: "card__title" }, icon("list", { size: 18 }), " Recent Applications"),
      h("a", { class: "btn btn--ghost btn--sm", href: "applications.html" }, "View All")
    ),
    data.applications && data.applications.length > 0
      ? renderApplicationsList(data.applications)
      : emptyState({
          title: "No applications submitted yet",
          message: "Browse available jobs to apply and track your recruitment status here.",
          action: h("a", { class: "btn btn--secondary btn--sm", href: "jobs.html" }, "Browse Jobs"),
          iconName: "briefcase"
        })
  );
  layout.appendChild(appsCard);

  // Recommended Jobs Card
  const recsCard = h("div", { class: "card" },
    h("div", { class: "card__header" },
      h("h3", { class: "card__title" }, icon("sparkles", { size: 18 }), " AI Job Recommendations"),
      h("a", { class: "btn btn--ghost btn--sm", href: "jobs.html" }, "All Jobs")
    ),
    h("div", { id: "recommended-jobs-list" }, loadingState("Fetching neural recommendations…"))
  );
  layout.appendChild(recsCard);

  container.appendChild(layout);

  // Load dynamic recommendations asynchronously
  loadJobRecommendations(recsCard.querySelector("#recommended-jobs-list"));
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

function renderActiveResumeCard(res) {
  return h("div", { class: "card", style: { marginBottom: "var(--space-6)" } },
    h("div", { class: "card__header" },
      h("h3", { class: "card__title" }, icon("file", { size: 18 }), ` Active Resume: ${res.file_name}`),
      h("div", { style: { display: "flex", gap: "var(--space-2)" } },
        h("span", { class: "badge badge--success", text: `ATS Score: ${res.ats_score}%` }),
        h("a", { class: "btn btn--secondary btn--sm", href: "resumes.html" }, "Manage Resumes")
      )
    ),
    h("div", { style: { display: "flex", flexDirection: "column", gap: "var(--space-3)" } },
      h("p", { class: "field__hint", text: `Uploaded on ${fmtDate(res.created_at)} • File size: ${(res.file_size_bytes / 1024).toFixed(1)} KB` }),
      res.skills && res.skills.length > 0
        ? h("div", {},
            h("span", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)", display: "block", marginBottom: "var(--space-2)" }, text: "Extracted Skills:" }),
            h("div", { class: "chip-list" }, res.skills.slice(0, 10).map(s => chip(s, "accent")))
          )
        : null
    )
  );
}

function renderApplicationsList(apps) {
  const table = h("div", { class: "table-wrapper" },
    h("table", { class: "table" },
      h("thead", {},
        h("tr", {},
          h("th", { text: "Role & Company" }),
          h("th", { text: "Stage" }),
          h("th", { text: "Match Score" })
        )
      ),
      h("tbody", {},
        apps.map(a =>
          h("tr", {},
            h("td", {},
              h("strong", { style: { display: "block" }, text: a.job_title }),
              h("span", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }, text: a.company_name })
            ),
            h("td", {}, badge(a.stage || a.status)),
            h("td", {},
              a.match_score !== null && a.match_score !== undefined
                ? h("span", { class: "badge badge--accent", text: `${Number(a.match_score).toFixed(1)}%` })
                : h("span", { class: "badge badge--neutral", text: "Not evaluated" })
            )
          )
        )
      )
    )
  );
  return table;
}

async function loadJobRecommendations(container) {
  try {
    const res = await Api.recommendations.jobs({ limit: 4 });
    const recs = res.recommendations || [];

    if (recs.length === 0) {
      container.replaceChildren(
        emptyState({
          title: "No recommendations available",
          message: "Ensure your active resume has valid technical skills to generate AI job matches.",
          iconName: "sparkles"
        })
      );
      return;
    }

    const list = h("div", { style: { display: "flex", flexDirection: "column", gap: "var(--space-3)" } },
      recs.map(j => {
        const jobId = j.id || j.job_id;
        const rawScore = j.score !== null && j.score !== undefined ? j.score : j.compatibility_score;
        const hasScore = typeof rawScore === "number" && !isNaN(rawScore);
        const scoreBadge = hasScore
          ? h("span", { class: "badge badge--ai", text: `${Number(rawScore).toFixed(1)}% Fit` })
          : h("span", { class: "badge badge--neutral", text: j.score_label || "Listing Available" });
        const jobUrl = jobId ? `jobs.html?job_id=${encodeURIComponent(jobId)}` : (j.application_url || j.source_url || "jobs.html");

        return h("div", { class: "card", style: { padding: "var(--space-4)" } },
          h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "var(--space-2)" } },
            h("div", {},
              h("h4", { style: { fontSize: "var(--font-size-sm)", fontWeight: "var(--font-weight-semibold)" }, text: j.title || "Job Listing" }),
              h("span", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }, text: `${j.company_name || "Organization"} • ${j.location || "Remote"}` })
            ),
            scoreBadge
          ),
          h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "var(--space-3)" } },
            h("span", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-secondary)" }, text: j.relevance_explanation || j.recommendation_reason || "Neural Match" }),
            h("a", { class: "btn btn--primary btn--sm", href: jobUrl }, "View Job")
          )
        );
      })
    );
    container.replaceChildren(list);
  } catch (err) {
    const status = err?.status;
    const msg = (err?.message || "").toLowerCase();

    if (status === 401 || msg.includes("unauthorized") || msg.includes("log in")) {
      container.replaceChildren(
        h("div", { class: "notice notice--warning" },
          h("p", { text: "Please sign in to view your tailored job recommendations." }),
          h("a", { class: "btn btn--secondary btn--sm", href: "login.html", style: { marginTop: "var(--space-2)" } }, "Sign In")
        )
      );
    } else if (msg.includes("resume") || msg.includes("upload") || status === 404) {
      container.replaceChildren(
        h("div", { class: "notice notice--info" },
          h("p", { text: "Upload your résumé in the 'My Resumes' section to generate neural job recommendations." }),
          h("a", { class: "btn btn--secondary btn--sm", href: "resumes.html", style: { marginTop: "var(--space-2)" } }, "Go to Resumes")
        )
      );
    } else {
      const retryBtn = h("button", { class: "btn btn--ghost btn--sm", style: { marginTop: "var(--space-2)" }, text: "Retry" });
      retryBtn.addEventListener("click", () => {
        container.replaceChildren(loadingState("Retrying recommendations…"));
        loadJobRecommendations(container);
      });
      container.replaceChildren(
        h("div", { class: "notice notice--error" },
          h("p", { text: `Unable to load job recommendations: ${err.message || "Network or service error"}` }),
          retryBtn
        )
      );
    }
  }
}

