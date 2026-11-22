import { describe, expect, it } from 'vitest';
import { errorLog, failedAfter, retriesOf } from './investigation';

const run = { id: 'RUN-D1CFE', trig: 'Event', note: 'Validation & enrichment: 3 retries exhausted (connection reset)', ts: Date.UTC(2026, 10, 20, 9, 0, 30) };

describe('the investigation text', () => {
  it('uses the run\'s retries, then the workflow\'s, then 3', () => {
    expect(retriesOf({ retries: 1 }, { retries: 5 })).toBe(1);
    expect(retriesOf({}, { retries: 5 })).toBe(5);
    expect(retriesOf(undefined, {})).toBe(3);
    expect(retriesOf({ retries: 0 }, {})).toBe(0);
  });
  it('says how many retries failed', () => {
    expect(failedAfter(3)).toBe('failed after 3 retries');
    expect(failedAfter(1)).toBe('failed after 1 retry');
    expect(failedAfter(0)).toBe('failed with no retries');
  });
  it('logs the demo\'s lines for 3 retries', () => {
    expect(errorLog(3, run, 'Validation & enrichment')).toBe([
      '09:00:21 INFO  run RUN-D1CFE started · trigger Event',
      '09:00:24 WARN  Validation & enrichment: attempt 1 failed',
      '09:00:26 WARN  Validation & enrichment: attempt 2 failed',
      '09:00:28 ERROR Validation & enrichment: 3 retries exhausted (connection reset)',
      '09:00:30 INFO  downstream steps marked upstream failed; held records kept',
    ].join('\n'));
  });
  it('logs one warning per attempt before the last', () => {
    const five = errorLog(5, { ...run, note: '' }, 'Map');
    expect(five.split('\n').filter((l) => l.includes('WARN'))).toHaveLength(4);
    expect(five).toContain('ERROR Map failed');
    expect(errorLog(0, run, 'Map').includes('WARN')).toBe(false);
  });
});
