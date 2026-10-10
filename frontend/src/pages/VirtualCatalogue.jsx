import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle, Archive, ArchiveRestore, BookLock, BookOpen, Boxes, Check, CheckSquare, ClipboardPaste, Download,
  FileText, FileUp, ImagePlus, Layers, Link2, Loader2, MessageCircle, MoreHorizontal, PackageOpen, Pencil, Percent,
  Ruler, ScanSearch, Scissors, Share2, Sparkles, Square, Star, Trash2, Truck, UserPlus, UserRound, Wand2, X, ZoomIn,
} from "lucide-react";
import Topbar from "@/components/Topbar";
import PicklistSelect from "@/components/PicklistSelect";
import ShareDialog, { openCatalogueFile } from "@/components/CatalogueShare";
import VendorSelect from "@/components/VendorSelect";
import Modal from "@/components/products/ProductModal";
import ClientPicker, { clientLabel } from "@/components/products/ClientPicker";
import ProductLightbox from "@/components/products/ProductLightbox";
import ShareProductDialog from "@/components/products/ShareProductDialog";
import QuoteBuilderDialog from "@/components/products/QuoteBuilderDialog";
import PdfTagger from "@/components/products/PdfTagger";
import useCatalogueMeta from "@/components/products/useCatalogueMeta";
import { brandTag, dimsOf, withoutSizeLines } from "@/components/products/productText";
import { useAuth } from "@/context/AuthContext";
import { useTenantConfig } from "@/context/TenantConfigContext";
import usePicklists from "@/hooks/usePicklists";
import api, { formatApiError } from "@/lib/api";
import { downloadFile } from "@/lib/pdf";
import { shrinkImage } from "@/lib/image";
import { inrFull } from "@/lib/format";

const MAX_CATALOGUE = 200;
const MAX_KIT = 60;
const MAX_PICTURES = 3;
const GST_RATES = ["", "0", "5", "12", "18", "28"];
const MOCKUPS = [
  ["room", "In a room"], ["wall", "On a wall"], ["framed", "Framed"], ["cutout", "Cut-out (PNG)"],
];
const DEFAULT_MOCKUP = { Furniture: "room", MAP: "wall", "D&W": "framed" };
const CLIENT_KEY = "vc_client";
const PASTE_EXAMPLE = "Code | Product | Size | Price\nDT MJ 1267 B | Dining Table, Italian marble | 240x110x75 CM | 2,80,000/-";
const field = "w-full px-2.5 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm";
const filterField = "px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-sm";
const bad = (e, fallback) => formatApiError(e?.response?.data?.detail) || fallback;
/** MADIO's price from the vendor's: × markup, rounded up to ₹10 (vendor_catalogue.madio_price). */
const madioPrice = (cost, markup) => {
  const c = Number(cost) || 0;
  const m = Number(markup) || 0;
  return c > 0 && m > 0 ? Math.ceil((c * m) / 10) * 10 : 0;
};

/** The customer the catalogue is being shown to (a lead or a walk-in), kept
 * for this browser tab so "+ Add" is one tap. */
function useActiveClient() {
  const [client, set] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem(CLIENT_KEY) || "null"); } catch { return null; }
  });
  const save = useCallback((c) => {
    set(c);
    try {
      if (c) sessionStorage.setItem(CLIENT_KEY, JSON.stringify(c));
      else sessionStorage.removeItem(CLIENT_KEY);
    } catch { /* storage off (private window): kept for this visit only */ }
  }, []);
  return [client, save];
}

/** A picture for a product from a link (the vendor's website): fetched by the
 * server, which only reaches public addresses. */
async function pictureFromLink() {
  const url = (window.prompt("Paste the picture's web address (right-click the picture → Copy image address)") || "").trim();
  if (!url) return "";
  const { data } = await api.post("/vendor-catalogues/picture-from-url", { url });
  return data.image;
}

/** The Virtual Catalogue: MADIO's own codes, names and prices for products
 * vendors make to order, imported from their catalogues without the
 * vendor's identity. Shown to customers in the showroom (zoom, WhatsApp,
 * shortlist on their lead or walk-in record, quotation / estimate), quoted
 * like stock (never reserved or issued), and made into MADIO-branded
 * catalogues, mockups and render kits for architects. */
