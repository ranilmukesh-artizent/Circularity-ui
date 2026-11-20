/** Sparkline (the demo's frSpark): 72 × 26, nothing for fewer than two points. */
export function Spark({ v, col }: { v?: number[]; col?: string }) {
  if (!v || v.length < 2) return null;
  const mn = Math.min(...v), mx = Math.max(...v), w = 72, h = 26, r = mx - mn || 1;
  const pts = v.map((x, i) => ((i / (v.length - 1)) * w).toFixed(1) + ',' + (h - 3 - ((x - mn) / r) * (h - 6)).toFixed(1)).join(' ');
  return (
    <svg className="frsp" viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <polyline points={pts} fill="none" stroke={col || 'currentColor'} strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
