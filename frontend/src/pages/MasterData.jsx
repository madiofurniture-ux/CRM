import { useEffect, useState } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import LocationsManager from "@/components/LocationsManager";

// Single home for tenant-wide reference lists that get reused across
// screens instead of each screen managing its own copy — Locations today
// (Inventory + Stock Ledger), more lists land here the same way as they
// gain their own /<collection> CRUD.
export default function MasterData() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [floors, setFloors] = useState(null);

  useEffect(() => { api.get("/floors").then(({ data }) => setFloors(data)); }, []);

  if (!isAdmin) return <><Topbar title="Master Data" /><div className="p-10 text-center text-[var(--ink-3)]">Admin access required.</div></>;

  return (
    <>
      <Topbar title="Master Data" subtitle="Reference lists shared across screens" />
      <div className="p-6 max-w-3xl space-y-6" data-testid="master-data-page">
        {floors === null
          ? <div className="text-sm text-[var(--ink-3)]">Loading…</div>
          : <LocationsManager floors={floors} onChange={setFloors} />}
      </div>
    </>
  );
}
