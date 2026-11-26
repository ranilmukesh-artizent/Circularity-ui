/* Pure helpers of the Compose panel (plan 9, P9-8.18, story X-10): step labels, which systems need an adapter or wait for
   their owner, the mapping summary, and the line a step's state shows. No React, no calls. */
import type { Autonomy, ComposeSystem, Composition, CompositionStep, MappingCounts, PublishInfo, PublishReport, StageRow, StepState, SystemStatus } from '../../../api/compose';
import type { MappingBand } from '../../../api/integration';
import { signed } from '../replayReport';

/** The five steps as Segmented items: [id, label]. */
export const STEP_ITEMS: readonly (readonly [CompositionStep, string])[] = [
  ['describe', 'Describe'],
  ['mapping', 'Adapter mapping'],
  ['agents', 'Agents'],
  ['approve', 'Approve'],
  ['publish', 'Publish'],
];

const STATUS: Record<SystemStatus, [label: string, tone: string]> = {
  connected: ['Connected', 'ok'],
  needs_adapter: ['Needs an adapter', 'bad'],
  test_connection: ['Test connection', 'warn'],
  awaiting_owner: ['Waiting for the system owner', 'warn'],
};

export const statusLabel = (s: SystemStatus): string => STATUS[s][0];
export const statusTone = (s: SystemStatus): string => STATUS[s][1];

const named = (all: ComposeSystem[], s: SystemStatus) => all.filter((x) => x.status === s).map((x) => x.name);
/** Names of the systems with no source yet: each needs an adapter from the registry. */
export const needsAdapter = (all: ComposeSystem[]): string[] => named(all, 'needs_adapter');
/** Names of the systems whose connection or mapping waits for the system owner. */
export const awaitingOwner = (all: ComposeSystem[]): string[] => named(all, 'awaiting_owner');

/** The bands of a source's suggestion rows, with the fields the owner was asked about. */
export function mappingSummary(rows: readonly { band: MappingBand }[], askedOwner = 0): MappingCounts {
  const n: MappingCounts = { fields: rows.length, pre_ticked: 0, check: 0, none: 0, asked_owner: askedOwner };
  for (const r of rows) n[r.band] += 1;
  return n;
}

/** The sum over every system. */
export const totalMapping = (all: ComposeSystem[]): MappingCounts =>
  all.reduce<MappingCounts>(
    (t, x) => ({
      fields: t.fields + x.mapping.fields, pre_ticked: t.pre_ticked + x.mapping.pre_ticked, check: t.check + x.mapping.check,
      none: t.none + x.mapping.none, asked_owner: t.asked_owner + x.mapping.asked_owner,
    }),
    { fields: 0, pre_ticked: 0, check: 0, none: 0, asked_owner: 0 },
  ); // prettier-ignore

/** "Mark done" waits while any field waits for its owner. */
export const canMarkMappingDone = (all: ComposeSystem[]): boolean => totalMapping(all).asked_owner === 0;

/** "3 pre-ticked, 1 to check, 2 without a proposal" (or "No sample yet"). */
export function summaryLine(m: MappingCounts): string {
  if (m.fields === 0) return 'No sample yet';
  const parts = [`${m.pre_ticked} pre-ticked`, `${m.check} to check`, `${m.none} without a proposal`];
  return m.asked_owner ? [...parts, `${m.asked_owner} waiting for the owner`].join(', ') : parts.join(', ');
}

/** What a step's state says, with the reason when it was sent back. */
export function stateLine(s: Pick<StepState, 'state' | 'note'> | undefined): string {
  if (!s || s.state === 'todo') return 'Not done';
  return s.state === 'done' ? 'Done' : 'Sent back: ' + (s.note?.reason ?? '');
}

// ---------------------------------------------------------------- agents, approve and publish (P9-8.20)

export const AUTONOMY_ITEMS: readonly (readonly [Autonomy, string])[] = [
  ['recommend', 'Recommend only'],
  ['limits', 'Act within limits'],
  ['alone', 'Act alone'],
];
export const autonomyLabel = (a: Autonomy): string => AUTONOMY_ITEMS.find(([k]) => k === a)?.[1] ?? a;

