import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";

/**
 * The tenant's configured workflow for one entity ("lead", "quote",
 * "project", …) from GET /workflows/{entity}: its stages (with probability,
 * guidance, required fields and allowed next stages), automation rules and
 * the field catalog.
 *
 * `fallback` is the page's own stage list, used only until the workflow has
 * loaded (or if loading fails) so a page never renders without stages.
 */
export default function useWorkflow(entity, fallback = []) {
  const [wf, setWf] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/workflows/${entity}`);
      setWf(data);
    } catch {
      setWf(null);
    } finally {
      setLoading(false);
    }
  }, [entity]);

  useEffect(() => { load(); }, [load]);

  const fallbackKey = fallback.join("|");
  return useMemo(() => {
    const stages = wf?.stages?.length
      ? wf.stages
      : fallbackKey.split("|").filter(Boolean).map((label) => ({
        key: label.toLowerCase().replace(/[^a-z0-9]+/g, "_"), label,
        terminal: false, won: false, probability: null, guidance: "",
        required_fields: [], next: [],
      }));
    const byLower = new Map(stages.map((s) => [s.label.toLowerCase(), s]));
    const stageOf = (value) => {
      const v = String(value || "").trim().toLowerCase();
      return byLower.get(v) || stages.find((s) => s.key === v.replace(/[^a-z0-9]+/g, "_")) || null;
    };
    return {
      workflow: wf,
      loading,
      reload: load,
      stages,
      labels: stages.map((s) => s.label),
      enforced: !!wf?.enforced,
      fields: wf?.fields || [],
      stageOf,
      isKnownStage: (value) => !!stageOf(value),
      // Stage default probability; null when the stage isn't a forecast stage.
      probabilityOf: (value) => {
        const p = stageOf(value)?.probability;
        return Number.isFinite(p) ? p : null;
      },
    };
  }, [wf, loading, load, fallbackKey]);
}

/** Pull the most useful message out of a failed stage change: the workflow
 * gates answer 400 with {message, code, missing_fields|allowed}. */
export function stageErrorMessage(err) {
  const d = err?.response?.data?.detail;
  if (d && typeof d === "object" && d.message) return d.message;
  if (typeof d === "string") return d;
  return "Couldn't change the stage.";
}
