import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronRight, FilePlus2, FolderPlus, CalendarPlus, ListPlus, Pencil, Phone, MessageCircle, Mail } from "lucide-react";
import Topbar from "@/components/Topbar";
import ErrorState from "@/components/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { RecordList, Timeline, GROUPS } from "@/components/ContextRecords";
import { NewProjectForm } from "@/components/CustomerProjectPicker";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { inrFull } from "@/lib/format";

const TABS = ["timeline", "projects", "quotes", "sales", "payments", "invoices", "meets", "tasks", "leads", "calls",
              "visitors", "service_tickets", "purchase_orders", "manufacturer_orders"];
const ALWAYS = new Set(["timeline", "projects", "quotes"]);

/** One customer and everything linked to them (GET /customers/{id}/context). */
export default function CustomerPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { canDo } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("timeline");
  const [addingProject, setAddingProject] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api.get(`/customers/${id}/context`, { skipCache: true })
      .then(({ data }) => setData(data))
      .catch((e) => setError(e?.response?.status === 404 ? "missing" : e?.response?.status === 403 ? "unauthorized" : "error"));
  }, [id]);
  useEffect(() => { setData(null); load(); }, [load]);

  const tabs = useMemo(() => TABS.filter((t) => ALWAYS.has(t) || (data?.records?.[t] || []).length), [data]);

  if (error) {
    return (
      <>
        <Topbar title="Customer" />
        <div className="p-6">
          <ErrorState
            title={error === "missing" ? "This customer doesn't exist (it may have been deleted)" : error === "unauthorized" ? "You don't have access to customers" : "Couldn't load this customer"}
            onRetry={error === "error" ? load : undefined}
          />
          <Link to="/customers" className="text-sm text-[var(--color-primary)]">← All customers</Link>
        </div>
      </>
    );
  }

  const c = data?.customer;
  const t = data?.totals || {};
  const r = data?.records || {};
  const phone = String(c?.phone || "").replace(/\D/g, "").slice(-10);
  const btn = "inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm hover:bg-[var(--color-surface-muted)]";

  return (
    <>
      <Topbar title={c?.name || "Customer"} subtitle={c ? [c.code, c.stage, c.company].filter(Boolean).join(" · ") : "Loading…"} />
      <div className="p-4 sm:p-6 space-y-4" data-testid="customer-page">
        <nav className="text-xs text-[var(--color-text-muted)] flex items-center gap-1" aria-label="Breadcrumb">
          <Link to="/customers" className="hover:underline">Customers</Link> <ChevronRight size={12} /> <span className="text-[var(--color-text)]">{c?.name || "…"}</span>
        </nav>

        {!data ? <Skeleton className="h-40 w-full" /> : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-lg font-semibold">{c.name} {c.code && <span className="ml-1 text-xs font-mono px-1.5 py-0.5 rounded bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]">{c.code}</span>}</div>
                    <div className="text-sm text-[var(--color-text-muted)]">{[c.company, c.division, c.stage].filter(Boolean).join(" · ")}</div>
                  </div>
                  {canDo("customers", "edit") && (
                    <Link to={`/customers?edit=${c.id}`} className={btn} data-testid="customer-edit"><Pencil size={14} /> Edit</Link>
                  )}
                </div>
                <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                  {c.phone && <a href={`tel:${c.phone}`} className="inline-flex items-center gap-1.5"><Phone size={13} /> {c.phone}</a>}
                  {phone && <a href={`https://wa.me/91${phone}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-[var(--color-success)]"><MessageCircle size={13} /> WhatsApp</a>}
                  {c.email && <a href={`mailto:${c.email}`} className="inline-flex items-center gap-1.5"><Mail size={13} /> {c.email}</a>}
                </div>
                {c.address && <div className="text-sm text-[var(--color-text-muted)]">{c.address}</div>}
                {(data.contacts || []).length > 0 && (
                  <div className="text-xs text-[var(--color-text-muted)]">
                    Contacts: {data.contacts.map((x) => [x.contact_name, x.role, x.contact_phone].filter(Boolean).join(" · ")).join("; ")}
                  </div>
                )}
                <div className="flex flex-wrap gap-2 pt-1">
                  {canDo("quotes", "create") && <button className={btn} onClick={() => nav(`/quotes?new=1&customer_id=${c.id}`)} data-testid="customer-new-quote"><FilePlus2 size={14} /> New quotation</button>}
                  {canDo("projects", "create") && <button className={btn} onClick={() => setAddingProject((v) => !v)} data-testid="customer-new-project"><FolderPlus size={14} /> New project</button>}
                  {canDo("meetplan", "create") && <button className={btn} onClick={() => nav(`/meets?new=1&customer_id=${c.id}`)} data-testid="customer-new-meet"><CalendarPlus size={14} /> New meeting</button>}
                  {canDo("tasks", "create") && <button className={btn} onClick={() => nav(`/tasks?new=1&customer_id=${c.id}`)} data-testid="customer-new-task"><ListPlus size={14} /> New task</button>}
                </div>
                {addingProject && (
                  <NewProjectForm customer={c} division={c.division || "Furniture"} testid="customer-np"
                                  onCancel={() => setAddingProject(false)}
                                  onCreated={(p) => { setAddingProject(false); nav(`/projects/${p.id}`); }} />
                )}
              </div>
              <div className="grid grid-cols-2 gap-3 content-start">
                {[["Order value", inrFull(t.order_value)], ["Received", inrFull(t.received)], ["Pending", inrFull(t.pending)],
                  ["Projects", t.projects || 0], ["Quotations", t.quotes || 0], ["Open service", t.open_service_tickets || 0]].map(([k, v]) => (
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
                          data-testid={`customer-tab-${k}`}>
                    {k === "timeline" ? "Timeline" : GROUPS[k].label}
                    {k !== "timeline" && <span className="ml-1 text-xs opacity-70">{(r[k] || []).length}</span>}
                  </button>
                ))}
              </div>
              <div className="p-3 sm:p-4">
                {tab === "timeline" ? <Timeline rows={data.timeline} testid="customer-timeline" />
                  : <RecordList kind={tab} rows={r[tab]} testid={`customer-${tab}`} />}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
