import { useEffect, useRef, useState } from "react";
import Topbar from "@/components/Topbar";
import api from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { Hash, Send, AtSign, MessageCircle, Users } from "lucide-react";

const POLL_MS = 15000;

export default function Discussions() {
  const { user } = useAuth();
  const [mode, setMode] = useState("channels"); // "channels" | "dms"

  // ---- channels ----
  const [channels, setChannels] = useState(["General"]);
  const [channel, setChannel] = useState("General");
  const [posts, setPosts] = useState([]);
  const [replyTo, setReplyTo] = useState(null);

  // ---- direct messages ----
  const [conversations, setConversations] = useState([]);
  const [activeDm, setActiveDm] = useState(null); // { id, name }
  const [dmMessages, setDmMessages] = useState([]);

  const [users, setUsers] = useState([]);
  const [text, setText] = useState("");
  const [mentionQuery, setMentionQuery] = useState(null);
  const bottomRef = useRef(null);

  const loadChannels = async () => {
    const { data } = await api.get("/discussions/channels");
    setChannels(data);
  };
  const loadPosts = async () => {
    const { data } = await api.get("/discussions", { params: { channel } });
    setPosts(data);
  };
  const loadConversations = async () => {
    const { data } = await api.get("/discussions/dms");
    setConversations(data);
  };
  const loadDmMessages = async (otherId) => {
    const { data } = await api.get(`/discussions/dm/${otherId}`);
    setDmMessages(data);
  };

  useEffect(() => { api.get("/users/directory").then(({ data }) => setUsers(data)).catch(() => {}); }, []);

  useEffect(() => {
    if (mode !== "channels") return;
    loadChannels();
  }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (mode !== "channels") return;
    loadPosts();
    const t = setInterval(loadPosts, POLL_MS);
    return () => clearInterval(t);
  }, [mode, channel]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (mode !== "dms") return;
    loadConversations();
    const t = setInterval(loadConversations, POLL_MS);
    return () => clearInterval(t);
  }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (mode !== "dms" || !activeDm) return;
    loadDmMessages(activeDm.id);
    const t = setInterval(() => loadDmMessages(activeDm.id), POLL_MS);
    return () => clearInterval(t);
  }, [mode, activeDm]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [posts.length, dmMessages.length]);

  const mentionMatches = mentionQuery === null ? [] :
    users.filter((u) => u.name.toLowerCase().includes(mentionQuery.toLowerCase())).slice(0, 6);

  const onTextChange = (v) => {
    setText(v);
    const m = v.match(/@(\w*)$/);
    setMentionQuery(mode === "channels" ? (m ? m[1] : null) : null);
  };
  const pickMention = (name) => {
    setText((t) => t.replace(/@(\w*)$/, `@${name} `));
    setMentionQuery(null);
  };

  const send = async () => {
    const body = text.trim();
    if (!body) return;
    if (mode === "dms") {
      if (!activeDm) return;
      await api.post(`/discussions/dm/${activeDm.id}`, { text: body });
      setText("");
      loadDmMessages(activeDm.id);
      loadConversations();
      return;
    }
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

  const openDm = (otherId, otherName) => {
    setActiveDm({ id: otherId, name: otherName });
    setText("");
  };

  const topLevel = posts.filter((p) => !p.parent_id);
  const repliesOf = (id) => posts.filter((p) => p.parent_id === id);

  // Contact list for Direct Messages: everyone in the directory, with a
  // last-message preview for whoever there's already a conversation with.
  const contactList = users
    .filter((u) => u.id !== user?.id)
    .map((u) => ({ ...u, ...conversations.find((c) => c.other_user_id === u.id) }))
    .sort((a, b) => (b.last_at || "").localeCompare(a.last_at || ""));

  return (
    <div className="flex flex-col h-screen">
      <Topbar title={mode === "channels" ? "Team Board" : "Direct Messages"} />

      <div className="flex items-center gap-1 px-3 py-2 border-b border-[var(--border)] bg-[var(--surface)] shrink-0">
        <button onClick={() => setMode("channels")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold ${
            mode === "channels" ? "bg-[var(--brand-soft)] text-[var(--brand)]" : "text-[var(--ink-2)] hover:bg-[var(--surface-2)]"}`}
          data-testid="mode-channels">
          <Users size={13} /> Channels
        </button>
        <button onClick={() => setMode("dms")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold ${
            mode === "dms" ? "bg-[var(--brand-soft)] text-[var(--brand)]" : "text-[var(--ink-2)] hover:bg-[var(--surface-2)]"}`}
          data-testid="mode-dms">
          <MessageCircle size={13} /> Direct Messages
        </button>
      </div>

      {mode === "channels" ? (
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
      ) : (
        // WhatsApp-style layout: contact list on the left, chat bubbles on the right.
        <div className="flex flex-1 min-h-0">
          <div className="w-64 border-r border-[var(--border)] bg-[var(--surface)] overflow-y-auto shrink-0">
            {contactList.length === 0 && (
              <div className="text-xs text-[var(--ink-3)] text-center py-8 px-3">No colleagues found.</div>
            )}
            {contactList.map((c) => (
              <button
                key={c.id}
                onClick={() => openDm(c.id, c.name)}
                data-testid={`dm-contact-${c.id}`}
                className={`w-full text-left px-3 py-2.5 border-b border-[var(--border-light)] flex items-center gap-2.5 ${
                  activeDm?.id === c.id ? "bg-[var(--brand-soft)]" : "hover:bg-[var(--surface-2)]"}`}
              >
                <div className="w-9 h-9 rounded-full bg-[var(--brand)] text-white flex items-center justify-center text-xs font-bold shrink-0">
                  {c.name?.slice(0, 2).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-[var(--ink)] truncate">{c.name}</div>
                  <div className="text-xs text-[var(--ink-3)] truncate">{c.last_text || "No messages yet"}</div>
                </div>
              </button>
            ))}
          </div>

          <div className="flex-1 flex flex-col min-w-0">
            {!activeDm ? (
              <div className="flex-1 flex items-center justify-center text-sm text-[var(--ink-3)]">
                Pick a colleague to start a conversation.
              </div>
            ) : (
              <>
                <div className="px-4 py-2.5 border-b border-[var(--border)] font-semibold text-sm text-[var(--ink)]">
                  {activeDm.name}
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-2 bg-[var(--surface-2)]/40">
                  {dmMessages.length === 0 && (
                    <div className="text-sm text-[var(--ink-3)] text-center py-10">No messages yet. Say hello.</div>
                  )}
                  {dmMessages.map((m) => {
                    const mine = m.author_id === user?.id;
                    return (
                      <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`} data-testid="dm-bubble">
                        <div className={`max-w-[70%] px-3 py-2 text-sm whitespace-pre-wrap ${
                          mine
                            ? "bg-[var(--brand)] text-white rounded-2xl rounded-br-sm"
                            : "bg-white border border-[var(--border-light)] text-[var(--ink)] rounded-2xl rounded-bl-sm"}`}>
                          {m.text}
                          <div className={`text-[10px] mt-1 ${mine ? "text-white/70" : "text-[var(--ink-3)]"}`}>{fmtDate(m.created_at)}</div>
                        </div>
                      </div>
                    );
                  })}
                  <div ref={bottomRef} />
                </div>
                <div className="border-t border-[var(--border)] p-3">
                  <div className="flex gap-2">
                    <input
                      value={text}
                      onChange={(e) => onTextChange(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                      placeholder={`Message ${activeDm.name}`}
                      className="flex-1 border border-[var(--border)] rounded-lg px-3 py-2 text-sm"
                      data-testid="dm-input"
                    />
                    <button onClick={send} className="btn-primary px-3" data-testid="dm-send"><Send size={15} /></button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
