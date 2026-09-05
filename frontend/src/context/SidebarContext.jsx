import { createContext, useContext, useState } from "react";

const SidebarContext = createContext(null);

const COLLAPSE_KEY = "crm_sidebar_collapsed";

function loadCollapsed() {
  try { return localStorage.getItem(COLLAPSE_KEY) === "1"; } catch { return false; }
}

export function SidebarProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsedState] = useState(loadCollapsed);

  const setCollapsed = (v) => {
    setCollapsedState(v);
    try { localStorage.setItem(COLLAPSE_KEY, v ? "1" : "0"); } catch {}
  };

  return (
    <SidebarContext.Provider value={{ open, setOpen, collapsed, setCollapsed }}>
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar() {
  return useContext(SidebarContext) || { open: false, setOpen: () => {}, collapsed: false, setCollapsed: () => {} };
}
