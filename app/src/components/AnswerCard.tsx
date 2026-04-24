import { useState } from "react";
import { FileText, Clock, ChevronRight, Sparkles } from "lucide-react";
import type { QueryResponse } from "../lib/api";
import { AnswerBody } from "./AnswerBody";

function Latency({ ms, label }: { ms: number | undefined; label: string }) {
  if (ms === undefined) return null;
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-muted font-mono">
      <span className="w-1.5 h-1.5 rounded-full bg-accent/70" />
      <span>{label} {ms.toFixed(0)}ms</span>
    </div>
  );
}

export function AnswerCard({
  result,
  onOpenSource,
}: {
  result: QueryResponse;
  onOpenSource?: (entityId: string) => void;
}) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  return (
    <div className="bg-surface-card rounded-2xl shadow-card p-7 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 text-muted text-[11px] uppercase tracking-[0.08em] font-medium">
          <FileText size={12} />
          <span>Answer</span>
          {result.from_cache && (
            <span className="ml-2 px-2 py-0.5 text-[10px] bg-accent/10 text-accent rounded-full normal-case tracking-normal">
              cache hit
            </span>
          )}
          {result.general_mode && (
            <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 text-[10px] bg-amber-50 text-amber-800 rounded-full normal-case tracking-normal">
              <Sparkles size={10} /> general knowledge
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <Latency ms={result.timings_ms.cache_lookup} label="cache" />
          <Latency ms={result.timings_ms.retrieve} label="retrieve" />
          <Latency ms={result.timings_ms.generate} label="generate" />
          <div className="flex items-center gap-1.5 text-[11px] text-ink font-mono font-semibold">
            <Clock size={11} />
            <span>{result.timings_ms.total.toFixed(0)}ms</span>
          </div>
        </div>
      </div>

      <AnswerBody
        answer={result.answer}
        citations={result.citations}
        onOpenSource={onOpenSource}
      />

      {result.citations.length > 0 && (
        <div className="pt-4 border-t border-surface-deep space-y-1.5">
          <div className="text-[10px] uppercase tracking-[0.08em] text-muted font-medium mb-3">
            Cited sources · {result.citations.length}
          </div>
          {result.citations.map((c, i) => (
            <div
              key={i}
              className="flex items-start gap-2 p-2 hover:bg-surface-deep/50 rounded-lg transition-colors group"
            >
              <div className="flex items-center justify-center w-6 h-6 rounded bg-accent text-white text-xs font-mono font-bold mt-0.5 flex-shrink-0">
                {c.index}
              </div>
              <button
                onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                className="flex-1 min-w-0 text-left"
              >
                <div className="text-sm text-ink truncate">
                  {c.title || c.entity_id || "(no title)"}
                </div>
                {expandedIdx === i && c.preview && (
                  <div className="mt-2 text-xs text-muted leading-relaxed whitespace-pre-wrap">
                    {c.preview}
                  </div>
                )}
              </button>
              {onOpenSource && c.entity_id && (
                <button
                  onClick={() => onOpenSource(c.entity_id)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity px-2 py-1 text-[10px] text-accent bg-accent/10 hover:bg-accent/20 rounded-md font-medium flex-shrink-0"
                >
                  View →
                </button>
              )}
              <button
                onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                className="flex-shrink-0"
              >
                <ChevronRight
                  size={16}
                  className={
                    "text-muted mt-1 transition-transform " +
                    (expandedIdx === i ? "rotate-90" : "")
                  }
                />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
