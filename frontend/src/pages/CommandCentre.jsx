import { useState } from "react";
import { Search, Download, Bell } from "lucide-react";
import Header from "@/components/Header";

const KPIS = [
  { label: "Open pipeline", value: "₹1.42 Cr", sub: "+8.4% vs last month" },
  { label: "Won this month", value: "₹38.6 L", sub: "+12% · 6 orders" },
  { label: "Receivables", value: "₹31.5 L", sub: "₹19.4 L over 60 days" },
  { label: "Projects live", value: "14", sub: "3 at risk" },
  { label: "SLA breaches", value: "5", sub: "Today needs action" },
];

const PIPELINE_BARS = [
  { label: "Design studio", value: 142, tone: "primary" },
  { label: "Factory", value: 96, tone: "primary" },
  { label: "Site teams", value: 44, tone: "primary" },
  { label: "Won FY", value: 118, tone: "muted" },
  { label: "Lost FY", value: 62, tone: "muted" },
  { label: "Stalled", value: 31, tone: "muted" },
];
const PIPELINE_MAX = Math.max(...PIPELINE_BARS.map((b) => b.value));

const READINESS = [
  { label: "Query isolation", pct: 92 },
  { label: "Audit trail instrumented", pct: 78 },
  { label: "Role matrix server-side", pct: 61 },
  { label: "Export controls & approval", pct: 84 },
  { label: "Tax pack integration (India)", pct: 67 },
  { label: "Install branding assets", pct: 20 },
];

const STATES = ["List", "Detail", "Create", "Edit", "Empty", "Error"];

/** Design-mockup screen for the "Baseplate" Command Centre shell — a
 * self-contained page with its own header, not wired into the app-wide
 * Layout/Sidebar every other route uses. */
export default function CommandCentre() {
  const [navTab, setNavTab] = useState("overview");
  const [uiState, setUiState] = useState("List");
  const [search, setSearch] = useState("");

  return (
    <div className="min-h-screen bg-[#F7F5F3]" data-testid="command-centre-page">
      <Header activeTab={navTab} onTabChange={setNavTab} />

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
          {KPIS.map((k) => (
            <div key={k.label} className="bg-white border border-[#E2E8F0] rounded-2xl p-4">
              <div className="text-[10px] font-mono uppercase tracking-widest text-[#94A3B8] mb-2">{k.label}</div>
              <div className="text-xl font-bold text-[#14161C]">{k.value}</div>
              <div className="text-xs text-[#64748B] mt-1">{k.sub}</div>
            </div>
          ))}
        </div>

        {/* Split view */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Pipeline by unit */}
          <div className="lg:col-span-8 bg-white border border-[#E2E8F0] rounded-2xl p-6">
            <div className="mb-6">
              <div className="font-semibold text-[#14161C]">Pipeline by unit</div>
              <div className="text-xs text-[#94A3B8]">value in ₹ lakh · current FY</div>
            </div>
            <div className="flex items-end gap-6 h-48" role="img" aria-label="Pipeline by unit bar chart">
              {PIPELINE_BARS.map((b) => (
                <div key={b.label} className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                  <div className="text-xs font-mono font-semibold text-[#14161C]">{b.value}</div>
                  <div
                    className="w-full rounded-t-md"
                    style={{
                      height: `${(b.value / PIPELINE_MAX) * 100}%`,
                      background: b.tone === "primary" ? "#EC3013" : "#FCA5A5",
                    }}
                  />
                  <div className="text-[10px] font-mono uppercase tracking-wider text-[#64748B] text-center">
                    {b.label}
                  </div>
                </div>
              ))}
            </div>
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
              <div className="flex items-start justify-between gap-3 p-3 rounded-lg bg-[#FEF2F2] border border-[#FCA5A5]/40">
                <div className="text-xs text-[#14161C]">
                  <span className="font-mono font-semibold">09:30</span> Approve QT-DW-0388 — 14% discount above your limit
                </div>
                <span className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded bg-[#EC3013] text-white">GATE</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
