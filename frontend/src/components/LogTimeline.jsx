import { useState } from "react";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { toast } from "sonner";

const KINDS = ["Note", "Phone", "WhatsApp", "Email", "Meeting", "Site Visit",
  "Price Discussion", "Design Discussion", "Negotiation", "Payment", "Order Confirmation", "Other"];

/**
 * Dated, multi-entry follow-up/remarks ledger. Appends to the `log` array
 * on a Lead/Quote/Project via POST /log/{entity}/{itemId} — the plain
 * `remarks` string on the record is untouched and keeps rendering elsewhere.
 * For entity="quote", also offers a Type and a Next Follow-up Date, which
 * the backend denormalizes onto the quote for the follow-up dashboard.
 *
 * Usage: <LogTimeline entity="quote" itemId={q.id} entries={q.log}
 *          onAppended={(log, record) => ...} />
 */
export default function LogTimeline({ entity, itemId, entries = [], onAppended }) {
  const [text, setText] = useState("");
  const [confidence, setConfidence] = useState("");
  const [kind, setKind] = useState("Note");
  const [nextFollowUp, setNextFollowUp] = useState("");
  const [busy, setBusy] = useState(false);
  const scheduling = entity === "quote";

  const add = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/log/${entity}/${itemId}`, {
        text: text.trim(), kind,
        confidence_level: confidence === "" ? null : parseFloat(confidence),
        ...(scheduling ? { next_follow_up: nextFollowUp } : {}),
      });
      setText(""); setConfidence(""); setNextFollowUp("");
      onAppended?.(data.log || [], data);
    } catch { toast.error("Couldn't save follow-up entry"); }
    finally { setBusy(false); }
  };

  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 space-y-3" data-testid="log-timeline">
      <div className="flex gap-2 items-start flex-wrap">
        <textarea
          value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Add a dated follow-up / remark…" rows={2}
          className="flex-1 min-w-[200px] px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]"
        />
        <div className="flex flex-col gap-2 shrink-0 w-36">
          <select value={kind} onChange={(e) => setKind(e.target.value)} className="px-2 py-1.5 rounded-lg border border-[var(--border)] bg-white text-xs">
            {KINDS.map((k) => <option key={k}>{k}</option>)}
          </select>
          <input
            type="number" min="0" max="100" value={confidence}
            onChange={(e) => setConfidence(e.target.value)}
            placeholder="Confidence %"
            className="px-2 py-1.5 rounded-lg border border-[var(--border)] bg-white text-xs outline-none focus:border-[var(--brand)]"
          />
          {scheduling && (
            <input
              type="date" value={nextFollowUp} onChange={(e) => setNextFollowUp(e.target.value)}
              title="Next follow-up date"
              className="px-2 py-1.5 rounded-lg border border-[var(--border)] bg-white text-xs outline-none focus:border-[var(--brand)]"
            />
          )}
          <button onClick={add} disabled={busy || !text.trim()} className="btn-primary text-xs py-1.5 disabled:opacity-50">
            {busy ? "Saving…" : "Add entry"}
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {entries.length === 0 && <div className="text-sm text-[var(--ink-3)] py-2">No follow-up entries yet.</div>}
        {[...entries].reverse().map((e, i) => (
          <div key={i} className="border-t border-[var(--border-light)] pt-2 first:border-0 first:pt-0">
            <div className="flex items-center gap-2 text-[11px] text-[var(--ink-3)]">
              <span className="font-semibold">{e.by || "—"}</span>
              <span>{fmtDate(e.at)}</span>
              {e.kind && <span className="px-1.5 py-0.5 rounded bg-[var(--surface-2)]">{e.kind}</span>}
              {e.confidence_level != null && e.confidence_level !== "" && (
                <span className="px-1.5 py-0.5 rounded bg-[var(--brand-soft)] text-[var(--brand)] font-semibold">{e.confidence_level}%</span>
              )}
            </div>
            <div className="text-sm text-[var(--ink)]">{e.text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
