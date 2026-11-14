/*
 * Public runtime configuration (NOT secret).
 *
 * This script is loaded synchronously before ES modules on every page.
 * It dynamically sets window.APP_CONFIG.API_ORIGIN:
 *   - Local development (localhost, 127.0.0.1, or local file): targets http://127.0.0.1:8001
 *   - Deployed frontend (e.g. Render static site): targets https://inclusive-ats-backend.onrender.com
 *   - Honors explicit window.APP_CONFIG.API_ORIGIN overrides (e.g. build scripts).
 */
(function () {
  var isLocal = false;
  try {
    var host = window.location.hostname;
    isLocal = !host || host === "localhost" || host === "127.0.0.1" || host === "::1" || window.location.protocol === "file:";
  } catch (e) {
    isLocal = true;
  }

  var PROD_BACKEND_ORIGIN = "https://inclusive-ats-backend.onrender.com";
  var LOCAL_BACKEND_ORIGIN = "http://127.0.0.1:8001";

  window.APP_CONFIG = window.APP_CONFIG || {};
  if (!window.APP_CONFIG.API_ORIGIN) {
    window.APP_CONFIG.API_ORIGIN = isLocal ? LOCAL_BACKEND_ORIGIN : PROD_BACKEND_ORIGIN;
  }
})();
