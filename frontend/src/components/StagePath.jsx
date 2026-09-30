import { useEffect, useMemo, useState } from "react";
import { Check, ChevronDown, ChevronUp, Loader2 } from "lucide-react";

/**
 * Salesforce-style Path for one record: the record's stage as a row of
 * chevrons, driven by the tenant's workflow (hooks/useWorkflow.js).
 *
 *  - open stages are chevrons; terminal stages (Won/Lost/Cancelled…) share
 *    one final "Closed" chevron, like Lightning's Path;
 *  - clicking a chevron selects it; "Mark as current stage" moves the record,
 *    "Mark stage as complete" advances it to the next allowed stage;
 *  - the panel below shows the selected stage's guidance and the fields it
 *    requires (filled / missing) plus time in the current stage.
 *
 * The server is the authority on gates: `onChange(label)` should PUT the new
 * stage and throw on failure — the caller turns the error into a toast
 * (see stageErrorMessage), and the Path stays on the old stage.
 */
export default function StagePath({
  wf, value, record = {}, onChange, canEdit = true, compact = false,
}) {
  const stages = wf?.stages || [];
  const current = wf?.stageOf ? wf.stageOf(value) : null;
  const open = stages.filter((s) => !s.terminal);
  const closed = stages.filter((s) => s.terminal);
  const hasClosed = closed.length > 0 && open.length > 0;
  const steps = hasClosed ? [...open, { key: "__closed__", label: "Closed", closed: true }] : stages;

  const currentStepKey = current
    ? (hasClosed && current.terminal ? "__closed__" : current.key)
    : null;
  const currentIdx = steps.findIndex((s) => s.key === currentStepKey);

  const [selected, setSelected] = useState(currentStepKey);
  const [closeChoice, setCloseChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showCoaching, setShowCoaching] = useState(!compact);

  useEffect(() => { setSelected(currentStepKey); setCloseChoice(""); }, [currentStepKey]);

  const fieldLabel = useMemo(() => {
    const m = new Map((wf?.fields || []).map((f) => [f.key, f.label]));
    return (k) => m.get(k) || k.replace(/_/g, " ");
  }, [wf?.fields]);

  if (!stages.length) return null;

  const selectedStep = steps.find((s) => s.key === selected) || null;
  const selectedStage = selectedStep?.closed
    ? (closeChoice ? stages.find((s) => s.key === closeChoice) : (current?.terminal ? current : null))
    : selectedStep;

  const move = async (label) => {
    if (!onChange || busy) return;
    setBusy(true);
    try { await onChange(label); } catch { /* caller reports; Path stays put */ } finally { setBusy(false); }
  };

  // Next stage for "Mark stage as complete": the first allowed next stage if
  // the workflow restricts transitions, else the following open stage, else
  // the Closed chooser.
  const nextStage = (() => {
    if (!current || current.terminal) return null;
    if (current.next?.length) {
      const openNext = open.find((s) => current.next.includes(s.key));
      return openNext || null;
    }
    const i = open.findIndex((s) => s.key === current.key);
    return i >= 0 && i < open.length - 1 ? open[i + 1] : null;
  })();

  const stepState = (s, i) => {
    if (s.key === currentStepKey) {
      if (s.closed && current) return current.won ? "won" : "lost";
      return "current";
    }
    if (currentIdx >= 0 && i < currentIdx) return "complete";
    return "incomplete";
  };

  const enteredAt = record.stage_entered_at;
  const daysInStage = enteredAt
    ? Math.max(0, Math.floor((Date.now() - new Date(enteredAt).getTime()) / 86400000))
    : null;

  let action = null;
  if (canEdit && onChange) {
    if (selectedStep?.closed) {
      const choice = closeChoice || "";
      action = (
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="path-close">Closed stage</label>
          <select
            id="path-close"
            value={choice}
            onChange={(e) => setCloseChoice(e.target.value)}
            className="px-2.5 py-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border-strong,var(--color-border))] bg-[var(--color-surface)] text-sm"
          >
            <option value="">Choose closed stage…</option>
            {closed.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
          <button
            type="button" className="btn-primary" disabled={!choice || busy}
            onClick={() => move(stages.find((s) => s.key === choice).label)}
          >
            {busy && <Loader2 size={14} className="animate-spin" />} Save closed stage
          </button>
        </div>
      );
    } else if (selectedStep && selectedStep.key !== currentStepKey) {
      action = (
        <button type="button" className="btn-primary" disabled={busy} onClick={() => move(selectedStep.label)}>
          {busy && <Loader2 size={14} className="animate-spin" />} Mark as current stage
        </button>
      );
    } else if (current && !current.terminal) {
      action = nextStage ? (
        <button type="button" className="btn-primary" disabled={busy} onClick={() => move(nextStage.label)}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Mark stage as complete
        </button>
      ) : hasClosed ? (
        <button type="button" className="btn-primary" onClick={() => setSelected("__closed__")}>
          Close this record
        </button>
      ) : null;
    }
  }

  const required = selectedStage?.required_fields || [];

  return (
    <section className="stage-path" aria-label="Stage path" data-testid="stage-path">
      <div className="flex items-center gap-3">
        <ol className="stage-path__track">
          {steps.map((s, i) => {
            const state = stepState(s, i);
            const label = s.closed && current?.terminal ? current.label : s.label;
            return (
              <li key={s.key} className="stage-path__item">
                <button
                  type="button"
                  className={`stage-path__step is-${state}${selected === s.key ? " is-selected" : ""}`}
                  aria-current={s.key === currentStepKey ? "step" : undefined}
                  title={s.probability != null ? `${label} · ${s.probability}% probability` : label}
                  onClick={() => { setSelected(s.key); setCloseChoice(""); }}
                >
                  {state === "complete" && <Check size={14} aria-hidden className="stage-path__check" />}
                  <span className={state === "complete" ? "stage-path__label--complete" : ""}>{label}</span>
                  {state === "complete" && <span className="sr-only"> (complete)</span>}
                </button>
              </li>
            );
          })}
        </ol>
        {!compact && (
          <button
            type="button"
            className="shrink-0 p-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)]"
            aria-expanded={showCoaching}
            aria-label={showCoaching ? "Hide stage guidance" : "Show stage guidance"}
            onClick={() => setShowCoaching((v) => !v)}
          >
            {showCoaching ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        )}
      </div>

      {value && !current && (
        <p className="mt-2 text-xs text-[var(--color-warning)]">
          This record is at "{value}", which isn't a stage in your workflow. Pick a stage to fix it.
        </p>
      )}

      {action && <div className="mt-3 flex justify-end">{action}</div>}

      {showCoaching && selectedStage && (
        <div className="mt-3 grid gap-4 sm:grid-cols-2 text-sm rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] p-3">
          <div>
            <h4 className="font-semibold text-[var(--color-text)] mb-1">Key fields</h4>
            {required.length ? (
              <ul className="space-y-1">
                {required.map((f) => {
                  const v = record[f];
                  const filled = !(v == null || v === "" || v === 0);
                  return (
                    <li key={f} className="flex items-baseline justify-between gap-3">
                      <span className="text-[var(--color-text-muted)]">{fieldLabel(f)}</span>
                      <span className={`text-right ${filled ? "text-[var(--color-text)]" : "text-[var(--color-danger)] font-medium"}`}>
                        {filled ? String(v) : "Required"}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-[var(--color-text-muted)]">No fields required for {selectedStage.label}.</p>
            )}
            {selectedStage.probability != null && (
              <p className="mt-2 text-[var(--color-text-muted)]">Probability {selectedStage.probability}%</p>
            )}
            {current && selectedStage.key === current.key && daysInStage != null && (
              <p className="mt-1 text-[var(--color-text-muted)]">
                In this stage for {daysInStage === 0 ? "less than a day" : `${daysInStage} day${daysInStage === 1 ? "" : "s"}`}
              </p>
            )}
          </div>
          <div>
            <h4 className="font-semibold text-[var(--color-text)] mb-1">Guidance for success</h4>
            <p className="text-[var(--color-text-muted)] whitespace-pre-line">
              {selectedStage.guidance || "No guidance yet. An admin can add it under Workflows."}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
