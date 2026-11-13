/**
 * UI toolkit: safe DOM construction, icons, toasts, dialogs, async states and formatters.
 * All untrusted text (resumes, job descriptions, API messages) is inserted with textContent.
 */
import { ApiError } from "./api.js";

/* ---------------------------------------------------------------- DOM */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key === "style" && typeof value === "object") Object.assign(el.style, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key in el && typeof value !== "string" && key !== "list") el[key] = value;
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  append(el, children);
  return el;
}

export function append(parent, children) {
  for (const child of [children].flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    parent.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function mount(el, ...children) {
  clear(el);
  append(el, children);
  return el;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/* ---------------------------------------------------------------- Icons (inline SVG, stroke-based) */
const ICONS = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  file: "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5",
  briefcase: "M3 8h18v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM8 8V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v3M3 13h18",
  sparkles: "M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4",
  scale: "M12 3v18M5 7h14M5 7l-3 7a4 4 0 0 0 6 0zM19 7l-3 7a4 4 0 0 0 6 0zM8 21h8",
  gauge: "M12 15l3-5M4.9 19a9 9 0 1 1 14.2 0",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  menu: "M3 6h18M3 12h18M3 18h18",
  x: "M18 6 6 18M6 6l12 12",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
  chevronDown: "M6 9l6 6 6-6",
  chevronRight: "M9 18l6-6-6-6",
  chevronLeft: "M15 18l-6-6 6-6",
  check: "M20 6 9 17l-5-5",
  alert: "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01",
  trash: "M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6",
  eye: "M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  eyeOff: "M17.9 17.9A10.1 10.1 0 0 1 12 20C5 20 1 12 1 12a18.5 18.5 0 0 1 5.1-5.9M9.9 4.2A9.1 9.1 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.2 3.2M14.1 14.1a3 3 0 1 1-4.2-4.2M1 1l22 22",
  bookmark: "M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z",
  plus: "M12 5v14M5 12h14",
  edit: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
  refresh: "M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  user: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  mapPin: "M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 1 1 18 0zM12 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  building: "M4 21V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v17M16 9h3a1 1 0 0 1 1 1v11M2 21h20M8 7h4M8 11h4M8 15h4",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2",
  layers: "M12 2 2 7l10 5 10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  server: "M2 3h20v8H2zM2 13h20v8H2zM6 7h.01M6 17h.01",
  external: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3",
  columns: "M12 3v18M3 3h18v18H3z",
  star: "M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"
};

export function icon(name, { size = 18, label = null, className = "" } = {}) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("class", `icon ${className}`.trim());
  if (label) {
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
  } else {
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
  }
  const path = document.createElementNS(NS, "path");
  path.setAttribute("d", ICONS[name] || ICONS.info);
  svg.appendChild(path);
  return svg;
}

/* ---------------------------------------------------------------- Live regions & toasts */
function ensureRegion(id, politeness) {
  let region = document.getElementById(id);
  if (!region) {
    region = h("div", { id, class: id === "toast-region" ? "toast-region" : "sr-only", "aria-live": politeness, "aria-atomic": "false" });
    document.body.appendChild(region);
  }
  return region;
}

export function announce(message, politeness = "polite") {
  const region = ensureRegion(politeness === "assertive" ? "sr-assertive" : "sr-polite", politeness);
  region.textContent = "";
  setTimeout(() => {
    region.textContent = message;
  }, 50);
}

const TOAST_ICON = { success: "check", error: "alert", warning: "alert", info: "info" };

export function toast(message, { type = "info", timeout = type === "error" ? 8000 : 4500, title = null } = {}) {
  const region = ensureRegion("toast-region", "polite");
  const node = h(
    "div",
    { class: `toast toast--${type}`, role: type === "error" ? "alert" : "status" },
    h("span", { class: "toast__icon" }, icon(TOAST_ICON[type] || "info")),
    h("div", { class: "toast__body" }, title ? h("strong", { class: "toast__title", text: title }) : null, h("span", { text: message })),
    h("button", { class: "icon-btn toast__close", type: "button", "aria-label": "Dismiss notification", onclick: () => dismiss() }, icon("x", { size: 16 }))
  );
  let timer = null;
  const dismiss = () => {
    clearTimeout(timer);
    node.classList.add("toast--leaving");
    setTimeout(() => node.remove(), 200);
  };
  region.appendChild(node);
  if (timeout) timer = setTimeout(dismiss, timeout);
  node.addEventListener("mouseenter", () => clearTimeout(timer));
  node.addEventListener("mouseleave", () => {
    if (timeout) timer = setTimeout(dismiss, 2500);
  });
  return dismiss;
}

/* ---------------------------------------------------------------- Errors */
export function errorMessage(err, fallback = "Something went wrong.") {
  if (!err) return fallback;
  if (err instanceof ApiError) {
    if (err.kind === "server" && err.message.startsWith("An internal server error")) {
      return "The server could not complete this request. If this keeps happening, the model service or database may be unavailable.";
    }
    return err.message || fallback;
  }
  return err.message || fallback;
}

/** Map API field errors onto inputs with aria-invalid + described error text. */
export function showFieldErrors(form, fieldErrors = {}, fieldMap = {}) {
  clearFieldErrors(form);
  let firstInvalid = null;
  for (const [field, msg] of Object.entries(fieldErrors)) {
    const name = fieldMap[field] || field;
    const input = form.querySelector(`[name="${CSS.escape(name)}"]`);
    if (input) {
      setFieldError(input, msg);
      if (!firstInvalid) firstInvalid = input;
    }
  }
  if (firstInvalid) firstInvalid.focus();
  return Boolean(firstInvalid);
}

export function setFieldError(input, msg) {
  const field = input.closest(".field") || input.parentElement;
  let err = field.querySelector(".field__error");
  if (!err) {
    err = h("p", { class: "field__error", id: `${input.id || input.name}-error` });
    field.appendChild(err);
  }
  err.replaceChildren(icon("alert", { size: 14 }), document.createTextNode(` ${msg}`));
  input.setAttribute("aria-invalid", "true");
  const describedBy = new Set((input.getAttribute("aria-describedby") || "").split(" ").filter(Boolean));
  describedBy.add(err.id);
  input.setAttribute("aria-describedby", Array.from(describedBy).join(" "));
}

export function clearFieldErrors(form) {
  $$(".field__error", form).forEach((e) => {
    const input = form.querySelector(`[aria-describedby~="${e.id}"]`);
    if (input) {
      input.removeAttribute("aria-invalid");
      const rest = (input.getAttribute("aria-describedby") || "").split(" ").filter((x) => x && x !== e.id);
      if (rest.length) input.setAttribute("aria-describedby", rest.join(" "));
      else input.removeAttribute("aria-describedby");
    }
    e.remove();
  });
}

/* ---------------------------------------------------------------- Async states */
export function loadingState(label = "Loading…") {
  return h("div", { class: "state state--loading", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }), h("span", { text: label }));
}

