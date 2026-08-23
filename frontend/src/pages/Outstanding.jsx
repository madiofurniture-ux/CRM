import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import StageBadge from "@/components/StageBadge";
import api, { formatApiError } from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { AlertTriangle, FileText, TrendingUp, X, IndianRupee } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const BUCKET_COLORS = { "0-30": "#4A5D4E", "31-60": "#D48B30", "61-90": "#C85A32", "90+": "#B24040" };
const MODES = ["Cash", "Bank", "UPI", "Cheque"];

export default function Outstanding() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [target, setTarget] = useState(null); // { kind: "sale"|"invoice", record }
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  // Skips the client cache: this report is computed server-side from sales/
  // invoices, so recording a payment (which only invalidates the "/payments"
  // cache entry) would otherwise leave stale totals on screen.
  const load = () => api.get("/outstanding", { skipCache: true }).then((r) => setData(r.data));
  useEffect(() => { load(); }, []);

  const maxAging = Math.max(...(data?.aging || []).map((a) => a.value), 1);

  const openRecordPayment = (kind, record) => {
    setTarget({ kind, record });
    setForm({
      date: new Date().toISOString().slice(0, 10),
      amount: record.balance || 0,
      mode: "Cash",
      remarks: "",
    });
  };

  const closeModal = () => { setTarget(null); setForm(null); };

  const submitPayment = async (e) => {
    e.preventDefault();
    if (saving || !target || !form) return;
    if (!(form.amount > 0)) {
      toast.error("Enter an amount greater than 0");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        date: form.date,
        division: target.record.division || "Furniture",
        direction: "In",
        amount: +form.amount,
        mode: form.mode,
        kind: +form.amount >= (target.record.balance || 0) ? "Final" : "Part",
        received_by: user?.name || "",
        phone: target.record.phone || "",
        remarks: form.remarks,
      };
      if (target.kind === "sale") payload.against_sale_id = target.record.id;
      else payload.against_invoice_id = target.record.id;

      await api.post("/payments", payload);
      toast.success("Payment recorded");
      closeModal();
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Failed to record payment");
    } finally {
      setSaving(false);
    }
  };

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
                    <th className="w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.outstanding_sales || []).map((s) => (
                    <tr key={s.id} className="border-t border-[var(--border-light)]">
                      <td className="px-4 py-2.5 font-mono text-xs">{s.sale_no}</td>
                      <td className="px-4 py-2.5">{s.customer}</td>
                      <td className="px-4 py-2.5 text-[var(--ink-2)]">{fmtDate(s.date)}</td>
                      <td className="px-4 py-2.5 text-right font-mono font-semibold text-[var(--danger)]">{inrFull(s.balance)}</td>
                      <td className="px-2 py-2.5 text-right">
                        <button
                          onClick={() => openRecordPayment("sale", s)}
                          className="p-1.5 rounded-md hover:bg-[var(--brand-light)] text-[var(--brand)]"
                          title="Record payment"
                          data-testid={`record-payment-sale-${s.id}`}
                        >
                          <IndianRupee size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {(data?.outstanding_sales || []).length === 0 && <tr><td colSpan="5" className="text-center py-8 text-[var(--ink-3)]">All sales fully collected 🎉</td></tr>}
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
                  <th className="w-10"></th>
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
                    <td className="px-2 py-2.5 text-right">
                      <button
                        onClick={() => openRecordPayment("invoice", i)}
                        className="p-1.5 rounded-md hover:bg-[var(--brand-light)] text-[var(--brand)]"
                        title="Record payment"
                        data-testid={`record-payment-invoice-${i.id}`}
                      >
                        <IndianRupee size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
                {(data?.outstanding_invoices || []).length === 0 && <tr><td colSpan="7" className="text-center py-8 text-[var(--ink-3)]">All invoices settled 🎉</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {target && form && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[var(--border)] w-full max-w-sm shadow-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-[var(--border)] flex items-center justify-between bg-[var(--surface-2)]">
              <div>
                <h3 className="font-heading font-bold text-base text-[var(--ink)]">Record Payment</h3>
                <p className="text-xs text-[var(--ink-3)]">
                  {target.kind === "sale" ? target.record.sale_no : target.record.invoice_no} · {target.record.customer}
                </p>
              </div>
              <button onClick={closeModal} className="p-1 rounded-lg text-[var(--ink-3)] hover:bg-white">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={submitPayment} className="p-6 space-y-4">
              <div className="text-xs text-[var(--ink-3)] bg-[var(--surface-2)] rounded-lg px-3 py-2">
                Balance due: <span className="font-mono font-semibold text-[var(--danger)]">{inrFull(target.record.balance)}</span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Amount Received (₹) *</label>
                <input
                  type="number"
                  required
                  min="0.01"
                  step="0.01"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)] font-mono"
                  data-testid="payment-amount"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={() => setForm({ ...form, amount: target.record.balance })}
                  className="mt-1 text-[11px] text-[var(--brand)] font-semibold hover:underline"
                >
                  Pay full balance ({inrFull(target.record.balance)})
                </button>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Date</label>
                  <input
                    type="date"
                    value={form.date}
                    onChange={(e) => setForm({ ...form, date: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Mode</label>
                  <select
                    value={form.mode}
                    onChange={(e) => setForm({ ...form, mode: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)] bg-white"
                  >
                    {MODES.map((m) => <option key={m}>{m}</option>)}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Remarks</label>
                <input
                  type="text"
                  placeholder="Optional note"
                  value={form.remarks}
                  onChange={(e) => setForm({ ...form, remarks: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button type="button" onClick={closeModal} className="px-4 py-2 text-xs font-semibold rounded-lg border border-[var(--border)] hover:bg-[var(--surface-2)] transition">
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-5 py-2 text-xs font-semibold rounded-lg bg-[var(--brand)] text-white hover:opacity-90 transition shadow-sm disabled:opacity-60"
                  data-testid="payment-save"
                >
                  {saving ? "Saving…" : "Record Payment"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
