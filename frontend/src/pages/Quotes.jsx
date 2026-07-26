import { useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { Trash2, Edit2, Printer, X, Plus } from "lucide-react";

const DIVISIONS = ["Furniture", "MAP", "D&W"];
const STAGES = ["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost"];
const HSN_OPTIONS = ["9403", "3208", "4418", "9401", "6304", "9405"];

const emptyItem = () => ({ sku: "", description: "", hsn: "9403", qty: 1, rate: 0, discount_pct: 0, tax_pct: 18 });

export default function Quotes() {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [fDiv, setFDiv] = useState("All");
  const [fStage, setFStage] = useState("All");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);

  const empty = {
    quote_no: "", date: new Date().toISOString().slice(0, 10),
    customer: "", reference: "", phone: "", division: "Furniture",
    by_user: "", stage: "Quoted", value: 0, cash: 0, bank: 0,
    mode: "Walk-in", remarks: "",
    line_items: [], tax_pct: 18, subtotal: 0, tax_total: 0, grand_total: 0,
  };
  const [form, setForm] = useState(empty);
  const [printRow, setPrintRow] = useState(null);
  const [office, setOffice] = useState({ name: "MADIO", address: "", gstin: "" });

  const load = async () => {
    const [r, o] = await Promise.all([api.get("/quotes"), api.get("/settings/office").catch(() => ({ data: { name: "MADIO", address: "", gstin: "" } }))]);
    setRows(r.data);
    setOffice(o.data);
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return rows.filter((r) =>
      (fDiv === "All" || r.division === fDiv) &&
      (fStage === "All" || r.stage === fStage) &&
      (!q || r.customer.toLowerCase().includes(q) || r.quote_no.toLowerCase().includes(q) || (r.reference || "").toLowerCase().includes(q))
    );
  }, [rows, search, fDiv, fStage]);

  const openNew = () => {
    setEditing(null);
    setForm({ ...empty, quote_no: `AF-${String(rows.length + 1).padStart(4, "0")}` });
    setShowForm(true);
  };
  const openEdit = (r) => { setEditing(r); setForm({ ...r, line_items: r.line_items?.length ? r.line_items : [] }); setShowForm(true); };

  const computed = useMemo(() => {
    const items = form.line_items || [];
    if (!items.length) return { subtotal: form.value || 0, tax_total: 0, grand_total: form.value || 0 };
    let subtotal = 0;
    for (const it of items) {
      const base = (it.qty || 0) * (it.rate || 0);
      const net = base * (1 - (it.discount_pct || 0) / 100);
      subtotal += net;
    }
    const tax_total = subtotal * ((form.tax_pct || 0) / 100);
    return { subtotal, tax_total, grand_total: subtotal + tax_total };
  }, [form.line_items, form.tax_pct, form.value]);

  const setItem = (idx, k, v) => setForm((f) => ({ ...f, line_items: f.line_items.map((it, i) => i === idx ? { ...it, [k]: v } : it) }));
  const addItem = () => setForm((f) => ({ ...f, line_items: [...(f.line_items || []), emptyItem()] }));
  const delItem = (idx) => setForm((f) => ({ ...f, line_items: f.line_items.filter((_, i) => i !== idx) }));

  const save = async () => {
    const payload = {
      ...form,
      subtotal: computed.subtotal, tax_total: computed.tax_total, grand_total: computed.grand_total,
      value: (form.line_items || []).length ? computed.grand_total : (form.value || 0),
    };
    try {
      if (editing) {
        await api.put(`/quotes/${editing.id}`, payload);
        toast.success("Quote updated");
      } else {
        await api.post("/quotes", payload);
        toast.success("Quote created");
      }
      setShowForm(false);
      load();
    } catch (e) {
      toast.error("Save failed");
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this quote?")) return;
    await api.delete(`/quotes/${id}`);
    toast.success("Deleted");
    load();
  };

  const total = filtered.reduce((a, b) => a + (b.value || 0), 0);

  return (
    <>
      <Topbar title="Quotations" subtitle={`${filtered.length} of ${rows.length} · ${inrFull(total)}`} onAdd={openNew} addLabel="New Quote" />
      <div className="p-6" data-testid="quotes-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input
            placeholder="Search customer, quote no, reference…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72"
            data-testid="quotes-search"
          />
          <select value={fDiv} onChange={(e) => setFDiv(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none" data-testid="filter-div">
            <option>All</option>
            {DIVISIONS.map((d) => <option key={d}>{d}</option>)}
          </select>
          <select value={fStage} onChange={(e) => setFStage(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none" data-testid="filter-stage">
            <option>All</option>
            {STAGES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Quote No</th>
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                  <th className="text-left font-semibold px-4 py-2.5">Reference</th>
                  <th className="text-left font-semibold px-4 py-2.5">Division</th>
                  <th className="text-left font-semibold px-4 py-2.5">By</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="text-right font-semibold px-4 py-2.5">Value</th>
                  <th className="w-20"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((q) => (
                  <tr key={q.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50" data-testid={`quote-${q.id}`}>
                    <td className="px-4 py-3 font-mono text-xs text-[var(--ink)]">{q.quote_no}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(q.date)}</td>
                    <td className="px-4 py-3 font-medium text-[var(--ink)]">{q.customer}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{q.reference}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{q.division}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{q.by_user}</td>
                    <td className="px-4 py-3"><StageBadge stage={q.stage} /></td>
                    <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(q.value)}</td>
                    <td className="px-2 py-3">
                      <div className="flex items-center gap-1">
                        <button onClick={() => setPrintRow(q)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]" title="Print" data-testid={`q-print-${q.id}`}><Printer size={13} /></button>
                        <button onClick={() => openEdit(q)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"><Edit2 size={13} /></button>
                        <button onClick={() => remove(q.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan="9" className="text-center py-10 text-[var(--ink-3)]">No quotes match your filters</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {showForm && (
        <FormDialog form={form} setForm={setForm} onClose={() => setShowForm(false)} onSave={save} editing={!!editing} computed={computed} setItem={setItem} addItem={addItem} delItem={delItem} />
      )}
      {printRow && <QuotePrint quote={printRow} office={office} onClose={() => setPrintRow(null)} />}
    </>
  );
}

function QuotePrint({ quote, office, onClose }) {
  useEffect(() => {
    document.body.classList.add("printing");
    return () => document.body.classList.remove("printing");
  }, []);
  const items = quote.line_items || [];
  const showBreakup = items.length > 0;
  return (
    <div className="fixed inset-0 bg-white z-[60] overflow-auto print-view">
      <div className="max-w-4xl mx-auto p-8 print:p-0" id="print-area">
        <div className="flex justify-between items-start mb-8">
          <div>
            <div className="w-40 mb-3 bg-[#0e0f0d] rounded-lg px-4 py-3 inline-block">
              <img src="/logos/madio-white.png" alt="MADIO" className="h-10 object-contain" />
            </div>
            <div className="font-heading font-bold text-2xl text-[var(--ink)]">{office.name || "MADIO"}</div>
            <div className="text-sm text-[var(--ink-2)]">{office.address}</div>
            {office.gstin && <div className="text-xs font-mono text-[var(--ink-3)] mt-1">GSTIN: {office.gstin}</div>}
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-widest text-[var(--ink-3)] font-semibold">Quotation</div>
            <div className="font-heading font-bold text-lg mt-1">{quote.quote_no}</div>
            <div className="text-sm text-[var(--ink-2)] mt-1">{fmtDate(quote.date)}</div>
            <div className="text-xs text-[var(--ink-3)] mt-2">Division: {quote.division}</div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-8 mb-8">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-[var(--ink-3)] font-semibold mb-1">Prepared for</div>
            <div className="font-semibold text-[var(--ink)]">{quote.customer}</div>
            {quote.phone && <div className="text-sm text-[var(--ink-2)] font-mono">📞 {quote.phone}</div>}
            {quote.reference && <div className="text-xs text-[var(--ink-3)]">Ref: {quote.reference}</div>}
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-widest text-[var(--ink-3)] font-semibold mb-1">Prepared by</div>
            <div className="font-medium">{quote.by_user || "—"}</div>
            <div className="text-xs text-[var(--ink-3)] mt-1">Mode: {quote.mode}</div>
          </div>
        </div>

        {showBreakup ? (
          <>
            <table className="w-full text-sm mb-6 border-t border-b border-[var(--ink)]">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="text-left py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">#</th>
                  <th className="text-left py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">Description</th>
                  <th className="text-right py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">Qty</th>
                  <th className="text-right py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">Rate</th>
                  <th className="text-right py-2 text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">Amount</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => {
                  const amt = (it.qty || 0) * (it.rate || 0) * (1 - (it.discount_pct || 0) / 100);
                  return (
                    <tr key={i} className="border-b border-[var(--border-light)]">
                      <td className="py-3">{i + 1}</td>
                      <td className="py-3">{it.description}</td>
                      <td className="py-3 text-right font-mono">{it.qty}</td>
                      <td className="py-3 text-right font-mono">{inrFull(it.rate)}</td>
                      <td className="py-3 text-right font-mono font-semibold">{inrFull(amt)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="flex justify-end mb-8">
              <div className="w-72 space-y-1 text-sm font-mono">
                <div className="flex justify-between"><span className="text-[var(--ink-2)]">Subtotal</span><span>{inrFull(quote.subtotal)}</span></div>
                <div className="flex justify-between"><span className="text-[var(--ink-2)]">GST @ {quote.tax_pct}%</span><span>{inrFull(quote.tax_total)}</span></div>
                <div className="flex justify-between border-t border-[var(--ink)] pt-2 mt-2 font-bold text-base"><span>GRAND TOTAL</span><span>{inrFull(quote.grand_total || quote.value)}</span></div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex justify-end mb-8">
            <div className="w-72 space-y-1 text-sm font-mono">
              <div className="flex justify-between border-t border-[var(--ink)] pt-2 mt-2 font-bold text-base"><span>QUOTED VALUE</span><span>{inrFull(quote.value)}</span></div>
            </div>
          </div>
        )}

        {quote.remarks && <div className="text-xs text-[var(--ink-2)] mb-3"><strong>Remarks:</strong> {quote.remarks}</div>}
        <div className="text-xs text-[var(--ink-3)] italic border-t border-[var(--border)] pt-4 space-y-1">
          <div>• Prices valid for 15 days from quote date.</div>
          <div>• 50% advance required to confirm order. Delivery timelines confirmed after advance.</div>
          <div>• Warranty & after-sales as per MADIO terms & conditions.</div>
        </div>
      </div>
      <div className="no-print fixed bottom-6 right-6 flex gap-2 z-10">
        <button onClick={onClose} className="btn-ghost">Close</button>
        <button onClick={() => window.print()} className="btn-primary" data-testid="quote-print-btn"><Printer size={14} />Print / Save PDF</button>
      </div>
    </div>
  );
}

function FormDialog({ form, setForm, onClose, onSave, editing, computed, setItem, addItem, delItem }) {
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const hasItems = (form.line_items || []).length > 0;
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-2 md:p-4" onClick={onClose} data-testid="quote-form">
      <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-3xl max-h-[95vh] flex flex-col shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <h3 className="font-heading font-semibold text-lg text-[var(--ink)]">{editing ? "Edit Quote" : "New Quote"}</h3>
          <button onClick={onClose} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
        </div>
        <div className="p-5 grid grid-cols-2 gap-4 overflow-y-auto">
          <Field label="Quote No" v={form.quote_no} onChange={(v) => set("quote_no", v)} testid="f-quote-no" />
          <Field label="Date" type="date" v={form.date} onChange={(v) => set("date", v)} testid="f-date" />
          <Field label="Customer" v={form.customer} onChange={(v) => set("customer", v)} className="col-span-2" testid="f-customer" />
          <Field label="Reference" v={form.reference} onChange={(v) => set("reference", v)} testid="f-ref" />
          <Field label="Phone" v={form.phone} onChange={(v) => set("phone", v)} testid="f-phone" />
          <SelectField label="Division" v={form.division} options={DIVISIONS} onChange={(v) => set("division", v)} testid="f-div" />
          <SelectField label="Stage" v={form.stage} options={STAGES} onChange={(v) => set("stage", v)} testid="f-stage" />
          <Field label="By" v={form.by_user} onChange={(v) => set("by_user", v)} testid="f-by" />
          {!hasItems && <Field label="Value" type="number" v={form.value} onChange={(v) => set("value", parseFloat(v) || 0)} testid="f-value" />}

          <div className="col-span-2 mt-2">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)]">Line items (optional)</div>
              <button onClick={addItem} className="btn-ghost text-xs" data-testid="q-add-item"><Plus size={12} />Add line</button>
            </div>
            {hasItems && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-[var(--surface-2)]">
                    <tr className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">
                      <th className="text-left px-2 py-2">Description</th>
                      <th className="text-right px-2 py-2 w-16">Qty</th>
                      <th className="text-right px-2 py-2 w-24">Rate</th>
                      <th className="text-right px-2 py-2 w-16">Disc%</th>
                      <th className="text-right px-2 py-2 w-24">Amount</th>
                      <th className="w-8"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {form.line_items.map((it, i) => {
                      const amt = (it.qty || 0) * (it.rate || 0) * (1 - (it.discount_pct || 0) / 100);
                      return (
                        <tr key={i} className="border-t border-[var(--border-light)]">
                          <td className="p-1"><input value={it.description} onChange={(e) => setItem(i, "description", e.target.value)} placeholder="Description" className="w-full px-2 py-1.5 rounded border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)]" data-testid={`q-item-desc-${i}`} /></td>
                          <td className="p-1"><input type="number" value={it.qty} onChange={(e) => setItem(i, "qty", parseFloat(e.target.value) || 0)} className="w-full px-2 py-1.5 rounded border border-[var(--border)] text-sm text-right font-mono" /></td>
                          <td className="p-1"><input type="number" value={it.rate} onChange={(e) => setItem(i, "rate", parseFloat(e.target.value) || 0)} className="w-full px-2 py-1.5 rounded border border-[var(--border)] text-sm text-right font-mono" /></td>
                          <td className="p-1"><input type="number" value={it.discount_pct} onChange={(e) => setItem(i, "discount_pct", parseFloat(e.target.value) || 0)} className="w-full px-2 py-1.5 rounded border border-[var(--border)] text-sm text-right font-mono" /></td>
                          <td className="p-1 text-right font-mono text-sm font-semibold">{inrFull(amt)}</td>
                          <td className="p-1"><button onClick={() => delItem(i)} className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={12} /></button></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <div className="mt-3 flex justify-end">
                  <div className="w-64 space-y-1 text-sm font-mono">
                    <div className="flex justify-between"><span className="text-[var(--ink-2)]">Subtotal</span><span>{inrFull(computed.subtotal)}</span></div>
                    <div className="flex items-center justify-between">
                      <label className="text-[var(--ink-2)] flex items-center gap-2">GST% <input type="number" value={form.tax_pct} onChange={(e) => set("tax_pct", parseFloat(e.target.value) || 0)} className="w-16 px-2 py-1 rounded border border-[var(--border)] text-xs text-right" /></label>
                      <span>{inrFull(computed.tax_total)}</span>
                    </div>
                    <div className="flex justify-between border-t border-[var(--ink)] pt-2 mt-2 font-bold"><span>Total</span><span>{inrFull(computed.grand_total)}</span></div>
                  </div>
                </div>
              </div>
            )}
          </div>

          <Field label="Cash" type="number" v={form.cash} onChange={(v) => set("cash", parseFloat(v) || 0)} testid="f-cash" />
          <Field label="Bank" type="number" v={form.bank} onChange={(v) => set("bank", parseFloat(v) || 0)} testid="f-bank" />
          <Field label="Remarks" v={form.remarks} onChange={(v) => set("remarks", v)} className="col-span-2" testid="f-remarks" />
        </div>
        <div className="px-5 py-4 border-t border-[var(--border)] flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose} data-testid="form-cancel">Cancel</button>
          <button className="btn-primary" onClick={onSave} data-testid="form-save">{editing ? "Save" : "Create"}</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, v, onChange, type = "text", className = "", testid }) {
  return (
    <div className={className}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{label}</label>
      <input
        type={type}
        value={v ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]"
        data-testid={testid}
      />
    </div>
  );
}
function SelectField({ label, v, options, onChange, testid }) {
  return (
    <div>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{label}</label>
      <select value={v} onChange={(e) => onChange(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none" data-testid={testid}>
        {options.map((o) => <option key={o}>{o}</option>)}
      </select>
    </div>
  );
}