/** The confidence threshold slider, in percent. */
export const THRESHOLD = { min: 65, max: 85, def: 75 } as const;
export const GUARDRAIL_NOTE = 'Guardrails are enforced by the platform whatever the autonomy.';
export const BOUNDS_TEXT = 'The confidence threshold is between 65 % and 85 %.';
export const MAKER_CHECKER = 'Maker-checker: you composed this, so you cannot approve it.';
export const SHARE_DEFAULT = 20;
export const NEEDS_REPLAY = 'Run the replay before publishing.';

export const thresholdText = (fraction: number): string => `${Math.round(fraction * 100)} %`;
/** The refusal for a slider value (percent) outside the range, else null. */
export const thresholdError = (pct: number): string | null => (Number.isFinite(pct) && pct >= THRESHOLD.min && pct <= THRESHOLD.max ? null : BOUNDS_TEXT);

/** The rows to send: limits only for "Act within limits", empty limits left out. */
export function cleanRows(rows: readonly StageRow[]): StageRow[] {
  return rows.map((r) => {
    const l = r.autonomy === 'limits' ? Object.fromEntries(Object.entries(r.limits ?? {}).filter(([, v]) => typeof v === 'number' && v >= 0)) : {};
    return { stage: r.stage, agent_id: r.agent_id.trim(), autonomy: r.autonomy, ...(Object.keys(l).length ? { limits: l } : {}) };
  });
}

/** "Act within limits ($600, 10 items)" for a stage row. */
export function stageLine(r: StageRow): string {
  const l = r.limits ?? {};
  const bits = [l.value_limit !== undefined ? `$${l.value_limit.toLocaleString('en-US')}` : '', l.bulk_limit !== undefined ? `${l.bulk_limit} items` : ''].filter(Boolean);
  return autonomyLabel(r.autonomy) + (r.autonomy === 'limits' && bits.length ? ` (${bits.join(', ')})` : '');
}

/** Everyone who made the composition: the creator, the submitter and every editor. */
export const makers = (c: Pick<Composition, 'created_by' | 'submitted_by' | 'editors'>): string[] =>
  [...new Set([c.created_by, c.submitted_by, ...c.editors].filter((x): x is string => !!x))];

/** Why Approve is off for this person, or null: not waiting for approval, or the maker is the one looking. */
export function approveBlock(c: Pick<Composition, 'status' | 'created_by' | 'submitted_by' | 'editors'>, me: string | null): string | null {
  if (c.status !== 'submitted') return 'It is not waiting for approval.';
  return me && makers(c).includes(me) ? MAKER_CHECKER : null;
}

/** What stops "Publish": the composition not approved, no flow in shadow, or no replay report; null when it may go. */
export function publishBlock(status: Composition['status'], info: PublishInfo): string | null {
  if (status === 'published') return 'It is published; widen the canary in the Rollout panel.';
  if (status !== 'approved') return 'Approve the composition first.';
  if (info.flow_stage !== 'shadow') return 'Approve the decision flow into shadow first (Modeler, Lifecycle).';
  return info.report ? null : NEEDS_REPLAY;
}

/** The share as a whole number 1 to 99, else null. */
export const parseShare = (v: string): number | null => (/^\d{1,2}$/.test(v.trim()) && +v >= 1 ? +v : null);

export const publishLabel = (region: string, share: number): string => `Publish to ${region.trim() || 'a region'} at ${share} %`;

/** The numbers of a replay report as the Publish step lists them. */
export const reportLines = (r: PublishReport): string[] => [
  `Straight-through: ${r.straight_through_pct.toFixed(1)} %`,
  `Approvals a day: ${r.approvals_per_day.toFixed(1)}`,
  `Exceptions a day: ${r.exceptions_per_day.toFixed(1)}`,
  `Uplift: ${signed(r.uplift.conservative)} (80 % band ${signed(r.uplift.band80[0])} to ${signed(r.uplift.band80[1])}), ${r.uplift.basis}`,
];

/** "Canary of Customer A at 20 %" for the rollout rows; "No canary yet" with none. */
export const rolloutLine = (rows: readonly { stage: string; region: string; share: number }[]): string =>
  rows.length ? rows.map((r) => `${r.stage === 'paused' ? 'Paused canary' : 'Canary'} of ${r.region} at ${r.share} %`).join('; ') : 'No canary yet';
