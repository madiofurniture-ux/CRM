import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import api from "@/lib/api";
import { inr, inrFull } from "@/lib/format";
import { TrendingUp, Trophy, IndianRupee, HardHat, AlertTriangle } from "lucide-react";

export default function CommandCentre() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    api.get("/dashboard/stats", { skipCache: true }).then(({ data }) => setStats(data));
  }, []);

  return (
    <>
      <Topbar title="Command centre" subtitle="Role-aware view of the unit in scope — pipeline, readiness, and what you owe today." />
      <div className="p-6 space-y-6 max-w-[1600px]" data-testid="command-centre-page">
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <KpiCard label="Open Pipeline" value={inr(stats?.pipeline_value)} hint="Active quotes" accent="brand" icon={TrendingUp} testid="cc-kpi-pipeline" />
          <KpiCard label="Won This Month" value={inr(stats?.won_this_month_value)}
            hint={stats ? `${stats.won_this_month_count} order${stats.won_this_month_count === 1 ? "" : "s"}` : ""}
            accent="moss" icon={Trophy} testid="cc-kpi-won" />
          <KpiCard label="Receivables" value={inr(stats?.outstanding)} hint="Balance due across sales" accent="warn" icon={IndianRupee} testid="cc-kpi-receivables" />
          <KpiCard label="Projects Live" value={stats?.projects_live ?? 0}
            hint={stats ? `${stats.projects_at_risk} past target date` : ""} accent="brand" icon={HardHat} testid="cc-kpi-projects" />
          <KpiCard label="Overdue Follow-ups" value={stats?.overdue_followups ?? 0} hint="Needs action today" accent="danger" icon={AlertTriangle} testid="cc-kpi-overdue" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-5">
            <div className="font-heading font-semibold text-[var(--ink)] mb-1">Pipeline by Stage</div>
            <div className="text-xs text-[var(--ink-3)] mb-4">Open quote value, by stage</div>
            <div className="space-y-3">
              {(stats?.by_stage || []).map((s) => {
                const max = Math.max(1, ...(stats?.by_stage || []).map((x) => x.value));
                return (
                  <div key={s.stage}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-medium text-[var(--ink-2)]">{s.stage}</span>
                      <span className="text-[var(--ink-3)] font-mono">{s.count} · {inrFull(s.value)}</span>
                    </div>
                    <div className="h-2 rounded-full bg-[var(--surface-2)] overflow-hidden">
                      <div className="h-full rounded-full bg-[var(--brand)]" style={{ width: `${(s.value / max) * 100}%` }} />
                    </div>
                  </div>
                );
              })}
              {stats && stats.by_stage.length === 0 && <div className="text-sm text-[var(--ink-3)]">No open pipeline yet.</div>}
              {!stats && <div className="text-sm text-[var(--ink-3)]">Loading…</div>}
            </div>
          </div>

          <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-5">
            <div className="font-heading font-semibold text-[var(--ink)] mb-1">Revenue by Division</div>
            <div className="text-xs text-[var(--ink-3)] mb-4">All-time sales, by division</div>
            <div className="space-y-3">
              {(stats?.division_split || []).map((d) => {
                const max = Math.max(1, ...(stats?.division_split || []).map((x) => x.value));
                return (
                  <div key={d.division}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-medium text-[var(--ink-2)]">{d.division}</span>
                      <span className="text-[var(--ink-3)] font-mono">{inrFull(d.value)}</span>
                    </div>
                    <div className="h-2 rounded-full bg-[var(--surface-2)] overflow-hidden">
                      <div className="h-full rounded-full bg-[var(--moss)]" style={{ width: `${(d.value / max) * 100}%` }} />
                    </div>
                  </div>
                );
              })}
              {stats && stats.division_split.length === 0 && <div className="text-sm text-[var(--ink-3)]">No sales yet.</div>}
              {!stats && <div className="text-sm text-[var(--ink-3)]">Loading…</div>}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
