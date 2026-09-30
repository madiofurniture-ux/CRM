const TONES = {
  neutral: "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]",
  success: "bg-[var(--color-success)]/10 text-[var(--color-success)]",
  warning: "bg-[var(--color-warning)]/10 text-[var(--color-warning)]",
  danger: "bg-[var(--color-danger)]/10 text-[var(--color-danger)]",
  primary: "bg-[var(--color-primary-soft)] text-[var(--color-primary)]",
};

/** Small pill for a status/stage/count — `tone` picks the token-driven
 * color pairing so contrast stays correct under either theme. */
export default function StatusBadge({ children, tone = "neutral" }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${TONES[tone] || TONES.neutral}`}>
      {children}
    </span>
  );
}
