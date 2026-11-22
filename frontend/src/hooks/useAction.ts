/**
 * Actions from pages (refactor step E6, W-02b): one place that shows a refused action, and a hook with a pending flag.
 *
 *   const act = useAction();
 *   const r = await act.run(() => invoke('decision.submit', { case_id }), { ms: 4200 });
 *   if (!r.ok) return;          // the refusal has been shown already
 *   <button disabled={act.pending}>…
 *
 * A refusal shows di-api's own message (the demo's texts: the server sends them) as a toast, for `ms` (the demo
 * used 3200 and 4200). `inline` takes validation errors that a form shows next to its fields instead of a toast;
 * `silent` lists error codes the caller handles itself (e.g. "duplicate" when a retry is fine).
 * Code outside components (caseActions, workflowActions) calls `refused(r, opts)` directly.
 */
import { useCallback, useRef, useState } from 'react';
import type { ActionError, ActionResult } from '../api/types';
import { toast } from '../components/toast';

export interface RefusalOptions {
  /** how long the toast stays (ms); the toast's default when left out */
  ms?: number;
  /** show a validation error here (a form's error line) instead of a toast */
  inline?: (message: string) => void;
  /** show every refusal here instead of a toast */
  all?: (message: string, code: ActionError['code']) => void;
  /** codes the caller handles itself: no toast */
  silent?: ActionError['code'][];
}

/** Show a refused action (if it was refused); true when it was. */
export function refused<R extends ActionResult<unknown>>(r: R, opts: RefusalOptions | number = {}): r is Extract<R, { ok: false }> {
  if (r.ok) return false;
  const o = typeof opts === 'number' ? { ms: opts } : opts;
  const { code, message } = r.error;
  if (o.silent?.includes(code)) return true;
  if (o.all) o.all(message, code);
  else if (o.inline && code === 'validation_error') o.inline(message);
  else toast(message, o.ms);
  return true;
}

export interface Action {
  /** true while a run() of this hook waits for di-api */
  pending: boolean;
  /** Invoke the action, show a refusal, and return the result. */
  run<R extends ActionResult<unknown>>(call: () => Promise<R>, opts?: RefusalOptions | number): Promise<R>;
}

export function useAction(): Action {
  const [pending, setPending] = useState(false);
  const live = useRef(0); // runs in flight (a page may start a second before the first returns)
  const run = useCallback(async <R extends ActionResult<unknown>>(call: () => Promise<R>, opts: RefusalOptions | number = {}): Promise<R> => {
    live.current += 1;
    setPending(true);
    try {
      const r = await call();
      refused(r, opts);
      return r;
    } finally {
      live.current -= 1;
      if (live.current === 0) setPending(false);
    }
  }, []);
  return { pending, run };
}
