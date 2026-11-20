/**
 * Full analysis (stFull): the Treatment Intelligence page (caseView) with every section open, for review and print.
 */
import { Suspense, type MouseEvent } from 'react';
import {
  caseAnalysis, caseScreen, exTs, fmtD, refList, stageHref, tiView,
  type CaseAnalysis, type CaseRec, type CaseScreen,
} from '../../api/case';
import { asHex } from './tabs/EarlyTabs';
import { can, canPage } from '../../api/session';
import { Icon } from '../../ui/Icon';
import { toast } from '../../ui/toast';
import { openSnapshot } from './CaseDrawers';
import { Panel, Photo, StageChip } from './kit';
import {
  compareBody, EvidenceBlock, ExplainBlock, OptionsBlock, PredictBlock, saveScenario, SpecialBlock, TiA, TiOutcome, TiP4, useRows,
} from './tabs/DecideTabs';
import { BestCard, ExecBlock, TiHandoff, TiReconcile } from './tabs/ExecuteTabs';
import { scrollToId, useCaseUi } from './ui';

const TI_STEPS = ['Asset and status', 'Possible outcomes', 'Why this outcome', 'What-if and edge cases', 'Approval and handoff'];
const StepH = ({ n, t, sub }: { n: number; t: string; sub?: string }) => (
  <header className="tish"><span className="tin">{n}</span><div><h2>{t}</h2>{sub && <p className="note">{sub}</p>}</div></header>
);
const addDays = (d: Date | string, n: number) => new Date(new Date(d).getTime() + n * 864e5);
const hex = (c: CaseRec, k: string) => asHex(c, k);
const asLease = (c: CaseRec) => 'LS-' + (4900 + (hex(c, 'cl') % 300));

