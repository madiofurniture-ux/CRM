/** A graceful "nothing here yet" block for list pages — icon + message,
 * replacing a bare line of text. */
export default function EmptyState({ icon: Icon, title, hint }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-14 text-center">
      {Icon && <Icon size={28} strokeWidth={1.5} className="text-[var(--ink-3)]" />}
      <div className="text-sm font-medium text-[var(--ink-2)]">{title}</div>
      {hint && <div className="text-xs text-[var(--ink-3)] max-w-xs">{hint}</div>}
    </div>
  );
}
