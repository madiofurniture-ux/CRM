import { useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { inr, inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { GripVertical, X, Trash2, Pencil } from "lucide-react";

const STAGES = ["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost"];
const DIVISIONS = ["Furniture", "MAP", "D&W"];
const STAGE_TINTS = {
  New: "border-t-[var(--ink-3)]",
  Qualified: "border-t-blue-500",
  Quoted: "border-t-[var(--warn)]",
  Negotiation: "border-t-[var(--brand)]",
  Won: "border-t-[var(--moss)]",
  Lost: "border-t-[var(--danger)]",
};

const emptyForm = {
  quote_no: "",
  date: new Date().toISOString().slice(0, 10),
  customer: "",
  division: "Furniture",
  by_user: "",
  stage: "New",
  value: 0,
  remarks: "",
};

export default function Pipeline() {
  const [quotes, setQuotes] = useState([]);
  const [dragId, setDragId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const { data } = await api.get("/quotes");
    setQuotes(data);
  };
  useEffect(() => { load(); }, []);

  const nextQuoteNo = useMemo(
    () => `AF-${String(quotes.length + 1).padStart(4, "0")}`,
    [quotes.length]
  );

  const openNew = () => {
    setEditing(null);
    setForm({ ...emptyForm, quote_no: nextQuoteNo });
    setShowForm(true);
  };

  const openEdit = (q) => {
    setEditing(q);
    setForm({
      quote_no: q.quote_no,
      date: q.date,
      customer: q.customer,
      division: q.division,
      by_user: q.by_user || "",
      stage: q.stage,
      value: q.value || 0,
      remarks: q.remarks || "",
    });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.customer.trim()) {
      toast.error("Customer name is required");
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await api.put(`/quotes/${editing.id}`, { ...editing, ...form });
        toast.success("Deal updated");
      } else {
        await api.post("/quotes", form);
        toast.success("Deal added");
      }
      setShowForm(false);
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (q) => {
    if (!window.confirm(`Delete the deal for "${q.customer}"?`)) return;
    try {
      await api.delete(`/quotes/${q.id}`);
      toast.success("Deal deleted");
      load();
    } catch {
      toast.error("Delete failed");
    }
  };

  const onDrop = async (stage) => {
    if (!dragId) return;
    const q = quotes.find((x) => x.id === dragId);
    if (!q || q.stage === stage) { setDragId(null); return; }
    setQuotes((prev) => prev.map((x) => (x.id === dragId ? { ...x, stage } : x)));
    setDragId(null);
    try {
      await api.put(`/quotes/${q.id}`, { ...q, stage });
      toast.success(`Moved to ${stage}`);
    } catch (e) {
      toast.error("Failed to update");
      load();
    }
  };

  return (
    <>
      <Topbar title="Pipeline" subtitle="Drag deals between stages" onAdd={openNew} addLabel="New Deal" />
      <div className="p-6" data-testid="pipeline-page">
        <div className="flex gap-4 overflow-x-auto pb-4">
          {STAGES.map((s) => {
            const items = quotes.filter((q) => q.stage === s);
            const total = items.reduce((a, b) => a + (b.value || 0), 0);
            return (
              <div
                key={s}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDrop(s)}
                className="w-[300px] shrink-0 bg-[var(--surface-2)] rounded-xl p-3 min-h-[400px]"
                data-testid={`kanban-col-${s}`}
              >
                <div className="flex items-center justify-between px-1 mb-3">
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${
                      s === "New" ? "bg-[var(--ink-3)]" :
                      s === "Qualified" ? "bg-blue-500" :
                      s === "Quoted" ? "bg-[var(--warn)]" :
                      s === "Negotiation" ? "bg-[var(--brand)]" :
                      s === "Won" ? "bg-[var(--moss)]" : "bg-[var(--danger)]"
                    }`} />
                    <span className="font-heading font-semibold text-[var(--ink)] text-sm">{s}</span>
                    <span className="text-xs text-[var(--ink-3)] font-mono">{items.length}</span>
                  </div>
                  <span className="text-[11px] font-mono font-semibold text-[var(--ink-2)]">{inr(total)}</span>
                </div>
                <div className="space-y-2">
                  {items.map((q) => (
                    <div
                      key={q.id}
                      draggable
                      onDragStart={() => setDragId(q.id)}
                      onDragEnd={() => setDragId(null)}
                      className={`group relative bg-[var(--surface)] border border-[var(--border)] border-t-2 ${STAGE_TINTS[s]} rounded-lg p-3 cursor-grab active:cursor-grabbing hover:shadow-md transition-shadow ${dragId === q.id ? "kanban-card-dragging" : ""}`}
                      data-testid={`kanban-card-${q.id}`}
                    >
                      <div className="absolute top-2 right-2 hidden group-hover:flex items-center gap-1 bg-[var(--surface)] rounded-md">
                        <button
                          onClick={() => openEdit(q)}
                          className="p-1 rounded hover:bg-[var(--surface-2)] text-[var(--ink-2)]"
                          title="Edit deal"
                          data-testid={`kanban-edit-${q.id}`}
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => remove(q)}
                          className="p-1 rounded hover:bg-red-50 text-red-600"
                          title="Delete deal"
                          data-testid={`kanban-delete-${q.id}`}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                      <div className="flex items-start justify-between gap-2 mb-1.5 pr-12">
                        <div className="font-semibold text-sm text-[var(--ink)] leading-tight">{q.customer}</div>
                        <GripVertical size={14} className="text-[var(--ink-3)] shrink-0 group-hover:opacity-0" />
                      </div>
                      <div className="text-[11px] text-[var(--ink-3)] mb-2 truncate">{q.remarks}</div>
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">{q.division}</span>
                        <span className="font-mono text-xs font-semibold text-[var(--ink)]">{inr(q.value)}</span>
                      </div>
                      <div className="mt-2 pt-2 border-t border-[var(--border-light)] flex items-center justify-between text-[10px] text-[var(--ink-3)]">
                        <span className="font-mono">{q.quote_no}</span>
                        <span>{fmtDate(q.date)} · {q.by_user}</span>
                      </div>
                    </div>
                  ))}
                  {items.length === 0 && (
                    <div className="text-center text-[11px] text-[var(--ink-3)] py-6 border border-dashed border-[var(--border)] rounded-lg">
                      Drop deals here
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[var(--border)] w-full max-w-lg shadow-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-[var(--border)] flex items-center justify-between bg-[var(--surface-2)]">
              <h3 className="font-heading font-bold text-base text-[var(--ink)]">
                {editing ? "Edit Deal" : "New Deal"}
              </h3>
              <button onClick={() => setShowForm(false)} className="p-1 rounded-lg text-[var(--ink-3)] hover:bg-white">
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Quote #</label>
                  <input
                    type="text"
                    value={form.quote_no}
                    onChange={(e) => setForm({ ...form, quote_no: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] font-mono outline-none focus:border-[var(--brand)]"
                    data-testid="deal-quote-no"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Date</label>
                  <input
                    type="date"
                    value={form.date}
                    onChange={(e) => setForm({ ...form, date: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                    data-testid="deal-date"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Customer Name *</label>
                <input
                  type="text"
                  placeholder="e.g. Krishna Reddy"
                  value={form.customer}
                  onChange={(e) => setForm({ ...form, customer: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                  data-testid="deal-customer"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Division</label>
                  <select
                    value={form.division}
                    onChange={(e) => setForm({ ...form, division: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)] bg-white"
                    data-testid="deal-division"
                  >
                    {DIVISIONS.map((d) => (
                      <option key={d}>{d}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Stage</label>
                  <select
                    value={form.stage}
                    onChange={(e) => setForm({ ...form, stage: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)] bg-white"
                    data-testid="deal-stage"
                  >
                    {STAGES.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Deal Value (₹)</label>
                  <input
                    type="number"
                    value={form.value}
                    onChange={(e) => setForm({ ...form, value: +e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] font-mono outline-none focus:border-[var(--brand)]"
                    data-testid="deal-value"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Handled By</label>
                  <input
                    type="text"
                    placeholder="e.g. Raghu MF"
                    value={form.by_user}
                    onChange={(e) => setForm({ ...form, by_user: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                    data-testid="deal-by-user"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Remarks</label>
                <textarea
                  rows={2}
                  placeholder="Notes about this deal…"
                  value={form.remarks}
                  onChange={(e) => setForm({ ...form, remarks: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                  data-testid="deal-remarks"
                />
              </div>
            </div>

            <div className="px-6 py-4 border-t border-[var(--border)] flex items-center justify-between bg-[var(--surface-2)]">
              <span className="font-mono text-lg font-bold text-[var(--brand)]">{inrFull(form.value)}</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowForm(false)}
                  className="px-4 py-2 text-xs font-semibold rounded-xl border border-[var(--border)] bg-white hover:bg-[var(--surface-2)] transition"
                >
                  Cancel
                </button>
                <button
                  onClick={save}
                  disabled={saving}
                  className="px-5 py-2 text-xs font-semibold rounded-xl bg-[var(--brand)] text-white hover:opacity-90 transition shadow-sm disabled:opacity-60"
                  data-testid="deal-save"
                >
                  {saving ? "Saving…" : editing ? "Save Changes" : "Add Deal"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
