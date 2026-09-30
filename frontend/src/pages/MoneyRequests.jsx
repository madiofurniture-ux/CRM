import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import Topbar from "@/components/Topbar";
import SearchSelect from "@/components/SearchSelect";
import EmptyState from "@/components/EmptyState";
import ErrorState from "@/components/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiError } from "@/lib/api";
import { inrFull, fmtDate, fmtDateTime, todayIST, isoDateIST } from "@/lib/format";
import { shrinkImage } from "@/lib/image";
import { toast } from "sonner";
import {
  X, Plus, Receipt, CheckCircle2, Clock, XCircle, ArrowUpRight, ZoomIn, ZoomOut,
  Settings2, Camera, Ban, Pencil, Send,
} from "lucide-react";

/**
 * Money requests: expense claims and advances, approved by the raiser's
 * reporting manager (then finance above the policy limit) and paid out of a
 * Cashbook wallet with the UTR recorded. Every request can be tied to a
 * project, sales order or quotation, so the spend lands in that deal's P&L.
 * /approvals opens the same screen filtered to what is waiting on you.
 */
const TABS = [
  { key: "", label: "All" },
  { key: "Pending review", label: "Pending review" },
  { key: "Pending transfer", label: "Pending transfer" },
  { key: "Transferred", label: "Transferred" },
  { key: "Rejected", label: "Rejected" },
];
const STATUS_TONE = {
  "Pending review": "bg-[var(--warn-soft)] text-[var(--color-warning)]",
  "Pending transfer": "bg-[var(--color-primary-soft)] text-[var(--color-primary)]",
  Transferred: "bg-[var(--moss-soft)] text-[var(--color-success)]",
  Rejected: "bg-[var(--danger-soft)] text-[var(--color-danger)]",
  Cancelled: "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]",
};
const DURATIONS = [["all", "All time"], ["month", "This month"], ["30", "Last 30 days"], ["fy", "This FY"]];
const MODES = [["UPI", "UPI"], ["BANK_TRANSFER", "Bank transfer"], ["OTHER", "Cash / direct"]];
const LINK_TYPES = [["", "Not linked (overhead)"], ["project_id", "Project"], ["sale_id", "Sales order"], ["quote_id", "Quotation"]];

const fieldBase = "px-2.5 py-2 rounded-[var(--radius-sm)] border border-[var(--color-border-strong,var(--color-border))] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)]";
const field = `${fieldBase} w-full`;
const labelCls = "block text-xs font-medium text-[var(--color-text-muted)] mb-1";

function durationRange(k) {
  const today = todayIST();
  if (k === "month") return [`${today.slice(0, 7)}-01`, today];
  if (k === "30") { const d = new Date(); d.setDate(d.getDate() - 29); return [isoDateIST(d), today]; }
  if (k === "fy") { const [y, m] = today.split("-").map(Number); return [`${m >= 4 ? y : y - 1}-04-01`, today]; }
  return ["", ""];
}

