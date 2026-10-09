import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Download, ExternalLink, FileText, PackageOpen } from "lucide-react";
import { API } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const size = (b) => (!b ? "" : b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

/** What a customer or architect sees when they open a shared catalogue link
 * (/c/:token). No login; the link itself is the permission. */
export default function PublicCatalogue() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const base = `${API}/public/catalogues/${encodeURIComponent(token)}`;

  useEffect(() => {
    let live = true;
    fetch(base, { headers: { Accept: "application/json" } })
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!live) return;
        if (r.ok) { setData(body); document.title = `${body.title}${body.company ? ` · ${body.company}` : ""}`; }
        else setError(typeof body.detail === "string" ? body.detail : "This link isn't valid.");
      })
      .catch(() => live && setError("Couldn't reach the server. Check your connection and try again."));
    return () => { live = false; };
  }, [base]);

  const isPdf = data?.content_type === "application/pdf";
  const isImage = (data?.content_type || "").startsWith("image/");
  return (
    <div className="min-h-screen bg-[var(--color-bg,#f3f3f3)] text-[var(--color-text,#181818)]" data-testid="public-catalogue">
      <header className="border-b border-[var(--color-border,#e5e5e5)] bg-[var(--color-surface,#fff)]">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <span className="font-semibold tracking-wide">{data?.company || " "}</span>
          <span className="text-xs text-[var(--color-text-muted,#666)]">Shared catalogue</span>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-4 py-6 space-y-4">
        {!data && !error && <div className="text-sm text-[var(--color-text-muted,#666)]">Opening…</div>}
        {error && (
          <div className="rounded-xl border border-[var(--color-border,#e5e5e5)] bg-[var(--color-surface,#fff)] p-8 text-center space-y-2" data-testid="public-catalogue-error">
            <FileText className="mx-auto opacity-40" size={32} aria-hidden="true" />
            <p className="font-medium">{error}</p>
          </div>
        )}
        {data && (
          <>
            <div className="rounded-xl border border-[var(--color-border,#e5e5e5)] bg-[var(--color-surface,#fff)] p-5 flex flex-wrap items-center justify-between gap-4">
              <div className="min-w-0">
                {data.recipient_name && <div className="text-sm text-[var(--color-text-muted,#666)]">For {data.recipient_name}</div>}
                <h1 className="text-xl font-semibold leading-tight">{data.title}</h1>
                <div className="text-sm text-[var(--color-text-muted,#666)]">
                  {[data.division !== "All" && data.division, data.kind, `Version ${data.version}`,
                    data.valid_from && `valid from ${fmtDate(data.valid_from)}`].filter(Boolean).join(" · ")}
                </div>
                <div className="text-xs text-[var(--color-text-muted,#666)] mt-1">
                  Updated {fmtDate(data.updated_at)}{data.size_bytes ? ` · ${size(data.size_bytes)}` : ""}
                  {data.expires_at && ` · link works until ${fmtDate(data.expires_at)}`}
                </div>
              </div>
              <div className="flex gap-2">
                {data.inline && (
                  <a href={base + "/file"} target="_blank" rel="noreferrer" data-testid="public-catalogue-open"
                     className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-[var(--color-border,#e5e5e5)] text-sm">
                    <ExternalLink size={15} /> Open</a>
                )}
                <a href={base + "/file?download=true"} data-testid="public-catalogue-download"
                   className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--color-primary,#0176d3)] text-white text-sm">
                  <Download size={15} /> Download</a>
              </div>
            </div>
            {data.render_kit && (
              <div className="rounded-xl border border-[var(--color-border,#e5e5e5)] bg-[var(--color-surface,#fff)] p-4 flex flex-wrap items-center justify-between gap-3">
                <div className="text-sm min-w-0">
                  <div className="font-medium">Render kit for architects and designers</div>
                  <div className="text-[var(--color-text-muted,#666)]">
                    Each product cut out on a transparent background (PNG), room mockups and a size sheet, for your 3D renders and mood boards{data.kit_size ? ` · ${size(data.kit_size)}` : ""}.
                  </div>
                </div>
                <a href={base + "/render-kit"} data-testid="public-catalogue-kit"
                   className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-[var(--color-border,#e5e5e5)] text-sm">
                  <PackageOpen size={15} /> Download render kit</a>
              </div>
            )}
            {isPdf && (
              <iframe title={data.title} src={base + "/file"} className="w-full h-[78vh] rounded-xl border border-[var(--color-border,#e5e5e5)] bg-white" />
            )}
            {isImage && <img src={base + "/file"} alt={data.title} className="w-full rounded-xl border border-[var(--color-border,#e5e5e5)] bg-white" />}
          </>
        )}
      </main>
    </div>
  );
}
