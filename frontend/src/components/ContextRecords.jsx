import { Link } from "react-router-dom";
import StageBadge from "@/components/StageBadge";
import { inrFull, fmtDate, fmtDateTime } from "@/lib/format";

/** How each kind of linked record shows on the customer and project pages. */
export const GROUPS = {
  projects: {
    label: "Projects", to: (r) => `/projects/${r.id}`,
    title: (r) => r.project_name || r.project_no, sub: (r) => [r.project_no, r.site_address, r.division].filter(Boolean).join(" · "),
    stage: (r) => r.stage, amount: (r) => r.value,
  },
  leads: {
    label: "Enquiries", to: (r) => `/leads?open=${r.id}`,
    title: (r) => r.name, sub: (r) => [fmtDate(r.date), r.source, r.division].filter(Boolean).join(" · "),
    stage: (r) => r.stage, amount: (r) => r.value,
  },
  quotes: {
    label: "Quotations", to: (r) => `/quotes/ws/${r.id}`,
    title: (r) => `${r.quote_no}${Number(r.version) > 1 ? ` v${r.version}` : ""}`, sub: (r) => [fmtDate(r.date), r.division, r.by_user].filter(Boolean).join(" · "),
    stage: (r) => r.stage || r.status, amount: (r) => r.grand_total || r.value,
  },
  sales: {
    label: "Orders", to: () => "/sales",
    title: (r) => r.sale_no || "Order", sub: (r) => [fmtDate(r.date), r.quote_ref && `from ${r.quote_ref}`, r.division].filter(Boolean).join(" · "),
    stage: (r) => r.stage || r.status, amount: (r) => r.value, extra: (r) => (Number(r.balance) > 0 ? `Balance ${inrFull(r.balance)}` : ""),
  },
  invoices: {
    label: "Invoices", to: () => "/invoices",
    title: (r) => r.invoice_no || "Invoice", sub: (r) => [fmtDate(r.date), r.status].filter(Boolean).join(" · "),
    stage: (r) => r.status, amount: (r) => r.grand_total || r.total || r.amount,
  },
  payments: {
    label: "Payments", to: () => "/payments",
    title: (r) => `${r.direction === "Refund" ? "Refund" : "Received"} ${inrFull(r.amount)}`, sub: (r) => [fmtDate(r.date), r.mode, r.reference || r.payment_id].filter(Boolean).join(" · "),
    amount: (r) => (r.direction === "Refund" ? -1 : 1) * (Number(r.amount) || 0),
  },
  meets: {
    label: "Meetings", to: () => "/meets",
    title: (r) => r.title, sub: (r) => [fmtDate(r.date), r.time, r.with_person, r.location].filter(Boolean).join(" · "),
    stage: (r) => r.status,
  },
  tasks: {
    label: "Tasks", to: () => "/tasks",
    title: (r) => r.title, sub: (r) => [r.due_date && `due ${fmtDate(r.due_date)}`, r.assigned_to].filter(Boolean).join(" · "),
    stage: (r) => r.status,
  },
  calls: {
    label: "Calls", to: () => "/calls",
    title: (r) => r.outcome || "Call", sub: (r) => [fmtDate(r.date), r.by_user, r.notes].filter(Boolean).join(" · "),
  },
  visitors: {
    label: "Showroom visits", to: () => "/visitors",
    title: (r) => fmtDate(r.date) || "Visit", sub: (r) => [r.requirement, r.attend_person].filter(Boolean).join(" · "),
    stage: (r) => r.stage,
  },
  service_tickets: {
    label: "Service", to: (r) => `/service?ticket=${r.id}`,
    title: (r) => r.ticket_no || "Ticket", sub: (r) => [r.issue_type, r.description].filter(Boolean).join(" · "),
    stage: (r) => r.status,
  },
  purchase_orders: {
    label: "Vendor POs", to: () => "/purchase-orders",
    title: (r) => r.po_no || "PO", sub: (r) => [fmtDate(r.date), r.vendor_name || r.vendor_code].filter(Boolean).join(" · "),
    stage: (r) => r.status, amount: (r) => r.grand_total,
  },
  manufacturer_orders: {
    label: "Vendor orders", to: () => "/manufacturer-orders",
    title: (r) => r.order_code || r.description || "Vendor order", sub: (r) => [r.vendor_code, r.description, r.promised_date && `promised ${fmtDate(r.promised_date)}`].filter(Boolean).join(" · "),
    stage: (r) => r.status,
  },
};

