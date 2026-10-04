import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  Building, Store, LayoutGrid, Rocket, Check, CheckCircle2, Circle, ArrowRight, Loader2,
  Sofa, Ruler, PaintBucket, DoorOpen, Factory, Building2, Sun, GraduationCap, Stethoscope,
  Briefcase, BadgeCheck, AlertCircle, Landmark,
} from "lucide-react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useTenantConfig } from "@/context/TenantConfigContext";
import { STATE_OPTIONS, validateGstin } from "@/lib/india";

/**
 * Admin → Business Setup. Four steps that take a new company from an empty
 * tenant to a CRM shaped for its trade:
 *   1. Company & GST — the statutory profile invoices print from;
 *   2. Industry — an industry pack (divisions, lead stages, sources, fields);
 *   3. Modules — which bundles of screens are switched on;
 *   4. Go live — the remaining checklist, each item linking to its screen.
 * Backend: /setup/* in server.py, industry_packs.py, india.py.
 */
const PACK_ICONS = { Sofa, Ruler, PaintBucket, DoorOpen, Factory, Building2, Sun, GraduationCap, Stethoscope, Briefcase };

const STEPS = [
  { key: "company", label: "Company & GST", icon: Building },
  { key: "industry", label: "Industry", icon: Store },
  { key: "modules", label: "Modules", icon: LayoutGrid },
  { key: "golive", label: "Go live", icon: Rocket },
];

const fieldCls = "w-full px-3 py-2 rounded-[var(--radius-sm)] border bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)] focus:ring-2 focus:ring-[var(--color-primary-soft)]";
const labelCls = "block text-xs font-semibold text-[var(--color-text-muted)] mb-1";

function Field({ label, error, hint, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className={labelCls}>{label}</span>
      {children}
      {error ? (
        <span className="mt-1 flex items-center gap-1 text-xs text-[var(--color-danger)]"><AlertCircle size={12} />{error}</span>
      ) : hint ? (
        <span className="mt-1 block text-xs text-[var(--color-text-muted)]">{hint}</span>
      ) : null}
    </label>
  );
}

function ProgressRing({ percent }) {
  const r = 22;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative w-14 h-14 shrink-0" aria-label={`${percent}% set up`}>
      <svg viewBox="0 0 56 56" className="w-14 h-14 -rotate-90">
        <circle cx="28" cy="28" r={r} fill="none" stroke="var(--color-surface-muted)" strokeWidth="6" />
        <circle cx="28" cy="28" r={r} fill="none" stroke="var(--color-success)" strokeWidth="6"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - percent / 100)}
          style={{ transition: "stroke-dashoffset .4s ease" }} />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-xs font-bold font-mono">{percent}%</span>
    </div>
  );
}

