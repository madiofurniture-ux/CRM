import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { AlertTriangle, FileText, TrendingUp } from "lucide-react";

const BUCKET_COLORS = { "0-30": "#4A5D4E", "31-60": "#D48B30", "61-90": "#C85A32", "90+": "#B24040" };

export default function Outstanding() {
  const [data, setData] = useState(null);

  useEffect(() => { api.get("/outstanding").then((r) => setData(r.data)); }, []);

  const maxAging = Math.max(...(data?.aging || []).map((a) => a.value), 1);
  const today = new Date().toISOString().slice(0, 10);

  return (
    <>
      <Topbar title="Outstanding" subtitle="What's owed & what's still open" />
      <div className="p-4 md:p-6 space-y-6" data-testid="outstanding-page">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KpiCard label="Sales Outstanding" value={inrFull(data?.sales_outstanding)} accent="danger" icon={AlertTriangle} />
          <KpiCard label="Invoice Outstanding" value={inrFull(data?.invoice_outstanding)} accent="warn" icon={FileText} />
          <KpiCard label="Hot Pipeline" value={inrFull(data?.hot_pipeline)} accent="brand" icon={TrendingUp} />
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
          <div className="font-heading font-semibold text-[var(--ink)] mb-4">Aging on sales balances</div>
          <div className="grid grid-cols-4 gap-3">
            {(data?.aging || []).map((a) => (
              <div key={a.bucket} className="p-4 rounded-lg border border-[var(--border-light)] bg-[var(--surface-2)]" data-testid={`aging-${a.bucket}`}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-2 h-2 rounded-full" style={{ background: BUCKET_COLORS[a.bucket] }} />
                  <span className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)]">{a.bucket} days</span>
                </div>
                <div className="font-heading font-bold text-lg text-[var(--ink)] font-mono">{inrFull(a.value)}</div>
                <div className="h-1 mt-2 bg-white rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${(a.value / maxAging) * 100}%`, background: BUCKET_COLORS[a.bucket] }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[var(--border-light)] flex items-center justify-between">
              <div>
                <div className="font-heading font-semibold text-[var(--ink)]">Unpaid Sales</div>
                <div className="text-xs text-[var(--ink-3)]">{data?.outstanding_sales?.length || 0} sales pending payment</div>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[var(--surface-2)]">
                  <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                    <th className="text-left font-semibold px-4 py-2.5">Sale No</th>
                    <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                    <th className="text-left font-semibold px-4 py-2.5">Date</th>
                    <th className="text-right font-semibold px-4 py-2.5">Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.outstanding_sales || []).map((s) => (
                    <tr key={s.id} className="border-t border-[var(--border-light)]">
                      <td className="px-4 py-2.5 font-mono text-xs">{s.sale_no}</td>
                      <td className="px-4 py-2.5">{s.customer}</td>
                      <td className="px-4 py-2.5 text-[var(--ink-2)]">{fmtDate(s.date)}</td>
                      <td className="px-4 py-2.5 text-right font-mono font-semibold text-[var(--danger)]">{inrFull(s.balance)}</td>
                    </tr>
                  ))}
                  {(data?.outstanding_sales || []).length === 0 && <tr><td colSpan="4" className="text-center py-8 text-[var(--ink-3)]">All sales fully collected 🎉</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[var(--border-light)]">
              <div className="font-heading font-semibold text-[var(--ink)]">Hot Quotes (₹1L+)</div>
              <div className="text-xs text-[var(--ink-3)]">{data?.hot_quotes?.length || 0} in Quoted / Negotiation</div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[var(--surface-2)]">
                  <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                    <th className="text-left font-semibold px-4 py-2.5">Quote</th>
                    <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                    <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                    <th className="text-right font-semibold px-4 py-2.5">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.hot_quotes || []).map((q) => (
                    <tr key={q.id} className="border-t border-[var(--border-light)]">
                      <td className="px-4 py-2.5 font-mono text-xs">{q.quote_no}</td>
                      <td className="px-4 py-2.5">{q.customer}</td>
                      <td className="px-4 py-2.5"><StageBadge stage={q.stage} /></td>
                      <td className="px-4 py-2.5 text-right font-mono font-semibold">{inrFull(q.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="p-4 border-b border-[var(--border-light)]">
            <div className="font-heading font-semibold text-[var(--ink)]">Unpaid Invoices</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Invoice</th>
                  <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-right font-semibold px-4 py-2.5">Total</th>
                  <th className="text-right font-semibold px-4 py-2.5">Paid</th>
                  <th className="text-right font-semibold px-4 py-2.5">Balance</th>
                </tr>
              </thead>
              <tbody>
                {(data?.outstanding_invoices || []).map((i) => (
                  <tr key={i.id} className="border-t border-[var(--border-light)]">
                    <td className="px-4 py-2.5 font-mono text-xs">{i.invoice_no}</td>
                    <td className="px-4 py-2.5">{i.customer}</td>
                    <td className="px-4 py-2.5 text-[var(--ink-2)]">{fmtDate(i.date)}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{inrFull(i.total)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-[var(--moss)]">{inrFull(i.paid)}</td>
                    <td className="px-4 py-2.5 text-right font-mono font-semibold text-[var(--danger)]">{inrFull(i.balance)}</td>
                  </tr>
                ))}
                {(data?.outstanding_invoices || []).length === 0 && <tr><td colSpan="6" className="text-center py-8 text-[var(--ink-3)]">All invoices settled 🎉</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
