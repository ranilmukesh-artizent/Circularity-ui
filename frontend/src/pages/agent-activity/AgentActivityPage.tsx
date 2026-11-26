import { useEffect, useId, useState } from 'react';
import { useAgentActivity, type ActivityEvent } from '../../api/agentActivity';
import { proposals, rgTime } from '../../api/home';
import { useBackend } from '../../api/useBackend';
import { Modal } from '../../components/Overlay';
import { ProposalRow } from '../../components/ProposalRow';
import { RunView } from '../agents/RunView';
import { countByKind, filterEvents, KIND_CHIP, KIND_LABEL, KINDS, NO_FILTER, type ActivityFilter } from './activityView';

/**
 * Agent activity (UI audit gap 12): what each agent did on the cases of the signed-in person's tenants, read only.
 * Filters by kind, agent, pack and case. A proposal still waiting for this person is the shared `ProposalRow` (the same
 * card as Home and the assistant); everything else is a plain row with the run one click away. The page changes nothing.
 */
export function AgentActivityPage() {
  useBackend();
  const s = useAgentActivity();
  const mine = new Map(proposals().map((p) => [p.id, p]));
  const [f, setF] = useState<ActivityFilter>(NO_FILTER);
  const [run, setRun] = useState<string | null>(null);
  const uid = useId();
  useEffect(() => {
    document.title = 'Agent activity · Circularity Decision Workbench';
  }, []);
  const counts = countByKind(s.events);
  const rows = filterEvents(s.events, f);
  const set = (p: Partial<ActivityFilter>) => setF((x) => ({ ...x, ...p }));
  return (
    <div className="frpage" id="agentactivity">
      <div className="phead">
        <div>
          <h1>Agent activity</h1>
          <p>What the agents did on your cases: held for a person, refused, accepted, rejected and run. Read only.</p>
        </div>
      </div>
      <div className="row" role="group" aria-label="Filter by kind" style={{ marginBottom: 12, gap: 8, flexWrap: 'wrap' }}>
        <button type="button" className={'chip ' + (f.kind === 'all' ? 'ok' : 'line')} aria-pressed={f.kind === 'all'} onClick={() => set({ kind: 'all' })}>
          All {s.events.length}
        </button>
        {KINDS.map((k) => (
          <button key={k} type="button" className={'chip ' + (f.kind === k ? 'ok' : 'line')} aria-pressed={f.kind === k} onClick={() => set({ kind: k })}>
            {KIND_LABEL[k]} {counts[k]}
          </button>
        ))}
      </div>
      <div className="row" style={{ marginBottom: 12, gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
        <label htmlFor={uid + 'a'} className="fld">
          Agent
          <select id={uid + 'a'} className="sel" value={f.agent} onChange={(e) => set({ agent: e.target.value })}>
            <option value="">All agents</option>
            {s.agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        <label htmlFor={uid + 'p'} className="fld">
          Pack
          <select id={uid + 'p'} className="sel" value={f.pack} onChange={(e) => set({ pack: e.target.value })}>
            <option value="">All packs</option>
            {s.packs.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
          </select>
        </label>
        <label htmlFor={uid + 'c'} className="fld">
          Case
          <input id={uid + 'c'} name="case" type="search" autoComplete="off" placeholder="RT-1048…" value={f.caseText} onChange={(e) => set({ caseText: e.target.value })} />
        </label>
      </div>
      {rows.length === 0 ? (
        <p className="note" role="status">{s.events.length ? 'Nothing matches these filters.' : 'No agent has acted on your cases yet.'}</p>
      ) : (
        <ul className="frbl" aria-label="Agent activity">
          {rows.map((e) => (e.kind === 'held' && e.proposal_id !== null && mine.has(e.proposal_id)
            ? <ProposalRow key={e.id} p={mine.get(e.proposal_id)!} id={'aa-' + e.id} />
            : <Row key={e.id} e={e} onRun={setRun} />))}
        </ul>
      )}
      {run && (
        <Modal title="Agent run" wide onClose={() => setRun(null)} foot={<button type="button" className="btn" onClick={() => setRun(null)}>Close</button>}>
          <RunView runId={run} />
        </Modal>
      )}
    </div>
  );
}

function Row({ e, onRun }: { e: ActivityEvent; onRun: (id: string) => void }) {
  return (
    <li className="as-card" aria-label={`${e.agentName}: ${e.title}`}>
      <span className="as-card-b">
        <span className="as-prov">
          {e.agentName} · {rgTime(e.at)}
          {e.case_id && <> · <a href={'#/product/' + e.case_id}>{e.case_id}</a></>}
        </span>
        <b className="as-card-t">{e.title} <span className={'chip ' + KIND_CHIP[e.kind]}>{KIND_LABEL[e.kind]}</span></b>
        {e.detail && <span className="note">{e.detail}</span>}
        {e.run_id && <span className="row"><button type="button" className="btn sm ghost" onClick={() => onRun(e.run_id!)}>View the run</button></span>}
      </span>
    </li>
  );
}
