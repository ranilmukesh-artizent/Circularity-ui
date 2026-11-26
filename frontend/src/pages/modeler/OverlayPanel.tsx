import { useState } from 'react';
import { approveOverlay, rebaseOverlay, rejectOverlay, saveOverlay, submitOverlay } from '../../api/modeler';
import type { ActionResult, GuardrailStage, ModelerScreen, OverlayCond, OverlayConflict, OverlayOp, OverlayScreen } from '../../api/types';
import { Panel } from '../../components/kit/Panel';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { guardrailControls, nextOpId, opLabel, STAGE_LABEL, tightenable, weakens, withApprover, withTighten } from './overlay';

const STATUS: Record<OverlayScreen['status'], string> = { none: 'No overlay yet', draft: 'Draft', review: 'In review', pub: 'Published' };
const MIN_REASON = 15;
const CMP: OverlayCond['op'][] = ['eq', 'ne', 'in', 'gte', 'lte', 'exists'];

const factValue = (op: OverlayCond['op'], raw: string): unknown => {
  if (op === 'exists') return true;
  if (op === 'in') return raw.split(',').map((x) => x.trim());
  return raw.trim() !== '' && !Number.isNaN(Number(raw)) ? Number(raw) : raw.trim();
};

/**
 * The Customer layer (plan 9, P9-1.3, story X-04): the shown org's changes to the pack. A customer may only tighten:
 * the server refuses a weakening and a shortcut that skips a compliance guardrail (its text is shown here), and a
 * different person approves the overlay (maker-checker). After a newer pack version, "Rebase" moves the changes over
 * and lists what a person must decide.
 */
export function OverlayPanel({ s }: { s: ModelerScreen }) {
  const o = s.overlay;
  const action = useAction();
  const [err, setErr] = useState('');
  const [returning, setReturning] = useState(false);
  const [reason, setReason] = useState('');
  const editing = o.can.edit && o.status !== 'review';

  const go = async (call: () => Promise<ActionResult<{ log?: string }>>) => {
    setErr('');
    const r = await action.run(call, { inline: setErr, ms: 4200 });
    if (r.ok && r.output.log) toast(r.output.log + '.');
    return r.ok;
  };
  const save = (ops: OverlayOp[], resolved?: string[]) => go(() => saveOverlay(o.pack_key, o.org_unit_id, ops, resolved));
  const giveBack = async () => {
    if (await go(() => rejectOverlay(o.pack_key, o.org_unit_id, reason.trim()))) {
      setReturning(false);
      setReason('');
    }
  };

  return (
    <Panel title="Customer layer" sub={`${o.org_unit_id} · ${o.pack_key} v${o.pack_version}: tighten only`} cls="mdl-overlay"
           right={<span className={'pill mdl-st ' + (o.status === 'none' ? 'draft' : o.status)} data-overlay-status={o.status}>{STATUS[o.status]}{o.ver ? ' · v' + o.ver : ''}</span>}>
      <div className="mdl-row">
        {o.can.edit && o.status === 'draft' && <button className="btn sm pri" disabled={action.pending} onClick={() => go(() => submitOverlay(o.pack_key, o.org_unit_id))}>Submit for approval</button>}
        {o.can.approve && o.status === 'review' && <button className="btn sm pri" disabled={action.pending} onClick={() => go(() => approveOverlay(o.pack_key, o.org_unit_id))}>Approve</button>}
        {o.can.approve && o.status === 'review' && !returning && <button className="btn sm" onClick={() => setReturning(true)}>Return to draft</button>}
        {o.can.edit && o.stale && o.status !== 'none' && o.status !== 'review' && (
          <button className="btn sm" disabled={action.pending} onClick={() => go(() => rebaseOverlay(o.pack_key, o.org_unit_id))}>Rebase onto v{o.pack_version}</button>
        )}
        {o.in_force && o.in_force.org_unit_id !== o.org_unit_id && <span className="note">In force here: the overlay of {o.in_force.org_unit_id}.</span>}
      </div>
      {returning && (
        <span className="mdl-row">
          <label className="sr" htmlFor="mdl-ov-reason">Reason</label>
          <input id="mdl-ov-reason" value={reason} placeholder="Why it goes back (15 characters or more)" style={{ width: 280 }} onChange={(e) => setReason(e.target.value)} />
          <button className="btn sm" disabled={action.pending || reason.trim().length < MIN_REASON} onClick={giveBack}>Return</button>
          <button className="btn sm ghost" onClick={() => setReturning(false)}>Cancel</button>
        </span>
      )}
      {o.notes.map((n, i) => <p key={i} className="note" data-overlay-note>{n}</p>)}
      <Conflicts o={o} busy={action.pending || !editing} onKeep={(c) => c.op && save([...o.ops, keepMine(c.op, c.theirs)], [c.op_id])} onTake={(c) => save(o.ops, [c.op_id])} />
      <h4>Changes</h4>
      {o.ops.length === 0 && <p className="note">No changes: this org uses the pack as published.</p>}
      <ul className="mdl-hist" data-overlay-ops>
        {o.ops.map((op) => (
          <li key={op.id}>
            {opLabel(op)} <span className="note">· {op.by || o.maker || '—'} · {STATUS[o.status]}</span>
            {editing && <button className="btn sm ghost" disabled={action.pending} onClick={() => save(o.ops.filter((x) => x.id !== op.id))}>Remove</button>}
          </li>
        ))}
      </ul>
      {err && <p className="mdl-msg blk" role="alert" data-overlay-refusal>{err}</p>}
      <GuardrailList o={o} busy={action.pending || !editing} onSave={save} />
      {editing && <TightenForm o={o} busy={action.pending} onSave={save} />}
      {editing && <DiversionForm o={o} busy={action.pending} onSave={save} />}
    </Panel>
  ); // prettier-ignore
}

