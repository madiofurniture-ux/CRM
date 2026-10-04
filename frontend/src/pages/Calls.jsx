import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Topbar from "@/components/Topbar";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/context/AuthContext";
import { useTenantConfig } from "@/context/TenantConfigContext";
import api, { formatApiError } from "@/lib/api";
import { fmtDate, todayIST, isoDateIST } from "@/lib/format";
import { toast } from "sonner";
import { PhoneOutgoing, UserPlus, Trash2, ArrowUpRight } from "lucide-react";

/**
 * Call log: reps record every cold call (and follow-up / inbound call) as they
 * make it. Built for speed: number, name, one tap for the outcome, save, next.
 * An interested caller becomes a lead with one click ("Convert to lead"),
 * which links to an existing lead instead if the number is already one.
 */
const OUTCOMES = ["Interested", "Callback", "Not interested", "No answer", "Busy", "Wrong number"];
const CONNECTED = new Set(["Interested", "Callback", "Not interested"]);
const TYPES = ["Cold call", "Follow-up", "Inbound"];
const OUTCOME_TONE = {
  Interested: "bg-[var(--moss-soft)] text-[var(--color-success)]",
  Callback: "bg-[var(--color-primary-soft)] text-[var(--color-primary)]",
  "Not interested": "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]",
  "No answer": "bg-[var(--warn-soft)] text-[var(--color-warning)]",
  Busy: "bg-[var(--warn-soft)] text-[var(--color-warning)]",
  "Wrong number": "bg-[var(--danger-soft)] text-[var(--color-danger)]",
};
const RANGES = [["today", "Today"], ["7", "Last 7 days"], ["30", "Last 30 days"], ["all", "All"]];

const field = "px-2.5 py-2 rounded-[var(--radius-sm)] border border-[var(--color-border-strong,var(--color-border))] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)]";

const blank = (division = "Furniture") => ({
  phone: "", name: "", company: "", location: "", division, call_type: "Cold call",
  outcome: "", notes: "", callback_date: "",
});

