import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ImagePlus, Plus, Trash2, X } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { shrinkImage } from "@/lib/image";
import { useAuth } from "@/context/AuthContext";

/** Master Data → Quotations: the markup that turns a manufacturer's rate
 * into the customer rate (only people who can see landing prices see it),
 * the aluminium rate new Doors & Windows quotations print, and the D&W
 * typology library (name, pattern, diagram) every line picks from. */
export default function QuoteSettingsManager() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [st, setSt] = useState(null);
  const [saving, setSaving] = useState("");
  useEffect(() => {
    api.get("/quote-settings", { skipCache: true }).then(({ data }) => setSt(data)).catch(() => setSt({ typologies: [] }));
  }, []);
  if (!st) return <div className="text-sm text-[var(--ink-3)]">Loading quotation settings…</div>;

  const save = async (part, label) => {
    setSaving(label);
    try {
      const { data } = await api.put("/quote-settings", part);
      setSt(data);
      toast.success(`${label} saved`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't save"); }
    finally { setSaving(""); }
  };
  const field = "px-2.5 py-1.5 rounded-md border border-[var(--border)] text-sm bg-white";

  return (
    <section className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 space-y-5" data-testid="quote-settings">
      <div>
        <h3 className="font-heading font-semibold">Quotations</h3>
        <p className="text-xs text-[var(--ink-3)]">How quotations are priced and what Doors &amp; Windows lines pick from.{!isAdmin && " Only an admin can change these."}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {st.markup && (
          <div className="space-y-2" data-testid="quote-settings-markup">
            <div className="text-sm font-medium">Markup on the manufacturer's rate</div>
            <p className="text-xs text-[var(--ink-3)]">Customer rate = MFG rate × markup, on lines that carry an MFG rate. 0 switches it off. Only people who can see landing prices see this.</p>
            <div className="flex flex-wrap gap-3">
              {Object.entries(st.markup).map(([div, v]) => (
                <label key={div} className="text-xs text-[var(--ink-3)]">
                  {div}
                  <input type="number" step="0.05" min="0" defaultValue={v} disabled={!isAdmin} id={`markup-${div}`}
                         className={`${field} w-20 block text-right`} data-testid={`quote-markup-${div}`} />
                </label>
              ))}
              {isAdmin && (
                <button type="button" className="btn-ghost self-end text-sm" disabled={saving === "Markup"}
                        onClick={() => save({ markup: Object.fromEntries(Object.keys(st.markup).map((d) => [d, document.getElementById(`markup-${d}`)?.value || 0])) }, "Markup")}>
                  Save markup
                </button>
              )}
            </div>
          </div>
        )}
        <div className="space-y-2">
          <div className="text-sm font-medium">Aluminium 6063 rate (₹ per kg)</div>
          <p className="text-xs text-[var(--ink-3)]">New Doors &amp; Windows quotations start with it and print it in their terms; each quotation can change its own.</p>
          <div className="flex gap-2">
            <input defaultValue={st.aluminium_rate} disabled={!isAdmin} id="alu-rate" placeholder="e.g. 480"
                   className={`${field} w-28 text-right`} data-testid="quote-aluminium-rate" />
            {isAdmin && <button type="button" className="btn-ghost text-sm" disabled={saving === "Aluminium rate"}
                                onClick={() => save({ aluminium_rate: document.getElementById("alu-rate")?.value || "" }, "Aluminium rate")}>Save</button>}
          </div>
        </div>
      </div>

      <TypologyLibrary rows={st.typologies || []} isAdmin={isAdmin} busy={saving === "Typology library"}
                       onSave={(typologies) => save({ typologies }, "Typology library")} />
    </section>
  );
}

function TypologyLibrary({ rows, isAdmin, busy, onSave }) {
  const [list, setList] = useState(rows);
  useEffect(() => { setList(rows); }, [rows]);
  const dirty = JSON.stringify(list) !== JSON.stringify(rows);
  const set = (i, patch) => setList((l) => l.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  const pick = async (i, file) => {
    try { set(i, { image: await shrinkImage(file, 360, 0.85) }); }
    catch (e) { toast.error(e.message || "Couldn't use that picture"); }
  };
  const field = "w-full px-2 py-1 rounded border border-[var(--border)] text-sm bg-white";
  return (
    <div className="space-y-2" data-testid="typology-library">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium">Doors &amp; Windows typologies</div>
          <p className="text-xs text-[var(--ink-3)]">A line's typology fills its pattern and prints its diagram on the quotation.</p>
        </div>
        {isAdmin && (
          <div className="flex gap-2">
            <button type="button" className="btn-ghost text-sm" onClick={() => setList((l) => [...l, { code: `T-${String(l.length + 1).padStart(2, "0")}`, name: "", pattern: "", image: "" }])}>
              <Plus size={14} /> Add
            </button>
            <button type="button" className="btn-primary text-sm disabled:opacity-50" disabled={!dirty || busy}
                    onClick={() => onSave(list)} data-testid="typology-save">{busy ? "Saving…" : "Save library"}</button>
          </div>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
            <tr><th className="text-left px-2 py-1 w-20">Code</th><th className="text-left px-2 py-1">Name</th>
              <th className="text-left px-2 py-1">Pattern</th><th className="text-left px-2 py-1 w-36">Diagram</th><th className="w-8" /></tr>
          </thead>
          <tbody>
            {list.map((t, i) => (
              <tr key={i} className="border-t border-[var(--border-light)]" data-testid={`typology-${t.code}`}>
                <td className="px-2 py-1.5"><input className={field} value={t.code} disabled={!isAdmin} onChange={(e) => set(i, { code: e.target.value })} /></td>
                <td className="px-2 py-1.5"><input className={field} value={t.name} disabled={!isAdmin} onChange={(e) => set(i, { name: e.target.value })} /></td>
                <td className="px-2 py-1.5"><input className={field} value={t.pattern} disabled={!isAdmin} onChange={(e) => set(i, { pattern: e.target.value })} /></td>
                <td className="px-2 py-1.5">
                  <div className="flex items-center gap-1.5">
                    {t.image ? <img src={t.image} alt="" className="h-10 w-16 object-contain bg-white rounded border border-[var(--border)]" />
                      : <span className="text-xs text-[var(--ink-3)]">none</span>}
                    {isAdmin && (
                      <>
                        <label className="cursor-pointer text-[var(--brand)]" title="Upload a diagram"><ImagePlus size={14} />
                          <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                                 onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) pick(i, f); }} />
                        </label>
                        {t.image && <button type="button" className="text-[var(--danger)]" onClick={() => set(i, { image: "" })} title="Remove diagram"><X size={13} /></button>}
                      </>
                    )}
                  </div>
                </td>
                <td className="px-1">{isAdmin && <button type="button" className="p-1 text-[var(--danger)]" onClick={() => setList((l) => l.filter((_, j) => j !== i))} aria-label={`Remove ${t.name || t.code}`}><Trash2 size={13} /></button>}</td>
              </tr>
            ))}
            {!list.length && <tr><td colSpan={5} className="px-2 py-3 text-xs text-[var(--ink-3)]">No typologies yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
