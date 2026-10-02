import { useCallback, useEffect, useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { toast } from "sonner";

/** Inventory: where CRM stock (the stock of record) differs from Tally's
 * closing stock, with a one-click audited adjustment to Tally's figure. */
export default function TallyStockCompare({ onChanged }) {
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    api.get("/inventory/tally-compare", { skipCache: true }).then(({ data }) => setRows(data || [])).catch(() => setRows([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const accept = async (r) => {
    if (!window.confirm(`Set CRM stock of ${r.name} from ${r.qty} to Tally's ${r.tally_qty}? This books a stock adjustment.`)) return;
    setBusy(r.sku);
    try {
      await api.post(`/inventory/${encodeURIComponent(r.sku)}/accept-tally-qty`);
      toast.success(`${r.name}: stock set to ${r.tally_qty}`);
      load();
      onChanged?.();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't adjust"); }
    finally { setBusy(""); }
  };

  if (!rows || rows.length === 0) return null;
  return (
    <div className="mb-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)]" data-testid="tally-stock-compare">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
              className="w-full flex items-center justify-between px-4 py-3 text-sm">
        <span className="inline-flex items-center gap-2 font-medium">
          <ArrowLeftRight size={14} /> {rows.length} item{rows.length === 1 ? "" : "s"} differ from Tally's stock
        </span>
        <span className="text-xs text-[var(--brand)]">{open ? "Hide" : "Review"}</span>
      </button>
      {open && (
        <div className="overflow-x-auto border-t border-[var(--border-light)]">
          <table className="w-full text-sm">
            <thead className="bg-[var(--surface-2)] text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
              <tr><th className="text-left px-4 py-2">Item</th><th className="text-right px-4 py-2">CRM</th>
                <th className="text-right px-4 py-2">Tally</th><th className="text-right px-4 py-2">Difference</th>
                <th className="text-left px-4 py-2">From Tally</th><th /></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.sku} className="border-t border-[var(--border-light)]">
                  <td className="px-4 py-2"><div className="font-medium">{r.name}</div><div className="text-[10px] font-mono text-[var(--ink-3)]">{r.sku}</div></td>
                  <td className="px-4 py-2 text-right font-mono">{r.qty}</td>
                  <td className="px-4 py-2 text-right font-mono">{r.tally_qty}</td>
                  <td className={`px-4 py-2 text-right font-mono font-semibold ${r.difference < 0 ? "text-[var(--danger)]" : ""}`}>{r.difference > 0 ? "+" : ""}{r.difference}</td>
                  <td className="px-4 py-2 text-xs text-[var(--ink-3)]">{fmtDateTime(r.tally_synced_at)}</td>
                  <td className="px-4 py-2 text-right">
                    <button type="button" className="btn-ghost text-xs disabled:opacity-60" disabled={busy === r.sku}
                            onClick={() => accept(r)} data-testid={`tally-accept-${r.sku}`}>Accept Tally figure</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
