import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import StageProgressBar from "@/components/StageProgressBar";
import LogTimeline from "@/components/LogTimeline";
import AttachmentPanel from "@/components/AttachmentPanel";
import ProductPicker, { StockBadge, rateFromMrp } from "@/components/ProductPicker";
import { downloadPdf } from "@/lib/pdf";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { shrinkImage } from "@/lib/image";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { ChevronLeft, Plus, Trash2, ArrowRightCircle, GitBranch, FileDown, SlidersHorizontal, FolderPlus, ImagePlus, X } from "lucide-react";

// Full detail workspace for one quote: line-item builder, discount + approval, versions.
export default function QuoteWorkspace() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [ws, setWs] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [pipeline, setPipeline] = useState(null);
  const [tab, setTab] = useState("lines");
  const [busy, setBusy] = useState(false);
  const lineTimers = useRef({});   // per-line debounce timers, kept across renders
  const [stock, setStock] = useState({});   // sku -> live stock for inventory-linked lines
  // Group new lines are added under (a floor, a room, "Doors"); groups that
  // have no lines yet live only here until their first line is added.
  const [curGroup, setCurGroup] = useState("");
  const [newGroups, setNewGroups] = useState([]);

  const load = useCallback(async () => {
    try {
      setLoadError(false);
      // Always fresh: line edits are written to /quote-lines, which doesn't
      // clear the cached /quotes/... workspace, so a cached read hid new lines.
      const { data } = await api.get(`/quotes/${id}/workspace`, { skipCache: true });
      setWs(data);
      if (data.quote?.phone) {
        try { const { data: j } = await api.get(`/journey/${data.quote.phone}`); setPipeline(j.pipeline || null); }
        catch { /* progress bar is a nice-to-have; the workspace still works without it */ }
      }
    }
    catch { toast.error("Quote not found"); setLoadError(true); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  const skuList = (ws?.lines || []).map((l) => l.sku).filter(Boolean).sort().join(",");
  useEffect(() => {
    if (!skuList) { setStock({}); return; }
    api.get(`/inventory/lookup?skus=${encodeURIComponent(skuList)}`, { skipCache: true })
      .then(({ data }) => setStock(Object.fromEntries((data || []).map((r) => [r.sku, r]))))
      .catch(() => setStock({}));
  }, [skuList]);

  // Without the error branch a failed fetch left `ws` null forever, so the
  // page sat on "Loading…" with no way back.
  if (loadError) return (
    <><Topbar title="Quote Workspace" />
      <div className="p-10 text-center space-y-3" data-testid="quote-workspace-error">
        <div className="text-sm text-[var(--ink-2)]">This quote could not be loaded.</div>
        <div className="text-xs text-[var(--ink-3)]">It may have been deleted, or the connection dropped.</div>
        <div className="flex items-center justify-center gap-2 pt-1">
          <button onClick={load} className="btn-primary px-4">Retry</button>
          <button onClick={() => nav("/quotes")} className="px-4 py-2 rounded-lg border border-[var(--border)] text-sm">Back to Quotes</button>
        </div>
      </div></>
  );

  if (!ws) return <><Topbar title="Quote Workspace" /><div className="p-10 text-center text-[var(--ink-3)]">Loading…</div></>;

  const q = ws.quote;
  // Division preset: Doors & Windows quotes take W/H in mm (sft = W×H/90,000)
  // and an opening specification per line; see quotation_templates.py.
  const preset = ws.preset || {};
  const mm = preset.dims === "mm";
  const specFields = preset.spec_fields || [];
  const isAdmin = user?.role === "admin";
  const rejected = q.approval === "rejected";
  // Rejected must block conversion too — checking only "pending" meant a
  // refused discount unlocked the Convert button instead of holding it.
  const pending = q.approval === "pending" || rejected;

  const addLine = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await api.post("/quote-lines", {
        quote_id: id, version: q.version || 1, description: "", w: 0, h: 0, qty: 1, rate: 0, group: curGroup,
        ...(mm ? { dim_unit: "mm", specs: { ...(preset.spec_defaults || {}) } } : {}),
      });
      await load();
    }
    finally { setBusy(false); }
  };
  // Debounced per-line save so rapid keystrokes collapse into one write.
  const patchLine = (line, changes) => {
    const merged = { ...line, ...changes };
    setWs((p) => ({ ...p, lines: p.lines.map((l) => l.id === line.id ? merged : l) }));
    clearTimeout(lineTimers.current[line.id]);
    lineTimers.current[line.id] = setTimeout(async () => {
      await api.put(`/quote-lines/${line.id}`, merged);
      load();
    }, 700);
  };
  const removeLine = async (lid) => { await api.delete(`/quote-lines/${lid}`); load(); };
  // Groups in order of first appearance, as the quotation prints them.
  const lineGroups = [];
  for (const l of ws.lines) {
    const g = (l.group || "").trim();
    if (!lineGroups.includes(g)) lineGroups.push(g);
  }
  const groupNames = [...lineGroups.filter(Boolean), ...newGroups.filter((g) => !lineGroups.includes(g))];
  const grouped = lineGroups.some(Boolean);
  const groupSummary = Object.fromEntries((ws.summary?.groups || []).map((g) => [g.name, g]));
  const addGroup = () => {
    const name = (window.prompt("Group name — a floor, a room, or e.g. “Doors”") || "").trim();
    if (!name) return;
    if (!groupNames.includes(name)) setNewGroups((p) => [...p, name]);
    setCurGroup(name);
  };
  const pickPicture = async (line, file) => {
    try { patchLine(line, { image_url: await shrinkImage(file, 800) }); }
    catch (e) { toast.error(e.message || "Could not use that picture"); }
  };
  // A product from inventory becomes a priced line; MRP includes GST, so the
  // pre-GST rate is used because the quote adds GST on its total.
  const addProduct = async (item) => {
    if (busy) return;
    setBusy(true);
    try {
      const taxPct = q.tax_pct ?? 18;
      await api.post("/quote-lines", {
        quote_id: id, version: q.version || 1, w: 0, h: 0, qty: 1, group: curGroup,
        description: [item.name, item.model_no, item.material_finish].filter(Boolean).join(" · "),
        rate: rateFromMrp(item.mrp, item.gst_pct ?? taxPct), sku: item.sku, unit: item.unit, hsn: item.hsn,
        // Same basis as the rate (before GST): the price-list quotation prints both.
        mrp: rateFromMrp(item.mrp, item.gst_pct ?? taxPct),
      });
      if (item.available <= 0) toast.warning(`${item.name}: none available in stock right now`);
      await load();
    } finally { setBusy(false); }
  };

  const setPrintLayout = async (value) => {
    try { await api.put(`/quotes/${id}`, { print_layout: value }); await load(); }
    catch { toast.error("Couldn't change the layout"); }
  };

  const getPdf = async () => {
    try { await downloadPdf(`/quotes/${id}/pdf`, `Quotation ${ws?.quote?.quote_no || id}`); }
    catch { toast.error("Couldn't build the PDF"); }
  };

  const saveTotal = async (discount, transport, tax_pct) => {
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/quotes/${id}/save-total`, { discount, transport, tax_pct });
      setWs((p) => ({ ...p, quote: data }));
      toast.success("Totals saved to quote");
      await load();
    } finally { setBusy(false); }
  };
  const approve = async (ok) => {
    if (busy) return;
    setBusy(true);
    try { await api.post(`/quotes/${id}/approve`, { approved: ok }); toast.success(ok ? "Approved" : "Rejected"); await load(); }
    finally { setBusy(false); }
  };
  const revise = async () => {
    if (busy) return;
    if (!window.confirm("Start a new revision? Current lines are copied forward.")) return;
    setBusy(true);
    try { const { data } = await api.post(`/quotes/${id}/revise`); toast.success(`Now v${data.version}`); await load(); }
    finally { setBusy(false); }
  };
  const convert = async () => {
    if (busy) return;
    if (!isAdmin) { toast.error("Only an admin can convert a quote to a sale"); return; }
    if (pending) { toast.error("Approve the discount before converting"); return; }
    if (!window.confirm(`Convert ${q.quote_no} to a sale?`)) return;
    setBusy(true);
    try { const { data } = await api.post(`/convert/quote-to-sale/${id}`); toast.success(`Sale ${data.sale_no} created`); await load(); }
    finally { setBusy(false); }
  };

  const setValidity = async (value) => {
    if (busy || !value) return;
    setBusy(true);
    try { await api.put(`/quotes/${id}`, { valid_until: value }); await load(); }
    catch { toast.error("Couldn't update the validity date"); }
    finally { setBusy(false); }
  };

  return (
    <>
      <Topbar title={`${q.quote_no}${q.version > 1 ? ` · v${q.version}` : ""}`} subtitle={q.customer}
        actions={
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            <span className="hidden sm:inline-flex"><StageBadge stage={q.derived_status} /></span>
            <button onClick={getPdf} className="btn-ghost" data-testid="quote-pdf" aria-label="PDF"><FileDown size={14} /><span className="hidden sm:inline"> PDF</span></button>
            <button onClick={revise} disabled={busy} className="btn-ghost disabled:opacity-60" aria-label="Revise"><GitBranch size={14} /><span className="hidden sm:inline"> Revise</span></button>
            {ws.sale ? (
              <button onClick={() => nav(`/sales?q=${encodeURIComponent(ws.sale.sale_no || "")}`)} className="btn-primary" data-testid="quote-open-sale"
                      aria-label={`Open sale ${ws.sale.sale_no}`}><ArrowRightCircle size={15} /><span className="hidden sm:inline"> Sale {ws.sale.sale_no}</span></button>
            ) : (
              <button onClick={convert} disabled={pending || busy || !isAdmin} aria-label="Convert to Sale" data-testid="quote-convert"
                title={!isAdmin ? "Admin approval required to convert a quote to a sale" : undefined}
                className={`btn-primary ${pending || busy || !isAdmin ? "opacity-50 cursor-not-allowed" : ""}`}><ArrowRightCircle size={15} /><span className="hidden sm:inline"> Convert to Sale</span></button>
            )}
          </div>
        } />
      <div className="p-6 space-y-4" data-testid="quote-workspace">
        <button onClick={() => nav("/quotes")} className="text-sm text-[var(--ink-2)] inline-flex items-center gap-1"><ChevronLeft size={14} /> All deals</button>
        {pipeline && <StageProgressBar stages={pipeline} />}

        <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="quote-validity">
          <span className="text-[var(--ink-2)]">Offer valid until</span>
          <input type="date" value={q.valid_until || ""} onChange={(e) => setValidity(e.target.value)} disabled={busy}
                 className="px-2 py-1 rounded border border-[var(--border)] bg-white text-sm" aria-label="Offer valid until" />
          {q.expired && (
            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-[var(--danger-soft)] text-[var(--danger)]">
              Expired {fmtDate(q.valid_until)}. Extend the date or revise the quote before the customer accepts.
            </span>
          )}
        </div>

        {pending && (
          <div className="bg-[var(--warn-soft)] border border-[var(--warn)] rounded-lg px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-[var(--ink)]">
              {rejected
                ? `Discount ${inrFull(q.discount)} was rejected — lower it or ask an admin again.`
                : `Discount ${inrFull(q.discount)} exceeds 10% of subtotal — needs approval.`}
            </span>
            {isAdmin
              ? <div className="flex gap-2"><button onClick={() => approve(true)} className="btn-primary">Approve</button><button onClick={() => approve(false)} className="btn-ghost text-[var(--danger)]">Reject</button></div>
              : <span className="text-xs text-[var(--ink-3)]">Awaiting an admin</span>}
          </div>
        )}
        {q.approval === "approved" && <div className="text-xs text-[var(--moss)]">✓ Discount approved</div>}

        <div className="flex gap-1 border-b border-[var(--border)]">
          {["lines", "versions", "followups", "attachments"].map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === t ? "border-[var(--brand)] text-[var(--brand)]" : "border-transparent text-[var(--ink-3)]"}`}>
              {t === "lines" ? "Line Items" : t === "versions" ? "Versions" : t === "followups" ? "Follow-ups" : "Attachments"}
            </button>
          ))}
        </div>

        {tab === "lines" && (
          <>
            <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl overflow-hidden">
              <div className="p-3 border-b border-[var(--border-light)] flex justify-between items-center">
                <div className="font-heading font-semibold text-sm">Line items</div>
                <div className="flex items-center gap-2 flex-wrap justify-end">
                  {(preset.print_layouts || []).length > 0 && (
                    <select value={q.print_layout || ""} onChange={(e) => setPrintLayout(e.target.value)} title="How the PDF is laid out"
                            className="px-2 py-1.5 rounded-lg border border-[var(--border)] bg-white text-sm max-w-[13rem]" data-testid="quote-print-layout">
                      {preset.print_layouts.map((o) => <option key={o.key} value={o.key}>PDF: {o.label}</option>)}
                    </select>
                  )}
                  <select value={curGroup} onChange={(e) => setCurGroup(e.target.value)} title="Group new lines are added under"
                          className="px-2 py-1.5 rounded-lg border border-[var(--border)] bg-white text-sm max-w-[10rem]" data-testid="quote-group-select">
                    <option value="">No group</option>
                    {groupNames.map((g) => <option key={g} value={g}>{g}</option>)}
                  </select>
                  <button onClick={addGroup} className="btn-ghost" data-testid="quote-add-group"><FolderPlus size={14} /> Add group</button>
                  <ProductPicker onPick={addProduct} className="w-56 md:w-72" testId="quote-product-picker" />
                  <button onClick={addLine} disabled={busy} className="btn-ghost disabled:opacity-60"><Plus size={14} /> Add line</button>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-[var(--surface-2)]">
                    <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                      <th className="text-left font-semibold px-3 py-2">Description</th>
                      <th className="text-right font-semibold px-3 py-2">{mm ? "W (mm)" : "W"}</th>
                      <th className="text-right font-semibold px-3 py-2">{mm ? "H (mm)" : "H"}</th>
                      {mm && <th className="text-right font-semibold px-3 py-2">Sft</th>}
                      <th className="text-right font-semibold px-3 py-2">Qty</th>
                      <th className="text-right font-semibold px-3 py-2">{mm ? "Total Sft" : "Sqft"}</th>
                      <th className="text-right font-semibold px-3 py-2">{mm ? "Rate / Sft" : "Rate"}</th>
                      <th className="text-right font-semibold px-3 py-2">Amount</th>
                      <th className="w-8"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {lineGroups.map((g) => (
                      <GroupRows key={g || "_"} name={g} grouped={grouped} cols={mm ? 9 : 8} mm={mm} summary={groupSummary[g]}>
                    {ws.lines.filter((l) => (l.group || "").trim() === g).map((l) => (
                      <LineRows key={l.id} line={l} mm={mm} specFields={specFields} patchLine={patchLine}
                                groups={groupNames} onPicture={pickPicture} showMrp={q.print_layout === "pricelist"}>
                      <tr className="border-t border-[var(--border-light)]">
                        <td className="px-3 py-2"><I v={l.description} oc={(v) => patchLine(l, { description: v })} />
                          {l.sku && (
                            <div className="mt-1 flex items-center gap-1.5 text-[10px] text-[var(--ink-3)]" data-testid={`quote-line-sku-${l.id}`}>
                              <span className="font-mono">{l.sku}</span>
                              <StockBadge item={stock[l.sku]} qty={l.qty} />
                            </div>
                          )}
                        </td>
                        <td className={`px-3 py-2 ${mm ? "w-24" : "w-16"}`}><I t="number" v={l.w} oc={(v) => patchLine(l, { w: parseFloat(v) || 0 })} right /></td>
                        <td className={`px-3 py-2 ${mm ? "w-24" : "w-16"}`}><I t="number" v={l.h} oc={(v) => patchLine(l, { h: parseFloat(v) || 0 })} right /></td>
                        {mm && <td className="px-3 py-2 text-right font-mono text-[var(--ink-3)]">{(l.sft_each || 0).toFixed(2)}</td>}
                        <td className="px-3 py-2 w-16"><I t="number" v={l.qty} oc={(v) => patchLine(l, { qty: parseFloat(v) || 0 })} right /></td>
                        <td className="px-3 py-2 text-right font-mono text-[var(--ink-3)]">{(l.sft || 0).toFixed(2)}</td>
                        <td className="px-3 py-2 w-24"><I t="number" v={l.rate} oc={(v) => patchLine(l, { rate: parseFloat(v) || 0 })} right /></td>
                        <td className="px-3 py-2 text-right font-mono font-semibold">{inrFull(l.amount)}</td>
                        <td className="px-2 py-2"><button onClick={() => removeLine(l.id)} className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button></td>
                      </tr>
                      </LineRows>
                    ))}
                      </GroupRows>
                    ))}
                    {ws.lines.length === 0 && <tr><td colSpan={mm ? 9 : 8} className="text-center py-8 text-[var(--ink-3)]">No line items — add the first.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
            {mm && ws.summary?.sft > 0 && (
              <div className="text-xs text-[var(--ink-2)] flex flex-wrap gap-4" data-testid="quote-summary">
                <span>{preset.line_label || "Openings"}: <b>{ws.summary.openings}</b></span>
                <span>Total area: <b>{ws.summary.sft} sft</b></span>
                <span>Average rate: <b>{inrFull(ws.summary.avg_rate)} / sft</b></span>
              </div>
            )}
            <TotalsBar ws={ws} onSave={saveTotal} busy={busy} transportLabel={`${preset.transport_label || "Transport"} ₹`} />
          </>
        )}

        {tab === "versions" && (
          <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-5">
            <div className="text-sm text-[var(--ink-2)] mb-3">This quote has {ws.versions.length} version(s). Current: <span className="font-semibold">v{q.version}</span>.</div>
            <div className="flex flex-wrap gap-2">
              {ws.versions.map((v) => (
                <span key={v} className={`px-3 py-1.5 rounded-lg text-sm ${v === q.version ? "bg-[var(--brand-soft)] text-[var(--brand)] font-semibold" : "bg-[var(--surface-2)] text-[var(--ink-2)]"}`}>v{v}</span>
              ))}
            </div>
            <div className="text-xs text-[var(--ink-3)] mt-3">“Revise” copies the current line items into a new version and reopens the quote as Sent.</div>
          </div>
        )}

        {tab === "followups" && (
          <LogTimeline
            entity="quote" itemId={q.id} entries={q.log || []}
            onAppended={(log, record) => setWs((p) => ({ ...p, quote: { ...p.quote, ...record, log } }))}
          />
        )}

        {tab === "attachments" && <AttachmentPanel entity="quote" itemId={q.id} />}
      </div>
    </>
  );
}

