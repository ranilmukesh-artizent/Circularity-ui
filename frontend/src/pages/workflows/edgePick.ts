/**
 * Which link a click on the canvas means. Each link has a wide invisible hit area so a thin line is easy to click, and
 * links that leave the same step share their first stretch, so the hit area drawn on top is often not the line the
 * person pointed at (clicking Validation → Convert currency used to select Validation → Error handler). The canvas
 * samples every link's line and picks the one that passes closest to the click.
 */
export interface Pt {
  x: number;
  y: number;
}

export interface Line {
  id: string;
  /** Points along the line, in order (canvas world coordinates). */
  points: Pt[];
}

/** Distance from p to the segment a–b. */
function segDist(p: Pt, a: Pt, b: Pt): number {
  const dx = b.x - a.x, dy = b.y - a.y, len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2)) : 0;
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

/** The id of the line closest to p (the first one listed wins a tie), or null when there is none. */
export function nearestLine(lines: Line[], p: Pt): string | null {
  let best: string | null = null, bestD = Infinity;
  for (const l of lines) {
    for (let i = 1; i < l.points.length; i++) {
      const d = segDist(p, l.points[i - 1], l.points[i]);
      if (d < bestD) { bestD = d; best = l.id; }
    }
    if (l.points.length === 1) {
      const d = Math.hypot(p.x - l.points[0].x, p.y - l.points[0].y);
      if (d < bestD) { bestD = d; best = l.id; }
    }
  }
  return best;
}

/** Points along an SVG path every `step` units (its own user space), for nearestLine. */
export function samplePath(path: SVGPathElement, step = 6): Pt[] {
  const len = path.getTotalLength();
  const n = Math.max(2, Math.ceil(len / step));
  return Array.from({ length: n + 1 }, (_, i) => {
    const q = path.getPointAtLength((len * i) / n);
    return { x: q.x, y: q.y };
  });
}
