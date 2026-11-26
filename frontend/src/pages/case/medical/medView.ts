/**
 * Wording of the medical-rental case panels (plan 9 UI audit gap 7; stories MR-04/05 decontamination, MR-06 certification
 * window, MR-10 repair approval, MR-17/18/22 service planning and turnaround, MR-19/23 follow-through and write-off). Pure: it
 * reads the facts the case screen already carries (gates with their evidence, `rentalRequests`, `serviceRead`, `serviceCheck`,
 * `serviceOrders`, `approvalHolds`, `close`, `valuer`, `exec`; backend/di/services/cases/service_evidence.py, close_medical_rental.py,
 * modeler/valuers/medical_rental.py); nothing here computes a clinical or financial figure.
 * Decontamination, certification and write-off wording touches health and safety rules and accounting: it needs review by
 * Kinective's Legal team before it is relied on.
 */
import type { CaseRec, GateRow } from '../../../api/case';
import { money } from '../../../api/format';
import { gateTime } from '../gates';

/** The Packs tab of Analytics, where the pack's worked questions are (MR-18 turnaround, MR-17 service weeks). */
export const QUESTIONS_HREF = '#/analytics/packs';

interface Request { req_id?: string; hospital?: string; hospital_id?: string; start_date?: string; days?: number; ends?: string }
interface ReqCheck { req_id: string; ends: string; ok: boolean; reason: string | null; recommendation: string | null }
interface Order { asset_tag: string; kind: string; due_by: string; sent?: boolean; order_id?: string | null }
interface Hold {
  id: string; reason?: string; repairEstimate?: number; limit?: number; income?: number | null; incomeBasis?: string | null;
  alternative?: { route: string; net: number } | null;
}
interface MedFacts {
  rentalRequests?: Request[]; serviceRead?: { certificationExpiry?: string; pmDue?: string };
  serviceCheck?: { requests: ReqCheck[]; proposed: { input: { asset_tag: string; kind: string; due_by: string } } | null };
  serviceOrders?: Order[]; approvalHolds?: Hold[]; valuer?: { book_value?: number };
  close?: { turnaround_hours?: number; rerented_within_48h?: boolean; utilisation?: number; certificate_ref?: string; posted?: { write_off?: { amount: number; at?: string } } };
  exec?: { steps: { k?: string; label: string; state: string }[] } | null;
}
const facts = (c: CaseRec) => c as CaseRec & MedFacts;

export interface MedView { tag: string | null; cls: string }

/** The rental-device facts of a case, or null for a case of another pack. */
export function medicalView(c: CaseRec): MedView | null {
  if (c.template !== 'medical_rental') return null;
  return { tag: c.assetId?.split(':').pop() ?? null, cls: c.cls };
}

/** G-MED-DECON as a line: the cycle end after check-in with the record, or why the case is held. */
export function deconLine(g: GateRow | undefined): string {
  if (!g) return 'No decontamination gate result on the case';
  const e = g.evidence.find((x) => x.type === 'decontamination');
  const v = (e?.value ?? {}) as { decon_ended_at?: string; checked_in_at?: string; decon_record_ref?: string; decon_enhanced?: boolean };
  if (!g.passed || !e) return `Held: ${g.reason || 'Decontamination record required'}`;
  const parts = [`Cycle ended ${gateTime(v.decon_ended_at ?? e.at)}`];
  if (v.checked_in_at) parts.push(`after check-in ${gateTime(v.checked_in_at)}`);
  if (v.decon_record_ref) parts.push(`record ${v.decon_record_ref}`);
  if (v.decon_enhanced) parts.push('enhanced cycle');
  return parts.join(' · ');
}

export interface CertRow { id: string; rental: string; ok: boolean; text: string; advice: string | null }

/** Each rental request with its dates, whether the unit's certification and maintenance cover it, and the unit to send instead. */
export function certRows(c: CaseRec): CertRow[] {
  const f = facts(c);
  const checks = new Map((f.serviceCheck?.requests ?? []).map((q) => [q.req_id, q]));
  return (f.rentalRequests ?? []).map((q, i) => {
    const k = checks.get(q.req_id ?? '');
    const ends = k?.ends ?? q.ends;
    const rental = [q.hospital ?? q.hospital_id, q.days != null && q.start_date ? `${q.days} days from ${q.start_date}` : q.start_date, ends ? `ends ${ends}` : null]
      .filter(Boolean).join(' · ');
    return { id: q.req_id ?? `request ${i + 1}`, rental, ok: k?.ok ?? true, text: k ? (k.ok ? 'In date for the whole rental' : k.reason ?? 'Not in date') : 'Not checked', advice: k?.recommendation ?? null };
  });
}

