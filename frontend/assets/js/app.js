/**
 * Application Shell Coordinator
 * Manages responsive sidebar (including desktop collapse toggle and mobile drawer),
 * role-based navigation, midnight theme defaults, and topbar user info.
 */
import { logout } from "./auth.js";
import { session } from "./session.js";
import { setAuthExpiredHandler } from "./api.js";
import { h, icon, $, $$ } from "./ui.js";

// Role-based navigation structure
const NAV_ITEMS = {
  candidate: [
    { label: "Overview", icon: "home", href: "dashboard.html" },
    { label: "My Resumes", icon: "file", href: "resumes.html" },
    { label: "Browse Jobs", icon: "briefcase", href: "jobs.html" },
    { label: "AI Matching", icon: "sparkles", href: "match.html" },
    { label: "Applications", icon: "list", href: "applications.html" },
    { label: "SDG 10 Fairness", icon: "scale", href: "fairness.html" }
  ],
  recruiter: [
    { label: "Recruiter Hub", icon: "gauge", href: "recruiter.html" },
    { label: "Job Openings", icon: "briefcase", href: "jobs.html" },
    { label: "Candidate Matcher", icon: "sparkles", href: "match.html" },
    { label: "SDG 10 Fairness", icon: "scale", href: "fairness.html" }
  ],
  admin: [
    { label: "System Health", icon: "server", href: "admin.html" },
    { label: "User Management", icon: "users", href: "admin.html#users" },
    { label: "Browse Jobs", icon: "briefcase", href: "jobs.html" },
    { label: "SDG 10 Fairness", icon: "scale", href: "fairness.html" }
  ]
};

export function initAppShell({ user = null, activePage = "", breadcrumbs = [] } = {}) {
  // Listen for session expiration
  setAuthExpiredHandler(() => {
    window.location.replace("login.html?expired=1");
  });

  // Initialize theme (defaults to dark midnight navy)
  initTheme();

  // Render navigation if app shell elements exist
  const sidebarNav = $("#sidebar-nav");
  if (sidebarNav) {
    renderSidebarNav(sidebarNav, user, activePage);
  }

  // Setup sidebar collapse toggle (desktop) and mobile drawer
  setupSidebarInteractions();

  // Setup topbar controls (theme, logout, user profile)
  setupTopbar(user);

  // Render breadcrumbs if container exists
  const bcContainer = $("#breadcrumbs");
  if (bcContainer && breadcrumbs.length > 0) {
    renderBreadcrumbs(bcContainer, breadcrumbs);
  }
}

function renderSidebarNav(container, user, activePage) {
  const role = user ? user.role : "candidate";
  const items = NAV_ITEMS[role] || NAV_ITEMS.candidate;

  container.replaceChildren();

  // Navigation Links
  items.forEach((item) => {
    const isActive = activePage === item.href || window.location.pathname.endsWith(item.href);
    const link = h(
      "a",
      {
        href: item.href,
        class: `sidebar__link ${isActive ? "sidebar__link--active" : ""}`,
        "aria-current": isActive ? "page" : null,
        title: item.label
      },
      icon(item.icon, { size: 18 }),
      h("span", { text: item.label })
    );
    container.appendChild(link);
  });
}

function setupSidebarInteractions() {
  const sidebar = $("#sidebar");
  const appShell = $(".app-shell");
  const mobileToggle = $("#mobile-menu-toggle");
  const backdrop = $("#drawer-backdrop");

  if (!sidebar) return;

  // Restore collapsed state on desktop
  const isCollapsed = localStorage.getItem("ats_sidebar_collapsed") === "true";
  if (isCollapsed && window.innerWidth > 1024) {
    sidebar.classList.add("sidebar--collapsed");
    if (appShell) appShell.classList.add("app-shell--collapsed");
  }

  // Inject collapse button in sidebar header if not present
  const brand = $(".sidebar__brand");
  if (brand && !$("#sidebar-collapse-btn")) {
    const collapseBtn = h(
      "button",
      {
        id: "sidebar-collapse-btn",
        class: "sidebar__collapse-btn",
        type: "button",
        "aria-label": "Toggle sidebar size",
        title: "Toggle sidebar"
      },
      icon("menu", { size: 16 })
    );
    collapseBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const collapsed = sidebar.classList.toggle("sidebar--collapsed");
      if (appShell) appShell.classList.toggle("app-shell--collapsed", collapsed);
      localStorage.setItem("ats_sidebar_collapsed", collapsed);
    });
    brand.appendChild(collapseBtn);
  }

  // Mobile Drawer Toggle
  if (mobileToggle && backdrop) {
    function openDrawer() {
      sidebar.classList.add("sidebar--open");
      backdrop.classList.add("drawer-backdrop--open");
      document.body.classList.add("no-scroll-drawer");
      mobileToggle.setAttribute("aria-expanded", "true");
    }

    function closeDrawer() {
      sidebar.classList.remove("sidebar--open");
      backdrop.classList.remove("drawer-backdrop--open");
      document.body.classList.remove("no-scroll-drawer");
      mobileToggle.setAttribute("aria-expanded", "false");
    }

    mobileToggle.addEventListener("click", () => {
      const isOpen = sidebar.classList.contains("sidebar--open");
      if (isOpen) closeDrawer();
      else openDrawer();
    });

    backdrop.addEventListener("click", closeDrawer);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && sidebar.classList.contains("sidebar--open")) {
        closeDrawer();
        mobileToggle.focus();
      }
    });
  }
}

function setupTopbar(user) {
  // Theme toggle button
  const themeToggle = $("#theme-toggle");
  if (themeToggle) {
    updateThemeIcon(themeToggle);
    themeToggle.addEventListener("click", () => {
      toggleTheme();
      updateThemeIcon(themeToggle);
    });
  }

  // Logout button
  const logoutBtn = $("#logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      await logout();
    });
  }

  // User display in topbar
  const userDisplay = $("#topbar-user-name");
  if (userDisplay && user) {
    userDisplay.textContent = user.full_name || user.email;
    const avatar = $(".user-pill__avatar");
    if (avatar) {
      const initial = (user.full_name || user.email || "U").trim().charAt(0).toUpperCase();
      avatar.textContent = initial;
    }
  }
}

function renderBreadcrumbs(container, crumbs) {
  container.replaceChildren();
  const nav = h("nav", { class: "breadcrumbs", "aria-label": "Breadcrumb" });

  crumbs.forEach((crumb, idx) => {
    if (idx > 0) {
      nav.appendChild(h("span", { class: "breadcrumbs__sep", text: "/" }));
    }
    if (idx === crumbs.length - 1 || !crumb.href) {
      nav.appendChild(h("span", { class: "breadcrumbs__current", text: crumb.label, "aria-current": "page" }));
    } else {
      nav.appendChild(h("a", { href: crumb.href, text: crumb.label }));
    }
  });

  container.appendChild(nav);
}

/* ------------------------------------------------ Theme Management */
export function initTheme() {
  const saved = localStorage.getItem("ats_theme");
  // Default to dark Midnight Navy if unset
  const theme = saved || "dark";
  document.documentElement.setAttribute("data-theme", theme);
}

export function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("ats_theme", next);
}

export function updateThemeIcon(btn) {
  const isDark = document.documentElement.getAttribute("data-theme") === "dark";
  btn.setAttribute("aria-label", isDark ? "Switch to light theme" : "Switch to midnight navy theme");
  btn.replaceChildren(icon(isDark ? "sun" : "moon", { size: 18 }));
}
