import { useEffect, useRef, useState, type SyntheticEvent } from 'react';
import { invoke } from '../../api/actions';
import {
  approvalLimit, approvalTerms, caseAnalysis, caseById, confidence, defaultSpend, draftRationale, eligibleRoutes, instruction,
  isoT, resetScen, scen, scenAdj, scenRoutes, setScen, snapshotItems, type CaseAnalysis, type CaseRec, type Route, type ScenKey,
} from '../../api/case';
import { money } from '../../api/format';
import { currentAccount } from '../../api/session';
import { Icon } from '../../ui/Icon';
import { Modal, useOverlay } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import { JsonView } from '../../ui/kit/JsonView';
import { AfBadge } from './CaseBlocks';
import { TiResult } from './tabs/DecideTabs';

/** The approval card (ACT.approve with the agent's draft, the limit and the raw instruction; confirmApprove). */
export function ApprovalModal({ c, mode, onClose }: { c: CaseRec; mode?: 'review'; onClose: () => void }) {
  // the recommendation as the entry of c.routes (the API sends it as a copy), so the comparisons below hold
  const rec = c.routes.find((x) => x.id === c.recommendation!.id && x.plan === c.recommendation!.plan) ?? c.recommendation!;
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
  const lim = approvalLimit(c), net = Math.abs(rec.net);
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
          <AfBadge k="Prepared by agent" /> The rationale above is the agent's draft. Edit it, or tick the box below to acknowledge it; nothing is approved until you press the button.
        </p>
        <p className="note">
          Your approval limit: <b>{lim === Infinity ? 'unlimited' : money(lim)}</b>
          {lim !== Infinity && net > lim && <> · <b className="neg">this decision is above it and escalates</b></>}.
        </p>
        <details className="afraw">
          <summary>Raw instruction that will be sent </summary>
          <JsonView variant="lines" value={instruction(c)} />
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
  const a = caseAnalysis(c.id);
  const [hot, setHot] = useState<string[]>([]);
  const timer = useRef(0);
  const close = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);
  useOverlay(onClose, box); // Esc through the overlay stack, Tab kept inside, focus back to the opener on close
  useEffect(() => {
    document.body.classList.add('cxopen');
    const t = window.setTimeout(() => close.current?.focus(), 30);
    return () => {
      document.body.classList.remove('cxopen');
      window.clearTimeout(t);
      window.clearTimeout(timer.current);
    };
  }, []);
  const light = (keys: string[]) => {
    setHot(keys);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setHot([]), 4200);
  };
  const s = scen();
  const nx = c.routes.filter((x) => !x.excluded && !(x.id === r.id && x.plan === r.plan)).sort((a, b) => b.net - a.net)[0];
  const ex = c.routes.filter((x) => x.excluded);
  const sn = c.snapshot;
  const preset = (k: 'parts' | 'demand' | 'resale' | 'reset') => {
    if (k === 'reset') { resetScen(); setHot([]); }
    else if (k === 'parts') { setScen({ cost: s.cost === 1.3 ? 1 : 1.3 }); light(CX_EV.cost); }
    else if (k === 'demand') { setScen({ demandOff: !s.demandOff }); light(CX_EV.demand); }
    else { setScen({ market: s.market === 0.8 ? 1 : 0.8 }); light(CX_EV.market); }
  };
  // a driver lights its evidence on hover, and on keyboard focus too
  const onDriver = (e: SyntheticEvent) => {
    const d = (e.target as Element).closest('.cxd[data-ev]') as HTMLElement | null;
    if (d?.dataset.ev) light(d.dataset.ev.split(' '));
  };

  return (
    <div ref={box} id="cxX" className="cxx" role="dialog" aria-modal="true" aria-label="Explain this decision">
      <div className="cxxw">
        <header className="cxxh">
          <div>
            <span className="note">{c.id} · {c.product} · Stage 6 · Decide</span>
            <h2>Why {r.plan} · {money(r.net)}</h2>
          </div>
          <span className="sp" />
          <AfBadge k="Prepared by agent" />
          <button ref={close} className="btn" aria-label="Close" onClick={onClose}>Close</button>
        </header>
        <div className="cxxb">
          <div className="cxl">
            <section className="panel cxp">
              <div className="cxph"><h3>Why this outcome</h3><span className="note">{r.why || ''}</span></div>
              <div className="cxds" onMouseOver={onDriver} onFocus={onDriver}><Drivers a={a} r={r} /></div>
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
                <div id="cxImpact"><TiResult c={c} a={a} sr={scenRoutes(c)} /></div>
              </div>
            </section>
          </div>
          <aside className="panel cxr" aria-label="Evidence snapshot">
            <div className="cxph">
              <h3>Evidence snapshot</h3>
              <span className="note">{sn ? sn.id + ' · frozen ' + isoT(a.snapshot_time) : 'No snapshot yet'}. Each figure, the system it came from and when.</span>
            </div>
            <ul className="cxevs">
              {snapshotItems(c, a).map((e) => (
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


const CX_DRV: Record<string, [string, string]> = {
  purchase: ['Avoids a new purchase', 'Planned purchase at the procurement contract price'],
  prep: ['Workshop refurbishment and transfer', 'Repair scope and hours from the MRO workshop; parts at contract prices'],
  service: ['Expected service cost', 'Failure history for this class at this duty'],
  residual: ['Value left at the end of the term', 'Market comparables for this grade and age'],
  sale: ['Sale proceeds', 'Market comparables for this grade and age'],
};
/** The value drivers of the recommended route as bars, each naming the evidence it rests on (cxDrivers). */
function Drivers({ a, r }: { a: CaseAnalysis; r: Route }) {
  const t = r.terms || [], mx = Math.max(1, ...t.map((x) => Math.abs(x.amt)));
  return (
    <>
      {t.map((x, i) => {
        const d = CX_DRV[x.kind] || [x.label, ''], ev = CX_EV[x.kind] || [], w = Math.max(4, Math.round((Math.abs(x.amt) / mx) * 100));
        return (
          <div key={i} className="cxd" data-ev={ev.join(' ')}>
            <div className="cxdl"><b>{x.kind === 'service' ? d[0] + ' \u00b7 ' + ((x.label.match(/\(([^)]+)\)/) || [])[1] || 'term') : d[0]}</b><span className="note">{d[1]}</span></div>
            <div className="cxdb"><span className={'cxbar ' + (x.amt < 0 ? 'neg' : 'pos')} style={{ width: w + '%' }}></span></div>
            <b className={'num cxda ' + (x.amt < 0 ? 'neg' : 'pos')}>{x.amt < 0 ? '\u2212' : '+'}{money(Math.abs(x.amt))}</b>
          </div>
        );
      })}
      <div className="cxd cxtot">
        <div className="cxdl"><b>Predicted net</b><span className="note">P10{'\u2013'}P90 {money(r.p10)} to {money(r.p90)} {'\u00b7'} confidence {confidence(a, r).toLowerCase()}</span></div>
        <div></div><b className="num cxda">{money(r.net)}</b>
      </div>
    </>
  );
}