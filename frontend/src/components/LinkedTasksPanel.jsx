import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { CheckCircle2, Circle, ListTodo } from "lucide-react";

// Tasks linked to one Lead/Project via Task.ref+ref_type, with a 1-click
// "+ Add Daily Task" that pre-populates the link. Reused by Leads.jsx and
// Projects.jsx — no /tasks?ref= filter exists server-side, so this filters
// the same full list Tasks.jsx already fetches client-side (consistent with
// this app's small-scale-data style elsewhere, e.g. Cashbook.jsx).
export default function LinkedTasksPanel({ refId, refType, entityName }) {
  const [tasks, setTasks] = useState([]);
  const [title, setTitle] = useState("");
  const [adding, setAdding] = useState(false);

  const load = () => {
    api.get("/tasks").then(({ data }) => setTasks(data.filter((t) => t.ref === refId))).catch(() => setTasks([]));
  };
  useEffect(load, [refId]); // eslint-disable-line

  const toggle = async (t) => {
    await api.patch(`/daily-planner/${t.id}/toggle`, {});
    load();
  };

  const addTask = async (e) => {
    e.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || adding) return;
    setAdding(true);
    try {
      await api.post("/daily-planner", {
        title: trimmed, ref: refId, ref_type: refType, linked_entity_name: entityName,
        date: new Date().toISOString().slice(0, 10),
      });
      setTitle("");
      load();
    } catch { toast.error("Couldn't add task"); }
    finally { setAdding(false); }
  };

  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-2 flex items-center gap-1.5">
        <ListTodo size={12} /> Daily Tasks
      </div>
      <form onSubmit={addTask} className="flex gap-1.5 mb-2">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="+ Add Daily Task…"
          className="flex-1 px-2.5 py-1.5 rounded-lg border border-[var(--border)] bg-white text-xs outline-none focus:border-[var(--brand)]"
          data-testid="linked-task-add-input" />
      </form>
      {tasks.length === 0 ? (
        <div className="text-xs text-[var(--ink-3)]">No linked tasks yet.</div>
      ) : (
        <div className="space-y-1">
          {tasks.map((t) => (
            <button key={t.id} onClick={() => toggle(t)} className="flex items-center gap-2 w-full text-left" data-testid={`linked-task-${t.id}`}>
              {t.done ? <CheckCircle2 size={14} className="text-[var(--moss)] shrink-0" /> : <Circle size={14} className="text-[var(--ink-3)] shrink-0" />}
              <span className={`text-xs ${t.done ? "line-through text-[var(--ink-3)]" : "text-[var(--ink)]"}`}>{t.title}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
