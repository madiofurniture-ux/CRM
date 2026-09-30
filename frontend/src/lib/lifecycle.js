import { inr } from "@/lib/format";

// Builds the {key, label, done} array StageProgressBar renders, for the
// Visitor -> Lead -> Deal -> Project -> Wallet -> P&L pipeline. Two flavors
// since a Lead and a Project each only know their own side of the chain —
// neither record alone carries every step's status.

const DEAL_STAGES = ["Quoted", "Negotiation", "Won"];

export function leadLifecycleStages(lead) {
  const dealActive = DEAL_STAGES.includes(lead.stage);
  return [
    { key: "visitor", label: "Visitor", done: !!lead.visitor_id },
    { key: "lead", label: "Lead", done: true },
    { key: "deal", label: dealActive ? `Deal: ${inr(lead.value)}` : "Deal", done: dealActive },
    { key: "project", label: "Project", done: false },
    { key: "wallet", label: "Wallet & Expenses", done: false },
    { key: "pnl", label: "P&L & Incentive", done: false },
  ];
}

// `pnlRow` is this project's own row from GET /reports/project-pnl, if the
// caller already has it loaded (e.g. Projects.jsx's pnlByProject map) —
// omit it and those last two steps just show inactive.
export function projectLifecycleStages(project, pnlRow) {
  const hasWallet = (pnlRow?.wallet_count || 0) > 0;
  // `has_approved_spend`, not `approved_petty_cash`: the amount is null in a
  // masked P&L payload, which would wrongly blank this step out. The boolean
  // is mask-safe — it says spend exists without saying how much.
  const hasPnl = hasWallet && (pnlRow?.has_approved_spend || (pnlRow?.approved_incentives || 0) > 0);
  return [
    // A Project's own record doesn't say whether a Visitor started this
    // lineage — approximated as "yes" whenever a Lead is attached, since a
    // won deal without any lead/visitor history is rare in this app.
    { key: "visitor", label: "Visitor", done: !!project.lead_id },
    { key: "lead", label: "Lead", done: !!project.lead_id },
    { key: "deal", label: `Deal: ${inr(project.value)}`, done: !!project.quote_id },
    { key: "project", label: "Project", done: true },
    { key: "wallet", label: "Wallet & Expenses", done: hasWallet },
    { key: "pnl", label: "P&L & Incentive", done: hasPnl },
  ];
}
