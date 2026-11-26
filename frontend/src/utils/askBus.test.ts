import { describe, expect, it, vi } from 'vitest';
import { askSoon, onOpenAssistant, openAsk, openAssistant } from './askBus';

describe('openAsk', () => {
  it('is openAssistant in Ask mode, and askSoon ignores a click event', () => {
    const fn = vi.fn();
    const off = onOpenAssistant(fn);
    openAsk('Why?');
    expect(fn).toHaveBeenLastCalledWith(expect.objectContaining({ mode: 'ask', question: 'Why?' }));
    askSoon({ type: 'click' });
    expect(fn).toHaveBeenLastCalledWith(expect.objectContaining({ mode: 'ask', question: undefined }));
    off();
  });
});

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
