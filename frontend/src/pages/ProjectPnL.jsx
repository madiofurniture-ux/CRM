import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import StageBadge from "@/components/StageBadge";
import EmptyState from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import api from "@/lib/api";
import { inr, inrFull, fmtDate, marginTone } from "@/lib/format";
import {
  IndianRupee, Wallet, TrendingUp, AlertTriangle, Download, ChevronDown, ChevronRight,
  LineChart, Plus, ExternalLink,
} from "lucide-react";

export default function ProjectPnL() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const [divisionFilter, setDivisionFilter] = useState("All");

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
  const allProjects = data?.projects || [];
  const projects = divisionFilter === "All" ? allProjects : allProjects.filter((p) => p.division === divisionFilter);
  const activeCount = projects.filter((p) => p.wallet_count > 0).length;

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
          <KpiCard label="Total Contract Revenue" value={inr(summary?.total_contract_revenue)}
            hint={`Across ${projects.length} project${projects.length === 1 ? "" : "s"}`}
            accent="brand" icon={IndianRupee} testid="pnl-kpi-revenue" />
          <KpiCard label="Total Field Cash Spent" value={inr(summary?.total_field_cash_spent)}
            hint={`${activeCount} with an active wallet`}
            accent="danger" icon={Wallet} testid="pnl-kpi-spent" />
          <KpiCard label="Aggregate Gross Margin" value={`${summary?.aggregate_margin_pct ?? 0}%`}
            hint="Revenue minus approved spend"
            accent="moss" icon={TrendingUp} testid="pnl-kpi-margin" />
          <KpiCard label="Pending Expense Exposure" value={inr(summary?.pending_exposure)}
            hint={`Unapproved: ${inrFull(summary?.pending_exposure)} pending review`}
            accent="warn" icon={AlertTriangle} testid="pnl-kpi-pending" />
        </div>

        <div className="flex justify-end">
          <select
            value={divisionFilter}
            onChange={(e) => setDivisionFilter(e.target.value)}
            className="px-3 py-2 text-sm rounded-xl bg-white border border-[var(--border)] outline-none focus:border-[var(--brand)]"
            data-testid="pnl-division-filter"
          >
            <option value="All">All Divisions</option>
            <option value="Furniture">Madio Furniture</option>
            <option value="MAP">MAP Paints</option>
            <option value="D&W">Madio Doors &amp; Windows</option>
          </select>
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
                  <th className="text-right font-semibold px-4 py-2.5">Incentives Provisioned</th>
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
                    <td className="px-4 py-3"><Skeleton className="h-4 w-20 ml-auto" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-6 w-14 mx-auto" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-4 w-20 ml-auto" /></td>
                    <td className="px-4 py-3"><Skeleton className="h-6 w-16" /></td>
                  </tr>
                ))}
                {!loading && projects.map((p) => {
                  const tone = marginTone(p.margin_pct);
                  const isOpen = expanded === p.project_id;
                  const firstWallet = p.wallet_ids?.[0];
                  const totalCategorySpend = p.category_breakdown.reduce((a, c) => a + c.amount, 0) || 1;
                  const burnPct = p.imprest_limit_total > 0
                    ? Math.min(100, Math.round((p.approved_petty_cash / p.imprest_limit_total) * 100)) : null;
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
                        <td className="px-4 py-3 text-right font-mono">
                          {inrFull(p.approved_incentives + p.pending_incentives)}
                          {p.pending_incentives > 0 && <div className="text-[10px] text-[var(--warn,#B45309)]">{inrFull(p.pending_incentives)} pending</div>}
                        </td>
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
                          <td colSpan={8} className="px-4 py-4">
                            {burnPct != null && (
                              <div className="mb-4">
                                <div className="flex justify-between text-[11px] text-[var(--ink-3)] mb-1">
                                  <span>Budget burn — {inrFull(p.approved_petty_cash)} of {inrFull(p.imprest_limit_total)}</span>
                                  <span>{burnPct}%</span>
                                </div>
                                <div className="h-1.5 rounded-full bg-[var(--surface-2)] overflow-hidden">
                                  <div className={`h-full ${burnPct >= 90 ? "bg-[var(--danger)]" : "bg-[var(--brand)]"}`} style={{ width: `${burnPct}%` }} />
                                </div>
                              </div>
                            )}
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                              <div>
                                <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-2">Cashbook Spend</div>
                                {p.category_breakdown.length === 0 ? (
                                  <div className="text-xs text-[var(--ink-3)]">No approved expenses yet.</div>
                                ) : (
                                  <div className="space-y-2 mb-3">
                                    {p.category_breakdown.map((c) => {
                                      const pct = Math.round((c.amount / totalCategorySpend) * 100);
                                      return (
                                        <div key={c.category}>
                                          <div className="flex justify-between text-xs mb-0.5">
                                            <span className="text-[var(--ink-2)]">{c.category}</span>
                                            <span className="font-mono font-semibold">{inrFull(c.amount)} · {pct}%</span>
                                          </div>
                                          <div className="h-1.5 rounded-full bg-[var(--surface-2)] overflow-hidden">
                                            <div className="h-full bg-[var(--brand)]" style={{ width: `${pct}%` }} />
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                )}
                                {p.pending_petty_cash > 0 && (
                                  <div className="text-xs mb-3 text-[var(--warn,#B45309)] font-medium">
                                    {inrFull(p.pending_petty_cash)} awaiting approval
                                  </div>
                                )}
                                {p.recent_entries.length > 0 && (
                                  <div className="space-y-1.5 max-h-40 overflow-y-auto border-t border-[var(--border-light)] pt-2">
                                    {p.recent_entries.map((e, i) => (
                                      <div key={i} className="flex justify-between text-xs">
                                        <span className="text-[var(--ink-2)] truncate pr-2">
                                          {fmtDate(e.date)} · {e.payee || "—"} · {e.category || e.type}
                                        </span>
                                        <span className={`font-mono font-semibold shrink-0 ${e.type === "CASH_IN" ? "text-[var(--moss)]" : "text-[var(--ink)]"}`}>
                                          {e.type === "CASH_IN" ? "+" : "-"}{inrFull(e.amount)}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                              <div>
                                <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-2">Commission & Incentives</div>
                                {p.incentive_payouts.length === 0 ? (
                                  <div className="text-xs text-[var(--ink-3)]">No incentives provisioned yet.</div>
                                ) : (
                                  <div className="space-y-1.5">
                                    {p.incentive_payouts.map((pay) => (
                                      <div key={pay.id} className="flex items-center justify-between text-xs">
                                        <span className="text-[var(--ink-2)] truncate pr-2">
                                          {pay.payee} <span className="text-[10px] text-[var(--ink-3)] uppercase">({pay.payee_type === "architect" ? "Architect" : "Sales Rep"})</span>
                                        </span>
                                        <span className="flex items-center gap-1.5 shrink-0">
                                          <span className="font-mono font-semibold">{inrFull(pay.amount)}</span>
                                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold uppercase ${
                                            pay.status === "Earned" ? "bg-amber-100 text-amber-700"
                                              : pay.status === "Approved" ? "bg-[var(--brand-soft)] text-[var(--brand)]"
                                              : "bg-emerald-100 text-emerald-700"}`}>{pay.status}</span>
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                              <div className="space-y-2">
                                <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-2">Active Wallets & Quick Actions</div>
                                <button
                                  disabled={!firstWallet}
                                  onClick={() => navigate(`/cashbook?book=${firstWallet}&openExpense=1`)}
                                  className="w-full flex items-center justify-center gap-1.5 text-xs py-1.5 rounded-lg border border-[var(--border)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
                                  data-testid={`pnl-log-expense-${p.project_id}`}
                                >
                                  <Plus size={12} /> Log Site Expense
                                </button>
                                <button
                                  disabled={!firstWallet}
                                  onClick={() => navigate(`/cashbook?book=${firstWallet}&openTopUp=1`)}
                                  className="w-full flex items-center justify-center gap-1.5 text-xs py-1.5 rounded-lg border border-[var(--border)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
                                  data-testid={`pnl-top-up-${p.project_id}`}
                                >
                                  <Plus size={12} /> Top Up Float
                                </button>
                                <button
                                  disabled={!firstWallet}
                                  onClick={() => navigate(`/cashbook?book=${firstWallet}`)}
                                  className="w-full flex items-center justify-center gap-1.5 text-xs py-1.5 rounded-lg border border-[var(--border)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
                                  data-testid={`pnl-view-wallet-${p.project_id}`}
                                >
                                  <ExternalLink size={12} /> View Linked Wallet
                                </button>
                                <div className="text-[11px] text-[var(--ink-3)]">{p.wallet_count} wallet{p.wallet_count === 1 ? "" : "s"}</div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
                {!loading && projects.length === 0 && (
                  <tr><td colSpan={9}>
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