/** A group's heading, its lines and — once a quote has groups — its subtotal. */
function GroupRows({ name, grouped, cols, mm, summary, children }) {
  if (!grouped) return children;
  return (
    <>
      <tr className="bg-[var(--brand-soft)]/60 border-t border-[var(--border)]">
        <td colSpan={cols} className="px-3 py-1.5 text-xs font-semibold text-[var(--brand)]" data-testid={`quote-group-${name || "other"}`}>{name || "Other items"}</td>
      </tr>
      {children}
      <tr className="border-t border-[var(--border-light)]">
        <td colSpan={cols - 2} className="px-3 py-1.5 text-right text-xs text-[var(--ink-3)]">
          Subtotal — {name || "Other items"}{mm && summary?.sft ? ` · ${summary.sft} sft` : ""}
        </td>
        <td className="px-3 py-1.5 text-right font-mono text-xs font-semibold">{inrFull(summary?.subtotal || 0)}</td>
        <td></td>
      </tr>
    </>
  );
}

/** A line row plus its details: group, picture (printed on the quotation)
 *  and, for Doors & Windows, the opening specification. */
function LineRows({ line, mm, specFields, patchLine, groups, onPicture, showMrp, children }) {
  const [open, setOpen] = useState(false);
  const fileRef = useRef(null);
  const specs = line.specs || {};
  const filled = specFields.filter((f) => String(specs[f.key] || "").trim()).length;
  return (
    <>
      {children}
      <tr className="bg-[var(--surface-2)]/40">
        <td colSpan={mm ? 9 : 8} className="px-3 pb-2">
          <div className="flex flex-wrap items-center gap-3 text-xs">
            {specFields.length > 0 && (
              <button type="button" onClick={() => setOpen((v) => !v)} className="text-[var(--brand)] inline-flex items-center gap-1"
                      data-testid={`quote-line-specs-${line.id}`}>
                <SlidersHorizontal size={12} /> Specification ({filled}/{specFields.length})
              </button>
            )}
            {line.image_url ? (
              <span className="inline-flex items-center gap-1">
                <img src={line.image_url} alt="" className="h-10 w-10 object-contain rounded border border-[var(--border)] bg-white cursor-pointer"
                     onClick={() => fileRef.current?.click()} data-testid={`quote-line-picture-${line.id}`} />
                <button type="button" onClick={() => patchLine(line, { image_url: "" })} title="Remove picture"
                        className="p-0.5 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]"><X size={12} /></button>
              </span>
            ) : (
              <button type="button" onClick={() => fileRef.current?.click()} className="text-[var(--brand)] inline-flex items-center gap-1"
                      data-testid={`quote-line-add-picture-${line.id}`}>
                <ImagePlus size={12} /> {mm ? "Typology picture" : "Picture"}
              </button>
            )}
            <input ref={fileRef} type="file" accept="image/*" className="hidden"
                   onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onPicture(line, f); }} />
            {showMrp && (
              <label className="inline-flex items-center gap-1 text-[var(--ink-3)]" title="List price before GST, printed beside the offer price (the rate)">
                MRP ₹
                <input type="number" value={line.mrp || ""} onChange={(e) => patchLine(line, { mrp: parseFloat(e.target.value) || 0 })}
                       className="w-24 px-1.5 py-0.5 rounded border border-[var(--border)] bg-white text-xs text-right text-[var(--ink)]"
                       data-testid={`quote-line-mrp-${line.id}`} />
                {line.mrp > line.rate && line.rate > 0 && <span className="text-[var(--moss)]">save {Math.round(100 * (line.mrp - line.rate) / line.mrp)}%</span>}
              </label>
            )}
            {groups.length > 0 && (
              <label className="inline-flex items-center gap-1 text-[var(--ink-3)]">
                Group
                <select value={(line.group || "").trim()} onChange={(e) => patchLine(line, { group: e.target.value })}
                        className="px-1.5 py-0.5 rounded border border-[var(--border)] bg-white text-xs text-[var(--ink)]"
                        data-testid={`quote-line-group-${line.id}`}>
                  <option value="">No group</option>
                  {groups.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </label>
            )}
          </div>
          {open && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mt-2">
              {specFields.map((f) => (
                <label key={f.key} className="text-[11px] text-[var(--ink-3)]">
                  {f.label}
                  <input value={specs[f.key] || ""} className="w-full px-2 py-1 rounded border border-[var(--border)] bg-white text-sm text-[var(--ink)]"
                         onChange={(e) => patchLine(line, { specs: { ...specs, [f.key]: e.target.value } })} />
                </label>
              ))}
            </div>
          )}
        </td>
      </tr>
    </>
  );
}

