/**
 * Checks before a decision table is saved (plan 9, P9-8.16, E §11.2). Owns: `check` (the same refusals the server makes, in the
 * same words, so a Planner sees them before saving), `pickVersion` (which stored version the editor opens), `typedInputs` and
 * `SAMPLE`. Never: saves, evaluates or approves; the marketTable.* actions do (backend/di/services/actions/market_tables.py).
 * Tables hold conditions and outputs only: no code, no money (rates live in rate cards).
 */
import type { Jdm, MarketTable } from '../../api/marketTables';

export const FUNCTION_OFF = 'Function nodes are off: tables hold conditions and outputs only.';
export const MONEY_OFF = 'Rates live in rate cards, not in tables.';
const CODE_NODES = ['functionNode', 'customNode', 'expressionNode'];

interface Column { id: string; name: string; field?: string; type?: string }
interface Content { inputs?: Column[]; outputs?: Column[]; rules?: Record<string, unknown>[] }

/** What the test form starts with: a cordless fleet tool in Germany. */
export const SAMPLE: Record<string, string> = { market: 'DE', family: 'CRH', cover_type: 'fleet', age_months: '14' };

/** The problems of a table in plain words (empty: it may be saved). `declared`: the input fields the pack allows. */
export function check(j: Jdm, declared: readonly string[]): string[] {
  const out: string[] = [];
  if (j.nodes.some((n) => CODE_NODES.includes(n.type))) out.push(FUNCTION_OFF);
  for (const n of j.nodes.filter((x) => x.type === 'decisionTableNode')) {
    const c = (n.content ?? {}) as Content;
    for (const col of c.inputs ?? []) {
      const f = /^[A-Za-z_]\w*/.exec(col.field ?? col.name)?.[0];
      if (f && !declared.includes(f)) out.push(`${f} is not an input of this table.`);
    }
    if ((c.outputs ?? []).some((o) => o.type === 'money')) out.push(MONEY_OFF);
    for (const r of c.rules ?? []) {
      for (const o of c.outputs ?? []) {
        if (String(r[o.id] ?? '').trim() === '') out.push(`Rule ${String(r._id)} has no value for ${o.name}.`);
      }
    }
  }
  return out;
}

/** The version of a table the editor opens: your own draft, else the one in force, else the newest. */
export function pickVersion(all: MarketTable[], market: string, name: string, me: string, org: string): MarketTable | null {
  const mine = all.filter((t) => t.market === market && t.name === name && (t.org_unit_id === null || t.org_unit_id === org));
  const newest = (xs: MarketTable[]) => xs.reduce<MarketTable | null>((a, t) => (!a || t.version > a.version ? t : a), null);
  return newest(mine.filter((t) => t.status === 'draft' && t.created_by === me)) ?? newest(mine.filter((t) => t.status === 'approved')) ?? newest(mine);
}

/** The test form's text as inputs: a number stays a number, true and false are booleans, the rest is text. */
export function typedInputs(t: Record<string, string>): Record<string, unknown> {
  const one = (v: string): unknown => (v.trim() !== '' && Number.isFinite(Number(v)) ? Number(v) : v === 'true' ? true : v === 'false' ? false : v);
  return Object.fromEntries(Object.entries(t).map(([k, v]) => [k, one(v)]));
}
