import { useLocation } from "react-router-dom";
import Header from "@/components/Header";
import ErrorBoundary from "@/components/ErrorBoundary";
import LightAppShell from "@/components/light/LightAppShell";
import { IS_LIGHT_THEME } from "@/lib/featureFlags";

const IS_STAGING = process.env.REACT_APP_ENV === "staging";

export default function Layout({ children }) {
  // Every authenticated route renders through here, so one boundary around
  // the page slot covers all of them. Keyed on pathname so navigating to a
  // different screen clears a caught error instead of stranding the user on
  // the fallback panel.
  const { pathname } = useLocation();
  const page = <ErrorBoundary key={pathname}>{children}</ErrorBoundary>;
  const stagingBanner = IS_STAGING && (
    <div className="bg-amber-500 text-white text-center text-xs font-bold py-1 tracking-wider" data-testid="staging-banner">
      STAGING / TEST — not production data
    </div>
  );

  if (IS_LIGHT_THEME) {
    return (
      <>
        {stagingBanner}
        <LightAppShell>{page}</LightAppShell>
      </>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      {stagingBanner}
      <Header />
      <main id="main-content" tabIndex={-1} className="outline-none">
        {page}
      </main>
    </div>
  );
}
