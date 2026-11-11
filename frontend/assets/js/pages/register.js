/**
 * Registration Page Controller
 */
import { Api } from "../api.js";
import { CONFIG } from "../config.js";
import { session } from "../session.js";
import { redirectIfSignedIn, setupPasswordToggle } from "../auth.js";
import { initTheme } from "../app.js";
import { $, setBusy, clearFieldErrors, showFieldErrors, toast, errorMessage } from "../ui.js";

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  redirectIfSignedIn();
  setupPasswordToggle();

  const form = $("#register-form");
  const submitBtn = $("#register-submit");
  const roleSelect = $("#role-select");
  const companyField = $("#company-field");

  // Toggle company name field when recruiter is selected
  if (roleSelect && companyField) {
    roleSelect.addEventListener("change", () => {
      const isRecruiter = roleSelect.value === "recruiter";
      companyField.style.display = isRecruiter ? "flex" : "none";
      const companyInput = companyField.querySelector("input");
      if (companyInput) companyInput.required = isRecruiter;
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(form);

    const full_name = form.full_name.value.trim();
    const email = form.email.value.trim();
    const password = form.password.value;
    const role = form.role.value;
    const company_name = role === "recruiter" ? (form.company_name ? form.company_name.value.trim() : "") : null;

    if (!full_name || !email || !password) {
      toast("Please fill in all required fields.", { type: "error" });
      return;
    }

    if (password.length < 6) {
      toast("Password must be at least 6 characters.", { type: "error" });
      return;
    }

    setBusy(submitBtn, true, "Creating Account…");

    try {
      const tokenData = await Api.auth.register({
        email,
        password,
        full_name,
        role,
        company_name: company_name || undefined
      });

      // Save tokens and user
      session.save(tokenData, false);

      toast("Account registered successfully! Redirecting…", { type: "success" });

      const dest = CONFIG.ROLE_HOME[role] || "dashboard.html";
      setTimeout(() => window.location.replace(dest), 400);
    } catch (err) {
      setBusy(submitBtn, false);
      if (err.fieldErrors && Object.keys(err.fieldErrors).length) {
        showFieldErrors(form, err.fieldErrors);
      } else {
        toast(errorMessage(err, "Failed to create account."), { type: "error" });
      }
    }
  });
});

