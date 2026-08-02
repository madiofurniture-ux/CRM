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

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Division</th>
                  <th className="text-right font-semibold px-4 py-2.5">Leads</th>
                  <th className="text-right font-semibold px-4 py-2.5">Quotes</th>
                  <th className="text-right font-semibold px-4 py-2.5">Quote Value</th>
                  <th className="text-right font-semibold px-4 py-2.5">Sales</th>
                  <th className="text-right font-semibold px-4 py-2.5">Sale Value</th>
                  <th className="text-right font-semibold px-4 py-2.5">Collected</th>
                  <th className="text-right font-semibold px-4 py-2.5">Outstanding</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((d) => {
                  const r = D[d] || {};
                  const isTotal = d === "TOTAL";
                  return (
                    <tr key={d} className={`border-t border-[var(--border-light)] ${isTotal ? "font-semibold border-t-2 border-[var(--border)]" : ""}`}>
                      <td className="px-4 py-2.5">{ROW_ICON[d]} {d}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{r.leads || 0}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{r.quotes || 0}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-[var(--warn)]">{r.qval ? inrFull(r.qval) : "—"}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{r.won || 0}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-[var(--moss)]">{r.wval ? inrFull(r.wval) : "—"}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{r.collected ? inrFull(r.collected) : "—"}</td>
                      <td className={`px-4 py-2.5 text-right font-mono ${r.due > 0 ? "text-[var(--danger)]" : "text-[var(--ink-3)]"}`}>{r.due ? inrFull(r.due) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
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
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4">
      <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)]">{label}</div>
      <div className={`font-heading font-bold ${small ? "text-lg" : "text-2xl"} font-mono mt-1 ${color}`}>{value}</div>
    </div>
  );
}
