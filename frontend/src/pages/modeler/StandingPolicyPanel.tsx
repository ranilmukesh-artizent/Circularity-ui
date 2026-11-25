import { Suspense, useState } from 'react';
import { can } from '../../api/session';
import {
  approveStandingPolicy, listStandingPolicies, retireStandingPolicy, saveStandingPolicy, submitStandingPolicy,
  type StandingPolicy, type StandingRules, type StandingStatus,
} from '../../api/standingPolicy'; // prettier-ignore
import type { ActionResult, ModelerScreen } from '../../api/types';
import { Panel } from '../../components/kit/Panel';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

const STATUS: Record<StandingStatus, string> = { draft: 'Draft', review: 'In review', active: 'In force', retired: 'Retired' };
const MIN_REASON = 15;
const money = (n: number) => '$' + n.toLocaleString('en-US', { maximumFractionDigits: 2 });

/** One line of what a policy covers, e.g. "Up to $500 at 0.75 confidence or better · routes: redeploy". */
export const rulesLine = (r: StandingRules): string =>
  [`Up to ${money(r.max_value)} at ${r.min_confidence.toFixed(2)} confidence or better`]
    .concat((['routes', 'classes', 'markets'] as const).flatMap((k) => (r[k]?.length ? [`${k}: ${r[k]?.join(', ')}`] : [])))
    .join(' · ');

const list = (raw: string): string[] | null => {
  const xs = raw.split(',').map((x) => x.trim()).filter(Boolean);
  return xs.length ? xs : null;
};

/**
 * Standing policies (plan 9, P9-2.5, story X-05): below its limits a decision is approved by a policy a person owns. The shown
 * pack and org (like the flow above): draft the limits, owner and routes and submit; a different person approves or retires it
 * (maker-checker). Refusals (maker-checker, the pack's or the owner's threshold) show under the buttons. The case History
 * reads "Approved by policy SP-1 v1, owner admin". Shown to those who may draft or approve a policy.
 */
export function StandingPolicyPanel({ s }: { s: ModelerScreen }) {
  if (!can('manageStandingPolicy') && !can('approve.standingPolicy')) return null;
  return (
    <Suspense fallback={<p className="note">Loading standing policies.</p>}>
      <Policies pack={s.overlay.pack_key} org={s.overlay.org_unit_id} />
    </Suspense>
  );
}

function Policies({ pack, org }: { pack: string; org: string }) {
  const l = listStandingPolicies(pack, org);
  const action = useAction();
  const [err, setErr] = useState('');
  const [retiring, setRetiring] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const go = async (call: () => Promise<ActionResult<{ log?: string }>>) => {
    setErr('');
    const r = await action.run(call, { all: setErr, ms: 4200 });
    if (r.ok && r.output.log) toast(r.output.log + '.');
    return r.ok;
  };
  const retire = async (id: string) => {
    if (await go(() => retireStandingPolicy(id, reason.trim()))) {
      setRetiring(null);
      setReason('');
    }
  };
  const inherited = l.in_force && l.in_force.org_unit_id !== org ? l.in_force : null;

  return (
    <div className="mdl-main mdl-lower" style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}>
      <Panel title="Standing policies" sub={`${org} · ${pack}: approve below the limits, owned by a person`} cls="mdl-standing">
        {inherited && <p className="note">In force here: {inherited.id} v{inherited.ver} of {inherited.org_unit_id}.</p>}
        {l.policies.length === 0 && <p className="note">No standing policy: a person approves every decision.</p>}
        <ul className="mdl-hist" data-standing-policies>
          {l.policies.map((p) => (
            <li key={p.id}>
              <b>{p.id}</b> {p.name} <span className={'pill mdl-st ' + (p.status === 'active' ? 'pub' : p.status)} data-standing-status={p.status}>{STATUS[p.status]}{p.ver ? ' · v' + p.ver : ''}</span>
              <span className="note"> {rulesLine(p.rules)} · owner {p.owner} · drafted by {p.maker}</span>
              {p.status === 'draft' && l.can.edit && <button className="btn sm pri" disabled={action.pending} onClick={() => go(() => submitStandingPolicy(p.id))}>Submit for approval</button>}
              {p.status === 'review' && l.can.approve && <button className="btn sm pri" disabled={action.pending} onClick={() => go(() => approveStandingPolicy(p.id))}>Approve</button>}
              {p.status !== 'retired' && l.can.approve && retiring !== p.id && <button className="btn sm" onClick={() => setRetiring(p.id)}>Retire</button>}
              {retiring === p.id && (
                <span className="mdl-row">
                  <label className="sr" htmlFor={'sp-reason-' + p.id}>Reason</label>
                  <input id={'sp-reason-' + p.id} value={reason} placeholder="Why (15 characters or more)" style={{ width: 260 }} onChange={(e) => setReason(e.target.value)} />
                  <button className="btn sm" disabled={action.pending || reason.trim().length < MIN_REASON} onClick={() => retire(p.id)}>Retire</button>
                  <button className="btn sm ghost" onClick={() => setRetiring(null)}>Cancel</button>
                </span>
              )}
            </li>
          ))}
        </ul>
        {err && <p className="mdl-msg blk" role="alert" data-standing-refusal>{err}</p>}
        {l.can.edit && <Draft pack={pack} org={org} limit={l.pack_limit} threshold={l.threshold} busy={action.pending} existing={l.policies} onSave={go} />}
      </Panel>
    </div>
  ); // prettier-ignore
}

