import { Link } from "react-router-dom";
import { Clock, Lock } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

/** A thin strip above every page when the company's plan needs attention:
 * the last week of a free trial, or a trial that has ended (read-only).
 * State comes from /tenants/me → subscription (backend/plans.py). */
export default function SubscriptionBanner() {
  const { tenant, user } = useAuth();
  const sub = tenant?.subscription;
  if (!sub || tenant?.is_platform_owner) return null;
  const ended = sub.can_write === false;
  const left = sub.trial_days_left;
  if (!ended && !(sub.plan === "trial" && left != null && left <= 7)) return null;
  const isAdmin = user?.role === "admin";
  return (
    <div role="status" data-testid="subscription-banner"
      className={`flex flex-wrap items-center gap-x-3 gap-y-1 px-4 md:px-6 py-2 text-sm border-b ${ended
        ? "bg-[var(--danger-soft)] text-[var(--color-danger)] border-[var(--color-danger)]/20"
        : "bg-[var(--warn-soft)] text-[var(--color-warning)] border-[var(--color-warning)]/20"}`}>
      {ended ? <Lock size={15} /> : <Clock size={15} />}
      <span className="font-semibold">
        {ended ? "Trial ended — read-only" : left === 0 ? "Your free trial ends today" : `${left} day${left === 1 ? "" : "s"} left in your free trial`}
      </span>
      <span className="text-[var(--color-text-muted)]">
        {ended ? "Your data is safe. Choose a plan to keep adding and editing records." : "Choose a plan to keep everything running without a break."}
      </span>
      {isAdmin && (
        <Link to="/admin/setup" className="ml-auto font-semibold underline underline-offset-2">Setup &amp; plan</Link>
      )}
    </div>
  );
}
