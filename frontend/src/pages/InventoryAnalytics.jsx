import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import api from "@/lib/api";
import { inr, inrFull } from "@/lib/format";
import { Package, Boxes, TrendingUp, Warehouse } from "lucide-react";

export default function InventoryAnalytics() {
  const [data, setData] = useState(null);

  useEffect(() => { api.get("/analytics/inventory").then((r) => setData(r.data)); }, []);

  const Bar = ({ items, color = "var(--brand)" }) => {
    const max = Math.max(...items.map((x) => x.value), 1);
    return (
      <div className="space-y-2">
        {items.map((i) => (
          <div key={i.name}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-[var(--ink-2)] truncate pr-2">{i.name}</span>
              <span className="font-mono font-semibold text-[var(--ink)]">{inr(i.value)}</span>
            </div>
            <div className="h-1.5 bg-[var(--surface-2)] rounded-full overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${(i.value / max) * 100}%`, background: color }} />
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <>
      <Topbar title="Inventory Analytics" subtitle="Stock breakdown & insights" />
      <div className="p-6 space-y-6 max-w-[1600px]" data-testid="inv-analytics-page">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard label="Total Items" value={data?.total_items ?? 0} accent="brand" icon={Package} />
          <KpiCard label="Total Qty" value={data?.total_qty ?? 0} accent="moss" icon={Boxes} />
          <KpiCard label="MRP Value" value={inr(data?.total_mrp)} accent="neutral" icon={TrendingUp} />
          <KpiCard label="Cost Value" value={inr(data?.total_cost)} accent="warn" icon={Warehouse} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="font-heading font-semibold text-[var(--ink)] mb-4">By Category</div>
            <Bar items={data?.by_category || []} color="#C85A32" />
          </div>
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="font-heading font-semibold text-[var(--ink)] mb-4">By Vendor</div>
            <Bar items={data?.by_vendor || []} color="#4A5D4E" />
          </div>
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="font-heading font-semibold text-[var(--ink)] mb-4">By Location</div>
            <Bar items={data?.by_location || []} color="#D48B30" />
          </div>
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="p-5 border-b border-[var(--border-light)]">
            <div className="font-heading font-semibold text-[var(--ink)]">Top 10 Items by Value</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">SKU</th>
                  <th className="text-left font-semibold px-4 py-2.5">Name</th>
                  <th className="text-left font-semibold px-4 py-2.5">Vendor</th>
                  <th className="text-right font-semibold px-4 py-2.5">Qty</th>
                  <th className="text-right font-semibold px-4 py-2.5">MRP</th>
                  <th className="text-right font-semibold px-4 py-2.5">Total Value</th>
                </tr>
              </thead>
              <tbody>
                {(data?.top_items || []).map((i) => (
                  <tr key={i.id} className="border-t border-[var(--border-light)]">
                    <td className="px-4 py-3 font-mono text-xs">{i.sku}</td>
                    <td className="px-4 py-3 font-medium">{i.name}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{[i.vendor_code, i.vendor].filter(Boolean).join(" · ")}</td>
                    <td className="px-4 py-3 text-right font-mono">{i.qty}</td>
                    <td className="px-4 py-3 text-right font-mono">{inrFull(i.mrp)}</td>
                    <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull((i.mrp || 0) * (i.qty || 0))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
