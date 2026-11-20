/** The connection test (5.10): DNS, TLS, auth, permissions, sample read, step by step; one per source, per session. */
import { useSyncExternalStore } from 'react';
import { hashId, type Source } from '../../api/integration';
import { sessionScoped } from '../../api/view';
import { plural } from './fabricFormat';

interface TestState { i: number; res: { ok: boolean; msg: string }[]; done: boolean; ok?: boolean; at: number }
const tests = sessionScoped<Record<string, TestState>>(() => ({}));
const tSubs = new Set<() => void>();
const tEmit = () => { tests.current = { ...tests.current }; tSubs.forEach((f) => f()); };
const useTests = () => useSyncExternalStore((f) => (tSubs.add(f), () => tSubs.delete(f)), () => tests.current);
const FR_TEST: [string, string][] = [['DNS', 'Resolve host'], ['TLS', 'Handshake and certificate'], ['Auth', 'Authenticate'], ['Permissions', 'Check read scopes'], ['Sample read', 'Read a sample record']];
const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export function runTest(s: Pick<Source, 'id' | 'vendor' | 'status' | 'auth' | 'read'> & { url?: string }, done?: (ok: boolean) => void) {
  const h = (k: string) => parseInt(hashId(k), 16);
  const host = (s.url || '').replace(/^[a-z]+:\/\//, '').split('/')[0] || s.vendor, res: TestState['res'] = [];
  const t: TestState = { i: 0, res, done: false, at: Date.now() };
  tests.current[s.id] = t;
  const msg = [
    () => host + ' → 10.' + (h(s.id) % 200) + '.' + (h(s.id + 'b') % 250) + '.' + (h(s.id + 'c') % 250),
    () => 'TLS 1.3 · certificate valid',
    () => (s.status === 'stale' ? 'Token rejected: expired' : s.auth),
    () => plural((s.read || []).length, 'read scope') + ' granted',
    () => '1 record in ' + (120 + (h(s.id + 't') % 300)) + ' ms',
  ];
  const step = () => {
    const i = t.i, fail = (s.status === 'unavailable' && i === 0) || (s.status === 'stale' && i === 2);
    res.push({ ok: !fail, msg: fail && i === 0 ? 'No route to host: the system is not provisioned' : msg[i]() });
    t.i++;
    if (fail || t.i >= FR_TEST.length) {
      t.done = true; t.ok = !fail; t.at = Date.now();
      tEmit();
      done?.(!!t.ok);
      return;
    }
    tEmit();
    window.setTimeout(step, reduced() ? 0 : 260);
  };
  tEmit();
  window.setTimeout(step, reduced() ? 0 : 200);
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
            <li key={x[0]} className={r ? (r.ok ? 'ok' : 'bad') : i === t.i ? 'run' : ''}>
              <span className="frtd">{r ? (r.ok ? '✓' : '✕') : i === t.i ? '…' : ''}</span>
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
