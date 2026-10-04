import { useCallback, useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { inrFull, fmtDate, amountInWords } from "@/lib/format";
import { toast } from "sonner";
import { ChevronDown, ChevronRight, Lock, Unlock, AlertTriangle, Printer, Settings2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import StatusBadge from "@/components/StatusBadge";
import PrimaryButton from "@/components/PrimaryButton";
import SecondaryButton from "@/components/SecondaryButton";
import ErrorState from "@/components/ErrorState";
import EmptyState from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";

// PAYROLL_STATUSES in backend/models_hr.py — this IS the full enum, no
// backend-supported status beyond these three.
const STATUS_TONE = { Draft: "warning", Approved: "primary", Paid: "success" };

function PayrollStatusBadge({ status }) {
  return <StatusBadge tone={STATUS_TONE[status] || "neutral"}>{status || "Draft"}</StatusBadge>;
}

function CalculatePayrollButton({ employees, onCalculated }) {
  const [employeeId, setEmployeeId] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [busy, setBusy] = useState(false);

  const calculate = async () => {
    if (!employeeId || !periodStart || !periodEnd) {
      toast.error("Pick an employee and both period dates");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/v1/payroll/calculate", {
        employee_id: employeeId, period_start: periodStart, period_end: periodEnd,
      });
      toast.success(`Payroll calculated: ${inrFull(data.net_salary)} net`);
      onCalculated();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-end gap-2 mb-4 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-3">
      <div>
        <label htmlFor="payroll-employee" className="block text-[11px] uppercase tracking-wide text-[var(--color-text-muted)] mb-1">Employee</label>
        <select id="payroll-employee" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}
          className="px-3 py-2 rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] border border-[var(--color-border)] text-sm min-w-[180px]">
          <option value="">Select…</option>
          {employees.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </select>
      </div>
      <div>
        <label htmlFor="payroll-period-start" className="block text-[11px] uppercase tracking-wide text-[var(--color-text-muted)] mb-1">Period start</label>
        <input id="payroll-period-start" type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)}
          className="px-3 py-2 rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] border border-[var(--color-border)] text-sm" />
      </div>
      <div>
        <label htmlFor="payroll-period-end" className="block text-[11px] uppercase tracking-wide text-[var(--color-text-muted)] mb-1">Period end</label>
        <input id="payroll-period-end" type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)}
          className="px-3 py-2 rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] border border-[var(--color-border)] text-sm" />
      </div>
      <PrimaryButton onClick={calculate} disabled={busy} data-testid="calculate-payroll-btn">
        {busy ? "Calculating…" : "Calculate Payroll"}
      </PrimaryButton>
    </div>
  );
}

// Attendance exceptions shown inline as a warning strip — never hidden,
// per the brief's "do not hide approval blockers." `override` only renders
// for a caller who already has payroll:approve (checked by the parent).
function ExceptionsBlock({ exceptions, canOverride, onApproveWithOverride, busy }) {
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  if (!exceptions?.length) return null;
  return (
    <div className="mt-2 p-3 rounded-[var(--radius-sm)] border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/10">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--color-warning)]">
        <AlertTriangle size={13} /> {exceptions.length} attendance exception{exceptions.length === 1 ? "" : "s"}
      </div>
      <ul className="mt-1 text-xs text-[var(--color-text-muted)] list-disc list-inside">
        {exceptions.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
        {exceptions.length > 5 && <li>+{exceptions.length - 5} more</li>}
      </ul>
      {canOverride && (
        confirming ? (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason for overriding (required)"
              aria-label="Override reason"
              className="px-2 py-1 text-xs rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] flex-1 min-w-[160px]"
            />
            <SecondaryButton
              disabled={busy || !reason.trim()}
              onClick={() => onApproveWithOverride(reason.trim())}
              className="text-xs py-1"
            >
              {busy ? "Approving…" : "Confirm override & approve"}
            </SecondaryButton>
            <button type="button" className="text-xs text-[var(--color-text-muted)] underline" onClick={() => setConfirming(false)}>Cancel</button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="mt-2 text-xs font-semibold text-[var(--color-primary)] underline"
          >
            Override and approve anyway
          </button>
        )
      )}
    </div>
  );
}

