import { useState, createContext, useContext } from "react";
import Sidebar from "@/components/Sidebar";

const DrawerCtx = createContext({ open: () => {} });
export const useDrawer = () => useContext(DrawerCtx);

export default function Layout({ children }) {
  const [open, setOpen] = useState(false);
  return (
    <DrawerCtx.Provider value={{ open: () => setOpen(true), close: () => setOpen(false) }}>
      <div className="flex min-h-screen bg-[var(--bg)]">
        <Sidebar open={open} onClose={() => setOpen(false)} />
        <main className="flex-1 min-w-0 w-full">{children}</main>
      </div>
    </DrawerCtx.Provider>
  );
}
