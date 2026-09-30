import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import EmptyState from "@/components/EmptyState";
import { usePrivacyMode } from "@/context/PrivacyModeContext";
import api, { formatApiError } from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { Wallet, Landmark, Receipt, X, Download } from "lucide-react";

const MODES = ["All", "BANK_TRANSFER", "OTHER", "SPLIT"];
const MODE_LABEL = { All: "All", BANK_TRANSFER: "Bank Transfer", OTHER: "Other", SPLIT: "Split" };
const STATUS_TONE = {
  RECORDED: "bg-[var(--surface-2)] text-[var(--ink-2)]",
  VERIFIED: "bg-blue-100 text-blue-700",
  RECONCILED: "bg-emerald-100 text-emerald-700",
};

const emptyForm = {
  project_id: "", payment_mode: "SPLIT", receipt_date: new Date().toISOString().slice(0, 10),
  bt_taxable: "", gst_rate: "18", utr_reference: "", other_amount: "", wallet_id: "",
};

export default function Payments() {
  const { isOtherHidden, requestUnlock } = usePrivacyMode();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modeFilter, setModeFilter] = useState("All");
  const [show, setShow] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    api.get("/finance/payments", { params: { mask_other: isOtherHidden } })
      .then(({ data }) => setRows(data)).finally(() => setLoading(false));
  };
  useEffect(load, [isOtherHidden]); // eslint-disable-line

  const taxable = parseFloat(form.bt_taxable) || 0;
  const rate = parseFloat(form.gst_rate) || 0;
  const gstAmount = Math.round(taxable * rate) / 100;
  const btTotal = taxable + gstAmount;
  const otherAmount = parseFloat(form.other_amount) || 0;
  const grandTotal = btTotal + otherAmount;

  const totals = rows.reduce((acc, r) => {
    acc.total += r.total_collected || 0;
    acc.bt += r.bank_transfer_component?.total_bt_amount || 0;
    acc.gst += r.bank_transfer_component?.gst_amount || 0;
    acc.other += r.other_component?.other_amount || 0;
    return acc;
  }, { total: 0, bt: 0, gst: 0, other: 0 });

  const visible = modeFilter === "All" ? rows : rows.filter((r) => r.payment_mode === modeFilter);

  const save = async () => {
    if (saving) return;
    if (taxable <= 0 && otherAmount <= 0) { toast.error("Enter a bank transfer or Other amount"); return; }
    setSaving(true);
    try {
      const payload = {
        project_id: form.project_id, payment_mode: form.payment_mode, receipt_date: form.receipt_date,
        bank_transfer_component: taxable > 0 ? {
          taxable_amount: taxable, gst_rate: rate, utr_reference: form.utr_reference,
        } : null,
        other_component: otherAmount > 0 ? { other_amount: otherAmount, wallet_id: form.wallet_id } : null,
      };
      await api.post("/finance/payments", payload);
      toast.success("Payment recorded");
      setShow(false);
      setForm(emptyForm);
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const downloadReceipt = (r) => {
    const lines = [
      `MADIO CRM — Payment Receipt`,
      `Date: ${r.receipt_date}`,
      `Mode: ${MODE_LABEL[r.payment_mode] || r.payment_mode}`,
      r.bank_transfer_component ? `Bank Transfer: Taxable ${inrFull(r.bank_transfer_component.taxable_amount)} + GST ${inrFull(r.bank_transfer_component.gst_amount)} = ${inrFull(r.bank_transfer_component.total_bt_amount)}` : null,
      r.bank_transfer_component?.tax_invoice_number ? `Tax Invoice: ${r.bank_transfer_component.tax_invoice_number}` : null,
      r.other_component ? `Other (Direct Settlement): ${inrFull(r.other_component.other_amount)}` : null,
      // Masked, the server restates total_collected as bank-transfer only.
      // Say so on the receipt — an unlabelled smaller total would read as
      // the full amount collected and understate the payment.
      isOtherHidden ? `Other (Direct Settlement): masked — unlock to include` : null,
      isOtherHidden
        ? `Total Collected (Bank Transfer only): ${inrFull(r.total_collected)}`
        : `Total Collected: ${inrFull(r.total_collected)}`,
      `Status: ${r.status}`,
    ].filter(Boolean).join("\n");
    const blob = new Blob([lines], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `receipt_${r.id}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <Topbar title="Payments & Tax Invoices" subtitle="Split Other / bank-transfer settlements" onAdd={() => setShow(true)} addLabel="Record Payment" />
      <div className="p-6 space-y-6" data-testid="payments-page">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            icon={Receipt}
            label={isOtherHidden ? "Collections (Bank Transfer only)" : "Total Collections"}
            value={inrFull(totals.total)}
            hint={isOtherHidden ? (
              <>Other excluded — <button onClick={requestUnlock} className="text-blue-600 underline">unlock</button> for the full total</>
            ) : null}
          />
          <KpiCard icon={Landmark} label="Bank Transfer (+GST)" value={inrFull(totals.bt)} hint={`GST: ${inrFull(totals.gst)}`} />
          <KpiCard
            icon={Wallet} label="Other Collections"
            value={isOtherHidden ? "••••••" : inrFull(totals.other)}
            hint={isOtherHidden ? <button onClick={requestUnlock} className="text-blue-600 underline">Unlock</button> : null}
          />
          <KpiCard icon={Receipt} label="Pending GST Liability" value={inrFull(totals.gst)} accent="warn" />
        </div>

        <div className="flex flex-wrap gap-2">
          {MODES.map((m) => (
            <button key={m} onClick={() => setModeFilter(m)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium border ${modeFilter === m ? "bg-blue-600 text-white border-blue-600" : "border-[var(--border)] text-[var(--ink-2)]"}`}>
              {MODE_LABEL[m]}
            </button>
          ))}
        </div>

        <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Mode</th>
                  <th className="text-right font-semibold px-4 py-2.5">Bank Transfer</th>
                  <th className="text-right font-semibold px-4 py-2.5">GST</th>
                  <th className="text-right font-semibold px-4 py-2.5">Other</th>
                  <th className="text-right font-semibold px-4 py-2.5">{isOtherHidden ? "Total (BT only)" : "Total"}</th>
                  <th className="text-left font-semibold px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {!loading && visible.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--border-light)]" data-testid={`payment-${r.id}`}>
                    <td className="px-4 py-2.5">{fmtDate(r.receipt_date)}</td>
                    <td className="px-4 py-2.5">{MODE_LABEL[r.payment_mode] || r.payment_mode}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{r.bank_transfer_component ? inrFull(r.bank_transfer_component.total_bt_amount) : "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{r.bank_transfer_component ? inrFull(r.bank_transfer_component.gst_amount) : "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono">
                      {r.other_component === null ? (isOtherHidden ? "••••••" : "—") : r.other_component ? inrFull(r.other_component.other_amount) : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono font-semibold">{inrFull(r.total_collected)}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${STATUS_TONE[r.status] || STATUS_TONE.RECORDED}`}>{r.status}</span>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button onClick={() => downloadReceipt(r)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)]" aria-label="Download receipt">
                        <Download size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && visible.length === 0 && (
              <EmptyState icon={Receipt} title="No payments recorded" hint="Record a split Other/bank-transfer payment to get started." />
            )}
          </div>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)} onKeyDown={(e) => e.key === "Escape" && setShow(false)}>
          <div role="dialog" aria-modal="true" aria-labelledby="payment-modal-title" className="bg-white rounded-2xl border border-[var(--border)] w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 id="payment-modal-title" className="font-heading font-semibold text-lg">Record Split Payment</h3>
              <button onClick={() => setShow(false)} aria-label="Close"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label htmlFor="pay-project" className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Project ID</label>
                <input id="pay-project" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--border)] text-sm" data-testid="pay-project-id" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="border border-blue-100 rounded-xl p-3">
                  <div className="text-xs font-semibold text-blue-700 mb-2">Bank Transfer + GST</div>
                  <label htmlFor="pay-taxable" className="text-[10px] uppercase text-[var(--ink-3)] block mb-1">Taxable Amount</label>
                  <input id="pay-taxable" type="number" min="0" value={form.bt_taxable} onChange={(e) => setForm({ ...form, bt_taxable: e.target.value })}
                    className="w-full px-2 py-1.5 rounded-lg border border-[var(--border)] text-sm mb-2" data-testid="pay-taxable" />
                  <label htmlFor="pay-gst-rate" className="text-[10px] uppercase text-[var(--ink-3)] block mb-1">GST Rate %</label>
                  <input id="pay-gst-rate" type="number" min="0" value={form.gst_rate} onChange={(e) => setForm({ ...form, gst_rate: e.target.value })}
                    className="w-full px-2 py-1.5 rounded-lg border border-[var(--border)] text-sm mb-2" />
                  <label htmlFor="pay-utr" className="text-[10px] uppercase text-[var(--ink-3)] block mb-1">UTR Reference</label>
                  <input id="pay-utr" value={form.utr_reference} onChange={(e) => setForm({ ...form, utr_reference: e.target.value })}
                    className="w-full px-2 py-1.5 rounded-lg border border-[var(--border)] text-sm" />
                </div>
                <div className="border border-[var(--border)] rounded-xl p-3">
                  <div className="text-xs font-semibold text-[var(--ink-2)] mb-2">Other (Direct Settlement)</div>
                  <label htmlFor="pay-other" className="text-[10px] uppercase text-[var(--ink-3)] block mb-1">Other Amount</label>
                  <input id="pay-other" type="number" min="0" value={form.other_amount} onChange={(e) => setForm({ ...form, other_amount: e.target.value })}
                    className="w-full px-2 py-1.5 rounded-lg border border-[var(--border)] text-sm mb-2" data-testid="pay-other" />
                  <label htmlFor="pay-wallet" className="text-[10px] uppercase text-[var(--ink-3)] block mb-1">Credit to Wallet (optional)</label>
                  <input id="pay-wallet" value={form.wallet_id} onChange={(e) => setForm({ ...form, wallet_id: e.target.value })}
                    placeholder="Cashbook wallet id"
                    className="w-full px-2 py-1.5 rounded-lg border border-[var(--border)] text-sm" />
                </div>
              </div>

              <div className="bg-[var(--surface-2)] rounded-xl p-3 text-sm space-y-1" data-testid="pay-breakdown">
                <div className="flex justify-between"><span className="text-[var(--ink-3)]">Taxable Value</span><span className="font-mono">{inrFull(taxable)}</span></div>
                <div className="flex justify-between"><span className="text-[var(--ink-3)]">GST ({rate}%)</span><span className="font-mono">{inrFull(gstAmount)}</span></div>
                <div className="flex justify-between"><span className="text-[var(--ink-3)]">Bank Transfer Total</span><span className="font-mono">{inrFull(btTotal)}</span></div>
                <div className="flex justify-between"><span className="text-[var(--ink-3)]">Other Total</span><span className="font-mono">{inrFull(otherAmount)}</span></div>
                <div className="flex justify-between font-semibold pt-1 border-t border-[var(--border-light)]"><span>Grand Total</span><span className="font-mono">{inrFull(grandTotal)}</span></div>
              </div>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="pay-save">
                {saving ? "Saving…" : "Record Payment"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function KpiCard({ icon: Icon, label, value, hint, accent = "ink" }) {
  const color = { ink: "text-[var(--ink)]", warn: "text-[var(--warn,#B45309)]" }[accent];
  return (
    <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-4">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)]">
        <Icon size={12} /> {label}
      </div>
      <div className={`font-heading font-bold text-xl mt-1 ${color}`}>{value}</div>
      {hint && <div className="text-[11px] text-[var(--ink-3)] mt-0.5">{hint}</div>}
    </div>
  );
}
