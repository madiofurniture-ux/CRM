import api from "@/lib/api";

/**
 * Fetch an authenticated PDF and hand it to the user as a file.
 *
 * The routes need the bearer token, so the PDF is fetched as a blob. Opening
 * that blob with window.open after the await is treated as a popup by Safari
 * and phone browsers and silently blocked; a download link is not, and phones
 * open the saved file in their viewer.
 */
export async function downloadPdf(path, filename) {
  const { data } = await api.get(path, { skipCache: true, responseType: "blob" });
  const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${String(filename || "document").replace(/[\\/:*?"<>|]+/g, "-")}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/**
 * Fetch any authenticated file (a render kit, a mockup) and save it. `post`
 * sends a JSON body (e.g. the products a render kit is made of).
 */
export async function downloadFile(path, filename, post = null) {
  const opts = { skipCache: true, responseType: "blob" };
  const { data } = post ? await api.post(path, post, opts) : await api.get(path, opts);
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = String(filename || "download").replace(/[\\/:*?"<>|]+/g, "-");
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
