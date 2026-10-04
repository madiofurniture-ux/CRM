import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell,
} from "recharts";
import Topbar from "@/components/Topbar";
import ErrorState from "@/components/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/context/AuthContext";
import { useTenantConfig } from "@/context/TenantConfigContext";
import api, { formatApiError } from "@/lib/api";
import { inr, inrFull, fmtDate, todayIST, isoDateIST } from "@/lib/format";
import { ArrowUp, ArrowDown, Table2, BarChart3 } from "lucide-react";

/**
 * Analytics hub: one screen, five tabs (Sales, Leads, Calls, Attendance,
 * Vendors & Projects), one filter row that scopes every chart below it.
 * Figures come from GET /analytics/hub/{tab}; the server applies the
 * caller's visibility (admins: whole business; others: their own/team).
 *
 * Chart rules (dataviz skill): one y-axis per chart, bars <= 24px with 4px
 * rounded data-ends, hairline solid grid, categorical slots in fixed order
 * (validated on the white card surface), an ordinal blue ramp for the lead
 * funnel, and a table view for every chart.
 */
const SERIES = ["#2a78d6", "#eb6834", "#1baf7a"];          // categorical slots 1-3
const FUNNEL_RAMP = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281"];
const INK_MUTED = "#5c5c5c";
const GRID = "#e5e5e5";

const TABS = [
  { key: "sales", label: "Sales", division: true },
  { key: "leads", label: "Leads", division: false },
  { key: "calls", label: "Calls", division: true },
  { key: "attendance", label: "Attendance", division: false },
  { key: "vendors", label: "Vendors & Projects", division: true, adminOnly: true },
];

// KPIs where a fall is the good direction.
const LOWER_IS_BETTER = new Set(["outstanding", "out_of_fence", "no_checkout", "overdue_projects", "vendor_balance"]);

const addDays = (iso, n) => {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return isoDateIST(d);
};

function presetRange(key) {
  const today = todayIST();
  const [y, m] = today.split("-").map(Number);
  switch (key) {
    case "7": return [addDays(today, -6), today];
    case "30": return [addDays(today, -29), today];
    case "90": return [addDays(today, -89), today];
    case "month": return [`${today.slice(0, 7)}-01`, today];
    case "fy": {
      const fyStart = m >= 4 ? y : y - 1;          // Indian financial year: Apr–Mar
      return [`${fyStart}-04-01`, today];
    }
    default: return [addDays(today, -29), today];
  }
}
const PRESETS = [["7", "7 days"], ["30", "30 days"], ["90", "90 days"], ["month", "This month"], ["fy", "This FY"]];

const fmtValue = (v, format) => {
  if (v === null || v === undefined) return "—";
  if (format === "money") return inr(v);
  if (format === "percent") return `${v}%`;
  if (format === "hours") return `${v} h`;
  if (format === "decimal") return Number(v).toFixed(1);
  if (format === "pts") return `${v} pts`;
  return Number(v).toLocaleString("en-IN");
};

const field = "px-2.5 py-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border-strong,var(--color-border))] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)]";

