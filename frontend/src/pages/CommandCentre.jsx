import { useCallback, useEffect, useState } from "react";
import { Download, Bell, RefreshCw } from "lucide-react";
import api from "@/lib/api";
import { inr } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import PageHeader from "@/components/PageHeader";
import MetricCard from "@/components/MetricCard";
import SectionCard from "@/components/SectionCard";
import SecondaryButton from "@/components/SecondaryButton";
import FilterBar from "@/components/FilterBar";
import ErrorState from "@/components/ErrorState";
import EmptyState from "@/components/EmptyState";

// Static — this checklist isn't backed by any collection, unlike the KPI
// cards and pipeline chart below, which are all live from
// GET /overview/command-centre.
const READINESS = [
  { label: "Query isolation", pct: 92 },
  { label: "Audit trail instrumented", pct: 78 },
  { label: "Role matrix server-side", pct: 61 },
  { label: "Export controls & approval", pct: 84 },
  { label: "Tax pack integration (India)", pct: 67 },
  { label: "Install branding assets", pct: 20 },
];

const STATES = ["List", "Detail", "Create", "Edit", "Empty", "Error"];

// GET /overview/command-centre returns a point-in-time snapshot, not a
// date-ranged query — there is no backend support yet for actually
// re-computing kpis for a past period, so this selector is informational
// only (documented in docs/LIGHT_THEME_MIGRATION_PLAN.md "Known gaps"
// rather than wired to a fake filter, per "do not invent it").
const PERIOD_OPTIONS = [{ value: "current", label: "Current" }];

