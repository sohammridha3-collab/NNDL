/*
 * Public runtime configuration (NOT secret).
 *
 * This classic script is loaded before the ES modules on every page and lets you
 * point the same static build at a different backend without editing source code.
 * Never put credentials, API keys or server secrets here — this file is public.
 *
 * Local development: leave the values below as-is (backend on http://127.0.0.1:8001).
 * Production (e.g. Render static site): overwrite this file during the build, e.g.
 *   echo "window.APP_CONFIG={API_ORIGIN:'https://YOUR-BACKEND.onrender.com'};" > env.js
 */
window.APP_CONFIG = window.APP_CONFIG || {
  API_ORIGIN: "http://127.0.0.1:8001"
};

