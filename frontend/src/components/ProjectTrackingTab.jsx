import { useEffect, useState } from "react";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { HardHat, AlertTriangle, Image as ImageIcon, Plus, X } from "lucide-react";
import { toast } from "sonner";

const emptyLog = {
  log_date: new Date().toISOString().split("T")[0],
  supervisor_name: "",
  work_completed_today: "",
  labor_count: { skilled: 0, unskilled: 0 },
  site_hindrances: "",
  current_milestone: "",
  completion_percentage: 0,
};

/** Daily site execution log feed + "+ Log Daily Progress" drawer for a
 * project — labor counts, work done, milestone %, hindrances, photos. */
export default function ProjectTrackingTab({ project, onProjectUpdated }) {
  const [logs, setLogs] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...emptyLog, completion_percentage: project.completion_percentage || 0 });
  const [saving, setSaving] = useState(false);

  const load = () => {
    api.get(`/projects/${project.id}/daily-logs`).then(({ data }) => setLogs(data)).catch(() => setLogs([]));
  };

  useEffect(load, [project.id]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.supervisor_name || !form.work_completed_today) {
      toast.error("Supervisor name and work summary are required");
      return;
    }
    setSaving(true);
    try {
      await api.post(`/projects/${project.id}/daily-logs`, form);
      toast.success("Daily log saved");
      setShowForm(false);
      setForm({ ...emptyLog, completion_percentage: project.completion_percentage || 0 });
      load();
      const { data } = await api.get("/projects");
      const updated = data.find((p) => p.id === project.id);
      if (updated) onProjectUpdated(updated);
    } catch {
      toast.error("Failed to save daily log");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4" data-testid="project-tracking-tab">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-semibold flex items-center gap-1.5">
          <HardHat size={15} className="text-[var(--brand)]" /> Site Execution Log
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[var(--brand-light)] text-[var(--brand)] text-xs font-medium hover:bg-[var(--brand)] hover:text-white transition"
          data-testid="log-daily-progress-open"
        >
          <Plus size={13} /> Log Daily Progress
        </button>
      </div>

      {logs.length === 0 && <div className="text-xs text-[var(--ink-3)] py-3 text-center">No site logs yet</div>}

      <div className="space-y-2 max-h-72 overflow-y-auto">
        {logs.map((l) => (
          <div key={l.id} className="rounded-lg border border-[var(--border-light)] p-2.5 text-xs" data-testid={`daily-log-${l.id}`}>
            <div className="flex items-center justify-between mb-1">
              <span className="font-semibold">{fmtDate(l.log_date)}</span>
              <span className="text-[var(--ink-3)]">{l.supervisor_name}</span>
            </div>
            <div className="text-[var(--ink-2)] mb-1">{l.work_completed_today}</div>
            <div className="flex items-center gap-2 flex-wrap text-[11px] text-[var(--ink-3)]">
              <span className="px-1.5 py-0.5 rounded bg-[var(--surface-2)]">
                Skilled {l.labor_count?.skilled || 0} · Unskilled {l.labor_count?.unskilled || 0}
              </span>
              {l.current_milestone && (
                <span className="px-1.5 py-0.5 rounded bg-[var(--brand-light)] text-[var(--brand)]">{l.current_milestone}</span>
              )}
              {l.site_photos?.length > 0 && (
                <span className="flex items-center gap-0.5"><ImageIcon size={11} /> {l.site_photos.length}</span>
              )}
            </div>
            {l.site_hindrances && (
              <div className="flex items-start gap-1 mt-1.5 text-amber-700">
                <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                <span>{l.site_hindrances}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
          <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-md shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-sm">Log Daily Progress</h3>
              <button onClick={() => setShowForm(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <form onSubmit={submit} className="p-5 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Date</label>
                  <input type="date" value={form.log_date} onChange={(e) => setForm({ ...form, log_date: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Supervisor *</label>
                  <input type="text" value={form.supervisor_name} onChange={(e) => setForm({ ...form, supervisor_name: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Work Completed Today *</label>
                <textarea rows={2} value={form.work_completed_today} onChange={(e) => setForm({ ...form, work_completed_today: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Skilled Labor</label>
                  <input type="number" min={0} value={form.labor_count.skilled}
                    onChange={(e) => setForm({ ...form, labor_count: { ...form.labor_count, skilled: +e.target.value } })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)] font-mono" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Unskilled Labor</label>
                  <input type="number" min={0} value={form.labor_count.unskilled}
                    onChange={(e) => setForm({ ...form, labor_count: { ...form.labor_count, unskilled: +e.target.value } })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)] font-mono" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Milestone</label>
                <input type="text" placeholder="e.g. Carpentry done" value={form.current_milestone}
                  onChange={(e) => setForm({ ...form, current_milestone: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">
                  Completion — {form.completion_percentage}%
                </label>
                <input type="range" min={0} max={100} value={form.completion_percentage}
                  onChange={(e) => setForm({ ...form, completion_percentage: +e.target.value })}
                  className="w-full" data-testid="completion-slider" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Site Hindrances</label>
                <textarea rows={2} placeholder="Power cuts, client site delays, water leakage…" value={form.site_hindrances}
                  onChange={(e) => setForm({ ...form, site_hindrances: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
              </div>
              <div className="pt-1 flex items-center justify-end gap-2">
                <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-xs font-semibold rounded-lg border border-[var(--border)] hover:bg-[var(--surface-2)]">
                  Cancel
                </button>
                <button type="submit" disabled={saving} className="px-5 py-2 text-xs font-semibold rounded-lg bg-[var(--brand)] text-white hover:opacity-90 disabled:opacity-60" data-testid="log-daily-progress-save">
                  {saving ? "Saving…" : "Save Log"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
