import { useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import api, { formatApiError } from "@/lib/api";
import { shrinkImage } from "@/lib/image";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import {
  Plus, ArrowDownCircle, ArrowUpCircle, Download, Trash2, X, Wallet,
  Check, Ban, Briefcase,
} from "lucide-react";

const CATEGORIES = ["Hardware", "Fuel", "Refreshments", "Transport", "Advances", "Other"];
const MODES = ["CASH", "UPI", "ONLINE"];

const emptyEntry = { amount: "", category: CATEGORIES[0], payment_mode: "CASH", remark: "", receipt_url: "", entry_person: "" };
const emptyBook = { book_name: "", description: "", initial_balance: "", project_id: "", imprest_limit: "", strict_overdraft: false };

export default function Cashbook() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [books, setBooks] = useState([]);
  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [entries, setEntries] = useState([]);
  const [users, setUsers] = useState([]);
  const [showNewBook, setShowNewBook] = useState(false);
  const [bookForm, setBookForm] = useState(emptyBook);
  const [drawer, setDrawer] = useState(null); // "CASH_IN" | "CASH_OUT" | null
  const [entryForm, setEntryForm] = useState(emptyEntry);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [projectFilter, setProjectFilter] = useState("All");
  const [pendingTotal, setPendingTotal] = useState(0);

  const loadBooks = async () => {
    // skipCache: this refetches right after top-up/expense/approve/reject/
    // delete, whose POST/DELETE urls (/cashbook-entries/...) don't share a
    // cache-invalidation prefix with GET /cashbooks/... in lib/api.js's
    // resource-prefix cache — without this, the balance/status shown here
    // can lag up to CACHE_TTL_MS behind what the mutation actually did.
    const { data } = await api.get("/cashbooks", { skipCache: true });
    setBooks(data);
    if (!selectedId && data.length) setSelectedId(data[0].id);
    // Pending-approval total across every wallet — small fan-out, fine at
    // this scale; add a dedicated aggregate endpoint if the list ever grows large.
    const perBook = await Promise.all(data.map((b) => api.get(`/cashbooks/${b.id}/entries`, { skipCache: true }).then((r) => r.data).catch(() => [])));
    const pending = perBook.flat().filter((e) => e.type === "CASH_OUT" && e.status === "Pending").reduce((a, e) => a + e.amount, 0);
    setPendingTotal(pending);
  };
  const loadEntries = (id) => { if (id) api.get(`/cashbooks/${id}/entries`, { skipCache: true }).then((r) => setEntries(r.data)); };

  useEffect(() => {
    loadBooks();
    api.get("/users/directory").then(({ data }) => setUsers(data)).catch(() => setUsers([]));
    api.get("/projects").then(({ data }) => setProjects(data)).catch(() => setProjects([]));
  }, []); // eslint-disable-line
  useEffect(() => loadEntries(selectedId), [selectedId]);

  const userName = (id) => users.find((u) => u.id === id)?.name || id;
  const projectLabel = (id) => projects.find((p) => p.id === id)?.project_no || projects.find((p) => p.id === id)?.customer || "";

  const book = books.find((b) => b.id === selectedId);
  const totals = useMemo(() => {
    const totalIn = entries.filter((e) => e.type === "CASH_IN").reduce((a, e) => a + e.amount, 0);
    const totalOut = entries.filter((e) => e.type === "CASH_OUT" && e.status !== "Rejected").reduce((a, e) => a + e.amount, 0);
    return { totalIn, totalOut };
  }, [entries]);

  const visibleBooks = useMemo(() => (
    projectFilter === "All" ? books : books.filter((b) => (b.project_id || "") === projectFilter)
  ), [books, projectFilter]);

  const filteredEntries = useMemo(() => (
    categoryFilter === "All" ? entries : entries.filter((e) => (e.category || "") === categoryFilter)
  ), [entries, categoryFilter]);

  const headerStats = useMemo(() => ({
    totalFloat: books.reduce((a, b) => a + (b.current_balance || 0), 0),
    activeProjectWallets: books.filter((b) => b.project_id && b.status === "ACTIVE").length,
  }), [books]);

  const createBook = async () => {
    if (!bookForm.book_name.trim() || saving) return;
    setSaving(true);
    try {
      const { data } = await api.post("/cashbooks", {
        book_name: bookForm.book_name, description: bookForm.description,
        initial_balance: parseFloat(bookForm.initial_balance) || 0, current_balance: 0,
        project_id: bookForm.project_id, imprest_limit: parseFloat(bookForm.imprest_limit) || 0,
        strict_overdraft: bookForm.strict_overdraft,
      });
      toast.success("Cashbook created");
      setShowNewBook(false); setBookForm(emptyBook);
      await loadBooks(); setSelectedId(data.id);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const openDrawer = (bookId, type) => {
    setSelectedId(bookId);
    setEntryForm({ ...emptyEntry, entry_person: user?.name || "" });
    setDrawer(type);
  };

  const uploadReceipt = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const dataUrl = await shrinkImage(file);
      setEntryForm((f) => ({ ...f, receipt_url: dataUrl }));
    } catch { toast.error("Could not read that file — try a photo (JPG/PNG)"); }
    finally { setUploading(false); }
  };

  const saveEntry = async () => {
    const amount = parseFloat(entryForm.amount);
    if (!amount || amount <= 0) return toast.error("Enter an amount greater than zero");
    if (saving) return;
    setSaving(true);
    try {
      if (drawer === "CASH_IN") {
        await api.post(`/cashbooks/${selectedId}/top-up`, {
          amount, payment_mode: entryForm.payment_mode, remark: entryForm.remark, entry_person: entryForm.entry_person,
        });
        toast.success("Top-up recorded");
      } else {
        await api.post(`/cashbooks/${selectedId}/expense`, {
          amount, category: entryForm.category, payment_mode: entryForm.payment_mode,
          remark: entryForm.remark, receipt_url: entryForm.receipt_url, entry_person: entryForm.entry_person,
        });
        toast.success("Expense logged — awaiting approval");
      }
      setDrawer(null);
      await Promise.all([loadBooks(), loadEntries(selectedId)]);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const decideEntry = async (entry, approved) => {
    try {
      await api.post(`/cashbook-entries/${entry.id}/approve`, { approved });
      toast.success(approved ? "Expense approved" : "Expense rejected");
      await Promise.all([loadBooks(), loadEntries(selectedId)]);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const removeEntry = async (entry) => {
    if (!window.confirm(`Delete this ${entry.type === "CASH_IN" ? "cash in" : "cash out"} entry of ${inrFull(entry.amount)}? This reverses the book balance.`)) return;
    try {
      await api.delete(`/cashbook-entries/${entry.id}`);
      toast.success("Entry deleted, balance reversed");
      await Promise.all([loadBooks(), loadEntries(selectedId)]);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const downloadReport = async () => {
    const { data } = await api.get("/cashbook-entries/export.csv", { skipCache: true, responseType: "blob" });
    const blob = new Blob([data], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `cashbook_entries_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <Topbar title="Petty Cash & Cashbooks" subtitle={book ? book.book_name : "Select a wallet"}
        actions={<button onClick={downloadReport} className="btn-ghost"><Download size={14} /> Export CSV</button>} />
      <div className="p-6 space-y-6" data-testid="cashbook-page">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <KpiCard label="Total Cash in Float" value={inrFull(headerStats.totalFloat)} icon={Wallet} />
          <KpiCard label="Active Project Wallets" value={headerStats.activeProjectWallets} icon={Briefcase} accent="moss" />
          <KpiCard label="Pending Approval" value={inrFull(pendingTotal)} accent="danger" icon={ArrowUpCircle} />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)}
            className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
            <option value="All">All projects</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.project_no || p.customer}</option>)}
          </select>
          <button onClick={() => setShowNewBook(true)} className="btn-ghost" data-testid="new-cashbook"><Plus size={14} /> New Wallet</button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {visibleBooks.map((b) => {
            const pct = b.imprest_limit > 0 ? Math.min(100, Math.max(0, (b.current_balance / b.imprest_limit) * 100)) : null;
            return (
              <button key={b.id} onClick={() => setSelectedId(b.id)} data-testid={`cashbook-tab-${b.id}`}
                className={`text-left p-4 rounded-xl border transition-colors ${selectedId === b.id ? "border-[var(--brand)] bg-[var(--brand-soft)]" : "border-[var(--border)] bg-[var(--surface)]"}`}>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="font-heading font-semibold text-sm flex items-center gap-1.5"><Wallet size={14} />{b.book_name}</div>
                  {b.project_id && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--surface-2)] text-[var(--ink-2)] shrink-0">{projectLabel(b.project_id)}</span>
                  )}
                </div>
                <div className="font-mono text-lg font-semibold mb-1">{inrFull(b.current_balance)}</div>
                {pct != null && (
                  <div className="h-1.5 rounded-full bg-[var(--surface-2)] overflow-hidden mb-1">
                    <div className={`h-full ${pct >= 90 ? "bg-[var(--danger)]" : "bg-[var(--brand)]"}`} style={{ width: `${pct}%` }} />
                  </div>
                )}
                <div className="text-xs text-[var(--ink-3)] mb-2">
                  {(b.assigned_users || []).map(userName).join(", ") || "No custodian"}
                </div>
                <div className="flex gap-1.5">
                  <button onClick={(e) => { e.stopPropagation(); openDrawer(b.id, "CASH_IN"); }}
                    className="flex-1 text-xs py-1.5 rounded-lg border border-[var(--border)] hover:bg-[var(--surface-hover)]">Top Up</button>
                  <button onClick={(e) => { e.stopPropagation(); openDrawer(b.id, "CASH_OUT"); }}
                    className="flex-1 text-xs py-1.5 rounded-lg border border-[var(--danger)] text-[var(--danger)] hover:bg-[var(--danger-soft)]">Log Expense</button>
                </div>
              </button>
            );
          })}
          {visibleBooks.length === 0 && (
            <div className="col-span-full text-sm text-[var(--ink-3)] py-8 text-center">No wallets yet — create one to start tracking petty cash.</div>
          )}
        </div>

        {book && (
          <>
            <div className="grid grid-cols-2 gap-4">
              <KpiCard label="Total In" value={inrFull(totals.totalIn)} accent="moss" icon={ArrowDownCircle} />
              <KpiCard label="Total Out" value={inrFull(totals.totalOut)} accent="danger" icon={ArrowUpCircle} />
            </div>

            <div className="flex flex-wrap gap-2">
              <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}
                className="px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-sm">
                <option value="All">All categories</option>
                {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>

            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-[var(--surface-2)]">
                    <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                      <th className="text-left font-semibold px-4 py-2.5">Date</th>
                      <th className="text-left font-semibold px-4 py-2.5">Category</th>
                      <th className="text-left font-semibold px-4 py-2.5">Mode</th>
                      <th className="text-left font-semibold px-4 py-2.5">Remark</th>
                      <th className="text-left font-semibold px-4 py-2.5">By</th>
                      <th className="text-left font-semibold px-4 py-2.5">Status</th>
                      <th className="text-right font-semibold px-4 py-2.5">Amount</th>
                      <th className="px-4 py-2.5" />
                    </tr>
                  </thead>
                  <tbody>
                    {filteredEntries.map((e) => (
                      <tr key={e.id} className="border-t border-[var(--border-light)]" data-testid={`entry-${e.id}`}>
                        <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(e.created_at)}</td>
                        <td className="px-4 py-3">{e.category || "—"}</td>
                        <td className="px-4 py-3 text-[var(--ink-2)]">{e.payment_mode}</td>
                        <td className="px-4 py-3 text-[var(--ink-2)] max-w-[220px] truncate">{e.remark || "—"}</td>
                        <td className="px-4 py-3 text-[var(--ink-2)]">{e.entry_person || "—"}</td>
                        <td className="px-4 py-3">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold uppercase ${
                            e.status === "Pending" ? "bg-amber-100 text-amber-700"
                              : e.status === "Rejected" ? "bg-[var(--danger-soft)] text-[var(--danger)]"
                              : "bg-emerald-100 text-emerald-700"}`}>{e.status || "Approved"}</span>
                        </td>
                        <td className={`px-4 py-3 text-right font-mono font-semibold ${e.type === "CASH_IN" ? "text-[var(--moss)]" : "text-[var(--danger)]"}`}>
                          {e.type === "CASH_IN" ? "+" : "-"}{inrFull(e.amount)}
                        </td>
                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          {isAdmin && e.status === "Pending" ? (
                            <span className="inline-flex gap-1">
                              <button onClick={() => decideEntry(e, true)} title="Approve" className="p-1 rounded hover:bg-emerald-100 text-emerald-700"><Check size={13} /></button>
                              <button onClick={() => decideEntry(e, false)} title="Reject" className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Ban size={13} /></button>
                            </span>
                          ) : (
                            <button onClick={() => removeEntry(e)} className="p-1 rounded hover:bg-[var(--surface-hover)] text-[var(--ink-3)]"><Trash2 size={13} /></button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {filteredEntries.length === 0 && (
                      <tr><td colSpan={8} className="py-8 text-center text-[var(--ink-3)]">No entries yet in this wallet.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>

      {showNewBook && (
        <div className="fixed inset-0 bg-black/40 z-[70] flex items-end sm:items-center justify-center sm:p-4" onClick={() => setShowNewBook(false)}>
          <div className="bg-white rounded-t-2xl sm:rounded-xl w-full max-w-sm p-5 max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading font-semibold">New Wallet</h3>
              <button onClick={() => setShowNewBook(false)}><X size={16} /></button>
            </div>
            <div className="space-y-3">
              <Field label="Wallet Name *" value={bookForm.book_name} onChange={(v) => setBookForm({ ...bookForm, book_name: v })} />
              <Field label="Description" value={bookForm.description} onChange={(v) => setBookForm({ ...bookForm, description: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Linked Project</label>
                <select value={bookForm.project_id} onChange={(e) => setBookForm({ ...bookForm, project_id: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                  <option value="">— None —</option>
                  {projects.map((p) => <option key={p.id} value={p.id}>{p.project_no || p.customer}</option>)}
                </select>
              </div>
              <Field label="Opening Balance" type="number" value={bookForm.initial_balance} onChange={(v) => setBookForm({ ...bookForm, initial_balance: v })} />
              <Field label="Imprest Limit (0 = none)" type="number" value={bookForm.imprest_limit} onChange={(v) => setBookForm({ ...bookForm, imprest_limit: v })} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={bookForm.strict_overdraft} onChange={(e) => setBookForm({ ...bookForm, strict_overdraft: e.target.checked })} />
                Block expenses that would overdraw this wallet
              </label>
            </div>
            <button onClick={createBook} disabled={saving} className="btn-primary w-full justify-center mt-4 disabled:opacity-60">
              {saving ? "Creating…" : "Create Wallet"}
            </button>
          </div>
        </div>
      )}

      {drawer && (
        <div className="fixed inset-0 z-[70] bg-black/40 flex items-end sm:items-stretch sm:justify-end" onClick={() => setDrawer(null)}>
          <div className="w-full sm:max-w-sm bg-white rounded-t-2xl sm:rounded-none h-auto sm:h-full max-h-[85vh] sm:max-h-none overflow-y-auto p-5" data-testid="entry-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading font-semibold">{drawer === "CASH_IN" ? "Top Up" : "Log Expense"}</h3>
              <button onClick={() => setDrawer(null)}><X size={16} /></button>
            </div>
            <div className="space-y-3">
              <Field label="Amount *" type="number" value={entryForm.amount} onChange={(v) => setEntryForm({ ...entryForm, amount: v })} />
              {drawer === "CASH_OUT" && (
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Category</label>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {CATEGORIES.map((c) => (
                      <button key={c} onClick={() => setEntryForm({ ...entryForm, category: c })}
                        className={`px-2.5 py-1 rounded-full text-xs border ${entryForm.category === c ? "bg-[var(--brand)] text-white border-[var(--brand)]" : "border-[var(--border)] text-[var(--ink-2)]"}`}>
                        {c}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <SelectField label="Payment Mode" value={entryForm.payment_mode} options={MODES}
                onChange={(v) => setEntryForm({ ...entryForm, payment_mode: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Staff</label>
                <select value={entryForm.entry_person} onChange={(e) => setEntryForm({ ...entryForm, entry_person: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
                  <option value={user?.name || ""}>{user?.name || "Me"}</option>
                  {users.filter((u) => u.name !== user?.name).map((u) => <option key={u.id} value={u.name}>{u.name}</option>)}
                </select>
              </div>
              <Field label="Note" value={entryForm.remark} onChange={(v) => setEntryForm({ ...entryForm, remark: v })} />
              {drawer === "CASH_OUT" && (
                <div>
                  <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Receipt (optional)</label>
                  <input type="file" accept="image/*" capture="environment" onChange={(e) => uploadReceipt(e.target.files?.[0])} className="text-xs" />
                  {uploading && <div className="text-xs text-[var(--ink-3)] mt-1">Processing…</div>}
                  {entryForm.receipt_url && <img src={entryForm.receipt_url} alt="Receipt" className="mt-2 h-20 rounded-lg border border-[var(--border)]" />}
                </div>
              )}
            </div>
            <button onClick={saveEntry} disabled={saving}
              className={`w-full justify-center mt-5 ${drawer === "CASH_IN" ? "btn-primary" : "btn-ghost !border-[var(--danger)] !text-[var(--danger)]"} disabled:opacity-60`}
              data-testid="save-entry">
              {saving ? "Saving…" : drawer === "CASH_IN" ? "Record Top Up" : "Log Expense (needs approval)"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function Field({ label, value, onChange, type = "text" }) {
  return (
    <div>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{label}</label>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm" />
    </div>
  );
}

function SelectField({ label, value, options, onChange }) {
  return (
    <div>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}
