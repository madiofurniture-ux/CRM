import { useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import useCustomFields from "@/hooks/useCustomFields";
import { toast } from "sonner";
import { Plus, Trash2, SlidersHorizontal } from "lucide-react";

const ENTITY_LABEL = { lead: "Leads", customer: "Customers" };
const TYPES = ["text", "number", "date", "select", "boolean"];
const empty = { label: "", type: "text", options: [], show_table: false, show_filter: false, show_detail: true };

export default function CustomFields() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [entity, setEntity] = useState("lead");
  const { defs, reload } = useCustomFields(entity);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);

  const create = async () => {
    if (!form.label.trim()) return toast.error("Label is required");
    setSaving(true);
    try {
      await api.post("/custom-fields", {
        entity, label: form.label.trim(), type: form.type,
        options: form.type === "select" ? form.options : [],
        show_table: form.show_table, show_filter: form.show_filter, show_detail: form.show_detail,
      });
      toast.success("Field added");
      setForm(empty);
      setAdding(false);
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const toggleFlag = async (def, flag) => {
    await api.put(`/custom-fields/${def.id}`, { [flag]: !def[flag] });
    reload();
  };

  const remove = async (def) => {
    if (!window.confirm(`Remove "${def.label}"? Existing values on records are kept but hidden.`)) return;
    await api.delete(`/custom-fields/${def.id}`);
    reload();
  };

  if (!isAdmin) {
    return (
      <>
        <Topbar title="Custom Fields" />
        <div className="p-6 text-sm text-[var(--ink-3)]">Only an administrator can manage custom fields.</div>
      </>
    );
  }

  return (
    <>
      <Topbar title="Custom Fields" subtitle="Add extra fields to Leads and Customers without a code change" />
      <div className="p-6 space-y-5">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 text-sm text-[var(--ink-2)] flex gap-3">
          <SlidersHorizontal size={18} className="shrink-0 mt-0.5 text-[var(--brand)]" />
          <div>Define extra fields per record type. Choose where each one shows up: the list table, the filter bar, or the detail form.</div>
        </div>

        <div className="flex flex-wrap gap-2" data-testid="cf-entities">
          {Object.keys(ENTITY_LABEL).map((k) => (
            <button key={k} onClick={() => setEntity(k)} data-testid={`cf-tab-${k}`}
                    className={`px-3 py-1.5 rounded-lg text-sm border transition ${
                      entity === k ? "bg-[var(--brand)] text-white border-[var(--brand)]" : "border-[var(--border)] hover:border-[var(--brand)]"
                    }`}>
              {ENTITY_LABEL[k]}
            </button>
          ))}
        </div>

        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[var(--surface-2)] text-[var(--ink-3)]">
              <tr className="text-[11px] uppercase tracking-wider">
                <th className="px-3 py-2 text-left">Label</th>
                <th className="px-3 py-2 text-left">Type</th>
                <th className="w-20 px-3 py-2 text-center">Table</th>
                <th className="w-20 px-3 py-2 text-center">Filter</th>
                <th className="w-20 px-3 py-2 text-center">Detail</th>
                <th className="w-10"></th>
              </tr>
            </thead>
            <tbody>
              {defs.map((d) => (
                <tr key={d.id} className="border-t border-[var(--border)]" data-testid={`cf-row-${d.key}`}>
                  <td className="px-3 py-2 font-medium">{d.label}</td>
                  <td className="px-3 py-2 text-[var(--ink-2)]">{d.type}</td>
                  <td className="px-3 py-2 text-center">
                    <input type="checkbox" checked={d.show_table} onChange={() => toggleFlag(d, "show_table")} />
                  </td>
                  <td className="px-3 py-2 text-center">
                    <input type="checkbox" checked={d.show_filter} onChange={() => toggleFlag(d, "show_filter")} />
                  </td>
                  <td className="px-3 py-2 text-center">
                    <input type="checkbox" checked={d.show_detail} onChange={() => toggleFlag(d, "show_detail")} />
                  </td>
                  <td className="px-2 py-2">
                    <button onClick={() => remove(d)} className="p-1 rounded text-[var(--danger)] hover:bg-[var(--danger-soft)]">
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
              {!defs.length && !adding && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-[var(--ink-3)]">No custom fields yet for {ENTITY_LABEL[entity]}.</td></tr>
              )}
            </tbody>
          </table>

          {adding ? (
            <div className="px-4 py-3 border-t border-[var(--border)] flex flex-wrap items-end gap-2">
              <input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })}
                     placeholder="Label, e.g. Budget Band"
                     className="px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm w-56" />
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}
                      className="px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              {form.type === "select" && (
                <input
                  value={form.options.join(", ")}
                  onChange={(e) => setForm({ ...form, options: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
                  placeholder="Options, comma separated"
                  className="px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm w-56"
                />
              )}
              <button onClick={create} disabled={saving} className="btn-primary text-sm disabled:opacity-60">
                {saving ? "Saving…" : "Add"}
              </button>
              <button onClick={() => { setAdding(false); setForm(empty); }} className="btn-ghost text-sm">Cancel</button>
            </div>
          ) : (
            <div className="px-4 py-3 border-t border-[var(--border)]">
              <button onClick={() => setAdding(true)} data-testid="cf-add" className="btn-ghost text-sm">
                <Plus size={14} /> Add field
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
