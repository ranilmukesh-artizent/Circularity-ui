// @vitest-environment jsdom
// Route line, tally strip and stage track: the markup the 28 Nov 2026 pages and their smokes rely on.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { RouteLine, type Stop } from './RouteLine';
import { StageTrack } from './StageTrack';
import { TallyStrip } from './TallyStrip';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const draw = (ui: React.ReactNode) => { act(() => root.render(ui)); return host; };
const $$ = (sel: string) => Array.from(host.querySelectorAll(sel));

const STOPS: Stop[] = [
  { id: 'a', label: 'A', state: 'done', note: 'Done' },
  { id: 'b', label: 'B', state: 'now', note: 'Next' },
  { id: 'c', label: 'C', state: 'back', note: 'Sent back' },
  { id: 'd', label: 'D', state: 'todo', note: 'Not started' },
];
const LANES: [string, string] = ['You', 'An approver'];

describe('RouteLine', () => {
  it('draws one li per stop with its state and id', () => {
    draw(<RouteLine stops={STOPS} handover={2} lanes={LANES} label="Steps" />);
    expect(host.querySelector('ol.rl')?.getAttribute('aria-label')).toBe('Steps');
    expect($$('li').map((l) => l.getAttribute('data-stop'))).toEqual(['a', 'b', 'c', 'd']);
    expect($$('li').map((l) => l.getAttribute('data-state'))).toEqual(['done', 'now', 'back', 'todo']);
    expect($$('li')[0].textContent).toContain('Done');
  });
  it('uses plain spans without hrefFor and links with it', () => {
    draw(<RouteLine stops={STOPS} handover={2} lanes={LANES} label="x" />);
    expect($$('a')).toHaveLength(0);
    expect($$('span.rl-stop')).toHaveLength(4);
    draw(<RouteLine stops={STOPS} handover={2} lanes={LANES} label="x" hrefFor={(id) => (id === 'c' ? null : `#/s?step=${id}`)} />);
    expect($$('a.rl-stop').map((a) => a.getAttribute('href'))).toEqual(['#/s?step=a', '#/s?step=b', '#/s?step=d']);
    expect($$('li[data-stop=c] span.rl-stop')).toHaveLength(1);
  });
  it('marks only the current stop with aria-current=step', () => {
    draw(<RouteLine stops={STOPS} handover={2} lanes={LANES} label="x" current="b" hrefFor={(id) => '#' + id} />);
    expect($$('[aria-current]').map((e) => e.closest('li')?.getAttribute('data-stop'))).toEqual(['b']);
    expect($$('[aria-current]')[0].getAttribute('aria-current')).toBe('step');
    draw(<RouteLine stops={STOPS} handover={2} lanes={LANES} label="x" />);
    expect($$('[aria-current]')).toHaveLength(0);
  });
  it('captions each lane once, on its first stop', () => {
    draw(<RouteLine stops={STOPS} handover={2} lanes={LANES} label="x" />);
    const caps = $$('.rl-lane');
    expect(caps.map((c) => c.textContent)).toEqual(['You', 'An approver']);
    expect(caps.map((c) => c.closest('li')?.getAttribute('data-stop'))).toEqual(['a', 'c']);
    expect($$('li').map((l) => l.classList.contains('low'))).toEqual([false, false, true, true]);
  });
  it('draws the step svg only on the stop before the handover', () => {
    draw(<RouteLine stops={STOPS} handover={2} lanes={LANES} label="x" />);
    expect($$('svg.rl-step')).toHaveLength(1);
    expect($$('svg.rl-step')[0].closest('li')?.getAttribute('data-stop')).toBe('b');
    expect($$('li[data-stop=b]')[0].classList.contains('hand')).toBe(true);
  });
  it('draws no step and one caption when there is one lane', () => {
    draw(<RouteLine stops={STOPS} handover={STOPS.length} lanes={LANES} label="x" />);
    expect($$('svg.rl-step')).toHaveLength(0);
    expect($$('.rl-lane')).toHaveLength(1);
  });
  it('draws a check for done and a bang for back, nothing for the rest', () => {
    draw(<RouteLine stops={STOPS} handover={2} lanes={LANES} label="x" />);
    expect($$('li').map((l) => l.querySelectorAll('.rl-dot svg').length)).toEqual([1, 0, 1, 0]);
  });
});

