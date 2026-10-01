import { useCallback, useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { toast } from "sonner";
import {
  Plus, Trash2, ChevronUp, ChevronDown, Save, Play, Zap, Clock, Edit2, X, FlaskConical, CheckCircle2, AlertCircle,
} from "lucide-react";

/**
 * Admin screen: Flows. Each flow watches one type of record and, when its
 * trigger fires and its conditions hold, runs its steps in order: create a
 * task, alert a teammate, set a field, assign the owner, WhatsApp the
 * customer, or wait some days first. Scheduled triggers ("2 days before a
 * quote expires", "stuck in Negotiation for 7 days") are checked every 10
 * minutes. Every run is logged with what each step did.
 */
const fieldCls = "px-2.5 py-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border-strong,var(--color-border))] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)]";
const inputCls = `${fieldCls} w-full`;
const labelCls = "block text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)] mb-1";

// Where each record type lists its records, for the dry-run picker.
const LIST_PATH = {
  visitor: "/visitors", lead: "/leads", customer: "/customers", quote: "/quotes", sale: "/sales",
  project: "/projects", vendor_order: "/manufacturer-orders", purchase_order: "/purchase-orders",
  invoice: "/invoices", product: "/inventory", task: "/tasks",
};
const recordLabel = (r) => r.quote_no || r.sale_no || r.invoice_no || r.project_no || r.order_code
  || r.po_no || r.name || r.customer || r.title || r.id;

const blankStep = (type) => ({
  create_task: { type, title: "Follow up on {record}", due_in_days: 1, priority: "Medium", assign_to: "owner" },
  alert_user: { type, user: "", message: "{record} needs your attention" },
  set_field: { type, field: "", value: "" },
  assign_owner: { type, user: "" },
  notify_customer: { type, event: "follow_up" },
  wait: { type, days: 1 },
}[type]);

const blankFlow = (entity = "lead") => ({
  name: "", description: "", entity, active: true,
  trigger: { type: "created" }, conditions: [], match: "all",
  steps: [blankStep("create_task")],
});

// Starting points an admin adapts, not flows saved behind their back.
const TEMPLATES = [
  {
    label: "Quotation expiring in 2 days",
    flow: {
      name: "Chase quotations before they expire", entity: "quote",
      trigger: { type: "date_relative", field: "valid_until", offset_days: -2 },
      conditions: [], match: "all",
      steps: [{ type: "create_task", title: "{quote_no} for {customer} expires in 2 days: call them", due_in_days: 0, priority: "High", assign_to: "owner" }],
    },
  },
  {
    label: "Lead stuck in Negotiation for 7 days",
    flow: {
      name: "Escalate stalled negotiations", entity: "lead",
      trigger: { type: "stage_stale", stage: "negotiation", days: 7 },
      conditions: [], match: "all",
      steps: [{ type: "alert_user", user: "", message: "{name} has been in Negotiation for a week" }],
    },
  },
  {
    label: "Big new lead",
    flow: {
      name: "Big lead: alert the manager", entity: "lead",
      trigger: { type: "created" },
      conditions: [{ field: "value", op: "gte", value: "500000" }], match: "all",
      steps: [
        { type: "alert_user", user: "", message: "New big lead {name}, value {value}" },
        { type: "wait", days: 2 },
        { type: "create_task", title: "Has {name} had a site visit?", due_in_days: 0, priority: "High", assign_to: "owner" },
      ],
    },
  },
];

const STATUS_TONE = {
  completed: "text-[var(--color-success,#15803d)]", waiting: "text-[var(--color-primary)]",
  running: "text-[var(--color-primary)]", failed: "text-[var(--color-danger)]",
  cancelled: "text-[var(--color-text-muted)]",
};

export default function Flows() {
  const [meta, setMeta] = useState(null);
  const [flows, setFlows] = useState([]);
  const [users, setUsers] = useState([]);
  const [tab, setTab] = useState("flows");
  const [editing, setEditing] = useState(null);   // a flow draft, or null
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [m, f] = await Promise.all([
        api.get("/flows/meta", { skipCache: true }), api.get("/flows", { skipCache: true }),
      ]);
      setMeta(m.data);
      setFlows(f.data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Couldn't load flows");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/users/directory").then(({ data }) => setUsers(data || [])).catch(() => setUsers([]));
  }, []);

  const toggle = async (flow) => {
    try {
      const { data } = await api.post(`/flows/${flow.id}/toggle`, { active: !flow.active });
      setFlows((fs) => fs.map((f) => (f.id === flow.id ? data : f)));
      toast.success(data.active ? "Flow switched on" : "Flow switched off");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Couldn't change it"); }
  };

  const remove = async (flow) => {
    if (!window.confirm(`Delete "${flow.name}"? Runs waiting on it are cancelled.`)) return;
    try {
      await api.delete(`/flows/${flow.id}`);
      setFlows((fs) => fs.filter((f) => f.id !== flow.id));
      toast.success("Flow deleted");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Couldn't delete it"); }
  };

  const runNow = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/flows/run-scheduled");
      toast.success(`Scheduled flows checked: ${data.started} started, ${data.resumed} resumed after a wait`);
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Couldn't run them"); }
    finally { setBusy(false); }
  };

  return (
    <>
      <Topbar
        title="Flows"
        subtitle="Automations that run when records change, or on a schedule"
        actions={
          <div className="flex items-center gap-2">
            <button type="button" onClick={runNow} disabled={busy} className="btn-ghost disabled:opacity-60" data-testid="flows-run-now"
                    title="Scheduled flows are checked every 10 minutes; this checks them now">
              <Play size={14} /> Run scheduled now
            </button>
            <button type="button" onClick={() => setEditing(blankFlow())} className="btn-primary" data-testid="flows-new">
              <Plus size={14} /> New flow
            </button>
          </div>
        }
      />
      <div className="p-4 md:p-6 space-y-4" data-testid="flows-page">
        <div role="tablist" className="flex gap-1 border-b border-[var(--color-border)]">
          {[["flows", `Flows (${flows.length})`], ["runs", "Run log"]].map(([k, l]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`flows-tab-${k}`}
                    className={`px-3 py-2 text-sm -mb-px border-b-2 ${tab === k ? "border-[var(--color-primary)] font-semibold" : "border-transparent text-[var(--color-text-muted)]"}`}>
              {l}
            </button>
          ))}
        </div>

        {tab === "runs" ? <RunLog flows={flows} /> : loading ? (
          <div className="text-sm text-[var(--color-text-muted)]">Loading flows…</div>
        ) : (
          <>
            {flows.length === 0 && (
              <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-5 bg-[var(--color-surface)]">
                <div className="font-semibold mb-1">No flows yet</div>
                <p className="text-sm text-[var(--color-text-muted)] mb-3">Start from one of these and adjust it, or build your own.</p>
                <div className="flex flex-wrap gap-2">
                  {TEMPLATES.map((t) => (
                    <button key={t.label} type="button" className="btn-ghost text-sm" onClick={() => setEditing({ ...blankFlow(), ...t.flow })}
                            data-testid={`flow-template-${t.flow.entity}-${t.flow.trigger.type}`}>
                      <Zap size={13} /> {t.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <ul className="grid gap-3 md:grid-cols-2">
              {flows.map((f) => (
                <li key={f.id} className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4" data-testid={`flow-${f.id}`}>
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold truncate">{f.name}</div>
                      <div className="text-sm text-[var(--color-text-muted)]">{f.summary}</div>
                      {f.description && <div className="text-xs text-[var(--color-text-muted)] mt-1">{f.description}</div>}
                      <div className="text-xs text-[var(--color-text-muted)] mt-2 flex items-center gap-3">
                        <span>{f.run_count || 0} run{f.run_count === 1 ? "" : "s"}</span>
                        {f.last_run_at && <span>Last {fmtDateTime(f.last_run_at)}</span>}
                        {meta?.triggers?.find((t) => t.key === f.trigger?.type)?.scheduled && <span className="inline-flex items-center gap-1"><Clock size={11} /> Scheduled</span>}
                      </div>
                    </div>
                    <label className="flex items-center gap-1.5 text-xs shrink-0 cursor-pointer">
                      <input type="checkbox" checked={!!f.active} onChange={() => toggle(f)} aria-label={`${f.name} on or off`} data-testid={`flow-toggle-${f.id}`} />
                      {f.active ? "On" : "Off"}
                    </label>
                  </div>
                  <div className="flex gap-2 mt-3">
                    <button type="button" className="btn-ghost text-xs" onClick={() => setEditing(f)} data-testid={`flow-edit-${f.id}`}><Edit2 size={12} /> Edit</button>
                    <button type="button" className="btn-ghost text-xs text-[var(--color-danger)]" onClick={() => remove(f)}><Trash2 size={12} /> Delete</button>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      {editing && meta && (
        <FlowEditor
          initial={editing} meta={meta} users={users}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setFlows((fs) => (fs.some((f) => f.id === saved.id) ? fs.map((f) => (f.id === saved.id ? saved : f)) : [saved, ...fs]));
            setEditing(null);
          }}
        />
      )}
    </>
  );
}

function FlowEditor({ initial, meta, users, onClose, onSaved }) {
  const [draft, setDraft] = useState(() => JSON.parse(JSON.stringify(initial)));
  const [saving, setSaving] = useState(false);
  const ent = useMemo(() => meta.entities.find((e) => e.entity === draft.entity) || meta.entities[0], [meta, draft.entity]);
  const fields = ent?.fields || [];
  const settable = fields.filter((f) => f.settable);
  const scheduled = meta.triggers.find((t) => t.key === draft.trigger.type)?.scheduled;

  const set = (patch) => setDraft((d) => ({ ...d, ...patch }));
  const setTrigger = (patch) => setDraft((d) => ({ ...d, trigger: { ...d.trigger, ...patch } }));
  const setCond = (i, patch) => setDraft((d) => ({ ...d, conditions: d.conditions.map((c, j) => (j === i ? { ...c, ...patch } : c)) }));
  const setStep = (i, patch) => setDraft((d) => ({ ...d, steps: d.steps.map((s, j) => (j === i ? { ...s, ...patch } : s)) }));
  const moveStep = (i, by) => setDraft((d) => {
    const steps = [...d.steps];
    const j = i + by;
    if (j < 0 || j >= steps.length) return d;
    [steps[i], steps[j]] = [steps[j], steps[i]];
    return { ...d, steps };
  });

  const changeTriggerType = (type) => {
    const t = { type };
    if (type === "stage_enter" || type === "stage_stale") t.stage = ent?.stages?.[0]?.key || "";
    if (type === "stage_stale") t.days = 7;
    if (type === "field_changed") t.field = fields[0]?.key || "";
    if (type === "date_relative") { t.field = ent?.date_fields?.[0] || ""; t.offset_days = -1; }
    set({ trigger: t });
  };

  const save = async () => {
    if (saving) return;
    setSaving(true);
    try {
      const body = { ...draft };
      const { data } = draft.id ? await api.put(`/flows/${draft.id}`, body) : await api.post("/flows", body);
      toast.success(draft.id ? "Flow saved" : "Flow created");
      onSaved(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Couldn't save the flow");
    } finally { setSaving(false); }
  };

  const userOptions = (value) => (
    <>
      <option value="">Pick a person…</option>
      {users.map((u) => <option key={u.id} value={u.name}>{u.name}</option>)}
      {value && !users.some((u) => u.name === value) && <option value={value}>{value}</option>}
    </>
  );

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex justify-end" onClick={onClose}>
      <div className="bg-[var(--color-surface)] w-full max-w-2xl h-full overflow-y-auto shadow-xl" onClick={(e) => e.stopPropagation()}
           role="dialog" aria-label={draft.id ? "Edit flow" : "New flow"} data-testid="flow-editor">
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
          <h2 className="font-semibold">{draft.id ? "Edit flow" : "New flow"}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1.5 rounded hover:bg-[var(--color-surface-muted)]"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-5">
          <section className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className={labelCls} htmlFor="flow-name">Name</label>
              <input id="flow-name" className={inputCls} value={draft.name} onChange={(e) => set({ name: e.target.value })}
                     placeholder="e.g. Chase quotations before they expire" data-testid="flow-name" />
            </div>
            <div>
              <label className={labelCls} htmlFor="flow-entity">Runs on</label>
              <select id="flow-entity" className={inputCls} value={draft.entity} disabled={!!draft.id}
                      onChange={(e) => setDraft({ ...blankFlow(e.target.value), name: draft.name, description: draft.description })}
                      data-testid="flow-entity">
                {meta.entities.map((e) => <option key={e.entity} value={e.entity}>{e.label}</option>)}
              </select>
            </div>
            <div>
              <label className={labelCls} htmlFor="flow-desc">Notes (optional)</label>
              <input id="flow-desc" className={inputCls} value={draft.description || ""} onChange={(e) => set({ description: e.target.value })} />
            </div>
          </section>

          <section>
            <h3 className="font-semibold text-sm mb-2">1. When</h3>
            <div className="grid gap-3 sm:grid-cols-2 rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] p-3">
              <div className="sm:col-span-2">
                <select className={inputCls} value={draft.trigger.type} onChange={(e) => changeTriggerType(e.target.value)}
                        aria-label="Trigger" data-testid="flow-trigger">
                  {meta.triggers.map((t) => <option key={t.key} value={t.key}>{t.label}{t.scheduled ? " (scheduled)" : ""}</option>)}
                </select>
              </div>
              {(draft.trigger.type === "stage_enter" || draft.trigger.type === "stage_stale") && (
                <div>
                  <label className={labelCls}>Stage</label>
                  <select className={inputCls} value={draft.trigger.stage || ""} onChange={(e) => setTrigger({ stage: e.target.value })} data-testid="flow-trigger-stage">
                    {ent.stages.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                  </select>
                </div>
              )}
              {draft.trigger.type === "stage_stale" && (
                <div>
                  <label className={labelCls}>For at least (days)</label>
                  <input type="number" min="1" className={inputCls} value={draft.trigger.days ?? 7} onChange={(e) => setTrigger({ days: parseInt(e.target.value, 10) || 1 })} />
                </div>
              )}
              {draft.trigger.type === "field_changed" && (
                <div className="sm:col-span-2">
                  <label className={labelCls}>Field</label>
                  <select className={inputCls} value={draft.trigger.field || ""} onChange={(e) => setTrigger({ field: e.target.value })}>
                    {fields.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                  </select>
                </div>
              )}
              {draft.trigger.type === "date_relative" && (
                ent.date_fields.length === 0 ? (
                  <div className="sm:col-span-2 text-sm text-[var(--color-danger)]">{ent.label} have no date field to count from.</div>
                ) : (
                  <>
                    <div>
                      <label className={labelCls}>Date field</label>
                      <select className={inputCls} value={draft.trigger.field || ""} onChange={(e) => setTrigger({ field: e.target.value })} data-testid="flow-trigger-date">
                        {ent.date_fields.map((k) => <option key={k} value={k}>{fields.find((f) => f.key === k)?.label || k}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className={labelCls}>Days (negative = before)</label>
                      <input type="number" className={inputCls} value={draft.trigger.offset_days ?? 0}
                             onChange={(e) => setTrigger({ offset_days: parseInt(e.target.value, 10) || 0 })} data-testid="flow-trigger-offset" />
                    </div>
                  </>
                )
              )}
              {scheduled && (
                <p className="sm:col-span-2 text-xs text-[var(--color-text-muted)]">
                  Checked every 10 minutes. Each record fires once per occasion; if the server was down, it catches up for up to 3 days.
                </p>
              )}
            </div>
          </section>

          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-sm">2. Only if <span className="font-normal text-[var(--color-text-muted)]">(optional)</span></h3>
              {draft.conditions.length > 1 && (
                <select className={fieldCls} value={draft.match} onChange={(e) => set({ match: e.target.value })} aria-label="Match">
                  <option value="all">All conditions hold</option>
                  <option value="any">Any condition holds</option>
                </select>
              )}
            </div>
            <div className="space-y-2">
              {draft.conditions.map((c, i) => {
                const op = meta.operators.find((o) => o.key === c.op);
                return (
                  <div key={i} className="flex flex-wrap gap-2 items-center" data-testid={`flow-cond-${i}`}>
                    <select className={`${fieldCls} flex-1 min-w-[8rem]`} value={c.field} onChange={(e) => setCond(i, { field: e.target.value })} aria-label="Field">
                      <option value="stage">Stage</option>
                      {fields.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                    </select>
                    <select className={fieldCls} value={c.op} onChange={(e) => setCond(i, { op: e.target.value })} aria-label="Comparison">
                      {meta.operators.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
                    </select>
                    {op?.needs_value !== false && (
                      <input className={`${fieldCls} flex-1 min-w-[6rem]`} value={c.value} onChange={(e) => setCond(i, { value: e.target.value })} aria-label="Value" />
                    )}
                    <button type="button" aria-label="Remove condition" className="p-1.5 text-[var(--color-danger)]"
                            onClick={() => set({ conditions: draft.conditions.filter((_, j) => j !== i) })}><Trash2 size={14} /></button>
                  </div>
                );
              })}
              {draft.conditions.length < meta.limits.conditions && (
                <button type="button" className="btn-ghost text-xs" data-testid="flow-add-cond"
                        onClick={() => set({ conditions: [...draft.conditions, { field: fields[0]?.key || "stage", op: "equals", value: "" }] })}>
                  <Plus size={12} /> Add condition
                </button>
              )}
            </div>
          </section>

          <section>
            <h3 className="font-semibold text-sm mb-1">3. Then, in order</h3>
            <p className="text-xs text-[var(--color-text-muted)] mb-2">Use {"{name}"}, {"{record}"}, {"{stage}"} or any field like {"{customer}"} in titles and messages.</p>
            <ol className="space-y-2">
              {draft.steps.map((s, i) => (
                <li key={i} className="rounded-[var(--radius-sm)] border border-[var(--color-border)] p-3" data-testid={`flow-step-${i}`}>
                  <div className="flex items-center gap-1 mb-2">
                    <span className="text-xs font-mono text-[var(--color-text-muted)]">{i + 1}</span>
                    <select className={`${fieldCls} flex-1 min-w-0`} value={s.type} onChange={(e) => setStep(i, blankStep(e.target.value))} aria-label={`Step ${i + 1} type`}>
                      {meta.steps.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                    </select>
                    <button type="button" aria-label="Move up" className="p-1" onClick={() => moveStep(i, -1)} disabled={i === 0}><ChevronUp size={14} /></button>
                    <button type="button" aria-label="Move down" className="p-1" onClick={() => moveStep(i, 1)} disabled={i === draft.steps.length - 1}><ChevronDown size={14} /></button>
                    <button type="button" aria-label="Remove step" className="p-1 text-[var(--color-danger)]" disabled={draft.steps.length === 1}
                            onClick={() => set({ steps: draft.steps.filter((_, j) => j !== i) })}><Trash2 size={14} /></button>
                  </div>
                  <StepFields step={s} onChange={(patch) => setStep(i, patch)} meta={meta} settable={settable} userOptions={userOptions} />
                </li>
              ))}
            </ol>
            {draft.steps.length < meta.limits.steps && (
              <button type="button" className="btn-ghost text-xs mt-2" data-testid="flow-add-step"
                      onClick={() => set({ steps: [...draft.steps, blankStep("create_task")] })}>
                <Plus size={12} /> Add step
              </button>
            )}
          </section>

          {draft.id && <DryRun flow={draft} />}
        </div>
        <div className="sticky bottom-0 flex items-center justify-between gap-2 px-5 py-3 border-t border-[var(--color-border)] bg-[var(--color-surface)]">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.active !== false} onChange={(e) => set({ active: e.target.checked })} /> Switched on
          </label>
          <div className="flex gap-2">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
            <button type="button" className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="flow-save">
              <Save size={14} /> {saving ? "Saving…" : "Save flow"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function StepFields({ step, onChange, meta, settable, userOptions }) {
  if (step.type === "create_task") {
    return (
      <div className="grid gap-2 sm:grid-cols-4">
        <input className={`${inputCls} sm:col-span-4`} value={step.title} onChange={(e) => onChange({ title: e.target.value })} aria-label="Task title" />
        <label className="text-xs">Due in (days)
          <input type="number" min="0" className={inputCls} value={step.due_in_days} onChange={(e) => onChange({ due_in_days: parseInt(e.target.value, 10) || 0 })} />
        </label>
        <label className="text-xs">Priority
          <select className={inputCls} value={step.priority} onChange={(e) => onChange({ priority: e.target.value })}>
            {meta.priorities.map((p) => <option key={p}>{p}</option>)}
          </select>
        </label>
        <label className="text-xs sm:col-span-2">Assign to
          <select className={inputCls} value={step.assign_to} onChange={(e) => onChange({ assign_to: e.target.value })}>
            <option value="owner">The record's owner</option>
            <option value="actor">Whoever made the change</option>
            {userOptions(["owner", "actor"].includes(step.assign_to) ? "" : step.assign_to)}
          </select>
        </label>
      </div>
    );
  }
  if (step.type === "alert_user") {
    return (
      <div className="grid gap-2 sm:grid-cols-3">
        <select className={inputCls} value={step.user} onChange={(e) => onChange({ user: e.target.value })} aria-label="Who to alert">{userOptions(step.user)}</select>
        <input className={`${inputCls} sm:col-span-2`} value={step.message} onChange={(e) => onChange({ message: e.target.value })} aria-label="Alert message" />
        <p className="sm:col-span-3 text-xs text-[var(--color-text-muted)]">Arrives as a high-priority task due today in their task list.</p>
      </div>
    );
  }
  if (step.type === "set_field") {
    return (
      <div className="grid gap-2 sm:grid-cols-2">
        <select className={inputCls} value={step.field} onChange={(e) => onChange({ field: e.target.value })} aria-label="Field">
          <option value="">Pick a field…</option>
          {settable.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
        </select>
        <input className={inputCls} value={step.value ?? ""} onChange={(e) => onChange({ value: e.target.value })} aria-label="New value" />
      </div>
    );
  }
  if (step.type === "assign_owner") {
    return <select className={inputCls} value={step.user} onChange={(e) => onChange({ user: e.target.value })} aria-label="New owner">{userOptions(step.user)}</select>;
  }
  if (step.type === "notify_customer") {
    return (
      <select className={inputCls} value={step.event} onChange={(e) => onChange({ event: e.target.value })} aria-label="Message template">
        {meta.message_templates.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
      </select>
    );
  }
  if (step.type === "wait") {
    return (
      <label className="text-xs flex items-center gap-2">Wait
        <input type="number" min="1" max={meta.limits.wait_days} className={`${fieldCls} w-24`} value={step.days}
               onChange={(e) => onChange({ days: parseInt(e.target.value, 10) || 1 })} /> days, then carry on with the next step
      </label>
    );
  }
  return null;
}

function DryRun({ flow }) {
  const [records, setRecords] = useState([]);
  const [recordId, setRecordId] = useState("");
  const [result, setResult] = useState(null);
  useEffect(() => {
    const path = LIST_PATH[flow.entity];
    if (!path) return;
    api.get(path).then(({ data }) => setRecords((Array.isArray(data) ? data : data?.items || []).slice(0, 200)))
      .catch(() => setRecords([]));
  }, [flow.entity]);
  const test = async () => {
    if (!recordId) return;
    try {
      const { data } = await api.post(`/flows/${flow.id}/test`, { record_id: recordId });
      setResult(data);
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Couldn't test it"); }
  };
  return (
    <section className="rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] p-3" data-testid="flow-dry-run">
      <h3 className="font-semibold text-sm mb-2 flex items-center gap-1.5"><FlaskConical size={14} /> Test on a record (saved version, nothing is changed)</h3>
      <div className="flex gap-2">
        <select className={`${fieldCls} flex-1`} value={recordId} onChange={(e) => { setRecordId(e.target.value); setResult(null); }} aria-label="Record to test">
          <option value="">Pick a record…</option>
          {records.map((r) => <option key={r.id} value={r.id}>{recordLabel(r)}</option>)}
        </select>
        <button type="button" className="btn-ghost" onClick={test} disabled={!recordId} data-testid="flow-dry-run-go">Test</button>
      </div>
      {result && (
        <div className="mt-3 text-sm space-y-1">
          <div className={`flex items-center gap-1.5 font-medium ${result.conditions_met ? "text-[var(--color-success,#15803d)]" : "text-[var(--color-danger)]"}`}>
            {result.conditions_met ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
            {result.conditions_met ? "Conditions hold for this record" : "Conditions don't hold for this record"}
          </div>
          {result.checks.map((c, i) => (
            <div key={i} className="text-xs text-[var(--color-text-muted)]">{c.passed ? "✓" : "✗"} {c.field} {c.op} {c.value} (is {String(c.actual ?? "empty")})</div>
          ))}
          {result.scheduled_key !== null && result.scheduled_key !== undefined && (
            <div className="text-xs">{result.scheduled_key ? "Due today on the schedule." : "Not due on the schedule today."}</div>
          )}
          <div className="text-xs text-[var(--color-text-muted)]">Steps: {result.steps.join(" → ")}</div>
        </div>
      )}
    </section>
  );
}

function RunLog({ flows }) {
  const [runs, setRuns] = useState(null);
  const [flowId, setFlowId] = useState("");
  const [open, setOpen] = useState("");
  useEffect(() => {
    const q = flowId ? `?flow_id=${encodeURIComponent(flowId)}&limit=200` : "?limit=200";
    api.get(`/flow-runs${q}`, { skipCache: true }).then(({ data }) => setRuns(data)).catch(() => setRuns([]));
  }, [flowId]);
  return (
    <div className="space-y-3" data-testid="flow-runs">
      <select className={fieldCls} value={flowId} onChange={(e) => setFlowId(e.target.value)} aria-label="Filter by flow">
        <option value="">All flows</option>
        {flows.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
      </select>
      {runs === null ? <div className="text-sm text-[var(--color-text-muted)]">Loading…</div> : runs.length === 0 ? (
        <div className="text-sm text-[var(--color-text-muted)]">No runs yet. They appear here as soon as a flow fires.</div>
      ) : (
        <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)]">
          <table className="w-full text-sm">
            <thead className="bg-[var(--color-surface-muted)] text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
              <tr><th className="text-left px-3 py-2">When</th><th className="text-left px-3 py-2">Flow</th><th className="text-left px-3 py-2">Record</th><th className="text-left px-3 py-2">Status</th></tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <FragmentRow key={r.id} r={r} open={open === r.id} onToggle={() => setOpen(open === r.id ? "" : r.id)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FragmentRow({ r, open, onToggle }) {
  return (
    <>
      <tr className="border-t border-[var(--color-border)] cursor-pointer hover:bg-[var(--color-surface-muted)]" onClick={onToggle} data-testid={`flow-run-${r.id}`}>
        <td className="px-3 py-2 whitespace-nowrap">{fmtDateTime(r.started_at)}</td>
        <td className="px-3 py-2">{r.flow_name}<div className="text-xs text-[var(--color-text-muted)]">{r.reason}</div></td>
        <td className="px-3 py-2">{r.record_title || r.record_id}</td>
        <td className={`px-3 py-2 font-medium capitalize ${STATUS_TONE[r.status] || ""}`}>
          {r.status}{r.status === "waiting" && r.resume_at ? ` until ${r.resume_at}` : ""}
        </td>
      </tr>
      {open && (
        <tr><td colSpan={4} className="px-3 pb-3">
          <ol className="text-xs space-y-1 bg-[var(--color-surface-muted)] rounded p-2">
            {(r.log || []).map((l, i) => (
              <li key={i} className={l.ok ? "" : "text-[var(--color-danger)]"}>{l.ok ? "✓" : "✗"} {l.step}: {l.result}</li>
            ))}
            {r.cancel_reason && <li>Cancelled: {r.cancel_reason}</li>}
          </ol>
        </td></tr>
      )}
    </>
  );
}
