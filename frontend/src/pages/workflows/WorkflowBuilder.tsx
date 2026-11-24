/**
 * Build with AI (Workflow Studio): describe a workflow, answer the follow-up questions, review the plan, create it.
 * The planner (workflow.plan) only proposes; Create workflow is the person's own click (workflow.create, then
 * workflow.save with the settings), with their permissions. Nothing is created before that click.
 */
import { useEffect, useReducer, useRef, type FormEvent } from 'react';
import {
  builderReducer, createFromPlan, current, EXAMPLES, formComplete, initialBuilder, nextAnswers, planWorkflow, toggled,
  type Answers, type BuilderState, type Plan, type Question,
} from '../../api/workflowBuilder';
import { Icon } from '../../components/Icon';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { refused } from '../../hooks/useAction';
import { ModelerLink } from './WorkflowModals';

export function WorkflowBuilder({ initialPrompt = '', onClose, onCreated }: { initialPrompt?: string; onClose: () => void; onCreated: (id: string) => void }) {
  const [s, dispatch] = useReducer(builderReducer, initialPrompt, initialBuilder);
  const reply = current(s);
  const started = useRef(false);

  async function ask(answers: Answers, prompt = s.prompt) {
    if (!prompt.trim()) return;
    dispatch({ t: 'start' });
    try {
      const r = await planWorkflow(prompt.trim(), answers);
      dispatch({ t: 'reply', sent: answers, reply: r });
    } catch (e) {
      dispatch({ t: 'fail', message: (e as Error).message });
    }
  }
  // a prompt handed in (Ask's "Refine in Workflow Studio", ?build=) starts at once
  useEffect(() => {
    if (initialPrompt.trim() && !started.current) {
      started.current = true;
      void ask({}, initialPrompt);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function create(plan: Plan) {
    dispatch({ t: 'start' });
    const r = await createFromPlan(plan);
    if (refused(r, 5200)) return dispatch({ t: 'fail', message: r.error.message });
    toast(`${r.output.name} created as a draft from your description. Check it, then Publish.`);
    onCreated(r.output.id);
  }

  const submitPrompt = (e: FormEvent) => {
    e.preventDefault();
    void ask({});
  };
  const plan = reply?.status === 'ready' ? reply.plan : null;
  const qs = reply?.status === 'questions' ? reply.questions : [];

  const foot = (
    <>
      {s.rounds.length > 0 && <button className="btn ghost" onClick={() => dispatch({ t: 'back' })} disabled={s.busy}><Icon name="back" /> Back</button>}
      <span className="grow" />
      <button className="btn ghost" onClick={onClose}>Cancel</button>
      {!reply && <button className="btn pri" onClick={() => void ask({})} disabled={s.busy || !s.prompt.trim()}><Icon name="spark" /> Plan it</button>}
      {qs.length > 0 && <>
        <button className="btn" onClick={() => void ask({ ...nextAnswers(s), _defaults: true })} disabled={s.busy}>Use defaults for the rest</button>
        <button className="btn pri" onClick={() => void ask(nextAnswers(s))} disabled={s.busy || !formComplete(qs, s.form)}>Continue</button>
      </>}
      {plan && <button className="btn pri" onClick={() => void create(plan)} disabled={s.busy}><Icon name="plus" /> Create workflow</button>}
    </>
  );

  return (
    <Modal title="Build a workflow with AI" wide onClose={onClose} foot={foot}>
      <form onSubmit={submitPrompt} className="fld">
        <label htmlFor="wbPrompt">Describe the workflow</label>
        <textarea id="wbPrompt" value={s.prompt} maxLength={2000} rows={3} readOnly={s.rounds.length > 0}
          placeholder="For example: ingest from Salesforce with currency conversion and de-duplication, every 30 minutes"
          onChange={(e) => dispatch({ t: 'prompt', prompt: e.target.value })}
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void ask({}); } }} />
        {s.rounds.length > 0
          ? <div className="hint"><button type="button" className="lnk" onClick={() => dispatch({ t: 'restart' })}><Icon name="edit" /> Edit the description and start again</button></div>
          : <div className="hint">Name the system, the steps you need (currency, units, UTC timestamps, de-duplication, lookups, filters …) and when it should run. Ctrl+Enter plans it.</div>}
      </form>
      {!reply && (
        <div>
          <p className="note" style={{ margin: '0 0 6px' }}>Try one of these:</p>
          <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
            {EXAMPLES.map((x) => <button key={x} className="btn sm" onClick={() => { dispatch({ t: 'prompt', prompt: x }); void ask({}, x); }}>{x}</button>)}
          </div>
        </div>
      )}
      {s.busy && <p className="note" aria-live="polite"><span className="afdots">Working…</span></p>}
      {s.error && <p className="callout bad" role="alert">{s.error}</p>}
      {reply && <Understood s={s} onEdit={(slot) => dispatch({ t: 'edit', slot })} />}
      {reply && !reply.redirect && reply.notes.length > 0 && <div className="callout" role="note" style={{ margin: '10px 0' }}>{reply.notes.map((n, i) => <p key={i} style={{ margin: i ? '4px 0 0' : 0 }}>{n}</p>)}</div>}
      {qs.length > 0 && <Questions qs={qs} form={s.form} set={(id, value) => dispatch({ t: 'set', id, value })} />}
      {plan && <PlanView plan={plan} />}
      {reply?.redirect && <RedirectNote reason={reply.redirect.reason} />}
      {reply?.status === 'blocked' && !reply.redirect && <p className="callout bad">The plan would not pass its checks. Go back and change an answer, or edit the description.</p>}
      <p className="note" style={{ marginTop: 12 }}>The assistant only proposes. Nothing is created until you press Create workflow; the new workflow starts as a draft and is never published for you.</p>
    </Modal>
  );
}

