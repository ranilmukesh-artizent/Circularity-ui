import { describe, expect, it } from 'vitest';
import { isOpen, prefill, registerPinned, setComposeId, takeDraft, uiState } from './store';

describe('prefill (plan 10 T8: Rephrase puts the sentence back in the composer, unsent)', () => {
  it('opens the dock, picks the mode, and the composer takes the text once', () => {
    prefill('Never send grade D motors to resale', 'change');
    expect(isOpen()).toBe(true);
    expect(uiState().picked).toBe('change');
    expect(takeDraft()).toBe('Never send grade D motors to resale');
    expect(takeDraft()).toBeNull();
  });

  it('focuses the pinned composer when the Modeler pins the panel', () => {
    let focused = 0;
    const off = registerPinned(() => focused++);
    prefill('Only redeploy grade A');
    expect(focused).toBe(1);
    expect(takeDraft()).toBe('Only redeploy grade A');
    off();
  });
});

describe('setComposeId (openAssistant({ composeId }))', () => {
  it('keeps the composition for Set up and forgets it with null', () => {
    setComposeId(12);
    expect(uiState().composeId).toBe(12);
    setComposeId(null);
    expect(uiState().composeId).toBeNull();
  });
});
