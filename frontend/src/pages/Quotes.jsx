import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import FilterChips from "@/components/FilterChips";
import JourneyDrawer from "@/components/JourneyDrawer";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { Trash2, Edit2, X, Compass, ArrowRightCircle, LayoutList } from "lucide-react";

const DIVISIONS = ["Furniture", "MAP", "D&W"];
// Ops stages the sheet actually uses; the sales-status axis is derived server-side.
const STAGES = ["Quoted", "Adv Received", "Design & Lock", "Site Not Ready", "Rescheduled", "Delivered", "Cancelled"];

// Saved-view predicates matching the web app's chip row. Backend enriches each quote
// with derived_status / age_days / due_flag / is_open, so the UI just reads them.
const VIEW_PRED = {
  all: () => true,
  myopen: (q, me) => q.is_open && (q.by_user === me || !me),
  awaiting: (q) => q.derived_status === "Sent" && q.age_days != null && q.age_days >= 3 && q.age_days <= 7,
  hot: (q) => q.is_open && (q.value || 0) > 200000,
  overdue: (q) => q.is_open && q.due_flag === "overdue",
  wonmtd: (q) => {
    if (q.derived_status !== "Won") return false;
    const d = new Date(q.date), first = new Date(); first.setDate(1); first.setHours(0, 0, 0, 0);
    return !isNaN(d) && d >= first;
  },
};

