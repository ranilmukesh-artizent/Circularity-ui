/**
 * What the new Analytics charts draw, counted in the browser from the closed decisions the page holds (the same rows the
 * existing charts and View data use, so a mark and its rows cannot disagree). Pure: no api, no React.
 */
import type { ClosedRow } from '../../../api/analytics';
import { median, STATUS_LABEL, type Labels } from '../data/dataView';

export const MIN_CELL = 5; // a heat cell with fewer rows shows a dash: a median of two cases says nothing

const uplift = (r: ClosedRow): number => (r.actual ?? 0) - r.baseline;
const sum = (a: number[]): number => a.reduce((s, x) => s + x, 0);

// ---------------------------------------------------------------- heat: median uplift per case, route by asset class
export interface HeatCell { route: string; cls: string; n: number; median: number | null }
export interface HeatData {
  routes: { id: string; label: string }[]; classes: { id: string; label: string }[];
  cells: HeatCell[]; byRoute: HeatCell[]; byClass: HeatCell[]; all: HeatCell; maxAbs: number;
}
const cellOf = (rows: ClosedRow[], route: string, cls: string): HeatCell => ({
  route, cls, n: rows.length, median: rows.length >= MIN_CELL ? median(rows.map(uplift)) : null,
});

/** Median uplift (actual net minus the agreed baseline) per reconciled case, for every route and class that has any. */
export function heatData(rows: ClosedRow[], l: Labels): HeatData {
  const rc = rows.filter((r) => r.status === 'reconciled');
  const routes = Object.keys(l.routes).filter((id) => rc.some((r) => r.route === id)).map((id) => ({ id, label: l.routes[id] }));
  const known = new Set(Object.keys(l.classes));
  const clsIds = [...new Set(rc.map((r) => r.cls))].sort((a, b) => (known.has(a) ? [...known].indexOf(a) : 999) - (known.has(b) ? [...known].indexOf(b) : 999) || a.localeCompare(b));
  const classes = clsIds.map((id) => ({ id, label: l.classes[id] ?? id }));
  const cells = routes.flatMap((rt) => classes.map((c) => cellOf(rc.filter((r) => r.route === rt.id && r.cls === c.id), rt.id, c.id)));
  const byRoute = routes.map((rt) => cellOf(rc.filter((r) => r.route === rt.id), rt.id, ''));
  const byClass = classes.map((c) => cellOf(rc.filter((r) => r.cls === c.id), '', c.id));
  const all = cellOf(rc, '', '');
  const maxAbs = Math.max(1, ...[...cells, ...byRoute, ...byClass, all].map((c) => Math.abs(c.median ?? 0)));
  return { routes, classes, cells, byRoute, byClass, all, maxAbs };
}

/** 0 to 1: how far from zero a cell is, for the tint (the scale is the same on both sides of zero). */
export const tint = (v: number | null, maxAbs: number): number => (v == null ? 0 : Math.min(1, Math.abs(v) / maxAbs));

// ---------------------------------------------------------------- trend: net recovered per month and the running uplift
export interface TrendMonth { mi: number; label: string; n: number; net: number; uplift: number; cumulative: number }
export function trendData(rows: ClosedRow[], l: Labels): TrendMonth[] {
  const rc = rows.filter((r) => r.status === 'reconciled');
  if (!rc.length) return [];
  const lo = Math.min(...rc.map((r) => r.mi)), hi = Math.max(...rc.map((r) => r.mi));
  const out: TrendMonth[] = [];
  let run = 0;
  for (let mi = lo; mi <= hi; mi++) {
    const a = rc.filter((r) => r.mi === mi), up = sum(a.map(uplift));
    run += up;
    out.push({ mi, label: (l.months[mi] ?? '').slice(0, 3), n: a.length, net: sum(a.map((r) => r.actual ?? 0)), uplift: up, cumulative: run });
  }
  return out;
}

// ---------------------------------------------------------------- flow: asset class to route to outcome
export type FlowKind = 'cls' | 'route' | 'out';
export interface FlowNode { id: string; label: string; col: 0 | 1 | 2; order: number; kind: FlowKind; ref: string; n: number; net: number }
export interface FlowLink { source: string; target: string; n: number }
export interface FlowGraph { nodes: FlowNode[]; links: FlowLink[]; total: number }
const OUTCOMES: ClosedRow['status'][] = ['reconciled', 'pending', 'cancelled', 'expired'];

