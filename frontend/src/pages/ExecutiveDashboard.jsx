import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import api, { formatApiError } from "@/lib/api";
import { inrFull } from "@/lib/format";
import { toast } from "sonner";
import { TrendingUp, IndianRupee, Target, Wallet, CheckCircle2 } from "lucide-react";

const STAGE_COLOR = {
  New: "bg-[var(--ink-3)]", Qualified: "bg-[var(--brand)]", Quoted: "bg-[var(--brand)]",
  Negotiation: "bg-[var(--warn)]", Won: "bg-[var(--moss)]", Lost: "bg-[var(--danger)]",
};

const STATUS_BADGE = {
  Draft: "bg-[var(--surface-2)] text-[var(--ink-2)]",
  "No Rule": "bg-[var(--surface-2)] text-[var(--ink-3)]",
  Approved: "bg-[var(--brand-soft)] text-[var(--brand)]",
  Paid: "bg-[var(--moss-soft,var(--brand-soft))] text-[var(--moss)]",
};

export default function ExecutiveDashboard() {
  const [pipeline, setPipeline] = useState(null);
  const [revenue, setRevenue] = useState(null);
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [commissions, setCommissions] = useState([]);
  const [approving, setApproving] = useState(null); // key of the row currently being approved
  const [overrides, setOverrides] = useState({}); // key -> { rate_pct, commission_amount } a manager edited before approving

  const loadOverview = () => {
    api.get("/analytics/pipeline").then(({ data }) => setPipeline(data)).catch(() => setPipeline(null));
    api.get("/analytics/revenue").then(({ data }) => setRevenue(data)).catch(() => setRevenue(null));
  };
  const loadCommissions = () => {
    api.get(`/analytics/commissions?period=${period}`).then(({ data }) => { setCommissions(data); setOverrides({}); }).catch(() => setCommissions([]));
  };

  useEffect(loadOverview, []);
  useEffect(loadCommissions, [period]); // eslint-disable-line

  const rowKey = (row) => `${row.payee}|${row.division}`;
  const editRate = (row, rate_pct) => {
    const commission_amount = Math.round((row.base_amount * (parseFloat(rate_pct) || 0)) / 100 + (row.flat_amount || 0));
    setOverrides((o) => ({ ...o, [rowKey(row)]: { rate_pct, commission_amount } }));
  };

  const approve = async (row) => {
    const key = rowKey(row);
    const final = { ...row, ...(overrides[key] || {}) };
    setApproving(key);
    try {
      await api.post("/analytics/commissions/approve", { ...final, period });
      toast.success(`Commission approved for ${row.payee}`);
      loadCommissions();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setApproving(null); }
  };

  const maxCount = Math.max(1, ...(pipeline?.funnel || []).map((s) => s.count));

  return (
    <>
      <Topbar title="Executive Analytics" subtitle="Pipeline, revenue, and sales-rep commissions" />
      <div className="p-6 space-y-6" data-testid="executive-dashboard-page">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard label="Win Rate" value={pipeline ? `${pipeline.win_rate}%` : "—"}
            hint={pipeline ? `${pipeline.won} of ${pipeline.total} quotes` : ""} icon={Target} testid="kpi-win-rate" />
          <KpiCard label="Collection Rate" value={revenue ? `${revenue.collection_rate}%` : "—"}
            hint={revenue ? `${inrFull(revenue.collected)} collected` : ""} icon={CheckCircle2} accent="moss" testid="kpi-collection-rate" />
          <KpiCard label="Revenue Pending" value={revenue ? inrFull(revenue.pending) : "—"}
            hint="Balance due across sales & invoices" icon={Wallet} accent="warn" testid="kpi-pending" />
          <KpiCard label="Revenue Total" value={revenue ? inrFull(revenue.total) : "—"}
            hint="Collected + pending" icon={IndianRupee} testid="kpi-total-revenue" />
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={16} className="text-[var(--brand)]" />
            <h3 className="font-heading font-semibold text-sm">Pipeline Funnel — Quote Stages</h3>
          </div>
          <div className="space-y-3">
            {(pipeline?.funnel || []).map((s) => (
              <div key={s.stage} data-testid={`funnel-stage-${s.stage}`}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-medium">{s.stage}</span>
                  <span className="text-[var(--ink-3)]">{s.count} quotes · {inrFull(s.value)} · {s.conversion_rate}% of pipeline</span>
                </div>
                <div className="h-2.5 rounded-full bg-[var(--surface-2)] overflow-hidden">
                  <div className={`h-full rounded-full ${STAGE_COLOR[s.stage] || "bg-[var(--brand)]"}`}
                    style={{ width: `${Math.max(3, (s.count / maxCount) * 100)}%` }} />
                </div>
              </div>
            ))}
            {!pipeline && <div className="text-sm text-[var(--ink-3)]">Loading…</div>}
          </div>
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-heading font-semibold text-sm">Commission Approval</h3>
            <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)}
              className="px-3 py-1.5 rounded-lg border border-[var(--border)] bg-white text-sm" />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="py-2 pr-3">Sales Rep</th>
                  <th className="py-2 px-2">Division</th>
                  <th className="py-2 px-2 text-right">Collected</th>
                  <th className="py-2 px-2 text-right">Rate</th>
                  <th className="py-2 px-2 text-right">Commission</th>
                  <th className="py-2 px-2">Status</th>
                  <th className="py-2 pl-2" />
                </tr>
              </thead>
              <tbody>
                {commissions.map((row) => {
                  const key = rowKey(row);
                  const editable = row.status === "Draft";
                  const rate = overrides[key]?.rate_pct ?? row.rate_pct;
                  const amount = overrides[key]?.commission_amount ?? row.commission_amount;
                  return (
                    <tr key={key} className="border-t border-[var(--border-light)]" data-testid={`commission-row-${key}`}>
                      <td className="py-2 pr-3 font-medium">{row.payee}</td>
                      <td className="py-2 px-2 text-[var(--ink-2)]">{row.division || "—"}</td>
                      <td className="py-2 px-2 text-right">{inrFull(row.base_amount)}</td>
                      <td className="py-2 px-2 text-right">
                        {editable ? (
                          <input type="number" step="0.1" value={rate} onChange={(e) => editRate(row, e.target.value)}
                            className="w-16 px-1.5 py-0.5 rounded border border-[var(--border)] text-right text-xs"
                            data-testid={`rate-input-${key}`} />
                        ) : `${rate}%`}
                        {row.flat_amount ? ` + ${inrFull(row.flat_amount)}` : editable ? "%" : ""}
                      </td>
                      <td className="py-2 px-2 text-right font-semibold">{inrFull(amount)}</td>
                      <td className="py-2 px-2">
                        <span className={`text-[11px] px-2 py-0.5 rounded-full ${STATUS_BADGE[row.status] || STATUS_BADGE.Draft}`}>{row.status}</span>
                      </td>
                      <td className="py-2 pl-2 text-right">
                        {editable && (
                          <button onClick={() => approve(row)} disabled={approving === key}
                            className="btn-primary !py-1 !px-2.5 text-xs disabled:opacity-60" data-testid={`approve-${key}`}>
                            {approving === key ? "Approving…" : "Approve"}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {commissions.length === 0 && (
                  <tr><td colSpan={7} className="py-6 text-center text-[var(--ink-3)]">No cleared payments in this period yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
