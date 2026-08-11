import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Download, Upload, Database } from "lucide-react";

// Import / export any dataset as CSV. Both are admin-only: export reads
// across the whole tenant's data, import writes across the whole collection.
// Upserts on each dataset's id field.
export default function DataCentre() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [cols, setCols] = useState([]);
  const [sel, setSel] = useState("");
  const [csv, setCsv] = useState("");
  const [result, setResult] = useState(null);

  const load = () => api.get("/data-centre/collections").then((r) => { setCols(r.data); if (!sel && r.data[0]) setSel(r.data[0].name); });
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const active = cols.find((c) => c.name === sel);

  const exportCsv = async (name) => {
    const { data } = await api.get(`/data-centre/export/${name}`);
    const blob = new Blob([data.csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `madio_${name}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    toast.success(`Exported ${data.count} ${name} rows`);
  };

  const importCsv = async () => {
    if (!csv.trim()) { toast.error("Paste some CSV first"); return; }
    if (!window.confirm(`Import into "${sel}"? Existing rows with a matching ${active?.id_field} are updated.`)) return;
    try {
      const { data } = await api.post(`/data-centre/import/${sel}`, { csv });
      setResult(data);
      toast.success(`${data.inserted} added, ${data.updated} updated, ${data.skipped} skipped`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Import failed");
    }
  };

  return (
    <>
      <Topbar title="Data Centre" subtitle="Import & export any dataset as CSV" />
      <div className="p-6 grid grid-cols-1 lg:grid-cols-3 gap-6" data-testid="data-centre-page">
        {/* Export */}
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4"><Database size={16} className="text-[var(--brand)]" /><div className="font-heading font-semibold">Datasets</div></div>
          <div className="space-y-2">
            {cols.map((c) => (
              <div key={c.name} className={`flex items-center justify-between px-3 py-2 rounded-lg border cursor-pointer ${sel === c.name ? "border-[var(--brand)] bg-[var(--brand-soft)]" : "border-[var(--border)]"}`} onClick={() => setSel(c.name)}>
                <div>
                  <div className="text-sm font-medium capitalize">{c.name}</div>
                  <div className="text-[11px] text-[var(--ink-3)]">{c.count} rows</div>
                </div>
                {isAdmin && (
                  <button onClick={(e) => { e.stopPropagation(); exportCsv(c.name); }} className="p-1.5 rounded-md hover:bg-white text-[var(--ink-2)]" title="Export CSV"><Download size={15} /></button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Import */}
        <div className="lg:col-span-2 bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2"><Upload size={16} className="text-[var(--brand)] " /><div className="font-heading font-semibold">Import into <span className="capitalize">{sel || "—"}</span></div></div>
            {active && <div className="text-[11px] text-[var(--ink-3)]">Key: <span className="font-mono">{active.id_field}</span></div>}
          </div>

          {!isAdmin ? (
            <div className="text-sm text-[var(--ink-3)] py-8 text-center">Import is available to admins only. You can still export any dataset.</div>
          ) : (
            <>
              {active && (
                <div className="text-[11px] text-[var(--ink-3)] mb-2">
                  Columns: <span className="font-mono">{active.fields.join(", ")}</span>. First row must be the header. Rows are matched on <span className="font-mono">{active.id_field}</span>; rows without it are skipped.
                </div>
              )}
              <textarea value={csv} onChange={(e) => setCsv(e.target.value)} rows={10} placeholder={`Paste CSV for "${sel}" here…`} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-xs font-mono outline-none focus:border-[var(--brand)]" data-testid="dc-import-textarea" />
              <div className="flex items-center gap-2 mt-3">
                <button className="btn-primary" onClick={importCsv}><Upload size={14} /> Import</button>
                <button className="btn-ghost" onClick={() => exportCsv(sel)}><Download size={14} /> Export current as template</button>
              </div>
              {result && (
                <div className="mt-4 text-sm bg-[var(--surface-2)] rounded-lg p-3">
                  <span className="text-[var(--moss)] font-semibold">{result.inserted}</span> added ·{" "}
                  <span className="text-[var(--brand)] font-semibold">{result.updated}</span> updated ·{" "}
                  <span className="text-[var(--ink-3)]">{result.skipped}</span> skipped (of {result.total})
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
