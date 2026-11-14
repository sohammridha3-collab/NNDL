/**
 * Centralized API client for the FastAPI backend.
 *
 * - Bearer-token auth (backend contract: POST /auth/login with JSON, returns access + refresh tokens)
 * - Single-flight token refresh; an eligible request is retried at most once after a 401
 *   (a 401 means the dependency rejected the request before the handler ran, so no duplicate side effects)
 * - Timeouts with AbortController, caller cancellation, stale-response protection
 * - JSON and multipart (never sets Content-Type for FormData)
 * - FastAPI validation (422) errors mapped to field messages
 * - XMLHttpRequest uploads for genuine transfer progress (kept separate from server processing)
 * - No automatic retries of mutations on network or server errors
 */
import { CONFIG, apiUrl, rootUrl } from "./config.js";
import { session } from "./session.js";

export class ApiError extends Error {
  constructor({ status = 0, kind = "unknown", message = "Something went wrong.", detail = null, fieldErrors = {}, payload = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
    this.payload = payload;
  }
  get isAborted() {
    return this.kind === "aborted";
  }
}

const KIND_BY_STATUS = {
  400: "bad_request",
  401: "auth",
  403: "forbidden",
  404: "not_found",
  409: "conflict",
  413: "too_large",
  422: "validation",
  429: "rate_limited",
  500: "server",
  502: "unavailable",
  503: "unavailable",
  504: "unavailable"
};

const DEFAULT_MESSAGES = {
  auth: "Your session has expired. Please sign in again.",
  forbidden: "You do not have permission to perform this action.",
  not_found: "The requested item could not be found.",
  validation: "Some fields need attention.",
  rate_limited: "Too many requests. Please wait a moment and try again.",
  server: "The server encountered an error. Please try again later.",
  unavailable: "The service is temporarily unavailable. Please try again shortly.",
  too_large: "The file is larger than the server allows."
};

function humanField(loc) {
  const parts = (loc || []).filter((p) => !["body", "query", "path", "header"].includes(p));
  return parts.length ? parts.join(".") : "_form";
}

export function errorFromResponse(status, body) {
  const kind = KIND_BY_STATUS[status] || (status >= 500 ? "server" : "bad_request");
  const detail = body && typeof body === "object" ? body.detail : typeof body === "string" ? body : null;
  const fieldErrors = {};
  let message = DEFAULT_MESSAGES[kind] || `Request failed (HTTP ${status}).`;

  if (Array.isArray(detail)) {
    for (const item of detail) {
      const field = humanField(item.loc);
      const msg = String(item.msg || "Invalid value").replace(/^Value error,\s*/i, "");
      if (!fieldErrors[field]) fieldErrors[field] = msg;
    }
    const first = Object.entries(fieldErrors)[0];
    if (first) message = first[0] === "_form" ? first[1] : `${first[0]}: ${first[1]}`;
  } else if (typeof detail === "string" && detail.trim() && !(status >= 500 && detail.startsWith("<"))) {
    message = detail;
  }
  const payload = body && typeof body === "object" ? body : null;
  return new ApiError({ status, kind, message, detail, fieldErrors, payload });
}

/* ---------- auth-expiry hook (set by the app shell) ---------- */
let onAuthExpired = null;
export function setAuthExpiredHandler(fn) {
  onAuthExpired = fn;
}
function handleExpired() {
  session.clear();
  if (typeof onAuthExpired === "function") onAuthExpired();
}

/* ---------- low-level fetch with timeout + external cancellation ---------- */
async function fetchWithTimeout(url, init, timeoutMs, externalSignal) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    else externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (timedOut) {
      throw new ApiError({ kind: "timeout", message: "The request took too long and was stopped. Please try again." });
    }
    if (controller.signal.aborted) {
      throw new ApiError({ kind: "aborted", message: "Request cancelled." });
    }
    throw new ApiError({
      kind: "network",
      message: `Cannot reach the server at ${CONFIG.API_ORIGIN}. Check that the backend is running and your connection is available.`
    });
  } finally {
    clearTimeout(timer);
    if (externalSignal) externalSignal.removeEventListener("abort", onExternalAbort);
  }
}

async function parseBody(res) {
  if (res.status === 204 || res.status === 205) return null;
  const text = await res.text();
  if (!text) return null;
  const type = res.headers.get("content-type") || "";
  if (type.includes("json")) {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }
  return text;
}

function filenameFrom(res) {
  const cd = res.headers.get("content-disposition") || "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  if (star) return decodeURIComponent(star[1]);
  const plain = /filename="?([^";]+)"?/i.exec(cd);
  return plain ? plain[1] : "download";
}

