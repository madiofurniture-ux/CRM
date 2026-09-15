import { useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import FilterChips from "@/components/FilterChips";
import api from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { History, ShieldAlert, Download } from "lucide-react";

// Buckets the real action strings this codebase actually emits into the
// mockup's 8-category taxonomy. EXPORT/LOGIN/DENIED have no writer anywhere
// in server.py yet (no export-approval flow, no login/denial audit calls) —
// they stay selectable because the taxonomy is the point of the screen, but
// they will legitimately show zero rows until something writes them.
const ACTION_BUCKET = {
  create: "CREATE", update: "UPDATE", stage_change: "UPDATE", payment: "UPDATE",
  revise: "UPDATE", convert: "UPDATE", mark_absent: "UPDATE",
  delete: "DELETE",
  approve: "APPROVE", reject: "APPROVE", regularize: "APPROVE",
  user_role_assigned: "PERMISSION", user_team_assigned: "PERMISSION",
  user_deactivated: "PERMISSION", user_activated: "PERMISSION",
};
const ACTIONS = ["CREATE", "UPDATE", "DELETE", "APPROVE", "EXPORT", "PERMISSION", "LOGIN", "DENIED"];
const BADGE = {
  CREATE: "bg-emerald-50 text-emerald-700", UPDATE: "bg-blue-50 text-blue-700",
  DELETE: "bg-red-50 text-red-700", APPROVE: "bg-purple-50 text-purple-700",
  EXPORT: "bg-amber-50 text-amber-700", PERMISSION: "bg-indigo-50 text-indigo-700",
  LOGIN: "bg-slate-100 text-slate-700", DENIED: "bg-red-50 text-red-700", OTHER: "bg-slate-100 text-slate-600",
};
const WINDOWS = [
  { key: "24h", label: "Last 24h" }, { key: "7d", label: "7 days" },
  { key: "fy", label: "This FY" }, { key: "all", label: "All time" },
];

function bucketOf(action) {
  return ACTION_BUCKET[action] || "OTHER";
}

function diffText(before, after) {
  const keys = new Set([...Object.keys(before || {}), ...Object.keys(after || {})]);
  const parts = [];
  for (const k of keys) {
    const b = (before || {})[k], a = (after || {})[k];
    if (JSON.stringify(b) !== JSON.stringify(a)) parts.push(`${k}: ${JSON.stringify(b ?? "")} → ${JSON.stringify(a ?? "")}`);
  }
  return parts.join(" · ");
}

export default function AuditTrail() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [rows, setRows] = useState(null);
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [win, setWin] = useState("7d");

  useEffect(() => {
    if (!isAdmin) return;
    Promise.all([
      api.get("/activities").catch(() => ({ data: [] })),
      api.get("/audit-log").catch(() => ({ data: [] })),
    ]).then(([act, aud]) => {
      const a = (act.data || []).map((r) => ({
        id: r.id, at: r.at, actor: r.by_user, by_id: r.by_id,
        entity: r.entity, action: r.action, bucket: bucketOf(r.action),
        change: diffText(r.before, r.after) || r.note || "",
      }));
      const b = (aud.data || []).map((r) => ({
        id: r.id, at: r.created_at, actor: r.by_user, by_id: r.by_id,
        entity: "", action: r.action, bucket: bucketOf(r.action),
        change: r.detail || "",
      }));
      setRows([...a, ...b].sort((x, y) => new Date(y.at) - new Date(x.at)));
    });
  }, [isAdmin]);

  const filtered = useMemo(() => {
    if (!rows) return [];
    const now = Date.now();
    const cutMs = win === "24h" ? 86400000 : win === "7d" ? 7 * 86400000 : null;
    return rows.filter((r) => {
      if (actor && !(r.actor || "").toLowerCase().includes(actor.toLowerCase())) return false;
      if (action && r.bucket !== action) return false;
      if (entity && r.entity !== entity) return false;
      if (cutMs && now - new Date(r.at).getTime() > cutMs) return false;
      return true;
    });
  }, [rows, actor, action, entity, win]);

  const entities = useMemo(() => [...new Set((rows || []).map((r) => r.entity).filter(Boolean))], [rows]);

  const kpis = useMemo(() => {
    const all = rows || [];
    const today = new Date().toISOString().slice(0, 10);
    const eventsToday = all.filter((r) => (r.at || "").slice(0, 10) === today).length;
    const sevenDaysAgo = Date.now() - 7 * 86400000;
    const permChanges = all.filter((r) => r.bucket === "PERMISSION" && new Date(r.at).getTime() >= sevenDaysAgo).length;
    const exportsAwaiting = all.filter((r) => r.bucket === "EXPORT").length;
    return { eventsToday, permChanges, exportsAwaiting };
  }, [rows]);

  if (!isAdmin) {
    return (
      <>
        <Topbar title="Audit Trail" />
        <div className="flex items-center justify-center h-full p-10 text-center">
          <div>
            <h2 className="font-heading text-2xl text-[var(--ink)] mb-2">Admin access required</h2>
            <p className="text-[var(--ink-2)] text-sm">The audit trail is admin-only for now. Contact an admin.</p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Topbar title="Audit Trail" subtitle="Business-record changes and permission/security events, on one feed" />
      <div className="p-6 space-y-6" data-testid="audit-trail-page">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <KpiCard label="Events Today" value={kpis.eventsToday} icon={History} />
          <KpiCard label="Permission Changes (7d)" value={kpis.permChanges} icon={ShieldAlert} accent="warn" />
          <KpiCard label="Exports Awaiting Approval" value={kpis.exportsAwaiting} icon={Download} accent="neutral" />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="Filter by actor…"
            className="px-3 py-1.5 rounded-lg border border-[var(--border)] text-sm w-48" data-testid="audit-filter-actor" />
          <select value={entity} onChange={(e) => setEntity(e.target.value)}
            className="px-3 py-1.5 rounded-lg border border-[var(--border)] text-sm" data-testid="audit-filter-entity">
            <option value="">All entities</option>
            {entities.map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
          <FilterChips views={[{ key: "", label: "All actions" }, ...ACTIONS.map((a) => ({ key: a, label: a }))]}
            active={action} onChange={setAction} />
        </div>
        <FilterChips views={WINDOWS} active={win} onChange={setWin} />

        <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Timestamp</th>
                  <th className="text-left font-semibold px-4 py-2.5">Actor</th>
                  <th className="text-left font-semibold px-4 py-2.5">Entity</th>
                  <th className="text-left font-semibold px-4 py-2.5">Action</th>
                  <th className="text-left font-semibold px-4 py-2.5">Change</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--border-light)]">
                    <td className="px-4 py-2.5 font-mono text-xs text-[var(--ink-2)]">{fmtDateTime(r.at)}</td>
                    <td className="px-4 py-2.5">{r.actor || "—"}</td>
                    <td className="px-4 py-2.5 text-[var(--ink-2)]">{r.entity || "—"}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${BADGE[r.bucket]}`}>{r.action}</span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-[var(--ink-2)] max-w-md truncate" title={r.change}>{r.change || "—"}</td>
                  </tr>
                ))}
                {rows === null && <tr><td colSpan="5" className="text-center py-8 text-[var(--ink-3)]">Loading…</td></tr>}
                {rows !== null && filtered.length === 0 && <tr><td colSpan="5" className="text-center py-8 text-[var(--ink-3)]">No events match these filters.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
