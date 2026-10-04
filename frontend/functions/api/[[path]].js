// Cloudflare Pages Function: forward /api/* to the FastAPI backend on Render,
// the same job netlify.toml's /api/* redirect did. The browser stays on one
// origin, so the app works without REACT_APP_BACKEND_URL or CORS setup.
const BACKEND = "https://madio-crm-api.onrender.com";

export async function onRequest({ request }) {
  const url = new URL(request.url);
  const target = BACKEND + url.pathname + url.search;
  const init = {
    method: request.method,
    headers: request.headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    redirect: "manual",
  };
  return fetch(target, init);
}
