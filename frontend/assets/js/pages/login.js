/**
 * Login Page Controller
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

  const form = $("#login-form");
  const submitBtn = $("#login-submit");

  // Check for expired session query param
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("expired")) {
    toast("Your session has expired. Please sign in again.", { type: "info" });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(form);

    const email = form.email.value.trim();
    const password = form.password.value;
    const rememberMe = form.remember ? form.remember.checked : false;

    if (!email || !password) {
      toast("Please enter both email and password.", { type: "error" });
      return;
    }

    setBusy(submitBtn, true, "Signing in…");

    try {
      const tokenData = await Api.auth.login(email, password);
      // Save tokens and user
      session.save(tokenData, rememberMe);

      toast("Signed in successfully!", { type: "success" });

      // Determine redirect destination
      const redirectParam = urlParams.get("redirect");
      let dest = "";
      if (redirectParam && !redirectParam.startsWith("http") && !redirectParam.includes("//")) {
        dest = decodeURIComponent(redirectParam);
      } else {
        const user = tokenData.user;
        dest = (user && CONFIG.ROLE_HOME[user.role]) || "dashboard.html";
      }

      setTimeout(() => window.location.replace(dest), 300);
    } catch (err) {
      setBusy(submitBtn, false);
      if (err.fieldErrors && Object.keys(err.fieldErrors).length) {
        showFieldErrors(form, err.fieldErrors);
      } else {
        toast(errorMessage(err, "Incorrect email or password."), { type: "error" });
      }
    }
  });
});

