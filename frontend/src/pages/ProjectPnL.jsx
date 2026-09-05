import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import StageBadge from "@/components/StageBadge";
import EmptyState from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import api from "@/lib/api";
import { inr, inrFull, marginTone } from "@/lib/format";
import { IndianRupee, Wallet, TrendingUp, AlertTriangle, Download, ChevronDown, ChevronRight, LineChart } from "lucide-react";

export default function ProjectPnL() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    setLoading(true);
    api.get("/reports/project-pnl").then(({ data }) => setData(data)).finally(() => setLoading(false));
  }, []);

  const exportCsv = async () => {
    const { data } = await api.get("/reports/project-pnl/export.csv", { skipCache: true, responseType: "blob" });
    const blob = new Blob([data], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `project_pnl_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const summary = data?.summary;
  const projects = data?.projects || [];

  return (
    <>
      <Topbar
        title="Project P&L"
        subtitle="Contract revenue vs. approved petty cash spend, by project"
        actions={
          <button onClick={exportCsv} title="Export CSV" className="p-2 rounded-lg hover:bg-[var(--surface-2)] text-[var(--ink-2)]" data-testid="pnl-export">
            <Download size={16} />
          </button>
        }
      />
      <div className="p-6 space-y-6 max-w-[1600px]" data-testid="project-pnl-page">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard label="Total Contract Revenue" value={inr(summary?.total_contract_revenue)} accent="brand" icon={IndianRupee} testid="pnl-kpi-revenue" />
          <KpiCard label="Total Field Cash Spent" value={inr(summary?.total_field_cash_spent)} accent="danger" icon={Wallet} testid="pnl-kpi-spent" />
          <KpiCard label="Aggregate Gross Margin" value={`${summary?.aggregate_margin_pct ?? 0}%`} accent="moss" icon={TrendingUp} testid="pnl-kpi-margin" />
          <KpiCard label="Pending Expense Exposure" value={inr(summary?.pending_exposure)} accent="warn" icon={AlertTriangle} testid="pnl-kpi-pending" />
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="w-8"></th>
                  <th className="text-left font-semibold px-4 py-2.5">Project / Deal</th>
                  <th className="text-right font-semibold px-4 py-2.5">Contract Value</th>
                  <th className="text-right font-semibold px-4 py-2.5">Approved Petty Cash</th>
                  <th className="text-right font-semibold px-4 py-2.5">Gross Profit</th>
                  <th className="text-center font-semibold px-4 py-2.5">Margin %</th>
                  <th className="text-right font-semibold px-4 py-2.5">Float Balance</th>
                  <th className="text-left font-semibold px-4 py-2.5">Status</th>
                </tr>
              </thead>
              <tbody>
                {loading && Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-t border-[var(--border-light)]">
                    <td className="px-2 py-3"></td>
                    <td className="px-4 py-3"><Skeleton className="h-4 w-32" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-4 w-20 ml-auto" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-4 w-20 ml-auto" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-4 w-20 ml-auto" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-6 w-14 mx-auto" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-4 w-20 ml-auto" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-6 w-16" /></td>
                  </tr>
                ))}
                {!loading && projects.map((p) => {
                  const tone = marginTone(p.margin_pct);
                  const isOpen = expanded === p.project_id;
                  return (
                    <>
                      <tr key={p.project_id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50 cursor-pointer" onClick={() => setExpanded(isOpen ? null : p.project_id)}>
                        <td className="px-2 py-3 text-[var(--ink-3)]">{isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
                        <td className="px-4 py-3 font-medium">
                          {p.customer}
                          <span className="ml-2 text-xs font-mono text-[var(--ink-3)]">{p.project_no}</span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono">{inrFull(p.contract_value)}</td>
                        <td className="px-4 py-3 text-right font-mono">{inrFull(p.approved_petty_cash)}</td>
                        <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(p.gross_profit)}</td>
                        <td className="px-4 py-3 text-center">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${tone.bg} ${tone.text}`} data-testid={`pnl-margin-${p.project_id}`}>
                            {p.margin_pct}%
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono">{inrFull(p.float_balance)}</td>
                        <td className="px-4 py-3"><StageBadge stage={p.stage} /></td>
                      </tr>
                      {isOpen && (
                        <tr className="border-t border-[var(--border-light)] bg-[var(--surface-2)]/30">
                          <td></td>
                          <td colSpan={7} className="px-4 py-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <div>
                                <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-2">Category Breakdown (Approved)</div>
                                {p.category_breakdown.length === 0 ? (
                                  <div className="text-xs text-[var(--ink-3)]">No approved expenses yet.</div>
                                ) : (
                                  <div className="space-y-1.5">
                                    {p.category_breakdown.map((c) => (
                                      <div key={c.category} className="flex justify-between text-xs">
                                        <span className="text-[var(--ink-2)]">{c.category}</span>
                                        <span className="font-mono font-semibold">{inrFull(c.amount)}</span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                              <div>
                                <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-2">Pending Approvals</div>
                                <div className="text-xs text-[var(--ink-2)]">
                                  {p.pending_petty_cash > 0
                                    ? <span className="font-mono font-semibold text-[var(--warn,#B45309)]">{inrFull(p.pending_petty_cash)} awaiting approval</span>
                                    : "None"}
                                </div>
                                <div className="text-xs text-[var(--ink-3)] mt-1">{p.wallet_count} wallet{p.wallet_count === 1 ? "" : "s"}</div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
                {!loading && projects.length === 0 && (
                  <tr><td colSpan={8}>
                    <EmptyState icon={LineChart} title="No project P&L data yet" hint="Link a Cashbook wallet to a project to start tracking margin." />
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
