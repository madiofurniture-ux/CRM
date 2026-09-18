import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { inrFull, fmtDate } from "@/lib/format";
import { toast } from "sonner";

// Same Draft/Approved/Paid palette family as StageBadge's Quoted/Confirmed/
// Won (amber -> blue -> green) — reused rather than a second badge component
// for a three-value enum.
const STATUS_STYLE = {
  Draft: { bg: "bg-amber-100", text: "text-amber-800" },
  Approved: { bg: "bg-blue-600", text: "text-white" },
  Paid: { bg: "bg-[var(--moss-soft)]", text: "text-[var(--moss)]" },
};

function PayrollStatusBadge({ status }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.Draft;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${s.bg} ${s.text}`}>
      {status || "Draft"}
    </span>
  );
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
    <div className="flex flex-wrap items-end gap-2 mb-4 bg-[var(--surface)] border border-[var(--border)] rounded-xl p-3">
      <div>
        <label className="block text-[11px] uppercase tracking-wide text-[var(--ink-3)] mb-1">Employee</label>
        <select value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}
          className="px-3 py-2 rounded-lg bg-[var(--surface-2)] border border-[var(--border)] text-sm min-w-[180px]">
          <option value="">Select…</option>
          {employees.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </select>
      </div>
      <div>
        <label className="block text-[11px] uppercase tracking-wide text-[var(--ink-3)] mb-1">Period start</label>
        <input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)}
          className="px-3 py-2 rounded-lg bg-[var(--surface-2)] border border-[var(--border)] text-sm" />
      </div>
      <div>
        <label className="block text-[11px] uppercase tracking-wide text-[var(--ink-3)] mb-1">Period end</label>
        <input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)}
          className="px-3 py-2 rounded-lg bg-[var(--surface-2)] border border-[var(--border)] text-sm" />
      </div>
      <button onClick={calculate} disabled={busy}
        className="px-4 py-2 rounded-lg bg-[var(--ink)] text-white text-sm font-semibold disabled:opacity-50">
        {busy ? "Calculating…" : "Calculate Payroll"}
      </button>
    </div>
  );
}

function PayrollList({ rows, employeesById }) {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-[var(--surface-2)]">
            <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
              <th className="px-4 py-2.5">Employee</th>
              <th className="px-4 py-2.5">Period</th>
              <th className="px-4 py-2.5 text-right">Gross Pay</th>
              <th className="px-4 py-2.5 text-right">Deductions</th>
              <th className="px-4 py-2.5 text-right">Net Pay</th>
              <th className="px-4 py-2.5">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-[var(--border-light)]" data-testid={`payroll-row-${r.id}`}>
                <td className="px-4 py-3 font-medium">{employeesById[r.employee_id] || r.employee_id}</td>
                <td className="px-4 py-3 whitespace-nowrap">{fmtDate(r.period_start)} – {fmtDate(r.period_end)}</td>
                <td className="px-4 py-3 text-right font-mono">{inrFull(r.gross_pay || 0)}</td>
                <td className="px-4 py-3 text-right font-mono">{inrFull(r.deductions || 0)}</td>
                <td className="px-4 py-3 text-right font-mono font-semibold">{inrFull(r.net_salary || 0)}</td>
                <td className="px-4 py-3"><PayrollStatusBadge status={r.status} /></td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan="6" className="text-center py-12 text-[var(--ink-3)]">No payroll runs yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function PayrollPage() {
  const [rows, setRows] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    api.get("/v1/payroll", { skipCache: true }).then((r) => setRows(r.data))
      .catch((err) => toast.error(formatApiError(err.response?.data?.detail) || "Couldn't load payroll runs"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    api.get("/users/directory").then((r) => setEmployees(r.data)).catch(() => {});
  }, []);

  const employeesById = Object.fromEntries(employees.map((e) => [e.id, e.name]));

  return (
    <>
      <Topbar title="Payroll" subtitle={loading ? "Loading…" : `${rows.length} payroll run(s)`} />
      <div className="p-6" data-testid="payroll-page">
        <CalculatePayrollButton employees={employees} onCalculated={load} />
        <PayrollList rows={rows} employeesById={employeesById} />
      </div>
    </>
  );
}
