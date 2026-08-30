import { useEffect, useState } from "react";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { X, MessageCircle, Phone } from "lucide-react";
import StageProgressBar from "@/components/StageProgressBar";
import { useAuth } from "@/context/AuthContext";

/**
 * Customer-360 slide-over. Give it a phone number and it pulls the whole journey
 * (visits, leads, quotes, sales, payments, activities) from the backend, joined by
 * phone, on one timeline — the same view as the 🧭 button in the live web app.
 *
 * Usage:  const [jny, setJny] = useState(null);
 *         <JourneyDrawer phone={jny?.phone} name={jny?.name} onClose={() => setJny(null)} />
 */
export default function JourneyDrawer({ phone, name, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!phone) { setData(null); return; }
    setLoading(true);
    api.get(`/journey/${encodeURIComponent(phone)}`)
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [phone]);

  const { tenant } = useAuth();
  if (!phone) return null;

  const t = data?.totals || {};
  const first = String(name || data?.name || "").split(" ")[0];
  const brand = tenant?.short_name || "CRM";
  const waHref = `https://wa.me/91${String(phone).replace(/\D/g, "").slice(-10)}?text=${encodeURIComponent(`Hi ${first}, this is ${brand}. `)}`;

  return (
    <div className="fixed inset-0 z-[60] flex justify-end" data-testid="journey-drawer">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <div className="w-full max-w-md bg-white h-full overflow-y-auto shadow-2xl border-l border-[var(--border)]">
        <div className="sticky top-0 bg-white border-b border-[var(--border)] px-5 py-4 flex items-center justify-between">
          <div className="min-w-0">
            <div className="font-heading font-semibold text-lg text-[var(--ink)] truncate">🧭 {name || data?.name || "Customer"}</div>
            <div className="text-xs text-[var(--ink-3)] font-mono">{phone}</div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
        </div>

        <div className="p-5 space-y-5">
          {data?.pipeline && <StageProgressBar stages={data.pipeline} />}
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Quoted" value={inrFull(t.quoted)} />
            <Stat label="Sold" value={inrFull(t.sold)} accent="moss" />
            <Stat label="Collected" value={inrFull(t.collected)} accent="moss" />
            <Stat label="Balance" value={inrFull(t.balance)} accent={t.balance > 0 ? "danger" : "ink"} />
          </div>

          {(data?.divisions?.length || data?.lead_stage) && (
            <div className="flex flex-wrap gap-1.5">
              {data.lead_stage && <Chip>{data.lead_stage}</Chip>}
              {(data.divisions || []).map((d) => <Chip key={d}>{d}</Chip>)}
            </div>
          )}

          <div className="flex gap-2">
            <a href={waHref} target="_blank" rel="noreferrer" className="btn-ghost flex-1 justify-center"><MessageCircle size={14} /> WhatsApp</a>
            <a href={`tel:${phone}`} className="btn-ghost flex-1 justify-center"><Phone size={14} /> Call</a>
          </div>

          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] mb-2">Timeline</div>
            {loading && <div className="text-sm text-[var(--ink-3)] py-4">Loading…</div>}
            {!loading && (data?.events || []).length === 0 && <div className="text-sm text-[var(--ink-3)] py-4">No history yet.</div>}
            <div className="space-y-0">
              {(data?.events || []).map((e, i) => (
                <div key={i} className="flex gap-3 pb-4 relative">
                  <div className="flex flex-col items-center">
                    <div className="w-7 h-7 rounded-full bg-[var(--surface-2)] border border-[var(--border)] flex items-center justify-center text-sm shrink-0">{e.icon}</div>
                    {i < data.events.length - 1 && <div className="w-px flex-1 bg-[var(--border)] mt-1" />}
                  </div>
                  <div className="min-w-0 pt-0.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] uppercase tracking-wide font-semibold text-[var(--ink-3)]">{e.kind}</span>
                      <span className="text-[10px] text-[var(--ink-3)]">{fmtDate(e.date)}</span>
                    </div>
                    <div className="text-sm text-[var(--ink)] font-medium">{e.title}</div>
                    {e.detail && <div className="text-xs text-[var(--ink-2)]">{e.detail}</div>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, accent = "ink" }) {
  const color = { moss: "text-[var(--moss)]", danger: "text-[var(--danger)]", ink: "text-[var(--ink)]" }[accent];
  return (
    <div className="p-3 rounded-lg border border-[var(--border-light)] bg-[var(--surface-2)]">
      <div className="text-[10px] uppercase tracking-widest font-semibold text-[var(--ink-3)]">{label}</div>
      <div className={`font-heading font-bold text-base font-mono ${color}`}>{value}</div>
    </div>
  );
}

function Chip({ children }) {
  return <span className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--brand-soft)] text-[var(--brand)] font-semibold">{children}</span>;
}
