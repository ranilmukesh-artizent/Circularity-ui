import { describe, expect, it, vi } from 'vitest';
import { onOpenAssistant, openAssistant } from './askBus';

describe('openAssistant', () => {
  it('passes the request to listeners until they unsubscribe', () => {
    const fn = vi.fn();
    const off = onOpenAssistant(fn);
    openAssistant({ mode: 'change', question: 'x' });
    expect(fn).toHaveBeenCalledWith(expect.objectContaining({ mode: 'change', question: 'x' }));
    off();
    openAssistant({});
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