export default function Analytics() {
  const { divisions } = useTenantConfig();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const tabs = TABS.filter((t) => !t.adminOnly || isAdmin);

  const [tab, setTab] = useState("sales");
  const [preset, setPreset] = useState("30");
  const [[start, end], setRange] = useState(presetRange("30"));
  const [division, setDivision] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const tabDef = tabs.find((t) => t.key === tab) || tabs[0];

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    const q = new URLSearchParams({ start, end });
    if (division && tabDef.division) q.set("division", division);
    api.get(`/analytics/hub/${tab}?${q.toString()}`)
      .then(({ data: d }) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setError(formatApiError(e.response?.data?.detail)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [tab, start, end, division, tabDef.division, reloadKey]);

  const choosePreset = (k) => { setPreset(k); setRange(presetRange(k)); };
  const span = Math.round((new Date(end) - new Date(start)) / 86400000) + 1;

  return (
    <>
      <Topbar title="Analytics" subtitle="Sales, leads, calls, attendance, vendors and projects" />
      <div className="p-4 md:p-6 space-y-5" data-testid="analytics-page">
        <div role="tablist" aria-label="Analytics area" className="flex gap-1 border-b border-[var(--color-border)] overflow-x-auto">
          {tabs.map((t) => (
            <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                    data-testid={`analytics-tab-${t.key}`}
                    className={`px-3 py-2 text-sm whitespace-nowrap -mb-px border-b-2 ${tab === t.key
                      ? "border-[var(--color-primary)] text-[var(--color-primary)] font-semibold"
                      : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"}`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* One filter row scopes every chart on the tab. */}
        <div className="flex flex-wrap items-center gap-2" data-testid="analytics-filters">
          <div role="group" aria-label="Date range" className="inline-flex max-w-full overflow-x-auto rounded-[var(--radius-sm)] border border-[var(--color-border-strong,var(--color-border))]">
            {PRESETS.map(([k, label]) => (
              <button key={k} type="button" aria-pressed={preset === k} onClick={() => choosePreset(k)}
                      className={`px-3 py-1.5 text-sm whitespace-nowrap ${preset === k ? "bg-[var(--color-primary)] text-white" : "bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)]"}`}>
                {label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1.5 text-sm text-[var(--color-text-muted)]">
            From
            <input type="date" className={field} value={start} max={end}
                   onChange={(e) => { setPreset("custom"); setRange([e.target.value, end]); }} />
          </label>
          <label className="flex items-center gap-1.5 text-sm text-[var(--color-text-muted)]">
            to
            <input type="date" className={field} value={end} min={start}
                   onChange={(e) => { setPreset("custom"); setRange([start, e.target.value]); }} />
          </label>
          {tabDef.division ? (
            <select className={field} aria-label="Division" value={division} onChange={(e) => setDivision(e.target.value)}>
              <option value="">All divisions</option>
              {divisions.map((d) => <option key={d.slug} value={d.slug}>{d.name || d.slug}</option>)}
            </select>
          ) : (
            <span className="text-xs text-[var(--color-text-muted)]">The division filter doesn't apply to {tabDef.label.toLowerCase()}.</span>
          )}
        </div>

        {data?.scope && data.scope !== "all" && (
          <p className="text-sm text-[var(--color-text-muted)]">
            Showing {data.scope === "team" ? "your team's" : "your own"} records.
          </p>
        )}

        {error ? (
          <ErrorState hint={error} onRetry={() => setReloadKey((k) => k + 1)} />
        ) : !data ? (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20" />)}</div>
        ) : (
          // Hold the previous render at reduced opacity while refetching: no skeleton flash.
          <div className={`space-y-5 transition-opacity ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
            <KpiRow kpis={data.kpis} span={span} showPrev={data.tab !== "vendors"} />
            {data.tab === "sales" && <SalesTab d={data} />}
            {data.tab === "leads" && <LeadsTab d={data} />}
            {data.tab === "calls" && <CallsTab d={data} />}
            {data.tab === "attendance" && <AttendanceTab d={data} />}
            {data.tab === "vendors" && <VendorsTab d={data} />}
          </div>
        )}
      </div>
    </>
  );
}

// ── KPI tiles ───────────────────────────────────────────────────────────────
function KpiRow({ kpis, span, showPrev }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3" data-testid="analytics-kpis">
      {kpis.map((k) => {
        const hasPrev = showPrev && k.prev !== null && k.prev !== undefined && k.value !== null;
        const diff = hasPrev ? k.value - k.prev : 0;
        const good = LOWER_IS_BETTER.has(k.key) ? diff < 0 : diff > 0;
        return (
          <div key={k.key} className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
            <div className="text-xs text-[var(--color-text-muted)]">{k.label}</div>
            <div className="text-2xl font-heading font-bold text-[var(--color-text)] mt-0.5"
                 title={k.format === "money" && k.value != null ? inrFull(k.value) : undefined}>
              {fmtValue(k.value, k.format)}
            </div>
            {hasPrev && (
              <div className="text-xs mt-1 flex items-center gap-1 text-[var(--color-text-muted)]">
                {diff !== 0 && (
                  <span className={`inline-flex items-center ${good ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>
                    {diff > 0 ? <ArrowUp size={12} aria-hidden /> : <ArrowDown size={12} aria-hidden />}
                    <span className="sr-only">{diff > 0 ? "up" : "down"}</span>
                    {fmtValue(Math.abs(Math.round(diff * 10) / 10), k.format === "percent" ? "pts" : k.format)}
                  </span>
                )}
                <span>{diff === 0 ? "No change" : ""} vs previous {span} days</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── chart primitives ────────────────────────────────────────────────────────
function ChartCard({ title, subtitle, table, children, className = "" }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className={`rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 ${className}`}>
      <header className="flex items-start gap-2 mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-heading font-semibold text-[var(--color-text)]">{title}</h3>
          {subtitle && <p className="text-xs text-[var(--color-text-muted)]">{subtitle}</p>}
        </div>
        {table && (
          <button type="button" onClick={() => setAsTable((v) => !v)}
                  aria-label={asTable ? `Show ${title} as a chart` : `Show ${title} as a table`}
                  className="p-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)]">
            {asTable ? <BarChart3 size={15} /> : <Table2 size={15} />}
          </button>
        )}
      </header>
      {asTable && table ? <DataTable {...table} /> : children}
    </section>
  );
}

function DataTable({ columns, rows, empty = "No data in this range." }) {
  if (!rows?.length) return <p className="text-sm text-[var(--color-text-muted)] py-6 text-center">{empty}</p>;
  return (
    <div className="overflow-x-auto max-h-80">
      <table className="w-full text-sm">
        <thead className="text-xs text-[var(--color-text-muted)] border-b border-[var(--color-border)] sticky top-0 bg-[var(--color-surface)]">
          <tr>{columns.map((c) => <th key={c.key} className={`py-2 pr-3 font-medium ${c.num ? "text-right" : "text-left"}`}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-[var(--color-border)] last:border-0">
              {columns.map((c) => (
                <td key={c.key} className={`py-2 pr-3 ${c.num ? "text-right tabular-nums" : ""}`}>
                  {c.render ? c.render(r[c.key], r) : (r[c.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChartTooltip({ active, payload, label, format }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs shadow-md">
      <div className="font-semibold text-[var(--color-text)] mb-1">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-[var(--color-text)]">
          <span className="w-2.5 h-2.5 rounded-sm" style={{ background: p.color || p.payload?.fill }} aria-hidden />
          <span className="text-[var(--color-text-muted)]">{p.name}</span>
          <span className="ml-auto font-medium tabular-nums">{fmtValue(p.value, format)}</span>
        </div>
      ))}
    </div>
  );
}

const axisProps = { tick: { fill: INK_MUTED, fontSize: 11 }, tickLine: false, axisLine: { stroke: GRID } };
const legendProps = { iconType: "square", iconSize: 10, wrapperStyle: { fontSize: 12, color: INK_MUTED } };

/** Vertical bars over time. `series` = [{key, name}] stacked when > 1. */
function TrendChart({ rows, series, format = "number", height = 240 }) {
  const empty = !rows?.some((r) => series.some((s) => r[s.key]));
  if (empty) return <p className="text-sm text-[var(--color-text-muted)] py-16 text-center">Nothing recorded in this range.</p>;
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} barCategoryGap="20%">
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="label" {...axisProps} interval="preserveStartEnd" minTickGap={16} />
          <YAxis {...axisProps} axisLine={false} width={format === "money" ? 56 : 32}
                 tickFormatter={(v) => (format === "money" ? inr(v) : v)} allowDecimals={false} />
          <Tooltip content={<ChartTooltip format={format} />} cursor={{ fill: "rgba(1,118,211,0.06)" }} />
          {series.length > 1 && <Legend {...legendProps} />}
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} stackId={series.length > 1 ? "a" : undefined}
                 fill={SERIES[i]} maxBarSize={24} stroke="#ffffff" strokeWidth={series.length > 1 ? 1 : 0}
                 radius={i === series.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Horizontal bars for ranked categories (reps, sources, vendors). One series. */
function RankChart({ rows, valueKey, name, format = "number", colors }) {
  if (!rows?.length) return <p className="text-sm text-[var(--color-text-muted)] py-10 text-center">Nothing recorded in this range.</p>;
  const data = rows.slice(0, 10);
  return (
    <div style={{ height: Math.max(120, data.length * 34 + 30) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 48, bottom: 0, left: 0 }} barCategoryGap="25%">
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis type="number" {...axisProps} tickFormatter={(v) => (format === "money" ? inr(v) : v)} allowDecimals={false} />
          <YAxis type="category" dataKey="name" {...axisProps} axisLine={false} width={110}
                 tickFormatter={(v) => (String(v).length > 16 ? `${String(v).slice(0, 15)}…` : v)} />
          <Tooltip content={<ChartTooltip format={format} />} cursor={{ fill: "rgba(1,118,211,0.06)" }} />
          <Bar dataKey={valueKey} name={name} fill={SERIES[0]} maxBarSize={24} radius={[0, 4, 4, 0]} isAnimationActive={false}
               label={{ position: "right", fill: INK_MUTED, fontSize: 11, formatter: (v) => fmtValue(v, format) }}>
            {colors && data.map((_, i) => <Cell key={i} fill={colors[i % colors.length]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

const pctCell = (v) => (v === null || v === undefined ? "—" : `${v}%`);
const moneyCell = (v) => inrFull(v);

// ── tabs ────────────────────────────────────────────────────────────────────
function SalesTab({ d }) {
  const t = d.tables;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ChartCard title="Sales value" subtitle={`By ${d.granularity}`} className="lg:col-span-2"
                 table={{ columns: [{ key: "label", label: "Period" }, { key: "value", label: "Value", num: true, render: moneyCell }, { key: "orders", label: "Orders", num: true }], rows: d.series.trend }}>
        <TrendChart rows={d.series.trend} series={[{ key: "value", name: "Sales value" }]} format="money" />
      </ChartCard>
      <ChartCard title="By sales rep" subtitle="Sales value"
                 table={{ columns: [{ key: "name", label: "Rep" }, { key: "value", label: "Value", num: true, render: moneyCell }, { key: "orders", label: "Orders", num: true }, { key: "collected", label: "Collected", num: true, render: moneyCell }], rows: t.by_rep }}>
        <RankChart rows={t.by_rep} valueKey="value" name="Sales value" format="money" />
      </ChartCard>
      <ChartCard title="By division" subtitle="Sales value"
                 table={{ columns: [{ key: "name", label: "Division" }, { key: "value", label: "Value", num: true, render: moneyCell }, { key: "orders", label: "Orders", num: true }], rows: t.by_division }}>
        <RankChart rows={t.by_division} valueKey="value" name="Sales value" format="money" />
      </ChartCard>
      <ChartCard title="Top customers" subtitle="Sales value in this range" className="lg:col-span-2">
        <DataTable columns={[{ key: "name", label: "Customer" }, { key: "value", label: "Value", num: true, render: moneyCell }]} rows={t.top_customers} />
      </ChartCard>
    </div>
  );
}

function LeadsTab({ d }) {
  const t = d.tables;
  const leadCols = [{ key: "name", label: "Name" }, { key: "leads", label: "Leads", num: true }, { key: "won", label: "Won", num: true }, { key: "lost", label: "Lost", num: true }, { key: "win_rate", label: "Win rate", num: true, render: pctCell }];
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ChartCard title="New leads and wins" subtitle={`By ${d.granularity}`} className="lg:col-span-2"
                 table={{ columns: [{ key: "label", label: "Period" }, { key: "leads", label: "Leads", num: true }, { key: "won", label: "Won", num: true }], rows: d.series.trend }}>
        <TrendChart rows={d.series.trend.map((r) => ({ ...r, open: r.leads - r.won }))}
                    series={[{ key: "won", name: "Won" }, { key: "open", name: "Not won" }]} />
      </ChartCard>
      <ChartCard title="Lead funnel" subtitle="Leads created in this range that reached each stage"
                 table={{ columns: [{ key: "name", label: "Stage" }, { key: "value", label: "Leads", num: true }], rows: t.funnel }}>
        <RankChart rows={t.funnel} valueKey="value" name="Leads" colors={FUNNEL_RAMP.slice(0, t.funnel.length)} />
      </ChartCard>
      <ChartCard title="By source" subtitle="Leads" table={{ columns: leadCols, rows: t.by_source }}>
        <RankChart rows={t.by_source} valueKey="leads" name="Leads" />
      </ChartCard>
      <ChartCard title="By owner" className="lg:col-span-2">
        <DataTable columns={leadCols} rows={t.by_owner} />
      </ChartCard>
    </div>
  );
}

function CallsTab({ d }) {
  const t = d.tables;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ChartCard title="Calls" subtitle={`Connected and not connected, by ${d.granularity}`} className="lg:col-span-2"
                 table={{ columns: [{ key: "label", label: "Period" }, { key: "connected", label: "Connected", num: true }, { key: "not_connected", label: "Not connected", num: true }], rows: d.series.trend }}>
        <TrendChart rows={d.series.trend} series={[{ key: "connected", name: "Connected" }, { key: "not_connected", name: "Not connected" }]} />
      </ChartCard>
      <ChartCard title="Outcomes"
                 table={{ columns: [{ key: "name", label: "Outcome" }, { key: "value", label: "Calls", num: true }], rows: t.outcomes }}>
        <RankChart rows={t.outcomes} valueKey="value" name="Calls" />
      </ChartCard>
      <ChartCard title="By caller" subtitle="Calls made"
                 table={{ columns: [{ key: "name", label: "Caller" }, { key: "calls", label: "Calls", num: true }, { key: "per_day", label: "Per day", num: true }, { key: "connect_rate", label: "Connect rate", num: true, render: pctCell }, { key: "interested", label: "Interested", num: true }, { key: "converted", label: "Converted", num: true }], rows: t.by_caller }}>
        <RankChart rows={t.by_caller} valueKey="calls" name="Calls" />
      </ChartCard>
    </div>
  );
}

function AttendanceTab({ d }) {
  const t = d.tables;
  return (
    <div className="grid gap-4">
      <ChartCard title="Attendance" subtitle={`Days present and absent, by ${d.granularity}`}
                 table={{ columns: [{ key: "label", label: "Period" }, { key: "present", label: "Present", num: true }, { key: "absent", label: "Absent", num: true }], rows: d.series.trend }}>
        <TrendChart rows={d.series.trend} series={[{ key: "present", name: "Present" }, { key: "absent", name: "Absent" }]} />
      </ChartCard>
      <ChartCard title="By person">
        <DataTable rows={t.by_person} columns={[
          { key: "name", label: "Name" }, { key: "days", label: "Days present", num: true },
          { key: "absent", label: "Absent", num: true },
          { key: "avg_hours", label: "Avg hours / day", num: true, render: (v) => (v == null ? "—" : `${v} h`) },
          { key: "hours", label: "Total hours", num: true },
          { key: "out_of_fence", label: "Outside site", num: true },
          { key: "no_checkout", label: "No check-out", num: true },
        ]} />
      </ChartCard>
    </div>
  );
}

function VendorsTab({ d }) {
  const t = d.tables;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ChartCard title="Vendor orders by status" subtitle="All open and closed orders"
                 table={{ columns: [{ key: "name", label: "Status" }, { key: "value", label: "Orders", num: true }], rows: t.orders_by_status }}>
        <RankChart rows={t.orders_by_status} valueKey="value" name="Orders" />
      </ChartCard>
      <ChartCard title="Projects by stage"
                 table={{ columns: [{ key: "name", label: "Stage" }, { key: "value", label: "Projects", num: true }], rows: t.projects_by_stage }}>
        <RankChart rows={t.projects_by_stage} valueKey="value" name="Projects" />
      </ChartCard>
      <ChartCard title="Top vendors" subtitle="Order value placed in this range"
                 table={{ columns: [{ key: "name", label: "Vendor" }, { key: "value", label: "Value", num: true, render: moneyCell }, { key: "orders", label: "Orders", num: true }, { key: "balance", label: "Balance due", num: true, render: moneyCell }], rows: t.top_vendors }}>
        <RankChart rows={t.top_vendors} valueKey="value" name="Order value" format="money" />
      </ChartCard>
      <ChartCard title="Projects past their target date">
        <DataTable rows={t.overdue_projects} empty="No project is past its target date." columns={[
          { key: "name", label: "Customer" }, { key: "project_no", label: "Project" },
          { key: "stage", label: "Stage" }, { key: "target_date", label: "Target", render: (v) => fmtDate(v) },
          { key: "days_late", label: "Days late", num: true },
        ]} />
      </ChartCard>
    </div>
  );
}
