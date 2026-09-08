import { createContext, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

const BusinessProfileContext = createContext(null);

const FALLBACK_DIVISIONS = [
  { id: "furniture", name: "Madio Furniture", slug: "Furniture" },
  { id: "map", name: "MAP Premium Acrylic Paints", slug: "MAP" },
  { id: "dw", name: "Madio Doors & Windows", slug: "D&W" },
];

/** Tenant-configured division roster (name/slug/brand color/etc.), fetched
 * once from /settings/business-profile and shared app-wide so a sister
 * business entity's own divisions replace Madio's hardcoded three. */
export function BusinessProfileProvider({ children }) {
  const [divisions, setDivisions] = useState(FALLBACK_DIVISIONS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/settings/business-profile")
      .then(({ data }) => {
        if (data?.divisions?.length) setDivisions(data.divisions);
      })
      .catch(() => {}) // keep the fallback roster
      .finally(() => setLoading(false));
  }, []);

  return (
    <BusinessProfileContext.Provider value={{ divisions, loading }}>
      {children}
    </BusinessProfileContext.Provider>
  );
}

export function useBusinessProfile() {
  return useContext(BusinessProfileContext) || { divisions: FALLBACK_DIVISIONS, loading: false };
}
