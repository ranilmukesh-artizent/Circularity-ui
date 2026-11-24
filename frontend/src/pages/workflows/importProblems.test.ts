import { describe, expect, it } from 'vitest';
import { problemLines } from './importProblems';

describe('problemLines (P9-0.7)', () => {
  it('gives one line per problem, path first', () => {
    const lines = problemLines({
      code: 'validation_error',
      message: '2 problems in this file. The first: x',
      problems: [{ path: 'steps[0].kind', message: 'bad kind' }, { path: 'links[0].to', message: 'no such step' }],
    });
    expect(lines).toEqual(['steps[0].kind: bad kind', 'links[0].to: no such step']);
  });

  it('gives the message when the refusal has no problems', () => {
    expect(problemLines({ code: 'out_of_scope', message: 'Not allowed.' })).toEqual(['Not allowed.']);
  });
});
