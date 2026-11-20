/**
 * Stage 6 (Decide): the detail tabs and the Treatment Intelligence blocks they are made of (afCasePacket, tiOutcome,
 * tiA, explainBlock, evidenceBlock, specialBlock, tiP4, predictBlock, optionsBlock, asDemand). Full analysis and the
 * Explain view reuse the blocks. Ported from index.html with the same classes and text.
 */
import { useState, type ReactNode } from 'react';
import { invoke } from '../../../api/actions';
import {
  confidence, fmtDY, fmtN, isoT, kfmt, lc, recert, refList, resetScen, scen, scenActive, scenAdj, scenChanged, scenRoutes, setScen, setTi,
  stageHref, tiRows, tieBreak, tieText, tiView, TB_RULES, exTs, locName,
  type CaseAnalysis, type CaseRec, type Evidence, type RankRow, type Route, type ScenKey, type ScenRoutes, type Tie, type TiRow,
} from '../../../api/case';
import { money } from '../../../api/format';
import { can } from '../../../api/session';
import { toast } from '../../../ui/toast';
import { openExSrc, openExSrcAll, openModels, openSources, openTrace } from '../drawers';
import { AfBadge, ExMethod, Panel, ProvB, RangeBar, Stp, Tbl } from '../kit';
import { approveGuarded, caseActions, runNextStep, scrollToId, useCaseUi } from '../ui';
import type { TabProps } from './index';

type P = { c: CaseRec; a: CaseAnalysis };
type PS = P & { sr: ScenRoutes; rows: TiRow[] };

/** Routes are copies in JSON: the same route has the same id and plan. */
export const sameR = (x: Route | null | undefined, y: Route | null | undefined): boolean => !!(x && y && x.id === y.id && x.plan === y.plan);
const rid = (id: string) => refList<{ id: string; name: string; short: string; color: string }[]>('ROUTES').find((x) => x.id === id) || { id, name: id, short: id, color: '#999' };
const gates = () => refList<string[]>('GATES');
const asOf = () => new Date(refList<string | Date>('AS_OF') as string);
const addDays = (d: Date | string, n: number) => new Date(new Date(d).getTime() + n * 864e5);
/** tiM for one route: the base ranking row with the scenario net. */
const metrics = (a: CaseAnalysis, r: Route, net = r.net): RankRow => {
  const z = a.ranking.find((x) => x.route === r.id && x.plan === r.plan);
  if (z) return { ...z, net };
  const sum = (f: (v: number) => boolean) => r.terms.filter((t) => f(t.amt)).reduce((s, t) => s + t.amt, 0);
  return { route: r.id, plan: r.plan, gross: sum((v) => v > 0), cost: sum((v) => v < 0), net, days: 0, prob: 0, life: '—', co2: 0 };
};
/** scenRoutes and tiRows for the assumptions in view. */
export function useRows(c: CaseRec, a: CaseAnalysis): { sr: ScenRoutes; rows: TiRow[] } {
  const sr = scenRoutes(c);
  const t = tiView();
  if (!t.sel || t.selFor !== c.id) {
    const rw = tiRows(c, a, sr).slice().sort((x, y) => y.net - x.net);
    setTiQuiet({ sel: rw.slice(0, 3).map((z) => z.r.plan), selFor: c.id, focus: null });
  }
  return { sr, rows: tiRows(c, a, sr) };
}
// first draw of a case picks the top three for comparison without re-rendering during render
function setTiQuiet(p: { sel: string[]; selFor: string; focus: null }) {
  Object.assign(tiView() as object, p);
}
const CONF_DO: Record<string, string> = { High: 'Approve as normal', Medium: 'Check the deciding factor before approving', Low: 'Compare the alternatives before approving' };

// ================================================================ the decision packet (afCasePacket)
const RUN_ST: Record<string, [string, string]> = { done: ['Completed', 'ok'], failed: ['Failed', 'bad'], person: ['Waiting for a person', 'y'], queued: ['Queued', 'line'], running: ['Running', 'warn'], skipped: ['Skipped', 'line'], waiting: ['Waiting for approval', 'y'], warning: ['Warning', 'warn'] };
const AfLv = ({ l }: { l: string }) => (
  <><span className={'afl afl-' + l} aria-hidden="true">{l === 'ok' ? '✓' : l === 'bad' ? '✕' : '!'}</span><span className="sr">{l === 'ok' ? 'OK' : l === 'bad' ? 'Problem' : 'Check'}: </span></>
);
function AfHead({ title, badges, sub }: { title: ReactNode; badges: string[]; sub?: ReactNode }) {
  return (
    <header className="afch">
      <div><h4>{title}</h4>{sub && <div className="note">{sub}</div>}</div>
      <span className="afbs">{badges.map((b) => <AfBadge key={b} k={b} />)}</span>
    </header>
  );
}
const B = ({ children, pri, onClick, href }: { children: ReactNode; pri?: boolean; onClick?: () => void; href?: string }) =>
  href ? <a className={'btn sm ' + (pri ? 'pri' : '')} href={href}>{children}</a> : <button className={'btn sm ' + (pri ? 'pri' : '')} onClick={onClick}>{children}</button>;

