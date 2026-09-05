import { useEffect, useState } from "react";
import api from "@/lib/api";
import { inrFull } from "@/lib/format";
import { Wallet } from "lucide-react";

/** Small "petty cash burn" summary for one project — wallet count, live
 * balance, approved spend, and anything still awaiting approval. Renders
 * nothing if the project has no linked cashbook wallets. */
export default function PettyCashBurnWidget({ projectId }) {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    if (!projectId) return;
    api.get(`/projects/${projectId}/petty-cash/summary`).then(({ data }) => setSummary(data)).catch(() => setSummary(null));
  }, [projectId]);

  if (!summary || summary.wallet_count === 0) return null;

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4" data-testid="petty-cash-burn-widget">
      <div className="flex items-center gap-2 mb-3 text-sm font-semibold">
        <Wallet size={15} className="text-[var(--brand)]" /> Petty Cash
        <span className="text-xs font-normal text-[var(--ink-3)]">{summary.wallet_count} wallet{summary.wallet_count === 1 ? "" : "s"}</span>
      </div>
      <div className="grid grid-cols-3 gap-3 text-center">
        <div>
          <div className="text-base font-semibold">{inrFull(summary.balance_total)}</div>
          <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">Balance</div>
        </div>
        <div>
          <div className="text-base font-semibold text-[var(--danger)]">{inrFull(summary.burn_total)}</div>
          <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">Burned</div>
        </div>
        <div>
          <div className="text-base font-semibold text-[var(--warning,#B45309)]">{inrFull(summary.pending_total)}</div>
          <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">Pending</div>
        </div>
      </div>
    </div>
  );
}
