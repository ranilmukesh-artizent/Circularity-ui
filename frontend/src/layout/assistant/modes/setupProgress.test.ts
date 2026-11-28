import { describe, expect, it } from 'vitest';
import { draftSource, isSamplePrompt, plainFailure, progressStatus, sourceLine, templateHref } from './setupProgress';

describe('progressStatus', () => {
  it('reads, matches, drafts, then says it is slow', () => {
    expect(progressStatus(0, 12, 'Customer A')).toMatchObject({ verb: 'Reading', item: '12 words for Customer A', state: 'working' });
    expect(progressStatus(2_500, 12, 'Customer A')).toMatchObject({ verb: 'Matching', item: 'it against the template' });
    expect(progressStatus(9_000, 12, 'Customer A')).toMatchObject({ verb: 'Drafting', item: 'the changes' });
    const slow = progressStatus(26_000, 12, 'Customer A');
    expect(slow.verb).toBe('Still drafting');
    expect(slow.limit).toContain('up to a minute');
  });
  it('says one word, not 1 words', () => {
    expect(progressStatus(0, 1, 'X').item).toBe('1 word for X');
  });
});

describe('draftSource and sourceLine', () => {
  it('trusts the server value and falls back to the reading flag', () => {
    expect(draftSource('stored', true)).toBe('stored');
    expect(draftSource(undefined, true)).toBe('model');
    expect(draftSource(undefined, false)).toBe('rules');
    expect(draftSource('x', false)).toBe('rules');
  });
  it('names a stored draft where a live one names the model', () => {
    expect(sourceLine('stored')).toBe('Used the stored draft for this sample');
    expect(sourceLine('model')).toContain('language model');
    expect(sourceLine('rules')).toBe('Read by the rules');
  });
});

describe('plainFailure and templateHref', () => {
  it('hides status codes and provider text behind one sentence', () => {
    const r = plainFailure('Error code: 429 - rate limit reached for model');
    expect(r).toMatch(/^No language model answered/);
    expect(r).not.toMatch(/429|rate limit/i);
    expect(plainFailure('x', 'network')).toMatch(/Could not reach/);
    expect(plainFailure('The description is 5,000 characters')).toBe('The description is 5,000 characters');
  });
  it('links back to the page start with the template and organisation', () => {
    expect(templateHref('tool_fleet', 'Customer A')).toBe('#/setup?new=1&pack=tool_fleet&org=Customer%20A');
  });
});

describe('isSamplePrompt', () => {
  const list = ['We lease cordless tools.', 'Repairs over $600 go to the vendor.'];
  it('matches after trimming, collapsing spaces and ignoring case', () => {
    expect(isSamplePrompt('  we lease   CORDLESS tools. ', list)).toBe(true);
  });
  it('does not match other text, an extension of a sample or nothing', () => {
    expect(isSamplePrompt('We lease cordless tools. Also resell.', list)).toBe(false);
    expect(isSamplePrompt('   ', list)).toBe(false);
    expect(isSamplePrompt('x', [])).toBe(false);
  });
});
