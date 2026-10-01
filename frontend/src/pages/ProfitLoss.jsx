import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import Topbar from "@/components/Topbar";
import ErrorState from "@/components/ErrorState";
import EmptyState from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { usePrivacyMode } from "@/context/PrivacyModeContext";
import api, { formatApiError } from "@/lib/api";
import { inr, inrFull, fmtDate, todayIST, isoDateIST } from "@/lib/format";
import {
  UserPlus, Sparkles, FileText, Receipt, Factory, Hammer, Wallet, IndianRupee, TrendingUp,
  ArrowLeft, Check, Lock, Table2, BarChart3, Search,
} from "lucide-react";

/**
 * Profit & Loss: the company statement for a period, and every deal's money
 * lineage from the first visit to its profit (GET /finance/pnl,
 * /finance/deals, /finance/deal-pnl). Spend figures follow privacy mode:
 * masked on the server until the PIN unlocks them, like Project P&L.
 */
const SERIES = ["#2a78d6", "#eb6834"];
const INK_MUTED = "#5c5c5c";
const GRID = "#e5e5e5";
const field = "px-2.5 py-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border-strong,var(--color-border))] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)]";

const CHAIN_ICON = {
  visitor: UserPlus, lead: Sparkles, quote: FileText, sale: Receipt, vendor: Factory,
  project: Hammer, expenses: Wallet, payment: IndianRupee, pnl: TrendingUp,
};

const money = (v) => (v === null || v === undefined ? null : inrFull(v));
const pct = (v) => (v === null || v === undefined ? "" : `${v}%`);

function presetRange(k) {
  const today = todayIST();
  const [y, m] = today.split("-").map(Number);
  if (k === "month") return [`${today.slice(0, 7)}-01`, today];
  if (k === "quarter") { const d = new Date(); d.setDate(d.getDate() - 89); return [isoDateIST(d), today]; }
  if (k === "lastfy") { const s = m >= 4 ? y - 1 : y - 2; return [`${s}-04-01`, `${s + 1}-03-31`]; }
  return [`${m >= 4 ? y : y - 1}-04-01`, today];      // this FY
}

export default function ProfitLoss() {
  const location = useLocation();
  const nav = useNavigate();
  const params = new URLSearchParams(location.search);
  const anchor = ["project_id", "sale_id", "quote_id", "lead_id"].find((k) => params.get(k));
  const [view, setView] = useState(anchor ? "deals" : "company");
  useEffect(() => { if (anchor) setView("deals"); }, [anchor]);

  return (
    <>
      <Topbar title="Profit & Loss" subtitle="Company profit, and every deal traced from first visit to profit" />
      <div className="p-4 md:p-6 space-y-5" data-testid="pnl-page">
        <div role="tablist" aria-label="Profit and loss view" className="flex gap-1 border-b border-[var(--color-border)]">
          {[["company", "Company P&L"], ["deals", "Deals"]].map(([k, l]) => (
            <button key={k} role="tab" aria-selected={view === k}
                    onClick={() => { setView(k); if (anchor) nav("/finance/pnl"); }}
                    className={`px-3 py-2 text-sm -mb-px border-b-2 ${view === k
                      ? "border-[var(--color-primary)] text-[var(--color-primary)] font-semibold"
                      : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"}`}>
              {l}
            </button>
          ))}
        </div>
        <PrivacyNote />
        {view === "company" ? <CompanyPnl /> : anchor
          ? <DealDetail query={`${anchor}=${encodeURIComponent(params.get(anchor))}`} onBack={() => nav("/finance/pnl")} />
          : <DealList onOpen={(r) => nav(`/finance/pnl?${r.kind === "sale" ? "sale_id" : "project_id"}=${r.id}`)} />}
      </div>
    </>
  );
}

function PrivacyNote() {
  const { isOtherHidden, requestUnlock } = usePrivacyMode();
  if (!isOtherHidden) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text-muted)]">
      <Lock size={14} aria-hidden /> Expenses and the profit figures built on them are hidden in privacy mode.
      <button type="button" className="text-[var(--color-primary)] font-medium hover:underline" onClick={requestUnlock}>Unlock with PIN</button>
    </div>
  );
}

const Hidden = () => <span className="text-[var(--color-text-muted)]" title="Hidden in privacy mode">••••</span>;
const Amt = ({ v, strong }) => (v === null || v === undefined ? <Hidden /> : <span className={`tabular-nums ${strong ? "font-semibold" : ""}`}>{inrFull(v)}</span>);

