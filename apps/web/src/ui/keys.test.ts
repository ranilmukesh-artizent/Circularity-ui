import type { KeyboardEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { onActivateKey } from './keys';

const ev = (key: string, onRow = true) => {
  const row = {};
  return { key, currentTarget: row, target: onRow ? row : {}, preventDefault: vi.fn() } as unknown as KeyboardEvent & { preventDefault: ReturnType<typeof vi.fn> };
};

describe('onActivateKey', () => {
  it('runs on Enter and on Space, like a button, and stops the page from scrolling on Space', () => {
    const fn = vi.fn(), h = onActivateKey(fn);
    const space = ev(' ');
    h(ev('Enter'));
    h(space);
    expect(fn).toHaveBeenCalledTimes(2);
    expect(space.preventDefault).toHaveBeenCalled();
  });

  it('ignores other keys and keys pressed on a control inside the row', () => {
    const fn = vi.fn(), h = onActivateKey(fn);
    h(ev('a'));
    h(ev('Tab'));
    h(ev('Enter', false));
    expect(fn).not.toHaveBeenCalled();
  });
});
