// Site-wide access gate for MADIO CRM (Netlify Edge Function).
//
// Enforces HTTP Basic Auth in front of every request BEFORE the page is served,
// so the app cannot be reached by hitting the file URL directly — unlike a
// client-side gate. Runs on Netlify's free tier.
//
// The password is read from an environment variable, never stored in the repo:
//   Netlify dashboard -> Site settings -> Environment variables
//     SITE_PASSWORD  = <your shared password>
//     SITE_USERNAME  = <optional, defaults to "madio">
//
// The gate is INACTIVE until SITE_PASSWORD is set, so merging/deploying this
// never bricks the site — turning on protection is a one-variable change.

export default async (request, context) => {
  const password = Deno.env.get("SITE_PASSWORD");

  // No password configured yet -> serve normally (gate not enabled).
  if (!password) return context.next();

  const username = Deno.env.get("SITE_USERNAME") || "madio";
  const expected = "Basic " + btoa(`${username}:${password}`);
  const provided = request.headers.get("authorization") || "";

  // Constant-length compare is not critical here (shared password, not per-user
  // secrets), but avoid leaking length via early return on obviously-wrong input.
  if (provided === expected) return context.next();

  return new Response("Authentication required.", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="MADIO CRM", charset="UTF-8"',
      "Content-Type": "text/plain; charset=utf-8",
    },
  });
};

export const config = { path: "/*" };