/** "Keep mine": the operation again, against the pack's new value. */
const keepMine = (op: OverlayOp, theirs: unknown): OverlayOp => (op.op === 'set_param' && typeof theirs === 'number' ? { ...op, seen: theirs } : op);

function Conflicts({ o, busy, onKeep, onTake }: { o: OverlayScreen; busy: boolean; onKeep: (c: OverlayConflict) => void; onTake: (c: OverlayConflict) => void }) {
  if (!o.conflicts.length) return null;
  return (
    <div className="mdl-prop" data-overlay-conflicts>
      <span className="label">Needs a person</span>
      {o.conflicts.map((c) => (
        <div key={c.op_id} className="mdl-row">
          <span>{c.message}</span>
          {c.kind === 'changed_by_pack' && <button className="btn sm" disabled={busy} onClick={() => onKeep(c)}>Keep mine</button>}
          <button className="btn sm" disabled={busy} onClick={() => onTake(c)}>Take the pack&apos;s</button>
        </div>
      ))}
    </div>
  );
}

/**
 * The pack's guardrails with their customer controls (UC-17): a locked guardrail shows threshold, scope, exception and
 * suspend-until disabled (the server answers `locked_guardrail`); every guardrail takes an extra approver.
 */
function GuardrailList({ o, busy, onSave }: { o: OverlayScreen; busy: boolean; onSave: (ops: OverlayOp[]) => Promise<boolean> }) {
  const [roles, setRoles] = useState<Record<string, string>>({});
  return (
    <div className="mdl-prop" data-overlay-guardrails>
      <span className="label">Guardrails</span>
      {o.guardrails.map((g) => {
        const c = guardrailControls(g);
        const role = roles[g.id] ?? '';
        return (
          <div key={g.id} className="mdl-row" data-overlay-guardrail={g.id}>
            <span>{g.id}: {g.text}{g.locked ? ' (locked by the pack)' : ''}</span>
            {c.fields.map((f) => (
              <label key={f.label} className="note">{f.label} <input type="checkbox" disabled={f.disabled || busy} aria-label={`${g.id} ${f.label}`} /></label>
            ))}
            <label className="sr" htmlFor={`mdl-ov-ap-${g.id}`}>Approver role for {g.id}</label>
            <input id={`mdl-ov-ap-${g.id}`} value={role} placeholder="approver role" style={{ width: 120 }} onChange={(e) => setRoles({ ...roles, [g.id]: e.target.value })} />
            <button className="btn sm" disabled={busy || !c.addApprover || role.trim() === ''}
                    onClick={async () => (await onSave(withApprover(o.ops, g, role))) && setRoles({ ...roles, [g.id]: '' })}>Add approver</button>
          </div>
        );
      })}
    </div>
  );
}

interface FormProps {
  o: OverlayScreen;
  busy: boolean;
  onSave: (ops: OverlayOp[]) => Promise<boolean>;
}

