import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";

const BUCKETS = [
  { key: "overdue", label: "Overdue" },
  { key: "today", label: "Today" },
  { key: "tomorrow", label: "Tomorrow" },
  { key: "this_week", label: "This Week" },
  { key: "upcoming", label: "Upcoming" },
];

export default function QuoteFollowups() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("overdue");
  const [fAssigned, setFAssigned] = useState("All");
  const [fMinConfidence, setFMinConfidence] = useState("");

  useEffect(() => {
    api.get("/quotes/followups").then((r) => setData(r.data)).catch(() => toast.error("Couldn't load follow-ups"));
  }, []);

  const rows = data?.[tab] || [];
  const assignees = useMemo(() => {
    const all = Object.values(data || {}).flat();
    return ["All", ...new Set(all.map((r) => r.assigned_to).filter(Boolean))];
  }, [data]);

  const filtered = rows.filter((r) =>
    (fAssigned === "All" || r.assigned_to === fAssigned) &&
    (fMinConfidence === "" || (r.confidence_level ?? 0) >= parseFloat(fMinConfidence))
  );

  const counts = Object.fromEntries(BUCKETS.map((b) => [b.key, (data?.[b.key] || []).length]));

  return (
    <>
      <Topbar title="Sales Follow-ups" subtitle={data ? `${Object.values(data).flat().length} quotes with a scheduled follow-up` : "Loading…"} />
      <div className="p-6" data-testid="quote-followups-page">
        <div className="flex flex-wrap gap-2 mb-4">
          {BUCKETS.map((b) => (
            <button key={b.key} onClick={() => setTab(b.key)}
              className={`px-3.5 py-2 rounded-xl text-xs font-semibold transition border ${tab === b.key
                ? "bg-[var(--ink)] text-white border-[var(--ink)]" : "bg-white text-[var(--ink-2)] border-[var(--border)] hover:bg-[var(--surface-hover)]"}`}>
              {b.label} ({counts[b.key] ?? 0})
            </button>
          ))}
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          <select value={fAssigned} onChange={(e) => setFAssigned(e.target.value)} className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            {assignees.map((a) => <option key={a}>{a}</option>)}
          </select>
          <input type="number" placeholder="Min confidence %" value={fMinConfidence} onChange={(e) => setFMinConfidence(e.target.value)}
            className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm w-40" />
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="px-4 py-2.5">Customer</th>
                  <th className="px-4 py-2.5">Project</th>
                  <th className="px-4 py-2.5">Quote #</th>
                  <th className="px-4 py-2.5 text-right">Value</th>
                  <th className="px-4 py-2.5">Confidence</th>
                  <th className="px-4 py-2.5">Assigned</th>
                  <th className="px-4 py-2.5">Follow-up</th>
                  <th className="px-4 py-2.5">Last remark / type</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id} onClick={() => nav(`/quotes/ws/${r.id}`)} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50 cursor-pointer" data-testid={`followup-row-${r.id}`}>
                    <td className="px-4 py-3 font-medium">{r.customer}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{r.project_no || "—"}</td>
                    <td className="px-4 py-3 font-mono text-xs">{r.quote_no}</td>
                    <td className="px-4 py-3 text-right font-mono">{inrFull(r.value)}</td>
                    <td className="px-4 py-3">{r.confidence_level != null ? `${r.confidence_level}%` : "—"}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{r.assigned_to}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{fmtDate(r.next_follow_up)}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)] max-w-[260px]">
                      {r.last_kind && <span className="text-[10px] uppercase tracking-wide text-[var(--ink-3)] mr-1.5">{r.last_kind}</span>}
                      <span className="truncate">{r.last_remark}</span>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan="8" className="text-center py-12 text-[var(--ink-3)]">No quotes in this bucket</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
