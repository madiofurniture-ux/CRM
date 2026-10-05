import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, X } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { reloadPicklists } from "@/hooks/usePicklists";

/** Master Data → Lists: the values behind every dropdown (lead sources,
 * project types, D&W frames and glass, stock categories, units…). Forms
 * only accept values on these lists. */
export default function PicklistsManager() {
  const [lists, setLists] = useState(null);
  const [open, setOpen] = useState("");
  useEffect(() => { reloadPicklists().then(setLists); }, []);
  if (!lists) return <div className="text-sm text-[var(--ink-3)]">Loading lists…</div>;
  return (
    <section className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 space-y-2" data-testid="picklists-manager">
      <div>
        <h3 className="font-heading font-semibold">Lists</h3>
        <p className="text-xs text-[var(--ink-3)]">The choices in every dropdown. Forms only accept values on these lists; records that already hold an old value keep it.</p>
      </div>
      <div className="divide-y divide-[var(--border-light)]">
        {Object.entries(lists).map(([key, l]) => (
          <div key={key}>
            <button type="button" onClick={() => setOpen(open === key ? "" : key)} aria-expanded={open === key}
                    className="w-full flex items-center gap-2 py-2.5 text-left" data-testid={`picklist-${key}`}>
              {open === key ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
              <span className="font-medium text-sm flex-1">{l.label}</span>
              <span className="text-xs text-[var(--ink-3)]">{l.values.length ? `${l.values.length} values` : "any value allowed"}</span>
            </button>
            {open === key && <ListEditor listKey={key} list={l} onSaved={(saved) => setLists((p) => ({ ...p, [key]: saved }))} />}
          </div>
        ))}
      </div>
    </section>
  );
}

function ListEditor({ listKey, list, onSaved }) {
  const [values, setValues] = useState(list.values);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(values) !== JSON.stringify(list.values);
  const add = () => {
    const v = draft.trim();
    if (!v) return;
    if (values.some((x) => x.toLowerCase() === v.toLowerCase())) { toast.error(`“${v}” is already on the list`); return; }
    setValues([...values, v]); setDraft("");
  };
  const move = (i, d) => {
    const next = [...values];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    setValues(next);
  };
  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put(`/picklists/${listKey}`, { values });
      onSaved(data); setValues(data.values);
      await reloadPicklists();
      toast.success(`${list.label} saved`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't save the list"); }
    finally { setSaving(false); }
  };
  return (
    <div className="pb-3 pl-6 space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {values.map((v, i) => (
          <span key={v} className="inline-flex items-center gap-1 pl-2.5 pr-1 py-1 rounded-full border border-[var(--border)] text-sm bg-[var(--surface-2)]">
            {v}
            <button type="button" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Move ${v} up`} className="opacity-60 hover:opacity-100 disabled:opacity-20"><ArrowUp size={12} /></button>
            <button type="button" disabled={i === values.length - 1} onClick={() => move(i, 1)} aria-label={`Move ${v} down`} className="opacity-60 hover:opacity-100 disabled:opacity-20"><ArrowDown size={12} /></button>
            <button type="button" onClick={() => setValues(values.filter((x) => x !== v))} aria-label={`Remove ${v}`} className="text-[var(--danger)] opacity-70 hover:opacity-100"><X size={13} /></button>
          </span>
        ))}
        {!values.length && <span className="text-xs text-[var(--ink-3)]">Empty: any value is accepted.</span>}
      </div>
      <div className="flex gap-2">
        <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
               placeholder={`Add to ${list.label.toLowerCase()}`} className="flex-1 max-w-xs px-2.5 py-1.5 rounded-md border border-[var(--border)] text-sm"
               data-testid={`picklist-${listKey}-new`} />
        <button type="button" onClick={add} className="btn-ghost text-sm">Add</button>
        <button type="button" onClick={save} disabled={!dirty || saving} className="btn-primary text-sm disabled:opacity-50" data-testid={`picklist-${listKey}-save`}>
          {saving ? "Saving…" : "Save list"}
        </button>
        {dirty && <button type="button" onClick={() => setValues(list.values)} className="text-xs text-[var(--ink-3)]">Undo changes</button>}
      </div>
    </div>
  );
}