/* ---------- token refresh (single flight) ---------- */
let refreshInFlight = null;
export function refreshTokens() {
  if (refreshInFlight) return refreshInFlight;
  const refreshToken = session.getRefreshToken();
  if (!refreshToken) return Promise.resolve(false);
  refreshInFlight = (async () => {
    try {
      const res = await fetchWithTimeout(
        apiUrl("/auth/refresh"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
          credentials: "omit"
        },
        CONFIG.REQUEST_TIMEOUT_MS
      );
      if (!res.ok) return false;
      const data = await res.json();
      if (!data || !data.access_token) return false;
      session.save(data);
      return true;
    } catch {
      return false;
    } finally {
      // Release after current waiters have received the result.
      setTimeout(() => {
        refreshInFlight = null;
      }, 0);
    }
  })();
  return refreshInFlight;
}

function buildUrl(path, query, root) {
  let url = root ? rootUrl(path) : apiUrl(path);
  if (query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      qs.append(k, String(v));
    }
    const s = qs.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }
  return url;
}

/**
 * Generic request.
 * @param {string} method
 * @param {string} path  path below /api/v1 (or below the origin when root=true)
 * @param {object} opts  { query, body, signal, timeout, auth, root, responseType }
 */
export async function request(method, path, opts = {}) {
  const { query, body, signal, timeout, auth = true, root = false, responseType = "json", headers = {}, _retried = false } = opts;
  const url = buildUrl(path, query, root);
  const h = { Accept: "application/json", ...headers };
  let payload;
  if (typeof FormData !== "undefined" && body instanceof FormData) {
    payload = body; // browser sets multipart boundary
  } else if (body !== undefined) {
    h["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (auth) {
    const token = session.getAccessToken();
    if (token) h.Authorization = `Bearer ${token}`;
  }

  const res = await fetchWithTimeout(
    url,
    { method, headers: h, body: payload, credentials: "omit" },
    timeout ?? CONFIG.REQUEST_TIMEOUT_MS,
    signal
  );

  if (res.status === 401 && auth && !_retried && session.getRefreshToken()) {
    const refreshed = await refreshTokens();
    if (refreshed) return request(method, path, { ...opts, _retried: true });
  }

  if (!res.ok) {
    const errBody = await parseBody(res).catch(() => null);
    const err = errorFromResponse(res.status, errBody);
    if (res.status === 401 && auth) handleExpired();
    throw err;
  }

  if (responseType === "blob") {
    return { blob: await res.blob(), filename: filenameFrom(res) };
  }
  return parseBody(res);
}

export const http = {
  get: (path, opts) => request("GET", path, opts),
  post: (path, body, opts = {}) => request("POST", path, { ...opts, body }),
  put: (path, body, opts = {}) => request("PUT", path, { ...opts, body }),
  patch: (path, body, opts = {}) => request("PATCH", path, { ...opts, body }),
  del: (path, opts) => request("DELETE", path, opts)
};

/** Download a binary response and trigger a browser save. */
export async function download(path, opts = {}) {
  const { blob, filename } = await request("GET", path, { ...opts, responseType: "blob" });
  saveBlob(blob, opts.filename || filename);
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Multipart upload with genuine transfer progress (XMLHttpRequest).
 * onProgress receives {phase:"upload", loaded, total} and then {phase:"processing"} once
 * the bytes are sent and the server is extracting text — those phases are reported separately.
 */
export function uploadWithProgress(path, formData, { onProgress, signal, timeout = CONFIG.UPLOAD_TIMEOUT_MS } = {}) {
  const attempt = () =>
    new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", apiUrl(path));
      xhr.timeout = timeout;
      xhr.setRequestHeader("Accept", "application/json");
      const token = session.getAccessToken();
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (e) => onProgress && onProgress({ phase: "upload", loaded: e.loaded, total: e.lengthComputable ? e.total : null });
      xhr.upload.onload = () => onProgress && onProgress({ phase: "processing" });
      xhr.onload = () => {
        let body = null;
        try {
          body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
        } catch {
          body = xhr.responseText;
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body);
        else reject(errorFromResponse(xhr.status, body));
      };
      xhr.onerror = () =>
        reject(new ApiError({ kind: "network", message: `Cannot reach the server at ${CONFIG.API_ORIGIN}. The upload was not completed.` }));
      xhr.ontimeout = () => reject(new ApiError({ kind: "timeout", message: "The upload timed out. Please try again." }));
      xhr.onabort = () => reject(new ApiError({ kind: "aborted", message: "Upload cancelled." }));
      if (signal) {
        if (signal.aborted) return xhr.abort();
        signal.addEventListener("abort", () => xhr.abort(), { once: true });
      }
      xhr.send(formData);
    });

  return attempt().catch(async (err) => {
    if (err.status === 401 && session.getRefreshToken() && (await refreshTokens())) {
      try {
        return await attempt();
      } catch (second) {
        if (second.status === 401) handleExpired();
        throw second;
      }
    }
    if (err.status === 401) handleExpired();
    throw err;
  });
}

/**
 * Stale-response protection: each call aborts the previous in-flight call
 * and only the most recent call may resolve.
 */