function Draft({ pack, org, limit, threshold, busy, existing, onSave }: {
  pack: string; org: string; limit: number | null; threshold: number; busy: boolean; existing: StandingPolicy[];
  onSave: (call: () => Promise<ActionResult<{ log?: string }>>) => Promise<boolean>;
}) { // prettier-ignore
  const [name, setName] = useState('');
  const [max, setMax] = useState('');
  const [conf, setConf] = useState(String(threshold));
  const [owner, setOwner] = useState('');
  const [routes, setRoutes] = useState('');
  const value = Number(max);
  const confidence = Number(conf);
  const tooBig = limit !== null && max.trim() !== '' && value > limit;
  const ready = name.trim() !== '' && owner.trim() !== '' && max.trim() !== '' && value > 0 && conf.trim() !== '' && !Number.isNaN(confidence) && !tooBig;
  const taken = existing.some((p) => p.status === 'draft' || p.status === 'review');
  return (
    <div className="mdl-prop" data-standing-draft>
      <span className="label">Draft a policy{taken ? ' (another is already waiting)' : ''}</span>
      <div className="mdl-row">
        <label className="sr" htmlFor="sp-name">Name</label>
        <input id="sp-name" value={name} placeholder="Name" style={{ width: 150 }} onChange={(e) => setName(e.target.value)} />
        <label className="sr" htmlFor="sp-max">Largest value in dollars</label>
        <input id="sp-max" type="number" min="0" step="any" value={max} placeholder={limit === null ? 'Up to ($)' : `Up to ($, at most ${money(limit)})`} style={{ width: 170 }} onChange={(e) => setMax(e.target.value)} />
        <label className="sr" htmlFor="sp-conf">Lowest confidence</label>
        <input id="sp-conf" type="number" min="0" max="1" step="0.01" value={conf} style={{ width: 80 }} onChange={(e) => setConf(e.target.value)} />
        <label className="sr" htmlFor="sp-owner">Owner</label>
        <input id="sp-owner" value={owner} placeholder="Owner (account id)" style={{ width: 150 }} onChange={(e) => setOwner(e.target.value)} />
        <label className="sr" htmlFor="sp-routes">Routes</label>
        <input id="sp-routes" value={routes} placeholder="Routes (all if empty)" style={{ width: 160 }} onChange={(e) => setRoutes(e.target.value)} />
        <button
          className="btn sm pri"
          disabled={busy || !ready}
          onClick={async () =>
            (await onSave(() => saveStandingPolicy({ pack, org, name: name.trim(), owner: owner.trim(), rules: { max_value: value, min_confidence: confidence, routes: list(routes), classes: null, markets: null } }))) &&
            (setName(''), setMax(''), setRoutes(''))
          }
        >Save draft</button>
      </div>
      {tooBig && <p className="mdl-msg blk" role="alert" style={{ margin: 0 }}>The policy cannot approve above the pack&apos;s {money(limit ?? 0)} threshold.</p>}
    </div>
  ); // prettier-ignore
}
