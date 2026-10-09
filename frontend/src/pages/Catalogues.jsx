import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Archive, ArchiveRestore, Download, ExternalLink, Eye, FileImage, FileSpreadsheet, FileText, Globe, Lock,
  MoreHorizontal, Pencil, Share2, ShieldCheck, Trash2, Upload, X, FolderOpen, RefreshCw, PackageOpen, Sparkles,
  Boxes,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import Topbar from "@/components/Topbar";
import PicklistSelect from "@/components/PicklistSelect";
import VendorSelect from "@/components/VendorSelect";
import ShareDialog, { openCatalogueFile } from "@/components/CatalogueShare";
import { useAuth } from "@/context/AuthContext";
import { useTenantConfig } from "@/context/TenantConfigContext";
import api, { formatApiError } from "@/lib/api";
import { downloadFile } from "@/lib/pdf";
import { OBJECT_COLOR } from "@/lib/apps";
import { fmtDate, fmtRelativeDateTime } from "@/lib/format";

const AUDIENCE = {
  external: { label: "Customers & architects", help: "Staff can open it and share links with customers and architects.", Icon: Globe, tone: "text-[var(--color-success)]" },
  internal: { label: "Staff only", help: "Every staff member can open it; it can't be shared outside.", Icon: Lock, tone: "text-[var(--color-text-muted)]" },
  restricted: { label: "Landing-price holders only", help: "Only admin, accounts and people who can see landing prices.", Icon: ShieldCheck, tone: "text-[var(--color-warning,#b45309)]" },
};
const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,.xlsx,.xls,.docx,.pptx,.zip";

