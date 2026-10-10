import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { FileText, Sofa, X } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { inrFull } from "@/lib/format";
import QuoteBuilderDialog from "./QuoteBuilderDialog";
import { dimsOf } from "./productText";

/** The products a lead or walk-in visitor liked in the showroom (added from
 * the Virtual Catalogue), with their pictures; a quotation or a WhatsApp
 * estimate is made from them, and "Browse catalogue" adds more for them. */
export default function ShortlistPanel({ kind, record, onChange }) {
  const navigate = useNavigate();
  const entries = useMemo(() => record?.shortlist || [], [record]);
  const [items, setItems] = useState({});
  const [quoting, setQuoting] = useState(false);
  const codes = entries.map((e) => e.sku).join(",");

  useEffect(() => {
    if (!codes) return;
    let live = true;
    api.get(`/virtual-items?skus=${encodeURIComponent(codes)}`, { skipCache: true })
      .then(({ data }) => live && setItems(Object.fromEntries((data || []).map((v) => [v.sku, v]))))
      .catch(() => {});
    return () => { live = false; };
  }, [codes]);

  const products = entries.map((e) => items[e.sku] || { sku: e.sku, name: e.name, mrp: e.price, division: e.division });
  const remove = async (sku) => {
    try {
      const { data } = await api.delete(`/shortlist/${kind}/${record.id}/${encodeURIComponent(sku)}`);
      onChange?.(data.shortlist || []);
    } catch (err) { toast.error(formatApiError(err?.response?.data?.detail) || "Couldn't take it off"); }
  };
  const client = { kind, id: record.id, name: record.name, phone: record.whatsapp || record.phone || "",
                   lead_id: record.lead_id || "", customer_id: record.customer_id || "" };

  return (
    <div className="rounded-lg border border-[var(--color-border)] p-3 space-y-2" data-testid="shortlist-panel">
      <div className="flex items-center gap-2">
        <Sofa size={15} className="text-[var(--color-primary)]" />
        <div className="text-sm font-medium flex-1">Shortlisted products{entries.length ? ` (${entries.length})` : ""}</div>
        <button type="button" className="text-xs text-[var(--color-primary)]" data-testid="shortlist-browse"
                onClick={() => navigate(`/virtual-catalogue?for=${kind}:${record.id}`)}>Browse catalogue</button>
      </div>
      {!entries.length ? (
        <p className="text-xs text-[var(--color-text-muted)]">Nothing yet. On the Virtual Catalogue, “+ Add” puts a product here.</p>
      ) : (
        <>
          <ul className="divide-y divide-[var(--color-border)]">
            {products.map((p) => (
              <li key={p.sku} className="flex items-center gap-2 py-1.5" data-testid={`shortlist-${p.sku}`}>
                <div className="w-10 h-10 shrink-0 rounded border border-[var(--color-border)] bg-white p-0.5">
                  {p.thumb ? <img src={p.thumb} alt="" className="w-full h-full object-contain" /> : null}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{p.name}</div>
                  <div className="text-xs text-[var(--color-text-muted)] truncate">
                    <span className="font-mono">{p.sku}</span>{dimsOf(p) ? ` · ${dimsOf(p)}` : ""}{p.mrp ? ` · ${inrFull(p.mrp)}` : ""}</div>
                </div>
                <button type="button" className="lx-icon-btn" aria-label={`Take ${p.sku} off`} onClick={() => remove(p.sku)}><X size={13} /></button>
              </li>
            ))}
          </ul>
          <button type="button" className="lx-btn lx-btn-brand w-full inline-flex items-center justify-center gap-1" onClick={() => setQuoting(true)}
                  data-testid="shortlist-quote"><FileText size={14} /> Quotation / WhatsApp estimate</button>
        </>
      )}
      {quoting && <QuoteBuilderDialog items={products} client={client} onClose={() => setQuoting(false)} />}
    </div>
  );
}
