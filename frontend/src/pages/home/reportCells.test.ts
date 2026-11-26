import { describe, expect, it } from 'vitest';
import { reportCell } from './reportCells';

describe('reportCell', () => {
  it('reads a stage id as the words the case pages use', () => {
    expect(reportCell('Stage', 'reeval').text).toBe('Re-evaluate');
    expect(reportCell('Stage', 'awaiting_approval').text).toBe('Awaiting approval');
  });
  it('leaves other columns with the same text alone', () => {
    expect(reportCell('Note', 'reeval').text).toBe('reeval');
  });
  it('shows an em dash for an empty cell', () => {
    expect(reportCell('Approval ref', '').empty).toBe(true);
    expect(reportCell('Approval ref', null).text).toBe('—');
    expect(reportCell('Qty', 0).text).toBe('0');
  });
  it('marks ids that must not wrap', () => {
    expect(reportCell('Case', 'RT-1002').id).toBe(true);
    expect(reportCell('Approval ref', 'CS-2994').id).toBe(true);
    expect(reportCell('Product', 'Industrial motor').id).toBe(false);
  });
});
