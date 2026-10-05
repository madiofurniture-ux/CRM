import { useEffect, useState } from "react";
import api from "@/lib/api";

// Master Data picklists (GET /picklists), fetched once per page load and
// shared by every form on screen. reloadPicklists() after an admin edits one.
let cache = null;
const listeners = new Set();
const load = () => {
  if (!cache) {
    cache = api.get("/picklists", { skipCache: true }).then(({ data }) => data || {}).catch(() => {
      cache = null;
      return {};
    });
  }
  return cache;
};
export const reloadPicklists = () => { cache = null; return load().then((d) => { listeners.forEach((fn) => fn(d)); return d; }); };

/** usePicklists() -> { lists, values(key, current) }. `values` returns the
 * list's values plus `current` when an older record holds one that's no
 * longer on the list, so editing it never silently blanks the field. */
export default function usePicklists() {
  const [lists, setLists] = useState({});
  useEffect(() => {
    let live = true;
    const fn = (d) => live && setLists(d);
    listeners.add(fn);
    load().then(fn);
    return () => { live = false; listeners.delete(fn); };
  }, []);
  const values = (key, current) => {
    const v = lists[key]?.values || [];
    return current && !v.some((x) => x.toLowerCase() === String(current).toLowerCase()) ? [...v, current] : v;
  };
  return { lists, values };
}
