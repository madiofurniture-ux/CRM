import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Copy, Link2, Mail, MessageCircle, X, Ban, Eye, Download } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { fmtDate, fmtRelativeDateTime } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import CustomerProjectPicker from "@/components/CustomerProjectPicker";
import SearchSelect from "@/components/SearchSelect";

export const EXPIRY_OPTIONS = [[7, "7 days"], [30, "30 days"], [90, "90 days"], [365, "1 year"], [0, "No expiry"]];

/** The public address of a share link (served by this same site). */
export const shareUrl = (token) => `${window.location.origin}/c/${token}`;

const digits = (p) => String(p || "").replace(/\D/g, "");
export function whatsappHref(phone, text) {
  let d = digits(phone);
  if (d.length === 10) d = `91${d}`;
  return `https://wa.me/${d}?text=${encodeURIComponent(text)}`;
}
export const shareMessage = (share, company) =>
  `Hello${share.recipient_name ? ` ${share.recipient_name}` : ""}, here is the ${share.catalogue_title}` +
  `${company ? ` from ${company}` : ""}. This link always opens the latest version: ${shareUrl(share.token)}`;

/** Open (or download) a catalogue's file as the signed-in user. The file
 * route needs the login token, so it is fetched, not linked. */
export async function openCatalogueFile(cat, download = false) {
  const tab = download ? null : window.open("", "_blank");
  try {
    const { data } = await api.get(`/catalogues/${cat.id}/file${download ? "?download=true" : ""}`,
                                   { responseType: "blob", skipCache: true });
    const url = URL.createObjectURL(data);
    if (tab && !download && (cat.content_type || "").match(/^(application\/pdf|image\/)/)) {
      tab.location.href = url;
    } else {
      tab?.close();
      const a = document.createElement("a");
      a.href = url; a.download = cat.file_name || "catalogue"; a.click();
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (e) {
    tab?.close();
    toast.error(e?.response?.status === 502 ? "Couldn't fetch the file from SharePoint" : "Couldn't open the catalogue");
  }
}

const STATE_TONE = { active: "text-[var(--color-success)]", expired: "text-[var(--color-text-muted)]", revoked: "text-[var(--color-danger)]" };

function ShareActions({ share, company }) {
  const copy = async () => {
    try { await navigator.clipboard.writeText(shareUrl(share.token)); toast.success("Link copied"); }
    catch { window.prompt("Copy this link", shareUrl(share.token)); }
  };
  const msg = shareMessage(share, company);
  return (
    <div className="flex flex-wrap gap-1.5">
      <button type="button" className="lx-btn inline-flex items-center gap-1" onClick={copy} data-testid={`share-copy-${share.id}`}><Copy size={13} /> Copy link</button>
      <a className="lx-btn inline-flex items-center gap-1 text-[var(--color-success)]" href={whatsappHref(share.recipient_phone, msg)}
         target="_blank" rel="noreferrer"><MessageCircle size={13} /> WhatsApp</a>
      <a className="lx-btn inline-flex items-center gap-1"
         href={`mailto:${share.recipient_email || ""}?subject=${encodeURIComponent(share.catalogue_title)}&body=${encodeURIComponent(msg)}`}>
        <Mail size={13} /> Email</a>
    </div>
  );
}

/** Links already given out (for one catalogue, or one customer), with views
 * and a way to switch a link off. */
export function SharedLinks({ rows, onChanged, showCatalogue = false, testid = "shared-links" }) {
  const { tenant } = useAuth();
  const company = tenant?.display_name || tenant?.name || "";
  const revoke = async (s) => {
    if (!window.confirm(`Stop the link shared with ${s.recipient_name}? It will no longer open.`)) return;
    try { await api.delete(`/catalogue-shares/${s.id}`); toast.success("Link stopped"); onChanged?.(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't stop the link"); }
  };
  if (!rows?.length) return <div className="text-sm text-[var(--color-text-muted)]" data-testid={testid}>Nothing shared yet.</div>;
  return (
    <ul className="divide-y divide-[var(--color-border)]" data-testid={testid}>
      {rows.map((s) => (
        <li key={s.id} className="py-2.5 space-y-1.5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div className="min-w-0">
              <div className="text-sm font-medium truncate">
                {showCatalogue ? s.catalogue_title : s.recipient_name}
                <span className="ml-2 text-xs font-normal text-[var(--color-text-muted)] capitalize">
                  {showCatalogue ? `to ${s.recipient_name}` : s.recipient_type}
                </span>
              </div>
              <div className="text-xs text-[var(--color-text-muted)]">
                Shared {fmtDate(s.created_at)} by {s.created_by}
                {" · "}{s.expires_at ? `${s.state === "expired" ? "expired" : "until"} ${fmtDate(s.expires_at)}` : "no expiry"}
                {s.follow_latest ? " · always latest" : " · this version only"}
              </div>
            </div>
            <div className="text-xs flex items-center gap-3">
              <span className="inline-flex items-center gap-1" title="Times opened"><Eye size={12} /> {s.views || 0}</span>
              <span className="inline-flex items-center gap-1" title="Downloads"><Download size={12} /> {s.downloads || 0}</span>
              <span className={`capitalize font-medium ${STATE_TONE[s.state] || ""}`}>{s.state}</span>
            </div>
          </div>
          {s.last_viewed_at && <div className="text-xs text-[var(--color-text-muted)]">Last opened {fmtRelativeDateTime(s.last_viewed_at)}</div>}
          {s.state === "active" && (
            <div className="flex flex-wrap items-center gap-1.5">
              <ShareActions share={s} company={company} />
              <button type="button" className="lx-btn inline-flex items-center gap-1 text-[var(--color-danger)]" onClick={() => revoke(s)}
                      data-testid={`share-revoke-${s.id}`}><Ban size={13} /> Stop link</button>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Share a catalogue outside the company. Pass `catalogue`, or leave it out
 * to pick one (the customer page). `customer` pre-selects the recipient. */
export default function ShareDialog({ catalogue: given, customer, onClose, onShared }) {
  const { tenant } = useAuth();
  const company = tenant?.display_name || tenant?.name || "";
  const [catalogues, setCatalogues] = useState([]);
  const [catId, setCatId] = useState(given?.id || "");
  const [kind, setKind] = useState("customer");
  const [customerId, setCustomerId] = useState(customer?.id || "");
  const [architects, setArchitects] = useState([]);
  const [architectId, setArchitectId] = useState("");
  const [other, setOther] = useState({ recipient_name: "", recipient_phone: "", recipient_email: "" });
  const [days, setDays] = useState(30);
  const [followLatest, setFollowLatest] = useState(true);
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState(null);
  const [existing, setExisting] = useState([]);

  const catalogue = given || catalogues.find((c) => c.id === catId);
  const loadExisting = () => {
    if (!catalogue?.id) { setExisting([]); return; }
    api.get(`/catalogues/${catalogue.id}/shares`, { skipCache: true }).then(({ data }) => setExisting(data || [])).catch(() => {});
  };
  useEffect(() => {
    if (!given) api.get("/catalogues?status=Current").then(({ data }) => setCatalogues((data || []).filter((c) => c.audience === "external"))).catch(() => {});
  }, [given]);
  useEffect(() => {
    if (kind === "architect" && !architects.length) api.get("/architects").then(({ data }) => setArchitects(data || [])).catch(() => {});
  }, [kind, architects.length]);
  useEffect(loadExisting, [catalogue?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const archOptions = useMemo(() => architects.map((a) => ({ id: a.id, label: a.name, sub: [a.firm, a.phone].filter(Boolean).join(" · ") })), [architects]);

  const submit = async (e) => {
    e.preventDefault();
    if (!catalogue) { toast.error("Pick a catalogue"); return; }
    setSaving(true);
    try {
      const payload = { recipient_type: kind, expires_days: days, follow_latest: followLatest,
                        ...(kind === "customer" ? { customer_id: customerId } : {}),
                        ...(kind === "architect" ? { architect_id: architectId } : {}),
                        ...(kind === "other" ? other : {}) };
      const { data } = await api.post(`/catalogues/${catalogue.id}/shares`, payload);
      setCreated(data);
      loadExisting();
      onShared?.(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Couldn't create the link");
    } finally { setSaving(false); }
  };

  const field = "w-full px-2.5 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm";
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-start sm:items-center justify-center p-3" role="dialog" aria-modal="true" aria-labelledby="share-title">
      <div className="bg-[var(--color-surface)] rounded-xl shadow-2xl w-full max-w-xl max-h-[92vh] overflow-y-auto" data-testid="catalogue-share-dialog">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)]">
          <h2 id="share-title" className="font-semibold flex items-center gap-2"><Link2 size={16} /> Share {catalogue ? `“${catalogue.title}”` : "a catalogue"}</h2>
          <button type="button" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>

        {created ? (
          <div className="p-5 space-y-3" data-testid="share-created">
            <div className="text-sm">Link ready for <b>{created.recipient_name}</b>
              {created.expires_at ? `, working until ${fmtDate(created.expires_at)}` : ", with no expiry"}.
              {created.follow_latest && " It always opens the newest version."}</div>
            <input readOnly value={shareUrl(created.token)} className={`${field} font-mono text-xs`} onFocus={(e) => e.target.select()} data-testid="share-url" />
            <ShareActions share={created} company={company} />
            <button type="button" className="text-sm text-[var(--color-primary)]" onClick={() => setCreated(null)}>Share with someone else</button>
          </div>
        ) : (
          <form onSubmit={submit} className="p-5 space-y-4">
            {!given && (
              <label className="block text-sm space-y-1">
                <span className="font-medium">Catalogue</span>
                <select value={catId} onChange={(e) => setCatId(e.target.value)} className={field} required data-testid="share-catalogue">
                  <option value="">Pick a catalogue…</option>
                  {catalogues.map((c) => <option key={c.id} value={c.id}>{c.title} · {c.division} · v{c.version}</option>)}
                </select>
                {!catalogues.length && <span className="text-xs text-[var(--color-text-muted)]">No catalogues are marked for customers and architects yet.</span>}
              </label>
            )}
            <div className="space-y-1.5">
              <div className="text-sm font-medium">Share with</div>
              <div className="inline-flex rounded-lg border border-[var(--color-border)] overflow-hidden text-sm" role="radiogroup">
                {[["customer", "Customer"], ["architect", "Architect"], ["other", "Someone else"]].map(([k, l]) => (
                  <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}
                          className={`px-3 py-1.5 ${kind === k ? "bg-[var(--color-primary)] text-white" : ""}`} data-testid={`share-kind-${k}`}>{l}</button>
                ))}
              </div>
              {kind === "customer" && (customer
                ? <div className="text-sm">{customer.name}{customer.phone ? ` · ${customer.phone}` : ""}</div>
                : <CustomerProjectPicker customerId={customerId} withProject={false} allowNewProject={false} testid="share-cust"
                                         onChange={({ customer: c }) => setCustomerId(c?.id || "")} />)}
              {kind === "architect" && (
                <SearchSelect options={archOptions} value={architectId} onChange={(id) => setArchitectId(id || "")}
                              placeholder="Search architects…" testId="share-architect" />
              )}
              {kind === "other" && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <input className={field} placeholder="Name" value={other.recipient_name} required data-testid="share-other-name"
                         onChange={(e) => setOther({ ...other, recipient_name: e.target.value })} />
                  <input className={field} placeholder="Phone" inputMode="tel" value={other.recipient_phone}
                         onChange={(e) => setOther({ ...other, recipient_phone: e.target.value })} />
                  <input className={field} placeholder="Email" type="email" value={other.recipient_email}
                         onChange={(e) => setOther({ ...other, recipient_email: e.target.value })} />
                </div>
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="block text-sm space-y-1">
                <span className="font-medium">Link works for</span>
                <select value={days} onChange={(e) => setDays(Number(e.target.value))} className={field} data-testid="share-expiry">
                  {EXPIRY_OPTIONS.map(([d, l]) => <option key={d} value={d}>{l}</option>)}
                </select>
              </label>
              <label className="flex items-start gap-2 text-sm pt-6">
                <input type="checkbox" checked={followLatest} onChange={(e) => setFollowLatest(e.target.checked)} className="mt-0.5" />
                <span>Always open the newest version<span className="block text-xs text-[var(--color-text-muted)]">When you publish an update, this link shows it.</span></span>
              </label>
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" className="lx-btn" onClick={onClose}>Cancel</button>
              <button type="submit" className="lx-btn lx-btn-brand" disabled={saving || !catalogue} data-testid="share-create">{saving ? "Creating…" : "Create link"}</button>
            </div>
          </form>
        )}

        {catalogue && (
          <div className="px-5 pb-5">
            <div className="text-sm font-medium mb-1 pt-3 border-t border-[var(--color-border)]">Links already shared</div>
            <SharedLinks rows={existing} onChanged={loadExisting} testid="share-existing" />
          </div>
        )}
      </div>
    </div>
  );
}
