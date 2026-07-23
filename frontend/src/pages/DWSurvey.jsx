import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { X, Trash2, Plus, ChevronLeft, FileText } from "lucide-react";

const TYPES = ["Window", "Door", "Sliding", "French Door", "Ventilator", "Partition"];
const FRAMES = ["uPVC", "Aluminium", "Wood", "MS", "WPC"];
const GLASS = ["Single", "Double (DGU)", "Toughened", "Frosted", "Tinted", "None"];

// W and H captured in INCHES; area is square feet.
const area = (o) => {
  const w = +o.w || 0, h = +o.h || 0, q = +o.qty || 0;
  return w > 0 && h > 0 ? +((w * h * (q || 1)) / 144).toFixed(2) : 0;
};

export default function DWSurvey() {
  const [surveys, setSurveys] = useState([]);
  const [openId, setOpenId] = useState(null);   // survey.id being edited, null = list
  const [openings, setOpenings] = useState([]);

  const loadList = () => api.get("/dw-surveys").then((r) => setSurveys(r.data));
  useEffect(() => { loadList(); }, []);

  const current = surveys.find((s) => s.id === openId);
  const loadOpenings = (sid) => api.get("/dw-openings").then((r) => setOpenings(r.data.filter((o) => o.survey_id === sid)));

  const openSurvey = (sid) => { setOpenId(sid); loadOpenings(sid); };

  const newSurvey = async () => {
    try {
      const { data } = await api.post("/dw-surveys", { customer: "", phone: "", site_address: "" });
      await loadList();
      openSurvey(data.id);
    } catch { toast.error("Could not create survey"); }
  };

  const patchSurvey = async (changes) => {
    setSurveys((p) => p.map((s) => s.id === openId ? { ...s, ...changes } : s));
    try { await api.put(`/dw-surveys/${openId}`, { ...current, ...changes }); }
    catch { toast.error("Update failed"); }
  };

  const addOpening = async () => {
    try {
      const { data } = await api.post("/dw-openings", { survey_id: openId, room: "", type: "Window", w: 0, h: 0, qty: 1, frame: "uPVC", glass: "Single", mesh: false });
      setOpenings((p) => [...p, data]);
    } catch { toast.error("Could not add opening"); }
  };
  const patchOpening = async (o, changes) => {
    const merged = { ...o, ...changes };
    merged.area = area(merged);
    setOpenings((p) => p.map((x) => x.id === o.id ? merged : x));
    try { await api.put(`/dw-openings/${o.id}`, merged); } catch { toast.error("Update failed"); }
  };
  const removeOpening = async (id) => { await api.delete(`/dw-openings/${id}`); setOpenings((p) => p.filter((x) => x.id !== id)); };

  const convert = async () => {
    try { const { data } = await api.post(`/convert/survey-to-quote/${openId}`); toast.success(`D&W quote ${data.quote_no} created`); loadList(); }
    catch { toast.error("Convert failed"); }
  };

  const totalArea = useMemo(() => openings.reduce((a, o) => a + (o.area || 0), 0), [openings]);

  if (openId && current) {
    return (
      <>
        <Topbar title={`D&W Survey · ${current.survey_id}`} subtitle={`${openings.length} openings · ${totalArea.toFixed(2)} sqft`}
          actions={<button onClick={convert} className="btn-ghost"><FileText size={14} /> Convert to Quote</button>} />
        <div className="p-6 space-y-5" data-testid="dwsurvey-detail">
          <button onClick={() => { setOpenId(null); loadList(); }} className="text-sm text-[var(--ink-2)] inline-flex items-center gap-1"><ChevronLeft size={14} /> All surveys</button>

          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 grid grid-cols-2 md:grid-cols-4 gap-4">
            <F l="Customer" v={current.customer} oc={(v) => patchSurvey({ customer: v })} />
            <F l="Phone" v={current.phone} oc={(v) => patchSurvey({ phone: v })} />
            <F l="Site address" v={current.site_address} oc={(v) => patchSurvey({ site_address: v })} cls="col-span-2" />
          </div>

          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[var(--border-light)] flex items-center justify-between">
              <div className="font-heading font-semibold">Openings</div>
              <button onClick={addOpening} className="btn-ghost"><Plus size={14} /> Add opening</button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[var(--surface-2)]">
                  <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                    <th className="text-left font-semibold px-3 py-2">Room</th>
                    <th className="text-left font-semibold px-3 py-2">Type</th>
                    <th className="text-right font-semibold px-3 py-2">W (in)</th>
                    <th className="text-right font-semibold px-3 py-2">H (in)</th>
                    <th className="text-right font-semibold px-3 py-2">Qty</th>
                    <th className="text-right font-semibold px-3 py-2">Sqft</th>
                    <th className="text-left font-semibold px-3 py-2">Frame</th>
                    <th className="text-left font-semibold px-3 py-2">Glass</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {openings.map((o) => (
                    <tr key={o.id} className="border-t border-[var(--border-light)]">
                      <td className="px-3 py-2"><Inp v={o.room} oc={(v) => patchOpening(o, { room: v })} /></td>
                      <td className="px-3 py-2"><Sel v={o.type} opts={TYPES} oc={(v) => patchOpening(o, { type: v })} /></td>
                      <td className="px-3 py-2"><Inp t="number" v={o.w} oc={(v) => patchOpening(o, { w: parseFloat(v) || 0 })} right /></td>
                      <td className="px-3 py-2"><Inp t="number" v={o.h} oc={(v) => patchOpening(o, { h: parseFloat(v) || 0 })} right /></td>
                      <td className="px-3 py-2"><Inp t="number" v={o.qty} oc={(v) => patchOpening(o, { qty: parseFloat(v) || 0 })} right /></td>
                      <td className="px-3 py-2 text-right font-mono">{(o.area || 0).toFixed(2)}</td>
                      <td className="px-3 py-2"><Sel v={o.frame} opts={FRAMES} oc={(v) => patchOpening(o, { frame: v })} /></td>
                      <td className="px-3 py-2"><Sel v={o.glass} opts={GLASS} oc={(v) => patchOpening(o, { glass: v })} /></td>
                      <td className="px-2 py-2"><button onClick={() => removeOpening(o.id)} className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button></td>
                    </tr>
                  ))}
                  {openings.length === 0 && <tr><td colSpan="9" className="text-center py-8 text-[var(--ink-3)]">No openings yet — add the first.</td></tr>}
                </tbody>
                {openings.length > 0 && (
                  <tfoot><tr className="border-t-2 border-[var(--border)] font-semibold">
                    <td className="px-3 py-2" colSpan="5">Total area</td>
                    <td className="px-3 py-2 text-right font-mono">{totalArea.toFixed(2)} sqft</td>
                    <td colSpan="3"></td>
                  </tr></tfoot>
                )}
              </table>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Topbar title="D&W Site Surveys" subtitle={`${surveys.length} surveys`} onAdd={newSurvey} addLabel="New Survey" />
      <div className="p-6" data-testid="dwsurvey-page">
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[var(--surface-2)]">
              <tr className="text-[11px] uppercase tracking-wider text-[var(--ink-3)]">
                <th className="text-left font-semibold px-4 py-2.5">Survey</th>
                <th className="text-left font-semibold px-4 py-2.5">Customer</th>
                <th className="text-left font-semibold px-4 py-2.5">Date</th>
                <th className="text-left font-semibold px-4 py-2.5">Status</th>
              </tr>
            </thead>
            <tbody>
              {surveys.map((s) => (
                <tr key={s.id} onClick={() => openSurvey(s.id)} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50 cursor-pointer">
                  <td className="px-4 py-3 font-mono text-xs">{s.survey_id}</td>
                  <td className="px-4 py-3 font-medium">{s.customer || <span className="text-[var(--ink-3)]">Untitled</span>}</td>
                  <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(s.date)}</td>
                  <td className="px-4 py-3 text-[var(--ink-2)]">{s.status}</td>
                </tr>
              ))}
              {surveys.length === 0 && <tr><td colSpan="4" className="text-center py-10 text-[var(--ink-3)]">No surveys yet</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function F({ l, v, oc, t = "text", cls = "" }) {
  return (
    <div className={cls}>
      <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">{l}</label>
      <input type={t} value={v ?? ""} onChange={(e) => oc(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)]" />
    </div>
  );
}
function Inp({ v, oc, t = "text", right }) {
  return <input type={t} value={v ?? ""} onChange={(e) => oc(e.target.value)} className={`w-full px-2 py-1 rounded border border-[var(--border)] bg-white text-xs outline-none ${right ? "text-right font-mono" : ""}`} />;
}
function Sel({ v, opts, oc }) {
  return <select value={v} onChange={(e) => oc(e.target.value)} className="w-full px-2 py-1 rounded border border-[var(--border)] bg-white text-xs">{opts.map((o) => <option key={o}>{o}</option>)}</select>;
}
