import { useEffect, useState } from "react";

/**
 * useState that survives a reload, for list-page filter state: the implicit
 * "I refreshed the page and my status filter was still set" behaviour, which
 * is per-browser and not worth a round trip. (The named, server-stored
 * "Save view" presets were taken off Leads and Customers; column filters
 * plus this cover what people used them for.)
 *
 * Storage is namespaced per page+key. Reads are defensive: a browser with
 * storage disabled, a private window, or a stale value left by an older
 * build must degrade to the initial value rather than throw on render.
 */
export default function usePersistedState(key, initial) {
  const storageKey = `madio.filter.${key}`;

  const [value, setValue] = useState(() => {
    try {
      const raw = window.localStorage.getItem(storageKey);
      return raw === null ? initial : JSON.parse(raw);
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(value));
    } catch {
      // Quota or a blocked storage API — filters simply stop persisting.
      // Never surface this: it is a convenience, not the user's task.
    }
  }, [storageKey, value]);

  return [value, setValue];
}
