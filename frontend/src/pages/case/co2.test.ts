import { describe, expect, it } from 'vitest';
import { co2Label } from './co2';

const prov = {
  set: 'cfs-2026.2',
  label: 'avoided, not inventory',
  factors: [{ name: 'e_new', value: 62, source: 'Sample value (synthetic)', year: 2026 }],
  transportKg: null,
};

describe('P9-1.12 co2Label', () => {
  it('shows the avoided figure with its label and factor set when the route has provenance', () => {
    const l = co2Label({ co2: 61, co2Prov: prov });
    expect(l.value).toBe('61 kg');
    expect(l.label).toBe('avoided, not inventory');
    expect(l.set).toBe('cfs-2026.2 · how it is computed');
    expect(l.factors).toHaveLength(1);
    expect(l.missing).toBeNull();
  });

  it('shows a dash and the transport kg when the rule gives transport only', () => {
    const l = co2Label({ co2: null, co2Prov: { ...prov, label: 'transport only, not avoided', transportKg: 1.5 } });
    expect(l.value).toBe('—');
    expect(l.label).toBe('transport only, not avoided');
    expect(l.transport).toBe('1.5 kg transport');
    expect(l.missing).toBeNull();
  });

  it('shows a dash and the reason when the route has no factor', () => {
    const l = co2Label({ co2: null, co2Prov: null });
    expect(l.value).toBe('—');
    expect(l.missing).toBe('—: no factor source on file.');
    expect(l.set).toBeNull();
  });

  it('shows nothing extra for an industrial route, which carries no CO2e line', () => {
    const l = co2Label({});
    expect(l.set).toBeNull();
    expect(l.missing).toBeNull();
    expect(l.label).toBeNull();
  });
});
