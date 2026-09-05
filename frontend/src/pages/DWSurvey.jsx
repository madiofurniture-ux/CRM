import { useEffect, useState, useMemo } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { X, Trash2, Plus, ChevronLeft, FileText, Camera, ImageOff } from "lucide-react";
import { shrinkImage, dataUrlKb } from "@/lib/image";

const TYPES = ["Window", "Door", "Sliding", "French Door", "Ventilator", "Partition"];
const FRAMES = ["uPVC", "Aluminium", "Wood", "MS", "WPC"];
const GLASS = ["Single", "Double (DGU)", "Toughened", "Frosted", "Tinted", "None"];
const HANDLE_POSITIONS = ["", "RHS", "LHS"];   // "" = N/A (e.g. fixed/ventilator openings)

// W and H captured in INCHES; area is square feet.
const area = (o) => {
  const w = +o.w || 0, h = +o.h || 0, q = +o.qty || 0;
  return w > 0 && h > 0 ? +((w * h * (q || 1)) / 144).toFixed(2) : 0;
};

export default function DWSurvey() {
  const [surveys, setSurveys] = useState([]);
  const [openId, setOpenId] = useState(null);   // survey.id being edited, null = list
  const [openings, setOpenings] = useState([]);
  const [busyPhoto, setBusyPhoto] = useState(false);
  const [creatingSurvey, setCreatingSurvey] = useState(false);
  const [addingOpening, setAddingOpening] = useState(false);

  const loadList = () => api.get("/dw-surveys").then((r) => setSurveys(r.data));
  useEffect(() => { loadList(); }, []);

  const current = surveys.find((s) => s.id === openId);
  const loadOpenings = (sid) => api.get("/dw-openings").then((r) => setOpenings(r.data.filter((o) => o.survey_id === sid)));

  const openSurvey = (sid) => { setOpenId(sid); loadOpenings(sid); };

  const newSurvey = async () => {
    if (creatingSurvey) return;
    setCreatingSurvey(true);
    try {
      const { data } = await api.post("/dw-surveys", { customer: "", phone: "", site_address: "" });
      await loadList();
      openSurvey(data.id);
    } catch { toast.error("Could not create survey"); }
    finally { setCreatingSurvey(false); }
  };

  const patchSurvey = async (changes) => {
    setSurveys((p) => p.map((s) => s.id === openId ? { ...s, ...changes } : s));
    try { await api.put(`/dw-surveys/${openId}`, { ...current, ...changes }); }
    catch { toast.error("Update failed"); }
  };

  // Site photos: shrink on-device, then persist with the survey. Multiple files
  // are handled in one go because engineers usually shoot a burst per elevation.
  const addSitePhotos = async (fileList, inputEl) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setBusyPhoto(true);
    try {
      const shrunk = [];
      for (const f of files) {
        try { shrunk.push(await shrinkImage(f)); }
        catch { toast.error(`Skipped ${f.name || "a file"} — not a readable image`); }
      }
      if (shrunk.length) {
        await patchSurvey({ photos: [...(current.photos || []), ...shrunk] });
        toast.success(`${shrunk.length} photo${shrunk.length > 1 ? "s" : ""} added`);
      }
    } finally {
      setBusyPhoto(false);
      if (inputEl) inputEl.value = "";   // allow re-picking the same file
    }
  };

  const removeSitePhoto = async (idx) => {
    const next = (current.photos || []).filter((_, i) => i !== idx);
    await patchSurvey({ photos: next });
  };

  // One photo per opening, so a fitter can see the exact window being replaced.
  const setOpeningPhoto = async (o, file, inputEl) => {
    if (!file) return;
    try {
      const url = await shrinkImage(file, 800, 0.7);
      await patchOpening(o, { image_url: url });
      toast.success("Opening photo saved");
    } catch (e) {
      toast.error(e.message || "Could not read that image");
    } finally {
      if (inputEl) inputEl.value = "";
    }
  };

  const addOpening = async () => {
    if (addingOpening) return;
    setAddingOpening(true);
    try {
      const { data } = await api.post("/dw-openings", { survey_id: openId, room: "", type: "Window", w: 0, h: 0, qty: 1, frame: "uPVC", glass: "Single", mesh: false, handle_position: "" });
      setOpenings((p) => [...p, data]);
    } catch { toast.error("Could not add opening"); }
    finally { setAddingOpening(false); }
  };
  const patchOpening = async (o, changes) => {
    const merged = { ...o, ...changes };
    merged.area = area(merged);
    setOpenings((p) => p.map((x) => x.id === o.id ? merged : x));
    try { await api.put(`/dw-openings/${o.id}`, merged); } catch { toast.error("Update failed"); }
  };
  const removeOpening = async (id) => { await api.delete(`/dw-openings/${id}`); setOpenings((p) => p.filter((x) => x.id !== id)); };

  const removeSurvey = async (s, e) => {
    e?.stopPropagation();
    if (!window.confirm(`Delete survey ${s.survey_id}${s.customer ? ` (${s.customer})` : ""}? This also removes its openings.`)) return;
    try {
      await api.delete(`/dw-surveys/${s.id}`);
      toast.success("Survey deleted");
      if (openId === s.id) setOpenId(null);
      loadList();
    } catch {
      toast.error("Delete failed");
    }
  };

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
          <div className="flex items-center justify-between">
            <button onClick={() => { setOpenId(null); loadList(); }} className="text-sm text-[var(--ink-2)] inline-flex items-center gap-1"><ChevronLeft size={14} /> All surveys</button>
            <button
              onClick={(e) => removeSurvey(current, e)}
              className="text-sm text-[var(--danger)] inline-flex items-center gap-1 hover:bg-[var(--danger-soft)] px-2 py-1 rounded-lg"
              data-testid="dws-delete-survey"
            >
              <Trash2 size={14} /> Delete survey
            </button>
          </div>

          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 grid grid-cols-2 md:grid-cols-4 gap-4">
            <F l="Customer" v={current.customer} oc={(v) => patchSurvey({ customer: v })} />
            <F l="Phone" v={current.phone} oc={(v) => patchSurvey({ phone: v })} />
            <F l="Site address" v={current.site_address} oc={(v) => patchSurvey({ site_address: v })} cls="col-span-2" />

            {/* Site remarks — free-text notes from the visit */}
            <div className="col-span-2 md:col-span-4">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-3)] block mb-1">
                Site remarks
              </label>
              <textarea
                rows={3}
                data-testid="dws-remarks"
                value={current.remarks ?? ""}
                onChange={(e) => patchSurvey({ remarks: e.target.value })}
                placeholder="Access, scaffolding, existing frames, deadlines, anything the fitter must know…"
                className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)] resize-y"
              />
            </div>
          </div>

          {/* ── Site photos ─────────────────────────────────────────── */}
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="font-heading font-semibold">Site photos</div>
                <div className="text-xs text-[var(--ink-3)]">
                  {(current.photos || []).length} captured · shrunk automatically before saving
                </div>
              </div>
              <label className="btn-ghost cursor-pointer" data-testid="dws-add-photo">
                <Camera size={14} /> {busyPhoto ? "Adding…" : "Add photo"}
                <input
                  type="file"
                  accept="image/*"
                  capture="environment"
                  multiple
                  className="hidden"
                  onChange={(e) => addSitePhotos(e.target.files, e.target)}
                />
              </label>
            </div>

            {(current.photos || []).length === 0 ? (
              <div className="text-sm text-[var(--ink-3)] flex items-center gap-2 py-4">
                <ImageOff size={15} /> No photos yet — tap “Add photo” to capture the site.
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                {(current.photos || []).map((p, i) => (
                  <div key={i} className="relative group rounded-lg overflow-hidden border border-[var(--border)]">
                    <img src={p} alt={`Site photo ${i + 1}`} className="w-full h-28 object-cover" />
                    <div className="absolute bottom-0 inset-x-0 bg-black/55 text-white text-[10px] px-1.5 py-0.5">
                      {dataUrlKb(p)} KB
                    </div>
                    <button
                      onClick={() => removeSitePhoto(i)}
                      title="Remove photo"
                      className="absolute top-1 right-1 p-1 rounded bg-black/60 text-white opacity-0 group-hover:opacity-100 transition"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="p-4 border-b border-[var(--border-light)] flex items-center justify-between">
              <div className="font-heading font-semibold">Openings</div>
              <button onClick={addOpening} disabled={addingOpening} className="btn-ghost disabled:opacity-60"><Plus size={14} /> {addingOpening ? "Adding…" : "Add opening"}</button>
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
                    <th className="text-left font-semibold px-3 py-2">Handle</th>
                    <th className="text-left font-semibold px-3 py-2">Notes</th>
                    <th className="text-center font-semibold px-3 py-2">Photo</th>
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
                      <td className="px-3 py-2">
                        <select value={o.handle_position || ""} onChange={(e) => patchOpening(o, { handle_position: e.target.value })} className="w-full px-2 py-1 rounded border border-[var(--border)] bg-white text-xs">
                          {HANDLE_POSITIONS.map((h) => <option key={h} value={h}>{h || "N/A"}</option>)}
                        </select>
                      </td>
                      <td className="px-3 py-2 min-w-[150px]">
                        <Inp v={o.notes} oc={(v) => patchOpening(o, { notes: v })} />
                      </td>
                      <td className="px-3 py-2 text-center">
                        {o.image_url ? (
                          <div className="relative inline-block group">
                            <img src={o.image_url} alt="" className="w-12 h-9 object-cover rounded border border-[var(--border)]" />
                            <button
                              onClick={() => patchOpening(o, { image_url: "" })}
                              title="Remove photo"
                              className="absolute -top-1.5 -right-1.5 p-0.5 rounded-full bg-black/70 text-white opacity-0 group-hover:opacity-100 transition"
                            >
                              <X size={10} />
                            </button>
                          </div>
                        ) : (
                          <label className="cursor-pointer inline-flex items-center justify-center w-12 h-9 rounded border border-dashed border-[var(--border)] text-[var(--ink-3)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
                                 title="Capture this opening">
                            <Camera size={13} />
                            <input type="file" accept="image/*" capture="environment" className="hidden"
                                   onChange={(e) => setOpeningPhoto(o, e.target.files?.[0], e.target)} />
                          </label>
                        )}
                      </td>
                      <td className="px-2 py-2"><button onClick={() => removeOpening(o.id)} className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={13} /></button></td>
                    </tr>
                  ))}
                  {openings.length === 0 && <tr><td colSpan="11" className="text-center py-8 text-[var(--ink-3)]">No openings yet — add the first.</td></tr>}
                </tbody>
                {openings.length > 0 && (
                  <tfoot><tr className="border-t-2 border-[var(--border)] font-semibold">
                    <td className="px-3 py-2" colSpan="5">Total area</td>
                    <td className="px-3 py-2 text-right font-mono">{totalArea.toFixed(2)} sqft</td>
                    <td colSpan="5"></td>
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
                <th className="w-10"></th>
              </tr>
            </thead>
            <tbody>
              {surveys.map((s) => (
                <tr key={s.id} onClick={() => openSurvey(s.id)} className="border-t border-[var(--border-light)] hover:bg-[var(--surface-2)]/50 cursor-pointer">
                  <td className="px-4 py-3 font-mono text-xs">{s.survey_id}</td>
                  <td className="px-4 py-3 font-medium">{s.customer || <span className="text-[var(--ink-3)]">Untitled</span>}</td>
                  <td className="px-4 py-3 text-[var(--ink-2)]">{fmtDate(s.date)}</td>
                  <td className="px-4 py-3 text-[var(--ink-2)]">{s.status}</td>
                  <td className="px-2 py-3">
                    <button
                      onClick={(e) => removeSurvey(s, e)}
                      className="p-1.5 rounded-md hover:bg-[var(--danger-soft)] text-[var(--danger)]"
                      title="Delete survey"
                      data-testid={`dws-delete-${s.id}`}
                    >
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
              {surveys.length === 0 && <tr><td colSpan="5" className="text-center py-10 text-[var(--ink-3)]">No surveys yet</td></tr>}
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