/** A decision sentence: the planner builds no draft and points to the Modeler (P9-0.16). */
export function RedirectNote({ reason }: { reason: string }) {
  return (
    <div className="callout" role="note" data-testid="wbRedirect">
      <p style={{ margin: 0 }}>{reason}</p>
      <p style={{ margin: '6px 0 0' }}><ModelerLink /></p>
    </div>
  );
}

/** What the assistant took from the description and the answers so far; an answered slot can be reopened. */
function Understood({ s, onEdit }: { s: BuilderState; onEdit: (slot: string) => void }) {
  const r = current(s);
  if (!r || !r.understood.length) return null;
  const asked = new Set(s.rounds.slice(0, -1).flatMap((x) => x.reply.questions.map((q) => q.id)));
  return (
    <div style={{ margin: '4px 0 10px' }} aria-label="Understood so far">
      <b style={{ fontSize: 12.5 }}>Understood</b>
      <div className="row" style={{ flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
        {r.understood.map((u, i) => (
          <span key={i} className="chip line" title={u.from === 'prompt' ? 'From your description' : 'Your answer'}>
            {u.label}: {u.value}
            {u.from === 'answer' && asked.has(u.slot) && (
              <button className="lnk" style={{ marginLeft: 6 }} aria-label={'Change ' + u.label} onClick={() => onEdit(u.slot)}>Change</button>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

function Questions({ qs, form, set }: { qs: Question[]; form: Answers; set: (id: string, v: Answers[string]) => void }) {
  return (
    <div className="methodbox" aria-label="Questions">
      {qs.map((q) => {
        const fid = 'wbq_' + q.id;
        const v = form[q.id];
        if (q.kind === 'text')
          return (
            <div className="fld" key={q.id}>
              <label htmlFor={fid}>{q.text}</label>
              <input id={fid} value={String(v ?? '')} maxLength={80} placeholder={String(q.default ?? '')} onChange={(e) => set(q.id, e.target.value)} />
              {q.note && <div className="hint">{q.note}</div>}
            </div>
          );
        if (q.multi)
          return (
            <fieldset className="fld" key={q.id} style={{ border: 0, padding: 0, margin: '0 0 14px' }}>
              <legend style={{ fontWeight: 600, fontSize: 12.5, marginBottom: 5 }}>{q.text}</legend>
              {q.note && <div className="hint" style={{ marginBottom: 6 }}>{q.note}</div>}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '4px 14px' }}>
                {q.choices.map((c) => {
                  const on = Array.isArray(v) && v.includes(c.value);
                  return (
                    <label key={String(c.value)} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontWeight: 400 }} title={c.hint}>
                      <input type="checkbox" checked={on} style={{ width: 'auto', marginTop: 3 }} onChange={(e) => set(q.id, toggled(v, c.value, e.target.checked))} />
                      <span><b>{c.label}</b>{c.hint && <span className="note" style={{ display: 'block' }}>{c.hint}</span>}</span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          );
        if (q.choices.length > 6)
          return (
            <div className="fld" key={q.id}>
              <label htmlFor={fid}>{q.text}</label>
              {q.note && <div className="hint" style={{ marginBottom: 6 }}>{q.note}</div>}
              <select id={fid} value={String(v ?? '')} onChange={(e) => {
                const c = q.choices.find((x) => String(x.value) === e.target.value);
                if (c) set(q.id, c.value);
              }}>
                {q.choices.map((c) => <option key={String(c.value)} value={String(c.value)}>{c.label}{c.hint ? ' · ' + c.hint : ''}</option>)}
              </select>
            </div>
          );
        return (
          <div className="fld" key={q.id} role="radiogroup" aria-labelledby={fid}>
            <label id={fid}>{q.text}</label>
            {q.note && <div className="hint" style={{ marginBottom: 6 }}>{q.note}</div>}
            <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
              {q.choices.map((c) => {
                const on = v === c.value;
                return (
                  <button key={String(c.value)} type="button" role="radio" aria-checked={on} className={'btn sm' + (on ? ' pri' : '')} title={c.hint} onClick={() => set(q.id, c.value)}>
                    {c.label}
                  </button>
                );
              })}
            </div>
            {q.choices.find((c) => c.value === v)?.hint && <div className="hint">{q.choices.find((c) => c.value === v)?.hint}</div>}
          </div>
        );
      })}
    </div>
  );
}

function PlanView({ plan }: { plan: Plan }) {
  return (
    <section aria-label="The plan">
      <h3 style={{ margin: '6px 0 2px' }}>{plan.name}</h3>
      <p className="note" style={{ margin: '0 0 8px' }}>{plan.type_label} · {plan.trigger_text} · owner {plan.owner}{plan.type !== 'blank' ? ` · ${plan.settings.retries} retries · alert when ${plan.settings.alert.toLowerCase()}` : ''}</p>
      <p style={{ margin: '0 0 10px' }}>{plan.desc}</p>
      <div className="callout ok" style={{ marginBottom: 10 }}>
        <b>Checks: 0 errors</b>{plan.checks.warnings.length ? `, ${plan.checks.warnings.length} warning${plan.checks.warnings.length > 1 ? 's' : ''}` : ''}.
        {[...plan.checks.warnings, ...plan.checks.notes].map((w, i) => <div key={i} className="note">{w}</div>)}
      </div>
      <Diff plan={plan} />
      <GraphPreview plan={plan} />
      <h4 style={{ margin: '12px 0 4px' }}>Every step, in run order</h4>
      <ol className="afplan afwf">
        {plan.steps.map((st) => (
          <li key={st.id} className={st.status === 'added' ? 'ghost' : st.fixed ? 'fx' : ''}>
            <b>{st.label}{st.status === 'added' && <span className="chip ok" style={{ marginLeft: 6 }}>You asked for it</span>}</b>
            <span className="note">{st.why}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Diff({ plan }: { plan: Plan }) {
  const d = plan.diff;
  return (
    <div className="tw" style={{ marginBottom: 10 }}>
      <table className="t static tight" aria-label="What the workflow contains">
        <thead><tr><th>What it contains</th><th /></tr></thead>
        <tbody>
          <tr><td>Required to run</td><td>{d.required.join(', ')}</td></tr>
          <tr><td>You asked for</td><td>{d.added.length ? d.added.join(', ') : 'Nothing extra: add blocks from the palette after you create it'}</td></tr>
          {d.changed.map((c, i) => <tr key={i}><td>{i === 0 ? 'Settings' : ''}</td><td>{c}</td></tr>)}
        </tbody>
      </table>
    </div>
  );
}

/** A small read-only drawing of the graph: steps where the canvas will put them, added ones dashed. */
function GraphPreview({ plan }: { plan: Plan }) {
  const g = plan.graph;
  if (!g.nodes.length) return null;
  const W = 176, H = 62;
  const minX = Math.min(...g.nodes.map((n) => n.x)), minY = Math.min(...g.nodes.map((n) => n.y));
  const maxX = Math.max(...g.nodes.map((n) => n.x)) + W, maxY = Math.max(...g.nodes.map((n) => n.y)) + H;
  const by = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const st = Object.fromEntries(plan.steps.map((x) => [x.id, x]));
  return (
    <div style={{ overflowX: 'auto', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--panel2)', padding: 8 }}>
      <svg role="img" aria-label={'Workflow graph: ' + plan.steps.map((x) => x.label).join(', ')} viewBox={`${minX - 10} ${minY - 10} ${maxX - minX + 20} ${maxY - minY + 20}`}
        style={{ width: '100%', minWidth: 560, height: 'auto', display: 'block' }}>
        {g.edges.map((e) => {
          const a = by[e.a], b = by[e.b];
          if (!a || !b) return null;
          const sx = a.x + W, sy = a.y + H / 2, tx = b.x, ty = b.y + H / 2, mx = (sx + tx) / 2;
          return <path key={e.id} d={`M${sx},${sy} C${mx},${sy} ${mx},${ty} ${tx},${ty}`} fill="none" stroke="var(--muted)" strokeWidth={2} />;
        })}
        {g.nodes.map((n) => {
          const x = st[n.id];
          const added = x?.status === 'added', fixed = x?.fixed;
          return (
            <g key={n.id}>
              <rect x={n.x} y={n.y} width={W} height={H} rx={8} fill={fixed ? 'var(--panel2)' : 'var(--panel)'} stroke={added ? 'var(--ink)' : 'var(--line)'}
                strokeWidth={added ? 2 : 1.5} strokeDasharray={added ? '6 4' : undefined} />
              <text x={n.x + 12} y={n.y + 27} fontSize={14} fontWeight={600} fill="var(--ink)">{(x?.label ?? n.ref).slice(0, 22)}</text>
              <text x={n.x + 12} y={n.y + 47} fontSize={11.5} fill="var(--muted)">{fixed ? 'Fixed step' : added ? 'You asked for it' : n.k === 'conn' ? 'Source' : n.k === 'wconn' ? 'Target' : 'Required'}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
