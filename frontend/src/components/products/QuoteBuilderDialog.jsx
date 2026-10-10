import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Copy, FileText, Loader2, MessageCircle, Minus, Plus, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { inrFull, todayIST } from "@/lib/format";
import { logWhatsAppClick } from "@/lib/whatsapp";
import { rateFromMrp } from "@/components/ProductPicker";
import ClientPicker, { clientLabel } from "./ClientPicker";
import ProductModal from "./ProductModal";
import useCatalogueMeta from "./useCatalogueMeta";
import { dimsOf, estimateMessage, waHref } from "./productText";

const MAX_QTY = 999;

/** Several products for one customer: quantities and the total, then an
 * estimate on WhatsApp and / or a quotation in the CRM. The quotation goes
 * through the quotation engine like any other (one per division, with its
 * terms and GST); it opens in the quotation workspace for discounts,
 * transport and the branded PDF. */
export default function QuoteBuilderDialog({ items, client: given, onClose, onClient }) {
  const { user, canDo } = useAuth();
  const canQuote = canDo("quotes", "create");
  const navigate = useNavigate();
  const meta = useCatalogueMeta();
  const [client, setClient] = useState(given || null);
  const [picking, setPicking] = useState(!given);
  const [lines, setLines] = useState(() => items.map((item) => ({ item, qty: 1 })));
  const [phone, setPhone] = useState(given?.phone || "");
  const [busy, setBusy] = useState(false);

  const live = lines.filter((l) => l.qty > 0);
  const total = live.reduce((t, l) => t + (Number(l.item.mrp) || 0) * l.qty, 0);
  const divisions = useMemo(() => [...new Set(live.map((l) => l.item.division || "Furniture"))], [live]);
  // One division's products carry its brand name; a mix is MADIO's estimate without one.
  const brand = divisions.length === 1 ? meta.brands?.[divisions[0]] || "" : "";
  const terms = live.map((l) => l.item.sale_terms).find(Boolean) || "";
  const message = estimateMessage({ client: client?.name, lines: live, brand, terms });

  const setQty = (sku, qty) => setLines((ls) => ls.map((l) => (l.item.sku === sku
    ? { ...l, qty: Math.max(0, Math.min(MAX_QTY, Math.round(Number(qty) || 0))) } : l)));
  const pick = (c) => { setClient(c); setPhone(c.phone || ""); setPicking(false); onClient?.(c); };

  const makeQuotation = async () => {
    if (!client) { toast.error("Pick who the quotation is for"); setPicking(true); return; }
    if (!live.length) { toast.error("Keep at least one product"); return; }
    setBusy(true);
    const made = [];
    try {
      for (const division of divisions) {
        const { data: q } = await api.post("/quotes", {
          quote_no: "", date: todayIST(), customer: client.name, customer_id: client.customer_id || "", project_id: "",
          reference: "", phone: client.phone || phone || "", division, by_user: user?.name || "", stage: "Quoted",
          value: 0, other: 0, bank: 0, mode: "Walk-in", remarks: "", line_items: [],
          lead_id: client.kind === "lead" ? client.id : "",
        });
        const taxPct = q.tax_pct ?? 18;
        for (const l of live.filter((x) => (x.item.division || "Furniture") === division)) {
          const pre = rateFromMrp(l.item.mrp, l.item.gst_pct ?? taxPct);
          await api.post("/quote-lines", {
            quote_id: q.id, version: q.version || 1, w: 0, h: 0, qty: l.qty, group: "",
            description: [l.item.name, dimsOf(l.item)].filter(Boolean).join(" · "),
            rate: pre, mrp: pre, sku: l.item.sku, unit: l.item.unit || "pcs", hsn: l.item.hsn || "", price_auto: true,
          });
        }
        made.push(q);
      }
      toast.success(made.length === 1 ? `Quotation ${made[0].quote_no} made` : `${made.length} quotations made (one per division)`);
      navigate(`/quotes/ws/${made[0].id}`);
    } catch (err) {
      toast.error(formatApiError(err?.response?.data?.detail) || "Couldn't make the quotation");
      if (made.length) navigate(`/quotes/ws/${made[0].id}`);
    } finally { setBusy(false); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(message); toast.success("Estimate copied"); }
    catch { toast.error("Couldn't copy"); }
  };

  return (
    <ProductModal title={`Quotation / estimate · ${live.length} product${live.length === 1 ? "" : "s"}`} onClose={onClose} testid="quote-builder" wide>
      <div className="p-5 grid grid-cols-1 lg:grid-cols-[1fr_22rem] gap-5">
        <div className="space-y-3 min-w-0">
          <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
            <table className="w-full text-sm">
              <thead className="bg-[var(--color-surface-muted)] text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
                <tr><th className="text-left px-3 py-2">Product</th><th className="text-right px-3 py-2">Price</th>
                  <th className="px-3 py-2">Qty</th><th className="text-right px-3 py-2">Amount</th><th /></tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.item.sku} className={`border-t border-[var(--color-border)] ${l.qty ? "" : "opacity-40"}`} data-testid={`qb-line-${l.item.sku}`}>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2 min-w-[12rem]">
                        <div className="w-12 h-12 shrink-0 rounded border border-[var(--color-border)] bg-white p-0.5">
                          {l.item.thumb ? <img src={l.item.thumb} alt="" className="w-full h-full object-contain" /> : null}
                        </div>
                        <div className="min-w-0">
                          <div className="font-medium leading-snug">{l.item.name}</div>
                          <div className="text-xs text-[var(--color-text-muted)]">
                            <span className="font-mono">{l.item.sku}</span>{dimsOf(l.item) ? ` · ${dimsOf(l.item)}` : ""}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">{l.item.mrp ? inrFull(l.item.mrp) : "—"}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center justify-center gap-1">
                        <button type="button" className="lx-icon-btn" onClick={() => setQty(l.item.sku, l.qty - 1)} aria-label="One less"><Minus size={13} /></button>
                        <input value={l.qty} onChange={(e) => setQty(l.item.sku, e.target.value)} inputMode="numeric" aria-label={`${l.item.sku} quantity`}
                               className="w-12 text-center px-1 py-1 rounded border border-[var(--color-border)] bg-[var(--color-surface)]" data-testid={`qb-qty-${l.item.sku}`} />
                        <button type="button" className="lx-icon-btn" onClick={() => setQty(l.item.sku, l.qty + 1)} aria-label="One more"><Plus size={13} /></button>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right font-medium whitespace-nowrap">{inrFull((Number(l.item.mrp) || 0) * l.qty)}</td>
                    <td className="px-2"><button type="button" className="lx-icon-btn text-[var(--color-danger)]" aria-label={`Remove ${l.item.sku}`}
                                                 onClick={() => setLines((ls) => ls.filter((x) => x.item.sku !== l.item.sku))}><Trash2 size={13} /></button></td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-[var(--color-border)] font-semibold">
                  <td className="px-3 py-2" colSpan={3}>Total <span className="font-normal text-xs text-[var(--color-text-muted)]">(prices include GST)</span></td>
                  <td className="px-3 py-2 text-right" data-testid="qb-total">{inrFull(total)}</td><td />
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="text-xs text-[var(--color-text-muted)]">
            Made to order. The quotation adds the division's terms and GST breakdown; discounts, transport and installation are set in its workspace.
            {divisions.length > 1 ? ` These products are from ${divisions.join(" and ")}: one quotation is made for each.` : ""}
          </p>
        </div>
        <div className="space-y-3">
          <div className="rounded-lg border border-[var(--color-border)] p-3 space-y-2">
            <div className="text-sm font-medium">For</div>
            {client && !picking ? (
              <div className="flex items-start gap-2 text-sm" data-testid="qb-client">
                <div className="flex-1 min-w-0"><div className="font-medium truncate">{clientLabel(client)}</div>
                  <div className="text-xs text-[var(--color-text-muted)]">{client.kind === "lead" ? "Lead" : "Walk-in visitor"}</div></div>
                <button type="button" className="text-xs text-[var(--color-primary)]" onClick={() => setPicking(true)}>Change</button>
              </div>
            ) : <ClientPicker onPick={pick} />}
            <label className="block text-sm space-y-1"><span className="font-medium">WhatsApp number</span>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" placeholder="Leave empty to pick the chat"
                     className="w-full px-2.5 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm" data-testid="qb-phone" /></label>
          </div>
          <details className="rounded-lg border border-[var(--color-border)] p-3 text-sm">
            <summary className="cursor-pointer font-medium">The WhatsApp estimate</summary>
            <pre className="mt-2 whitespace-pre-wrap text-xs font-sans text-[var(--color-text-muted)]" data-testid="qb-message">{message}</pre>
          </details>
          <div className="flex flex-col gap-2">
            <a href={live.length ? waHref(phone, message) : undefined} target="_blank" rel="noreferrer" aria-disabled={!live.length}
               onClick={() => logWhatsAppClick("estimate-shared", { to: phone, customerName: client?.name || "", refType: client?.kind || "",
                 refId: live.map((l) => l.item.sku).join(", ") })}
               className={`lx-btn inline-flex items-center justify-center gap-1 ${live.length ? "" : "pointer-events-none opacity-50"}`} data-testid="qb-whatsapp">
              <MessageCircle size={14} /> Send estimate on WhatsApp</a>
            <button type="button" className="lx-btn inline-flex items-center justify-center gap-1" onClick={copy}><Copy size={14} /> Copy estimate</button>
            {canQuote ? (
              <button type="button" className="lx-btn lx-btn-brand inline-flex items-center justify-center gap-1" onClick={makeQuotation}
                      disabled={busy || !live.length} data-testid="qb-make-quote">
                {busy ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />} Make quotation in the CRM</button>
            ) : (
              <p className="text-xs text-[var(--color-text-muted)]">A quotation in the CRM is made by someone who can create quotations; the shortlist on the lead keeps these products for them.</p>
            )}
          </div>
        </div>
      </div>
    </ProductModal>
  );
}