const fileIcon = (t = "") => (t.startsWith("image/") ? FileImage : /sheet|excel/.test(t) ? FileSpreadsheet : FileText);
const size = (b) => (!b ? "" : b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

/** Mirrors permissions.py can(): admin always; legacy accounts (no role)
 * may view/create/edit; role accounts need the documents grant. */
function useDocsPermission() {
  const { user, roles } = useAuth();
  return useCallback((action) => {
    if (!user) return false;
    if (user.role === "admin") return true;
    if (!user.role_id) return ["view", "create", "edit", "delete"].includes(action);
    const role = (roles || []).find((r) => r.id === user.role_id);
    return !!role?.permissions?.find((p) => p.module === "documents")?.[action];
  }, [user, roles]);
}

/** Catalogues: each division's current price lists, brochures and shade
 * cards, kept in SharePoint, opened here and shared with customers and
 * architects by links that always show the newest version.
 * vendorMode: the Vendor Brochures page — vendors' own brochures, kept for
 * landing-price holders only and never shared outside; their products are
 * imported into the Virtual Catalogue to make MADIO's own version. */
export default function Catalogues({ vendorMode = false }) {
  const { user, canSeeCost } = useAuth();
  const { divisions } = useTenantConfig();
  const can = useDocsPermission();
  const navigate = useNavigate();
  const [rows, setRows] = useState(null);
  const [status, setStatus] = useState("Current");
  const [division, setDivision] = useState("All");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [publishing, setPublishing] = useState(null);   // {} new | {replaces: cat}
  const [editing, setEditing] = useState(null);
  const [sharing, setSharing] = useState(null);

  const load = useCallback(() => {
    if (vendorMode && !canSeeCost) { setRows([]); return; }
    api.get(`/catalogues?status=${status}${vendorMode ? "&origin=vendor" : ""}`, { skipCache: true })
      .then(({ data }) => setRows(data || []))
      .catch((e) => { setRows([]); toast.error(formatApiError(e.response?.data?.detail) || "Couldn't load catalogues"); });
  }, [status, vendorMode, canSeeCost]);
  useEffect(() => { setRows(null); load(); }, [load]);

  const shown = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (rows || []).filter((c) =>
      (division === "All" || c.division === division || c.division === "All") &&
      (!kind || c.kind === kind) &&
      (!term || [c.title, c.kind, c.division, c.file_name, c.notes, c.vendor_name, c.vendor_code].join(" ").toLowerCase().includes(term)));
  }, [rows, division, kind, q]);

  const act = async (fn, ok) => {
    try { await fn(); toast.success(ok); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "That didn't work"); }
  };

  const field = "px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-sm";
  return (
    <>
      <Topbar title={vendorMode ? "Vendor Brochures" : "Catalogues"}
              subtitle={rows ? `${shown.length} ${status === "Current" ? "current" : "archived"}${vendorMode ? " · internal, landing-price holders only" : ""}` : "Loading…"}
              onAdd={can("create") && (!vendorMode || canSeeCost) ? () => setPublishing({}) : undefined}
              addLabel={vendorMode ? "Add vendor brochure" : "Publish catalogue"} />
      <div className="p-4 sm:p-6 space-y-4" data-testid={vendorMode ? "vendor-brochures-page" : "catalogues-page"}>
        {vendorMode && (
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted,#f7f7f7)] px-4 py-3 text-sm flex flex-wrap items-center gap-x-3 gap-y-1">
            <ShieldCheck size={16} className="text-[var(--color-warning,#b45309)] shrink-0" />
            <span className="flex-1 min-w-[16rem]">Brochures and price lists exactly as vendors sent them — their names, prices and contacts included — so they stay with admin, accounts and landing-price holders and are never shared outside. <b>Import products</b> turns one into MADIO-coded products in the Virtual Catalogue, ready for a MADIO-branded catalogue.</span>
            <button type="button" className="lx-btn inline-flex items-center gap-1" onClick={() => navigate("/virtual-catalogue")}><Boxes size={14} /> Virtual Catalogue</button>
          </div>
        )}
        {vendorMode && !canSeeCost ? (
          <div className="rounded-xl border border-dashed border-[var(--color-border)] p-10 text-center text-sm text-[var(--color-text-muted)]">
            Vendor brochures are open to admin, accounts and people who can see landing prices.
          </div>
        ) : (<>
        <div className="flex flex-wrap items-center gap-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search catalogues…" aria-label="Search catalogues"
                 className={`${field} w-full sm:w-64`} data-testid="catalogue-search" />
          <select value={division} onChange={(e) => setDivision(e.target.value)} className={field} aria-label="Division" data-testid="catalogue-division">
            <option value="All">All divisions</option>
            {divisions.map((d) => <option key={d.id || d.slug} value={d.slug}>{d.slug}</option>)}
          </select>
          <PicklistSelect list="catalogue_types" value={kind} onChange={setKind} placeholder="All types" className={field} ariaLabel="Type" />
          <div className="inline-flex rounded-lg border border-[var(--color-border)] overflow-hidden text-sm ml-auto" role="tablist">
            {["Current", "Archived"].map((s) => (
              <button key={s} role="tab" aria-selected={status === s} onClick={() => setStatus(s)}
                      className={`px-3 py-1.5 ${status === s ? "bg-[var(--color-primary)] text-white" : "bg-[var(--color-surface)]"}`}
                      data-testid={`catalogue-status-${s}`}>{s}</button>
            ))}
          </div>
        </div>

        {rows === null ? <div className="text-sm text-[var(--color-text-muted)]">Loading…</div> : !shown.length ? (
          <div className="rounded-xl border border-dashed border-[var(--color-border)] p-10 text-center text-sm text-[var(--color-text-muted)]" data-testid="catalogue-empty">
            {status === "Current" ? (vendorMode
              ? "No vendor brochures yet. Add the brochures and price lists vendors send, then import their products into the Virtual Catalogue."
              : "No catalogues yet. Publish a price list, brochure or shade card so everyone works from the same file.") : "Nothing archived."}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {shown.map((c) => (
              <CatalogueCard key={c.id} c={c} can={can} isAdmin={user?.role === "admin"} vendorMode={vendorMode}
                             onImport={() => navigate(`/virtual-catalogue?brochure=${c.id}`)}
                             onRegenerate={() => act(() => api.post(`/catalogues/${c.id}/regenerate`), "Made again with today's names, prices and pictures; shared links now open it")}
                             onShare={() => setSharing(c)} onNewVersion={() => setPublishing({ replaces: c })}
                             onEdit={() => setEditing(c)}
                             onArchive={() => act(() => api.post(`/catalogues/${c.id}/archive`), "Archived")}
                             onRestore={() => act(() => api.post(`/catalogues/${c.id}/restore`), "Made current again")}
                             onDelete={() => window.confirm(`Delete “${c.title}” v${c.version}? Share links to it stop if it's the last version.`)
                               && act(() => api.delete(`/catalogues/${c.id}`), "Deleted")} />
            ))}
          </div>
        )}
        </>)}
      </div>

      {publishing && <PublishDialog replaces={publishing.replaces} vendorMode={vendorMode} onClose={() => setPublishing(null)}
                                    onSaved={() => { setPublishing(null); setStatus("Current"); load(); }} />}
      {editing && <EditDialog c={editing} vendorMode={vendorMode} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
      {sharing && <ShareDialog catalogue={sharing} onClose={() => { setSharing(null); load(); }} />}
    </>
  );
}

