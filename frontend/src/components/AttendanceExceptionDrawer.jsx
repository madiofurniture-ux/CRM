import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { X, MapPin, Camera, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const REASONS = [
  { value: "forgot_to_punch", label: "Forgot to punch" },
  { value: "device_issue", label: "Device issue" },
  { value: "approved_field_visit", label: "Approved field visit" },
  { value: "other", label: "Other" },
];

/**
 * Right-side drawer for one attendance exception row (out-of-geofence punch,
 * missing punch). Admin-only actions: Regularise (net-new POST — see report)
 * and Mark absent. Non-admins can still open it to see the outcome fields
 * the bulk /attendance list already returns; the raw GPS/selfie block only
 * loads for admins, from the existing admin-only /attendance/{id}/raw route.
 */
export default function AttendanceExceptionDrawer({ record, onClose, onChanged }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [raw, setRaw] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [reason, setReason] = useState(REASONS[0].value);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setRaw(null);
    setShowForm(false);
    setNote("");
    if (record && isAdmin) {
      api.get(`/attendance/${record.id}/raw`).then((r) => setRaw(r.data)).catch(() => setRaw(null));
    }
  }, [record, isAdmin]);

  if (!record) return null;

  const regularise = async () => {
    setSaving(true);
    try {
      await api.post(`/attendance/${record.id}/regularize`, { reason, note });
      toast.success("Punch regularised");
      setShowForm(false);
      onChanged?.();
      onClose();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const markAbsent = async () => {
    if (!window.confirm(`Mark ${record.name} absent for ${record.date}?`)) return;
    setSaving(true);
    try {
      await api.post(`/attendance/${record.id}/mark-absent`);
      toast.success("Marked absent");
      onChanged?.();
      onClose();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const resolved = record.status === "regularized" || record.status === "absent";

  return (
    <div className="fixed inset-0 z-[60] flex justify-end" data-testid="attendance-exception-drawer">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <div className="w-full max-w-md bg-[var(--color-surface)] h-full overflow-y-auto shadow-2xl border-l border-[var(--color-border)]">
        <div className="sticky top-0 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-5 py-4 flex items-center justify-between">
          <div className="min-w-0">
            <div className="font-heading font-semibold text-lg text-[var(--color-text)] truncate">{record.name}</div>
            <div className="text-xs text-[var(--color-text-muted)]">{record.site_name || "Office"} · {record.date}</div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-md hover:bg-[var(--color-surface-muted)]"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-5">
          <div className="p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] grid grid-cols-2 gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--color-text-muted)]">Check-In</div>
              <div className="font-mono text-sm">{record.check_in_at ? record.check_in_at.slice(11, 16) : "—"}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--color-text-muted)]">Check-Out</div>
              <div className="font-mono text-sm">{record.check_out_at ? record.check_out_at.slice(11, 16) : "—"}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--color-text-muted)]">Duration</div>
              <div className="font-mono text-sm">{record.duration_min ? `${record.duration_min} min` : "—"}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--color-text-muted)]">Status</div>
              <div className="text-sm font-medium">{record.status}</div>
            </div>
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-wider font-semibold text-[var(--color-text-muted)] mb-2">Selfie &amp; Location Check</div>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm">
                <MapPin size={14} className="text-[var(--color-text-muted)]" />
                Distance from fence: <span className="font-mono font-semibold">{record.distance_variance_m ?? "—"}m</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Camera size={14} className="text-[var(--color-text-muted)]" />
                Selfie: {record.selfie_verified ? "Captured" : "None"}
              </div>
              {isAdmin && raw?.check_in_photo && (
                <img src={raw.check_in_photo} alt="Check-in selfie" className="rounded-lg border border-[var(--color-border)] max-h-40" />
              )}
              {isAdmin && raw && (
                <div className="text-xs text-[var(--color-text-muted)] font-mono">
                  {raw.check_in_lat?.toFixed?.(5)}, {raw.check_in_lng?.toFixed?.(5)}
                </div>
              )}
            </div>
          </div>

          <div className="p-3 rounded-lg border border-amber-100 bg-amber-50 flex gap-2">
            <AlertTriangle size={16} className="text-amber-700 shrink-0 mt-0.5" />
            <div className="text-xs text-amber-900">
              {record.status === "flagged_out_of_bounds"
                ? `Punched ${record.distance_variance_m}m outside the ${record.site_name || "office"} geofence.`
                : record.status === "regularized"
                  ? `Regularised — ${record.regularize_reason || ""} ${record.regularize_note ? `· ${record.regularize_note}` : ""}`
                  : record.status === "absent"
                    ? "Marked absent."
                    : "No check-out recorded."}
            </div>
          </div>

          {isAdmin && !resolved && (
            <div className="space-y-2 pt-2 border-t border-[var(--color-border)]">
              {!showForm ? (
                <div className="flex gap-2">
                  <button onClick={() => setShowForm(true)} className="btn-primary flex-1 justify-center" data-testid="open-regularise">
                    Regularise…
                  </button>
                  <button onClick={markAbsent} disabled={saving} className="btn-ghost flex-1 justify-center" data-testid="mark-absent">
                    Mark absent
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  <select value={reason} onChange={(e) => setReason(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-lg border border-[var(--color-border)] text-sm" data-testid="regularise-reason">
                    {REASONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                  </select>
                  <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)"
                    className="w-full px-3 py-1.5 rounded-lg border border-[var(--color-border)] text-sm" rows={2} />
                  <div className="flex gap-2">
                    <button onClick={regularise} disabled={saving} className="btn-primary flex-1 justify-center" data-testid="submit-regularise">
                      {saving ? "Saving…" : "Confirm Regularise"}
                    </button>
                    <button onClick={() => setShowForm(false)} className="btn-ghost">Cancel</button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