describe('TallyStrip', () => {
  const href = (id: string | null) => '#/tasks' + (id ? '?show=' + id : '');
  it('draws a link per group with its count, label and late words', () => {
    draw(<TallyStrip label="Waiting" cur={null} hrefFor={href} groups={[{ id: 'approval', label: 'Approvals', n: 3, late: 1 }, { id: 'task', label: 'Tasks', n: 0, late: 0, gap: true }]} />);
    const g = $$('a.tly-g');
    expect(g.map((a) => a.getAttribute('data-group'))).toEqual(['approval', 'task']);
    expect(g.map((a) => a.getAttribute('href'))).toEqual(['#/tasks?show=approval', '#/tasks?show=task']);
    expect(g[0].querySelector('.tly-cap b')?.textContent).toBe('3');
    expect(g[0].textContent).toContain('Approvals');
    expect(g[0].querySelector('.tly-late')?.textContent).toBe('1 late');
    expect(g[1].querySelector('.tly-late')).toBeNull();
    expect(g[1].classList.contains('none')).toBe(true);
    expect(g[1].classList.contains('gap')).toBe(true);
    expect(g[0].classList.contains('gap')).toBe(false);
  });
  it('draws one mark per item with the late ones first', () => {
    draw(<TallyStrip label="x" cur={null} hrefFor={href} groups={[{ id: 'g', label: 'G', n: 5, late: 2 }]} />);
    const marks = $$('.tly-marks i');
    expect(marks).toHaveLength(5);
    expect(marks.map((m) => m.classList.contains('late'))).toEqual([true, true, false, false, false]);
    expect($$('.tly-more')).toHaveLength(0);
  });
  it('caps the marks at 36 with +N', () => {
    draw(<TallyStrip label="x" cur={null} hrefFor={href} groups={[{ id: 'g', label: 'G', n: 50, late: 40 }]} />);
    expect($$('.tly-marks i')).toHaveLength(36);
    expect($$('.tly-marks i.late')).toHaveLength(36);
    expect($$('.tly-more')[0].textContent).toBe('+14');
    expect($$('.tly-cap b')[0].textContent).toBe('50');
    expect($$('.tly-late')[0].textContent).toBe('40 late');
  });
  it('has no +N at exactly 36', () => {
    draw(<TallyStrip label="x" cur={null} hrefFor={href} groups={[{ id: 'g', label: 'G', n: 36, late: 0 }]} />);
    expect($$('.tly-marks i')).toHaveLength(36);
    expect($$('.tly-more')).toHaveLength(0);
  });
  it('marks the group in view and links it back to the whole list', () => {
    draw(<TallyStrip label="x" cur="task" hrefFor={href} groups={[{ id: 'approval', label: 'A', n: 1, late: 0 }, { id: 'task', label: 'T', n: 1, late: 0 }]} />);
    const [a, t] = $$('a.tly-g');
    expect(a.getAttribute('aria-current')).toBeNull();
    expect(t.getAttribute('aria-current')).toBe('true');
    expect(a.getAttribute('href')).toBe('#/tasks?show=approval');
    expect(t.getAttribute('href')).toBe('#/tasks');
    expect(host.querySelector('nav.tly')?.getAttribute('aria-label')).toBe('x');
  });
});

describe('StageTrack', () => {
  const segs = [{ l: 'Intake', v: 1200, c: '#111' }, { l: 'Decide', v: 0, c: '#222' }, { l: 'Close', v: 30, c: '#333' }];
  it('draws the total, a length per non-zero part and every part number', () => {
    draw(<StageTrack segs={segs} center="1,230" sub="decisions" />);
    expect(host.querySelector('.stk-total b')?.textContent).toBe('1,230');
    expect(host.querySelector('.stk-total span')?.textContent).toBe('decisions');
    expect($$('.stk-line i')).toHaveLength(2);
    expect(($$('.stk-line i')[0] as HTMLElement).style.flexGrow).toBe('1200');
    expect($$('.stk-parts li')).toHaveLength(3);
    expect($$('.stk-parts li')[1].classList.contains('none')).toBe(true);
    expect($$('.stk-parts li')[0].textContent).toContain('Intake');
  });
  it('labels the line from the parts unless a label is given', () => {
    draw(<StageTrack segs={segs} center="1" />);
    const label = host.querySelector('.stk-line')?.getAttribute('aria-label') ?? '';
    expect(label).toContain('Intake');
    expect(label).toContain('Close');
    expect(host.querySelector('.stk-total span')).toBeNull();
    draw(<StageTrack segs={segs} center="1" label="Mine" />);
    expect(host.querySelector('.stk-line')?.getAttribute('aria-label')).toBe('Mine');
  });
  it('draws one empty length when every part is zero or there are none', () => {
    draw(<StageTrack segs={[{ l: 'A', v: 0, c: '#1' }]} center="0" />);
    expect($$('.stk-line i.none')).toHaveLength(1);
    draw(<StageTrack segs={[]} center="0" />);
    expect($$('.stk-line i.none')).toHaveLength(1);
    expect($$('.stk-parts li')).toHaveLength(0);
  });
});
