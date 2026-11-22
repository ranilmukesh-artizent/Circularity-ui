// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { downloadCsv, q } from './csv';

describe('q: one CSV cell', () => {
  it('always quotes, so commas and line breaks stay inside the cell', () => {
    expect(q('plain')).toBe('"plain"');
    expect(q('a,b')).toBe('"a,b"');
    expect(q('line 1\nline 2')).toBe('"line 1\nline 2"');
    expect(q('cr\r\nlf')).toBe('"cr\r\nlf"');
  });
  it('doubles inner quotes', () => {
    expect(q('say "hi"')).toBe('"say ""hi"""');
    expect(q('"')).toBe('""""');
  });
  it('prints non-strings as text', () => {
    expect(q(42)).toBe('"42"');
    expect(q(null)).toBe('"null"');
    expect(q(undefined)).toBe('"undefined"');
    expect(q(true)).toBe('"true"');
  });
  it('builds rows a CSV reader splits back into the same cells', () => {
    const cells = ['RT-1048', 'Quote "A", rev 2', 'two\nlines'];
    const row = cells.map(q).join(',');
    expect(row).toBe('"RT-1048","Quote ""A"", rev 2","two\nlines"');
    // a minimal RFC 4180 reader for one row
    const back: string[] = [];
    let cur = '', inQ = false;
    for (let i = 0; i < row.length; i++) {
      const c = row[i];
      if (inQ) {
        if (c === '"' && row[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') inQ = false; else cur += c;
      } else if (c === '"') inQ = true;
      else if (c === ',') { back.push(cur); cur = ''; } else cur += c;
    }
    back.push(cur);
    expect(back).toEqual(cells);
  });
});

const readText = (b: Blob) => new Promise<string>((ok) => { const r = new FileReader(); r.onload = () => ok(String(r.result)); r.readAsText(b); });

describe('downloadCsv', () => {
  const orig = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  afterEach(() => {
    Object.assign(URL, { createObjectURL: orig.create, revokeObjectURL: orig.revoke });
    vi.useRealTimers();
    vi.restoreAllMocks();
  });
  it('downloads the text as a text/csv file with the given name, then releases the URL', async () => {
    vi.useFakeTimers();
    const seen: { blob?: Blob; a?: HTMLAnchorElement; inPage?: boolean } = {};
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: (b: Blob) => { seen.blob = b; return 'blob:csv-1'; }, revokeObjectURL: revoke });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      seen.a = this;
      seen.inPage = document.body.contains(this); // in the page while clicked (Firefox needs that)
    });

    downloadCsv('field,value\nid,"RT-1048"', 'audit-log.csv');

    expect(seen.a?.download).toBe('audit-log.csv');
    expect(seen.a?.getAttribute('href')).toBe('blob:csv-1');
    expect(seen.inPage).toBe(true);
    expect(document.body.contains(seen.a!)).toBe(false); // removed afterwards
    expect(revoke).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(revoke).toHaveBeenCalledWith('blob:csv-1');
    vi.useRealTimers();
    expect(seen.blob?.type).toBe('text/csv');
    expect(await readText(seen.blob!)).toBe('field,value\nid,"RT-1048"');
  });
});
