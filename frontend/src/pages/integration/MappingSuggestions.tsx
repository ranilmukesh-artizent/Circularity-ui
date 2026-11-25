/* Suggested field mappings for a source (plan 9, P9-8.2 and P9-8.4, registry entry I-19): "Suggest mappings" in the Data Mapping tab
   profiles the sample the source landed (up to 500 records per resource) and proposes a canonical field for each source field, with
   a calibrated confidence, a band and a reason. Nothing is pre-ticked: a person makes one of five choices per row (Accept, Choose
   another field, Accept with a conversion, Not needed, Ask the owner), and "Save mapping" applies the accepted rows as a new mapping
   version. A question to the system owner holds the save until they answer. Sample values are masked by the server before they
   reach this table, and the model's own number is never shown as confidence. */
import { useState } from 'react';
import {
  answerOwner, applyMappings, askOwner, decideMapping, suggestFieldMappings,
  type AppliedRow, type MappingBand, type MappingChoiceAnswer, type MappingChoiceInput, type MappingSuggestion, type MappingSuggestions,
} from '../../api/integration';
import type { ActionResult } from '../../api/types';
import { StatusPill } from '../../components/kit/StatusPill';
import { toast } from '../../components/toast';
import { refused } from '../../hooks/useAction';

const BAND: Record<MappingBand, [string, string]> = { pre_ticked: ['Pre-ticked', 'ok'], check: ['Check', 'warn'], none: ['No proposal', 'line'] };
const pct = (c: number) => Math.round(c * 100) + '%';
/** Conversions the server's `parse_rule` accepts (backend/di/connectors/mapping.py). */
const CONVERSIONS = ['number', 'int', 'upper', 'lower', 'date', 'utc', 'units:lb>kg', 'units:kg>lb', 'units:g>kg', 'units:kg>t', 'units:in>cm', 'units:cm>in', 'units:ft>m', 'units:m>ft', 'units:f>c', 'units:c>f', 'units:gal>l', 'units:l>gal', 'fx:USD', 'fx:EUR'];

/** What the person chose for a row, as the table shows it (the server's `decision` plus the answer's converted values). */
interface Choice { id: number; decision: string; target: string | null; rule: string | null; owner: string | null; reason: string | null; values?: MappingChoiceAnswer['values']; warning?: string }
const keyOf = (x: MappingSuggestion) => x.resource + '/' + x.field;

export function MappingSuggestions({ sourceId }: { sourceId: string }) {
  const [state, setState] = useState<'idle' | 'running' | MappingSuggestions | { fail: string }>('idle');
  async function run() {
    setState('running');
    const r = await suggestFieldMappings(sourceId);
    if (refused(r)) return setState({ fail: r.error.message });
    setState(r.output);
  }
  return (
    <div style={{ marginBottom: 12 }}>
      <div className="row" style={{ gap: 10, alignItems: 'center' }}>
        <button className="btn sm" onClick={run} disabled={state === 'running'}>Suggest mappings</button>
        <span className="note">Proposes a canonical field for each field in the sample. You choose; nothing is saved until you save the mapping.</span>
      </div>
      {state === 'running' && <div className="note"><span className="spin" /> Profiling the sample…</div>}
      {typeof state === 'object' && 'fail' in state && <div className="err">{state.fail}</div>}
      {typeof state === 'object' && 'rows' in state && <Result sourceId={sourceId} r={state} />}
    </div>
  );
}

