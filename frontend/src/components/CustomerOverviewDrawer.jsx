import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { X } from "lucide-react";
import AttachmentPanel from "@/components/AttachmentPanel";

/** Customer 360 from GET /customers/{id}/overview: every project (with its
 * division-stage progress), quotation, payment and service ticket. */
export default function CustomerOverviewDrawer({ customerId, onClose }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!customerId) return;
    setData(null); setFailed(false);
    api.get(`/customers/${customerId}/overview`, { skipCache: true })
      .then(({ data }) => setData(data)).catch(() => setFailed(true));
  }, [customerId]);
  if (!customerId) return null;
  const c = data?.customer;
  const Section = ({ title, children }) => (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-bold mb-1.5">{title}</div>
      {children}
    </div>
  );
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center sm:p-4" onClick={onClose}>
      <div className="bg-[var(--color-surface)] rounded-t-2xl sm:rounded-xl w-full max-w-2xl max-h-[95vh] overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()} data-testid="customer-overview">
        <div className="sticky top-0 bg-[var(--color-surface)] flex items-center justify-between px-4 py-3 border-b z-10">
          <h3 className="font-heading font-semibold">{c?.name || "Customer"}</h3>
          <button onClick={onClose} className="p-1.5 rounded-md" aria-label="Close"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-5">
          {failed && <div className="text-sm text-[var(--color-danger)]">Couldn't load this customer.</div>}
          {!data && !failed && <div className="text-sm text-[var(--color-text-muted)]">Loading…</div>}
          {data && (
            <>
              <div className="text-xs text-[var(--color-text-muted)]">
                {[c.phone, c.email, c.address, c.gstin && `GST ${c.gstin}`].filter(Boolean).join(" · ") || "No contact details"}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[["Projects", data.totals.projects], ["Order value", inrFull(data.totals.order_value)],
                  ["Received", inrFull(data.totals.received)], ["Pending", inrFull(data.totals.pending)]].map(([k, v]) => (
                  <div key={k} className="bg-[var(--color-surface-muted)] rounded-xl p-3">
                    <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-semibold">{k}</div>
                    <div className="font-mono font-bold text-sm">{v}</div>
                  </div>
                ))}
              </div>
              <Section title="Projects">
                {data.projects.length === 0 && <div className="text-sm text-[var(--color-text-muted)]">No projects yet.</div>}
                <div className="space-y-1.5">
                  {data.projects.map((p) => (
                    <Link key={p.id} to={`/projects?open=${p.id}`} className="block border border-[var(--color-border)] rounded-xl px-3 py-2 hover:bg-[var(--color-surface-muted)]">
                      <div className="flex justify-between text-sm"><b>{p.project_no}</b><span className="font-mono">{inrFull(p.value)}</span></div>
                      <div className="text-xs text-[var(--color-text-muted)]">{p.division} · {p.project_name || p.site_address || "—"} · {p.progress}% · next {p.current_stage || "—"}</div>
                    </Link>
                  ))}
                </div>
              </Section>
              <Section title={`Service history (${data.totals.open_service_tickets} open)`}>
                {data.service_tickets.length === 0 && <div className="text-sm text-[var(--color-text-muted)]">No service requests.</div>}
                <div className="space-y-1.5">
                  {data.service_tickets.map((t) => (
                    <Link key={t.id} to={`/service?ticket=${t.id}`} className="block border border-[var(--color-border)] rounded-xl px-3 py-2 hover:bg-[var(--color-surface-muted)]">
                      <div className="flex justify-between text-sm"><b className="font-mono text-xs">{t.ticket_no}</b><span className="text-[11px] font-bold">{t.status}</span></div>
                      <div className="text-xs">{t.complaint}</div>
                      <div className="text-[11px] text-[var(--color-text-muted)]">{fmtDate(t.created_at)} · {t.project_no}</div>
                    </Link>
                  ))}
                </div>
              </Section>
              <Section title="Quotations">
                {data.quotes.length === 0 && <div className="text-sm text-[var(--color-text-muted)]">No quotations.</div>}
                {data.quotes.map((q) => (
                  <Link key={q.id} to={`/quotes/ws/${q.id}`} className="flex justify-between text-sm border-b border-[var(--color-border)] py-1.5 hover:underline">
                    <span>{q.quote_no}{q.version > 1 ? ` (rev ${q.version})` : ""} · {q.stage || q.status}</span>
                    <span className="font-mono">{inrFull(q.grand_total || q.value)}</span>
                  </Link>
                ))}
              </Section>
              <Section title="Payments">
                {data.payments.length === 0 && <div className="text-sm text-[var(--color-text-muted)]">No payments recorded.</div>}
                {data.payments.map((p) => (
                  <div key={p.id} className="flex justify-between text-sm border-b border-[var(--color-border)] py-1.5">
                    <span>{fmtDate(p.date)} · {p.mode}{p.kind ? ` · ${p.kind}` : ""}</span>
                    <span className="font-mono">{p.direction === "Refund" ? "−" : ""}{inrFull(p.amount)}</span>
                  </div>
                ))}
              </Section>
              <Section title="Documents">
                <AttachmentPanel entity="customer" itemId={c.id} defaultCategory="Customer Reference" />
              </Section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
