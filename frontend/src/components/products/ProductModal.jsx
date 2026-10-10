import { X } from "lucide-react";

/** The dialog the Virtual Catalogue's screens open in: a title bar, a
 * scrolling body, full width on a phone. */
export default function ProductModal({ title, onClose, children, testid, wide }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-start sm:items-center justify-center p-2 sm:p-3" role="dialog" aria-modal="true" aria-label={title}>
      <div className={`bg-[var(--color-surface)] rounded-xl shadow-2xl w-full ${wide ? "max-w-6xl" : "max-w-xl"} max-h-[94vh] flex flex-col`} data-testid={testid}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)] shrink-0">
          <h2 className="font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
