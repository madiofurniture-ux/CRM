/** Token-driven primary action button — replaces the hardcoded
 * `bg-[#EC3013]`/`bg-brand` one-offs scattered across pages so the accent
 * color follows the active theme automatically. */
export default function PrimaryButton({ children, className = "", ...props }) {
  return (
    <button
      type="button"
      className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-[var(--radius-sm)] text-sm font-semibold text-white bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