export function skeleton(lines = 3) {
  return h(
    "div",
    { class: "skeleton-group", "aria-hidden": "true" },
    Array.from({ length: lines }, (_, i) => h("div", { class: "skeleton", style: { width: `${90 - i * 12}%` } }))
  );
}

export function emptyState(opts = {}) {
  const { title, message, action = null, iconName = "layers" } =
    typeof opts === "string" ? { title: opts, message: "" } : (opts || {});
  return h(
    "div",
    { class: "state state--empty" },
    h("span", { class: "state__icon" }, icon(iconName, { size: 28 })),
    h("h3", { class: "state__title", text: title || "No items found" }),
    message ? h("p", { class: "state__text", text: message }) : null,
    action
  );
}

export function errorState(err, { onRetry = null, title = null } = {}) {
  const kind = err && err.kind;
  const heading =
    title ||
    (kind === "network"
      ? "Backend unavailable"
      : kind === "forbidden"
        ? "Access restricted"
        : kind === "timeout"
          ? "Request timed out"
          : kind === "not_found"
            ? "Not found"
            : "Could not load this section");
  return h(
    "div",
    { class: "state state--error", role: "alert" },
    h("span", { class: "state__icon" }, icon("alert", { size: 28 })),
    h("h3", { class: "state__title", text: heading }),
    h("p", { class: "state__text", text: errorMessage(err) }),
    onRetry ? h("button", { class: "btn btn--secondary", type: "button", onclick: onRetry }, icon("refresh", { size: 16 }), " Try again") : null
  );
}