export function RecordList({ kind, rows, empty, testid }) {
  const g = GROUPS[kind];
  if (!rows?.length) {
    return <div className="text-sm text-[var(--color-text-muted)] py-6 text-center" data-testid={`${testid}-empty`}>{empty || `No ${g.label.toLowerCase()} yet.`}</div>;
  }
  return (
    <div className="divide-y divide-[var(--color-border)]" data-testid={testid}>
      {rows.map((r) => {
        const amount = g.amount?.(r);
        const stage = g.stage?.(r);
        const extra = g.extra?.(r);
        return (
          <Link key={r.id} to={g.to(r)} className="flex items-center justify-between gap-3 py-2.5 px-1 hover:bg-[var(--color-surface-muted)] rounded" data-testid={`${testid}-row`}>
            <div className="min-w-0">
              <div className="text-sm font-medium text-[var(--color-text)] truncate">
                {g.title(r)}
                {r.linked === false && (
                  <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-warning)]/15 text-[var(--color-warning)]" title="Same phone number, not linked to this customer yet">same phone</span>
                )}
              </div>
              <div className="text-xs text-[var(--color-text-muted)] truncate">{g.sub(r)}</div>
            </div>
            <div className="text-right shrink-0">
              {amount ? <div className="text-sm font-mono">{inrFull(amount)}</div> : null}
              {extra && <div className="text-[11px] text-[var(--color-warning)]">{extra}</div>}
              {stage && <StageBadge stage={stage} />}
            </div>
          </Link>
        );
      })}
    </div>
  );
}

const ACTION = { create: "created", update: "updated", delete: "deleted", convert: "converted", payment: "payment recorded",
                 approve: "approved", stage: "moved stage", log: "note" };
const ENTITY = { lead: "Enquiry", quote: "Quotation", sale: "Order", project: "Project", customer: "Customer", visitor: "Visit",
                 inventory: "Stock item", payment: "Payment", meet: "Meeting", call: "Call", service_ticket: "Service ticket",
                 invoice: "Invoice" };

export function Timeline({ rows, testid = "timeline" }) {
  if (!rows?.length) return <div className="text-sm text-[var(--color-text-muted)] py-6 text-center">Nothing recorded yet.</div>;
  return (
    <ol className="relative border-l border-[var(--color-border)] ml-2 space-y-3" data-testid={testid}>
      {rows.map((t, i) => (
        <li key={t.id || i} className="ml-4">
          <span className="absolute -left-[5px] mt-1.5 w-2.5 h-2.5 rounded-full bg-[var(--color-primary)]" />
          <div className="text-sm">
            {t.from_record ? <span className="font-medium">{t.note}</span> : (
              <>
                <span className="font-medium">{ENTITY[t.entity] || t.entity}</span> {ACTION[t.action] || t.action}
                {t.note ? <span className="text-[var(--color-text-muted)]"> — {t.note}</span> : null}
                {t.action === "update" && t.changed?.length ? <span className="text-[var(--color-text-muted)]"> ({t.changed.join(", ").replace(/_/g, " ")})</span> : null}
              </>
            )}
          </div>
          <div className="text-[11px] text-[var(--color-text-muted)]">{String(t.at || "").length <= 10 ? fmtDate(t.at) : fmtDateTime(t.at)}{t.by_user ? ` · ${t.by_user}` : ""}</div>
        </li>
      ))}
    </ol>
  );
}
