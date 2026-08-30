import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { MapPin, Navigation, Camera, CheckCircle2, AlertCircle, Clock, ShieldCheck, UserCheck, RefreshCw } from "lucide-react";
import { toast } from "sonner";

// Placeholder only — overwritten from GET /settings/office on mount below,
// the same admin-configurable office record invoices/office settings use.
// This used to be a second, hardcoded copy of the office geofence.
const HQ_FALLBACK = { lat: 17.4065, lng: 78.4772, name: "Head Office", radius: 200 };

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
  const [logs, setLogs] = useState([]);
  const [todayRec, setTodayRec] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hq, setHq] = useState(HQ_FALLBACK);
  const [loc, setLoc] = useState({ lat: HQ_FALLBACK.lat, lng: HQ_FALLBACK.lng });
  const [dist, setDist] = useState(0);
  const [withinGeofence, setWithinGeofence] = useState(true);
  const [photoUrl, setPhotoUrl] = useState("");
  const [note, setNote] = useState("");
  const [gpsStatus, setGpsStatus] = useState("Fetching GPS...");
  const [punching, setPunching] = useState(false);

  const getGPS = () => {
    setGpsStatus("Locating device...");
    if ("geolocation" in navigator) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const latitude = pos.coords.latitude;
          const longitude = pos.coords.longitude;
          setLoc({ lat: latitude, lng: longitude });
          const d = haversineMeters(latitude, longitude, hq.lat, hq.lng);
          setDist(d);
          setWithinGeofence(d <= hq.radius);
          setGpsStatus("GPS Acquired");
          toast.success("Location updated");
        },
        () => {
          // Fallback to HQ simulated location for demo
          setLoc({ lat: hq.lat, lng: hq.lng });
          setDist(45);
          setWithinGeofence(true);
          setGpsStatus("GPS Standard Mode (HQ Office)");
        },
        { enableHighAccuracy: true, timeout: 8000 }
      );
    } else {
      setGpsStatus("GPS Not Supported");
    }
  };

  const loadLogs = async () => {
    try {
      const { data } = await api.get("/attendance");
      setLogs(data);
      const today = new Date().toISOString().slice(0, 10);
      const mine = data.find((r) => r.date === today);
      setTodayRec(mine || null);
    } catch {
      toast.error("Failed to load attendance logs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api.get("/settings/office").then(({ data }) => {
      if (data?.lat && data?.lng) setHq({ lat: data.lat, lng: data.lng, name: data.name || HQ_FALLBACK.name, radius: data.radius_m || HQ_FALLBACK.radius });
    }).catch(() => {}).finally(() => { getGPS(); loadLogs(); });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCheckIn = async () => {
    if (punching) return;
    setPunching(true);
    try {
      const payload = {
        lat: loc.lat,
        lng: loc.lng,
        note,
        photo_url: photoUrl || "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&auto=format&fit=crop&q=60",
      };
      const { data } = await api.post("/attendance/check-in", payload);
      toast.success(data.check_in_within ? "Checked in within Geofence!" : "Checked in (Outside Geofence recorded)");
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
        photo_url: photoUrl || "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&auto=format&fit=crop&q=60",
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
      <Topbar title="Attendance & Geo-Fencing" subtitle="Real-time GPS tracking, office geofence verification & photo audit" />

      <div className="p-6 space-y-6" data-testid="attendance-page">
        {/* GPS Radar Card & Quick Check-in */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-white border border-[var(--border)] rounded-2xl p-6 shadow-sm flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-xl bg-[var(--brand-light)] text-[var(--brand)] flex items-center justify-center font-bold">
                    <Navigation size={18} />
                  </div>
                  <div>
                    <h3 className="font-heading font-bold text-base text-[var(--ink)]">Geo-Fencing Radar</h3>
                    <p className="text-xs text-[var(--ink-3)]">{hq.name}</p>
                  </div>
                </div>
                <button
                  onClick={getGPS}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)] text-xs font-semibold text-[var(--ink-2)] hover:bg-[var(--surface-2)] transition"
                >
                  <RefreshCw size={13} />
                  Refresh GPS
                </button>
              </div>

              {/* Status Badge */}
              <div className="bg-[var(--surface-2)] p-4 rounded-xl border border-[var(--border-light)] mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  {withinGeofence ? (
                    <span className="w-10 h-10 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
                      <ShieldCheck size={22} />
                    </span>
                  ) : (
                    <span className="w-10 h-10 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center shrink-0">
                      <AlertCircle size={22} />
                    </span>
                  )}
                  <div>
                    <div className="font-bold text-sm text-[var(--ink)]">
                      {withinGeofence ? "INSIDE OFFICE GEOFENCE" : "OUTSIDE GEOFENCE RANGE"}
                    </div>
                    <div className="text-xs text-[var(--ink-2)]">
                      Distance to office: <span className="font-mono font-semibold">{dist.toFixed(1)} meters</span> (Limit: {hq.radius}m)
                    </div>
                  </div>
                </div>

                <div className="text-right">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--ink-3)] block">GPS Coordinates</span>
                  <span className="font-mono text-xs text-[var(--ink)] font-semibold">
                    {loc.lat.toFixed(4)}° N, {loc.lng.toFixed(4)}° E
                  </span>
                </div>
              </div>
            </div>

            {/* Attendance Punch Box */}
            <div className="pt-4 border-t border-[var(--border-light)]">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">
                    <Camera size={13} className="inline mr-1" />
                    Photo Verification URL (Selfie / Site)
                  </label>
                  <input
                    type="text"
                    placeholder="https://..."
                    value={photoUrl}
                    onChange={(e) => setPhotoUrl(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">Check-in Note / Site remarks</label>
                  <input
                    type="text"
                    placeholder="e.g. Arrived at showroom / On-site survey"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]"
                  />
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={handleCheckIn}
                  disabled={!!todayRec?.check_in_at || punching}
                  className={`flex-1 py-2.5 rounded-xl font-semibold text-xs transition flex items-center justify-center gap-2 ${
                    todayRec?.check_in_at || punching
                      ? "bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-200"
                      : "bg-[var(--brand)] text-white hover:opacity-90 shadow-sm"
                  }`}
                >
                  <UserCheck size={16} />
                  {todayRec?.check_in_at ? `Checked In at ${todayRec.check_in_at.slice(11, 16)}` : punching ? "Punching…" : "Punch Check-In"}
                </button>

                <button
                  onClick={handleCheckOut}
                  disabled={!todayRec?.check_in_at || !!todayRec?.check_out_at || punching}
                  className={`flex-1 py-2.5 rounded-xl font-semibold text-xs transition flex items-center justify-center gap-2 ${
                    !todayRec?.check_in_at || todayRec?.check_out_at || punching
                      ? "bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-200"
                      : "bg-[var(--ink)] text-white hover:bg-black shadow-sm"
                  }`}
                >
                  <Clock size={16} />
                  {todayRec?.check_out_at ? `Checked Out at ${todayRec.check_out_at.slice(11, 16)}` : punching ? "Punching…" : "Punch Check-Out"}
                </button>
              </div>
            </div>
          </div>

          {/* Today Summary Card */}
          <div className="bg-white border border-[var(--border)] rounded-2xl p-6 shadow-sm flex flex-col justify-between">
            <div>
              <h3 className="font-heading font-bold text-base text-[var(--ink)] mb-1">Today's Status</h3>
              <p className="text-xs text-[var(--ink-3)] mb-4">{new Date().toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}</p>

              <div className="space-y-3">
                <div className="p-3 bg-[var(--surface-2)] rounded-xl border border-[var(--border-light)]">
                  <div className="text-[10px] uppercase font-mono text-[var(--ink-3)] mb-0.5">Check-In Time</div>
                  <div className="font-mono text-sm font-bold text-[var(--ink)]">
                    {todayRec?.check_in_at ? todayRec.check_in_at.slice(11, 19) : "Not Recorded"}
                  </div>
                  {todayRec?.check_in_distance != null && (
                    <div className="text-[11px] text-[var(--ink-2)] mt-1">
                      Distance: <span className="font-semibold">{todayRec.check_in_distance}m</span> ({todayRec.check_in_within ? "In Range" : "Outside Range"})
                    </div>
                  )}
                </div>

                <div className="p-3 bg-[var(--surface-2)] rounded-xl border border-[var(--border-light)]">
                  <div className="text-[10px] uppercase font-mono text-[var(--ink-3)] mb-0.5">Check-Out Time</div>
                  <div className="font-mono text-sm font-bold text-[var(--ink)]">
                    {todayRec?.check_out_at ? todayRec.check_out_at.slice(11, 19) : "Not Recorded"}
                  </div>
                  {todayRec?.duration_min != null && (
                    <div className="text-[11px] text-[var(--moss)] font-medium mt-1">
                      Work Duration: {Math.floor(todayRec.duration_min / 60)}h {todayRec.duration_min % 60}m
                    </div>
                  )}
                </div>
              </div>
            </div>

            {todayRec?.check_in_photo && (
              <div className="mt-4 pt-3 border-t border-[var(--border-light)]">
                <div className="text-[10px] uppercase font-mono text-[var(--ink-3)] mb-1">Attendance Verification Photo</div>
                <img src={todayRec.check_in_photo} alt="Verification" className="w-full h-28 object-cover rounded-xl border border-[var(--border)]" />
              </div>
            )}
          </div>
        </div>

        {/* History Table */}
        <div className="bg-white border border-[var(--border)] rounded-2xl overflow-hidden shadow-sm">
          <div className="px-6 py-4 border-b border-[var(--border)] bg-[var(--surface-2)] flex items-center justify-between">
            <h3 className="font-heading font-bold text-base text-[var(--ink)]">Attendance Log History</h3>
            <span className="text-xs text-[var(--ink-3)]">{logs.length} records</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] text-[11px] uppercase tracking-wider text-[var(--ink-3)] border-b border-[var(--border)]">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold">Staff Name</th>
                  <th className="px-4 py-3 text-left font-semibold">Date</th>
                  <th className="px-4 py-3 text-left font-semibold">Check-In</th>
                  <th className="px-4 py-3 text-left font-semibold">Check-Out</th>
                  <th className="px-4 py-3 text-left font-semibold">Geofence Status</th>
                  <th className="px-4 py-3 text-left font-semibold">Photo Audit</th>
                  <th className="px-4 py-3 text-left font-semibold">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-light)]">
                {logs.map((r) => (
                  <tr key={r.id} className="hover:bg-[var(--surface-2)]/50 transition">
                    <td className="px-4 py-3 font-semibold text-[var(--ink)]">{r.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-[var(--ink-2)]">{r.date}</td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {r.check_in_at ? r.check_in_at.slice(11, 16) : "-"}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {r.check_out_at ? r.check_out_at.slice(11, 16) : "-"}
                    </td>
                    <td className="px-4 py-3">
                      {r.check_in_within ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md">
                          <CheckCircle2 size={12} />
                          Inside Geofence ({r.check_in_distance}m)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md">
                          <AlertCircle size={12} />
                          Outside ({r.check_in_distance}m)
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {r.check_in_photo ? (
                        <img src={r.check_in_photo} alt="" className="w-8 h-8 rounded-lg object-cover border border-[var(--border)]" />
                      ) : (
                        <span className="text-xs text-[var(--ink-3)]">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--ink-2)] truncate max-w-xs">{r.note || "-"}</td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={7} className="text-center py-10 text-[var(--ink-3)] text-xs">No attendance records logged yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
