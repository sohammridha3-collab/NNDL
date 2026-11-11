/**
 * Centralized API Client for Inclusive Resume & Job Matching System
 * SDG 10: Reduced Inequalities
 */

// Dynamically resolve base URL: from window env, Vite env, or fallback to relative/localhost
const API_BASE_URL = 
  (typeof window !== "undefined" && window.__ENV__ && window.__ENV__.VITE_API_BASE_URL) ||
  (typeof import.meta !== "undefined" && import.meta.env && import.meta.env.VITE_API_BASE_URL) ||
  "http://localhost:8000/api/v1";

class ApiClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  getToken() {
    return localStorage.getItem("ats_access_token");
  }

  getRefreshToken() {
    return localStorage.getItem("ats_refresh_token");
  }

  setTokens(accessToken, refreshToken) {
    if (accessToken) localStorage.setItem("ats_access_token", accessToken);
    if (refreshToken) localStorage.setItem("ats_refresh_token", refreshToken);
  }

  clearTokens() {
    localStorage.removeItem("ats_access_token");
    localStorage.removeItem("ats_refresh_token");
    localStorage.removeItem("ats_user");
  }

  getUser() {
    try {
      const u = localStorage.getItem("ats_user");
      return u ? JSON.parse(u) : null;
    } catch {
      return null;
    }
  }

  setUser(user) {
    localStorage.setItem("ats_user", JSON.stringify(user));
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;
    const headers = options.headers || {};

    const token = this.getToken();
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    const config = {
      ...options,
      headers
    };

    let response = await fetch(url, config);

    // Auto token refresh on 401
    if (response.status === 401 && this.getRefreshToken() && !endpoint.includes("/auth/")) {
      const refreshed = await this.refreshToken();
      if (refreshed) {
        headers["Authorization"] = `Bearer ${this.getToken()}`;
        response = await fetch(url, { ...options, headers });
      }
    }

    if (!response.ok) {
      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = { detail: response.statusText || "Request failed" };
      }
      const message = errorData.detail || "An error occurred during the API request.";
      throw new Error(message);
    }

    // Return empty for 204
    if (response.status === 204) return null;
    return response.json();
  }

  async refreshToken() {
    try {
      const refreshTok = this.getRefreshToken();
      if (!refreshTok) return false;
      const res = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshTok })
      });
      if (res.ok) {
        const data = await res.json();
        this.setTokens(data.access_token, data.refresh_token);
        return true;
      }
    } catch {
      // Refresh failed
    }
    this.clearTokens();
    return false;
  }

  // ==========================================
  // AUTHENTICATION APIS
  // ==========================================
  async login(email, password) {
    const res = await this.request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    });
    this.setTokens(res.access_token, res.refresh_token);
    this.setUser(res.user);
    return res;
  }

  async register(data) {
    const res = await this.request("/auth/register", {
      method: "POST",
      body: JSON.stringify(data)
    });
    this.setTokens(res.access_token, res.refresh_token);
    this.setUser(res.user);
    return res;
  }

  logout() {
    this.clearTokens();
  }

  async getMe() {
    return this.request("/auth/me");
  }

  // ==========================================
  // RESUME APIS
  // ==========================================
  async uploadResume(file) {
    const formData = new FormData();
    formData.append("file", file);
    return this.request("/resumes/upload", {
      method: "POST",
      body: formData
    });
  }

  async listResumes() {
    return this.request("/resumes");
  }

  async getResume(id) {
    return this.request(`/resumes/${id}`);
  }

  async analyzeResume(id) {
    return this.request(`/resumes/${id}/analyze`, { method: "POST" });
  }

  async deleteResume(id) {
    return this.request(`/resumes/${id}`, { method: "DELETE" });
  }

  // ==========================================
  // JOBS APIS
  // ==========================================
  async listJobs(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/jobs${query ? `?${query}` : ""}`);
  }

  async getJob(id) {
    return this.request(`/jobs/${id}`);
  }

  async createJob(jobData) {
    return this.request("/jobs", {
      method: "POST",
      body: JSON.stringify(jobData)
    });
  }

  async updateJob(id, jobData) {
    return this.request(`/jobs/${id}`, {
      method: "PUT",
      body: JSON.stringify(jobData)
    });
  }

  async closeJob(id) {
    return this.request(`/jobs/${id}`, { method: "DELETE" });
  }

  async applyToJob(jobId, applicationData = {}) {
    return this.request(`/jobs/${jobId}/apply`, {
      method: "POST",
      body: JSON.stringify(applicationData)
    });
  }

  async getJobApplicants(jobId) {
    return this.request(`/jobs/${jobId}/applicants`);
  }

  async updateApplicantStage(jobId, appId, data) {
    return this.request(`/jobs/${jobId}/applicants/${appId}`, {
      method: "PUT",
      body: JSON.stringify(data)
    });
  }

  // ==========================================
  // AI MATCHING APIS
  // ==========================================
  async predictMatch(payload) {
    return this.request("/matching/predict", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }

  async getMatchHistory() {
    return this.request("/matching/history");
  }

  async getMatchExplanation(matchId) {
    return this.request(`/matching/${matchId}/explanation`);
  }

  // ==========================================
  // RECOMMENDATIONS APIS
  // ==========================================
  async getRecommendedJobs(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/recommendations/jobs${query ? `?${query}` : ""}`);
  }

  async getRecommendedCandidates(jobId, limit = 10) {
    return this.request(`/recommendations/candidates?job_id=${jobId}&limit=${limit}`);
  }

  // ==========================================
  // DASHBOARDS
  // ==========================================
  async getCandidateDashboard() {
    return this.request("/dashboard/candidate");
  }

  async getRecruiterDashboard() {
    return this.request("/dashboard/recruiter");
  }

  async getAdminDashboard() {
    return this.request("/dashboard/admin");
  }

  // ==========================================
  // FAIRNESS & SDG 10
  // ==========================================
  async runFairnessAudit(auditData = {}) {
    return this.request("/fairness/audit", {
      method: "POST",
      body: JSON.stringify(auditData)
    });
  }

  async getFairnessReports() {
    return this.request("/fairness/reports");
  }

  // ==========================================
  // SYSTEM HEALTH
  // ==========================================
  async checkHealth() {
    const url = `${this.baseUrl.replace("/api/v1", "")}/health`;
    const res = await fetch(url);
    return res.json();
  }
}

export const api = new ApiClient(API_BASE_URL);
if (typeof window !== "undefined") {
  window.api = api;
}