export function notice(type, title, message, extra = null) {
  return h(
    "div",
    { class: `notice notice--${type}`, role: type === "error" ? "alert" : "note" },
    h("span", { class: "notice__icon" }, icon(type === "success" ? "check" : type === "info" || type === "ai" ? "info" : "alert")),
    h("div", {}, title ? h("strong", { class: "notice__title", text: title }) : null, message ? h("p", { text: message }) : null, extra)
  );
}

/* ---------------------------------------------------------------- Buttons */
export function setBusy(button, busy, busyLabel = "Working…") {
  if (!button) return;
  if (busy) {
    if (!button.dataset.idleHtml) button.dataset.idleLabel = button.textContent.trim();
    button._idleChildren = Array.from(button.childNodes).map((n) => n.cloneNode(true));
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.replaceChildren(h("span", { class: "spinner spinner--sm", "aria-hidden": "true" }), document.createTextNode(` ${busyLabel}`));
  } else {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    if (button._idleChildren) button.replaceChildren(...button._idleChildren);
  }
}

/* ---------------------------------------------------------------- Dialogs */
let dialogSeq = 0;
export function openDialog({ title, description = null, body = null, content = null, actions = [], size = "md", onClose = null, dismissible = true }) {
  const dialogBody = body || content;
  const opener = document.activeElement;
  const id = `dlg-${++dialogSeq}`;
  const dialog = h("dialog", { class: `dialog dialog--${size}`, "aria-labelledby": `${id}-title`, "aria-describedby": description ? `${id}-desc` : null });
  const close = (result) => {
    if (!dialog.open) return;
    dialog.close();
    dialog.remove();
    document.body.classList.remove("no-scroll-dialog");
    if (opener && typeof opener.focus === "function" && document.contains(opener)) opener.focus();
    if (onClose) onClose(result);
  };
  const header = h(
    "header",
    { class: "dialog__header" },
    h("div", {}, h("h2", { class: "dialog__title", id: `${id}-title`, text: title }), description ? h("p", { class: "dialog__desc", id: `${id}-desc`, text: description }) : null),
    dismissible ? h("button", { class: "icon-btn", type: "button", "aria-label": "Close dialog", onclick: () => close(null) }, icon("x")) : null
  );
  const footer = actions.length
    ? h(
        "footer",
        { class: "dialog__footer" },
        actions.map((a) =>
          h("button", { class: `btn btn--${a.variant || "secondary"}`, type: a.type || "button", form: a.form || null, onclick: a.onClick ? (e) => a.onClick(e, close) : () => close(a.value ?? null) }, a.label)
        )
      )
    : null;
  append(dialog, [header, h("div", { class: "dialog__body" }, dialogBody), footer]);
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    if (dismissible) close(null);
  });
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog && dismissible) close(null);
  });
  document.body.appendChild(dialog);
  document.body.classList.add("no-scroll-dialog");
  dialog.showModal();
  const focusTarget = dialog.querySelector("[autofocus]") || dialog.querySelector(".dialog__body input, .dialog__body select, .dialog__body textarea, .dialog__body button") || dialog.querySelector(".dialog__footer .btn");
  if (focusTarget) focusTarget.focus();
  return { dialog, close };
}

export function confirmDialog({ title, message, confirmLabel = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    openDialog({
      title,
      size: "sm",
      body: h("p", { text: message }),
      actions: [
        { label: "Cancel", variant: "secondary", value: false },
        { label: confirmLabel, variant: danger ? "danger" : "primary", value: true }
      ],
      onClose: (result) => resolve(result === true)
    });
  });
}