export function flowGraph(rows: ClosedRow[], l: Labels): FlowGraph {
  if (!rows.length) return { nodes: [], links: [], total: 0 };
  const count = (f: (r: ClosedRow) => boolean) => rows.filter(f).length;
  const net = (f: (r: ClosedRow) => boolean) => sum(rows.filter((r) => r.status === 'reconciled' && f(r)).map((r) => r.actual ?? 0));
  const clsIds = [...new Set(rows.map((r) => r.cls))].sort((a, b) => count((r) => r.cls === b) - count((r) => r.cls === a) || a.localeCompare(b));
  const routeIds = Object.keys(l.routes).filter((id) => rows.some((r) => r.route === id));
  const outs = OUTCOMES.filter((s) => rows.some((r) => r.status === s));
  const nodes: FlowNode[] = [
    ...clsIds.map((id, i): FlowNode => ({ id: 'cls:' + id, label: l.classes[id] ?? id, col: 0, order: i, kind: 'cls', ref: id, n: count((r) => r.cls === id), net: net((r) => r.cls === id) })),
    ...routeIds.map((id, i): FlowNode => ({ id: 'route:' + id, label: l.routes[id], col: 1, order: i, kind: 'route', ref: id, n: count((r) => r.route === id), net: net((r) => r.route === id) })),
    ...outs.map((s, i): FlowNode => ({ id: 'out:' + s, label: STATUS_LABEL[s], col: 2, order: i, kind: 'out', ref: s, n: count((r) => r.status === s), net: net((r) => r.status === s) })),
  ];
  const links: FlowLink[] = [];
  for (const c of clsIds) for (const rt of routeIds) {
    const n = count((r) => r.cls === c && r.route === rt);
    if (n) links.push({ source: 'cls:' + c, target: 'route:' + rt, n });
  }
  for (const rt of routeIds) for (const s of outs) {
    const n = count((r) => r.route === rt && r.status === s);
    if (n) links.push({ source: 'route:' + rt, target: 'out:' + s, n });
  }
  return { nodes, links, total: rows.length };
}

/** Ids lit when a node or a link is hovered or focused: the part itself and what it touches, so the path reads end to end. */
export function litPath(g: FlowGraph, active: { kind: 'node' | 'link'; id: string } | null): { nodes: Set<string>; links: Set<string> } | null {
  if (!active) return null;
  const key = (k: FlowLink) => k.source + '>' + k.target;
  const nodes = new Set<string>(), links = new Set<string>();
  if (active.kind === 'node') {
    nodes.add(active.id);
    for (const k of g.links) if (k.source === active.id || k.target === active.id) { links.add(key(k)); nodes.add(k.source); nodes.add(k.target); }
  } else {
    const hit = g.links.find((k) => key(k) === active.id);
    if (!hit) return null;
    links.add(active.id); nodes.add(hit.source); nodes.add(hit.target);
    // carry the path on: a class-to-route band lights the routes' onward bands too
    for (const k of g.links) if (k.source === hit.target) links.add(key(k));
  }
  return { nodes, links };
}
export const linkKey = (k: { source: string; target: string }): string => k.source + '>' + k.target;

/** Spread labels down a column so none overlaps the next: each keeps as near its own y as the gap allows. */
export function spreadLabels(ys: number[], gap: number, top: number, bottom: number): number[] {
  const idx = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  const out = idx.map((x) => Math.max(top, x.y));
  for (let k = 1; k < out.length; k++) out[k] = Math.max(out[k], out[k - 1] + gap);
  for (let k = out.length - 1; k >= 0; k--) {
    const limit = k === out.length - 1 ? bottom : out[k + 1] - gap;
    out[k] = Math.min(out[k], limit);
  }
  const res = new Array<number>(ys.length);
  idx.forEach((x, k) => { res[x.i] = out[k]; });
  return res;
}

// ---------------------------------------------------------------- sentences (the text alternative of each chart)
const int = new Intl.NumberFormat('en-US');
const share = (a: number, b: number) => (b ? Math.round((a / b) * 100) : 0);

export function flowSummary(g: FlowGraph): string {
  if (!g.total) return 'No decisions in this selection.';
  const routes = g.nodes.filter((n) => n.kind === 'route').sort((a, b) => b.n - a.n);
  const rec = g.nodes.find((n) => n.id === 'out:reconciled');
  const top = routes[0];
  return `${top.label} takes ${share(top.n, g.total)}% of ${int.format(g.total)} decisions, the most of any route; ${share(rec?.n ?? 0, g.total)}% have reconciled with actuals.`;
}

export function heatSummary(h: HeatData): string {
  const ok = h.cells.filter((c) => c.median != null);
  if (!ok.length) return 'Too few reconciled cases in any cell to compare.';
  const best = ok.reduce((a, b) => ((b.median ?? 0) > (a.median ?? 0) ? b : a)), worst = ok.reduce((a, b) => ((b.median ?? 0) < (a.median ?? 0) ? b : a));
  const lab = (c: HeatCell) => `${h.routes.find((r) => r.id === c.route)?.label} on ${h.classes.find((x) => x.id === c.cls)?.label}`;
  return `Highest typical gain: ${lab(best)}; lowest: ${lab(worst)}. Cells with fewer than ${MIN_CELL} cases show a dash.`;
}

export function trendSummary(t: TrendMonth[], fmt: (n: number) => string): string {
  if (!t.length) return 'No reconciled decisions in this selection.';
  const best = t.reduce((a, b) => (b.net > a.net ? b : a));
  return `${fmt(t[t.length - 1].cumulative)} gained over the baseline across ${t.length} months; ${best.label} recovered the most, ${fmt(best.net)}.`;
}

// ---------------------------------------------------------------- axis
/** About `count` round tick values from `lo` to `hi` (steps of 1, 2, 2.5 or 5 times a power of ten). */
export function niceTicks(lo: number, hi: number, count = 4): number[] {
  const span = hi - lo || 1, raw = span / count, pow = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / pow;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * pow;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v / step) * step);
  return out;
}
