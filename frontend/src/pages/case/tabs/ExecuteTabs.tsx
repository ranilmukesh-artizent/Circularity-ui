/**
 * The detail tabs of stages 7 to 10 and the hand-off blocks Full analysis reuses (bestCard, execBlock, tiHandoff,
 * tiReconcile, exMoveHTML, exWhatIfHTML, stPlanTl, stDelivery, stDocsTab, stCarried, stLines).
 */
import { Fragment, type ReactNode } from 'react';
import { actionCatalog } from '../../../api/actions';
import {
  approverRole, defaultSpend, exNum, fixedAssetLine, exTs, fmtD, fmtDY, inr, moveDay, refList, when,
  type CaseAnalysis, type CaseRec, type OutcomeLine, type ScenRoutes,
} from '../../../api/case';
import { money } from '../../../api/format';
import { can, canPage } from '../../../api/session';
import { Icon } from '../../../components/Icon';
import { openExSrc, openPayload, openRaw } from '../CaseDrawers';
import { Timeline } from '../../../components/kit/Timeline';
import { VendorLogo } from '../../../components/kit/VendorLogo';
import { AfBadge, CasePanel, Doc, ExClockChip, Kv, Pva, Stp, Tag, locOf } from '../CaseBlocks';
import { approveGuarded, caseActions, declineGuarded } from '../caseActions';
import { useCaseUi } from '../CaseContext';
import type { TabProps } from './index';

const routeOf = (c: CaseRec) => c.chosen || c.recommendation;
const routeIndex = (c: CaseRec) => { const r = routeOf(c); return r ? c.routes.findIndex((x) => x.id === r.id && x.plan === r.plan) : -1; };
const uniq = <T,>(a: T[]) => [...new Set(a)];

