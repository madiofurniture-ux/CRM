import { useCallback, useMemo } from "react";
import usePersistedState from "@/hooks/usePersistedState";

/**
 * Per-column filters for a list page, on top of its own search box and
 * chips. `columns` is [{ key, label, type, get?, options? }]:
 *   type "text"   — contains (case-insensitive)
 *   type "select" — one of the values (options default to the distinct
 *                   values in the rows)
 *   type "date"   — from / to (YYYY-MM-DD, compared as text)
 *   type "number" — min / max
 * `get(row)` reads the value when it isn't simply row[key].
 *
 * State survives a reload (per page) and is a plain object, so a page can
 * put it into its saved views. `apply(rows)` returns the matching rows.
 */
export default function useColumnFilters(page, columns) {
  const [values, setValues] = usePersistedState(`${page}.columns`, {});

  const read = useCallback((col, row) => (col.get ? col.get(row) : row?.[col.key]), []);

  const active = useMemo(() => columns.filter((c) => {
    const v = values?.[c.key];
    if (v == null) return false;
    if (typeof v === "object") return Object.values(v).some((x) => x !== "" && x != null);
    return v !== "";
  }), [columns, values]);

  const apply = useCallback((rows) => {
    if (!active.length) return rows;
    return (rows || []).filter((row) => active.every((col) => {
      const want = values[col.key];
      const have = read(col, row);
      if (col.type === "select") {
        if (want === "(blank)") return have == null || String(have).trim() === "";
        return String(have ?? "") === String(want);
      }
      if (col.type === "date") {
        const d = String(have || "").slice(0, 10);
        if (want.from && (!d || d < want.from)) return false;
        if (want.to && (!d || d > want.to)) return false;
        return true;
      }
      if (col.type === "number") {
        const n = Number(have) || 0;
        if (want.min !== "" && want.min != null && n < Number(want.min)) return false;
        if (want.max !== "" && want.max != null && n > Number(want.max)) return false;
        return true;
      }
      return String(have ?? "").toLowerCase().includes(String(want).toLowerCase().trim());
    }));
  }, [active, values, read]);

  const set = useCallback((key, value) => setValues((prev) => ({ ...(prev || {}), [key]: value })), [setValues]);
  const clear = useCallback((key) => setValues((prev) => {
    if (!key) return {};
    const next = { ...(prev || {}) };
    delete next[key];
    return next;
  }), [setValues]);

  return { columns, values: values || {}, setValues, set, clear, active, apply, read };
}
