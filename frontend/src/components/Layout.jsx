import Sidebar from "@/components/Sidebar";
import BottomNav from "@/components/BottomNav";
import { SidebarProvider } from "@/context/SidebarContext";

const IS_STAGING = process.env.REACT_APP_ENV === "staging";

export default function Layout({ children }) {
  return (
    <SidebarProvider>
      {IS_STAGING && (
        <div className="fixed top-0 inset-x-0 z-[100] bg-amber-500 text-white text-center text-xs font-bold py-1 tracking-wider" data-testid="staging-banner">
          STAGING / TEST — not production data
        </div>
      )}
      <div className={`flex min-h-screen bg-[var(--bg)] ${IS_STAGING ? "pt-6" : ""}`}>
        <Sidebar />
        <main className="flex-1 min-w-0 pb-16 lg:pb-0">{children}</main>
      </div>
      <BottomNav />
    </SidebarProvider>
  );
}