// ── company ────────────────────────────────────────────────────────────────
function CompanyPnl() {
  const { isOtherHidden } = usePrivacyMode();
  const [preset, setPreset] = useState("fy");
  const [[start, end], setRange] = useState(presetRange("fy"));
  const [division, setDivision] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [asTable, setAsTable] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    setError(null);
    const q = new URLSearchParams({ start, end, mask_other: String(isOtherHidden) });
    if (division) q.set("division", division);
    api.get(`/finance/pnl?${q}`, { skipCache: true })
      .then(({ data: d }) => alive && setData(d))
      .catch((e) => alive && setError(formatApiError(e.response?.data?.detail)));
    return () => { alive = false; };
  }, [start, end, division, isOtherHidden, reload]);

  const st = data?.statement;
  const chartRows = useMemo(() => (data?.series || []).map((r) => ({
    ...r,
    costs: r.project_expenses === null ? null
      : r.vendor_cost + r.project_expenses + r.overheads + r.incentives,
  })), [data]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Period" className="inline-flex max-w-full overflow-x-auto rounded-[var(--radius-sm)] border border-[var(--color-border-strong,var(--color-border))]">
          {[["month", "This month"], ["quarter", "Last 90 days"], ["fy", "This FY"], ["lastfy", "Last FY"]].map(([k, l]) => (
            <button key={k} type="button" aria-pressed={preset === k} onClick={() => { setPreset(k); setRange(presetRange(k)); }}
                    className={`px-3 py-1.5 text-sm whitespace-nowrap ${preset === k ? "bg-[var(--color-primary)] text-white" : "bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)]"}`}>
              {l}
            </button>
          ))}
        </div>
        <input type="date" aria-label="From" className={field} value={start} max={end} onChange={(e) => { setPreset(""); setRange([e.target.value, end]); }} />
        <input type="date" aria-label="To" className={field} value={end} min={start} onChange={(e) => { setPreset(""); setRange([start, e.target.value]); }} />
        <select className={field} aria-label="Division" value={division} onChange={(e) => setDivision(e.target.value)}>
          <option value="">All divisions</option>
          {["Furniture", "MAP", "D&W"].map((d) => <option key={d}>{d}</option>)}
        </select>
      </div>

      {error ? <ErrorState hint={error} onRetry={() => setReload((n) => n + 1)} /> : !st ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
            <section className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4" aria-label="Profit and loss statement">
              <h3 className="font-heading font-semibold mb-3">Statement</h3>
              <dl className="text-sm">
                <Line label="Sales (revenue)" v={st.revenue} strong />
                <Line label="Vendor orders & POs" v={st.vendor_cost} minus />
                <Line label="Project expenses" v={st.project_expenses} minus />
                <Line label="Gross profit" v={st.gross_profit} total note={pct(st.gross_margin_pct)} />
                <Line label="Overheads" v={st.overheads} minus />
                {st.salaries ? <Line label="Salaries (paid payroll)" v={st.salaries} minus /> : null}
                <Line label="Incentives" v={st.incentives} minus />
                <Line label="Net profit" v={st.net_profit} total note={pct(st.net_margin_pct)} />
              </dl>
            </section>
            <section className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <header className="flex items-start mb-3">
                <div className="flex-1">
                  <h3 className="font-heading font-semibold">Revenue and costs by month</h3>
                  <p className="text-xs text-[var(--color-text-muted)]">Costs = vendor orders + project expenses + overheads + incentives</p>
                </div>
                <button type="button" onClick={() => setAsTable((v) => !v)} aria-label={asTable ? "Show as chart" : "Show as table"}
                        className="p-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)]">
                  {asTable ? <BarChart3 size={15} /> : <Table2 size={15} />}
                </button>
              </header>
              {!chartRows.some((r) => r.revenue || r.costs) ? (
                <p className="text-sm text-[var(--color-text-muted)] py-20 text-center">Nothing recorded in this period.</p>
              ) : asTable ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-xs text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
                      <tr>{["Month", "Revenue", "Vendor", "Project exp.", "Overheads", "Salaries", "Incentives", "Net profit"].map((h, i) => <th key={h} className={`py-2 pr-3 font-medium ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr>
                    </thead>
                    <tbody>
                      {data.series.map((r) => (
                        <tr key={r.month} className="border-b border-[var(--color-border)] last:border-0">
                          <td className="py-2 pr-3">{r.label}</td>
                          {["revenue", "vendor_cost", "project_expenses", "overheads", "salaries", "incentives", "net_profit"].map((f) => (
                            <td key={f} className="py-2 pr-3 text-right"><Amt v={r[f]} /></td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{ height: 260 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartRows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} barGap={2} barCategoryGap="25%">
                      <CartesianGrid vertical={false} stroke={GRID} />
                      <XAxis dataKey="label" tick={{ fill: INK_MUTED, fontSize: 11 }} tickLine={false} axisLine={{ stroke: GRID }} />
                      <YAxis tick={{ fill: INK_MUTED, fontSize: 11 }} tickLine={false} axisLine={false} width={56} tickFormatter={(v) => inr(v)} />
                      <Tooltip formatter={(v) => (v === null ? "Hidden" : inrFull(v))} cursor={{ fill: "rgba(1,118,211,0.06)" }} />
                      <Legend iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12, color: INK_MUTED }} />
                      <Bar dataKey="revenue" name="Revenue" fill={SERIES[0]} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                      {!isOtherHidden && <Bar dataKey="costs" name="Costs" fill={SERIES[1]} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </section>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <h3 className="font-heading font-semibold mb-3">By division</h3>
              <SimpleTable rows={data.by_division} empty="No sales in this period." columns={[
                ["name", "Division"], ["revenue", "Revenue", true], ["vendor_cost", "Vendor", true],
                ["expenses", "Project exp.", true], ["gross_margin", "Gross margin", true]]} />
            </section>
            <section className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <h3 className="font-heading font-semibold mb-3">Overheads by category</h3>
              <SimpleTable rows={data.overheads_by_category} empty={isOtherHidden ? "Hidden in privacy mode." : "No overheads in this period."}
                           columns={[["name", "Category"], ["amount", "Amount", true]]} />
            </section>
          </div>
        </>
      )}
    </div>
  );
}

function Line({ label, v, minus, total, strong, note }) {
  return (
    <div className={`flex items-baseline justify-between gap-3 py-1.5 ${total ? "border-t border-[var(--color-border)] font-semibold mt-1 pt-2" : ""}`}>
      <dt className={minus ? "text-[var(--color-text-muted)] pl-3" : ""}>{minus ? "− " : ""}{label}</dt>
      <dd className="text-right">
        <Amt v={v} strong={strong || total} />
        {note && v !== null && <span className="ml-2 text-xs text-[var(--color-text-muted)] font-normal">{note}</span>}
      </dd>
    </div>
  );
}

function SimpleTable({ rows, columns, empty }) {
  if (!rows?.length) return <p className="text-sm text-[var(--color-text-muted)] py-6 text-center">{empty}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-xs text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
          <tr>{columns.map(([k, l, num]) => <th key={k} className={`py-2 pr-3 font-medium ${num ? "text-right" : "text-left"}`}>{l}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-[var(--color-border)] last:border-0">
              {columns.map(([k, , num]) => <td key={k} className={`py-2 pr-3 ${num ? "text-right" : ""}`}>{num ? <Amt v={r[k]} /> : r[k]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── deals ──────────────────────────────────────────────────────────────────
function DealList({ onOpen }) {
  const { isOtherHidden } = usePrivacyMode();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [q, setQ] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setError(null);
    api.get(`/finance/deals?mask_other=${isOtherHidden}`, { skipCache: true })
      .then(({ data }) => setRows(data)).catch((e) => setError(formatApiError(e.response?.data?.detail)));
  }, [isOtherHidden, reload]);

  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (rows || []).filter((r) => !s || [r.customer, r.ref, r.project_no].some((v) => String(v || "").toLowerCase().includes(s)));
  }, [rows, q]);

  if (error) return <ErrorState hint={error} onRetry={() => setReload((n) => n + 1)} />;
  if (!rows) return <Skeleton className="h-64 w-full" />;
  return (
    <div className="space-y-3">
      <div className="relative max-w-sm">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" aria-hidden />
        <input className={`${field} w-full pl-8`} placeholder="Search customer, sale or project number" aria-label="Search deals" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {!shown.length ? (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)]">
          <EmptyState icon={TrendingUp} title={rows.length ? "No deals match" : "No deals yet"} hint="Deals appear once a sales order or project exists." />
        </div>
      ) : (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] overflow-x-auto">
          <table className="w-full text-sm" data-testid="deal-list">
            <thead className="text-left text-xs text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
              <tr>
                <th className="px-4 py-2.5 font-medium">Deal</th>
                <th className="px-4 py-2.5 font-medium text-right">Revenue</th>
                <th className="px-4 py-2.5 font-medium text-right hidden md:table-cell">Vendor cost</th>
                <th className="px-4 py-2.5 font-medium text-right hidden lg:table-cell">Gross margin</th>
                <th className="px-4 py-2.5 font-medium text-right">Net profit</th>
                <th className="px-4 py-2.5 font-medium text-right hidden md:table-cell">To collect</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={`${r.kind}-${r.id}`} className="border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--surface-hover)] cursor-pointer" onClick={() => onOpen(r)}>
                  <td className="px-4 py-2.5">
                    <button type="button" className="font-medium text-left hover:underline" onClick={(e) => { e.stopPropagation(); onOpen(r); }}>{r.customer || "Unnamed"}</button>
                    <div className="text-xs text-[var(--color-text-muted)]">{[r.ref, r.project_no && r.project_no !== r.ref ? r.project_no : "", r.division, fmtDate(r.date)].filter((x) => x && x !== "—").join(" · ")}</div>
                  </td>
                  <td className="px-4 py-2.5 text-right"><Amt v={r.revenue} /></td>
                  <td className="px-4 py-2.5 text-right hidden md:table-cell"><Amt v={r.vendor_cost} /></td>
                  <td className="px-4 py-2.5 text-right hidden lg:table-cell"><Amt v={r.gross_margin} />{r.gross_margin_pct != null && <div className="text-xs text-[var(--color-text-muted)]">{r.gross_margin_pct}%</div>}</td>
                  <td className="px-4 py-2.5 text-right">
                    <span className={r.net_margin != null && r.net_margin < 0 ? "text-[var(--color-danger)]" : ""}><Amt v={r.net_margin} /></span>
                    {r.net_margin_pct != null && <div className="text-xs text-[var(--color-text-muted)]">{r.net_margin_pct}%</div>}
                  </td>
                  <td className="px-4 py-2.5 text-right hidden md:table-cell">{r.receivable == null ? "—" : <Amt v={r.receivable} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DealDetail({ query, onBack }) {
  const { isOtherHidden } = usePrivacyMode();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [focus, setFocus] = useState("sale");

  useEffect(() => {
    setError(null);
    api.get(`/finance/deal-pnl?${query}&mask_other=${isOtherHidden}`, { skipCache: true })
      .then(({ data: d }) => setData(d)).catch((e) => setError(formatApiError(e.response?.data?.detail)));
  }, [query, isOtherHidden]);

  if (error) return <ErrorState hint={error} />;
  if (!data) return <Skeleton className="h-72 w-full" />;
  const p = data.pnl;
  const node = data.chain.find((n) => n.key === focus);

  return (
    <div className="space-y-5" data-testid="deal-detail">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={onBack} className="btn-ghost text-sm"><ArrowLeft size={14} /> All deals</button>
        <h2 className="font-heading font-bold text-xl">{data.customer || "Deal"}</h2>
      </div>

      {/* The lineage: one card per step, visitor to profit. */}
      <ol className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-9 gap-2" aria-label="Deal lineage from visitor to profit">
        {data.chain.map((n, i) => {
          const Icon = CHAIN_ICON[n.key] || Check;
          const selected = focus === n.key;
          return (
            <li key={n.key}>
              <button type="button" onClick={() => setFocus(n.key)} aria-pressed={selected}
                      className={`w-full h-full text-left rounded-[var(--radius-lg)] border p-3 ${selected
                        ? "border-[var(--color-primary)] ring-1 ring-[var(--color-primary)] bg-[var(--color-primary-soft)]"
                        : "border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)]"}`}>
                <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
                  <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full ${n.done ? "bg-[var(--color-success)] text-white" : "bg-[var(--color-surface-muted)] border border-[var(--color-border)]"}`}>
                    {n.done ? <Check size={12} aria-hidden /> : <span className="text-[10px]">{i + 1}</span>}
                  </span>
                  <Icon size={13} aria-hidden /> {n.label}
                </div>
                <div className="mt-1.5 text-sm font-medium text-[var(--color-text)] truncate" title={n.title}>{n.title || (n.done ? "" : "Not yet")}</div>
                <div className="text-sm tabular-nums">{n.amount === null && ["expenses", "pnl"].includes(n.key) && data.masked ? <Hidden /> : n.amount != null ? inr(n.amount) : ""}</div>
                {n.date && <div className="text-[11px] text-[var(--color-text-muted)]">{fmtDate(n.date)}</div>}
              </button>
            </li>
          );
        })}
      </ol>

      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <section className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4" aria-label="Deal profit and loss">
          <h3 className="font-heading font-semibold mb-1">Deal P&L</h3>
          <p className="text-xs text-[var(--color-text-muted)] mb-3">Revenue from the {p.revenue_basis}.</p>
          <dl className="text-sm">
            <Line label="Revenue" v={p.revenue} strong />
            <Line label="Vendor orders & POs" v={p.vendor_cost} minus />
            <Line label="Gross margin" v={p.gross_margin} total note={pct(p.gross_margin_pct)} />
            <Line label="Expenses" v={p.expenses} minus />
            <Line label="Incentives" v={p.incentives} minus />
            <Line label="Net profit" v={p.net_margin} total note={pct(p.net_margin_pct)} />
          </dl>
          <dl className="text-sm mt-4 pt-3 border-t border-[var(--color-border)] space-y-1">
            <div className="flex justify-between"><dt className="text-[var(--color-text-muted)]">Collected from customer</dt><dd><Amt v={p.collected} /></dd></div>
            {p.receivable != null && <div className="flex justify-between"><dt className="text-[var(--color-text-muted)]">Still to collect</dt><dd><Amt v={p.receivable} /></dd></div>}
            <div className="flex justify-between"><dt className="text-[var(--color-text-muted)]">Paid to vendors</dt><dd><Amt v={p.vendor_paid} /></dd></div>
            <div className="flex justify-between"><dt className="text-[var(--color-text-muted)]">Owed to vendors</dt><dd><Amt v={p.vendor_due} /></dd></div>
            <div className="flex justify-between"><dt className="text-[var(--color-text-muted)]">Spend awaiting approval</dt><dd><Amt v={p.pending_expenses} /></dd></div>
          </dl>
        </section>

        <section className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 min-w-0">
          <h3 className="font-heading font-semibold mb-1">{node?.label}</h3>
          {node?.detail && <p className="text-sm text-[var(--color-text-muted)] mb-3">{node.detail}</p>}
          <NodeItems node={node} masked={data.masked} />
        </section>
      </div>
    </div>
  );
}

