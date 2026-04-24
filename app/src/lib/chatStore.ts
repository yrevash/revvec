import type { Persona, QueryResponse } from "./api";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  result?: QueryResponse;         // full response for assistant turns
  streaming?: boolean;            // true while tokens are still arriving
  generalMode?: boolean;
  fromCache?: boolean;
  topScore?: number | null;
  createdAt: number;
}

export interface Chat {
  id: string;
  title: string;
  persona: Persona;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
}

const STORAGE_KEY = "revvec:chats:v1";
const ACTIVE_KEY = "revvec:activeChat:v1";

function uid(): string {
  return (
    Math.random().toString(36).slice(2, 10) +
    Date.now().toString(36).slice(-4)
  );
}

function tryJSON<T>(raw: string | null, fallback: T): T {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function loadChats(): Chat[] {
  if (typeof window === "undefined") return [];
  return tryJSON<Chat[]>(localStorage.getItem(STORAGE_KEY), []);
}

export function saveChats(chats: Chat[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
  } catch {
    /* quota exceeded — drop oldest and retry */
    const pruned = chats.slice(0, 40);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pruned));
  }
}

export function loadActiveId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACTIVE_KEY);
}

export function saveActiveId(id: string | null): void {
  if (typeof window === "undefined") return;
  if (id) localStorage.setItem(ACTIVE_KEY, id);
  else localStorage.removeItem(ACTIVE_KEY);
}

export function newChat(persona: Persona): Chat {
  const now = Date.now();
  return {
    id: uid(),
    title: "New conversation",
    persona,
    messages: [],
    createdAt: now,
    updatedAt: now,
  };
}

export function newMessage(
  role: "user" | "assistant",
  content: string,
  extras: Partial<Message> = {},
): Message {
  return {
    id: uid(),
    role,
    content,
    createdAt: Date.now(),
    ...extras,
  };
}

export function titleFrom(msg: string): string {
  const t = msg.trim().replace(/\s+/g, " ");
  return t.length > 44 ? t.slice(0, 44) + "…" : t || "New conversation";
}

export interface HistoryTurn {
  role: "user" | "assistant";
  content: string;
}

/** Build history to send to the LLM. Takes last K turns, capped at `maxChars`
 * characters total. Oldest turns are dropped first. The current user message
 * is NOT included — the caller adds it as `query_text`. */
export function buildHistory(
  chat: Chat,
  opts: { maxTurns?: number; maxChars?: number } = {},
): HistoryTurn[] {
  const maxTurns = opts.maxTurns ?? 6;
  const maxChars = opts.maxChars ?? 4000;

  const msgs = chat.messages
    .filter((m) => (m.role === "user" || m.role === "assistant") && !m.streaming)
    .slice(-maxTurns);

  // Budget newest-first; then reverse so the LLM reads chronologically.
  const budgeted: HistoryTurn[] = [];
  let used = 0;
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    const content = (m.content || "").trim();
    if (!content) continue;
    if (used + content.length > maxChars) break;
    used += content.length;
    budgeted.push({ role: m.role, content });
  }
  return budgeted.reverse();
}
