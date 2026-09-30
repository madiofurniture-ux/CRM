import { useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { inr, inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { GripVertical, X, Trash2, Pencil } from "lucide-react";
import { useTenantConfig } from "@/context/TenantConfigContext";
import { useAuth } from "@/context/AuthContext";
import StageBadge from "@/components/StageBadge";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";

const STAGES = ["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost"];
const STAGE_TINTS = {
  New: "border-t-blue-400",
  Qualified: "border-t-blue-600",
  Quoted: "border-t-amber-500",
  Negotiation: "border-t-indigo-800",
  Won: "border-t-[var(--color-success)]",
  Lost: "border-t-[var(--color-danger)]",
};

// Weighted-pipeline probability for a deal sitting at each stage — the
// standard CRM read on how likely it is to close. A deal that carries its
// own `probability` (set by the rep) overrides the stage default.
const STAGE_PROBABILITY = { New: 10, Qualified: 30, Quoted: 50, Negotiation: 70, Won: 100, Lost: 0 };

const dealProbability = (q) =>
  Number.isFinite(q?.probability) ? q.probability : (STAGE_PROBABILITY[q?.stage] ?? 0);

const probabilityTone = (pct) =>
  pct >= 70 ? "bg-[var(--moss-soft)] text-[var(--color-success)]"
    : pct >= 40 ? "bg-blue-50 text-blue-700"
      : pct > 0 ? "bg-[var(--warn-soft)] text-[var(--color-warning)]"
        : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]";

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
  const { divisions } = useTenantConfig();
  const { canDo } = useAuth();
  const canCreate = canDo("quotes", "create");
  const canEdit = canDo("quotes", "edit");
  const canDelete = canDo("quotes", "delete");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const { data } = await api.get("/quotes");
      setQuotes(data);
    } catch (e) {
      setLoadError(e?.response?.status === 401 || e?.response?.status === 403 ? "unauthorized" : "error");
    } finally {
      setLoading(false);
    }
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

  // No optimistic update — the board reflects `quotes` state only after
  // `load()` re-fetches from the server, so a failed or partially-applied
  // move never shows a card sitting somewhere it isn't actually saved.
  const onDrop = async (stage) => {
    if (!dragId || !canEdit) { setDragId(null); return; }
    const q = quotes.find((x) => x.id === dragId);
    setDragId(null);
    if (!q || q.stage === stage) return;
    try {
      await api.put(`/quotes/${q.id}`, { ...q, stage });
      toast.success(`Moved to ${stage}`);
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed to update");
    }
  };

  return (
    <>
      <Topbar title="Pipeline" subtitle="Drag deals between stages" onAdd={canCreate ? openNew : undefined} addLabel="New Deal" />
      <div className="p-6" data-testid="pipeline-page">
        {loadError ? (
          <ErrorState
            title={loadError === "unauthorized" ? "You don't have access to the Pipeline" : "Couldn't load the pipeline"}
            hint={loadError === "unauthorized" ? undefined : "The deal list didn't load — check your connection and try again."}
            onRetry={loadError === "unauthorized" ? undefined : load}
          />
        ) : loading ? (
          <div className="flex gap-4 overflow-x-auto pb-4">
            {STAGES.map((s) => (
              <div key={s} className="w-[300px] shrink-0 bg-[var(--color-surface-muted)] rounded-[var(--radius-lg)] p-3 min-h-[400px]">
                <Skeleton className="h-4 w-20 mb-3" />
                <Skeleton className="h-20 w-full mb-2" />
                <Skeleton className="h-20 w-full" />
              </div>
            ))}
          </div>
        ) : quotes.length === 0 ? (
          <EmptyState title="No deals yet" hint="Deals moved through this pipeline (from Leads, or added directly) will show up here." />
        ) : (
        <>
        {/* Kanban board — desktop/tablet. Below md, a stacked list (below)
            is the real fallback view, not just horizontal scroll. */}
        <div className="hidden md:flex gap-4 overflow-x-auto pb-4">
          {STAGES.map((s) => {
            const items = quotes.filter((q) => q.stage === s);
            const total = items.reduce((a, b) => a + (b.value || 0), 0);
            return (
              <div
                key={s}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDrop(s)}
                className="w-[300px] shrink-0 bg-[var(--color-surface-muted)] rounded-2xl p-3 min-h-[400px]"
                data-testid={`kanban-col-${s}`}
              >
                <div className="flex items-center justify-between px-1 mb-3">
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${
                      s === "New" ? "bg-blue-400" :
                      s === "Qualified" ? "bg-blue-600" :
                      s === "Quoted" ? "bg-amber-500" :
                      s === "Negotiation" ? "bg-indigo-800" :
                      s === "Won" ? "bg-[var(--color-success)]" : "bg-[var(--color-danger)]"
                    }`} />
                    <span className="font-heading font-semibold text-[var(--color-text)] text-sm">{s}</span>
                    <span className="text-xs text-[var(--color-text-muted)] font-mono">{items.length}</span>
                  </div>
                  <span className="text-[11px] font-mono font-semibold text-[var(--color-text-muted)]">{inr(total)}</span>
                </div>
                <div className="space-y-2">
                  {items.map((q) => (
                    <div
                      key={q.id}
                      draggable={canEdit}
                      onDragStart={() => canEdit && setDragId(q.id)}
                      onDragEnd={() => setDragId(null)}
                      className={`group relative bg-[var(--color-surface)] border border-[var(--color-border)] border-t-2 ${STAGE_TINTS[s]} rounded-[var(--radius-lg)] p-3 ${canEdit ? "cursor-grab active:cursor-grabbing" : ""} hover:shadow-md transition-shadow ${dragId === q.id ? "kanban-card-dragging" : ""}`}
                      data-testid={`kanban-card-${q.id}`}
                    >
                      <div className="absolute top-2 right-2 hidden group-hover:flex items-center gap-1 bg-[var(--color-surface)] rounded-md">
                        {canEdit && (
                          <button
                            onClick={() => openEdit(q)}
                            className="p-1 rounded hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"
                            title="Edit deal"
                            data-testid={`kanban-edit-${q.id}`}
                          >
                            <Pencil size={13} />
                          </button>
                        )}
                        {canDelete && (
                          <button
                            onClick={() => remove(q)}
                            className="p-1 rounded hover:bg-red-50 text-red-600"
                            title="Delete deal"
                            data-testid={`kanban-delete-${q.id}`}
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                      <div className="flex items-start justify-between gap-2 mb-1.5 pr-12">
                        <div className="font-semibold text-sm text-[var(--color-text)] leading-tight">{q.customer}</div>
                        <GripVertical size={14} className="text-[var(--color-text-muted)] shrink-0 group-hover:opacity-0" />
                      </div>
                      <div className="text-[11px] text-[var(--color-text-muted)] mb-2 truncate">{q.remarks}</div>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-semibold truncate">{q.division}</span>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${probabilityTone(dealProbability(q))}`}
                                title="Probability of closing at this stage"
                                data-testid={`kanban-probability-${q.id}`}>
                            {dealProbability(q)}%
                          </span>
                          <span className="font-mono text-xs font-semibold text-[var(--color-text)]">{inr(q.value)}</span>
                        </div>
                      </div>
                      <div className="mt-2 pt-2 border-t border-[var(--color-border)] flex items-center justify-between text-[10px] text-[var(--color-text-muted)]">
                        <span className="font-mono">{q.quote_no}</span>
                        <span>{fmtDate(q.date)} · {q.by_user}</span>
                      </div>
                    </div>
                  ))}
                  {items.length === 0 && (
                    <div className="text-center text-[11px] text-[var(--color-text-muted)] py-6 border border-dashed border-[var(--color-border)] rounded-lg">
                      Drop deals here
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Stacked list — narrow screens (real fallback, not a resized
            kanban): same `quotes` data, grouped by stage. */}
        <div className="md:hidden space-y-6">
          {STAGES.map((s) => {
            const items = quotes.filter((q) => q.stage === s);
            if (items.length === 0) return null;
            return (
              <div key={s}>
                <div className="flex items-center gap-2 mb-2 px-1">
                  <StageBadge stage={s} />
                  <span className="text-xs text-[var(--color-text-muted)] font-mono">{items.length} · {inr(items.reduce((a, b) => a + (b.value || 0), 0))}</span>
                </div>
                <div className="space-y-2">
                  {items.map((q) => (
                    <button
                      key={q.id}
                      type="button"
                      onClick={() => canEdit && openEdit(q)}
                      className="w-full text-left bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-3"
                      data-testid={`pipeline-list-${q.id}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="font-semibold text-sm text-[var(--color-text)]">{q.customer}</div>
                        <span className="font-mono text-xs font-semibold text-[var(--color-text)]">{inr(q.value)}</span>
                      </div>
                      <div className="flex items-center justify-between gap-2 mt-1 text-[10px] text-[var(--color-text-muted)]">
                        <span className="font-mono">{q.quote_no}</span>
                        <span>{dealProbability(q)}% · {fmtDate(q.date)}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        </>
        )}
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[var(--color-surface)] rounded-2xl border border-[var(--color-border)] w-full max-w-lg shadow-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-[var(--color-border)] flex items-center justify-between bg-[var(--color-surface-muted)]">
              <h3 className="font-heading font-bold text-base text-[var(--color-text)]">
                {editing ? "Edit Deal" : "New Deal"}
              </h3>
              <button onClick={() => setShowForm(false)} className="p-1 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface)]">
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Quote #</label>
                  <input
                    type="text"
                    value={form.quote_no}
                    onChange={(e) => setForm({ ...form, quote_no: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] font-mono outline-none focus:border-[var(--color-primary)]"
                    data-testid="deal-quote-no"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Date</label>
                  <input
                    type="date"
                    value={form.date}
                    onChange={(e) => setForm({ ...form, date: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] outline-none focus:border-[var(--color-primary)]"
                    data-testid="deal-date"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Customer Name *</label>
                <input
                  type="text"
                  placeholder="e.g. Krishna Reddy"
                  value={form.customer}
                  onChange={(e) => setForm({ ...form, customer: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] outline-none focus:border-[var(--color-primary)]"
                  data-testid="deal-customer"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Division</label>
                  <select
                    value={form.division}
                    onChange={(e) => setForm({ ...form, division: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] outline-none focus:border-[var(--color-primary)] bg-[var(--color-surface)]"
                    data-testid="deal-division"
                  >
                    {divisions.map((d) => (
                      <option key={d.id} value={d.slug}>{d.slug}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Stage</label>
                  <select
                    value={form.stage}
                    onChange={(e) => setForm({ ...form, stage: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] outline-none focus:border-[var(--color-primary)] bg-[var(--color-surface)]"
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
                  <label className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Deal Value (₹)</label>
                  <input
                    type="number"
                    value={form.value}
                    onChange={(e) => setForm({ ...form, value: +e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] font-mono outline-none focus:border-[var(--color-primary)]"
                    data-testid="deal-value"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Handled By</label>
                  <input
                    type="text"
                    placeholder="e.g. Raghu MF"
                    value={form.by_user}
                    onChange={(e) => setForm({ ...form, by_user: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] outline-none focus:border-[var(--color-primary)]"
                    data-testid="deal-by-user"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Remarks</label>
                <textarea
                  rows={2}
                  placeholder="Notes about this deal…"
                  value={form.remarks}
                  onChange={(e) => setForm({ ...form, remarks: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] outline-none focus:border-[var(--color-primary)]"
                  data-testid="deal-remarks"
                />
              </div>
            </div>

            <div className="px-6 py-4 border-t border-[var(--color-border)] flex items-center justify-between bg-[var(--color-surface-muted)]">
              <span className="font-mono text-lg font-bold text-[var(--color-primary)]">{inrFull(form.value)}</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowForm(false)}
                  className="px-4 py-2 text-xs font-semibold rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)] transition"
                >
                  Cancel
                </button>
                <button
                  onClick={save}
                  disabled={saving}
                  className="px-5 py-2 text-xs font-semibold rounded-xl bg-[var(--color-primary)] text-white hover:opacity-90 transition shadow-sm disabled:opacity-60"
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