// ── Step 1 ───────────────────────────────────────────────────────────────
function CompanyStep({ initial, onSaved }) {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  useEffect(() => setForm(initial), [initial]);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const g = validateGstin(form.gstin);

  // A valid GSTIN fills the state and PAN — the two most mistyped fields.
  useEffect(() => {
    if (g.valid) setForm((f) => ({ ...f, home_state: g.state, pan: g.pan }));
  }, [g.valid, g.state, g.pan]);

  const save = async () => {
    setSaving(true);
    setErrors({});
    try {
      const { data } = await api.put("/setup/company", form);
      toast.success("Company details saved");
      onSaved(data);
    } catch (e) {
      const d = e.response?.data?.detail;
      if (d?.fields) setErrors(d.fields);
      toast.error(formatApiError(d));
    } finally {
      setSaving(false);
    }
  };

  const border = (k) => (errors[k] ? "border-[var(--color-danger)]" : "border-[var(--color-border-strong,var(--color-border))]");

  return (
    <div className="space-y-6">
      <section>
        <h2 className="font-heading text-lg font-bold">Who you are</h2>
        <p className="text-sm text-[var(--color-text-muted)] mb-4">Printed on every quotation and tax invoice.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Business name (as customers know it)" error={errors.name}>
            <input className={`${fieldCls} ${border("name")}`} value={form.name || ""} onChange={set("name")} placeholder="Sunrise Interiors" />
          </Field>
          <Field label="Legal name (as on GST certificate)" error={errors.legal_name}>
            <input className={`${fieldCls} ${border("legal_name")}`} value={form.legal_name || ""} onChange={set("legal_name")} placeholder="Sunrise Interiors Private Limited" />
          </Field>
          <Field label="GSTIN" error={errors.gstin || (form.gstin && !g.valid ? g.error : "")}
            hint={g.valid ? undefined : "15 characters — leave blank if you are not registered"}>
            <div className="relative">
              <input className={`${fieldCls} ${border("gstin")} font-mono uppercase tracking-wider pr-9`} maxLength={15}
                value={form.gstin || ""} onChange={set("gstin")} placeholder="36ABCDE1234F1Z5" />
              {g.valid && <BadgeCheck size={18} className="absolute right-2.5 top-2 text-[var(--color-success)]" aria-label="Valid GSTIN" />}
            </div>
            {g.valid && (
              <span className="mt-1 block text-xs text-[var(--color-success)] font-medium">Valid · {g.state} · PAN {g.pan}</span>
            )}
          </Field>
          <Field label="State (GST registration)" error={errors.home_state}
            hint="Sales to other states are billed IGST; within the state, CGST + SGST.">
            <select className={`${fieldCls} ${border("home_state")}`} value={form.home_state || ""} onChange={set("home_state")} disabled={g.valid}>
              <option value="">Choose state…</option>
              {STATE_OPTIONS.map((s) => <option key={s.code} value={s.name}>{s.code} · {s.name}</option>)}
            </select>
          </Field>
          <Field label="Registered address" error={errors.address} className="sm:col-span-2">
            <textarea rows={2} className={`${fieldCls} ${border("address")}`} value={form.address || ""} onChange={set("address")} placeholder="Plot 12, Road No. 3, Kondapur, Hyderabad" />
          </Field>
          <Field label="PIN code" error={errors.pincode}>
            <input inputMode="numeric" maxLength={6} className={`${fieldCls} ${border("pincode")} font-mono`} value={form.pincode || ""} onChange={set("pincode")} placeholder="500084" />
          </Field>
          <Field label="PAN" error={errors.pan} hint={g.valid ? "Read from your GSTIN" : undefined}>
            <input maxLength={10} className={`${fieldCls} ${border("pan")} font-mono uppercase`} value={form.pan || ""} onChange={set("pan")} disabled={g.valid} placeholder="ABCDE1234F" />
          </Field>
          <Field label="Phone" error={errors.phone}>
            <input inputMode="tel" className={`${fieldCls} ${border("phone")}`} value={form.phone || ""} onChange={set("phone")} placeholder="98480 12345" />
          </Field>
          <Field label="Email" error={errors.email}>
            <input type="email" className={`${fieldCls} ${border("email")}`} value={form.email || ""} onChange={set("email")} placeholder="sales@sunrise.in" />
          </Field>
          <Field label="Invoice number prefix" hint="Starts every invoice number">
            <input maxLength={8} className={`${fieldCls} ${border("invoice_prefix")} font-mono uppercase`} value={form.invoice_prefix || ""} onChange={set("invoice_prefix")} />
          </Field>
          <Field label="Website">
            <input className={`${fieldCls} ${border("website")}`} value={form.website || ""} onChange={set("website")} placeholder="sunrise.in" />
          </Field>
        </div>
      </section>

      <section className="pt-5 border-t border-[var(--color-border)]">
        <h2 className="font-heading text-lg font-bold flex items-center gap-2"><Landmark size={18} /> Getting paid</h2>
        <p className="text-sm text-[var(--color-text-muted)] mb-4">Shown on quotations so customers can pay by NEFT, RTGS or UPI.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Bank name"><input className={`${fieldCls} ${border("bank_name")}`} value={form.bank_name || ""} onChange={set("bank_name")} placeholder="HDFC Bank, Kondapur" /></Field>
          <Field label="Account number"><input inputMode="numeric" className={`${fieldCls} ${border("bank_account_no")} font-mono`} value={form.bank_account_no || ""} onChange={set("bank_account_no")} /></Field>
          <Field label="IFSC" error={errors.bank_ifsc}><input maxLength={11} className={`${fieldCls} ${border("bank_ifsc")} font-mono uppercase`} value={form.bank_ifsc || ""} onChange={set("bank_ifsc")} placeholder="HDFC0001234" /></Field>
          <Field label="UPI ID"><input className={`${fieldCls} ${border("upi_id")}`} value={form.upi_id || ""} onChange={set("upi_id")} placeholder="sunrise@hdfcbank" /></Field>
        </div>
      </section>

      <div className="flex justify-end">
        <button type="button" className="btn-primary" onClick={save} disabled={saving || (form.gstin && !g.valid)}>
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Save and continue
        </button>
      </div>
    </div>
  );
}