function CatalogueCard({ c, can, isAdmin, vendorMode, onImport, onRegenerate, onShare, onNewVersion, onEdit, onArchive, onRestore, onDelete }) {
  const [menu, setMenu] = useState(false);
  const Icon = fileIcon(c.content_type);
  const aud = AUDIENCE[c.audience] || AUDIENCE.external;
  const shareable = c.audience === "external" && c.status === "Current";
  const generated = c.origin === "generated";
  const importable = (c.content_type || "") === "application/pdf";
  const btn = "lx-btn inline-flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed";
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 flex flex-col gap-3" data-testid={`catalogue-${c.id}`}>
      <div className="flex gap-3">
        <span className="lx-tile shrink-0" style={{ background: OBJECT_COLOR.catalogues }} aria-hidden="true"><Icon size={18} /></span>
        <div className="min-w-0 flex-1">
          <div className="font-semibold leading-snug">{c.title}</div>
          <div className="text-xs text-[var(--color-text-muted)] flex flex-wrap gap-x-2">
            <span>{c.division === "All" ? "All divisions" : c.division}</span>
            {c.kind && <span>· {c.kind}</span>}
            <span>· v{c.version}</span>
            {vendorMode && (c.vendor_name || c.vendor_code) && <span data-testid={`catalogue-vendor-${c.id}`}>· {c.vendor_name || c.vendor_code}</span>}
          </div>
        </div>
        <div className="relative">
          <button type="button" className="lx-icon-btn" onClick={() => setMenu((m) => !m)} aria-label="More actions" aria-expanded={menu}
                  data-testid={`catalogue-menu-${c.id}`}><MoreHorizontal size={16} /></button>
          {menu && (
            <div className="absolute right-0 mt-1 w-48 z-20 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg shadow-lg py-1 text-sm"
                 onMouseLeave={() => setMenu(false)}>
              {can("edit") && <MenuItem Icon={Pencil} onClick={() => { setMenu(false); onEdit(); }}>Edit details</MenuItem>}
              {can("create") && c.status === "Current" && (generated
                ? <MenuItem Icon={RefreshCw} onClick={() => { setMenu(false); onRegenerate(); }} testid={`catalogue-regenerate-${c.id}`}>Make again with today's prices</MenuItem>
                : <MenuItem Icon={Upload} onClick={() => { setMenu(false); onNewVersion(); }} testid={`catalogue-newversion-${c.id}`}>Publish new version</MenuItem>)}
              {generated && c.kit_url && <MenuItem Icon={PackageOpen} onClick={() => { setMenu(false); downloadFile(`/catalogues/${c.id}/render-kit`, `${c.title} render kit.zip`).catch(() => toast.error("Couldn't download the render kit")); }}>Download render kit</MenuItem>}
              <MenuItem Icon={Download} onClick={() => { setMenu(false); openCatalogueFile(c, true); }}>Download</MenuItem>
              {c.sharepoint_web_url && <MenuItem Icon={ExternalLink} onClick={() => { setMenu(false); window.open(c.sharepoint_web_url, "_blank", "noopener"); }}>Edit in SharePoint</MenuItem>}
              {can("edit") && (c.status === "Current"
                ? <MenuItem Icon={Archive} onClick={() => { setMenu(false); onArchive(); }}>Archive</MenuItem>
                : <MenuItem Icon={ArchiveRestore} onClick={() => { setMenu(false); onRestore(); }}>Make current again</MenuItem>)}
              {isAdmin && <MenuItem Icon={Trash2} danger onClick={() => { setMenu(false); onDelete(); }}>Delete</MenuItem>}
            </div>
          )}
        </div>
      </div>

      <div className="text-xs space-y-1">
        <div className={`inline-flex items-center gap-1 ${aud.tone}`}><aud.Icon size={12} /> {aud.label}</div>
        <div className="text-[var(--color-text-muted)]">
          {c.status === "Current" ? "Published" : "Archived"} {fmtDate(c.status === "Current" ? c.published_at : c.archived_at)} by {c.created_by}
          {c.valid_from && <> · valid from {fmtDate(c.valid_from)}</>}
        </div>
        <div className="text-[var(--color-text-muted)] truncate" title={c.file_name}>
          {c.source === "sharepoint" ? "SharePoint · " : ""}{c.file_name}{c.size_bytes ? ` · ${size(c.size_bytes)}` : ""}
        </div>
        {generated && <div className="inline-flex items-center gap-1 text-[var(--color-primary)]"><Sparkles size={12} /> Made from the Virtual Catalogue · {c.item_count || (c.item_ids || []).length} products{c.render_kit ? " · with render kit" : ""}</div>}
        {c.notes && <div className="text-[var(--color-text)] line-clamp-2">{c.notes}</div>}
        {(c.share_count > 0 || c.view_count > 0) && (
          <div className="text-[var(--color-text-muted)]">
            {c.share_count} active link{c.share_count === 1 ? "" : "s"} · opened {c.view_count} time{c.view_count === 1 ? "" : "s"}
            {c.last_viewed_at && <> · last {fmtRelativeDateTime(c.last_viewed_at)}</>}
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2 mt-auto">
        <button type="button" className={btn} onClick={() => openCatalogueFile(c)} data-testid={`catalogue-open-${c.id}`}><Eye size={14} /> Open</button>
        {vendorMode ? (
          <button type="button" className={`${btn} lx-btn-brand`} onClick={onImport} disabled={!importable || c.status !== "Current"}
                  title={importable ? "Read its products into the Virtual Catalogue, without the vendor's name" : "Only PDF brochures can be imported"}
                  data-testid={`catalogue-import-${c.id}`}><Boxes size={14} /> Import products</button>
        ) : (
          <button type="button" className={`${btn} ${shareable ? "lx-btn-brand" : ""}`} onClick={onShare} disabled={!shareable}
                  title={shareable ? "Share a link with a customer or architect" : c.status !== "Current" ? "Only the current version can be shared" : "Staff-only catalogues can't be shared outside"}
                  data-testid={`catalogue-share-${c.id}`}><Share2 size={14} /> Share</button>
        )}
      </div>
    </div>
  );
}

function MenuItem({ Icon, children, onClick, danger, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid}
            className={`w-full text-left px-3 py-1.5 inline-flex items-center gap-2 hover:bg-[var(--color-surface-muted)] ${danger ? "text-[var(--color-danger)]" : ""}`}>
      <Icon size={14} /> {children}
    </button>
  );
}

