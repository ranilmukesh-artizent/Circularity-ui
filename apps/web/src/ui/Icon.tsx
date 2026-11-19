import { iconSvg } from '../api/nav';

const cache = new Map<string, { attrs: Record<string, string>; inner: string } | null>();

function parse(name: string) {
  if (!cache.has(name)) {
    const svg = iconSvg(name);
    const m = svg && /^<svg([^>]*)>([\s\S]*)<\/svg>$/.exec(svg.trim());
    if (!m) cache.set(name, null);
    else {
      const attrs: Record<string, string> = {};
      for (const [, k, v] of m[1].matchAll(/([\w-]+)="([^"]*)"/g)) attrs[k] = v;
      cache.set(name, { attrs, inner: m[2] });
    }
  }
  return cache.get(name)!;
}

/** One of the demo's inline icons (same paths, same stroke), rendered as a real <svg> so the demo's CSS applies. */
export function Icon({ name, className }: { name: string; className?: string }) {
  const p = parse(name);
  if (!p) return null;
  const a = p.attrs;
  return (
    <svg
      className={className}
      viewBox={a.viewBox ?? '0 0 24 24'}
      fill={a.fill ?? 'none'}
      stroke={a.stroke ?? 'currentColor'}
      strokeWidth={a['stroke-width'] ?? '1.75'}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: p.inner }} // static, trusted paths from the demo's icon set
    />
  );
}
