import { useEffect, useRef, useState, type MouseEvent } from 'react';
import { invoke } from '../../api/actions';
import {
  approvalLimit, approvalTerms, badgeHtml, caseById, defaultSpend, draftRationale, driversHtml, eligibleRoutes,
  instructionJsonHtml, resetScen, scen, scenAdj, scenarioImpactHtml, scheduleAutoAck, setScen, snapshotFrozenAt, snapshotItems,
  type CaseRec, type ScenKey,
} from '../../api/case';
import { money } from '../../api/format';
import { currentAccount } from '../../api/session';
import { Icon } from '../../ui/Icon';
import { Modal } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import { Legacy } from './ui';

/** The approval card (ACT.approve with the agent's draft, the limit and the raw instruction; confirmApprove). */
export function ApprovalModal({ c, mode, onClose }: { c: CaseRec; mode?: 'review'; onClose: () => void }) {
  const rec = c.recommendation!;
  const el = eligibleRoutes(c);
  const draft = draftRationale(c);
  const [plan, setPlan] = useState(rec.plan);
  const [why, setWhy] = useState(draft);
  const [auto, setAuto] = useState(false); // the override text was filled in by the card, not typed
  const [spend, setSpend] = useState(String(defaultSpend(c, rec)));
  const [terms, setTerms] = useState(approvalTerms(c, rec));
  const [ack, setAck] = useState(false);
  const [err, setErr] = useState('');
  const sel = useRef<HTMLSelectElement>(null);
  useEffect(() => { if (mode === 'review') window.setTimeout(() => sel.current?.focus(), 60); }, [mode]);
  const lim = approvalLimit(), net = Math.abs(rec.net);
  const t = c.routes.find((x) => x.plan === plan) ?? rec;

  function pickRoute(v: string) {
    const r = c.routes.find((x) => x.plan === v)!;
    setPlan(v);
    setTerms(approvalTerms(c, r));
    setSpend(String(defaultSpend(c, r)));
    if (r !== rec && (!why || why === draft || auto)) {
      setWhy('Override: ' + r.plan + ' instead of ' + rec.plan + ' (' + money(rec.net - r.net) + ' less predicted net). Reason: ');
      setAuto(true);
    } else if (r === rec && auto) {
      setWhy(draft);
      setAuto(false);
    }
  }

  async function confirm() {
    const text = why.trim();
    const val = Math.max(Math.abs(t.net), +spend || 0);
    if (val > lim && text.length >= 15 && ack) {
      setErr(c.id + ' is worth ' + money(val) + ', above your approval limit of ' + money(lim) + '. It has been escalated to Admin.');
      invoke('escalation.send', { case_id: c.id, to: 'admin', msg: c.id + ' needs approval above the ' + currentAccount()?.role + ' limit of ' + money(lim) + ' (' + money(val) + '): ' + text.slice(0, 180), blocker: 'Above approval limit' });
      return;
    }
    const ov = plan !== rec.plan;
    const r = await invoke<{ ref: string; sent_to: string }>(ov ? 'decision.override' : 'decision.approve', { case_id: c.id, route: plan, rationale: text, reviewed: ack, spend: +spend || 0, terms });
    if (!r.ok) {
      if (r.error.code === 'validation_error') setErr(r.error.message);
      else toast(r.error.message, 4200);
      return;
    }
    onClose();
    toast(`${r.output.ref} created. Instruction handed to ${r.output.sent_to.split(' · ')[0]}.`);
    scheduleAutoAck(c.id, 0);
  }

  return (
    <Modal
      title={'Approve ' + c.id} wide onClose={onClose}
      foot={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn pri" onClick={confirm}><Icon name="check" /> Approve and send instruction</button>
      </>}
    >
      <div className="callout info" style={{ marginBottom: 14 }}>
        <b>{rec.plan}</b> · expected net <b>{money(rec.net)}</b> (P10–P90 {money(rec.p10)}–{money(rec.p90)}). Approving sends an instruction to the owning systems; they remain authoritative for the work.
      </div>
      <div className="fld">
        <label htmlFor="ap-route">Route to approve</label>
        <select id="ap-route" ref={sel} value={plan} onChange={(e) => pickRoute(e.target.value)}>
          {el.map((x) => (
            <option key={x.plan} value={x.plan}>{x === rec ? 'Recommended · ' : 'Override · '}{x.plan} ({money(x.net)})</option>
          ))}
        </select>
        <div className="hint" id="ap-hint">
          {t === rec ? 'Recommended route selected.' : <><b>Override.</b> A human-selected route replaces the recommendation. Your rationale is recorded and counted in override analytics.</>}
        </div>
      </div>
      <div className="fld">
        <label htmlFor="ap-why">Rationale <span className="muted">(required)</span></label>
        <textarea id="ap-why" placeholder="Why is this the right action? Mention anything the model cannot see." value={why} onChange={(e) => { setWhy(e.target.value); setAuto(false); }} />
        <div className="err" id="ap-err" hidden={!err}>{err}</div>
      </div>
      <div className="afapx">
        <p className="note">
          <span dangerouslySetInnerHTML={{ __html: badgeHtml('Prepared by agent') }} /> The rationale above is the agent's draft. Edit it, or tick the box below to acknowledge it; nothing is approved until you press the button.
        </p>
        <p className="note">
          Your approval limit: <b>{lim === Infinity ? 'unlimited' : money(lim)}</b>
          {lim !== Infinity && net > lim && <> · <b className="neg">this decision is above it and escalates</b></>}.
        </p>
        <details className="afraw">
          <summary>Raw instruction that will be sent </summary>
          <pre className="code" dangerouslySetInnerHTML={{ __html: instructionJsonHtml(c) }} />
        </details>
      </div>
      <div className="grid g2">
        <div className="fld">
          <label htmlFor="ap-spend">Spend authority (USD)</label>
          <input id="ap-spend" type="number" min={0} value={spend} onChange={(e) => setSpend(e.target.value)} />
          <div className="hint">Instruction cannot commit beyond this amount.</div>
        </div>
        <div className="fld">
          <label htmlFor="ap-terms">Spend and sale terms</label>
          <input id="ap-terms" type="text" value={terms} onChange={(e) => setTerms(e.target.value)} />
        </div>
      </div>
      <label className="tog">
        <input type="checkbox" id="ap-ack" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I reviewed evidence snapshot {c.snapshot?.id} and the excluded routes
      </label>
    </Modal>
  );
}

