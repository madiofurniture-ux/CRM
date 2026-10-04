import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw, ChevronRight } from "lucide-react";
import api from "@/lib/api";
import { inr } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import PageHeader from "@/components/PageHeader";
import MetricCard from "@/components/MetricCard";
import SectionCard from "@/components/SectionCard";
import SecondaryButton from "@/components/SecondaryButton";
import ErrorState from "@/components/ErrorState";
import EmptyState from "@/components/EmptyState";
import SetupNudge from "@/components/SetupNudge";

function greeting(hour) {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);

function TodayRow({ to, label, count, tone = "default" }) {
  const toneClass = count > 0 && tone === "danger"
    ? "text-[var(--color-danger)]"
    : count > 0 ? "text-[var(--color-primary)]" : "text-[var(--color-text-muted)]";
  return (
    <Link
      to={to}
      className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] hover:bg-[var(--color-surface-muted)] transition-colors"
    >
      <span className="text-sm text-[var(--color-text)]">{label}</span>
      <span className="flex items-center gap-1">
        <span className={`text-sm font-semibold font-mono ${toneClass}`}>{count}</span>
        <ChevronRight size={14} className="text-[var(--color-text-muted)]" />
      </span>
    </Link>
  );
}

/** Vertical bars, one per division, scaled to the largest. */
function DivisionBars({ bars, loading, empty, label }) {
  if (!loading && bars.length === 0) return <EmptyState title={empty} />;
  const max = Math.max(...bars.map((b) => b.value), 1);
  return (
    <div className="flex items-end gap-6 h-48" role="img" aria-label={`${label} bar chart`}>
      {(loading ? Array.from({ length: 3 }) : bars).map((b, i) => (
        <div key={b?.division || i} className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
          {b && <div className="text-xs font-mono font-semibold text-[var(--color-text)]">{inr(b.value)}</div>}
          <div
            className={`w-full rounded-t-[var(--radius-sm)] ${b ? "" : "bg-[var(--color-surface-muted)] animate-pulse"}`}
            style={b ? { height: `${Math.max((b.value / max) * 100, 2)}%`, background: "var(--color-primary)" } : { height: "30%" }}
          />
          <div className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-text-muted)] text-center">
            {b ? b.division : ""}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Home screen: live KPIs, open pipeline by division, and what needs you
 * today. Everything here comes from GET /overview/command-centre (plus the
 * money-request summary when the Expenses module is on). */
export default function CommandCentre() {
  const { user, tenant, canAccess } = useAuth();
  const [overview, setOverview] = useState(null);
  const [moneySummary, setMoneySummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [fu, setFu] = useState(null);
  const showMoney = canAccess("expenses");
  const showFollowups = canAccess("leads");

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    if (showFollowups) {
      api.get("/followups/summary", { skipCache: true })
        .then((r) => setFu(r.data?.counts || null))
        .catch(() => setFu(null));
    }
    if (showMoney) {
      api.get("/money-requests/summary", { skipCache: true })
        .then((r) => setMoneySummary(r.data))
        .catch(() => setMoneySummary(null));
    }
    return api
      .get("/overview/command-centre", { skipCache: true })
      .then((r) => {
        setOverview(r.data || {});
        setUpdatedAt(new Date());
      })
      .catch((err) => {
        const status = err?.response?.status;
        setError({ unauthorized: status === 401 || status === 403 });
      })
      .finally(() => setLoading(false));
  }, [showMoney, showFollowups]);

  useEffect(() => { load(); }, [load]);

  const k = overview?.kpis || {};
  const won = k.won_this_month || {};
  const live = k.projects_live || {};
  const breaches = num(k.sla_breaches);
  const kpis = [
    { label: "Open pipeline", value: inr(num(k.open_pipeline)), sub: "Open-stage quotations", to: "/pipeline" },
    { label: "Won this month", value: inr(num(won.value)),
      sub: `${num(won.orders)} order${num(won.orders) === 1 ? "" : "s"} this month`, to: "/sales" },
    { label: "Receivables", value: inr(num(k.receivables)), sub: "Outstanding across all sales", to: "/outstanding" },
    { label: "Projects live", value: String(num(live.count)), sub: `${num(live.at_risk)} at risk`, to: "/projects" },
    { label: "Overdue tasks", value: String(breaches), sub: breaches > 0 ? "Needs action" : "All clear", to: "/tasks" },
  ];

  const pipelineBars = (overview?.pipeline_by_unit || []).map((b) => ({ ...b, value: num(b.value) }));
  const revenueBars = (overview?.revenue_by_unit || []).map((b) => ({ ...b, value: num(b.value) }));
  const pendingApprovals = overview?.pending_approvals || [];
  const today = overview?.today || {};
  const moneyForYou = num(moneySummary?.assigned_to_me);
  const now = new Date();

  return (
    <div className="min-h-screen bg-[var(--color-bg)]" data-testid="command-centre-page">
      <div className="p-4 md:p-6 max-w-[1440px] mx-auto space-y-6">
        <PageHeader
          eyebrow="HOME"
          title={`${greeting(now.getHours())}, ${user?.name || "there"}`}
          subtitle={`${tenant?.name || "Your business"} at a glance: pipeline, projects and what needs you today.`}
          actions={
            <SecondaryButton onClick={load} disabled={loading} aria-label="Refresh">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
              {updatedAt ? `Updated ${updatedAt.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}` : "Refresh"}
            </SecondaryButton>
          }
        />

        <SetupNudge />

        {error ? (
          <ErrorState
            title={error.unauthorized ? "You don't have access to this view" : "Couldn't load the home screen"}
            hint={error.unauthorized ? undefined : "The server didn't respond. Check your connection and try again."}
            onRetry={error.unauthorized ? undefined : load}
          />
        ) : (
          <>
            {fu && (
              <Link to="/follow-ups" className="grid grid-cols-3 gap-3" data-testid="followup-strip" aria-label="Open follow-ups">
                {[["Overdue", fu.overdue, "bg-red-50 text-red-700 border-red-200"],
                  ["Today", fu.today, "bg-amber-50 text-amber-700 border-amber-200"],
                  ["Upcoming", fu.upcoming, "bg-blue-50 text-blue-700 border-blue-200"]].map(([label, n, tone]) => (
                  <div key={label} className={`rounded-[var(--radius-lg)] border p-3 md:p-4 ${tone}`}>
                    <div className="text-[10px] md:text-xs font-bold uppercase tracking-wider">{label} follow-ups</div>
                    <div className="font-heading font-bold text-2xl md:text-3xl">{num(n)}</div>
                  </div>
                ))}
                {(num(fu.no_follow_up) + num(fu.no_next_action) + num(fu.unassigned)) > 0 && (
                  <div className="col-span-3 text-xs text-[var(--color-text-muted)] -mt-1">
                    {num(fu.no_follow_up)} open leads have no follow-up date · {num(fu.no_next_action)} have no next action · {num(fu.unassigned)} unassigned · {num(fu.open_service_tickets)} open service tickets
                  </div>
                )}
              </Link>
            )}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {loading && !overview
                ? Array.from({ length: 5 }).map((_, i) => <MetricCard key={i} label="" loading />)
                : kpis.map((m) => <MetricCard key={m.label} {...m} />)}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-8 space-y-6">
                <SectionCard title="Pipeline by division" subtitle="Open quotation value">
                  <DivisionBars bars={pipelineBars} loading={loading && !overview} empty="No open pipeline right now." label="Pipeline by division" />
                </SectionCard>
                <SectionCard title="Revenue by division" subtitle="Booked sales, cancelled orders excluded">
                  <DivisionBars bars={revenueBars} loading={loading && !overview} empty="No sales booked yet." label="Revenue by division" />
                </SectionCard>
              </div>

              <div className="lg:col-span-4 space-y-6">
                <SectionCard title="Today">
                  {loading && !overview ? (
                    <div className="h-24 rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] animate-pulse" />
                  ) : (
                    <div className="space-y-2" data-testid="today-panel">
                      <TodayRow to="/follow-ups" label="Lead follow-ups due" count={num(today.follow_ups_due)} />
                      <TodayRow to="/follow-ups" label="Follow-ups overdue" count={num(today.follow_ups_overdue)} tone="danger" />
                      <TodayRow to="/tasks" label="Overdue tasks" count={breaches} tone="danger" />
                      {showMoney && (
                        <TodayRow to="/approvals" label="Money requests waiting on you" count={moneyForYou} />
                      )}
                    </div>
                  )}
                </SectionCard>

                <SectionCard title="Discount approvals">
                  {loading && !overview ? (
                    <div className="h-14 rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] animate-pulse" />
                  ) : pendingApprovals.length === 0 ? (
                    <EmptyState title="No approvals pending." />
                  ) : (
                    <div className="space-y-2">
                      {pendingApprovals.map((p) => (
                        <Link
                          key={p.id || p.quote_no}
                          to={p.id ? `/quotes/ws/${p.id}` : "/quotes"}
                          className="block p-3 rounded-[var(--radius-sm)] bg-[var(--color-danger)]/5 border border-[var(--color-danger)]/20 hover:bg-[var(--color-danger)]/10 transition-colors"
                        >
                          <div className="text-xs text-[var(--color-text)]">
                            <span className="font-mono font-semibold">{p.quote_no}</span> ({p.customer}): {num(p.discount_pct)}% discount above the limit
                          </div>
                        </Link>
                      ))}
                    </div>
                  )}
                </SectionCard>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
