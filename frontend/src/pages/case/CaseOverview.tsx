import type { CSSProperties } from 'react';
import type { PackStage } from '../../api/analytics';
import {
  assetModel, assetSerial, custody, lc, nextStep, packStages, phases, recordMatch, runOf, stageHref, stageSentence,
  stageState, stageTitle, stages, when, type CaseRec,
} from '../../api/case';
import { fmtDate, fmtDateYear, money } from '../../api/format';
import { canPage } from '../../api/session';
import { Icon } from '../../components/Icon';
import { Panel } from '../../components/kit/Panel';
import { Photo, Pva, Tag } from './CaseBlocks';
import { approveGuarded, caseActions, runNextStep } from './caseActions';
import { useCaseUi } from './CaseContext';
import { custodyLines, recordMatchLine } from './custody';

const href = (id: string, n: number | 'overview' | 'full') => '#/' + stageHref(id, n);
const AUTONOMY = { recommend: 'recommends only', limits: 'within limits', alone: 'acts alone' } as const;

/** "Intake (acts alone) · Condition (within limits) · …": the pack's stage agents, a repeated agent once; null for no pack stages. */
const agentsLine = (stages: PackStage[] | null): string | null => {
  if (!stages) return null;
  const seen = new Set<string>();
  const parts = stages.flatMap((s) => {
    const part = `${s.agent} (${AUTONOMY[s.autonomy]})`;
    return seen.has(part) ? [] : (seen.add(part), [part]);
  });
  return parts.length ? parts.join(' · ') : null;
};

