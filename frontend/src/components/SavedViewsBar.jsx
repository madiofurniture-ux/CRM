import { useState } from "react";
import { toast } from "sonner";
import { X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import useSavedViews from "@/hooks/useSavedViews";

/** A row of saved-view chips for one list page, plus "Save current view".
 * `filters` is the page's own current filter state (plain object);
 * `onApply(filters)` is called when a chip is clicked. */
export default function SavedViewsBar({ entity, filters, onApply }) {
  const { user } = useAuth();
  const { views, save, remove } = useSavedViews(entity);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");

  const doSave = async () => {
    if (!name.trim()) return toast.error("Name is required");
    await save(name.trim(), filters, false);
    setNaming(false);
    setName("");
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="saved-views-bar">
      {views.map((v) => (
        <span
          key={v.id}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border bg-[var(--surface)] border-[var(--border)] text-[var(--ink-2)] hover:bg-[var(--surface-2)]"
        >
          <button onClick={() => onApply(v.filters)} data-testid={`saved-view-${v.id}`}>{v.name}</button>
          {(v.created_by_id === user?.id || user?.role === "admin") && (
            <button onClick={() => remove(v.id)} title="Delete view" className="opacity-60 hover:opacity-100">
              <X size={11} />
            </button>
          )}
        </span>
      ))}
      {naming ? (
        <span className="inline-flex items-center gap-1">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && doSave()}
            placeholder="View name"
            className="px-2 py-1 rounded-md border border-[var(--border)] text-xs w-32"
          />
          <button onClick={doSave} className="text-xs font-medium text-[var(--brand)]">Save</button>
          <button onClick={() => { setNaming(false); setName(""); }} className="text-xs text-[var(--ink-3)]">Cancel</button>
        </span>
      ) : (
        <button
          onClick={() => setNaming(true)}
          className="px-3 py-1.5 rounded-lg text-xs font-medium border border-dashed border-[var(--border)] text-[var(--ink-3)] hover:bg-[var(--surface-2)]"
          data-testid="save-current-view"
        >
          + Save view
        </button>
      )}
    </div>
  );
}
