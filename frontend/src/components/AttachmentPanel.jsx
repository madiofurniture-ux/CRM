import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { toast } from "sonner";
import { FileText, Image as ImageIcon, Trash2, Upload } from "lucide-react";

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"];

/**
 * Drag-drop attachments/photos for a lead/quote/project/architect/sale record.
 * Mirrors LogTimeline's props: <AttachmentPanel entity="quote" itemId={q.id}/>.
 */
export default function AttachmentPanel({ entity, itemId }) {
  const [docs, setDocs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const load = async () => {
    const { data } = await api.get("/documents", { params: { entity_type: entity, entity_id: itemId } });
    setDocs(data);
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

      {images.length > 0 && (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
          {images.map((d) => (
            <div key={d.id} className="relative group rounded-lg overflow-hidden border border-[var(--border-light)]">
              <a href={d.file_url} target="_blank" rel="noreferrer">
                <img src={d.file_url} alt={d.file_name} className="w-full h-24 object-cover" />
              </a>
              <button
                onClick={() => remove(d)}
                className="absolute top-1 right-1 p-1 rounded-md bg-black/50 text-white opacity-0 group-hover:opacity-100"
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
              <a href={d.file_url} target="_blank" rel="noreferrer" className="flex-1 truncate hover:underline">{d.file_name}</a>
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
