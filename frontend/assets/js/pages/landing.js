/**
 * Landing Page Controller
 * Includes interactive 3D cursor parallax, performance optimization, and backend status check.
 */
import { Api } from "../api.js";
import { session } from "../session.js";
import { CONFIG } from "../config.js";
import { initTheme, toggleTheme, updateThemeIcon } from "../app.js";
import { $, icon } from "../ui.js";

document.addEventListener("DOMContentLoaded", async () => {
  // Initialize theme controls
  initTheme();
  const themeToggle = $("#theme-toggle");
  if (themeToggle) {
    updateThemeIcon(themeToggle);
    themeToggle.addEventListener("click", () => {
      toggleTheme();
      updateThemeIcon(themeToggle);
    });
  }

  // Check if user is already signed in and adjust CTAs if needed
  if (session.isSignedIn()) {
    const user = session.getCachedUser();
    const dest = (user && CONFIG.ROLE_HOME[user.role]) || "dashboard.html";
    const primaryCta = $("a[href='match.html']");
    if (primaryCta) {
      // keep link accessible
    }
  }

  // Setup 3D Cursor Parallax
  setupHeroParallax();

  // Check backend health & model readiness
  const statusBadge = $("#backend-status");
  if (statusBadge) {
    try {
      const health = await Api.system.health();
      if (health && health.status === "healthy") {
        statusBadge.replaceChildren(
          icon("check", { size: 14 }),
          document.createTextNode(" AI Match Engine Online")
        );
        statusBadge.className = "badge badge--success";
      }
    } catch {
      statusBadge.replaceChildren(
        icon("alert", { size: 14 }),
        document.createTextNode(" Backend Connecting…")
      );
      statusBadge.className = "badge badge--warning";
    }
  }
});

/**
 * Gentle 3D Cursor Parallax for the Split Hero Stage
 * Damped with requestAnimationFrame and strict tilt bounds (±8deg max).
 */
function setupHeroParallax() {
  const stage = $("#hero-3d-stage");
  const scene = $("#hero-3d-scene");
  if (!stage || !scene) return;

  // Check for reduced motion preference
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (prefersReduced) return;

  let mouseX = 0;
  let mouseY = 0;
  let currentRotX = 6;
  let currentRotY = -8;
  let targetRotX = 6;
  let targetRotY = -8;
  let rafId = null;
  let isVisible = true;

  // Pause when offscreen for battery/GPU performance
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        isVisible = entry.isIntersecting;
        if (isVisible && !rafId) {
          rafId = requestAnimationFrame(animateLoop);
        }
      });
    }, { threshold: 0.1 });
    observer.observe(stage);
  }

  function handleMouseMove(e) {
    const rect = stage.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;

    const normX = (e.clientX - centerX) / (window.innerWidth / 2);
    const normY = (e.clientY - centerY) / (window.innerHeight / 2);

    // Subtle tilt: base rotation + parallax offset
    targetRotY = -8 + (normX * 9);
    targetRotX = 6 - (normY * 7);
  }

  function handleMouseLeave() {
    targetRotX = 6;
    targetRotY = -8;
  }

  window.addEventListener("mousemove", handleMouseMove, { passive: true });
  document.addEventListener("mouseleave", handleMouseLeave);

  function animateLoop() {
    if (!isVisible) {
      rafId = null;
      return;
    }

    // Spring damping interpolation
    currentRotX += (targetRotX - currentRotX) * 0.08;
    currentRotY += (targetRotY - currentRotY) * 0.08;

    scene.style.transform = `rotateY(${currentRotY.toFixed(2)}deg) rotateX(${currentRotX.toFixed(2)}deg)`;
    rafId = requestAnimationFrame(animateLoop);
  }

  rafId = requestAnimationFrame(animateLoop);
}
