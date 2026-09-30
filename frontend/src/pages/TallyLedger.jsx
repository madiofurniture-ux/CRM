import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import EmptyState from "@/components/EmptyState";
import api, { formatApiError } from "@/lib/api";
import { inrFull } from "@/lib/format";
import { toast } from "sonner";
import {
  ArrowLeftRight, RefreshCw, CheckCircle2, AlertCircle, Loader2,
  Plus, X, ShieldCheck, Upload,
} from "lucide-react";

// Ledger suggestions for the from/to dropdowns. Free text is still allowed —
// these must match the ledger names in Tally exactly, and every deployment's
// chart of accounts differs, so this is a starting list rather than a
// constraint that would block a valid ledger.
const MONEY_LEDGERS = ["Cash-in-Hand", "Petty Cash", "HDFC Bank", "ICICI Bank", "UPI Suspense"];
const PARTY_LEDGERS = [
  "Sundry Debtors", "Sundry Creditors", "Timber Vendor", "Hardware Vendor",
  "Transport Charges", "Site Expenses", "Salaries Payable", "Fuel & Travel",
];
const ALL_LEDGERS = [...MONEY_LEDGERS, ...PARTY_LEDGERS];

const TABS = [
  { id: "review", label: "Needs Review (UPI)" },
  { id: "ready", label: "Ready to Sync" },
  { id: "synced", label: "Synced" },
];

const emptyForm = {
  date: new Date().toISOString().slice(0, 10),
  type: "OUT", payment_mode: "CASH", amount: "",
  from_ledger: "Cash-in-Hand", to_ledger: "", reference_no: "", narration: "",
};