export default function Quotes() {
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState("");
  const [fDiv, setFDiv] = useState("All");
  const [view, setView] = useState("all");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [jny, setJny] = useState(null);
  const nav = useNavigate();

  const empty = {
    quote_no: "", date: new Date().toISOString().slice(0, 10),
    customer: "", reference: "", phone: "", division: "Furniture",
    by_user: "", stage: "Quoted", value: 0, cash: 0, bank: 0,
    mode: "Walk-in", remarks: "", next_action_date: "",
  };
  const [form, setForm] = useState(empty);
  const me = JSON.parse(localStorage.getItem("madio_user") || "{}")?.name || "";

  const load = async () => { const { data } = await api.get("/quotes"); setRows(data); };
  useEffect(() => { load(); }, []);

  const views = useMemo(() => [
    { key: "all", label: "All", count: rows.length },
    { key: "myopen", label: "👤 My Open", count: rows.filter((q) => VIEW_PRED.myopen(q, me)).length },
    { key: "awaiting", label: "⏳ Awaiting 3–7d", count: rows.filter(VIEW_PRED.awaiting).length },
    { key: "hot", label: "🔥 Hot >₹2L", count: rows.filter(VIEW_PRED.hot).length },
    { key: "overdue", label: "⚠ Overdue", count: rows.filter(VIEW_PRED.overdue).length },
    { key: "wonmtd", label: "✅ Won MTD", count: rows.filter(VIEW_PRED.wonmtd).length },
  ], [rows, me]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    const vp = VIEW_PRED[view] || VIEW_PRED.all;
    return rows.filter((r) =>
      (fDiv === "All" || r.division === fDiv) &&
      vp(r, me) &&
      (!q || (r.customer || "").toLowerCase().includes(q) || (r.quote_no || "").toLowerCase().includes(q)
        || (r.reference || "").toLowerCase().includes(q) || (r.phone || "").toString().includes(q))
    );
  }, [rows, search, fDiv, view, me]);

  const openNew = () => { setEditing(null); setForm({ ...empty }); setShowForm(true); };
  const openEdit = (r) => { setEditing(r); setForm(r); setShowForm(true); };

  const save = async () => {
    try {
      if (editing) { await api.put(`/quotes/${editing.id}`, form); toast.success("Quote updated"); }
      else { await api.post("/quotes", form); toast.success("Quote created"); }
      setShowForm(false); load();
    } catch { toast.error("Save failed"); }
  };
  const convert = async (q) => {
    if (!window.confirm(`Convert ${q.quote_no} to a sale?`)) return;
    try { const { data } = await api.post(`/convert/quote-to-sale/${q.id}`); toast.success(`Sale ${data.sale_no} created`); load(); }
    catch { toast.error("Convert failed"); }
  };
  const remove = async (id) => {
    if (!window.confirm("Delete this quote?")) return;
    await api.delete(`/quotes/${id}`); toast.success("Deleted"); load();
  };

  const total = filtered.reduce((a, b) => a + (b.value || 0), 0);

  return (
    <>
      <Topbar title="Deals / Quotations" subtitle={`${filtered.length} of ${rows.length} · ${inrFull(total)}`} onAdd={openNew} addLabel="New Quote" />
      <div className="p-6" data-testid="quotes-page">
        <div className="flex flex-col gap-3 mb-4">
          <FilterChips views={views} active={view} onChange={setView} />
          <div className="flex flex-wrap gap-2">
            <input placeholder="Search customer, quote no, phone…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72" data-testid="quotes-search" />
            <select value={fDiv} onChange={(e) => setFDiv(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none" data-testid="filter-div">
              <option>All</option>
              {DIVISIONS.map((d) => <option key={d}>{d}</option>)}
            </select>
          </div>
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Quote No</th>
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                  <th className="text-left font-semibold px-4 py-2.5">Division</th>
                  <th className="text-left font-semibold px-4 py-2.5">Status</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="text-right font-semibold px-4 py-2.5">Value</th>
                  <th className="w-28"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((q) => (
                  <tr key={q.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50" data-testid={`quote-${q.id}`}>
                    <td className="px-4 py-3 font-mono text-xs text-[var(--ink)]">
                      {q.quote_no}{q.version > 1 && <span className="ml-1 text-[10px] text-[var(--ink-3)]">v{q.version}</span>}
                    </td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(q.date)}</td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-[var(--ink)]">{q.customer}</div>
                      {q.reference && <div className="text-xs text-[var(--ink-3)]">{q.reference}</div>}
                    </td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{q.division}</td>
                    <td className="px-4 py-3">
                      <StageBadge stage={q.derived_status} />
                      {q.due_flag === "overdue" && <span className="ml-1 text-[10px] text-[var(--danger)] font-semibold">⚠ due</span>}
                      {q.due_flag === "stale" && <span className="ml-1 text-[10px] text-[var(--warn)]">⏳ {q.age_days}d</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--ink-2)]">{q.stage}</td>
                    <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(q.value)}</td>
                    <td className="px-2 py-3">
                      <div className="flex items-center gap-1">
                        {q.phone && <button onClick={() => setJny({ phone: q.phone, name: q.customer })} title="Journey" className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"><Compass size={13} /></button>}
                        <button onClick={() => nav(`/quotes/ws/${q.id}`)} title="Workspace (line items)" className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"><LayoutList size={13} /></button>
                        {q.is_open && <button onClick={() => convert(q)} title="Convert to sale" className="p-1.5 rounded-md hover:bg-[var(--moss-soft)] text-[var(--moss)]"><ArrowRightCircle size={13} /></button>}
                        <button onClick={() => openEdit(q)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]"><Edit2 size={13} /></button>
                        <button onClick={() => remove(q.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan="8" className="text-center py-10 text-[var(--ink-3)]">No quotes match this view</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {showForm && (
        <FormDialog form={form} setForm={setForm} onClose={() => setShowForm(false)} onSave={save} editing={!!editing} />
      )}
      <JourneyDrawer phone={jny?.phone} name={jny?.name} onClose={() => setJny(null)} />
    </>
  );
}

function FormDialog({ form, setForm, onClose, onSave, editing }) {
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose} data-testid="quote-form">
      <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-2xl shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <div>
            <h3 className="font-heading font-semibold text-lg text-[var(--ink)]">{editing ? "Edit Quote" : "New Quote"}</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
        </div>
        <div className="p-5 grid grid-cols-2 gap-4 max-h-[60vh] overflow-y-auto">
          <Field label="Quote No" v={form.quote_no} onChange={(v) => set("quote_no", v)} testid="f-quote-no" />
          <Field label="Date" type="date" v={form.date} onChange={(v) => set("date", v)} testid="f-date" />
          <Field label="Customer" v={form.customer} onChange={(v) => set("customer", v)} className="col-span-2" testid="f-customer" />
          <Field label="Reference" v={form.reference} onChange={(v) => set("reference", v)} testid="f-ref" />
          <Field label="Phone" v={form.phone} onChange={(v) => set("phone", v)} testid="f-phone" />
          <SelectField label="Division" v={form.division} options={DIVISIONS} onChange={(v) => set("division", v)} testid="f-div" />
          <SelectField label="Stage" v={form.stage} options={STAGES} onChange={(v) => set("stage", v)} testid="f-stage" />
          <Field label="Value" type="number" v={form.value} onChange={(v) => set("value", parseFloat(v) || 0)} testid="f-value" />
          <Field label="By" v={form.by_user} onChange={(v) => set("by_user", v)} testid="f-by" />
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
