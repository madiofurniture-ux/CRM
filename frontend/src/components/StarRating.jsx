import { Star } from "lucide-react";

/**
 * 1-5 star confidence picker.
 *
 * Stored as the existing `confidence_level` percentage (0-100), NOT as a new
 * field — so nothing on the backend, in CSV export or in the follow-up
 * dashboard had to change. A star maps to 20/40/60/80/100; a legacy row
 * holding an arbitrary percentage (the old input was a free 0-100 number box)
 * renders at its nearest star rather than being migrated. Mirrors
 * lifecycle.confidence_stars / snap_confidence server-side, which is also
 * what re-snaps whatever a client sends.
 */
export const starsFromPct = (pct) => {
  if (pct === null || pct === undefined || pct === "") return 0;
  const n = Number(pct);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return Math.max(1, Math.min(5, Math.round(n / 20)));
};

export const pctFromStars = (stars) => (stars > 0 ? stars * 20 : null);

const LABELS = ["Not rated", "Very low", "Low", "Medium", "High", "Very high"];

export default function StarRating({ value, onChange, label = "Confidence", testId, readOnly = false }) {
  const stars = starsFromPct(value);

  return (
    <div>
      {label && (
        <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">
          {label}
        </label>
      )}
      <div className="flex items-center gap-1" data-testid={testId} role={readOnly ? undefined : "radiogroup"} aria-label={label}>
        {[1, 2, 3, 4, 5].map((s) => (
          <button
            key={s}
            type="button"
            disabled={readOnly}
            // Clicking the current rating clears it — otherwise a value set
            // by mistake could never be returned to "not rated".
            onClick={() => onChange?.(pctFromStars(s === stars ? 0 : s))}
            className={`p-0.5 rounded ${readOnly ? "cursor-default" : "hover:scale-110 transition"}`}
            title={LABELS[s]}
            aria-label={`${s} of 5 — ${LABELS[s]}`}
            aria-pressed={!readOnly && s <= stars}
            data-testid={testId ? `${testId}-${s}` : undefined}
          >
            <Star
              size={18}
              className={s <= stars ? "text-[var(--warn)]" : "text-[var(--border)]"}
              fill={s <= stars ? "currentColor" : "none"}
              strokeWidth={1.6}
            />
          </button>
        ))}
        <span className="ml-1.5 text-[11px] text-[var(--ink-3)]">{LABELS[stars]}</span>
      </div>
    </div>
  );
}