export function latestOnly() {
  let current = null;
  return function run(fn) {
    if (current) current.abort();
    const controller = new AbortController();
    current = controller;
    return fn(controller.signal).then(
      (value) => {
        if (current !== controller) throw new ApiError({ kind: "aborted", message: "Superseded." });
        return value;
      },
      (err) => {
        if (current !== controller) throw new ApiError({ kind: "aborted", message: "Superseded." });
        throw err;
      }
    );
  };
}

/* ======================================================================
 * Endpoint catalogue — verified against backend/app/api/*.py
 * ====================================================================== */
const enc = encodeURIComponent;

export const Api = {
  system: {
    health: (opts) => http.get(CONFIG.HEALTH_PATH, { ...opts, root: true, auth: false, timeout: 8000 }),
    ready: (opts) => http.get(CONFIG.READY_PATH, { ...opts, root: true, auth: false, timeout: 15000 })
  },
  auth: {
    login: (email, password) => http.post("/auth/login", { email, password }, { auth: false }),
    register: (payload) => http.post("/auth/register", payload, { auth: false }),
    me: (opts) => http.get("/auth/me", opts),
    logout: () => http.post("/auth/logout", undefined, { timeout: 5000 })
  },
  resumes: {
    list: (opts) => http.get("/resumes", opts),
    get: (id, opts) => http.get(`/resumes/${enc(id)}`, opts),
    upload: (file, handlers) => {
      const fd = new FormData();
      fd.append("file", file, file.name); // backend field name: "file"
      return uploadWithProgress("/resumes/upload", fd, handlers);
    },
    remove: (id) => http.del(`/resumes/${enc(id)}`),
    analyze: (id, opts) => http.post(`/resumes/${enc(id)}/analyze`, undefined, opts)
  },
  jobs: {
    list: (query, opts = {}) => http.get("/jobs", { ...opts, query }),
    get: (id, opts) => http.get(`/jobs/${enc(id)}`, opts),
    create: (payload) => http.post("/jobs", payload),
    update: (id, payload) => http.put(`/jobs/${enc(id)}`, payload),
    close: (id) => http.del(`/jobs/${enc(id)}`),
    apply: (id, payload) => http.post(`/jobs/${enc(id)}/apply`, payload, { timeout: CONFIG.INFERENCE_TIMEOUT_MS }),
    toggleSave: (id) => http.post(`/jobs/${enc(id)}/save`),
    applicants: (id, opts) => http.get(`/jobs/${enc(id)}/applicants`, opts),
    updateApplicant: (jobId, appId, payload) => http.put(`/jobs/${enc(jobId)}/applicants/${enc(appId)}`, payload),
    mine: (status = "all", opts = {}) => http.get("/jobs/recruiter/mine", { ...opts, query: { status } }),
    myApplications: (opts) => http.get("/jobs/applications/mine", opts),
    saved: (opts) => http.get("/jobs/saved/mine", opts),
    saveExternal: (payload) => http.post("/jobs/save-external", payload),
    liveStatus: (opts = {}) => http.get("/jobs/live/status", opts),
    searchLive: (query, opts = {}) => http.get("/jobs/live/search", { ...opts, query })
  },
  matching: {
    predict: (payload, opts = {}) => http.post("/matching/predict", payload, { timeout: CONFIG.INFERENCE_TIMEOUT_MS, ...opts }),
    history: (opts) => http.get("/matching/history", opts),
    explanation: (id, opts) => http.get(`/matching/${enc(id)}/explanation`, opts)
  },
  recommendations: {
    jobs: (query, opts = {}) => http.get("/recommendations/jobs", { timeout: CONFIG.INFERENCE_TIMEOUT_MS, ...opts, query }),
    candidates: (jobId, limit = 10, opts = {}) =>
      http.get("/recommendations/candidates", { timeout: CONFIG.INFERENCE_TIMEOUT_MS, ...opts, query: { job_id: jobId, limit } }),
    bySkills: (payload, opts = {}) => http.post("/recommendations/skills", payload, { timeout: CONFIG.INFERENCE_TIMEOUT_MS, ...opts }),
    extractSkills: (payload, opts = {}) => http.post("/recommendations/extract-skills", payload, opts),
    profileSummary: (payload, opts = {}) => http.post("/recommendations/profile-summary", payload, opts)
  },
  dashboard: {
    candidate: (opts) => http.get("/dashboard/candidate", opts),
    recruiter: (opts) => http.get("/dashboard/recruiter", opts),
    admin: (opts) => http.get("/dashboard/admin", opts)
  },
  fairness: {
    run: (name) => http.post("/fairness/audit", { name }, { timeout: 300000 }),
    reports: (opts) => http.get("/fairness/reports", opts)
  },
  admin: {
    users: (query, opts = {}) => http.get("/admin/users", { ...opts, query }),
    setStatus: (userId, isActive) => http.put(`/admin/users/${enc(userId)}/status`, undefined, { query: { is_active: isActive } }),
    auditLogs: (limit = 50, opts = {}) => http.get("/admin/audit-logs", { ...opts, query: { limit } }),
    systemHealth: (opts) => http.get("/admin/system-health", { timeout: 60000, ...opts })
  }
};

