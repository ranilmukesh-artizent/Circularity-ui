/**
 * What accepting a proposal does, in words (UI fix 39, audit E13): the held action's input as "label: value" lines, the
 * agent's confidence, the evidence behind it and the groups of proposals a person may accept together. Pure; nothing here
 * calls the server. A field the server did not send (confidence, evidence) gives nothing: no value is made up.
 */
import type { HomeProposal } from '../api/home';

type Shown = Pick<HomeProposal, 'input' | 'why' | 'case_id'>;

const WORD: Record<string, string> = { ref: 'reference', id: 'ID', qty: 'quantity', no: 'number', po: 'PO', sku: 'SKU' };
const WHY_KEYS = ['reason', 'rationale', 'note', 'message', 'comment'];

/** "work_order_ref" and "workOrderRef" read as "Work order reference". */
export function labelOf(key: string): string {
  const w = key.replace(/([a-z0-9])([A-Z])/g, '$1_$2').split(/[_\s.-]+/).filter(Boolean).map((x) => x.toLowerCase());
  const last = w.length - 1;
  const words = w.map((x, k) => (k === last ? WORD[x] : undefined) ?? x);
  const s = words.join(' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const isScalar = (v: unknown): v is string | number | boolean => ['string', 'number', 'boolean'].includes(typeof v);
const scalar = (v: string | number | boolean): string => (typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v));

/** One input value as a short phrase, or '' when there is nothing to say. */
export function valueText(v: unknown): string {
  if (v === null || v === undefined || v === '') return '';
  if (isScalar(v)) return scalar(v);
  if (Array.isArray(v)) {
    if (!v.length) return '';
    if (v.every(isScalar)) return v.map(scalar).join(', ');
    return `${v.length} ${v.length === 1 ? 'item' : 'items'}`;
  }
  if (typeof v === 'object') {
    return Object.entries(v as Record<string, unknown>)
      .filter(([, x]) => isScalar(x) && x !== '')
      .slice(0, 3)
      .map(([k, x]) => `${labelOf(k).toLowerCase()} ${scalar(x as string | number | boolean)}`)
      .join(', ');
  }
  return '';
}

export interface InputLine { label: string; value: string }

/** The input of the held action as lines (at most `max`; `more` counts the rest). The agent's own reason is the proposal's
 *  "Why", and the case is in the header: neither repeats here. */
export function describeInput(p: Shown, max = 6): { lines: InputLine[]; more: number } {
  const all: InputLine[] = [];
  for (const [k, v] of Object.entries(p.input ?? {})) {
    if (WHY_KEYS.includes(k) && typeof v === 'string' && v.trim() === (p.why ?? '').trim()) continue;
    if (k === 'case_id' && v === p.case_id) continue;
    const value = valueText(v);
    if (value) all.push({ label: labelOf(k), value });
  }
  return { lines: all.slice(0, max), more: Math.max(0, all.length - max) };
}

/** "Confidence 62% (threshold 75%)", or '' when the server sent none. */
export function confidenceText(p: Pick<HomeProposal, 'confidence' | 'threshold'>): string {
  if (typeof p.confidence !== 'number') return '';
  const pct = (x: number) => `${Math.round(x * 100)}%`;
  return `Confidence ${pct(p.confidence)}` + (typeof p.threshold === 'number' ? ` (threshold ${pct(p.threshold)})` : '');
}

const KIND_WORD: Record<string, string> = {
  risk: 'a guardrail', value: 'value above the limit', confidence: 'confidence below the threshold', taint: 'untrusted content read',
  destructive: 'a destructive action', autonomy: 'the agent may only propose', model_concern: 'a concern the model raised',
};

export interface BulkGroup { key: string; label: string; ids: number[] }

/** Proposals the person may accept together: the same action held for the same reason kinds, two or more, none their own
 *  agent's (maker-checker). A proposal with no recorded reason is never grouped: there is no reason to share. */
export function bulkGroups(list: readonly Pick<HomeProposal, 'id' | 'action' | 'title' | 'reasons' | 'own'>[]): BulkGroup[] {
  const by = new Map<string, BulkGroup>();
  for (const p of list) {
    const kinds = [...new Set((p.reasons ?? []).map((r) => r.reason))].sort();
    if (p.own || !kinds.length) continue;
    const key = p.action + '|' + kinds.join(',');
    const g = by.get(key) ?? { key, label: `${p.title}, held for ${kinds.map((k) => KIND_WORD[k] ?? k).join(' and ')}`, ids: [] };
    g.ids.push(p.id);
    by.set(key, g);
  }
  return [...by.values()].filter((g) => g.ids.length > 1);
}
