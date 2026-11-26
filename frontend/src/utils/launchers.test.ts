import { describe, expect, it } from 'vitest';
import { launch } from './launchers';

describe('launcher questions', () => {
  it('"Explain this number" names the KPI', () => {
    expect(launch.explainKpi('Open returns')).toContain('Open returns');
  });
  it('"Ask how to do this" names the group and how many tasks it holds', () => {
    expect(launch.howToDo('Approvals', 3)).toBe('How do I do these 3 "Approvals" tasks? Walk me through what to open and what to check.');
  });
  it('a task launcher carries the case id when the task has one', () => {
    expect(launch.howToDoTask('RT-1048 needs a decision', 'RT-1048')).toBe('How do I do this: RT-1048 needs a decision (RT-1048)?');
    expect(launch.howToDoTask('Review the weekly report')).toBe('How do I do this: Review the weekly report?');
  });
  it('alert, check, report and workflow launchers name their subject', () => {
    expect(launch.explainAlert('Sync late')).toContain('"Sync late"');
    expect(launch.explainCheck('Serial match')).toContain('"Serial match"');
    expect(launch.summariseReport('Weekly returns')).toContain('"Weekly returns"');
    expect(launch.diagnoseRun('Ingest', 'wf-1', 'Map', 'run-9')).toBe('Why did Ingest (wf-1) fail at Map in run run-9, and how do I fix it?');
  });
});
