import { useEffect, useState } from "react";
import { Search, Download, Bell } from "lucide-react";
import api from "@/lib/api";
import { inr } from "@/lib/format";

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

/** The Baseplate Command Centre screen. Rendered through the app-wide
 * Layout like every other page, so the Header above it is shared, not
 * re-rendered per-page. */
export default function CommandCentre() {
  const [uiState, setUiState] = useState("List");
  const [search, setSearch] = useState("");
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/overview/command-centre")
      .then((r) => setOverview(r.data))
      .finally(() => setLoading(false));
  }, []);

  const kpis = overview
    ? [
        { label: "Open pipeline", value: inr(overview.kpis.open_pipeline), sub: "Live open-stage quotes" },
        { label: "Won this month", value: inr(overview.kpis.won_this_month.value),
          sub: `${overview.kpis.won_this_month.orders} order${overview.kpis.won_this_month.orders === 1 ? "" : "s"} this month` },
        { label: "Receivables", value: inr(overview.kpis.receivables), sub: "Outstanding across all sales" },
        { label: "Projects live", value: String(overview.kpis.projects_live.count),
          sub: `${overview.kpis.projects_live.at_risk} at risk` },
        { label: "SLA breaches", value: String(overview.kpis.sla_breaches),
          sub: overview.kpis.sla_breaches > 0 ? "Today needs action" : "All clear" },
      ]
    : [];

  const pipelineBars = overview?.pipeline_by_unit || [];
  const pipelineMax = Math.max(...pipelineBars.map((b) => b.value), 1);
  const pendingApprovals = overview?.pending_approvals || [];

  return (
    <div className="min-h-screen bg-[#F7F5F3]" data-testid="command-centre-page">
      <div className="p-6 max-w-[1440px] mx-auto space-y-6">
        {/* Title & action row */}
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-[#94A3B8] mb-1">
              OVERVIEW / DA / INDEX
            </div>
            <h1 className="text-2xl font-bold text-[#14161C]">Command centre</h1>
            <p className="text-sm text-[#64748B] mt-1 max-w-xl">
              Role-aware view of the unit in scope — pipeline, readiness, and what you owe today.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#94A3B8]" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search command centre"
                aria-label="Search command centre"
                className="pl-8 pr-3 py-2 text-sm rounded-lg border border-[#E2E8F0] bg-white outline-none focus:border-[#EC3013] w-56"
              />
            </div>
            <button
              type="button"
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-[#E2E8F0] bg-white text-sm font-medium text-[#14161C] hover:bg-[#F1F5F9] transition"
            >
              <Download size={14} /> Export
            </button>
            <button
              type="button"
              aria-label="Notifications, 4 unread"
              className="relative p-2 rounded-lg border border-[#E2E8F0] bg-white hover:bg-[#F1F5F9] transition"
            >
              <Bell size={16} className="text-[#14161C]" />
              <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-[#EC3013] text-white text-[9px] font-bold flex items-center justify-center">
                4
              </span>
            </button>
          </div>
        </div>

        {/* State debug pill bar */}
        <div className="flex items-center gap-1.5" data-testid="state-debug-pills">
          {STATES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setUiState(s)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-mono font-semibold transition ${
                uiState === s ? "bg-[#EC3013] text-white" : "bg-white border border-[#E2E8F0] text-[#64748B] hover:bg-[#F1F5F9]"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* KPI cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {loading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="bg-white border border-[#E2E8F0] rounded-2xl p-4 animate-pulse">
                <div className="h-2.5 w-20 bg-[#F1F5F9] rounded mb-3" />
                <div className="h-6 w-16 bg-[#F1F5F9] rounded mb-2" />
                <div className="h-2.5 w-24 bg-[#F1F5F9] rounded" />
              </div>
            ))
          ) : (
            kpis.map((k) => (
              <div key={k.label} className="bg-white border border-[#E2E8F0] rounded-2xl p-4" data-testid={`kpi-${k.label}`}>
                <div className="text-[10px] font-mono uppercase tracking-widest text-[#94A3B8] mb-2">{k.label}</div>
                <div className="text-xl font-bold text-[#14161C] font-mono tabular-nums">{k.value}</div>
                <div className="text-xs text-[#64748B] mt-1">{k.sub}</div>
              </div>
            ))
          )}
        </div>

        {/* Split view */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Pipeline by unit */}
          <div className="lg:col-span-8 bg-white border border-[#E2E8F0] rounded-2xl p-6">
            <div className="mb-6">
              <div className="font-semibold text-[#14161C]">Pipeline by unit</div>
              <div className="text-xs text-[#94A3B8]">open quote value by division · current FY</div>
            </div>
            {!loading && pipelineBars.length === 0 ? (
              <div className="h-48 flex items-center justify-center text-sm text-[#94A3B8]">
                No open pipeline right now.
              </div>
            ) : (
              <div className="flex items-end gap-6 h-48" role="img" aria-label="Pipeline by unit bar chart">
                {(loading ? Array.from({ length: 3 }) : pipelineBars).map((b, i) => (
                  <div key={b?.division || i} className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                    {!loading && <div className="text-xs font-mono font-semibold text-[#14161C]">{b.value}</div>}
                    <div
                      className={`w-full rounded-t-md ${loading ? "bg-[#F1F5F9] animate-pulse" : ""}`}
                      style={loading ? { height: "30%" } : { height: `${(b.value / pipelineMax) * 100}%`, background: "#EC3013" }}
                    />
                    <div className="text-[10px] font-mono uppercase tracking-wider text-[#64748B] text-center">
                      {loading ? "" : b.division}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Readiness + action feed */}
          <div className="lg:col-span-4 space-y-6">
            <div className="bg-white border border-[#E2E8F0] rounded-2xl p-6">
              <div className="font-semibold text-[#14161C] mb-4">Go-live readiness</div>
              <div className="space-y-3">
                {READINESS.map((r) => (
                  <div key={r.label}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-[#64748B]">{r.label}</span>
                      <span className="font-mono font-semibold text-[#14161C]">{r.pct}%</span>
                    </div>
                    <div className="h-1.5 bg-[#F1F5F9] rounded-full overflow-hidden">
                      <div className="h-full bg-[#EC3013] rounded-full" style={{ width: `${r.pct}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-white border border-[#E2E8F0] rounded-2xl p-6">
              <div className="font-semibold text-[#14161C] mb-4">Today — Division Head · Unit scope</div>
              <div className="space-y-2">
                {loading ? (
                  <div className="h-14 rounded-lg bg-[#F1F5F9] animate-pulse" />
                ) : pendingApprovals.length === 0 ? (
                  <div className="text-sm text-[#94A3B8] py-2">No approvals pending.</div>
                ) : (
                  pendingApprovals.map((p) => (
                    <div key={p.quote_no} className="flex items-start justify-between gap-3 p-3 rounded-lg bg-[#FEF2F2] border border-[#FCA5A5]/40">
                      <div className="text-xs text-[#14161C]">
                        Approve <span className="font-mono font-semibold">{p.quote_no}</span> ({p.customer}) — {p.discount_pct}% discount above your limit
                      </div>
                      <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-[#EC3013] text-white">GATE</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
