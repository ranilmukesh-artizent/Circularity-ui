import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { CaseScreen } from '../../api/case';
import { NotConnected } from './CaseBlocks';

const html = (notes?: string[]) => renderToStaticMarkup(createElement(NotConnected, { notes }));

describe('P9-9.13 systems not connected (UC-04)', () => {
  it('types the screen field as a list of notes', () => {
    const notes: CaseScreen['notConnected'] = ['Older damage history not connected'];
    expect(notes).toHaveLength(1);
  });

  it('shows one muted line for a screen with one note', () => {
    const out = html(['Older damage history not connected']);
    expect(out.match(/<p /g)).toHaveLength(1);
    expect(out).toContain('Older damage history not connected');
    expect(out).toContain('class="note"');
  });

  it('shows one line per note, in order', () => {
    const out = html(['Older damage history not connected', 'Service history not connected']);
    expect(out.match(/<p /g)).toHaveLength(2);
    expect(out.indexOf('Older')).toBeLessThan(out.indexOf('Service'));
  });

  it('writes nothing when every system is connected, or for a screen without the field', () => {
    expect(html([])).toBe('');
    expect(html(undefined)).toBe('');
  });
});
