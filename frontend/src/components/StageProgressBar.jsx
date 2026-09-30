// 11-stage operational flow progress bar. `stages` is the `pipeline` array
// from GET /journey/{phone} ({key, label, done, at}) — computed server-side
// so the browser never re-derives cross-collection stage logic.
export default function StageProgressBar({ stages }) {
  if (!stages || !stages.length) return null;
  return (
    <div className="flex items-center overflow-x-auto py-2" data-testid="stage-progress-bar">
      {stages.map((s, i) => (
        <div key={s.key} className="flex items-center shrink-0">
          <div className="flex flex-col items-center gap-1" title={s.at ? `${s.label} · ${s.at}` : s.label}>
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                s.done ? "bg-[var(--moss)]" : "bg-[var(--surface-2)] border border-[var(--border)]"
              }`}
            />
            <span className={`text-[10px] whitespace-nowrap ${s.done ? "text-[var(--ink)]" : "text-[var(--ink-3)]"}`}>
              {s.label}
            </span>
          </div>
          {i < stages.length - 1 && (
            <div className={`h-px w-6 mx-1 mb-4 ${s.done ? "bg-[var(--moss)]" : "bg-[var(--border)]"}`} />
          )}
        </div>
      ))}
    </div>
  );
}
