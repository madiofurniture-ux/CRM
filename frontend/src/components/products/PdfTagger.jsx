import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Camera, ChevronLeft, ChevronRight, Crop, Loader2, Minus, Plus, Trash2, X } from "lucide-react";
import api from "@/lib/api";

// PDF.js 3.11.174, served from the CRM (public/vendor/pdfjs, see its README).
const PDFJS_BASE = `${process.env.PUBLIC_URL || ""}/vendor/pdfjs/3.11.174`;
const MAX_CAPTURES = 100;
const BLANK = { name: "", vendor_item_code: "", vendor_price: "", dimensions: "", lead_time: "" };
const field = "w-full px-2.5 py-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm";

let pdfjsPromise = null;
/** PDF.js, loaded the first time a PDF is opened here. */
export function loadPdfJs() {
  if (window.pdfjsLib) return Promise.resolve(window.pdfjsLib);
  if (!pdfjsPromise) {
    pdfjsPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = `${PDFJS_BASE}/pdf.min.js`;
      s.async = true;
      s.onload = () => {
        const lib = window.pdfjsLib;
        if (!lib) { pdfjsPromise = null; reject(new Error("The PDF viewer didn't start")); return; }
        lib.GlobalWorkerOptions.workerSrc = `${PDFJS_BASE}/pdf.worker.min.js`;
        resolve(lib);
      };
      s.onerror = () => { pdfjsPromise = null; reject(new Error("Couldn't load the PDF viewer")); };
      document.head.appendChild(s);
    });
  }
  return pdfjsPromise;
}

async function pageLines(page) {
  const tc = await page.getTextContent();
  const rows = new Map();
  for (const it of tc.items) {
    const s = String(it.str || "").trim();
    if (!s) continue;
    const y = Math.round(it.transform[5] / 4);
    if (!rows.has(y)) rows.set(y, []);
    rows.get(y).push({ x: it.transform[4], s });
  }
  return [...rows.entries()].sort((a, b) => b[0] - a[0])
    .map(([, parts]) => parts.sort((a, b) => a.x - b.x).map((p) => p.s).join(" ").replace(/\s+/g, " ").trim())
    .filter(Boolean);
}

/** A vendor's PDF open beside the capture form: browse the pages, drag a box
 * around a product's picture, type (or tap from the page's text) its code,
 * name, size and price, and "Capture" it. The captured products then go to
 * the same review as an automatic import. `source` is {file} or {brochure}. */
