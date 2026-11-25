import { describe, expect, it } from 'vitest';
import type { Jdm } from '../../api/marketTables';
import { blankRow, jdmToRows, rowsToJdm, tableLabel, valuesFromText } from './tables';

/** The pack's cover_terms table (packs/tool_fleet.json, market_tables). */
const COVER: Jdm = {
  nodes: [
    { id: 'n_in', type: 'inputNode', name: 'Request', position: { x: 100, y: 100 } },
    {
      id: 'n_tbl', type: 'decisionTableNode', name: 'Table', position: { x: 360, y: 100 },
      content: {
        hitPolicy: 'first',
        inputs: ['market', 'family', 'cover_type', 'age_months'].map((k) => ({ id: `in_${k}`, name: k, field: k, type: 'expression' })),
        outputs: ['repair_covered', 'swap_allowed', 'upgrade_allowed', 'reason'].map((k) => ({ id: `out_${k}`, name: k, field: k, type: 'expression' })),
        rules: [
          { _id: 'r1', in_market: '', in_family: '"CRH"', in_cover_type: '"fleet"', in_age_months: '', out_repair_covered: 'true', out_swap_allowed: 'true', out_upgrade_allowed: 'true', out_reason: '"Fleet cover: swap allowed for cordless tools"' },
          { _id: 'r2', in_market: '', in_family: '', in_cover_type: '"fleet"', in_age_months: '', out_repair_covered: 'true', out_swap_allowed: 'false', out_upgrade_allowed: 'false', out_reason: '"Fleet cover: repair covered"' },
          { _id: 'r3', in_market: '', in_family: '', in_cover_type: '"warranty"', in_age_months: '<= 24', out_repair_covered: 'true', out_swap_allowed: 'false', out_upgrade_allowed: 'false', out_reason: '"Warranty: repair covered"' },
          { _id: 'r4', in_market: '', in_family: '', in_cover_type: '', in_age_months: '', out_repair_covered: 'false', out_swap_allowed: 'false', out_upgrade_allowed: 'false', out_reason: '"No cover"' },
        ],
      },
    },
    { id: 'n_out', type: 'outputNode', name: 'Response', position: { x: 620, y: 100 } },
  ],
  edges: [
    { id: 'e1', sourceId: 'n_in', targetId: 'n_tbl', type: 'edge' },
    { id: 'e2', sourceId: 'n_tbl', targetId: 'n_out', type: 'edge' },
  ],
}; // prettier-ignore

describe('the market table grid (plan 9, P9-4.2, SD-03)', () => {
  it('sd-03: jdmToRows reads the cover_terms rows in first-hit order', () => {
    const g = jdmToRows(COVER);
    expect(g.hitPolicy).toBe('first');
    expect(g.inputs).toEqual(['market', 'family', 'cover_type', 'age_months']);
    expect(g.rows.map((r) => r.id)).toEqual(['r1', 'r2', 'r3', 'r4']);
    expect(g.rows[0].inputs).toEqual(['', '"CRH"', '"fleet"', '']);
    expect(g.rows[0].outputs[3]).toBe('"Fleet cover: swap allowed for cordless tools"');
  });

  it('sd-03: rowsToJdm and jdmToRows round-trip the cover_terms table', () => {
    const g = jdmToRows(COVER);
    expect(rowsToJdm(COVER, g)).toEqual(COVER);
    expect(jdmToRows(rowsToJdm(COVER, g))).toEqual(g);
  });

  it('sd-03: an edited cell and a new rule reach the graph; the other nodes stay', () => {
    const g = jdmToRows(COVER);
    g.rows[2].inputs[3] = '<= 12';
    g.rows.splice(3, 0, blankRow(g));
    const j = rowsToJdm(COVER, g);
    expect(j.nodes.filter((n) => n.type !== 'decisionTableNode')).toEqual(COVER.nodes.filter((n) => n.type !== 'decisionTableNode'));
    expect(jdmToRows(j).rows.map((r) => r.id)).toEqual(['r1', 'r2', 'r3', 'r5', 'r4']);
    expect(jdmToRows(j).rows[2].inputs[3]).toBe('<= 12');
  });

  it('sd-03: tableLabel names the table and its version', () => {
    expect(tableLabel({ market: 'DE', title: 'labour rates', version: 1 })).toBe('DE labour rates v1');
  });

  it('sd-03: valuesFromText keeps numbers and nulls what is not one', () => {
    expect(valuesFromText({ per_hour: '48', markup: '0.35', bad: 'x', empty: ' ' })).toEqual({ per_hour: 48, markup: 0.35, bad: null, empty: null });
  });
});
