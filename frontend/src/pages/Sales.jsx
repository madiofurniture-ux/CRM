import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import StageBadge from "@/components/StageBadge";
import WhatsAppButton from "@/components/WhatsAppButton";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { Link, useNavigate } from "react-router-dom";
import ColumnFilters from "@/components/ColumnFilters";
import useColumnFilters from "@/hooks/useColumnFilters";

const COLUMNS = [
  { key: "sale_no", label: "Sale no", type: "text" },
  { key: "customer", label: "Customer", type: "text" },
  { key: "date", label: "Date", type: "date" },
  { key: "division", label: "Division", type: "select" },
  { key: "by_user", label: "By", type: "select" },
  { key: "stage", label: "Stage", type: "select" },
  { key: "status", label: "Payment status", type: "select" },
  { key: "value", label: "Value", type: "number" },
  { key: "balance", label: "Balance", type: "number" },
  { key: "quote_ref", label: "Quotation", type: "text" },
];
import { toast } from "sonner";
import { FileText, IndianRupee } from "lucide-react";
import RecordPaymentModal from "@/components/RecordPaymentModal";
import { useAuth } from "@/context/AuthContext";
import { useTenantConfig } from "@/context/TenantConfigContext";

export default function Sales() {
  const cf = useColumnFilters("sales", COLUMNS);
  const applyColumns = cf.apply;
  const [rows, setRows] = useState([]);
  // ?q= pre-fills the search (the quote workspace links to its sale this way).
  const [search, setSearch] = useState(() => new URLSearchParams(window.location.search).get("q") || "");
  const [fDiv, setFDiv] = useState("All");
  const { divisions } = useTenantConfig();
  const { canAccess } = useAuth();
  const navigate = useNavigate();
  const [invoicing, setInvoicing] = useState("");
  const [paying, setPaying] = useState(null);     // sale taking a payment
  const canInvoice = canAccess("invoice-gen");
  // Customer payments are taken where balances are worked: Outstanding.
  const canPay = canAccess("outstanding");

  // One click: the server builds the tax invoice from the sale and its
  // quotation (or returns the one already raised).
  const raiseInvoice = async (s) => {
    if (invoicing) return;
    setInvoicing(s.id);
    try {
      const { data } = await api.post(`/invoices/from-sale/${s.id}`);
      toast.success(`Invoice ${data.invoice_no} ready`);
      navigate("/invoices");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't create the invoice");
    } finally { setInvoicing(""); }
  };

  // A sales order stores no phone of its own; the customer's number lives on
  // the quotation it came from (same lookup the backend uses for the
  // order-confirmed notification). Without quote access the button hides.
  const [phoneByQuote, setPhoneByQuote] = useState({});

  // Fresh after a payment: the server re-derives paid/balance on the sale.
  const load = () => api.get("/sales", { skipCache: true }).then((r) => setRows(r.data));
  useEffect(() => { load(); }, []);
  useEffect(() => {
    api.get("/quotes").then(({ data }) => {
      const m = {};
      data.forEach((q) => {
        if (!q.phone) return;
        if (q.id) m[`id:${q.id}`] = q.phone;
        if (q.quote_no) m[`no:${q.quote_no}`] = q.phone;
      });
      setPhoneByQuote(m);
    }).catch(() => setPhoneByQuote({}));
  }, []);
  const phoneOf = (s) => s.phone || phoneByQuote[`id:${s.quote_id}`] || phoneByQuote[`no:${s.quote_ref}`] || "";

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return applyColumns(rows.filter((r) =>
      (fDiv === "All" || r.division === fDiv) &&
      (!q || [r.customer, r.sale_no, r.quote_ref, r.phone].some((v) => String(v || "").toLowerCase().includes(q)))
    ));
  }, [rows, search, fDiv, applyColumns]);

  const totals = useMemo(() => ({
    value: filtered.reduce((a, b) => a + (b.value || 0), 0),
    paid: filtered.reduce((a, b) => a + (b.paid || 0), 0),
    balance: filtered.reduce((a, b) => a + (b.balance || 0), 0),
  }), [filtered]);

  return (
    <>
      <Topbar title="Sales Register" subtitle={`${filtered.length} sales · ${inrFull(totals.value)} · ₹${totals.balance.toLocaleString("en-IN")} outstanding`} />
      <div className="p-6" data-testid="sales-page">
        <div className="flex flex-wrap gap-2 mb-4">
          <input placeholder="Search…" value={search} onChange={(e) => setSearch(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm outline-none focus:border-[var(--brand)] w-72" data-testid="sales-search" />
          <select value={fDiv} onChange={(e) => setFDiv(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option>All</option>
            {divisions.map((d) => <option key={d.id} value={d.slug}>{d.slug}</option>)}
          </select>
          <ColumnFilters filters={cf} rows={rows} shown={filtered.length} testid="sales-filters" />
        </div>
        <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Sale No</th>
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                  <th className="text-left font-semibold px-4 py-2.5">Division</th>
                  <th className="text-left font-semibold px-4 py-2.5">By</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="text-right font-semibold px-4 py-2.5">Value</th>
                  <th className="text-right font-semibold px-4 py-2.5">Paid</th>
                  <th className="text-right font-semibold px-4 py-2.5">Balance</th>
                  <th className="relative px-2 py-2.5"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr key={s.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50">
                    <td className="px-4 py-3 font-mono text-xs">{s.sale_no}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(s.date)}</td>
                    <td className="px-4 py-3 font-medium">
                      {s.customer_id ? <Link to={`/customers/${s.customer_id}`} className="hover:text-[var(--brand)] hover:underline">{s.customer}</Link> : s.customer}
                      {s.project_id && <Link to={`/projects/${s.project_id}`} className="ml-2 text-[11px] font-normal text-[var(--brand)] hover:underline">Project</Link>}
                    </td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{s.division}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{s.by_user}</td>
                    <td className="px-4 py-3"><StageBadge stage={s.stage} /></td>
                    <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(s.value)}</td>
                    <td className="px-4 py-3 text-right font-mono text-[var(--moss)]">{inrFull(s.paid)}</td>
                    <td className={`px-4 py-3 text-right font-mono ${s.balance > 0 ? "text-[var(--danger)] font-semibold" : "text-[var(--ink-3)]"}`}>{inrFull(s.balance)}</td>
                    <td className="px-2 py-3">
                      <div className="flex items-center gap-1">
                      {canPay && s.balance > 0 && (
                        <button onClick={() => setPaying({ kind: "sale", record: s })}
                                className="p-1.5 rounded-md hover:bg-[var(--moss-soft)] text-[var(--moss)]"
                                title="Record payment" aria-label={`Record payment for ${s.sale_no}`}
                                data-testid={`sale-pay-${s.id}`}><IndianRupee size={14} /></button>
                      )}
                      {canInvoice && (
                        <button onClick={() => raiseInvoice(s)} disabled={invoicing === s.id}
                                className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)] disabled:opacity-50"
                                title="Create tax invoice" aria-label={`Create tax invoice for ${s.sale_no}`}
                                data-testid={`sale-invoice-${s.id}`}><FileText size={14} /></button>
                      )}
                      <WhatsAppButton phone={phoneOf(s)} context={s.balance > 0 ? "payment-reminder" : "follow-up"}
                                      customerName={s.customer} ref={s.sale_no} refType="sale" refId={s.id}
                                      testId={`sale-wa-${s.id}`} />
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan="10" className="text-center py-10 text-[var(--ink-3)]">No sales</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      {paying && <RecordPaymentModal target={paying} onClose={() => setPaying(null)} onSaved={load} />}
    </>
  );
}
