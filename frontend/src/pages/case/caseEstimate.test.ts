import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { Fact } from '../../api/case';
import { StProv } from './CaseBlocks';

const grade: Fact = { l: 'Grade', v: 'Grade C', k: 'ret', sys: 'Inspection', estimate: true };

const html = (f: Fact) => renderToStaticMarkup(createElement(StProv, { k: f.k, sys: f.sys, src: {}, estimate: f.estimate }));

describe('P9-9.7 estimate badge (UC-09)', () => {
  it('shows the text "estimate" on a fact with estimate: true', () => {
    expect(html(grade)).toContain('>estimate<');
  });

  it('shows no estimate badge on a read fact', () => {
    expect(html({ ...grade, estimate: false })).not.toContain('estimate');
    expect(html({ l: 'Grade', v: 'Grade B', k: 'ret', sys: 'Inspection' })).not.toContain('estimate');
  });
});
