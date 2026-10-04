import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, X, Loader2, Copy, Users, Building2, Search, PauseCircle, PlayCircle, CalendarPlus } from "lucide-react";
import Topbar from "@/components/Topbar";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";
import MetricCard from "@/components/MetricCard";
import api, { formatApiError } from "@/lib/api";
import { fmtDate, todayIST, isoDateIST } from "@/lib/format";

/**
 * Platform → Customers: the operator's console for the companies using the
 * CRM. Onboard a company (industry pack + first admin login), then manage
 * its plan, seats, trial and status. Owner tenant only — the server refuses
 * everyone else (/tenants, /platform/*; backend/plans.py).
 */
const field = "w-full px-3 py-2 rounded-[var(--radius-sm)] border border-[var(--color-border-strong,var(--color-border))] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)]";

const PLAN_TONE = {
  trial: "bg-[var(--warn-soft)] text-[var(--color-warning)]",
  starter: "bg-[var(--color-surface-muted)] text-[var(--ink-2)]",
  growth: "bg-[var(--color-primary-soft)] text-[var(--color-primary)]",
  business: "bg-[var(--color-primary-soft)] text-[var(--color-primary-hover)]",
  enterprise: "bg-[var(--moss-soft)] text-[var(--color-success)]",
  owner: "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]",
};

// Extends from the later of today and the current end, in IST calendar days.
const addDays = (iso, n) => {
  const from = iso && iso > todayIST() ? iso : todayIST();
  const d = new Date(`${from}T12:00:00+05:30`);
  d.setDate(d.getDate() + n);
  return isoDateIST(d);
};

