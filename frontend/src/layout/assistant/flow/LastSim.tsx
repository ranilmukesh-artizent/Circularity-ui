import { useEffect, useState } from 'react';
import { simulateFlow, useLastSim } from '../../../api/modeler';
import type { ModelerScreen } from '../../../api/types';
import { formatImpact } from '../../../pages/modeler/impact';
import { toast } from '../../../components/toast';
import { flowSurface } from './changeStore';
import { Row, Sec } from './Sec';

/** "2 min ago" from the elapsed milliseconds; no number is shown for under a minute. */
export function age(ms: number): string {
  const m = Math.floor(ms / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h} h ago` : `${Math.floor(h / 24)} d ago`;
}

/**
 * "Last simulation" (plan 10, 3.3): the last flow.simulate answer of this flow in this session, from the facade's store
 * (useLastSim), with Run again (a read: the saved draft against the open queue, nothing is written).
 */
export function LastSim({ s }: { s: ModelerScreen }) {
  const last = useLastSim(s.flow.id);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);
  const ver = s.flow.dver ?? null;
  const run = async () => {
    setBusy(true);
    try {
      await flowSurface()?.flush();
      await simulateFlow(s.flow.id, undefined, (last?.sim.params ?? undefined) as never, ver);
      setNow(Date.now());
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const what = ver != null ? `draft v${ver}` : 'the flow';
  const unit = last?.sim.kind === 'device' ? 'lots' : 'decisions';
  const button = (label: string) => <button type="button" className="as-link" disabled={busy} onClick={() => void run()}>{busy ? 'Simulating' : label}</button>;
  return (
    <Sec icon="activity" title="Last simulation" tag="Simulated">
      {busy && <p className="as-status" data-state="working" role="status">Simulating {what} on the open queue · nothing saved…</p>}
      {last ? (
        <>
          <Row icon="activity" go={busy ? undefined : 'Run again'} onGo={() => void run()}>
            {last.draftVer != null ? `Draft v${last.draftVer}` : 'The flow'} on {last.sim.n} open {unit}, {age(now - last.at)}
          </Row>
          <p className="as-sub">{formatImpact(last.sim)}</p>
        </>
      ) : (
        <p className="as-empty">Not simulated yet. {button(`Simulate ${what}`)}</p>
      )}
    </Sec>
  );
}
