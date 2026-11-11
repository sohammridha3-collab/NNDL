/**
 * Administrator & System Governance Controller
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
  fmtDate,
  loadingState,
  emptyState,
  errorState,
  confirmDialog,
  toast,
  errorMessage
} from "../ui.js";

document.addEventListener("DOMContentLoaded", async () => {
  const user = await requireAuth(["admin"]);
  if (!user) return;

  initAppShell({
    user,
    activePage: "admin.html",
    breadcrumbs: [{ label: "Workspace" }, { label: "System Administration" }]
  });

  loadAdminOverview();
  loadSystemHealth();
  loadUsers();
  loadAuditLogs();
});

async function loadAdminOverview() {
  const container = $("#admin-metrics-container");
  if (!container) return;

  try {
    const data = await Api.dashboard.admin();
    container.replaceChildren(
      renderMetricCard("Total Users", `${data.total_users}`, "users", `${data.total_candidates} candidates • ${data.total_recruiters} recruiters`),
      renderMetricCard("Job Openings", `${data.total_jobs}`, "briefcase", "Active and closed posts"),
      renderMetricCard("Applications", `${data.total_applications}`, "list", "Submitted candidate pipelines"),
      renderMetricCard("AI Matches Run", `${data.total_matches_run}`, "sparkles", "Neural predictions logged")
    );
  } catch (err) {
    container.replaceChildren(
      h("div", { class: "notice notice--error" }, h("p", { text: "Could not load admin platform metrics." }))
    );
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

async function loadSystemHealth() {
  const container = $("#system-health-container");
  if (!container) return;

  container.replaceChildren(loadingState("Auditing system health & ML model readiness…"));

  try {
    const health = await Api.admin.systemHealth();
    const ml = health.ml_service || {};

    const content = h("div", { class: "card" },
      h("div", { class: "card__header" },
        h("h3", { class: "card__title" }, icon("server", { size: 18 }), " Real-time Environment & Model Diagnostics"),
        h("span", { class: "badge badge--success", text: "Healthy & Online" })
      ),
      h("div", { class: "grid grid--cols-2", style: { gap: "var(--space-4)" } },
        h("div", { style: { display: "flex", flexDirection: "column", gap: "var(--space-2)", fontSize: "var(--font-size-sm)" } },
          h("div", {}, h("strong", { text: "Classifier Architecture: " }), ml.model_type || "PyTorch MLP (770 features)"),
          h("div", {}, h("strong", { text: "Decision Threshold: " }), `${ml.threshold || 0.9032} (Calibrated P/R)`),
          h("div", {}, h("strong", { text: "Text Encoder: " }), ml.encoder || "all-MiniLM-L6-v2"),
          h("div", {}, h("strong", { text: "Inference Hardware: " }), `${ml.device || "cpu"} mode`)
        ),
        h("div", { style: { display: "flex", flexDirection: "column", gap: "var(--space-2)", fontSize: "var(--font-size-sm)" } },
          h("div", {}, h("strong", { text: "Database Connectivity: " }), health.database_connected ? "Connected (SQLAlchemy)" : "Disconnected"),
          h("div", {}, h("strong", { text: "Server OS / Platform: " }), health.platform),
          h("div", {}, h("strong", { text: "Python Runtime: " }), health.python_version ? health.python_version.split(" ")[0] : "3.11+")
        )
      )
    );
    container.replaceChildren(content);
  } catch (err) {
    container.replaceChildren(
      errorState(err, {
        title: "Could not audit system health",
        onRetry: () => loadSystemHealth()
      })
    );
  }
}

async function loadUsers() {
  const container = $("#users-table-container");
  if (!container) return;

  container.replaceChildren(loadingState("Loading registered user accounts…"));

  try {
    const users = await Api.admin.users({ limit: 50 });
    renderUsersTable(container, users);
  } catch (err) {
    container.replaceChildren(
      errorState(err, {
        title: "Could not load user accounts",
        onRetry: () => loadUsers()
      })
    );
  }
}

function renderUsersTable(container, users) {
  container.replaceChildren();

  if (!users || users.length === 0) {
    container.appendChild(emptyState({ title: "No users registered", iconName: "users" }));
    return;
  }

  const tableWrapper = h("div", { class: "table-wrapper" },
    h("table", { class: "table" },
      h("thead", {},
        h("tr", {},
          h("th", { text: "Full Name" }),
          h("th", { text: "Email Address" }),
          h("th", { text: "Role" }),
          h("th", { text: "Status" }),
          h("th", { text: "Joined" }),
          h("th", { text: "Action" })
        )
      ),
      h("tbody", {},
        users.map(u =>
          h("tr", {},
            h("td", {}, h("strong", { text: u.full_name })),
            h("td", { text: u.email }),
            h("td", {}, badge(u.role)),
            h("td", {},
              u.is_active
                ? h("span", { class: "badge badge--success", text: "Active" })
                : h("span", { class: "badge badge--danger", text: "Deactivated" })
            ),
            h("td", { style: { fontSize: "var(--font-size-xs)" }, text: fmtDate(u.created_at) }),
            h("td", {},
              h("button", {
                class: `btn btn--sm ${u.is_active ? "btn--ghost" : "btn--secondary"}`,
                style: u.is_active ? { color: "var(--color-danger)" } : {},
                onclick: async () => {
                  const newStatus = !u.is_active;
                  const confirmed = await confirmDialog({
                    title: newStatus ? "Activate Account" : "Deactivate Account",
                    message: `Are you sure you want to ${newStatus ? "activate" : "deactivate"} '${u.email}'?`,
                    confirmLabel: newStatus ? "Activate" : "Deactivate",
                    danger: !newStatus
                  });
                  if (!confirmed) return;
                  try {
                    await Api.admin.setStatus(u.id, newStatus);
                    toast(`Account ${u.email} status updated.`, { type: "success" });
                    loadUsers();
                  } catch (e) {
                    toast(errorMessage(e, "Failed to update account status."), { type: "error" });
                  }
                }
              }, u.is_active ? "Deactivate" : "Activate")
            )
          )
        )
      )
    )
  );

  container.appendChild(tableWrapper);
}

async function loadAuditLogs() {
  const container = $("#audit-logs-container");
  if (!container) return;

  try {
    const logs = await Api.admin.auditLogs(15);
    if (!logs || logs.length === 0) {
      container.replaceChildren(h("p", { class: "field__hint", text: "No security audit events recorded." }));
      return;
    }

    const tableWrapper = h("div", { class: "table-wrapper" },
      h("table", { class: "table" },
        h("thead", {},
          h("tr", {},
            h("th", { text: "Action" }),
            h("th", { text: "IP Address" }),
            h("th", { text: "Timestamp" })
          )
        ),
        h("tbody", {},
          logs.map(l =>
            h("tr", {},
              h("td", {}, h("strong", { text: l.action })),
              h("td", { style: { fontSize: "var(--font-size-xs)" }, text: l.ip_address || "Localhost" }),
              h("td", { style: { fontSize: "var(--font-size-xs)" }, text: fmtDate(l.created_at, { time: true }) })
            )
          )
        )
      )
    );
    container.replaceChildren(tableWrapper);
  } catch {
    container.replaceChildren(h("p", { class: "field__hint", text: "Could not load security logs." }));
  }
}

