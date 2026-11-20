import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/** Every source file under src/ (B17c deleted the in-browser engine; nothing may bring it back). */
function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? sources(p) : /\.(ts|tsx)$/.test(f) ? [p] : [];
  });
}

describe('the app reads only di-api', () => {
  it('imports no engine and no backend switch', () => {
    const offenders = sources(join(__dirname, '..')).filter((p) =>
      /from ['"][./]*(engine\/engine|api\/backend|\.\/backend)['"]|legacy\.gen\.js/.test(readFileSync(p, 'utf8')),
    );
    expect(offenders).toEqual([]);
  });
});
