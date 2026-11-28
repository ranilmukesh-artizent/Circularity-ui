/**
 * Pure helpers of the Markdown component (plan 11, E1 and E3): which links are kept, and `settle`, which holds back the
 * unfinished tail of an answer that is still streaming so it does not flash as raw characters.
 */

/** A link is kept when it is http, https, mailto or an in-app hash link (`#/…`). Anything else renders as plain text. */
export function safeHref(url: string | undefined): string | null {
  if (!url) return null;
  // browsers ignore tabs, newlines and other control characters inside a scheme ("java\nscript:"), so look at the cleaned form
  // eslint-disable-next-line no-control-regex
  const u = url.replace(/[\u0000- \u007f-\u009f]+/g, '');
  return /^(https?:|mailto:)/i.test(u) || /^#\//.test(u) ? url.trim() : null;
}

/** An external link opens in a new tab; a hash link stays in the app. */
export const isExternal = (href: string): boolean => !href.startsWith('#');

const FENCE = /^\s{0,3}(`{3,}|~{3,})/;
const TABLE_ROW = /^\s*\|/;
const TABLE_DELIM = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;
const LONE_MARKER = /^\s*([-*+]|\d{1,9}[.)]|#{1,6}|>)\s*$/;

/**
 * The text as it should be drawn while it is still arriving. Everything the renderer would show as raw characters for a
 * moment is held back or closed: a lone list, heading or quote marker, one or two backticks, a table that has no
 * delimiter row yet, an unclosed `**` or backtick, a link whose URL is not closed. Text inside a code fence is left
 * alone (an open fence is closed by the renderer itself). A finished text should not go through it.
 */
export function settle(text: string): string {
  const lines = text.split('\n');
  let open = false;
  for (const l of lines) if (FENCE.test(l)) open = !open;
  if (open) return text;

  // a table needs its delimiter row before it is a table: hold back the rows written so far
  let start = lines.length;
  while (start > 0 && TABLE_ROW.test(lines[start - 1])) start--;
  const cells = (l: string) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').length;
  const head = lines[start];
  if (start < lines.length && !lines.slice(start + 1).some((l) => TABLE_DELIM.test(l) && cells(l) === cells(head))) lines.length = start;
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop();

  const last = lines.length - 1;
  if (last < 0) return '';
  let tail = lines[last];
  if (LONE_MARKER.test(tail) || /^`{1,2}$/.test(tail.trim())) {
    lines[last] = '';
    return lines.join('\n').trimEnd();
  }
  tail = tail.replace(/(^|\s)[*_~]{1,3}$/, '$1');
  if (((tail.match(/\*\*/g) ?? []).length & 1) === 1) tail += '**';
  if (((tail.match(/`/g) ?? []).length & 1) === 1) tail += '`';
  if (/\[[^\]]*\]\([^)\s]*$/.test(tail)) tail += ')';
  else if (/\[[^\]]*$/.test(tail)) tail = tail.replace(/\[([^\]]*)$/, '$1');
  lines[last] = tail;
  return lines.join('\n');
}