/** The case Overview: one card per stage, grouped by phase; the decision or outcome at a glance (stOverview). */
export function Overview({ c }: { c: CaseRec }) {
  const ui = useCaseUi();
  const run = runOf(c), r = c.chosen || c.recommendation, o = c.outcome, nx = nextStep(c), id = c.id, ss = run.stages;
  const glance = o && r ? (
    <span className="stgl">
      <b className="num">{money(o.net)}</b> actual · <span className={o.net - r.net < 0 ? 'tx-bad' : 'tx-ok'}>{(o.net - r.net < 0 ? '−' : '+') + money(Math.abs(o.net - r.net))}</span> against prediction
    </span>
  ) : r ? (
    <span className="stgl">
      <b>{r.plan}</b> · <b className="num">{money(r.net)}</b>
      {c.approval ? ' · Approved ' + fmtDate(c.approval.at) : c.submitted ? ' · Submitted, waiting for approval' : ' · Recommended'}
    </span>
  ) : (
    <span className="stgl">{ss[run.stage > 10 ? 9 : run.stage - 1].result || 'No route yet'}</span>
  );
  const card = (n: number) => {
    const t = stageState(c, n, run), s = ss[n - 1];
    return (
      <li key={n}>
        <a className={`stcard st-${t.k} ${n === run.stage ? 'cur' : ''}`} href={href(id, n)} aria-label={`${stageSentence(c, n, t)}. Open stage ${n}.`}>
          <span className="stcn">{n}</span>
          <span className="stcb">
            <b>{stageTitle(n)}</b>
            <span className="stcr">{t.k === 'todo' ? 'Not reached yet' : t.k === 'block' ? t.why || s.result : s.result || ''}</span>
            <span className="note">
              {t.k === 'wait' ? 'Waiting on ' + t.who + (t.since ? ' since ' + when(t.since) : '')
                : t.k === 'done' ? [s.at ? when(s.at) : '', s.by || ''].filter(Boolean).join(' · ')
                : t.k === 'todo' ? 'Starts on ' + lc(stages()[n - 1].trig) : ''}
            </span>
          </span>
          <Tag t={t} />
          <span className="stgo" aria-hidden="true">Open →</span>
        </a>
      </li>
    );
  };
  const matchLine = recordMatchLine(recordMatch(c)), trail = custodyLines(custody(c)), agents = agentsLine(packStages(c));
  const mine = nx.kind ==='act' || nx.kind === 'approve' || nx.kind === 'ack';
  return (
    <div className="stpage stovw" data-stage="overview">
      <nav className="frbc stbc" aria-label="Breadcrumb">
        <a href="#/product/received">Returned assets</a><Icon name="chevR" />
        <b>{id} · Overview</b>
      </nav>
      <header className="sthead stovh">
        <Photo c={c} cls="stph" />
        <div className="sthl">
          <p className="stcap">Case overview · {c.owner} · {c.location}</p>
          <h1 id="stH1" tabIndex={-1}>{id} · {assetModel(c)}</h1>
          <p className="stsub">{glance}</p>
          <p className="note">
            {c.assetId} · {assetSerial(c)} · received {fmtDateYear(c.received)} · {run.stage > 10 ? 'every stage done' : 'at stage ' + run.stage + ', ' + lc(stageTitle(run.stage))}
          </p>
        </div>
      </header>
      <div className="stovg">
        <div className="stovl">
          {phases().map((ph) => (
            <section key={ph.k} className="stovp" style={{ '--c': `var(--h-${ph.h})` } as CSSProperties} aria-labelledby={'stph-' + ph.k}>
              <h2 id={'stph-' + ph.k} className="stphase">{ph.t}</h2>
              <ol className="stcards">{ph.n.map(card)}</ol>
            </section>
          ))}
        </div>
        <aside className="stovr">
          <section className="panel frp">
            <div className="ph"><h3>Needs you</h3></div>
            <div className="pb">
              {mine ? (
                <>
                  <p className="note" style={{ marginTop: 0 }}>Stage {nx.n} · {stageTitle(nx.n)}</p>
                  <button className="btn sm pri" onClick={() => (nx.kind === 'approve' ? approveGuarded(id, ui) : runNextStep(id, ui))}>{nx.label}</button>
                </>
              ) : (
                <p className="note" style={{ margin: 0 }}>Nothing on {id} waits on you.{nx.kind !== 'done' ? ' ' + nx.label + '.' : ''}</p>
              )}
            </div>
          </section>
          {agents && (
            <section className="panel frp" aria-label="Agents on this case">
              <div className="ph"><h3>Agents on this case</h3></div>
              <div className="pb"><p className="note" style={{ margin: 0 }}>{agents}</p></div>
            </section>
          )}
          {(matchLine || trail.length > 0) && (
            <section className="panel frp" aria-label="System of record and custody">
              <div className="ph"><h3>Custody</h3></div>
              <div className="pb">
                {matchLine && <p className={recordMatch(c)?.found ? 'note' : 'note tx-bad'} style={{ marginTop: 0 }}>{matchLine}</p>}
                {trail.length > 0 && <ul className="note" style={{ margin: 0, paddingLeft: 16 }}>{trail.map((l) => <li key={l}>{l}</li>)}</ul>}
              </div>
            </section>
          )}
          <section className="panel frp">
            <div className="ph"><h3><Icon name="spark" /> Agent suggests</h3></div>
            <div className="pb">
              <p style={{ margin: '0 0 8px' }}>
                {nx.kind === 'done' ? 'Every stage is done.' : nx.label}
                {nx.role && nx.kind !== 'act' && <> <span className="note">({nx.role})</span></>}
              </p>
              <button className="btn sm afai2" onClick={caseActions.askSoon}><Icon name="spark" /> Ask about {id}</button>
            </div>
          </section>
          {o && r && (
            <Panel title="Predicted against actual"><Pva pred={r.net} act={o.net} /></Panel>
          )}
          <section className="panel frp">
            <div className="ph"><h3>More on {id}</h3></div>
            <div className="pb stlinks">
              <a className="lnk" href={`#/product/asset/${id}`}>Asset intelligence</a>
              <a className="lnk" href={href(id, 'full')}>Full analysis</a>
              {canPage('orchestration', 'run') && <a className="lnk" href={`#/orchestration/run?case=${id}`}>See it run</a>}
              <button className="btn sm" id="afPackBtn" onClick={() => caseActions.downloadPack(id)}>Evidence pack</button>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
