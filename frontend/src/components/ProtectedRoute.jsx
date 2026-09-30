import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export default function ProtectedRoute({ children, page }) {
  const { user, loading, canAccess } = useAuth();
  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen text-[var(--ink-2)] font-heading text-sm tracking-wide">
        Loading…
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (page && !canAccess(page)) {
    return (
      <div className="flex items-center justify-center h-full p-10 text-center">
        <div>
          <h2 className="font-heading text-2xl text-[var(--ink)] mb-2">No access</h2>
          <p className="text-[var(--ink-2)] text-sm">
            Your role doesn’t have permission for this page. Contact admin.
          </p>
        </div>
      </div>
    );
  }
  return children;
}