function NewCustomer({ packs, plans, onClose, onCreated }) {
  const [f, setF] = useState({ name: "", industry: "", plan: "trial", admin_username: "", admin_pin: "",
    contact_name: "", contact_phone: "", city: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/tenants", f);
      setDone(data);
      onCreated();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const handover = done ? `Welcome to your CRM, ${done.tenant.name}!\nLogin: ${window.location.origin}/login\nUsername: ${done.admin_username}\nPIN: ${done.admin_pin}\nPlease change your PIN after the first login.` : "";

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="New customer">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} aria-hidden="true" />
      <div className="relative w-full max-w-md h-full overflow-y-auto bg-[var(--color-surface)] shadow-xl fadeup">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
          <h2 className="font-heading font-bold text-lg">{done ? "Customer ready" : "New customer"}</h2>
          <button type="button" onClick={onClose} className="p-1.5 rounded-[var(--radius-sm)] hover:bg-[var(--color-surface-muted)]" aria-label="Close"><X size={18} /></button>
        </div>
        {done ? (
          <div className="p-5 space-y-4">
            <p className="text-sm text-[var(--color-text-muted)]">
              Share these details with the customer. The PIN is shown only once.
            </p>
            <pre className="p-4 rounded-[var(--radius-lg)] bg-[var(--color-surface-muted)] text-sm font-mono whitespace-pre-wrap">{handover}</pre>
            {done.industry_pack?.name && (
              <p className="text-sm">Set up for <b>{done.industry_pack.name}</b>: {(done.industry_pack.divisions || []).join(", ")}.</p>
            )}
            <div className="flex gap-2">
              <button type="button" className="btn-primary" onClick={() => navigator.clipboard?.writeText(handover).then(() => toast.success("Copied"))}>
                <Copy size={14} /> Copy
              </button>
              <a className="btn-ghost" target="_blank" rel="noreferrer" href={`https://wa.me/?text=${encodeURIComponent(handover)}`}>Share on WhatsApp</a>
            </div>
          </div>
        ) : (
          <form onSubmit={submit} className="p-5 space-y-4">
            <label className="block"><span className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Company name *</span>
              <input required className={field} value={f.name} onChange={set("name")} placeholder="Pixel Eye Clinic" /></label>
            <label className="block"><span className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Industry</span>
              <select className={field} value={f.industry} onChange={set("industry")}>
                <option value="">Decide later (customer picks in Business Setup)</option>
                {packs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select></label>
            <label className="block"><span className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Plan</span>
              <select className={field} value={f.plan} onChange={set("plan")}>
                {plans.map((p) => <option key={p.id} value={p.id}>{p.label} — {p.max_users ? `${p.max_users} users` : "unlimited users"}</option>)}
              </select></label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block"><span className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Admin username</span>
                <input className={field} value={f.admin_username} onChange={set("admin_username")} placeholder="auto" /></label>
              <label className="block"><span className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Admin PIN</span>
                <input className={`${field} font-mono`} inputMode="numeric" value={f.admin_pin} onChange={set("admin_pin")} placeholder="auto" /></label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="block"><span className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Contact person</span>
                <input className={field} value={f.contact_name} onChange={set("contact_name")} /></label>
              <label className="block"><span className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">Contact phone</span>
                <input className={field} inputMode="tel" value={f.contact_phone} onChange={set("contact_phone")} /></label>
            </div>
            <label className="block"><span className="block text-xs font-semibold text-[var(--color-text-muted)] mb-1">City</span>
              <input className={field} value={f.city} onChange={set("city")} placeholder="Hyderabad" /></label>
            <button type="submit" className="btn-primary w-full justify-center" disabled={busy}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Create customer
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function Platform() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [plans, setPlans] = useState([]);
  const [packs, setPacks] = useState([]);
  const [showNew, setShowNew] = useState(false);
  const [q, setQ] = useState("");
  const [busyId, setBusyId] = useState("");

  const load = async () => {
    setError("");
    try {
      const { data } = await api.get("/tenants", { skipCache: true });
      setRows(data);
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail));
    }
  };

  useEffect(() => {
    load();
    api.get("/platform/plans").then((r) => setPlans(r.data)).catch(() => {});
    api.get("/setup/packs").then((r) => setPacks(r.data.packs || [])).catch(() => {});
  }, []);

  const packName = useMemo(() => Object.fromEntries(packs.map((p) => [p.id, p.name])), [packs]);

  const change = async (t, body, msg) => {
    setBusyId(t.id);
    try {
      await api.patch(`/platform/tenants/${t.id}`, body);
      toast.success(msg);
      await load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setBusyId("");
    }
  };

  const customers = (rows || []).filter((t) => t.plan !== "owner");
  const shown = customers.filter((t) => !q || `${t.name} ${t.city || ""} ${t.contact_name || ""}`.toLowerCase().includes(q.toLowerCase()));
  const active = customers.filter((t) => t.subscription?.can_write).length;
  const trials = customers.filter((t) => t.plan === "trial").length;
  const seats = customers.reduce((n, t) => n + (t.users || 0), 0);

  return (
    <div>
      <Topbar title="Customers" subtitle="Companies using your CRM — onboarding, plans and seats" />
      <div className="p-4 md:p-6 space-y-5">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MetricCard label="Companies" value={rows ? customers.length : undefined} loading={!rows} />
          <MetricCard label="Active" value={rows ? active : undefined} sub="can add and edit" loading={!rows} />
          <MetricCard label="On trial" value={rows ? trials : undefined} loading={!rows} />
          <MetricCard label="Users" value={rows ? seats : undefined} sub="across customers" loading={!rows} />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[14rem] max-w-sm">
            <Search size={15} className="absolute left-3 top-2.5 text-[var(--color-text-muted)]" />
            <input className={`${field} pl-9`} placeholder="Search company, city, contact" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <button type="button" className="btn-primary ml-auto" onClick={() => setShowNew(true)} data-testid="new-customer">
            <Plus size={15} /> New customer
          </button>
        </div>

        <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] overflow-x-auto">
          {error ? <ErrorState hint={error} onRetry={load} /> : !rows ? (
            <div className="py-14 flex justify-center"><Loader2 className="animate-spin text-[var(--color-text-muted)]" /></div>
          ) : shown.length === 0 ? (
            <EmptyState icon={Building2} title={customers.length ? "No company matches" : "No customers yet"}
              hint={customers.length ? "Try another search." : "Create the first one — it gets its own data, users and industry setup."} />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
                  <th className="px-4 py-3 font-semibold">Company</th>
                  <th className="px-4 py-3 font-semibold">Plan</th>
                  <th className="px-4 py-3 font-semibold">Users</th>
                  <th className="px-4 py-3 font-semibold text-right">Records</th>
                  <th className="px-4 py-3 font-semibold">Since</th>
                  <th className="px-4 py-3 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((t) => {
                  const s = t.subscription || {};
                  const suspended = s.status === "suspended";
                  return (
                    <tr key={t.id} className="border-b border-[var(--border-light)] last:border-0 hover:bg-[var(--surface-hover)]">
                      <td className="px-4 py-3">
                        <div className="font-semibold">{t.name}</div>
                        <div className="text-xs text-[var(--color-text-muted)]">
                          {[packName[t.industry] || (t.industry ? t.industry : "Industry not chosen"), t.city, t.contact_name].filter(Boolean).join(" · ")}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <select aria-label={`Plan for ${t.name}`} value={t.plan} disabled={busyId === t.id}
                            onChange={(e) => change(t, { plan: e.target.value }, `${t.name} moved to ${e.target.value}`)}
                            className={`px-2 py-0.5 rounded-full text-[11px] font-semibold border-0 ${PLAN_TONE[t.plan] || PLAN_TONE.starter}`}>
                            {plans.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                          </select>
                          {suspended && <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-[var(--danger-soft)] text-[var(--color-danger)]">Suspended</span>}
                        </div>
                        {t.plan === "trial" && (
                          <div className={`text-xs mt-1 ${s.can_write ? "text-[var(--color-text-muted)]" : "text-[var(--color-danger)] font-medium"}`}>
                            {s.can_write ? `${s.trial_days_left ?? "—"} days left` : "Trial ended"} · ends {fmtDate(s.trial_ends_at)}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono tabular-nums">
                        <span className="inline-flex items-center gap-1.5"><Users size={13} className="text-[var(--color-text-muted)]" />{t.users}{s.max_users ? ` / ${s.max_users}` : ""}</span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums">{t.records?.toLocaleString("en-IN")}</td>
                      <td className="px-4 py-3 text-[var(--color-text-muted)]">{fmtDate(t.created_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1">
                          {t.plan === "trial" && (
                            <button type="button" title="Extend trial by 14 days" disabled={busyId === t.id}
                              onClick={() => change(t, { trial_ends_at: addDays(s.trial_ends_at, 14) }, "Trial extended by 14 days")}
                              className="p-2 rounded-[var(--radius-sm)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text)]">
                              <CalendarPlus size={16} />
                            </button>
                          )}
                          <button type="button" disabled={busyId === t.id}
                            title={suspended ? "Reactivate" : "Suspend"}
                            onClick={() => {
                              if (!suspended && !window.confirm(`Suspend ${t.name}? Their users will be signed out until you reactivate.`)) return;
                              change(t, { status: suspended ? "active" : "suspended" }, suspended ? `${t.name} reactivated` : `${t.name} suspended`);
                            }}
                            className={`p-2 rounded-[var(--radius-sm)] hover:bg-[var(--color-surface-muted)] ${suspended ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}`}>
                            {suspended ? <PlayCircle size={16} /> : <PauseCircle size={16} />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
      {showNew && <NewCustomer packs={packs} plans={plans} onClose={() => setShowNew(false)} onCreated={load} />}
    </div>
  );
}
