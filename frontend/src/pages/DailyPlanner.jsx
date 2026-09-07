import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import EmptyState from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { toast } from "sonner";
import {
  ChevronLeft, ChevronRight, Calendar, RotateCcw, Plus, X, PartyPopper,
  CheckCircle2, Circle, Link2, ListTodo,
} from "lucide-react";

const PRIORITIES = ["Urgent", "High", "Medium", "Low"];
const PRIORITY_TONE = {
  Urgent: "text-[var(--danger)] bg-[var(--danger-soft)]",
  High: "text-[var(--warn,#B45309)] bg-[var(--warn-soft,#FEF3C7)]",
  Medium: "text-[var(--brand)] bg-[var(--brand-soft)]",
  Low: "text-[var(--ink-3)] bg-[var(--surface-2)]",
};
const emptyForm = { title: "", priority: "Medium", time_slot: "", notes: "" };

const isoToday = () => new Date().toISOString().slice(0, 10);
const shiftDate = (iso, days) => {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};
const dayLabel = (iso) => {
  const today = isoToday();
  if (iso === today) return "Today";
  if (iso === shiftDate(today, -1)) return "Yesterday";
  if (iso === shiftDate(today, 1)) return "Tomorrow";
  return fmtDate(iso);
};

export default function DailyPlanner() {
  const [date, setDate] = useState(isoToday());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [quickTitle, setQuickTitle] = useState("");
  const [adding, setAdding] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [rollingOver, setRollingOver] = useState(false);
  const [teams, setTeams] = useState([]);
  const [teammates, setTeammates] = useState([]);

  const load = () => {
    setLoading(true);
    api.get("/daily-planner", { params: { date } }).then(({ data }) => setData(data)).finally(() => setLoading(false));
  };
  useEffect(load, [date]); // eslint-disable-line
  useEffect(() => {
    api.get("/teams").then(({ data }) => setTeams(data)).catch(() => {});
    api.get("/users/directory").then(({ data }) => setTeammates(data)).catch(() => {});
  }, []);

  const tasks = data?.tasks || [];
  const stats = data?.stats || { total: 0, completed: 0, pending: 0, completion_rate: 0 };
  const grouped = PRIORITIES.map((p) => ({ priority: p, items: tasks.filter((t) => (t.priority || "Medium") === p) }))
    .filter((g) => g.items.length > 0);

  const toggle = async (task) => {
    setData((d) => ({
      ...d,
      tasks: d.tasks.map((t) => t.id === task.id ? { ...t, done: !t.done } : t),
    }));
    try {
      await api.patch(`/daily-planner/${task.id}/toggle`, {});
      load();
    } catch {
      toast.error("Couldn't update task");
      load();
    }
  };

  const quickAdd = async (e) => {
    e.preventDefault();
    const title = quickTitle.trim();
    if (!title || adding) return;
    setAdding(true);
    try {
      await api.post("/daily-planner", { title, date, priority: "Medium" });
      setQuickTitle("");
      load();
    } catch { toast.error("Couldn't add task"); }
    finally { setAdding(false); }
  };

  const createFull = async () => {
    if (!form.title.trim() || adding) return;
    setAdding(true);
    try {
      await api.post("/daily-planner", { ...form, date });
      toast.success("Task added");
      setForm(emptyForm);
      setShowCreate(false);
      load();
    } catch { toast.error("Couldn't add task"); }
    finally { setAdding(false); }
  };

  const rollover = async () => {
    setRollingOver(true);
    try {
      const { data } = await api.post("/daily-planner/rollover", {});
      toast.success(data.rolled_over > 0 ? `Rolled over ${data.rolled_over} task${data.rolled_over === 1 ? "" : "s"}` : "Nothing to roll over");
      load();
    } catch { toast.error("Rollover failed"); }
    finally { setRollingOver(false); }
  };

  return (
    <>
      <Topbar title="Daily Planner" subtitle={dayLabel(date)} />
      <div className="p-6 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-6 items-start" data-testid="daily-planner-page">
      <div className="space-y-6 max-w-3xl">
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setDate(shiftDate(date, -1))} className="p-2 rounded-lg border border-[var(--border)] hover:bg-[var(--surface-hover)]" data-testid="dp-prev-day">
            <ChevronLeft size={16} />
          </button>
          <button onClick={() => setDate(isoToday())} className="px-3 py-2 rounded-lg border border-[var(--border)] text-sm font-medium hover:bg-[var(--surface-hover)]" data-testid="dp-today">
            Today
          </button>
          <button onClick={() => setDate(shiftDate(date, 1))} className="p-2 rounded-lg border border-[var(--border)] hover:bg-[var(--surface-hover)]" data-testid="dp-next-day">
            <ChevronRight size={16} />
          </button>
          <div className="relative">
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
              className="pl-8 pr-3 py-2 rounded-lg border border-[var(--border)] text-sm bg-white" data-testid="dp-date-picker" />
            <Calendar size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--ink-3)] pointer-events-none" />
          </div>
          <button onClick={rollover} disabled={rollingOver}
            className="ml-auto flex items-center gap-1.5 px-3 py-2 rounded-lg border border-[var(--border)] text-sm hover:bg-[var(--surface-hover)] disabled:opacity-60"
            data-testid="dp-rollover">
            <RotateCcw size={14} /> {rollingOver ? "Rolling over…" : "Rollover Incomplete"}
          </button>
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold">
              {stats.completed} / {stats.total} completed
            </span>
            <span className="flex items-center gap-1.5 text-sm font-semibold">
              {stats.completion_rate === 100 && stats.total > 0 && <PartyPopper size={15} className="text-[var(--moss)]" />}
              {stats.completion_rate}%
            </span>
          </div>
          <div className="h-2 rounded-full bg-[var(--surface-2)] overflow-hidden">
            <div className={`h-full transition-all duration-300 ${stats.completion_rate === 100 && stats.total > 0 ? "bg-[var(--moss)]" : "bg-[var(--brand)]"}`}
              style={{ width: `${stats.completion_rate}%` }} />
          </div>
        </div>

        <form onSubmit={quickAdd} className="flex gap-2">
          <input value={quickTitle} onChange={(e) => setQuickTitle(e.target.value)}
            placeholder="Quick-add a task and press Enter…"
            className="flex-1 px-3 py-2.5 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]"
            data-testid="dp-quick-add" />
          <button type="button" onClick={() => setShowCreate(true)} className="px-3 py-2.5 rounded-lg border border-[var(--border)] hover:bg-[var(--surface-hover)]" title="More options" data-testid="dp-open-create">
            <Plus size={16} />
          </button>
        </form>

        {loading && (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12 w-full rounded-lg" />)}
          </div>
        )}

        {!loading && tasks.length === 0 && (
          <EmptyState icon={ListTodo} title="Nothing planned yet" hint="Add a task above to start planning your day." />
        )}

        {!loading && grouped.map((g) => (
          <div key={g.priority}>
            <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-2">{g.priority}</div>
            <div className="space-y-1.5">
              {g.items.map((t) => (
                <div key={t.id} className="flex items-center gap-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg px-3 py-2.5" data-testid={`dp-task-${t.id}`}>
                  <button onClick={() => toggle(t)} className="shrink-0 text-[var(--ink-3)] hover:text-[var(--moss)]" data-testid={`dp-toggle-${t.id}`}>
                    {t.done ? <CheckCircle2 size={20} className="text-[var(--moss)]" /> : <Circle size={20} />}
                  </button>
                  <div className="flex-1 min-w-0">
                    <div className={`text-sm transition-all duration-200 ${t.done ? "line-through text-[var(--ink-3)]" : "text-[var(--ink)]"}`}>
                      {t.title}
                    </div>
                    {(t.time_slot || t.ref) && (
                      <div className="flex items-center gap-2 mt-0.5">
                        {t.time_slot && <span className="text-[11px] text-[var(--ink-3)]">{t.time_slot}</span>}
                        {t.ref && (
                          <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded bg-[var(--surface-2)] text-[var(--ink-2)]">
                            <Link2 size={10} /> {t.linked_entity_name || t.ref_type || t.ref}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  <span className={`shrink-0 text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded ${PRIORITY_TONE[t.priority] || PRIORITY_TONE.Medium}`}>
                    {t.priority}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-4 lg:sticky lg:top-20">
        <h2 className="font-heading font-bold text-[var(--ink)] tracking-tight mb-3">Team follow-through</h2>
        {teammates.length === 0 || !teams.some((t) => t.active && teammates.some((u) => u.team_id === t.id)) ? (
          <div className="text-sm text-[var(--ink-3)]">No teammates assigned to a team yet.</div>
        ) : (
          <div className="space-y-3">
            {teams.filter((t) => t.active).map((team) => {
              const members = teammates.filter((u) => u.team_id === team.id);
              if (members.length === 0) return null;
              return (
                <div key={team.id}>
                  <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-1.5">{team.name}</div>
                  <div className="space-y-1.5">
                    {members.map((m) => (
                      <div key={m.id} className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[11px] font-heading font-bold shrink-0" style={{ background: m.color || "#0062D2" }}>
                          {m.icon || m.name?.[0]}
                        </div>
                        <span className="text-sm text-[var(--ink-2)] truncate">{m.name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      </div>

      {showCreate && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center sm:p-4" onClick={() => setShowCreate(false)}>
          <div className="bg-white rounded-t-2xl sm:rounded-xl w-full max-w-sm p-5 max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading font-semibold">New Task — {dayLabel(date)}</h3>
              <button onClick={() => setShowCreate(false)}><X size={16} /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Title *</label>
                <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" data-testid="dp-form-title" />
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Priority</label>
                <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                  {PRIORITIES.map((p) => <option key={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Time Slot (optional)</label>
                <input value={form.time_slot} onChange={(e) => setForm({ ...form, time_slot: e.target.value })}
                  placeholder="e.g. 09:00 - 10:30 or Morning"
                  className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" />
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Notes (optional)</label>
                <input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" />
              </div>
            </div>
            <button onClick={createFull} disabled={adding} className="btn-primary w-full justify-center mt-4 disabled:opacity-60" data-testid="dp-form-save">
              {adding ? "Adding…" : "Add Task"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