/** Step 1: why the case is in its status, and what is still outstanding (tiStatus). */
function TiStatus({ c, a, s }: { c: CaseRec; a: CaseAnalysis; s: CaseScreen }) {
  const st = c.stage, x = c.exec, act = x && x.steps.find((y) => y.state === 'active'), dl = s.approval.role;
  const AS_OF = refList<string>('AS_OF');
  const why = st === 'awaiting_approval' ? `Awaiting approval since ${fmtD(c.submitted ? c.submitted.at : addDays(AS_OF, -((hex(c, 'aw') % 6) + 1)))} · ${c.submitted ? 'submitted by ' + c.submitted.by : 'recommended by Circularity'} · ${c.owner}`
    : st === 'approved' ? `Approved by ${c.approval ? c.approval.by : 'Approver'}${c.approval ? ' on ' + fmtD(c.approval.at) : ''} · instruction going to ${act ? act.sys : x ? x.steps[0].sys : 'the enterprise system'}`
    : st === 'executing' ? `Handed off to ${act ? act.sys : 'enterprise systems'} · awaiting outcome`
    : st === 'reeval' ? `Re-evaluate: ${c.reevalReason || 'a review was triggered'}` : st === 'closed' ? (c.outcome ? 'Outcome confirmed by Finance' : 'Outcome reported; waiting for Finance to confirm')
    : c.blocked ? `${c.blocked.gateName} gate: ${c.blocked.reason}` : 'Waiting for evidence before a pathway can be recommended';
  const out: [string, string][] = [];
  c.evidence.filter((e) => e.state !== 'ready').forEach((e) => out.push([e.label + ' (' + e.state + ')', e.source]));
  if (c.assessment === 'Pending') out.push(['Inspection or test report', 'Engineering']);
  if (st === 'awaiting_approval') out.push(['Approval', `waits on ${dl}${c.submitted ? '' : ' (not yet submitted by the Planner)'}`]);
  if (act) {
    const v = a.view.steps.find((y) => y.label === act.label && y.sys === act.sys), k = s.clock;
    out.push(['Acknowledgement', `from ${v ? v.app : act.sys} · ${v ? v.owner : 'Enterprise system'} · ${k ? (k.level ? 'escalated to ' + k.to : k.due ? 'due ' + exTs(k.due) : 'on the event') : 'on the event'}`]);
  }
  if (st === 'closed' && !c.outcome) out.push(['Outcome confirmation', 'Finance']);
  return (
    <>
      <h3>Current status</h3>
      <div style={{ margin: '4px 0 6px' }}><StageChip c={c} /></div>
      <p className="ink2 tistw" style={{ margin: '0 0 10px' }}>{why}</p>
      <h4 style={{ margin: '0 0 4px' }}>Outstanding <span className="note">{out.length}</span></h4>
      {out.length ? <ul className="tiout">{out.map((o, i) => <li key={i}><b>{o[0]}</b><span className="note">{o[1]}</span></li>)}</ul> : <p className="note" style={{ margin: 0 }}>Nothing outstanding.</p>}
    </>
  );
}
/** Step 1: the returned asset (tiCtx). */
function TiCtx({ c, a, s }: { c: CaseRec; a: CaseAnalysis; s: CaseScreen }) {
  const pick = ['Asset ID', 'Serial number', 'Product', 'Revision', 'Ownership', 'Location', 'Received', 'Age'];
  const facts = a.view.facts.filter((x) => pick.includes(x[0])), h = a.view.health;
  const label = refList<Record<string, { label: string }>>('CLASSES')[c.cls]?.label ?? c.cls;
  return (
    <section className="aship ticx">
      <div className="asphoto"><Photo c={c} /></div>
      <div className="asmain">
        <div className="asttl"><h2>{a.view.title}</h2><span className="chip line">{label}</span><StageChip c={c} /></div>
        <dl className="asfacts">
          {facts.map((x) => <div key={x[0]}><dt>{x[0]}</dt><dd>{x[1]}</dd></div>)}
          <div><dt>Condition</dt><dd>{c.grade ? 'Grade ' + c.grade + ' (' + h.score + '/100)' : c.condition}</dd></div>
          <div><dt>Next inspection</dt><dd>{c.nextInspection}</dd></div>
        </dl>
        <a className="btn sm" style={{ marginTop: 10 }} href={'#/product/asset/' + c.id}>View in Asset Intelligence →</a>
      </div>
      <div className="ashealth tist"><TiStatus c={c} a={a} s={s} /></div>
    </section>
  );
}
/** Step 5: handoff readiness (tiP5). */
function TiP5({ c, a, s }: { c: CaseRec; a: CaseAnalysis; s: CaseScreen }) {
  const r = c.chosen || c.recommendation, cap = refList<Record<string, number>>('CC_CAP')['Repair centre'] || 45, rc = a.view.repair_load / cap;
  const parts = a.view.parts, inS = parts.filter((p) => p.st === 'In stock').length;
  const eam = s.sources.eam || { status: 'unavailable', name: 'EAM', vendor: '' }, erp = s.sources.erp || { status: 'unavailable', name: 'ERP', vendor: '' };
  const lith = ['drill', 'batch', 'it'].includes(c.cls), d = c.demand || {};
  const items: [string, string, string, string][] = !r ? [['Evidence for a recommendation', 'Waiting on ' + (c.blocked ? c.blocked.owner : 'inspection'), 'Pending', 'warn']] : [
    ['Repair facility available', 'Repair centre · ' + Math.round(rc * 100) + '% loaded', rc >= 0.9 ? 'Constrained' : 'Confirmed', rc >= 0.9 ? 'bad' : 'ok'],
    ['Required parts available', inS + ' of ' + parts.length + ' parts in stock', inS === parts.length ? 'Confirmed' : inS >= parts.length - 2 ? 'Partly' : 'Backorder', inS === parts.length ? 'ok' : inS >= parts.length - 2 ? 'warn' : 'bad'],
    ['Hazmat and battery compliance', lith ? 'Lithium battery handling' : 'Not applicable', lith ? 'Check certificate' : 'Ready', lith ? 'warn' : 'ok'],
    ['Customer release required', d.lease && r.id !== 'redeploy' ? 'Lease ' + asLease(c) + ' · contract review' : 'Not required', d.lease && r.id !== 'redeploy' ? 'Pending' : 'Ready', d.lease && r.id !== 'redeploy' ? 'warn' : 'ok'],
    ['Create work order in EAM', eam.name + ' · ' + (eam.vendor || ''), eam.status === 'live' ? 'Ready' : 'Blocked', eam.status === 'live' ? 'ok' : 'bad'],
    [r.id === 'redeploy' || r.id === 'resale' ? 'Reserve stock in ERP' : 'Notify ERP finance', erp.name + ' · ' + (erp.vendor || ''), erp.status === 'live' ? 'Ready' : 'Blocked', erp.status === 'live' ? 'ok' : 'bad'],
  ];
  const ready = items.filter((i) => i[3] === 'ok').length;
  return (
    <Panel t="Handoff readiness" cls="tix5">
      <div className="tirdy"><b className="num">{ready} of {items.length}</b><span className="note">checks ready</span>{canPage('integration', 'map') && <a className="lnk" href="#/integration/map">View system actions</a>}</div>
      {items.map((i) => <div key={i[0]} className="asrow"><span><b>{i[0]}</b><div className="note">{i[1]}</div></span><span className={'chip ' + i[3]}>{i[2]}</span></div>)}
    </Panel>
  );
}