function MetaFields({ form, set, optional, vendorMode }) {
  const { divisions } = useTenantConfig();
  const field = "w-full px-2.5 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm";
  return (
    <>
      <label className="block text-sm space-y-1">
        <span className="font-medium">Title</span>
        <input className={field} value={form.title} onChange={(e) => set({ title: e.target.value })} required={!optional}
               placeholder={optional || "e.g. Furniture price list 2026"} data-testid="catalogue-title" />
      </label>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <label className="block text-sm space-y-1">
          <span className="font-medium">Division</span>
          <select className={field} value={form.division} onChange={(e) => set({ division: e.target.value })} data-testid="catalogue-form-division">
            <option value="All">All divisions</option>
            {divisions.map((d) => <option key={d.id || d.slug} value={d.slug}>{d.slug}</option>)}
          </select>
        </label>
        <label className="block text-sm space-y-1">
          <span className="font-medium">Type</span>
          <PicklistSelect list="catalogue_types" value={form.kind} onChange={(v) => set({ kind: v })} className={field} testId="catalogue-kind" />
        </label>
        <label className="block text-sm space-y-1">
          <span className="font-medium">Valid from</span>
          <input type="date" className={field} value={form.valid_from} onChange={(e) => set({ valid_from: e.target.value })} />
        </label>
      </div>
      {vendorMode ? (
        <div className="space-y-1">
          <span className="text-sm font-medium">Vendor</span>
          <VendorSelect value={form.vendor_id} onChange={(v) => set({ vendor_id: v })} testId="catalogue-vendor" />
          <p className="text-xs text-[var(--color-text-muted)] inline-flex items-center gap-1"><ShieldCheck size={12} /> Kept for landing-price holders only; never shared outside.</p>
        </div>
      ) : (
      <fieldset className="space-y-1.5">
        <legend className="text-sm font-medium mb-1">Who is it for?</legend>
        {Object.entries(AUDIENCE).map(([k, a]) => (
          <label key={k} className={`flex items-start gap-2 rounded-lg border p-2.5 text-sm cursor-pointer ${form.audience === k ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)]" : "border-[var(--color-border)]"}`}>
            <input type="radio" name="audience" value={k} checked={form.audience === k} onChange={() => set({ audience: k })} className="mt-0.5" data-testid={`catalogue-audience-${k}`} />
            <span><span className="font-medium inline-flex items-center gap-1"><a.Icon size={13} /> {a.label}</span>
              <span className="block text-xs text-[var(--color-text-muted)]">{a.help}</span></span>
          </label>
        ))}
      </fieldset>
      )}
      <label className="block text-sm space-y-1">
        <span className="font-medium">Notes <span className="font-normal text-[var(--color-text-muted)]">(staff only)</span></span>
        <textarea className={field} rows={2} value={form.notes} onChange={(e) => set({ notes: e.target.value })}
                  placeholder="What changed, who it's for…" />
      </label>
    </>
  );
}

