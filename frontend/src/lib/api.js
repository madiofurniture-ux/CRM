import axios from "axios";

// If REACT_APP_BACKEND_URL is unset the old code produced the literal string
// "undefined/api" and every request failed. Fall back to same-origin "/api",
// which is what a reverse-proxied / single-domain deployment wants anyway.
const BASE = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
export const API = BASE ? `${BASE}/api` : "/api";

const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("crm_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── GET cache (stale-while-revalidate) ──────────────────────────────────
// Every page fetches its data fresh on mount, so switching tabs and coming
// back always paid a full network round trip. A revisit within TTL is
// served from cache with nothing else happening. A revisit after TTL is
// STILL served from cache instantly — no visible reload — while a real
// request quietly refreshes that entry in the background for next time.
// So a page is never more than one visit behind, but a visit is never
// blocked waiting on the network. Any write clears the cache outright so
// an edit is never shown stale.
const CACHE_TTL_MS = 20_000;
const _cache = new Map(); // url -> { response, expiry }

const rawGet = api.get.bind(api);
api.get = (url, config) => {
  if (config?.skipCache) return rawGet(url, config);
  const cached = _cache.get(url);
  if (cached) {
    if (Date.now() >= cached.expiry) {
      rawGet(url, config)
        .then((response) => _cache.set(url, { response, expiry: Date.now() + CACHE_TTL_MS }))
        .catch(() => {}); // stale data is still shown; a failed refresh just tries again next visit
    }
    return Promise.resolve({ ...cached.response, data: structuredClone(cached.response.data) });
  }
  return rawGet(url, config).then((response) => {
    _cache.set(url, { response, expiry: Date.now() + CACHE_TTL_MS });
    return response;
  });
};

for (const method of ["post", "put", "patch", "delete"]) {
  const raw = api[method].bind(api);
  api[method] = (url, ...args) =>
    raw(url, ...args).then((response) => {
      // Records are linked: saving a customer updates their projects and
      // leads, converting a quotation creates an order and a project. So a
      // write clears every cached read, not just its own resource's.
      _cache.clear();
      return response;
    });
}

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("crm_token");
      localStorage.removeItem("crm_user");
      // Public pages (a shared catalogue at /c/<token>) are opened by people
      // who never log in; a background 401 there must not bounce them.
      if (window.location.pathname !== "/login" && !window.location.pathname.startsWith("/c/")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export function formatApiError(detail) {
  if (detail == null) return "Something went wrong.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e?.msg ? e.msg : JSON.stringify(e))).join(" ");
  if (detail?.msg) return detail.msg;
  // Structured 400/409s ({message, code, ...}) from the workflow gates and
  // other validators — used to render as "[object Object]".
  if (detail?.message) return detail.message;
  return String(detail);
}

export default api;
