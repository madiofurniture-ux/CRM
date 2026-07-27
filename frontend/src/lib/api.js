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
