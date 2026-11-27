// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { needsSessionRead } from './session';

/** A route refused for its tenant is checked against a freshly read session once (a tenant made since sign-in is not in it). */
describe('needsSessionRead', () => {
  it('reads the session again on the first refusal of a route', () => expect(needsSessionRead('tenant', null, 'product/RT-1148/overview')).toBe(true));
  it('reads it again for another route than the one last read for', () =>
    expect(needsSessionRead('tenant', 'product/RT-1/overview', 'product/RT-2/overview')).toBe(true));
  it('lets the second refusal of the same route stand', () =>
    expect(needsSessionRead('tenant', 'product/RT-1148/overview', 'product/RT-1148/overview')).toBe(false));
  it('does nothing for a route that is allowed or refused for another reason', () => {
    expect(needsSessionRead(true, null, 'home/')).toBe(false);
    expect(needsSessionRead(false, null, 'agents/')).toBe(false);
  });
});