function TotalsBar({ ws, onSave, busy, transportLabel }) {
  const [discount, setDiscount] = useState(ws.quote.discount || 0);
  const [transport, setTransport] = useState(ws.quote.transport || 0);
  const [taxPct, setTaxPct] = useState(ws.quote.tax_pct ?? 18);
  useEffect(() => { setTaxPct(ws.quote.tax_pct ?? 18); }, [ws.quote.tax_pct]);
  useEffect(() => { setDiscount(ws.quote.discount || 0); }, [ws.quote.discount]);
  useEffect(() => { setTransport(ws.quote.transport || 0); }, [ws.quote.transport]);
  const t = ws.totals;
  return (
    <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-5 flex flex-col md:flex-row md:items-end gap-4 justify-between">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 text-sm">
        <Cell label="Subtotal" value={inrFull(ws.subtotal)} />
        <div>
          <label className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)] block mb-1">Discount ₹</label>
          <input type="number" value={discount} onChange={(e) => setDiscount(parseFloat(e.target.value) || 0)} className="w-28 px-2 py-1.5 rounded border border-[var(--border)] bg-white text-sm text-right font-mono outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)] block mb-1">{transportLabel}</label>
          <input type="number" value={transport} onChange={(e) => setTransport(parseFloat(e.target.value) || 0)} data-testid="quote-transport"
                 className="w-28 px-2 py-1.5 rounded border border-[var(--border)] bg-white text-sm text-right font-mono outline-none focus:border-[var(--brand)]" />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)] block mb-1">GST</label>
          <select value={taxPct} onChange={(e) => setTaxPct(Number(e.target.value))} data-testid="quote-gst"
                  className="px-2 py-1.5 rounded border border-[var(--border)] bg-white text-sm">
            {[0, 5, 12, 18, 28].map((r) => <option key={r} value={r}>{r}%</option>)}
          </select>
          <div className="text-[11px] font-mono text-[var(--ink-2)] mt-0.5">{inrFull(t.tax_total)} at {ws.quote.tax_pct ?? 18}%</div>
        </div>
        {!!t.round_off && <Cell label="Round off" value={inrFull(t.round_off)} />}
        <Cell label="Net payable" value={inrFull(t.grand_total)} strong />
      </div>
      <button onClick={() => onSave(discount, transport, taxPct)} disabled={busy} className="btn-primary disabled:opacity-60">{busy ? "Saving…" : "Save totals to quote"}</button>
    </div>
  );
}
function Cell({ label, value, strong }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)]">{label}</div>
      <div className={`font-mono ${strong ? "font-bold text-lg text-[var(--ink)]" : "text-[var(--ink-2)]"}`}>{value}</div>
    </div>
  );
}
function I({ v, oc, t = "text", right }) {
  return <input type={t} value={v ?? ""} onChange={(e) => oc(e.target.value)} className={`w-full px-2 py-1 rounded border border-[var(--border)] bg-white text-xs outline-none focus:border-[var(--brand)] ${right ? "text-right font-mono" : ""}`} />;
}
