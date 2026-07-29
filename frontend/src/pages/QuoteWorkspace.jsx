import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { inrFull } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { ChevronLeft, Plus, Trash2, ArrowRightCircle, GitBranch } from "lucide-react";

// Full detail workspace for one quote: line-item builder, discount + approval, versions.
export default function QuoteWorkspace() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [ws, setWs] = useState(null);
  const [tab, setTab] = useState("lines");
  const lineTimers = useRef({});   // per-line debounce timers, kept across renders

  const load = useCallback(async () => {
    try { const { data } = await api.get(`/quotes/${id}/workspace`); setWs(data); }
    catch { toast.error("Quote not found"); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (!ws) return <><Topbar title="Quote Workspace" /><div className="p-10 text-center text-[var(--ink-3)]">Loading…</div></>;

  const q = ws.quote;
  const isAdmin = user?.role === "admin";
  const pending = q.approval === "pending";

  const addLine = async () => {
    await api.post("/quote-lines", { quote_id: id, version: q.version || 1, description: "", w: 0, h: 0, qty: 1, rate: 0 });
    load();
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

  const saveTotal = async (discount) => {
    const { data } = await api.post(`/quotes/${id}/save-total`, { discount });
    setWs((p) => ({ ...p, quote: data }));
    toast.success("Totals saved to quote");
    load();
  };
  const approve = async (ok) => { await api.post(`/quotes/${id}/approve`, { approved: ok }); toast.success(ok ? "Approved" : "Rejected"); load(); };
  const revise = async () => { if (!window.confirm("Start a new revision? Current lines are copied forward.")) return; const { data } = await api.post(`/quotes/${id}/revise`); toast.success(`Now v${data.version}`); load(); };
  const convert = async () => {
    if (pending) { toast.error("Approve the discount before converting"); return; }
    if (!window.confirm(`Convert ${q.quote_no} to a sale?`)) return;
    const { data } = await api.post(`/convert/quote-to-sale/${id}`); toast.success(`Sale ${data.sale_no} created`); load();
  };

  return (
    <>
      <Topbar title={`${q.quote_no}${q.version > 1 ? ` · v${q.version}` : ""}`} subtitle={q.customer}
        actions={
          <div className="flex items-center gap-2">
            <StageBadge stage={q.derived_status} />
            <button onClick={revise} className="btn-ghost"><GitBranch size={14} /> Revise</button>
            <button onClick={convert} disabled={pending} className={`btn-primary ${pending ? "opacity-50 cursor-not-allowed" : ""}`}><ArrowRightCircle size={15} /> Convert to Sale</button>
          </div>
        } />
      <div className="p-6 space-y-4" data-testid="quote-workspace">
        <button onClick={() => nav("/quotes")} className="text-sm text-[var(--ink-2)] inline-flex items-center gap-1"><ChevronLeft size={14} /> All deals</button>

        {pending && (
          <div className="bg-[var(--warn-soft)] border border-[var(--warn)] rounded-lg px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-[var(--ink)]">Discount {inrFull(q.discount)} exceeds 10% of subtotal — needs approval.</span>
            {isAdmin
              ? <div className="flex gap-2"><button onClick={() => approve(true)} className="btn-primary">Approve</button><button onClick={() => approve(false)} className="btn-ghost text-[var(--danger)]">Reject</button></div>
              : <span className="text-xs text-[var(--ink-3)]">Awaiting an admin</span>}
          </div>
        )}
        {q.approval === "approved" && <div className="text-xs text-[var(--moss)]">✓ Discount approved</div>}

        <div className="flex gap-1 border-b border-[var(--border)]">
          {["lines", "versions"].map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === t ? "border-[var(--brand)] text-[var(--brand)]" : "border-transparent text-[var(--ink-3)]"}`}>
              {t === "lines" ? "Line Items" : "Versions"}
            </button>
          ))}
        </div>

        {tab === "lines" && (
          <>
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
              <div className="p-3 border-b border-[var(--border-light)] flex justify-between items-center">
                <div className="font-heading font-semibold text-sm">Line items</div>
                <button onClick={addLine} className="btn-ghost"><Plus size={14} /> Add line</button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-[var(--surface-2)]">
                    <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                      <th className="text-left font-semibold px-3 py-2">Description</th>
                      <th className="text-right font-semibold px-3 py-2">W</th>
                      <th className="text-right font-semibold px-3 py-2">H</th>
                      <th className="text-right font-semibold px-3 py-2">Qty</th>
                      <th className="text-right font-semibold px-3 py-2">Sqft</th>
                      <th className="text-right font-semibold px-3 py-2">Rate</th>
                      <th className="text-right font-semibold px-3 py-2">Amount</th>
                      <th className="w-8"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {ws.lines.map((l) => (
                      <tr key={l.id} className="border-t border-[var(--border-light)]">
                        <td className="px-3 py-2"><I v={l.description} oc={(v) => patchLine(l, { description: v })} /></td>
                        <td className="px-3 py-2 w-16"><I t="number" v={l.w} oc={(v) => patchLine(l, { w: parseFloat(v) || 0 })} right /></td>
                        <td className="px-3 py-2 w-16"><I t="number" v={l.h} oc={(v) => patchLine(l, { h: parseFloat(v) || 0 })} right /></td>
                        <td className="px-3 py-2 w-16"><I t="number" v={l.qty} oc={(v) => patchLine(l, { qty: parseFloat(v) || 0 })} right /></td>
                        <td className="px-3 py-2 text-right font-mono text-[var(--ink-3)]">{(l.sft || 0).toFixed(2)}</td>
                        <td className="px-3 py-2 w-24"><I t="number" v={l.rate} oc={(v) => patchLine(l, { rate: parseFloat(v) || 0 })} right /></td>
                        <td className="px-3 py-2 text-right font-mono font-semibold">{inrFull(l.amount)}</td>
                        <td className="px-2 py-2"><button onClick={() => removeLine(l.id)} className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button></td>
                      </tr>
                    ))}
                    {ws.lines.length === 0 && <tr><td colSpan="8" className="text-center py-8 text-[var(--ink-3)]">No line items — add the first.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
            <TotalsBar ws={ws} onSave={saveTotal} />
          </>
        )}

        {tab === "versions" && (
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="text-sm text-[var(--ink-2)] mb-3">This quote has {ws.versions.length} version(s). Current: <span className="font-semibold">v{q.version}</span>.</div>
            <div className="flex flex-wrap gap-2">
              {ws.versions.map((v) => (
                <span key={v} className={`px-3 py-1.5 rounded-lg text-sm ${v === q.version ? "bg-[var(--brand-soft)] text-[var(--brand)] font-semibold" : "bg-[var(--surface-2)] text-[var(--ink-2)]"}`}>v{v}</span>
              ))}
            </div>
            <div className="text-xs text-[var(--ink-3)] mt-3">“Revise” copies the current line items into a new version and reopens the quote as Sent.</div>
          </div>
        )}
      </div>
    </>
  );
}

function TotalsBar({ ws, onSave }) {
  const [discount, setDiscount] = useState(ws.quote.discount || 0);
  useEffect(() => { setDiscount(ws.quote.discount || 0); }, [ws.quote.discount]);
  const t = ws.totals;
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 flex flex-col md:flex-row md:items-end gap-4 justify-between">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
        <Cell label="Subtotal" value={inrFull(ws.subtotal)} />
        <div>
          <label className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)] block mb-1">Discount ₹</label>
          <input type="number" value={discount} onChange={(e) => setDiscount(parseFloat(e.target.value) || 0)} className="w-28 px-2 py-1.5 rounded border border-[var(--border)] bg-white text-sm text-right font-mono outline-none focus:border-[var(--brand)]" />
        </div>
        <Cell label={`Tax (${ws.quote.tax_pct || 18}%)`} value={inrFull(t.tax_total)} />
        <Cell label="Grand Total" value={inrFull(t.grand_total)} strong />
      </div>
      <button onClick={() => onSave(discount)} className="btn-primary">Save totals to quote</button>
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
