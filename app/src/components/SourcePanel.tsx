import { useEffect, useState } from "react";
import { X, FileText, ExternalLink, Hash } from "lucide-react";
import { sourceMeta, sourcePdfUrl } from "../lib/api";
import { extractHighlightPhrase } from "../lib/highlight";
import type { SourceMeta } from "../lib/api";

export function SourcePanel({
  entityId,
  onClose,
}: {
  entityId: string;
  onClose: () => void;
}) {
  const [meta, setMeta] = useState<SourceMeta | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setMeta(null);
    setErr(null);
    sourceMeta(entityId).then(setMeta).catch((e) => setErr(String(e)));
  }, [entityId]);

  const highlight = meta ? extractHighlightPhrase(meta.text_preview) : "";
  const pdfUrl = sourcePdfUrl(entityId, meta?.page, highlight);

  // Filename hint from the URL (handy when the title is a long paper title)
  const filename = (() => {
    if (!meta?.source_url) return "";
    try {
      const u = new URL(meta.source_url);
      const last = u.pathname.split("/").filter(Boolean).pop() || "";
      return decodeURIComponent(last);
    } catch {
      return meta.source_url.split("/").pop() || "";
    }
  })();

  return (
    <aside className="w-[520px] flex-shrink-0 bg-surface-card border-l border-surface-deep/80 flex flex-col shadow-[-6px_0_20px_rgba(0,0,0,0.03)]">
      <header className="flex items-center justify-between px-5 py-3 border-b border-surface-deep">
        <div className="flex items-center gap-2.5 text-[11px] uppercase tracking-[0.08em] font-medium text-muted">
          <FileText size={13} className="text-accent" />
          <span>Cited source</span>
          {meta?.page && (
            <span className="flex items-center gap-1 px-1.5 py-0.5 ml-1 rounded bg-accent/10 text-accent normal-case tracking-normal">
              <Hash size={9} /> page {meta.page}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-md hover:bg-surface-deep transition-colors"
          aria-label="close cited source"
        >
          <X size={16} className="text-muted" />
        </button>
      </header>

      <div className="px-5 py-4 border-b border-surface-deep space-y-1.5">
        <div className="text-[15px] font-semibold text-ink leading-snug">
          {meta?.title || (err ? "error" : "Loading…")}
        </div>
        {filename && (
          <div className="flex items-center gap-1 text-[10px] text-muted font-mono truncate">
            <ExternalLink size={10} />
            <span className="truncate" title={meta?.source_url}>{filename}</span>
          </div>
        )}
        {highlight && (
          <div className="flex items-start gap-1.5 pt-1 text-[11px] text-muted">
            <span className="font-mono text-[9px] text-accent bg-accent/10 rounded px-1 py-0.5 mt-0.5 flex-shrink-0 uppercase tracking-wider">
              highlighting
            </span>
            <span className="italic leading-snug">"{highlight}"</span>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-hidden bg-[#d6d1ca]">
        {err && (
          <div className="p-4 text-sm text-red-700 bg-red-50 m-4 rounded">{err}</div>
        )}
        {meta?.has_pdf ? (
          <iframe
            src={pdfUrl}
            className="w-full h-full border-0"
            title="cited PDF"
          />
        ) : meta ? (
          <div className="p-5">
            <div className="text-[10px] uppercase tracking-wider text-muted mb-2">Preview</div>
            <div className="text-sm leading-relaxed text-ink whitespace-pre-wrap">
              {meta.text_preview || "(no preview available)"}
            </div>
          </div>
        ) : null}
      </div>

      {meta?.has_pdf && (
        <footer className="px-5 py-2 text-[10px] text-muted font-mono flex items-center justify-between border-t border-surface-deep">
          <span>PDF rendered natively by WKWebView</span>
          <a
            href={pdfUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 hover:text-ink transition-colors"
          >
            <ExternalLink size={10} /> open externally
          </a>
        </footer>
      )}
    </aside>
  );
}
