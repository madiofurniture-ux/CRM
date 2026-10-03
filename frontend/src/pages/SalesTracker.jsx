import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import ErrorState from "@/components/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import api, { formatApiError } from "@/lib/api";
import { inrFull, fmtDate, todayIST } from "@/lib/format";
import { Download } from "lucide-react";

/**
 * Division sales tracker — MADIO's Paints Sales Tracker built from CRM data,
 * for any division: KPI cards, pipeline by Pending / Active / Won / Lost,
 * sales register, applicator site schedule, weekly activity log, monthly and
 * quarterly summaries. Figures come from GET /analytics/tracker; the server
 * applies the caller's analytics visibility.
 */
const DIVISIONS = ["MAP", "Furniture", "D&W"];
const CAT_STYLE = {
  Pending: "bg-amber-50 text-amber-700", Active: "bg-blue-50 text-blue-700",
  Won: "bg-emerald-50 text-emerald-700", Lost: "bg-rose-50 text-rose-700",
};

function rangeFor(key) {
  const today = todayIST();
  const [y, m] = today.split("-").map(Number);
  const fy = m >= 4 ? y : y - 1;
  if (key === "quarter") {
    const qm = m <= 3 ? 1 : 4 + Math.floor((m - 4) / 3) * 3;      // Apr, Jul, Oct, Jan
    return [`${y}-${String(qm).padStart(2, "0")}-01`, today];
  }
  if (key === "month") return [`${today.slice(0, 7)}-01`, today];
  if (key === "lastfy") return [`${fy - 1}-04-01`, `${fy}-03-31`];
  return [`${fy}-04-01`, today];
}

const pctTxt = (v) => (v === null || v === undefined ? "—" : `${v}%`);
const num = (v) => (v ? Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "—");

function fmtKpi(k) {
  if (k.format === "money") return inrFull(k.value || 0);
  if (k.format === "percent") return pctTxt(k.value);
  return num(k.value);
}

// One table definition per tab: columns are [key, label, kind].
const TABLES = {
  pipeline: {
    label: "Pipeline", cols: [["client", "Client"], ["quote_no", "Quote"], ["reference", "Reference"],
      ["next_step", "Next step / remarks"], ["value", "Quote value", "money"], ["sft", "Sft", "num"],
      ["stage", "Status"], ["category", "Category", "cat"], ["month", "Month"], ["priority", "Priority"]],
  },
  register: {
    label: "Sales Register", cols: [["client", "Client"], ["quote_no", "Quotation no."], ["date", "Date", "date"],
      ["value", "Order value", "money"], ["sft", "Sft", "num"], ["advance", "Advance", "money"],
      ["balance", "Balance due", "money"], ["collected_pct", "Collected", "pct"], ["status", "Status"]],
  },
  schedule: {
    label: "Site Schedule", cols: [["site", "Site / client"], ["applicator", "Applicator"], ["start", "Start", "date"],
      ["end", "End", "date"], ["days", "Days", "num"], ["sft", "Sft", "num"], ["status", "Status", "status"]],
  },
  log: {
    label: "Weekly Log", cols: [["date", "Date", "date"], ["week", "Wk#"], ["client", "Client / prospect"],
      ["activity", "Activity"], ["quote_value", "Quote value", "money"], ["order_value", "Order value", "money"],
      ["advance", "Advance", "money"], ["status", "Status"], ["notes", "Notes"]],
  },
  monthly: {
    label: "Monthly Summary", cols: [["label", "Month"], ["quotes", "Quotes"], ["quote_value", "Quoted", "money"],
      ["orders", "Orders"], ["order_value", "Confirmed", "money"], ["conversion", "Conversion", "pct"],
      ["advance", "Advance", "money"], ["balance", "Balance", "money"], ["collection_rate", "Collected", "pct"],
      ["sft", "Sft", "num"]],
  },
  quarterly: {
    label: "Quarterly Report", cols: [["period", "Quarter"], ["quotes", "Quotes"], ["quote_value", "Quoted", "money"],
      ["orders", "Orders"], ["order_value", "Confirmed", "money"], ["conversion", "Conversion", "pct"],
      ["advance", "Advance", "money"], ["balance", "Balance", "money"], ["collection_rate", "Collected", "pct"],
      ["sft", "Sft", "num"]],
  },
};

function cellText(row, [key, , kind]) {
  const v = row[key];
  if (kind === "money") return v ? inrFull(v) : "—";
  if (kind === "pct") return pctTxt(v);
  if (kind === "num") return num(v);
  if (kind === "date") return v ? fmtDate(v) : "—";
  return v === null || v === undefined || v === "" ? "—" : String(v);
}

