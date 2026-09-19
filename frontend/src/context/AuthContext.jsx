import { createContext, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

// Modules the backend actually gates through the Role permission matrix
// (server.py's make_crud(..., module=...) calls) — mirrors that set exactly.
// Every other page id keeps using the legacy `pages` grant, role_id or not.
const GATED_MODULES = [
  "leads", "customers", "quotes", "sales", "inventory",
  "visitors", "architects", "tasks", "invoice-gen", "meetplan", "petty", "requirements",
  "commissions", "cashbook", "record-contacts",
  // api_hr.py's own permissions.py-backed modules (_can_hr/_require_hr) —
  // added so a role_id account's Payroll/Leave route+action access mirrors
  // its actual configured grant instead of falling through to the legacy
  // `pages` array, same as every module above.
  "payroll", "leave",
];

// api_hr.py's _can_hr() bypasses the role-permission check entirely for
// role === "admin" OR "accountant" on these two modules specifically — the
// literal-role floor this codebase's HR API has always had, never narrowed
// by the later permissions.py engine. Mirrored here so the UI never shows
// (or hides) an action the backend would answer differently for.
const HR_ROLE_BYPASS_MODULES = ["payroll", "leave"];

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking; false = anon; obj = user
  const [loading, setLoading] = useState(true);
  const [tenant, setTenant] = useState(null); // entity config: branding + enabled_modules
  const [roles, setRoles] = useState([]);

  const loadTenant = () => api.get("/tenants/me").then((r) => setTenant(r.data)).catch(() => setTenant(null));
  const loadRoles = () => api.get("/roles").then((r) => setRoles(r.data)).catch(() => setRoles([]));

  useEffect(() => {
    const token = localStorage.getItem("crm_token");
    if (!token) {
      setUser(false);
      setLoading(false);
      return;
    }
    api
      .get("/auth/me")
      .then((r) => { setUser(r.data); loadTenant(); loadRoles(); })
      .catch(() => setUser(false))
      .finally(() => setLoading(false));
  }, []);

  const login = async (username, pin) => {
    const { data } = await api.post("/auth/login", { username, pin });
    localStorage.setItem("crm_token", data.token);
    localStorage.setItem("crm_user", JSON.stringify(data.user));
    setUser(data.user);
    loadTenant();
    loadRoles();
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem("crm_token");
    localStorage.removeItem("crm_user");
    setUser(false);
    setTenant(null);
    window.location.href = "/login";
  };

  const canAccess = (pageId) => {
    if (!user) return false;
    if (tenant && Array.isArray(tenant.enabled_modules) && !tenant.enabled_modules.includes(pageId)) return false;
    if (user.role === "admin") return true;
    if (user.role === "accountant" && HR_ROLE_BYPASS_MODULES.includes(pageId)) return true;
    if (user.role_id && GATED_MODULES.includes(pageId)) {
      const role = roles.find((r) => r.id === user.role_id);
      const modPerm = role?.permissions?.find((p) => p.module === pageId);
      return !!modPerm?.view;
    }
    if (user.pages == null) return true;
    return Array.isArray(user.pages) && user.pages.includes(pageId);
  };

  // Per-action counterpart to canAccess (which only ever checks "view").
  // Mirrors permissions.py's LEGACY_IMPLICIT_ACTIONS server-side: an account
  // with role_id set and a gated module is checked against that specific
  // action's grant; a legacy account (no role_id) or an ungated module keeps
  // canAccess's all-or-nothing view grant for create/edit/delete, but never
  // for approve/export — those never existed in the old pages-only system.
  const canDo = (moduleId, action) => {
    if (action === "view") return canAccess(moduleId);
    if (!canAccess(moduleId)) return false;
    if (user.role === "admin") return true;
    if (user.role === "accountant" && HR_ROLE_BYPASS_MODULES.includes(moduleId)) return true;
    if (user.role_id && GATED_MODULES.includes(moduleId)) {
      const role = roles.find((r) => r.id === user.role_id);
      const modPerm = role?.permissions?.find((p) => p.module === moduleId);
      return !!modPerm?.[action];
    }
    return action !== "approve" && action !== "export";
  };

  return (
    <AuthContext.Provider value={{ user, loading, tenant, roles, refreshTenant: loadTenant, refreshRoles: loadRoles, login, logout, canAccess, canDo }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
