// @vitest-environment jsdom
// The exact markup of the three jsonHtml ports, the status pill, the panel and the vendor initials (step E2).
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { JsonView } from './JsonView';
import { Panel } from './Panel';
import { KeyedStatus, StatusPill } from './StatusPill';
import { VendorLogo } from './VendorLogo';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { host = document.createElement('div'); root = createRoot(host); });
afterEach(() => act(() => root.unmount()));
const html = (ui: React.ReactNode) => {
  act(() => root.render(ui));
  return host.innerHTML;
};

const V = { id: 'RT-1048', n: 2, ok: true, big: 1e21 };

describe('JsonView', () => {
  it('tokens: one run of text with keys, strings and numbers marked', () => {
    expect(html(<JsonView variant="tokens" value={V} />)).toBe(
      '<pre class="code">{\n  <span class="k">"id"</span>: <span class="s">"RT-1048"</span>,\n  <span class="k">"n"</span>: <span class="n">2</span>,\n'
      + '  <span class="k">"ok"</span>: true,\n  <span class="k">"big"</span>: <span class="n">1</span>e+21\n}</pre>',
    );
  });
  it('lines: a span per line; only whole strings and numbers are marked', () => {
    expect(html(<JsonView variant="lines" value={V} />)).toBe(
      '<pre class="code"><span>{\n</span><span>  <span class="k">"id"</span>: <span class="s">"RT-1048"</span>,\n</span>'
      + '<span>  <span class="k">"n"</span>: <span class="n">2</span>,\n</span><span>  <span class="k">"ok"</span>: true,\n</span>'
      + '<span>  <span class="k">"big"</span>: 1e+21\n</span><span>}\n</span></pre>',
    );
  });
  it('escaped: a span per line; a value is marked by its first character', () => {
    expect(html(<JsonView variant="escaped" value={V} />)).toContain('<span>  <span class="k">"big"</span>: <span class="n">1e+21</span>\n</span>');
    expect(html(<JsonView variant="escaped" value={{ 'a"b': 1 }} />)).toBe(
      '<pre class="code"><span>{\n</span><span>  <span class="k">"a\\"b"</span>: <span class="n">1</span>\n</span><span>}\n</span></pre>',
    );
  });
});

describe('StatusPill', () => {
  it('is a dot and a label in a tone; a keyed pill falls back to the key in the line tone', () => {
    expect(html(<StatusPill tone="ok" label="Live" />)).toBe('<span class="frst ok"><i></i>Live</span>');
    const T = { live: ['Live', 'ok'] } as const;
    expect(html(<KeyedStatus k="live" t="Syncing" table={T} />)).toBe('<span class="frst ok"><i></i>Syncing</span>');
    expect(html(<KeyedStatus k="odd" table={T} />)).toBe('<span class="frst line"><i></i>odd</span>');
  });
});

describe('Panel', () => {
  it('keeps the title block, the subtitle and the right-hand control', () => {
    expect(html(<Panel title="Checks" sub="3 of 4 pass" right={<a href="#/x">All</a>} id="p1" cls="wide">body</Panel>)).toBe(
      '<section class="panel frp wide" id="p1"><div class="ph"><div><h3>Checks</h3><span class="note">3 of 4 pass</span></div><a href="#/x">All</a></div><div class="pb">body</div></section>',
    );
    expect(html(<Panel title="T">b</Panel>)).toBe('<section class="panel frp "><div class="ph"><div><h3>T</h3></div></div><div class="pb">b</div></section>');
  });
});

describe('VendorLogo', () => {
  it('shows two initials on the vendor hue', () => {
    expect(html(<VendorLogo vendor="Voltara Motors" />)).toBe('<span class="vlogo" style="--h: 302;" aria-hidden="true">VM</span>');
    expect(html(<VendorLogo vendor="SAP S/4HANA" />)).toBe('<span class="vlogo" style="--h: 39;" aria-hidden="true">SS</span>');
  });
});
