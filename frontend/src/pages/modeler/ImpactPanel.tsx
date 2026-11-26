import { useState } from 'react';
import { simulateFlow } from '../../api/modeler';
import type { FlowGraph, ModelerScreen, SimResult } from '../../api/types';
import { RailSection } from './RailSection';
import { toast } from '../../components/toast';
import { formatImpact, poMoney, tradeOff } from './impact';
import { WhatIf } from './WhatIf';

/** Impact on the open queue (flow.simulate), run on demand against the published rules. */
export function ImpactPanel({ s, graph }: { s: ModelerScreen; graph: FlowGraph }) {
  const [sim, setSim] = useState<SimResult | null>(null);
  const [busy, setBusy] = useState(false);
  const name = (k: string | null) => s.template.paths.find((p) => p.id === k)?.name ?? k ?? 'none';
  const run = async () => {
    setBusy(true);
    try {
      setSim(await simulateFlow(s.flow.id, graph));
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const note = sim && tradeOff(sim);
  return (
    <>
    <RailSection title="Impact" icon="trend" sub="This draft against the published flow" cls="mdl-impact">
      <div className="row">
        <button className="btn sm" disabled={busy} onClick={run}>Simulate on open queue</button>
      </div>
      {!sim && <p className="note">Simulate to see which open decisions this draft would change.</p>}
      {sim && (
        <>
          <p className="mdl-impact-line" data-impact>Impact vs published: <b className={sim.dv >= 0 ? 'good' : 'bad'}>{formatImpact(sim)}</b></p>
          {note && <p className="note">{note}</p>}
          <div className="mdl-flips">
            <ul>
              {sim.flips.slice(0, 20).map((f) => (
                <li key={f.case_id}>
                  <b>{f.case_id}</b> {name(f.from)} → {name(f.to)} <span className="note">{f.dv >= 0 ? '+' : ''}{poMoney(f.dv)}</span>
                </li>
              ))}
            </ul>
            {sim.flips.length > 20 && <p className="note">and {sim.flips.length - 20} more</p>}
          </div>
        </>
      )}
    </RailSection>
    {s.template.key === 'tool_fleet' && <WhatIf s={s} graph={graph} />}
    </>
  ); // prettier-ignore
}
