import { describe, expect, it } from 'vitest';
import type { ComposeSystem, PublishInfo, PublishReport } from '../../../api/compose';
import {
  AUTONOMY_ITEMS, BOUNDS_TEXT, MAKER_CHECKER, NEEDS_REPLAY, STEP_ITEMS, approveBlock, autonomyLabel, awaitingOwner, canMarkMappingDone, cleanRows,
  makers, mappingSummary, needsAdapter, parseShare, publishBlock, publishLabel, reportLines, rolloutLine, stageLine, sentBackPin, stateLine, statusLabel,
  thresholdError, thresholdText, totalMapping,
} from './composeView';

const zero = { fields: 0, pre_ticked: 0, check: 0, none: 0, asked_owner: 0 };
const sys = (name: string, status: ComposeSystem['status'], mapping = zero): ComposeSystem => ({
  name, system_type: 'erp', source_id: status === 'needs_adapter' ? null : name.toLowerCase(), registry: [], status, mapping,
});

describe('compose steps and systems (X-10, P9-8.18)', () => {
  it('x-10: the five steps are labelled in order', () => {
    expect(STEP_ITEMS.map(([id]) => id)).toEqual(['describe', 'mapping', 'agents', 'approve', 'publish']);
    expect(STEP_ITEMS[1][1]).toBe('Adapter mapping');
  });

  it('x-10: a system with no source needs an adapter', () => {
    const all = [sys('ERP', 'connected'), sys('Repair log', 'needs_adapter'), sys('CRM', 'test_connection')];
    expect(needsAdapter(all)).toEqual(['Repair log']);
  });

  it('x-10: a system whose test connection waits for its owner is awaiting the owner', () => {
    const all = [sys('Repair log', 'awaiting_owner'), sys('ERP', 'connected')];
    expect(awaitingOwner(all)).toEqual(['Repair log']);
    expect(statusLabel('awaiting_owner')).toBe('Waiting for the system owner');
    expect(statusLabel('needs_adapter')).toBe('Needs an adapter');
  });

  it('x-10: the mapping summary counts the bands', () => {
    const rows = [{ band: 'pre_ticked' }, { band: 'pre_ticked' }, { band: 'check' }, { band: 'none' }, { band: 'none' }] as { band: 'pre_ticked' | 'check' | 'none' }[];
    expect(mappingSummary(rows, 1)).toEqual({ fields: 5, pre_ticked: 2, check: 1, none: 2, asked_owner: 1 });
    const a = sys('A', 'connected', { fields: 4, pre_ticked: 2, check: 1, none: 1, asked_owner: 0 });
    const b = sys('B', 'connected', { fields: 3, pre_ticked: 1, check: 1, none: 1, asked_owner: 2 });
    expect(totalMapping([a, b])).toEqual({ fields: 7, pre_ticked: 3, check: 2, none: 2, asked_owner: 2 });
  });

  it('x-10: mark done waits while a field waits for its owner', () => {
    expect(canMarkMappingDone([sys('A', 'connected')])).toBe(true);
    expect(canMarkMappingDone([sys('A', 'connected', { ...zero, asked_owner: 1 })])).toBe(false);
  });

  it('x-10: the state line says what is left', () => {
    expect(stateLine({ state: 'todo' })).toBe('Not done');
    expect(stateLine({ state: 'done' })).toBe('Done');
    expect(stateLine({ state: 'sent_back', note: { reason: 'Check the grades.', by: 'approver', at: '2026-11-26T10:00:00Z' } })).toBe('Sent back: Check the grades.');
  });
});

const report: PublishReport = {
  run_id: 1, n_items: 40, n_decided: 38, days: 20, route_mix: [{ route: 'redeploy', actual_pct: 40, flow_pct: 55 }],
  straight_through_pct: 62.5, approvals_per_day: 3.2, exceptions_per_day: 0.4,
  uplift: { primary: 2.8, band80: [-1, 5.4], band95: [-2, 6.5], secondary: 2.1, bias: 1, conservative: 2.1, basis: 'modelled' },
};
const info = (over: Partial<PublishInfo> = {}): PublishInfo => ({ flow_id: 3, flow_status: 'shadow', flow_stage: 'shadow', report, rollouts: [], ...over });
const made = { status: 'submitted' as const, created_by: 'planner-a', submitted_by: 'planner-a', editors: ['planner-a', 'planner.b'] };

