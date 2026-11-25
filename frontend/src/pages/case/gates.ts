/** The lines the Decide tab's Gates block shows for a case's gate results and its hold (P9-1.2, stories X-03 and X-07). */
import type { BatchStatus, GateHold, GateRow } from '../../api/case';

/** 2026-10-01T08:00:00+00:00 -> "2026-10-01 08:00 UTC" (the time as the server wrote it, in UTC). */
export function gateTime(iso: string): string {
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(iso);
  return m ? `${m[1]} ${m[2]} UTC` : iso;
}

const list = (xs: string[]) => xs.join(', ');

/**
 * The contract clause a gate result carries, as "Contract LS-5412 · clause 7.2 · 'No resale without consent' · from <source>,
 * <date>" (P9-1.11, story X-11); null when the result has no contract clause evidence. Contract wording is product text; it
 * needs review by Kinective's Legal team.
 */
export function clauseLine(g: GateRow): string | null {
  const e = g.evidence.find((x) => x.type === 'contract_clause');
  if (!e) return null;
  const v = e.value ?? {};
  return `Contract ${String(v.contract_id ?? '')} · clause ${String(v.clause ?? '')} · '${String(v.text ?? '')}' · from ${e.source || 'a source'}, ${gateTime(e.at)}`;
}

/**
 * A gate's line: "Passed: <evidence> from <source>, <time>" when it passed, "Blocks <route names>: <reason>" when it blocks
 * routes. A failed gate that blocks no route says what it does instead (a required step or approval, a blocked close).
 */
export function gateLine(g: GateRow): string {
  const clause = clauseLine(g);
  if (clause) return `${clause}. ${g.passed ? g.reason : `Blocks ${list(g.routeNames.length ? g.routeNames : g.routes)}: ${g.reason}`}`;
  if (g.passed) {
    const on = g.evidence.map((e) => `${e.label} from ${e.source || 'a source'}, ${gateTime(e.at)}`);
    return 'Passed: ' + (on.length ? list(on) : g.reason);
  }
  if (g.kind === 'block') return `Blocks ${list(g.routeNames.length ? g.routeNames : g.routes)}: ${g.reason}`;
  if (g.kind === 'require_step') return `Requires a step${g.step ? ' (' + g.step + ')' : ''}: ${g.reason}`;
  if (g.kind === 'require_approval') return `Needs approval${g.step ? ' (' + g.step + ')' : ''}: ${g.reason}`;
  return `Blocks closing: ${g.reason}`;
}

/** "Held until evidence arrives (batch B-7: 1 of 3 released)"; without a batch, no bracket. */
export function holdLine(hold: GateHold, batch?: BatchStatus | null): string {
  const tail = batch
    ? ` (batch ${batch.ref}: ${batch.released} of ${batch.total} released)`
    : hold.batch ? ` (batch ${hold.batch})` : '';
  return 'Held until evidence arrives' + tail;
}
