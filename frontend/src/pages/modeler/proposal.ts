/** The assistant's proposal as the Modeler shows it (the prototype's chat() and propHtml, lines 2438 and 2461-2465). */
import { readBy, type Proposal } from '../../api/modeler';
import type { FlowGraph, FlowNode, ModelerScreen } from '../../api/types';
import { formatImpact, tradeOff } from './impact';

/** The opening line of the assistant for a template (the prototype's chat(), line 2438). */
export function openingLine(template: string): string {
  return template === 'device'
    ? 'This is the device recommerce template: four channels, routed on cash per unit against days on hand. Describe a change and I will check it, simulate it on the sample lots and, once you approve, apply it to the draft flow.'
    : 'I watch this flow and the decisions it produces. Tell me what you want to change in plain words. I check it against the process, the guardrails and the existing rules, simulate it on the open queue, and only change the flow once you approve.';
}

export interface CheckLine {
  level: 'ok' | 'warn';
  text: string;
}

/** The checks list of a proposal: fits the process, passes the guardrails, the conflicts (or none), models unchanged. */
export function proposalChecks(p: Proposal, guardrails: number): CheckLine[] {
  const conflicts = p.checks.filter((c) => c.level === 'warn');
  return [
    { level: 'ok', text: 'Fits the process: placed between the guardrail gate and the decision' },
    { level: 'ok', text: `Passes all ${guardrails} locked guardrails` },
    ...(conflicts.length ? conflicts.map((c): CheckLine => ({ level: 'warn', text: c.msg })) : [{ level: 'ok' as const, text: 'No conflict with existing rules' }]),
    { level: 'ok', text: 'Prediction models and agents unchanged' },
  ];
}

// ---- plan 10 (T2): the preview card of the one assistant (section 2.3), Undo (2.7) and the question hint (2.1)

export interface DiffLine {
  sign: '+' | '~' | '-';
  text: string;
}

/** What the preview card shows for a proposal; every number comes from the server's read (the proposal and its simulation). */
export interface PreviewModel {
  blocked: boolean;
  title: string;
  /** the rule id at the card's right edge, when there is one */
  tag: string | null;
  /** where it was read: "Read by the rules" or "Read by a language model, checked by the rules" (2.5) */
  basis: string;
  diff: DiffLine[];
  checks: CheckLine[];
  impact: { heading: string; lines: string[] } | null;
  limits: string;
  canApply: boolean;
}

const VERB = { exclude: 'never', require: 'only', prefer: 'prefer' } as const;

/** "Grade is D", "Value at least 500": a rule's scope in the template's own words. */
function scopeText(n: FlowNode, s: ModelerScreen): string {
  const parts: string[] = [];
  for (const d of s.template.dims) {
    const v = n.scope?.[d.key];
    if (v == null || v === '' || (Array.isArray(v) && !v.length)) continue;
    const val = Array.isArray(v) ? v.join(' or ') : String(v);
    parts.push(d.kind === 'min' ? `${d.label} at least ${val}` : d.kind === 'max' ? `${d.label} at most ${val}` : `${d.label} is ${val}`);
  }
  return parts.join(' and ');
}

/** "IR-02 · never resale when Grade is D", or "<label> (process step)" for another kind of node. */
export function nodeText(n: FlowNode, s: ModelerScreen): string {
  if (n.t !== 'rule') return `${n.label} (${n.t === 'step' ? 'process step' : n.t})`;
  const path = s.template.paths.find((p) => p.id === n.path)?.name.toLowerCase() ?? 'a path to set';
  const sc = scopeText(n, s);
  return `${n.rid ?? n.id} · ${VERB[n.action ?? 'prefer']} ${path}${sc ? ' when ' + sc : ''}`;
}

const shape = (n: FlowNode) => JSON.stringify({ ...n, x: 0, y: 0, h: 0 });

/** Added, changed and removed steps between two graphs, as + ~ - lines (node positions do not count). */
export function diffGraphs(from: FlowGraph, to: FlowGraph, s: ModelerScreen): DiffLine[] {
  const old = new Map(from.nodes.map((n) => [n.id, n]));
  const out: DiffLine[] = [];
  for (const n of to.nodes) {
    const o = old.get(n.id);
    if (!o) out.push({ sign: '+', text: nodeText(n, s) });
    else if (shape(o) !== shape(n)) out.push({ sign: '~', text: nodeText(n, s) });
  }
  const now = new Set(to.nodes.map((n) => n.id));
  for (const n of from.nodes) if (!now.has(n.id)) out.push({ sign: '-', text: nodeText(n, s) });
  return out;
}

/** The card for a proposal (or a suggestion drafted as one): title, diff, checks, impact, limits by the person's rights. */
export function previewOf(p: Proposal, s: ModelerScreen): PreviewModel {
  const basis = readBy(p.read_by);
  if (p.kind === 'blocked') {
    return { blocked: true, title: `Blocked by ${p.guard ?? 'a guardrail'}`, tag: p.guard, basis, diff: [], checks: [{ level: 'warn', text: p.msg }], impact: null, limits: 'Nothing was changed. Rephrase it, or dismiss it.', canApply: false };
  }
  const canApply = s.can.edit;
  const draft = s.flow.dver ?? s.flow.ver + 1;
  const checks = p.kind === 'rule' ? proposalChecks(p, s.template.guardrails.length) : p.checks.map((c): CheckLine => ({ level: c.level === 'ok' ? 'ok' : 'warn', text: c.msg }));
  const unit = p.sim?.kind === 'device' ? 'lots' : 'decisions';
  const note = p.sim ? tradeOff(p.sim) : null;
  return {
    blocked: false,
    title: `Proposed: ${p.label ?? p.text}`,
    tag: p.rid,
    basis,
    diff: p.graph ? diffGraphs(s.flow.graph, p.graph, s) : [],
    checks,
    impact: p.sim ? { heading: `Impact on the ${p.sim.n} open ${unit}`, lines: [formatImpact(p.sim), ...(note ? [note] : [])] } : null,
    limits: canApply ? `Saved to draft v${draft} only. Not published. A different person approves it after you submit.` : 'Only a person with Modeler edit rights applies this.',
    canApply,
  };
}

/** The journal note of an Undo: the person's own saveDraft of the earlier graph says what it undoes. */
export const undoNote = (text: string): string => `Undid the assistant's change: ${text}`;

/** Undo is offered while the draft still equals what the apply saved (compared as graph JSON); any later edit removes it. */
export const undoAvailable = (appliedJson: string, currentJson: string): boolean => appliedJson === currentJson;

const firstWord = (t: string) => /^[\s"'“]*([A-Za-z]+)/.exec(t)?.[1]?.toLowerCase() ?? '';
const QUESTION = new Set(['what', 'why', 'how', 'which', 'who', 'when', 'does', 'is', 'can']);
const CHANGE = new Set(['never', 'always', 'only', 'require', 'prefer', 'exclude', 'send', 'route', 'block']);

/** Change flow mode: the text reads like a question (ends in "?" or starts with a question word); no model decides. */
export const looksLikeQuestion = (t: string): boolean => t.trim().endsWith('?') || QUESTION.has(firstWord(t));
/** Ask mode on the Modeler: the text reads like a change to the flow. */
export const looksLikeChange = (t: string): boolean => CHANGE.has(firstWord(t));