/** Decline with a required reason (ACT.declineDecision / declineDecisionOk). */
export function DeclineModal({ c, onClose }: { c: CaseRec; onClose: () => void }) {
  const [why, setWhy] = useState('');
  const [err, setErr] = useState('');
  async function ok() {
    const r = await invoke('decision.decline', { case_id: c.id, reason: why.trim() });
    if (!r.ok) {
      if (r.error.code === 'validation_error') setErr(r.error.message);
      else toast(r.error.message, 4200);
      return;
    }
    onClose();
    toast(c.id + ' declined and sent back for re-evaluation.', 4200);
  }
  return (
    <Modal
      title={'Decline ' + c.id} onClose={onClose}
      foot={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn danger" onClick={ok}>Decline</button></>}
    >
      <p className="ink2" style={{ marginTop: 0 }}>The recommendation goes back for re-evaluation, and the Planner sees your reason. Nothing is sent to any system.</p>
      <div className="fld">
        <label htmlFor="dc-why">Reason <span className="muted">(required)</span></label>
        <textarea id="dc-why" maxLength={300} placeholder="What has to change before you would approve?" value={why} onChange={(e) => setWhy(e.target.value)} />
        <div className="hint">Recorded in the audit log. Do not enter personal data.</div>
        <div className="err" id="dc-err" hidden={!err}>{err}</div>
      </div>
    </Modal>
  );
}

// the evidence each driver or assumption rests on: moving a slider lights these rows (CX_EV)
const CX_EV: Record<string, string[]> = { purchase: ['cost', 'dem'], prep: ['insp', 'photo'], cost: ['insp', 'photo'], service: ['svc', 'eng'], residual: ['mkt'], market: ['mkt'], sale: ['mkt'], demand: ['dem'], gates: ['pol', 'id', 'eng'] };
const CX_SL: [ScenKey, string][] = [['purchase', 'Avoided purchase price'], ['cost', 'Workshop, parts and fees'], ['service', 'Service exposure'], ['market', 'Resale price']];

/** Stage 6 "✦ Explain this decision": why, what-if sliders and the evidence snapshot on one screen (cxExplainHTML). */
export function ExplainView({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const c = caseById(caseId)!;
  const r = c.recommendation!;
  const [hot, setHot] = useState<string[]>([]);
  const timer = useRef(0);
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    document.body.classList.add('cxopen');
    window.setTimeout(() => close.current?.focus(), 30);
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', k);
    return () => {
      document.body.classList.remove('cxopen');
      document.removeEventListener('keydown', k);
      window.clearTimeout(timer.current);
    };
  }, [onClose]);
  const light = (keys: string[]) => {
    setHot(keys);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setHot([]), 4200);
  };
  const s = scen();
  const nx = c.routes.filter((x) => !x.excluded && x !== r).sort((a, b) => b.net - a.net)[0];
  const ex = c.routes.filter((x) => x.excluded);
  const sn = c.snapshot;
  const preset = (k: 'parts' | 'demand' | 'resale' | 'reset') => {
    if (k === 'reset') { resetScen(); setHot([]); }
    else if (k === 'parts') { setScen({ cost: s.cost === 1.3 ? 1 : 1.3 }); light(CX_EV.cost); }
    else if (k === 'demand') { setScen({ demandOff: !s.demandOff }); light(CX_EV.demand); }
    else { setScen({ market: s.market === 0.8 ? 1 : 0.8 }); light(CX_EV.market); }
  };
  const onDriver = (e: MouseEvent) => {
    const d = (e.target as Element).closest('.cxd[data-ev]') as HTMLElement | null;
    if (d?.dataset.ev) light(d.dataset.ev.split(' '));
  };

  return (
    <div id="cxX" className="cxx" role="dialog" aria-modal="true" aria-label="Explain this decision">
      <div className="cxxw">
        <header className="cxxh">
          <div>
            <span className="note">{c.id} · {c.product} · Stage 6 · Decide</span>
            <h2>Why {r.plan} · {money(r.net)}</h2>
          </div>
          <span className="sp" />
          <span dangerouslySetInnerHTML={{ __html: badgeHtml('Prepared by agent') }} style={{ display: 'contents' }} />
          <button ref={close} className="btn" aria-label="Close" onClick={onClose}>Close</button>
        </header>
        <div className="cxxb">
          <div className="cxl">
            <section className="panel cxp">
              <div className="cxph"><h3>Why this outcome</h3><span className="note">{r.why || ''}</span></div>
              <div className="cxds" onMouseOver={onDriver} dangerouslySetInnerHTML={{ __html: driversHtml(c, r) }} />
              <p className="cxnx note">
                {nx && <>Next best: <b>{nx.plan}</b>, {money(nx.net)}, {money(r.net - nx.net)} less. </>}
                {ex.length > 0 && <>Withheld before pricing: {ex.map((x) => x.plan + ' (' + String(x.failReason || 'a gate failed').replace(/^./, (m) => m.toLowerCase()) + ')').join('; ')}. </>}
                All six eligibility checks passed.
              </p>
            </section>
            <section className="panel cxp">
              <div className="cxph"><h3>What if</h3><span className="note">Stress the assumptions. The recommendation on record does not change until it is re-evaluated.</span></div>
              <div className="cxwi">
                <div>
                  <div className="tisl">
                    {CX_SL.map(([k, l]) => (
                      <div key={k} className="sl cxsl">
                        <label htmlFor={'cx-sc-' + k}>{l}</label>
                        <input
                          id={'cx-sc-' + k} type="range" min={50} max={150} step={5} value={Math.round(s[k] * 100)}
                          onChange={(e) => { setScen({ [k]: +e.target.value / 100 }); light(CX_EV[k] || []); }}
                        />
                        <b className="num" id={'cx-scv-' + k}>{scenAdj(s[k])}</b>
                      </div>
                    ))}
                  </div>
                  <div className="cxpre" role="group" aria-label="Edge cases">
                    <button className="btn sm" aria-pressed={s.cost === 1.3} onClick={() => preset('parts')}>Workshop cost +30%</button>
                    <button className="btn sm" aria-pressed={!!s.demandOff} onClick={() => preset('demand')}>Customer order cancelled</button>
                    <button className="btn sm" aria-pressed={s.market === 0.8} onClick={() => preset('resale')}>Resale price −20%</button>
                    <button className="btn sm" onClick={() => preset('reset')}>Reset to base</button>
                  </div>
                </div>
                <Legacy html={scenarioImpactHtml(c)} />
              </div>
            </section>
          </div>
          <aside className="panel cxr" aria-label="Evidence snapshot">
            <div className="cxph">
              <h3>Evidence snapshot</h3>
              <span className="note">{sn ? sn.id + ' · frozen ' + snapshotFrozenAt(c) : 'No snapshot yet'}. Each figure, the system it came from and when.</span>
            </div>
            <ul className="cxevs">
              {snapshotItems(c).map((e) => (
                <li key={e.k} className={'cxev' + (hot.includes(e.k) ? ' hot' : '')} data-k={e.k}>
                  <span className={'cxevi ' + (e.ready ? 'ok' : 'warn')} aria-hidden="true">{e.ready ? '✓' : '!'}</span>
                  <div>
                    <b>{e.label}</b>
                    <div className="cxevv">{e.value}</div>
                    <div className="cxevm mono">{e.system}{e.available ? ' · ' + e.record + ' · ' + e.fetchedAt : ''}</div>
                  </div>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      </div>
    </div>
  );
}

