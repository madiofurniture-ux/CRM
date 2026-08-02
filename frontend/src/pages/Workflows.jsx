import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import {
  Workflow, Plus, Trash2, ChevronUp, ChevronDown, Save, RotateCcw,
  Wand2, Lock, Unlock, Flag, Trophy,
} from "lucide-react";

/**
 * Admin screen: define the stages each entity moves through.
 *
 * Stages used to be hardcoded in one business's vocabulary. Here every business
 * describes its own pipeline — and can adopt the stages its data already uses
 * rather than being forced onto someone else's words.
 */
const ENTITY_LABEL = {
  lead: "Leads", customer: "Customers", quote: "Quotations", sale: "Sales",
  project: "Projects", product: "Products", task: "Tasks",
};

export default function Workflows() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [all, setAll] = useState({});
  const [entity, setEntity] = useState("lead");
  const [stages, setStages] = useState([]);
  const [enforced, setEnforced] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/workflows");
      setAll(data);
      const cur = data[entity];
      setStages(cur?.stages ? cur.stages.map((s) => ({ ...s })) : []);
      setEnforced(!!cur?.enforced);
      setDirty(false);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);           // eslint-disable-line
  useEffect(() => {
    const cur = all[entity];
    if (cur) {
      setStages(cur.stages.map((s) => ({ ...s })));
      setEnforced(!!cur.enforced);
      setDirty(false);
    }
  }, [entity]);                                // eslint-disable-line

  const mutate = (fn) => { fn(); setDirty(true); };
  const setAt = (i, patch) =>
    mutate(() => setStages((p) => p.map((s, idx) => (idx === i ? { ...s, ...patch } : s))));
  const move = (i, d) =>
    mutate(() => setStages((p) => {
      const n = [...p], j = i + d;
      if (j < 0 || j >= n.length) return p;
      [n[i], n[j]] = [n[j], n[i]];
      return n;
    }));
  const remove = (i) => mutate(() => setStages((p) => p.filter((_, idx) => idx !== i)));
  const add = () =>
    mutate(() => setStages((p) => [...p, { key: "", label: "", terminal: false, won: false }]));

  const save = async (force = false) => {
    if (stages.some((s) => !s.label.trim())) {
      toast.error("Every stage needs a name");
      return;
    }
    setSaving(true);
    try {
      await api.put(`/workflows/${entity}`, { stages, enforce: enforced, force });
      toast.success(`${ENTITY_LABEL[entity]} workflow saved`);
      await load();
    } catch (e) {
      const d = e.response?.data?.detail;
      // 409: existing records sit on stages this change would remove.
      if (e.response?.status === 409 && d?.orphaned_stages) {
        const list = d.orphaned_stages.join(", ");
        if (window.confirm(
          `Records still use these stages:\n\n${list}\n\n` +
          `Removing them leaves those records on a stage that no longer exists. ` +
          `Renaming instead keeps them valid.\n\nRemove anyway?`)) {
          await save(true);
        }
      } else {
        toast.error(formatApiError(d));
      }
    } finally {
      setSaving(false);
    }
  };

  const adopt = async () => {
    if (!window.confirm(
      `Build the ${ENTITY_LABEL[entity]} workflow from the stages your records already use?\n\n` +
      `Nothing existing becomes invalid — this is the safe way to switch enforcement on.`)) return;
    try {
      const { data } = await api.post(`/workflows/${entity}/adopt`, { enforce: true });
      toast.success(`Learned ${data.adopted_from_records} stage(s) from your data`);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const reset = async () => {
    if (!window.confirm(`Reset ${ENTITY_LABEL[entity]} back to the default stages?`)) return;
    try {
      await api.post(`/workflows/${entity}/reset`);
      toast.success("Reset to defaults");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const cur = all[entity] || {};

  return (
    <>
      <Topbar
        title="Workflows"
        subtitle={`How each record moves through your business · ${Object.keys(ENTITY_LABEL).length} entities`}
      />

      <div className="p-6 space-y-5">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 text-sm text-[var(--ink-2)] flex gap-3">
          <Workflow size={18} className="shrink-0 mt-0.5 text-[var(--brand)]" />
          <div>
            Set the stages each type of record moves through. Mark the ones that
            <b> end</b> the journey, and which of those count as a <b>win</b> in reports.
            <br />
            <span className="text-[var(--ink-3)]">
              Stages are only enforced once you turn enforcement on — until then your
              team can type anything and existing records keep working.
            </span>
          </div>
        </div>

        {/* entity picker */}
        <div className="flex flex-wrap gap-2" data-testid="wf-entities">
          {Object.keys(ENTITY_LABEL).map((k) => (
            <button
              key={k}
              onClick={() => setEntity(k)}
              data-testid={`wf-tab-${k}`}
              className={`px-3 py-1.5 rounded-lg text-sm border transition ${
                entity === k
                  ? "bg-[var(--brand)] text-white border-[var(--brand)]"
                  : "border-[var(--border)] hover:border-[var(--brand)]"
              }`}
            >
              {ENTITY_LABEL[k]}
              {all[k]?.customised && (
                <span className="ml-1.5 text-[10px] opacity-75">
                  {all[k]?.enforced ? "locked" : "custom"}
                </span>
              )}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-sm text-[var(--ink-3)]">Loading…</div>
        ) : (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
            <div className="px-4 py-3 border-b border-[var(--border)] flex items-center gap-3 flex-wrap">
              <div className="font-heading font-semibold flex-1">
                {ENTITY_LABEL[entity]} stages
                <span className="ml-2 text-xs font-normal text-[var(--ink-3)]">
                  {cur.customised ? "your own" : "using defaults"}
                </span>
              </div>

              <button
                onClick={() => { setEnforced((v) => !v); setDirty(true); }}
                disabled={!isAdmin}
                data-testid="wf-enforce"
                title={enforced
                  ? "Records must use one of these stages"
                  : "Any stage is accepted; these are only suggestions"}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs ${
                  enforced
                    ? "border-emerald-500 text-emerald-600"
                    : "border-[var(--border)] text-[var(--ink-3)]"
                } disabled:opacity-40`}
              >
                {enforced ? <Lock size={13} /> : <Unlock size={13} />}
                {enforced ? "Enforced" : "Not enforced"}
              </button>

              <button onClick={adopt} disabled={!isAdmin} data-testid="wf-adopt"
                      className="btn-ghost text-xs disabled:opacity-40"
                      title="Build this workflow from stages your records already use">
                <Wand2 size={13} /> Use my data
              </button>
              <button onClick={reset} disabled={!isAdmin} data-testid="wf-reset"
                      className="btn-ghost text-xs disabled:opacity-40">
                <RotateCcw size={13} /> Reset
              </button>
            </div>

            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] text-[var(--ink-3)]">
                <tr className="text-[11px] uppercase tracking-wider">
                  <th className="w-16 px-3 py-2 text-left">Order</th>
                  <th className="px-3 py-2 text-left">Stage name</th>
                  <th className="w-28 px-3 py-2 text-center">Ends here</th>
                  <th className="w-28 px-3 py-2 text-center">Counts as won</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {stages.map((s, i) => (
                  <tr key={i} className="border-t border-[var(--border)]" data-testid={`wf-stage-${i}`}>
                    <td className="px-3 py-2">
                      <div className="flex gap-0.5">
                        <button onClick={() => move(i, -1)} disabled={i === 0 || !isAdmin}
                                className="p-1 rounded hover:bg-[var(--surface-2)] disabled:opacity-25">
                          <ChevronUp size={13} />
                        </button>
                        <button onClick={() => move(i, 1)} disabled={i === stages.length - 1 || !isAdmin}
                                className="p-1 rounded hover:bg-[var(--surface-2)] disabled:opacity-25">
                          <ChevronDown size={13} />
                        </button>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <input
                        value={s.label}
                        disabled={!isAdmin}
                        placeholder="e.g. Site Visit"
                        onChange={(e) => setAt(i, { label: e.target.value })}
                        className="w-full px-2 py-1.5 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)] disabled:opacity-60"
                      />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <button onClick={() => setAt(i, { terminal: !s.terminal })} disabled={!isAdmin}
                              title="Nothing happens after this stage"
                              className={`p-1.5 rounded-lg border ${s.terminal
                                ? "border-[var(--brand)] text-[var(--brand)]"
                                : "border-[var(--border)] text-[var(--ink-3)]"} disabled:opacity-40`}>
                        <Flag size={13} />
                      </button>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <button onClick={() => setAt(i, { won: !s.won })} disabled={!isAdmin}
                              title="Reports count this as a success"
                              className={`p-1.5 rounded-lg border ${s.won
                                ? "border-emerald-500 text-emerald-600"
                                : "border-[var(--border)] text-[var(--ink-3)]"} disabled:opacity-40`}>
                        <Trophy size={13} />
                      </button>
                    </td>
                    <td className="px-2 py-2">
                      <button onClick={() => remove(i)} disabled={!isAdmin || stages.length <= 1}
                              className="p-1 rounded text-[var(--danger)] hover:bg-[var(--danger-soft)] disabled:opacity-25">
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
                {!stages.length && (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-[var(--ink-3)]">
                    No stages yet — add the first.
                  </td></tr>
                )}
              </tbody>
            </table>

            {isAdmin && (
              <div className="px-4 py-3 border-t border-[var(--border)] flex items-center gap-2">
                <button onClick={add} data-testid="wf-add" className="btn-ghost text-sm">
                  <Plus size={14} /> Add stage
                </button>
                <div className="flex-1" />
                <button
                  onClick={() => save(false)}
                  disabled={saving || !dirty}
                  data-testid="wf-save"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--brand)] text-white text-sm disabled:opacity-40"
                >
                  <Save size={15} />
                  {saving ? "Saving…" : dirty ? "Save workflow" : "Saved"}
                </button>
              </div>
            )}
          </div>
        )}

        {!isAdmin && (
          <div className="text-sm text-[var(--ink-3)]">
            Only an administrator can change workflows.
          </div>
        )}
      </div>
    </>
  );
}
