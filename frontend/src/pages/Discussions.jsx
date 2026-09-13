import { useEffect, useRef, useState } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { Hash, Send, AtSign } from "lucide-react";

const POLL_MS = 15000;

export default function Discussions() {
  const [channels, setChannels] = useState(["General"]);
  const [channel, setChannel] = useState("General");
  const [posts, setPosts] = useState([]);
  const [users, setUsers] = useState([]);
  const [text, setText] = useState("");
  const [mentionQuery, setMentionQuery] = useState(null);
  const [replyTo, setReplyTo] = useState(null);
  const bottomRef = useRef(null);

  const loadChannels = async () => {
    const { data } = await api.get("/discussions/channels");
    setChannels(data);
  };
  const loadPosts = async () => {
    const { data } = await api.get("/discussions", { params: { channel } });
    setPosts(data);
  };
  useEffect(() => { api.get("/users/directory").then(({ data }) => setUsers(data)).catch(() => {}); }, []);
  useEffect(() => { loadChannels(); }, []);
  useEffect(() => {
    loadPosts();
    const t = setInterval(loadPosts, POLL_MS);
    return () => clearInterval(t);
  }, [channel]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [posts.length]);

  const mentionMatches = mentionQuery === null ? [] :
    users.filter((u) => u.name.toLowerCase().includes(mentionQuery.toLowerCase())).slice(0, 6);

  const onTextChange = (v) => {
    setText(v);
    const m = v.match(/@(\w*)$/);
    setMentionQuery(m ? m[1] : null);
  };
  const pickMention = (name) => {
    setText((t) => t.replace(/@(\w*)$/, `@${name} `));
    setMentionQuery(null);
  };

  const send = async () => {
    const body = text.trim();
    if (!body) return;
    const mentions = users.filter((u) => body.includes(`@${u.name}`)).map((u) => u.id);
    if (replyTo) {
      await api.post(`/discussions/${replyTo}/reply`, { channel, text: body, mentions });
    } else {
      await api.post("/discussions", { channel, text: body, mentions });
    }
    setText("");
    setReplyTo(null);
    loadPosts();
    loadChannels();
  };

  const topLevel = posts.filter((p) => !p.parent_id);
  const repliesOf = (id) => posts.filter((p) => p.parent_id === id);

  return (
    <div className="flex flex-col h-screen">
      <Topbar title="Team Board" />
      <div className="flex flex-1 min-h-0">
        <div className="w-48 border-r border-[var(--border)] bg-[var(--surface)] p-3 space-y-1 shrink-0 overflow-y-auto">
          {channels.map((c) => (
            <button key={c} onClick={() => setChannel(c)}
              className={`w-full text-left px-2.5 py-1.5 rounded-lg text-sm flex items-center gap-1.5 ${
                channel === c ? "bg-[var(--brand-soft)] text-[var(--brand)] font-semibold" : "text-[var(--ink-2)] hover:bg-[var(--surface-2)]"}`}>
              <Hash size={13} /> {c}
            </button>
          ))}
        </div>

        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {topLevel.length === 0 && (
              <div className="text-sm text-[var(--ink-3)] text-center py-10">No posts in #{channel} yet. Say hello.</div>
            )}
            {topLevel.map((p) => (
              <div key={p.id} className="bg-[var(--surface)] border border-[var(--border-light)] rounded-xl p-3" data-testid="discussion-post">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold text-sm text-[var(--ink)]">{p.author_name}</span>
                  <span className="text-[11px] text-[var(--ink-3)]">{fmtDate(p.created_at)}</span>
                </div>
                <div className="text-sm text-[var(--ink-2)] whitespace-pre-wrap mt-0.5">{p.text}</div>
                {repliesOf(p.id).map((r) => (
                  <div key={r.id} className="mt-2 ml-4 pl-3 border-l-2 border-[var(--border-light)]">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="font-semibold text-xs text-[var(--ink)]">{r.author_name}</span>
                      <span className="text-[10px] text-[var(--ink-3)]">{fmtDate(r.created_at)}</span>
                    </div>
                    <div className="text-xs text-[var(--ink-2)] whitespace-pre-wrap">{r.text}</div>
                  </div>
                ))}
                <button onClick={() => setReplyTo(p.id)} className="text-[11px] text-[var(--brand)] mt-1.5 hover:underline">Reply</button>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-[var(--border)] p-3 relative">
            {replyTo && (
              <div className="text-[11px] text-[var(--ink-3)] mb-1 flex items-center gap-2">
                Replying to a post <button onClick={() => setReplyTo(null)} className="text-[var(--danger)] hover:underline">cancel</button>
              </div>
            )}
            {mentionMatches.length > 0 && (
              <div className="absolute bottom-full mb-1 left-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg shadow-lg overflow-hidden">
                {mentionMatches.map((u) => (
                  <button key={u.id} onClick={() => pickMention(u.name)}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm hover:bg-[var(--surface-2)] w-full text-left">
                    <AtSign size={12} /> {u.name}
                  </button>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <input
                value={text}
                onChange={(e) => onTextChange(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                placeholder={`Message #${channel}`}
                className="flex-1 border border-[var(--border)] rounded-lg px-3 py-2 text-sm"
                data-testid="discussion-input"
              />
              <button onClick={send} className="btn-primary px-3" data-testid="discussion-send"><Send size={15} /></button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
