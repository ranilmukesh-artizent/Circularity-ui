import { describe, expect, it } from 'vitest';
import type { Jdm } from '../../api/marketTables';
import { check, FUNCTION_OFF, MONEY_OFF } from './tableEdit';

const table = (over: Record<string, unknown> = {}, extra: Jdm['nodes'] = []): Jdm => ({
  nodes: [
    { id: 'n_in', type: 'inputNode', name: 'Request' },
    {
      id: 'n_tbl', type: 'decisionTableNode', name: 'Table',
      content: {
        hitPolicy: 'first',
        inputs: [{ id: 'in_family', name: 'family', field: 'family', type: 'expression' }],
        outputs: [{ id: 'out_swap', name: 'swap_allowed', field: 'swap_allowed', type: 'expression' }],
        rules: [{ _id: 'r1', in_family: '"CRH"', out_swap: 'true' }],
        ...over,
      },
    },
    { id: 'n_out', type: 'outputNode', name: 'Response' },
    ...extra,
  ],
  edges: [],
}); // prettier-ignore

describe('P9-8.16 tableEdit.check', () => {
  it('passes a valid table', () => {
    expect(check(table(), ['family', 'market'])).toEqual([]);
  });
  it('refuses a function node with the message', () => {
    expect(check(table({}, [{ id: 'fx', type: 'functionNode' }]), ['family'])).toEqual([FUNCTION_OFF]);
    expect(FUNCTION_OFF).toBe('Function nodes are off: tables hold conditions and outputs only.');
  });
  it('refuses an expression node', () => {
    expect(check(table({}, [{ id: 'ex', type: 'expressionNode' }]), ['family'])).toEqual([FUNCTION_OFF]);
  });
  it('refuses an unknown input column', () => {
    expect(check(table(), ['market'])).toEqual(['family is not an input of this table.']);
  });
  it('refuses an empty output cell', () => {
    const t = table({ rules: [{ _id: 'r1', in_family: '"CRH"', out_swap: ' ' }] });
    expect(check(t, ['family'])).toEqual(['Rule r1 has no value for swap_allowed.']);
  });
  it('refuses a money output column', () => {
    const t = table({ outputs: [{ id: 'out_swap', name: 'swap_allowed', field: 'swap_allowed', type: 'money' }] });
    expect(check(t, ['family'])).toEqual([MONEY_OFF]);
    expect(MONEY_OFF).toBe('Rates live in rate cards, not in tables.');
  });
});
