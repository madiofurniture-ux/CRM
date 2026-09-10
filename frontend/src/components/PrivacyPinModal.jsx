import { useState } from "react";
import { Shield, X } from "lucide-react";
import { usePrivacyMode } from "@/context/PrivacyModeContext";
import api, { formatApiError } from "@/lib/api";

export default function PrivacyPinModal() {
  const { showPinModal, setShowPinModal, unlockWithPin } = usePrivacyMode();
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [needsSetup, setNeedsSetup] = useState(false);

  if (!showPinModal) return null;

  const close = () => { setShowPinModal(false); setPin(""); setError(""); setNeedsSetup(false); };

  const submit = async (e) => {
    e.preventDefault();
    if (pin.length !== 4 || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      if (needsSetup) {
        await api.post("/finance/set-privacy-pin", { pin });
      }
      await unlockWithPin(pin);
    } catch (e) {
      const detail = e.response?.data?.detail || "";
      if (e.response?.status === 400 && /not set/i.test(detail)) {
        setNeedsSetup(true);
        setError("No privacy PIN set yet — choose one now to unlock.");
      } else {
        setError(formatApiError(detail) || "Incorrect PIN");
      }
      setPin("");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-[100] flex items-center justify-center p-4" onClick={close} onKeyDown={(e) => e.key === "Escape" && close()}>
      <div role="dialog" aria-modal="true" aria-labelledby="privacy-pin-title" className="bg-white rounded-2xl border border-[var(--border)] w-full max-w-xs p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Shield size={18} className="text-[var(--brand)]" />
            <h3 id="privacy-pin-title" className="font-heading font-semibold">{needsSetup ? "Set Privacy PIN" : "Unlock Other Amounts"}</h3>
          </div>
          <button onClick={close} aria-label="Close"><X size={16} /></button>
        </div>
        <p className="text-xs text-[var(--ink-3)] mb-4">
          {needsSetup ? "Choose a 4-digit PIN to protect Other amounts going forward." : "Enter your privacy PIN to view masked Other amounts."}
        </p>
        <form onSubmit={submit}>
          <input
            type="password" inputMode="numeric" maxLength={4} autoFocus
            value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
            className="w-full text-center text-2xl tracking-[0.5em] px-3 py-3 rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]"
            data-testid="privacy-pin-input"
          />
          {error && <div className="mt-3 text-xs text-[var(--danger)]" data-testid="privacy-pin-error">{error}</div>}
          <button type="submit" disabled={pin.length !== 4 || submitting} className="btn-primary w-full justify-center mt-4 disabled:opacity-60" data-testid="privacy-pin-submit">
            {submitting ? "Checking…" : needsSetup ? "Set PIN & Unlock" : "Unlock"}
          </button>
        </form>
      </div>
    </div>
  );
}
