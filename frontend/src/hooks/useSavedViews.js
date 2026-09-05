import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";

/** Saved filter presets for one list page. `filters` is whatever plain
 * object the page wants replayed later (e.g. { search, fStage }). */
export default function useSavedViews(entity) {
  const [views, setViews] = useState([]);

  const load = useCallback(async () => {
    const { data } = await api.get(`/saved-views?entity=${encodeURIComponent(entity)}`);
    setViews(data);
  }, [entity]);

  useEffect(() => { load(); }, [load]);

  const save = async (name, filters, shared = false) => {
    const { data } = await api.post("/saved-views", { entity, name, filters, shared });
    setViews((p) => [data, ...p]);
    return data;
  };

  const remove = async (id) => {
    await api.delete(`/saved-views/${id}`);
    setViews((p) => p.filter((v) => v.id !== id));
  };

  return { views, save, remove };
}