/** The unit's own dates: certification and preventive maintenance. */
export function serviceDates(c: CaseRec): [string, string][] {
  const r = facts(c).serviceRead;
  return [['Certification to', r?.certificationExpiry], ['Preventive maintenance due', r?.pmDue]].filter((x): x is [string, string] => Boolean(x[1]));
}

/** What the close measured: check-in to dispatch against 48 hours, and the share of the cycle the device earns. */
export function turnaroundLines(c: CaseRec): string[] {
  const k = facts(c).close;
  const out: string[] = [];
  if (k?.turnaround_hours != null) out.push(`Check-in to dispatch ${+k.turnaround_hours.toFixed(2)} h${k.rerented_within_48h == null ? '' : k.rerented_within_48h ? ' · within 48 hours' : ' · over 48 hours'}`);
  if (k?.utilisation != null) out.push(`Utilisation ${+(k.utilisation * 100).toFixed(1)} % of the cycle`);
  return out;
}

/** The booking the service gate proposes (a person books it) and the service orders already on the case. */
export function serviceLines(c: CaseRec): string[] {
  const f = facts(c);
  const p = f.serviceCheck?.proposed?.input;
  const out = p ? [`Proposed for a person to book: ${p.kind} for ${p.asset_tag} by ${p.due_by}`] : [];
  for (const o of f.serviceOrders ?? []) {
    out.push(`Booked: ${o.kind} for ${o.asset_tag} by ${o.due_by} · ${o.sent ? `sent to the service system${o.order_id ? ` (${o.order_id})` : ''}` : 'recorded on the case'}`);
  }
  return out;
}

/** The repair above its limit (AP-MR-REPAIR), held for the fleet manager: reason and the figures the person decides on. */
export function repairHold(c: CaseRec): { reason: string; lines: string[] } | null {
  const h = (facts(c).approvalHolds ?? []).find((x) => x.id === 'AP-MR-REPAIR');
  if (!h) return null;
  const lines: string[] = [];
  if (h.repairEstimate != null && h.limit != null) lines.push(`Repair estimate ${money(h.repairEstimate)} against a ${money(h.limit)} limit`);
  if (h.income != null) lines.push(`Rental income over the next period ${money(h.income)}${h.incomeBasis ? ` (${h.incomeBasis})` : ''}`);
  if (h.alternative) lines.push(`Instead, ${h.alternative.route}: net ${money(h.alternative.net)}`);
  return { reason: h.reason ?? 'The repair is over its limit', lines };
}

const KINDS: Record<string, string> = {
  dispatch: 'Dispatch', service_order: 'Service order', biomed_refurb: 'Biomedical refurbishment', data_sanitisation: 'Data sanitisation',
  disposal_collection: 'Disposal collection', write_off: 'Write-off',
};
export interface FollowRow { key: string; label: string; state: string }

/** The follow-through after approval: the execution plan's steps with their state, else the chosen route's steps as planned. */
export function followRows(c: CaseRec): FollowRow[] {
  const ex = facts(c).exec?.steps;
  if (ex?.length) return ex.map((s, i) => ({ key: `${s.k ?? i}`, label: s.label, state: s.state }));
  const steps = ((c.chosen ?? c.recommendation) as { steps?: string[] } | null)?.steps ?? [];
  return steps.map((k) => ({ key: k, label: KINDS[k] ?? k, state: 'planned' }));
}

/** The write-off of a retired device: held for Finance until a person accepts it (an agent never does), then posted. Null for another route. */
export function writeOffLine(c: CaseRec): string | null {
  const f = facts(c);
  if ((c.chosen ?? c.recommendation)?.id.split(':')[0] !== 'retire') return null;
  const posted = f.close?.posted?.write_off;
  if (posted) return `Write-off of ${money(posted.amount)} posted${posted.at ? ` ${gateTime(posted.at)}` : ''}`;
  const book = f.valuer?.book_value;
  if (!book || book <= 0) return null;
  const cert = f.close?.certificate_ref ? ` · disposal certificate ${f.close.certificate_ref}` : '';
  return `Write-off of ${money(book)} is prepared for Finance and held until a person accepts it${cert}`;
}