export default function TallyLedger() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("review");
  const [show, setShow] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  // id -> "syncing" | "success" | "error", drives the per-row live indicator.
  const [syncState, setSyncState] = useState({});
  const [batching, setBatching] = useState(false);

  const load = () => {
    setLoading(true);
    api.get("/finance/cashbook")
      .then(({ data }) => setRows(data))
      .catch((e) => toast.error(formatApiError(e.response?.data?.detail)))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const visible = rows.filter((r) => {
    if (tab === "review") return r.needs_review && !r.tally_synced;
    if (tab === "ready") return !r.needs_review && !r.tally_synced;
    return r.tally_synced;
  });

  const counts = {
    review: rows.filter((r) => r.needs_review && !r.tally_synced).length,
    ready: rows.filter((r) => !r.needs_review && !r.tally_synced).length,
    synced: rows.filter((r) => r.tally_synced).length,
  };

  const save = async () => {
    if (saving) return;
    const amount = parseFloat(form.amount) || 0;
    if (amount <= 0) { toast.error("Enter an amount"); return; }
    if (!form.from_ledger || !form.to_ledger) { toast.error("Both ledgers are required"); return; }
    setSaving(true);
    try {
      await api.post("/finance/cashbook", { ...form, amount });
      toast.success("Transaction recorded");
      setShow(false);
      setForm(emptyForm);
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const review = async (row) => {
    try {
      await api.post(`/finance/cashbook/${row.id}/review`);
      toast.success("Marked reviewed — ready to sync");
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  const syncOne = async (row) => {
    setSyncState((s) => ({ ...s, [row.id]: "syncing" }));
    try {
      await api.post(`/finance/tally/sync/${row.id}`);
      setSyncState((s) => ({ ...s, [row.id]: "success" }));
      toast.success("Voucher posted to Tally");
      load();
    } catch (e) {
      setSyncState((s) => ({ ...s, [row.id]: "error" }));
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  const syncAll = async () => {
    if (batching) return;
    setBatching(true);
    try {
      const { data } = await api.post("/finance/tally/sync-batch");
      if (data.synced) toast.success(`${data.synced} voucher(s) posted to Tally`);
      if (data.failed) toast.error(`${data.failed} voucher(s) failed — see the error column`);
      if (!data.attempted) toast.info("Nothing is waiting to sync");
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setBatching(false);
    }
  };

  const SyncButton = ({ row }) => {
    const state = syncState[row.id];
    if (row.tally_synced) {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-1 rounded-md">
          <CheckCircle2 size={12} />
          Synced
        </span>
      );
    }
    if (row.needs_review) {
      return <span className="text-[11px] text-[var(--ink-3)]">Review first</span>;
    }
    return (
      <button
        onClick={() => syncOne(row)}
        disabled={state === "syncing"}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold transition ${
          state === "error"
            ? "bg-red-50 text-red-700 border border-red-200 hover:bg-red-100"
            : "bg-[var(--brand)] text-white hover:opacity-90 disabled:opacity-60"
        }`}
      >
        {state === "syncing" ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
        {state === "syncing" ? "Syncing…" : state === "error" ? "Retry" : "Sync to Tally"}
      </button>
    );
  };

  return (
    <>
      <Topbar title="Cashbook & Tally Sync" subtitle="UPI review queue, ledger mapping and Tally voucher dispatch" />

      <div className="p-6 space-y-6" data-testid="tally-ledger-page">
        {/* Tabs + actions */}
        <div className="bg-white border border-[var(--border)] rounded-2xl p-4 shadow-sm flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition ${
                  tab === t.id
                    ? "bg-[var(--brand)] text-white shadow-sm"
                    : "bg-[var(--surface-2)] text-[var(--ink-2)] hover:bg-[var(--border-light)]"
                }`}
              >
                {t.label}
                <span className="ml-1.5 opacity-70">{counts[t.id]}</span>
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={load}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)] text-xs font-semibold text-[var(--ink-2)] hover:bg-[var(--surface-2)] transition"
            >
              <RefreshCw size={13} />
              Refresh
            </button>
            <button
              onClick={syncAll}
              disabled={batching || !counts.ready}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--ink)] text-white text-xs font-semibold hover:bg-black transition disabled:opacity-40"
            >
              {batching ? <Loader2 size={13} className="animate-spin" /> : <ArrowLeftRight size={13} />}
              {batching ? "Syncing…" : `Sync All (${counts.ready})`}
            </button>
            <button
              onClick={() => setShow(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--brand)] text-white text-xs font-semibold hover:opacity-90 transition"
            >
              <Plus size={13} />
              New Entry
            </button>
          </div>
        </div>

        {/* Dense ledger table */}
        <div className="bg-white border border-[var(--border)] rounded-2xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] text-[11px] uppercase tracking-wider text-[var(--ink-3)] border-b border-[var(--border)]">
                <tr>
                  <th className="px-3 py-2.5 text-left font-semibold">Date</th>
                  <th className="px-3 py-2.5 text-left font-semibold">Type</th>
                  <th className="px-3 py-2.5 text-left font-semibold">Mode</th>
                  <th className="px-3 py-2.5 text-left font-semibold">From Ledger</th>
                  <th className="px-3 py-2.5 text-left font-semibold">To Ledger</th>
                  <th className="px-3 py-2.5 text-right font-semibold">Amount</th>
                  <th className="px-3 py-2.5 text-left font-semibold">Voucher</th>
                  <th className="px-3 py-2.5 text-left font-semibold">Ref</th>
                  <th className="px-3 py-2.5 text-left font-semibold">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-light)]">
                {visible.map((r) => (
                  <tr key={r.id} className="hover:bg-[var(--surface-2)]/50 transition">
                    <td className="px-3 py-2 font-mono text-xs text-[var(--ink-2)]">{r.date}</td>
                    <td className="px-3 py-2">
                      <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${
                        r.type === "IN" ? "bg-emerald-50 text-emerald-700" : "bg-orange-50 text-orange-700"
                      }`}>
                        {r.type}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-[var(--ink-2)]">{r.payment_mode}</td>
                    <td className="px-3 py-2 text-xs text-[var(--ink)]">{r.from_ledger}</td>
                    <td className="px-3 py-2 text-xs text-[var(--ink)]">{r.to_ledger}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs font-semibold text-[var(--ink)]">
                      {inrFull(r.amount)}
                    </td>
                    <td className="px-3 py-2 text-xs text-[var(--ink-2)]">{r.tally_voucher_type || "-"}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-[var(--ink-3)]">{r.reference_no || "-"}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        {r.needs_review && !r.tally_synced && (
                          <button
                            onClick={() => review(r)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-50 text-amber-700 border border-amber-200 text-[11px] font-semibold hover:bg-amber-100 transition"
                          >
                            <ShieldCheck size={12} />
                            Mark Reviewed
                          </button>
                        )}
                        <SyncButton row={r} />
                      </div>
                      {r.tally_error && !r.tally_synced && (
                        <div className="flex items-start gap-1 mt-1 text-[10px] text-red-600 max-w-xs">
                          <AlertCircle size={11} className="shrink-0 mt-0.5" />
                          <span className="truncate">{r.tally_error}</span>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
                {loading && (
                  <tr><td colSpan={9} className="text-center py-10 text-[var(--ink-3)] text-xs">Loading transactions…</td></tr>
                )}
                {!loading && !visible.length && (
                  <tr><td colSpan={9} className="py-10">
                    <EmptyState title="Nothing here" subtitle="No transactions in this queue yet." />
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* New entry */}
      {show && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="px-6 py-4 border-b border-[var(--border)] flex items-center justify-between">
              <h3 className="font-heading font-bold text-base text-[var(--ink)]">New Cashbook Transaction</h3>
              <button onClick={() => setShow(false)} className="text-[var(--ink-3)] hover:text-[var(--ink)]">
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Field label="Date">
                  <input type="date" value={form.date}
                    onChange={(e) => setForm({ ...form, date: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
                </Field>
                <Field label="Amount">
                  <input type="number" placeholder="0.00" value={form.amount}
                    onChange={(e) => setForm({ ...form, amount: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
                </Field>
                <Field label="Direction">
                  <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]">
                    <option value="OUT">OUT — money paid</option>
                    <option value="IN">IN — money received</option>
                  </select>
                </Field>
                <Field label="Payment Mode">
                  <select value={form.payment_mode}
                    onChange={(e) => setForm({ ...form, payment_mode: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]">
                    <option value="CASH">CASH</option>
                    <option value="UPI">UPI</option>
                    <option value="BANK_TRANSFER">BANK_TRANSFER</option>
                  </select>
                </Field>
                <Field label="From Ledger (credited)">
                  <LedgerSelect value={form.from_ledger}
                    onChange={(v) => setForm({ ...form, from_ledger: v })} />
                </Field>
                <Field label="To Ledger (debited)">
                  <LedgerSelect value={form.to_ledger}
                    onChange={(v) => setForm({ ...form, to_ledger: v })} />
                </Field>
              </div>

              <Field label="Reference No (UTR / UPI ref)">
                <input type="text" value={form.reference_no}
                  onChange={(e) => setForm({ ...form, reference_no: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
              </Field>
              <Field label="Narration">
                <input type="text" value={form.narration}
                  onChange={(e) => setForm({ ...form, narration: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]" />
              </Field>

              {form.payment_mode === "UPI" && (
                <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
                  UPI entries are parked for review and cannot be synced to Tally until a reviewer confirms the ledgers.
                </p>
              )}
            </div>

            <div className="px-6 py-4 border-t border-[var(--border)] flex justify-end gap-2">
              <button onClick={() => setShow(false)}
                className="px-4 py-2 rounded-xl border border-[var(--border)] text-xs font-semibold text-[var(--ink-2)] hover:bg-[var(--surface-2)]">
                Cancel
              </button>
              <button onClick={save} disabled={saving}
                className="px-4 py-2 rounded-xl bg-[var(--brand)] text-white text-xs font-semibold hover:opacity-90 disabled:opacity-60">
                {saving ? "Saving…" : "Save Transaction"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-[var(--ink-2)] mb-1">{label}</label>
      {children}
    </div>
  );
}

// A datalist rather than a hard <select>: the suggestions help, but a ledger
// name that isn't on the list must still be enterable or a valid Tally ledger
// becomes unusable in this app.
function LedgerSelect({ value, onChange }) {
  return (
    <>
      <input
        list="tally-ledgers"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Select or type a ledger"
        className="w-full px-3 py-2 text-sm rounded-xl border border-[var(--border)] outline-none focus:border-[var(--brand)]"
      />
      <datalist id="tally-ledgers">
        {ALL_LEDGERS.map((l) => <option key={l} value={l} />)}
      </datalist>
    </>
  );
}