function Result({ sourceId, r }: { sourceId: string; r: MappingSuggestions }) {
  const [choices, setChoices] = useState<Record<string, Choice>>(() =>
    Object.fromEntries(r.rows.filter((x) => x.decision).map((x) => [keyOf(x), x.decision as Choice])),
  );
  const [saved, setSaved] = useState<string | null>(null);
  const waiting = Object.values(choices).filter((c) => c.decision === 'asked_owner').length;
  const accepted = r.rows.flatMap((x): AppliedRow[] => {
    const c = choices[keyOf(x)];
    if (!c?.target || !['accepted', 'replaced', 'accepted_with_rule'].includes(c.decision)) return [];
    return [{ src: x.field, target: c.target, ...(c.rule ? { rule: c.rule } : {}), ...(x.resource ? { resource: x.resource } : {}) }];
  });
  const put = (x: MappingSuggestion, c: Choice) => { setSaved(null); setChoices((o) => ({ ...o, [keyOf(x)]: c })); };
  async function save() {
    const a = await applyMappings(sourceId, accepted);
    if (refused(a)) return;
    setSaved(`Saved as mapping version ${a.output.version} (${a.output.rows} rows).`);
  }
  if (!r.rows.length) return <div className="empty"><b>No sample yet</b>Sync this source once so there are records to profile.</div>;
  return (
    <>
      <div className="tw">
        <table className="t static maptbl" aria-label="Suggested field mappings">
          <thead><tr><th>Source field</th><th>Sample values</th><th>Proposed field</th><th>Confidence</th><th>Band</th><th>Reason</th><th>Your choice</th></tr></thead>
          <tbody>
            {r.rows.map((x) => {
              const [label, tone] = BAND[x.band];
              return (
                <tr key={keyOf(x)}>
                  <td className="mono">{x.field}</td>
                  <td className="mono">{x.samples.slice(0, 3).join(', ') || '—'}</td>
                  <td className="mono">
                    {x.target ?? <>No proposal{x.candidates.length > 0 && <span className="note"> · candidates: {x.candidates.map(([t, s]) => `${t} (${s.toFixed(2)})`).join(', ')}</span>}</>}
                  </td>
                  <td>{pct(x.confidence)}</td>
                  <td><StatusPill tone={tone} label={label} /></td>
                  <td>{x.reason}</td>
                  <td><Choices sourceId={sourceId} x={x} fields={r.fields} choice={choices[keyOf(x)]} onChoice={(c) => put(x, c)} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {r.gaps.length > 0 && <div className="note">Required canonical fields with no proposal: <span className="mono">{r.gaps.join(', ')}</span></div>}
      <div className="row" style={{ gap: 10, alignItems: 'center', marginTop: 8 }}>
        <button className="btn pri sm" onClick={save} disabled={waiting > 0 || accepted.length === 0}>Save mapping</button>
        {waiting > 0
          ? <span className="note">Waiting for the system owner on {waiting} field{waiting === 1 ? '' : 's'}</span>
          : <span className="note">{accepted.length} accepted row{accepted.length === 1 ? '' : 's'} will be saved as a new mapping version.</span>}
        {saved && <span className="note">{saved}</span>}
      </div>
    </>
  );
}

type Mode = null | 'other' | 'rule' | 'ask';

/** The five choices of one row, or the choice already made (with the converted samples, a blocking warning, or the open question). */
function Choices({ sourceId, x, fields, choice, onChoice }: { sourceId: string; x: MappingSuggestion; fields: string[]; choice?: Choice; onChoice: (c: Choice) => void }) {
  const [mode, setMode] = useState<Mode>(null);
  const [field, setField] = useState(x.target ?? '');
  const [rule, setRule] = useState(CONVERSIONS[0]);
  const [question, setQuestion] = useState('');
  const [again, setAgain] = useState(false);
  const base = { resource: x.resource, ...(x.target ? { proposed: x.target } : {}), confidence: x.confidence, reason: x.reason, proposed_by: x.proposed_by };

  async function decide(c: MappingChoiceInput) {
    const a = await decideMapping(sourceId, x.field, { ...base, ...c });
    if (refused(a)) return;
    onChoice({ id: a.output.id, decision: a.output.decision, target: a.output.target, rule: a.output.rule, owner: null, reason: null, values: a.output.values, warning: a.output.warning });
    setMode(null);
    setAgain(false);
  }
  async function ask() {
    const a = await askOwner(sourceId, x.field, question.trim(), x.resource);
    if (refused(a)) return;
    onChoice({ id: a.output.id, decision: 'asked_owner', target: null, rule: null, owner: a.output.owner, reason: question.trim() });
    toast(`Asked ${a.output.owner}. It is in their My work.`);
    setMode(null);
  }
  async function answer() {
    const r: ActionResult<MappingChoiceAnswer> = await answerOwner(choice!.id, { decision: 'accepted', target: field });
    if (refused(r)) return;
    onChoice({ id: r.output.id, decision: r.output.decision, target: r.output.target, rule: null, owner: choice!.owner, reason: null });
  }
  const pickField = (label: string) => (
    <select aria-label={label} value={field} onChange={(e) => setField(e.target.value)}>
      <option value="">Choose a field</option>
      {fields.map((f) => <option key={f} value={f}>{f}</option>)}
    </select>
  );

  if (choice && !again) {
    return (
      <div>
        <ChoiceText c={choice} />
        {choice.decision === 'asked_owner' ? (
          <div className="row" style={{ gap: 6 }}>{pickField('Owner answer: field')}<button className="btn sm" disabled={!field} onClick={answer}>Send answer</button></div>
        ) : <button className="btn ghost sm" onClick={() => setAgain(true)}>Change</button>}
      </div>
    );
  }
  return (
    <div>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        <button className="btn sm" disabled={!x.target} onClick={() => decide({ decision: 'accepted', target: x.target ?? undefined })}>Accept</button>
        <button className="btn sm" aria-pressed={mode === 'other'} onClick={() => setMode(mode === 'other' ? null : 'other')}>Choose another field</button>
        <button className="btn sm" aria-pressed={mode === 'rule'} onClick={() => setMode(mode === 'rule' ? null : 'rule')}>Accept with a conversion</button>
        <button className="btn sm" onClick={() => decide({ decision: 'not_needed', target: x.target ?? undefined })}>Not needed</button>
        <button className="btn sm" aria-pressed={mode === 'ask'} onClick={() => setMode(mode === 'ask' ? null : 'ask')}>Ask the owner</button>
      </div>
      {mode === 'other' && (
        <div className="row" style={{ gap: 6, marginTop: 6 }}>{pickField('Choose another field')}<button className="btn pri sm" disabled={!field} onClick={() => decide({ decision: 'replaced', target: field })}>Use this field</button></div>
      )}
      {mode === 'rule' && (
        <div className="row" style={{ gap: 6, marginTop: 6 }}>
          {pickField('Field to convert into')}
          <select aria-label="Conversion" value={rule} onChange={(e) => setRule(e.target.value)}>{CONVERSIONS.map((c) => <option key={c} value={c}>{c}</option>)}</select>
          <button className="btn pri sm" disabled={!field} onClick={() => decide({ decision: 'accepted_with_rule', target: field, rule })}>Convert and show values</button>
        </div>
      )}
      {mode === 'ask' && (
        <div className="row" style={{ gap: 6, marginTop: 6 }}>
          <input aria-label="Question for the owner" value={question} placeholder="What does this field mean?" onChange={(e) => setQuestion(e.target.value)} />
          <button className="btn pri sm" disabled={question.trim().length < 5} onClick={ask}>Send question</button>
        </div>
      )}
    </div>
  );
}

function ChoiceText({ c }: { c: Choice }) {
  const text: Record<string, string> = {
    accepted: `Accepted ${c.target}`, replaced: `Replaced with ${c.target}`, accepted_with_rule: `Accepted ${c.target} with ${c.rule}`,
    not_needed: 'Not needed', asked_owner: `Asked ${c.owner}${c.reason ? `: ${c.reason}` : ''}`,
  };
  return (
    <div>
      <span>{text[c.decision] ?? c.decision}</span>
      {c.values && c.values.length > 0 && <div className="note mono">Converted samples: {c.values.join(', ')}</div>}
      {c.warning && <div className="err">{c.warning}</div>}
    </div>
  );
}