const StatusPill = ({ status }) => (
  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${STATUS_TONE[status] || ""}`}>{status}</span>
);

export default function MoneyRequests() {
  const location = useLocation();
  const nav = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const approvalsView = location.pathname.startsWith("/approvals");

  const [tab, setTab] = useState("");
  const [assigned, setAssigned] = useState(approvalsView);
  const [duration, setDuration] = useState("all");
  const [member, setMember] = useState("");
  const [category, setCategory] = useState("");
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [editing, setEditing] = useState(null);      // null | {} (new) | request (edit)
  const [showPolicy, setShowPolicy] = useState(false);

  useEffect(() => { setAssigned(approvalsView); }, [approvalsView]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [start, end] = durationRange(duration);
    const q = new URLSearchParams();
    if (tab) q.set("status", tab);
    if (assigned) q.set("assigned", "true");
    if (member) q.set("raised_by_id", member);
    if (category) q.set("category", category);
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    try {
      const [{ data }, { data: s }] = await Promise.all([
        api.get(`/money-requests?${q.toString()}`, { skipCache: true }),
        api.get("/money-requests/summary", { skipCache: true }),
      ]);
      setRows(data);
      setSummary(s);
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, [tab, assigned, member, category, duration]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get("/finance/expense-policy").then(({ data }) => setPolicy(data)).catch(() => {}); }, []);

  const members = useMemo(() => {
    const m = new Map();
    rows.forEach((r) => r.raised_by_id && m.set(r.raised_by_id, r.raised_by));
    return [...m.entries()];
  }, [rows]);

  const open = rows.find((r) => r.id === openId) || null;
  const replace = (r) => setRows((p) => p.map((x) => (x.id === r.id ? r : x)));
  const actionable = rows.filter((r) => r.can_decide || r.can_transfer);
  const reviewNext = () => {
    const next = actionable.find((r) => r.id !== openId);
    if (next) setOpenId(next.id); else { setOpenId(null); toast.success("Nothing else is waiting on you"); }
  };

  return (
    <>
      <Topbar
        title={approvalsView ? "Approvals" : "Money Requests"}
        subtitle={approvalsView ? "Money requests waiting on you" : "Expense claims and advances, approved and paid from wallets"}
        onAdd={() => setEditing({})}
        addLabel="New request"
      />
      <div className="p-4 md:p-6 space-y-4" data-testid="money-requests-page">
        <div className="flex flex-wrap items-end gap-2 border-b border-[var(--color-border)]">
          <div role="tablist" aria-label="Request status" className="flex gap-1 overflow-x-auto">
            {TABS.map((t) => {
              const n = t.key ? summary?.counts?.[t.key] : summary?.total;
              return (
                <button key={t.label} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                        className={`px-3 py-2 text-sm whitespace-nowrap -mb-px border-b-2 ${tab === t.key
                          ? "border-[var(--color-primary)] text-[var(--color-primary)] font-semibold"
                          : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"}`}>
                  {t.label}{n != null && <span className="ml-1.5 text-xs opacity-80">{n}</span>}
                </button>
              );
            })}
          </div>
          <div className="ml-auto flex items-center gap-2 pb-1.5">
            {isAdmin && (
              <button type="button" className="btn-ghost text-sm" onClick={() => setShowPolicy(true)}>
                <Settings2 size={14} /> Policy
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2" data-testid="mr-filters">
          <button type="button" aria-pressed={assigned} onClick={() => setAssigned((v) => !v)}
                  className={`px-3 py-1.5 rounded-full text-sm border ${assigned
                    ? "bg-[var(--color-primary)] border-[var(--color-primary)] text-white"
                    : "border-[var(--color-border-strong,var(--color-border))] bg-[var(--color-surface)]"}`}>
            Assigned to you{summary?.assigned_to_me ? ` · ${summary.assigned_to_me}` : ""}
          </button>
          <select className={`${fieldBase} w-auto`} aria-label="Duration" value={duration} onChange={(e) => setDuration(e.target.value)}>
            {DURATIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <select className={`${fieldBase} w-auto`} aria-label="Raised by" value={member} onChange={(e) => setMember(e.target.value)}>
            <option value="">Everyone</option>
            {members.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
          <select className={`${fieldBase} w-auto`} aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {(policy?.categories || []).map((c) => <option key={c}>{c}</option>)}
          </select>
          {tab === "Pending transfer" && summary && (
            <span className="text-sm text-[var(--color-text-muted)] ml-auto">
              {inrFull(summary.amounts?.["Pending transfer"])} to pay out
            </span>
          )}
        </div>

        {error ? (
          <ErrorState hint={error} onRetry={load} />
        ) : loading && !rows.length ? (
          <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14 w-full" />)}</div>
        ) : !rows.length ? (
          <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)]">
            <EmptyState icon={Receipt}
                        title={assigned ? "Nothing is waiting on you" : "No money requests here"}
                        hint={assigned ? "Requests you need to approve or pay will appear here." : "Raise one with New request: add the amount, a receipt photo and what it's for."} />
          </div>
        ) : (
          <div className={`rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] overflow-x-auto ${loading ? "opacity-60" : ""}`}>
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Request</th>
                  <th className="px-4 py-2.5 font-medium hidden md:table-cell">Raised by</th>
                  <th className="px-4 py-2.5 font-medium hidden sm:table-cell">Date</th>
                  <th className="px-4 py-2.5 font-medium hidden lg:table-cell">Category</th>
                  <th className="px-4 py-2.5 font-medium hidden lg:table-cell">For</th>
                  <th className="px-4 py-2.5 font-medium text-right">Amount</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} onClick={() => setOpenId(r.id)} data-testid={`mr-row-${r.id}`}
                      className={`border-b border-[var(--color-border)] last:border-0 cursor-pointer hover:bg-[var(--surface-hover)] ${openId === r.id ? "bg-[var(--color-primary-soft)]" : ""}`}>
                    <td className="px-4 py-2.5">
                      <button type="button" className="text-left font-medium text-[var(--color-text)] hover:underline"
                              onClick={(e) => { e.stopPropagation(); setOpenId(r.id); }}>
                        {r.title}
                      </button>
                      <div className="text-xs text-[var(--color-text-muted)]">{r.request_no}</div>
                    </td>
                    <td className="px-4 py-2.5 hidden md:table-cell">{r.raised_by}</td>
                    <td className="px-4 py-2.5 hidden sm:table-cell whitespace-nowrap text-[var(--color-text-muted)]">{fmtDate(r.date)}</td>
                    <td className="px-4 py-2.5 hidden lg:table-cell">{r.category}</td>
                    <td className="px-4 py-2.5 hidden lg:table-cell text-[var(--color-text-muted)]">{r.link_label || "Overhead"}</td>
                    <td className="px-4 py-2.5 text-right font-medium tabular-nums whitespace-nowrap">{inrFull(r.amount)}</td>
                    <td className="px-4 py-2.5">
                      <StatusPill status={r.status} />
                      {(r.can_decide || r.can_transfer) && <div className="text-[11px] text-[var(--color-primary)] mt-0.5">Needs you</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {open && (
        <RequestDrawer
          req={open} onClose={() => setOpenId(null)} onChanged={(r) => { replace(r); api.get("/money-requests/summary", { skipCache: true }).then(({ data }) => setSummary(data)).catch(() => {}); }}
          onEdit={() => setEditing(open)} onReviewNext={actionable.length ? reviewNext : null}
          onOpenDeal={(r) => nav(`/finance/pnl?${new URLSearchParams(r.project_id ? { project_id: r.project_id } : r.sale_id ? { sale_id: r.sale_id } : { quote_id: r.quote_id })}`)}
        />
      )}
      {editing && (
        <RequestForm initial={editing} policy={policy} onClose={() => setEditing(null)}
                     onSaved={(r) => { setEditing(null); setOpenId(r.id); load(); }} />
      )}
      {showPolicy && policy && (
        <PolicyForm policy={policy} onClose={() => setShowPolicy(false)} onSaved={(p) => { setPolicy(p); setShowPolicy(false); }} />
      )}
    </>
  );
}

// ── detail drawer ───────────────────────────────────────────────────────────
function RequestDrawer({ req, onClose, onChanged, onEdit, onReviewNext, onOpenDeal }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [wallets, setWallets] = useState([]);
  const [transfer, setTransfer] = useState({ cashbook_id: "", payment_mode: "UPI", utr: "", date: todayIST() });

  useEffect(() => { setNote(""); setZoom(1); }, [req.id]);
  useEffect(() => {
    if (!req.can_transfer) return;
    api.get("/cashbooks", { skipCache: true })
      .then(({ data }) => {
        const active = data.filter((w) => w.status === "ACTIVE");
        setWallets(active);
        setTransfer((t) => ({ ...t, cashbook_id: t.cashbook_id || active[0]?.id || "" }));
      })
      .catch(() => setWallets([]));
  }, [req.can_transfer, req.id]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const act = async (path, body, done) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/money-requests/${req.id}/${path}`, body);
      onChanged(data);
      toast.success(done);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const wait = req.waiting_on;
  const linked = req.project_id || req.sale_id || req.quote_id;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <aside role="dialog" aria-modal="true" aria-label="Request details" onClick={(e) => e.stopPropagation()}
             className="h-full w-full max-w-[42rem] bg-[var(--color-surface)] shadow-2xl flex flex-col" data-testid="mr-drawer">
        <header className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
          <h2 className="font-heading font-semibold text-lg">Request details</h2>
          <button type="button" aria-label="Close" onClick={onClose} className="p-1.5 rounded hover:bg-[var(--color-surface-muted)]"><X size={18} /></button>
        </header>

        <div className="flex-1 overflow-y-auto grid md:grid-cols-[1fr_15rem]">
          <div className="p-5 space-y-5 min-w-0">
            <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] p-4 flex items-center justify-between gap-3">
              <div>
                <div className="text-2xl font-heading font-bold">{inrFull(req.amount)}</div>
                <div className="text-sm text-[var(--color-text-muted)]">{req.title} · {req.request_no}</div>
              </div>
              <StatusPill status={req.status} />
            </div>

            <section>
              <h3 className="font-semibold mb-2">Approval log</h3>
              <ol className="space-y-2.5">
                {(req.log || []).map((l, i) => (
                  <li key={i} className="flex gap-2.5 text-sm">
                    {l.action === "rejected" || l.action === "cancelled"
                      ? <XCircle size={16} className="text-[var(--color-danger)] mt-0.5 shrink-0" aria-hidden />
                      : <CheckCircle2 size={16} className="text-[var(--color-success)] mt-0.5 shrink-0" aria-hidden />}
                    <div>
                      <div>{l.text}{l.action !== "raised" && l.by ? ` · ${l.by}` : ""}</div>
                      <div className="text-xs text-[var(--color-text-muted)]">{fmtDateTime(l.at)}</div>
                    </div>
                  </li>
                ))}
                {wait && (
                  <li className="flex gap-2.5 text-sm text-[var(--color-text-muted)]">
                    <Clock size={16} className="mt-0.5 shrink-0" aria-hidden />
                    Approval pending by {wait.label}{wait.level === "manager" ? `: ${wait.approver_name}` : ""}
                  </li>
                )}
                {req.status === "Pending transfer" && (
                  <li className="flex gap-2.5 text-sm text-[var(--color-text-muted)]">
                    <Clock size={16} className="mt-0.5 shrink-0" aria-hidden /> Waiting for finance to transfer the money
                  </li>
                )}
              </ol>
            </section>

            <section className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <Detail label="Category" value={req.category} />
              <Detail label="Spend date" value={fmtDate(req.date)} />
              <Detail label="Raised by" value={req.raised_by} />
              <Detail label="Pay to" value={[req.payee_name, req.payee_upi].filter(Boolean).join(" · ")} />
              <div className="col-span-2">
                <div className={labelCls}>For</div>
                {linked ? (
                  <button type="button" onClick={() => onOpenDeal(req)} className="inline-flex items-center gap-1 text-[var(--color-primary)] hover:underline">
                    {req.link_label || "Linked deal"} <ArrowUpRight size={13} />
                  </button>
                ) : <span>Overhead (not linked to a deal)</span>}
              </div>
              {req.description && <div className="col-span-2"><div className={labelCls}>Notes</div><p className="whitespace-pre-line">{req.description}</p></div>}
              {req.transfer?.at && (
                <div className="col-span-2 rounded-[var(--radius-sm)] bg-[var(--moss-soft)] p-3">
                  Paid from <b>{req.transfer.cashbook_name}</b> on {fmtDate(req.transfer.date)} by {req.transfer.by}
                  {req.transfer.utr ? <> · UTR <span className="tabular-nums">{req.transfer.utr}</span></> : " · direct settlement"}
                </div>
              )}
            </section>

            {req.can_decide && (
              <section className="space-y-2 border-t border-[var(--color-border)] pt-4">
                <label className={labelCls} htmlFor="mr-note">Note (required to reject)</label>
                <textarea id="mr-note" rows={2} className={field} value={note} onChange={(e) => setNote(e.target.value)}
                          placeholder="e.g. Approved, keep the original bill" />
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="btn-primary" disabled={busy} data-testid="mr-approve"
                          onClick={() => act("approve", { note }, "Approved")}>
                    <CheckCircle2 size={14} /> Approve
                  </button>
                  <button type="button" disabled={busy} data-testid="mr-reject"
                          onClick={() => (note.trim() ? act("reject", { note }, "Rejected") : toast.error("Add a note saying why you're rejecting it"))}
                          className="inline-flex items-center gap-2 px-4 py-2 rounded-[var(--radius-md)] text-sm font-semibold bg-[var(--color-danger)] text-white disabled:opacity-50">
                    <XCircle size={14} /> Reject
                  </button>
                </div>
              </section>
            )}

            {req.can_transfer && (
              <section className="space-y-3 border-t border-[var(--color-border)] pt-4" data-testid="mr-transfer">
                <h3 className="font-semibold">Record the transfer</h3>
                <p className="text-xs text-[var(--color-text-muted)]">Pay {req.payee_name || req.raised_by}{req.payee_upi ? ` (${req.payee_upi})` : ""} from your bank or UPI app, then record it here.</p>
                <div className="grid sm:grid-cols-2 gap-3">
                  <div>
                    <label className={labelCls} htmlFor="mr-wallet">Paid from wallet</label>
                    <select id="mr-wallet" className={field} value={transfer.cashbook_id} onChange={(e) => setTransfer({ ...transfer, cashbook_id: e.target.value })}>
                      {!wallets.length && <option value="">No active wallet: create one under Cashbooks</option>}
                      {wallets.map((w) => <option key={w.id} value={w.id}>{w.book_name}{w.current_balance != null ? ` · ${inrFull(w.current_balance)}` : ""}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={labelCls} htmlFor="mr-mode">Mode</label>
                    <select id="mr-mode" className={field} value={transfer.payment_mode} onChange={(e) => setTransfer({ ...transfer, payment_mode: e.target.value })}>
                      {MODES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={labelCls} htmlFor="mr-utr">UTR / UPI reference{transfer.payment_mode === "OTHER" ? " (optional)" : ""}</label>
                    <input id="mr-utr" className={field} value={transfer.utr} onChange={(e) => setTransfer({ ...transfer, utr: e.target.value })} placeholder="e.g. 618348670368" />
                  </div>
                  <div>
                    <label className={labelCls} htmlFor="mr-date">Paid on</label>
                    <input id="mr-date" type="date" className={field} value={transfer.date} onChange={(e) => setTransfer({ ...transfer, date: e.target.value })} />
                  </div>
                </div>
                <button type="button" className="btn-primary" disabled={busy || !transfer.cashbook_id} data-testid="mr-transfer-save"
                        onClick={() => act("transfer", transfer, "Transfer recorded")}>
                  <Send size={14} /> Mark as transferred
                </button>
              </section>
            )}
          </div>

          <div className="p-5 md:border-l border-[var(--color-border)] bg-[var(--color-surface-muted)]">
            <h3 className="font-semibold mb-2">Receipt</h3>
            {req.receipt_url ? (
              <>
                <div className="overflow-auto rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-black/80 max-h-[26rem]">
                  <img src={req.receipt_url} alt={`Receipt for ${req.title}`} style={{ width: `${zoom * 100}%`, maxWidth: "none" }} />
                </div>
                <div className="flex items-center justify-center gap-2 mt-2 text-sm">
                  <button type="button" aria-label="Zoom out" className="p-1.5 rounded border border-[var(--color-border)] bg-[var(--color-surface)]" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}><ZoomOut size={14} /></button>
                  <span className="tabular-nums w-12 text-center">{Math.round(zoom * 100)}%</span>
                  <button type="button" aria-label="Zoom in" className="p-1.5 rounded border border-[var(--color-border)] bg-[var(--color-surface)]" onClick={() => setZoom((z) => Math.min(3, z + 0.25))}><ZoomIn size={14} /></button>
                </div>
              </>
            ) : <p className="text-sm text-[var(--color-text-muted)]">No receipt attached.</p>}
          </div>
        </div>

        <footer className="px-5 py-3 border-t border-[var(--color-border)] flex flex-wrap items-center gap-2">
          {req.can_cancel && (
            <>
              <button type="button" className="btn-ghost text-sm" onClick={onEdit}><Pencil size={14} /> Edit</button>
              <button type="button" className="btn-ghost text-sm" disabled={busy}
                      onClick={() => window.confirm("Cancel this request?") && act("cancel", {}, "Request cancelled")}>
                <Ban size={14} /> Cancel request
              </button>
            </>
          )}
          {onReviewNext && (
            <button type="button" className="btn-primary ml-auto" onClick={onReviewNext} data-testid="mr-next">
              Review next request
            </button>
          )}
        </footer>
      </aside>
    </div>
  );
}

const Detail = ({ label, value }) => (
  <div><div className={labelCls}>{label}</div><div>{value || "—"}</div></div>
);

// ── new / edit request ─────────────────────────────────────────────────────
function RequestForm({ initial, policy, onClose, onSaved }) {
  const isEdit = !!initial.id;
  const linkType = initial.project_id ? "project_id" : initial.sale_id ? "sale_id" : initial.quote_id ? "quote_id" : "";
  const [form, setForm] = useState({
    title: initial.title || "", amount: initial.amount || "", category: initial.category || "",
    date: initial.date || todayIST(), description: initial.description || "", receipt_url: initial.receipt_url || "",
    payee_name: initial.payee_name || "", payee_upi: initial.payee_upi || "",
  });
  const [link, setLink] = useState({ type: linkType, id: linkType ? initial[linkType] : "" });
  const [options, setOptions] = useState({ project_id: [], sale_id: [], quote_id: [] });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const load = async (path, key, map) => {
      try {
        const { data } = await api.get(path);
        setOptions((o) => ({ ...o, [key]: data.map(map) }));
      } catch { /* no access to that list: leave it empty */ }
    };
    load("/projects", "project_id", (p) => ({ id: p.id, label: `${p.customer || "Project"} · ${p.project_no || ""}`, sub: p.stage }));
    load("/sales", "sale_id", (s) => ({ id: s.id, label: `${s.customer || "Sale"} · ${s.sale_no || ""}`, sub: s.division }));
    load("/quotes", "quote_id", (q) => ({ id: q.id, label: `${q.customer || "Quotation"} · ${q.quote_no || ""}`, sub: q.stage }));
  }, []);

  const pickReceipt = async (file) => {
    if (!file) return;
    try {
      const url = await shrinkImage(file, 1400, 0.75);
      setForm((f) => ({ ...f, receipt_url: url }));
    } catch (e) {
      toast.error(e.message || "Couldn't read that photo");
    }
  };

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    const body = { ...form, amount: Number(form.amount), project_id: "", sale_id: "", quote_id: "" };
    if (link.type && link.id) body[link.type] = link.id;
    try {
      const { data } = isEdit
        ? await api.put(`/money-requests/${initial.id}`, body)
        : await api.post("/money-requests", body);
      toast.success(isEdit ? "Request updated" : "Request raised");
      onSaved(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const needsReceipt = Number(form.amount || 0) >= Number(policy?.receipt_required_above || 0);

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 sm:p-4" onClick={onClose}>
      <form onSubmit={save} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={isEdit ? "Edit request" : "New money request"}
            className="w-full max-w-xl max-h-[92vh] overflow-y-auto rounded-t-2xl sm:rounded-[var(--radius-lg)] bg-[var(--color-surface)] shadow-2xl" data-testid="mr-form">
        <header className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
          <h2 className="font-heading font-semibold text-lg">{isEdit ? "Edit request" : "New money request"}</h2>
          <button type="button" aria-label="Close" onClick={onClose} className="p-1.5 rounded hover:bg-[var(--color-surface-muted)]"><X size={18} /></button>
        </header>
        <div className="p-5 grid sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className={labelCls} htmlFor="mrf-title">What is it for?</label>
            <input id="mrf-title" className={field} required value={form.title} placeholder="e.g. Mobile recharge, site transport, hardware"
                   onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="mrf-title" />
          </div>
          <div>
            <label className={labelCls} htmlFor="mrf-amount">Amount (₹)</label>
            <input id="mrf-amount" className={field} required type="number" min="1" step="0.01" inputMode="decimal" value={form.amount}
                   onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="mrf-amount" />
          </div>
          <div>
            <label className={labelCls} htmlFor="mrf-category">Category</label>
            <select id="mrf-category" className={field} required value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} data-testid="mrf-category">
              <option value="" disabled>Choose…</option>
              {(policy?.categories || []).map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="mrf-date">Spend date</label>
            <input id="mrf-date" type="date" className={field} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </div>
          <div>
            <label className={labelCls} htmlFor="mrf-link">Linked to</label>
            <select id="mrf-link" className={field} value={link.type} onChange={(e) => setLink({ type: e.target.value, id: "" })}>
              {LINK_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          {link.type && (
            <div className="sm:col-span-2">
              <label className={labelCls}>Which {LINK_TYPES.find(([k]) => k === link.type)[1].toLowerCase()}?</label>
              <SearchSelect options={options[link.type]} value={link.id} onChange={(id) => setLink((l) => ({ ...l, id }))}
                            placeholder="Search by customer or number" testId="mrf-link-picker" />
              <p className="text-xs text-[var(--color-text-muted)] mt-1">The spend is added to this deal's P&L, including its project and quotation.</p>
            </div>
          )}
          <div>
            <label className={labelCls} htmlFor="mrf-payee">Pay to</label>
            <input id="mrf-payee" className={field} value={form.payee_name} placeholder="You, if left blank" onChange={(e) => setForm({ ...form, payee_name: e.target.value })} />
          </div>
          <div>
            <label className={labelCls} htmlFor="mrf-upi">Their UPI ID</label>
            <input id="mrf-upi" className={field} value={form.payee_upi} placeholder="name@okhdfcbank" onChange={(e) => setForm({ ...form, payee_upi: e.target.value })} />
          </div>
          <div className="sm:col-span-2">
            <label className={labelCls} htmlFor="mrf-notes">Notes</label>
            <textarea id="mrf-notes" rows={2} className={field} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="sm:col-span-2">
            <span className={labelCls}>Receipt photo{needsReceipt ? " (required)" : " (optional)"}</span>
            <div className="flex items-center gap-3">
              <label className="btn-ghost text-sm cursor-pointer">
                <Camera size={14} /> {form.receipt_url ? "Replace photo" : "Add photo"}
                <input type="file" accept="image/*" capture="environment" className="sr-only" data-testid="mrf-receipt"
                       onChange={(e) => pickReceipt(e.target.files?.[0])} />
              </label>
              {form.receipt_url && (
                <>
                  <img src={form.receipt_url} alt="Receipt preview" className="h-14 w-14 object-cover rounded border border-[var(--color-border)]" />
                  <button type="button" className="text-sm text-[var(--color-danger)]" onClick={() => setForm({ ...form, receipt_url: "" })}>Remove</button>
                </>
              )}
            </div>
          </div>
        </div>
        <footer className="px-5 py-3 border-t border-[var(--color-border)] flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={saving} data-testid="mrf-save">
            <Plus size={14} /> {saving ? "Saving…" : isEdit ? "Save changes" : "Raise request"}
          </button>
        </footer>
      </form>
    </div>
  );
}

function PolicyForm({ policy, onClose, onSaved }) {
  const [form, setForm] = useState({
    finance_threshold: policy.finance_threshold, receipt_required_above: policy.receipt_required_above,
    categories: (policy.categories || []).join("\n"),
  });
  const [saving, setSaving] = useState(false);
  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const { data } = await api.put("/finance/expense-policy", {
        finance_threshold: Number(form.finance_threshold), receipt_required_above: Number(form.receipt_required_above),
        categories: form.categories.split("\n").map((c) => c.trim()).filter(Boolean),
      });
      toast.success("Policy saved");
      onSaved(data);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <form onSubmit={save} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Expense policy"
            className="w-full max-w-md rounded-[var(--radius-lg)] bg-[var(--color-surface)] shadow-2xl">
        <header className="px-5 py-4 border-b border-[var(--color-border)] font-heading font-semibold text-lg">Expense policy</header>
        <div className="p-5 space-y-4">
          <div>
            <label className={labelCls} htmlFor="pol-fin">Finance approval needed from (₹)</label>
            <input id="pol-fin" type="number" min="0" className={field} value={form.finance_threshold} onChange={(e) => setForm({ ...form, finance_threshold: e.target.value })} />
            <p className="text-xs text-[var(--color-text-muted)] mt-1">Below this, the reporting manager's approval is enough.</p>
          </div>
          <div>
            <label className={labelCls} htmlFor="pol-rec">Receipt photo required from (₹)</label>
            <input id="pol-rec" type="number" min="0" className={field} value={form.receipt_required_above} onChange={(e) => setForm({ ...form, receipt_required_above: e.target.value })} />
          </div>
          <div>
            <label className={labelCls} htmlFor="pol-cat">Categories, one per line</label>
            <textarea id="pol-cat" rows={8} className={field} value={form.categories} onChange={(e) => setForm({ ...form, categories: e.target.value })} />
          </div>
        </div>
        <footer className="px-5 py-3 border-t border-[var(--color-border)] flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={saving}>{saving ? "Saving…" : "Save policy"}</button>
        </footer>
      </form>
    </div>
  );
}
