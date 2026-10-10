import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, X, ZoomIn, ZoomOut } from "lucide-react";
import api from "@/lib/api";
import { inrFull } from "@/lib/format";
import { dimsOf } from "./productText";

/** A product's pictures, large. Click or tap the picture to zoom into that
 * spot (again to zoom out), arrows / swipe for the next picture, Esc closes. */
export default function ProductLightbox({ item, onClose }) {
  const [images, setImages] = useState(item.thumb ? [item.thumb] : []);
  const [i, setI] = useState(0);
  const [zoom, setZoom] = useState(null);           // {x, y} in % when zoomed in
  const touch = useRef(null);

  useEffect(() => {
    if (!item.id) return;
    let live = true;
    api.get(`/virtual-items/${item.id}`, { skipCache: true })
      .then(({ data }) => { if (live && data?.images?.length) setImages(data.images); })
      .catch(() => {});
    return () => { live = false; };
  }, [item.id]);
  const go = useCallback((d) => { setZoom(null); setI((n) => (images.length ? (n + d + images.length) % images.length : 0)); }, [images.length]);
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, onClose]);

  const toggleZoom = (e) => {
    if (zoom) { setZoom(null); return; }
    const r = e.currentTarget.getBoundingClientRect();
    setZoom({ x: ((e.clientX - r.left) / r.width) * 100, y: ((e.clientY - r.top) / r.height) * 100 });
  };
  const dims = dimsOf(item);
  return (
    <div className="fixed inset-0 z-[60] bg-black/90 text-white flex flex-col" role="dialog" aria-modal="true"
         aria-label={`${item.sku} pictures`} data-testid="product-lightbox">
      <div className="flex items-center gap-3 px-4 py-3 shrink-0">
        <span className="font-mono text-xs font-semibold px-1.5 py-0.5 rounded bg-white/15">{item.sku}</span>
        <div className="min-w-0 flex-1">
          <div className="font-semibold truncate">{item.name}</div>
          <div className="text-xs text-white/70 truncate">{[dims && `📐 ${dims}`, item.mrp ? inrFull(item.mrp) : ""].filter(Boolean).join(" · ")}</div>
        </div>
        <button type="button" onClick={() => setZoom(zoom ? null : { x: 50, y: 50 })} className="p-2 rounded hover:bg-white/10" aria-label={zoom ? "Zoom out" : "Zoom in"}>
          {zoom ? <ZoomOut size={18} /> : <ZoomIn size={18} />}</button>
        <button type="button" onClick={onClose} className="p-2 rounded hover:bg-white/10" aria-label="Close" data-testid="product-lightbox-close"><X size={20} /></button>
      </div>
      <div className="relative flex-1 min-h-0 flex items-center justify-center px-2 sm:px-14 overflow-hidden"
           onTouchStart={(e) => { touch.current = e.touches[0].clientX; }}
           onTouchEnd={(e) => {
             const dx = e.changedTouches[0].clientX - (touch.current ?? e.changedTouches[0].clientX);
             if (!zoom && Math.abs(dx) > 50) go(dx < 0 ? 1 : -1);
           }}>
        {images.length ? (
          <div className="max-h-full max-w-full overflow-hidden rounded bg-white" onClick={toggleZoom}
               style={{ cursor: zoom ? "zoom-out" : "zoom-in" }}>
            <img src={images[i]} alt={item.name} className="block max-h-[78vh] max-w-full object-contain transition-transform duration-200"
                 style={zoom ? { transform: "scale(2.4)", transformOrigin: `${zoom.x}% ${zoom.y}%` } : undefined} data-testid="product-lightbox-img" />
          </div>
        ) : <div className="text-white/70 text-sm">No picture yet.</div>}
        {images.length > 1 && (
          <>
            <button type="button" onClick={() => go(-1)} className="absolute left-2 top-1/2 -translate-y-1/2 p-2 rounded-full bg-white/10 hover:bg-white/20" aria-label="Previous picture"><ChevronLeft size={22} /></button>
            <button type="button" onClick={() => go(1)} className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-full bg-white/10 hover:bg-white/20" aria-label="Next picture"><ChevronRight size={22} /></button>
          </>
        )}
      </div>
      {images.length > 1 && (
        <div className="flex justify-center gap-2 p-3 shrink-0">
          {images.map((src, n) => (
            <button key={n} type="button" onClick={() => { setZoom(null); setI(n); }} aria-label={`Picture ${n + 1}`}
                    className={`w-14 h-14 rounded bg-white p-0.5 ${n === i ? "ring-2 ring-[var(--color-primary,#2563eb)]" : "opacity-60"}`}>
              <img src={src} alt="" className="w-full h-full object-contain" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