function PublishDialog({ replaces, vendorMode, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: "", division: replaces?.division || "All", kind: replaces?.kind || (vendorMode ? "Brochure" : ""),
    audience: vendorMode ? "restricted" : (replaces?.audience || "external"), valid_from: "", notes: "",
    ...(vendorMode ? { vendor_id: replaces?.vendor_id || "" } : {}),
  });
  const set = (p) => setForm((f) => ({ ...f, ...p }));
  const [source, setSource] = useState("upload");
  const [file, setFile] = useState(null);
  const [sp, setSp] = useState(null);           // {folder, files} | {error}
  const [spRef, setSpRef] = useState("");
  const [saving, setSaving] = useState(false);

  const loadSp = useCallback(() => {
    setSp(null);
    api.get("/catalogues/sharepoint-files", { skipCache: true })
      .then(({ data }) => setSp(data))
      .catch((e) => setSp({ error: formatApiError(e.response?.data?.detail) || "Couldn't read SharePoint" }));
  }, []);
  useEffect(() => { if (source === "sharepoint" && !sp) loadSp(); }, [source, sp, loadSp]);

  const submit = async (e) => {
    e.preventDefault();
    if (source === "upload" && !file) { toast.error("Choose the file"); return; }
    if (source === "sharepoint" && !spRef) { toast.error("Pick a file from SharePoint"); return; }
    if (vendorMode && !replaces && !form.vendor_id) { toast.error("Pick the vendor"); return; }
    const fd = new FormData();
    if (vendorMode) fd.append("origin", "vendor");
    Object.entries(form).forEach(([k, v]) => fd.append(k, v ?? ""));
    if (replaces) fd.append("replaces", replaces.id);
    if (source === "upload") fd.append("file", file); else fd.append("sharepoint_ref", spRef);
    setSaving(true);
    try {
      await api.post("/catalogues", fd);
      toast.success(replaces ? "New version published; the earlier one is archived" : "Catalogue published");
      onSaved();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Couldn't publish");
    } finally { setSaving(false); }
  };

  return (
    <Modal title={replaces ? `New version of “${replaces.title}”` : vendorMode ? "Add a vendor brochure" : "Publish a catalogue"} onClose={onClose} testid="catalogue-publish">
      <form onSubmit={submit} className="p-5 space-y-4">
        {replaces && <p className="text-sm text-[var(--color-text-muted)]">This becomes v{replaces.version + 1}. Version {replaces.version} is archived, and links already shared show the new file. Leave fields blank to keep them as they are.</p>}
        <div className="inline-flex rounded-lg border border-[var(--color-border)] overflow-hidden text-sm" role="tablist">
          {[["upload", "Upload a file", Upload], ["sharepoint", "From SharePoint", FolderOpen]].map(([k, l, I]) => (
            <button key={k} type="button" role="tab" aria-selected={source === k} onClick={() => setSource(k)}
                    className={`px-3 py-1.5 inline-flex items-center gap-1.5 ${source === k ? "bg-[var(--color-primary)] text-white" : ""}`}
                    data-testid={`catalogue-source-${k}`}><I size={14} /> {l}</button>
          ))}
        </div>
        {source === "upload" ? (
          <label className="block rounded-lg border border-dashed border-[var(--color-border)] p-4 text-sm text-center cursor-pointer">
            <input type="file" accept={ACCEPT} className="sr-only" data-testid="catalogue-file"
                   onChange={(e) => { const f = e.target.files?.[0] || null; setFile(f); if (f && !form.title && !replaces) set({ title: f.name.replace(/\.[^.]+$/, "") }); }} />
            {file ? <span className="font-medium">{file.name} · {size(file.size)}</span>
              : <span>Choose a PDF, image, Excel, Word, PowerPoint or ZIP (up to 50 MB)</span>}
          </label>
        ) : (
          <div className="rounded-lg border border-[var(--color-border)] p-3 text-sm space-y-2" data-testid="catalogue-sharepoint">
            {!sp ? <div className="text-[var(--color-text-muted)]">Reading SharePoint…</div> : sp.error ? (
              <div className="text-[var(--color-danger)]">{sp.error}</div>
            ) : (
              <>
                <div className="flex items-center justify-between gap-2 text-xs text-[var(--color-text-muted)]">
                  <span>Files in <b className="font-mono">{sp.folder}</b>. Edits made there show here straight away.</span>
                  <button type="button" onClick={loadSp} aria-label="Refresh"><RefreshCw size={13} /></button>
                </div>
                {!sp.files.length && <div className="text-[var(--color-text-muted)]">That folder is empty. Put the catalogue files there in SharePoint, then refresh.</div>}
                <ul className="max-h-56 overflow-y-auto divide-y divide-[var(--color-border)]">
                  {sp.files.map((f) => (
                    <li key={f.ref}>
                      <label className="flex items-center gap-2 py-1.5 cursor-pointer">
                        <input type="radio" name="spfile" checked={spRef === f.ref}
                               onChange={() => { setSpRef(f.ref); if (!form.title && !replaces) set({ title: f.name.replace(/\.[^.]+$/, "") }); }} />
                        <span className="flex-1 min-w-0 truncate">{f.name}</span>
                        <span className="text-xs text-[var(--color-text-muted)] shrink-0">
                          {f.linked_to ? `used by “${f.linked_to}”` : f.modified ? `edited ${fmtDate(f.modified)}` : ""}{f.size ? ` · ${size(f.size)}` : ""}
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
        <MetaFields form={form} set={set} optional={replaces ? replaces.title : ""} vendorMode={vendorMode} />
        <div className="flex justify-end gap-2">
          <button type="button" className="lx-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="lx-btn lx-btn-brand" disabled={saving} data-testid="catalogue-publish-submit">{saving ? "Publishing…" : "Publish"}</button>
        </div>
      </form>
    </Modal>
  );
}

function EditDialog({ c, vendorMode, onClose, onSaved }) {
  const [form, setForm] = useState({ title: c.title, division: c.division, kind: c.kind || "", audience: c.audience,
                                     valid_from: c.valid_from || "", notes: c.notes || "",
                                     ...(vendorMode ? { vendor_id: c.vendor_id || "" } : {}) });
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (c.audience === "external" && form.audience !== "external" && c.share_count > 0 &&
        !window.confirm(`${c.share_count} link(s) shared outside will stop working. Continue?`)) return;
    setSaving(true);
    try { await api.put(`/catalogues/${c.id}`, form); toast.success("Saved"); onSaved(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Couldn't save"); }
    finally { setSaving(false); }
  };
  return (
    <Modal title={`Edit “${c.title}”`} onClose={onClose} testid="catalogue-edit">
      <form onSubmit={submit} className="p-5 space-y-4">
        <MetaFields form={form} set={(p) => setForm((f) => ({ ...f, ...p }))} vendorMode={vendorMode} />
        <div className="flex justify-end gap-2">
          <button type="button" className="lx-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="lx-btn lx-btn-brand" disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}

function Modal({ title, onClose, children, testid }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-start sm:items-center justify-center p-3" role="dialog" aria-modal="true" aria-label={title}>
      <div className="bg-[var(--color-surface)] rounded-xl shadow-2xl w-full max-w-xl max-h-[92vh] overflow-y-auto" data-testid={testid}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)]">
          <h2 className="font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
