import { useState } from "react";
import { ChevronDown, Database } from "lucide-react";
import type { ActianInspector, QueryResponse } from "../lib/api";

function pathBadge(path: ActianInspector["path"]): { label: string; tone: string } {
  switch (path) {
    case "cache":
      return { label: "cache hit", tone: "bg-emerald-50 text-emerald-700 border-emerald-200" };
    case "rrf":
      return { label: "RRF fusion", tone: "bg-violet-50 text-violet-700 border-violet-200" };
    case "general":
      return { label: "general · model knowledge", tone: "bg-amber-50 text-amber-800 border-amber-200" };
    case "search":
    default:
      return { label: "vector search", tone: "bg-sky-50 text-sky-700 border-sky-200" };
  }
}

export function Inspector({ result }: { result: QueryResponse }) {
  const [open, setOpen] = useState(false);
  const a = result.actian;
  if (!a) return null;
  const badge = pathBadge(a.path);
  const total = a.actian_ms + a.rerank_ms;

  return (
    <div className="border border-surface-deep/70 rounded-xl bg-surface-deep/30 text-[11.5px] font-mono">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-surface-deep/50 rounded-xl transition-colors"
        aria-expanded={open}
        aria-label="Actian inspector"
      >
        <Database size={12} className="text-accent flex-shrink-0" />
        <span className="text-muted uppercase tracking-[0.08em] text-[10px] font-medium">
          Actian
        </span>
        <span
          className={"px-1.5 py-0.5 rounded border text-[10px] tracking-tight normal-case " + badge.tone}
        >
          {badge.label}
        </span>
        <span className="text-ink/80 truncate flex-1 text-left normal-case">
          {a.summary}
        </span>
        <span className="text-muted whitespace-nowrap">
          {total.toFixed(0)} ms
        </span>
        <ChevronDown
          size={12}
          className={"text-muted transition-transform " + (open ? "rotate-180" : "")}
        />
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 space-y-1.5 text-muted leading-relaxed">
          <Row k="vectors" v={a.vectors.join(" + ") || ","} />
          <Row
            k="hits"
            v={
              a.hits_used > 0
                ? `${a.hits_used}${a.top_score !== null ? ` · top score ${a.top_score.toFixed(3)}` : ""}`
                : ","
            }
          />
          <Row
            k="latency"
            v={
              a.rerank_ms > 0
                ? `${a.actian_ms.toFixed(0)} ms (Actian) + ${a.rerank_ms.toFixed(0)} ms (BM25)`
                : `${a.actian_ms.toFixed(0)} ms`
            }
          />
          <Row k="op" v={a.operation} mono wrap />
          <div className="pt-2 mt-2 border-t border-surface-deep/60">
            <div className="text-[9.5px] uppercase tracking-[0.08em] text-muted/70 mb-1.5">
              Actian features in play
            </div>
            <div className="flex flex-wrap gap-1.5">
              {[
                "named vectors",
                "points.query (RRF prefetch)",
                "points.search",
                "FilterBuilder",
                "set_payload",
                "score_threshold",
                "HNSW m=32 ef_construct=256",
                "vde.open_collection",
              ].map((f) => (
                <span
                  key={f}
                  className="px-1.5 py-0.5 rounded bg-accent/10 text-accent text-[10px] border border-accent/20"
                >
                  {f}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({
  k,
  v,
  mono = false,
  wrap = false,
}: {
  k: string;
  v: string;
  mono?: boolean;
  wrap?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="text-muted/70 text-[10px] uppercase tracking-[0.08em] w-14 flex-shrink-0">
        {k}
      </span>
      <span
        className={
          "text-ink/85 " + (mono ? "font-mono " : "") + (wrap ? "break-all" : "truncate")
        }
      >
        {v}
      </span>
    </div>
  );
}
