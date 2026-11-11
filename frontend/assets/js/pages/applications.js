/**
 * Applications & AI Match History Controller
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
  classificationBadge,
  fmtDate,
  loadingState,
  emptyState,
  errorState,
  openDialog,
  toast,
  errorMessage
} from "../ui.js";

document.addEventListener("DOMContentLoaded", async () => {
  const user = await requireAuth(["candidate", "admin"]);
  if (!user) return;

  initAppShell({
    user,
    activePage: "applications.html",
    breadcrumbs: [{ label: "Workspace" }, { label: "My Applications & History" }]
  });

  setupTabs();
  loadApplications();
});

function setupTabs() {
  const tabs = $$(".tab-button");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => {
        t.classList.remove("btn--primary");
        t.classList.add("btn--secondary");
        t.setAttribute("aria-selected", "false");
      });
      tab.classList.remove("btn--secondary");
      tab.classList.add("btn--primary");
      tab.setAttribute("aria-selected", "true");

      const target = tab.dataset.target;
      if (target === "applications") loadApplications();
      else if (target === "history") loadHistory();
    });
  });
}

async function loadApplications() {
  const container = $("#tab-content-container");
  if (!container) return;

  container.replaceChildren(loadingState("Loading your job applications…"));

  try {
    const apps = await Api.jobs.myApplications();
    renderApplications(container, apps);
  } catch (err) {
    container.replaceChildren(
      errorState(err, {
        title: "Could not load applications",
        onRetry: () => loadApplications()
      })
    );
  }
}

function renderApplications(container, apps) {
  container.replaceChildren();

  if (!apps || apps.length === 0) {
    container.appendChild(
      emptyState({
        title: "No job applications found",
        message: "When you apply to jobs, your submissions, status updates, and notes will appear here.",
        action: h("a", { class: "btn btn--primary btn--sm", href: "jobs.html" }, "Explore Jobs"),
        iconName: "list"
      })
    );
    return;
  }

  const tableWrapper = h("div", { class: "table-wrapper" },
    h("table", { class: "table" },
      h("thead", {},
        h("tr", {},
          h("th", { text: "Job Title & Company" }),
          h("th", { text: "Status & Stage" }),
          h("th", { text: "AI Match Fit" }),
          h("th", { text: "Applied Date" }),
          h("th", { text: "Recruiter Note" })
        )
      ),
      h("tbody", {},
        apps.map(a =>
          h("tr", {},
            h("td", {},
              h("strong", { style: { display: "block" }, text: a.job_title }),
              h("span", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }, text: a.company_name || "Verified Partner" })
            ),
            h("td", {},
              badge(a.status),
              h("span", { style: { display: "block", fontSize: "var(--font-size-xs)", color: "var(--text-muted)", marginTop: "2px" }, text: `Stage: ${a.stage}` })
            ),
            h("td", {},
              a.match_score !== null && a.match_score !== undefined
                ? h("span", { class: "badge badge--accent", text: `${Number(a.match_score).toFixed(1)}%` })
                : h("span", { class: "badge badge--neutral", text: "Not evaluated" })
            ),
            h("td", { style: { fontSize: "var(--font-size-xs)" }, text: fmtDate(a.created_at) }),
            h("td", { style: { fontSize: "var(--font-size-xs)", color: a.recruiter_note ? "var(--text-primary)" : "var(--text-muted)" }, text: a.recruiter_note || "None" })
          )
        )
      )
    )
  );

  container.appendChild(tableWrapper);
}

async function loadHistory() {
  const container = $("#tab-content-container");
  if (!container) return;

  container.replaceChildren(loadingState("Loading AI matching history…"));

  try {
    const history = await Api.matching.history();
    renderHistory(container, history);
  } catch (err) {
    container.replaceChildren(
      errorState(err, {
        title: "Could not load match history",
        onRetry: () => loadHistory()
      })
    );
  }
}

function renderHistory(container, history) {
  container.replaceChildren();

  if (!history || history.length === 0) {
    container.appendChild(
      emptyState({
        title: "No AI match predictions logged",
        message: "Predictions run on the AI Matching page or via job applications will be saved here for auditing.",
        action: h("a", { class: "btn btn--primary btn--sm", href: "match.html" }, "Run Match"),
        iconName: "sparkles"
      })
    );
    return;
  }

  const tableWrapper = h("div", { class: "table-wrapper" },
    h("table", { class: "table" },
      h("thead", {},
        h("tr", {},
          h("th", { text: "Job Target" }),
          h("th", { text: "Classification" }),
          h("th", { text: "Score" }),
          h("th", { text: "Similarity" }),
          h("th", { text: "Skill Coverage" }),
          h("th", { text: "Model Version" }),
          h("th", { text: "Date" })
        )
      ),
      h("tbody", {},
        history.map(hItem =>
          h("tr", {},
            h("td", {},
              h("strong", { text: hItem.job_title || "Direct Input Job" })
            ),
            h("td", {}, classificationBadge(hItem.classification)),
            h("td", {},
              h("strong", { style: { color: "var(--color-primary)" }, text: `${Number(hItem.compatibility_score).toFixed(1)}%` })
            ),
            h("td", { style: { fontSize: "var(--font-size-xs)" }, text: Number(hItem.semantic_similarity).toFixed(4) }),
            h("td", { style: { fontSize: "var(--font-size-xs)" }, text: `${(Number(hItem.required_skill_coverage) * 100).toFixed(1)}%` }),
            h("td", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }, text: hItem.model_version }),
            h("td", { style: { fontSize: "var(--font-size-xs)" }, text: fmtDate(hItem.created_at) })
          )
        )
      )
    )
  );

  container.appendChild(tableWrapper);
}