export default function VirtualCatalogue() {
  const { user, canSeeCost } = useAuth();
  const { divisions } = useTenantConfig();
  const meta = useCatalogueMeta();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [rows, setRows] = useState(null);
  const [status, setStatus] = useState("Active");
  const [division, setDivision] = useState("All");
  const [category, setCategory] = useState("");
  const [q, setQ] = useState(() => params.get("q") || "");
  const urlQ = params.get("q");
  useEffect(() => { if (urlQ !== null) setQ(urlQ); }, [urlQ]);         // a global-search hit
  const [sel, setSel] = useState(() => new Set());
  const [importing, setImporting] = useState(null);   // {} | {brochureId}
  const [editing, setEditing] = useState(null);
  const [mockup, setMockup] = useState(null);
  const [making, setMaking] = useState(false);
  const [made, setMade] = useState(null);
  const [kitBusy, setKitBusy] = useState(false);
  const [client, setClient] = useActiveClient();
  const [zoomed, setZoomed] = useState(null);
  const [sharing, setSharing] = useState(null);
  const [quoting, setQuoting] = useState(null);       // products for the quotation / estimate
  const [choosing, setChoosing] = useState(null);     // {skus}: pick who they're for, then add
  const [repricing, setRepricing] = useState(false);

  const load = useCallback(() => {
    api.get(`/virtual-items?status=${status}`, { skipCache: true })
      .then(({ data }) => setRows(data || []))
      .catch((e) => { setRows([]); toast.error(bad(e, "Couldn't load the virtual catalogue")); });
  }, [status]);
  useEffect(() => { setRows(null); load(); }, [load]);

  // Vendor Brochures → "Import products" lands here with ?brochure=<id>; a
  // lead or visitor → "Browse catalogue" with ?for=lead:<id>.
  useEffect(() => {
    const b = params.get("brochure");
    const f = params.get("for");
    if (!b && !f) return;
    if (b && canSeeCost) setImporting({ brochureId: b });
    params.delete("brochure");
    params.delete("for");
    setParams(params, { replace: true });
    const [kind, id] = String(f || "").split(":");
    if (id && (kind === "lead" || kind === "visitor")) {
      api.get(`/shortlist/${kind}/${id}`, { skipCache: true })
        .then(({ data }) => setClient({ ...data, shortlist: (data.shortlist || []).length }))
        .catch((e) => toast.error(bad(e, "Couldn't open that record")));
    }
  }, [params, setParams, canSeeCost, setClient]);

  const categories = useMemo(() => [...new Set((rows || []).map((r) => r.category).filter(Boolean))].sort(), [rows]);
  const shown = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (rows || []).filter((r) =>
      (division === "All" || r.division === division) && (!category || r.category === category) &&
      (!term || [r.sku, r.name, r.subtitle, r.category, r.dimensions, ...(r.features || [])].join(" ").toLowerCase().includes(term)));
  }, [rows, division, category, q]);
  const selected = useMemo(() => (rows || []).filter((r) => sel.has(r.id)), [rows, sel]);

  const toggle = (id) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const act = async (fn, ok) => {
    try { await fn(); toast.success(ok); load(); } catch (e) { toast.error(bad(e, "That didn't work")); }
  };
  const renderKit = async () => {
    if (selected.length > MAX_KIT) { toast.error(`A render kit takes up to ${MAX_KIT} products; pick fewer`); return; }
    setKitBusy(true);
    try {
      await downloadFile("/virtual-items/render-kit", "MADIO render kit.zip", { item_ids: selected.map((r) => r.id) });
      toast.success("Render kit downloaded");
    } catch (e) {
      toast.error("Couldn't make the render kit");
    } finally { setKitBusy(false); }
  };
  const addTo = async (c, skus) => {
    try {
      const { data } = await api.post(`/shortlist/${c.kind}/${c.id}`, { skus });
      setClient({ ...c, shortlist: (data.shortlist || []).length });
      toast.success(data.added ? `Added to ${c.name}'s shortlist (${data.shortlist.length})` : `Already on ${c.name}'s shortlist`);
    } catch (e) { toast.error(bad(e, "Couldn't add it to the shortlist")); }
  };
  const add = (skus) => (client ? addTo(client, skus) : setChoosing({ skus }));
  const quoteShortlist = async () => {
    try {
      const { data } = await api.get(`/shortlist/${client.kind}/${client.id}`, { skipCache: true });
      const bySku = Object.fromEntries((rows || []).map((r) => [r.sku, r]));
      const items = (data.shortlist || []).map((e) => bySku[e.sku] || { sku: e.sku, name: e.name, mrp: e.price, division: e.division });
      if (!items.length) { toast.info(`Nothing on ${client.name}'s shortlist yet: “+ Add” puts products there`); return; }
      setQuoting(items);
    } catch (e) { toast.error(bad(e, "Couldn't open the shortlist")); }
  };
  const brandOf = (r) => meta.brands?.[r.division] || "";

  return (
    <>
      <Topbar title="Virtual Catalogue"
              subtitle={rows ? `${shown.length} product${shown.length === 1 ? "" : "s"} · made to order` : "Loading…"}
              onAdd={canSeeCost ? () => setImporting({}) : undefined} addLabel="Import vendor catalogue" />
      <div className="p-4 sm:p-6 space-y-4 pb-24" data-testid="virtual-catalogue-page">
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted,#f7f7f7)] px-4 py-3 text-sm flex flex-wrap items-center gap-x-3 gap-y-2">
          <Sparkles size={16} className="text-[var(--color-primary)] shrink-0" />
          <span className="flex-1 min-w-[16rem]">
            Products our vendors make to order, under MADIO's own codes, names and prices — no vendor names or contacts.
            Show them to customers, keep what they like on their lead, quote them like stock, or pick some to make a <b>MADIO catalogue</b> or a <b>render kit</b> for architects.
          </span>
          {canSeeCost && (
            <button type="button" className="lx-btn inline-flex items-center gap-1" onClick={() => navigate("/vendor-brochures")}
                    data-testid="vc-open-brochures"><BookLock size={14} /> Vendor brochures</button>
          )}
        </div>

        <div className={`rounded-lg border px-4 py-2.5 text-sm flex flex-wrap items-center gap-2 ${client ? "border-[var(--color-primary)] bg-[var(--color-primary-soft,#eff6ff)]" : "border-dashed border-[var(--color-border)]"}`}
             data-testid="vc-client-bar">
          <UserRound size={16} className="text-[var(--color-primary)] shrink-0" />
          {client ? (
            <>
              <span className="flex-1 min-w-[12rem]">Showing to <b data-testid="vc-client-name">{clientLabel(client)}</b>
                {client.shortlist ? <span className="text-[var(--color-text-muted)]"> · {client.shortlist} shortlisted</span> : null}</span>
              <button type="button" className="lx-btn !py-1 inline-flex items-center gap-1" onClick={quoteShortlist} data-testid="vc-client-quote">
                <FileText size={14} /> Shortlist → quotation / estimate</button>
              <button type="button" className="text-xs text-[var(--color-primary)]" onClick={() => setChoosing({})}>Change</button>
              <button type="button" className="lx-icon-btn" onClick={() => setClient(null)} aria-label="Stop showing to this customer"><X size={14} /></button>
            </>
          ) : (
            <>
              <span className="flex-1 min-w-[12rem] text-[var(--color-text-muted)]">With a customer? Pick their lead or walk-in record, then “+ Add” keeps what they like on it.</span>
              <button type="button" className="lx-btn !py-1 inline-flex items-center gap-1" onClick={() => setChoosing({})} data-testid="vc-pick-client">
                <UserPlus size={14} /> Lead / walk-in</button>
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search code, name, size, specification…" aria-label="Search products"
                 className={`${filterField} w-full sm:w-72`} data-testid="vc-search" />
          <select value={division} onChange={(e) => setDivision(e.target.value)} className={filterField} aria-label="Division" data-testid="vc-division">
            <option value="All">All divisions</option>
            {divisions.map((d) => <option key={d.id || d.slug} value={d.slug}>{d.slug}</option>)}
          </select>
          <select value={category} onChange={(e) => setCategory(e.target.value)} className={filterField} aria-label="Category" data-testid="vc-category">
            <option value="">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button type="button" className="lx-btn inline-flex items-center gap-1" disabled={!shown.length}
                  onClick={() => setSel((s) => new Set([...s, ...shown.map((r) => r.id)]))} data-testid="vc-select-all">
            <CheckSquare size={14} /> Select all shown</button>
          <div className="inline-flex rounded-lg border border-[var(--color-border)] overflow-hidden text-sm ml-auto" role="tablist">
            {["Active", "Archived"].map((s) => (
              <button key={s} role="tab" aria-selected={status === s} onClick={() => { setStatus(s); setSel(new Set()); }}
                      className={`px-3 py-1.5 ${status === s ? "bg-[var(--color-primary)] text-white" : "bg-[var(--color-surface)]"}`}
                      data-testid={`vc-status-${s}`}>{s}</button>
            ))}
          </div>
        </div>

        {rows === null ? <div className="text-sm text-[var(--color-text-muted)]">Loading…</div> : !shown.length ? (
          <div className="rounded-xl border border-dashed border-[var(--color-border)] p-10 text-center text-sm text-[var(--color-text-muted)]" data-testid="vc-empty">
            {status === "Active" ? (rows.length ? "No products match." : canSeeCost
              ? "No products yet. Import a vendor's catalogue: a PDF read automatically, a price list pasted as text, or products tagged while you browse their PDF. Their name, contacts and sales copy are taken out and each product gets a MADIO code."
              : "No products yet. Someone who can see landing prices imports them from vendors' catalogues.") : "Nothing archived."}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-3">
            {shown.map((r) => (
              <ProductCard key={r.id} r={r} brand={brandOf(r)} picked={sel.has(r.id)} onToggle={() => toggle(r.id)} canSeeCost={canSeeCost}
                           isAdmin={user?.role === "admin"} client={client} onZoom={() => setZoomed(r)} onShare={() => setSharing(r)}
                           onAdd={() => add([r.sku])} onMockup={() => setMockup(r)} onEdit={() => setEditing(r)}
                           onArchive={() => act(() => api.put(`/virtual-items/${r.id}`, { status: r.status === "Archived" ? "Active" : "Archived" }),
                             r.status === "Archived" ? "Back in the catalogue" : "Archived — old quotations keep it")}
                           onDelete={() => window.confirm(`Delete ${r.sku} “${r.name}” for good? Archive keeps it for old quotations.`)
                             && act(() => api.delete(`/virtual-items/${r.id}`), "Deleted")} />
            ))}
          </div>
        )}
      </div>

      {sel.size > 0 && (
        <div className="fixed bottom-0 inset-x-0 z-40 border-t border-[var(--color-border)] bg-[var(--color-surface)] shadow-[0_-4px_16px_rgba(0,0,0,.08)]" data-testid="vc-selection-bar">
          <div className="max-w-6xl mx-auto px-4 py-3 flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{sel.size} selected</span>
            <button type="button" className="text-xs text-[var(--color-text-muted)] underline" onClick={() => setSel(new Set())}>Clear</button>
            <div className="ml-auto flex flex-wrap gap-2">
              <button type="button" className="lx-btn inline-flex items-center gap-1" onClick={() => add(selected.map((r) => r.sku))}
                      data-testid="vc-add-selected"><UserPlus size={14} /> {client ? `Add to ${client.name}` : "Add to lead / walk-in"}</button>
              <button type="button" className="lx-btn inline-flex items-center gap-1" onClick={() => setQuoting(selected)} data-testid="vc-quote-selected">
                <FileText size={14} /> Quotation / estimate</button>
              {canSeeCost && (
                <button type="button" className="lx-btn inline-flex items-center gap-1" onClick={() => setRepricing(true)} data-testid="vc-reprice">
                  <Percent size={14} /> Re-price</button>
              )}
              <button type="button" className="lx-btn inline-flex items-center gap-1" onClick={renderKit} disabled={kitBusy}
                      title="Cut-outs on a transparent background, room mockups and a size sheet, for architects' renders" data-testid="vc-render-kit">
                {kitBusy ? <Loader2 size={14} className="animate-spin" /> : <PackageOpen size={14} />} Render kit (ZIP)
              </button>
              <button type="button" className="lx-btn lx-btn-brand inline-flex items-center gap-1" onClick={() => setMaking(true)}
                      disabled={sel.size > MAX_CATALOGUE} data-testid="vc-make-catalogue">
                <BookOpen size={14} /> Make MADIO catalogue
              </button>
            </div>
          </div>
        </div>
      )}

      {importing && <ImportDialog brochureId={importing.brochureId} onClose={() => setImporting(null)}
                                  onDone={() => { setImporting(null); setStatus("Active"); load(); }} />}
      {editing && <EditDialog item={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
      {mockup && <MockupDialog item={mockup} onClose={() => setMockup(null)} />}
      {making && <MakeCatalogueDialog items={selected} onClose={() => setMaking(false)}
                                      onMade={(c) => { setMaking(false); setSel(new Set()); setMade(c); }} />}
      {made && <MadeDialog catalogue={made} onClose={() => setMade(null)} />}
      {zoomed && <ProductLightbox item={zoomed} onClose={() => setZoomed(null)} />}
      {sharing && <ShareProductDialog item={sharing} brand={brandOf(sharing)} client={client} onClose={() => setSharing(null)} />}
      {quoting && <QuoteBuilderDialog items={quoting} client={client} onClose={() => setQuoting(null)}
                                      onClient={(c) => setClient({ ...c, shortlist: c.shortlist || 0 })} />}
      {repricing && <RepriceDialog items={selected} markup={meta.markup?.[selected[0]?.division] || ""} onClose={() => setRepricing(false)}
                                   onDone={() => { setRepricing(false); load(); }} />}
      {choosing && (
        <Modal title={choosing.skus?.length ? `Add ${choosing.skus.length === 1 ? choosing.skus[0] : `${choosing.skus.length} products`} to…` : "Who are you showing products to?"}
               onClose={() => setChoosing(null)} testid="vc-choose-client">
          <div className="p-5">
            <ClientPicker onPick={(c) => {
              const skus = choosing.skus;
              const picked = { ...c, shortlist: c.shortlist || 0 };
              setChoosing(null);
              setClient(picked);
              if (skus?.length) addTo(picked, skus);
            }} />
          </div>
        </Modal>
      )}
    </>
  );
}

function Thumb({ src, alt, className = "" }) {
  return src
    ? <img src={src} alt={alt} className={`w-full h-full object-contain ${className}`} loading="lazy" />
    : <div className={`w-full h-full flex items-center justify-center text-xs text-[var(--color-text-muted)] ${className}`}>No picture</div>;
}

function Chip({ Icon, children, title, testid }) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-[var(--color-surface-muted)] text-[var(--color-text)] max-w-full"
          title={title} data-testid={testid}>
      {Icon && <Icon size={11} className="shrink-0 text-[var(--color-text-muted)]" />}<span className="truncate">{children}</span>
    </span>
  );
}

function ProductCard({ r, brand, picked, onToggle, canSeeCost, isAdmin, client, onZoom, onShare, onAdd, onMockup, onEdit, onArchive, onDelete }) {
  const [menu, setMenu] = useState(false);
  const dims = dimsOf(r);
  const specs = withoutSizeLines(r.features).slice(0, 2);
  return (
    <div className={`rounded-xl border bg-[var(--color-surface)] overflow-hidden flex flex-col ${picked ? "border-[var(--color-primary)] ring-2 ring-[var(--color-primary-soft,#dbeafe)]" : "border-[var(--color-border)]"}`}
         data-testid={`vc-item-${r.sku}`}>
      <div className="relative aspect-[4/3] bg-white border-b border-[var(--color-border)] group">
        <button type="button" onClick={onZoom} className="absolute inset-0 w-full h-full p-3 cursor-zoom-in" aria-label={`Zoom ${r.name}`}
                data-testid={`vc-zoom-${r.sku}`}>
          <Thumb src={r.thumb} alt={r.name} />
          {r.thumb && <ZoomIn size={16} className="absolute bottom-2 right-2 text-[var(--color-text-muted)] opacity-0 group-hover:opacity-100" />}
        </button>
        <button type="button" onClick={onToggle} aria-pressed={picked} aria-label={`${picked ? "Unselect" : "Select"} ${r.name}`}
                className="absolute top-2 left-2 text-[var(--color-primary)] bg-white/90 rounded p-0.5" data-testid={`vc-select-${r.sku}`}>
          {picked ? <CheckSquare size={18} /> : <Square size={18} className="text-[var(--color-text-muted)]" />}
        </button>
        <span className="absolute top-2 right-2 font-mono text-[11px] font-semibold px-1.5 py-0.5 rounded bg-[var(--color-surface)]/95 border border-[var(--color-border)]">{r.sku}</span>
        <span className="absolute bottom-2 left-2 pointer-events-none text-[10px] font-bold tracking-wider px-1.5 py-0.5 rounded bg-[var(--color-primary)] text-white"
              title={brand || r.division}>{brandTag(r.division, brand)}</span>
      </div>
      <div className="p-3 flex flex-col gap-1.5 flex-1">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <div className="font-semibold leading-snug">{r.name}</div>
            <div className="text-xs text-[var(--color-text-muted)] truncate">
              {[r.division, r.category, r.subtitle].filter(Boolean).join(" · ") || "—"}
            </div>
          </div>
          <div className="relative">
            <button type="button" className="lx-icon-btn" onClick={() => setMenu((m) => !m)} aria-label="More actions" aria-expanded={menu}
                    data-testid={`vc-menu-${r.sku}`}><MoreHorizontal size={16} /></button>
            {menu && (
              <div className="absolute right-0 mt-1 w-44 z-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg shadow-lg py-1 text-sm"
                   onMouseLeave={() => setMenu(false)}>
                <MenuItem Icon={Wand2} onClick={() => { setMenu(false); onMockup(); }}>Mockup</MenuItem>
                {canSeeCost && <MenuItem Icon={Pencil} onClick={() => { setMenu(false); onEdit(); }}>Edit</MenuItem>}
                {canSeeCost && <MenuItem Icon={r.status === "Archived" ? ArchiveRestore : Archive} onClick={() => { setMenu(false); onArchive(); }}>
                  {r.status === "Archived" ? "Restore" : "Archive"}</MenuItem>}
                {isAdmin && <MenuItem Icon={Trash2} danger onClick={() => { setMenu(false); onDelete(); }}>Delete</MenuItem>}
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-1">
          <Chip Icon={Truck} testid={`vc-mto-${r.sku}`}>Made to order{r.lead_time ? ` · ${r.lead_time.replace(/^made[\s-]*to[\s-]*order[,;\s-]*/i, "")}` : ""}</Chip>
          {dims && <Chip Icon={Ruler} title="Size" testid={`vc-dims-${r.sku}`}>{dims}</Chip>}
          {r.moq && <Chip Icon={Boxes} title="Minimum order">MOQ {r.moq}</Chip>}
        </div>
        {specs.length > 0 && (
          <ul className="text-xs text-[var(--color-text-muted)] space-y-0.5">
            {specs.map((f) => <li key={f} className="truncate" title={f}>{f}</li>)}
          </ul>
        )}
        <div className="mt-auto pt-1 space-y-1.5">
          <div>
            <div className="text-lg font-semibold" data-testid={`vc-price-${r.sku}`}>{r.mrp ? inrFull(r.mrp) : <span className="text-sm text-[var(--color-text-muted)]">Price on request</span>}</div>
            <div className="text-[11px] text-[var(--color-text-muted)] truncate" title={r.sale_terms || undefined}>
              {r.sale_terms || (r.mrp ? "incl. GST · per piece" : "")}</div>
          </div>
          {canSeeCost && r.cost != null && (
            <div className="text-[11px] text-[var(--color-text-muted)] truncate" data-testid={`vc-cost-${r.sku}`}
                 title={[r.vendor_code, r.vendor].filter(Boolean).join(" · ")}>
              Landing {inrFull(r.cost)}{r.margin ? ` · margin ${r.margin}%` : ""}{r.markup ? ` · × ${r.markup}` : ""}{r.vendor ? ` · ${r.vendor}` : ""}
            </div>
          )}
          <div className="grid grid-cols-2 gap-1.5">
            <button type="button" className="lx-btn inline-flex items-center justify-center gap-1 !px-2" onClick={onShare}
                    data-testid={`vc-share-${r.sku}`}><MessageCircle size={14} /> WhatsApp</button>
            <button type="button" className="lx-btn lx-btn-brand inline-flex items-center justify-center gap-1 !px-2 min-w-0" onClick={onAdd}
                    title={client ? `Add to ${clientLabel(client)}'s shortlist` : "Add to a lead or walk-in's shortlist"} data-testid={`vc-add-${r.sku}`}>
              <UserPlus size={14} className="shrink-0" /><span className="truncate">{client ? `Add · ${client.name.split(" ")[0]}` : "Add to lead"}</span></button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MenuItem({ Icon, children, onClick, danger }) {
  return (
    <button type="button" onClick={onClick}
            className={`w-full text-left px-3 py-1.5 inline-flex items-center gap-2 hover:bg-[var(--color-surface-muted)] ${danger ? "text-[var(--color-danger)]" : ""}`}>
      <Icon size={14} /> {children}
    </button>
  );
}

/** A category from Master Data's list once the company has filled it; until
 * then anything, with the categories already used as suggestions. */
function CategoryInput({ value, onChange, hint, known = [], testId }) {
  const { values } = usePicklists();
  const listed = values("catalogue_categories", "").filter(Boolean);
  const id = useRef(`cat-${Math.random().toString(36).slice(2)}`).current;
  if (listed.length) {
    return (
      <div>
        <PicklistSelect list="catalogue_categories" value={value} onChange={onChange} placeholder="Category…" className={field} testId={testId} />
        {hint && !value && <div className="text-[11px] text-[var(--color-text-muted)] mt-0.5">Catalogue says “{hint}” — not in the list</div>}
      </div>
    );
  }
  return (
    <>
      <input list={id} value={value} onChange={(e) => onChange(e.target.value)} placeholder={hint || "Category"} className={field} data-testid={testId} />
      <datalist id={id}>{known.map((c) => <option key={c} value={c} />)}</datalist>
    </>
  );
}

function RepriceDialog({ items, markup, onClose, onDone }) {
  const [m, setM] = useState(String(markup || ""));
  const [busy, setBusy] = useState(false);
  const priced = items.filter((r) => Number(r.cost) > 0);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/virtual-items/reprice", { item_ids: items.map((r) => r.id), markup: Number(m) || 0 });
      toast.success(`${data.updated} re-priced at × ${m}${data.skipped.length ? `; ${data.skipped.length} without a landing price kept theirs` : ""}`);
      onDone();
    } catch (err) { toast.error(bad(err, "Couldn't re-price")); } finally { setBusy(false); }
  };
  return (
    <Modal title={`Re-price ${items.length} product${items.length === 1 ? "" : "s"}`} onClose={onClose} testid="vc-reprice-dialog">
      <form onSubmit={submit} className="p-5 space-y-3">
        <p className="text-sm text-[var(--color-text-muted)]">MADIO price = landing (vendor) price × markup, rounded up to ₹10. The company's markup for vendor catalogues is set in Master Data → Quotations.</p>
        <label className="block text-sm space-y-1 w-40"><span className="font-medium">Markup ×</span>
          <input type="number" min="0.1" max="10" step="0.05" className={field} value={m} onChange={(e) => setM(e.target.value)} required data-testid="vc-reprice-markup" /></label>
        <ul className="text-xs space-y-0.5">
          {priced.slice(0, 6).map((r) => (
            <li key={r.id}><span className="font-mono">{r.sku}</span> {inrFull(r.cost)} → <b>{inrFull(madioPrice(r.cost, m))}</b>
              <span className="text-[var(--color-text-muted)]"> (now {inrFull(r.mrp)})</span></li>
          ))}
          {priced.length > 6 && <li className="text-[var(--color-text-muted)]">… and {priced.length - 6} more</li>}
          {priced.length < items.length && <li className="text-[var(--color-warning,#b45309)]">{items.length - priced.length} without a landing price keep their price.</li>}
        </ul>
        <div className="flex justify-end gap-2">
          <button type="button" className="lx-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="lx-btn lx-btn-brand" disabled={busy || !Number(m)} data-testid="vc-reprice-submit">{busy ? "Re-pricing…" : "Re-price"}</button>
        </div>
      </form>
    </Modal>
  );
}

// ── import a vendor's catalogue ────────────────────────────────────────────
const IMPORT_MODES = [
  ["file", FileUp, "PDF or pictures", "Read automatically"],
  ["paste", ClipboardPaste, "Paste a list", "From a PDF, Excel or OCR"],
  ["tag", ScanSearch, "Tag from the PDF", "Browse it, capture each product"],
];

function ImportDialog({ brochureId, onClose, onDone }) {
  const { divisions } = useTenantConfig();
  const meta = useCatalogueMeta();
  const [mode, setMode] = useState("file");
  const [step, setStep] = useState("source");
  const [form, setForm] = useState({ vendor_id: "", division: "", remove_words: "", markup: "", brochure_id: brochureId || "",
                                     lead_time: "", moq: "", sale_terms: "" });
  const set = (p) => setForm((f) => ({ ...f, ...p }));
  const [files, setFiles] = useState([]);
  const [text, setText] = useState("");
  const [brochures, setBrochures] = useState([]);
  const [pending, setPending] = useState([]);
  const [busy, setBusy] = useState(false);
  const [imp, setImp] = useState(null);
  const [tagging, setTagging] = useState(null);       // {file} | {brochure}

  useEffect(() => {
    api.get("/catalogues?status=Current&origin=vendor", { skipCache: true })
      .then(({ data }) => {
        const list = (data || []).filter((b) => b.content_type === "application/pdf");
        setBrochures(list);
        const b = list.find((x) => x.id === brochureId);
        if (b) setForm((f) => ({ ...f, vendor_id: b.vendor_id || "", division: b.division !== "All" ? b.division : "" }));
      }).catch(() => setBrochures([]));
    api.get("/vendor-catalogues/imports", { skipCache: true })
      .then(({ data }) => setPending((data || []).filter((i) => i.status === "Review"))).catch(() => setPending([]));
  }, [brochureId]);

  const ready = () => {
    if (!form.vendor_id) { toast.error("Pick the vendor whose catalogue this is"); return false; }
    if (!form.division) { toast.error("Pick the division"); return false; }
    return true;
  };
  const read = async (e) => {
    e.preventDefault();
    if (!ready()) return;
    if (mode === "tag") {
      const b = brochures.find((x) => x.id === form.brochure_id);
      const pdf = files.find((f) => /\.pdf$/i.test(f.name));
      if (!b && !pdf) { toast.error("Choose the vendor's PDF"); return; }
      setTagging(b ? { brochure: b } : { file: pdf });
      return;
    }
    setBusy(true);
    try {
      let data;
      if (mode === "paste") {
        if (!text.trim()) { toast.error("Paste the vendor's list first"); setBusy(false); return; }
        ({ data } = await api.post("/vendor-catalogues/rows", { ...form, brochure_id: "", text }, { timeout: 120000 }));
      } else {
        if (!form.brochure_id && !files.length) { toast.error("Choose the PDF or the product pictures"); setBusy(false); return; }
        const fd = new FormData();
        Object.entries(form).forEach(([k, v]) => fd.append(k, v ?? ""));
        if (!form.brochure_id) files.forEach((f) => fd.append("files", f));
        ({ data } = await api.post("/vendor-catalogues/extract", fd, { timeout: 300000 }));
      }
      setImp(data); setStep("review");
    } catch (err) {
      toast.error(bad(err, "Couldn't read that"));
    } finally { setBusy(false); }
  };
  const captured = async (rows) => {
    setBusy(true);
    try {
      const { data } = await api.post("/vendor-catalogues/rows", {
        ...form, brochure_id: tagging.brochure?.id || "", file_name: tagging.file?.name || tagging.brochure?.file_name || "", rows,
      }, { timeout: 300000 });
      setTagging(null); setImp(data); setStep("review");
    } catch (err) {
      toast.error(bad(err, "Couldn't add those products"));
    } finally { setBusy(false); }
  };
  const resume = async (id) => {
    setBusy(true);
    try { const { data } = await api.get(`/vendor-catalogues/imports/${id}`, { skipCache: true }); setImp(data); setStep("review"); }
    catch (err) { toast.error(bad(err, "Couldn't open that import")); }
    finally { setBusy(false); }
  };
  const discard = async (id) => {
    try { await api.delete(`/vendor-catalogues/imports/${id}`); setPending((l) => l.filter((i) => i.id !== id)); }
    catch (err) { toast.error(bad(err, "Couldn't discard it")); }
  };

  if (tagging) {
    return <PdfTagger source={tagging} vendorId={form.vendor_id} removeWords={form.remove_words} busy={busy}
                      onClose={() => setTagging(null)} onDone={captured} />;
  }
  if (step === "review" && imp) {
    return <ReviewImport imp={imp} onBack={() => { setStep("source"); setImp(null); }} onClose={onClose} onDone={onDone}
                         onDiscard={async () => { await discard(imp.id); onClose(); }} />;
  }
  const defaultMarkup = meta.markup?.[form.division];
  return (
    <Modal title="Import a vendor's catalogue" onClose={onClose} testid="vc-import">
      <form onSubmit={read} className="p-5 space-y-4">
        <div className="grid grid-cols-3 gap-2" role="tablist" aria-label="How to bring the products in">
          {IMPORT_MODES.map(([k, Icon, label, hint]) => (
            <button key={k} type="button" role="tab" aria-selected={mode === k} onClick={() => setMode(k)} data-testid={`vc-import-mode-${k}`}
                    className={`rounded-lg border p-2 text-left text-sm ${mode === k ? "border-[var(--color-primary)] bg-[var(--color-primary-soft,#eff6ff)]" : "border-[var(--color-border)]"}`}>
              <Icon size={16} className="text-[var(--color-primary)] mb-1" />
              <div className="font-medium leading-tight">{label}</div>
              <div className="text-[11px] text-[var(--color-text-muted)] leading-tight">{hint}</div>
            </button>
          ))}
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">
          {mode === "file" ? "Each page's product pictures, name and specification are read; " : mode === "paste" ? "Each row (or block) becomes a product: its code, name, size, price, lead time and terms are found wherever they are; " : "Open the PDF beside a capture form: drag a box round each product's picture and type (or tap) its code, name, size and price; "}
          the vendor's name, phone numbers, e-mails, websites, GSTIN, address and sales copy are taken out. You check everything before anything is added.
        </p>
        {pending.length > 0 && (
          <div className="rounded-lg border border-[var(--color-border)] p-3 text-sm space-y-1.5" data-testid="vc-pending">
            <div className="font-medium">Waiting for review</div>
            {pending.map((p) => (
              <div key={p.id} className="flex items-center gap-2">
                <span className="flex-1 min-w-0 truncate">{p.file_name} · {p.candidate_count} products · {p.division}</span>
                <button type="button" className="text-xs font-medium text-[var(--color-primary)]" onClick={() => resume(p.id)}>Continue</button>
                <button type="button" className="text-xs text-[var(--color-text-muted)]" onClick={() => discard(p.id)}>Discard</button>
              </div>
            ))}
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1 text-sm">
            <span className="font-medium">Vendor</span>
            <VendorSelect value={form.vendor_id} onChange={(v) => set({ vendor_id: v })} testId="vc-import-vendor" />
          </div>
          <label className="block text-sm space-y-1">
            <span className="font-medium">Division</span>
            <select className={field} value={form.division} onChange={(e) => set({ division: e.target.value })} data-testid="vc-import-division">
              <option value="">Pick…</option>
              {divisions.map((d) => <option key={d.id || d.slug} value={d.slug}>{d.slug}</option>)}
            </select>
          </label>
        </div>
        {mode === "paste" ? (
          <label className="block text-sm space-y-1">
            <span className="font-medium">The vendor's list <span className="font-normal text-[var(--color-text-muted)]">(copied from their PDF, a spreadsheet or OCR — one product a row, or a block per product)</span></span>
            <textarea className={`${field} font-mono text-xs`} rows={8} value={text} onChange={(e) => setText(e.target.value)}
                      placeholder={PASTE_EXAMPLE} data-testid="vc-import-text" />
          </label>
        ) : (
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium mb-1">{mode === "tag" ? "The vendor's PDF" : "The catalogue"}</legend>
            {brochures.length > 0 && (
              <select className={field} value={form.brochure_id} onChange={(e) => {
                const b = brochures.find((x) => x.id === e.target.value);
                set({ brochure_id: e.target.value, ...(b ? { vendor_id: b.vendor_id || form.vendor_id, division: b.division !== "All" ? b.division : form.division } : {}) });
              }} data-testid="vc-import-brochure">
                <option value="">Upload a file instead…</option>
                {brochures.map((b) => <option key={b.id} value={b.id}>{b.title} (v{b.version}){b.vendor_name ? ` · ${b.vendor_name}` : b.vendor_code ? ` · ${b.vendor_code}` : ""}</option>)}
              </select>
            )}
            {!form.brochure_id && (
              <label className="block rounded-lg border border-dashed border-[var(--color-border)] p-4 text-sm text-center cursor-pointer">
                <input type="file" multiple={mode === "file"} accept={mode === "tag" ? ".pdf" : ".pdf,.jpg,.jpeg,.png,.webp"} className="sr-only" data-testid="vc-import-files"
                       onChange={(e) => setFiles([...(e.target.files || [])])} />
                <FileUp size={18} className="mx-auto mb-1 text-[var(--color-text-muted)]" />
                {files.length ? <span className="font-medium">{files.length === 1 ? files[0].name : `${files.length} pictures`}</span>
                  : <span>{mode === "tag" ? "The vendor's PDF catalogue" : "One PDF catalogue (up to 40 MB, 120 pages), or product pictures"}</span>}
              </label>
            )}
          </fieldset>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label className="block text-sm space-y-1 sm:col-span-2">
            <span className="font-medium">Also take out <span className="font-normal text-[var(--color-text-muted)]">(their brand / series names, comma-separated)</span></span>
            <input className={field} value={form.remove_words} onChange={(e) => set({ remove_words: e.target.value })}
                   placeholder="e.g. Acmeflex, Royal Series" data-testid="vc-import-remove" />
          </label>
          <label className="block text-sm space-y-1">
            <span className="font-medium">Markup ×</span>
            <input type="number" min="0" step="0.05" className={field} value={form.markup} onChange={(e) => set({ markup: e.target.value })}
                   placeholder={defaultMarkup ? `${defaultMarkup} (company's)` : "Division's"} data-testid="vc-import-markup" />
          </label>
        </div>
        <details className="text-sm">
          <summary className="cursor-pointer font-medium">Lead time, MOQ and terms for every product <span className="font-normal text-[var(--color-text-muted)]">(unless the catalogue says otherwise)</span></summary>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2">
            <input className={field} value={form.lead_time} onChange={(e) => set({ lead_time: e.target.value })} placeholder="Lead time, e.g. 3-4 weeks" data-testid="vc-import-lead" />
            <input className={field} value={form.moq} onChange={(e) => set({ moq: e.target.value })} placeholder="MOQ, e.g. 1 piece" data-testid="vc-import-moq" />
            <input className={field} value={form.sale_terms} onChange={(e) => set({ sale_terms: e.target.value })} placeholder="Terms, e.g. transport extra" data-testid="vc-import-terms" />
          </div>
        </details>
        <div className="flex justify-end gap-2">
          <button type="button" className="lx-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="lx-btn lx-btn-brand inline-flex items-center gap-1" disabled={busy} data-testid="vc-import-read">
            {busy ? <><Loader2 size={14} className="animate-spin" /> Reading…{mode === "file" ? " (a long catalogue takes a minute)" : ""}</>
              : mode === "paste" ? "Read the list" : mode === "tag" ? "Open the PDF" : "Read catalogue"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

const rowFrom = (c, markup) => ({
  rid: c.key, key: c.key, keep: c.likely !== false, page: c.page, images: c.images || [], base: (c.images || []).length,
  pics: (c.images || []).map((_, i) => i),
  // A product already in the catalogue keeps the name MADIO gave it.
  name: c.match?.name || c.name || "", subtitle: c.subtitle || "", category: c.category || "", hint: c.category_hint || "",
  // The size has its own field; the server writes "Size: …" back as the first specification line.
  featuresText: withoutSizeLines(c.features).join("\n"), dimensions: c.dimensions || "", lead_time: c.lead_time || "",
  moq: c.moq || "", sale_terms: c.sale_terms || "", description: "", vendor_item_code: c.vendor_item_code || "",
  vendor_price: c.vendor_price ?? "", mrp: c.suggested_price || madioPrice(c.vendor_price, markup) || "",
  match: c.match, whole_page: c.whole_page, removed: c.removed || 0,
});

function ReviewImport({ imp, onBack, onClose, onDone, onDiscard }) {
  const [markup, setMarkup] = useState(imp.markup || "");
  const [rows, setRows] = useState(() => (imp.candidates || []).map((c) => rowFrom(c, imp.markup)));
  const [saving, setSaving] = useState(false);
  const [bulkCat, setBulkCat] = useState("");
  const kept = rows.filter((r) => r.keep);
  const known = useMemo(() => [...new Set(rows.map((r) => r.category || r.hint).filter(Boolean))], [rows]);
  const upd = (rid, p) => setRows((l) => l.map((r) => (r.rid === rid ? { ...r, ...p } : r)));
  const split = (r) => setRows((l) => l.flatMap((x) => (x.rid !== r.rid ? [x] : x.pics.map((i, n) => ({
    ...x, rid: `${x.key}-${i}`, pics: [i], name: `${x.name} ${n + 1}`, vendor_item_code: x.vendor_item_code ? `${x.vendor_item_code}-${n + 1}` : "", match: null,
  })))));
  const reprice = () => setRows((l) => l.map((r) => ({ ...r, mrp: madioPrice(r.vendor_price, markup) || r.mrp })));
  const typed = imp.source === "text" || imp.source === "capture";

  const commit = async () => {
    if (!kept.length) { toast.error("Keep at least one product"); return; }
    const unnamed = kept.find((r) => !r.name.trim());
    if (unnamed) { toast.error(`${typed ? "Row" : "Page"} ${unnamed.page}: give the product a name`); return; }
    setSaving(true);
    try {
      const { data } = await api.post(`/vendor-catalogues/imports/${imp.id}/commit`, {
        markup: Number(markup) || 0,
        items: kept.map((r) => ({
          key: r.key, name: r.name, subtitle: r.subtitle, category: r.category, description: r.description,
          features: r.featuresText.split("\n").map((x) => x.trim()).filter(Boolean),
          dimensions: r.dimensions, lead_time: r.lead_time, moq: r.moq, sale_terms: r.sale_terms,
          vendor_item_code: r.vendor_item_code, vendor_price: Number(r.vendor_price) || 0, mrp: Number(r.mrp) || 0,
          // The read pictures by number; pictures added here as they are.
          images: r.pics.map((i) => (i < r.base ? i : r.images[i])),
        })),
      }, { timeout: 120000 });
      toast.success(`${data.created} added${data.updated ? `, ${data.updated} updated` : ""} in the Virtual Catalogue`);
      onDone();
    } catch (err) {
      toast.error(bad(err, "Couldn't add the products"));
    } finally { setSaving(false); }
  };

  const s = imp.summary || {};
  return (
    <Modal title={`Review: ${imp.file_name}`} onClose={onClose} testid="vc-review" wide>
      <div className="px-5 py-3 border-b border-[var(--color-border)] text-sm space-y-2 bg-[var(--color-surface-muted,#f7f7f7)]">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[var(--color-text-muted)]">
          <span><b className="text-[var(--color-text)]">{rows.length}</b> products {imp.source === "text" ? `from ${s.rows} pasted lines` : imp.source === "capture" ? "captured" : `found in ${s.pages} ${s.pages === 1 ? "page" : "pages"}`}</span>
          {!typed && <span>{s.pictures_dropped || 0} logos / icons dropped</span>}
          <span>{s.removed || 0} vendor details taken out</span>
          {imp.vendor_name && <span>Vendor: {imp.vendor_name}</span>}
          <span>Division: {imp.division}</span>
          {s.collection && <span>Range: {s.collection}</span>}
        </div>
        {(s.common_features || []).length > 0 && (
          <div className="text-xs text-[var(--color-text-muted)]" data-testid="vc-common-features">
            The brochure's product details were added to every shade: {s.common_features.join(" · ")}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="lx-btn !py-1" onClick={() => setRows((l) => l.map((r) => ({ ...r, keep: true })))}>Keep all</button>
          <button type="button" className="lx-btn !py-1" onClick={() => setRows((l) => l.map((r) => ({ ...r, keep: false })))}>Keep none</button>
          <span className="inline-flex items-center gap-1">
            <span className="text-xs">Category for all kept</span>
            <span className="w-40"><CategoryInput value={bulkCat} onChange={setBulkCat} known={known} testId="vc-bulk-category" /></span>
            <button type="button" className="lx-btn !py-1" disabled={!bulkCat}
                    onClick={() => setRows((l) => l.map((r) => (r.keep ? { ...r, category: bulkCat } : r)))}>Apply</button>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="text-xs">Markup ×</span>
            <input type="number" min="0" step="0.05" value={markup} onChange={(e) => setMarkup(e.target.value)}
                   className="w-20 px-2 py-1 rounded-md border border-[var(--color-border)] text-sm" data-testid="vc-review-markup" />
            <button type="button" className="lx-btn !py-1" onClick={reprice} disabled={!Number(markup)}>Re-price all</button>
          </span>
        </div>
      </div>
      <div className="divide-y divide-[var(--color-border)]">
        {rows.map((r) => (
          <ReviewRow key={r.rid} r={r} typed={typed} known={known} onChange={(p) => upd(r.rid, p)} onSplit={() => split(r)} markup={markup} />
        ))}
      </div>
      <div className="sticky bottom-0 px-5 py-3 border-t border-[var(--color-border)] bg-[var(--color-surface)] flex flex-wrap items-center gap-2">
        <button type="button" className="lx-btn" onClick={onBack}>Back</button>
        <button type="button" className="lx-btn text-[var(--color-danger)]" onClick={() => window.confirm("Discard this import? Nothing has been added yet.") && onDiscard()}>Discard</button>
        <span className="ml-auto text-sm text-[var(--color-text-muted)]">{kept.length} to add</span>
        <button type="button" className="lx-btn lx-btn-brand inline-flex items-center gap-1" onClick={commit} disabled={saving || !kept.length} data-testid="vc-review-commit">
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Add to Virtual Catalogue
        </button>
      </div>
    </Modal>
  );
}

function ReviewRow({ r, typed, known, onChange, onSplit, markup }) {
  const togglePic = (i) => onChange({ pics: r.pics.includes(i) ? r.pics.filter((x) => x !== i) : [...r.pics, i].slice(0, MAX_PICTURES) });
  const suggested = madioPrice(r.vendor_price, markup);
  const addPicture = (src) => src && onChange({ images: [...r.images, src], pics: [...r.pics, r.images.length].slice(0, MAX_PICTURES) });
  const fromFile = async (file) => {
    if (!file) return;
    try { addPicture(await shrinkImage(file, 1000, 0.85)); } catch (e) { toast.error(e.message || "Couldn't read that picture"); }
  };
  const fromLink = async () => {
    try { addPicture(await pictureFromLink()); } catch (e) { toast.error(bad(e, "Couldn't use that link")); }
  };
  return (
    <div className={`p-4 grid grid-cols-1 lg:grid-cols-[auto_15rem_1fr] gap-4 ${r.keep ? "" : "opacity-50"}`} data-testid={`vc-review-${r.rid}`}>
      <label className="flex lg:flex-col items-center gap-2 text-xs text-[var(--color-text-muted)]">
        <input type="checkbox" checked={r.keep} onChange={(e) => onChange({ keep: e.target.checked })} className="w-4 h-4" data-testid={`vc-keep-${r.rid}`} />
        <span>{typed ? `#${r.page}` : `p.${r.page}`}</span>
      </label>
      <div className="space-y-1.5">
        <div className="grid grid-cols-3 gap-1.5">
          {r.images.map((src, i) => {
            const on = r.pics.includes(i);
            return (
              <button key={i} type="button" onClick={() => togglePic(i)} title={on ? "Leave this picture out" : "Use this picture"}
                      className={`relative aspect-square rounded border bg-white p-0.5 ${on ? "border-[var(--color-primary)]" : "border-[var(--color-border)] opacity-40"}`}>
                <img src={src} alt="" className="w-full h-full object-contain" />
                {on && r.pics[0] === i && <Star size={12} className="absolute top-0.5 left-0.5 text-amber-500 fill-amber-400" />}
              </button>
            );
          })}
          {!r.images.length && <div className="col-span-3 text-xs text-[var(--color-text-muted)]">{typed ? "No picture yet" : "No picture on this page"}</div>}
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
          <label className="inline-flex items-center gap-1 text-[var(--color-primary)] cursor-pointer">
            <input type="file" accept="image/*" className="sr-only" onChange={(e) => fromFile(e.target.files?.[0])} data-testid={`vc-review-pic-${r.rid}`} />
            <ImagePlus size={12} /> Picture</label>
          <button type="button" className="inline-flex items-center gap-1 text-[var(--color-primary)]" onClick={fromLink}><Link2 size={12} /> From a link</button>
          {r.pics.length > 1 && (
            <button type="button" className="inline-flex items-center gap-1 text-[var(--color-primary)]" onClick={onSplit}>
              <Scissors size={12} /> One product per picture</button>
          )}
        </div>
        {r.whole_page && (
          <div className="text-[11px] text-[var(--color-warning,#b45309)] flex gap-1"><AlertTriangle size={12} className="shrink-0 mt-0.5" />
            The whole page is one picture: it may still show the vendor's logo or text. Check it, or replace the picture after adding.</div>
        )}
        {r.match && <div className="text-[11px] text-[var(--color-primary)]">Updates {r.match.sku} ({r.match.name}); its MADIO code stays.</div>}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2 content-start">
        <label className="text-xs space-y-0.5 sm:col-span-2"><span>Name</span>
          <input className={field} value={r.name} onChange={(e) => onChange({ name: e.target.value })} data-testid={`vc-name-${r.rid}`} /></label>
        <label className="text-xs space-y-0.5"><span>Category</span>
          <CategoryInput value={r.category} hint={r.hint} known={known} onChange={(v) => onChange({ category: v })} /></label>
        <label className="text-xs space-y-0.5"><span>Size</span>
          <input className={field} value={r.dimensions} onChange={(e) => onChange({ dimensions: e.target.value })} placeholder="240 x 110 x 75 cm"
                 data-testid={`vc-dims-${r.rid}`} /></label>
        <label className="text-xs space-y-0.5 sm:col-span-2"><span>Specification (one per line)</span>
          <textarea className={field} rows={3} value={r.featuresText} onChange={(e) => onChange({ featuresText: e.target.value })} /></label>
        <label className="text-xs space-y-0.5 sm:col-span-2"><span>MADIO's description <span className="text-[var(--color-text-muted)]">(optional, printed in the catalogue)</span></span>
          <textarea className={field} rows={3} value={r.description} onChange={(e) => onChange({ description: e.target.value })}
                    placeholder="In our own words — the vendor's sales copy is left out." /></label>
        <label className="text-xs space-y-0.5"><span>Lead time</span>
          <input className={field} value={r.lead_time} onChange={(e) => onChange({ lead_time: e.target.value })} placeholder="3-4 weeks" /></label>
        <label className="text-xs space-y-0.5"><span>MOQ</span>
          <input className={field} value={r.moq} onChange={(e) => onChange({ moq: e.target.value })} placeholder="1 piece" /></label>
        <label className="text-xs space-y-0.5 sm:col-span-2"><span>Terms</span>
          <input className={field} value={r.sale_terms} onChange={(e) => onChange({ sale_terms: e.target.value })} placeholder="GST included, transport & installation extra" /></label>
        <label className="text-xs space-y-0.5"><span>Vendor's code</span>
          <input className={field} value={r.vendor_item_code} onChange={(e) => onChange({ vendor_item_code: e.target.value })} /></label>
        <label className="text-xs space-y-0.5"><span>Vendor's price (landing)</span>
          <input type="number" min="0" className={field} value={r.vendor_price} onChange={(e) => onChange({ vendor_price: e.target.value })} /></label>
        <label className="text-xs space-y-0.5"><span>MADIO price (incl. GST)</span>
          <input type="number" min="0" className={field} value={r.mrp} onChange={(e) => onChange({ mrp: e.target.value })}
                 placeholder={suggested ? String(suggested) : "Price on request"} data-testid={`vc-mrp-${r.rid}`} /></label>
        <div className="text-[11px] text-[var(--color-text-muted)] self-end pb-2">
          {suggested ? `× ${markup} = ${inrFull(suggested)}` : "Set a markup or type MADIO's price"}
        </div>
      </div>
    </div>
  );
}

// ── one product ────────────────────────────────────────────────────────────
function EditDialog({ item, onClose, onSaved }) {
  const { divisions } = useTenantConfig();
  const [full, setFull] = useState(null);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    api.get(`/virtual-items/${item.id}`, { skipCache: true }).then(({ data }) => {
      setFull(data);
      setForm({
        name: data.name || "", subtitle: data.subtitle || "", category: data.category || "", division: data.division || "",
        unit: data.unit || "pcs", gst_pct: data.gst_pct == null ? "" : String(data.gst_pct), hsn: data.hsn || "",
        mrp: data.mrp ?? "", cost: data.cost ?? "", vendor_item_code: data.vendor_item_code || "",
        dimensions: dimsOf(data), lead_time: data.lead_time || "", moq: data.moq || "", sale_terms: data.sale_terms || "",
        featuresText: withoutSizeLines(data.features).join("\n"), description: data.description || "", images: data.images || [],
      });
    }).catch((e) => { toast.error(bad(e, "Couldn't open it")); closeRef.current(); });
  }, [item.id]);
  if (!form) return <Modal title={`${item.sku} · ${item.name}`} onClose={onClose}><div className="p-5 text-sm">Loading…</div></Modal>;
  const set = (p) => setForm((f) => ({ ...f, ...p }));
  const addPic = async (file) => {
    if (!file) return;
    try { const url = await shrinkImage(file, 1000, 0.82); set({ images: [...form.images, url].slice(0, MAX_PICTURES) }); }
    catch (e) { toast.error(e.message || "Couldn't read that picture"); }
  };
  const addLink = async () => {
    try { const url = await pictureFromLink(); if (url) set({ images: [...form.images, url].slice(0, MAX_PICTURES) }); }
    catch (e) { toast.error(bad(e, "Couldn't use that link")); }
  };
  const save = async (e) => {
    e.preventDefault();
    const { featuresText, ...rest } = form;
    const payload = { ...rest, features: featuresText.split("\n").map((x) => x.trim()).filter(Boolean),
                      mrp: Number(form.mrp) || 0, cost: Number(form.cost) || 0 };
    if (JSON.stringify(form.images) === JSON.stringify(full.images || [])) delete payload.images;
    setSaving(true);
    try { await api.put(`/virtual-items/${item.id}`, payload); toast.success("Saved"); onSaved(); }
    catch (err) { toast.error(bad(err, "Couldn't save")); }
    finally { setSaving(false); }
  };
  return (
    <Modal title={`${item.sku} · ${item.name}`} onClose={onClose} testid="vc-edit">
      <form onSubmit={save} className="p-5 space-y-3">
        <div className="space-y-1">
          <span className="text-sm font-medium">Pictures <span className="font-normal text-xs text-[var(--color-text-muted)]">(the first is the main one; up to 3)</span></span>
          <div className="flex flex-wrap gap-2">
            {form.images.map((src, i) => (
              <div key={i} className="relative w-24 h-24 rounded border border-[var(--color-border)] bg-white p-1">
                <img src={src} alt="" className="w-full h-full object-contain" />
                <div className="absolute inset-x-0 bottom-0 flex justify-between p-0.5">
                  {i > 0 ? <button type="button" title="Make main" className="bg-white/90 rounded p-0.5"
                                   onClick={() => set({ images: [src, ...form.images.filter((_, k) => k !== i)] })}><Star size={12} /></button> : <span />}
                  <button type="button" title="Remove" className="bg-white/90 rounded p-0.5 text-[var(--color-danger)]"
                          onClick={() => set({ images: form.images.filter((_, k) => k !== i) })}><Trash2 size={12} /></button>
                </div>
              </div>
            ))}
            {form.images.length < MAX_PICTURES && (
              <>
                <label className="w-24 h-24 rounded border border-dashed border-[var(--color-border)] flex flex-col items-center justify-center text-xs text-[var(--color-text-muted)] cursor-pointer">
                  <input type="file" accept="image/*" className="sr-only" onChange={(e) => addPic(e.target.files?.[0])} />
                  <ImagePlus size={18} /> Add
                </label>
                <button type="button" onClick={addLink}
                        className="w-24 h-24 rounded border border-dashed border-[var(--color-border)] flex flex-col items-center justify-center text-xs text-[var(--color-text-muted)]">
                  <Link2 size={18} /> From a link</button>
              </>
            )}
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-sm space-y-1 sm:col-span-2"><span className="font-medium">Name</span>
            <input className={field} value={form.name} onChange={(e) => set({ name: e.target.value })} required data-testid="vc-edit-name" /></label>
          <label className="block text-sm space-y-1"><span className="font-medium">Subtitle</span>
            <input className={field} value={form.subtitle} onChange={(e) => set({ subtitle: e.target.value })} /></label>
          <label className="block text-sm space-y-1"><span className="font-medium">Category</span>
            <CategoryInput value={form.category} onChange={(v) => set({ category: v })} /></label>
          <label className="block text-sm space-y-1"><span className="font-medium">Division</span>
            <select className={field} value={form.division} onChange={(e) => set({ division: e.target.value })}>
              {divisions.map((d) => <option key={d.id || d.slug} value={d.slug}>{d.slug}</option>)}
            </select></label>
          <div className="grid grid-cols-3 gap-2">
            <label className="block text-sm space-y-1"><span className="font-medium">Unit</span>
              <PicklistSelect list="units" value={form.unit} onChange={(v) => set({ unit: v || "pcs" })} className={field} required /></label>
            <label className="block text-sm space-y-1"><span className="font-medium">GST %</span>
              <select className={field} value={form.gst_pct} onChange={(e) => set({ gst_pct: e.target.value })}>
                {GST_RATES.map((g) => <option key={g} value={g}>{g === "" ? "—" : g}</option>)}
              </select></label>
            <label className="block text-sm space-y-1"><span className="font-medium">HSN</span>
              <input className={field} value={form.hsn} onChange={(e) => set({ hsn: e.target.value })} /></label>
          </div>
          <label className="block text-sm space-y-1"><span className="font-medium">Size</span>
            <input className={field} value={form.dimensions} onChange={(e) => set({ dimensions: e.target.value })} placeholder="240 x 110 x 75 cm" data-testid="vc-edit-dims" /></label>
          <label className="block text-sm space-y-1"><span className="font-medium">Lead time</span>
            <input className={field} value={form.lead_time} onChange={(e) => set({ lead_time: e.target.value })} placeholder="3-4 weeks" /></label>
          <label className="block text-sm space-y-1"><span className="font-medium">MOQ</span>
            <input className={field} value={form.moq} onChange={(e) => set({ moq: e.target.value })} placeholder="1 piece" /></label>
          <label className="block text-sm space-y-1"><span className="font-medium">Terms</span>
            <input className={field} value={form.sale_terms} onChange={(e) => set({ sale_terms: e.target.value })} placeholder="GST included, transport extra" /></label>
          <label className="block text-sm space-y-1"><span className="font-medium">MADIO price (incl. GST)</span>
            <input type="number" min="0" className={field} value={form.mrp} onChange={(e) => set({ mrp: e.target.value })} data-testid="vc-edit-mrp" /></label>
          <label className="block text-sm space-y-1"><span className="font-medium">Landing price (vendor's)</span>
            <input type="number" min="0" className={field} value={form.cost} onChange={(e) => set({ cost: e.target.value })} /></label>
          <label className="block text-sm space-y-1"><span className="font-medium">Vendor's code</span>
            <input className={field} value={form.vendor_item_code} onChange={(e) => set({ vendor_item_code: e.target.value })} /></label>
          <label className="block text-sm space-y-1 sm:col-span-2"><span className="font-medium">Specification (one per line)</span>
            <textarea className={field} rows={4} value={form.featuresText} onChange={(e) => set({ featuresText: e.target.value })} /></label>
          <label className="block text-sm space-y-1 sm:col-span-2"><span className="font-medium">Description</span>
            <textarea className={field} rows={3} value={form.description} onChange={(e) => set({ description: e.target.value })} /></label>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="lx-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="lx-btn lx-btn-brand" disabled={saving} data-testid="vc-edit-save">{saving ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}

function MockupDialog({ item, onClose }) {
  const [kind, setKind] = useState(DEFAULT_MOCKUP[item.division] || "room");
  const [img, setImg] = useState(null);       // {url, removed} | {error}
  useEffect(() => {
    let url = "";
    let live = true;
    setImg(null);
    api.get(`/virtual-items/${item.id}/mockup?kind=${kind}`, { responseType: "blob", skipCache: true, timeout: 120000 })
      .then((res) => {
        url = URL.createObjectURL(res.data);
        if (live) setImg({ url, removed: res.headers?.["x-background-removed"] !== "no" });
      })
      .catch(() => live && setImg({ error: true }));
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
  }, [item.id, kind]);
  const ext = kind === "cutout" ? "png" : "jpg";
  const checker = "bg-[length:20px_20px] bg-[linear-gradient(45deg,#eee_25%,transparent_25%,transparent_75%,#eee_75%),linear-gradient(45deg,#eee_25%,transparent_25%,transparent_75%,#eee_75%)] [background-position:0_0,10px_10px]";
  return (
    <Modal title={`Mockup · ${item.sku} ${item.name}`} onClose={onClose} testid="vc-mockup" wide>
      <div className="p-5 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border border-[var(--color-border)] overflow-hidden text-sm" role="tablist">
            {MOCKUPS.map(([k, l]) => (
              <button key={k} type="button" role="tab" aria-selected={kind === k} onClick={() => setKind(k)}
                      className={`px-3 py-1.5 ${kind === k ? "bg-[var(--color-primary)] text-white" : "bg-[var(--color-surface)]"}`}
                      data-testid={`vc-mockup-${k}`}>{l}</button>
            ))}
          </div>
          <button type="button" className="lx-btn lx-btn-brand inline-flex items-center gap-1 ml-auto" disabled={!img?.url}
                  onClick={() => downloadFile(`/virtual-items/${item.id}/mockup?kind=${kind}&download=true`, `${item.sku}_${kind}.${ext}`)
                    .catch(() => toast.error("Couldn't download it"))} data-testid="vc-mockup-download">
            <Download size={14} /> Download {ext.toUpperCase()}
          </button>
        </div>
        <div className={`rounded-lg border border-[var(--color-border)] min-h-[16rem] flex items-center justify-center overflow-hidden ${kind === "cutout" ? checker : "bg-[var(--color-surface-muted,#f5f5f5)]"}`}>
          {!img ? <Loader2 className="animate-spin text-[var(--color-text-muted)]" />
            : img.error ? <span className="text-sm text-[var(--color-danger)]">Couldn't make this mockup.</span>
              : <img src={img.url} alt={`${item.name} ${kind} mockup`} className="max-h-[60vh] w-auto" data-testid="vc-mockup-img" />}
        </div>
        {img?.url && !img.removed && (
          <p className="text-xs text-[var(--color-warning,#b45309)] flex gap-1"><AlertTriangle size={13} className="shrink-0" />
            {kind === "cutout"
              ? "This picture's backdrop isn't plain, so it couldn't be cut out; it's included as it is. A product shot on a white background cuts out cleanly."
              : "This picture has its own background, so it's shown hung on the wall rather than standing in the room."}</p>
        )}
        <p className="text-xs text-[var(--color-text-muted)]">
          Cut-outs are transparent PNGs that architects drop straight into SketchUp, 3ds Max or Photoshop renders and mood boards. Room and wall mockups carry MADIO's name and the product code.
          For several products at once, select them and download a <b>render kit</b>.
        </p>
      </div>
    </Modal>
  );
}

// ── MADIO's catalogue ──────────────────────────────────────────────────────
function MakeCatalogueDialog({ items, onClose, onMade }) {
  const divs = [...new Set(items.map((i) => i.division).filter(Boolean))];
  const month = new Date().toLocaleDateString("en-IN", { month: "long", year: "numeric", timeZone: "Asia/Kolkata" });
  const [form, setForm] = useState({
    title: `${divs.length === 1 ? divs[0] : "MADIO"} Collection — ${month}`, subtitle: "", division: divs.length === 1 ? divs[0] : "All",
    show_prices: true, render_kit: items.length <= MAX_KIT, audience: "external", note: "", replaces: "",
    // MAP finishes print as a shade card (twelve a page); the rest two a page.
    layout: divs.length === 1 && divs[0] === "MAP" ? "swatches" : "products",
  });
  const set = (p) => setForm((f) => ({ ...f, ...p }));
  const [existing, setExisting] = useState([]);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    api.get("/catalogues?status=Current", { skipCache: true })
      .then(({ data }) => setExisting((data || []).filter((c) => c.origin === "generated"))).catch(() => setExisting([]));
  }, []);
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const { data } = await api.post("/virtual-items/catalogue", { ...form, item_ids: items.map((i) => i.id) }, { timeout: 300000 });
      toast.success(form.replaces ? "New version made; links already shared open it" : "MADIO catalogue made");
      onMade(data);
    } catch (err) {
      toast.error(bad(err, "Couldn't make the catalogue"));
    } finally { setSaving(false); }
  };
  return (
    <Modal title={`MADIO catalogue of ${items.length} product${items.length === 1 ? "" : "s"}`} onClose={onClose} testid="vc-make">
      <form onSubmit={submit} className="p-5 space-y-3">
        <p className="text-sm text-[var(--color-text-muted)]">
          A branded PDF — cover, two products a page with MADIO codes, and how to order — saved on the Catalogues page, ready to share by link.
        </p>
        <label className="block text-sm space-y-1"><span className="font-medium">Title</span>
          <input className={field} value={form.title} onChange={(e) => set({ title: e.target.value })} required data-testid="vc-make-title" /></label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-sm space-y-1"><span className="font-medium">Subtitle</span>
            <input className={field} value={form.subtitle} onChange={(e) => set({ subtitle: e.target.value })} placeholder="e.g. Living room · for Ar. Meera" /></label>
          <label className="block text-sm space-y-1"><span className="font-medium">Make it a new version of</span>
            <select className={field} value={form.replaces} onChange={(e) => set({ replaces: e.target.value })}>
              <option value="">— a new catalogue —</option>
              {existing.map((c) => <option key={c.id} value={c.id}>{c.title} (v{c.version})</option>)}
            </select></label>
        </div>
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium mb-1">Layout</legend>
          <div className="inline-flex rounded-lg border border-[var(--color-border)] overflow-hidden text-sm" role="radiogroup">
            {[["products", "Product pages · 2 a page"], ["swatches", "Shade card · 12 a page"]].map(([k, l]) => (
              <button key={k} type="button" role="radio" aria-checked={form.layout === k} onClick={() => set({ layout: k })}
                      className={`px-3 py-1.5 ${form.layout === k ? "bg-[var(--color-primary)] text-white" : "bg-[var(--color-surface)]"}`}
                      data-testid={`vc-make-layout-${k}`}>{l}</button>
            ))}
          </div>
        </fieldset>
        <div className="space-y-1.5 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.show_prices} onChange={(e) => set({ show_prices: e.target.checked })} data-testid="vc-make-prices" /> Show MADIO prices</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.render_kit} disabled={items.length > MAX_KIT}
                                                            onChange={(e) => set({ render_kit: e.target.checked })} data-testid="vc-make-kit" />
            Include a render kit for architects (cut-outs and mockups){items.length > MAX_KIT ? ` — up to ${MAX_KIT} products` : ""}</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={form.audience === "internal"}
                                                            onChange={(e) => set({ audience: e.target.checked ? "internal" : "external" })} /> Staff only (can't be shared outside)</label>
        </div>
        {form.show_prices && (
          <label className="block text-sm space-y-1"><span className="font-medium">Price note <span className="font-normal text-[var(--color-text-muted)]">(printed on the back page)</span></span>
            <textarea className={field} rows={2} value={form.note} onChange={(e) => set({ note: e.target.value })}
                      placeholder="Prices in ₹ include GST and are subject to change without notice. Transport and installation are extra unless stated." /></label>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="lx-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="lx-btn lx-btn-brand inline-flex items-center gap-1" disabled={saving} data-testid="vc-make-submit">
            {saving ? <><Loader2 size={14} className="animate-spin" /> Making…</> : <><Layers size={14} /> Make catalogue</>}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function MadeDialog({ catalogue, onClose }) {
  const navigate = useNavigate();
  const [sharing, setSharing] = useState(false);
  if (sharing) return <ShareDialog catalogue={catalogue} onClose={onClose} />;
  return (
    <Modal title={`“${catalogue.title}” is ready`} onClose={onClose} testid="vc-made">
      <div className="p-5 space-y-3 text-sm">
        <p>v{catalogue.version} · {catalogue.item_count} products{catalogue.render_kit ? " · with a render kit" : ""}. It's on the Catalogues page; share links always open its newest version.</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="lx-btn inline-flex items-center gap-1" onClick={() => openCatalogueFile(catalogue)}><BookOpen size={14} /> Open PDF</button>
          {catalogue.audience === "external" && (
            <button type="button" className="lx-btn lx-btn-brand inline-flex items-center gap-1" onClick={() => setSharing(true)} data-testid="vc-made-share">
              <Share2 size={14} /> Share with a customer or architect</button>
          )}
          <button type="button" className="lx-btn inline-flex items-center gap-1" onClick={() => navigate("/catalogues")}><Boxes size={14} /> Catalogues</button>
        </div>
      </div>
    </Modal>
  );
}
