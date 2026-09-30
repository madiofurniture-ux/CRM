import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Topbar from "@/components/Topbar";
import api, { formatApiError } from "@/lib/api";
import { inrFull } from "@/lib/format";
import { toast } from "sonner";
import {
  GripVertical, Plus, X, FileText, Table2, Wallet, ClipboardList, PenTool,
  LayoutTemplate, Eye, Save,
} from "lucide-react";

const BLOCK_TYPES = [
  { type: "ITEM_GRID", label: "Room Section / Item Table", icon: Table2 },
  { type: "PAYMENT_MILESTONES", label: "Payment Schedule", icon: Wallet },
  { type: "TERMS_CONDITIONS", label: "Terms & Scope", icon: ClipboardList },
  { type: "TEXT_BLOCK", label: "Text Block", icon: FileText },
  { type: "SIGNATURE_BLOCK", label: "Signature Box", icon: PenTool },
];

const emptyItem = { description: "", dimensions: "", finish: "", qty: 1, unit_rate: 0, discount_pct: 0, gst_rate: 18 };

function newSection(type) {
  const id = `sec-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  const base = { id, type };
  if (type === "ITEM_GRID") return { ...base, title: "New Item Table", items: [{ ...emptyItem }] };
  if (type === "PAYMENT_MILESTONES") return { ...base, title: "Payment Schedule", items: [], milestones: [{ label: "Advance", pct: 100 }] };
  if (type === "TERMS_CONDITIONS") return { ...base, title: "Terms & Scope", items: [], text: "" };
  if (type === "SIGNATURE_BLOCK") return { ...base, title: "Sign-off", items: [] };
  return { ...base, title: "Text Block", items: [], text: "" };
}

// Mirrors server._compute_quote_financials / _price_item — a live preview;
// the server always recomputes authoritatively on save, this is never trusted.
const round2 = (n) => Math.round(n * 100) / 100;

function priceItem(item) {
  // Per-line rounding must match server._price_item exactly (round each line
  // to paise, then sum — not sum-then-round), or the preview quotes a total
  // the saved record won't agree with. The `|| 1` qty fallback mirrors the
  // server's `lc.money(...) or 1`.
  const qty = Number(item.qty) || 1;
  const rate = Number(item.unit_rate) || 0;
  const subtotal = round2(qty * rate);
  const discount = round2(subtotal * (Number(item.discount_pct) || 0) / 100);
  const taxable = subtotal - discount;
  const tax = round2(taxable * (Number(item.gst_rate) || 0) / 100);
  return { subtotal, discount, tax, line_total: round2(taxable + tax) };
}
function computeFinancials(sections) {
  let subtotal = 0, total_discount = 0, total_tax = 0;
  for (const sec of sections) {
    if (sec.type !== "ITEM_GRID") continue;
    for (const item of sec.items) {
      const p = priceItem(item);
      subtotal += p.subtotal; total_discount += p.discount; total_tax += p.tax;
    }
  }
  return { subtotal, total_discount, total_tax, grand_total: subtotal - total_discount + total_tax };
}

export default function QuoteBuilder() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [quote, setQuote] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [showTemplates, setShowTemplates] = useState(!id);
  const [selected, setSelected] = useState(null); // { sectionId } | { sectionId, itemIndex }
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(!!id);
  const [dragSection, setDragSection] = useState(null);
  const [dragItem, setDragItem] = useState(null); // { sectionId, index }

  useEffect(() => {
    api.get("/quotation-templates").then(({ data }) => setTemplates(data)).catch(() => setTemplates([]));
    if (id) {
      setLoading(true);
      api.get(`/quotes/${id}`).then(({ data }) => setQuote(data)).finally(() => setLoading(false));
    }
  }, [id]);

  const patchSections = (updater) => {
    setQuote((q) => {
      const sections = updater([...q.sections]);
      return { ...q, sections, financial_summary: computeFinancials(sections) };
    });
  };

  const applyTemplate = async (templateId) => {
    try {
      const { data: existing } = await api.get("/quotes");
      const quote_no = `AF-${String(existing.length + 1).padStart(4, "0")}`;
      const { data } = await api.post("/quotes", {
        quote_no, date: new Date().toISOString().slice(0, 10), customer: "New Customer",
        template_id: templateId,
      });
      setShowTemplates(false);
      navigate(`/quotes/builder/${data.id}`, { replace: true });
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const startBlank = async () => {
    try {
      const { data: existing } = await api.get("/quotes");
      const quote_no = `AF-${String(existing.length + 1).padStart(4, "0")}`;
      const { data } = await api.post("/quotes", {
        quote_no, date: new Date().toISOString().slice(0, 10), customer: "New Customer",
        sections: [], layout_config: { section_order: [], visible: {} },
      });
      setShowTemplates(false);
      navigate(`/quotes/builder/${data.id}`, { replace: true });
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const addSection = (type) => {
    if (!quote) return;
    patchSections((sections) => [...sections, newSection(type)]);
  };

  const reorderSections = (fromIdx, toIdx) => {
    patchSections((sections) => {
      const copy = [...sections];
      const [moved] = copy.splice(fromIdx, 1);
      copy.splice(toIdx, 0, moved);
      return copy;
    });
  };

  const reorderItems = (sectionId, fromIdx, toIdx) => {
    patchSections((sections) => sections.map((s) => {
      if (s.id !== sectionId) return s;
      const items = [...s.items];
      const [moved] = items.splice(fromIdx, 1);
      items.splice(toIdx, 0, moved);
      return { ...s, items };
    }));
  };

  const updateSection = (sectionId, patch) => {
    patchSections((sections) => sections.map((s) => s.id === sectionId ? { ...s, ...patch } : s));
  };

  const updateItem = (sectionId, index, patch) => {
    patchSections((sections) => sections.map((s) => {
      if (s.id !== sectionId) return s;
      const items = s.items.map((it, i) => i === index ? { ...it, ...patch } : it);
      return { ...s, items };
    }));
  };

  const removeItem = (sectionId, index) => {
    patchSections((sections) => sections.map((s) => s.id === sectionId ? { ...s, items: s.items.filter((_, j) => j !== index) } : s));
  };

  const addItem = (sectionId) => {
    patchSections((sections) => sections.map((s) => s.id === sectionId ? { ...s, items: [...s.items, { ...emptyItem }] } : s));
  };

  const removeSection = (sectionId) => {
    patchSections((sections) => sections.filter((s) => s.id !== sectionId));
    setSelected(null);
  };

  const save = async () => {
    if (!quote || saving) return;
    setSaving(true);
    try {
      await api.put(`/quotes/${quote.id}`, {
        sections: quote.sections,
        layout_config: { section_order: quote.sections.map((s) => s.id), visible: quote.layout_config?.visible || {} },
      });
      toast.success("Quote saved");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const previewPdf = async () => {
    if (!quote) return;
    await save();
    const { data } = await api.get(`/quotes/${quote.id}/pdf`, { skipCache: true, responseType: "blob" });
    const blob = new Blob([data], { type: "application/pdf" });
    window.open(URL.createObjectURL(blob), "_blank");
  };

  const fs = quote ? computeFinancials(quote.sections || []) : null;
  const selectedSection = quote?.sections?.find((s) => s.id === selected?.sectionId);
  const selectedItem = selectedSection && selected?.itemIndex != null ? selectedSection.items[selected.itemIndex] : null;

  return (
    <>
      <Topbar title="Quote Builder" subtitle={quote ? `${quote.quote_no} — ${quote.customer}` : "Choose a starting point"}
        actions={<button onClick={() => setShowTemplates(true)} className="btn-ghost" data-testid="qb-load-template"><LayoutTemplate size={14} /> Load Industry Template</button>} />

      {loading && <div className="p-6 text-sm text-[var(--ink-3)]">Loading…</div>}

      {!loading && quote && (
        <div className="flex" style={{ height: "calc(100vh - 65px)" }}>
          {/* Palette */}
          <div className="w-56 shrink-0 border-r border-[var(--border)] p-3 space-y-1.5 overflow-y-auto">
            <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-1">Blocks</div>
            {BLOCK_TYPES.map((b) => {
              const Icon = b.icon;
              return (
                <div key={b.type} draggable
                  onDragStart={(e) => e.dataTransfer.setData("blockType", b.type)}
                  onClick={() => addSection(b.type)}
                  className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-xs cursor-grab hover:bg-[var(--surface-hover)]"
                  data-testid={`qb-palette-${b.type}`}
                >
                  <Icon size={14} className="text-[var(--ink-3)]" /> {b.label}
                </div>
              );
            })}
          </div>

          {/* Canvas */}
          <div
            className="flex-1 overflow-y-auto p-6 space-y-3"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              const type = e.dataTransfer.getData("blockType");
              if (type) addSection(type);
            }}
            data-testid="qb-canvas"
          >
            {(quote.sections || []).length === 0 && (
              <div className="text-sm text-[var(--ink-3)] border-2 border-dashed border-[var(--border)] rounded-xl p-10 text-center">
                Drag a block here, or click one in the palette.
              </div>
            )}
            {(quote.sections || []).map((sec, i) => (
              <div
                key={sec.id}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => { if (dragSection != null && dragSection !== i) reorderSections(dragSection, i); setDragSection(null); }}
                className={`bg-[var(--surface)] border rounded-xl p-4 ${selected?.sectionId === sec.id && !selected.itemIndex ? "border-[var(--brand)]" : "border-[var(--border)]"}`}
                data-testid={`qb-section-${sec.id}`}
              >
                <div className="flex items-center gap-2 mb-3">
                  <span draggable onDragStart={() => setDragSection(i)} className="cursor-grab text-[var(--ink-3)]" data-testid={`qb-section-grip-${sec.id}`}>
                    <GripVertical size={16} />
                  </span>
                  <input value={sec.title} onChange={(e) => updateSection(sec.id, { title: e.target.value })}
                    onClick={() => setSelected({ sectionId: sec.id })}
                    className="font-heading font-semibold text-sm flex-1 outline-none bg-transparent" />
                  <span className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">{sec.type.replace(/_/g, " ")}</span>
                  <button onClick={() => removeSection(sec.id)} className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]"><X size={14} /></button>
                </div>

                {sec.type === "ITEM_GRID" && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">
                          <th className="w-6"></th>
                          <th className="text-left font-semibold py-1">Description</th>
                          <th className="text-left font-semibold py-1">Dimensions</th>
                          <th className="text-left font-semibold py-1">Finish</th>
                          <th className="text-right font-semibold py-1">Qty</th>
                          <th className="text-right font-semibold py-1">Rate</th>
                          <th className="text-right font-semibold py-1">Disc %</th>
                          <th className="text-right font-semibold py-1">GST %</th>
                          <th className="text-right font-semibold py-1">Line Total</th>
                          <th className="w-6"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {sec.items.map((item, idx) => (
                          <tr key={idx}
                            onDragOver={(e) => e.preventDefault()}
                            onDrop={() => { if (dragItem?.sectionId === sec.id && dragItem.index !== idx) reorderItems(sec.id, dragItem.index, idx); setDragItem(null); }}
                            className={`border-t border-[var(--border-light)] ${selected?.sectionId === sec.id && selected.itemIndex === idx ? "bg-[var(--brand-soft)]" : ""}`}
                          >
                            <td><span draggable onDragStart={() => setDragItem({ sectionId: sec.id, index: idx })} className="cursor-grab text-[var(--ink-3)]"><GripVertical size={12} /></span></td>
                            {["description", "dimensions", "finish"].map((f) => (
                              <td key={f} className="py-1 pr-1">
                                <input value={item[f]} onChange={(e) => updateItem(sec.id, idx, { [f]: e.target.value })}
                                  onFocus={() => setSelected({ sectionId: sec.id, itemIndex: idx })}
                                  className="w-full px-1.5 py-1 rounded border border-[var(--border)] bg-white" />
                              </td>
                            ))}
                            {["qty", "unit_rate", "discount_pct", "gst_rate"].map((f) => (
                              <td key={f} className="py-1 pr-1">
                                <input type="number" value={item[f]} onChange={(e) => updateItem(sec.id, idx, { [f]: parseFloat(e.target.value) || 0 })}
                                  onFocus={() => setSelected({ sectionId: sec.id, itemIndex: idx })}
                                  className="w-16 px-1.5 py-1 rounded border border-[var(--border)] bg-white text-right" />
                              </td>
                            ))}
                            <td className="py-1 text-right font-mono font-semibold whitespace-nowrap">{inrFull(priceItem(item).line_total)}</td>
                            <td>
                              <button onClick={() => removeItem(sec.id, idx)} className="p-1 text-[var(--ink-3)] hover:text-[var(--danger)]"><X size={12} /></button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <button onClick={() => addItem(sec.id)} className="mt-2 text-xs flex items-center gap-1 text-[var(--brand)]"><Plus size={12} /> Add row</button>
                  </div>
                )}

                {(sec.type === "TERMS_CONDITIONS" || sec.type === "TEXT_BLOCK") && (
                  <textarea value={sec.text || ""} onChange={(e) => updateSection(sec.id, { text: e.target.value })}
                    onFocus={() => setSelected({ sectionId: sec.id })}
                    rows={3} className="w-full px-2 py-1.5 rounded-lg border border-[var(--border)] bg-white text-xs" />
                )}

                {sec.type === "PAYMENT_MILESTONES" && (
                  <div className="space-y-1.5">
                    {(sec.milestones || []).map((m, mi) => (
                      <div key={mi} className="flex gap-2">
                        <input value={m.label} onChange={(e) => {
                          const milestones = sec.milestones.map((x, j) => j === mi ? { ...x, label: e.target.value } : x);
                          updateSection(sec.id, { milestones });
                        }} className="flex-1 px-2 py-1 rounded border border-[var(--border)] bg-white text-xs" />
                        <input type="number" value={m.pct} onChange={(e) => {
                          const milestones = sec.milestones.map((x, j) => j === mi ? { ...x, pct: parseFloat(e.target.value) || 0 } : x);
                          updateSection(sec.id, { milestones });
                        }} className="w-16 px-2 py-1 rounded border border-[var(--border)] bg-white text-xs text-right" />
                        <span className="text-xs self-center text-[var(--ink-3)]">%</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Inspector */}
          <div className="w-64 shrink-0 border-l border-[var(--border)] p-4 overflow-y-auto">
            <div className="text-[11px] uppercase tracking-wider text-[var(--ink-3)] font-semibold mb-3">Properties</div>
            {!selectedSection && <div className="text-xs text-[var(--ink-3)]">Select a section or line item.</div>}
            {selectedSection && !selectedItem && (
              <div className="space-y-2">
                <label className="text-[11px] text-[var(--ink-3)] block">Section Title</label>
                <input value={selectedSection.title} onChange={(e) => updateSection(selectedSection.id, { title: e.target.value })}
                  className="w-full px-2 py-1.5 rounded border border-[var(--border)] bg-white text-xs" />
              </div>
            )}
            {selectedItem && (
              <div className="space-y-2">
                <div className="text-xs font-medium">{selectedItem.description || "Line item"}</div>
                <label className="text-[11px] text-[var(--ink-3)] block">Discount %</label>
                <input type="number" value={selectedItem.discount_pct}
                  onChange={(e) => updateItem(selectedSection.id, selected.itemIndex, { discount_pct: parseFloat(e.target.value) || 0 })}
                  className="w-full px-2 py-1.5 rounded border border-[var(--border)] bg-white text-xs" />
                <label className="text-[11px] text-[var(--ink-3)] block">GST Rate %</label>
                <input type="number" value={selectedItem.gst_rate}
                  onChange={(e) => updateItem(selectedSection.id, selected.itemIndex, { gst_rate: parseFloat(e.target.value) || 0 })}
                  className="w-full px-2 py-1.5 rounded border border-[var(--border)] bg-white text-xs" />
              </div>
            )}
          </div>
        </div>
      )}

      {quote && fs && (
        <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-[var(--border)] px-6 py-3 flex items-center gap-6 shadow-[0_-2px_8px_rgba(0,0,0,0.06)] z-40">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">Grand Total</div>
            <div className="font-heading font-bold text-lg">{inrFull(fs.grand_total)}</div>
          </div>
          <div title="No cost basis is tracked per line item in this builder, so this is the effective discount rate achieved, not a true profit margin.">
            <div className="text-[10px] uppercase tracking-wider text-[var(--ink-3)]">Effective Discount %</div>
            <div className="font-heading font-bold text-lg">{fs.subtotal ? ((fs.total_discount / fs.subtotal) * 100).toFixed(1) : "0.0"}%</div>
          </div>
          <div className="flex-1" />
          <button onClick={previewPdf} className="btn-ghost" data-testid="qb-preview-pdf"><Eye size={14} /> Preview PDF</button>
          <button onClick={save} disabled={saving} className="btn-primary disabled:opacity-60" data-testid="qb-save-quote">
            <Save size={14} /> {saving ? "Saving…" : "Save Quote"}
          </button>
        </div>
      )}

      {showTemplates && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => quote && setShowTemplates(false)}>
          <div className="bg-white rounded-xl border border-[var(--border)] w-full max-w-2xl p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading font-semibold text-lg">Choose a Starting Point</h3>
              {quote && <button onClick={() => setShowTemplates(false)}><X size={16} /></button>}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {templates.map((t) => (
                <button key={t.id} onClick={() => applyTemplate(t.id)}
                  className="text-left p-4 rounded-xl border border-[var(--border)] hover:border-[var(--brand)] hover:bg-[var(--brand-soft)] transition"
                  data-testid={`qb-template-${t.id}`}>
                  <LayoutTemplate size={20} className="text-[var(--brand)] mb-2" />
                  <div className="font-semibold text-sm mb-1">{t.name}</div>
                  <div className="text-xs text-[var(--ink-3)]">{t.section_count} sections · {t.division}</div>
                  <div className="mt-2 text-xs font-medium text-[var(--brand)]">Use Template →</div>
                </button>
              ))}
              <button onClick={startBlank}
                className="text-left p-4 rounded-xl border border-dashed border-[var(--border)] hover:border-[var(--brand)] transition"
                data-testid="qb-blank-quote">
                <Plus size={20} className="text-[var(--ink-3)] mb-2" />
                <div className="font-semibold text-sm mb-1">Blank Quote</div>
                <div className="text-xs text-[var(--ink-3)]">Start from an empty canvas</div>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
