// @vitest-environment jsdom
// The exact markup of the KPI tile, icon tile, change and sparkline: the demo's stylesheet depends on it (step E2).
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { Delta, pctDelta } from './Delta';
import { IconTile } from './IconTile';
import { Kpi } from './Kpi';
import { Spark } from './Spark';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const html = (ui: React.ReactNode) => {
  act(() => root.render(ui));
  return host.innerHTML.replace(/<svg[^>]*aria-hidden="true"[^>]*>(?:(?!<\/svg>)[\s\S])*<\/svg>/g, (s) => (s.includes('frsp') ? s : '<svg/>'));
};

describe('IconTile', () => {
  it('is a tinted span around the icon, neutral when no hue is given', () => {
    expect(html(<IconTile ic="alert" h="int" cls="sm" />)).toBe('<span class="frit sm" style="--c: var(--h-int);"><svg/></span>');
    expect(html(<IconTile ic="alert" />)).toBe('<span class="frit " style="--c: var(--h-neutral);"><svg/></span>');
  });
});

describe('Kpi', () => {
  it('a plain tile has data-k, no data-n and no change row', () => {
    expect(html(<Kpi ic="alert" h="dec" v={3} l="Open conflicts" />)).toBe(
      '<div class="frkpi" data-k=""><span class="frit " style="--c: var(--h-dec);"><svg/></span>'
      + '<span class="frkv"><b class="num">3</b><span class="frkl">Open conflicts</span></span></div>',
    );
  });
  it('a link tile carries data-n, the note and the change', () => {
    const d = { cls: 'good', tip: 'Against last month', text: '▲ 4%' };
    expect(html(<Kpi ic="checks" h="int" v="12" l="Passing" sub="today" k="ok" n="" href="#/checks" delta={<Delta d={d} />} />)).toBe(
      '<a class="frkpi" href="#/checks" data-k="ok" data-n=""><span class="frit " style="--c: var(--h-int);"><svg/></span>'
      + '<span class="frkv"><b class="num">12</b><span class="frkl">Passing</span><span class="note">today</span></span>'
      + '<span class="frkd"><span class="frd good" data-tip="Against last month">▲ 4%</span></span></a>',
    );
  });
  it('a sparkline uses the tile hue', () => {
    expect(html(<Kpi ic="clock" h="money" v={1} l="x" sp={[0, 1]} />)).toContain(
      '<span class="frkd"><svg class="frsp" viewBox="0 0 72 26" aria-hidden="true"><polyline points="0.0,23.0 72.0,3.0" fill="none" stroke="var(--h-money)"',
    );
  });
});

describe('Spark and pctDelta', () => {
  it('draws nothing for fewer than two points', () => {
    expect(html(<Spark v={[5]} />)).toBe('');
  });
  it('words the change as the Connection Fabric did', () => {
    expect(pctDelta(110, 100, true)).toEqual({ cls: 'good', tip: 'Against the same measure 30 days earlier', text: '▲ 10%' });
    expect(pctDelta(95, 100, true)?.text).toBe('▼ 5.0%');
    expect(pctDelta(95, 100, null)?.cls).toBe('');
    expect(pctDelta(5, 0, true)).toBeNull();
  });
});