// ── Step 2 ───────────────────────────────────────────────────────────────
function IndustryStep({ packs, current, onApplied }) {
  const [sel, setSel] = useState(current || "");
  const [replaceDivisions, setReplaceDivisions] = useState(true);
  const [replaceStages, setReplaceStages] = useState(true);
  const [busy, setBusy] = useState(false);
  useEffect(() => setSel((s) => s || current || ""), [current]);
  const pack = packs.find((p) => p.id === sel);

  const apply = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/setup/apply-pack", {
        pack: sel, replace_divisions: replaceDivisions, replace_lead_workflow: replaceStages,
      });
      if (data.lead_workflow === "kept" && data.lead_workflow_blocked_by?.length) {
        toast.warning(`Kept your lead stages: leads still sit on ${data.lead_workflow_blocked_by.join(", ")}. Rename them in Workflows first.`);
      } else {
        toast.success(`${data.name} applied`);
      }
      onApplied(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-heading text-lg font-bold">What does your business do?</h2>
        <p className="text-sm text-[var(--color-text-muted)]">
          We'll set up divisions, lead stages, lead sources and the fields your trade asks about. Everything stays editable.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" role="radiogroup" aria-label="Industry">
        {packs.map((p) => {
          const Icon = PACK_ICONS[p.icon] || Store;
          const on = p.id === sel;
          return (
            <button key={p.id} type="button" role="radio" aria-checked={on} onClick={() => setSel(p.id)}
              data-testid={`pack-${p.id}`}
              className={`text-left p-4 rounded-[var(--radius-lg)] border transition-all ${on
                ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)] ring-2 ring-[var(--color-primary)]/20"
                : "border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-primary)]/50 hover:shadow-sm"}`}>
              <div className="flex items-start gap-3">
                <span className={`w-10 h-10 rounded-[var(--radius-sm)] flex items-center justify-center shrink-0 ${on ? "bg-[var(--color-primary)] text-white" : "bg-[var(--color-surface-muted)] text-[var(--color-text)]"}`}>
                  <Icon size={20} strokeWidth={1.75} />
                </span>
                <div className="min-w-0">
                  <div className="font-semibold text-sm flex items-center gap-1.5">
                    {p.name}
                    {current === p.id && <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-success)]">current</span>}
                  </div>
                  <div className="text-xs text-[var(--color-text-muted)] mt-0.5 leading-snug">{p.tagline}</div>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {pack && (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-4 fadeup">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-text-muted)] mb-2">Lead pipeline</div>
            <ol className="stage-path__track" aria-label="Lead stages">
              {pack.lead_stages.map((s, i) => (
                <li key={s} className="stage-path__item">
                  <span title={s} className={`stage-path__step ${i === pack.lead_stages.length - 2 ? "is-won" : i === pack.lead_stages.length - 1 ? "is-lost" : i === 0 ? "is-current" : "is-incomplete"}`}>
                    <span>{s}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-text-muted)] mb-2">Divisions</div>
              <ul className="space-y-1 text-sm">{pack.divisions.map((d) => <li key={d} className="flex items-center gap-2"><Check size={14} className="text-[var(--color-success)]" />{d}</li>)}</ul>
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-text-muted)] mb-2">Fields you'll capture</div>
              <ul className="space-y-1 text-sm">{pack.custom_fields.map((f) => <li key={f.label} className="flex items-center gap-2"><Check size={14} className="text-[var(--color-success)]" />{f.label}</li>)}</ul>
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-text-muted)] mb-2">Lead sources</div>
              <div className="flex flex-wrap gap-1">{pack.lead_sources.map((s) => (
                <span key={s} className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]">{s}</span>
              ))}</div>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-[var(--color-border)]">
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="inline-flex items-center gap-2"><input type="checkbox" checked={replaceDivisions} onChange={(e) => setReplaceDivisions(e.target.checked)} /> Replace my divisions</label>
              <label className="inline-flex items-center gap-2"><input type="checkbox" checked={replaceStages} onChange={(e) => setReplaceStages(e.target.checked)} /> Replace my lead stages</label>
            </div>
            <button type="button" className="btn-primary" onClick={apply} disabled={busy} data-testid="apply-pack">
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Use {pack.name}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Step 3 ───────────────────────────────────────────────────────────────
function ModulesStep({ bundles, core, enabled, onSaved }) {
  const bundleOn = (b) => b.modules.every((m) => enabled.includes(m));
  const [picked, setPicked] = useState(() => Object.fromEntries(bundles.map((b) => [b.id, bundleOn(b)])));
  const [saving, setSaving] = useState(false);
  useEffect(() => { setPicked(Object.fromEntries(bundles.map((b) => [b.id, bundleOn(b)]))); }, [bundles, enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    const inBundles = new Set(bundles.flatMap((b) => b.modules));
    // Modules outside every bundle (e.g. a company's own go-live tools) keep their current state.
    const keep = enabled.filter((m) => !inBundles.has(m) && !core.includes(m));
    const wanted = new Set([...core, ...keep, ...bundles.filter((b) => picked[b.id]).flatMap((b) => b.modules)]);
    setSaving(true);
    try {
      const { data } = await api.put("/tenants/me/config", { enabled_modules: [...wanted] });
      toast.success("Modules updated");
      onSaved(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-heading text-lg font-bold">Switch on what you use</h2>
        <p className="text-sm text-[var(--color-text-muted)]">
          Leads, quotations, GST invoices, follow-ups, tasks, attendance, payroll and reports are always on. Add the rest when you need them.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {bundles.map((b) => (
          <label key={b.id} className={`flex items-start gap-3 p-4 rounded-[var(--radius-lg)] border cursor-pointer transition-colors ${picked[b.id] ? "border-[var(--color-primary)] bg-[var(--color-primary-soft)]" : "border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-muted)]"}`}>
            <input type="checkbox" className="mt-1" checked={!!picked[b.id]} onChange={(e) => setPicked((p) => ({ ...p, [b.id]: e.target.checked }))} />
            <span>
              <span className="block font-semibold text-sm">{b.label}</span>
              <span className="block text-xs text-[var(--color-text-muted)] mt-0.5 font-mono">{b.modules.join(" · ")}</span>
            </span>
          </label>
        ))}
      </div>
      <div className="flex justify-end">
        <button type="button" className="btn-primary" onClick={save} disabled={saving}>
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Save modules
        </button>
      </div>
    </div>
  );
}

// ── Step 4 ───────────────────────────────────────────────────────────────
function GoLiveStep({ status }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-heading text-lg font-bold">
          {status.percent === 100 ? "You're live." : "Almost there"}
        </h2>
        <p className="text-sm text-[var(--color-text-muted)]">{status.done} of {status.total} done. Each step opens the screen that finishes it.</p>
      </div>
      <ul className="divide-y divide-[var(--color-border)] rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)]">
        {status.steps.map((s) => (
          <li key={s.key}>
            <Link to={s.to} className="flex items-center gap-3 px-4 py-3 hover:bg-[var(--surface-hover)] transition-colors">
              {s.done
                ? <CheckCircle2 size={20} className="text-[var(--color-success)] shrink-0" />
                : <Circle size={20} className="text-[var(--color-border-strong,var(--color-border))] shrink-0" />}
              <span className="flex-1 min-w-0">
                <span className={`block text-sm font-semibold ${s.done ? "text-[var(--color-text-muted)] line-through decoration-1" : ""}`}>{s.label}</span>
                <span className="block text-xs text-[var(--color-text-muted)]">{s.hint}</span>
              </span>
              {!s.done && <ArrowRight size={16} className="text-[var(--color-primary)] shrink-0" />}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Setup() {
  const { tenant, refreshTenant } = useAuth();
  const { reload: reloadTenantConfig } = useTenantConfig();
  const [step, setStep] = useState("company");
  const [status, setStatus] = useState(null);
  const [catalog, setCatalog] = useState({ packs: [], bundles: [], core_modules: [] });

  const loadStatus = async () => {
    try {
      const { data } = await api.get("/setup/status", { skipCache: true });
      setStatus(data);
      return data;
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
      return null;
    }
  };

  useEffect(() => {
    (async () => {
      const [s, c] = await Promise.all([loadStatus(), api.get("/setup/packs").then((r) => r.data).catch(() => null)]);
      if (c) setCatalog(c);
      if (s) {
        const company = s.steps.find((x) => x.key === "company");
        const industry = s.steps.find((x) => x.key === "industry");
        setStep(!company?.done ? "company" : !industry?.done ? "industry" : "golive");
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const doneOf = useMemo(() => {
    const by = Object.fromEntries((status?.steps || []).map((s) => [s.key, s.done]));
    return { company: by.company, industry: by.industry, modules: by.industry, golive: status?.percent === 100 };
  }, [status]);

  const after = async (next) => {
    await Promise.all([loadStatus(), refreshTenant?.(), reloadTenantConfig?.()]);
    if (next) {
      setStep(next);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  return (
    <div>
      <Topbar title="Business Setup" subtitle="Shape the CRM to your company, trade and team" />
      <div className="p-4 md:p-6 grid gap-6 lg:grid-cols-[16rem_1fr] max-w-6xl">
        <aside className="space-y-4">
          <div className="flex items-center gap-3 p-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)]">
            <ProgressRing percent={status?.percent || 0} />
            <div className="min-w-0">
              <div className="text-sm font-semibold truncate">{status?.company?.trade_name || status?.company?.name || tenant?.display_name || "Your company"}</div>
              <div className="text-xs text-[var(--color-text-muted)]">{status ? `${status.done} of ${status.total} steps done` : "Loading…"}</div>
            </div>
          </div>
          <nav aria-label="Setup steps">
            <ol className="space-y-1">
              {STEPS.map((s, i) => {
                const Icon = s.icon;
                const active = step === s.key;
                return (
                  <li key={s.key}>
                    <button type="button" onClick={() => setStep(s.key)} aria-current={active ? "step" : undefined}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-sm)] text-sm text-left transition-colors ${active ? "bg-[var(--color-primary-soft)] text-[var(--color-primary)] font-semibold" : "hover:bg-[var(--color-surface-muted)]"}`}>
                      <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${doneOf[s.key] ? "bg-[var(--color-success)] text-white" : active ? "bg-[var(--color-primary)] text-white" : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"}`}>
                        {doneOf[s.key] ? <Check size={14} /> : i + 1}
                      </span>
                      <Icon size={16} className="shrink-0 opacity-70" />
                      {s.label}
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>
        </aside>

        <main className="min-w-0 p-5 md:p-6 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)]">
          {!status ? (
            <div className="py-16 flex justify-center"><Loader2 className="animate-spin text-[var(--color-text-muted)]" /></div>
          ) : step === "company" ? (
            <CompanyStep initial={status.company} onSaved={() => after("industry")} />
          ) : step === "industry" ? (
            <IndustryStep packs={catalog.packs} current={status.industry} onApplied={() => after("modules")} />
          ) : step === "modules" ? (
            <ModulesStep bundles={catalog.bundles} core={catalog.core_modules}
              enabled={tenant?.enabled_modules || []} onSaved={() => after("golive")} />
          ) : (
            <GoLiveStep status={status} />
          )}
        </main>
      </div>
    </div>
  );
}
