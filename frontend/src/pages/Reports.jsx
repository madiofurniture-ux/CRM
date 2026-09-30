import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import FilterChips from "@/components/FilterChips";
import api from "@/lib/api";
import { inrFull } from "@/lib/format";
import { toast } from "sonner";
import { Copy } from "lucide-react";

const PERIODS = [
  { key: "thisweek", label: "This Week" },
  { key: "lastweek", label: "Last Week" },
  { key: "thismonth", label: "This Month" },
  { key: "lastmonth", label: "Last Month" },
  { key: "alltime", label: "All Time" },
];
const ROW_ICON = { Furniture: "🛋", MAP: "🎨", "D&W": "🚪", Other: "▫", TOTAL: "Σ" };
const ROWS = ["Furniture", "MAP", "D&W", "Other", "TOTAL"];

export default function Reports() {
  const [period, setPeriod] = useState("thisweek");
  const [data, setData] = useState(null);

  useEffect(() => { api.get(`/reports?period=${period}`).then((r) => setData(r.data)); }, [period]);

  const D = data?.divisions || {};
  const T = D.TOTAL || {};

  const copySummary = () => {
    const txt = data?.whatsapp || "";
    (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject())
      .then(() => toast.success("Summary copied — paste into WhatsApp"))
      .catch(() => window.prompt("Copy this summary:", txt));
  };

  const visibleRows = ROWS.filter((d) => {
    const r = D[d];
    return d === "TOTAL" || (r && (r.leads || r.quotes || r.won || r.collected || r.due));
  });

  return (
    <>
      <Topbar title="Weekly / Monthly Reports" subtitle={data?.label || "—"}
        actions={<button onClick={copySummary} className="btn-ghost"><Copy size={14} /> Copy for WhatsApp</button>} />
      <div className="p-6 space-y-6" data-testid="reports-page">
        <FilterChips views={PERIODS} active={period} onChange={setPeriod} />

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Kpi label="New Leads" value={T.leads || 0} />
          <Kpi label="Quotes Issued" value={`${T.quotes || 0} · ${inrFull(T.qval)}`} small />
          <Kpi label="Sales Won" value={`${T.won || 0} · ${inrFull(T.wval)}`} small accent="moss" />
          <Kpi label="Collected" value={inrFull(T.collected)} small accent="moss" />
        </div>

        {T.wval > 0 && (
          <div className="bg-blue-600 rounded-2xl p-5 text-white">
            <div className="text-[11px] uppercase tracking-widest font-semibold text-blue-100">Coach's Insight</div>
            <div className="text-lg font-heading font-bold mt-1">
              {T.won || 0} deal{T.won === 1 ? "" : "s"} won worth {inrFull(T.wval)} — {T.due > 0 ? `${inrFull(T.due)} still outstanding across divisions.` : "fully collected, nothing outstanding."}
            </div>
          </div>
        )}

        <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-5">
          <h2 className="font-heading font-bold text-[var(--ink)] tracking-tight mb-4">Pipeline Health</h2>
          <div className="space-y-4">
            {visibleRows.filter((d) => d !== "TOTAL").map((d) => {
              const r = D[d] || {};
              const pct = T.wval > 0 ? Math.round(((r.wval || 0) / T.wval) * 100) : 0;
              return (
                <div key={d}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="font-medium text-[var(--ink)]">{ROW_ICON[d]} {d}</span>
                    <span className="text-[var(--ink-2)]">{r.won || 0} won · {inrFull(r.wval)}{r.due > 0 && <span className="text-[var(--danger)]"> · {inrFull(r.due)} due</span>}</span>
                  </div>
                  <div className="h-2.5 rounded-full bg-[var(--surface-2)] overflow-hidden">
                    <div className="h-full bg-blue-600 rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="text-[11px] text-[var(--ink-3)]">
          Leads = intake in period · Quotes / Sales = dated in period · Collected = payments + paid on period sales · Outstanding = all-time open balances per division.
        </div>
      </div>
    </>
  );
}

function Kpi({ label, value, small, accent = "ink" }) {
  const color = { moss: "text-[var(--moss)]", ink: "text-[var(--ink)]" }[accent];
  return (
    <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-4">
      <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)]">{label}</div>
      <div className={`font-heading font-bold ${small ? "text-lg" : "text-2xl"} font-mono mt-1 ${color}`}>{value}</div>
    </div>
  );
}