function AttendanceSummaryPanel({ periodId }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    api.get(`/v1/payroll/${periodId}/attendance-summary`)
      .then(({ data }) => { if (!cancelled) setSummary(data?.[0] || null); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [periodId]);

  if (loading) return <Skeleton className="h-16 w-full" />;
  if (error) return <div className="text-xs text-[var(--color-danger)]">Couldn't load the live attendance summary for this period.</div>;
  if (!summary) return <div className="text-xs text-[var(--color-text-muted)]">No attendance summary available.</div>;
  return (
    <div className="grid grid-cols-3 gap-3 text-xs">
      <div><div className="text-[var(--color-text-muted)] uppercase tracking-wide text-[10px]">Payable days</div><div className="font-mono font-semibold">{summary.payable_days}</div></div>
      <div><div className="text-[var(--color-text-muted)] uppercase tracking-wide text-[10px]">LOP days</div><div className="font-mono font-semibold">{summary.lop_days}</div></div>
      <div><div className="text-[var(--color-text-muted)] uppercase tracking-wide text-[10px]">OT hours</div><div className="font-mono font-semibold">{summary.overtime_hours}</div></div>
    </div>
  );
}

function PayrollRow({ r, employeesById, canApprove, onChanged, onPayslip }) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);

  const setStatus = async (status, overridePayload) => {
    setBusy(true);
    try {
      await api.post(`/v1/payroll/${r.id}/status`, { status, ...overridePayload });
      toast.success(`Payroll ${status.toLowerCase()}`);
      onChanged();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail && typeof detail === "object" && Array.isArray(detail.exceptions)) {
        // Handled by the ExceptionsBlock override flow — not a toast-worthy
        // surprise, it's the expected "blocked" response the UI already shows.
        return;
      }
      toast.error(formatApiError(detail) || "Couldn't update status");
    } finally {
      setBusy(false);
    }
  };

  const unlock = async () => {
    setBusy(true);
    try {
      await api.post(`/v1/payroll/${r.id}/unlock-attendance`, { reason: "" });
      toast.success("Attendance unlocked for re-import");
      onChanged();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Couldn't unlock attendance");
    } finally {
      setBusy(false);
    }
  };

  const exceptions = r.attendance_exceptions || [];

  return (
    <>
      <tr className="border-t border-[var(--color-border)]" data-testid={`payroll-row-${r.id}`}>
        <td className="px-4 py-3">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse row" : "Expand row"}
            className="p-0.5 -ml-1 mr-1 rounded hover:bg-[var(--color-surface-muted)] align-middle"
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
          <span className="font-medium">{employeesById[r.employee_id] || r.employee_id}</span>
        </td>
        <td className="px-4 py-3 whitespace-nowrap">{fmtDate(r.period_start)} – {fmtDate(r.period_end)}</td>
        <td className="px-4 py-3 text-right font-mono">{inrFull(r.gross_pay || 0)}</td>
        <td className="px-4 py-3 text-right font-mono">{r.payable_days ?? "—"}</td>
        <td className="px-4 py-3 text-right font-mono">{r.lop_days ?? "—"}</td>
        <td className="px-4 py-3 text-right font-mono">{r.overtime_hours ?? "—"}</td>
        <td className="px-4 py-3 text-right font-mono">{inrFull(r.lop_deduction || 0)}</td>
        <td className="px-4 py-3 text-right font-mono">{inrFull(r.overtime_pay || 0)}</td>
        <td className="px-4 py-3 text-right font-mono">{inrFull(r.deductions || 0)}</td>
        <td className="px-4 py-3 text-right font-mono" title={`PF ${inrFull(r.pf_employee || 0)} · ESI ${inrFull(r.esi_employee || 0)} · PT ${inrFull(r.professional_tax || 0)}`}>{inrFull(r.statutory_deductions || 0)}</td>
        <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(r.net_salary || 0)}</td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-1.5">
            <PayrollStatusBadge status={r.status} />
            {r.attendance_locked ? <Lock size={12} className="text-[var(--color-text-muted)]" title="Attendance locked" /> : null}
          </div>
        </td>
        <td className="px-4 py-3 text-right">
          <div className="flex items-center justify-end gap-1.5">
          <button type="button" onClick={() => onPayslip(r)} title="Payslip" aria-label="Payslip" data-testid={`payslip-${r.id}`}
            className="p-1.5 rounded-[var(--radius-sm)] hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]">
            <Printer size={14} />
          </button>
          {canApprove && (
            <div className="flex items-center justify-end gap-1.5">
              {r.status === "Draft" && exceptions.length === 0 && (
                <SecondaryButton disabled={busy} onClick={() => setStatus("Approved")} className="text-xs py-1">Approve</SecondaryButton>
              )}
              {r.status === "Approved" && (
                <SecondaryButton disabled={busy} onClick={() => setStatus("Paid")} className="text-xs py-1">Mark Paid</SecondaryButton>
              )}
              {r.status === "Approved" && (
                <SecondaryButton disabled={busy} onClick={() => setStatus("Draft")} className="text-xs py-1">Reopen</SecondaryButton>
              )}
              {r.status === "Draft" && r.attendance_locked && (
                <button type="button" onClick={unlock} disabled={busy} title="Unlock attendance for re-import"
                  className="p-1.5 rounded-[var(--radius-sm)] hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]">
                  <Unlock size={14} />
                </button>
              )}
            </div>
          )}
          </div>
        </td>
      </tr>
      {r.status === "Draft" && exceptions.length > 0 && (
        <tr>
          <td colSpan={13} className="px-4 pb-3">
            <ExceptionsBlock
              exceptions={exceptions}
              canOverride={canApprove}
              busy={busy}
              onApproveWithOverride={(reason) => setStatus("Approved", { override_attendance_exceptions: true, override_reason: reason })}
            />
          </td>
        </tr>
      )}
      {expanded && (
        <tr>
          <td colSpan={13} className="px-4 pb-3">
            <div className="bg-[var(--color-surface-muted)] rounded-[var(--radius-sm)] p-3">
              <div className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)] mb-2">
                Live attendance summary (re-checked now, not just what this period was calculated with)
              </div>
              <AttendanceSummaryPanel periodId={r.id} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function PayrollList({ rows, employeesById, canApprove, onChanged, onPayslip }) {
  return (
    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[var(--color-surface-muted)]">
            <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
              <th className="px-4 py-2.5">Employee</th>
              <th className="px-4 py-2.5">Period</th>
              <th className="px-4 py-2.5 text-right">Gross Pay</th>
              <th className="px-4 py-2.5 text-right">Payable Days</th>
              <th className="px-4 py-2.5 text-right">LOP Days</th>
              <th className="px-4 py-2.5 text-right">OT Hours</th>
              <th className="px-4 py-2.5 text-right">LOP Deduction</th>
              <th className="px-4 py-2.5 text-right">OT Pay</th>
              <th className="px-4 py-2.5 text-right">Deductions</th>
              <th className="px-4 py-2.5 text-right">Statutory</th>
              <th className="px-4 py-2.5 text-right">Net Pay</th>
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <PayrollRow key={r.id} r={r} employeesById={employeesById} canApprove={canApprove} onChanged={onChanged} onPayslip={onPayslip} />
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={13}><EmptyState title="No payroll runs yet" hint="Calculated payroll periods will show up here." /></td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function PayrollPage() {
  const { user, canDo } = useAuth();
  const canCreate = canDo("payroll", "create");
  const canApprove = canDo("payroll", "approve");
  const [rows, setRows] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [employeeFilter, setEmployeeFilter] = useState("");
  const [payslip, setPayslip] = useState(null);
  const [showPolicy, setShowPolicy] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    const params = employeeFilter ? { employee_id: employeeFilter } : {};
    api.get("/v1/payroll", { params, skipCache: true })
      .then((r) => setRows(r.data))
      .catch((err) => {
        toast.error(formatApiError(err.response?.data?.detail) || "Couldn't load payroll runs");
        setLoadError(err?.response?.status === 401 || err?.response?.status === 403 ? "unauthorized" : "error");
      })
      .finally(() => setLoading(false));
  }, [employeeFilter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/users/directory").then((r) => setEmployees(r.data)).catch(() => {});
  }, []);

  const employeesById = Object.fromEntries(employees.map((e) => [e.id, e.name]));

  if (!user) return null;

  return (
    <>
      <Topbar
        title="Payroll"
        subtitle={loading ? "Loading…" : `${rows.length} payroll run(s)`}
        actions={
          <div className="flex items-center gap-2">
          {canApprove && (
            <SecondaryButton onClick={() => setShowPolicy((v) => !v)} aria-expanded={showPolicy} data-testid="payroll-policy-toggle">
              <Settings2 size={14} /> Statutory settings
            </SecondaryButton>
          )}
          <select
            aria-label="Filter by employee"
            value={employeeFilter}
            onChange={(e) => setEmployeeFilter(e.target.value)}
            className="px-3 py-2 text-sm rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] max-w-[180px]"
          >
            <option value="">All employees</option>
            {employees.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
          </div>
        }
      />
      <div className="p-6" data-testid="payroll-page">
        {loadError === "unauthorized" ? (
          <ErrorState title="You don't have access to Payroll" />
        ) : loadError ? (
          <ErrorState title="Couldn't load payroll runs" hint="Check your connection and try again." onRetry={load} />
        ) : (
          <>
            {showPolicy && canApprove && <PolicyPanel onClose={() => setShowPolicy(false)} />}
            {canCreate && <CalculatePayrollButton employees={employees} onCalculated={load} />}
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : (
              <PayrollList rows={rows} employeesById={employeesById} canApprove={canApprove} onChanged={load} onPayslip={setPayslip} />
            )}
          </>
        )}
      </div>
      {payslip && <Payslip r={payslip} name={payslip.employee_name || employeesById[payslip.employee_id] || payslip.employee_id} onClose={() => setPayslip(null)} />}
    </>
  );
}