function Packet({ c, a, s }: TabProps) {
  const ui = useCaseUi();
  const r = c.recommendation;
  if (!r) {
    const run = s.run, nx = s.next;
    return (
      <article className="afc afc-stages" data-card="stages">
        <AfHead title={'Case run · ' + ((run as { id?: string }).id ?? c.id)} badges={['Retrieved', 'Rules']} sub={c.id + ' · ' + (run.stage > 10 ? 'complete' : 'stage ' + run.stage + ' of 10')} />
        <ol className="afst">
          {run.stages.map((x) => (
            <li key={x.n} className={x.state + ' ' + (x.n === run.stage ? 'cur' : '')}>
              <span className="tin">{x.n}</span><b>{x.t}</b><span className={'chip ' + (RUN_ST[x.state] || [x.state, 'line'])[1]}>{(RUN_ST[x.state] || [x.state])[0]}</span>
              <span className="note">{x.result || ''}{x.by ? ' · ' + x.by : ''}{(x as { prep?: string }).prep ? ' · prepared by agent' : ''}</span>
            </li>
          ))}
        </ol>
        <footer className="afcf">
          {nx && (nx.kind === 'act' || nx.kind === 'ack') ? <B pri onClick={() => runNextStep(c.id, ui)}>{nx.label}</B> : nx && nx.kind === 'approve' ? <B pri onClick={() => approveGuarded(c.id, ui)}>Open the approval card</B> : null}
          <B href={'#/orchestration/run?case=' + c.id}>Open the run view</B>
        </footer>
      </article>
    );
  }
  const v = a.view, M = a.demand, rt = v.routes_read, ap = can('approve'), sb = can('submit') && !c.submitted && c.stage === 'awaiting_approval';
  const tr = a.routes.find((x) => x.id === r.id && x.plan === r.plan);
  const mv = a.move;
  const order = M && M.order && r.id === 'redeploy' ? { ref: M.order, line: M.line, customer: c.owner, site: locName(a, M.shipTo), need: M.needBy ? fmtDY(M.needBy) : '', po: M.avoidedPo } : null;
  const risks = v.risks.filter((x) => x.level !== 'ok');
  const prep = !!c.packet?.prep;
  return (
    <article className="afc afc-packet" data-card="packet">
      <AfHead title={'Decision packet · ' + c.id} badges={['Rules', 'Model'].concat(prep ? ['Prepared by agent'] : [])} sub={s.model + ' · ' + c.owner + ' · ' + c.location + ' · ' + v.stage_label} />
      <div className="afrec">
        <span className="chip y">Recommended</span><b className="afrect">{r.plan}</b><span className="afnet num">{money(r.net)}</span>
        <span className="note">predicted net · P10–P90 {money(r.p10)}–{money(r.p90)} · {confidence(a, r)} confidence</span>
        <p className="afwhy">{r.why ? r.why.replace(/\.?$/, '.') : 'Highest predicted net among eligible routes.'}</p>
        {order && <p className="note aford" id="afOrder">Against <b className="mono">{order.ref} line {order.line}</b> · {order.customer} · {order.site} · need-by {order.need} · replaces planned {order.po}</p>}
      </div>
      <div className="afgrid">
        <section>
          <h5>Alternatives</h5>
          {rt.eligible.length > 1 ? (
            <table className="t static tight"><tbody>{rt.eligible.slice(1, 4).map((x) => <tr key={x.plan}><td>{x.plan}</td><td className="r num">{money(x.net)}</td><td className="r note num">−{money(r.net - x.net).replace('−', '')}</td></tr>)}</tbody></table>
          ) : <p className="note">No other eligible route.</p>}
          {rt.excluded.length > 0 && <><h5>Not eligible</h5><ul className="afex">{rt.excluded.slice(0, 4).map((x) => <li key={x.plan}><b>{x.plan}</b> <span className="note">{x.gate} gate: {x.reason}</span></li>)}</ul></>}
        </section>
        <section>
          <h5>Gates <AfBadge k="Rules" /></h5>
          <ul className="afgates">{gates().map((g, i) => <li key={g} className={r.gates[i]}><AfLv l={r.gates[i] === 'pass' ? 'ok' : r.gates[i] === 'fail' ? 'bad' : 'warn'} />{g}</li>)}</ul>
          {risks.length > 0 && <><h5>Risks and open items</h5><ul className="afrisk">{risks.map((x, i) => <li key={i}><AfLv l={x.level} /><b>{x.text}</b> <span className="note">{x.detail}</span></li>)}</ul></>}
        </section>
      </div>
      {v.evidence_read.items.length > 0 && (
        <><h5>Key evidence <AfBadge k="Retrieved" /></h5>
          <p className="afev">{v.evidence_read.items.slice(0, 10).map((e) => <span key={e.label} className={'chip ' + (e.state === 'ready' ? 'ok' : e.state === 'missing' ? 'bad' : 'warn')} title={e.system || ''}>{e.label.replace(/ (available|verified|retrieved|checked|current|linked)$/, '')}</span>)}</p></>
      )}
      <div className="afgrid">
        <section><h5>Who decides</h5><p className="note">{s.approval.role}{c.submitted ? ' · submitted by ' + c.submitted.by : c.stage === 'awaiting_approval' ? ' · after a Planner submits it' : ''}{c.approval ? ' · approved under ' + c.approval.ref : ''}</p></section>
        {mv && mv.legs.length > 0 && (
          <section><h5>Where and when</h5><p className="note afmove">{mv.stops.join(' → ')} · ETD {exTs(mv.legs[0].etd)} · ETA {mv.eta ? exTs(mv.eta) : ''}{mv.slack != null ? ' · ' + (mv.slack < 0 ? Math.abs(mv.slack) + ' days late' : mv.slack + ' days of slack') : ''}{mv.stage ? '. Staging: ' + mv.stage.why : ''}</p></section>
        )}
      </div>
      <h5>After approval </h5>
      <div className="tw">
        <table className="t static tight afins">
          <thead><tr><th>#</th><th>Step</th><th>System</th><th>Document</th><th>Owner</th><th>Time limit</th></tr></thead>
          <tbody>{a.plan.map((x, i) => (
            <tr key={i}><td className="num">{i + 1}</td><td><b>{x.label}</b></td><td>{x.app}</td><td className="mono">{x.docs[0]}{x.planned && <div className="note">to be created</div>}</td><td>{x.owner}</td>
              <td className="nowrap">{x.lim}{x.clock && x.clock.level ? <> <span className="chip bad">Escalated to {x.clock.to}</span></> : null}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <h5>What happens if</h5>
      <ul className="afhap">{a.what_if.map((w) => <li key={w.k}><span className={'chip ' + (w.on ? 'warn' : 'line')}>{w.on ? 'Enforced' : 'Guidance'}</span> <b>{w.t}</b> <span className="note">{w.d}</span></li>)}</ul>
      <h5>How {money(r.net)} is built</h5>
      <table className="t static tight afval"><tbody>{r.terms.map((t, i) => <tr key={i}><td>{t.label} <ExMethod m={tr?.terms?.[i]?.method ?? 'Modelled'} /></td><td className="r num">{money(t.amt)}</td></tr>)}</tbody></table>
      {c.packet && <div className="afdraft"><b>Drafted rationale</b> {c.packet.prep && <AfBadge k="Prepared by agent" />}<p>{c.packet.rationale}</p></div>}
      <footer className="afcf">
        {ap && c.stage === 'awaiting_approval' && <B pri onClick={() => approveGuarded(c.id, ui)}>Approve…</B>}
        {sb && <B pri onClick={() => caseActions.submit(c.id)}>Submit for review</B>}
        {(ap || sb) && c.stage === 'awaiting_approval' && <B href={'#/' + stageHref(c.id, 7)}>Edit</B>}
        <B onClick={caseActions.askSoon}>Escalate</B>
        <B href={'#/' + stageHref(c.id, 'full')}>Full analysis</B>
        <B onClick={() => openExSrcAll(ui, c, a, c.routes.findIndex((x) => sameR(x, r)))}>Where the numbers come from</B>
        <B href={'#/orchestration/run?case=' + c.id}>Show trace</B>
      </footer>
    </article>
  );
}
export const PacketTab = (p: TabProps) => <div id="afPacket"><Packet {...p} /></div>;

// ================================================================ step 2: possible outcomes (tiOutcome)
function TiAllPaths({ c }: { c: CaseRec }) {
  const rec = c.recommendation, ch = c.chosen, rs = c.routes.slice().sort((x, y) => y.net - x.net), el = rs.filter((r) => !r.excluded).length;
  if (!rs.length) return null;
  return (
    <Panel t={<>All pathways <span className="note">{rs.length} route{rs.length > 1 ? 's' : ''} · {el} eligible · {rs.length - el} withheld</span></>} cls="tiallw" id="tiAllPaths">
      <p className="note" style={{ margin: '0 0 8px' }}>Every route Circularity built for {c.id}, including any a gate withheld. Net is the predicted net contribution.</p>
      <Tbl head={[['Pathway'], ['Net', 'r'], ['P10 to P90', 'r'], ['Status']]} cls="tiallp" rows={rs.map((r, i) => {
        const isRec = sameR(r, rec), isCh = sameR(r, ch || rec);
        return (
          <tr key={i} className={isCh ? 'sel' : ''} data-route={r.id} data-st={isRec ? 'rec' : r.excluded ? 'withheld' : 'eligible'}>
            <td><b>{r.plan}</b>{r.demandLabel && <div className="note">{r.demandLabel}</div>}</td>
            <td className="r num"><b>{money(r.net)}</b></td><td className="r num">{money(r.p10)} to {money(r.p90)}</td>
            <td>{isRec && <><span className="chip y">Recommended</span> </>}{ch && !sameR(ch, rec) && sameR(r, ch) && <span className="chip ok">Approved (override)</span>}
              {r.excluded ? <><span className="chip bad">Withheld</span><div className="note">{r.failReason || 'A gate failed'}</div></> : !isRec && !sameR(r, ch) ? <span className="chip ok">Eligible</span> : null}</td>
          </tr>
        );
      })} />
    </Panel>
  );
}
function TiKnown({ c, a }: P) {
  const D = a.view.diag, R = a.rul, d = refList<Record<string, [string, string]>>('DIAG')[c.cls] || ['', 'pct'];
  return (
    <>
      <div className="ticlvc"><span className="ticlh">Diagnostic condition</span>
        {D ? <><b>{D.metric}: {D.value}</b><span className="note">{D.source} · {D.at}</span>{d[1] !== 'grade' && <span className="note">Value modelled from grade, age and class</span>}</>
          : <><b>Not inspected yet</b><span className="note">Waiting for the inspection report</span></>}
      </div>
      <div className="ticlvc"><span className="ticlh">Certified period</span>
        {R ? <><span className="ticert" style={{ border: 0, padding: 0, margin: 0 }}>Certified operating period <b className="num">{R.certMonths} months</b></span><span className="note">{R.basis} · {R.certRef}</span></>
          : <><b>No certified life</b><span className="note">{c.engLife || 'Not assessed'}</span></>}
      </div>
    </>
  );
}
function TiPredicted({ c, a }: P) {
  const R = a.rul, r = c.chosen || c.recommendation, M = a.demand, rc = r && recert(a, r), hz = M && R ? Math.min(rc ? rc.need : M.horizonMonths, R.certMonths) : null;
  return (
    <>
      <div className="ticlvc"><span className="ticlh">Life after intervention</span>
        {R ? <><span>Estimated RUL <b className="num">{R.estLow}–{R.estHigh} months</b></span><span className="note">Most likely {R.estMonths} · modelled range</span>
          {R.certMonths < R.estMonths && <span className="note">Cannot be certified for {R.estMonths} months; limited to the certified {R.certMonths}.</span>}</>
          : <><b>No estimate yet</b><span className="note">Needs an inspection grade</span></>}
      </div>
      <div className="ticlvc"><span className="ticlh">Commercial value for that life</span>
        {r ? <>
          <b>{r.plan} · <span className="num">{money(r.net)}</span></b>
          {hz ? <span>Demand horizon <b className="num">{hz} months</b> <span className="note">capped at the certified period</span></span> : null}
          {M && M.order ? <span>Matched demand: contract replacement order <b className="mono">{M.order}</b> for <b>{c.owner}</b> at <b>{M.site || '—'}</b> · {M.confirmed ? 'confirmed' : 'forecast'} · accepts certified refurbished</span>
            : M && M.lease ? <span>Lease opportunity {M.lease}</span> : <span className="note">No internal demand matched</span>}
          {r.target && <span className="note">Target: {r.target}</span>}
          {rc && <span><span className="chip warn">Needs re-certification</span> <span className="note">Demand needs {rc.need} months; certified for {rc.cert}. The pathway is Conditional.</span></span>}
        </> : <b>No recommendation yet</b>}
      </div>
    </>
  );
}
function TiClv(p: P) {
  return (
    <div className="ticlv2" id="tiClv">
      <div className="tiz known"><div className="tizh"><b>What we know</b><ProvB k="ret" sys={p.c.cls === 'motor' || p.c.cls === 'pump' ? 'EAM, QMS' : 'Inspection, QMS'} /></div><div className="tizb"><TiKnown {...p} /></div></div>
      <div className="tiz pred"><div className="tizh"><b>What we predict</b><ProvB k="mod" sys="Circularity models" /></div><div className="tizb"><TiPredicted {...p} /></div></div>
    </div>
  );
}
export function TiOutcome({ c, a, rows }: PS) {
  const r = c.chosen || c.recommendation;
  if (!r) return (
    <>
      <TiAllPaths c={c} />
      <div className="panel" id="tiRecPath"><div className="pb"><div className="empty"><b>No recommended outcome yet</b>{c.blocked ? c.blocked.reason : 'Evidence is needed first.'}</div></div></div>
      <TiClv c={c} a={a} />
    </>
  );
  const me = rows.find((z) => sameR(z.r, r)) || metrics(a, r), R = a.rul, M = a.demand, t = tieBreak(a, rows), cf = confidence(a, r);
  return (
    <>
      <TiAllPaths c={c} />
      <div className="tisum" id="tiRecPath">
        <div className="tisumh"><span className="chip ok">Recommended outcome</span>{t && t.near && <span className="chip warn">Close call</span>}<span className="chip line" data-tip={CONF_DO[cf]}>Confidence: {cf}</span></div>
        <div className="tirt">{r.plan}</div>
        <div className="tisumg">
          <div><span className="note">Net recovery</span><b className="num">{money(r.net)}</b></div>
          <div><span className="note">Costs</span><b className="num">{money(me.cost)}</b></div>
          <div><span className="note">Estimated RUL</span><b className="num">{R ? R.estLow + '–' + R.estHigh + ' mo' : '—'}</b></div>
          <div><span className="note">Certified period</span><b className="num">{R ? R.certMonths + ' mo' : '—'}</b></div>
          <div><span className="note">Success</span><b className="num">{me.prob}%</b></div>
          <div><span className="note">Cycle time</span><b className="num">{me.days} days</b></div>
        </div>
        <p className="note" style={{ margin: '8px 0 0' }}>
          {M && M.order && <>Matched to {c.owner}'s contract replacement order <b className="mono">{M.order}</b> at <b>{M.site || '—'}</b>, which accepts a certified refurbished unit. </>}
          {r.target ? 'Target: ' + r.target + '. ' : ''}<b>Confidence {cf}:</b> {CONF_DO[cf].toLowerCase()}.{t && t.near ? ' ' + tieText(t) : ''}
        </p>
      </div>
      <TiClv c={c} a={a} />
    </>
  );
}
export function CompareTab({ c, a }: TabProps) {
  const x = useRows(c, a);
  return <section className="tistep" id="step-2"><TiOutcome c={c} a={a} {...x} /></section>;
}

// ================================================================ step 3: why this outcome (tiA)
function TiP1({ c, a, sr }: PS) {
  const ti = tiView();
  const el = c.routes.map((r) => {
    const ex = sr.all.find((x) => x.r === r), restricted = !!(ex && ex.ex), rc = recert(a, r);
    const warn = r.gates.includes('warn') || !!rc || (!restricted && r.demandStatus === 'forecast' && r.id !== 'exit' && r.id !== 'material');
    const st: [string, string, string] = restricted ? ['Restricted', 'bad', ex!.why || r.failReason || 'Excluded in this scenario']
      : warn ? ['Conditional', 'warn', rc ? 'Needs re-certification: demand needs ' + rc.need + ' months, certified for ' + rc.cert : r.demandStatus === 'forecast' ? 'Demand is a forecast; verify before committing' : 'A gate passed with a warning']
      : ['Eligible', 'ok', r.unc || r.why || 'All six gates passed'];
    return { r, st, rt: rid(r.id) };
  }).sort((x, y) => ({ ok: 0, warn: 1, bad: 2 } as Record<string, number>)[x.st[1]] - ({ ok: 0, warn: 1, bad: 2 } as Record<string, number>)[y.st[1]] || y.r.net - x.r.net);
  return (
    <Panel t="Eligibility and feasible pathways" cls="tix1">
      {el.length ? <>
        <p className="note" style={{ margin: '0 0 8px' }}>Based on condition, product, ownership, policy, parts and operating constraints. Select a pathway to highlight it.</p>
        <div className="tipath">{el.map((e, i) => (
          <button key={i} className={'tipw ' + (ti.focus === e.r.plan ? 'on' : '')} onClick={() => setTi({ focus: ti.focus === e.r.plan ? null : e.r.plan })}>
            <span className="tipd" style={{ background: e.rt.color }}></span><span className="tipt"><b>{e.r.plan}</b><span className="note">{e.st[2]}</span></span><span className={'chip ' + e.st[1]}>{e.st[0]}</span>
          </button>
        ))}</div>
      </> : <div className="empty"><b>No pathways evaluated</b>{c.blocked ? c.blocked.reason : 'This asset needs evidence first.'}</div>}
    </Panel>
  );
}
function TiScatter({ rows, rec }: { rows: TiRow[]; rec: Route | null | undefined }) {
  const ti = tiView();
  if (!rows.length) return null;
  const W = 420, H = 230, L = 48, R = 14, T0 = 12, Bm = 34, dx = Math.max(...rows.map((r) => r.days)) * 1.2 || 1, ny = rows.map((r) => r.net), lo = Math.min(0, ...ny), hi = Math.max(...ny) * 1.15 || 1;
  const X = (v: number) => L + (v / dx) * (W - L - R), Y = (v: number) => H - Bm - ((v - lo) / (hi - lo || 1)) * (H - Bm - T0);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="tisc" role="img" aria-label="Net recovery against cycle time for each eligible pathway">
      {[0, 0.25, 0.5, 0.75, 1].map((t) => { const v = lo + (hi - lo) * t; return <g key={'g' + t}><line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} stroke="var(--line2)" /><text x={L - 6} y={Y(v) + 4} textAnchor="end" fontSize="10" fill="var(--muted)">{kfmt(v).replace('$', '')}</text></g>; })}
      {[0, 0.25, 0.5, 0.75, 1].map((t) => <text key={'x' + t} x={X(dx * t)} y={H - 16} textAnchor="middle" fontSize="10" fill="var(--muted)">{Math.round(dx * t)}</text>)}
      <text x={(L + W - R) / 2} y={H - 2} textAnchor="middle" fontSize="10.5" fill="var(--ink2)">Cycle time (days)</text>
      <text transform="rotate(-90)" x={-(H - Bm) / 2} y="12" textAnchor="middle" fontSize="10.5" fill="var(--ink2)">Net recovery</text>
      {rows.map((z, i) => {
        const cx = X(z.days), cy = Y(z.net), isR = sameR(z.r, rec), f = ti.focus === z.r.plan, sel = (ti.sel || []).includes(z.r.plan);
        return (
          <g key={i} style={{ cursor: 'pointer' }} onClick={() => setTi({ focus: f ? null : z.r.plan })} data-tip={z.r.plan + ' · net ' + money(z.net) + ' · ' + z.days + ' days · ' + z.prob + '% success'}>
            {(isR || f) && <circle cx={cx} cy={cy} r="12" fill="none" stroke="var(--ink)" strokeWidth="2" />}
            <circle cx={cx} cy={cy} r={sel ? 8 : 6.5} fill={rid(z.r.id).color} stroke={sel ? 'var(--ink)' : 'var(--panel)'} strokeWidth={sel ? 2 : 1.5} />
            <text x={cx + 11} y={cy - 8} fontSize="10" fill="var(--ink2)">{rid(z.r.id).short}</text>
          </g>
        );
      })}
    </svg>
  );
}
function TiP2({ c, rows }: PS) {
  const ti = tiView(), rec = c.chosen || c.recommendation, sel = ti.sel || [], mxn = Math.max(1, ...rows.map((z) => Math.abs(z.net)));
  const pickSel = (p: string, on: boolean) => {
    const s = ti.sel || [];
    if (on) { if (s.length >= 3) return toast('Compare up to three pathways. Untick one first.'); if (!s.includes(p)) setTi({ sel: [...s, p] }); }
    else setTi({ sel: s.filter((x) => x !== p) });
  };
  return (
    <Panel t="Predicted outcomes and comparison" cls="tix2">
      {rows.length ? <>
        <p className="note" style={{ margin: '0 0 8px' }}>Model-predicted outcomes for each feasible pathway{scenActive() ? <>. <b>Scenario applied.</b></> : '.'}</p>
        <div className="tw">
          <table className="t static tight tipt2">
            <thead><tr><th></th><th>Pathway</th><th className="r">Recovery value</th><th className="r">Cost</th><th>Net recovery</th><th className="r">Cycle (days)</th><th className="r">Success</th><th className="r">Useful life</th><th className="r">CO₂e avoided</th><th className="r">Fit</th></tr></thead>
            <tbody>{rows.map((z, i) => (
              <tr key={i} className={ti.focus === z.r.plan ? 'sel' : ''}>
                <td><input type="checkbox" checked={sel.includes(z.r.plan)} onChange={(e) => pickSel(z.r.plan, e.target.checked)} aria-label={'Compare ' + z.r.plan} /></td>
                <td><b>{z.r.plan}</b>{sameR(z.r, rec) && <> <span className="chip y">Recommended</span></>}</td>
                <td className="r num">{money(z.gross)}</td><td className="r num">{money(z.cost)}</td>
                <td><span className="tinet"><b className="num">{money(z.net)}</b><span className="bar"><i style={{ width: Math.max(4, (Math.abs(z.net) / mxn) * 100) + '%', background: z.net < 0 ? 'var(--bad)' : 'var(--ok)' }}></i></span></span></td>
                <td className="r num">{z.days}</td><td className="r num">{z.prob}%</td><td className="r num">{z.life}</td><td className="r num">{fmtN(z.co2)} kg</td><td className="r num"><b>{z.fit}</b></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <h4 style={{ margin: '12px 0 4px' }}>Comparison chart (net recovery vs cycle time)</h4>
        <TiScatter rows={rows} rec={rec} />
      </> : <div className="empty"><b>No predictions yet</b>{c.blocked ? c.blocked.reason : 'Evidence is needed before outcomes can be predicted.'}</div>}
    </Panel>
  );
}
export const TbNote = () => (
  <p className="note titr"><b>Tie-breaker rules.</b> When the top two pathways are within 5% or $250 (whichever is larger), compare in order: {TB_RULES.map((t, i) => `${i + 1} ${t[1]} (${t[2]})`).join(', ')}. A factor decides only when its gap is meaningful. Set by Admin (assumed).</p>
);
function TieBox({ t, rec }: { t: Tie | null; rec: Route | null | undefined }) {
  if (!t || !t.near) return null;
  const flip = !!rec && !sameR(t.preferred!.r, rec);
  return (
    <div className={'callout ' + (flip ? '' : 'info') + ' titie'} style={{ margin: '8px 0' }}>
      <b>Close call.</b> {tieText(t)}{flip && <> <b>The approved recommendation stays on net value</b> until it is re-evaluated; an Approver can override with this reason.</>}
      <ul className="titf">{t.values!.map((v) => (
        <li key={v.k}><span aria-hidden="true">{v.w ? '✓' : '–'}</span> {v.label}: {v.a} vs {v.b}{v.k === t.decidedBy ? <> <span className="chip y">decides</span></> : v.w ? null : <> <span className="note">no meaningful gap</span></>}</li>
      ))}</ul>
    </div>
  );
}
const explainOpen = () => {
  const d = document.getElementById('tiFull') as HTMLDetailsElement | null;
  if (d) d.open = true;
  scrollToId(document.getElementById('b-explain') ? 'b-explain' : 'explain');
};
function TiP3({ c, a, sr, rows }: PS) {
  const r = c.chosen || c.recommendation, ti = tiView();
  if (!r) return (
    <Panel t="Recommendation and rationale" cls="tix3">
      <div className="empty"><b>No recommendation yet</b>{c.blocked ? c.blocked.reason : 'Evidence is needed before a pathway can be recommended.'}</div>
      <a className="lnk" href="#step-5" onClick={(e) => { e.preventDefault(); scrollToId('step-5'); }}>See what happens next (step 5)</a>
    </Panel>
  );
  const others = rows.filter((z) => !sameR(z.r, r)).sort((x, y) => y.r.net - x.r.net), next = others[0], me = rows.find((z) => sameR(z.r, r)) || { ...metrics(a, r), fit: '—' as unknown as number };
  const pctUp = next && next.r.net ? Math.round(((r.net - next.r.net) / Math.abs(next.r.net)) * 100) : null, W = ti.w, top = rows.slice().sort((x, y) => y.fit - x.fit)[0];
  const drivers = r.terms.slice().sort((x, y) => Math.abs(y.amt) - Math.abs(x.amt)).slice(0, 2).map((t) => t.label).join(' and ').toLowerCase();
  const why = next ? (() => {
    const d = r.terms.map((t) => { const o = next.r.terms.find((u) => u.kind === t.kind); return { l: t.label, v: t.amt - (o ? o.amt : 0) }; }).sort((x, y) => Math.abs(y.v) - Math.abs(x.v))[0];
    return next.r.plan + ' trails by ' + money(r.net - next.r.net) + (d ? ', mostly on ' + d.l.toLowerCase() : '') + '.';
  })() : 'No other eligible pathway.';
  const exN = sr.all.filter((x) => x.ex).length;
  const cons = c.blocked ? c.blocked.reason : r.demandStatus === 'forecast' ? 'Demand is a forecast, so a haircut is included.' : exN ? exN + ' pathway(s) withheld by a gate.' : 'None for this asset.';
  const tag = (z: TiRow) => [(z.r.net > r.net ? 'Higher value' : 'Lower value') + ' · ' + (z.days < me.days ? 'Shorter cycle time' : 'Longer cycle time'), (z.prob < me.prob ? 'Higher risk' : 'Lower risk') + ' · ' + (z.cost > me.cost ? 'Lower cost' : 'Higher cost')];
  return (
    <Panel t="Recommendation and rationale" cls="tix3">
      <div className="tirec"><span className="chip ok">Recommended</span><div className="tirt">{r.plan}</div>
        <div className="tirv"><span className="note">Expected net recovery</span><b className="num">{money(r.net)}</b>
          {pctUp != null && next && <span className={pctUp >= 0 ? 'tx-ok' : 'tx-bad'}>{pctUp >= 0 ? '▲' : '▼'} {Math.abs(pctUp)}% vs next best alternative</span>}</div>
      </div>
      <p className="ink2" style={{ margin: '8px 0' }}>{r.why || 'Highest expected net contribution among eligible pathways.'} {me.prob}% success probability{me.days ? ' and about ' + me.days + ' days to complete' : ''}.</p>
      <dl className="tikv">
        <div><dt>Business objectives</dt><dd>Value ({W.net}%), time ({W.time}%), sustainability ({W.env}%), serviceability ({W.serv}%)</dd></div>
        <div><dt>Key drivers</dt><dd>{drivers || '—'}</dd></div>
        <div><dt>Why not {next ? next.r.plan : 'others'}?</dt><dd>{why}</dd></div>
        <div><dt>Binding constraints</dt><dd>{cons}</dd></div>
      </dl>
      {top && !sameR(top.r, r) && <div className="callout" style={{ margin: '8px 0' }}><b>With your objective weights</b>, {top.r.plan} ranks first (fit {top.fit} vs {rows.find((z) => sameR(z.r, r))?.fit ?? '—'}). The approved recommendation does not change until it is re-evaluated.</div>}
      <a className="lnk" href="#explain" onClick={(e) => { e.preventDefault(); explainOpen(); }}>View detailed explanation</a>
      {others.length > 0 && <>
        <h4 style={{ margin: '12px 0 6px' }}>Next best alternatives</h4>
        {others.slice(0, 2).map((z, i) => { const t = tag(z); return (
          <div key={i} className="tialt"><b className="tial-n">{i + 1}</b><span className="tialt-t"><b>{z.r.plan}</b><span className="note num">{money(z.net)} · {z.days} days · {z.prob}%</span></span><span className="tialt-g"><span className="note">{t[0]}</span><span className="note">{t[1]}</span></span></div>
        ); })}
      </>}
      <TieBox t={tieBreak(a, rows)} rec={r} /><TbNote />
      <a className="lnk" href="#step-5" onClick={(e) => { e.preventDefault(); scrollToId('step-5'); }}>Approve and hand off in step 5 →</a>
    </Panel>
  );
}
export const TiA = (p: PS) => <><TiP1 {...p} /><TiP2 {...p} /><TiP3 {...p} /></>;

// ================================================================ explain and trace (explainBlock)
const SRC_MAP: Record<string, string> = {
  purchase: 'SAP Ariba contract price · planned purchase', prep: 'MRO scope and hours · Ariba part prices · TMS lanes', service: 'Maximo failure history · FSM labour rate',
  residual: 'Valuation model v1.3', sale: 'Sales records + market', parts: 'Parts demand + BOM', lease: 'CRM pipeline', material: 'Recycler rates', fees: 'TMS lane rate card · channel fees',
  risk: 'Calibrated risk allowance', credit: 'Vendor rate card', avoid: 'Disposal cost table',
};
export function ExSrcBtn({ c, a, r, i, txt }: P & { r: Route; i: number; txt?: string }) {
  const ui = useCaseUi();
  if (i < 0) return null;
  return <button className="lnk exsrc" aria-label={'Where ' + lc(r.terms[i].label) + ' comes from'} onClick={() => openExSrc(ui, c, a, c.routes.findIndex((x) => sameR(x, r)), i)}>{txt || 'Source'}</button>;
}
export function ExplainBlock({ c, a }: P) {
  const r = c.recommendation;
  if (!r) return null;
  const t = tiView().xtab, tot = r.terms.reduce((s, x) => s + Math.abs(x.amt), 0) || 1;
  let body: ReactNode = null;
  if (t === 'why') body = <>
    <p className="ink2" style={{ margin: '0 0 10px' }}>What influenced the {money(r.net)} for <b>{r.plan}</b>. Bar length is each input's share of the total movement.</p>
    {r.terms.map((x, i) => (
      <div key={i} className="sl" style={{ gridTemplateColumns: 'minmax(160px,1.2fr) 2fr 90px' }}>
        <span>{x.label}<div className="note">{SRC_MAP[x.kind] || ''} · <ExSrcBtn c={c} a={a} r={r} i={i} /></div></span>
        <div className="bar"><i style={{ width: Math.max(3, (Math.abs(x.amt) / tot) * 100) + '%', ...(x.amt < 0 ? { background: 'var(--bad)' } : {}) }}></i></div>
        <b className={'num right ' + (x.amt < 0 ? 'neg' : '')}>{x.amt < 0 ? '−' : '+'}{money(Math.abs(x.amt)).replace('−', '')}</b>
      </div>
    ))}
  </>;
  if (t === 'assume') body = (
    <dl className="kv">
      <dt>Decision ID</dt><dd>DI-2026-{c.id.slice(3)}</dd>
      <dt>Evidence snapshot</dt><dd>{c.snapshot?.id} · {c.snapshot?.items} of {c.evidence.length} items · taken {isoT(a.snapshot_time)}</dd>
      <dt>Models</dt><dd>{[...new Set((c.predictions || []).map((p) => p.model + ' ' + p.ver))].join(', ') || '—'}</dd>
      <dt>Policy version</dt><dd>POL-3.2 (reuse, certification, criticality)</dd>
      <dt>Baseline</dt><dd>{(c.facts || []).find((f) => /Baseline/.test(f)) || 'Current practice: separate sell-or-scrap decisions by team'}</dd>
      <dt>Horizon</dt><dd>{c.horizon || '30 months'}, same for every route</dd>
      <dt>Discounting</dt><dd>8% a year on deferred receipts</dd>
      <dt>Demand</dt><dd>{r.demandStatus === 'confirmed' ? 'Confirmed' : 'Forecast opportunity (haircut applied)'}</dd>
      <dt>Expires</dt><dd>{fmtDY(addDays(asOf(), 7))}; re-evaluated if condition, demand or market evidence changes</dd>
    </dl>
  );
  if (t === 'flip') body = <>
    <p className="ink2" style={{ margin: '0 0 10px' }}>The ranking changes from <b>{r.plan}</b> to the next-best plan when any of these happen on their own:</p>
    {a.flips.length ? a.flips.map((f, i) => (
      <div key={i} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--line2)' }}>
        <span className="grow">{f.txt}</span>
        <span className={'chip ' + (f.pct == null ? 'bad' : Math.abs(f.pct) < 0.25 ? 'warn' : 'ok')}>{f.pct == null ? 'event' : (f.pct > 0 ? '+' : '−') + Math.abs(Math.round(f.pct * 100)) + '%'}</span>
      </div>
    )) : <div className="empty">No competing eligible route.</div>}
    <div className="note" style={{ marginTop: 8 }}>Larger percentages mean a sturdier recommendation. Use Scenario preview to try your own values.</div>
  </>;
  return (
    <section className="blk" id="b-explain">
      <div className="bh"><span className="bn">5</span><h2>Explain and trace</h2><Stp n={3} /><Stp n={4} /></div>
      <div className="tabs" role="tablist">
        {([['why', 'What influenced this decision'], ['assume', 'Assumptions and versions'], ['flip', 'What would flip the ranking']] as ['why' | 'assume' | 'flip', string][]).map((x) => (
          <button key={x[0]} role="tab" aria-selected={t === x[0]} onClick={() => setTi({ xtab: x[0] })}>{x[1]}</button>
        ))}
      </div>
      {body}
    </section>
  );
}
export function WhyTab({ c, a }: TabProps) {
  const x = useRows(c, a);
  return (
    <section className="tistep" id="step-3">
      <div className="tig3" id="tiA"><TiA c={c} a={a} {...x} /></div>
      <div className="tidetail" id="explain"><ExplainBlock c={c} a={a} /></div>
    </section>
  );
}

// ================================================================ evidence (evidenceBlock, evRow, specialBlock)
function EvRow({ e, c, a }: P & { e: Evidence }) {
  const ui = useCaseUi();
  const ic = ({ ready: '✓', missing: '!', partial: '~', stale: '~', conflict: '!' } as Record<string, string>)[e.state];
  return (
    <div className={'ev ' + e.state}>
      <span className="ic" aria-hidden="true">{ic}</span>
      <div><b>{e.label}{e.state !== 'ready' && <> <span className={'chip ' + (e.state === 'missing' || e.state === 'conflict' ? 'bad' : 'warn')}>{e.state}</span></>}</b><small>{e.source}{e.note ? ' · ' + e.note : ''}</small></div>
      <em>{e.state === 'missing' ? '—' : e.fresh}
        {e.state === 'missing' ? <div style={{ marginTop: 2 }}><span className="chip bad" style={{ height: 'auto', padding: '1px 8px' }}>Provenance unavailable</span></div>
          : <div><button className="btn sm ghost" style={{ height: 22, padding: '0 4px', fontSize: 11.5 }} onClick={() => openTrace(ui, c, a, e.k)}>View Data Trace</button></div>}
      </em>
    </div>
  );
}
export function EvidenceBlock({ c, a }: P) {
  const ev = c.evidence, rd = ev.filter((e) => e.state === 'ready').length;
  return (
    <section className="blk" id="b-evidence">
      <div className="bh"><span className="bn">1</span><h2>Evidence readiness</h2><Stp n={1} /><span className="sp"></span><span className={'chip ' + (rd === ev.length ? 'ok' : 'warn')}>{rd} of {ev.length} ready</span></div>
      <div className="evgrid">{ev.map((e) => <EvRow key={e.k} e={e} c={c} a={a} />)}</div>
      {c.blocked && <div className="callout bad" style={{ marginTop: 12 }}><b>Failed gate: {c.blocked.gateName}.</b> {c.blocked.reason} Missing evidence produces an exception, not an unsupported approval.</div>}
      {!c.blocked && ev.some((e) => e.state === 'stale') && <div className="callout" style={{ marginTop: 12 }}>Some inputs are stale; predictions carry the evidence date and widen their range accordingly.</div>}
    </section>
  );
}
const F22 = { font: '800 24px var(--f-display)', margin: '4px 0' };
export function SpecialBlock({ c }: { c: CaseRec }) {
  const top = c.routes.find((r) => r.hold);
  return (
    <>
      {c.kind === 'hold' && top && top.hold && (() => { const h = top.hold!; return (
        <section className="blk">
          <div className="bh"><span className="bn">3b</span><h2>Why hold beats selling today</h2><Stp n={4} /></div>
          <div className="grid g2">
            <div className="callout"><b>Headline view (misleading)</b><div className="num" style={{ fontSize: 22, fontWeight: 800, margin: '4px 0' }}>{money(h.forecast)} − {money(h.holding)} = {money(h.headline)}</div>Looks twice as good as the {money(h.sellNow)} sale today. It assumes demand always arrives and nothing decays.</div>
            <div><b>Risk-adjusted view</b>
              <table className="terms" style={{ marginTop: 6 }}><tbody>
                {top.terms.map((t, i) => <tr key={i}><td>{t.label}</td><td className={t.amt < 0 ? 'neg' : ''}>{money(t.amt)}</td></tr>)}
                <tr className="tot"><td>Risk-adjusted hold value</td><td>{money(top.net)}</td></tr>
                <tr><td>Sell now</td><td>{money(h.sellNow)}</td></tr>
                <tr><td><b>Advantage of holding</b></td><td className="pos"><b>{money(top.net - h.sellNow)}</b></td></tr>
              </tbody></table>
            </div>
          </div>
          <dl className="kv" style={{ marginTop: 12 }}><dt>Named opportunity</dt><dd>{h.opp}</dd><dt>Review date</dt><dd>{h.review} ({h.days} days)</dd><dt>If demand fails</dt><dd>Sell near {money(h.fallback)} ({money(h.fallback - h.sellNow)} vs today)</dd></dl>
        </section>
      ); })()}
      {c.kind === 'harvest' && c.routes[0]?.components && (() => { const h = c.routes[0]; return (
        <section className="blk">
          <div className="bh"><span className="bn">3b</span><h2>Selective harvest: one teardown, five outputs</h2><Stp n={4} /></div>
          <div className="panel flat tw"><table className="t static"><thead><tr><th>Output</th><th>Destination</th><th>Reference</th><th className="r">Value</th></tr></thead><tbody>
            {h.components!.map((x, i) => <tr key={i}><td>{x.n}</td><td>{x.dest}</td><td className="num">{x.ref}</td><td className="r num">{money(x.v)}</td></tr>)}
            <tr><td colSpan={3}><b>Shared teardown</b> <span className="chip ok">charged once</span></td><td className="r num neg">−$240</td></tr>
            <tr><td colSpan={3}>Logistics</td><td className="r num neg">−$90</td></tr>
            <tr><td colSpan={3}><b>Net contribution</b></td><td className="r num"><b>{money(h.net)}</b></td></tr>
          </tbody></table></div>
          <div className="note" style={{ marginTop: 6 }}>Each component is allocated to exactly one destination. The remainder goes to material recovery; disposal avoidance is counted once.</div>
        </section>
      ); })()}
      {c.kind === 'exit' && c.routes.length >= 3 && (() => { const [A, Bv, U] = c.routes; return (
        <section className="blk">
          <div className="bh"><span className="bn">3b</span><h2>Responsible exit: approved vendors only</h2><Stp n={4} /></div>
          <div className="grid g3">{[A, Bv, U].map((v, i) => (
            <div key={i} className="panel flat" style={{ padding: 12, ...(v.excluded ? { borderColor: 'var(--bad)' } : {}) }}>
              <b>{v.vendor}</b><div className="num" style={F22}>{money(v.net)}</div><div className="note">{(v.demandLabel || '').split(' · ')[1] || ''}</div>
              {v.excluded ? <span className="chip bad" style={{ marginTop: 6 }}>Ineligible: not certified</span> : i === 0 ? <span className="chip ok" style={{ marginTop: 6 }}>Saves {money(Bv.net - A.net)} vs B</span> : null}
            </div>
          ))}</div>
        </section>
      ); })()}
    </>
  );
}
export const EvidenceTab = ({ c, a }: TabProps) => <div className="tidetail"><EvidenceBlock c={c} a={a} /><SpecialBlock c={c} /></div>;

// ================================================================ how it was predicted (predictBlock, optionsBlock)
export function PredictBlock({ c }: { c: CaseRec }) {
  const ui = useCaseUi();
  const P = c.predictions;
  if (!P || !P.length) return (
    <section className="blk" id="b-predict">
      <div className="bh"><span className="bn">2</span><h2>How outcomes were predicted</h2><Stp n={3} /></div>
      <div className="empty"><b>No predictions yet</b>Predictions need condition and remaining-life evidence. {(c as { indicative?: boolean }).indicative ? '' : 'Use the request on the right to get inspection started.'}</div>
    </section>
  );
  return (
    <section className="blk" id="b-predict">
      <div className="bh"><span className="bn">2</span><h2>How outcomes were predicted</h2><Stp n={3} /><span className="sp"></span><span className="note">Every prediction carries model version, evidence date and uncertainty</span></div>
      <div className="panel flat tw"><table className="t static">
        <thead><tr><th>Source evidence</th><th>Inputs used</th><th>Model evaluated</th><th>Predicted result</th><th>Confidence</th></tr></thead>
        <tbody>{P.map((p, i) => (
          <tr key={i}><td>{p.src}</td><td>{p.inputs}</td><td>{p.model} <span className="chip line">{p.ver}</span></td><td><b>{p.result}</b><div className="note">{p.range}</div></td>
            <td>{/Reduced/.test(p.conf) ? <span className="chip warn">{p.conf}</span> : p.conf}</td></tr>
        ))}</tbody>
      </table></div>
      <div className="row note" style={{ marginTop: 10, gap: 18 }}>
        {(c.facts || []).map((f, i) => <span key={i}>{f}</span>)}<span className="grow"></span>
        <button className="btn sm" onClick={() => openSources(ui, c)}>Inspect source records</button>
        <button className="btn sm" onClick={() => openModels(ui)}>Model versions &amp; validation</button>
      </div>
    </section>
  );
}
function RouteDetail({ r }: { r: Route }) {
  return (
    <>
      <div className="gstrip" style={{ marginBottom: 14 }}>{gates().map((g, i) => (
        <div key={g} className={'gcell ' + (r.gates[i] === 'pass' ? 'pass' : r.gates[i] === 'fail' ? 'fail' : 'skip')}>
          <b>{r.gates[i] === 'pass' ? '✓' : r.gates[i] === 'fail' ? '✕' : '–'} {g}</b>
          <p>{(r.gateNotes || [])[i] || (r.gates[i] === 'pass' ? 'Passed' : r.gates[i] === 'fail' ? r.failReason : 'Not reached')}</p>
        </div>
      ))}</div>
      <table className="terms"><tbody>
        {r.terms.map((t, i) => <tr key={i}><td>{t.label}</td><td className={t.amt < 0 ? 'neg' : ''}>{t.amt < 0 ? '−' : t.amt > 0 ? '+' : ''}{money(Math.abs(t.amt)).replace('−', '')}</td></tr>)}
        <tr className="tot"><td>Expected net contribution</td><td>{money(r.net)}</td></tr>
      </tbody></table>
      {r.refurbDelta != null && <div className="note" style={{ marginTop: 8 }}>Refurbishment {r.refurbDelta >= 0 ? 'adds' : 'subtracts'} {money(Math.abs(r.refurbDelta))} over the as-is option{r.refurbDelta < 0 ? ' — not justified' : ''} before delay and failure risk.</div>}
    </>
  );
}
export function OptionsBlock({ c, sr }: { c: CaseRec; sr: ScenRoutes }) {
  if (!c.routes.length) return (
    <section className="blk" id="b-options">
      <div className="bh"><span className="bn">3</span><h2>Options evaluated against demand</h2><Stp n={4} /></div>
      <div className="empty"><b>No routes evaluated</b>{c.blocked ? c.blocked.reason : 'This case needs evidence first.'}{c.facts && c.facts[0] && <div className="note" style={{ marginTop: 6 }}>{c.facts[0]}</div>}</div>
    </section>
  );
  const ti = tiView(), act = scenActive(), live = c.routes.filter((r) => !r.excluded), lo = Math.min(0, ...live.map((r) => r.p10)), hi = Math.max(...live.map((r) => r.p90));
  const ex = sr.all.filter((x) => x.ex), G = gates();
  const toggle = (plan: string) => setTi({ expand: { ...ti.expand, [c.id + plan]: !ti.expand[c.id + plan] } });
  return (
    <section className="blk" id="b-options">
      <div className="bh"><span className="bn">3</span><h2>Options evaluated against demand</h2><Stp n={4} /><span className="sp"></span><span className="note">{c.horizon || '30-month horizon'} · same horizon and baseline for every route</span></div>
      {act && <div className="callout" style={{ marginBottom: 10 }}><b>Scenario preview.</b> Ranking shown under your adjusted assumptions; the approved recommendation does not change. <button className="btn sm" style={{ marginLeft: 8 }} onClick={resetScen}>Reset</button></div>}
      <div className="panel flat tw"><table className="t tight">
        <thead><tr><th>Rank / plan</th><th>Demand matched</th><th>Expected net contribution</th><th>Uncertainty and rationale</th><th>Gates</th></tr></thead>
        <tbody>{sr.el.map((x) => {
          const r = x.r, open = !!ti.expand[c.id + r.plan];
          return [
            <tr key={r.plan} tabIndex={0} className={x.rank === 1 ? 'sel' : ''} aria-expanded={open} onClick={() => toggle(r.plan)} onKeyDown={(e) => e.key === 'Enter' && toggle(r.plan)}>
              <td style={{ minWidth: 150 }}>
                <span className="bn" style={{ ...(x.rank === 1 ? {} : { background: 'var(--panel3)', color: 'var(--ink)' }), width: 22, height: 22, display: 'inline-grid', marginRight: 8, verticalAlign: 'top' }}>{x.rank}</span>
                <span style={{ display: 'inline-block', maxWidth: 150, verticalAlign: 'top' }}><b>{r.plan}</b>{r.variant === 'greedy' && <> <span className="chip warn">Pool conflict</span></>}</span>
              </td>
              <td style={{ minWidth: 120 }}>{r.demandLabel}<div className="note">{r.id === 'exit' ? 'Approved destination' : r.demandStatus === 'confirmed' ? 'Confirmed demand' : 'Forecast opportunity'}</div></td>
              <td style={{ minWidth: 130 }}><b className="num" style={{ fontSize: 16 }}>{money(x.sn)}</b>{act && x.sn !== r.net && <> <span className="note">base {money(r.net)}</span></>}
                <RangeBar p10={r.p10} p50={r.net} p90={r.p90} lo={lo} hi={hi} /><div className="note num">{money(r.p10)} – {money(r.p90)}</div></td>
              <td style={{ minWidth: 140 }}><b style={{ fontWeight: 600 }}>{r.unc}</b><div className="note">{r.why}</div></td>
              <td><div className="gates" data-tip={G.map((g, i) => g + ': ' + r.gates[i]).join(' · ')}>{r.gates.map((g, i) => <i key={i} className={'gate ' + (g === 'pass' ? '' : g)}></i>)}</div></td>
            </tr>,
            open ? <tr key={r.plan + '-x'}><td colSpan={5} className="exp"><RouteDetail r={r} /></td></tr> : null,
          ];
        })}</tbody>
      </table></div>
      <div className="note" style={{ marginTop: 6 }}>Select a row for the six eligibility gates and cost build-up. Gates, left to right: {G.join(' · ')}.</div>
      {ex.length > 0 && <>
        <h4 style={{ margin: '16px 0 6px' }}>Excluded routes <span className="note">({ex.length}) — a high price cannot compensate for a failed gate</span></h4>
        <div className="panel flat tw"><table className="t static"><thead><tr><th>Route</th><th>Failed gate</th><th>Why</th></tr></thead><tbody>
          {ex.map((x, i) => <tr key={i}><td><b>{x.r.plan}</b></td><td><span className="chip bad">{(x.r.failGate ?? -1) >= 0 ? G[x.r.failGate!] : 'Demand fit'}</span></td><td>{x.r.failReason || 'Confirmed demand cancelled in this scenario'}</td></tr>)}
        </tbody></table></div>
      </>}
    </section>
  );
}
export function PredictedTab({ c }: TabProps) {
  return <div className="tidetail"><PredictBlock c={c} /><OptionsBlock c={c} sr={scenRoutes(c)} /></div>;
}

// ================================================================ what-if (tiP4, tiResult, tiObj, tiMulti)
export function TiResult({ c, sr }: { c: CaseRec; a?: CaseAnalysis; sr: ScenRoutes }) {
  const r = c.chosen || c.recommendation;
  if (!c.routes.length || !r) return <div className="tiwi"><div className="empty"><b>No pathways to compare</b>{c.blocked ? c.blocked.reason : 'Evidence is needed first.'}</div></div>;
  const x = sr.all.find((y) => sameR(y.r, r)), out = !!(x && x.ex), bn = r.net, sn = out ? 0 : x ? x.sn : bn, d = sn - bn, dp = bn ? Math.round((d / Math.abs(bn)) * 100) : 0;
  const ar = d > 0 ? '▲' : d < 0 ? '▼' : '', cls = d > 0 ? 'tx-ok' : d < 0 ? 'tx-bad' : 'note', top = sr.el[0], ch = scenChanged();
  const sent = !top ? 'No pathway stays eligible under these assumptions.' : sameR(top.r, r) ? `Under these assumptions ${r.plan} still ranks first.` : `${top.r.plan} would now rank first by ${money(top.sn - (out ? 0 : sn))}.`;
  return (
    <section className="tiwi" data-dir={d > 0 ? 'up' : d < 0 ? 'down' : 'flat'} aria-label="What-if result">
      <div className="tiwih"><b>What-if result</b><span className="note">{r.plan}{out ? ' · not eligible in this scenario' : ''}</span></div>
      <div className="tiwig">
        <div><span className="note">Base net</span><b className="num" id="wiBase">{money(bn)}</b></div>
        <div><span className="note">Scenario net</span><b className="num" id="wiSim">{out ? 'Not eligible' : money(sn)}</b></div>
        <div><span className="note">Δ $</span><b className={'num ' + cls} id="wiD">{d === 0 ? 'No change' : ar + ' ' + (d > 0 ? '+' : '−') + money(Math.abs(d))}</b></div>
        <div><span className="note">Δ %</span><b className={'num ' + cls} id="wiP">{d === 0 ? 'No change' : ar + ' ' + (dp > 0 ? '+' : dp < 0 ? '−' : '±') + Math.abs(dp) + '%'}</b></div>
      </div>
      <div className="tiwic"><span className="note">Changed from base:</span> {ch.length ? ch.map((t) => <span key={t}><span className="chip line">{t}</span> </span>) : <span className="note">nothing yet (base assumptions)</span>}</div>
      <p className="tiwis" aria-live="polite">{sent}</p>
    </section>
  );
}
const TI_PRESETS: [string, string, () => boolean][] = [
  ['demand', 'Demand cancelled', () => !!scen().demandOff], ['parts', 'Parts cost +30%', () => scen().cost === 1.3], ['resale', 'Resale price −20%', () => scen().market === 0.8],
  ['cert', 'Certification shorter than demand', () => !!scen().certShort], ['ecm', 'Critical part unavailable', () => !!scen().partUnavail], ['newonly', 'Customer requires a new unit', () => !!scen().newOnly],
];
function preset(k: string) {
  const s = scen();
  if (k === 'demand') setScen({ demandOff: !s.demandOff });
  if (k === 'parts') setScen({ cost: s.cost === 1.3 ? 1 : 1.3 });
  if (k === 'resale') setScen({ market: s.market === 0.8 ? 1 : 0.8 });
  if (k === 'cert') setScen({ certShort: !s.certShort });
  if (k === 'ecm') setScen({ partUnavail: !s.partUnavail });
  if (k === 'newonly') setScen({ newOnly: !s.newOnly });
}
/** Save the assumptions in view as a scenario of the case (ACT.tiSave). */
export async function saveScenario(c: CaseRec, a: CaseAnalysis) {
  if (!can('scenario')) return toast('Your role cannot save scenarios.');
  const sr = scenRoutes(c), s = scen();
  const parts = ([['purchase', 'purchase price'], ['cost', 'prep and fees'], ['service', 'service'], ['market', 'market']] as [ScenKey, string][]).filter((x) => s[x[0]] !== 1).map((x) => x[1] + ' ' + scenAdj(s[x[0]]));
  const n = a.view.scenarios.length;
  const r = await invoke('scenario.save', {
    case_id: c.id, name: 'Scenario ' + (n + 1) + (parts.length ? ': ' + parts.join(', ') : ': base'),
    top: sr.el[0] ? sr.el[0].r.plan + ' · ' + money(sr.el[0].sn) : 'No eligible pathway', scen: { ...s }, w: { ...tiView().w },
  });
  if (!r.ok) return toast(r.error.message, 4200);
  toast('Scenario saved for ' + c.id + '.');
}
const TI_OBJ: [keyof ReturnType<typeof tiView>['w'], string][] = [['net', 'Maximize net recovery'], ['time', 'Minimize turnaround time'], ['env', 'Minimize environmental impact'], ['serv', 'Preserve serviceability (redeploy)']];
function TiObj() {
  const w = tiView().w;
  return (
    <Panel t={<>Business objectives <span className="note">(for the Fit score)</span></>} cls="tiobj">
      {TI_OBJ.map(([k, l]) => (
        <div key={k} className="sl"><label htmlFor={'tw-' + k}>{l}</label>
          <input id={'tw-' + k} type="range" min={0} max={100} step={5} value={w[k]} onChange={(e) => setTi({ w: { ...w, [k]: +e.target.value } })} />
          <b className="num" id={'twv-' + k}>{w[k]}%</b></div>
      ))}
      <p className="note" style={{ margin: '6px 0 0' }}>The weights produce the Fit score, a second opinion next to net value. They do not change the approved recommendation.</p>
    </Panel>
  );
}
export function TiMulti({ c, a, rows }: PS) {
  const ti = tiView();
  if (rows.length < 2) return <Panel t="Compare pathways" cls="ticmpp"><div className="empty"><b>Only one eligible pathway</b>Nothing to compare under these assumptions.</div></Panel>;
  const rec = c.chosen || c.recommendation, t = tieBreak(a, rows), sel = (ti.sel || []).map((p) => rows.find((z) => z.r.plan === p)).filter(Boolean) as TiRow[];
  const pick = sel.length >= 2 ? sel : rows.slice(0, 3), ranked = rows.slice();
  if (t && t.near && t.preferred === t.b) { ranked[0] = t.b; ranked[1] = t.a; }
  const R = a.rul, life = (z: TiRow) => (R && ['redeploy', 'resale', 'relase'].includes(z.r.id) ? R.estLow + '–' + R.estHigh + ' mo' : '—'), cf = rec ? confidence(a, rec) : 'Medium', open = cf === 'Low' || !!(t && t.near);
  const cols: [string, (z: TiRow) => string, string][] = [['Cycle time', (z) => z.days + ' days', 'cycle'], ['RUL', life, 'rul'], ['Success', (z) => z.prob + '%', 'risk'], ['Demand', (z) => (z.r.demandStatus === 'confirmed' ? 'Confirmed' : 'Forecast'), 'demand'], ['CO₂e avoided', (z) => fmtN(z.co2) + ' kg', 'co2']];
  const vis = cols.filter((col) => !ti.diffOnly || new Set(pick.map(col[1])).size > 1);
  const why = t && t.near ? tieText(t) : `${ranked[0].r.plan} ranks first on net value, ahead by ${money(ranked[0].net - ranked[1].net)}.`;
  return (
    <TiDetails open={open} keyOpen={c.id + open}>
      <summary className="ph"><h3>Compare the top {pick.length} pathways</h3>{open ? <span className="chip warn">{t && t.near ? 'Close call' : 'Low confidence'}: compare before approving</span> : <span className="note">Select to expand</span>}</summary>
      <div className="pb">
        <label className="tog" style={{ margin: '0 0 8px' }}><input type="checkbox" checked={ti.diffOnly} onChange={(e) => setTi({ diffOnly: e.target.checked })} /> Show differences only</label>
        <div className="tw"><table className="t static tight" id="tiMulti">
          <thead><tr><th>Pathway</th><th className="r">Base net</th><th className="r">Scenario net</th><th className="r">Δ</th>{vis.map((v) => <th key={v[0]} className="r">{v[0]}</th>)}<th className="r">Rank</th></tr></thead>
          <tbody>{pick.map((z) => { const d = z.net - z.r.net; return (
            <tr key={z.r.plan} data-plan={z.r.plan}>
              <td><b>{z.r.plan}</b>{sameR(z.r, rec) && <> <span className="chip y">Recommended</span></>}</td>
              <td className="r num">{money(z.r.net)}</td><td className="r num"><b>{money(z.net)}</b></td>
              <td className={'r num ' + (d > 0 ? 'tx-ok' : d < 0 ? 'tx-bad' : '')}>{d === 0 ? '—' : (d > 0 ? '▲ +' : '▼ −') + money(Math.abs(d))}</td>
              {vis.map((v) => { const dec = t && t.near && t.decidedBy === v[2] && (z === t.a || z === t.b); return <td key={v[0]} className="r num">{dec ? <><b>{v[1](z)}</b> <span className="chip y">decides</span></> : v[1](z)}</td>; })}
              <td className="r num"><b>{ranked.indexOf(z) + 1}</b></td>
            </tr>
          ); })}</tbody>
        </table></div>
        <p className="ink2" style={{ margin: '8px 0 0' }}>{why}</p><TbNote />
      </div>
    </TiDetails>
  );
}
function TiDetails({ open, keyOpen, children }: { open: boolean; keyOpen: string; children: ReactNode }) {
  const [o, setO] = useState<{ k: string; v: boolean }>({ k: keyOpen, v: open });
  const v = o.k === keyOpen ? o.v : open;
  return <details className="panel ticmp" id="tiCmp" open={v} onToggle={(e) => { const n = (e.target as HTMLDetailsElement).open; if (n !== v) setO({ k: keyOpen, v: n }); }}>{children}</details>;
}
export function TiP4({ c, a, sr, rows }: PS) {
  const s = scen(), ti = tiView(), sv = a.view.scenarios;
  const sl = (k: ScenKey, l: string, tip?: string) => (
    <div className="sl" data-tip={tip}><label htmlFor={'sc-' + k}>{l}</label>
      <input id={'sc-' + k} type="range" min={50} max={150} step={5} value={Math.round(s[k] * 100)} onChange={(e) => setScen({ [k]: +e.target.value / 100 })} />
      <b className="num" id={'scv-' + k}>{scenAdj(s[k])}</b></div>
  );
  const load = (id: string) => {
    const x = sv.find((y) => y.id === id);
    if (!x) return;
    resetScen();
    setScen({ ...x.scen });
    setTi({ w: { ...x.w } });
    toast(x.name + ' loaded.');
  };
  const del = async (id: string) => {
    const r = await invoke('scenario.delete', { case_id: c.id, id });
    if (!r.ok) toast(r.error.message, 4200);
  };
  return (
    <>
      <div id="tiImpact"><TiResult c={c} sr={sr} /></div>
      <div className="tig2">
        <Panel t="Assumptions and edge cases" cls="tix4">
          <p className="note" style={{ margin: '0 0 8px' }}>Adjust the assumptions to see how the ranking would change. The approved recommendation stays as it is until re-evaluated.{!can('scenario') && <> <b>Preview only:</b> saving scenarios belongs to the Planner and Approver.</>}</p>
          <div className="tisl">{sl('purchase', 'Avoided purchase price')}{sl('cost', 'Preparation, parts and fees')}{sl('service', 'Service exposure')}{sl('market', 'Resale price', 'Also scales lease income')}</div>
          <label className="tog" style={{ margin: '4px 0 8px' }}><input type="checkbox" checked={!!s.demandOff} onChange={(e) => setScen({ demandOff: e.target.checked })} /> Confirmed internal demand is cancelled</label>
          <div className="fld" style={{ margin: '6px 0' }}>
            <label htmlFor="ti-apply">Apply to</label>
            <select id="ti-apply" className="sel" value={ti.apply} onChange={(e) => setTi({ apply: e.target.value })}>
              <option value="">All pathways</option>{rows.map((z) => <option key={z.r.plan} value={z.r.plan}>{z.r.plan}</option>)}
            </select>
            <div className="hint">Stress one pathway on its own; the others stay at base.</div>
          </div>
          <div className="tipre" role="group" aria-label="Edge cases"><span className="note">Edge cases</span>{TI_PRESETS.map((p) => <button key={p[0]} className="btn sm" aria-pressed={p[2]()} onClick={() => preset(p[0])}>{p[1]}</button>)}</div>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn" onClick={resetScen}>Reset to base</button>
            <button className="btn" onClick={() => saveScenario(c, a)}>Save scenario</button>
            <button className="btn pri" disabled={!c.routes.length} onClick={() => toast(sr.el[0] ? 'Re-ranked. Top pathway: ' + sr.el[0].r.plan + '.' : 'No eligible pathway under these assumptions.')}>Recalculate and optimise</button>
          </div>
          {sv.length > 0 && <>
            <h4 style={{ margin: '12px 0 6px' }}>Saved scenarios</h4>
            {sv.map((x) => (
              <div key={x.id} className="asrow"><span><b>{x.name}</b><div className="note">{x.top}</div></span>
                <span className="tacts" style={{ display: 'inline-flex' }}><button className="tbtn" onClick={() => load(x.id)}>Load</button><button className="tbtn dng" onClick={() => del(x.id)}>Delete</button></span></div>
            ))}
          </>}
        </Panel>
        <TiObj />
      </div>
      <div id="tiCmpW"><TiMulti c={c} a={a} sr={sr} rows={rows} /></div>
    </>
  );
}
export function WhatIfTab({ c, a }: TabProps) {
  const x = useRows(c, a);
  return <section className="tistep" id="step-4"><TiP4 c={c} a={a} {...x} /></section>;
}

// ================================================================ demand (asDemand)
export function MatchedDemand({ c, a }: P) {
  const d = c.demand || {}, M = a.demand, R = a.rul, rows: ReactNode[] = [];
  const row = (l: string, v: string, st: string, t: string, n: ReactNode) => (
    <div key={l} className="asrow"><span><b>{l}</b><div className="note">{n}</div></span><span className="right"><b className="mono">{v}</b> <span className={'chip ' + t}>{st}</span></span></div>
  );
  if (M && M.order) rows.push(row('Customer contract demand', M.order + ' · ' + c.owner + ', ' + (M.site || '—'), M.confirmed ? 'Confirmed' : 'Forecast', M.confirmed ? 'ok' : 'warn',
    `Replacement under ${c.owner}'s contract: line ${M.line} in IBM Sterling OMS, ship to ${locName(a, M.shipTo)}, need-by ${M.needBy ? fmtDY(M.needBy) : ''}. It accepts a certified refurbished unit; orders that require a new unit are never matched.`));
  if (M && M.order && R) {
    const ok = R.certMonths >= M.horizonMonths;
    rows.push(row('Certified life needed', M.horizonMonths + ' months needed · ' + R.certMonths + ' certified', ok ? 'Covered' : 'Re-certify', ok ? 'ok' : 'warn', 'The contract needs this much life; the certified period comes from QMS (' + R.certRef + '). Redeploy is subject to it.'));
  }
  if (d.lease) rows.push(row('Re-lease opportunity', d.lease, 'Forecast', 'warn', 'Opportunity in CRM and lease management, where a contract is likely to be extended'));
  if (d.parts) rows.push(row('Internal parts demand', 'Open requests', 'Forecast', 'warn', 'Parts requests from repair work orders'));
  if (!rows.length) return <div className="empty"><b>No contract demand matched</b>Only external market routes apply.</div>;
  return <>{rows}<p className="note" style={{ margin: '6px 0 0' }}>Matched by Circularity from orders, contracts and opportunities in ERP and CRM. The routes that use this demand are priced in step 3.</p></>;
}
export const DemandTab = ({ c, a }: TabProps) => <Panel t="Matched demand" badge={<ProvB k="rul" sys="Demand matching" />}><MatchedDemand c={c} a={a} /></Panel>;

// ================================================================ compare modal (ACT.tiCompare)
export function compareBody(c: CaseRec, rows: TiRow[], sel: string[] | null): ReactNode | null {
  const pick = (sel || []).map((p) => rows.find((z) => z.r.plan === p)).filter(Boolean) as TiRow[];
  if (pick.length < 2) return null;
  const rec = c.chosen || c.recommendation;
  const best = (k: keyof TiRow, dir: number) => pick.reduce((x, y) => (dir * ((y[k] as number) - (x[k] as number)) > 0 ? y : x), pick[0]);
  const rowsd: [string, keyof TiRow, (v: number) => ReactNode, number][] = [
    ['Net recovery', 'net', money, 1], ['Recovery value', 'gross', money, 1], ['Treatment cost', 'cost', money, 1], ['Cycle time (days)', 'days', (v) => v, -1],
    ['Success probability', 'prob', (v) => v + '%', 1], ['CO₂e avoided', 'co2', (v) => fmtN(v) + ' kg', 1], ['Objective fit', 'fit', (v) => v, 1],
  ];
  return (
    <>
      <div className="tw"><table className="t static tight">
        <thead><tr><th></th>{pick.map((z) => <th key={z.r.plan}>{z.r.plan}{sameR(z.r, rec) && <> <span className="chip y">Recommended</span></>}</th>)}</tr></thead>
        <tbody>
          {rowsd.map((r) => { const b = best(r[1], r[3]); return <tr key={r[0]}><td className="note">{r[0]}</td>{pick.map((z) => <td key={z.r.plan} className={z === b ? 'tx-ok' : ''}><b>{r[2](z[r[1]] as number)}</b></td>)}</tr>; })}
          <tr><td className="note">Gates passed</td>{pick.map((z) => <td key={z.r.plan}>{z.r.gates.filter((g) => g === 'pass').length} of 6</td>)}</tr>
        </tbody>
      </table></div>
      <p className="note" style={{ marginTop: 8 }}>Green marks the best value in each row. Assumptions follow the scenario sliders on the page.</p>
    </>
  );
}