describe('compose agents, approve and publish (X-10, P9-8.20)', () => {
  it('x-10: the three autonomy levels are labelled as the step shows them', () => {
    expect(AUTONOMY_ITEMS.map(([k]) => k)).toEqual(['recommend', 'limits', 'alone']);
    expect(autonomyLabel('limits')).toBe('Act within limits');
    expect(autonomyLabel('recommend')).toBe('Recommend only');
  });

  it('x-10: the threshold is 65 to 85 percent, as the server says', () => {
    expect(thresholdError(60)).toBe(BOUNDS_TEXT);
    expect(thresholdError(90)).toBe(BOUNDS_TEXT);
    expect(thresholdError(65)).toBeNull();
    expect(thresholdError(85)).toBeNull();
    expect(thresholdError(Number.NaN)).toBe(BOUNDS_TEXT);
    expect(thresholdText(0.8)).toBe('80 %');
  });

  it('x-10: rows are sent with limits only for Act within limits', () => {
    const sent = cleanRows([
      { stage: 'receive', agent_id: ' Intake ', autonomy: 'alone', limits: { value_limit: 5 } },
      { stage: 'decide', agent_id: 'Decide', autonomy: 'limits', limits: { value_limit: 600, bulk_limit: -1 } },
      { stage: 'close', agent_id: 'Close', autonomy: 'limits', limits: {} },
    ]);
    expect(sent).toEqual([
      { stage: 'receive', agent_id: 'Intake', autonomy: 'alone' },
      { stage: 'decide', agent_id: 'Decide', autonomy: 'limits', limits: { value_limit: 600 } },
      { stage: 'close', agent_id: 'Close', autonomy: 'limits' },
    ]);
    expect(stageLine({ stage: 'decide', agent_id: 'x', autonomy: 'limits', limits: { value_limit: 600, bulk_limit: 10 } })).toBe('Act within limits ($600, 10 items)');
    expect(stageLine({ stage: 'decide', agent_id: 'x', autonomy: 'alone' })).toBe('Act alone');
  });

  it('x-10: the maker, the submitter and every editor cannot approve', () => {
    expect(makers(made)).toEqual(['planner-a', 'planner.b']);
    for (const who of ['planner-a', 'planner.b']) expect(approveBlock(made, who)).toBe(MAKER_CHECKER);
    expect(approveBlock(made, 'approver')).toBeNull();
    expect(approveBlock({ ...made, status: 'draft' }, 'approver')).toBe('It is not waiting for approval.');
  });

  it('x-10: publish waits for an approval, a flow in shadow and a replay report', () => {
    expect(publishBlock('submitted', info())).toBe('Approve the composition first.');
    expect(publishBlock('approved', info({ flow_stage: 'replay' }))).toMatch(/into shadow/);
    expect(publishBlock('approved', info({ flow_stage: null, flow_id: null }))).toMatch(/into shadow/);
    expect(publishBlock('approved', info({ report: null }))).toBe(NEEDS_REPLAY);
    expect(publishBlock('approved', info())).toBeNull();
    expect(publishBlock('published', info({ flow_stage: 'canary' }))).toMatch(/widen the canary/);
  });

  it('x-10: the share is a whole number from 1 to 99 and the button says where and how much', () => {
    expect(['20', ' 5 ', '99', '1'].map(parseShare)).toEqual([20, 5, 99, 1]);
    expect(['0', '100', '2.5', '', 'x', '-3'].map(parseShare)).toEqual([null, null, null, null, null, null]);
    expect(publishLabel('Customer A', 20)).toBe('Publish to Customer A at 20 %');
    expect(publishLabel(' ', 20)).toBe('Publish to a region at 20 %');
  });

  it('x-10: the replay report lists the four numbers and the rollout line the canary rows', () => {
    expect(reportLines(report)).toEqual([
      'Straight-through: 62.5 %', 'Approvals a day: 3.2', 'Exceptions a day: 0.4',
      'Uplift: +2.1 % (80 % band -1.0 % to +5.4 %), modelled',
    ]);
    expect(rolloutLine([])).toBe('No canary yet');
    expect(rolloutLine([{ stage: 'canary', region: 'Customer A', share: 20 }])).toBe('Canary of Customer A at 20 %');
    expect(rolloutLine([{ stage: 'paused', region: 'FR', share: 10 }])).toBe('Paused canary of FR at 10 %');
  });
});

describe('sentBackPin', () => {
  it('is null unless the step was sent back', () => {
    expect(sentBackPin(undefined)).toBeNull();
    expect(sentBackPin({ state: 'done' })).toBeNull();
  });
  it('names who, why and the node', () => {
    expect(sentBackPin({ state: 'sent_back', note: { reason: 'Act.', by: 'approver', at: 'x', node_id: 'condition' } })).toEqual({ by: 'approver', reason: 'Act.', node: 'condition' });
    expect(sentBackPin({ state: 'sent_back', note: { reason: 'Act.', by: 'approver', at: 'x' } })?.node).toBeNull();
  });
});
