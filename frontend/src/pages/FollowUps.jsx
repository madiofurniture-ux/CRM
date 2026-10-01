import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Topbar from "@/components/Topbar";
import EmptyState from "@/components/EmptyState";
import api from "@/lib/api";
import { fmtDate, inrFull } from "@/lib/format";
import { toast } from "sonner";
import { AlarmClock, Phone, MessageCircle, CheckCircle2 } from "lucide-react";

const BUCKETS = [
  { id: "overdue", label: "Overdue", tone: "text-red-700 bg-red-50 border-red-200" },
  { id: "today", label: "Today", tone: "text-amber-700 bg-amber-50 border-amber-200" },
  { id: "upcoming", label: "Next 7 days", tone: "text-blue-700 bg-blue-50 border-blue-200" },
  { id: "no_follow_up", label: "No follow-up date", tone: "text-[var(--ink)] bg-white border-[var(--border)]" },
  { id: "no_next_action", label: "No next action", tone: "text-[var(--ink)] bg-white border-[var(--border)]" },
  { id: "inactive", label: "Inactive 14+ days", tone: "text-[var(--ink)] bg-white border-[var(--border)]" },
  { id: "unassigned", label: "Unassigned", tone: "text-[var(--ink)] bg-white border-[var(--border)]" },
];

const addDays = (n) => {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
};
const wa = (lead) => `https://wa.me/91${String(lead.whatsapp || lead.phone || "").replace(/\D/g, "").slice(-10)}`;