function toCsv(rows, cols) {
  const esc = (s) => `"${String(s ?? "").replace(/"/g, '""')}"`;
  return [cols.map((c) => esc(c[1])).join(","), ...rows.map((r) => cols.map((c) => esc(r[c[0]])).join(","))].join("\n");
}

function DataTable({ rows, cols, testId, empty }) {
  return (
    <div className="overflow-x-auto" data-testid={testId}>
      <table className="w-full text-sm">
        <thead className="bg-[var(--surface-2)]">
          <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
            {cols.map(([k, label, kind]) => (
              <th key={k} className={`px-3 py-2 font-semibold whitespace-nowrap ${["money", "num", "pct"].includes(kind) ? "text-right" : "text-left"}`}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id || `${r.date}-${i}`} className={`border-t border-[var(--border-light)] ${r.overdue ? "bg-rose-50/50" : ""}`}>
              {cols.map((c) => {
                const [k, , kind] = c;
                if (kind === "cat") return <td key={k} className="px-3 py-2"><span className={`px-2 py-0.5 rounded-full text-xs font-medium ${CAT_STYLE[r[k]] || ""}`}>{r[k]}</span></td>;
                return (
                  <td key={k} className={`px-3 py-2 ${["money", "num", "pct"].includes(kind) ? "text-right font-mono" : ""} ${k === "next_step" || k === "notes" ? "max-w-xs truncate" : "whitespace-nowrap"}`}
                      title={k === "next_step" || k === "notes" ? r[k] : undefined}>
                    {cellText(r, c)}{kind === "status" && r.overdue ? <span className="ml-1 text-xs text-rose-600">overdue</span> : null}
                  </td>
                );
              })}
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={cols.length} className="text-center py-8 text-[var(--ink-3)]">{empty || "Nothing in this period."}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

export default function SalesTracker() {
  const [division, setDivision] = useState(() => { try { return localStorage.getItem("tracker_division") || "MAP"; } catch { return "MAP"; } });
  const [preset, setPreset] = useState("fy");
  const [[start, end], setRange] = useState(rangeFor("fy"));
  const [tab, setTab] = useState("dashboard");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => { try { localStorage.setItem("tracker_division", division); } catch { /* per-viewer nicety only */ } }, [division]);
  useEffect(() => {
    let live = true;
    setData(null);
    setError("");
    api.get("/analytics/tracker", { params: { division, start, end }, skipCache: true })
      .then(({ data: d }) => { if (live) setData(d); })
      .catch((e) => { if (live) setError(formatApiError(e.response?.data?.detail) || "Couldn't load the tracker"); });
    return () => { live = false; };
  }, [division, start, end]);

  const pickPreset = (k) => { setPreset(k); setRange(rangeFor(k)); };
  const download = () => {
    const def = TABLES[tab];
    if (!def || !data) return;
    const blob = new Blob([toCsv(data.tables[tab] || [], def.cols)], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${division}-${def.label.replace(/\s+/g, "-")}-${start}-to-${end}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const t = data?.tables || {};
  return (
    <div className="flex flex-col min-h-full">
      <Topbar title="Sales Tracker" subtitle="Pipeline, orders, collections and site schedule by division" />
      <div className="p-4 md:p-6 w-full space-y-4" data-testid="sales-tracker">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-[var(--border)] overflow-hidden" role="tablist">
            {DIVISIONS.map((d) => (
              <button key={d} type="button" onClick={() => setDivision(d)} aria-selected={division === d}
                      data-testid={`tracker-div-${d}`}
                      className={`px-3 py-1.5 text-sm ${division === d ? "bg-[var(--brand)] text-white" : "bg-[var(--surface)]"}`}>{d}</button>
            ))}
          </div>
          <select value={preset} onChange={(e) => pickPreset(e.target.value)} className="px-2 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm">
            <option value="fy">This financial year</option>
            <option value="quarter">This quarter</option>
            <option value="month">This month</option>
            <option value="lastfy">Last financial year</option>
            <option value="custom">Custom</option>
          </select>
          <input type="date" value={start} onChange={(e) => { setPreset("custom"); setRange([e.target.value, end]); }}
                 className="px-2 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm" />
          <span className="text-[var(--ink-3)] text-sm">to</span>
          <input type="date" value={end} onChange={(e) => { setPreset("custom"); setRange([start, e.target.value]); }}
                 className="px-2 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm" />
          {data?.scope && data.scope !== "all" && <span className="text-xs text-[var(--ink-3)]">Showing {data.scope === "mine" ? "your" : "your team's"} records</span>}
        </div>

        {error ? <ErrorState title="Couldn't load the tracker" hint={error} /> : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3" data-testid="tracker-kpis">
              {(data?.kpis || Array.from({ length: 6 })).map((k, i) => (
                <div key={k?.key || i} className="bg-[var(--surface)] border border-[var(--border-light)] rounded-2xl p-3">
                  {k ? (<>
                    <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">{k.label}</div>
                    <div className="text-lg font-semibold mt-1 font-mono">{fmtKpi(k)}</div>
                  </>) : <Skeleton className="h-10" />}
                </div>
              ))}
            </div>

            <div className="flex gap-1 border-b border-[var(--border)] overflow-x-auto">
              {[["dashboard", "Dashboard"], ...Object.entries(TABLES).map(([k, v]) => [k, v.label])].map(([k, label]) => (
                <button key={k} type="button" onClick={() => setTab(k)} data-testid={`tracker-tab-${k}`}
                        className={`px-3 py-2 text-sm whitespace-nowrap border-b-2 -mb-px ${tab === k ? "border-[var(--brand)] text-[var(--brand)] font-medium" : "border-transparent text-[var(--ink-2)]"}`}>{label}</button>
              ))}
            </div>

            {!data ? <Skeleton className="h-64 rounded-2xl" /> : tab === "dashboard" ? (
              <div className="grid lg:grid-cols-2 gap-4">
                <section className="bg-[var(--surface)] border border-[var(--border-light)] rounded-2xl overflow-hidden">
                  <h2 className="font-heading font-semibold text-sm p-3 border-b border-[var(--border-light)]">Pipeline status breakdown</h2>
                  <DataTable testId="tracker-breakdown" rows={t.breakdown || []}
                             cols={[["category", "Category", "cat"], ["count", "Quotes", "num"], ["value", "Value", "money"],
                                    ["share", "Share", "pct"], ["sft", "Sft", "num"]]} />
                  <div className="p-3 space-y-1">
                    {(t.breakdown || []).map((b) => (
                      <div key={b.category} className="flex items-center gap-2 text-xs">
                        <span className="w-14 text-[var(--ink-3)]">{b.category}</span>
                        <div className="flex-1 h-2 rounded bg-[var(--surface-2)]">
                          <div className={`h-2 rounded ${{ Pending: "bg-amber-400", Active: "bg-blue-500", Won: "bg-emerald-500", Lost: "bg-rose-400" }[b.category]}`}
                               style={{ width: `${Math.min(b.share || 0, 100)}%` }} />
                        </div>
                        <span className="w-12 text-right font-mono">{pctTxt(b.share)}</span>
                      </div>
                    ))}
                  </div>
                </section>
                <section className="bg-[var(--surface)] border border-[var(--border-light)] rounded-2xl overflow-hidden">
                  <h2 className="font-heading font-semibold text-sm p-3 border-b border-[var(--border-light)]">Top open prospects</h2>
                  <DataTable testId="tracker-top" rows={t.top_prospects || []} empty="No open quotations in this period."
                             cols={[["client", "Client"], ["value", "Quote value", "money"], ["sft", "Sft", "num"],
                                    ["category", "Category", "cat"], ["next_step", "Next step"]]} />
                </section>
                <section className="bg-[var(--surface)] border border-[var(--border-light)] rounded-2xl overflow-hidden lg:col-span-2">
                  <h2 className="font-heading font-semibold text-sm p-3 border-b border-[var(--border-light)]">Confirmed orders</h2>
                  <DataTable rows={(t.register || []).slice(0, 10)} cols={TABLES.register.cols} empty="No confirmed orders in this period." />
                </section>
                <section className="bg-[var(--surface)] border border-[var(--border-light)] rounded-2xl overflow-hidden lg:col-span-2">
                  <h2 className="font-heading font-semibold text-sm p-3 border-b border-[var(--border-light)]">Weekly activity</h2>
                  <DataTable rows={(t.weekly || []).slice(0, 8)} empty="No activity in this period."
                             cols={[["week", "Week"], ["activities", "Activities", "num"], ["quote_value", "Quoted", "money"],
                                    ["order_value", "Confirmed", "money"], ["advance", "Advance", "money"]]} />
                </section>
              </div>
            ) : (
              <section className="bg-[var(--surface)] border border-[var(--border-light)] rounded-2xl overflow-hidden">
                <div className="p-3 border-b border-[var(--border-light)] flex items-center justify-between">
                  <h2 className="font-heading font-semibold text-sm">{TABLES[tab].label} <span className="text-[var(--ink-3)] font-normal">({(t[tab] || []).length})</span></h2>
                  <button type="button" className="btn-ghost text-xs" onClick={download} data-testid="tracker-csv"><Download size={13} /> CSV</button>
                </div>
                <DataTable testId={`tracker-table-${tab}`} rows={t[tab] || []} cols={TABLES[tab].cols}
                           empty={tab === "schedule" ? "No sites scheduled. Set the applicator, start and target dates on the project." : undefined} />
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
