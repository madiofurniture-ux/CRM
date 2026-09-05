import { useState } from "react";
import { toast } from "sonner";
import { X } from "lucide-react";
import api from "@/lib/api";

const FIELD_LABEL = { id: "ID (match existing row)" };

/** Two-step CSV import: pick a file, preview + map its columns onto known
 * fields, then commit. `entity` is "leads" or "customers" (matches the API
 * path); `onImported` is called with the result summary after commit. */
export default function CsvImportModal({ entity, onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);   // { headers, sample_rows, fields, row_count }
  const [mapping, setMapping] = useState({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const doPreview = async () => {
    if (!file) return toast.error("Choose a CSV file first");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post(`/${entity}/import/preview`, form);
      setPreview({ headers: [], sample_rows: [], fields: [], row_count: 0, ...data });
      setMapping(data.suggested_mapping || {});
    } catch (e) {
      toast.error(e?.response?.data?.detail?.toString?.() || "Couldn't read that file");
    } finally {
      setBusy(false);
    }
  };

  const doCommit = async () => {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("mapping", JSON.stringify(mapping));
      const { data } = await api.post(`/${entity}/import/commit`, form);
      setResult(data);
      if (data.imported || data.updated) onImported?.();
      toast.success(`${data.imported} added, ${data.updated} updated, ${data.failed} failed`);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.toString?.() || "Import failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center sm:p-4" onClick={onClose}>
      <div className="bg-white rounded-t-2xl sm:rounded-xl border border-[var(--border)] w-full max-w-2xl shadow-2xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 className="font-heading font-semibold text-lg">Import CSV</h3>
          <button onClick={onClose} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)]"><X size={16} /></button>
        </div>

        {!result ? (
          <div className="p-5 space-y-4">
            {!preview ? (
              <>
                <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] || null)}
                       className="w-full text-sm" data-testid="csv-file-input" />
                <div className="flex justify-end gap-2">
                  <button className="btn-ghost" onClick={onClose}>Cancel</button>
                  <button className="btn-primary disabled:opacity-60" onClick={doPreview} disabled={busy || !file} data-testid="csv-preview-btn">
                    {busy ? "Reading…" : "Preview"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="text-sm text-[var(--ink-2)]">
                  {preview.row_count} row{preview.row_count === 1 ? "" : "s"} found — map each column below, or leave it "— Skip —".
                </div>
                <div className="border border-[var(--border)] rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-[var(--surface-2)] text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                      <tr><th className="text-left px-3 py-2">CSV column</th><th className="text-left px-3 py-2">Sample</th><th className="text-left px-3 py-2">Maps to</th></tr>
                    </thead>
                    <tbody>
                      {preview.headers.map((h) => (
                        <tr key={h} className="border-t border-[var(--border-light)]">
                          <td className="px-3 py-2 font-medium">{h}</td>
                          <td className="px-3 py-2 text-[var(--ink-3)] truncate max-w-[10rem]">{preview.sample_rows[0]?.[h] || ""}</td>
                          <td className="px-3 py-2">
                            <select value={mapping[h] || ""} onChange={(e) => setMapping((m) => ({ ...m, [h]: e.target.value }))}
                                    className="w-full px-2 py-1 rounded-md border border-[var(--border)] bg-white text-sm"
                                    data-testid={`csv-map-${h}`}>
                              <option value="">— Skip —</option>
                              {preview.fields.map((f) => <option key={f} value={f}>{FIELD_LABEL[f] || f}</option>)}
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex justify-end gap-2">
                  <button className="btn-ghost" onClick={() => setPreview(null)}>Back</button>
                  <button className="btn-primary disabled:opacity-60" onClick={doCommit} disabled={busy} data-testid="csv-commit-btn">
                    {busy ? "Importing…" : "Import"}
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          <div className="p-5 space-y-3">
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-lg bg-[var(--surface-2)] py-3"><div className="text-xl font-semibold">{result.imported}</div><div className="text-xs text-[var(--ink-3)]">Added</div></div>
              <div className="rounded-lg bg-[var(--surface-2)] py-3"><div className="text-xl font-semibold">{result.updated}</div><div className="text-xs text-[var(--ink-3)]">Updated</div></div>
              <div className="rounded-lg bg-[var(--surface-2)] py-3"><div className="text-xl font-semibold text-[var(--danger)]">{result.failed}</div><div className="text-xs text-[var(--ink-3)]">Failed</div></div>
            </div>
            {result.errors?.length > 0 && (
              <div className="border border-[var(--border)] rounded-lg max-h-48 overflow-y-auto text-xs divide-y divide-[var(--border-light)]">
                {result.errors.map((e, i) => (
                  <div key={i} className="px-3 py-1.5 text-[var(--danger)]">Row {e.row}: {e.error}</div>
                ))}
              </div>
            )}
            <div className="flex justify-end">
              <button className="btn-primary" onClick={onClose} data-testid="csv-done-btn">Done</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
