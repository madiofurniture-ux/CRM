import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { inrFull, fmtDate, todayIST } from "@/lib/format";
import { toast } from "sonner";
import { CheckCircle2, Circle, ClipboardList, IndianRupee, LifeBuoy, ListChecks, Plus, Trash2, Ruler } from "lucide-react";
import AttachmentPanel from "@/components/AttachmentPanel";
import StaffPicker from "@/components/StaffPicker";

const err = (e, fallback) => e?.response?.data?.detail
  ? (typeof e.response.data.detail === "string" ? e.response.data.detail : fallback)
  : fallback;

const PAY_TONE = {
  PAID: "bg-emerald-50 text-emerald-700", PARTIAL: "bg-amber-50 text-amber-700",
  UNPAID: "bg-[var(--surface-2)] text-[var(--ink-2)]", OVERDUE: "bg-red-50 text-red-700",
};
const TICKET_TONE = {
  OPEN: "bg-red-50 text-red-700", ASSIGNED: "bg-amber-50 text-amber-700",
  "VISIT SCHEDULED": "bg-blue-50 text-blue-700", "IN PROGRESS": "bg-blue-50 text-blue-700",
  WAITING: "bg-[var(--surface-2)] text-[var(--ink-2)]", RESOLVED: "bg-emerald-50 text-emerald-700",
  CLOSED: "bg-emerald-50 text-emerald-700",
};

/**
 * Project operations: the division-specific stage checklist, costing and
 * payment status, site surveys and service tickets for ONE project, all
 * from GET /projects/{id}/summary. Built for a phone: large tap targets,
 * one tab at a time.
 */
export default function ProjectOpsPanel({ project, onProjectUpdated }) {
  const [tab, setTab] = useState("stages");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setFailed(false);
    try {
      const { data } = await api.get(`/projects/${project.id}/summary`, { skipCache: true });
      setData(data);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [project.id]);

  useEffect(() => { setLoading(true); load(); }, [load]);

  const tabs = [
    { id: "stages", label: "Stages", icon: ListChecks },
    { id: "money", label: "Money", icon: IndianRupee },
    { id: "survey", label: "Survey", icon: Ruler },
    { id: "service", label: "Service", icon: LifeBuoy },
  ];

  return (
    <div className="border border-[var(--border)] rounded-2xl overflow-hidden bg-white" data-testid="project-ops-panel">
      <div className="grid grid-cols-4 border-b border-[var(--border)] bg-[var(--surface-2)]">
        {tabs.map((t) => {
          const Icon = t.icon;
          const count = t.id === "service" ? (data?.service_tickets || []).filter((x) => !["RESOLVED", "CLOSED"].includes(x.status)).length : 0;
          return (
            <button key={t.id} type="button" onClick={() => setTab(t.id)}
              className={`flex flex-col sm:flex-row items-center justify-center gap-1 py-2.5 text-xs font-semibold transition ${
                tab === t.id ? "bg-white text-[var(--brand)] border-b-2 border-[var(--brand)]" : "text-[var(--ink-2)]"}`}
              data-testid={`ops-tab-${t.id}`}>
              <Icon size={15} />
              <span>{t.label}{count ? ` (${count})` : ""}</span>
            </button>
          );
        })}
      </div>
      <div className="p-4">
        {loading && <div className="text-sm text-[var(--ink-3)] py-6 text-center">Loading…</div>}
        {!loading && failed && (
          <div className="text-sm text-center py-6">
            <div className="text-[var(--danger)] mb-2">Couldn't load project details.</div>
            <button className="btn-ghost" onClick={() => { setLoading(true); load(); }}>Retry</button>
          </div>
        )}
        {!loading && !failed && data && (
          <>
            {tab === "stages" && <StagesTab project={project} data={data} reload={load} onProjectUpdated={onProjectUpdated} />}
            {tab === "money" && <MoneyTab project={project} data={data} reload={load} />}
            {tab === "survey" && <SurveyTab project={project} data={data} reload={load} />}
            {tab === "service" && <ServiceTab project={project} data={data} reload={load} />}
          </>
        )}
      </div>
    </div>
  );
}

