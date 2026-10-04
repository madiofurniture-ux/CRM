import { createContext, useCallback, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

const TenantConfigContext = createContext(null);

const FALLBACK_DIVISIONS = [
  { id: "furniture", name: "Madio Furniture", slug: "Furniture" },
  { id: "map", name: "MAP Premium Acrylic Paints", slug: "MAP" },
  { id: "dw", name: "Madio Doors & Windows", slug: "D&W" },
];

/** Tenant-configured division roster (name/slug/brand color/SKU prefix/stage
 * labels), fetched once from /settings/business-profile and shared app-wide
 * so a sister business entity's own divisions replace Madio's hardcoded
 * three. `reload` lets the Business Settings editor refresh the roster for
 * every other screen right after a save, instead of leaving them stale
 * until the next full page load. */
// Mirrors models.DEFAULT_LEAD_SOURCES — used until the profile loads.
export const FALLBACK_LEAD_SOURCES = ["Walk-in", "Architect", "Referral", "Website", "WhatsApp",
  "Instagram", "Facebook", "Google", "Phone", "Existing Customer", "Social Media", "Site Visit",
  "Cold Call", "Other"];

export function TenantConfigProvider({ children }) {
  const [divisions, setDivisions] = useState(FALLBACK_DIVISIONS);
  const [leadSources, setLeadSources] = useState(FALLBACK_LEAD_SOURCES);
  const [industry, setIndustry] = useState("");
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/settings/business-profile", { skipCache: true });
      if (data?.divisions?.length) setDivisions(data.divisions);
      if (data?.lead_sources?.length) setLeadSources(data.lead_sources);
      setIndustry(data?.industry || "");
      return data;
    } catch {
      return null; // keep the fallback roster
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  return (
    <TenantConfigContext.Provider value={{ divisions, leadSources, industry, loading, reload, setDivisions }}>
      {children}
    </TenantConfigContext.Provider>
  );
}

/** Division roster + custom stage labels for the signed-in tenant. */
export function useTenantConfig() {
  return useContext(TenantConfigContext) || {
    divisions: FALLBACK_DIVISIONS, leadSources: FALLBACK_LEAD_SOURCES, industry: "", loading: false,
    reload: async () => null, setDivisions: () => {},
  };
}
