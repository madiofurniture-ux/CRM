/** Renders/edits ONE custom field value given its definition. No form
 * library — native inputs per type, same as the rest of this codebase. */
export default function CustomFieldInput({ def, value, onChange }) {
  const base = "w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]";

  if (def.type === "boolean") {
    return (
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} />
        {def.label}
      </label>
    );
  }

  return (
    <div>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{def.label}</label>
      {def.type === "select" ? (
        <select value={value || ""} onChange={(e) => onChange(e.target.value)} className={base}>
          <option value="">— Select —</option>
          {(def.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input
          type={def.type === "number" ? "number" : def.type === "date" ? "date" : "text"}
          value={value ?? ""}
          onChange={(e) => onChange(def.type === "number" ? (e.target.value === "" ? "" : parseFloat(e.target.value) || 0) : e.target.value)}
          className={base}
        />
      )}
    </div>
  );
}
