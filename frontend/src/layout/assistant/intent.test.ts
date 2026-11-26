import { describe, expect, it } from 'vitest';
import { modeHint } from './intent';

describe('modeHint', () => {
  it('Change flow: a question gets the Ask hint', () => {
    expect(modeHint('change', 'What does GR-I2 do')?.to).toBe('ask');
    expect(modeHint('change', 'Block grade D?')?.to).toBe('ask');
  });
  it('Change flow: a change gets no hint', () => expect(modeHint('change', 'Never send grade D motors to resale')).toBeNull());
  it('Ask on the Modeler: a rule-like sentence gets the change hint', () => {
    expect(modeHint('ask', 'Never send grade D motors to resale')?.to).toBe('change');
    expect(modeHint('ask', 'Route grade D to recycling')?.to).toBe('change');
  });
  it('Ask: a question is never hinted, even if it starts with a change word', () => {
    expect(modeHint('ask', 'Send which cases to resale?')).toBeNull();
    expect(modeHint('ask', 'Why is RT-1048 redeploy?')).toBeNull();
  });
  it('empty text gets no hint', () => expect(modeHint('change', '  ')).toBeNull());
});
