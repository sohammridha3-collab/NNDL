/**
 * Token storage.
 * The backend issues bearer access + refresh tokens in the JSON body (no HttpOnly cookie
 * support exists), so tokens must live in Web Storage. By default they are kept in
 * sessionStorage (cleared when the tab closes). "Keep me signed in" switches to localStorage.
 * Tokens and personal data are never written to the console.
 */
const KEYS = { access: "ijm.access", refresh: "ijm.refresh", user: "ijm.user" };

function stores() {
  return [window.sessionStorage, window.localStorage];
}

function activeStore() {
  return window.localStorage.getItem(KEYS.refresh) ? window.localStorage : window.sessionStorage;
}

export const session = {
  getAccessToken() {
    return activeStore().getItem(KEYS.access);
  },
  getRefreshToken() {
    return activeStore().getItem(KEYS.refresh);
  },
  getCachedUser() {
    try {
      const raw = activeStore().getItem(KEYS.user);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },
  save({ access_token, refresh_token, user }, persist) {
    const target = persist === undefined ? activeStore() : (persist ? window.localStorage : window.sessionStorage);
    if (persist !== undefined) this.clear();
    if (access_token) target.setItem(KEYS.access, access_token);
    if (refresh_token) target.setItem(KEYS.refresh, refresh_token);
    if (user) target.setItem(KEYS.user, JSON.stringify(user));
  },
  setUser(user) {
    activeStore().setItem(KEYS.user, JSON.stringify(user));
  },
  clear() {
    for (const s of stores()) {
      Object.values(KEYS).forEach((k) => s.removeItem(k));
    }
  },
  isSignedIn() {
    return Boolean(this.getAccessToken() || this.getRefreshToken());
  }
};

