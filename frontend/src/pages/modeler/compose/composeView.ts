/* Pure helpers of the Compose panel (plan 9, P9-8.18, story X-10): step labels, which systems need an adapter or wait for
   their owner, the mapping summary, and the line a step's state shows. No React, no calls. */
import type { ComposeSystem, CompositionStep, MappingCounts, StepState, SystemStatus } from '../../../api/compose';
import type { MappingBand } from '../../../api/integration';

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
