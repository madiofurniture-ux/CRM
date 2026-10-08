import { useEffect, useState, useCallback, useRef } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import StageProgressBar from "@/components/StageProgressBar";
import LogTimeline from "@/components/LogTimeline";
import AttachmentPanel from "@/components/AttachmentPanel";
import ProductPicker, { StockBadge, rateFromMrp } from "@/components/ProductPicker";
import { downloadPdf } from "@/lib/pdf";
import api, { formatApiError } from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { shrinkImage } from "@/lib/image";
import usePicklists from "@/hooks/usePicklists";
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
  // Quotation settings: the Doors & Windows typology library (and, for
  // people who can see landing prices, the markup).
  const [qs, setQs] = useState({ typologies: [] });
  useEffect(() => {
    api.get("/quote-settings").then(({ data }) => setQs(data || { typologies: [] })).catch(() => {});
  }, []);

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
  // The server sends cost figures only to people allowed to see landing prices.
  const canCost = !!ws.cost_summary;
  const markup = Number(preset.markup) || 0;
  const showMfg = canCost && markup > 0;
  const typologies = preset.typologies ? (qs.typologies || []) : [];
  const typologyOf = (code) => typologies.find((t) => t.code === code);
  const cols = 8 + (mm ? 1 : 0) + (showMfg ? 1 : 0);
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
        ...(mm ? { dim_unit: "mm" } : {}),
        ...(specFields.length ? { specs: { ...(preset.spec_defaults || {}) } } : {}),
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
      try { await api.put(`/quote-lines/${line.id}`, merged); }
      catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't save that line"); }
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
        quote_id: id, version: q.version || 1, w: 0, h: 0, qty: 1, group: curGroup, model_no: item.model_no || "",
        description: [item.name, item.model_no, item.material_finish].filter(Boolean).join(" · "),
        rate: rateFromMrp(item.mrp, item.gst_pct ?? taxPct), sku: item.sku, unit: item.unit, hsn: item.hsn,
        price_auto: true,           // the server prices it from the item's quantity breaks
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

  // discount: { discount } in rupees or { discount_pct } as % of the subtotal.
  const saveTotal = async (discount, transport, tax_pct) => {
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/quotes/${id}/save-total`, { ...discount, transport, tax_pct });
      setWs((p) => ({ ...p, quote: data }));
      toast.success("Totals saved to quote");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't save the totals"); }
    finally { setBusy(false); }
  };
  const setExtra = async (key, value) => {
    try { await api.put(`/quotes/${id}`, { extra: { ...(q.extra || {}), [key]: value } }); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't save that"); }
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
      <Topbar title={`${q.display_no || q.quote_no}${q.version > 1 ? ` · v${q.version}` : ""}`} subtitle={q.customer}
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
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <button onClick={() => nav("/quotes")} className="text-[var(--ink-2)] inline-flex items-center gap-1"><ChevronLeft size={14} /> All deals</button>
          <span className="text-[var(--ink-3)]" data-testid="quote-context">
            For{" "}
            {q.customer_id
              ? <Link to={`/customers/${q.customer_id}`} className="text-[var(--brand)] hover:underline" title="Open the customer">{q.customer || "customer"}</Link>
              : <span title="Not linked to a customer record">{q.customer || "—"} <span className="text-[var(--warn)]">(not linked)</span></span>}
            {q.project_id && <> · <Link to={`/projects/${q.project_id}`} className="text-[var(--brand)] hover:underline">Project</Link></>}
            {q.phone && <span> · {q.phone}</span>}
            <span className="ml-1 text-[11px]" title="Name and phone as issued on this quotation; the customer record holds the current details">(as issued)</span>
          </span>
        </div>
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
          {/* Per-quotation facts the division prints as terms (D&W: aluminium rate). */}
          {(preset.quote_fields || []).map((f) => (
            <label key={f.key} className="inline-flex items-center gap-1.5 text-[var(--ink-2)] ml-2" title={f.term ? `Printed: ${f.term}` : undefined}>
              {f.label}
              <input type={f.type === "number" ? "number" : "text"} defaultValue={(q.extra || {})[f.key] || ""}
                     key={`${f.key}-${(q.extra || {})[f.key] || ""}`}
                     onBlur={(e) => e.target.value !== String((q.extra || {})[f.key] || "") && setExtra(f.key, e.target.value)}
                     className="w-24 px-2 py-1 rounded border border-[var(--border)] bg-white text-sm text-right" data-testid={`quote-extra-${f.key}`} />
            </label>
          ))}
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
                      {showMfg && <th className="text-right font-semibold px-3 py-2" title="Manufacturer's rate — a landing price, never printed">{mm ? "MFG / Sft" : "MFG rate"}</th>}
                      <th className="text-right font-semibold px-3 py-2">{mm ? "Rate / Sft" : "Rate"}</th>
                      <th className="text-right font-semibold px-3 py-2">Amount</th>
                      <th className="w-8"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {lineGroups.map((g) => (
                      <GroupRows key={g || "_"} name={g} grouped={grouped} cols={cols} mm={mm} summary={groupSummary[g]}>
                    {ws.lines.filter((l) => (l.group || "").trim() === g).map((l) => (
                      <LineRows key={l.id} line={l} mm={mm} specFields={specFields} patchLine={patchLine} cols={cols}
                                groups={groupNames} onPicture={pickPicture} showMrp={q.print_layout === "pricelist"}
                                typologies={typologies} showModel={preset.layout === "catalogue"} wastage={!!preset.wastage}>
                      <tr className="border-t border-[var(--border-light)]">
                        <td className="px-3 py-2">
                          {l.typology && typologyOf(l.typology) && (
                            <div className="flex items-center gap-1.5 mb-1 text-[11px] text-[var(--ink-2)]" data-testid={`quote-line-typology-${l.id}`}>
                              {typologyOf(l.typology).image && <img src={typologyOf(l.typology).image} alt="" className="h-7 w-10 object-contain bg-white rounded border border-[var(--border)]" />}
                              <span className="font-medium">{typologyOf(l.typology).name}</span>
                            </div>
                          )}
                          <I v={l.description} oc={(v) => patchLine(l, { description: v })} testId={`quote-line-desc-${l.id}`} />
                          {l.sku && (
                            <div className="mt-1 flex items-center gap-1.5 text-[10px] text-[var(--ink-3)]" data-testid={`quote-line-sku-${l.id}`}>
                              <span className="font-mono">{l.sku}</span>
                              <StockBadge item={stock[l.sku]} qty={l.qty} />
                              <PriceHints line={l} item={stock[l.sku]} taxPct={q.tax_pct ?? 18} />
                            </div>
                          )}
                        </td>
                        <td className={`px-3 py-2 ${mm ? "w-24" : "w-16"}`}><I t="number" v={l.w} oc={(v) => patchLine(l, { w: parseFloat(v) || 0 })} right testId={`quote-line-w-${l.id}`} /></td>
                        <td className={`px-3 py-2 ${mm ? "w-24" : "w-16"}`}><I t="number" v={l.h} oc={(v) => patchLine(l, { h: parseFloat(v) || 0 })} right testId={`quote-line-h-${l.id}`} /></td>
                        {mm && <td className="px-3 py-2 text-right font-mono text-[var(--ink-3)]">{(l.sft_each || 0).toFixed(2)}</td>}
                        <td className="px-3 py-2 w-16"><I t="number" v={l.qty} oc={(v) => patchLine(l, { qty: parseFloat(v) || 0 })} right testId={`quote-line-qty-${l.id}`} /></td>
                        <td className="px-3 py-2 text-right font-mono text-[var(--ink-3)]">{(l.sft || 0).toFixed(2)}</td>
                        {showMfg && (
                          <td className="px-3 py-2 w-24 bg-[var(--warn-soft)]/30">
                            <I t="number" v={l.cost_rate || ""} oc={(v) => {
                              const cost = parseFloat(v) || 0;
                              patchLine(l, { cost_rate: cost, rate_auto: cost > 0, ...(cost > 0 ? { rate: Math.round(cost * markup * 100) / 100 } : {}) });
                            }} right testId={`quote-line-mfg-${l.id}`} />
                            <MarginHint line={l} markup={markup} onAuto={() => patchLine(l, { rate_auto: true, rate: Math.round(l.cost_rate * markup * 100) / 100 })} />
                          </td>
                        )}
                        <td className="px-3 py-2 w-24"><I t="number" v={l.rate} oc={(v) => patchLine(l, { rate: parseFloat(v) || 0, price_auto: false, rate_auto: false })} right testId={`quote-line-rate-${l.id}`} />
                          {l.sku && !l.price_auto && stock[l.sku]?.price_tiers?.length > 0 && (
                            <button type="button" className="text-[10px] text-[var(--brand)]" onClick={() => patchLine(l, { price_auto: true })}
                                    title="Price this line from the item's quantity pricing again">use qty price</button>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right font-mono font-semibold">{inrFull(l.amount)}</td>
                        <td className="px-2 py-2"><button onClick={() => removeLine(l.id)} className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button></td>
                      </tr>
                      </LineRows>
                    ))}
                      </GroupRows>
                    ))}
                    {ws.lines.length === 0 && <tr><td colSpan={cols} className="text-center py-8 text-[var(--ink-3)]">No line items — add the first.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
            {ws.summary?.sft > 0 && (
              <div className="text-xs text-[var(--ink-2)] flex flex-wrap gap-4" data-testid="quote-summary">
                <span>{preset.line_label || "Openings"}: <b>{ws.summary.openings}</b></span>
                <span>Total area: <b>{ws.summary.sft} sft</b></span>
                <span title="Value after discount ÷ total area, as the quotation's project summary states it">Average rate: <b>{inrFull(ws.summary.avg_rate)} / sft</b></span>
              </div>
            )}
            <TotalsBar ws={ws} preset={preset} onSave={saveTotal} busy={busy} transportLabel={`${preset.transport_label || "Transport"} ₹`} />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {(ws.payment_schedule || []).length > 0 && (
                <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-4 text-sm" data-testid="quote-payment-schedule">
                  <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)] mb-2">Payment schedule {preset.gst_extra ? "(incl. GST)" : ""}</div>
                  {ws.payment_schedule.map((s) => (
                    <div key={s.label} className="flex justify-between gap-3 py-0.5">
                      <span>{s.label} <span className="text-[var(--ink-3)]">· {s.pct}%</span></span>
                      <span className="font-mono">{inrFull(s.amount)}</span>
                    </div>
                  ))}
                </div>
              )}
              {ws.cost_summary && (
                <div className="bg-[var(--warn-soft)]/40 border border-[var(--warn)]/40 rounded-2xl p-4 text-sm" data-testid="quote-margin">
                  <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)] mb-2">Margin — only you can see this</div>
                  {ws.cost_summary.lines_costed > 0 ? (
                    <>
                      <div className="flex justify-between"><span>Cost (MFG / landing)</span><span className="font-mono">{inrFull(ws.cost_summary.cost)}</span></div>
                      <div className="flex justify-between"><span>Value after discount</span><span className="font-mono">{inrFull(ws.totals.value)}</span></div>
                      <div className={`flex justify-between font-semibold ${ws.cost_summary.margin < 0 ? "text-[var(--danger)]" : "text-[var(--moss)]"}`}>
                        <span>Margin</span><span className="font-mono">{inrFull(ws.cost_summary.margin)} · {ws.cost_summary.margin_pct}%</span>
                      </div>
                      {ws.cost_summary.lines_costed < ws.cost_summary.lines && (
                        <div className="text-xs text-[var(--ink-3)] mt-1">Cost known for {ws.cost_summary.lines_costed} of {ws.cost_summary.lines} lines.</div>
                      )}
                    </>
                  ) : <div className="text-xs text-[var(--ink-3)]">Add the MFG rate on a line (or pick it from stock) to see the margin.</div>}
                </div>
              )}
            </div>
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

/** A line row plus its details: group, picture (printed on the quotation),
 *  the typology (Doors & Windows), model number (Furniture), wastage (MAP)
 *  and the specification, whose fields come from Master Data lists. */
function LineRows({ line, mm, specFields, patchLine, groups, onPicture, showMrp, cols, typologies, showModel, wastage, children }) {
  const [open, setOpen] = useState(false);
  const fileRef = useRef(null);
  const { values } = usePicklists();
  const specs = line.specs || {};
  const filled = specFields.filter((f) => String(specs[f.key] || "").trim()).length;
  const small = "px-1.5 py-0.5 rounded border border-[var(--border)] bg-white text-xs text-[var(--ink)]";
  const setSpec = (key, v) => patchLine(line, { specs: { ...specs, [key]: v } });
  return (
    <>
      {children}
      <tr className="bg-[var(--surface-2)]/40">
        <td colSpan={cols} className="px-3 pb-2">
          <div className="flex flex-wrap items-center gap-3 text-xs">
            {typologies.length > 0 && (
              <label className="inline-flex items-center gap-1 text-[var(--ink-3)]">
                Typology
                <select value={line.typology || ""} onChange={(e) => patchLine(line, { typology: e.target.value,
                          ...(e.target.value ? { specs: { ...specs, pattern: typologies.find((t) => t.code === e.target.value)?.pattern || specs.pattern } } : {}) })}
                        className={`${small} max-w-[14rem]`} data-testid={`quote-line-typology-select-${line.id}`}>
                  <option value="">—</option>
                  {typologies.map((t) => <option key={t.code} value={t.code}>{t.code} · {t.name}</option>)}
                </select>
              </label>
            )}
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
                      data-testid={`quote-line-add-picture-${line.id}`}
                      title={mm ? "Prints instead of the typology's diagram" : undefined}>
                <ImagePlus size={12} /> {mm ? "Own picture" : "Picture"}
              </button>
            )}
            <input ref={fileRef} type="file" accept="image/*" className="hidden"
                   onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onPicture(line, f); }} />
            {showModel && (
              <label className="inline-flex items-center gap-1 text-[var(--ink-3)]">
                Model no.
                <input value={line.model_no || ""} onChange={(e) => patchLine(line, { model_no: e.target.value })}
                       className={`${small} w-24`} data-testid={`quote-line-model-${line.id}`} />
              </label>
            )}
            {wastage && !mm && (
              <label className="inline-flex items-center gap-1 text-[var(--ink-3)]" title="Billed area = measured W × H plus this much">
                Wastage %
                <input type="number" value={line.wastage_pct || ""} onChange={(e) => patchLine(line, { wastage_pct: parseFloat(e.target.value) || 0 })}
                       className={`${small} w-14 text-right`} data-testid={`quote-line-wastage-${line.id}`} />
                {line.sft_measured > 0 && <span>{line.sft_measured} sft measured</span>}
              </label>
            )}
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
                        className={small} data-testid={`quote-line-group-${line.id}`}>
                  <option value="">No group</option>
                  {groups.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </label>
            )}
          </div>
          {open && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mt-2">
              {specFields.map((f) => {
                const opts = f.list ? values(f.list, specs[f.key]) : [];
                const box = "w-full px-2 py-1 rounded border border-[var(--border)] bg-white text-sm text-[var(--ink)]";
                return (
                  <label key={f.key} className="text-[11px] text-[var(--ink-3)]">
                    {f.label}
                    {f.strict && opts.length > 0 ? (
                      <select value={specs[f.key] || ""} onChange={(e) => setSpec(f.key, e.target.value)} className={box}
                              data-testid={`quote-line-spec-${f.key}-${line.id}`}>
                        <option value="">—</option>
                        {opts.map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : (
                      <>
                        <input value={specs[f.key] || ""} className={box} list={opts.length ? `dl-${f.list}` : undefined}
                               onChange={(e) => setSpec(f.key, e.target.value)} data-testid={`quote-line-spec-${f.key}-${line.id}`} />
                        {opts.length > 0 && <datalist id={`dl-${f.list}`}>{opts.map((o) => <option key={o} value={o} />)}</datalist>}
                      </>
                    )}
                  </label>
                );
              })}
            </div>
          )}
        </td>
      </tr>
    </>
  );
}

/** Under the MFG rate: the margin at this line's rate, and a way back to
 *  MFG × markup once someone has typed a rate. */
function MarginHint({ line, markup, onAuto }) {
  const cost = Number(line.cost_rate) || 0;
  if (!cost) return null;
  const rate = Number(line.rate) || 0;
  const margin = rate > 0 ? Math.round(((rate - cost) / rate) * 100) : null;
  return (
    <div className="text-[10px] text-right mt-0.5 space-x-1" data-testid={`quote-line-margin-${line.id}`}>
      {line.rate_auto ? <span className="text-[var(--moss)]">× {markup}</span>
        : <button type="button" className="text-[var(--brand)]" onClick={onAuto} title={`Rate = MFG × ${markup}`}>use × {markup}</button>}
      {margin != null && <span className={margin < 0 ? "text-[var(--danger)]" : "text-[var(--ink-3)]"}>{margin}%</span>}
    </div>
  );
}

function TotalsBar({ ws, preset, onSave, busy, transportLabel }) {
  const [mode, setMode] = useState(ws.quote.discount_pct > 0 ? "pct" : "amt");
  const [discount, setDiscount] = useState(ws.quote.discount || 0);
  const [pct, setPct] = useState(ws.quote.discount_pct || 0);
  const [transport, setTransport] = useState(ws.quote.transport || 0);
  const [taxPct, setTaxPct] = useState(ws.quote.tax_pct ?? 18);
  useEffect(() => { setTaxPct(ws.quote.tax_pct ?? 18); }, [ws.quote.tax_pct]);
  useEffect(() => { setDiscount(ws.quote.discount || 0); }, [ws.quote.discount]);
  useEffect(() => { setPct(ws.quote.discount_pct || 0); setMode(ws.quote.discount_pct > 0 ? "pct" : "amt"); }, [ws.quote.discount_pct]);
  useEffect(() => { setTransport(ws.quote.transport || 0); }, [ws.quote.transport]);
  const t = ws.totals;
  const box = "w-24 px-2 py-1.5 rounded border border-[var(--border)] bg-white text-sm text-right font-mono outline-none focus:border-[var(--brand)]";
  const save = () => onSave(mode === "pct" ? { discount_pct: pct, discount: 0 } : { discount, discount_pct: 0 }, transport, taxPct);
  return (
    <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-5 flex flex-col md:flex-row md:items-end gap-4 justify-between" data-testid="quote-totals">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 text-sm">
        <Cell label="Subtotal" value={inrFull(ws.subtotal)} />
        <div>
          <div className="flex items-center gap-1 mb-1">
            <label className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)]">Discount</label>
            <div className="inline-flex rounded border border-[var(--border)] overflow-hidden text-[10px]" role="radiogroup" aria-label="Discount in rupees or percent">
              {[["amt", "₹"], ["pct", "%"]].map(([k, l]) => (
                <button key={k} type="button" role="radio" aria-checked={mode === k} onClick={() => setMode(k)}
                        className={`px-1.5 ${mode === k ? "bg-[var(--brand)] text-white" : ""}`} data-testid={`quote-discount-mode-${k}`}>{l}</button>
              ))}
            </div>
          </div>
          {mode === "pct"
            ? <input type="number" value={pct} onChange={(e) => setPct(parseFloat(e.target.value) || 0)} className={box} data-testid="quote-discount-pct" />
            : <input type="number" value={discount} onChange={(e) => setDiscount(parseFloat(e.target.value) || 0)} className={box} data-testid="quote-discount" />}
          {mode === "pct" && t.discount > 0 && <div className="text-[11px] font-mono text-[var(--ink-2)] mt-0.5">= {inrFull(t.discount)}</div>}
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)] block mb-1">{transportLabel}</label>
          <input type="number" value={transport} onChange={(e) => setTransport(parseFloat(e.target.value) || 0)} data-testid="quote-transport" className={box} />
          {preset.tax_transport && t.transport > 0 && <div className="text-[11px] text-[var(--ink-3)] mt-0.5">GST applies to it too</div>}
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)] block mb-1">GST{preset.gst_extra ? " (extra)" : ""}</label>
          <select value={taxPct} onChange={(e) => setTaxPct(Number(e.target.value))} data-testid="quote-gst"
                  className="px-2 py-1.5 rounded border border-[var(--border)] bg-white text-sm">
            {[0, 5, 12, 18, 28].map((r) => <option key={r} value={r}>{r}%</option>)}
          </select>
          <div className="text-[11px] font-mono text-[var(--ink-2)] mt-0.5">{inrFull(t.tax_total)} at {ws.quote.tax_pct ?? 18}%</div>
        </div>
        {preset.gst_extra ? (
          <>
            <Cell label={`${preset.total_label || "Grand total"} (excl. GST)`} value={inrFull(t.before_tax)} strong />
            <Cell label="Order value incl. GST" value={inrFull(t.grand_total)} />
          </>
        ) : (
          <>
            {!!t.round_off && <Cell label="Round off" value={inrFull(t.round_off)} />}
            <Cell label={(preset.total_label || "Net payable").replace(" (₹)", "")} value={inrFull(t.grand_total)} strong />
          </>
        )}
      </div>
      <button onClick={save} disabled={busy} className="btn-primary disabled:opacity-60" data-testid="quote-save-totals">{busy ? "Saving…" : "Save totals to quote"}</button>
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
function I({ v, oc, t = "text", right, testId }) {
  return <input type={t} value={v ?? ""} onChange={(e) => oc(e.target.value)} data-testid={testId} className={`w-full px-2 py-1 rounded border border-[var(--border)] bg-white text-xs outline-none focus:border-[var(--brand)] ${right ? "text-right font-mono" : ""}`} />;
}


// Under a stock line: which quantity price applies (and the next break), and
// for people allowed to see it, the landing price and margin at this rate.
function PriceHints({ line, item, taxPct }) {
  if (!item) return null;
  const tiers = item.price_tiers || [];
  const qty = Number(line.qty) || 0;
  const next = tiers.find((t) => qty < t.min_qty);
  const active = [...tiers].reverse().find((t) => qty >= t.min_qty);
  const gst = item.gst_pct ?? taxPct ?? 18;
  const landing = "cost" in item ? Number(item.cost) || 0 : null;      // landing price, before GST like the rate
  const margin = landing > 0 && line.rate > 0 ? Math.round(((line.rate - landing) / line.rate) * 100) : null;
  return (
    <>
      {line.price_auto && tiers.length > 0 && (
        <span className="text-[var(--moss)]" data-testid={`qty-price-${line.id}`}
              title={tiers.map((t) => `${t.min_qty}+ : ₹${t.price}`).join(" · ")}>
          {active ? `qty price ${active.min_qty}+` : "MRP"}{next ? ` · ${next.min_qty}+ ₹${Math.round(rateFromMrp(next.price, gst))}` : ""}
        </span>
      )}
      {landing != null && (
        <span className={margin != null && margin < 0 ? "text-[var(--danger)]" : ""} data-testid={`landing-${line.id}`}>
          landing ₹{Math.round(landing).toLocaleString("en-IN")}{margin != null ? ` · margin ${margin}%` : ""}
        </span>
      )}
    </>
  );
}
