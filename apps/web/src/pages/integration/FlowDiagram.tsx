/* How data flows (the demo's flowDiagram): sources → integration layer → platform → enterprise systems, with the return loop. */
import type { ReactNode } from 'react';
import { journeyStep, openConflictCount, sources, srcCats, srcChannels } from '../../api/integration';
import { Icon } from '../../ui/Icon';
import { plural } from './fabricFormat';

/** A journey step chip (the demo's stp). */
function Stp({ n }: { n: number }) {
  const j = journeyStep(n);
  return (
    <span className={'stp ' + (j.kind === 'built' ? '' : j.kind)} title={'Journey step ' + j.n + ': ' + j.label + ' — ' + j.desc}>
      <b>{j.n}</b>
      {j.label}
    </span>
  );
}

export function FlowDiagram() {
  const S = sources(), C = srcCats();
  const dot = (st: string) => ({ live: 'ok', stale: 'warn', manual: '', unavailable: 'bad' })[st] ?? '';
  const grp = (c: string, t: string) => (
    <div className="zg">
      <h5>{C[c]}<span className="note">{t}</span></h5>
      {S.filter((x) => x.cat === c).map((x) => (
        <div className="fnode" key={x.id}><span className={'dotc ' + dot(x.status)} />{x.name}<span className="note" style={{ marginLeft: 'auto' }}>{x.vendor}</span></div>
      ))}
    </div>
  );
  const n = (ch: string) => S.filter((x) => srcChannels(x).includes(ch)).length;
  const box = (t: string, d: string, x?: ReactNode) => (
    <div className="zbox"><b>{t}</b><span className="note">{d}</span>{x && <div className="row">{x}</div>}</div>
  );
  const arr = (l: string) => <div className="zarr"><Icon name="arrow" /><span>{l}</span></div>;
  const out = S.filter((x) => x.write.length), open = openConflictCount();
  return (
    <>
      <div className="zf">
        <section className="zone" aria-label="Enterprise data sources">
          <header>Enterprise data sources</header>
          <div className="zb">{grp('internal', 'Batch, API and file feeds')}{grp('streaming', 'Device and operational events')}{grp('external', 'Partner and market data')}</div>
        </section>
        {arr('Batch files, events and API calls')}
        <section className="zone" aria-label="Integration layer">
          <header>Integration layer</header>
          <div className="zb">
            {box('API gateway', 'REST and SOAP · ' + n('api') + ' sources')}
            {box('Event ingestion', 'Webhooks and queues · ' + n('event') + ' sources')}
            {box('File ingestion', 'SFTP and CSV · ' + plural(n('file'), 'source'))}
            {box('Connectors', S.length + ' adapters, one per system')}
            {box('Validation & enrichment', 'Schema, completeness and reference data. Failed rows are rejected with a reason.')}
          </div>
        </section>
        {arr('Validated data and events')}
        <section className="zone plat" aria-label="Circularity platform">
          <header>Circularity platform</header>
          <div className="zb">
            {box('Context assembly', 'Seven versioned canonical models, identity resolved inside each tenant, and a conflict queue (' + open + ' open).', <Stp n={2} />)}
            {box('Decision services', 'Evaluate routes against demand, predict outcomes with ranges, apply the six eligibility gates, recommend, and stop at human approval.', <><Stp n={3} /><Stp n={4} /><Stp n={5} /></>)}
            {box('Action orchestration', 'Outbound API · Event trigger · File generation · Process orchestration. Every message carries the decision ID and approval reference.', <><Stp n={6} /><Stp n={7} /><Stp n={8} /></>)}
          </div>
        </section>
        {arr('Approved instruction')}
        <section className="zone" aria-label="Enterprise systems">
          <header>Enterprise systems (carry out the work)</header>
          <div className="zb">
            {out.map((x) => (
              <div className="fnode" key={x.id}><span className={'dotc ' + (x.status === 'live' ? 'ok' : 'warn')} />{x.name}<span className="note" style={{ marginLeft: 'auto' }}>{plural(x.write.length, 'write op')}</span></div>
            ))}
            <div className="note" style={{ marginTop: 6 }}>The owning system stays authoritative for physical movements and status.</div>
          </div>
        </section>
      </div>
      <div className="zloop">
        <span className="lab">Return loop</span>
        {box('Model and policy update', 'Calibration from outcomes becomes a new model version for Context assembly and Decision services.', <Stp n={10} />)}
        <span className="zarrl"><Icon name="arrow" /></span>
        {box('Feedback events', 'Outcome capture: actual receipts, costs and avoided spend, linked to the decision.', <Stp n={9} />)}
        <span className="zarrl"><Icon name="arrow" /></span>
        {box('Handoff status', 'Acknowledgement or error from the owning system, with retries and duplicates handled.', <Stp n={9} />)}
      </div>
    </>
  );
}