export default function FollowUps() {
  const [data, setData] = useState(null);
  const [bucket, setBucket] = useState("overdue");
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(null); // lead id whose next action is being edited
  const [nextAction, setNextAction] = useState("");

  const load = async () => {
    setFailed(false);
    try {
      const { data } = await api.get("/followups/summary", { skipCache: true });
      setData(data);
    } catch {
      setFailed(true);
    }
  };
  useEffect(() => { load(); }, []);

  const update = async (lead, patch, msg) => {
    try {
      await api.put(`/leads/${lead.id}`, patch);
      toast.success(msg);
      load();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : d?.message || "Update failed");
    }
  };

  const rows = data ? data[bucket] || [] : [];

  return (
    <>
      <Topbar title="Follow-ups" subtitle={data ? `${data.counts.overdue} overdue · ${data.counts.today} today · ${data.counts.upcoming} upcoming` : "Loading…"} />
      <div className="p-3 sm:p-6" data-testid="followups-page">
        {failed && (
          <div className="text-center py-10">
            <div className="text-sm text-[var(--danger)] mb-2">Couldn't load follow-ups.</div>
            <button className="btn-ghost" onClick={load}>Retry</button>
          </div>
        )}
        {data && (
          <>
            <div className="grid grid-cols-3 gap-2 mb-3">
              {BUCKETS.slice(0, 3).map((b) => (
                <button key={b.id} onClick={() => setBucket(b.id)}
                  className={`rounded-2xl border p-3 text-left ${b.tone} ${bucket === b.id ? "ring-2 ring-[var(--brand)]" : ""}`}
                  data-testid={`bucket-${b.id}`}>
                  <div className="text-[10px] uppercase tracking-wider font-bold">{b.label}</div>
                  <div className="font-heading font-bold text-2xl">{data.counts[b.id]}</div>
                </button>
              ))}
            </div>
            <div className="flex gap-2 overflow-x-auto pb-2 mb-4">
              {BUCKETS.slice(3).map((b) => (
                <button key={b.id} onClick={() => setBucket(b.id)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold border whitespace-nowrap ${bucket === b.id ? "bg-[var(--ink)] text-white border-[var(--ink)]" : "bg-white border-[var(--border)] text-[var(--ink-2)]"}`}>
                  {b.label} ({data.counts[b.id]})
                </button>
              ))}
              <button onClick={() => setBucket("overdue_payments")}
                className={`px-3 py-1.5 rounded-full text-xs font-semibold border whitespace-nowrap ${bucket === "overdue_payments" ? "bg-[var(--ink)] text-white border-[var(--ink)]" : "bg-white border-[var(--border)] text-[var(--ink-2)]"}`}>
                Payments overdue ({data.counts.overdue_payments})
              </button>
              <Link to="/quotes/followups" className="px-3 py-1.5 rounded-full text-xs font-semibold border whitespace-nowrap bg-white border-[var(--border)] text-[var(--brand)]">
                Quotation follow-ups →
              </Link>
              <Link to="/service" className="px-3 py-1.5 rounded-full text-xs font-semibold border whitespace-nowrap bg-white border-[var(--border)] text-[var(--brand)]">
                Open service ({data.counts.open_service_tickets}) →
              </Link>
            </div>

            {bucket === "overdue_payments" ? (
              rows.length === 0 ? <EmptyState icon={CheckCircle2} title="No overdue payments" /> : (
                <div className="space-y-2">
                  {rows.map((p) => (
                    <div key={p.project_id} className="bg-white border border-[var(--border)] rounded-2xl p-3 flex flex-wrap items-center gap-3">
                      <div className="flex-1 min-w-[180px]">
                        <Link to={`/projects?open=${p.project_id}`} className="font-semibold hover:underline">{p.customer}</Link>
                        <div className="text-xs text-[var(--ink-3)]">{p.project_no} · due {fmtDate(p.next_payment_due)}</div>
                      </div>
                      <div className="font-mono text-sm text-[var(--danger)] font-bold">{inrFull(p.amount_pending)}</div>
                      {p.phone && <a href={`tel:${p.phone}`} className="p-2 rounded-lg border border-[var(--border)]" aria-label="Call"><Phone size={15} /></a>}
                    </div>
                  ))}
                </div>
              )
            ) : rows.length === 0 ? (
              <EmptyState icon={CheckCircle2} title="Nothing here — nice." hint="Every open lead in this bucket has been handled." />
            ) : (
              <div className="space-y-2">
                {rows.map((l) => (
                  <div key={l.id} className="bg-white border border-[var(--border)] rounded-2xl p-3" data-testid={`fu-${l.id}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <Link to={`/leads?open=${l.id}`} className="font-semibold text-[var(--ink)] hover:underline">{l.name}</Link>
                        <div className="text-xs text-[var(--ink-3)]">
                          {[l.stage, l.division, l.source, l.assigned_to || "Unassigned", l.value ? inrFull(l.value) : ""].filter(Boolean).join(" · ")}
                        </div>
                        <div className="text-xs mt-1">
                          <AlarmClock size={11} className="inline mr-1 text-[var(--ink-3)]" />
                          {l.follow_up_date ? fmtDate(l.follow_up_date) : "No date"} — {l.next_action ? <b>{l.next_action}</b> : <span className="text-[var(--danger)]">no next action</span>}
                        </div>
                      </div>
                      <div className="flex gap-1.5 shrink-0">
                        {l.phone && <a href={`tel:${l.phone}`} className="p-2.5 rounded-lg border border-[var(--border)]" aria-label={`Call ${l.name}`}><Phone size={15} /></a>}
                        {(l.whatsapp || l.phone) && <a href={wa(l)} target="_blank" rel="noreferrer" className="p-2.5 rounded-lg border border-emerald-200 text-emerald-700" aria-label={`WhatsApp ${l.name}`}><MessageCircle size={15} /></a>}
                      </div>
                    </div>
                    {editing === l.id ? (
                      <div className="flex flex-wrap gap-2 mt-2">
                        <input value={nextAction} onChange={(e) => setNextAction(e.target.value)} placeholder="e.g. Share revised quote"
                          className="flex-1 min-w-[160px] px-2 py-1.5 border border-[var(--border)] rounded-lg text-sm" autoFocus />
                        <button className="btn-primary" onClick={() => { update(l, { next_action: nextAction }, "Next action saved"); setEditing(null); }}>Save</button>
                        <button className="btn-ghost" onClick={() => setEditing(null)}>Cancel</button>
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {[["Tomorrow", 1], ["+3 days", 3], ["+1 week", 7]].map(([label, n]) => (
                          <button key={label} onClick={() => update(l, { follow_up_date: addDays(n) }, `Follow-up moved to ${fmtDate(addDays(n))}`)}
                            className="px-2.5 py-1.5 rounded-lg border border-[var(--border)] text-xs font-medium hover:bg-[var(--surface-2)]">
                            {label}
                          </button>
                        ))}
                        <button onClick={() => { setEditing(l.id); setNextAction(l.next_action || ""); }}
                          className="px-2.5 py-1.5 rounded-lg border border-[var(--border)] text-xs font-medium hover:bg-[var(--surface-2)]">
                          Next action
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
