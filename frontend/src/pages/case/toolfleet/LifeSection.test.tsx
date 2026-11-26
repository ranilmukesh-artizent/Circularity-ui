// @vitest-environment jsdom
// Plan 9, P9-3.9 (TF-06): the wear and remaining life of a tool, the worked example.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { LifeView } from '../../../api/toolFleet';
import { LifeSection, confidenceLine, rulLine, wtiLine } from './LifeSection';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const PER = [
  ['Motor armature', 943, 79, 21, 'pack'], ['Gearbox', 943, 63, 37, 'pack'], ['Electronics module', 820, 41, 59, 'pack'], ['Piston and seal kit', 368, 61, 39, 'pack'],
] as const;
const life = (over: Partial<LifeView> = {}): LifeView => ({
  wti: 65, rul_tool: 21, rul_tool_hours: 223.5, weakest: 'Motor armature', confidence: 'High', range: null, inputs: {},
  table_version: 'tf-life-table-1', rule_version: 'tf-life-1',
  per_component: PER.map(([name, used_hours, consumed_pct, rul_pct, source]) => ({ name, used_hours, consumed_pct, rul_pct, source })),
  ...over,
});

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const render = (l: LifeView | null) => {
  act(() => root.render(<LifeSection life={l} />));
  return host;
};

describe('life lines', () => {
  it('says the wear index, the remaining life with its weakest component and the confidence', () => {
    expect(wtiLine(life())).toBe('WTI 65');
    expect(rulLine(life())).toBe('RUL 21% (Motor armature), 223.5 h');
    expect(confidenceLine(life())).toBe('High');
    expect(confidenceLine(life({ confidence: 'Low', range: [0, 53] }))).toBe('Low: 0% to 53% without telematics');
  });
});

describe('LifeSection', () => {
  it('renders the worked example: a row for each component with its rating source and the table version', () => {
    const h = render(life());
    expect(h.querySelector('[data-testid="tf-life-wti"]')?.textContent).toBe('WTI 65');
    expect(h.querySelector('[data-testid="tf-life-rul"]')?.textContent).toBe('RUL 21% (Motor armature), 223.5 h');
    expect(h.querySelectorAll('tbody tr')).toHaveLength(4);
    expect(h.querySelector('[data-testid="tf-life-Motor armature"]')?.textContent).toContain('21%');
    expect(h.textContent).toContain('Pack table tf-life-table-1');
    expect(h.querySelector('.chip.ok')?.textContent).toBe('High');
  });
  it('shows a PLM rating as PLM and a Low confidence with its range', () => {
    const l = life({ confidence: 'Low', range: [0, 53] });
    l.per_component[0].source = 'plm';
    const h = render(l);
    expect(h.querySelector('.chip.bad')?.textContent).toBe('Low: 0% to 53% without telematics');
    expect(h.querySelector('[data-testid="tf-life-Motor armature"]')?.textContent).toContain('PLM');
  });
  it('renders nothing for a case with no life result', () => {
    expect(render(null).innerHTML).toBe('');
  });
  it('says when the telematics and the inspection disagree, naming the components', () => {
    const text = 'Telematics and inspection disagree: grade A, WTI 65 (Motor armature 79%, Gearbox 63%, Piston and seal kit 61%)';
    act(() => root.render(<LifeSection life={life()} disagreement={{ text, components: ['Motor armature', 'Gearbox', 'Piston and seal kit'] }} />));
    const line = host.querySelector('[data-testid="tf-disagreement"]');
    expect(line?.textContent).toContain(text);
    expect(line?.textContent).toContain('Quality');
  });
  it('shows no disagreement line when they agree', () => {
    act(() => root.render(<LifeSection life={life()} disagreement={null} />));
    expect(host.querySelector('[data-testid="tf-disagreement"]')).toBeNull();
  });
});
