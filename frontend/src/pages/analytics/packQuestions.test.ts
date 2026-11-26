// P9-6.17 (DV-13): the helpers of the device pack's worked questions.
import { describe, expect, it } from 'vitest';
import { answerTitle, plot, topShare } from './packQuestions';

describe('P9-6.17 packQuestions', () => {
  it('answerTitle gives the question text', () => {
    expect(answerTitle({ question_id: 'price_after_launch', question: 'Why did price realised drop?' })).toBe('Why did price realised drop?');
    expect(answerTitle({ question_id: 'wq_uc_1', question: '' })).toBe('wq_uc_1');
  });
  it('topShare of the dispute series is 58%', () => {
    const series = [['P02', 15], ['P04', 14], ['P01', 8], ['P03', 7], ['P05', 6]].map(([x, y]) => ({ x: String(x), y: Number(y) }));
    expect(topShare(series)).toBe('58%');
    expect(topShare([])).toBe('0%');
  });
  it('plot skips weeks without a value', () => {
    const p = plot([{ x: 'a', y: 90 }, { x: 'b', y: null }, { x: 'c', y: 100 }], 90, 100);
    expect(p.map((q) => [q.x, q.y])).toEqual([[0, 0], [1, 1]]);
  });
});
