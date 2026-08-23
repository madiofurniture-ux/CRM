import axios from "axios";

// If REACT_APP_BACKEND_URL is unset the old code produced the literal string
// "undefined/api" and every request failed. Fall back to same-origin "/api",
// which is what a reverse-proxied / single-domain deployment wants anyway.
const BASE = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
export const API = BASE ? `${BASE}/api` : "/api";

const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("madio_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── GET cache ────────────────────────────────────────────────────────────
// Every page fetches its data fresh on mount, so switching tabs and coming
// back always paid a full network round trip. Short-lived in-memory cache
// makes revisits instant; a write to a resource clears that resource's
// entries so the next read after an edit is never stale.
const CACHE_TTL_MS = 20_000;
const _cache = new Map(); // url -> { response, expiry }

function resourceOf(url) {
  const path = url.split("?")[0];
  const segment = path.split("/").filter(Boolean)[0] || "";
  return "/" + segment;
}

function invalidateResource(url) {
  const resource = resourceOf(url);
  for (const key of _cache.keys()) {
    if (resourceOf(key) === resource) _cache.delete(key);
  }
}

const rawGet = api.get.bind(api);
api.get = (url, config) => {
  if (config?.skipCache) return rawGet(url, config);
  const cached = _cache.get(url);
  if (cached && Date.now() < cached.expiry) {
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
      invalidateResource(url);
      return response;
    });
}

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("madio_token");
      localStorage.removeItem("madio_user");
      if (window.location.pathname !== "/login") {
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
  return String(detail);
}

export default api;