function greeting(hour) {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function roleLabel(user) {
  if (!user) return "";
  if (user.role === "admin") return "Admin";
  return "Team member";
}

/** The Overview / Command Centre screen. Rendered through the app-wide
 * Layout like every other page, so the Header/LightAppShell above it is
 * shared, not re-rendered per-page. */
export default function CommandCentre() {
  const { user, tenant } = useAuth();
  const [uiState, setUiState] = useState("List");
  const [search, setSearch] = useState("");
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    return api
      .get("/overview/command-centre")
      .then((r) => {
        setOverview(r.data);
        setUpdatedAt(new Date());
      })
      .catch((err) => {
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          setError({ unauthorized: true });
        } else {
          setError({ unauthorized: false });
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const kpis = overview
    ? [
        { label: "Open pipeline", value: inr(overview.kpis.open_pipeline), sub: "Live open-stage quotes", to: "/pipeline" },
        { label: "Won this month", value: inr(overview.kpis.won_this_month.value),
          sub: `${overview.kpis.won_this_month.orders} order${overview.kpis.won_this_month.orders === 1 ? "" : "s"} this month`, to: "/sales" },
        { label: "Receivables", value: inr(overview.kpis.receivables), sub: "Outstanding across all sales", to: "/outstanding" },
        { label: "Projects live", value: String(overview.kpis.projects_live.count),
          sub: `${overview.kpis.projects_live.at_risk} at risk`, to: "/projects" },
        { label: "SLA breaches", value: String(overview.kpis.sla_breaches),
          sub: overview.kpis.sla_breaches > 0 ? "Today needs action" : "All clear", to: "/tasks" },
      ]
    : [];

  const pipelineBars = overview?.pipeline_by_unit || [];
  const pipelineMax = Math.max(...pipelineBars.map((b) => b.value), 1);
  const pendingApprovals = overview?.pending_approvals || [];
  const now = new Date();

  return (
    <div className="min-h-screen bg-[var(--color-bg)]" data-testid="command-centre-page">
      <div className="p-6 max-w-[1440px] mx-auto space-y-6">
        <PageHeader
          eyebrow="OVERVIEW / DA / INDEX"
          title={`${greeting(now.getHours())}, ${user?.name || "there"}`}
          subtitle={
            <>
              {roleLabel(user)} view of {tenant?.name || "your business"} — pipeline, readiness, and what you owe today.
            </>
          }
          actions={
            <>
              <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Search command centre" />
              <select
                aria-label="Period"
                value="current"
                onChange={() => {}}
                disabled
                title="Only the current snapshot is available today — no backend period filter yet"
                className="px-3 py-2 text-sm rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)]"
              >
                {PERIOD_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <SecondaryButton onClick={load} disabled={loading} aria-label="Refresh">
                <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
                {updatedAt ? `Updated ${updatedAt.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}` : "Refresh"}
              </SecondaryButton>
              <SecondaryButton>
                <Download size={14} /> Export
              </SecondaryButton>
              <button
                type="button"
                aria-label="Notifications, 4 unread"
                className="relative p-2 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)] transition-colors"
              >
                <Bell size={16} className="text-[var(--color-text)]" />
                <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-[var(--color-primary)] text-white text-[9px] font-bold flex items-center justify-center">
                  4
                </span>
              </button>
            </>
          }
        />

        {/* State debug pill bar */}
        <div className="flex items-center gap-1.5" data-testid="state-debug-pills">
          {STATES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setUiState(s)}
              className={`px-2.5 py-1 rounded-[var(--radius-sm)] text-[11px] font-mono font-semibold transition-colors ${
                uiState === s
                  ? "bg-[var(--color-primary)] text-white"
                  : "bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)]"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {error ? (
          <ErrorState
            title={error.unauthorized ? "You don't have access to this view" : "Couldn't load the command centre"}
            hint={error.unauthorized ? undefined : "The overview API didn't respond — check your connection and try again."}
            onRetry={error.unauthorized ? undefined : load}
          />
        ) : (
          <>
            {/* KPI cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {loading
                ? Array.from({ length: 5 }).map((_, i) => <MetricCard key={i} label="" loading />)
                : kpis.map((k) => <MetricCard key={k.label} {...k} />)}
            </div>

            {/* Split view */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <SectionCard
                className="lg:col-span-8"
                title="Pipeline by unit"
                subtitle="open quote value by division · current FY"
              >
                {!loading && pipelineBars.length === 0 ? (
                  <EmptyState title="No open pipeline right now." />
                ) : (
                  <div className="flex items-end gap-6 h-48" role="img" aria-label="Pipeline by unit bar chart">
                    {(loading ? Array.from({ length: 3 }) : pipelineBars).map((b, i) => (
                      <div key={b?.division || i} className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                        {!loading && <div className="text-xs font-mono font-semibold text-[var(--color-text)]">{b.value}</div>}
                        <div
                          className={`w-full rounded-t-[var(--radius-sm)] ${loading ? "bg-[var(--color-surface-muted)] animate-pulse" : ""}`}
                          style={loading ? { height: "30%" } : { height: `${(b.value / pipelineMax) * 100}%`, background: "var(--color-primary)" }}
                        />
                        <div className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-text-muted)] text-center">
                          {loading ? "" : b.division}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </SectionCard>

              <div className="lg:col-span-4 space-y-6">
                <SectionCard title="Go-live readiness">
                  <div className="space-y-3">
                    {READINESS.map((r) => (
                      <div key={r.label}>
                        <div className="flex items-center justify-between text-xs mb-1">
                          <span className="text-[var(--color-text-muted)]">{r.label}</span>
                          <span className="font-mono font-semibold text-[var(--color-text)]">{r.pct}%</span>
                        </div>
                        <div className="h-1.5 bg-[var(--color-surface-muted)] rounded-full overflow-hidden">
                          <div className="h-full bg-[var(--color-primary)] rounded-full" style={{ width: `${r.pct}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </SectionCard>

                <SectionCard title={`Today — ${roleLabel(user)} · ${tenant?.name || "Unit"} scope`}>
                  {loading ? (
                    <div className="h-14 rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] animate-pulse" />
                  ) : pendingApprovals.length === 0 ? (
                    <EmptyState title="No approvals pending." />
                  ) : (
                    <div className="space-y-2">
                      {pendingApprovals.map((p) => (
                        <div key={p.quote_no} className="flex items-start justify-between gap-3 p-3 rounded-[var(--radius-sm)] bg-[var(--color-danger)]/5 border border-[var(--color-danger)]/20">
                          <div className="text-xs text-[var(--color-text)]">
                            Approve <span className="font-mono font-semibold">{p.quote_no}</span> ({p.customer}) — {p.discount_pct}% discount above your limit
                          </div>
                          <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-[var(--color-primary)] text-white">GATE</span>
                        </div>
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