// ---------- the decision card (bestCard) ----------
export function BestCard({ c, a }: { c: CaseRec; a: CaseAnalysis; sr?: ScenRoutes }) {
  const ui = useCaseUi();
  if (c.blocked && !c.recommendation) {
    const req = c.requested, isId = c.blocked.action === 'Resolve identity';
    return (
      <div className="best blocked">
        <span className="chip bad">{c.blocked.gateName} gate · exception</span>
        <div className="act" style={{ marginTop: 10 }}>{c.assessment === 'Pending' ? 'Inspection required' : 'Technical assessment required'}</div>
        <p className="why">{c.blocked.reason}</p>
        <div className="meta"><div><span>Value ranking</span>Withheld</div><div><span>Owner of next step</span>{c.blocked.owner}</div></div>
        {req ? (
          <>
            <div className="callout ok" style={{ marginBottom: 10 }}><b>Requested.</b> {c.blocked.action} · {req.ref} sent to {c.blocked.owner}.</div>
            {can('assess')
              ? <><button className="btn pri" style={{ width: '100%' }} onClick={() => caseActions.recordResult(c.id)}>Record assessment result</button><p className="note" style={{ margin: '6px 0 0' }}>Records the result from the inspection system.</p></>
              : <p className="note" style={{ margin: 0 }}>Waiting for Engineering to record the result.</p>}
          </>
        ) : isId ? (
          canPage('integration', 'conflicts') ? <a className="btn pri" style={{ width: '100%' }} href="#/integration/conflicts">Open conflict queue</a>
            : <p className="note" style={{ margin: 0 }}>The data owner resolves this identity conflict in the conflict queue.</p>
        ) : can('request') ? <button className="btn pri" style={{ width: '100%' }} onClick={() => caseActions.requestEvidence(c.id)}>{c.blocked.action}</button>
          : <p className="note" style={{ margin: 0 }}>A Planner, Approver or Engineer requests the missing evidence.</p>}
        <p className="note" style={{ margin: '10px 0 0' }}>No approval is possible until the gate passes. Agents cannot waive it.</p>
      </div>
    );
  }
  const r = routeOf(c);
  if (!r) return <div className="best blocked"><span className="chip bad">No eligible route</span><div className="act" style={{ marginTop: 10 }}>Human review required</div><p className="why">Every route failed a gate. Send to engineering and policy owners.</p></div>;
  const steps = a.view.steps, isHold = r.id === 'hold', st = c.stage;
  const title = c.id === 'RT-1048' ? 'Redeploy RT-1048 to Customer A (Site 3)' : isHold ? `Hold ${c.id} until 14 Nov 2026` : r.variant === 'harvest' ? `Selectively harvest ${c.id}` : r.id === 'exit' ? `Exit ${c.id} via ${r.vendor}` : r.plan;
  const sub = c.submitted ? <div className="callout" style={{ marginBottom: 10 }}><b>Submitted for review</b> by {c.submitted.by} · {fmtD(c.submitted.at)}</div> : null;
  let actions: ReactNode = null;
  if (st === 'awaiting_approval') {
    if (can('approve')) actions = <>{sub}
      <div className="row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
        <button className="btn pri lg" onClick={() => approveGuarded(c.id, ui)}><Icon name="check" /> {isHold ? 'Approve hold' : r.poolNet ? 'Approve allocation' : 'Approve ' + (r.id === 'redeploy' ? 'redeployment' : 'recommendation')}</button>
        <div className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
          <button className="btn" style={{ flex: 1 }} data-tip="Choose another route with a reason" onClick={() => approveGuarded(c.id, ui, 'review')}>Override</button>
          <button className="btn" style={{ flex: 1 }} data-tip="Send it back for re-evaluation with a reason" onClick={() => declineGuarded(c.id, ui)}>Decline</button>
        </div>
      </div></>;
    else if (can('submit')) actions = c.submitted ? <>{sub}<p className="note" style={{ margin: 0 }}>Waiting for an Approver to approve, override or decline it.</p></>
      : <><button className="btn pri lg" style={{ width: '100%' }} onClick={() => caseActions.submit(c.id)}>Submit for review</button><p className="note" style={{ margin: '8px 0 0' }}>An Approver approves, overrides or declines it.</p></>;
    else actions = <>{sub}<p className="note" style={{ margin: 0 }}>Waiting for an Approver to approve, override or decline it.</p></>;
  } else if (st === 'reeval') {
    actions = can('reeval') ? <button className="btn pri" style={{ width: '100%' }} onClick={() => caseActions.reevaluate(c.id)}>Run re-evaluation</button> : <p className="note" style={{ margin: 0 }}>A Planner or Approver re-runs the evaluation.</p>;
  } else if (c.approval) {
    actions = <>
      <div className="callout ok"><b>{c.approval.ref}</b><br />{c.override ? 'Override approved' : 'Approved'} by {c.approval.by} · {fmtD(c.approval.at)}<br /><span className="note">{c.approval.rationale}</span></div>
      <div className="row" style={{ marginTop: 10 }}><button className="btn" onClick={() => openPayload(ui, c, a)}>Review work instructions</button></div>
    </>;
  }
  const flip = a.flips[0];
  return (
    <div className={'best ' + (isHold ? 'hold-b' : '')}>
      <div className="row between"><span className="chip y">Best next action</span><Stp n={4} /></div>
      <div className="act" style={{ marginTop: 10 }}>{title}</div>
      <div className="big num">{money(r.net)}</div>
      <div className="note">Expected net contribution · P10–P90 {money(r.p10)}–{money(r.p90)}</div>
      <p className="why">{r.why || 'Highest expected net contribution among eligible plans.'}{r.demandStatus !== 'confirmed' ? ' Demand is a forecast, so a haircut is included.' : ''}</p>
      <div className="meta">
        <div><span>Eligibility</span>{r.gates.every((g) => g === 'pass') ? 'All six gates passed' : 'Review gates'}</div>
        <div><span>Timing</span>{c.timing || 'Act now'}</div>
        <div><span>Ranking</span>{flip ? `Flips if ${flip.txt.toLowerCase()}` : 'Only eligible route'}</div>
        <div><span>Spend authority</span>{money(defaultSpend(c, r))}</div>
      </div>
      {actions}
      <div style={{ marginTop: 12 }}>
        <div className="chain">
          <b>{st === 'awaiting_approval' ? 'Awaiting approval' : st === 'reeval' ? 'On hold: re-evaluate' : st === 'closed' ? 'Closed' : 'Approved'}</b>
          {steps.map((s, i) => <Fragment key={i}><span>→</span><span style={s.state === 'done' ? { color: 'var(--ok)', fontWeight: 600 } : undefined}>{s.label}</span></Fragment>)}
        </div>
      </div>
    </div>
  );
}

