import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import StageBadge from "@/components/StageBadge";
import api from "@/lib/api";
import { inr, inrFull, fmtDate } from "@/lib/format";
import { TrendingUp, Receipt, Package, Users, Calendar, AlertTriangle, IndianRupee } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from "recharts";

const DIVISION_COLORS = ["#C85A32", "#4A5D4E", "#D48B30", "#8A8C8A", "#B24040"];

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [quotes, setQuotes] = useState([]);
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [s, q, l] = await Promise.all([
        api.get("/dashboard/stats"),
        api.get("/quotes"),
        api.get("/leads"),
      ]);
      setStats(s.data);
      setQuotes(q.data);
      setLeads(l.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const today = new Date().toISOString().slice(0, 10);
  const overdue = leads.filter((l) => l.follow_up_date && l.follow_up_date < today && !["Won", "Lost"].includes(l.stage)).slice(0, 6);

  return (
    <>
      <Topbar title="Dashboard" subtitle="Live snapshot of your business" />
      <div className="p-6 space-y-6 max-w-[1600px]" data-testid="dashboard-page">
        {/* KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          <KpiCard label="Pipeline" value={inr(stats?.pipeline_value)} hint="Open quotes" accent="brand" icon={TrendingUp} testid="kpi-pipeline" />
          <KpiCard label="Total Sales" value={inr(stats?.total_sales)} hint="All time" accent="moss" icon={Receipt} testid="kpi-sales" />
          <KpiCard label="Outstanding" value={inr(stats?.outstanding)} hint="To collect" accent="warn" icon={IndianRupee} testid="kpi-outstanding" />
          <KpiCard label="Stock MRP" value={inr(stats?.stock_mrp)} hint="Inventory value" accent="neutral" icon={Package} testid="kpi-stock" />
          <KpiCard label="Active Leads" value={stats?.active_leads ?? 0} hint="Across pipeline" accent="brand" icon={Users} testid="kpi-leads" />
          <KpiCard label="Overdue Follow-ups" value={stats?.overdue_followups ?? 0} hint="Need attention" accent="danger" icon={AlertTriangle} testid="kpi-overdue" />
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="font-heading font-semibold text-[var(--ink)]">Monthly Revenue</div>
                <div className="text-xs text-[var(--ink-3)]">Last 12 months</div>
              </div>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stats?.monthly_revenue || []}>
                  <XAxis dataKey="month" stroke="#8A8C8A" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis stroke="#8A8C8A" fontSize={11} tickLine={false} axisLine={false} tickFormatter={(v) => inr(v)} />
                  <Tooltip
                    formatter={(v) => inrFull(v)}
                    contentStyle={{ background: "#fff", border: "1px solid #E2E0D9", borderRadius: 8, fontSize: 12 }}
                  />
                  <Bar dataKey="value" fill="#C85A32" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="font-heading font-semibold text-[var(--ink)] mb-1">Division Split</div>
            <div className="text-xs text-[var(--ink-3)] mb-4">Revenue by division</div>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={stats?.division_split || []}
                    dataKey="value"
                    nameKey="division"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                  >
                    {(stats?.division_split || []).map((_, i) => (
                      <Cell key={i} fill={DIVISION_COLORS[i % DIVISION_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => inrFull(v)} contentStyle={{ background: "#fff", border: "1px solid #E2E0D9", borderRadius: 8, fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-1.5 mt-2">
              {(stats?.division_split || []).map((d, i) => (
                <div key={d.division} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: DIVISION_COLORS[i % DIVISION_COLORS.length] }} />
                    <span className="text-[var(--ink-2)]">{d.division}</span>
                  </div>
                  <span className="font-mono text-[var(--ink)] font-semibold">{inr(d.value)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Pipeline + alerts */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="font-heading font-semibold text-[var(--ink)] mb-4">Pipeline by stage</div>
            <div className="space-y-3">
              {(stats?.by_stage || []).map((s) => {
                const max = Math.max(...(stats?.by_stage || []).map((x) => x.value), 1);
                const pct = (s.value / max) * 100;
                return (
                  <div key={s.stage}>
                    <div className="flex items-center justify-between text-xs mb-1.5">
                      <div className="flex items-center gap-2">
                        <StageBadge stage={s.stage} />
                        <span className="text-[var(--ink-3)]">{s.count} {s.count === 1 ? "deal" : "deals"}</span>
                      </div>
                      <span className="font-mono text-[var(--ink)] font-semibold">{inr(s.value)}</span>
                    </div>
                    <div className="h-1.5 bg-[var(--surface-2)] rounded-full overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-[var(--brand)] to-[var(--brand-hover)] rounded-full transition-all" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="font-heading font-semibold text-[var(--ink)]">Follow-up alerts</div>
              <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--danger-soft)] text-[var(--danger)] font-medium">{overdue.length}</span>
            </div>
            {overdue.length === 0 ? (
              <div className="text-sm text-[var(--ink-3)] py-6 text-center">All caught up 🌿</div>
            ) : (
              <div className="space-y-2.5">
                {overdue.map((l) => (
                  <div key={l.id} className="p-3 rounded-lg bg-[var(--surface-2)] border border-[var(--border-light)]" data-testid={`overdue-${l.id}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-semibold text-sm text-[var(--ink)] truncate">{l.name}</div>
                      <StageBadge stage={l.stage} />
                    </div>
                    <div className="flex items-center gap-3 mt-1.5 text-[11px] text-[var(--ink-3)]">
                      <span className="flex items-center gap-1"><Calendar size={11} />{fmtDate(l.follow_up_date)}</span>
                      <span>{l.assigned_to}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Recent quotes */}
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="p-5 border-b border-[var(--border-light)]">
            <div className="font-heading font-semibold text-[var(--ink)]">Recent quotations</div>
            <div className="text-xs text-[var(--ink-3)] mt-0.5">Latest deals in your pipeline</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)]">
                <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                  <th className="text-left font-semibold px-4 py-2.5">Quote No</th>
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                  <th className="text-left font-semibold px-4 py-2.5">Division</th>
                  <th className="text-left font-semibold px-4 py-2.5">By</th>
                  <th className="text-left font-semibold px-4 py-2.5">Stage</th>
                  <th className="text-right font-semibold px-4 py-2.5">Value</th>
                </tr>
              </thead>
              <tbody>
                {quotes.slice(0, 8).map((q) => (
                  <tr key={q.id} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/60" data-testid={`quote-row-${q.id}`}>
                    <td className="px-4 py-3 font-mono text-[var(--ink)] text-xs">{q.quote_no}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(q.date)}</td>
                    <td className="px-4 py-3 font-medium text-[var(--ink)]">{q.customer}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{q.division}</td>
                    <td className="px-4 py-3 text-[var(--ink-2)]">{q.by_user}</td>
                    <td className="px-4 py-3"><StageBadge stage={q.stage} /></td>
                    <td className="px-4 py-3 text-right font-mono font-semibold text-[var(--ink)]">{inrFull(q.value)}</td>
                  </tr>
                ))}
                {quotes.length === 0 && !loading && (
                  <tr><td colSpan="7" className="text-center py-10 text-[var(--ink-3)]">No quotes yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
