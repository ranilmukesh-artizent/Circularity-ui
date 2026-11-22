import { describe, expect, it } from 'vitest';
import { ICON, LOGO, LOGO_INK, LOGO_KEY, SYSLOGO } from './assets.gen';

describe('static assets (scripts/dump-assets.mjs)', () => {
  it('has the logos and the icon set', () => {
    expect(LOGO.length).toBeGreaterThan(100);
    expect(LOGO_INK.length).toBeGreaterThan(100);
    expect(ICON.spark).toContain('<');
    expect(Object.keys(ICON).length).toBeGreaterThan(50);
  });

  it('has a vendor logo for every rule, and the rules are regular expressions', () => {
    for (const [re, key] of LOGO_KEY) {
      expect(re).toBeInstanceOf(RegExp);
      expect(SYSLOGO[key], key).toBeTruthy();
    }
    expect(LOGO_KEY.find(([re]) => re.test('SAP S/4HANA'))?.[1]).toBeTruthy();
  });
});
