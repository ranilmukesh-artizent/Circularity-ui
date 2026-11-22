import { Suspense, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import {
  activeClock, approverRole, assetModel, caseAnalysis, caseScreen, lc, nextStep, phaseOf, phases, rememberTab, rememberedTab, runOf,
  sources, stageData, stageHref, stageSentence, stageState, stageTitle, stageWillHappen, stages, when,
  type CaseRec, type Run, type StageTag,
} from '../../api/case';
import { can, canPage } from '../../api/session';
import { ErrorBoundary } from '../../components/Boundary';
import { Icon } from '../../components/Icon';
import { IconTile } from '../../components/kit/IconTile';
import { Doc, hue, StageLogos, StProv, Tag } from './CaseBlocks';
import { stageTabs, type TabDef } from './tabs';
import { approveGuarded, caseActions, runNextStep } from './caseActions';
import { useCaseUi, type CaseUi } from './CaseContext';

export type CaseView = { kind: 'stage'; n: number; tab: string | null } | { kind: 'overview' } | { kind: 'full' };

const href = (id: string, n: number | 'overview' | 'full', tab?: string | null) => '#/' + stageHref(id, n, tab);

/** The stage bar: four phases, ten chips, states in words; aria-current marks the stage in view (stBar). */
export function StageBar({ c, view }: { c: CaseRec; view: CaseView }) {
  const [open, setOpen] = useState(false);
  const run = runOf(c), p = run.stage, id = c.id, on = view.kind === 'stage' ? view.n : 0;
  const now = p > 10 ? 'Every stage is done' : 'Case at Stage ' + p + ' of 10 · ' + stageTitle(p) + ' · ' + stageState(c, p, run).word;
  const chip = (n: number) => {
    const t = stageState(c, n, run), s = stageSentence(c, n, t);
    return (
      <li key={n}>
        <a
          className={`afjd stc st-${t.k} ${run.stages[n - 1].state} ${n === on ? 'on' : ''} ${n === p ? 'cur' : ''}`}
          href={href(id, n)} aria-current={n === on ? 'step' : undefined} aria-label={s} data-tip={s} onClick={() => setOpen(false)}
        >
          <span className="stci" aria-hidden="true">{t.icon}</span>
          <span className="n">{n}</span>
          <span className="t">{stageTitle(n)}</span>
          <span className="sts">{t.k === 'wait' ? 'Waiting' : t.word}</span>
        </a>
      </li>
    );
  };
  return (
    <nav className={'stbar' + (open ? ' open' : '')} id="jgNav" aria-label={`Stages of ${id}: ${now}`}>
      <div className="stbt">
        <a className={'stov ' + (view.kind === 'overview' ? 'on' : '')} href={href(id, 'overview')} aria-current={view.kind === 'overview' ? 'page' : undefined}>
          <Icon name="home" />
          <span>Overview · <b>{id}</b></span>
        </a>
        <span className="stnow note">{now}</span>
        <button className="stmob" aria-expanded={open} aria-controls="stPh" onClick={() => setOpen((o) => !o)}>
          {on ? 'Stage ' + on + ' of 10 · ' + stageTitle(on) : view.kind === 'full' ? 'Full analysis' : 'Overview'} <span aria-hidden="true">▾</span>
        </button>
      </div>
      <div className="stphs" id="stPh">
        {phases().map((ph) => (
          <div key={ph.k} className="stph" style={hue(ph.h, ph.n.length)}>
            <span className="stphl">{ph.t}</span>
            <ol>{ph.n.map(chip)}</ol>
          </div>
        ))}
      </div>
    </nav>
  );
}

/** "Notify the owner": the agent drafts an escalation to whoever the stage waits on. */
function NotifyBtn({ who }: { who: string }) {
  return /Approver|Admin|Planner|Finance|Engineer|Inspection|Engineering/.test(who || '') ? (
    <button className="btn sm" onClick={caseActions.askSoon}>Notify the owner</button>
  ) : null;
}

function Wait({ who, since, extra }: { who: string; since?: string | null; extra?: ReactNode }) {
  return (
    <>
      <p className="stwait">
        <Tag t={{ k: 'wait', icon: '⏳', word: 'Waiting on ' + who }} />
        {since && <> <span className="note">since {when(since)}</span></>}
      </p>
      {extra}
      <NotifyBtn who={who} />
    </>
  );
}

const Cons = ({ b, l }: { b: ReactNode; l: ReactNode }) => (
  <div className="stact">
    {b}
    <p className="note">{l}</p>
  </div>
);

/** What this person does now, or who it waits on; one primary action per page (stDo). */
export function stageDo(c: CaseRec, n: number, t: StageTag, ui: CaseUi): { h: string; pri: boolean; b: ReactNode } {
  const r = c.chosen || c.recommendation, id = c.id, A = approverRole(c);
  const Pri = ({ children, onClick }: { children: ReactNode; onClick: () => void }) => <button className="btn pri lg" onClick={onClick}>{children}</button>;
  const ex = (h: string, b: ReactNode, pri = false) => ({ h, b, pri });
  if (t.k === 'todo') {
    const p = Math.min(runOf(c).stage, 10), S1 = stages()[n - 1];
    return ex('What happens next', <>
      <p style={{ marginTop: 0 }}>Starts on <b>{lc(S1.trig)}</b>. {S1.person}.</p>
      <p className="note">{id} is at stage {p}, {lc(stageTitle(p))}. <a className="lnk" href={href(id, p)}>Go to stage {p}</a></p>
    </>);
  }
  if (n <= 3) return ex('What you do now', <p style={{ marginTop: 0 }}><b>Nothing for you.</b> {n === 1 ? 'Opened by the agent from Lease management.' : n === 2 ? 'Recorded by the agent from Lease management and ERP finance.' : "Tracked by the agent from the carrier's TMS."}</p>);
  if (n === 4) {
    if (c.blocked && !c.requested && !c.recommendation && can('request'))
      return ex('What you do now', <Cons b={<Pri onClick={() => caseActions.requestEvidence(id)}>{c.blocked.action}</Pri>} l={`Sends the request to ${c.blocked.owner}; the case continues when it arrives.`} />, true);
    return ex('What you do now', <p style={{ marginTop: 0 }}><b>Nothing required.</b> Receipt is recorded in WMS{(c.evidence || []).some((e) => e.state !== 'ready') ? '; the missing evidence is requested in stage 5' : ''}.</p>);
  }
  if (n === 5) {
    if (t.k === 'done') return ex('What you do now', <p style={{ marginTop: 0 }}><b>Nothing required.</b> The result is recorded{c.grade ? ': grade ' + c.grade : ''}.</p>);
    if (c.requested && can('assess')) return ex('What you do now', <Cons b={<Pri onClick={() => caseActions.recordResult(id)}>Record the result</Pri>} l="Records the inspection result from the inspection system; the routes are built next." />, true);
    if (!c.requested && can('request')) return ex('What you do now', <Cons b={<Pri onClick={() => caseActions.requestEvidence(id)}>{c.blocked ? c.blocked.action : 'Request the test'}</Pri>} l={`Sends the request to ${c.blocked ? c.blocked.owner : 'Engineering'}.`} />, true);
    return ex('What happens next', <Wait who={c.blocked ? c.blocked.owner : 'Engineer'} since={c.requested ? c.requested.at : null} />);
  }
  if (n === 6) {
    if (t.k === 'block') {
      const re = can('reeval') && c.stage === 'reeval';
      return ex('What happens next', <>
        <p style={{ marginTop: 0 }}>{t.why || ''}</p>
        {re && <Cons b={<Pri onClick={() => caseActions.reevaluate(id)}>Re-evaluate {id}</Pri>} l="Rebuilds every route on fresh evidence." />}
      </>, re);
    }
    if (c.stage === 'awaiting_approval' && !c.submitted && can('submit'))
      return ex('What you do now', <Cons b={<Pri onClick={() => caseActions.submit(id)}>Submit {id} for review</Pri>} l={`The ${A} gets it in their inbox and approves, edits or declines it in stage 7.`} />, true);
    if (c.stage === 'awaiting_approval' && !c.submitted)
      return ex('What happens next', <Wait who="Planner" since={c.packet ? c.packet.at : null} extra={<p className="note">The Planner reviews the packet and submits it for approval.</p>} />);
    return ex('What happens next', <p style={{ marginTop: 0 }}><b>Decided.</b> {c.submitted && !c.approval ? 'Submitted by ' + c.submitted.by + '; the approval is in stage 7.' : c.approval ? 'Approved in stage 7.' : ''} <a className="lnk" href={href(id, 7)}>Open stage 7</a></p>);
  }
  if (n === 7) {
    if (c.stage === 'awaiting_approval' && can('approve') && r)
      return ex('What you do now', <div className="stact">
        <button className="btn pri lg" onClick={() => approveGuarded(id, ui)}><Icon name="check" /> Approve {r.plan}</button>
        <div className="row" style={{ gap: 8, marginTop: 8 }}>
          <button className="btn" onClick={() => approveGuarded(id, ui, 'review')}>Edit route</button>
          <button className="btn" onClick={() => ui.openDecline(id)}>Decline</button>
        </div>
        <p className="note">Opens the approval card with the agent's drafted rationale. Approving sends the instructions to the enterprise systems.</p>
      </div>, true);
    if (c.stage === 'awaiting_approval' && !c.submitted && can('submit'))
      return ex('What you do now', <Cons b={<Pri onClick={() => caseActions.submit(id)}>Submit {id} for review</Pri>} l={`The ${A} gets it in their inbox.`} />, true);
    if (t.k === 'wait') return ex('What happens next', <Wait who={t.who!} since={t.since} extra={<p className="note">The {t.who} approves, edits or declines it.</p>} />);
    return ex('What happens next', <p style={{ marginTop: 0 }}><b>Approved.</b> The instructions went to the enterprise systems. <a className="lnk" href={href(id, 8)}>Follow them in stage 8</a></p>);
  }
  if (n === 8) {
    if (t.k === 'done') return ex('What happens next', <p style={{ marginTop: 0 }}><b>Every instruction is acknowledged.</b> <a className="lnk" href={href(id, 9)}>See the outcome in stage 9</a></p>);
    const k = activeClock(c);
    if (can('execSim'))
      return ex('What you do now', <Cons b={<Pri onClick={() => caseActions.advance(id)}>Check for the next acknowledgement</Pri>} l={`You handle exceptions only${k && k.level ? ': this step passed its ' + k.lim + ' limit and escalated to ' + k.to : ''}. The systems do the work and report back.`} />, true);
    return ex('What happens next', <Wait who={t.who || 'the enterprise systems'} since={t.since} extra={<p className="note">You handle exceptions only.{k && k.level ? ' This step passed its limit and escalated to ' + k.to + '.' : ''}</p>} />);
  }
  if (n === 9) {
    if (c.outcome) return ex('What happens next', <p style={{ marginTop: 0 }}><b>Confirmed.</b> <a className="lnk" href={href(id, 10)}>Reconcile it line by line in stage 10</a></p>);
    if (c.stage === 'closed' && can('confirm')) return ex('What you do now', <Cons b={<Pri onClick={() => caseActions.confirmOutcome(id)}>Confirm the outcome</Pri>} l="Records the actual costs and value; stage 10 compares them with the prediction." />, true);
    // the CXO demo adds the next acknowledgement here while the systems are still reporting
    const nx = nextStep(c);
    const run = nx.kind === 'ack' ? <button className="btn pri cxnext" onClick={() => runNextStep(id, ui, true)}>{nx.label}</button> : null;
    if (t.k === 'wait') return ex('What happens next', <><Wait who={t.who!} since={t.since} />{run}</>);
    return ex('What happens next', <><p style={{ marginTop: 0 }}>The outcome comes back once every instruction is acknowledged.</p>{run}</>);
  }
  if (c.outcome)
    return ex('What you do now', <>
      <p style={{ marginTop: 0 }}><b>Review the variances</b> in the lines below.</p>
      {canPage('analytics', 'predicted') && <a className="btn" href={`#/analytics/predicted?dp=${id}`}>Open in Analytics</a>}
    </>);
  return ex('What happens next', <p style={{ marginTop: 0 }}>Reconciles once Finance confirms the outcome.</p>);
}

/** One stage page: what happened, what it means, what you do now, details in tabs (stPage). */
export function StagePage({ c, n, tab }: { c: CaseRec; n: number; tab: string | null }) {
  const ui = useCaseUi();
  const nav = useNavigate();
  const run = runOf(c), t = stageState(c, n, run), ph = phaseOf(n), d = stageData(c, n), S1 = stages()[n - 1], reached = t.k !== 'todo';
  const line = t.k === 'done' ? [d.when ? when(d.when) : '', d.who ? 'by ' + d.who : ''].filter(Boolean).join(' · ')
    : t.k === 'wait' ? (t.since ? 'since ' + when(t.since) + ' · ' : '') + S1.person
    : t.k === 'block' ? `Blocked: ${t.why || ''}` : t.k === 'cur' ? 'The case is here now' : `Starts on ${lc(S1.trig)}`;
  const D = stageDo(c, n, t, ui);
  const tabs = stageTabs(c, n), rem = rememberedTab(c.id, n);
  const cur = tabs.find((x) => x[0] === tab) ? tab : rem && tabs.find((x) => x[0] === rem) ? rem : tabs[0]?.[0];
  const pick = (k: string) => {
    rememberTab(c.id, n, k);
    nav('/' + stageHref(c.id, n, k), { replace: true });
  };
  const explain = n === 6 && !!c.recommendation;

  return (
    <div className="stpage" data-stage={n} data-phase={ph.k} style={hue(ph.h)}>
      <nav className="frbc stbc" aria-label="Breadcrumb">
        <a href="#/product/received">Returned assets</a><Icon name="chevR" />
        <a href={href(c.id, 'overview')}>{c.id} · {assetModel(c)}</a><Icon name="chevR" />
        <b>Stage {n}</b>
      </nav>
      <header className="sthead">
        <div className="sthl">
          <p className="stcap"><span className="stphase">{ph.t}</span> · Stage {n} of 10</p>
          <h1 id="stH1" tabIndex={-1}>{S1.t}</h1>
          <p className="stsub"><Tag t={t} big /><span className="stline">{line}</span></p>
          <p className="stlogos"><StageLogos n={n} src={sources(c)} /></p>
        </div>
        <div className="row stha">
          <button className="btn afai2" onClick={caseActions.askSoon}><Icon name="spark" /> Ask about this stage</button>
          {explain && <button className="btn pri cxxbtn" onClick={() => ui.openExplain(c.id)}>✦ Explain this decision</button>}
          {(n === 6 || n === 7) && <button className="btn" id="afPackBtn" onClick={() => caseActions.downloadPack(c.id)}>Evidence pack</button>}
        </div>
      </header>
      <div className="stgrid">
        {reached ? (
          <section className="stwh" id="stWhat" aria-labelledby="stWhatH">
            <div className="stwhh"><h2 id="stWhatH">What happened</h2><Tag t={t} /></div>
            <p className="stres" id="stRes">{d.res}</p>
            {d.facts.length > 0 && (
              <dl className="stfacts">
                {d.facts.map((f) => (
                  <div key={f.l} className={String(f.v).length > 34 ? 'wide' : undefined}>
                    <dt>{f.l}</dt><dd>{f.v}</dd><span className="stpv"><StProv k={f.k} sys={f.sys} src={sources(c)} /></span>
                  </div>
                ))}
              </dl>
            )}
            {d.docs.length > 0 && <p className="stdocs"><span className="note">Documents</span>{d.docs.map((r) => <Doc key={r} r={r} />)}</p>}
          </section>
        ) : (
          <section className="stwh will" id="stWhat" aria-labelledby="stWhatH">
            <div className="stwhh"><h2 id="stWhatH">What will happen</h2><Tag t={t} /></div>
            <p className="stres" id="stRes">{stageWillHappen(n)}.</p>
            <dl className="stfacts">
              <div><dt>Starts on</dt><dd>{S1.trig}</dd></div>
              <div><dt>The agent</dt><dd>{S1.agent}</dd></div>
              <div><dt>A person</dt><dd>{S1.person}</dd></div>
              <div><dt>Systems</dt><dd>{S1.sys.join(', ')}</dd></div>
            </dl>
          </section>
        )}
        <div className="stside">
          {d.mean && reached && (
            <section className="stmean" id="stMean" aria-labelledby="stMeanH">
              <IconTile ic="spark" h={ph.h} cls="sm" />
              <div><h2 id="stMeanH">What it means</h2><p>{d.mean}</p></div>
            </section>
          )}
          <section className={'stdo ' + (D.pri ? 'act' : '')} id="stDo" aria-labelledby="stDoH">
            <h2 id="stDoH">{D.h}</h2>
            {D.b}
          </section>
        </div>
      </div>
      {n > 1 && <Recap c={c} n={n} run={run} />}
      {tabs.length > 0 && (
        <section className="stdet" id="stDet" aria-label="Details">
          <div className="frseg sttabs" role="tablist" aria-label={`Details of stage ${n}`}>
            {tabs.map((x) => (
              <button key={x[0]} role="tab" id={'stt-' + x[0]} aria-controls={'stp-' + x[0]} aria-selected={x[0] === cur} tabIndex={x[0] === cur ? 0 : -1} onClick={() => pick(x[0])}>
                {x[1]}
              </button>
            ))}
          </div>
          {tabs.map((x) => (
            <details
              key={x[0]} className="stacc" id={'stp-' + x[0]} data-k={x[0]} open={x[0] === cur}
            >
              <summary onClick={(e) => { e.preventDefault(); pick(x[0]); }}>{x[1]}</summary>
              {x[0] === cur && (
                <div className="stpn" role="tabpanel" aria-labelledby={'stt-' + x[0]}>
                  <ErrorBoundary resetKey={c.id + n + x[0]}><Suspense fallback={<p className="note stpad">Loading…</p>}><TabBody c={c} tab={x} /></Suspense></ErrorBoundary>
                </div>
              )}
            </details>
          ))}
        </section>
      )}
    </div>
  );
}

/** One tab's content, drawn from the analysis (read here, so the stage page shows before it arrives). */
function TabBody({ c, tab }: { c: CaseRec; tab: TabDef }) {
  const a = caseAnalysis(c.id), s = caseScreen(c.id)!;
  const View = tab[2];
  return <View c={c} a={a} s={s} />;
}

function Recap({ c, n, run }: { c: CaseRec; n: number; run: Run }) {
  return (
    <details className="strecap" id="stRecap">
      <summary><b>Established so far</b> <span className="note">stages 1–{n - 1}</span></summary>
      <ol>
        {Array.from({ length: n - 1 }, (_, k) => k + 1).map((i) => {
          const s = run.stages[i - 1];
          return (
            <li key={i} className={'st-' + stageState(c, i, run).k}>
              <span className="n">{i}</span><b>{stageTitle(i)}</b>
              <span className="note">{s.state === 'queued' ? 'Not reached' : s.result || ''}</span>
              <a className="lnk" href={href(c.id, i)}>View</a>
            </li>
          );
        })}
      </ol>
    </details>
  );
}

/** The footer: named Back and Next, the position, the Overview and the agent's suggestion (stFoot). */
export function StageFoot({ c, view, pri }: { c: CaseRec; view: CaseView; pri: boolean }) {
  const ui = useCaseUi();
  const id = c.id, nx = nextStep(c), at = Math.min(runOf(c).stage, 10);
  if (view.kind !== 'stage')
    return (
      <aside className="jgg stfoot" id="jgGuide" aria-label="Stage navigation">
        <span className="stpos">{view.kind === 'full' ? 'Full analysis' : 'Overview'} · {id}</span>
        <span className="sp" />
        <a className={'btn ' + (view.kind === 'full' ? '' : 'pri')} id="jgContinue" href={href(id, view.kind === 'full' ? 6 : at)}>
          {view.kind === 'full' ? 'Back to stage 6' : 'Open stage ' + at + ' · ' + stageTitle(at)} →
        </a>
      </aside>
    );
  const n = view.n, sug = nx.kind === 'done' ? 'Every stage is done' : nx.label;
  const btn = pri ? null
    : (nx.kind === 'act' || nx.kind === 'ack') && nx.n !== n ? <button className="btn sm" onClick={() => runNextStep(id, ui)}>{nx.label}</button>
    : nx.kind === 'approve' && n !== 7 ? <button className="btn sm" onClick={() => approveGuarded(id, ui)}>Open the approval card</button>
    : null;
  return (
    <aside className="jgg stfoot" id="jgGuide" aria-label="Stage navigation" data-state={stageState(c, n).k}>
      {n > 1 ? (
        <a className="btn" id="jgBack" href={href(id, n - 1)} aria-label={`Back to stage ${n - 1}, ${stageTitle(n - 1)}`}>← <span className="stfn">{n - 1} {stageTitle(n - 1)}</span></a>
      ) : <span />}
      <span className="stpos">Stage {n} of 10</span>
      <a className="btn ghost sm" href={href(id, 'overview')}>Overview</a>
      <p className="stsug">
        <span className="jgk"><Icon name="spark" /> Agent suggests</span> <b>{sug}</b>
        {nx.n && nx.n !== n && nx.kind !== 'done' ? <> <span className="note">(stage {nx.n})</span></> : null} {btn}
      </p>
      {n < 10 ? (
        <a className={'btn ' + (pri ? '' : 'pri')} id="jgContinue" href={href(id, n + 1)} aria-label={`Next: stage ${n + 1}, ${stageTitle(n + 1)}`}><span className="stfn">{n + 1} {stageTitle(n + 1)}</span> →</a>
      ) : (
        <a className={'btn ' + (pri ? '' : 'pri')} id="jgContinue" href={href(id, 'overview')}>Overview →</a>
      )}
    </aside>
  );
}
