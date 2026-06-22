import { createContext, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking; false = anon; obj = user
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("madio_token");
    if (!token) {
      setUser(false);
      setLoading(false);
      return;
    }
    api
      .get("/auth/me")
      .then((r) => setUser(r.data))
      .catch(() => setUser(false))
      .finally(() => setLoading(false));
  }, []);

  const login = async (username, pin) => {
    const { data } = await api.post("/auth/login", { username, pin });
    localStorage.setItem("madio_token", data.token);
    localStorage.setItem("madio_user", JSON.stringify(data.user));
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem("madio_token");
    localStorage.removeItem("madio_user");
    setUser(false);
    window.location.href = "/login";
  };

  const canAccess = (pageId) => {
    if (!user) return false;
    if (user.role === "admin" || user.pages == null) return true;
    return Array.isArray(user.pages) && user.pages.includes(pageId);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, canAccess }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