function StagesTab({ project, data, reload, onProjectUpdated }) {
  const wf = data.workflow;
  const [busy, setBusy] = useState("");
  const toggle = async (m) => {
    if (busy) return;
    const done = m.status !== "Done";
    if (!done && !window.confirm(`Re-open "${m.name}"?`)) return;
    setBusy(m.name);
    try {
      const { data: out } = await api.post(`/projects/${project.id}/milestones`, { name: m.name, done });
      toast.success(`${m.name} ${done ? "completed" : "re-opened"}`);
      onProjectUpdated?.({ ...project, milestones: out.milestones,
        completion_percentage: out.progress.percent, current_milestone: out.progress.current });
      reload();
    } catch (e) {
      toast.error(err(e, "Could not update stage"));
    } finally {
      setBusy("");
    }
  };
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">{wf.division} workflow</div>
          <div className="text-sm font-semibold text-[var(--ink)]">
            {wf.progress.completed ? "Completed" : `Next: ${wf.progress.current || "—"}`}
          </div>
        </div>
        <div className="text-right">
          <div className="font-heading font-bold text-xl text-[var(--ink)]">{wf.progress.percent}%</div>
          <div className="text-[11px] text-[var(--ink-3)]">{wf.progress.done}/{wf.progress.total} stages</div>
        </div>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--surface-2)] mb-4 overflow-hidden">
        <div className="h-full bg-[var(--moss)] transition-all" style={{ width: `${wf.progress.percent}%` }} />
      </div>
      <ol className="space-y-1.5">
        {wf.milestones.map((m, i) => {
          const done = m.status === "Done";
          const current = !done && m.name === wf.progress.current;
          return (
            <li key={m.name}>
              <button type="button" onClick={() => toggle(m)} disabled={!!busy}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border text-left transition min-h-[44px] ${
                  done ? "bg-emerald-50/60 border-emerald-100" : current ? "bg-[var(--brand-soft)] border-[var(--brand)]" : "bg-white border-[var(--border)]"
                } ${m.legacy ? "opacity-60" : ""}`}
                data-testid={`milestone-${m.name}`}>
                {done ? <CheckCircle2 size={18} className="text-[var(--moss)] shrink-0" /> : <Circle size={18} className="text-[var(--ink-3)] shrink-0" />}
                <span className="text-[11px] font-mono text-[var(--ink-3)] w-5">{i + 1}</span>
                <span className={`flex-1 text-sm ${done ? "text-[var(--ink)]" : "text-[var(--ink-2)]"} ${current ? "font-semibold text-[var(--ink)]" : ""}`}>
                  {m.name}{m.legacy ? " (earlier)" : ""}
                </span>
                {done && (
                  <span className="text-[10px] text-[var(--ink-3)] text-right leading-tight">
                    {fmtDate(m.completed_at)}<br />{m.completed_by}
                  </span>
                )}
                {busy === m.name && <span className="text-[10px] text-[var(--ink-3)]">Saving…</span>}
              </button>
            </li>
          );
        })}
      </ol>
      {data.timeline?.length > 0 && (
        <div className="mt-5">
          <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-2">Activity</div>
          <ul className="space-y-1.5 max-h-56 overflow-y-auto">
            {[...data.timeline].sort((a, b) => String(b.at).localeCompare(String(a.at))).slice(0, 40).map((a, i) => (
              <li key={i} className="text-xs border-l-2 border-[var(--border)] pl-2">
                <div className="text-[var(--ink)]">{a.note || `${a.action}`}</div>
                <div className="text-[10px] text-[var(--ink-3)]">{fmtDate(a.at)} · {a.by_user || "—"}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function MoneyTab({ project, data, reload }) {
  const c = data.costing;
  const [editing, setEditing] = useState(false);
  const [est, setEst] = useState(c.estimated);
  const [act, setAct] = useState(c.actual);
  const [due, setDue] = useState(c.next_payment_due || "");
  const [saving, setSaving] = useState(false);
  useEffect(() => { setEst(c.estimated); setAct(c.actual); setDue(c.next_payment_due || ""); }, [c]);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/projects/${project.id}/costing`, { estimated: est, actual: act, next_payment_due: due });
      toast.success("Costing saved");
      setEditing(false);
      reload();
    } catch (e) {
      toast.error(err(e, "Could not save costing"));
    } finally {
      setSaving(false);
    }
  };

  const Stat = ({ label, value, tone }) => (
    <div className="bg-[var(--surface-2)] rounded-xl p-3">
      <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">{label}</div>
      <div className={`font-mono font-bold text-sm mt-0.5 ${tone || "text-[var(--ink)]"}`}>{value}</div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">Payments</div>
        <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${PAY_TONE[c.payment_status] || ""}`} data-testid="payment-status">
          {c.payment_status}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Stat label="Order value" value={inrFull(c.order_value)} />
        <Stat label="Received" value={inrFull(c.amount_received)} tone="text-[var(--moss)]" />
        <Stat label="Pending" value={inrFull(c.amount_pending)} tone={c.amount_pending > 0 ? "text-[var(--danger)]" : ""} />
        <Stat label="Next due" value={c.next_payment_due ? fmtDate(c.next_payment_due) : "—"} />
      </div>
      {data.payments?.length > 0 && (
        <div className="text-xs space-y-1">
          {data.payments.slice(0, 8).map((p) => (
            <div key={p.id} className="flex items-center justify-between border-b border-[var(--border-light)] py-1">
              <span>{fmtDate(p.date)} · {p.mode}{p.kind ? ` · ${p.kind}` : ""}</span>
              <span className="font-mono font-semibold">{p.direction === "Refund" ? "−" : ""}{inrFull(p.amount)}</span>
            </div>
          ))}
        </div>
      )}
      <Link to="/payments" className="inline-flex text-xs font-medium text-[var(--brand)] hover:underline">Record a payment →</Link>

      <div className="pt-2 border-t border-[var(--border-light)]">
        <div className="flex items-center justify-between mb-2">
          <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">
            Profitability <span className="normal-case font-normal">({c.basis} cost)</span>
          </div>
          {!editing && <button className="text-xs font-semibold text-[var(--brand)]" onClick={() => setEditing(true)} data-testid="edit-costing">Edit costs</button>}
        </div>
        <div className="grid grid-cols-3 gap-2 mb-3">
          <Stat label="Revenue" value={inrFull(c.revenue)} />
          <Stat label="Gross profit" value={inrFull(c.gross_profit)} tone={c.gross_profit < 0 ? "text-[var(--danger)]" : "text-[var(--moss)]"} />
          <Stat label="Margin" value={`${c.margin_pct}%`} tone={c.margin_pct < 0 ? "text-[var(--danger)]" : ""} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">
                <th className="text-left py-1">Category</th><th className="text-right py-1">Estimated</th><th className="text-right py-1">Actual</th>
              </tr>
            </thead>
            <tbody>
              {c.categories.map((cat) => (
                <tr key={cat} className="border-t border-[var(--border-light)]">
                  <td className="py-1.5">{cat}</td>
                  <td className="text-right">
                    {editing
                      ? <input type="number" min="0" inputMode="decimal" value={est[cat] ?? 0} onChange={(e) => setEst({ ...est, [cat]: e.target.value })}
                          className="w-24 px-2 py-1 border border-[var(--border)] rounded text-right font-mono" data-testid={`est-${cat}`} />
                      : <span className="font-mono">{inrFull(c.estimated[cat])}</span>}
                  </td>
                  <td className="text-right">
                    {editing
                      ? <input type="number" min="0" inputMode="decimal" value={act[cat] ?? 0} onChange={(e) => setAct({ ...act, [cat]: e.target.value })}
                          className="w-24 px-2 py-1 border border-[var(--border)] rounded text-right font-mono" data-testid={`act-${cat}`} />
                      : <span className="font-mono">{inrFull(c.actual[cat])}</span>}
                  </td>
                </tr>
              ))}
              <tr className="border-t border-[var(--border)] font-semibold">
                <td className="py-1.5">Total</td>
                <td className="text-right font-mono">{inrFull(c.estimated_total)}</td>
                <td className="text-right font-mono">{inrFull(c.actual_total)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        {editing && (
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="text-xs">
              <span className="block text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-1">Next payment due</span>
              <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className="px-2 py-1.5 border border-[var(--border)] rounded" />
            </label>
            <div className="flex-1" />
            <button className="btn-ghost" onClick={() => setEditing(false)}>Cancel</button>
            <button className="btn-primary" onClick={save} disabled={saving} data-testid="save-costing">{saving ? "Saving…" : "Save"}</button>
          </div>
        )}
      </div>
    </div>
  );
}

const FURNITURE_ROW = { room: "", length: "", width: "", height: "", requirement: "", existing_conditions: "", notes: "" };
const MAP_ROW = { area_name: "", length: "", height: "", area: "", surface_condition: "", moisture: "", existing_finish: "",
  proposed_finish: "", sample: "", shade: "", coverage: "", applicator: "", notes: "" };

function SurveyTab({ project, data, reload }) {
  const division = data.workflow.division;
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [openSurvey, setOpenSurvey] = useState(null);

  if (division === "D&W") {
    return (
      <div className="space-y-3">
        <p className="text-sm text-[var(--ink-2)]">
          Doors &amp; Windows projects use the D&amp;W survey — openings, sizes, profile/series, glass, hardware, mesh and finish, with client sign-off and BOQ.
        </p>
        {(data.dw_surveys || []).map((s) => (
          <div key={s.id} className="flex items-center justify-between text-sm border border-[var(--border)] rounded-xl px-3 py-2">
            <span className="font-mono">{s.survey_id || s.id.slice(0, 8)}</span>
            <span className="text-xs">{s.status || "—"} · {s.client_sign_off ? "Signed off" : "Not signed"}</span>
          </div>
        ))}
        <Link to={`/dw-survey?project_id=${project.id}`} className="btn-primary inline-flex" data-testid="open-dw-survey">
          <ClipboardList size={14} /> Open D&amp;W Survey
        </Link>
      </div>
    );
  }

  const blank = division === "MAP" ? MAP_ROW : FURNITURE_ROW;
  const startNew = () => setForm({ survey_date: todayIST(), surveyor: "", site_address: project.site_address || "",
    notes: "", customer_signed: false, signed_by: "", rows: [{ ...blank }] });
  const setRow = (i, k, v) => setForm((f) => ({ ...f, rows: f.rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)) }));

  const save = async () => {
    setSaving(true);
    try {
      if (form.id) await api.put(`/site-surveys/${form.id}`, form);
      else await api.post("/site-surveys", { ...form, project_id: project.id });
      toast.success("Survey saved");
      setForm(null);
      reload();
    } catch (e) {
      toast.error(err(e, "Could not save survey"));
    } finally {
      setSaving(false);
    }
  };

  if (form) {
    const fields = division === "MAP"
      ? [["area_name", "Wall / area", "text"], ["length", "Length (ft)", "number"], ["height", "Height (ft)", "number"],
         ["area", "Area (sq ft, auto)", "number"], ["surface_condition", "Surface condition", "text"], ["moisture", "Moisture", "text"],
         ["existing_finish", "Existing finish", "text"], ["proposed_finish", "Proposed finish", "text"], ["sample", "Sample", "text"],
         ["shade", "Shade", "text"], ["coverage", "Coverage (sq ft/L)", "number"], ["applicator", "Applicator", "text"], ["notes", "Notes", "text"]]
      : [["room", "Room", "text"], ["length", "Length (ft)", "number"], ["width", "Width (ft)", "number"], ["height", "Height (ft)", "number"],
         ["requirement", "Furniture requirement", "text"], ["existing_conditions", "Existing conditions", "text"], ["notes", "Notes", "text"]];
    return (
      <div className="space-y-3" data-testid="site-survey-form">
        <div className="grid grid-cols-2 gap-2">
          <Input label="Survey date" type="date" value={form.survey_date} onChange={(v) => setForm({ ...form, survey_date: v })} />
          <Input label="Surveyor" value={form.surveyor} onChange={(v) => setForm({ ...form, surveyor: v })} placeholder="Defaults to you" />
          <Input label="Site address" value={form.site_address} onChange={(v) => setForm({ ...form, site_address: v })} cls="col-span-2" />
        </div>
        {form.rows.map((r, i) => (
          <div key={i} className="border border-[var(--border)] rounded-xl p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-[var(--ink-2)]">{division === "MAP" ? "Wall / area" : "Room"} {i + 1}</span>
              <button type="button" onClick={() => setForm((f) => ({ ...f, rows: f.rows.filter((_, j) => j !== i) }))}
                className="p-1 text-[var(--danger)]" aria-label="Remove row"><Trash2 size={13} /></button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {fields.map(([k, label, type]) => (
                <Input key={k} label={label} type={type} value={r[k] ?? ""} onChange={(v) => setRow(i, k, v)}
                  placeholder={k === "area" && r.length && r.height ? String(Math.round(r.length * r.height * 100) / 100) : ""} />
              ))}
            </div>
          </div>
        ))}
        <button type="button" className="btn-ghost" onClick={() => setForm((f) => ({ ...f, rows: [...f.rows, { ...blank }] }))}>
          <Plus size={14} /> Add {division === "MAP" ? "wall / area" : "room"}
        </button>
        <Input label="Notes" value={form.notes} onChange={(v) => setForm({ ...form, notes: v })} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={!!form.customer_signed} onChange={(e) => setForm({ ...form, customer_signed: e.target.checked })} />
          Customer confirmed measurements
        </label>
        {form.customer_signed && <Input label="Confirmed by (name)" value={form.signed_by} onChange={(v) => setForm({ ...form, signed_by: v })} />}
        <div className="flex justify-end gap-2">
          <button className="btn-ghost" onClick={() => setForm(null)}>Cancel</button>
          <button className="btn-primary" onClick={save} disabled={saving} data-testid="save-site-survey">{saving ? "Saving…" : "Save survey"}</button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {(data.site_surveys || []).length === 0 && (
        <p className="text-sm text-[var(--ink-3)]">No {division === "MAP" ? "inspection" : "site survey"} recorded yet.</p>
      )}
      {(data.site_surveys || []).map((s) => (
        <div key={s.id} className="border border-[var(--border)] rounded-xl">
          <button type="button" className="w-full flex items-center justify-between px-3 py-2 text-sm" onClick={() => setOpenSurvey(openSurvey === s.id ? null : s.id)}>
            <span className="font-mono font-semibold">{s.survey_no}</span>
            <span className="text-xs text-[var(--ink-2)]">
              {fmtDate(s.survey_date)} · {s.surveyor} · {division === "MAP" ? `${s.totals?.total_area || 0} sq ft` : `${s.totals?.rooms || 0} rooms`}
            </span>
          </button>
          {openSurvey === s.id && (
            <div className="px-3 pb-3 space-y-2">
              {(s.rows || []).map((r, i) => (
                <div key={i} className="text-xs bg-[var(--surface-2)] rounded-lg p-2">
                  {division === "MAP"
                    ? <><b>{r.area_name}</b> — {r.length}×{r.height} ft = {r.area} sq ft · {r.surface_condition || "—"} · moisture {r.moisture || "—"} · {r.existing_finish || "—"} → {r.proposed_finish || "—"} {r.shade ? `· shade ${r.shade}` : ""}</>
                    : <><b>{r.room}</b> — {r.length}×{r.width}×{r.height} ft · {r.requirement || "—"} {r.existing_conditions ? `· ${r.existing_conditions}` : ""}</>}
                  {r.notes && <div className="text-[var(--ink-3)]">{r.notes}</div>}
                </div>
              ))}
              {s.notes && <div className="text-xs text-[var(--ink-2)]">{s.notes}</div>}
              <div className="text-[11px] text-[var(--ink-3)]">{s.customer_signed ? `Confirmed by ${s.signed_by || "customer"}` : "Not confirmed by customer"}</div>
              <button className="text-xs font-semibold text-[var(--brand)]" onClick={() => setForm({ ...s })}>Edit survey</button>
              <AttachmentPanel entity="site_survey" itemId={s.id} defaultCategory="Measurement" />
            </div>
          )}
        </div>
      ))}
      <button className="btn-primary" onClick={startNew} data-testid="new-site-survey">
        <Plus size={14} /> {division === "MAP" ? "New inspection" : "New site survey"}
      </button>
    </div>
  );
}

function ServiceTab({ project, data, reload }) {
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ complaint: "", priority: "Medium", assigned_to: "", visit_date: "" });
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (!form.complaint.trim()) { toast.error("Describe the complaint"); return; }
    setSaving(true);
    try {
      await api.post("/service-tickets", { ...form, project_id: project.id,
        status: form.visit_date ? "VISIT SCHEDULED" : form.assigned_to ? "ASSIGNED" : "OPEN" });
      toast.success("Service ticket raised");
      setShow(false);
      setForm({ complaint: "", priority: "Medium", assigned_to: "", visit_date: "" });
      reload();
    } catch (e) {
      toast.error(err(e, "Could not raise ticket"));
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="space-y-3">
      <div className="text-xs text-[var(--ink-2)]">
        Warranty: <b className={data.warranty_active ? "text-[var(--moss)]" : ""}>{data.warranty_active ? "Active" : "Not active / not completed"}</b>
      </div>
      {(data.service_tickets || []).length === 0 && <p className="text-sm text-[var(--ink-3)]">No service history.</p>}
      {(data.service_tickets || []).map((t) => (
        <Link key={t.id} to={`/service?ticket=${t.id}`} className="block border border-[var(--border)] rounded-xl px-3 py-2 hover:bg-[var(--surface-2)]">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-semibold">{t.ticket_no}</span>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${TICKET_TONE[t.status] || ""}`}>{t.status}</span>
          </div>
          <div className="text-sm mt-1">{t.complaint}</div>
          <div className="text-[11px] text-[var(--ink-3)] mt-0.5">{fmtDate(t.created_at)} · {t.priority} · {t.assigned_to || "Unassigned"}</div>
        </Link>
      ))}
      {show ? (
        <div className="border border-[var(--border)] rounded-xl p-3 space-y-2">
          <Input label="Complaint *" value={form.complaint} onChange={(v) => setForm({ ...form, complaint: v })} />
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs">
              <span className="block text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-1">Priority</span>
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}
                className="w-full px-2 py-2 border border-[var(--border)] rounded-lg bg-white text-sm">
                {["Low", "Medium", "High", "Urgent"].map((p) => <option key={p}>{p}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="block text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-1">Assign to</span>
              <StaffPicker value={form.assigned_to} onChange={(name) => setForm((f) => ({ ...f, assigned_to: name }))} />
            </label>
            <Input label="Visit date" type="date" value={form.visit_date} onChange={(v) => setForm({ ...form, visit_date: v })} />
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
            <button className="btn-primary" onClick={save} disabled={saving} data-testid="save-service-ticket">{saving ? "Saving…" : "Raise ticket"}</button>
          </div>
        </div>
      ) : (
        <button className="btn-primary" onClick={() => setShow(true)} data-testid="new-service-ticket"><Plus size={14} /> Raise service request</button>
      )}
    </div>
  );
}

function Input({ label, value, onChange, type = "text", placeholder = "", cls = "" }) {
  return (
    <label className={`text-xs block ${cls}`}>
      <span className="block text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-1">{label}</span>
      <input type={type} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)}
        inputMode={type === "number" ? "decimal" : undefined} min={type === "number" ? "0" : undefined}
        className="w-full px-2 py-2 border border-[var(--border)] rounded-lg bg-white text-sm outline-none focus:border-[var(--brand)]" />
    </label>
  );
}
