import { useEffect, useState } from "react";
import api from "@/lib/api";
import { X, Search } from "lucide-react";
import useFocusTrap from "@/hooks/useFocusTrap";

/** Self-contained search-and-link overlay for one stakeholder slot on a
 * project. Given a role hint, searches architects/customers/record_contacts
 * via /stakeholders/search and hands the picked person back via onLink. */
export default function StakeholderLinkModal({ role, onLink, onClose }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const trapRef = useFocusTrap(true);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    const t = setTimeout(() => {
      api.get("/stakeholders/search", { params: { query, role } })
        .then(({ data }) => setResults(data))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [query, role]);

  useEffect(() => {
    const onKeyDown = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4" onClick={onClose}>
      <div ref={trapRef} role="dialog" aria-modal="true" aria-labelledby="stakeholder-link-title" className="bg-white rounded-xl border border-[var(--border)] w-full max-w-md shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 id="stakeholder-link-title" className="font-heading font-semibold text-sm">Link stakeholder</h3>
          <button onClick={onClose} aria-label="Close link stakeholder dialog" className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
        </div>
        <div className="p-4 space-y-3">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]" />
            <input
              autoFocus
              type="text"
              aria-label="Search stakeholders by name or phone"
              placeholder="Search by name or phone…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-2 text-sm rounded-lg border border-[var(--border)] outline-none focus:border-[var(--brand)]"
            />
          </div>
          <div className="max-h-64 overflow-y-auto divide-y divide-[var(--border-light)]">
            {loading && <div className="text-xs text-[var(--ink-3)] py-3 text-center">Searching…</div>}
            {!loading && query.trim().length >= 2 && results.length === 0 && (
              <div className="text-xs text-[var(--ink-3)] py-3 text-center">No matches</div>
            )}
            {results.map((r) => (
              <button
                key={`${r.source}-${r.id}`}
                onClick={() => onLink(r)}
                className="w-full text-left px-2 py-2.5 hover:bg-[var(--surface-2)] rounded-lg transition"
              >
                <div className="text-sm font-medium text-[var(--ink)]">{r.name}</div>
                <div className="text-xs text-[var(--ink-3)]">
                  {r.phone || "No phone"} · {r.firm || r.email || r.role || r.source}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
