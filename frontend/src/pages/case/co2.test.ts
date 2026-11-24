import { describe, expect, it } from 'vitest';
import { co2Label } from './co2';

describe('P9-0.6 co2Label', () => {
  it('gives the factor source when the route has one', () => {
    const l = co2Label({ co2: 275, co2Src: 'cfs-2026.1 · Sample value (synthetic), 2026' });
    expect(l.value).toBe('275 kg');
    expect(l.source).toBe('cfs-2026.1 · Sample value (synthetic), 2026');
  });

  it('gives no source for a route without one (industrial)', () => {
    expect(co2Label({}).source).toBeNull();
    expect(co2Label({ co2Src: '' }).source).toBeNull();
  });
});
