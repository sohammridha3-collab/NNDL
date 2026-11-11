/**
 * Resume Management Controller
 */
import { Api } from "../api.js";
import { CONFIG } from "../config.js";
import { requireAuth } from "../auth.js";
import { initAppShell } from "../app.js";
import {
  $,
  h,
  icon,
  badge,
  chip,
  fmtDate,
  fmtBytes,
  loadingState,
  emptyState,
  errorState,
  confirmDialog,
  openDialog,
  toast,
  errorMessage
} from "../ui.js";

let resumesList = [];

document.addEventListener("DOMContentLoaded", async () => {
  const user = await requireAuth(["candidate", "admin"]);
  if (!user) return;

  initAppShell({
    user,
    activePage: "resumes.html",
    breadcrumbs: [{ label: "Workspace" }, { label: "My Resumes" }]
  });

  setupDropzone();
  loadResumes();
});

function setupDropzone() {
  const dropzone = $("#resume-dropzone");
  const fileInput = $("#resume-file-input");
  const progressContainer = $("#upload-progress-container");
  const progressBar = $("#upload-progress-bar");
  const progressText = $("#upload-progress-text");

  if (!dropzone || !fileInput) return;

  // Click to trigger file input
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  // Drag-and-drop events
  ["dragenter", "dragover"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dropzone--dragover");
    });
  });

  ["dragleave", "drop"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dropzone--dragover");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFileUpload(files[0]);
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length > 0) {
      handleFileUpload(fileInput.files[0]);
      fileInput.value = ""; // Reset
    }
  });

  async function handleFileUpload(file) {
    // Validate format
    const ext = `.${file.name.split(".").pop().toLowerCase()}`;
    if (!CONFIG.ACCEPTED_RESUME_TYPES.includes(ext)) {
      toast(`Unsupported file format. Please upload a ${CONFIG.ACCEPTED_RESUME_TYPES.join(", ")} document.`, { type: "error" });
      return;
    }

    // Validate size (10MB)
    const maxBytes = CONFIG.MAX_UPLOAD_MB * 1024 * 1024;
    if (file.size > maxBytes) {
      toast(`File is too large (${fmtBytes(file.size)}). Maximum allowed is ${CONFIG.MAX_UPLOAD_MB}MB.`, { type: "error" });
      return;
    }

    // Show progress
    progressContainer.style.display = "block";
    progressBar.style.width = "0%";
    progressText.textContent = "Uploading document…";

    try {
      const res = await Api.resumes.upload(file, {
        onProgress: (p) => {
          if (p.phase === "upload") {
            const pct = p.total ? Math.round((p.loaded / p.total) * 100) : 50;
            progressBar.style.width = `${pct}%`;
            progressText.textContent = `Uploading: ${pct}%`;
          } else if (p.phase === "processing") {
            progressBar.style.width = "100%";
            progressText.textContent = "Extracting text, evaluating ATS score & skills…";
          }
        }
      });

      toast(`Resume '${file.name}' parsed successfully! (ATS Score: ${res.ats_score}%)`, { type: "success" });
      progressContainer.style.display = "none";
      loadResumes();
    } catch (err) {
      progressContainer.style.display = "none";
      toast(errorMessage(err, "Failed to upload and parse resume."), { type: "error" });
    }
  }
}

async function loadResumes() {
  const container = $("#resumes-list-container");
  if (!container) return;

  container.replaceChildren(loadingState("Loading your uploaded resumes…"));

  try {
    resumesList = await Api.resumes.list();
    renderResumesList(container, resumesList);
  } catch (err) {
    container.replaceChildren(
      errorState(err, {
        title: "Could not load resumes",
        onRetry: () => loadResumes()
      })
    );
  }
}

function renderResumesList(container, resumes) {
  container.replaceChildren();

  if (!resumes || resumes.length === 0) {
    container.appendChild(
      emptyState({
        title: "No resumes uploaded yet",
        message: "Upload a PDF, DOCX, or TXT file above to analyze ATS readability and unlock AI job recommendations.",
        iconName: "file"
      })
    );
    return;
  }

  const grid = h("div", { class: "grid grid--cols-1", style: { gap: "var(--space-4)" } });

  resumes.forEach((r) => {
    const card = h("div", { class: "card" },
      h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-3)", marginBottom: "var(--space-3)" } },
        h("div", {},
          h("div", { style: { display: "flex", alignItems: "center", gap: "var(--space-2)", marginBottom: "var(--space-1)" } },
            h("h3", { style: { fontSize: "var(--font-size-base)", fontWeight: "var(--font-weight-semibold)" }, text: r.file_name }),
            r.is_active ? h("span", { class: "badge badge--success", text: "Active" }) : null
          ),
          h("p", { class: "field__hint", text: `Version ${r.version} • ${fmtBytes(r.file_size_bytes)} • Uploaded ${fmtDate(r.created_at)}` })
        ),
        h("div", { style: { display: "flex", alignItems: "center", gap: "var(--space-2)" } },
          h("button", {
            class: "btn btn--secondary btn--sm",
            onclick: () => viewAnalysis(r.id)
          }, icon("sparkles", { size: 14 }), " ATS Breakdown"),
          h("button", {
            class: "btn btn--ghost btn--sm",
            style: { color: "var(--color-danger)" },
            "aria-label": `Delete ${r.file_name}`,
            onclick: () => deleteResume(r.id, r.file_name)
          }, icon("trash", { size: 14 }), " Delete")
        )
      ),

      // Scores Row
      h("div", { style: { display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-3)" } },
        h("div", { style: { fontSize: "var(--font-size-sm)" } },
          h("span", { style: { color: "var(--text-muted)" }, text: "ATS Readability: " }),
          h("strong", { style: { color: r.ats_score >= 70 ? "var(--color-success)" : "var(--color-warning)" }, text: `${r.ats_score}%` })
        ),
        h("div", { style: { fontSize: "var(--font-size-sm)" } },
          h("span", { style: { color: "var(--text-muted)" }, text: "Completeness: " }),
          h("strong", { text: `${r.completeness_score}%` })
        )
      ),

      // Skills chips
      r.skills && r.skills.length > 0
        ? h("div", {},
            h("span", { style: { fontSize: "var(--font-size-xs)", color: "var(--text-muted)", display: "block", marginBottom: "var(--space-1)" }, text: "Recognized Technical Skills:" }),
            h("div", { class: "chip-list" }, r.skills.map((s) => chip(s, "accent")))
          )
        : h("p", { class: "field__hint", text: "No canonical skills identified in this version." })
    );

    grid.appendChild(card);
  });

  container.appendChild(grid);
}

