/**
 * The telecom network case, as the case page shows it (plan 9, UI audit gap 7): the unit's inventory match, test bench and wipe,
 * export class and screening, the trade compliance approval with its bid and alternative, spares before a new purchase, the
 * battery lane and recycler, and the close. Pure functions over the case record the screen sends (`gates`, `network`, `bench`,
 * `battery`, `downstream`, `valuer`, `close`, `routes`); the server words the gate reasons, this file words the rest the way
 * backend/di/services/cases (export_approval, tn_cross_region, close_telecom_network) does. Nothing is computed that the
 * server did not send: a missing fact is said to be missing.
 *
 * Export control and battery text: Kinective's Legal team reviews this wording before it is relied on or acted on. The class is
 * the inventory's or a person's, never derived here; only a person approves a resale (the Approvals queue).
 */
import type { CaseRec, GateRow } from '../../../api/case';
import { fmtDateYear } from '../../../api/format';

export type TelecomCase = CaseRec & {
  network?: { serial?: string; model?: string; site?: string; removedAt?: string; job?: string; source?: string } | null;
  bench?: { summary?: string; firmware?: string | null; firmwareLatest?: string | null; wipe?: { status?: string | null; attempts?: number | null; scope?: string[]; certificate?: string | null; verifiedAt?: string | null } } | null;
  battery?: { chemistry?: string; damaged?: boolean } | null;
  downstream?: { vendor_id?: string; weee_category?: string; weight_kg?: number; certificate?: { ref?: string } | null } | null;
  valuer?: { asset?: { region?: string }; spares?: { gap?: number; region_below_target?: string }; market?: { new_price?: number } } | null;
  close?: { telecom?: { reused: boolean; new_spend_avoided: number; days_to_redeploy: number | null; route?: string } } | null;
};

export const isTelecom = (c: { template?: string }): boolean => c.template === 'telecom_network';

const usd = (n: number): string => '$' + Math.round(n).toLocaleString('en-US');
const gateOf = (c: TelecomCase, id: string): GateRow | undefined => c.gates?.find((g) => g.id === id);
const valueOf = (g: GateRow | undefined): Record<string, unknown> => (g?.evidence[0]?.value as Record<string, unknown> | undefined) ?? {};

interface Bid { id?: string; unit_price?: number; qty?: number; country?: string; screening?: string | null; ref?: string | null }
const bidOf = (c: TelecomCase): Bid => (valueOf(gateOf(c, 'G-NET-EXP')).bid as Bid | undefined) ?? {};
const screeningText = (b: Bid): string => (b.screening ? `end-user screening ${b.screening}${b.ref ? ` (ref ${b.ref})` : ''}` : 'end-user screening not on file');

/** The unit's export class and the buyer's screening, from the export gate's evidence (G-NET-EXP, TN-07). */
export function exportLine(c: TelecomCase): string {
  const g = gateOf(c, 'G-NET-EXP');
  if (!g || !g.evidence.length) return 'Export class not on file';
  const v = valueOf(g);
  const cls = v.export_class
    ? `Export class ${String(v.export_class)} (${String(v.class_source ?? 'a source')})`
    : `Export class not confirmed (inferred ${String(v.inferred)} from the part number)`;
  return `${cls} · ${screeningText(bidOf(c))}`;
}

/** What the trade compliance approver decides on: the bid and the alternative "keep as spares" (AP-TN-EXP, TN-08); null when no approval is needed. */
export function approvalLines(c: TelecomCase): { bid: string; alternative: string } | null {
  const g = gateOf(c, 'G-NET-EXP');
  if (!g || g.passed || g.kind !== 'require_approval') return null;
  const b = bidOf(c);
  const spare = c.routes.find((r) => r.id === 'spare' && !r.excluded);
  return {
    bid: `Bid ${b.id}: ${b.qty} units at ${usd(b.unit_price ?? 0)} each, buyer country ${b.country}, ${screeningText(b)}.`,
    alternative: `Alternative: keep as spares${spare ? `, worth ${usd(spare.net)}` : ''}.`,
  };
}

