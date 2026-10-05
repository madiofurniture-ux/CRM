import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { inrFull, todayIST } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { X } from "lucide-react";

const MODES = ["Other", "Bank", "UPI", "Cheque"];

/**
 * A customer payment against a sale or an invoice (POST /payments). The
 * server rolls it into the sale's paid/balance and re-syncs its invoices.
 * Used by Outstanding and the Sales Register.
 */
export default function RecordPaymentModal({ target, onClose, onSaved }) {
  const { user } = useAuth();
  const [form, setForm] = useState({ date: todayIST(), amount: target.record.balance || 0, mode: "Other", remarks: "" });
  const [saving, setSaving] = useState(false);
  const [wallets, setWallets] = useState([]);
  const [walletId, setWalletId] = useState("");
  const closeModal = onClose;

  // Optional: bank the receipt in a Cashbook wallet (one receipt, one wallet entry).
  useEffect(() => {
    api.get("/cashbooks").then(({ data }) => setWallets((data || []).filter((b) => b.status === "ACTIVE")))
      .catch(() => setWallets([]));         // no cashbook access: the field stays hidden
  }, []);

  const submitPayment = async (e) => {
    e.preventDefault();
    if (saving) return;
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
        wallet_id: walletId,
      };
      if (target.kind === "sale") payload.against_sale_id = target.record.id;
      else payload.against_invoice_id = target.record.id;
      await api.post("/payments", payload);
      toast.success("Payment recorded");
      onSaved?.();
      onClose();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Failed to record payment");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[var(--border)] w-full max-w-sm shadow-xl overflow-hidden max-h-[92vh] overflow-y-auto">
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

              {wallets.length > 0 && (
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Bank in wallet (optional)</label>
                  <select value={walletId} onChange={(e) => setWalletId(e.target.value)} data-testid="payment-wallet"
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)] bg-white">
                    <option value="">Not banked in a wallet</option>
                    {wallets.map((w) => <option key={w.id} value={w.id}>{w.book_name}</option>)}
                  </select>
                </div>
              )}

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
      
    </>
  );
}
