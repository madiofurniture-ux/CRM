import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Save } from "lucide-react";

// Mirrors backend ALL_MODULE_IDS (server.py) — kept as a flat list here since
// this is the only screen that needs the full set with human labels.
const MODULES = [
  { id: "dashboard", label: "Dashboard" }, { id: "alerts", label: "Follow-Up Alerts" },
  { id: "reports", label: "Reports" }, { id: "pipeline", label: "Pipeline" },
  { id: "quotes", label: "Quotations" }, { id: "quote-followups", label: "Quote Follow-ups" },
  { id: "sales", label: "Sales Register" }, { id: "visitors", label: "Visitors" },
  { id: "leads", label: "Leads" }, { id: "requirements", label: "Requirements" },
  { id: "configurator", label: "Configurator" }, { id: "architects", label: "Architects" },
  { id: "inventory", label: "Inventory" }, { id: "stock-ledger", label: "Stock Ledger" },
  { id: "inv-analytics", label: "Inventory Analytics" }, { id: "projects", label: "Projects" },
  { id: "dwsurvey", label: "D&W Survey" }, { id: "attendance", label: "Attendance" },
  { id: "tasks", label: "Tasks" }, { id: "meetplan", label: "Meet Planner" },
  { id: "customers", label: "Customers" }, { id: "invoice-gen", label: "Tax Invoices" },
  { id: "petty", label: "Petty Cash" }, { id: "outstanding", label: "Outstanding" },
  { id: "data-centre", label: "Data Centre" }, { id: "financial-year", label: "Financial Year" },
  { id: "workflows", label: "Workflows" }, { id: "roles", label: "Role Manager" },
];

export default function BusinessSettings() {
  const { user, tenant, refreshTenant } = useAuth();
  const isAdmin = user?.role === "admin";
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (tenant) setForm({
      display_name: tenant.display_name || "", short_name: tenant.short_name || "",
      logo_url: tenant.logo_url || "", primary_color: tenant.primary_color || "",
      secondary_color: tenant.secondary_color || "",
      enabled_modules: tenant.enabled_modules || MODULES.map((m) => m.id),
    });
  }, [tenant]);

  const toggle = (id) => setForm((f) => ({
    ...f,
    enabled_modules: f.enabled_modules.includes(id)
      ? f.enabled_modules.filter((m) => m !== id)
      : [...f.enabled_modules, id],
  }));

  const save = async () => {
    if (saving || !form) return;
    setSaving(true);
    try {
      await api.put("/tenants/me/config", form);
      await refreshTenant();
      toast.success("Business settings saved");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  if (!isAdmin) return <><Topbar title="Business Settings" /><div className="p-10 text-center text-[var(--ink-3)]">Admin access required.</div></>;
  if (!form) return <><Topbar title="Business Settings" /><div className="p-10 text-center text-[var(--ink-3)]">Loading…</div></>;

  return (
    <>
      <Topbar title="Business Settings" subtitle="Branding and which modules this business uses" />
      <div className="p-6 max-w-3xl space-y-6" data-testid="business-settings-page">
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 space-y-4">
          <div className="font-heading font-semibold text-sm">Branding</div>
          <div className="grid grid-cols-2 gap-4">
            <Fld l="Display Name" v={form.display_name} oc={(v) => setForm({ ...form, display_name: v })} placeholder="e.g. Acme Interiors CRM" />
            <Fld l="Short Name (sidebar logo)" v={form.short_name} oc={(v) => setForm({ ...form, short_name: v })} placeholder="e.g. ACME" />
            <Fld l="Logo URL" v={form.logo_url} oc={(v) => setForm({ ...form, logo_url: v })} cls="col-span-2" placeholder="https://…" />
            <Fld l="Primary Color" v={form.primary_color} oc={(v) => setForm({ ...form, primary_color: v })} placeholder="#C85A32" />
            <Fld l="Secondary Color" v={form.secondary_color} oc={(v) => setForm({ ...form, secondary_color: v })} placeholder="#4A5D4E" />
          </div>
        </div>

        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
          <div className="font-heading font-semibold text-sm mb-3">Enabled Modules</div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {MODULES.map((m) => (
              <label key={m.id} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-[var(--border)] cursor-pointer hover:bg-[var(--surface-2)] text-sm">
                <input type="checkbox" checked={form.enabled_modules.includes(m.id)} onChange={() => toggle(m.id)} className="accent-[var(--brand)]" />
                {m.label}
              </label>
            ))}
          </div>
        </div>

        <button onClick={save} disabled={saving} className="btn-primary disabled:opacity-60" data-testid="business-settings-save">
          <Save size={14} /> {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </>
  );
}

function Fld({ l, v, oc, cls = "", placeholder = "" }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input value={v} placeholder={placeholder} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
    </div>
  );
}
