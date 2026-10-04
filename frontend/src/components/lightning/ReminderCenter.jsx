import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CalendarDays, CheckSquare, X, AlarmClock } from "lucide-react";
import api from "@/lib/api";
import { isoDateIST } from "@/lib/format";

// Dates and times on tasks and meetings are IST wall-clock values.
const toDate = (at) => new Date(`${at}:00+05:30`);
const fmtTime = (hhmm) => {
  if (!hhmm) return "";
  const [h, m] = hhmm.split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
};
const STORE = "madio.reminders.v1";
const readStore = () => { try { return JSON.parse(window.localStorage.getItem(STORE) || "{}"); } catch { return {}; } };
const writeStore = (v) => { try { window.localStorage.setItem(STORE, JSON.stringify(v)); } catch { /* reminders still show */ } };
const keyOf = (r) => `${r.kind}:${r.id}:${r.at}`;
const SNOOZE_MIN = 10;
const SHOW_AFTER_START_MIN = 60;

function relative(ms) {
  const min = Math.round(ms / 60000);
  if (Math.abs(min) < 1) return "now";
  if (min > 0) return min < 60 ? `in ${min} min` : `in ${Math.floor(min / 60)} h ${min % 60} min`;
  return `${-min} min ago`;
}

/** Bell with today's tasks and meetings, and pop-up reminders that appear
 * on any screen when a timed task or meeting is due (its reminder lead
 * time before). Snooze and dismiss are remembered in this browser. */
