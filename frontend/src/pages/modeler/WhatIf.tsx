import { useState } from 'react';
import { simulateFlow } from '../../api/modeler';
import type { FlowGraph, ModelerScreen, SimResult } from '../../api/types';
import { toast } from '../../components/toast';
import { RailSection } from './RailSection';
import { formatWhatIf, leverError, LEVERS, poMoney, type LeverName, type Levers } from './impact';

const NAMES = Object.keys(LEVERS) as LeverName[];
const NEUTRAL = Object.fromEntries(NAMES.map((k) => [k, LEVERS[k].base])) as Levers;
const show = (k: LeverName, v: number) => (LEVERS[k].pct ? `${Math.round(v * 100)} %` : String(v));

/** "What if" on a tool-fleet flow (flow.simulate `params`, P9-0.15): four levers on the market, labour, lease and repair
 *  slots, run against the published rules. A read: nothing is saved. */
export function WhatIf({ s, graph }: { s: ModelerScreen; graph: FlowGraph }) {
  const [v, setV] = useState<Levers>(NEUTRAL);
  const [sim, setSim] = useState<SimResult | null>(null);
  const [busy, setBusy] = useState(false);
  const name = (k: string | null) => s.template.paths.find((p) => p.id === k)?.name ?? k ?? 'none';
  const run = async () => {
    const bad = NAMES.map((k) => leverError(k, v[k])).find((e) => e);
    if (bad) return toast(bad);
    setBusy(true);
    try {
      setSim(await simulateFlow(s.flow.id, graph, v));
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <RailSection title="What if" icon="activity" sub="Move the levers, then run it against the published rules. Nothing is saved.">
    <div className="mdl-whatif">
      {NAMES.map((k) => {
        const { label, lo, hi, pct } = LEVERS[k];
        return (
          <label key={k} className="mdl-lever">
            {label} <b>{show(k, v[k])}</b>
            <input type="range" min={pct ? lo * 100 : lo} max={pct ? hi * 100 : hi} step={pct ? 5 : 1}
                   value={pct ? Math.round(v[k] * 100) : v[k]}
                   onChange={(e) => setV({ ...v, [k]: pct ? +e.target.value / 100 : +e.target.value })} />
          </label>
        );
      })}
      <button className="btn sm" disabled={busy} onClick={run}>Run what-if</button>
      {sim && (
        <>
          <p data-whatif><b className={sim.dv >= 0 ? 'good' : 'bad'}>{formatWhatIf(sim)}</b></p>
          <ul>
            {sim.flips.slice(0, 20).map((f) => (
              <li key={f.case_id}>
                <b>{f.case_id}</b> {name(f.from)} → {name(f.to)} <span className="note">{f.dv >= 0 ? '+' : ''}{poMoney(f.dv)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
    </RailSection>
  ); // prettier-ignore
}