export default function PdfTagger({ source, vendorId, removeWords = "", onDone, onClose, busy }) {
  const [pdf, setPdf] = useState(null);
  const [error, setError] = useState("");
  const [n, setN] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [lines, setLines] = useState([]);
  const [form, setForm] = useState(BLANK);
  const [focus, setFocus] = useState("name");
  const [rect, setRect] = useState(null);
  const [cutting, setCutting] = useState(() => !window.matchMedia?.("(pointer: coarse)").matches);
  const [captured, setCaptured] = useState([]);
  const [rendering, setRendering] = useState(false);
  const viewer = useRef(null);
  const canvas = useRef(null);
  const drag = useRef(null);
  const task = useRef(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    let live = true;
    let doc = null;
    (async () => {
      try {
        const lib = await loadPdfJs();
        const data = source.file ? await source.file.arrayBuffer()
          : (await api.get(`/catalogues/${source.brochure.id}/file`, { responseType: "arraybuffer", skipCache: true })).data;
        doc = await lib.getDocument({ data: new Uint8Array(data) }).promise;
        if (live) setPdf(doc); else doc.destroy();
      } catch (e) {
        if (live) setError(e?.name === "PasswordException" ? "This PDF is password-protected." : (e?.message || "Couldn't open the PDF"));
      }
    })();
    return () => { live = false; doc?.destroy?.(); };
  }, [source]);

  useEffect(() => {
    const el = viewer.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, [pdf]);

  // Render the page to fit the viewer's width (× zoom), sharp enough to cut pictures from.
  useEffect(() => {
    if (!pdf || !width || !canvas.current) return undefined;
    let live = true;
    (async () => {
      setRendering(true);
      try {
        const page = await pdf.getPage(n);
        const base = page.getViewport({ scale: 1 });
        const cssScale = Math.max(0.2, ((width - 24) / base.width) * zoom);
        const out = Math.min(4, Math.max(2, window.devicePixelRatio || 1));
        const vp = page.getViewport({ scale: cssScale * out });
        const c = canvas.current;
        c.width = Math.floor(vp.width);
        c.height = Math.floor(vp.height);
        c.style.width = `${Math.floor(vp.width / out)}px`;
        c.style.height = `${Math.floor(vp.height / out)}px`;
        task.current?.cancel?.();
        task.current = page.render({ canvasContext: c.getContext("2d"), viewport: vp });
        await task.current.promise;
        const text = await pageLines(page);
        if (!live) return;
        setLines(text);
        // What the page says, read the way the automatic import reads it (so a
        // code comes out the same), fills the fields still empty.
        const { data: g } = text.length
          ? await api.post("/vendor-catalogues/read-page", { vendor_id: vendorId, remove_words: removeWords, text: text.join("\n") })
            .catch(() => ({ data: {} }))
          : { data: {} };
        if (!live) return;
        setForm((f) => Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v || (g?.[k] ? String(g[k]) : "")])));
      } catch (e) {
        if (e?.name !== "RenderingCancelledException" && live) toast.error("Couldn't show that page");
      } finally { if (live) setRendering(false); }
    })();
    return () => { live = false; };
  }, [pdf, n, width, zoom, vendorId, removeWords]);

  const pages = pdf?.numPages || 0;
  const turn = useCallback((d) => {
    setRect(null);
    setForm((f) => ({ ...BLANK, lead_time: f.lead_time }));
    setN((p) => Math.min(Math.max(1, p + d), pages || 1));
  }, [pages]);
  useEffect(() => {
    const onKey = (e) => {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target?.tagName || "")) return;
      if (e.key === "ArrowRight") turn(1);
      if (e.key === "ArrowLeft") turn(-1);
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [turn, onClose]);

  const point = (e) => {
    const r = canvas.current.getBoundingClientRect();
    return { x: Math.min(Math.max(0, e.clientX - r.left), r.width), y: Math.min(Math.max(0, e.clientY - r.top), r.height) };
  };
  const down = (e) => {
    if (!cutting || e.button > 0) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    drag.current = point(e);
    setRect({ x: drag.current.x, y: drag.current.y, w: 0, h: 0 });
  };
  const move = (e) => {
    if (!drag.current) return;
    const p = point(e);
    const o = drag.current;
    setRect({ x: Math.min(o.x, p.x), y: Math.min(o.y, p.y), w: Math.abs(p.x - o.x), h: Math.abs(p.y - o.y) });
  };
  const up = () => {
    drag.current = null;
    setRect((r) => (r && r.w > 12 && r.h > 12 ? r : null));
  };

  const cut = () => {
    const c = canvas.current;
    if (!rect || !c) return "";
    const k = c.width / c.clientWidth;
    const sw = Math.round(rect.w * k);
    const sh = Math.round(rect.h * k);
    const fit = Math.min(1, 1200 / Math.max(sw, sh));
    const out = document.createElement("canvas");
    out.width = Math.round(sw * fit);
    out.height = Math.round(sh * fit);
    const ctx = out.getContext("2d");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, out.width, out.height);
    ctx.drawImage(c, Math.round(rect.x * k), Math.round(rect.y * k), sw, sh, 0, 0, out.width, out.height);
    return out.toDataURL("image/jpeg", 0.85);
  };
  const capture = (e) => {
    e?.preventDefault?.();
    if (!form.name.trim() && !form.vendor_item_code.trim()) { toast.error("Type the product's name or code"); return; }
    if (captured.length >= MAX_CAPTURES) { toast.error(`Up to ${MAX_CAPTURES} products at a time; review these first`); return; }
    const picture = cut();
    setCaptured((l) => [...l, { key: `${Date.now()}-${l.length}`, page: n, picture, ...form }]);
    setForm((f) => ({ ...BLANK, lead_time: f.lead_time }));
    setRect(null);
    toast.success(`Captured${picture ? "" : " (no picture: drag a box around it next time)"} · ${captured.length + 1} so far`);
  };
  const fill = (text) => setForm((f) => ({ ...f, [focus]: f[focus] && focus === "name" ? `${f[focus]} ${text}` : text }));
  const input = (k, label, extra = {}) => (
    <label className="block text-xs space-y-0.5"><span>{label}</span>
      <input className={`${field} ${focus === k ? "ring-2 ring-[var(--color-primary-soft,#dbeafe)]" : ""}`} value={form[k]}
             onFocus={() => setFocus(k)} onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} data-testid={`tag-${k}`} {...extra} /></label>
  );

  return (
    <div className="fixed inset-0 z-[55] bg-[var(--color-surface)] flex flex-col" role="dialog" aria-modal="true" aria-label="Tag products from the PDF" data-testid="pdf-tagger">
      <div className="flex flex-wrap items-center gap-2 px-3 sm:px-4 py-2 border-b border-[var(--color-border)] shrink-0">
        <div className="font-semibold mr-auto truncate max-w-[50vw]">Tag products · {source.file?.name || source.brochure?.title}</div>
        <div className="inline-flex items-center gap-1 text-sm">
          <button type="button" className="lx-icon-btn" onClick={() => turn(-1)} disabled={n <= 1} aria-label="Previous page"><ChevronLeft size={16} /></button>
          <span data-testid="tag-page">Page {n} / {pages || "…"}</span>
          <button type="button" className="lx-icon-btn" onClick={() => turn(1)} disabled={!pages || n >= pages} aria-label="Next page" data-testid="tag-next"><ChevronRight size={16} /></button>
        </div>
        <div className="inline-flex items-center gap-1 text-sm">
          <button type="button" className="lx-icon-btn" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} aria-label="Zoom out"><Minus size={14} /></button>
          <span className="w-10 text-center">{Math.round(zoom * 100)}%</span>
          <button type="button" className="lx-icon-btn" onClick={() => setZoom((z) => Math.min(3, z + 0.25))} aria-label="Zoom in"><Plus size={14} /></button>
        </div>
        <button type="button" onClick={() => setCutting((v) => !v)} aria-pressed={cutting}
                className={`lx-btn !py-1 inline-flex items-center gap-1 ${cutting ? "lx-btn-brand" : ""}`} data-testid="tag-cut-mode">
          <Crop size={14} /> {cutting ? "Drag a box round the picture" : "Cut a picture"}</button>
        <button type="button" className="lx-icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button>
      </div>
      <div className="flex-1 min-h-0 flex flex-col lg:flex-row">
        <div ref={viewer} className="relative flex-1 min-h-0 max-h-[52vh] lg:max-h-none overflow-auto bg-[var(--color-surface-muted,#f3f4f6)] p-3">
          {error ? <div className="p-6 text-sm text-[var(--color-danger)]">{error}</div>
            : !pdf ? <div className="p-6 text-sm text-[var(--color-text-muted)] inline-flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Opening the PDF…</div> : null}
          <div className="relative mx-auto w-fit shadow" style={{ touchAction: cutting ? "none" : "auto", cursor: cutting ? "crosshair" : "default" }}
               onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} data-testid="tag-canvas-wrap">
            <canvas ref={canvas} className="block bg-white" />
            {rect && <div className="absolute border-2 border-dashed border-[var(--color-primary,#2563eb)] bg-[var(--color-primary,#2563eb)]/10 pointer-events-none"
                          style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h }} data-testid="tag-rect" />}
            {rendering && <Loader2 size={18} className="absolute top-2 right-2 animate-spin text-[var(--color-text-muted)]" />}
          </div>
        </div>
        <div className="lg:w-[24rem] shrink-0 border-t lg:border-t-0 lg:border-l border-[var(--color-border)] flex flex-col min-h-0 overflow-y-auto">
          <form onSubmit={capture} className="p-3 space-y-2 border-b border-[var(--color-border)]" data-testid="tag-form">
            <div className="flex items-center gap-2">
              <div className="w-14 h-14 shrink-0 rounded border border-dashed border-[var(--color-border)] bg-white flex items-center justify-center text-[10px] text-center text-[var(--color-text-muted)] overflow-hidden">
                {rect ? "Picture box drawn" : "No picture yet"}
              </div>
              <p className="text-xs text-[var(--color-text-muted)]">Drag a box round the product's photo on the page (not the vendor's logo), fill what the page says, then Capture. Tap a line of the page's text below to fill the field you're in.</p>
            </div>
            {input("name", "Name", { autoFocus: true })}
            <div className="grid grid-cols-2 gap-2">
              {input("vendor_item_code", "Vendor's code")}
              {input("vendor_price", "Price on the page (landing)", { inputMode: "decimal" })}
              {input("dimensions", "Size")}
              {input("lead_time", "Lead time")}
            </div>
            <button type="submit" className="lx-btn lx-btn-brand w-full inline-flex items-center justify-center gap-1" data-testid="tag-capture">
              <Camera size={14} /> Capture product</button>
          </form>
          {lines.length > 0 && (
            <div className="p-3 border-b border-[var(--color-border)]">
              <div className="text-xs font-medium mb-1">Text on page {n}</div>
              <div className="flex flex-wrap gap-1 max-h-40 overflow-y-auto">
                {lines.slice(0, 60).map((l, i) => (
                  <button key={i} type="button" onClick={() => fill(l)} title={`Fill ${focus.replace("_", " ")}`}
                          className="text-[11px] px-1.5 py-0.5 rounded border border-[var(--color-border)] hover:bg-[var(--color-surface-muted)] max-w-full truncate">{l.slice(0, 60)}</button>
                ))}
              </div>
            </div>
          )}
          <div className="p-3 flex-1 space-y-1.5" data-testid="tag-captured">
            <div className="text-xs font-medium">Captured ({captured.length})</div>
            {captured.map((c) => (
              <div key={c.key} className="flex items-center gap-2 text-sm">
                <div className="w-10 h-10 shrink-0 rounded border border-[var(--color-border)] bg-white p-0.5">
                  {c.picture ? <img src={c.picture} alt="" className="w-full h-full object-contain" /> : null}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{c.name || c.vendor_item_code}</div>
                  <div className="text-xs text-[var(--color-text-muted)] truncate">p.{c.page}{c.vendor_item_code ? ` · ${c.vendor_item_code}` : ""}{c.vendor_price ? ` · ${c.vendor_price}` : ""}</div>
                </div>
                <button type="button" className="lx-icon-btn" aria-label="Remove" onClick={() => setCaptured((l) => l.filter((x) => x.key !== c.key))}><Trash2 size={13} /></button>
              </div>
            ))}
          </div>
          <div className="p-3 border-t border-[var(--color-border)] sticky bottom-0 bg-[var(--color-surface)]">
            <button type="button" className="lx-btn lx-btn-brand w-full inline-flex items-center justify-center gap-1" disabled={!captured.length || busy}
                    onClick={() => onDone(captured.map(({ key, ...r }) => r))} data-testid="tag-review">
              {busy ? <Loader2 size={14} className="animate-spin" /> : null} Review {captured.length} product{captured.length === 1 ? "" : "s"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
