import { AlertTriangle } from "lucide-react";
import SecondaryButton from "@/components/SecondaryButton";

/** API-failure block — companion to EmptyState.jsx (which covers "loaded,
 * but nothing there"; this covers "the request itself failed"). */
export default function ErrorState({ title = "Couldn't load this", hint, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-14 text-center">
      <AlertTriangle size={28} strokeWidth={1.5} className="text-[var(--color-danger)]" />
      <div className="text-sm font-medium text-[var(--color-text)]">{title}</div>
      {hint && <div className="text-xs text-[var(--color-text-muted)] max-w-xs">{hint}</div>}
      {onRetry && (
        <SecondaryButton onClick={onRetry} className="mt-2">
          Retry
        </SecondaryButton>
      )}
    </div>
  );
}