function Body({ c }: { c: CaseRec }) {
  const ui = useCaseUi();
  const a = caseAnalysis(c.id), s = caseScreen(c.id)!;
  const { sr, rows } = useRows(c, a);
  const ti = tiView(), CL = refList<Record<string, { plural: string }>>('CLASSES')[c.cls];
  const compare = () => {
    const body = compareBody(c, rows, ti.sel);
    if (!body) return toast('Tick at least two pathways to compare.');
    ui.modal({ title: 'Compare pathways · ' + c.id, body, foot: <button className="btn ghost" onClick={() => ui.modal(null)}>Close</button>, wide: true });
  };
  const step = (n: number) => (e: MouseEvent) => { e.preventDefault(); scrollToId('step-' + n); };
  return (
    <div className="ti">
      <nav className="crumbs ascr" aria-label="Breadcrumb">
        <a href="#/product/received">Assets</a> <span>›</span> <span>{CL?.plural ?? c.cls}</span> <span>›</span> <span>{s.model}</span> <span>›</span> <a href={'#/product/asset/' + c.id}>{c.assetId}</a> <span>›</span> <b>Treatment Intelligence</b>
      </nav>
      <div className="phead asph2">
        <div className="row" style={{ gap: 14, flexWrap: 'nowrap', alignItems: 'flex-start' }}>
          <span className="asico"><Icon name="analytics" /></span>
          <div><h1>Treatment Intelligence</h1><p>Evaluate, compare and optimise treatment pathways using predictive models and business constraints. <span className="note">{c.id}</span></p></div>
        </div>
        <div className="row asact">
          <button className="btn" disabled={!c.routes.length} onClick={() => saveScenario(c, a)}>Save scenario</button>
          <button className="btn" disabled={c.routes.length <= 1} onClick={compare}>Compare ({(ti.sel || []).length})</button>
          <button className="btn" onClick={() => openSnapshot(ui, c, a)}>Evidence snapshot</button>
          {c.stage === 'awaiting_approval' && (can('approve') || can('submit')) && <a className="btn pri" href="#step-5" onClick={step(5)}>{can('approve') ? 'Go to approval' : 'Go to submit'} →</a>}
        </div>
      </div>
      <nav className="tistp" aria-label="Decision steps">
        {TI_STEPS.map((t, i) => <a key={t} href={'#step-' + (i + 1)} onClick={step(i + 1)}><span className="tin">{i + 1}</span>{t}</a>)}
      </nav>
      <section className="tistep" id="step-1" aria-labelledby="sh-1">
        <StepH n={1} t="Returned asset and current status" sub="What the asset is, why it is in this status and what is still outstanding" />
        <TiCtx c={c} a={a} s={s} />
        {c.stage === 'reeval' && <div className="callout bad" style={{ marginBottom: 14 }}><b>Review triggered: {c.reevalReason}.</b> The earlier recommendation is on hold until it is re-evaluated. <a className="lnk" href="#step-5" onClick={step(5)}>Re-evaluate in step 5</a></div>}
      </section>
      <section className="tistep" id="step-2">
        <StepH n={2} t="Possible outcomes and the recommended one" sub="Every route Circularity built for this asset, eligible or withheld, then the one it recommends with its value, certified life and matched demand" />
        <TiOutcome c={c} a={a} sr={sr} rows={rows} />
      </section>
      <section className="tistep" id="step-3">
        <StepH n={3} t="Why this outcome" sub="Eligibility and gates, predicted outcomes, and the reasoning behind the ranking" />
        <div className="tig3" id="tiA"><TiA c={c} a={a} sr={sr} rows={rows} /></div>
        <details className="tifull" id="tiFull" open>
          <summary><b>Show full analysis</b> <span className="note">Evidence, prediction, options and gates and explanation</span></summary>
          <div className="tidetail" id="explain">
            <EvidenceBlock c={c} a={a} /><PredictBlock c={c} /><OptionsBlock c={c} sr={sr} /><SpecialBlock c={c} /><ExplainBlock c={c} a={a} />
          </div>
        </details>
      </section>
      <section className="tistep" id="step-4">
        <StepH n={4} t="What-if and edge cases" sub="Stress the assumptions and compare the top pathways. Nothing here changes the approved recommendation." />
        <TiP4 c={c} a={a} sr={sr} rows={rows} />
      </section>
      <section className="tistep" id="step-5">
        <StepH n={5} t="Next best action: approval and enterprise handoff" sub="Circularity recommends and sends the approved instruction; OMS, EAM, TMS, WMS and ERP finance carry out the work" />
        <div className="tig2">
          <div>
            <Panel t="Decision" cls="tix5a" id="tiDecision"><div className="tidec"><BestCard c={c} a={a} sr={sr} /></div></Panel>
            <TiHandoff c={c} a={a} />
          </div>
          <div><TiP5 c={c} a={a} s={s} /><ExecBlock c={c} a={a} /></div>
        </div>
        <TiReconcile c={c} a={a} />
      </section>
    </div>
  );
}

export function FullAnalysis({ c }: { c: CaseRec }) {
  return (
    <div className="stfull">
      <div className="callout info stfb" role="note">
        <b>Full analysis.</b> Everything on one page, for review and print. <a className="lnk" href={'#/' + stageHref(c.id, 6)}>Back to stage 6</a> · <a className="lnk" href={'#/' + stageHref(c.id, 'overview')}>Overview</a>
      </div>
      <Suspense fallback={<p className="note">Loading…</p>}><Body c={c} /></Suspense>
    </div>
  );
}
