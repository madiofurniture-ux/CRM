import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { Search, CheckCircle2, Circle, MinusCircle, ArrowRight } from "lucide-react";

// Real gate text only — pulled from server.py/lifecycle.py, never the mockup's
// sample copy. Left blank where this codebase enforces nothing today (see
// the report: Project stage-advance has no "assigned engineer" check, for
// instance, even though the original mockup showed one).
const GATES = {
  quote_to_sale: "Discount above 10% of the quote subtotal requires admin sign-off (lifecycle.needs_approval) — both auto-approval-conversion and the manual Quote→Sale route are admin-only.",
  payment_to_customer: "The customer record is created/activated only once the sale's balance reaches zero (atomic upsert-by-phone, so a race between two payments can't double it).",
  project_stage: "Stage must be one of Survey / Quoted / Execution / Review / Closure / Completed — this codebase has no \"assigned engineer required\" check on any stage transition today.",
};

function StepIcon({ state }) {
  if (state === "reached") return <CheckCircle2 size={18} className="text-[var(--moss)]" />;
  if (state === "not_tracked") return <MinusCircle size={18} className="text-[var(--ink-3)]" />;
  return <Circle size={18} className="text-[var(--ink-3)]" />;
}

function Step({ label, state, summary, gate, link, note }) {
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <StepIcon state={state} />
        <div className="w-px flex-1 bg-[var(--border)] my-1" />
      </div>
      <div className="pb-6 min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-heading font-semibold text-sm text-[var(--ink)]">{label}</span>
          {state === "reached" && link && (
            <a href={link} className="text-[11px] text-[var(--brand)] hover:underline inline-flex items-center gap-0.5">
              Open <ArrowRight size={11} />
            </a>
          )}
        </div>
        {state === "reached" && summary && <div className="text-xs text-[var(--ink-2)] mt-0.5">{summary}</div>}
        {state === "not_reached" && <div className="text-xs text-[var(--ink-3)] italic mt-0.5">Not reached yet</div>}
        {state === "not_tracked" && <div className="text-xs text-[var(--ink-3)] italic mt-0.5">{note || "No per-customer link exists for this record in this codebase"}</div>}
        {gate && <div className="text-[11px] text-[var(--warn)] bg-amber-50 border border-amber-100 rounded-md px-2 py-1 mt-1.5">🔒 {gate}</div>}
      </div>
    </div>
  );
}

export default function RecordChain() {
  const [params] = useSearchParams();
  const [phone, setPhone] = useState(params.get("phone") || "");
  const [query, setQuery] = useState(phone);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const search = (p) => {
    const ph = (p || query).trim();
    if (!ph) return;
    setLoading(true);
    api.get(`/journey/${encodeURIComponent(ph)}`)
      .then((r) => { setData(r.data); setPhone(ph); })
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  };

  const eventsByPrefix = (prefix) => (data?.events || []).filter((e) => (e.kind || "").startsWith(prefix));
  const isDW = (data?.divisions || []).includes("D&W");
  const quotes = data?.linked?.quotes || [];
  const sales = data?.linked?.sales || [];
  const payments = eventsByPrefix("Payment");
  const incentives = data?.incentives || [];

  return (
    <>
      <Topbar title="Record Chain" subtitle="Where one customer's records stand across the full conversion chain" />
      <div className="p-6 space-y-6 max-w-2xl" data-testid="record-chain-page">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]" />
            <input value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
              placeholder="Search by phone number…"
              className="w-full pl-8 pr-3 py-2 rounded-lg border border-[var(--border)] text-sm"
              data-testid="record-chain-search" />
          </div>
          <button onClick={() => search()} className="btn-primary" data-testid="record-chain-go">Go</button>
        </div>

        {loading && <div className="text-sm text-[var(--ink-3)]">Loading…</div>}

        {!loading && data && !data.phone && (
          <div className="text-sm text-[var(--ink-3)]">No records found for that phone number.</div>
        )}

        {!loading && data?.phone && (
          <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-5">
            <div className="mb-1">
              <div className="font-heading font-bold text-lg text-[var(--ink)]">{data.name || "Unnamed"}</div>
              <div className="text-xs text-[var(--ink-3)] font-mono">{data.phone}</div>
            </div>

            <div className="mt-5">
              <Step label="Visitor" state={data.visitor ? "reached" : "not_reached"}
                summary={data.visitor && `${data.visitor.requirement || "Visit"} · attended by ${data.visitor.attend_person || "—"} · ${fmtDate(data.visitor.date)}`}
                link="/visitors" />

              <Step label="Lead" state={eventsByPrefix("Lead").length ? "reached" : "not_reached"}
                summary={eventsByPrefix("Lead")[0]?.title}
                link="/leads" />

              <Step label="Quotation" state={quotes.length ? "reached" : "not_reached"}
                summary={quotes.length && `${quotes.length} quote(s) · latest ${quotes[quotes.length - 1].quote_no} · ${inrFull(quotes[quotes.length - 1].value)} · ${quotes[quotes.length - 1].stage}`}
                link={quotes.length ? `/quotes/${quotes[quotes.length - 1].id}` : undefined} />

              <Step label="Sales Order" state={sales.length ? "reached" : "not_reached"}
                summary={sales.length && `${sales[sales.length - 1].sale_no} · ${inrFull(sales[sales.length - 1].value)} · ${sales[sales.length - 1].stage}`}
                gate={sales.length || quotes.some((q) => q.approval === "approved" || q.status === "Won") ? GATES.quote_to_sale : undefined}
                link="/sales" />

              {isDW && (
                <Step label="Survey / BOQ (D&W)" state={data.dw_survey ? "reached" : "not_reached"}
                  summary={data.dw_survey && `${data.dw_survey.survey_id || ""} · ${data.dw_survey.status || ""}`}
                  link="/dw-survey" />
              )}

              <Step label="Project" state={data.project ? "reached" : "not_reached"}
                summary={data.project && `${data.project.project_no} · Stage: ${data.project.stage} · Engineer: ${data.project.assigned_engineer || "unassigned"}`}
                gate={data.project ? GATES.project_stage : undefined}
                link="/projects" />

              <Step label="Invoice / Payments" state={payments.length ? "reached" : "not_reached"}
                summary={payments.length && `${payments.length} payment(s) · Collected ${inrFull(data.totals?.collected)} · Balance ${inrFull(data.totals?.balance)}`}
                gate={data.totals?.balance === 0 ? GATES.payment_to_customer : undefined}
                link="/outstanding" />

              <Step label="Incentives" state={incentives.length ? "reached" : "not_reached"}
                summary={incentives.length && `${incentives.length} payout(s) · ${incentives.map((i) => i.status).join(", ")}`}
                link="/incentives" />

              <Step label="Petty Cash" state="not_tracked"
                note="Petty cash is a general project wallet, not a per-customer ledger field in this codebase — nothing here to link."
                link="/petty-cash" />

              <Step label="P&L" state={data.project ? "reached" : "not_reached"}
                summary={data.project && "Computed per-project — visible to roles with Project P&L access"}
                link="/reports/project-pnl" />
            </div>

            <div className="text-[11px] text-[var(--ink-3)] pt-2 border-t border-[var(--border-light)]">
              The customer record is created once (upsert-by-phone on first fully-paid sale) and every hop above that
              writes to a business record is now in the Audit Trail, tenant-scoped server-side.
            </div>
          </div>
        )}
      </div>
    </>
  );
}
