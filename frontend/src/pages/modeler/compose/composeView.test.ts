import { describe, expect, it } from 'vitest';
import type { ComposeSystem } from '../../../api/compose';
import { STEP_ITEMS, awaitingOwner, canMarkMappingDone, mappingSummary, needsAdapter, stateLine, statusLabel, totalMapping } from './composeView';

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