/** The test bench's own count and firmware, as it gave them. */
export function benchLine(c: TelecomCase): string | null {
  const b = c.bench;
  if (!b?.summary) return null;
  return `Test bench: ${b.summary}${b.firmware ? ` · firmware ${b.firmware}` : ''}`;
}

/** The configuration wipe (G-NET-CFG, TN-06): verified with its certificate and scope, failed, or not on file. */
export function wipeLine(c: TelecomCase): string | null {
  const w = c.bench?.wipe;
  if (w?.status === 'verified') {
    const when = w.verifiedAt ? ` · ${fmtDateYear(w.verifiedAt)}` : '';
    return `Wipe verified · certificate ${w.certificate ?? 'not named'}${w.scope?.length ? ` · ${w.scope.join(', ')}` : ''}${when}`;
  }
  if (w?.status === 'failed') return `Wipe failed after ${w.attempts ?? 0} attempts: re-run it or destroy the unit`;
  return 'No wipe certificate on file';
}

/** Whether the serial matches the network inventory (G-NET-INV, TN-05). */
export function inventoryLine(c: TelecomCase): string {
  const g = gateOf(c, 'G-NET-INV');
  if (!g) return 'Network inventory not checked yet';
  if (g.passed) {
    const v = valueOf(g);
    return `Matches the network inventory: ${String(v.model ?? c.network?.model ?? '')} at ${String(v.site ?? c.network?.site ?? '')}`;
  }
  return `Does not match the network inventory: ${g.reason}`;
}

/** Spares before a new purchase (TN-18): the catalogue price a reuse avoids, and the cross-region transfer when another region is short. */
export function sparesLines(c: TelecomCase): string[] {
  const out: string[] = [];
  const price = c.valuer?.market?.new_price;
  if (typeof price === 'number') out.push(`New price ${usd(price)}: a unit that fills a gap avoids that spend.`);
  const s = c.valuer?.spares;
  if (s?.region_below_target && s.gap) {
    const here = c.valuer?.asset?.region;
    const short = `${s.region_below_target} is ${s.gap} ${s.gap === 1 ? 'unit' : 'units'} below its spares target`;
    out.push(here && here !== s.region_below_target ? `${short}: transfer this unit from ${here} before buying new.` : `${short}: keep this unit as a spare.`);
  }
  return out;
}

/** The battery lane (G-BAT-4, TN-23): a lithium unit takes the dangerous-goods lane only; a damaged one is not resold. */
export function batteryLines(c: TelecomCase): string[] {
  const b = c.battery;
  if (!b?.chemistry) return [];
  const lines = [`${b.chemistry[0].toUpperCase()}${b.chemistry.slice(1)} battery${b.damaged ? ', damaged' : ''}: dangerous-goods lane only`];
  const g = gateOf(c, 'G-BAT-4');
  if (g && !g.passed && g.reason) lines.push(g.reason);
  return lines;
}

/** The recycler the route names, with the WEEE category, the weight and the certificate (TN-20); null when none is named. */
export function recyclerLine(c: TelecomCase): string | null {
  const d = c.downstream;
  if (!d?.vendor_id) return null;
  const parts = [`Recycler ${d.vendor_id}`];
  if (d.weee_category) parts.push(`WEEE ${d.weee_category}`);
  if (typeof d.weight_kg === 'number') parts.push(`${d.weight_kg} kg`);
  if (d.certificate?.ref) parts.push(`certificate ${d.certificate.ref}`);
  return parts.join(' · ');
}

/** What the reuse saved (TN-21, TN-22), from the close the server recorded; null before it closes. */
export function closeLine(c: TelecomCase): string | null {
  const t = c.close?.telecom;
  if (!t) return null;
  if (!t.reused) return `Not reused (${t.route}): no new spend avoided`;
  return `Reused (${t.route}): new spend avoided ${usd(t.new_spend_avoided)}${t.days_to_redeploy != null ? ` · ${t.days_to_redeploy} days to redeploy` : ''}`;
}
