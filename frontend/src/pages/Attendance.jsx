import { useCallback, useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { MapPin, Navigation, Camera, CheckCircle2, AlertCircle, Clock, ShieldCheck, UserCheck, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import AttendanceExceptionDrawer from "@/components/AttendanceExceptionDrawer";
import { useAuth } from "@/context/AuthContext";
import MetricCard from "@/components/MetricCard";
import ErrorState from "@/components/ErrorState";
import EmptyState from "@/components/EmptyState";

// Real, supported query params only — GET /attendance takes `date`,
// `user_id`, `days`, nothing else (no true from/to range exists server-side,
// see server.py's list_attendance). "Range" here means "last N days," the
// one real range concept the API has.
const RANGE_OPTIONS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

// A row is an "exception" if the punch itself flagged it (outside geofence)
// or it's a PAST day still missing a check-out (today's in-progress shift is
// not an exception — mirrors the only two failure states check-in/check-out
// actually record; see server.py's check_in/check_out).
const isException = (r) => {
  if (r.status === "flagged_out_of_bounds") return true;
  const today = new Date().toISOString().slice(0, 10);
  return !!(r.check_in_at && !r.check_out_at && r.date !== today);
};

// Placeholder only — overwritten from GET /attendance/geofence as soon as GPS
// lands. That endpoint runs the server's own _resolve_geofence, which is what
// the punch is judged against: the nearest of the user's assigned sites, or
// the office when they have none. The preview used to measure against
// /settings/office regardless, so anyone with an assigned site saw a distance
// to a place their check-in was never going to be compared with.
const HQ_FALLBACK = { lat: 17.4065, lng: 78.4772, name: "Head Office", radius: 200 };

// A stable per-browser id sent with each punch, so an attendance dispute can
// be tied to a device without the server keeping the raw location trail.
function deviceId() {
  let id = localStorage.getItem("crm_device_id");
  if (!id) {
    id = `web-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem("crm_device_id", id);
  }
  return id;
}

function haversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000; // meters
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

export default function Attendance() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [logs, setLogs] = useState([]);
  const [todayRec, setTodayRec] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [range, setRange] = useState("30");
  const [employeeId, setEmployeeId] = useState(""); // admin-only filter
  const [employees, setEmployees] = useState([]);
  const [hq, setHq] = useState(HQ_FALLBACK);
  const [loc, setLoc] = useState({ lat: HQ_FALLBACK.lat, lng: HQ_FALLBACK.lng });
  // null = not known yet (no GPS / fence unresolved) — deliberately not
  // "inside", so the card can't claim a verdict it hasn't earned.
  const [dist, setDist] = useState(null);
  const [withinGeofence, setWithinGeofence] = useState(null);
  const [photoUrl, setPhotoUrl] = useState("");
  const [note, setNote] = useState("");
  const [gpsStatus, setGpsStatus] = useState("Fetching GPS...");
  const [punching, setPunching] = useState(false);
  const [selectedRow, setSelectedRow] = useState(null);

  // Ask the server which fence this punch would be judged against, then
  // measure to that. The resolution rules (nearest assigned site, skip
  // inactive, fall back to the office) stay in one place — re-deriving them
  // here is how the preview drifted out of step with check-in to begin with.
  const applyResolvedFence = async (latitude, longitude) => {
    const { data } = await api.get("/attendance/geofence", { params: { lat: latitude, lng: longitude } });
    const fence = { lat: data.lat, lng: data.lng, name: data.site_name || HQ_FALLBACK.name, radius: data.radius_m };
    setHq(fence);
    const d = haversineMeters(latitude, longitude, fence.lat, fence.lng);
    setDist(d);
    setWithinGeofence(d <= fence.radius);
  };

  const getGPS = () => {
    setGpsStatus("Locating device...");
    if (!("geolocation" in navigator)) return setGpsStatus("GPS Not Supported");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const latitude = pos.coords.latitude;
        const longitude = pos.coords.longitude;
        setLoc({ lat: latitude, lng: longitude });
        try {
          await applyResolvedFence(latitude, longitude);
          setGpsStatus("GPS Acquired");
          toast.success("Location updated");
        } catch {
          // Don't invent a verdict from a fence we couldn't resolve — the
          // punch itself still validates server-side.
          setDist(null);
          setWithinGeofence(null);
          setGpsStatus("Could not resolve your site — check-in will still verify");
        }
      },
      () => {
        // No position, so "nearest assigned site" has no meaning and neither
        // does a distance. The old code invented 45m/inside here, which is
        // the same misleading preview this screen is being fixed for.
        setDist(null);
        setWithinGeofence(null);
        setGpsStatus("GPS unavailable — distance is checked when you punch");
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const params = { days: range };
      if (isAdmin && employeeId) params.user_id = employeeId;
      const { data } = await api.get("/attendance", { params });
      setLogs(data);
      const today = new Date().toISOString().slice(0, 10);
      const mine = data.find((r) => r.date === today);
      setTodayRec(mine || null);
    } catch (e) {
      toast.error("Failed to load attendance logs");
      setLoadError(e?.response?.status === 401 || e?.response?.status === 403 ? "unauthorized" : "error");
    } finally {
      setLoading(false);
    }
  }, [range, employeeId, isAdmin]);

  useEffect(() => { getGPS(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadLogs(); }, [loadLogs]);
  useEffect(() => {
    // Employee directory only fetched for admins — the only role the
    // backend even accepts a `user_id` filter from (list_attendance's own
    // 403 check). Real API, same one Leads/Payroll already use.
    if (isAdmin) api.get("/users/directory").then(({ data }) => setEmployees(data)).catch(() => setEmployees([]));
  }, [isAdmin]);

  // Real counts only, derived from the rows already loaded for the
  // selected range — no separate "summary" endpoint exists for this
  // attendance system, and no fabricated Late/LOP/Holiday concept (this
  // collection has neither — see docs/LIGHT_PEOPLE_UI.md).
  const summary = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    let present = 0, absent = 0, openExceptions = 0, overtimeHours = 0;
    for (const r of logs) {
      if (r.status === "absent") absent++;
      else if (r.check_in_at) present++;
      const flagged = r.status === "flagged_out_of_bounds";
      const missingCheckout = !!r.check_in_at && !r.check_out_at && r.date !== today;
      if ((flagged || missingCheckout) && r.status !== "regularized" && r.status !== "absent") openExceptions++;
      if (r.duration_min) overtimeHours += Math.max(0, r.duration_min - 8 * 60) / 60;
    }
    return { present, absent, openExceptions, overtimeHours: Math.round(overtimeHours * 10) / 10 };
  }, [logs]);

  const handleCheckIn = async () => {
    if (punching) return;
    setPunching(true);
    try {
      const payload = {
        lat: loc.lat,
        lng: loc.lng,
        note,
        photo_url: photoUrl,
        device_id: deviceId(),
      };
      const { data } = await api.post("/attendance/check-in", payload);
      toast.success(data.verified
        ? `Checked in at ${data.site_name || "office"} — inside geofence`
        : `Checked in ${data.distance_variance_m}m away — flagged for review`);
      setPhotoUrl("");
      setNote("");
      loadLogs();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Check-in failed");
    } finally {
      setPunching(false);
    }
  };

  const handleCheckOut = async () => {
    if (punching) return;
    setPunching(true);
    try {
      const payload = {
        lat: loc.lat,
        lng: loc.lng,
        note,
        photo_url: photoUrl,
        device_id: deviceId(),
      };
      await api.post("/attendance/check-out", payload);
      toast.success("Checked out successfully");
      setPhotoUrl("");
      setNote("");
      loadLogs();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Check-out failed");
    } finally {
      setPunching(false);
    }
  };

  return (
    <>
      <Topbar
        title="Attendance & Geo-Fencing"
        subtitle="Real-time GPS tracking, office geofence verification & photo audit"
        actions={
          <>
            <select
              aria-label="Date range"
              value={range}
              onChange={(e) => setRange(e.target.value)}
              className="px-3 py-2 text-sm rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)]"
            >
              {RANGE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            {isAdmin && (
              <select
                aria-label="Employee"
                value={employeeId}
                onChange={(e) => setEmployeeId(e.target.value)}
                className="px-3 py-2 text-sm rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] max-w-[160px]"
              >
                <option value="">Everyone</option>
                {employees.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
              </select>
            )}
            <button
              type="button"
              onClick={loadLogs}
              aria-label="Refresh attendance"
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-2 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-muted)] disabled:opacity-50"
            >
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
            </button>
          </>
        }
      />

      <div className="p-6 space-y-6" data-testid="attendance-page">
        {/* Summary cards — real counts from the rows loaded for this range only */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard label="Present" value={loading ? null : String(summary.present)} sub={`in the last ${range} days`} loading={loading} />
          <MetricCard label="Absent" value={loading ? null : String(summary.absent)} sub="marked absent" loading={loading} />
          <MetricCard label="Overtime" value={loading ? null : `${summary.overtimeHours}h`} sub="beyond an 8h day" loading={loading} />
          <MetricCard label="Open exceptions" value={loading ? null : String(summary.openExceptions)} sub="need regularizing" loading={loading} />
        </div>

        {loadError ? (
          <ErrorState
            title={loadError === "unauthorized" ? "You don't have access to this view" : "Couldn't load attendance"}
            hint={loadError === "unauthorized" ? undefined : "The attendance log didn't load — check your connection and try again."}
            onRetry={loadError === "unauthorized" ? undefined : loadLogs}
          />
        ) : (
        <>
        {/* GPS Radar Card & Quick Check-in */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl p-6 shadow-sm flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-xl bg-[var(--color-primary-soft)] text-[var(--color-primary)] flex items-center justify-center font-bold">
                    <Navigation size={18} />
                  </div>
                  <div>
                    <h3 className="font-heading font-bold text-base text-[var(--color-text)]">Geo-Fencing Radar</h3>
                    <p className="text-xs text-[var(--color-text-muted)]">{hq.name}</p>
                  </div>
                </div>
                <button
                  onClick={getGPS}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--color-border)] text-xs font-semibold text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)] transition"
                >
                  <RefreshCw size={13} />
                  Refresh GPS
                </button>
              </div>

              {/* Status Badge */}
              <div className="bg-[var(--color-surface-muted)] p-4 rounded-xl border border-[var(--color-border)] mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  {withinGeofence === null ? (
                    <span className="w-10 h-10 rounded-full bg-[var(--color-surface)] text-[var(--color-text-muted)] flex items-center justify-center shrink-0">
                      <Navigation size={22} />
                    </span>
                  ) : withinGeofence ? (
                    <span className="w-10 h-10 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
                      <ShieldCheck size={22} />
                    </span>
                  ) : (
                    <span className="w-10 h-10 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center shrink-0">
                      <AlertCircle size={22} />
                    </span>
                  )}
                  <div>
                    <div className="font-bold text-sm text-[var(--color-text)]" data-testid="geofence-verdict">
                      {withinGeofence === null ? "LOCATION NOT CONFIRMED"
                        : withinGeofence ? `INSIDE ${hq.name.toUpperCase()} GEOFENCE` : "OUTSIDE GEOFENCE RANGE"}
                    </div>
                    <div className="text-xs text-[var(--color-text-muted)]">
                      {dist === null
                        ? gpsStatus
                        : <>Distance to {hq.name}: <span className="font-mono font-semibold">{dist.toFixed(1)} meters</span> (Limit: {hq.radius}m)</>}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Attendance Punch Box */}
            <div className="pt-4 border-t border-[var(--color-border)]">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">
                    <Camera size={13} className="inline mr-1" />
                    Photo Verification URL (Selfie / Site)
                  </label>
                  <input
                    type="text"
                    placeholder="https://..."
                    value={photoUrl}
                    onChange={(e) => setPhotoUrl(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] outline-none focus:border-[var(--color-primary)]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Check-in Note / Site remarks</label>
                  <input
                    type="text"
                    placeholder="e.g. Arrived at showroom / On-site survey"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--color-border)] outline-none focus:border-[var(--color-primary)]"
                  />
                </div>
              </div>

              {/* Stacked full-width on a phone — this is punched one-handed
                  at a site gate, so the targets are thumb-sized there. */}
              <div className="flex flex-col sm:flex-row items-stretch gap-3">
                <button
                  onClick={handleCheckIn}
                  disabled={!!todayRec?.check_in_at || punching}
                  className={`flex-1 py-3.5 sm:py-2.5 rounded-xl font-semibold text-sm sm:text-xs transition flex items-center justify-center gap-2 ${
                    todayRec?.check_in_at || punching
                      ? "bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-200"
                      : "bg-[var(--color-primary)] text-white hover:opacity-90 shadow-sm"
                  }`}
                >
                  <UserCheck size={16} />
                  {todayRec?.check_in_at ? `Checked In at ${todayRec.check_in_at.slice(11, 16)}` : punching ? "Punching…" : "Punch Check-In"}
                </button>

                <button
                  onClick={handleCheckOut}
                  disabled={!todayRec?.check_in_at || !!todayRec?.check_out_at || punching}
                  className={`flex-1 py-3.5 sm:py-2.5 rounded-xl font-semibold text-sm sm:text-xs transition flex items-center justify-center gap-2 ${
                    !todayRec?.check_in_at || todayRec?.check_out_at || punching
                      ? "bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-200"
                      : "bg-[var(--color-text)] text-white hover:bg-black shadow-sm"
                  }`}
                >
                  <Clock size={16} />
                  {todayRec?.check_out_at ? `Checked Out at ${todayRec.check_out_at.slice(11, 16)}` : punching ? "Punching…" : "Punch Check-Out"}
                </button>
              </div>
            </div>
          </div>

          {/* Today Summary Card */}
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl p-6 shadow-sm flex flex-col justify-between">
            <div>
              <h3 className="font-heading font-bold text-base text-[var(--color-text)] mb-1">Today's Status</h3>
              <p className="text-xs text-[var(--color-text-muted)] mb-4">{new Date().toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}</p>

              <div className="space-y-3">
                <div className="p-3 bg-[var(--color-surface-muted)] rounded-xl border border-[var(--color-border)]">
                  <div className="text-[10px] uppercase font-mono text-[var(--color-text-muted)] mb-0.5">Check-In Time</div>
                  <div className="font-mono text-sm font-bold text-[var(--color-text)]">
                    {todayRec?.check_in_at ? todayRec.check_in_at.slice(11, 19) : "Not Recorded"}
                  </div>
                  {todayRec?.distance_variance_m != null && (
                    <div className="text-[11px] text-[var(--color-text-muted)] mt-1">
                      Distance: <span className="font-semibold">{todayRec.distance_variance_m}m</span> ({todayRec.verified ? "In Range" : "Outside Range"})
                      {todayRec.site_name ? ` · ${todayRec.site_name}` : ""}
                    </div>
                  )}
                </div>

                <div className="p-3 bg-[var(--color-surface-muted)] rounded-xl border border-[var(--color-border)]">
                  <div className="text-[10px] uppercase font-mono text-[var(--color-text-muted)] mb-0.5">Check-Out Time</div>
                  <div className="font-mono text-sm font-bold text-[var(--color-text)]">
                    {todayRec?.check_out_at ? todayRec.check_out_at.slice(11, 19) : "Not Recorded"}
                  </div>
                  {todayRec?.duration_min != null && (
                    <div className="text-[11px] text-[var(--color-success)] font-medium mt-1">
                      Work Duration: {Math.floor(todayRec.duration_min / 60)}h {todayRec.duration_min % 60}m
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* The selfie itself is never returned to the browser — only
                whether one was captured. Raw GPS and the photo are readable
                only through the admin-gated single-record audit route. */}
            {todayRec?.selfie_verified && (
              <div className="mt-4 pt-3 border-t border-[var(--color-border)] flex items-center gap-2">
                <ShieldCheck size={15} className="text-[var(--color-primary)]" />
                <span className="text-xs font-semibold text-[var(--color-text-muted)]">Verification selfie captured</span>
              </div>
            )}
          </div>
        </div>

        {/* History Table */}
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl overflow-hidden shadow-sm">
          <div className="px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] flex items-center justify-between">
            <h3 className="font-heading font-bold text-base text-[var(--color-text)]">Attendance Log History</h3>
            <span className="text-xs text-[var(--color-text-muted)]">{logs.length} records</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--color-surface-muted)] text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold">Staff Name</th>
                  <th className="px-4 py-3 text-left font-semibold">Date</th>
                  <th className="px-4 py-3 text-left font-semibold">Check-In</th>
                  <th className="px-4 py-3 text-left font-semibold">Check-Out</th>
                  <th className="px-4 py-3 text-right font-semibold">Worked</th>
                  <th className="px-4 py-3 text-left font-semibold">Site</th>
                  <th className="px-4 py-3 text-left font-semibold">Status</th>
                  <th className="px-4 py-3 text-left font-semibold">Selfie</th>
                  <th className="px-4 py-3 text-left font-semibold">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {logs.map((r) => (
                  <tr key={r.id}
                    onClick={() => isException(r) && setSelectedRow(r)}
                    onKeyDown={(e) => { if (isException(r) && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); setSelectedRow(r); } }}
                    tabIndex={isException(r) ? 0 : undefined}
                    role={isException(r) ? "button" : undefined}
                    aria-label={isException(r) ? `Open exception for ${r.name} on ${r.date}` : undefined}
                    className={`hover:bg-[var(--color-surface-muted)]/50 transition ${isException(r) ? "cursor-pointer focus-visible:bg-[var(--color-surface-muted)]" : ""}`}
                    data-testid={`attendance-row-${r.id}`}>
                    <td className="px-4 py-3 font-semibold text-[var(--color-text)]">{r.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-[var(--color-text-muted)]">{r.date}</td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {r.check_in_at ? r.check_in_at.slice(11, 16) : "-"}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {r.check_out_at ? r.check_out_at.slice(11, 16) : "-"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-[var(--color-text-muted)]">
                      {r.duration_min ? `${Math.floor(r.duration_min / 60)}h ${r.duration_min % 60}m` : "-"}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-text-muted)]">{r.site_name || "Office"}</td>
                    <td className="px-4 py-3">
                      {r.status === "regularized" ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--color-primary)] bg-[var(--color-primary-soft)] px-2 py-0.5 rounded-md">
                          <ShieldCheck size={12} /> Regularized
                        </span>
                      ) : r.status === "absent" ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--color-danger)] bg-[var(--color-danger)]/10 px-2 py-0.5 rounded-md">
                          <AlertCircle size={12} /> Absent
                        </span>
                      ) : r.verified ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md">
                          <CheckCircle2 size={12} />
                          Inside geofence ({r.distance_variance_m}m)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md">
                          <AlertCircle size={12} />
                          Outside ({r.distance_variance_m}m)
                        </span>
                      )}
                    </td>
                    {/* Selfie and GPS are deliberately NOT in this response —
                        the server returns the verification outcome only. */}
                    <td className="px-4 py-3">
                      {r.selfie_verified ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--color-primary)] bg-[var(--color-primary-soft)] px-2 py-0.5 rounded-md">
                          <ShieldCheck size={12} />
                          Verified
                        </span>
                      ) : (
                        <span className="text-xs text-[var(--color-text-muted)]">None</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--color-text-muted)] truncate max-w-xs">{r.note || "-"}</td>
                  </tr>
                ))}
                {loading && Array.from({ length: 4 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={9} className="px-4 py-3">
                      <div className="h-4 w-full bg-[var(--color-surface-muted)] rounded animate-pulse" />
                    </td>
                  </tr>
                ))}
                {!loading && logs.length === 0 && (
                  <tr>
                    <td colSpan={9}>
                      <EmptyState icon={UserCheck} title="No attendance records" hint="Punches logged in this range will show up here." />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        </>
        )}
      </div>
      <AttendanceExceptionDrawer record={selectedRow} onClose={() => setSelectedRow(null)} onChanged={loadLogs} />
    </>
  );
}
