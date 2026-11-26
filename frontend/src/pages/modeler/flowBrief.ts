/**
 * The agent column's "What I see" and "Watching" (plan 10, section 3.3), written by rules from the screen read
 * (GET /api/screens/modeler) and the rows already fetched: no model writes these sentences, and every number is a count
 * of what the read holds. Pure, so it is tested without a page. A sentence carries the link the column follows: a node
 * (select it on the canvas, open the Inspector) or the Checks tab.
 */
import type { HomeProposal } from '../../api/home';
import type { RuleSuggestions } from '../../api/modeler';
import type { Check, FlowNode, ModelerScreen } from '../../api/types';

/** The five provenance words of the demo's `.afb` badges (plan 10, 4.1). */
export type Prov = 'Retrieved' | 'Rules' | 'Model' | 'Simulated' | 'Prepared by agent';

export type BriefLink = { kind: 'node'; id: string } | { kind: 'checks' } | null;

export interface BriefLine {
  id: string;
  /** a name from the icon set (plan 10, 4.6) */
  icon: 'book' | 'alert' | 'branch' | 'users' | 'edit';
  text: string;
  tag: Prov;
  link: BriefLink;
}

const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`;
const shape = (n: FlowNode) => JSON.stringify({ ...n, x: 0, y: 0, h: 0 });
const MAX_LINES = 5;
const MAX_BLOCKING = 2;

/** 3 to 5 sentences about this flow: what it holds, what blocks a submit, what came back, how the draft differs. */
export function flowBrief(s: ModelerScreen, checks: Check[]): BriefLine[] {
  const nodes = s.flow.graph.nodes;
  const out: BriefLine[] = [
    {
      id: 'counts', icon: 'book', tag: 'Rules', link: null,
      text: `${plural(s.template.guardrails.length, 'locked guardrail')}, ${plural(nodes.filter((n) => n.t === 'rule').length, 'business rule')}, ${plural(nodes.filter((n) => n.t === 'path').length, 'outcome')}.`,
    },
  ];

  const fails = checks.filter((c) => c.level === 'fail');
  fails.slice(0, fails.length > MAX_BLOCKING + 1 ? MAX_BLOCKING : fails.length).forEach((c, i) =>
    out.push({ id: 'fail' + i, icon: 'alert', tag: 'Rules', text: c.msg, link: c.node_id ? { kind: 'node', id: c.node_id } : { kind: 'checks' } }));
  if (fails.length > MAX_BLOCKING + 1) {
    out.push({ id: 'failmore', icon: 'alert', tag: 'Rules', text: `${fails.length - MAX_BLOCKING} more blocking checks.`, link: { kind: 'checks' } });
  }

  const ret = s.flow.returned;
  if (ret) out.push({ id: 'returned', icon: 'edit', tag: 'Rules', text: `Returned by ${ret.by}: ${ret.reason}`, link: ret.node_id ? { kind: 'node', id: ret.node_id } : null });

  if ((s.flow.status === 'draft' || s.flow.status === 'review') && s.flow.dver != null) {
    const old = new Map(s.flow.published.nodes.map((n) => [n.id, n]));
    const added = nodes.filter((n) => !old.has(n.id));
    const changed = nodes.filter((n) => old.has(n.id) && shape(old.get(n.id)!) !== shape(n));
    const ids = new Set(nodes.map((n) => n.id));
    const removed = s.flow.published.nodes.filter((n) => !ids.has(n.id));
    const parts = [
      added.length ? `${plural(added.length, 'step')} added` : '',
      changed.length ? `${changed.length} changed` : '',
      removed.length ? `${removed.length} removed` : '',
    ].filter(Boolean);
    const first = added[0] ?? changed[0];
    out.push({
      id: 'draft', icon: 'branch', tag: 'Rules', link: first ? { kind: 'node', id: first.id } : null,
      text: parts.length ? `Draft v${s.flow.dver} differs from v${s.flow.ver}: ${parts.join(', ')}.` : `Draft v${s.flow.dver} matches v${s.flow.ver}.`,
    });
  } else if (s.flow.status === 'pub') {
    out.push({ id: 'pub', icon: 'branch', tag: 'Rules', link: null, text: `Published v${s.flow.ver}. No draft.` });
  }

  if (s.flow.org_unit_id !== s.org) out.push({ id: 'inherit', icon: 'users', tag: 'Rules', link: null, text: `${s.org} uses the flow of ${s.flow.org_unit_id}.` });
  return out.slice(0, MAX_LINES);
}

export interface WatchRow {
  id: 'shadow' | 'review' | 'suggestions' | 'held';
  icon: 'activity' | 'clock' | 'users' | 'eye';
  text: string;
  tag: Prov;
  /** `suggestions` opens the first suggestion as a preview card; `held` scrolls to the held card */
  action?: 'suggestions' | 'held';
}

/** What the held proposals are about: flow, overlay and compose actions of this flow (or with no flow named). */
export const heldForFlow = (all: HomeProposal[], flowId: number): HomeProposal[] =>
  all.filter((p) => /^(flow|overlay|compose)\./.test(p.action) && (p.input.flow_id == null || p.input.flow_id === flowId));

/** The signals that exist, one row each: the shadow run, a draft waiting for approval, override suggestions, held proposals. */
export function watchingRows(s: ModelerScreen, x: { suggestions: RuleSuggestions | null; held: HomeProposal[] }): WatchRow[] {
  const rows: WatchRow[] = [];
  if (s.shadow) {
    rows.push({ id: 'shadow', icon: 'activity', tag: 'Simulated', text: `Shadow run: ${plural(s.shadow.n, 'decision')}, ${s.shadow.agree} agree, ${s.shadow.disagree} differ.` });
  }
  if (s.flow.status === 'review' && s.flow.dver != null) {
    rows.push({ id: 'review', icon: 'clock', tag: 'Rules', text: `Draft v${s.flow.dver} waits for approval by someone other than ${s.flow.maker ?? 'its maker'}.` });
  }
  const n = x.suggestions?.suggestions.length ?? 0;
  if (n) rows.push({ id: 'suggestions', icon: 'users', tag: 'Retrieved', action: 'suggestions', text: `${plural(n, 'rule')} suggested by approver overrides.` });
  else if (x.suggestions && x.suggestions.decisions > 0) {
    // the read found nothing to suggest: say what was read (the old "Find suggestions" panel's line), not "no overrides"
    const o = x.suggestions.groups.reduce((k, g) => k + g.n, 0);
    rows.push({ id: 'suggestions', icon: 'users', tag: 'Retrieved', text: `Read ${plural(x.suggestions.decisions, 'decision')} and ${plural(o, 'override')}: no rule suggested yet.` });
  }
  if (x.held.length) {
    rows.push({ id: 'held', icon: 'clock', tag: 'Prepared by agent', action: 'held', text: `${plural(x.held.length, 'proposal')} held for a person: ${x.held[0].title}.` });
  }
  return rows;
}
