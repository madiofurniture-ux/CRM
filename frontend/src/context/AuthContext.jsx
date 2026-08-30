import { createContext, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking; false = anon; obj = user
  const [loading, setLoading] = useState(true);
  const [tenant, setTenant] = useState(null); // entity config: branding + enabled_modules

  const loadTenant = () => api.get("/tenants/me").then((r) => setTenant(r.data)).catch(() => setTenant(null));

  useEffect(() => {
    const token = localStorage.getItem("crm_token");
    if (!token) {
      setUser(false);
      setLoading(false);
      return;
    }
    api
      .get("/auth/me")
      .then((r) => { setUser(r.data); loadTenant(); })
      .catch(() => setUser(false))
      .finally(() => setLoading(false));
  }, []);

  const login = async (username, pin) => {
    const { data } = await api.post("/auth/login", { username, pin });
    localStorage.setItem("crm_token", data.token);
    localStorage.setItem("crm_user", JSON.stringify(data.user));
    setUser(data.user);
    loadTenant();
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
    if (user.role === "admin" || user.pages == null) return true;
    return Array.isArray(user.pages) && user.pages.includes(pageId);
  };


  return (
    <AuthContext.Provider value={{ user, loading, tenant, refreshTenant: loadTenant, login, logout, canAccess }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
