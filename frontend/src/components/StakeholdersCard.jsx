import { useState } from "react";
import api from "@/lib/api";
import StakeholderLinkModal from "@/components/StakeholderLinkModal";
import { Phone, MessageCircle, UserPlus, Building2, HardHat, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

const SLOTS = [
  { key: "client_poc", label: "Client POC", icon: UserPlus },
  { key: "architect", label: "Architect", icon: Building2 },
  { key: "applicator_or_contractor", label: "Applicator / Contractor", icon: HardHat },
  { key: "internal_site_supervisor", label: "Internal Supervisor", icon: ShieldCheck },
];

function waLink(phone) {
  const digits = (phone || "").replace(/\D/g, "");
  return digits ? `https://wa.me/${digits}` : null;
}

/** 4-tile stakeholder panel for a project's client_poc / architect /
 * applicator_or_contractor / internal_site_supervisor slots, each linkable
 * in one click via StakeholderLinkModal. */
export default function StakeholdersCard({ project, onUpdated }) {
  const [linking, setLinking] = useState(null); // slot key currently being linked

  const stakeholders = project.stakeholders || {};

  const link = async (slotKey, person) => {
    const patch = { [slotKey]: buildSlot(slotKey, person) };
    try {
      const { data } = await api.put(`/projects/${project.id}`, {
        stakeholders: { ...stakeholders, ...patch },
      });
      onUpdated(data);
      toast.success("Stakeholder linked");
    } catch {
      toast.error("Failed to link stakeholder");
    } finally {
      setLinking(null);
    }
  };

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4" data-testid="stakeholders-card">
      <div className="text-sm font-semibold mb-3">Stakeholders</div>
      <div className="grid grid-cols-2 gap-3">
        {SLOTS.map((slot) => {
          const person = stakeholders[slot.key];
          const Icon = slot.icon;
          return (
            <div key={slot.key} className="rounded-lg border border-[var(--border-light)] p-3" data-testid={`stakeholder-tile-${slot.key}`}>
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-[var(--ink-3)] mb-1.5">
                <Icon size={12} /> {slot.label}
              </div>
              {person ? (
                <>
                  <div className="text-sm font-medium text-[var(--ink)] truncate">{person.name}</div>
                  {slot.key === "architect" && person.firm && (
                    <div className="text-[11px] text-[var(--ink-3)] truncate">
                      {person.firm}{person.commission_rate != null ? ` · ${person.commission_rate}% commission` : ""}
                    </div>
                  )}
                  {slot.key === "applicator_or_contractor" && person.role && (
                    <span className="inline-block mt-0.5 mb-1 px-1.5 py-0.5 rounded text-[10px] bg-[var(--brand-light)] text-[var(--brand)] font-medium">
                      {person.role}
                    </span>
                  )}
                  {person.phone && (
                    <div className="flex items-center gap-2 mt-1.5">
                      <a href={`tel:${person.phone}`} className="p-1 rounded hover:bg-[var(--surface-2)] text-[var(--ink-2)]" title="Call">
                        <Phone size={13} />
                      </a>
                      {waLink(person.phone) && (
                        <a href={waLink(person.phone)} target="_blank" rel="noreferrer" className="p-1 rounded hover:bg-[var(--surface-2)] text-[var(--ink-2)]" title="WhatsApp">
                          <MessageCircle size={13} />
                        </a>
                      )}
                      <button onClick={() => setLinking(slot.key)} className="ml-auto text-[11px] text-[var(--brand)] font-medium hover:underline">
                        Swap
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <button onClick={() => setLinking(slot.key)} className="text-[11px] text-[var(--brand)] font-medium hover:underline" data-testid={`stakeholder-link-${slot.key}`}>
                  + Link
                </button>
              )}
            </div>
          );
        })}
      </div>

      {linking && (
        <StakeholderLinkModal
          role={linking}
          onClose={() => setLinking(null)}
          onLink={(person) => link(linking, person)}
        />
      )}
    </div>
  );
}

function buildSlot(slotKey, person) {
  const base = { id: person.id || "", name: person.name, phone: person.phone || "" };
  if (slotKey === "client_poc") return { ...base, email: person.email || "" };
  if (slotKey === "architect") return { ...base, firm: person.firm || "" };
  if (slotKey === "applicator_or_contractor") return { ...base, role: person.role || "APPLICATOR" };
  if (slotKey === "internal_site_supervisor") return base;
  return base;
}
