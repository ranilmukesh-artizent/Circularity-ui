/** What an import dialog shows for a refused workflow.import (P9-0.7): one row per problem the server found. */
import type { ActionError } from '../../api/types';

export interface ProblemRow {
  /** where in the file, such as `steps[2].cfg.interval`; null when the refusal names no place */
  path: string | null;
  message: string;
}

/** One row per problem; a refusal without `problems` gives one row with its message. */
export function problemRows(error: ActionError): ProblemRow[] {
  return error.problems?.length ? error.problems.map((p) => ({ path: p.path, message: p.message })) : [{ path: null, message: error.message }];
}

/** The rows as text lines: `path: message`. */
export function problemLines(error: ActionError): string[] {
  return problemRows(error).map((r) => (r.path ? r.path + ': ' + r.message : r.message));
}
