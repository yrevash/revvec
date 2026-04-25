/**
 * Extract a short distinctive phrase from a PDF chunk's preview so Safari/
 * WKWebView's PDF viewer can auto-search + highlight it when we open the
 * PDF with `#search=<phrase>`.
 *
 * Heuristic:
 *   1. Strip PDF artifacts (orphan line numbers, newlines, non-ascii markers).
 *   2. Pick the longest uninterrupted run of words, clipped to ~40 chars.
 *   3. URL-encode.
 */
export function extractHighlightPhrase(preview: string): string {
  if (!preview) return "";
  let t = preview;
  // Strip orphan short number-only lines: "\n 30 \n" → " "
  t = t.replace(/\n\s*\d{1,4}\s*\n/g, " ");
  t = t.replace(/\n+/g, " ").replace(/\s+/g, " ").trim();

  // Find the longest "clean" substring with at least 3 words
  const chunks = t.split(/[.!?]|\s[,–-]\s/);
  let best = "";
  for (const raw of chunks) {
    const c = raw.trim();
    if (c.length >= 20 && c.length > best.length) best = c;
    if (best.length >= 55) break;
  }
  if (!best) best = t;

  // Clip to ~45 chars; prefer word boundary
  if (best.length > 45) {
    const sliced = best.slice(0, 45);
    const lastSpace = sliced.lastIndexOf(" ");
    best = lastSpace > 20 ? sliced.slice(0, lastSpace) : sliced;
  }
  return best;
}
