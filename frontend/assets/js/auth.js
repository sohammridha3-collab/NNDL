/**
 * Authentication & Authorization Manager
 */
import { Api } from "./api.js";
import { CONFIG } from "./config.js";
import { session } from "./session.js";
import { toast, icon } from "./ui.js";

/**
 * Checks session and redirects to login if unauthenticated or forbidden.
 * Returns the verified user object.
 */
export async function requireAuth(allowedRoles = null) {
  if (!session.isSignedIn()) {
    const here = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.replace(`login.html?redirect=${here}`);
    return null;
  }

  let user = session.getCachedUser();
  try {
    // Refresh user profile from backend
    user = await Api.auth.me();
    session.setUser(user);
  } catch (err) {
    if (err.status === 401) {
      session.clear();
      const here = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.replace(`login.html?redirect=${here}`);
      return null;
    }
  }

  if (allowedRoles && user && !allowedRoles.includes(user.role)) {
    toast(`Access restricted. This area is reserved for ${allowedRoles.join(" or ")} accounts.`, { type: "error" });
    const fallback = CONFIG.ROLE_HOME[user.role] || "index.html";
    setTimeout(() => window.location.replace(fallback), 1200);
    return null;
  }

  return user;
}

/**
 * If already logged in, redirect user away from auth pages to their workspace.
 */
export function redirectIfSignedIn() {
  if (session.isSignedIn()) {
    const user = session.getCachedUser();
    const dest = (user && CONFIG.ROLE_HOME[user.role]) || "dashboard.html";
    window.location.replace(dest);
  }
}

/**
 * Log out user and clear state.
 */
export async function logout() {
  try {
    await Api.auth.logout();
  } catch {
    // Ignore network errors on logout
  } finally {
    session.clear();
    window.location.replace("login.html");
  }
}

/**
 * Sets up accessible password show/hide toggle on inputs.
 */
export function setupPasswordToggle(container = document) {
  const toggleButtons = container.querySelectorAll(".password-toggle");
  toggleButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = btn.parentElement.querySelector("input");
      if (!input) return;
      const isPassword = input.type === "password";
      input.type = isPassword ? "text" : "password";
      btn.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
      btn.replaceChildren(icon(isPassword ? "eyeOff" : "eye", { size: 18 }));
    });
  });
}

