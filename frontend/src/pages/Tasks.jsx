import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { Check, Calendar, User, Trash2, X } from "lucide-react";
import { toast } from "sonner";

const PRIORITIES = ["Low", "Medium", "High"];
const CATEGORIES = ["General", "Sales", "Site Visit", "Marketing", "Delivery", "Inventory", "Admin", "Procurement", "Finance"];

export default function Tasks() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("Open"); // Open / Done / All
  const [show, setShow] = useState(false);
  const empty = { title: "", priority: "Medium", due_date: "", assigned_to: "", category: "General", notes: "", done: false };
  const [form, setForm] = useState(empty);

  const load = async () => { const { data } = await api.get("/tasks"); setRows(data); };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    if (filter === "Open") return rows.filter((r) => !r.done);
    if (filter === "Done") return rows.filter((r) => r.done);
    return rows;
  }, [rows, filter]);

  const today = new Date().toISOString().slice(0, 10);

  const counts = {
    open: rows.filter((r) => !r.done).length,
    done: rows.filter((r) => r.done).length,
    overdue: rows.filter((r) => !r.done && r.due_date && r.due_date < today).length,
    today: rows.filter((r) => !r.done && r.due_date === today).length,
  };

  const toggle = async (t) => {
    await api.put(`/tasks/${t.id}`, { ...t, done: !t.done });
    setRows((p) => p.map((x) => x.id === t.id ? { ...x, done: !x.done } : x));
  };
  const save = async () => {
    try { await api.post("/tasks", form); toast.success("Task added"); setShow(false); setForm(empty); load(); }
    catch { toast.error("Save failed"); }
  };
  const remove = async (id) => { if (!window.confirm("Delete task?")) return; await api.delete(`/tasks/${id}`); load(); };

  return (
    <>
      <Topbar
        title="Tasks"
        subtitle={`${counts.open} open · ${counts.overdue} overdue · ${counts.today} due today`}
        onAdd={() => { setForm(empty); setShow(true); }}
        addLabel="New Task"
      />
      <div className="p-6" data-testid="tasks-page">
        <div className="flex items-center gap-1 mb-4 bg-[var(--surface-2)] inline-flex rounded-lg p-0.5">
          {["Open", "Done", "All"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-sm rounded-md font-medium transition ${filter === f ? "bg-white shadow-sm text-[var(--ink)]" : "text-[var(--ink-2)]"}`}
              data-testid={`task-filter-${f}`}
            >
              {f}
              <span className="ml-1.5 text-[10px] font-mono text-[var(--ink-3)]">
                {f === "Open" ? counts.open : f === "Done" ? counts.done : rows.length}
              </span>
            </button>
          ))}
        </div>

        <div className="space-y-2">
          {filtered.map((t) => {
            const overdue = t.due_date && t.due_date < today && !t.done;
            return (
              <div key={t.id} className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 flex items-start gap-3 hover:shadow-sm transition" data-testid={`task-${t.id}`}>
                <button
                  onClick={() => toggle(t)}
                  className={`w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 mt-0.5 transition ${t.done ? "bg-[var(--moss)] border-[var(--moss)]" : "border-[var(--border)] hover:border-[var(--brand)]"}`}
                  data-testid={`task-toggle-${t.id}`}
                >
                  {t.done && <Check size={12} className="text-white" />}
                </button>
                <div className="flex-1 min-w-0">
                  <div className={`text-sm font-medium ${t.done ? "line-through text-[var(--ink-3)]" : "text-[var(--ink)]"}`}>{t.title}</div>
                  <div className="flex flex-wrap items-center gap-3 mt-1.5 text-[11px] text-[var(--ink-3)]">
                    <span className={`flex items-center gap-1 ${overdue ? "text-[var(--danger)] font-semibold" : ""}`}>
                      <Calendar size={11} />{fmtDate(t.due_date)}
                    </span>
                    {t.assigned_to && <span className="flex items-center gap-1"><User size={11} />{t.assigned_to}</span>}
                    <span className="px-1.5 py-0.5 rounded bg-[var(--surface-2)] text-[var(--ink-2)]">{t.category}</span>
                  </div>
                </div>
                <StageBadge stage={t.priority} />
                <button onClick={() => remove(t.id)} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button>
              </div>
            );
          })}
          {filtered.length === 0 && <div className="text-center py-12 text-[var(--ink-3)]">All clear ✨</div>}
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border w-full max-w-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">New Task</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Title</label>
                <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" data-testid="task-title" />
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Priority</label>
                <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">{PRIORITIES.map((p) => <option key={p}>{p}</option>)}</select>
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Category</label>
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select>
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Due date</label>
                <input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" />
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Assign to</label>
                <input value={form.assigned_to} onChange={(e) => setForm({ ...form, assigned_to: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" />
              </div>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary" onClick={save} data-testid="task-save">Create</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