export default function ReminderCenter() {
  const nav = useNavigate();
  const [items, setItems] = useState([]);
  const [now, setNow] = useState(Date.now());
  const [state, setState] = useState(readStore);
  const [open, setOpen] = useState(false);
  const notified = useRef(new Set());
  const panelRef = useRef(null);

  const load = useCallback(() => {
    api.get("/reminders", { skipCache: true }).then(({ data }) => setItems(data?.items || [])).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    const poll = setInterval(load, 60000);
    const tick = setInterval(() => setNow(Date.now()), 15000);
    const onFocus = () => { load(); setNow(Date.now()); };
    window.addEventListener("focus", onFocus);
    return () => { clearInterval(poll); clearInterval(tick); window.removeEventListener("focus", onFocus); };
  }, [load]);
  useEffect(() => {
    const onDoc = (e) => { if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const update = (key, value) => setState((s) => {
    const next = { ...s, [key]: value };
    // Forget entries older than two days so the store stays small.
    const cutoff = Date.now() - 2 * 86400000;
    for (const [k, v] of Object.entries(next)) if (typeof v === "number" && v < cutoff) delete next[k];
    writeStore(next);
    return next;
  });

  // Reminders due now: lead time reached, not dismissed, not snoozed, and
  // not more than an hour past the start.
  const due = useMemo(() => items.filter((r) => {
    if (!r.at || r.remind_minutes == null) return false;
    const start = toDate(r.at).getTime();
    const fire = start - Number(r.remind_minutes) * 60000;
    const st = state[keyOf(r)];
    if (st === "dismissed") return false;
    if (typeof st === "number" && st > now) return false;
    return now >= fire && now <= start + SHOW_AFTER_START_MIN * 60000;
  }), [items, state, now]);

  // Desktop notification once per reminder, when the browser allows it.
  useEffect(() => {
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    for (const r of due) {
      const k = keyOf(r);
      if (notified.current.has(k)) continue;
      notified.current.add(k);
      try {
        new Notification(r.kind === "meeting" ? `Meeting: ${r.title}` : `Task: ${r.title}`,
          { body: `${r.kind === "meeting" ? "Starts" : "Due"} at ${fmtTime(r.time)}${r.subtitle ? ` · ${r.subtitle}` : ""}`, tag: k });
      } catch { /* some browsers only allow notifications from a service worker */ }
    }
  }, [due]);

  const todayIso = isoDateIST(new Date(now));
  const upcoming = items.filter((r) => (r.date === todayIso || r.overdue || (r.at && toDate(r.at).getTime() > now)));
  const count = items.filter((r) => r.overdue || r.date === todayIso).length;
  const canAskDesktop = typeof Notification !== "undefined" && Notification.permission === "default";

  return (
    <>
      <div className="relative" ref={panelRef}>
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
                aria-label={`Reminders: ${count} today`} data-testid="reminders-bell"
                className="lx-icon-btn relative">
          <Bell size={18} strokeWidth={1.8} />
          {count > 0 && <span className="lx-badge" aria-hidden="true">{count > 9 ? "9+" : count}</span>}
        </button>
        {open && (
          <div className="absolute right-0 mt-2 w-[22rem] max-w-[calc(100vw-1.5rem)] bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-xl z-50" data-testid="reminders-panel">
            <div className="px-4 py-3 border-b border-[var(--color-border)] flex items-center justify-between">
              <span className="font-semibold text-sm">Your tasks and meetings</span>
              {canAskDesktop && (
                <button type="button" className="text-xs text-[var(--color-primary)] font-medium"
                        onClick={() => Notification.requestPermission().then(() => setNow(Date.now()))}>Turn on desktop alerts</button>
              )}
            </div>
            <div className="max-h-96 overflow-y-auto divide-y divide-[var(--color-border)]">
              {upcoming.length === 0 && <div className="p-4 text-sm text-[var(--color-text-muted)]">Nothing due today or tomorrow.</div>}
              {upcoming.map((r) => (
                <button key={keyOf(r)} type="button" onClick={() => { setOpen(false); nav(r.link); }}
                        className="w-full text-left px-4 py-2.5 flex gap-3 hover:bg-[var(--color-surface-muted)]">
                  <KindTile kind={r.kind} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium truncate">{r.title}</span>
                    <span className={`block text-xs ${r.overdue ? "text-[var(--color-danger)]" : "text-[var(--color-text-muted)]"}`}>
                      {r.overdue ? `Overdue since ${r.date}` : `${r.date === todayIso ? "Today" : "Tomorrow"}${r.time ? ` at ${fmtTime(r.time)}` : ""}`}
                      {r.subtitle ? ` · ${r.subtitle}` : ""}
                    </span>
                  </span>
                  {r.at && r.remind_minutes != null && <AlarmClock size={14} className="text-[var(--color-text-muted)] mt-1 shrink-0" aria-label="Reminder set" />}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Pop-up reminders, bottom right, on every screen */}
      <div className="fixed bottom-4 right-4 z-[80] flex flex-col gap-2 w-[22rem] max-w-[calc(100vw-2rem)]" aria-live="assertive">
        {due.slice(0, 3).map((r) => {
          const start = toDate(r.at).getTime();
          return (
            <div key={keyOf(r)} role="alert" className="lx-reminder" data-testid={`reminder-popup-${r.id}`}>
              <div className="flex gap-3">
                <KindTile kind={r.kind} />
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-[var(--color-text-muted)]">{r.kind === "meeting" ? "Meeting reminder" : "Task reminder"}</div>
                  <div className="font-semibold text-[15px] leading-snug">{r.title}</div>
                  <div className="text-sm mt-0.5">
                    {r.kind === "meeting" ? "Starts" : "Due"} at <b>{fmtTime(r.time)}</b>
                    {r.end_time ? `–${fmtTime(r.end_time)}` : ""} · {relative(start - now)}
                  </div>
                  {r.subtitle && <div className="text-xs text-[var(--color-text-muted)] truncate mt-0.5">{r.subtitle}</div>}
                </div>
                <button type="button" onClick={() => update(keyOf(r), "dismissed")} aria-label="Dismiss reminder"
                        className="self-start text-[var(--color-text-muted)] hover:text-[var(--color-text)]"><X size={16} /></button>
              </div>
              <div className="flex justify-end gap-2 mt-3">
                <button type="button" className="lx-btn" onClick={() => update(keyOf(r), Date.now() + SNOOZE_MIN * 60000)}
                        data-testid={`reminder-snooze-${r.id}`}>Snooze {SNOOZE_MIN} min</button>
                <button type="button" className="lx-btn lx-btn-brand" onClick={() => { update(keyOf(r), "dismissed"); nav(r.link); }}
                        data-testid={`reminder-open-${r.id}`}>Open {r.kind === "meeting" ? "meeting" : "task"}</button>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

function KindTile({ kind }) {
  const Icon = kind === "meeting" ? CalendarDays : CheckSquare;
  return (
    <span className="lx-tile lx-tile-sm" style={{ background: kind === "meeting" ? "#EB7092" : "#4BC076" }} aria-hidden="true">
      <Icon size={14} />
    </span>
  );
}
