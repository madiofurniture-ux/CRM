import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Topbar from "@/components/Topbar";
import EmptyState from "@/components/EmptyState";
import AttachmentPanel from "@/components/AttachmentPanel";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { LifeBuoy, Phone, MessageCircle, X, ShieldCheck } from "lucide-react";

const STATUSES = ["OPEN", "ASSIGNED", "VISIT SCHEDULED", "IN PROGRESS", "WAITING", "RESOLVED", "CLOSED"];
const OPEN = new Set(STATUSES.slice(0, 5));
const PRIORITIES = ["Low", "Medium", "High", "Urgent"];
const TYPES = ["Warranty", "Paid Service", "Complaint", "Installation Snag", "Other"];
const TONE = {
  OPEN: "bg-red-50 text-red-700", ASSIGNED: "bg-amber-50 text-amber-700",
  "VISIT SCHEDULED": "bg-blue-50 text-blue-700", "IN PROGRESS": "bg-blue-50 text-blue-700",
  WAITING: "bg-[var(--surface-2)] text-[var(--ink-2)]", RESOLVED: "bg-emerald-50 text-emerald-700",
  CLOSED: "bg-emerald-50 text-emerald-700",
};
const PRI_TONE = { Urgent: "text-red-700", High: "text-amber-700", Medium: "text-[var(--ink-2)]", Low: "text-[var(--ink-3)]" };

const detail = (e, fallback) => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : fallback;
};
const wa = (phone) => `https://wa.me/91${String(phone || "").replace(/\D/g, "").slice(-10)}`;

export default function Service() {
  const [rows, setRows] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState("open");
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [params, setParams] = useSearchParams();
  const selected = rows.find((r) => r.id === params.get("ticket")) || null;

  const load = async () => {
    setFailed(false);
    try {
      const { data } = await api.get("/service-tickets", { skipCache: true });
      setRows(data);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
    api.get("/projects").then(({ data }) => setProjects(data)).catch(() => setProjects([]));
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) =>
      (filter === "all" || (filter === "open" ? OPEN.has(r.status) : r.status === filter)) &&
      (!q || [r.ticket_no, r.customer, r.phone, r.project_no, r.complaint, r.assigned_to].some((v) => String(v || "").toLowerCase().includes(q))));
  }, [rows, filter, search]);

  const counts = useMemo(() => {
    const c = { open: 0 };
    for (const r of rows) { c[r.status] = (c[r.status] || 0) + 1; if (OPEN.has(r.status)) c.open += 1; }
    return c;
  }, [rows]);

  const openTicket = (id) => { params.set("ticket", id); setParams(params, { replace: true }); };
  const closeTicket = () => { params.delete("ticket"); setParams(params, { replace: true }); };

  return (
    <>
      <Topbar title="Service & Warranty" subtitle={`${counts.open} open · ${rows.length} total`}
        onAdd={() => setCreating(true)} addLabel="New Ticket" />
      <div className="p-3 sm:p-6" data-testid="service-page">
        <div className="flex gap-2 overflow-x-auto pb-2 mb-3">
          {[["open", `Open (${counts.open})`], ...STATUSES.slice(5).map((s) => [s, `${s} (${counts[s] || 0})`]), ["all", "All"]].map(([k, label]) => (
            <button key={k} onClick={() => setFilter(k)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold border whitespace-nowrap ${filter === k ? "bg-[var(--ink)] text-white border-[var(--ink)]" : "bg-white border-[var(--border)] text-[var(--ink-2)]"}`}>
              {label}
            </button>
          ))}
        </div>
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search ticket, customer, phone, project…"
          className="w-full sm:w-96 mb-4 px-3 py-2 rounded-xl bg-white border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)]" />

        {loading && <div className="text-sm text-[var(--ink-3)] py-10 text-center">Loading…</div>}
        {!loading && failed && (
          <div className="text-center py-10">
            <div className="text-sm text-[var(--danger)] mb-2">Couldn't load service tickets.</div>
            <button className="btn-ghost" onClick={() => { setLoading(true); load(); }}>Retry</button>
          </div>
        )}
        {!loading && !failed && filtered.length === 0 && (
          <EmptyState icon={LifeBuoy} title="No service tickets here"
            hint="Raise a ticket from a completed project, or with New Ticket above." />
        )}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {filtered.map((t) => (
            <button key={t.id} type="button" onClick={() => openTicket(t.id)}
              className="text-left bg-white border border-[var(--border)] rounded-2xl p-4 hover:shadow-md transition" data-testid={`ticket-${t.id}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs font-semibold">{t.ticket_no}</span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${TONE[t.status] || ""}`}>{t.status}</span>
              </div>
              <div className="font-semibold text-[var(--ink)] mt-1.5">{t.customer}</div>
              <div className="text-sm text-[var(--ink-2)] mt-0.5 line-clamp-2">{t.complaint}</div>
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[var(--ink-3)] mt-2">
                <span className={`font-semibold ${PRI_TONE[t.priority] || ""}`}>{t.priority}</span>
                <span>{t.division}</span>
                <span>{t.project_no}</span>
                <span>{t.assigned_to || "Unassigned"}</span>
                {t.visit_date && <span>Visit {fmtDate(t.visit_date)}</span>}
                {t.under_warranty && <span className="text-[var(--moss)] font-semibold inline-flex items-center gap-0.5"><ShieldCheck size={11} /> Warranty</span>}
              </div>
            </button>
          ))}
        </div>
      </div>

      {creating && <NewTicket projects={projects} onClose={() => setCreating(false)}
        onSaved={(t) => { setCreating(false); setRows((p) => [t, ...p]); openTicket(t.id); }} />}
      {selected && <TicketDetail ticket={selected} onClose={closeTicket}
        onSaved={(t) => setRows((p) => p.map((x) => (x.id === t.id ? t : x)))} />}
    </>
  );
}

