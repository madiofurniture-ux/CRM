import { useCallback, useEffect, useState } from "react";
import { KeyRound, RefreshCw, AlertTriangle, CheckCircle2, Copy } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { toast } from "sonner";

const KIND_LABEL = {
  stock_items: "Stock items", ledgers: "Customer ledgers",
  sales_vouchers: "Sales invoices", receipts: "Receipts",
};

/** Finance → Tally: status of the office-PC connector that refreshes the CRM
 * from Tally, its key, and the import log. Setup: docs/TALLY_CONNECTOR.md. */
export default function TallyConnectorPanel() {
  const [status, setStatus] = useState(null);
  const [imports, setImports] = useState([]);
  const [newKey, setNewKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [showLog, setShowLog] = useState(false);

  const load = useCallback(() => {
    api.get("/finance/tally/connector", { skipCache: true }).then(({ data }) => setStatus(data)).catch(() => setStatus(null));
    api.get("/finance/tally/imports?limit=50", { skipCache: true }).then(({ data }) => setImports(data || [])).catch(() => setImports([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    if (status?.key && !window.confirm("Generate a new key? The connector stops working until its settings get the new key.")) return;
    setBusy(true);
    try {
      const { data } = await api.post("/finance/tally/connector-key");
      setNewKey(data.key);
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't generate a key"); }
    finally { setBusy(false); }
  };

  const copy = async () => {
    try { await navigator.clipboard.writeText(newKey); toast.success("Key copied"); }
    catch { toast.error("Copy failed; select the key and copy it manually"); }
  };

  const last = status?.last_imports || {};
  return (
    <section className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-4 mb-4" data-testid="tally-connector">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-heading font-semibold">Tally → CRM refresh</h2>
          <p className="text-xs text-[var(--ink-3)] max-w-xl">
            The MADIO Tally Connector on the Tally computer sends stock, customer ledgers, sales invoices and receipts
            every 15 minutes. CRM stock stays the stock of record; Tally's figure shows beside it in Inventory.
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn-ghost text-sm" onClick={load}><RefreshCw size={13} /> Refresh</button>
          <button type="button" className="btn-primary text-sm disabled:opacity-60" onClick={generate} disabled={busy}
                  data-testid="tally-key-generate">
            <KeyRound size={13} /> {status?.key ? "New connector key" : "Generate connector key"}
          </button>
        </div>
      </div>

      {newKey && (
        <div className="mt-3 p-3 rounded-lg border border-[var(--warn,#d97706)] bg-[var(--warn-soft,#fffbeb)]" data-testid="tally-key-shown">
          <div className="text-sm font-medium mb-1">Copy this key into the connector's tally_connector.ini now. It won't be shown again.</div>
          <div className="flex gap-2 items-center">
            <code className="flex-1 text-xs break-all bg-white rounded px-2 py-1 border">{newKey}</code>
            <button type="button" className="btn-ghost text-xs" onClick={copy}><Copy size={12} /> Copy</button>
            <button type="button" className="btn-ghost text-xs" onClick={() => setNewKey("")}>Done</button>
          </div>
        </div>
      )}

      <div className="mt-3 text-sm flex flex-wrap items-center gap-x-4 gap-y-1">
        {!status?.key ? (
          <span className="text-[var(--ink-3)]">Not set up yet. Generate a key, then follow the setup guide (docs/TALLY_CONNECTOR.md).</span>
        ) : status.stale ? (
          <span className="inline-flex items-center gap-1 text-[var(--danger)]"><AlertTriangle size={14} />
            {status.last_import_at ? `Nothing from Tally since ${fmtDateTime(status.last_import_at)}. Is Tally open and the connector scheduled?` : "Key issued; waiting for the first refresh from the connector."}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-[var(--success,#15803d)]"><CheckCircle2 size={14} /> Last refresh {fmtDateTime(status.last_import_at)}</span>
        )}
        {status?.key && <span className="text-xs text-[var(--ink-3)] font-mono">key {status.key.prefix}…</span>}
      </div>

      {Object.keys(last).length > 0 && (
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          {Object.keys(KIND_LABEL).map((k) => last[k] && (
            <div key={k} className="rounded-lg bg-[var(--surface-2)] p-2 text-xs">
              <div className="font-semibold text-[var(--ink)]">{KIND_LABEL[k]}</div>
              <div className="text-[var(--ink-3)]">{last[k].created} new · {last[k].updated} updated</div>
              {last[k].error_count > 0 && <div className="text-[var(--danger)]">{last[k].error_count} not imported</div>}
            </div>
          ))}
        </div>
      )}

      {imports.length > 0 && (
        <div className="mt-3">
          <button type="button" className="text-xs text-[var(--brand)] underline" onClick={() => setShowLog((v) => !v)}
                  data-testid="tally-import-log-toggle">
            {showLog ? "Hide import log" : `Import log (${imports.length})`}
          </button>
          {showLog && (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr className="text-left text-[var(--ink-3)]"><th className="py-1 pr-3">When</th><th className="pr-3">What</th><th className="pr-3">New</th><th className="pr-3">Updated</th><th>Problems</th></tr></thead>
                <tbody>
                  {imports.map((r) => (
                    <tr key={r.id} className="border-t border-[var(--border-light)] align-top">
                      <td className="py-1 pr-3 whitespace-nowrap">{fmtDateTime(r.at)}</td>
                      <td className="pr-3">{KIND_LABEL[r.kind] || r.kind}</td>
                      <td className="pr-3">{r.created}</td>
                      <td className="pr-3">{r.updated}</td>
                      <td className="text-[var(--danger)]">{(r.errors || []).slice(0, 3).join(" · ")}{r.error_count > 3 ? ` (+${r.error_count - 3} more)` : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
