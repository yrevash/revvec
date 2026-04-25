import { useEffect, useMemo, useRef, useState } from "react";
import { Send, Loader2 } from "lucide-react";
import { PersonaPicker } from "./components/PersonaPicker";
import { SourcePanel } from "./components/SourcePanel";
import { MicButton } from "./components/MicButton";
import { ChatSidebar } from "./components/ChatSidebar";
import { MessageThread } from "./components/MessageThread";
import { Logo } from "./components/Logo";
import { UserProfilePanel } from "./components/UserProfilePanel";
import { health, streamQuery, voiceStream } from "./lib/api";
import type { Persona, HealthResponse, QueryResponse, UserProfile } from "./lib/api";
import {
  activeProfile,
  clearProfile,
  EMPTY_PROFILE,
  isProfileSet,
  loadProfile,
  saveProfile,
} from "./lib/userProfile";
import {
  buildHistory,
  loadActiveId,
  loadChats,
  newChat,
  newMessage,
  saveActiveId,
  saveChats,
  titleFrom,
  type Chat,
  type Message,
} from "./lib/chatStore";

export default function App() {
  const [chats, setChats] = useState<Chat[]>(() => {
    const stored = loadChats();
    return stored.length ? stored : [newChat("maintenance")];
  });
  const [activeId, setActiveId] = useState<string | null>(() => {
    const stored = loadActiveId();
    if (stored) return stored;
    return null;
  });

  // Ensure we always have a selected chat
  useEffect(() => {
    if (!activeId && chats.length > 0) {
      setActiveId(chats[0].id);
    }
  }, [activeId, chats]);

  // Persist
  useEffect(() => {
    saveChats(chats);
  }, [chats]);
  useEffect(() => {
    saveActiveId(activeId);
  }, [activeId]);

  const active = useMemo(
    () => chats.find((c) => c.id === activeId) ?? null,
    [chats, activeId],
  );

  const persona: Persona = active?.persona ?? "maintenance";

  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [srv, setSrv] = useState<HealthResponse | null>(null);
  const [openEntityId, setOpenEntityId] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [profile, setProfile] = useState<UserProfile>(() => loadProfile());
  const [profileOpen, setProfileOpen] = useState(false);
  const [skipCache, setSkipCache] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const tick = () => health().then(setSrv).catch((e) => setErr(String(e)));
    tick();
    const iv = setInterval(tick, 5000);
    return () => clearInterval(iv);
  }, []);

  // ─── chat ops ─────────────────────────────────────────────────────────────

  function patchChat(chatId: string, patch: (c: Chat) => Chat) {
    setChats((prev) => prev.map((c) => (c.id === chatId ? patch(c) : c)));
  }

  function updateMessage(chatId: string, msgId: string, patch: Partial<Message>) {
    patchChat(chatId, (c) => ({
      ...c,
      messages: c.messages.map((m) => (m.id === msgId ? { ...m, ...patch } : m)),
      updatedAt: Date.now(),
    }));
  }

  function handleNewChat() {
    const c = newChat(persona);
    setChats((prev) => [c, ...prev]);
    setActiveId(c.id);
    setQ("");
    setErr(null);
    setOpenEntityId(null);
  }

  function handleDeleteChat(id: string) {
    setChats((prev) => {
      const next = prev.filter((c) => c.id !== id);
      // if we deleted all, make a fresh one
      if (next.length === 0) {
        const fresh = newChat(persona);
        setActiveId(fresh.id);
        return [fresh];
      }
      if (id === activeId) setActiveId(next[0].id);
      return next;
    });
  }

  function handleSetPersona(p: Persona) {
    if (!active) return;
    if (p === active.persona) return;
    // Empty chat: reassign persona in place.
    if (active.messages.length === 0) {
      patchChat(active.id, (c) => ({ ...c, persona: p, updatedAt: Date.now() }));
      return;
    }
    // Non-empty: start a fresh chat under the new persona so the old thread's
    // retrieval context doesn't bleed across role boundaries.
    const c = newChat(p);
    setChats((prev) => [c, ...prev]);
    setActiveId(c.id);
    setQ("");
    setErr(null);
    setOpenEntityId(null);
  }

  // ─── submit ───────────────────────────────────────────────────────────────

  async function submit(override?: string) {
    const text = (override ?? q).trim();
    if (!text || loading || !active) return;

    // snapshot chat BEFORE appending, so history only contains prior turns
    const priorChat: Chat = active;
    const userMsg = newMessage("user", text);
    const asstMsg = newMessage("assistant", "", { streaming: true });

    // apply title if this is the chat's first user message
    const isFirstTurn = priorChat.messages.filter((m) => m.role === "user").length === 0;

    patchChat(priorChat.id, (c) => ({
      ...c,
      title: isFirstTurn ? titleFrom(text) : c.title,
      messages: [...c.messages, userMsg, asstMsg],
      updatedAt: Date.now(),
    }));

    setLoading(true);
    setErr(null);
    setQ("");

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const history = buildHistory(priorChat);
    const userProfile = activeProfile(profile);

    try {
      await streamQuery(
        {
          query_text: text,
          persona: priorChat.persona,
          history,
          user_profile: userProfile,
          use_cache: !skipCache,
        },
        {
          onStart: (m) =>
            updateMessage(priorChat.id, asstMsg.id, {
              generalMode: m.general_mode,
              fromCache: m.from_cache,
              topScore: m.top_score,
            }),
          onDelta: (_delta, accum) =>
            updateMessage(priorChat.id, asstMsg.id, { content: accum }),
          onDone: (final: QueryResponse) =>
            updateMessage(priorChat.id, asstMsg.id, {
              content: final.answer,
              result: final,
              streaming: false,
            }),
          onError: (e) => setErr(String(e)),
        },
        ctrl.signal,
      );
    } catch (e) {
      const eStr = (e as Error).name === "AbortError" ? null : String(e);
      if (eStr) setErr(eStr);
      updateMessage(priorChat.id, asstMsg.id, {
        streaming: false,
        content:
          eStr ??
          "(cancelled)",
      });
    } finally {
      setLoading(false);
    }
  }

  async function recordAndAsk() {
    if (loading || listening || !active) return;
    setErr(null);
    setOpenEntityId(null);
    setQ("");
    setListening(true);

    let finalText = "";
    try {
      finalText = await voiceStream(5, {
        onPartial: (t) => setQ(t),
        onFinal: (t) => {
          finalText = t;
          setQ(t);
        },
        onError: (e) => setErr(String(e)),
      });
    } catch (e) {
      if ((e as Error).name !== "AbortError") setErr(String(e));
      setListening(false);
      return;
    } finally {
      setListening(false);
    }

    if (finalText.trim()) await submit(finalText);
  }

  // Persona-keyed suggestions, each grounded in the actual NASA Mars 2020
  // corpus so retrieval has real chunks to cite.
  const SUGGESTIONS: Record<Persona, string[]> = {
    new_hire: [
      "What is the Perseverance rover's mission?",
      "How does SuperCam work on Mars?",
      "Explain MEDA in simple terms",
      "What instruments are on Perseverance?",
    ],
    maintenance: [
      "MEDA atmospheric pressure sensor performance",
      "CMAPSS engine sensor anomaly signatures",
      "Mars 2020 entry descent landing telemetry",
      "Perseverance thermal subsystem operations",
    ],
    quality: [
      "SuperCam analysis of the Maaz formation",
      "SHERLOC and WATSON imaging in Jezero Crater",
      "Igneous rock characterization on Mars",
      "Abrasion target verification procedures",
    ],
    plant_manager: [
      "Mars 2020 mission performance summary",
      "Marshall Space Flight Center R&T highlights",
      "Perseverance science return overview",
      "Technology areas in human spaceflight",
    ],
  };

  const SUBTITLES: Record<Persona, string> = {
    new_hire: "Get oriented · everything stays on this device",
    maintenance: "Diagnose, triage, repeat · everything stays on this device",
    quality: "Verify, cite, confirm · everything stays on this device",
    plant_manager: "Plan and decide · everything stays on this device",
  };

  const suggestions = SUGGESTIONS[persona] ?? SUGGESTIONS.maintenance;
  const subtitle = SUBTITLES[persona] ?? SUBTITLES.maintenance;

  const showSuggestions = active && active.messages.length === 0 && !err && srv?.ok;

  return (
    <div className="min-h-screen flex">
      {/* Top-of-window drag strip. Covers only the LEFT sidebar width so the
          right-side source panel and main header buttons stay clickable.
          Tauri 2 macOS needs this because the traffic-light area otherwise
          has no drag surface in titleBarStyle:Overlay. */}
      <div
        data-tauri-drag-region
        className="fixed top-0 left-0 w-[260px] h-[36px] z-[100]"
      />
      <div
        data-tauri-drag-region
        className="fixed top-0 left-[260px] right-[60px] h-[28px] z-[100]"
      />
      <ChatSidebar
        chats={chats}
        activeId={activeId}
        onSelect={(id) => setActiveId(id)}
        onNew={handleNewChat}
        onDelete={handleDeleteChat}
        onOpenProfile={() => setProfileOpen(true)}
        profileActive={isProfileSet(profile)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <header
          data-tauri-drag-region
          className="flex items-center justify-between px-8 pt-5 pb-4 border-b border-surface-deep/60 backdrop-blur bg-surface/80 sticky top-0 z-10"
        >
          <div className="flex items-center gap-3">
            <Logo online={!!srv?.ok} />
            {!srv?.ok && (
              <span className="text-[11px] text-muted font-mono tracking-wide">
                connecting…
              </span>
            )}
          </div>
          <PersonaPicker active={persona} onChange={handleSetPersona} />
        </header>

        <main className="flex-1 w-full max-w-3xl mx-auto px-8 py-10 space-y-6 overflow-y-auto">
          {active && active.messages.length > 0 && (
            <MessageThread
              messages={active.messages}
              onOpenSource={(entityId) => setOpenEntityId(entityId)}
            />
          )}

          {err && (
            <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl p-4 text-sm font-mono">
              {err}
            </div>
          )}

          {showSuggestions && (
            <div className="pt-10 text-center text-muted">
              <div className="text-sm font-medium text-ink/80 mb-1">
                Ask as a {persona.replace("_", " ")}
              </div>
              <div className="text-xs text-muted mb-5">{subtitle}</div>
              <div className="flex flex-wrap justify-center gap-2">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => submit(s)}
                    className="px-3 py-1.5 text-xs bg-surface-card border border-surface-deep hover:border-accent/40 hover:text-ink rounded-full transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
        </main>

        <div className="sticky bottom-0 bg-surface/95 backdrop-blur border-t border-surface-deep/60 px-8 py-4">
          <div className="max-w-3xl mx-auto space-y-2">
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submit()}
                  placeholder={
                    listening
                      ? "listening…"
                      : "ask anything · press Enter to send"
                  }
                  className={
                    "w-full px-4 py-3 text-[15px] bg-surface-card border rounded-xl focus:outline-none focus:ring-2 transition-all " +
                    (listening
                      ? "border-accent/50 ring-2 ring-accent/20 pl-10"
                      : "border-surface-deep focus:ring-accent/30 focus:border-accent/50")
                  }
                  autoFocus
                  disabled={loading || listening}
                />
                {listening && (
                  <span className="absolute left-3.5 top-1/2 -translate-y-1/2 flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-70 animate-ping" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-accent" />
                  </span>
                )}
              </div>
              <MicButton onRecord={recordAndAsk} disabled={loading} seconds={5} />
              <button
                onClick={() => submit()}
                disabled={loading || listening || !q.trim()}
                aria-label="send message"
                className="px-4 py-3 bg-ink text-white rounded-xl hover:bg-ink-soft transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {loading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
              </button>
            </div>
            <div className="flex items-center justify-between text-[10px] text-muted font-mono">
              <span className="flex items-center gap-3">
                {listening
                  ? "recording · releases automatically after 5s"
                  : active && active.messages.length > 0
                  ? `${active.messages.length} message${active.messages.length === 1 ? "" : "s"} · history included`
                  : "start a new conversation"}
                <label className="flex items-center gap-1 cursor-pointer hover:text-ink/80 transition-colors">
                  <input
                    type="checkbox"
                    checked={skipCache}
                    onChange={(e) => setSkipCache(e.target.checked)}
                    className="w-3 h-3 accent-accent cursor-pointer"
                  />
                  skip cache
                </label>
              </span>
              <span className="flex items-center gap-1.5 flex-shrink-0">
                <span className="w-1 h-1 rounded-full bg-green-500" />
                airgapped · on-device
              </span>
            </div>
          </div>
        </div>
      </div>

      {openEntityId && (
        <SourcePanel
          entityId={openEntityId}
          onClose={() => setOpenEntityId(null)}
        />
      )}

      <UserProfilePanel
        open={profileOpen}
        initial={profile}
        onClose={() => setProfileOpen(false)}
        onSave={(next) => {
          setProfile(next);
          saveProfile(next);
          setProfileOpen(false);
        }}
        onClear={() => {
          setProfile({ ...EMPTY_PROFILE });
          clearProfile();
        }}
      />
    </div>
  );
}