// ---------- the enterprise hand-off (execBlock) ----------
function HandoffLegend() {
  const rows = refList('HANDOFF_MODEL');
  return (
    <div className="tw" style={{ marginTop: 10 }}>
      <table className="t static">
        <thead><tr><th>Decision</th><th>Instruction goes to</th><th>What that system does</th></tr></thead>
        <tbody>{rows.map((h) => <tr key={h[0]}><td><b>{h[0]}</b></td><td>{h[1]}</td><td className="note">{h[2]}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
export function ExecBlock({ c, a }: { c: CaseRec; a: CaseAnalysis }) {
  const ui = useCaseUi();
  const r = routeOf(c);
  if (!r) return null;
  const steps = a.view.steps, started = !!c.exec, done = steps.filter((s) => s.state === 'done').length;
  const dim = (s: { state: string }) => s.state === 'todo' || !started;
  return (
    <div className="panel" id="tiHandoff" style={{ marginTop: 16 }}>
      <div className="ph"><h3>Enterprise handoff</h3><span className="sp"></span>{[6, 7, 8, 9].map((n) => <Stp key={n} n={n} short />)}</div>
      <div className="pb">
        {!started && <div className="note" style={{ marginBottom: 8 }}>Starts after approval. Circularity sends the approved instruction; the target system carries out the work and reports back.</div>}
        {steps.map((s, i) => (
          <div key={i} className={'ev ' + (s.state === 'done' ? '' : s.state === 'active' ? 'partial' : 'missing')} id={'tiHo' + (i + 1)} style={dim(s) ? { opacity: 0.62 } : undefined}>
            <span className="ic" aria-hidden="true" style={dim(s) ? { background: 'var(--panel3)', color: 'var(--ink)' } : undefined}>{s.state === 'done' ? '✓' : i + 1}</span>
            <div>
              <b>{s.label} <span className={'chip ' + (!started || s.state === 'todo' ? 'line' : s.state === 'active' ? 'warn' : 'ok')}>{!started || s.state === 'todo' ? 'Not sent' : s.state === 'active' ? 'Sent · awaiting acknowledgement' : i === steps.length - 1 ? 'Done' : 'Acknowledged'}</span></b>
              <small>
                To <b>{s.app}</b> <span className="note">{s.sys}</span>
                {s.ack
                  ? <> · <span className="hoRef">{s.doc[1]} <span className="mono hoN">{s.ack.ref}</span></span> returned by {s.ack.by}{s.note ? ` · ${s.note}` : ''}</>
                  : <> · {s.doc[1]} <span className="mono">{s.doc_ref ?? s.doc[0] + '-…'}</span> to be created · {s.owner}</>}
              </small>
            </div>
            <em>{s.ack ? fmtD(s.ack.at) : ''}</em>
          </div>
        ))}
        {started && (
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn sm" disabled={done >= steps.length} onClick={() => caseActions.advance(c.id)}>Check for acknowledgement</button>
            <button className="btn sm" onClick={() => caseActions.resend(c.id)}>Resend instruction</button>
            <button className="btn sm ghost" onClick={() => openPayload(ui, c, a)}>View payload</button>
          </div>
        )}
        <div className="note" style={{ marginTop: 10 }}>Circularity sends the approved instruction. {uniq(steps.map((s) => s.sys.split(' · ')[0])).filter((x) => x !== 'Circularity' && x !== 'Planning').join(' / ')} carries out the work and reports back; those systems stay the record for orders, stock and repairs.</div>
        <HandoffLegend />
        {c.stage === 'closed' && (
          <div className={'callout ' + (c.outcome ? 'ok' : '')} style={{ marginTop: 12 }}>
            {c.outcome
              ? <><b>Outcome confirmed.</b> Predicted {money(r.net)} · actual {money(c.outcome.net)} · variance {money(c.outcome.net - r.net)}{c.outcome.order ? ' against ' + c.outcome.order : ''}. Linked to {c.exec?.decisionId} for learning. <a className="lnk" href={'#/product/' + c.id + '/stage/10'}>Line by line (step 10)</a></>
              : <><b>Outcome reported by source systems.</b> Finance confirms the economic result.{can('confirm') && <div style={{ marginTop: 8 }}><button className="btn sm pri" onClick={() => caseActions.confirmOutcome(c.id)}>Confirm outcome <Stp n={10} /></button></div>}</>}
            {fixedAssetLine(c) && <div className="note" style={{ marginTop: 6 }}>{fixedAssetLine(c)}</div>}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------- the move and what happens if (exMoveHTML, exWhatIfHTML) ----------
export function MoveTable({ a }: { c?: CaseRec; a: CaseAnalysis }) {
  const m = a.move;
  if (!m || !m.legs.length) return null;
  return (
    <div className="exmv" id="exMove">
      {m.stage && <p className="note" style={{ margin: '0 0 6px' }}><b>Staging:</b> {m.stage.why}.</p>}
      <div className="tw">
        <table className="t static tight">
          <thead><tr><th>Leg</th><th className="r">km</th><th>ETD</th><th>ETA</th><th>Carrier</th><th className="r">Freight</th></tr></thead>
          <tbody>
            {m.legs.map((l, i) => (
              <tr key={i}>
                <td><b>{l.from} → {l.to}</b><div className="note">{locOf(a, l.to)} · receives {a.view.locs[l.to]?.win ?? '—'}</div></td>
                <td className="r num">{exNum(l.km)}</td>
                <td className="num nowrap">{exTs(l.etd)}<div className="note">Day {moveDay(m, l.etd)}</div></td>
                <td className="num nowrap">{exTs(l.eta)}<div className="note">Day {moveDay(m, l.eta)}{l.readyAt ? ' · refurbished ' + fmtD(l.readyAt) + ', Day ' + moveDay(m, l.readyAt) : ''}</div></td>
                <td>{l.carrier}<div className="note">{l.mode}</div></td>
                <td className="r num">{inr(l.inr)}<div className="note">{money(l.inr / refList('EX_FX'))}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {m.need && m.eta && (
        <p className="note" style={{ margin: '6px 0 0' }}>
          Approved {fmtD(m.d0)} (Day 0) · need-by {fmtDY(m.need)} (Day {moveDay(m, m.need)}) · ETA {exTs(m.eta)} (Day {moveDay(m, m.eta)}) · <b className={(m.slack ?? 0) < 0 ? 'tx-bad' : 'tx-ok'}>{(m.slack ?? 0) < 0 ? Math.abs(m.slack!) + ' days late' : m.slack + ' days of slack'}</b>
        </p>
      )}
    </div>
  );
}
export function WhatIfList({ a }: { a: CaseAnalysis }) {
  const w = a.what_if;
  if (!w.length) return null;
  return (
    <ul className="exwi" id="exWhatIf">
      {w.map((x) => <li key={x.k} data-k={x.k}><span className={'chip ' + (x.on ? 'warn' : 'line')}>{x.on ? 'Enforced' : 'Guidance'}</span><span><b>{x.t}</b> <span className="note">{x.d}</span></span></li>)}
    </ul>
  );
}

// ---------- approval and hand-off (tiHandoff) ----------
export function TiHandoff({ c, a, noMove }: { c: CaseRec; a: CaseAnalysis; noMove?: boolean }) {
  const ui = useCaseUi();
  const r = routeOf(c);
  if (!r) return <CasePanel t="Approval and enterprise handoff" cls="tiho"><p className="note" style={{ margin: 0 }}>Nothing can be approved or handed off until a pathway is recommended.</p></CasePanel>;
  const steps = a.view.steps, p = (a.instruction || {}) as { targetSite?: string; expectedNetUsd?: number; spendAuthorityUsd?: number }, M = a.demand;
  const dl = approverRole(c) === 'Approver', big = r.net > 25000, mv = a.move, legs = !!(mv && mv.legs.length);
  const apps = uniq(steps.map((s) => s.app)).filter((s) => !/^Circularity|^Planning/.test(s));
  return (
    <CasePanel t="Approval and enterprise handoff" cls="tiho" id="tiInstr">
      <dl className="tikv">
        <div><dt>Required approval</dt><dd>{dl ? 'Approver (decisions delegated by Admin)' : 'Admin (decisions are not delegated)'}{big ? ' · above $25k also needs Admin (assumed)' : ''}</dd></div>
        <div><dt>Responsible approver</dt><dd>{c.approval ? c.approval.by : dl ? 'Approver' : 'Admin'}</dd></div>
        <div><dt>Target applications</dt><dd>{apps.map((s, i) => <Fragment key={s}>{i ? ' ' : ''}<span className="chip line">{s}</span></Fragment>)}</dd></div>
        {r.id === 'redeploy' && M?.order && <div><dt>Destination</dt><dd>{M.order} line {M.line} · {c.owner} · {locOf(a, M.shipTo)} · need-by {M.needBy ? fmtDY(M.needBy) : '—'}</dd></div>}
        <div><dt>Instruction status</dt><dd>{c.exec ? steps.filter((s) => s.state === 'done').length + ' of ' + steps.length + ' acknowledged' : 'Not sent · sent only after approval'}</dd></div>
        <div><dt>Expected outcome</dt><dd>{money(r.net)} net · {c.outcome ? 'actual ' + money(c.outcome.net) : c.stage === 'closed' ? 'actual reported, to confirm' : 'actual result pending'}</dd></div>
      </dl>
      <h4 style={{ margin: '12px 0 4px' }}>{c.exec ? 'Instruction sent' : 'Instruction preview (before approval)'}</h4>
      <div className="tw">
        <table className="t static tight" id="tiPrev">
          <thead><tr><th>Target system</th><th>Instruction</th><th>Document</th><th>Owner</th><th>Time limit</th></tr></thead>
          <tbody>
            {steps.map((s, i) => {
              const q = a.plan[i];
              return (
                <tr key={i} data-k={s.k || ''}>
                  <td><b>{s.app}</b><div className="note">{s.sys}</div></td>
                  <td>
                    {s.label}: {r.plan} · {c.assetId}{c.qty > 1 ? ' ×' + c.qty : ''}
                    {s.k === 'order' && M?.order ? ' · against ' + c.owner + ' contract replacement order ' + M.order + ' (' + (M.site || '—') + ') line ' + M.line : ''}
                    {s.k === 'move' && p.targetSite ? ' · to ' + p.targetSite : ''}
                    {q?.act && <div className="note">{q.act}</div>}
                  </td>
                  <td className="mono">{(q?.docs || []).map((d, j) => <Fragment key={j}>{j ? <br /> : null}{d}</Fragment>)}<div className="note">{q?.planned ? 'to be created' : 'acknowledged'}</div></td>
                  <td>{q?.owner || ''}<div className="note">{q?.why || ''}</div></td>
                  <td className="nowrap">{q?.lim || ''}<ExClockChip k={q?.clock} /></td>
                </tr>
              );
            })}
            <tr><td><b>Amounts</b></td><td colSpan={4}>Expected net {money(p.expectedNetUsd ?? r.net)} · spend authority {money(p.spendAuthorityUsd ?? defaultSpend(c, r))}</td></tr>
          </tbody>
        </table>
      </div>
      {!(noMove && legs) && (
        <>
          {legs && <><h4 style={{ margin: '12px 0 4px' }}>Route and timing</h4><MoveTable c={c} a={a} /></>}
          <h4 style={{ margin: '12px 0 4px' }}>What happens if</h4><WhatIfList a={a} />
        </>
      )}
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn sm" onClick={() => openRaw(ui, c, a)}>View raw payload</button>
        <span className="note">There is no auto-approve path. Every handoff carries the approval reference.</span>
      </div>
    </CasePanel>
  );
}

// ---------- reconcile and learn (tiReconcile) ----------
export function TiReconcile({ c, a }: { c: CaseRec; a: CaseAnalysis }) {
  const ui = useCaseUi();
  const r = routeOf(c);
  if (!r) return null;
  const o = c.outcome, vo = a.view.value_order, an = canPage('analytics', 'predicted'), ri = routeIndex(c);
  const head = <div className="ph"><h3>Reconcile and learn</h3><span className="sp"></span><Stp n={10} /></div>;
  if (!o) {
    return (
      <section className="panel" id="tiReconcile" style={{ marginTop: 16 }}>
        {head}
        <div className="pb">
          <p className="ink2" style={{ margin: 0 }}>{c.stage === 'closed' ? 'The outcome is reported. Waiting for Finance to confirm it' + (can('confirm') ? ': confirm it in the enterprise handoff above.' : '.') : "Waiting for the outcome from ERP (step 9) and Finance's confirmation."}</p>
          <p className="note" style={{ margin: '6px 0 0' }}>Once confirmed, each cost line of <b>{r.plan}</b> is compared with its prediction{vo ? ' against ' + vo.kind.toLowerCase() + ' ' + vo.ref : ''}, and the model that made the prediction learns from the difference.</p>
        </div>
      </section>
    );
  }
  const d = o.net - r.net, dl = (x: number) => (x === 0 ? '—' : (x > 0 ? '+' : '−') + money(Math.abs(x)));
  const exSigned = (v: number) => (v > 0 ? '+' : v < 0 ? '−' : '') + inr(Math.abs(v));
  return (
    <section className="panel" id="tiReconcile" style={{ marginTop: 16 }}>
      {head}
      <div className="pb">
        <p className="rcsum" id="rcSum">
          <b>Predicted {money(r.net)}</b>{vo ? <> against {vo.kind.toLowerCase()} <b className="mono">{vo.ref}</b></> : ''} · <b>actual {money(o.net)}</b> · variance <b className={d < 0 ? 'tx-bad' : 'tx-ok'}>{dl(d)}</b>
          {a.view.delivered && <span className="note"> · {a.view.delivered}</span>}
        </p>
        <div className="tw">
          <table className="t static tight" id="rcLines">
            <thead><tr><th>Cost line</th><th className="r">Predicted</th><th className="r">Actual</th><th className="r">Δ</th><th>Learns</th></tr></thead>
            <tbody>
              {o.lines.map((l, i) => {
                const x = l.act - l.pred, ti = r.terms.findIndex((t) => t.label === l.label), A = x ? a.view.actuals[i] || [] : [];
                return (
                  <tr key={i} data-kind={l.kind}>
                    <td>
                      {l.label} {ti >= 0 && ri >= 0 && <button className="lnk exsrc" aria-label={'Where ' + l.label.charAt(0).toLowerCase() + l.label.slice(1) + ' comes from'} onClick={() => openExSrc(ui, c, a, ri, ti)}>Source</button>}
                      {A.length > 0 && <div className="note">{A.map((y) => y[0] + ' ' + exSigned(y[2])).join(' · ')}</div>}
                    </td>
                    <td className="r num">{money(l.pred)}</td><td className="r num">{money(l.act)}</td>
                    <td className={'r num ' + (x < 0 ? 'tx-bad' : x > 0 ? 'tx-ok' : '')}>{dl(x)}</td>
                    <td>{l.model ? <span className="mono">{l.model} {l.ver}</span> : <span className="note">No model · {l.src}</span>}</td>
                  </tr>
                );
              })}
              <tr className="rcnet"><td><b>Net</b></td><td className="r num"><b>{money(r.net)}</b></td><td className="r num"><b>{money(o.net)}</b></td><td className="r num"><b>{dl(d)}</b></td><td className="note">Linked to {c.exec?.decisionId}</td></tr>
            </tbody>
          </table>
        </div>
        <p className="note" style={{ margin: '8px 0 0' }}>
          {rcStory(o.lines)} Actuals come from the enterprise systems' outcome report and Finance's confirmation; Circularity records them and does not change them.
          {an && <> <a className="lnk" href={`#/analytics/predicted?dp=${c.id}`}>Predicted vs actual across all decisions</a></>}
        </p>
      </div>
    </section>
  );
}
/** Which cost line moved most, and which model learns from it (rcStory). */
function rcStory(lines: OutcomeLine[]): string {
  const l = lines.filter((x) => x.act !== x.pred).sort((a, b) => Math.abs(b.act - b.pred) - Math.abs(a.act - a.pred))[0];
  if (!l) return 'Every line came in as predicted.';
  const x = l.act - l.pred, cost = l.pred < 0;
  return `The largest difference is ${l.label.charAt(0).toLowerCase() + l.label.slice(1)}: ${money(Math.abs(x))} ${cost ? (x < 0 ? 'more' : 'less') + ' cost' : (x < 0 ? 'less' : 'more') + ' value'} than predicted, so ${l.model} ${l.ver} learns most from this outcome.`;
}

// ---------- stage 7 ----------
export function RationaleTab({ c, a }: TabProps) {
  const rat = c.approval ? c.approval.rationale : c.packet ? c.packet.rationale : a.rationale;
  return (
    <div className="stpad">
      <p className="note" style={{ marginTop: 0 }}>{c.approval ? 'The rationale recorded with the approval.' : <><AfBadge k="Prepared by agent" /> The drafted rationale the Approver edits or acknowledges.</>}</p>
      <blockquote className="strat">{rat || '—'}</blockquote>
    </div>
  );
}
export function ChecksTab({ c, a }: TabProps) {
  return (
    <section className="tistep" id="step-5">
      <CasePanel t="Decision" cls="tix5a" id="tiDecision"><div className="tidec"><BestCard c={c} a={a} /></div></CasePanel>
    </section>
  );
}
export function HistoryTab({ c, a }: TabProps) {
  const jr = a.journal.slice(-8).reverse(), cat = actionCatalog();
  if (!jr.length) return <p className="note stpad">No recorded actions on {c.id} yet.</p>;
  return <Timeline rows={jr.map((e) => ({ ic: 'clock', h: 'neutral', t: cat.find((x) => x.id === e.id)?.title ?? e.id, s: e.by + (e.prep ? ' · prepared by the agent' : ''), ago: when(e.at) }))} />;
}

// ---------- stage 8 ----------
/** The instruction plan as a vertical timeline (stPlanTl). */
export function PlanTab({ c, a, s }: TabProps) {
  const pl = a.plan;
  if (!pl.length) return <p className="note stpad">No plan yet.</p>;
  const src = Object.values(s.sources);
  return (
    <ol className="sttl">
      {pl.map((p) => {
        const k = p.state === 'done' ? 'done' : p.state === 'active' ? 'wait' : 'todo', so = src.find((z) => z.vendor === p.app);
        const t = k === 'done' ? { k, icon: '✓', word: 'Acknowledged' } : k === 'wait' ? { k, icon: '⏳', word: 'With ' + p.app } : { k, icon: '○', word: c.exec ? 'Not sent yet' : 'Sent after approval' };
        return (
          <li key={p.n} className={'st-' + k}>
            <span className="sttn" aria-hidden="true">{p.state === 'done' ? '✓' : p.n}</span>
            <div className="sttb">
              <b>{p.label}</b> <Tag t={t as { k: 'done' | 'wait' | 'todo'; icon: string; word: string }} />
              <p className="note">{p.act}</p>
              <p className="sttm">{so && <VendorLogo vendor={so.vendor} />}<span>{p.app}</span><span className="mono">{p.docs.join(' · ')}</span><span>{p.owner}</span><span>Limit {p.lim}</span></p>
              <ExClockChip k={p.clock} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}
export function MoveTab({ c, a }: TabProps) {
  if (!a.move || !a.move.legs.length) return <p className="note stpad">No transport for this route.</p>;
  return <div className="stpad"><MoveTable c={c} a={a} /><h4 style={{ margin: '12px 0 4px' }}>What happens if</h4><WhatIfList a={a} /></div>;
}
export const AcksTab = ({ c, a }: TabProps) => <ExecBlock c={c} a={a} />;
export const InstrTab = ({ c, a }: TabProps) => <TiHandoff c={c} a={a} noMove />;

// ---------- stage 9 ----------
/** The delivery against the order line (stDelivery). */
export function DeliveryTab({ c, a }: TabProps) {
  const r = routeOf(c)!, d = a.view.delivered, m = a.move, M = a.demand;
  if (!d || !m || !M) return <p className="note stpad">{r.id === 'redeploy' ? 'Delivery is confirmed by proof of delivery in stage 8.' : 'This route has no delivery to a customer site.'}</p>;
  const L = m.legs[m.legs.length - 1], pod = (c.exec ? c.exec.steps : []).find((y) => y.k === 'pod');
  return (
    <div className="stpad">
      <p style={{ marginTop: 0 }}>{d.charAt(0).toUpperCase() + d.slice(1)}.</p>
      <Kv pad={false} rows={[
        ['Delivered to', locOf(a, m.to)], ['Order line', M.order + ' line ' + M.line], ['Arrival', m.eta ? exTs(m.eta) : '—'], ['Need-by', M.needBy ? fmtDY(M.needBy) : '—'],
        ['Slack', m.slack == null ? '—' : m.slack < 0 ? Math.abs(m.slack) + ' days late' : m.slack + ' days early'], ['Last leg', L ? L.from + ' → ' + L.to + ' · ' + L.carrier : '—'],
        ['Proof of delivery', pod && pod.ack ? pod.ack.ref : 'Not yet'],
      ]} />
    </div>
  );
}
/** Cost lines, predicted against actual (stLines). */
function Lines({ lines, learn }: { lines: OutcomeLine[]; learn: boolean }) {
  const l = learn ? lines.filter((z) => z.model) : lines;
  return (
    <div className="tw stpad">
      <table className="t static tight">
        <thead><tr><th>{learn ? 'Learning record' : 'Cost line'}</th><th className="r">Predicted</th><th className="r">Actual</th>{learn && <th>Model</th>}</tr></thead>
        <tbody>{l.map((z, i) => <tr key={i}><td>{z.label}</td><td className="r num">{money(z.pred)}</td><td className="r num">{money(z.act)}</td>{learn && <td className="mono">{z.model} {z.ver || ''}</td>}</tr>)}</tbody>
      </table>
    </div>
  );
}
export function CostsTab({ c }: TabProps) {
  const r = routeOf(c)!, o = c.outcome;
  if (!o) return <p className="note stpad">Actual costs arrive with the outcome report and Finance's confirmation.</p>;
  return <><Pva pred={r.net} act={o.net} /><Lines lines={o.lines} learn={false} /></>;
}
/** Every document the enterprise systems returned (stDocsTab). */
export function DocsTab({ a }: TabProps) {
  const st = a.view.steps.filter((y) => y.ack);
  if (!st.length) return <p className="note stpad">Documents arrive as the enterprise systems acknowledge each instruction in stage 8.</p>;
  return (
    <div className="tw stpad">
      <table className="t static tight">
        <thead><tr><th>Document</th><th>Step</th><th>System</th><th>Returned</th></tr></thead>
        <tbody>{st.map((y, i) => <tr key={i}><td><Doc r={y.ack!.ref} /></td><td>{y.label}</td><td>{y.app}</td><td className="num">{when(y.ack!.at)} · {y.ack!.by}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

// ---------- stage 10 ----------
export const LinesTab = ({ c, a }: TabProps) => <TiReconcile c={c} a={a} />;
export function LearnTab({ c }: TabProps) {
  const o = c.outcome;
  return o ? <Lines lines={o.lines} learn /> : <p className="note stpad">Each cost line becomes a learning record once the outcome is confirmed.</p>;
}
/** What is carried forward from the matched demand (stCarried). */
export function CarriedTab({ c, a }: TabProps) {
  const M = a.demand, r = routeOf(c), met = r && r.id === 'redeploy' && M && M.order;
  return (
    <div className="stpad">
      {M && M.order
        ? <p style={{ marginTop: 0 }}>{met ? `${M.order} line ${M.line} is filled by ${c.id}; nothing is carried forward from it.` : `${M.order} line ${M.line} stays open and is carried forward to the next matching return.`}</p>
        : <p className="note" style={{ marginTop: 0 }}>No contract demand was matched for this case, so nothing is carried forward.</p>}
      {M && M.lease && <p className="note">Re-lease opportunity {M.lease} stays open in CRM.</p>}
    </div>
  );
}
