// @vitest-environment jsdom
// The Markdown component (plan 11, E1 to E4): what it draws, what it never draws, and that a half-written answer is safe.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { Markdown } from './Markdown';
import { safeHref, settle } from './markdownText';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
let host: HTMLDivElement;
let root: Root;
beforeAll(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
});
beforeEach(() => {
  host = document.createElement('div');
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
const draw = (text: string, streaming = false) => {
  act(() => root.render(<Markdown text={text} streaming={streaming} />));
  return host;
};

const ANSWER = [
  '# Result', '', 'Two **cases** wait; see `RT-1048` and [the case](#/product/RT-1048).', '',
  '- one', '  - nested', '- two', '', '| Case | Value |', '| --- | ---: |', '| RT-1048 | 12,400 |', '', '```json', '{"a": 1}', '```', '',
  'More at [docs](https://example.com/x) and ~~old~~.',
].join('\n');

describe('Markdown', () => {
  it('draws headings, nested lists, a table, inline and block code and links', () => {
    const el = draw(ANSWER);
    expect(el.querySelector('h1,h2')).toBeNull();
    expect(el.querySelector('h3')?.textContent).toBe('Result');
    expect(el.querySelectorAll('ul ul li')).toHaveLength(1);
    expect(el.querySelectorAll('.md-table table th')).toHaveLength(2);
    expect(el.querySelector('p code')?.textContent).toBe('RT-1048');
    expect(el.querySelector('.md-pre pre code')?.textContent).toContain('"a": 1');
    expect(el.querySelector('.md-copy')?.textContent).toBe('Copy');
    const ext = el.querySelector<HTMLAnchorElement>('a[href="https://example.com/x"]');
    expect(ext?.target).toBe('_blank');
    expect(ext?.rel).toBe('noopener noreferrer');
    const app = el.querySelector<HTMLAnchorElement>('a[href="#/product/RT-1048"]');
    expect(app?.getAttribute('target')).toBeNull();
    expect(el.querySelector('del')?.textContent).toBe('old');
  });

  it('never makes an element or a handler from script, an image or a javascript: link', () => {
    const el = draw('<script>alert(1)</script>\n\nSee <img src=x onerror="alert(2)"> [bad](javascript:alert(3)) ![pic](https://example.com/p.png) ![x](javascript:alert(4))');
    expect(el.querySelector('script, img')).toBeNull();
    // the markup is shown as text: no element carries an on* attribute
    expect([...el.querySelectorAll('*')].some((n) => n.getAttributeNames().some((a) => a.startsWith('on')))).toBe(false);
    expect(el.querySelector('a[href^="javascript"]')).toBeNull();
    expect(el.textContent).toContain('bad');
    const pic = el.querySelector<HTMLAnchorElement>('a[href="https://example.com/p.png"]');
    expect(pic?.textContent).toBe('pic');
    expect(el.textContent).toContain('x');
  });

  it('keeps a plain one-line answer as one paragraph with the same text', () => {
    const el = draw('Rule 7 holds RT-1048 for the approver.');
    expect(el.querySelectorAll('p')).toHaveLength(1);
    expect(el.querySelector('p')?.textContent).toBe('Rule 7 holds RT-1048 for the approver.');
  });

  it('renders the sample answer cut at every length, streaming or not, without throwing', () => {
    for (let n = 0; n <= ANSWER.length; n++) {
      expect(() => draw(ANSWER.slice(0, n), true)).not.toThrow();
      expect(() => draw(ANSWER.slice(0, n))).not.toThrow();
    }
    expect(host.querySelector('.md-plain')).toBeNull();
  }, 60_000);
});

describe('settle', () => {
  it('holds back a lone marker, a table without its delimiter row and an open backtick', () => {
    expect(settle('Steps:\n-')).toBe('Steps:');
    expect(settle('Steps:\n1.')).toBe('Steps:');
    expect(settle('Intro\n\n| A | B |')).toBe('Intro');
    expect(settle('Intro\n\n| A | B |\n| ---')).toBe('Intro');
    expect(settle('Intro\n\n| A | B |\n| --- | --- |\n| 1')).toContain('| 1');
    expect(settle('use `abc')).toBe('use `abc`');
    expect(settle('``')).toBe('');
  });
  it('closes bold and a link, drops a trailing emphasis marker', () => {
    expect(settle('a **bold')).toBe('a **bold**');
    expect(settle('a [link](https://x.io/p')).toBe('a [link](https://x.io/p)');
    expect(settle('a [lin')).toBe('a lin');
    expect(settle('a *')).toBe('a ');
  });
  it('leaves text inside an open code fence alone and a finished line unchanged', () => {
    expect(settle('```\nx **\n-')).toBe('```\nx **\n-');
    expect(settle('Done. Two cases.')).toBe('Done. Two cases.');
  });
});

describe('safeHref', () => {
  it('keeps http, https, mailto and hash links only', () => {
    expect(safeHref('https://a.io')).toBe('https://a.io');
    expect(safeHref('mailto:a@b.io')).toBe('mailto:a@b.io');
    expect(safeHref('#/product/RT-1048')).toBe('#/product/RT-1048');
    for (const u of ['javascript:alert(1)', 'JaVa\nScRiPt:alert(1)', 'data:text/html,x', 'vbscript:x', '/relative', 'ftp://x', '#top', '']) {
      expect(safeHref(u)).toBeNull();
    }
  });
});
