import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Save, Plus, Trash2 } from "lucide-react";

let divisionSeq = 0;
const blankDivision = () => ({
  id: `new-${Date.now()}-${divisionSeq++}`, name: "", slug: "", brand_color: "#0062D2",
  logo_url: "", custom_sku_prefix: "", terms_and_conditions: "",
});

/** Shared Divisions master-data manager — the single place these get
 * created/edited/deleted. Every other screen's division dropdown just
 * consumes the resulting list, same as how Locations work in LocationsManager. */
export default function DivisionsManager({ divisions, onChange, onSaved }) {
  const [saving, setSaving] = useState(false);

  const updateDivision = (id, patch) => onChange(divisions.map((d) => (d.id === id ? { ...d, ...patch } : d)));
  const addDivision = () => onChange([...divisions, blankDivision()]);
  const removeDivision = (id) => onChange(divisions.filter((d) => d.id !== id));

  const save = async () => {
    if (saving || !divisions) return;
    if (divisions.some((d) => !d.name.trim() || !d.slug.trim())) {
      toast.error("Every division needs a name and a slug");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.put("/settings/business-profile", { divisions });
      onChange(data.divisions);
      // Refresh the app-wide roster too, so every other screen's division
      // dropdowns pick the change up without a page reload.
      await onSaved?.();
      toast.success("Divisions saved");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  return (
    <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-5 space-y-4" data-testid="divisions-settings">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-heading font-semibold text-sm">Divisions</div>
          <div className="text-xs text-[var(--ink-3)]">The business lines this CRM tracks — shown in every division dropdown.</div>
        </div>
        <button onClick={addDivision} disabled={!divisions} className="btn-ghost text-xs" data-testid="division-add">
          <Plus size={14} /> Add Division
        </button>
      </div>

      {!divisions && <div className="text-sm text-[var(--ink-3)]">Loading…</div>}

      {divisions?.map((d) => (
        <div key={d.id} className="grid grid-cols-2 gap-3 p-3 rounded-lg border border-[var(--border)]" data-testid={`division-row-${d.id}`}>
          <Fld l="Name" v={d.name} oc={(v) => updateDivision(d.id, { name: v })} placeholder="e.g. Madio Furniture" />
          <Fld l="Slug (used in filters)" v={d.slug} oc={(v) => updateDivision(d.id, { slug: v })} placeholder="e.g. Furniture" />
          <Fld l="SKU Prefix" v={d.custom_sku_prefix} oc={(v) => updateDivision(d.id, { custom_sku_prefix: v })} placeholder="e.g. MF" />
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Brand Color</label>
            <input type="color" value={d.brand_color || "#0062D2"} onChange={(e) => updateDivision(d.id, { brand_color: e.target.value })}
              className="w-full h-9 rounded-lg border border-[var(--border)] bg-white" />
          </div>
          <Fld l="Logo URL" v={d.logo_url} oc={(v) => updateDivision(d.id, { logo_url: v })} cls="col-span-2" placeholder="https://…" />
          <div className="col-span-2">
            <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Terms & Conditions</label>
            <textarea rows={2} value={d.terms_and_conditions} onChange={(e) => updateDivision(d.id, { terms_and_conditions: e.target.value })}
              className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
          </div>
          <button onClick={() => removeDivision(d.id)} className="col-span-2 justify-self-end text-xs text-[var(--danger)] flex items-center gap-1 hover:underline" data-testid={`division-remove-${d.id}`}>
            <Trash2 size={13} /> Remove
          </button>
        </div>
      ))}

      <button onClick={save} disabled={saving || !divisions} className="btn-primary disabled:opacity-60" data-testid="divisions-save">
        <Save size={14} /> {saving ? "Saving…" : "Save Divisions"}
      </button>
    </div>
  );
}

function Fld({ l, v, oc, cls = "", placeholder = "" }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input value={v} onChange={(e) => oc(e.target.value)} placeholder={placeholder}
        className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
    </div>
  );
}
