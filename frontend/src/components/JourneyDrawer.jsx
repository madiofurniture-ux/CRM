import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { X, MessageCircle, Phone, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";
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
  const [tab, setTab] = useState("timeline");
  const [notifs, setNotifs] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [people, setPeople] = useState([]);
  const [addingPerson, setAddingPerson] = useState(false);
  const [personForm, setPersonForm] = useState({ contact_name: "", contact_phone: "", role: "" });

  const loadPeople = () => {
    if (!phone) { setPeople([]); return; }
    api.get(`/record-contacts?phone=${encodeURIComponent(phone)}`)
      .then((r) => setPeople(r.data))
      .catch(() => setPeople([]));
  };

  useEffect(() => {
    if (!phone) { setData(null); setNotifs([]); setConversations([]); setPeople([]); return; }
    setLoading(true);
    api.get(`/journey/${encodeURIComponent(phone)}`)
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
    api.get(`/notifications?phone=${encodeURIComponent(phone)}`)
      .then((r) => setNotifs(r.data))
      .catch(() => setNotifs([]));
    api.get(`/agent-conversations?phone=${encodeURIComponent(phone)}`)
      .then((r) => setConversations(r.data))
      .catch(() => setConversations([]));
    loadPeople();
  }, [phone]); // eslint-disable-line

  const addPerson = async () => {
    if (!personForm.contact_name.trim()) return toast.error("Name is required");
    setAddingPerson(true);
    try {
      await api.post(`/record-contacts?resolve_phone=${encodeURIComponent(phone)}`,
        { subject_type: "lead", ...personForm });
      toast.success("Contact added");
      setPersonForm({ contact_name: "", contact_phone: "", role: "" });
      loadPeople();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setAddingPerson(false); }
  };

  const removePerson = async (id) => {
    try { await api.delete(`/record-contacts/${id}`); loadPeople(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

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
            <div className="flex gap-4 border-b border-[var(--border-light)] mb-3">
              <button onClick={() => setTab("timeline")}
                className={`text-[11px] font-semibold uppercase tracking-wider pb-2 -mb-px border-b-2 ${tab === "timeline" ? "border-[var(--brand)] text-[var(--brand)]" : "border-transparent text-[var(--ink-3)]"}`}>
                Timeline
              </button>
              <button onClick={() => setTab("notifications")} data-testid="journey-tab-notifications"
                className={`text-[11px] font-semibold uppercase tracking-wider pb-2 -mb-px border-b-2 ${tab === "notifications" ? "border-[var(--brand)] text-[var(--brand)]" : "border-transparent text-[var(--ink-3)]"}`}>
                Notification Log{notifs.length ? ` (${notifs.length})` : ""}
              </button>
              <button onClick={() => setTab("agent")} data-testid="journey-tab-agent"
                className={`text-[11px] font-semibold uppercase tracking-wider pb-2 -mb-px border-b-2 ${tab === "agent" ? "border-[var(--brand)] text-[var(--brand)]" : "border-transparent text-[var(--ink-3)]"}`}>
                Agent{conversations.length ? ` (${conversations.length})` : ""}
              </button>
              <button onClick={() => setTab("people")} data-testid="journey-tab-people"
                className={`text-[11px] font-semibold uppercase tracking-wider pb-2 -mb-px border-b-2 ${tab === "people" ? "border-[var(--brand)] text-[var(--brand)]" : "border-transparent text-[var(--ink-3)]"}`}>
                People{people.length ? ` (${people.length})` : ""}
              </button>
            </div>

            {tab === "timeline" && (
              <>
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
              </>
            )}

            {tab === "notifications" && (
              <div className="space-y-2" data-testid="journey-notification-log">
                {notifs.length === 0 && <div className="text-sm text-[var(--ink-3)] py-4">No notifications sent yet.</div>}
                {notifs.map((n) => (
                  <div key={n.id} className="p-3 rounded-lg border border-[var(--border-light)] bg-[var(--surface-2)]">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] uppercase tracking-wide font-semibold text-[var(--ink-3)]">{n.channel} · {n.event.replace(/_/g, " ")}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${n.status === "Sent" ? "bg-[var(--brand-soft)] text-[var(--brand)]" : "bg-[var(--danger-soft,#fee)] text-[var(--danger)]"}`}>{n.status}</span>
                    </div>
                    <div className="text-xs text-[var(--ink-2)]">{n.message}</div>
                    <div className="text-[10px] text-[var(--ink-3)] mt-1">{fmtDate(n.created_at)}</div>
                  </div>
                ))}
              </div>
            )}

            {tab === "agent" && (
              <div className="space-y-3" data-testid="journey-agent-tab">
                {conversations.length === 0 && <div className="text-sm text-[var(--ink-3)] py-4">No agent conversations yet.</div>}
                {conversations.map((c) => (
                  <div key={c.id} className="p-3 rounded-lg border border-[var(--border-light)] bg-[var(--surface-2)]">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] uppercase tracking-wide font-semibold text-[var(--ink-3)]">{c.subject_type} · {fmtDate(c.created_at)}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${c.status === "closed" ? "bg-[var(--surface-2)] text-[var(--ink-3)]" : "bg-[var(--brand-soft)] text-[var(--brand)]"}`}>{c.status}</span>
                    </div>
                    <div className="space-y-1.5">
                      {(c.log || []).map((e, i) => (
                        <div key={i} className="text-xs">
                          <span className="font-semibold text-[var(--ink-2)]">{e.by}: </span>
                          <span className="text-[var(--ink-2)]">{e.text}</span>
                        </div>
                      ))}
                      {c.status === "awaiting_input" && c.pending_question && (
                        <div className="text-xs text-[var(--warn)] italic mt-1">Waiting on: {c.pending_question.text}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {tab === "people" && (
              <div className="space-y-3" data-testid="journey-people-tab">
                {people.length === 0 && <div className="text-sm text-[var(--ink-3)] py-2">No other contacts on this record yet.</div>}
                {people.map((p) => (
                  <div key={p.id} className="p-3 rounded-lg border border-[var(--border-light)] bg-[var(--surface-2)] flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-[var(--ink)]">{p.contact_name}</div>
                      <div className="text-xs text-[var(--ink-3)]">{p.role || "—"}{p.contact_phone ? ` · ${p.contact_phone}` : ""}</div>
                    </div>
                    <button onClick={() => removePerson(p.id)} className="p-1 rounded hover:bg-[var(--surface-hover)] text-[var(--ink-3)] shrink-0"><Trash2 size={13} /></button>
                  </div>
                ))}
                <div className="pt-2 border-t border-[var(--border-light)] space-y-2">
                  <input value={personForm.contact_name} onChange={(e) => setPersonForm({ ...personForm, contact_name: e.target.value })}
                    placeholder="Name" className="w-full px-3 py-1.5 rounded-lg border border-[var(--border)] text-sm" />
                  <div className="flex gap-2">
                    <input value={personForm.role} onChange={(e) => setPersonForm({ ...personForm, role: e.target.value })}
                      placeholder="Role (e.g. Site Engineer)" className="flex-1 min-w-0 px-3 py-1.5 rounded-lg border border-[var(--border)] text-sm" />
                    <input value={personForm.contact_phone} onChange={(e) => setPersonForm({ ...personForm, contact_phone: e.target.value })}
                      placeholder="Phone" className="w-28 px-3 py-1.5 rounded-lg border border-[var(--border)] text-sm" />
                  </div>
                  <button onClick={addPerson} disabled={addingPerson} className="btn-ghost w-full justify-center disabled:opacity-60" data-testid="add-person">
                    <UserPlus size={14} /> {addingPerson ? "Adding…" : "Add Contact"}
                  </button>
                </div>
              </div>
            )}
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