function Sheet({ title, onClose, children, testid }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center sm:p-4" onClick={onClose}>
      <div className="bg-white rounded-t-2xl sm:rounded-2xl w-full max-w-xl max-h-[95vh] overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()} data-testid={testid}>
        <div className="sticky top-0 bg-white flex items-center justify-between px-4 py-3 border-b z-10">
          <h3 className="font-heading font-semibold">{title}</h3>
          <button onClick={onClose} className="p-1.5 rounded-md hover:bg-[var(--surface-2)]" aria-label="Close"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-3">{children}</div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block text-xs">
      <span className="block text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-1">{label}</span>
      {children}
    </label>
  );
}
const inputCls = "w-full px-3 py-2 border border-[var(--border)] rounded-lg bg-white text-sm outline-none focus:border-[var(--brand)]";

function NewTicket({ projects, onClose, onSaved }) {
  const [q, setQ] = useState("");
  const [form, setForm] = useState({ project_id: "", complaint: "", priority: "Medium", ticket_type: "", assigned_to: "", visit_date: "" });
  const [saving, setSaving] = useState(false);
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase();
    const list = s ? projects.filter((p) => [p.project_no, p.customer, p.phone, p.project_name].some((v) => String(v || "").toLowerCase().includes(s))) : projects;
    return list.slice(0, 30);
  }, [projects, q]);
  const picked = projects.find((p) => p.id === form.project_id);
  const save = async () => {
    if (!form.project_id) { toast.error("Pick the project this complaint is about"); return; }
    if (!form.complaint.trim()) { toast.error("Describe the complaint"); return; }
    setSaving(true);
    try {
      const status = form.visit_date ? "VISIT SCHEDULED" : form.assigned_to ? "ASSIGNED" : "OPEN";
      const { data } = await api.post("/service-tickets", { ...form, status });
      toast.success(`Ticket ${data.ticket_no} raised`);
      onSaved(data);
    } catch (e) {
      toast.error(detail(e, "Could not raise ticket"));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Sheet title="New service ticket" onClose={onClose} testid="new-ticket">
      {!picked ? (
        <Field label="Project *">
          <input className={inputCls} placeholder="Search customer, phone or project no…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
          <div className="mt-2 max-h-56 overflow-y-auto border border-[var(--border)] rounded-lg divide-y">
            {matches.map((p) => (
              <button key={p.id} type="button" onClick={() => setForm({ ...form, project_id: p.id })}
                className="w-full text-left px-3 py-2 hover:bg-[var(--surface-2)] text-sm">
                <b>{p.customer}</b> · <span className="font-mono text-xs">{p.project_no}</span>
                <div className="text-[11px] text-[var(--ink-3)]">{p.division} · {p.phone || "no phone"} · {p.site_address || "—"}</div>
              </button>
            ))}
            {matches.length === 0 && <div className="px-3 py-3 text-xs text-[var(--ink-3)]">No matching project.</div>}
          </div>
        </Field>
      ) : (
        <div className="flex items-center justify-between bg-[var(--surface-2)] rounded-lg px-3 py-2 text-sm">
          <span><b>{picked.customer}</b> · <span className="font-mono text-xs">{picked.project_no}</span> · {picked.division}</span>
          <button className="text-xs font-semibold text-[var(--brand)]" onClick={() => setForm({ ...form, project_id: "" })}>Change</button>
        </div>
      )}
      <Field label="Complaint *">
        <textarea rows={3} className={inputCls} value={form.complaint} onChange={(e) => setForm({ ...form, complaint: e.target.value })} />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Priority">
          <select className={inputCls} value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
            {PRIORITIES.map((p) => <option key={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Type">
          <select className={inputCls} value={form.ticket_type} onChange={(e) => setForm({ ...form, ticket_type: e.target.value })}>
            <option value="">Auto (warranty if in warranty)</option>
            {TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </Field>
        <Field label="Assign to">
          <input className={inputCls} value={form.assigned_to} onChange={(e) => setForm({ ...form, assigned_to: e.target.value })} />
        </Field>
        <Field label="Visit date">
          <input type="date" className={inputCls} value={form.visit_date} onChange={(e) => setForm({ ...form, visit_date: e.target.value })} />
        </Field>
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <button className="btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={save} disabled={saving} data-testid="ticket-save">{saving ? "Saving…" : "Raise ticket"}</button>
      </div>
    </Sheet>
  );
}

function TicketDetail({ ticket, onClose, onSaved }) {
  const [form, setForm] = useState(ticket);
  const [saving, setSaving] = useState(false);
  useEffect(() => setForm(ticket), [ticket]);
  const save = async (patch = {}) => {
    setSaving(true);
    try {
      const body = { ...["status", "priority", "ticket_type", "assigned_to", "visit_date", "resolution", "parts_used", "notes", "customer_signed", "signed_by"]
        .reduce((o, k) => ({ ...o, [k]: form[k] ?? "" }), {}), ...patch };
      const { data } = await api.put(`/service-tickets/${ticket.id}`, body);
      toast.success(`Saved — ${data.status}`);
      onSaved(data);
    } catch (e) {
      toast.error(detail(e, "Could not save ticket"));
    } finally {
      setSaving(false);
    }
  };
  const next = { OPEN: "ASSIGNED", ASSIGNED: "VISIT SCHEDULED", "VISIT SCHEDULED": "IN PROGRESS", "IN PROGRESS": "RESOLVED", WAITING: "IN PROGRESS", RESOLVED: "CLOSED" }[ticket.status];
  return (
    <Sheet title={`${ticket.ticket_no} · ${ticket.customer}`} onClose={onClose} testid="ticket-detail">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${TONE[ticket.status] || ""}`}>{ticket.status}</span>
        <span className="text-xs text-[var(--ink-2)]">{ticket.ticket_type} · {ticket.division} · raised {fmtDate(ticket.created_at)} by {ticket.created_by}</span>
      </div>
      <div className="text-sm bg-[var(--surface-2)] rounded-lg p-3">{ticket.complaint}</div>
      <div className="flex gap-2">
        {ticket.phone && <a href={`tel:${ticket.phone}`} className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-lg border border-[var(--border)] text-sm font-semibold"><Phone size={14} /> Call</a>}
        {ticket.phone && <a href={wa(ticket.phone)} target="_blank" rel="noreferrer" className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-lg border border-emerald-200 text-emerald-700 text-sm font-semibold"><MessageCircle size={14} /> WhatsApp</a>}
        <Link to={`/projects?open=${ticket.project_id}`} className="flex-1 inline-flex items-center justify-center py-2 rounded-lg border border-[var(--border)] text-sm font-semibold">Project</Link>
      </div>
      {ticket.site_address && <div className="text-xs text-[var(--ink-2)]">Site: {ticket.site_address}</div>}
      <div className="grid grid-cols-2 gap-2">
        <Field label="Status">
          <select className={inputCls} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} data-testid="ticket-status">
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="Priority">
          <select className={inputCls} value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
            {PRIORITIES.map((p) => <option key={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Assigned to">
          <input className={inputCls} value={form.assigned_to || ""} onChange={(e) => setForm({ ...form, assigned_to: e.target.value })} data-testid="ticket-assign" />
        </Field>
        <Field label="Visit date">
          <input type="date" className={inputCls} value={form.visit_date || ""} onChange={(e) => setForm({ ...form, visit_date: e.target.value })} />
        </Field>
      </div>
      <Field label="Resolution (required to resolve / close)">
        <textarea rows={2} className={inputCls} value={form.resolution || ""} onChange={(e) => setForm({ ...form, resolution: e.target.value })} data-testid="ticket-resolution" />
      </Field>
      <Field label="Parts used">
        <input className={inputCls} value={form.parts_used || ""} onChange={(e) => setForm({ ...form, parts_used: e.target.value })} />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={!!form.customer_signed} onChange={(e) => setForm({ ...form, customer_signed: e.target.checked })} />
        Customer signed off the visit
      </label>
      {form.customer_signed && <Field label="Signed by"><input className={inputCls} value={form.signed_by || ""} onChange={(e) => setForm({ ...form, signed_by: e.target.value })} /></Field>}
      <div className="flex flex-wrap justify-end gap-2">
        {next && <button className="btn-ghost" disabled={saving} onClick={() => save({ status: next })} data-testid="ticket-advance">Mark {next.toLowerCase()}</button>}
        <button className="btn-primary" disabled={saving} onClick={() => save()} data-testid="ticket-update">{saving ? "Saving…" : "Save"}</button>
      </div>
      <AttachmentPanel entity="service_ticket" itemId={ticket.id} defaultCategory="Site Photo" />
      {(ticket.history || []).length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-1">History</div>
          <ul className="space-y-1">
            {[...ticket.history].reverse().map((h, i) => (
              <li key={i} className="text-xs border-l-2 border-[var(--border)] pl-2">
                <b>{h.status}</b> · {fmtDate(h.at)} · {h.by}{h.note ? ` — ${h.note}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Sheet>
  );
}
