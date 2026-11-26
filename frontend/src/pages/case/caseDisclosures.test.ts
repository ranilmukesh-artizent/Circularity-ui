import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { GateRow } from '../../api/case';
import { Disclosures } from './CaseBlocks';
import { gateLine } from './gates';

const html = (disclosures?: string[]) => renderToStaticMarkup(createElement(Disclosures, { r: { disclosures } }));

describe('P9-9.8 route disclosures (UC-24)', () => {
  it('shows the title brand a route must disclose', () => {
    const out = html(['Title brand: rebuilt']);
    expect(out).toContain('Disclose:');
    expect(out).toContain('Title brand: rebuilt');
  });

  it('shows every disclosure of a route, and nothing for a route without one', () => {
    expect(html(['Title brand: flood', 'Title brand: salvage'])).toContain('Title brand: flood; Title brand: salvage');
    expect(html([])).toBe('');
    expect(html(undefined)).toBe('');
  });

  it('words a disclosing gate as disclosed, not as passed', () => {
    const gate: GateRow = {
      id: 'G-VEH-BRAND', name: 'Title brand disclosed', type: 'Compliance', stage: 'match', stageLabel: 'Title and finance', passed: true,
      kind: 'disclose', routes: [], routeNames: [], hold: false, step: null, owner: 'Title desk', evidence: [], missing: [],
      reason: 'Title brand: rebuilt', locked: false,
    };
    expect(gateLine(gate)).toBe('Disclosed: Title brand: rebuilt');
  });
});
