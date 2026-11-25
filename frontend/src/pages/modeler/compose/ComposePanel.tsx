import { Suspense, useState } from 'react';
import { useComposition, type Composition, type CompositionStep } from '../../../api/compose';
import { Segmented } from '../../../components/kit/Segmented';
import { DescribeStep } from './DescribeStep';
import { MappingStep } from './MappingStep';
import { STEP_ITEMS, stateLine } from './composeView';
import './compose.css';

/**
 * Compose (plan 9, P9-8.18, story X-10): the five steps of one composition as tabs. This task builds Describe and Adapter mapping;
 * the other tabs show their state (and the reason, when the approver sent a step back). `id` is null before the first draft.
 * Nothing here approves, publishes or deletes: those are a different person's actions.
 */
export function ComposePanel({ org, pack, id, onId, onClose }: {
  org: string;
  pack: string;
  id: number | null;
  onId: (id: number) => void;
  onClose: () => void;
}) {
  return (
    <section className="panel frp cmp" aria-label="Compose">
      <div className="ph">
        <div>
          <h3>Compose</h3>
          <span className="note">Describe the business, connect its systems, set the agents, then a different person approves it.</span>
        </div>
        <button className="btn sm" onClick={onClose}>Close</button>
      </div>
      <Suspense fallback={<p className="note">Loading…</p>}>
        {id == null ? <Body org={org} pack={pack} c={null} onId={onId} /> : <Loaded org={org} pack={pack} id={id} onId={onId} />}
      </Suspense>
    </section>
  );
}

function Loaded({ org, pack, id, onId }: { org: string; pack: string; id: number; onId: (id: number) => void }) {
  return <Body org={org} pack={pack} c={useComposition(id)} onId={onId} />;
}

function Body({ org, pack, c, onId }: { org: string; pack: string; c: Composition | null; onId: (id: number) => void }) {
  const [step, setStep] = useState<CompositionStep>('describe');
  const shown = c ? step : 'describe'; // the later steps need a composition
  return (
    <>
      <Segmented name="compose-step" label="Compose steps" items={c ? STEP_ITEMS : STEP_ITEMS.slice(0, 1)} cur={shown} onPick={setStep} />
      {c && (
        <p className="note cmp-state">
          {STEP_ITEMS.find(([k]) => k === shown)?.[1]}: {stateLine(c.steps[shown])} · composition {c.id} is {c.status.replace('_', ' ')}
        </p>
      )}
      {c?.steps[shown]?.note?.node_id && <p className="note">About: {c.steps[shown].note?.node_id}</p>}
      {shown === 'describe' && <DescribeStep org={org} pack={pack} composition={c} onStarted={onId} />}
      {shown === 'mapping' && c && <MappingStep c={c} />}
      {(shown === 'agents' || shown === 'approve' || shown === 'publish') && <p className="note cmp-step">This step is not available yet.</p>}
    </>
  );
}