export default function Calls() {
  const nav = useNavigate();
  const { canDo } = useAuth();
  const canCreate = canDo("calls", "create");
  const canEdit = canDo("calls", "edit");
  const canDelete = canDo("calls", "delete");
  const DIVISIONS = useTenantConfig().divisions.map((d) => d.slug);

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [form, setForm] = useState(blank());
  const [saving, setSaving] = useState(false);
  const [converting, setConverting] = useState(null);
  const [range, setRange] = useState("today");
  const [fOutcome, setFOutcome] = useState("All");
  const [fCaller, setFCaller] = useState("All");
  const [search, setSearch] = useState("");
  const phoneRef = useRef(null);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const { data } = await api.get("/calls", { skipCache: true });
      setRows(data);
    } catch (e) {
      setLoadError(formatApiError(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const since = useMemo(() => {
    if (range === "all") return "";
    if (range === "today") return todayIST();
    const d = new Date();
    d.setDate(d.getDate() - (Number(range) - 1));
    return isoDateIST(d);
  }, [range]);

  const callers = useMemo(() => [...new Set(rows.map((r) => r.by_user).filter(Boolean))].sort(), [rows]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) =>
      (!since || String(r.date || "") >= since)
      && (fOutcome === "All" || r.outcome === fOutcome)
      && (fCaller === "All" || r.by_user === fCaller)
      && (!q || [r.name, r.phone, r.company, r.location, r.notes].some((v) => String(v || "").toLowerCase().includes(q))));
  }, [rows, since, fOutcome, fCaller, search]);

  const stats = useMemo(() => {
    const total = filtered.length;
    const connected = filtered.filter((r) => CONNECTED.has(r.outcome)).length;
    const interested = filtered.filter((r) => r.outcome === "Interested").length;
    const converted = filtered.filter((r) => r.lead_id).length;
    return { total, connected, interested, converted,
      connectRate: total ? Math.round((connected / total) * 100) : 0 };
  }, [filtered]);

  const save = async (e) => {
    e?.preventDefault();
    if (!form.phone.trim()) { toast.error("Enter the phone number"); return; }
    if (!form.outcome) { toast.error("Pick how the call went"); return; }
    setSaving(true);
    try {
      const { data } = await api.post("/calls", { ...form, date: todayIST() });
      setRows((p) => [data, ...p]);
      toast.success("Call logged");
      setForm(blank(form.division));       // keep the division for the next call
      phoneRef.current?.focus();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const convert = async (r) => {
    setConverting(r.id);
    try {
      const { data } = await api.post(`/calls/${r.id}/convert`);
      setRows((p) => p.map((x) => (x.id === r.id ? { ...x, lead_id: data.lead_id } : x)));
      toast.success(data.created ? `Lead created for ${data.lead.name}` : `Linked to existing lead ${data.lead.name}`);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setConverting(null);
    }
  };

  const setOutcome = async (r, outcome) => {
    try {
      const { data } = await api.put(`/calls/${r.id}`, { outcome });
      setRows((p) => p.map((x) => (x.id === r.id ? { ...x, ...data } : x)));
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const remove = async (r) => {
    if (!window.confirm(`Delete the call to ${r.name || r.phone}?`)) return;
    try {
      await api.delete(`/calls/${r.id}`);
      setRows((p) => p.filter((x) => x.id !== r.id));
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  return (
    <>
      <Topbar title="Call Log" subtitle="Log every call as you make it, and convert interested callers to leads" />
      <div className="p-4 md:p-6 space-y-5" data-testid="calls-page">
        {canCreate && (
          <form onSubmit={save} className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3" data-testid="call-form">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_9rem_9rem]">
              <input ref={phoneRef} className={field} placeholder="Phone number" inputMode="tel" aria-label="Phone number"
                     value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} data-testid="call-phone" />
              <input className={field} placeholder="Name" aria-label="Name"
                     value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="call-name" />
              <input className={field} placeholder="Company or area (optional)" aria-label="Company or area"
                     value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
              <select className={field} aria-label="Division" value={form.division}
                      onChange={(e) => setForm({ ...form, division: e.target.value })}>
                {DIVISIONS.map((d) => <option key={d}>{d}</option>)}
              </select>
              <select className={field} aria-label="Call type" value={form.call_type}
                      onChange={(e) => setForm({ ...form, call_type: e.target.value })}>
                {TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
            </div>
            <fieldset>
              <legend className="sr-only">Outcome</legend>
              <div className="flex flex-wrap gap-2" data-testid="call-outcomes">
                {OUTCOMES.map((o) => (
                  <button key={o} type="button" aria-pressed={form.outcome === o}
                          onClick={() => setForm({ ...form, outcome: o })}
                          className={`px-3 py-1.5 rounded-full text-sm border ${form.outcome === o
                            ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
                            : "border-[var(--color-border-strong,var(--color-border))] text-[var(--color-text)] hover:bg-[var(--color-surface-muted)]"}`}>
                    {o}
                  </button>
                ))}
              </div>
            </fieldset>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto] items-start">
              <input className={field} placeholder="Notes: what they need, budget, best time to call" aria-label="Notes"
                     value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              {form.outcome === "Callback" && (
                <label className="flex items-center gap-2 text-sm">
                  Call back on
                  <input type="date" className={field} value={form.callback_date}
                         onChange={(e) => setForm({ ...form, callback_date: e.target.value })} />
                </label>
              )}
              <button type="submit" className="btn-primary justify-center" disabled={saving} data-testid="call-save">
                <PhoneOutgoing size={14} /> {saving ? "Saving…" : "Log call"}
              </button>
            </div>
          </form>
        )}

        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3" data-testid="call-stats">
          {[
            ["Calls", stats.total],
            ["Connected", stats.connected],
            ["Connect rate", `${stats.connectRate}%`],
            ["Interested", stats.interested],
            ["Converted to leads", stats.converted],
          ].map(([label, value]) => (
            <div key={label} className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
              <div className="text-xs text-[var(--color-text-muted)]">{label}</div>
              <div className="text-2xl font-heading font-bold text-[var(--color-text)] tabular-nums">{value}</div>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          <div role="group" aria-label="Date range" className="inline-flex max-w-full overflow-x-auto rounded-[var(--radius-sm)] border border-[var(--color-border-strong,var(--color-border))]">
            {RANGES.map(([k, label]) => (
              <button key={k} type="button" aria-pressed={range === k} onClick={() => setRange(k)}
                      className={`px-3 py-1.5 text-sm whitespace-nowrap ${range === k ? "bg-[var(--color-primary)] text-white" : "bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)]"}`}>
                {label}
              </button>
            ))}
          </div>
          <select className={field} aria-label="Outcome filter" value={fOutcome} onChange={(e) => setFOutcome(e.target.value)}>
            <option value="All">All outcomes</option>
            {OUTCOMES.map((o) => <option key={o}>{o}</option>)}
          </select>
          <select className={field} aria-label="Caller filter" value={fCaller} onChange={(e) => setFCaller(e.target.value)}>
            <option value="All">All callers</option>
            {callers.map((c) => <option key={c}>{c}</option>)}
          </select>
          <input className={`${field} flex-1 min-w-[12rem]`} placeholder="Search name, number, notes" aria-label="Search calls"
                 value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>

        {loadError ? (
          <ErrorState hint={loadError} onRetry={load} />
        ) : loading ? (
          <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
        ) : !filtered.length ? (
          <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)]">
            <EmptyState icon={PhoneOutgoing} title={rows.length ? "No calls match these filters" : "No calls logged yet"}
                        hint={rows.length ? "Try a wider date range." : "Log your first call above. It takes a few seconds."} />
          </div>
        ) : (
          <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Date</th>
                  <th className="px-4 py-2.5 font-medium">Contact</th>
                  <th className="px-4 py-2.5 font-medium">Outcome</th>
                  <th className="px-4 py-2.5 font-medium hidden md:table-cell">Notes</th>
                  <th className="px-4 py-2.5 font-medium hidden sm:table-cell">Caller</th>
                  <th className="px-4 py-2.5 font-medium text-right">Lead</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id} className="border-b border-[var(--color-border)] last:border-0 align-top" data-testid={`call-row-${r.id}`}>
                    <td className="px-4 py-2.5 whitespace-nowrap text-[var(--color-text-muted)]">
                      {fmtDate(r.date)}
                      <div className="text-xs">{r.call_type}</div>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-[var(--color-text)]">{r.name || "Unknown"}</div>
                      <div className="text-xs text-[var(--color-text-muted)]">
                        <a href={`tel:${r.phone}`} className="hover:underline">{r.phone}</a>
                        {r.company ? ` · ${r.company}` : ""}{r.division ? ` · ${r.division}` : ""}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      {canEdit ? (
                        <select aria-label={`Outcome for ${r.name || r.phone}`} value={r.outcome}
                                onChange={(e) => setOutcome(r, e.target.value)}
                                className={`px-2 py-1 rounded-full text-xs font-medium border-0 ${OUTCOME_TONE[r.outcome] || ""}`}>
                          {OUTCOMES.map((o) => <option key={o}>{o}</option>)}
                        </select>
                      ) : (
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${OUTCOME_TONE[r.outcome] || ""}`}>{r.outcome}</span>
                      )}
                      {r.outcome === "Callback" && r.callback_date && (
                        <div className="text-xs text-[var(--color-text-muted)] mt-1">Call back {fmtDate(r.callback_date)}</div>
                      )}
                    </td>
                    <td className="px-4 py-2.5 hidden md:table-cell text-[var(--color-text-muted)] max-w-xs">{r.notes}</td>
                    <td className="px-4 py-2.5 hidden sm:table-cell text-[var(--color-text-muted)]">{r.by_user}</td>
                    <td className="px-4 py-2.5 text-right whitespace-nowrap">
                      {r.lead_id ? (
                        <button type="button" onClick={() => nav("/leads")}
                                className="inline-flex items-center gap-1 text-[var(--color-primary)] hover:underline text-sm">
                          Lead <ArrowUpRight size={13} />
                        </button>
                      ) : canEdit && ["Interested", "Callback"].includes(r.outcome) ? (
                        <button type="button" className="btn-ghost text-xs" disabled={converting === r.id}
                                onClick={() => convert(r)} data-testid={`call-convert-${r.id}`}>
                          <UserPlus size={13} /> {converting === r.id ? "Converting…" : "Convert to lead"}
                        </button>
                      ) : null}
                      {canDelete && (
                        <button type="button" aria-label={`Delete call to ${r.name || r.phone}`} onClick={() => remove(r)}
                                className="ml-1 p-1.5 rounded text-[var(--color-danger)] hover:bg-[var(--danger-soft)] align-middle">
                          <Trash2 size={13} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