async function viewAnalysis(resumeId) {
  try {
    const analysis = await Api.resumes.analyze(resumeId);

    const content = h("div", { style: { display: "flex", flexDirection: "column", gap: "var(--space-4)" } },
      // Overview stats
      h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)" } },
        h("div", { class: "metric-card" },
          h("span", { class: "field__hint", text: "ATS Readability Score" }),
          h("strong", { style: { fontSize: "var(--font-size-2xl)", color: "var(--color-primary)" }, text: `${analysis.ats_score}%` }),
          h("span", { class: "field__hint", text: `Rating: ${analysis.readability_rating}` })
        ),
        h("div", { class: "metric-card" },
          h("span", { class: "field__hint", text: "Resume Completeness" }),
          h("strong", { style: { fontSize: "var(--font-size-2xl)" }, text: `${analysis.completeness_score}%` }),
          h("span", { class: "field__hint", text: "Key section coverage" })
        )
      ),

      // Identified Sections
      h("div", {},
        h("h4", { style: { fontSize: "var(--font-size-sm)", marginBottom: "var(--space-2)" }, text: "Identified Sections" }),
        h("div", { class: "chip-list" },
          analysis.identified_sections && analysis.identified_sections.length > 0
            ? analysis.identified_sections.map((s) => chip(s, "matched"))
            : h("span", { class: "field__hint", text: "No standard section headers recognized." })
        )
      ),

      // Missing Sections
      analysis.missing_critical_sections && analysis.missing_critical_sections.length > 0
        ? h("div", {},
            h("h4", { style: { fontSize: "var(--font-size-sm)", color: "var(--color-danger)", marginBottom: "var(--space-2)" }, text: "Missing Critical Sections" }),
            h("div", { class: "chip-list" },
              analysis.missing_critical_sections.map((s) => chip(s, "missing"))
            )
          )
        : null,

      // Strengths
      analysis.strengths && analysis.strengths.length > 0
        ? h("div", {},
            h("h4", { style: { fontSize: "var(--font-size-sm)", color: "var(--color-success)", marginBottom: "var(--space-2)" }, text: "Strengths" }),
            h("ul", { style: { paddingLeft: "var(--space-5)", fontSize: "var(--font-size-sm)", color: "var(--text-secondary)" } },
              analysis.strengths.map((str) => h("li", { text: str }))
            )
          )
        : null,

      // Recommendations
      analysis.improvement_recommendations && analysis.improvement_recommendations.length > 0
        ? h("div", {},
            h("h4", { style: { fontSize: "var(--font-size-sm)", color: "var(--color-warning)", marginBottom: "var(--space-2)" }, text: "Improvement Recommendations" }),
            h("ul", { style: { paddingLeft: "var(--space-5)", fontSize: "var(--font-size-sm)", color: "var(--text-secondary)" } },
              analysis.improvement_recommendations.map((rec) => h("li", { text: rec }))
            )
          )
        : null,

      // SDG 10 Bias Mitigation notice
      h("div", { class: "notice notice--info", style: { margin: 0 } },
        icon("shield", { size: 16 }),
        h("p", { text: "SDG 10 Privacy Active: Personal identifiers (name, age, gender pronouns, contact details) are masked prior to ML feature vector calculation." })
      )
    );

    openDialog({
      title: "Detailed ATS & Skill Analysis",
      description: "Automated parsing and readability audit",
      body: content,
      size: "lg",
      actions: [{ label: "Close", variant: "secondary" }]
    });
  } catch (err) {
    toast(errorMessage(err, "Could not fetch resume analysis."), { type: "error" });
  }
}

async function deleteResume(resumeId, filename) {
  const confirmed = await confirmDialog({
    title: "Delete Resume",
    message: `Are you sure you want to delete '${filename}'? This cannot be undone.`,
    confirmLabel: "Delete Resume",
    danger: true
  });

  if (!confirmed) return;

  try {
    await Api.resumes.remove(resumeId);
    toast("Resume deleted successfully.", { type: "success" });
    loadResumes();
  } catch (err) {
    toast(errorMessage(err, "Failed to delete resume."), { type: "error" });
  }
}