function PolicyPanel({ onClose }) {
  const [policy, setPolicy] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get("/v1/payroll/policy", { skipCache: true }).then((r) => setPolicy(r.data))
      .catch(() => toast.error("Couldn't load statutory settings"));
  }, []);
  if (!policy) return <Skeleton className="h-24 w-full mb-4" />;
  const set = (k, v) => setPolicy((p) => ({ ...p, [k]: v }));
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.put("/v1/payroll/policy", policy);
      setPolicy(data);
      toast.success("Statutory settings saved. They apply to payroll calculated from now on.");
      onClose();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Couldn't save"); }
    finally { setBusy(false); }
  };
  const toggles = [
    ["pf_enabled", "Provident Fund (PF)", `${policy.pf_rate}% of basic, employee and employer; wage ceiling ${inrFull(policy.pf_wage_ceiling)}`],
    ["esi_enabled", "ESI", `${policy.esi_rate}% employee, ${policy.esi_employer_rate}% employer, for gross up to ${inrFull(policy.esi_gross_limit)}`],
    ["pt_enabled", "Professional Tax (Telangana)", "Nil up to ₹15,000 gross, ₹150 up to ₹20,000, ₹200 above"],
  ];
  return (
    <div className="mb-4 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-4" data-testid="payroll-policy">
      <div className="font-semibold mb-1">Statutory deductions</div>
      <p className="text-xs text-[var(--color-text-muted)] mb-3">Switch on only what your company is registered for. Changes apply to payroll calculated after saving; recalculate a Draft to apply them to it.</p>
      <div className="space-y-2 mb-3">
        {toggles.map(([k, label, hint]) => (
          <label key={k} className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={!!policy[k]} onChange={(e) => set(k, e.target.checked)} className="mt-1" data-testid={`policy-${k}`} />
            <span><span className="font-medium">{label}</span><span className="block text-xs text-[var(--color-text-muted)]">{hint}</span></span>
          </label>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-3 mb-3">
        <label className="text-xs">Basic, % of gross
          <input type="number" value={policy.basic_pct} onChange={(e) => set("basic_pct", parseFloat(e.target.value) || 0)}
            className="block mt-1 w-28 px-2 py-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] text-sm" />
        </label>
        <label className="text-xs">HRA, % of basic
          <input type="number" value={policy.hra_pct_of_basic} onChange={(e) => set("hra_pct_of_basic", parseFloat(e.target.value) || 0)}
            className="block mt-1 w-28 px-2 py-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] text-sm" />
        </label>
      </div>
      <div className="flex justify-end gap-2">
        <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
        <PrimaryButton onClick={save} disabled={busy} data-testid="payroll-policy-save">{busy ? "Saving…" : "Save settings"}</PrimaryButton>
      </div>
    </div>
  );
}

function Payslip({ r, name, onClose }) {
  const [office, setOffice] = useState({});
  useEffect(() => {
    document.body.classList.add("printing");
    api.get("/settings/office").then((x) => setOffice(x.data || {})).catch(() => {});
    return () => document.body.classList.remove("printing");
  }, []);
  const gross = r.gross_pay || 0;
  // Older runs predate the salary split: show the whole gross as one line.
  const earnings = (r.basic || r.hra || r.special_allowance)
    ? [["Basic", r.basic], ["HRA", r.hra], ["Special allowance", r.special_allowance]]
    : [["Gross pay", gross]];
  if (r.bonuses) earnings.push(["Bonus", r.bonuses]);
  if (r.incentive_bonus) earnings.push(["Incentives", r.incentive_bonus]);
  const deductions = [["Provident Fund", r.pf_employee], ["ESI", r.esi_employee],
    ["Professional Tax", r.professional_tax], ["Other deductions", r.deductions]].filter(([, v]) => v);
  const totalEarn = earnings.reduce((a, [, v]) => a + (v || 0), 0);
  const totalDed = deductions.reduce((a, [, v]) => a + (v || 0), 0);
  const line = (label, v) => (
    <div key={label} className="flex justify-between py-1 border-b border-[var(--color-border)]"><span>{label}</span><span className="font-mono">{inrFull(v || 0)}</span></div>
  );
  const month = r.period_start ? new Date(`${r.period_start}T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" }) : "";
  return (
    <div className="fixed inset-0 bg-white z-[60] overflow-auto print-view" data-testid="payslip">
      <div className="max-w-3xl mx-auto p-8 print:p-0 max-h-[92vh] overflow-y-auto" id="print-area">
        <div className="flex justify-between items-start mb-6">
          <div>
            <div className="font-heading font-bold text-xl">{office.name || ""}</div>
            <div className="text-sm text-[var(--color-text-muted)]">{office.address || ""}</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] font-semibold">Payslip</div>
            <div className="font-semibold">{month}</div>
            <div className="text-xs text-[var(--color-text-muted)]">{fmtDate(r.period_start)} – {fmtDate(r.period_end)}</div>
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mb-6">
          <div><div className="text-[10px] uppercase text-[var(--color-text-muted)]">Employee</div><div className="font-medium">{name}</div></div>
          <div><div className="text-[10px] uppercase text-[var(--color-text-muted)]">Payable days</div><div className="font-mono">{r.payable_days ?? "—"}</div></div>
          <div><div className="text-[10px] uppercase text-[var(--color-text-muted)]">LOP days</div><div className="font-mono">{r.lop_days ?? "—"}</div></div>
          <div><div className="text-[10px] uppercase text-[var(--color-text-muted)]">Status</div><div>{r.status}</div></div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-sm mb-6">
          <div>
            <div className="font-semibold mb-1">Earnings</div>
            {earnings.map(([l, v]) => line(l, v))}
            <div className="flex justify-between py-1 font-semibold"><span>Total earnings</span><span className="font-mono">{inrFull(totalEarn)}</span></div>
          </div>
          <div>
            <div className="font-semibold mb-1">Deductions</div>
            {deductions.length ? deductions.map(([l, v]) => line(l, v)) : <div className="py-1 text-[var(--color-text-muted)]">None</div>}
            <div className="flex justify-between py-1 font-semibold"><span>Total deductions</span><span className="font-mono">{inrFull(totalDed)}</span></div>
          </div>
        </div>
        <div className="border-t-2 border-[var(--color-text)] pt-3 flex justify-between items-baseline">
          <span className="font-semibold">Net pay</span>
          <span className="font-mono font-bold text-xl" data-testid="payslip-net">{inrFull(r.net_salary || 0)}</span>
        </div>
        <div className="text-sm mt-1">{amountInWords(r.net_salary || 0)}</div>
        {(r.pf_employer || r.esi_employer) ? (
          <div className="text-xs text-[var(--color-text-muted)] mt-4">Employer contributions (not deducted): PF {inrFull(r.pf_employer || 0)}, ESI {inrFull(r.esi_employer || 0)}</div>
        ) : null}
        <div className="text-[10px] text-[var(--color-text-muted)] mt-8">This is a computer-generated payslip.</div>
      </div>
      <div className="no-print fixed bottom-6 right-6 flex gap-2 z-10">
        <SecondaryButton onClick={onClose}>Close</SecondaryButton>
        <PrimaryButton onClick={() => window.print()}><Printer size={14} /> Print / Save PDF</PrimaryButton>
      </div>
    </div>
  );
}
