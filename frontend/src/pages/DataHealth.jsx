import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { CheckCircle2, XCircle, RefreshCw } from "lucide-react";

export default function DataHealth() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api.get("/reports/data-health").then((r) => setData(r.data)).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const results = data?.results || [];

  return (
    <>
      <Topbar title="Data Health" subtitle="Business-rule integrity audit across your live data"
        actions={<button className="btn-ghost" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Re-run
        </button>} />
      <div className="p-6 space-y-6" data-testid="data-health-page">
        <div className="grid grid-cols-2 gap-4 max-w-md">
          <div className="rounded-2xl bg-emerald-50 dark:bg-emerald-950/30 p-5">
            <div className="text-[11px] uppercase tracking-widest font-semibold text-emerald-700 dark:text-emerald-400">Passed</div>
            <div className="text-2xl font-heading font-bold text-emerald-700 dark:text-emerald-400">{data?.passed ?? "—"}</div>
          </div>
          <div className="rounded-2xl bg-red-50 dark:bg-red-950/30 p-5">
            <div className="text-[11px] uppercase tracking-widest font-semibold text-red-700 dark:text-red-400">Failed</div>
            <div className="text-2xl font-heading font-bold text-red-700 dark:text-red-400">{data?.failed ?? "—"}</div>
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--line)] divide-y divide-[var(--line)]">
          {results.map((r) => (
            <div key={r.group + r.name} className="flex items-start gap-3 p-4">
              {r.status === "passed"
                ? <CheckCircle2 size={18} className="text-emerald-600 shrink-0 mt-0.5" />
                : <XCircle size={18} className="text-red-600 shrink-0 mt-0.5" />}
              <div>
                <div className="text-[10px] uppercase tracking-widest text-[var(--ink-2)] font-semibold">{r.group}</div>
                <div className="font-medium">{r.name}</div>
                {r.message && <div className="text-sm text-red-600 mt-1">{r.message}</div>}
              </div>
            </div>
          ))}
          {!loading && results.length === 0 && (
            <div className="p-8 text-center text-[var(--ink-2)] text-sm">No checks returned.</div>
          )}
        </div>
      </div>
    </>
  );
}