function NodeItems({ node, masked }) {
  if (!node) return null;
  if (node.key === "expenses" && masked) return <p className="text-sm text-[var(--color-text-muted)]">Hidden in privacy mode.</p>;
  if (!node.items?.length) {
    return <p className="text-sm text-[var(--color-text-muted)]">{node.done ? `${node.title || node.label}${node.date ? ` · ${fmtDate(node.date)}` : ""}` : "Nothing recorded for this step yet."}</p>;
  }
  const cols = Object.keys(node.items[0]).filter((k) => !["id"].includes(k));
  const label = { no: "Number", amount: "Amount", paid: "Paid", status: "Status", stage: "Stage", vendor: "Vendor",
    date: "Date", title: "Item", category: "Category", source: "Source", mode: "Mode", request_no: "Request" };
  return (
    <div className="overflow-x-auto max-h-96">
      <table className="w-full text-sm">
        <thead className="text-xs text-[var(--color-text-muted)] border-b border-[var(--color-border)] sticky top-0 bg-[var(--color-surface)]">
          <tr>{cols.map((c) => <th key={c} className={`py-2 pr-3 font-medium ${["amount", "paid"].includes(c) ? "text-right" : "text-left"}`}>{label[c] || c}</th>)}</tr>
        </thead>
        <tbody>
          {node.items.map((it, i) => (
            <tr key={i} className="border-b border-[var(--color-border)] last:border-0">
              {cols.map((c) => (
                <td key={c} className={`py-2 pr-3 ${["amount", "paid"].includes(c) ? "text-right tabular-nums" : ""}`}>
                  {["amount", "paid"].includes(c) ? money(it[c]) : c === "date" ? fmtDate(it[c]) : (it[c] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
