import React, { Fragment, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "../lib/api";

/**
 * Render a grounded answer:
 *  - markdown body (bold, lists, inline code)
 *  - `[source:N]` markers inline replaced with a clickable orange pill
 *  - leading `(general)` / `(from model knowledge)` tag rendered as a subtle badge
 *
 * We replace [source:N] BEFORE passing to ReactMarkdown — we swap each marker
 * for a placeholder `§§CITE:N§§` so markdown doesn't interpret the brackets,
 * then we do a post-render pass in each text node via a components override.
 * That keeps the pills clickable without turning the whole thing into ad-hoc
 * DOM stitching.
 */

const PLACEHOLDER_RE = /§§CITE:(\d+)§§/g;
const SOURCE_RE = /\[source:\s*(\d+)\s*\]/g;

export function AnswerBody({
  answer,
  citations,
  onOpenSource,
  streaming,
}: {
  answer: string;
  citations: Citation[];
  onOpenSource?: (entityId: string) => void;
  streaming?: boolean;
}) {
  // Map index → entity_id for the inline pills
  const byIdx = useMemo(() => {
    const m = new Map<number, Citation>();
    for (const c of citations) m.set(c.index, c);
    return m;
  }, [citations]);

  // Inject placeholders so markdown doesn't mangle "[source:2]"
  const preprocessed = useMemo(
    () => answer.replace(SOURCE_RE, (_m, n) => `§§CITE:${n}§§`),
    [answer],
  );

  // Turn any text node into an array of (plain | pill) segments
  function renderSegments(text: string): (string | React.ReactElement)[] {
    const out: (string | React.ReactElement)[] = [];
    let last = 0;
    PLACEHOLDER_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    let key = 0;
    while ((m = PLACEHOLDER_RE.exec(text)) !== null) {
      if (m.index > last) out.push(text.slice(last, m.index));
      const n = Number(m[1]);
      const c = byIdx.get(n);
      out.push(
        <button
          key={`cite-${key++}`}
          onClick={() => c?.entity_id && onOpenSource?.(c.entity_id)}
          className={
            "inline-flex items-center justify-center align-[0.1em] mx-[1px] " +
            "min-w-[18px] h-[18px] px-[5px] rounded-md font-mono text-[10px] font-bold " +
            "bg-accent text-white hover:bg-ink transition-colors"
          }
          title={c?.title || `source ${n}`}
        >
          {n}
        </button>,
      );
      last = m.index + m[0].length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  }

  return (
    <div
      className={
        "prose prose-ink max-w-none " +
        "prose-p:my-3 prose-p:leading-[1.7] prose-p:text-[16px] prose-p:text-ink " +
        "prose-headings:text-ink prose-headings:font-semibold prose-headings:mt-5 prose-headings:mb-2 " +
        "prose-h1:text-xl prose-h2:text-lg prose-h3:text-base " +
        "prose-strong:text-ink prose-strong:font-semibold " +
        "prose-em:text-ink/90 " +
        "prose-a:text-accent prose-a:no-underline hover:prose-a:underline " +
        "prose-ul:my-3 prose-ul:pl-5 prose-ol:my-3 prose-ol:pl-5 " +
        "prose-li:my-1 prose-li:text-[16px] prose-li:leading-[1.65] prose-li:marker:text-muted " +
        "prose-code:bg-surface-deep prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-[13.5px] prose-code:font-mono prose-code:text-ink prose-code:before:hidden prose-code:after:hidden " +
        "prose-pre:bg-ink prose-pre:text-white/90 prose-pre:text-[13px] prose-pre:rounded-lg prose-pre:px-4 prose-pre:py-3 " +
        "prose-blockquote:border-l-2 prose-blockquote:border-accent/60 prose-blockquote:pl-4 prose-blockquote:italic prose-blockquote:text-ink/80 prose-blockquote:my-3 " +
        "prose-hr:border-surface-deep prose-hr:my-5 " +
        "prose-table:text-[14px] prose-th:font-semibold prose-th:text-ink prose-td:border-surface-deep"
      }
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Split text nodes into segments, so we can inject pill buttons
          // (buttons aren't allowed inside <p> via naïve replace; we use
          // Fragments so React tolerates them).
          p: ({ children, ...props }) => (
            <p {...props}>
              {transformChildren(children, renderSegments)}
            </p>
          ),
          li: ({ children, ...props }) => (
            <li {...props}>
              {transformChildren(children, renderSegments)}
            </li>
          ),
        }}
      >
        {preprocessed}
      </ReactMarkdown>
      {streaming && (
        <span className="inline-block w-2 h-[1.1em] ml-[2px] bg-accent align-middle animate-pulse" />
      )}
    </div>
  );
}

function transformChildren(
  children: React.ReactNode,
  render: (t: string) => (string | React.ReactElement)[],
): React.ReactNode {
  if (typeof children === "string") return <>{render(children).map((x, i) => <Fragment key={i}>{x}</Fragment>)}</>;
  if (Array.isArray(children)) {
    return children.map((c, i) =>
      typeof c === "string"
        ? <Fragment key={i}>{render(c).map((x, j) => <Fragment key={j}>{x}</Fragment>)}</Fragment>
        : <Fragment key={i}>{c}</Fragment>,
    );
  }
  return children;
}
