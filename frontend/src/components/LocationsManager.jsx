import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { X, Plus } from "lucide-react";

// Must match backend server.py's PALETTE_KEYS — the fixed color order both
// "create a new floor" and the seed data cycle through.
export const PALETTE_KEYS = ["brand", "blue", "moss", "warn", "danger", "purple", "teal", "pink"];
export const FLOOR_STYLES = {
  brand: { bg: "bg-[var(--brand-soft)]", text: "text-[var(--brand)]", dot: "bg-[var(--brand)]", swatch: "bg-[var(--brand)]" },
  blue: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500", swatch: "bg-blue-500" },
  moss: { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]", dot: "bg-[var(--moss)]", swatch: "bg-[var(--moss)]" },
  warn: { bg: "bg-[var(--warn-soft)]", text: "text-[var(--warn)]", dot: "bg-[var(--warn)]", swatch: "bg-[var(--warn)]" },
  danger: { bg: "bg-[var(--danger-soft)]", text: "text-[var(--danger)]", dot: "bg-[var(--danger)]", swatch: "bg-[var(--danger)]" },
  purple: { bg: "bg-purple-50", text: "text-purple-700", dot: "bg-purple-500", swatch: "bg-purple-500" },
  teal: { bg: "bg-teal-50", text: "text-teal-700", dot: "bg-teal-500", swatch: "bg-teal-500" },
  pink: { bg: "bg-pink-50", text: "text-pink-700", dot: "bg-pink-500", swatch: "bg-pink-500" },
};
export const NEUTRAL_STYLE = { bg: "bg-[var(--surface-2)]", text: "text-[var(--ink-2)]", dot: "bg-[var(--ink-3)]" };

export function FloorBadge({ name, floorByName }) {
  if (!name) return null;
  const floor = floorByName?.[name];
  const c = (floor && FLOOR_STYLES[floor.color]) || NEUTRAL_STYLE;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${c.bg} ${c.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {name}
    </span>
  );
}

const emptyForm = { name: "", color: "" };

/** Shared Locations (Floors/Warehouses) master-data manager — the single
 * place these get created/deleted. Inventory and Stock Ledger only consume
 * the resulting /floors list (dropdowns, badges), same as how Divisions are
 * managed once in Business Settings and consumed everywhere else. */
export default function LocationsManager({ floors, onChange }) {
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const remove = async (f) => {
    if (!window.confirm(`Delete location "${f.name}"? Existing records keep the plain text, just without a color.`)) return;
    await api.delete(`/floors/${f.id}`);
    onChange(floors.filter((x) => x.id !== f.id));
  };

  const save = async () => {
    if (saving) return;
    if (!form.name.trim()) { toast.error("Name is required"); return; }
    setSaving(true);
    try {
      const { data } = await api.post("/floors", form);
      toast.success("Location created");
      setShowModal(false); setForm(emptyForm);
      onChange([...floors, data]);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-5 space-y-4" data-testid="locations-settings">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-heading font-semibold text-sm">Locations</div>
          <div className="text-xs text-[var(--ink-3)]">Floors / warehouses used by Inventory and Stock Ledger.</div>
        </div>
        <button onClick={() => { setForm(emptyForm); setShowModal(true); }} className="btn-ghost text-xs" data-testid="location-add-btn">
          <Plus size={14} /> Add Location
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {floors.length === 0 && <span className="text-xs text-[var(--ink-3)]">None yet — create one above.</span>}
        {floors.map((f) => (
          <span key={f.id} className="group inline-flex items-center">
            <FloorBadge name={f.name} floorByName={{}} />
            <button
              onClick={() => remove(f)}
              className="opacity-0 group-hover:opacity-100 -ml-1.5 p-0.5 rounded-full hover:bg-[var(--danger-soft)] text-[var(--danger)] transition"
              title={`Delete "${f.name}"`}
              data-testid={`location-delete-${f.id}`}
            >
              <X size={11} />
            </button>
          </span>
        ))}
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-sm shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-heading font-semibold text-lg">New Location</h3>
              <button onClick={() => setShowModal(false)} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Location / Warehouse name</label>
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
              </div>
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-2">Colour</label>
                <div className="flex flex-wrap gap-2">
                  {PALETTE_KEYS.map((k) => (
                    <button
                      key={k}
                      type="button"
                      onClick={() => setForm({ ...form, color: k })}
                      title={k}
                      className={`w-8 h-8 rounded-full ${FLOOR_STYLES[k].swatch} ${form.color === k ? "ring-2 ring-offset-2 ring-[var(--ink)]" : ""}`}
                      data-testid={`location-color-${k}`}
                    />
                  ))}
                </div>
                {!form.color && <div className="text-[11px] text-[var(--ink-3)] mt-2">No colour picked — one will be assigned automatically.</div>}
              </div>
            </div>
            <div className="px-5 py-4 border-t flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setShowModal(false)}>Cancel</button>
              <button className="btn-primary disabled:opacity-60" onClick={save} disabled={saving} data-testid="location-save">
                {saving ? "Saving…" : "Create Location"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
