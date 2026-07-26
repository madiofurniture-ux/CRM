import { useState, useMemo, createContext, useContext } from "react";
import Sidebar from "@/components/Sidebar";

const DrawerCtx = createContext({ open: () => {} });
export const useDrawer = () => useContext(DrawerCtx);

export default function Layout({ children }) {
  const [open, setOpen] = useState(false);
  const value = useMemo(() => ({ open: () => setOpen(true), close: () => setOpen(false) }), []);
  return (
    <DrawerCtx.Provider value={value}>
      <div className="flex min-h-screen bg-[var(--bg)]">
        <Sidebar open={open} onClose={() => setOpen(false)} />
        <main className="flex-1 min-w-0 w-full">{children}</main>
      </div>
    </DrawerCtx.Provider>
  );
}
