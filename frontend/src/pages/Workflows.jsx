import { useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import StagePath from "@/components/StagePath";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import {
  Plus, Trash2, ChevronUp, ChevronDown, Save, RotateCcw, Wand2, Lock, Zap,
} from "lucide-react";

/**
 * Admin screen: how each type of record moves through the business.
 *
 * For every record type (lead, quotation, project, vendor order, …) an admin
 * sets the stages, and for each stage: its forecast probability, guidance
 * shown on the record's Path, the fields that must be filled before a record
 * may enter it, and which stages may follow. Automations run when a record
 * is created or enters a stage. Gates only bind once "Enforce" is on.
 *
 * Record types marked "System stages" (projects, vendor orders, POs,
 * invoices, tasks) have a fixed stage list the rest of the CRM depends on —
 * everything about each stage is configurable, the list itself is not.
 */
const ORDER = ["visitor", "lead", "quote", "sale", "customer", "project",
  "vendor_order", "purchase_order", "invoice", "task", "product"];

const MESSAGE_TEMPLATES = {
  quote_created: "Quotation created",
  order_confirmed: "Order confirmed",
  installation_scheduled: "Installation scheduled",
  payment_cleared: "Payment received in full",
  payment_reminder: "Payment reminder",
  follow_up: "Follow-up",
};

const blankStage = () => ({
  key: "", label: "", terminal: false, won: false, color: "", probability: null,
  guidance: "", required_fields: [], next: [],
});

const blankAction = (type = "create_task") => ({
  create_task: { type, title: "Follow up on {record}", due_in_days: 1, priority: "Medium", assign_to: "owner" },
  set_field: { type, field: "", value: "" },
  notify_customer: { type, event: "follow_up" },
}[type]);

const keyOf = (label) => String(label || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
const fieldCls = "px-2.5 py-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border-strong,var(--color-border))] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)] disabled:opacity-60";
const inputCls = `${fieldCls} w-full`;

export default function Workflows() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [all, setAll] = useState({});
  const [entity, setEntity] = useState("lead");
  const [draft, setDraft] = useState(null);      // {stages, rules, enforced}
  const [dirty, setDirty] = useState(false);
  const [sel, setSel] = useState(0);
  const [tab, setTab] = useState("stages");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const cur = all[entity];
  const locked = !!cur?.locked;
  const fields = useMemo(() => cur?.fields || [], [cur]);

  const load = async (keep = entity) => {
    setLoading(true);
    try {
      const { data } = await api.get("/workflows", { skipCache: true });
      setAll(data);
      pick(data, keep);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  const pick = (data, e) => {
    const w = data[e];
    setEntity(e);
    setDraft(w ? {
      stages: w.stages.map((s) => ({ ...blankStage(), ...s })),
      rules: (w.rules || []).map((r) => ({ ...r, actions: r.actions.map((a) => ({ ...a })) })),
      enforced: !!w.enforced,
    } : null);
    setSel(0);
    setDirty(false);
  };

  useEffect(() => { load(); }, []);            // eslint-disable-line

  const switchTo = (e) => {
    if (e === entity) return;
    if (dirty && !window.confirm("You have unsaved changes to this workflow. Discard them?")) return;
    pick(all, e);
  };

  const edit = (fn) => { setDraft((d) => fn(structuredClone(d))); setDirty(true); };
  const setStage = (i, patch) => edit((d) => { Object.assign(d.stages[i], patch); return d; });

  const moveStage = (i, dir) => edit((d) => {
    const j = i + dir;
    if (j < 0 || j >= d.stages.length) return d;
    [d.stages[i], d.stages[j]] = [d.stages[j], d.stages[i]];
    setSel(j);
    return d;
  });

  const removeStage = (i) => edit((d) => {
    const gone = d.stages[i].key || keyOf(d.stages[i].label);
    d.stages.splice(i, 1);
    d.stages.forEach((s) => { s.next = (s.next || []).filter((k) => k !== gone); });
    setSel(Math.max(0, i - 1));
    return d;
  });

  const addStage = () => edit((d) => {
    d.stages.push(blankStage());
    setSel(d.stages.length - 1);
    return d;
  });

  const save = async (force = false) => {
    if (draft.stages.some((s) => !s.label.trim())) {
      toast.error("Every stage needs a name");
      return;
    }
    setSaving(true);
    try {
      const stages = draft.stages.map((s) => ({ ...s, key: s.key || keyOf(s.label) }));
      await api.put(`/workflows/${entity}`, {
        stages, rules: draft.rules, enforce: draft.enforced, force,
      });
      toast.success(`${cur.label} workflow saved`);
      await load(entity);
    } catch (e) {
      const d = e.response?.data?.detail;
      if (e.response?.status === 409 && d?.orphaned_stages) {
        if (window.confirm(
          `Records still use these stages:\n\n${d.orphaned_stages.join(", ")}\n\n` +
          "Removing them leaves those records on a stage that no longer exists. " +
          "Renaming a stage instead keeps them valid.\n\nRemove anyway?")) {
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
      `Build the ${cur.label} workflow from the stages your records already use?\n\n` +
      "Nothing existing becomes invalid, so this is the safe way to switch enforcement on.")) return;
    try {
      const { data } = await api.post(`/workflows/${entity}/adopt`, { enforce: true });
      toast.success(`Found ${data.adopted_from_records} stage(s) in your records`);
      await load(entity);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const reset = async () => {
    if (!window.confirm(`Reset ${cur.label} to the default stages? This also removes its automations.`)) return;
    try {
      await api.post(`/workflows/${entity}/reset`);
      toast.success(`${cur.label} reset to defaults`);
      await load(entity);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  // A useWorkflow-shaped object over the draft, so the Path preview shows
  // unsaved edits exactly as a record page will render them.
  const previewWf = useMemo(() => {
    if (!draft) return null;
    const stages = draft.stages.filter((s) => s.label.trim())
      .map((s) => ({ ...s, key: s.key || keyOf(s.label) }));
    return {
      stages, fields,
      stageOf: (v) => stages.find((s) => s.label.toLowerCase() === String(v || "").toLowerCase()) || null,
    };
  }, [draft, fields]);

  const stage = draft?.stages[sel];
  const readOnly = !isAdmin;

  return (
    <>
      <Topbar title="Workflows" subtitle="Stages, gates and automations for each type of record" />

      <div className="p-4 md:p-6 grid gap-5 lg:grid-cols-[14rem_1fr]">
        {/* Record types */}
        <nav aria-label="Record types" className="lg:sticky lg:top-4 self-start">
          <label htmlFor="wf-entity" className="sr-only">Record type</label>
          <select id="wf-entity" className={`${inputCls} lg:hidden`} value={entity}
                  onChange={(e) => switchTo(e.target.value)}>
            {ORDER.filter((k) => all[k]).map((k) => <option key={k} value={k}>{all[k].label}</option>)}
          </select>
          <ul className="hidden lg:block rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] py-1" data-testid="wf-entities">
            {ORDER.filter((k) => all[k]).map((k) => {
              const w = all[k];
              return (
                <li key={k}>
                  <button
                    type="button"
                    onClick={() => switchTo(k)}
                    data-testid={`wf-tab-${k}`}
                    aria-current={entity === k ? "page" : undefined}
                    className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 border-l-[3px] ${entity === k
                      ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)] font-semibold text-[var(--color-text)]"
                      : "border-transparent text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)]"}`}
                  >
                    <span className="flex-1">{w.label}</span>
                    {w.rules?.length > 0 && <Zap size={12} aria-label={`${w.rules.length} automations`} />}
                    {w.enforced && <Lock size={12} aria-label="Enforced" />}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        {loading || !draft ? (
          <div className="text-sm text-[var(--color-text-muted)]">Loading workflows…</div>
        ) : (
          <div className="min-w-0 space-y-4">
            {/* Header */}
            <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <div className="flex flex-wrap items-start gap-3">
                <div className="flex-1 min-w-[12rem]">
                  <h2 className="font-heading text-lg font-bold text-[var(--color-text)]">{cur.label}</h2>
                  <p className="text-sm text-[var(--color-text-muted)]">
                    {locked
                      ? "System stages: configure each stage below. The list itself is fixed because reports and costing depend on it."
                      : cur.customised ? "Your own stages." : "Using the default stages. Edit them or build them from your records."}
                  </p>
                </div>
                <label className={`inline-flex items-center gap-2 text-sm ${readOnly ? "opacity-60" : "cursor-pointer"}`}>
                  <input type="checkbox" className="h-4 w-4 accent-[var(--color-primary)]"
                         checked={draft.enforced} disabled={readOnly} data-testid="wf-enforce"
                         onChange={(e) => { setDraft((d) => ({ ...d, enforced: e.target.checked })); setDirty(true); }} />
                  Enforce stages and required fields
                </label>
                {!locked && (
                  <button onClick={adopt} disabled={readOnly} data-testid="wf-adopt" className="btn-ghost text-sm disabled:opacity-40">
                    <Wand2 size={14} /> Build from my records
                  </button>
                )}
                <button onClick={reset} disabled={readOnly || !cur.customised} data-testid="wf-reset" className="btn-ghost text-sm disabled:opacity-40">
                  <RotateCcw size={14} /> Reset
                </button>
                {isAdmin && (
                  <button onClick={() => save(false)} disabled={saving || !dirty} data-testid="wf-save" className="btn-primary disabled:opacity-40">
                    <Save size={14} /> {saving ? "Saving…" : dirty ? "Save workflow" : "Saved"}
                  </button>
                )}
              </div>
              <div className="mt-4">
                <p className="text-xs text-[var(--color-text-muted)] mb-1.5">Path preview: how a record's stage bar will look</p>
                <StagePath wf={previewWf} value={previewWf.stages[0]?.label} compact />
              </div>
              {!draft.enforced && (draft.stages.some((s) => s.required_fields?.length || s.next?.length)) && (
                <p className="mt-3 text-xs text-[var(--color-warning)]">
                  Required fields and allowed next stages only apply once "Enforce" is on.
                </p>
              )}
            </div>

            {/* Tabs */}
            <div role="tablist" className="flex gap-1 border-b border-[var(--color-border)]">
              {[["stages", `Stages (${draft.stages.length})`], ["rules", `Automations (${draft.rules.length})`]].map(([k, label]) => (
                <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                        className={`px-3 py-2 text-sm -mb-px border-b-2 ${tab === k
                          ? "border-[var(--color-primary)] text-[var(--color-primary)] font-semibold"
                          : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"}`}>
                  {label}
                </button>
              ))}
            </div>

            {tab === "stages" ? (
              <div className="grid gap-4 md:grid-cols-[16rem_1fr]">
                {/* Stage list */}
                <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)]">
                  <ol className="py-1">
                    {draft.stages.map((s, i) => (
                      <li key={i} className="flex items-center">
                        <button
                          type="button" onClick={() => setSel(i)} data-testid={`wf-stage-${i}`}
                          aria-current={sel === i ? "true" : undefined}
                          className={`flex-1 min-w-0 text-left px-3 py-2 text-sm flex items-center gap-2 border-l-[3px] ${sel === i
                            ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)]"
                            : "border-transparent hover:bg-[var(--color-surface-muted)]"}`}
                        >
                          <span className="w-5 text-xs text-[var(--color-text-muted)]">{i + 1}</span>
                          <span className="flex-1 truncate">{s.label || <em className="text-[var(--color-text-muted)]">Unnamed</em>}</span>
                          {s.terminal && (
                            <span className={`text-[11px] ${s.won ? "text-[var(--color-success)]" : "text-[var(--color-text-muted)]"}`}>
                              {s.won ? "Won" : "Closed"}
                            </span>
                          )}
                          {s.probability != null && !s.terminal && (
                            <span className="text-[11px] text-[var(--color-text-muted)]">{s.probability}%</span>
                          )}
                        </button>
                        {!locked && isAdmin && (
                          <span className="flex pr-1">
                            <button type="button" aria-label={`Move ${s.label} up`} onClick={() => moveStage(i, -1)} disabled={i === 0}
                                    className="p-1 rounded hover:bg-[var(--color-surface-muted)] disabled:opacity-25"><ChevronUp size={13} /></button>
                            <button type="button" aria-label={`Move ${s.label} down`} onClick={() => moveStage(i, 1)} disabled={i === draft.stages.length - 1}
                                    className="p-1 rounded hover:bg-[var(--color-surface-muted)] disabled:opacity-25"><ChevronDown size={13} /></button>
                          </span>
                        )}
                      </li>
                    ))}
                  </ol>
                  {!locked && isAdmin && (
                    <div className="border-t border-[var(--color-border)] p-2">
                      <button onClick={addStage} data-testid="wf-add" className="btn-ghost w-full justify-center text-sm">
                        <Plus size={14} /> Add stage
                      </button>
                    </div>
                  )}
                </div>

                {/* Stage detail */}
                {stage && (
                  <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-5">
                    <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
                      <div>
                        <label className="block text-sm font-medium mb-1" htmlFor="wf-stage-name">Stage name</label>
                        <input id="wf-stage-name" className={inputCls} value={stage.label} disabled={readOnly || locked}
                               placeholder="e.g. Site measurement" onChange={(e) => setStage(sel, { label: e.target.value })} />
                      </div>
                      <div>
                        <label className="block text-sm font-medium mb-1" htmlFor="wf-stage-prob">Probability %</label>
                        <input id="wf-stage-prob" type="number" min={0} max={100} className={inputCls} disabled={readOnly}
                               value={stage.probability ?? ""} placeholder="—"
                               onChange={(e) => setStage(sel, { probability: e.target.value === "" ? null : Math.max(0, Math.min(100, Number(e.target.value))) })} />
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-5 text-sm">
                      <label className="inline-flex items-center gap-2">
                        <input type="checkbox" className="h-4 w-4 accent-[var(--color-primary)]" disabled={readOnly}
                               checked={!!stage.terminal} onChange={(e) => setStage(sel, { terminal: e.target.checked, won: e.target.checked ? stage.won : false })} />
                        Closes the record
                      </label>
                      <label className="inline-flex items-center gap-2">
                        <input type="checkbox" className="h-4 w-4 accent-[var(--color-primary)]" disabled={readOnly}
                               checked={!!stage.won} onChange={(e) => setStage(sel, { won: e.target.checked })} />
                        Counts as won in reports
                      </label>
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-1" htmlFor="wf-stage-guidance">Guidance for success</label>
                      <textarea id="wf-stage-guidance" rows={3} className={inputCls} disabled={readOnly}
                                placeholder="What the team should do at this stage, e.g. confirm site measurements and share the colour catalogue."
                                value={stage.guidance || ""} onChange={(e) => setStage(sel, { guidance: e.target.value })} />
                    </div>

                    <fieldset>
                      <legend className="text-sm font-medium">Required before entering this stage</legend>
                      <p className="text-xs text-[var(--color-text-muted)] mb-2">Also shown as the stage's key fields on the record.</p>
                      <div className="grid gap-1.5 sm:grid-cols-2 xl:grid-cols-3 max-h-56 overflow-y-auto pr-1">
                        {fields.map((f) => (
                          <label key={f.key} className="inline-flex items-center gap-2 text-sm">
                            <input type="checkbox" className="h-4 w-4 accent-[var(--color-primary)]" disabled={readOnly}
                                   checked={(stage.required_fields || []).includes(f.key)}
                                   onChange={(e) => setStage(sel, {
                                     required_fields: e.target.checked
                                       ? [...(stage.required_fields || []), f.key]
                                       : (stage.required_fields || []).filter((k) => k !== f.key),
                                   })} />
                            {f.label}
                          </label>
                        ))}
                      </div>
                    </fieldset>

                    <fieldset>
                      <legend className="text-sm font-medium">Can move next to</legend>
                      <p className="text-xs text-[var(--color-text-muted)] mb-2">Leave all unticked to allow any stage.</p>
                      <div className="flex flex-wrap gap-x-5 gap-y-1.5">
                        {draft.stages.filter((_, j) => j !== sel && draft.stages[j].label.trim()).map((s) => {
                          const k = s.key || keyOf(s.label);
                          return (
                            <label key={k} className="inline-flex items-center gap-2 text-sm">
                              <input type="checkbox" className="h-4 w-4 accent-[var(--color-primary)]" disabled={readOnly}
                                     checked={(stage.next || []).includes(k)}
                                     onChange={(e) => setStage(sel, {
                                       next: e.target.checked ? [...(stage.next || []), k] : (stage.next || []).filter((x) => x !== k),
                                     })} />
                              {s.label}
                            </label>
                          );
                        })}
                      </div>
                    </fieldset>

                    {!locked && isAdmin && (
                      <div className="pt-2 border-t border-[var(--color-border)]">
                        <button type="button" onClick={() => removeStage(sel)} disabled={draft.stages.length <= 1}
                                className="inline-flex items-center gap-1.5 text-sm text-[var(--color-danger)] disabled:opacity-40">
                          <Trash2 size={14} /> Remove stage
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <RulesEditor draft={draft} edit={edit} fields={fields} readOnly={readOnly} />
            )}

            {!isAdmin && (
              <p className="text-sm text-[var(--color-text-muted)]">Only an administrator can change workflows.</p>
            )}
          </div>
        )}
      </div>
    </>
  );
}

function RulesEditor({ draft, edit, fields, readOnly }) {
  const settable = fields.filter((f) => f.settable);
  const stages = draft.stages.filter((s) => s.label.trim());

  const setRule = (i, patch) => edit((d) => { Object.assign(d.rules[i], patch); return d; });
  const setAction = (i, j, patch) => edit((d) => { Object.assign(d.rules[i].actions[j], patch); return d; });

  const addRule = () => edit((d) => {
    d.rules.push({
      name: "", active: true, trigger: "stage_enter",
      stage: stages[0] ? (stages[0].key || keyOf(stages[0].label)) : "",
      actions: [blankAction()],
    });
    return d;
  });

  if (!draft.rules.length) {
    return (
      <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border-strong,var(--color-border))] bg-[var(--color-surface)] p-8 text-center">
        <Zap className="mx-auto mb-2 text-[var(--color-primary)]" size={22} />
        <p className="font-semibold text-[var(--color-text)]">No automations yet</p>
        <p className="text-sm text-[var(--color-text-muted)] max-w-md mx-auto mt-1">
          Have the CRM do the routine step for you. For example, when a quotation is won,
          create a task for its owner to raise the vendor PO.
        </p>
        {!readOnly && (
          <button onClick={addRule} className="btn-primary mt-4"><Plus size={14} /> Add automation</button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {draft.rules.map((r, i) => (
        <div key={r.id || i} className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3" data-testid={`wf-rule-${i}`}>
          <div className="flex flex-wrap items-center gap-3">
            <input className={`${fieldCls} flex-1 min-w-[12rem] font-medium`} placeholder="Name this automation" disabled={readOnly}
                   aria-label="Automation name" value={r.name} onChange={(e) => setRule(i, { name: e.target.value })} />
            <label className="inline-flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4 accent-[var(--color-primary)]" disabled={readOnly}
                     checked={r.active !== false} onChange={(e) => setRule(i, { active: e.target.checked })} />
              Active
            </label>
            {!readOnly && (
              <button type="button" aria-label="Delete automation" onClick={() => edit((d) => { d.rules.splice(i, 1); return d; })}
                      className="p-1.5 rounded text-[var(--color-danger)] hover:bg-[var(--danger-soft)]"><Trash2 size={14} /></button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-[var(--color-text-muted)]">When a record</span>
            <select className={`${fieldCls} w-auto`} disabled={readOnly} aria-label="Trigger" value={r.trigger}
                    onChange={(e) => setRule(i, { trigger: e.target.value })}>
              <option value="stage_enter">enters the stage</option>
              <option value="created">is created</option>
            </select>
            {r.trigger === "stage_enter" && (
              <select className={`${fieldCls} w-auto`} disabled={readOnly} aria-label="Stage" value={r.stage}
                      onChange={(e) => setRule(i, { stage: e.target.value })}>
                {stages.map((s) => {
                  const k = s.key || keyOf(s.label);
                  return <option key={k} value={k}>{s.label}</option>;
                })}
              </select>
            )}
          </div>

          <ol className="space-y-2">
            {r.actions.map((a, j) => (
              <li key={j} className="rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] p-3 flex flex-wrap items-start gap-2 text-sm">
                <select className={`${fieldCls} w-auto`} disabled={readOnly} aria-label="Action" value={a.type}
                        onChange={(e) => edit((d) => { d.rules[i].actions[j] = blankAction(e.target.value); return d; })}>
                  <option value="create_task">Create a task</option>
                  <option value="set_field">Update a field</option>
                  <option value="notify_customer">Message the customer</option>
                </select>

                {a.type === "create_task" && (
                  <>
                    <input className={`${fieldCls} flex-1 min-w-[14rem]`} disabled={readOnly} aria-label="Task title"
                           value={a.title} onChange={(e) => setAction(i, j, { title: e.target.value })} />
                    <label className="inline-flex items-center gap-1.5">
                      due in
                      <input type="number" min={0} max={365} className={`${fieldCls} w-16`} disabled={readOnly}
                             aria-label="Due in days" value={a.due_in_days}
                             onChange={(e) => setAction(i, j, { due_in_days: Number(e.target.value) || 0 })} />
                      days
                    </label>
                    <select className={`${fieldCls} w-auto`} disabled={readOnly} aria-label="Priority" value={a.priority}
                            onChange={(e) => setAction(i, j, { priority: e.target.value })}>
                      {["Low", "Medium", "High", "Urgent"].map((p) => <option key={p}>{p}</option>)}
                    </select>
                    <select className={`${fieldCls} w-auto`} disabled={readOnly} aria-label="Assign to"
                            value={["owner", "actor"].includes(a.assign_to) ? a.assign_to : "named"}
                            onChange={(e) => setAction(i, j, { assign_to: e.target.value === "named" ? "" : e.target.value })}>
                      <option value="owner">for the record owner</option>
                      <option value="actor">for whoever moved it</option>
                      <option value="named">for a named person</option>
                    </select>
                    {!["owner", "actor"].includes(a.assign_to) && (
                      <input className={`${fieldCls} w-40`} disabled={readOnly} placeholder="Team member name"
                             aria-label="Assignee name" value={a.assign_to}
                             onChange={(e) => setAction(i, j, { assign_to: e.target.value })} />
                    )}
                    <p className="basis-full text-xs text-[var(--color-text-muted)]">
                      Use {"{record}"} for the customer or record name and {"{stage}"} for the stage.
                    </p>
                  </>
                )}

                {a.type === "set_field" && (() => {
                  const spec = settable.find((f) => f.key === a.field);
                  return (
                    <>
                      <select className={`${fieldCls} w-auto`} disabled={readOnly} aria-label="Field" value={a.field}
                              onChange={(e) => setAction(i, j, { field: e.target.value, value: "" })}>
                        <option value="">Choose field…</option>
                        {settable.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                      </select>
                      {spec?.type === "bool" ? (
                        <label className="inline-flex items-center gap-2">
                          <input type="checkbox" className="h-4 w-4 accent-[var(--color-primary)]" disabled={readOnly}
                                 checked={!!a.value} onChange={(e) => setAction(i, j, { value: e.target.checked })} />
                          Yes
                        </label>
                      ) : (
                        <input className={`${fieldCls} flex-1 min-w-[12rem]`} disabled={readOnly || !a.field}
                               aria-label="New value" placeholder="New value" value={a.value ?? ""}
                               onChange={(e) => setAction(i, j, { value: e.target.value })} />
                      )}
                    </>
                  );
                })()}

                {a.type === "notify_customer" && (
                  <>
                    <select className={`${fieldCls} w-auto`} disabled={readOnly} aria-label="Message" value={a.event}
                            onChange={(e) => setAction(i, j, { event: e.target.value })}>
                      {Object.entries(MESSAGE_TEMPLATES).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
                    </select>
                    <span className="text-xs text-[var(--color-text-muted)] self-center">
                      Sent to the record's phone number and logged under notifications.
                    </span>
                  </>
                )}

                {!readOnly && r.actions.length > 1 && (
                  <button type="button" aria-label="Remove action" className="ml-auto p-1.5 rounded text-[var(--color-danger)] hover:bg-[var(--danger-soft)]"
                          onClick={() => edit((d) => { d.rules[i].actions.splice(j, 1); return d; })}>
                    <Trash2 size={13} />
                  </button>
                )}
              </li>
            ))}
          </ol>
          {!readOnly && r.actions.length < 5 && (
            <button type="button" className="btn-ghost text-sm"
                    onClick={() => edit((d) => { d.rules[i].actions.push(blankAction()); return d; })}>
              <Plus size={14} /> Add action
            </button>
          )}
        </div>
      ))}
      {!readOnly && draft.rules.length < 25 && (
        <button onClick={addRule} className="btn-ghost"><Plus size={14} /> Add automation</button>
      )}
    </div>
  );
}
