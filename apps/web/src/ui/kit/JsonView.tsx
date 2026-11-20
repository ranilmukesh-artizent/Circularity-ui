/**
 * Highlighted JSON in a <pre class="code"> (the demo's jsonHtml): keys (.k), and string (.s) and number (.n) values.
 * The three ports of jsonHtml differ at the edges, and each page keeps its own output (step E2 changes no markup):
 *   - "tokens" (Connection Fabric): one run of text; every `"key":`, and a string or number after ": ", is marked.
 *   - "lines" (case pages): one span per line; a value is marked only when the whole value is a string or a number.
 *   - "escaped" (MCP): one span per line; keys may hold escaped quotes; a value is marked by its first character.
 */
import type { ReactNode } from 'react';

export type JsonVariant = 'tokens' | 'lines' | 'escaped';

function tokens(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /"([^"]+?)":|(?<=: )"(.*?)"|(?<=: )(-?\d+(?:\.\d+)?)/g;
  let at = 0, m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    out.push(text.slice(at, m.index));
    if (m[1] !== undefined) out.push(<span key={m.index} className="k">"{m[1]}"</span>, ':');
    else if (m[2] !== undefined) out.push(<span key={m.index} className="s">"{m[2]}"</span>);
    else out.push(<span key={m.index} className="n">{m[3]}</span>);
    at = m.index + m[0].length;
  }
  out.push(text.slice(at));
  return out;
}

function line(ln: string, i: number): ReactNode {
  const m = /^(\s*)(?:"([^"]+)"(: ))?(.*?)(,?)$/.exec(ln)!;
  const [, ind, key, sep, val, comma] = m;
  const v = /^".*"$/.test(val) && key ? <span className="s">{val}</span> : /^-?\d+(\.\d+)?$/.test(val) && key ? <span className="n">{val}</span> : val;
  return <span key={i}>{ind}{key && <><span className="k">"{key}"</span>{sep}</>}{v}{comma}{'\n'}</span>;
}

function escapedLine(ln: string, i: number): ReactNode {
  const m = /^(\s*)"((?:[^"\\]|\\.)*)": (.*?)(,?)$/.exec(ln);
  if (!m) return <span key={i}>{ln}{'\n'}</span>;
  const v = m[3], cls = v.startsWith('"') ? 's' : /^-?\d+(\.\d+)?/.test(v) ? 'n' : '';
  return <span key={i}>{m[1]}<span className="k">"{m[2]}"</span>: {cls ? <span className={cls}>{v}</span> : v}{m[4]}{'\n'}</span>;
}

export function JsonView({ value, variant }: { value: unknown; variant: JsonVariant }) {
  const text = JSON.stringify(value, null, 2) ?? '';
  const body = variant === 'tokens' ? tokens(text) : text.split('\n').map(variant === 'lines' ? line : escapedLine);
  return <pre className="code">{body}</pre>;
}
