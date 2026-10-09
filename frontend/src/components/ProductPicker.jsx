import { useEffect, useRef, useState } from "react";
import { Search, Package } from "lucide-react";
import api from "@/lib/api";
import { inrFull } from "@/lib/format";

/**
 * Search inventory by name, SKU or model and pick an item for a quotation or
 * invoice line. Shows live stock (available = on hand − reserved) and never
 * cost; Virtual Catalogue products (MV- codes) show as made to order.
 * `onPick(item)` gets the GET /inventory/lookup row.
 */
export default function ProductPicker({ onPick, placeholder = "Add from inventory…", testId = "product-picker", className = "" }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setLoading(true);
      api.get(`/inventory/lookup?q=${encodeURIComponent(q.trim())}&limit=12`, { skipCache: true })
        .then(({ data }) => setRows(Array.isArray(data) ? data : []))
        .catch(() => setRows([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(timer.current);
  }, [q, open]);

  const pick = (item) => {
    onPick(item);
    setQ("");
    setOpen(false);
  };

  return (
    <div className={`relative ${className}`} data-testid={testId}>
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[var(--border)] bg-white focus-within:border-[var(--brand)]">
        <Search size={13} className="text-[var(--ink-3)] shrink-0" />
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}
          placeholder={placeholder}
          aria-label={placeholder}
          className="w-full text-sm outline-none bg-transparent min-w-0"
          data-testid={`${testId}-input`}
        />
      </div>
      {open && (
        <ul role="listbox" className="absolute z-30 mt-1 w-full min-w-[18rem] max-h-72 overflow-auto rounded-lg border border-[var(--border)] bg-white shadow-lg">
          {loading && rows.length === 0 && <li className="px-3 py-2 text-xs text-[var(--ink-3)]">Searching…</li>}
          {!loading && rows.length === 0 && <li className="px-3 py-2 text-xs text-[var(--ink-3)]">No matching products</li>}
          {rows.map((r) => (
            <li key={r.sku} role="option" aria-selected="false">
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(r)}
                      className="w-full text-left px-3 py-2 hover:bg-[var(--surface-2)] flex items-start gap-2"
                      data-testid={`${testId}-opt-${r.sku}`}>
                <Package size={14} className="mt-0.5 text-[var(--ink-3)] shrink-0" />
                <span className="flex-1 min-w-0">
                  <span className="block text-sm font-medium truncate">{r.name}</span>
                  <span className="block text-[11px] text-[var(--ink-3)] font-mono truncate">
                    {r.sku}{r.model_no ? ` · ${r.model_no}` : ""}{r.mrp ? ` · MRP ${inrFull(r.mrp)}` : ""}
                  </span>
                </span>
                <StockBadge item={r} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function StockBadge({ item, qty = 0 }) {
  if (!item) return null;
  if (item.virtual) {
    // A Virtual Catalogue product: made to order by the vendor, never held in stock.
    return (
      <span title="Virtual Catalogue: made to order, not held in stock"
            className="shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[var(--surface-2)] text-[var(--brand)]">
        Made to order
      </span>
    );
  }
  const avail = Number(item.available ?? item.on_hand ?? 0);
  const short = qty > 0 ? avail < qty : avail <= 0;
  return (
    <span title={`On hand ${item.on_hand ?? "?"} · reserved ${item.reserved ?? 0}`}
          className={`shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded ${short
            ? "bg-[var(--danger-soft,#fee2e2)] text-[var(--danger,#b91c1c)]"
            : "bg-[var(--surface-2)] text-[var(--ink-2)]"}`}>
      {avail} avail.
    </span>
  );
}

/** Pre-GST rate from an MRP (Indian MRP includes GST). */
export function rateFromMrp(mrp, gstPct) {
  const m = Number(mrp) || 0;
  const g = Number(gstPct) || 0;
  return g > 0 ? Math.round((m / (1 + g / 100)) * 100) / 100 : m;
}