/* ---------------------------------------------------------------- Formatting */
function toDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  let s = String(value);
  // Backend stores UTC timestamps; SQLite returns them without an offset.
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s)) s += "Z";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtDate(value, { time = false } = {}) {
  const d = toDate(value);
  if (!d) return "—";
  return d.toLocaleString(undefined, time ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" });
}

export function fmtRelative(value) {
  const d = toDate(value);
  if (!d) return "—";
  const diff = (Date.now() - d.getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const table = [
    [60, "second", 1],
    [3600, "minute", 60],
    [86400, "hour", 3600],
    [604800, "day", 86400],
    [2629800, "week", 604800],
    [31557600, "month", 2629800],
    [Infinity, "year", 31557600]
  ];
  for (const [limit, unit, div] of table) {
    if (Math.abs(diff) < limit) return rtf.format(-Math.round(diff / div), unit);
  }
  return fmtDate(d);
}

export function isNum(v) {
  return typeof v === "number" && Number.isFinite(v);
}

/** Value already on a 0–100 scale. Preserves legitimate zero. */
export function fmtPct100(v, digits = 1) {
  return isNum(v) ? `${v.toFixed(digits)}%` : "—";
}

/** Value on a 0–1 scale rendered as a percentage. */
export function fmtRatioPct(v, digits = 1) {
  return isNum(v) ? `${(v * 100).toFixed(digits)}%` : "—";
}

export function fmtNumber(v, digits = 0) {
  return isNum(v) ? v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits }) : "—";
}

export function fmtBytes(bytes) {
  if (!isNum(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function fmtSalary(min, max, currency = "USD") {
  const f = (n) => {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "USD", maximumFractionDigits: 0 }).format(n);
    } catch {
      return `${currency} ${Math.round(n).toLocaleString()}`;
    }
  };
  if (isNum(min) && isNum(max)) return `${f(min)} – ${f(max)}`;
  if (isNum(min)) return `From ${f(min)}`;
  if (isNum(max)) return `Up to ${f(max)}`;
  return null;
}

export function titleCase(s) {
  return String(s || "")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ---------------------------------------------------------------- Badges */
const STATUS_TONE = {
  applied: "neutral",
  under_review: "info",
  shortlisted: "accent",
  interviewed: "ai",
  offered: "success",
  rejected: "danger",
  active: "success",
  closed: "neutral",
  candidate: "info",
  recruiter: "accent",
  admin: "ai"
};

export function badge(text, tone = null) {
  const key = String(text || "").toLowerCase();
  return h("span", { class: `badge badge--${tone || STATUS_TONE[key] || "neutral"}`, text: titleCase(text) });
}

export function classificationBadge(cls) {
  const strong = /strong/i.test(cls || "");
  return h("span", { class: `badge badge--${strong ? "success" : "warning"}` }, icon(strong ? "check" : "info", { size: 13 }), ` ${cls || "—"}`);
}

export function chip(text, tone = "neutral") {
  return h("span", { class: `chip chip--${tone}`, text });
}

/* ---------------------------------------------------------------- Misc */
export function debounce(fn, wait = 300) {
  let t = null;
  const wrapped = (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
  wrapped.cancel = () => clearTimeout(t);
  return wrapped;
}

export function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

export function setQuery(params, { replace = false } = {}) {
  const url = new URL(window.location.href);
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") url.searchParams.delete(k);
    else url.searchParams.set(k, v);
  }
  const method = replace ? "replaceState" : "pushState";
  if (url.href !== window.location.href) window.history[method]({}, "", url);
}

/** Accessible horizontal bar list (with numeric values in text). */
export function barList(items, { max = null, valueFormat = (v) => fmtNumber(v), label = "Chart" } = {}) {
  const top = max ?? Math.max(1, ...items.map((i) => i.value || 0));
  return h(
    "ul",
    { class: "bar-list", "aria-label": label },
    items.map((item) =>
      h(
        "li",
        { class: "bar-list__item" },
        h("span", { class: "bar-list__label", text: item.label }),
        h("span", { class: "bar-list__track", "aria-hidden": "true" }, h("span", { class: `bar-list__fill bar-list__fill--${item.tone || "accent"}`, style: { width: `${Math.max(0, Math.min(100, ((item.value || 0) / top) * 100))}%` } })),
        h("span", { class: "bar-list__value", text: valueFormat(item.value) })
      )
    )
  );
}

export function downloadCsv(filename, rows) {
  const escapeCell = (v) => {
    const s = v === null || v === undefined ? "" : String(v);
    // Neutralize spreadsheet formula injection.
    const safe = /^[=+\-@\t\r]/.test(s) ? `'${s}` : s;
    return /[",\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
  };
  const csv = rows.map((r) => r.map(escapeCell).join(",")).join("\r\n");
  const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = h("a", { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

