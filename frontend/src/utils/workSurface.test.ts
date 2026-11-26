import { describe, expect, it, vi } from 'vitest';
import { currentSurface, onSurfaceChange, registerSurface } from './workSurface';

describe('workSurface', () => {
  it('starts empty, holds the registered surface, and clears on null', () => {
    expect(currentSurface()).toBeNull();
    registerSurface({ kind: 'compose', id: 3, org: 'o', pack: 'industrial' });
    expect(currentSurface()).toMatchObject({ kind: 'compose', id: 3 });
    registerSurface(null);
    expect(currentSurface()).toBeNull();
  });
  it('notifies subscribers on change and stops after unsubscribe', () => {
    const fn = vi.fn();
    const off = onSurfaceChange(fn);
    registerSurface({ kind: 'compose', id: null, org: 'o', pack: 'p' });
    expect(fn).toHaveBeenCalledTimes(1);
    off();
    registerSurface(null);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
