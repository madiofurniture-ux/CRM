import { useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { inrFull } from "@/lib/format";
import { toast } from "sonner";
import EmptyState from "@/components/EmptyState";
import { HandCoins, Check } from "lucide-react";

const STATUS_TONE = {
  Draft: "bg-[var(--surface-2)] text-[var(--ink-2)]",
  "No Rule": "bg-[var(--surface-2)] text-[var(--ink-3)]",
  Earned: "bg-amber-100 text-amber-700",
  Approved: "bg-[var(--brand-soft)] text-[var(--brand)]",
  Paid: "bg-emerald-100 text-emerald-700",
};

export default function Incentives() {
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState("All");
  const [payeeFilter, setPayeeFilter] = useState("All");
  const [acting, setActing] = useState(null);

  const load = () => {
    setLoading(true);
    api.get("/analytics/commissions", { params: { period } }).then(({ data }) => setRows(data)).finally(() => setLoading(false));
  };
  useEffect(load, [period]); // eslint-disable-line

  const payees = useMemo(() => Array.from(new Set(rows.map((r) => r.payee))).sort(), [rows]);
  const filtered = useMemo(() => rows.filter((r) =>
    (typeFilter === "All" || (typeFilter === "Architect" ? r.payee_type === "architect" : r.payee_type !== "architect"))
    && (payeeFilter === "All" || r.payee === payeeFilter)
  ), [rows, typeFilter, payeeFilter]);

  const approve = async (row) => {
    setActing(row.id || row.payee);
    try {
      if (row.id) {
        await api.patch(`/commission-payouts/${row.id}/approve`, {});
      } else {
        await api.post("/analytics/commissions/approve", row);
      }
      toast.success("Payout approved");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setActing(null); }
  };

  return (
    <>
      <Topbar title="Incentives" subtitle="Sales rep and architect commission payouts" />
      <div className="p-6 space-y-4" data-testid="incentives-page">
        <div className="flex flex-wrap gap-2">
          <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)}
            className="px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" data-testid="incentives-period" />
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
            className="px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
            <option>All</option>
            <option>Sales Rep</option>
            <option>Architect</option>
          </select>
          <select value={payeeFilter} onChange={(e) => setPayeeFilter(e.target.value)}
            className="px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
            <option>All</option>
            {payees.map((p) => <option key={p}>{p}</option>)}
          </select>
        </div>

        <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Payee</th>
                  <th className="text-left font-semibold px-4 py-2.5">Type</th>
                  <th className="text-left font-semibold px-4 py-2.5">Division</th>
                  <th className="text-right font-semibold px-4 py-2.5">Base Amount</th>
                  <th className="text-right font-semibold px-4 py-2.5">Rate</th>
                  <th className="text-right font-semibold px-4 py-2.5">Commission</th>
                  <th className="text-left font-semibold px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {!loading && filtered.map((r, i) => (
                  <tr key={r.id || `${r.payee}-${i}`} className="border-t border-[var(--border-light)]">
                    <td className="px-4 py-3 font-medium">{r.payee}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{r.payee_type === "architect" ? "Architect" : "Sales Rep"}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{r.division || "—"}</td>
                    <td className="px-4 py-3 text-right font-mono">{inrFull(r.base_amount)}</td>
                    <td className="px-4 py-3 text-right font-mono text-[var(--ink-2)]">{r.rate_pct}%{r.flat_amount ? ` +${inrFull(r.flat_amount)}` : ""}</td>
                    <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(r.commission_amount)}</td>
                    <td className="px-4 py-3">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold uppercase ${STATUS_TONE[r.status] || STATUS_TONE.Draft}`}>{r.status}</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {(r.status === "Draft" || r.status === "Earned") && (
                        <button onClick={() => approve(r)} disabled={acting === (r.id || r.payee)}
                          className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md border border-[var(--border)] hover:bg-[var(--surface-hover)] disabled:opacity-60"
                          data-testid={`approve-payout-${r.id || r.payee}`}>
                          <Check size={12} /> Approve Payout
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {!loading && filtered.length === 0 && (
                  <tr><td colSpan={8}>
                    <EmptyState icon={HandCoins} title="No incentives for this period" hint="Payouts appear here once a deal is won or a commission rule matches a cleared payment." />
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
