import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, MapPin, Users as UsersIcon, X, Trash2 } from "lucide-react";

const HOURS = Array.from({ length: 12 }, (_, i) => 8 + i); // 8..19

function startOfWeek(d) {
  const dt = new Date(d);
  const day = dt.getDay(); // 0=Sun
  const diff = day === 0 ? -6 : 1 - day; // week starts Monday
  dt.setDate(dt.getDate() + diff);
  dt.setHours(0, 0, 0, 0);
  return dt;
}

export default function Meets() {
  const [rows, setRows] = useState([]);
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [view, setView] = useState("week"); // week / list
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(null);
  const empty = { title: "", date: new Date().toISOString().slice(0, 10), start_time: "10:00", end_time: "11:00", location: "", with_person: "", ref_type: "Internal", ref_name: "", agenda: "", status: "Scheduled", attendees: [] };
  const [form, setForm] = useState(empty);

  const load = async () => { const { data } = await api.get("/meets"); setRows(data); };
  useEffect(() => { load(); }, []);

  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart); d.setDate(d.getDate() + i); return d;
  }), [weekStart]);

  const shiftWeek = (delta) => {
    const d = new Date(weekStart); d.setDate(d.getDate() + delta * 7); setWeekStart(d);
  };

  const byDay = useMemo(() => {
    const map = {};
    for (const m of rows) map[m.date] = [...(map[m.date] || []), m];
    return map;
  }, [rows]);

  const openNew = (dateStr, startHour) => {
    setEditing(null);
    setForm({ ...empty, date: dateStr, start_time: `${String(startHour).padStart(2, "0")}:00`, end_time: `${String(startHour + 1).padStart(2, "0")}:00` });
    setShow(true);
  };
  const openEdit = (m) => { setEditing(m); setForm(m); setShow(true); };
  const save = async () => {
    try {
      if (editing) { await api.put(`/meets/${editing.id}`, form); toast.success("Meet updated"); }
      else { await api.post("/meets", form); toast.success("Meet scheduled"); }
      setShow(false); load();
    } catch { toast.error("Save failed"); }
  };
  const remove = async (id) => { if (!window.confirm("Delete meeting?")) return; await api.delete(`/meets/${id}`); load(); };

  const upcoming = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return rows.filter((m) => m.date >= today).sort((a, b) => (a.date + a.start_time).localeCompare(b.date + b.start_time)).slice(0, 20);
  }, [rows]);

  const label = (d) => d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
  const isToday = (d) => d.toDateString() === new Date().toDateString();

  return (
    <>
      <Topbar
        title="Meet Planner"
        subtitle={`${rows.length} meetings · ${upcoming.length} upcoming`}
        onAdd={() => openNew(new Date().toISOString().slice(0, 10), 10)}
        addLabel="Schedule"
        actions={
          <div className="hidden md:flex items-center bg-[var(--surface-2)] border border-[var(--border)] rounded-lg p-0.5">
            <button onClick={() => setView("week")} className={`px-3 py-1 rounded text-xs font-medium ${view === "week" ? "bg-white shadow-sm" : "text-[var(--ink-2)]"}`}>Week</button>
            <button onClick={() => setView("list")} className={`px-3 py-1 rounded text-xs font-medium ${view === "list" ? "bg-white shadow-sm" : "text-[var(--ink-2)]"}`}>List</button>
          </div>
        }
      />
      <div className="p-4 md:p-6" data-testid="meets-page">
        {view === "week" ? (
          <>
            <div className="flex items-center justify-between mb-4">
              <button onClick={() => shiftWeek(-1)} className="btn-ghost text-xs" data-testid="week-prev"><ChevronLeft size={14} />Prev week</button>
              <div className="font-heading font-semibold text-[var(--ink)]">
                {days[0].toLocaleDateString("en-IN", { day: "numeric", month: "short" })} — {days[6].toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
              </div>
              <button onClick={() => shiftWeek(1)} className="btn-ghost text-xs" data-testid="week-next">Next<ChevronRight size={14} /></button>
            </div>
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <div className="grid grid-cols-[60px_repeat(7,minmax(140px,1fr))] min-w-[900px]">
                  <div className="bg-[var(--surface-2)] border-b border-[var(--border)]" />
                  {days.map((d) => (
                    <div key={d.toISOString()} className={`bg-[var(--surface-2)] border-b border-l border-[var(--border)] px-3 py-2 text-center ${isToday(d) ? "bg-[var(--brand-soft)]" : ""}`}>
                      <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)] font-semibold">{d.toLocaleDateString("en-IN", { weekday: "short" })}</div>
                      <div className={`font-heading font-bold text-lg ${isToday(d) ? "text-[var(--brand)]" : "text-[var(--ink)]"}`}>{d.getDate()}</div>
                    </div>
                  ))}
                  {HOURS.map((h) => (
                    <>
                      <div key={`h-${h}`} className="text-[10px] font-mono text-[var(--ink-3)] text-right pr-2 py-6 border-t border-[var(--border-light)]">{String(h).padStart(2, "0")}:00</div>
                      {days.map((d) => {
                        const dateStr = d.toISOString().slice(0, 10);
                        const meets = (byDay[dateStr] || []).filter((m) => {
                          const start = parseInt(m.start_time.split(":")[0], 10);
                          return start === h;
                        });
                        return (
                          <div
                            key={`${dateStr}-${h}`}
                            className="border-t border-l border-[var(--border-light)] min-h-[52px] p-1 hover:bg-[var(--surface-2)]/50 cursor-pointer relative"
                            onClick={() => meets.length === 0 && openNew(dateStr, h)}
                            data-testid={`meet-slot-${dateStr}-${h}`}
                          >
                            {meets.map((m) => (
                              <div
                                key={m.id}
                                onClick={(e) => { e.stopPropagation(); openEdit(m); }}
                                className="text-[11px] px-1.5 py-1 rounded bg-[var(--brand-soft)] text-[var(--brand)] mb-0.5 border-l-2 border-[var(--brand)] cursor-pointer hover:brightness-95"
                                data-testid={`meet-${m.id}`}
                              >
                                <div className="font-semibold truncate">{m.title}</div>
                                <div className="text-[10px] text-[var(--ink-3)]">{m.start_time}–{m.end_time}</div>
                              </div>
                            ))}
                          </div>
                        );
                      })}
                    </>
                  ))}
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="space-y-2">
            {upcoming.map((m) => (
              <div key={m.id} className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 flex items-start gap-4 hover:shadow-sm" onClick={() => openEdit(m)}>
                <div className="text-center min-w-[60px]">
                  <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">{new Date(m.date).toLocaleDateString("en-IN", { month: "short" })}</div>
                  <div className="font-heading font-bold text-2xl text-[var(--brand)]">{new Date(m.date).getDate()}</div>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-heading font-semibold text-[var(--ink)]">{m.title}</div>
                  <div className="flex flex-wrap gap-3 mt-1 text-xs text-[var(--ink-2)]">
                    <span className="font-mono">{m.start_time}–{m.end_time}</span>
                    {m.location && <span className="flex items-center gap-1"><MapPin size={11} />{m.location}</span>}
                    {m.with_person && <span className="flex items-center gap-1"><UsersIcon size={11} />{m.with_person}</span>}
                  </div>
                  {m.agenda && <div className="text-xs text-[var(--ink-3)] mt-1.5 line-clamp-2">{m.agenda}</div>}
                </div>
                <button onClick={(e) => { e.stopPropagation(); remove(m.id); }} className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button>
              </div>
            ))}
            {upcoming.length === 0 && <div className="text-center py-12 text-[var(--ink-3)]">No upcoming meetings</div>}
          </div>
        )}
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-3" onClick={() => setShow(false)}>
          <div className="bg-white rounded-xl border w-full max-w-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">{editing ? "Edit Meeting" : "Schedule Meeting"}</h3>
              <button onClick={() => setShow(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 grid grid-cols-2 gap-4">
              <F l="Title" v={form.title} oc={(v) => setForm({ ...form, title: v })} cls="col-span-2" t2="meet-title" />
              <F l="Date" t="date" v={form.date} oc={(v) => setForm({ ...form, date: v })} />
              <div className="grid grid-cols-2 gap-2">
                <F l="Start" t="time" v={form.start_time} oc={(v) => setForm({ ...form, start_time: v })} />
                <F l="End" t="time" v={form.end_time} oc={(v) => setForm({ ...form, end_time: v })} />
              </div>
              <F l="Location" v={form.location} oc={(v) => setForm({ ...form, location: v })} />
              <F l="With" v={form.with_person} oc={(v) => setForm({ ...form, with_person: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Type</label>
                <select value={form.ref_type} onChange={(e) => setForm({ ...form, ref_type: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                  <option>Lead</option><option>Architect</option><option>Customer</option><option>Internal</option>
                </select>
              </div>
              <F l="Reference name" v={form.ref_name} oc={(v) => setForm({ ...form, ref_name: v })} />
              <div className="col-span-2">
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Agenda</label>
                <textarea value={form.agenda} onChange={(e) => setForm({ ...form, agenda: e.target.value })} rows="3" className="w-full px-3 py-2 rounded-lg border border-[var(--border)] text-sm resize-none focus:border-[var(--brand)] outline-none" />
              </div>
            </div>
            <div className="px-5 py-4 border-t flex justify-between">
              {editing ? <button onClick={() => { remove(editing.id); setShow(false); }} className="btn-ghost text-[var(--danger)]"><Trash2 size={13} />Delete</button> : <span />}
              <div className="flex gap-2">
                <button className="btn-ghost" onClick={() => setShow(false)}>Cancel</button>
                <button className="btn-primary" onClick={save} data-testid="meet-save">{editing ? "Save" : "Schedule"}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
function F({ l, v, oc, t = "text", cls = "", t2 }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input type={t} value={v} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" data-testid={t2} />
    </div>
  );
}
