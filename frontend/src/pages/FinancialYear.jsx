import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { CalendarRange, Eye, EyeOff, Save } from "lucide-react";

/**
 * Admin screen: choose which financial years appear across the CRM.
 *
 * Hiding a year is a VIEW filter only — no record is ever deleted, and rows
 * with no usable date are always kept visible so nothing silently disappears.
 */
export default function FinancialYear() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [years, setYears] = useState([]);
  const [hidden, setHidden] = useState([]);
  const [currentFy, setCurrentFy] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/fy/options");
      setYears(data.years || []);
      setHidden(data.hidden_fys || []);
      setCurrentFy(data.current_fy || "");
      setDirty(false);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = (fy) => {
    if (!isAdmin) return;
    setHidden((h) => (h.includes(fy) ? h.filter((x) => x !== fy) : [...h, fy]));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/fy/settings", { hidden_fys: hidden });
      toast.success(hidden.length ? `${hidden.length} year(s) hidden` : "Showing all years");
      await load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const visibleCount = years.filter((y) => !hidden.includes(y.fy))
                            .reduce((a, y) => a + y.records, 0);
  const hiddenCount = years.filter((y) => hidden.includes(y.fy))
                           .reduce((a, y) => a + y.records, 0);

  return (
    <>
      <Topbar
        title="Financial Year"
        subtitle={`Current FY ${currentFy} · ${visibleCount.toLocaleString("en-IN")} records visible${hiddenCount ? ` · ${hiddenCount.toLocaleString("en-IN")} hidden` : ""}`}
      />

      <div className="p-6 space-y-5">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 text-sm text-[var(--ink-2)] flex gap-3">
          <CalendarRange size={18} className="shrink-0 mt-0.5 text-[var(--brand)]" />
          <div>
            Financial years run <b>1 April → 31 March</b>. Hiding a year removes it from
            lists across the CRM so the team sees only current business.
            <br />
            <span className="text-[var(--ink-3)]">
              Nothing is deleted — un-hide any year to bring it straight back. Records with
              no usable date always stay visible.
            </span>
          </div>
        </div>

        {loading ? (
          <div className="text-sm text-[var(--ink-3)]">Loading…</div>
        ) : (
          <div className="rounded-xl border border-[var(--border)] overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] text-[var(--ink-3)]">
                <tr>
                  <th className="text-left px-4 py-2.5 font-medium">Financial year</th>
                  <th className="text-right px-4 py-2.5 font-medium">Records</th>
                  <th className="text-left px-4 py-2.5 font-medium">Status</th>
                  <th className="text-right px-4 py-2.5 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {years.map((y) => {
                  const isHidden = hidden.includes(y.fy);
                  const isCurrent = y.fy === currentFy;
                  return (
                    <tr key={y.fy} className="border-t border-[var(--border)]"
                        data-testid={`fy-row-${y.fy}`}>
                      <td className="px-4 py-2.5 font-medium">
                        FY {y.fy}
                        {isCurrent && (
                          <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-[var(--brand)] text-white align-middle">
                            CURRENT
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        {y.records.toLocaleString("en-IN")}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={isHidden ? "text-[var(--ink-3)]" : "text-emerald-600"}>
                          {isHidden ? "Hidden" : "Visible"}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <button
                          onClick={() => toggle(y.fy)}
                          disabled={!isAdmin}
                          data-testid={`fy-toggle-${y.fy}`}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-[var(--border)] hover:border-[var(--brand)] disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {isHidden ? <Eye size={14} /> : <EyeOff size={14} />}
                          {isHidden ? "Show" : "Hide"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {!years.length && (
                  <tr><td colSpan={4} className="px-4 py-6 text-center text-[var(--ink-3)]">
                    No dated records yet.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {isAdmin ? (
          <button
            onClick={save}
            disabled={saving || !dirty}
            data-testid="fy-save"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--brand)] text-white text-sm disabled:opacity-40"
          >
            <Save size={15} />
            {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
          </button>
        ) : (
          <div className="text-sm text-[var(--ink-3)]">
            Only an administrator can change which years are visible.
          </div>
        )}
      </div>
    </>
  );
}
