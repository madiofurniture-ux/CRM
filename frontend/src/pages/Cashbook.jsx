import { useEffect, useMemo, useState } from "react";
import Topbar from "@/components/Topbar";
import KpiCard from "@/components/KpiCard";
import api, { formatApiError } from "@/lib/api";
import { shrinkImage } from "@/lib/image";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Plus, ArrowDownCircle, ArrowUpCircle, Download, Trash2, X, Wallet } from "lucide-react";

const CATEGORIES = ["Hardware", "Fuel", "Refreshments", "Transport", "Advances", "Other"];
const MODES = ["CASH", "UPI", "ONLINE"];

const emptyEntry = { amount: "", category: CATEGORIES[0], payment_mode: "CASH", remark: "", receipt_url: "", entry_person: "" };
const emptyBook = { book_name: "", description: "", initial_balance: "" };

export default function Cashbook() {
  const { user } = useAuth();
  const [books, setBooks] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [entries, setEntries] = useState([]);
  const [users, setUsers] = useState([]);
  const [showNewBook, setShowNewBook] = useState(false);
  const [bookForm, setBookForm] = useState(emptyBook);
  const [drawer, setDrawer] = useState(null); // "CASH_IN" | "CASH_OUT" | null
  const [entryForm, setEntryForm] = useState(emptyEntry);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const loadBooks = async () => {
    const { data } = await api.get("/cashbooks");
    setBooks(data);
    if (!selectedId && data.length) setSelectedId(data[0].id);
  };
  const loadEntries = (id) => { if (id) api.get(`/cashbooks/${id}/entries`).then((r) => setEntries(r.data)); };

  useEffect(() => {
    loadBooks();
    api.get("/users/directory").then(({ data }) => setUsers(data)).catch(() => setUsers([]));
  }, []); // eslint-disable-line
  useEffect(() => loadEntries(selectedId), [selectedId]);

  const book = books.find((b) => b.id === selectedId);
  const totals = useMemo(() => {
    const totalIn = entries.filter((e) => e.type === "CASH_IN").reduce((a, e) => a + e.amount, 0);
    const totalOut = entries.filter((e) => e.type === "CASH_OUT").reduce((a, e) => a + e.amount, 0);
    return { totalIn, totalOut };
  }, [entries]);

  const createBook = async () => {
    if (!bookForm.book_name.trim() || saving) return;
    setSaving(true);
    try {
      const { data } = await api.post("/cashbooks", {
        book_name: bookForm.book_name, description: bookForm.description,
        initial_balance: parseFloat(bookForm.initial_balance) || 0, current_balance: 0,
      });
      toast.success("Cashbook created");
      setShowNewBook(false); setBookForm(emptyBook);
      await loadBooks(); setSelectedId(data.id);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const openDrawer = (type) => { setEntryForm({ ...emptyEntry, entry_person: user?.name || "" }); setDrawer(type); };

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
      await api.post(`/cashbooks/${selectedId}/entries`, { ...entryForm, cashbook_id: selectedId, amount, type: drawer });
      toast.success(drawer === "CASH_IN" ? "Cash in recorded" : "Cash out recorded");
      setDrawer(null);
      await Promise.all([loadBooks(), loadEntries(selectedId)]);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const removeEntry = async (entry) => {
    if (!window.confirm(`Delete this ${entry.type === "CASH_IN" ? "cash in" : "cash out"} entry of ${inrFull(entry.amount)}? This reverses the book balance.`)) return;
    try {
      await api.delete(`/cashbook-entries/${entry.id}`);
      toast.success("Entry deleted, balance reversed");
      await Promise.all([loadBooks(), loadEntries(selectedId)]);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const downloadReport = () => {
    const rows = [["Date", "Type", "Category", "Mode", "Amount", "Remark", "Entered By"]];
    entries.forEach((e) => rows.push([fmtDate(e.created_at), e.type, e.category, e.payment_mode, e.amount, e.remark, e.entry_person]));
    const csv = rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(book?.book_name || "cashbook").replace(/\s+/g, "_")}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <Topbar title="Petty Cash & Cashbooks" subtitle={book ? book.book_name : "Select a book"}
        actions={<button onClick={downloadReport} disabled={!entries.length} className="btn-ghost disabled:opacity-50"><Download size={14} /> Download Report (CSV)</button>} />
      <div className="p-6 space-y-6" data-testid="cashbook-page">
        <div className="flex flex-wrap items-center gap-2">
          {books.map((b) => (
            <button key={b.id} onClick={() => setSelectedId(b.id)} data-testid={`cashbook-tab-${b.id}`}
              className={`px-3 py-2 rounded-lg text-sm font-medium border ${selectedId === b.id ? "bg-[var(--brand-soft)] border-[var(--brand)] text-[var(--brand)]" : "bg-[var(--surface)] border-[var(--border)] text-[var(--ink-2)]"}`}>
              <Wallet size={13} className="inline mr-1.5 -mt-0.5" />{b.book_name} · {inrFull(b.current_balance)}
            </button>
          ))}
          <button onClick={() => setShowNewBook(true)} className="btn-ghost" data-testid="new-cashbook"><Plus size={14} /> New Book</button>
        </div>

        {book && (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              <KpiCard label="Total In" value={inrFull(totals.totalIn)} accent="moss" icon={ArrowDownCircle} />
              <KpiCard label="Total Out" value={inrFull(totals.totalOut)} accent="danger" icon={ArrowUpCircle} />
              <KpiCard label="Balance" value={inrFull(book.current_balance)} icon={Wallet} />
            </div>

            <div className="flex gap-2">
              <button onClick={() => openDrawer("CASH_IN")} className="btn-primary flex-1 justify-center" data-testid="cash-in-btn">
                <ArrowDownCircle size={15} /> Cash In
              </button>
              <button onClick={() => openDrawer("CASH_OUT")} className="btn-ghost flex-1 justify-center !border-[var(--danger)] !text-[var(--danger)]" data-testid="cash-out-btn">
                <ArrowUpCircle size={15} /> Cash Out
              </button>
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
                      <th className="text-right font-semibold px-4 py-2.5">Amount</th>
                      <th className="px-4 py-2.5" />
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((e) => (
                      <tr key={e.id} className="border-t border-[var(--border-light)]" data-testid={`entry-${e.id}`}>
                        <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(e.created_at)}</td>
                        <td className="px-4 py-3">{e.category || "—"}</td>
                        <td className="px-4 py-3 text-[var(--ink-2)]">{e.payment_mode}</td>
                        <td className="px-4 py-3 text-[var(--ink-2)] max-w-[220px] truncate">{e.remark || "—"}</td>
                        <td className="px-4 py-3 text-[var(--ink-2)]">{e.entry_person || "—"}</td>
                        <td className={`px-4 py-3 text-right font-mono font-semibold ${e.type === "CASH_IN" ? "text-[var(--moss)]" : "text-[var(--danger)]"}`}>
                          {e.type === "CASH_IN" ? "+" : "-"}{inrFull(e.amount)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button onClick={() => removeEntry(e)} className="p-1 rounded hover:bg-[var(--surface-hover)] text-[var(--ink-3)]"><Trash2 size={13} /></button>
                        </td>
                      </tr>
                    ))}
                    {entries.length === 0 && (
                      <tr><td colSpan={7} className="py-8 text-center text-[var(--ink-3)]">No entries yet in this book.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
        {!book && books.length === 0 && (
          <div className="text-sm text-[var(--ink-3)] py-8 text-center">No cashbooks yet — create one to start tracking petty cash.</div>
        )}
      </div>

      {showNewBook && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40" onClick={() => setShowNewBook(false)}>
          <div className="bg-white rounded-xl w-full max-w-sm p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading font-semibold">New Cashbook</h3>
              <button onClick={() => setShowNewBook(false)}><X size={16} /></button>
            </div>
            <div className="space-y-3">
              <Field label="Book Name *" value={bookForm.book_name} onChange={(v) => setBookForm({ ...bookForm, book_name: v })} />
              <Field label="Description" value={bookForm.description} onChange={(v) => setBookForm({ ...bookForm, description: v })} />
              <Field label="Opening Balance" type="number" value={bookForm.initial_balance} onChange={(v) => setBookForm({ ...bookForm, initial_balance: v })} />
            </div>
            <button onClick={createBook} disabled={saving} className="btn-primary w-full justify-center mt-4 disabled:opacity-60">
              {saving ? "Creating…" : "Create Book"}
            </button>
          </div>
        </div>
      )}

      {drawer && (
        <div className="fixed inset-0 z-[70] flex justify-end">
          <div className="flex-1 bg-black/40" onClick={() => setDrawer(null)} />
          <div className="w-full max-w-sm bg-white h-full overflow-y-auto p-5" data-testid="entry-drawer">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading font-semibold">{drawer === "CASH_IN" ? "Cash In" : "Cash Out"}</h3>
              <button onClick={() => setDrawer(null)}><X size={16} /></button>
            </div>
            <div className="space-y-3">
              <Field label="Amount *" type="number" value={entryForm.amount} onChange={(v) => setEntryForm({ ...entryForm, amount: v })} />
              <SelectField label="Category" value={entryForm.category} options={CATEGORIES}
                onChange={(v) => setEntryForm({ ...entryForm, category: v })} />
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
              <Field label="Remark" value={entryForm.remark} onChange={(v) => setEntryForm({ ...entryForm, remark: v })} />
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">Receipt (optional)</label>
                <input type="file" accept="image/*" onChange={(e) => uploadReceipt(e.target.files?.[0])} className="text-xs" />
                {uploading && <div className="text-xs text-[var(--ink-3)] mt-1">Processing…</div>}
                {entryForm.receipt_url && <img src={entryForm.receipt_url} alt="Receipt" className="mt-2 h-20 rounded-lg border border-[var(--border)]" />}
              </div>
            </div>
            <button onClick={saveEntry} disabled={saving}
              className={`w-full justify-center mt-5 ${drawer === "CASH_IN" ? "btn-primary" : "btn-ghost !border-[var(--danger)] !text-[var(--danger)]"} disabled:opacity-60`}
              data-testid="save-entry">
              {saving ? "Saving…" : drawer === "CASH_IN" ? "Record Cash In" : "Record Cash Out"}
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
