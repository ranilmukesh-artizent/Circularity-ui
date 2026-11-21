/**
 * The connection test (5.10): DNS, TLS, auth, permissions, sample read; one per source, per session. The server probes
 * the source's connector against the system (source.test); the page then shows the steps one by one, as the demo did.
 */
import { useSyncExternalStore } from 'react';
import { testConnection, type TestInput, type TestStep } from '../../api/integration';
import { sessionScoped } from '../../api/view';

interface TestState { i: number; res: TestStep[]; done: boolean; ok?: boolean; at: number }
const tests = sessionScoped<Record<string, TestState>>(() => ({}));
const tSubs = new Set<() => void>();
const tEmit = () => { tests.current = { ...tests.current }; tSubs.forEach((f) => f()); };
const useTests = () => useSyncExternalStore((f) => (tSubs.add(f), () => tSubs.delete(f)), () => tests.current);
const FR_TEST: [string, string][] = [['DNS', 'Resolve host'], ['TLS', 'Handshake and certificate'], ['Auth', 'Authenticate'], ['Permissions', 'Check read scopes'], ['Sample read', 'Read a sample record']];
const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Run the test of `input.source_id` (a source id, or `cat:<id>` for a catalogue system being connected). */
export function runTest(input: TestInput, done?: (ok: boolean) => void) {
  const id = input.source_id, res: TestStep[] = [];
  const t: TestState = { i: 0, res, done: false, at: Date.now() };
  tests.current[id] = t;
  tEmit();
  const finish = (ok: boolean) => {
    t.done = true; t.ok = ok; t.at = Date.now();
    tEmit();
    done?.(ok);
  };
  const started = Date.now();
  void testConnection(input).then((r) => {
    if (tests.current[id] !== t) return; // a newer test of the same source replaced this one
    const steps = r.ok ? r.output.steps : [{ ok: false, msg: r.error.message }];
    // reveal the probed steps one by one, at the demo's pace (the first after 200 ms, then every 260 ms)
    const step = () => {
      res.push(steps[t.i]);
      t.i++;
      if (!steps[t.i - 1].ok || t.i >= steps.length) return finish(steps[t.i - 1].ok && t.i >= FR_TEST.length);
      tEmit();
      window.setTimeout(step, reduced() ? 0 : 260);
    };
    window.setTimeout(step, reduced() ? 0 : Math.max(0, 200 - (Date.now() - started)));
  });
}

export function TestSteps({ id }: { id: string }) {
  const t = useTests()[id];
  if (!t) return null;
  return (
    <>
      <ol className="frtest">
        {FR_TEST.map((x, i) => {
          const r = t.res[i];
          return (
            <li key={x[0]} className={r ? (r.ok ? 'ok' : 'bad') : i === t.i && !t.done ? 'run' : ''}>
              <span className="frtd">{r ? (r.ok ? '✓' : '✕') : i === t.i && !t.done ? '…' : ''}</span>
              <b>{x[0]}</b>
              <span className="note">{r ? r.msg : x[1]}</span>
            </li>
          );
        })}
      </ol>
      {t.done && (
        <p className="note">
          {t.ok ? 'Connection test passed' : 'Connection test failed'} · {new Date(t.at).toTimeString().slice(0, 8)}
        </p>
      )}
    </>
  );
}
