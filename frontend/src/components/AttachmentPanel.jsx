import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { Camera, FileText, Image as ImageIcon, Trash2, Upload } from "lucide-react";

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"];
const CATEGORIES = ["Site Photo", "Drawing", "Measurement", "Quotation", "Invoice", "PO",
  "Payment Proof", "Customer Reference", "Installation Photo", "Warranty", "Other"];

// Files are private: they are fetched with the user's token from
// GET /documents/{id}/file and shown through an object URL, never linked
// directly (there is no public file URL any more).
async function fileBlobUrl(doc) {
  const { data } = await api.get(`/documents/${doc.id}/file`, { responseType: "blob", skipCache: true });
  return URL.createObjectURL(data);
}

function Thumb({ doc }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let url = "";
    let alive = true;
    fileBlobUrl(doc).then((u) => { url = u; if (alive) setSrc(u); }).catch(() => {});
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [doc.id]); // eslint-disable-line
  return src
    ? <img src={src} alt={doc.file_name} className="w-full h-24 object-cover" />
    : <div className="w-full h-24 bg-[var(--surface-2)] flex items-center justify-center text-[10px] text-[var(--ink-3)]">Loading…</div>;
}

async function openDoc(doc) {
  // Open the tab synchronously (popup blockers), then point it at the blob.
  const win = window.open("", "_blank");
  try {
    const url = await fileBlobUrl(doc);
    if (win) win.location.href = url; else window.location.href = url;
  } catch (e) {
    if (win) win.close();
    toast.error(e.response?.status === 404 ? "File is no longer available on the server" : "Could not open file");
  }
}

/**
 * Drag-drop attachments/photos for a lead/quote/project/architect/sale record.
 * Mirrors LogTimeline's props: <AttachmentPanel entity="quote" itemId={q.id}/>.
 */
export default function AttachmentPanel({ entity, itemId, defaultCategory = "Site Photo" }) {
  const [docs, setDocs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [category, setCategory] = useState(defaultCategory);
  const inputRef = useRef(null);
  const cameraRef = useRef(null);

  const load = async () => {
    // Query string inlined + skipCache: lib/api.js caches GETs by URL only,
    // so `params` would make every record share one cached attachment list.
    const qs = `entity_type=${encodeURIComponent(entity)}&entity_id=${encodeURIComponent(itemId)}`;
    try {
      const { data } = await api.get(`/documents?${qs}`, { skipCache: true });
      setDocs(data);
    } catch {
      setDocs([]);
    }
  };
  useEffect(() => { if (itemId) load(); }, [entity, itemId]); // eslint-disable-line

  const upload = async (files) => {
    if (!files?.length || busy) return;
    setBusy(true);
    try {
      for (const file of files) {
        const form = new FormData();
        form.append("entity_type", entity);
        form.append("entity_id", itemId);
        form.append("category", category);
        form.append("file", file);
        await api.post("/documents", form);
      }
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (doc) => {
    if (!window.confirm(`Delete "${doc.file_name}"?`)) return;
    try {
      await api.delete(`/documents/${doc.id}`);
      setDocs((p) => p.filter((d) => d.id !== doc.id));
    } catch {
      toast.error("Delete failed");
    }
  };

  const images = docs.filter((d) => IMAGE_TYPES.includes(d.content_type));
  const files = docs.filter((d) => !IMAGE_TYPES.includes(d.content_type));

  return (
    <div className="bg-[var(--surface)] border border-blue-100/80 rounded-2xl p-4 space-y-3" data-testid="attachment-panel">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); upload(Array.from(e.dataTransfer.files)); }}
        onClick={() => inputRef.current?.click()}
        className={`flex items-center justify-center gap-2 border-2 border-dashed rounded-xl py-6 cursor-pointer text-sm text-[var(--ink-3)] transition ${dragOver ? "border-[var(--brand)] bg-[var(--brand-soft)]" : "border-[var(--border)]"}`}
        data-testid="attachment-dropzone"
      >
        <Upload size={16} />
        {busy ? "Uploading…" : "Drag files here or click to upload"}
        <input
          ref={inputRef} type="file" multiple hidden
          onChange={(e) => { upload(Array.from(e.target.files)); e.target.value = ""; }}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select value={category} onChange={(e) => setCategory(e.target.value)}
          className="px-2 py-1.5 rounded-lg border border-[var(--border)] bg-white text-xs" aria-label="Attachment type">
          {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
        </select>
        <button type="button" onClick={() => cameraRef.current?.click()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)] text-xs font-medium hover:bg-[var(--surface-2)]"
          data-testid="attachment-camera">
          <Camera size={14} /> Take photo
        </button>
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden
          onChange={(e) => { upload(Array.from(e.target.files)); e.target.value = ""; }} />
      </div>

      {images.length > 0 && (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
          {images.map((d) => (
            <div key={d.id} className="relative group rounded-lg overflow-hidden border border-[var(--border-light)]">
              <button type="button" onClick={() => openDoc(d)} className="block w-full" title={d.category || d.file_name}>
                <Thumb doc={d} />
              </button>
              <button
                onClick={() => remove(d)}
                className="absolute top-1 right-1 p-1 rounded-md bg-black/50 text-white sm:opacity-0 sm:group-hover:opacity-100"
                title="Delete"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {files.length > 0 && (
        <div className="space-y-1">
          {files.map((d) => (
            <div key={d.id} className="flex items-center gap-2 text-sm border-t border-[var(--border-light)] pt-2 first:border-0 first:pt-0">
              <FileText size={14} className="text-[var(--ink-3)] shrink-0" />
              <button type="button" onClick={() => openDoc(d)} className="flex-1 truncate text-left hover:underline">{d.file_name}</button>
              {d.category && <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--surface-2)] text-[var(--ink-2)]">{d.category}</span>}
              <span className="text-[11px] text-[var(--ink-3)]">{fmtDate(d.uploaded_at)}</span>
              <button onClick={() => remove(d)} className="p-1 rounded hover:bg-[var(--danger-soft)] text-[var(--danger)]"><Trash2 size={12} /></button>
            </div>
          ))}
        </div>
      )}

      {docs.length === 0 && (
        <div className="text-sm text-[var(--ink-3)] flex items-center gap-1.5 justify-center py-1">
          <ImageIcon size={14} /> No attachments yet.
        </div>
      )}
    </div>
  );
}
