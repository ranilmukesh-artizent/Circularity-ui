import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/** A UTF-8 character read as Windows-1252 shows up as a lead like "Â", "â" or "Ã" followed by a symbol. */
const MOJIBAKE = /[ÂÃâ][\u0080-¿ŒœŠšŸŽžƒˆ˜–—‘-„†-•…‰‹›€™]/;

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === 'node_modules' ? [] : sources(p);
    return /\.(tsx?|css)$/.test(f) && !/\.gen\./.test(f) && f !== 'noMojibake.test.ts' ? [p] : [];
  });
}

describe('frontend sources are UTF-8, not Windows-1252 read as UTF-8 (the Modeler Inspector showed "Â·" and "â†’")', () => {
  it('has no mojibake in any source file', () => {
    const bad = sources(join(__dirname, '..'))
      .map((p) => [p, readFileSync(p, 'utf-8').split(/\r?\n/).findIndex((l) => MOJIBAKE.test(l)) + 1] as const)
      .filter(([, line]) => line > 0)
      .map(([p, line]) => `${p}:${line}`);
    expect(bad).toEqual([]);
  });
});
