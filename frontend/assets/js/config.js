/**
 * Central frontend configuration.
 * Values are verified against the FastAPI backend (backend/app/core/config.py and routers).
 * The API origin can be overridden at deploy time through the public `env.js` file.
 */
const runtime = (typeof window !== "undefined" && window.APP_CONFIG) || {};

function cleanOrigin(value, fallback) {
  const v = typeof value === "string" && value.trim() ? value.trim() : fallback;
  return v.replace(/\/+$/, "");
}

export const CONFIG = Object.freeze({
  /** Backend origin (scheme + host + port). */
  API_ORIGIN: cleanOrigin(runtime.API_ORIGIN, "http://127.0.0.1:8001"),
  /** Versioned API prefix — settings.API_V1_STR in the backend. */
  API_PREFIX: "/api/v1",
  /** Probes are mounted at the application root, outside /api/v1. */
  HEALTH_PATH: "/health",
  READY_PATH: "/ready",
  /** Default request timeout. Model inference endpoints use INFERENCE_TIMEOUT_MS. */
  REQUEST_TIMEOUT_MS: 20000,
  INFERENCE_TIMEOUT_MS: 120000,
  UPLOAD_TIMEOUT_MS: 120000,
  /** Mirrors backend settings.MAX_UPLOAD_SIZE_MB and file_extractor.py support (pdf, docx, txt). */
  MAX_UPLOAD_MB: Number(runtime.MAX_UPLOAD_MB) || 10,
  ACCEPTED_RESUME_TYPES: Object.freeze([".pdf", ".docx", ".txt"]),
  /** Minimum characters the backend accepts for extracted resume text. */
  MIN_RESUME_CHARS: 30,
  /** JobCreate.description min_length in backend schemas. */
  MIN_JOB_CHARS: 20,
  PAGE_SIZE: 12,
  ROLE_HOME: Object.freeze({
    candidate: "dashboard.html",
    recruiter: "recruiter.html",
    admin: "admin.html"
  })
});

export const apiUrl = (path) => `${CONFIG.API_ORIGIN}${CONFIG.API_PREFIX}${path.startsWith("/") ? "" : "/"}${path}`;
export const rootUrl = (path) => `${CONFIG.API_ORIGIN}${path.startsWith("/") ? "" : "/"}${path}`;