function TightenForm({ o, busy, onSave }: FormProps) {
  const gs = tightenable(o.guardrails);
  const [id, setId] = useState(gs[0]?.id ?? '');
  const [raw, setRaw] = useState('');
  const g = gs.find((x) => x.id === id);
  if (!g) return null;
  const value = Number(raw);
  const refusal = raw.trim() === '' || Number.isNaN(value) ? null : weakens(g, value);
  return (
    <div className="mdl-prop" data-overlay-tighten>
      <span className="label">Tighten a guardrail</span>
      <div className="mdl-row">
        <label className="sr" htmlFor="mdl-ov-g">Guardrail</label>
        <select id="mdl-ov-g" value={id} onChange={(e) => { setId(e.target.value); setRaw(''); }}>
          {gs.map((x) => <option key={x.id} value={x.id}>{x.id}: {x.text} ({x.field} {x.value})</option>)}
        </select>
        <label className="sr" htmlFor="mdl-ov-v">New {g.field}</label>
        <input id="mdl-ov-v" type="number" step="any" value={raw} placeholder={`${g.field}, ${g.stricter} is stricter`} style={{ width: 150 }} onChange={(e) => setRaw(e.target.value)} />
        <button className="btn sm pri" disabled={busy || raw.trim() === '' || Number.isNaN(value) || refusal !== null}
                onClick={async () => (await onSave(withTighten(o.ops, g, value))) && setRaw('')}>Save</button>
      </div>
      {refusal && <p className="mdl-msg blk" role="alert" style={{ margin: 0 }}>{refusal}</p>}
    </div>
  );
}

function DiversionForm({ o, busy, onSave }: FormProps) {
  const [stage, setStage] = useState<GuardrailStage>('condition');
  const [kind, setKind] = useState<'step' | 'shortcut'>('step');
  const [fact, setFact] = useState('');
  const [cmp, setCmp] = useState<OverlayCond['op']>('eq');
  const [val, setVal] = useState('');
  const [step, setStep] = useState('');
  const [owner, setOwner] = useState('');
  const [to, setTo] = useState('');
  const later = o.stages.slice(o.stages.findIndex((x) => x.key === stage) + 1);
  const when: OverlayCond[] = fact.trim() ? [{ fact: fact.trim(), op: cmp, value: factValue(cmp, val) }] : [];
  const ready = kind === 'step' ? step.trim() !== '' && owner.trim() !== '' : to !== '';
  const make = (): OverlayOp => {
    const base = { id: nextOpId(o.ops), by: '', note: '', stage, when };
    return kind === 'step' ? { ...base, op: 'add_step', step: step.trim(), owner_role: owner.trim() } : { ...base, op: 'shortcut', to };
  };
  return (
    <div className="mdl-prop" data-overlay-diversion>
      <span className="label">Add a diversion</span>
      <div className="mdl-row">
        <label className="sr" htmlFor="mdl-ov-stage">Stage</label>
        <select id="mdl-ov-stage" value={stage} onChange={(e) => { setStage(e.target.value as GuardrailStage); setTo(''); }}>
          {o.stages.map((x) => <option key={x.key} value={x.key}>{STAGE_LABEL[x.key]}</option>)}
        </select>
        <label className="sr" htmlFor="mdl-ov-fact">Condition fact</label>
        <input id="mdl-ov-fact" value={fact} placeholder="when this fact (optional)" style={{ width: 150 }} onChange={(e) => setFact(e.target.value)} />
        <label className="sr" htmlFor="mdl-ov-cmp">Operator</label>
        <select id="mdl-ov-cmp" value={cmp} onChange={(e) => setCmp(e.target.value as OverlayCond['op'])}>{CMP.map((c) => <option key={c} value={c}>{c}</option>)}</select>
        {cmp !== 'exists' && <><label className="sr" htmlFor="mdl-ov-val">Value</label><input id="mdl-ov-val" value={val} placeholder="value" style={{ width: 100 }} onChange={(e) => setVal(e.target.value)} /></>}
      </div>
      <div className="mdl-row">
        <label className="sr" htmlFor="mdl-ov-kind">Kind</label>
        <select id="mdl-ov-kind" value={kind} onChange={(e) => setKind(e.target.value as 'step' | 'shortcut')}>
          <option value="step">Extra step</option>
          <option value="shortcut">Shortcut</option>
        </select>
        {kind === 'step' ? (
          <>
            <label className="sr" htmlFor="mdl-ov-step">Step</label>
            <input id="mdl-ov-step" value={step} placeholder="step, e.g. Second grading check" style={{ width: 220 }} onChange={(e) => setStep(e.target.value)} />
            <label className="sr" htmlFor="mdl-ov-owner">Owner role</label>
            <input id="mdl-ov-owner" value={owner} placeholder="owner role" style={{ width: 110 }} onChange={(e) => setOwner(e.target.value)} />
          </>
        ) : (
          <>
            <label className="sr" htmlFor="mdl-ov-to">Go to</label>
            <select id="mdl-ov-to" value={to} onChange={(e) => setTo(e.target.value)}>
              <option value="">Go to…</option>
              {later.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
              {o.routes.map((r) => <option key={r.id} value={r.id}>Route: {r.name}</option>)}
            </select>
          </>
        )}
        <button className="btn sm pri" disabled={busy || !ready} onClick={() => onSave([...o.ops, make()])}>Save</button>
      </div>
    </div>
  );
}
