import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronRight, FilePlus2, CalendarPlus, ListPlus, Pencil, Phone, MapPin, AlertTriangle } from "lucide-react";
import Topbar from "@/components/Topbar";
import ErrorState from "@/components/ErrorState";
import StageBadge from "@/components/StageBadge";
import { Skeleton } from "@/components/ui/skeleton";
import { RecordList, Timeline, GROUPS } from "@/components/ContextRecords";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";

const TABS = ["timeline", "quotes", "sales", "payments", "invoices", "meets", "tasks", "purchase_orders",
              "manufacturer_orders", "service_tickets", "leads", "calls"];
const ALWAYS = new Set(["timeline", "quotes", "meets", "tasks"]);

/** One project, its customer (live) and everything that belongs to it
 * (GET /projects/{id}/context). The full editor stays on Projects. */
export default function ProjectPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { canDo } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("timeline");

  const load = useCallback(() => {
    setError(null);
    api.get(`/projects/${id}/context`, { skipCache: true })
      .then(({ data }) => setData(data))
      .catch((e) => setError(e?.response?.status === 404 ? "missing" : e?.response?.status === 403 ? "unauthorized" : "error"));
  }, [id]);
  useEffect(() => { setData(null); load(); }, [load]);

  const tabs = useMemo(() => TABS.filter((t) => ALWAYS.has(t) || (data?.records?.[t] || []).length), [data]);

  if (error) {
    return (
      <>
        <Topbar title="Project" />
        <div className="p-6">
          <ErrorState
            title={error === "missing" ? "This project doesn't exist (it may have been deleted)" : error === "unauthorized" ? "You don't have access to projects" : "Couldn't load this project"}
            onRetry={error === "error" ? load : undefined}
          />
          <Link to="/projects" className="text-sm text-[var(--color-primary)]">← All projects</Link>
        </div>
      </>
    );
  }

  const p = data?.project;
  const c = data?.customer;
  const t = data?.totals || {};
  const r = data?.records || {};
  const prog = data?.workflow?.progress || {};
  const btn = "inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm hover:bg-[var(--color-surface-muted)]";

  return (
    <>
      <Topbar title={p ? (p.project_name || p.project_no) : "Project"} subtitle={p ? [p.project_no, p.division, p.stage].filter(Boolean).join(" · ") : "Loading…"} />
      <div className="p-4 sm:p-6 space-y-4" data-testid="project-page">
        <nav className="text-xs text-[var(--color-text-muted)] flex items-center gap-1 flex-wrap" aria-label="Breadcrumb">
          <Link to="/customers" className="hover:underline">Customers</Link> <ChevronRight size={12} />
          {c ? <Link to={`/customers/${c.id}`} className="hover:underline">{c.name}</Link> : <span>{p?.customer || "…"}</span>}
          <ChevronRight size={12} /> <span className="text-[var(--color-text)]">{p ? (p.project_name || p.project_no) : "…"}</span>
        </nav>

        {!data ? <Skeleton className="h-40 w-full" /> : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-lg font-semibold">{p.project_name || "Project"} <span className="ml-1 text-xs font-mono text-[var(--color-text-muted)]">{p.project_no}</span></div>
                    <div className="text-sm text-[var(--color-text-muted)] flex items-center gap-2 flex-wrap">
                      <StageBadge stage={p.stage} /> {p.division}
                      {p.target_date && <span>· target {fmtDate(p.target_date)}</span>}
                    </div>
                  </div>
                  {canDo("projects", "edit") && (
                    <Link to={`/projects?open=${p.id}`} className={btn} data-testid="project-edit"><Pencil size={14} /> Open in Projects</Link>
                  )}
                </div>
                {p.site_address && <div className="text-sm inline-flex items-center gap-1.5"><MapPin size={13} /> {p.site_address}</div>}
                <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm" data-testid="project-people">
                  {p.assigned_engineer && <span><span className="text-[var(--color-text-muted)]">Engineer:</span> {p.assigned_engineer}</span>}
                  {p.project_manager && <span><span className="text-[var(--color-text-muted)]">Manager:</span> {p.project_manager}</span>}
                  <span><span className="text-[var(--color-text-muted)]">{p.partner_role || (String(p.division).toUpperCase() === "MAP" ? "Applicator" : "Supplier")}:</span>{" "}
                    {p.partner_name || p.partner_code || <span className="text-[var(--color-warning)]">not set</span>}</span>
                </div>
                <div className="rounded-lg bg-[var(--color-surface-muted)] p-3 text-sm" data-testid="project-customer">
                  {c ? (
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">Customer</div>
                        <Link to={`/customers/${c.id}`} className="font-medium text-[var(--color-primary)]">{c.name}</Link>
                        {c.code && <span className="ml-1.5 text-[11px] font-mono text-[var(--color-text-muted)]">{c.code}</span>}
                        <div className="text-xs text-[var(--color-text-muted)]">{[c.company, c.email].filter(Boolean).join(" · ")}</div>
                      </div>
                      {c.phone && <a href={`tel:${c.phone}`} className="inline-flex items-center gap-1.5"><Phone size={13} /> {c.phone}</a>}
                    </div>
                  ) : (
                    <div className="text-[var(--color-warning)] inline-flex items-center gap-1.5">
                      <AlertTriangle size={13} /> Not linked to a customer yet{p.customer ? ` (“${p.customer}”)` : ""} — open it in Projects to link one.
                    </div>
                  )}
                </div>
                {prog.total > 0 && (
                  <div>
                    <div className="flex justify-between text-xs text-[var(--color-text-muted)] mb-1">
                      <span>{prog.current ? `Now: ${prog.current}` : "All stages done"}</span><span>{prog.done}/{prog.total} · {prog.percent}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-[var(--color-surface-muted)] overflow-hidden">
                      <div className="h-full bg-[var(--color-primary)]" style={{ width: `${prog.percent}%` }} />
                    </div>
                  </div>
                )}
                <div className="flex flex-wrap gap-2 pt-1">
                  {canDo("quotes", "create") && <button className={btn} onClick={() => nav(`/quotes?new=1&project_id=${p.id}`)} data-testid="project-new-quote"><FilePlus2 size={14} /> New quotation</button>}
                  {canDo("meetplan", "create") && <button className={btn} onClick={() => nav(`/meets?new=1&project_id=${p.id}`)} data-testid="project-new-meet"><CalendarPlus size={14} /> New meeting</button>}
                  {canDo("tasks", "create") && <button className={btn} onClick={() => nav(`/tasks?new=1&project_id=${p.id}`)} data-testid="project-new-task"><ListPlus size={14} /> New task</button>}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 content-start">
                {[["Order value", inrFull(t.order_value)], ["Received", inrFull(t.received)], ["Pending", inrFull(t.pending)],
                  ["Quotations", t.quotes || 0], ["Meetings", t.meets || 0], ["Vendor POs", t.purchase_orders || 0]].map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
                    <div className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">{k}</div>
                    <div className="text-base font-semibold font-mono">{v}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
              <div className="flex gap-1 overflow-x-auto border-b border-[var(--color-border)] px-2" role="tablist">
                {tabs.map((k) => (
                  <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                          className={`px-3 py-2.5 text-sm whitespace-nowrap border-b-2 -mb-px ${tab === k ? "border-[var(--color-primary)] text-[var(--color-primary)] font-medium" : "border-transparent text-[var(--color-text-muted)]"}`}
                          data-testid={`project-tab-${k}`}>
                    {k === "timeline" ? "Timeline" : GROUPS[k].label}
                    {k !== "timeline" && <span className="ml-1 text-xs opacity-70">{(r[k] || []).length}</span>}
                  </button>
                ))}
              </div>
              <div className="p-3 sm:p-4">
                {tab === "timeline" ? <Timeline rows={data.timeline} testid="project-timeline" />
                  : <RecordList kind={tab} rows={r[tab]} testid={`project-${tab}`} />}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
