import { useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { MapPin, LogIn, LogOut, Compass, Shield, Clock, CheckCircle2, XCircle } from "lucide-react";

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}
function durHM(min) {
  if (!min && min !== 0) return "—";
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${h}h ${m}m`;
}

export default function Attendance() {
  const { user: me } = useAuth();
  const [today, setToday] = useState(null);
  const [history, setHistory] = useState([]);
  const [teamToday, setTeamToday] = useState([]);
  const [office, setOffice] = useState(null);
  const [pos, setPos] = useState(null);
  const [posErr, setPosErr] = useState("");
  const [busy, setBusy] = useState(false);

  const isAdmin = me?.role === "admin";
  const todayStr = new Date().toISOString().slice(0, 10);

  const load = async () => {
    const [t, h, s] = await Promise.all([
      api.get("/attendance/today").catch(() => ({ data: null })),
      api.get("/attendance", { params: { days: 30 } }),
      api.get("/settings/office"),
    ]);
    setToday(t.data);
    setHistory(h.data);
    setOffice(s.data);
    if (isAdmin) {
      const tt = await api.get("/attendance", { params: { date: todayStr } });
      setTeamToday(tt.data);
    }
  };

  useEffect(() => { load(); }, []);

  const getPosition = () => {
    setPosErr("");
    if (!navigator.geolocation) { setPosErr("Geolocation not supported by this browser"); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => setPos({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy }),
      (e) => setPosErr(e.message || "Location permission denied"),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  useEffect(() => { getPosition(); }, []);

  const distance = useMemo(() => {
    if (!pos || !office) return null;
    const R = 6371000;
    const dLat = ((office.lat - pos.lat) * Math.PI) / 180;
    const dLng = ((office.lng - pos.lng) * Math.PI) / 180;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos((pos.lat * Math.PI) / 180) * Math.cos((office.lat * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }, [pos, office]);

  const within = distance != null && office && distance <= office.radius_m;

  const doCheckIn = async () => {
    if (!pos) { toast.error("Location not available"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/attendance/check-in", { lat: pos.lat, lng: pos.lng });
      setToday(data);
      if (data.check_in_within) toast.success("Checked in — within office");
      else toast.warning(`Checked in — outside office (${Math.round(data.check_in_distance)}m away)`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Check-in failed");
    }
    setBusy(false);
  };
  const doCheckOut = async () => {
    if (!pos) { toast.error("Location not available"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/attendance/check-out", { lat: pos.lat, lng: pos.lng });
      setToday(data);
      toast.success("Checked out");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Check-out failed");
    }
    setBusy(false);
  };

  const canCheckIn = !today?.check_in_at;
  const canCheckOut = today?.check_in_at && !today?.check_out_at;

  // Days present count
  const myHistory = history.filter((h) => h.user_id === me?.id);
  const daysPresent = new Set(myHistory.map((h) => h.date)).size;
  const monthlyMinutes = myHistory.reduce((a, b) => a + (b.duration_min || 0), 0);

  return (
    <>
      <Topbar title="Attendance" subtitle={office ? `${office.name} · geofence ${office.radius_m}m` : "Loading…"} />
      <div className="p-4 md:p-6 space-y-6" data-testid="attendance-page">
        {/* Check in card */}
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-widest text-[var(--ink-3)] font-semibold">Today</div>
              <div className="font-heading font-bold text-2xl text-[var(--ink)]">{new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</div>
              <div className="flex flex-wrap items-center gap-4 mt-3 text-sm">
                <span className="flex items-center gap-1.5 text-[var(--ink-2)]"><LogIn size={14} className="text-[var(--moss)]" />In {fmtTime(today?.check_in_at)}</span>
                <span className="flex items-center gap-1.5 text-[var(--ink-2)]"><LogOut size={14} className="text-[var(--brand)]" />Out {fmtTime(today?.check_out_at)}</span>
                <span className="flex items-center gap-1.5 text-[var(--ink-2)]"><Clock size={14} />{durHM(today?.duration_min)}</span>
              </div>
            </div>
            <div className="flex flex-col gap-2 min-w-[220px]">
              <button
                onClick={doCheckIn}
                disabled={!canCheckIn || busy || !pos}
                className={`px-4 py-3 rounded-lg font-heading font-semibold text-sm flex items-center justify-center gap-2 transition ${
                  canCheckIn && pos ? "bg-[var(--moss)] text-white hover:brightness-95" : "bg-[var(--surface-2)] text-[var(--ink-3)] cursor-not-allowed"
                }`}
                data-testid="checkin-btn"
              >
                <LogIn size={15} />
                {canCheckIn ? "Check In" : "Checked In"}
              </button>
              <button
                onClick={doCheckOut}
                disabled={!canCheckOut || busy || !pos}
                className={`px-4 py-3 rounded-lg font-heading font-semibold text-sm flex items-center justify-center gap-2 transition ${
                  canCheckOut && pos ? "bg-[var(--brand)] text-white hover:brightness-95" : "bg-[var(--surface-2)] text-[var(--ink-3)] cursor-not-allowed"
                }`}
                data-testid="checkout-btn"
              >
                <LogOut size={15} />
                {canCheckOut ? "Check Out" : today?.check_out_at ? "Checked Out" : "—"}
              </button>
            </div>
          </div>

          {/* Location state */}
          <div className="mt-5 pt-5 border-t border-[var(--border-light)] grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-widest text-[var(--ink-3)] font-semibold mb-1 flex items-center gap-1"><Compass size={11} />Your location</div>
              {posErr ? (
                <div className="text-xs text-[var(--danger)]">{posErr}</div>
              ) : pos ? (
                <div className="text-xs font-mono text-[var(--ink-2)]">
                  {pos.lat.toFixed(5)}, {pos.lng.toFixed(5)}
                  <span className="ml-2 text-[var(--ink-3)]">±{Math.round(pos.accuracy)}m</span>
                </div>
              ) : (
                <div className="text-xs text-[var(--ink-3)]">Fetching…</div>
              )}
              <button onClick={getPosition} className="text-[11px] text-[var(--brand)] mt-1 underline">Refresh location</button>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest text-[var(--ink-3)] font-semibold mb-1 flex items-center gap-1"><Shield size={11} />Office</div>
              <div className="text-xs font-mono text-[var(--ink-2)]">
                {office ? `${office.lat.toFixed(5)}, ${office.lng.toFixed(5)}` : "—"}
              </div>
              <div className="text-[11px] text-[var(--ink-3)]">{office?.address}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest text-[var(--ink-3)] font-semibold mb-1">Distance</div>
              {distance == null ? (
                <div className="text-xs text-[var(--ink-3)]">—</div>
              ) : (
                <div className={`text-lg font-heading font-bold ${within ? "text-[var(--moss)]" : "text-[var(--danger)]"}`}>
                  {distance < 1000 ? `${Math.round(distance)} m` : `${(distance / 1000).toFixed(2)} km`}
                </div>
              )}
              <div className={`text-[11px] font-semibold flex items-center gap-1 mt-1 ${within ? "text-[var(--moss)]" : "text-[var(--danger)]"}`}>
                {within ? <><CheckCircle2 size={12} />Inside geofence</> : <><XCircle size={12} />Outside geofence</>}
              </div>
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <KpiCard label="Days present (30d)" value={daysPresent} accent="moss" icon={CheckCircle2} />
          <KpiCard label="Hours worked (30d)" value={`${Math.floor(monthlyMinutes / 60)}h`} accent="brand" icon={Clock} />
          <KpiCard label="Avg per day" value={daysPresent ? durHM(Math.round(monthlyMinutes / daysPresent)) : "—"} accent="neutral" />
        </div>

        {/* Team today (admin) */}
        {isAdmin && (
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[var(--border-light)]">
              <div className="font-heading font-semibold text-[var(--ink)]">Team — today</div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[var(--surface-2)]">
                  <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                    <th className="text-left font-semibold px-4 py-2.5">User</th>
                    <th className="text-left font-semibold px-4 py-2.5">In</th>
                    <th className="text-left font-semibold px-4 py-2.5">Out</th>
                    <th className="text-left font-semibold px-4 py-2.5">Duration</th>
                    <th className="text-left font-semibold px-4 py-2.5">Geofence</th>
                  </tr>
                </thead>
                <tbody>
                  {teamToday.map((t) => (
                    <tr key={t.id} className="border-t border-[var(--border-light)]">
                      <td className="px-4 py-2.5 font-medium">{t.name}</td>
                      <td className="px-4 py-2.5 font-mono text-xs">{fmtTime(t.check_in_at)}</td>
                      <td className="px-4 py-2.5 font-mono text-xs">{fmtTime(t.check_out_at)}</td>
                      <td className="px-4 py-2.5 text-[var(--ink-2)]">{durHM(t.duration_min)}</td>
                      <td className="px-4 py-2.5">
                        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${t.check_in_within ? "bg-[var(--moss-soft)] text-[var(--moss)]" : "bg-[var(--danger-soft)] text-[var(--danger)]"}`}>
                          {t.check_in_within ? "Inside" : "Outside"} {t.check_in_distance != null && `· ${Math.round(t.check_in_distance)}m`}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {teamToday.length === 0 && <tr><td colSpan="5" className="text-center py-8 text-[var(--ink-3)]">No check-ins yet today</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* History */}
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="p-4 border-b border-[var(--border-light)]">
            <div className="font-heading font-semibold text-[var(--ink)]">Your last 30 days</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">In</th>
                  <th className="text-left font-semibold px-4 py-2.5">Out</th>
                  <th className="text-left font-semibold px-4 py-2.5">Duration</th>
                  <th className="text-left font-semibold px-4 py-2.5">Check-in geofence</th>
                </tr>
              </thead>
              <tbody>
                {myHistory.map((h) => (
                  <tr key={h.id} className="border-t border-[var(--border-light)]">
                    <td className="px-4 py-2.5">{fmtDate(h.date)}</td>
                    <td className="px-4 py-2.5 font-mono text-xs">{fmtTime(h.check_in_at)}</td>
                    <td className="px-4 py-2.5 font-mono text-xs">{fmtTime(h.check_out_at)}</td>
                    <td className="px-4 py-2.5 text-[var(--ink-2)]">{durHM(h.duration_min)}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full inline-flex items-center gap-1 ${h.check_in_within ? "bg-[var(--moss-soft)] text-[var(--moss)]" : "bg-[var(--danger-soft)] text-[var(--danger)]"}`}>
                        <MapPin size={10} />{h.check_in_within ? "Inside" : "Outside"}{h.check_in_distance != null ? ` · ${Math.round(h.check_in_distance)}m` : ""}
                      </span>
                    </td>
                  </tr>
                ))}
                {myHistory.length === 0 && <tr><td colSpan="5" className="text-center py-8 text-[var(--ink-3)]">No attendance history yet</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
