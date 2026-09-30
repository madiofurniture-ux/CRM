import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";

/** Active custom field definitions for one entity ("lead" / "customer"),
 * ordered for display. */
export default function useCustomFields(entity) {
  const [defs, setDefs] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/custom-fields?entity=${encodeURIComponent(entity)}`);
      setDefs(data);
    } finally {
      setLoading(false);
    }
  }, [entity]);

  useEffect(() => { load(); }, [load]);

  return { defs, loading, reload: load };
}
