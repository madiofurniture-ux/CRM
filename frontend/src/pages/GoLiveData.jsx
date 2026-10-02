import { useCallback, useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { toast } from "sonner";
import { Upload, FileSpreadsheet, AlertTriangle, CheckCircle2, Undo2, Zap, Loader2 } from "lucide-react";

/**
 * Admin screen: Go-live data. Upload the working spreadsheets (enquiry book,
 * purchase-order book, MIS), preview what they turn into, then replace this
 * company's business data with them. Everything replaced is archived first
 * and any load can be undone. Users, roles, settings, workflows and flows
 * stay. See go_live_import.py.
 */
const LABELS = {
  visitors: "Visitors", leads: "Leads (Navaki referrals)", architects: "Architects & partners",
  quotes: "Quotations", sales: "Sales orders", customers: "Customers", vendors: "Vendors",
  purchase_orders: "Purchase orders", inventory: "Inventory items",
};

function FilePicker({ files, setFiles }) {
  return (
    <label className="flex flex-col items-center justify-center gap-2 p-6 border-2 border-dashed border-[var(--border)] rounded-xl cursor-pointer hover:border-[var(--brand)]"
           data-testid="golive-files">
      <Upload size={22} className="text-[var(--ink-3)]" />
      <span className="text-sm font-medium">Choose the .xlsx workbooks</span>
      <span className="text-xs text-[var(--ink-3)] text-center">
        Enquiry book (Visitors, MF Quotes, MF Sale, Arch, Navaki), Purchase Order book, MIS (Closing Stock)
      </span>
      <input type="file" accept=".xlsx" multiple className="hidden"
             onChange={(e) => setFiles(Array.from(e.target.files || []))} data-testid="golive-file-input" />
      {files.length > 0 && (
        <ul className="mt-2 text-xs text-[var(--ink-2)]">
          {files.map((f) => <li key={f.name} className="flex items-center gap-1"><FileSpreadsheet size={12} /> {f.name}</li>)}
        </ul>
      )}
    </label>
  );
}

function ReportTable({ report }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-[var(--ink-3)]">
            <th className="py-1 pr-3">Sheet</th><th className="pr-3">Rows</th><th className="pr-3">Loaded</th>
            <th className="pr-3">Skipped</th><th>Cleaned up</th>
          </tr>
        </thead>
        <tbody>
          {report.map((r) => (
            <tr key={r.sheet} className="border-t border-[var(--border-light)] align-top">
              <td className="py-1.5 pr-3 font-medium">{r.sheet}</td>
              <td className="pr-3">{r.rows}</td>
              <td className="pr-3">{r.loaded}</td>
              <td className="pr-3 text-xs">
                {r.skipped_total === 0 ? "—" : Object.entries(r.skipped).map(([k, n]) => <div key={k}>{n} · {k}</div>)}
              </td>
              <td className="text-xs text-[var(--ink-3)]">
                {Object.entries(r.notes).map(([k, n]) => <div key={k}>{n} · {k}</div>)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function GoLiveData() {
  const [files, setFiles] = useState([]);
  const [includeHr, setIncludeHr] = useState(false);
  const [preview, setPreview] = useState(null);
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState(null);
  const [resets, setResets] = useState([]);

  const loadResets = useCallback(() => {
    api.get("/admin/go-live/resets", { skipCache: true }).then(({ data }) => setResets(data || [])).catch(() => setResets([]));
  }, []);
  useEffect(() => { loadResets(); }, [loadResets]);
  useEffect(() => { setPreview(null); setResult(null); setConfirm(""); }, [files, includeHr]);

  const form = () => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("include_hr", includeHr ? "true" : "false");
    return fd;
  };

  const doPreview = async () => {
    setBusy("preview");
    try {
      const { data } = await api.post("/admin/go-live/preview", form());
      setPreview(data);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't read the workbooks"); }
    finally { setBusy(""); }
  };

  const doLoad = async () => {
    setBusy("load");
    try {
      const fd = form();
      fd.append("confirm", confirm);
      fd.append("apply_office", "true");
      const { data } = await api.post("/admin/go-live/load", fd, { timeout: 300000 });
      setResult(data);
      setPreview(null);
      setConfirm("");
      toast.success("Data loaded");
      loadResets();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Load failed"); }
    finally { setBusy(""); }
  };

  const undo = async (r) => {
    const typed = window.prompt(`Undo the load of ${fmtDateTime(r.at)}? Everything loaded or added since is removed and the archived data comes back.\n\nType RESTORE to confirm.`);
    if (!typed) return;
    setBusy(`undo-${r.id}`);
    try {
      await api.post(`/admin/go-live/resets/${r.id}/restore`, { confirm: typed });
      toast.success("Previous data restored");
      loadResets();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Undo failed"); }
    finally { setBusy(""); }
  };

  const starterFlows = async () => {
    setBusy("flows");
    try {
      const { data } = await api.post("/admin/go-live/starter-flows");
      toast.success(data.added.length ? `Added ${data.added.length} flows` : "Starter flows are already there");
      (data.skipped || []).filter((s) => s.reason !== "already there")
        .forEach((s) => toast.warning(`${s.name}: ${s.reason}`));
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Couldn't add the flows"); }
    finally { setBusy(""); }
  };

  const willClear = preview ? Object.entries(preview.will_clear || {}) : [];
  const clearTotal = willClear.reduce((a, [, n]) => a + n, 0);

  return (
    <div className="flex flex-col min-h-full">
      <Topbar title="Go-live data" subtitle="Replace test data with the business's own records" />
      <div className="p-4 md:p-6 max-w-5xl w-full space-y-4">
        <section className="bg-[var(--surface)] border border-[var(--border-light)] rounded-2xl p-4 space-y-3">
          <h2 className="font-heading font-semibold">1. Upload and preview</h2>
          <FilePicker files={files} setFiles={setFiles} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={includeHr} onChange={(e) => setIncludeHr(e.target.checked)} data-testid="golive-include-hr" />
            Also clear staff attendance, leave and payroll records
          </label>
          <button type="button" className="btn-primary text-sm disabled:opacity-60" disabled={!files.length || !!busy}
                  onClick={doPreview} data-testid="golive-preview">
            {busy === "preview" ? <Loader2 size={14} className="animate-spin" /> : <FileSpreadsheet size={14} />} Preview
          </button>
        </section>

        {preview && (
          <section className="bg-[var(--surface)] border border-[var(--border-light)] rounded-2xl p-4 space-y-4" data-testid="golive-preview-result">
            <h2 className="font-heading font-semibold">2. Check what will load</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {Object.entries(preview.counts).map(([k, n]) => (
                <div key={k} className="rounded-lg bg-[var(--surface-2)] p-2">
                  <div className="text-lg font-semibold">{n}</div>
                  <div className="text-xs text-[var(--ink-3)]">{LABELS[k] || k}</div>
                </div>
              ))}
            </div>
            {preview.office?.gstin && (
              <p className="text-sm">Company details for invoices: <b>{preview.office.name}</b>, {preview.office.address} · GSTIN {preview.office.gstin}</p>
            )}
            {(preview.warnings || []).map((w) => (
              <p key={w} className="text-sm text-[var(--danger)] flex items-center gap-1"><AlertTriangle size={14} /> {w}</p>
            ))}
            <ReportTable report={preview.report} />
            {preview.sheets_ignored?.length > 0 && (
              <p className="text-xs text-[var(--ink-3)]">Not used: {preview.sheets_ignored.join(", ")}</p>
            )}

            <div className="rounded-xl border border-[var(--danger)] p-3 space-y-2">
              <h3 className="font-semibold text-sm flex items-center gap-1 text-[var(--danger)]"><AlertTriangle size={14} /> 3. Replace the data</h3>
              <p className="text-sm">
                {clearTotal
                  ? `${clearTotal} existing records will be archived and removed: ${willClear.map(([k, n]) => `${n} ${k.replace(/_/g, " ")}`).join(", ")}.`
                  : "There is no existing business data to remove."}
                {" "}Users, roles, settings, workflows and flows stay. You can undo this below.
              </p>
              <div className="flex flex-wrap gap-2 items-center">
                <input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder={`Type ${preview.confirm_phrase}`}
                       className="px-2.5 py-1.5 rounded-lg border border-[var(--border)] text-sm w-56" data-testid="golive-confirm" />
                <button type="button" className="btn-primary text-sm disabled:opacity-60" data-testid="golive-load"
                        disabled={confirm.trim().toUpperCase() !== preview.confirm_phrase || !!busy} onClick={doLoad}>
                  {busy === "load" ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} Delete and load
                </button>
              </div>
            </div>
          </section>
        )}

        {result && (
          <section className="bg-[var(--surface)] border border-[var(--border-light)] rounded-2xl p-4 space-y-2" data-testid="golive-done">
            <h2 className="font-heading font-semibold flex items-center gap-1 text-[var(--success,#15803d)]"><CheckCircle2 size={16} /> Loaded</h2>
            <p className="text-sm">
              {Object.entries(result.loaded).map(([k, n]) => `${n} ${LABELS[k] || k}`).join(" · ")}
            </p>
            <p className="text-xs text-[var(--ink-3)]">
              Archived {Object.values(result.archived).reduce((a, n) => a + n, 0)} old records.
              {result.office?.gstin ? ` Office details set to ${result.office.name}, GSTIN ${result.office.gstin}.` : ""}
            </p>
          </section>
        )}

        <section className="bg-[var(--surface)] border border-[var(--border-light)] rounded-2xl p-4 space-y-2">
          <h2 className="font-heading font-semibold">Follow-up flows</h2>
          <p className="text-sm text-[var(--ink-3)]">
            Adds MADIO's follow-up automations: call back new visitors, first call to new leads, quotation follow-ups at 3 and 7 days,
            stalled negotiations, collecting balances after delivery, raising the vendor PO on a new order, long-running projects.
            They apply to records that change from now on, so loading old data doesn't create a flood of tasks. Edit them under Flows.
          </p>
          <button type="button" className="btn-ghost text-sm" onClick={starterFlows} disabled={!!busy} data-testid="golive-flows">
            <Zap size={14} /> Add starter flows
          </button>
        </section>

        {resets.length > 0 && (
          <section className="bg-[var(--surface)] border border-[var(--border-light)] rounded-2xl p-4">
            <h2 className="font-heading font-semibold mb-2">Previous loads</h2>
            <table className="w-full text-sm">
              <tbody>
                {resets.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--border-light)]">
                    <td className="py-1.5 pr-3 whitespace-nowrap">{fmtDateTime(r.at)}</td>
                    <td className="pr-3">{r.by_user}</td>
                    <td className="pr-3 text-xs text-[var(--ink-3)]">
                      loaded {Object.values(r.loaded || {}).reduce((a, n) => a + n, 0)} · archived {Object.values(r.archived || {}).reduce((a, n) => a + n, 0)}
                    </td>
                    <td className="pr-3 text-xs">{r.status === "restored" ? `undone ${fmtDateTime(r.restored_at)}` : r.status}</td>
                    <td className="text-right">
                      {r.status !== "restored" && (
                        <button type="button" className="btn-ghost text-xs" onClick={() => undo(r)} disabled={!!busy}>
                          <Undo2 size={12} /> Undo
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
      </div>
    </div>
  );
}
