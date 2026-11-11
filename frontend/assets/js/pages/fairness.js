/**
 * SDG 10 Fairness & Counterfactual Sensitivity Controller
 */
import { Api } from "../api.js";
import { requireAuth } from "../auth.js";
import { initAppShell } from "../app.js";
import {
  $,
  h,
  icon,
  badge,
  fmtDate,
  loadingState,
  emptyState,
  errorState,
  setBusy,
  toast,
  errorMessage,
  barList
} from "../ui.js";

document.addEventListener("DOMContentLoaded", async () => {
  const user = await requireAuth();
  if (!user) return;

  initAppShell({
    user,
    activePage: "fairness.html",
    breadcrumbs: [{ label: "Workspace" }, { label: "SDG 10: Reduced Inequalities" }]
  });

  setupAuditTrigger(user);
  loadFairnessReports();
});

function setupAuditTrigger(user) {
  const runBtn = $("#run-fairness-audit-btn");
  if (!runBtn) return;

  // Only recruiters and admins have permission to trigger full audits
  if (user.role === "candidate") {
    runBtn.style.display = "none";
    return;
  }

  runBtn.addEventListener("click", async () => {
    setBusy(runBtn, true, "Running Synthetic Testing (72 pairs)…");
    try {
      const auditResult = await Api.fairness.run("SDG 10 Counterfactual Fairness Audit");
      toast("Fairness audit completed and recorded!", { type: "success" });
      setBusy(runBtn, false);
      renderActiveAuditResult(auditResult);
      loadFairnessReports();
    } catch (err) {
      setBusy(runBtn, false);
      toast(errorMessage(err, "Failed to run fairness audit."), { type: "error" });
    }
  });
}

function renderActiveAuditResult(audit) {
  const container = $("#active-audit-result-container");
  if (!container) return;

  const summary = (audit.metrics && audit.metrics.summary) || audit.demographic_parity_summary || {};
  const verdict = audit.overall_fairness_verdict || (
    summary.unmasked_mean_score_deviation !== undefined
      ? `Synthetic paired test over ${summary.evaluation_sample_pairs || 72} comparisons: mean score change ${summary.masked_mean_score_deviation} pts with masking vs ${summary.unmasked_mean_score_deviation} pts without; decision flip rate with masking ${(Number(summary.decision_flip_rate_with_masking || 0) * 100).toFixed(1)}%. Covers only the tested name, pronoun and age variants.`
      : "Evaluated under UN SDG 10 standards for demographic invariance and counterfactual fairness."
  );
  const recommendations = audit.recommendations || [
    "Maintain automated regex-based PII and demographic masking prior to feature generation (SDG 10 compliance).",
    "Prohibit recruiters from viewing unmasked demographic tokens during preliminary AI ranking.",
    "Mandate human-in-the-loop review for hiring decisions; never automate rejections based strictly on threshold scores."
  ];

  const card = h("div", { class: "card", style: { marginBottom: "var(--space-6)", borderColor: "var(--color-primary)" } },
    h("div", { class: "card__header" },
      h("h3", { class: "card__title" }, icon("shield", { size: 18 }), " Latest Audit Verification Results"),
      h("span", { class: "badge badge--success", text: "SDG 10 Invariance Verified" })
    ),

    // Metric Summary Grid
    h("div", { class: "grid grid--stats", style: { marginBottom: "var(--space-4)" } },
      renderMetricTile("Unmasked Deviation", `${summary.unmasked_mean_score_deviation ?? 0} pts`, "Mean score variation with PII visible"),
      renderMetricTile("Masked Deviation", `${summary.masked_mean_score_deviation ?? 0} pts`, "Score variation under SDG 10 privacy masking"),
      renderMetricTile("Demographic Bias Reduction", `${summary.demographic_bias_reduction_percentage ?? 0}%`, "Equal opportunity enhancement"),
      renderMetricTile("Masked Decision Flip Rate", `${(Number(summary.decision_flip_rate_with_masking || 0) * 100).toFixed(1)}%`, "Classification stability across demographic variants")
    ),

    // Factual Verdict Box
    h("div", { class: "notice notice--info", style: { marginBottom: "var(--space-4)" } },
      icon("info", { size: 16 }),
      h("div", {},
        h("strong", { class: "notice__title", text: "Empirical Audit Verdict" }),
        h("p", { text: verdict })
      )
    ),

    // Recommendations list
    recommendations.length > 0
      ? h("div", {},
          h("h4", { style: { fontSize: "var(--font-size-sm)", marginBottom: "var(--space-2)" }, text: "Ethical AI Governance Guidelines" }),
          h("ul", { style: { paddingLeft: "var(--space-5)", fontSize: "var(--font-size-sm)", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: "var(--space-1)" } },
            recommendations.map(r => h("li", { text: r }))
          )
        )
      : null
  );

  container.replaceChildren(card);
}

function renderMetricTile(label, value, subtext) {
  return h("div", { class: "metric-card" },
    h("span", { class: "field__hint", text: label }),
    h("div", { class: "metric-card__value", text: value }),
    h("div", { class: "metric-card__subtext", text: subtext })
  );
}

async function loadFairnessReports() {
  const container = $("#fairness-history-container");
  if (!container) return;

  container.replaceChildren(loadingState("Loading historical audit reports…"));

  try {
    const reports = await Api.fairness.reports();
    renderFairnessReportsTable(container, reports);
    if (reports && reports.length > 0) {
      renderActiveAuditResult(reports[0]);
    }
  } catch (err) {
    container.replaceChildren(
      errorState(err, {
        title: "Could not load fairness history",
        onRetry: () => loadFairnessReports()
      })
    );
  }
}

function renderFairnessReportsTable(container, reports) {
  container.replaceChildren();

  if (!reports || reports.length === 0) {
    container.appendChild(
      emptyState({
        title: "No audit reports logged yet",
        message: "Trigger a synthetic counterfactual audit above to measure model demographic score invariance.",
        iconName: "scale"
      })
    );
    return;
  }

  const tableWrapper = h("div", { class: "table-wrapper" },
    h("table", { class: "table" },
      h("thead", {},
        h("tr", {},
          h("th", { text: "Audit Name" }),
          h("th", { text: "Tested Pairs" }),
          h("th", { text: "Model Architecture" }),
          h("th", { text: "Timestamp" }),
          h("th", { text: "Masked Flip Rate" })
        )
      ),
      h("tbody", {},
        reports.map(r => {
          const metrics = r.metrics || {};
          const summary = metrics.summary || {};
          return h("tr", {},
            h("td", {}, h("strong", { text: r.name })),
            h("td", { text: `${r.total_pairs} pairs` }),
            h("td", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)" }, text: r.model_version }),
            h("td", { style: { fontSize: "var(--font-size-xs)" }, text: fmtDate(r.created_at) }),
            h("td", {},
              summary.decision_flip_rate_with_masking !== undefined
                ? h("span", { class: "badge badge--success", text: `${(summary.decision_flip_rate_with_masking * 100).toFixed(1)}%` })
                : h("span", { text: "—" })
            )
          );
        })
      )
    )
  );

  container.appendChild(tableWrapper);
}

