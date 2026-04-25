// Tiny client for the FastAPI sidecar.
// Tauri dev and prod both run the server at 127.0.0.1:8000.

const BASE = "http://127.0.0.1:8000";

export type Persona = "new_hire" | "maintenance" | "quality" | "plant_manager";

export interface Citation {
  index: number;
  entity_id: string;
  title: string;
  preview: string;
}

export interface UserProfile {
  role?: string;
  experience?: string;
  focus?: string;
  preferences?: string;
  notes?: string;
}

export interface ActianInspector {
  path: "cache" | "search" | "rrf" | "general";
  vectors: string[];
  actian_ms: number;
  rerank_ms: number;
  hits_used: number;
  top_score: number | null;
  summary: string;
  operation: string;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  from_cache: boolean;
  persona: Persona;
  retrieved: number;
  general_mode?: boolean;
  top_score?: number;
  actian?: ActianInspector;
  timings_ms: {
    cache_lookup: number;
    retrieve?: number;
    generate?: number;
    total: number;
    asr?: number;
    tts?: number;
  };
}

export interface SourceMeta {
  entity_type: string;
  title: string;
  text_preview: string;
  source_url: string;
  page: number | null;
  has_pdf: boolean;
}

export interface HealthResponse {
  ok: boolean;
  version: string;
  actian: { reachable: boolean; collection: string; points: number };
  models: { text: string; photo: string; sensor: string; llm: string; asr: string; tts: string };
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    throw new Error(`${r.status} ${r.statusText}: ${await r.text()}`);
  }
  return r.json() as Promise<T>;
}

export async function health(): Promise<HealthResponse> {
  return jsonFetch<HealthResponse>("/api/health");
}

export async function query(params: {
  query_text: string;
  persona: Persona;
  user_profile?: UserProfile;
}): Promise<QueryResponse> {
  return jsonFetch<QueryResponse>("/api/query", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function voiceQuery(
  wavBlob: Blob,
  persona: Persona,
): Promise<QueryResponse & { transcript: string; answer_audio_b64?: string }> {
  const form = new FormData();
  form.append("audio", wavBlob, "query.wav");
  form.append("persona", persona);
  const r = await fetch(BASE + "/api/voice", { method: "POST", body: form });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

/** Backend-mic voice path, avoids WKWebView getUserMedia permission issues.
 * Server records via sounddevice for `seconds`, then runs the full pipeline. */
export async function voiceLive(
  persona: Persona,
  seconds = 5,
): Promise<QueryResponse & { transcript: string; answer_audio_b64?: string }> {
  const r = await fetch(BASE + "/api/voice/live", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona, seconds }),
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export interface VoiceStreamHandlers {
  onPartial?: (text: string) => void;
  onFinal?: (text: string, asrMs: number) => void;
  onError?: (err: Error) => void;
}

/** SSE streaming mic path, partial transcripts fire every ~0.6s while recording,
 * then a single `final` event with the full transcript. */
export async function voiceStream(
  seconds: number,
  handlers: VoiceStreamHandlers,
  signal?: AbortSignal,
): Promise<string> {
  const r = await fetch(BASE + "/api/voice/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seconds }),
    signal,
  });
  if (!r.ok || !r.body) {
    const msg = r.body ? await r.text() : `${r.status} ${r.statusText}`;
    throw new Error(msg);
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalText = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const line = raw.trim();
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      try {
        const msg = JSON.parse(payload);
        if (msg.event === "partial") {
          handlers.onPartial?.(msg.text ?? "");
        } else if (msg.event === "final") {
          finalText = msg.text ?? "";
          handlers.onFinal?.(finalText, Number(msg.asr_ms) || 0);
        } else if (msg.event === "error") {
          handlers.onError?.(new Error(msg.message ?? "voice/stream error"));
        }
      } catch {
        // ignore malformed frames
      }
    }
  }
  return finalText;
}

export async function clearCache(): Promise<{ ok: boolean; deleted_count: number; error: string | null }> {
  return jsonFetch("/api/admin/cache/clear", { method: "POST" });
}

export async function sourceMeta(entityId: string): Promise<SourceMeta> {
  return jsonFetch<SourceMeta>(`/api/source/${entityId}/meta`);
}

export function sourcePdfUrl(
  entityId: string,
  page?: number | null,
  highlight?: string | null,
): string {
  const parts: string[] = [];
  if (page) parts.push(`page=${page}`);
  if (highlight) parts.push(`search=${encodeURIComponent(highlight)}`);
  const hash = parts.length ? `#${parts.join("&")}` : "";
  return `${BASE}/api/source/${entityId}/pdf${hash}`;
}

export interface StreamHandlers {
  onStart?: (meta: {
    persona: Persona;
    from_cache: boolean;
    general_mode: boolean;
    retrieved: number;
    top_score: number | null;
    actian?: ActianInspector;
  }) => void;
  onDelta?: (delta: string, accumulated: string) => void;
  onDone?: (final: QueryResponse) => void;
  onError?: (err: Error) => void;
}

export interface HistoryTurn {
  role: "user" | "assistant";
  content: string;
}

export async function streamQuery(
  params: {
    query_text: string;
    persona: Persona;
    history?: HistoryTurn[];
    user_profile?: UserProfile;
    use_cache?: boolean;
    fusion_mode?: "rrf" | "dbsf";
  },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch(BASE + "/api/query/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal,
  });
  if (!r.ok || !r.body) {
    const msg = r.body ? await r.text() : `${r.status} ${r.statusText}`;
    throw new Error(msg);
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let accumulated = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const line = raw.trim();
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      try {
        const msg = JSON.parse(payload);
        if (msg.event === "start") {
          handlers.onStart?.({
            persona: msg.persona,
            from_cache: !!msg.from_cache,
            general_mode: !!msg.general_mode,
            retrieved: msg.retrieved ?? 0,
            top_score: msg.top_score ?? null,
            actian: msg.actian,
          });
        } else if (msg.event === "delta") {
          accumulated += msg.text;
          handlers.onDelta?.(msg.text, accumulated);
        } else if (msg.event === "done") {
          handlers.onDone?.({
            answer: msg.answer,
            citations: msg.citations ?? [],
            from_cache: !!msg.from_cache,
            persona: msg.persona ?? params.persona,
            retrieved: msg.retrieved ?? 0,
            general_mode: !!msg.general_mode,
            top_score: msg.top_score ?? undefined,
            actian: msg.actian,
            timings_ms: msg.timings_ms ?? { cache_lookup: 0, total: 0 },
          });
        }
      } catch (e) {
        // ignore malformed frames; SSE parser is resilient
      }
    }
  }
}
