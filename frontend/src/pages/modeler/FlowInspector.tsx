import type { FlowGraph, FlowNode, ModelerScreen, ScopeDim } from '../../api/types';
import { LockIcon, nodeTitle, TTAG } from './FlowCanvas';
import { byStage } from './guardrails';

type Scope = NonNullable<FlowNode['scope']>;

interface Props {
  s: ModelerScreen;
  graph: FlowGraph;
  node: FlowNode | null;
  editable: boolean;
  onRule: (id: string, patch: Pick<Partial<FlowNode>, 'action' | 'path' | 'scope' | 'owner'>) => void;
  onConnect: (a: string, b: string) => void;
  onDisconnect: (edgeId: string) => void;
  onRemove: (id: string) => void;
}

const ACTIONS: [NonNullable<FlowNode['action']>, string][] = [['exclude', 'Never'], ['prefer', 'Prefer'], ['require', 'Only']];

function DimField({ d, scope, editable, set }: { d: ScopeDim; scope: Scope; editable: boolean; set: (v: Scope[string]) => void }) {
  const id = 'mdl-dim-' + d.key;
  if (d.kind !== 'set') {
    const v = scope[d.key];
    return (
      <label className="mdl-f" htmlFor={id}>
        <span>{d.label} {d.kind === 'min' ? '≥' : '<'}</span>
        <input id={id} type="number" disabled={!editable} value={v == null ? '' : String(v)} style={{ width: 90 }}
               onChange={(e) => set(e.target.value === '' ? null : Number(e.target.value))} />
      </label>
    ); // prettier-ignore
  }
  const cur = (Array.isArray(scope[d.key]) ? scope[d.key] : []) as string[];
  const toggle = (v: string) => set(cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]);
  return (
    <fieldset className="mdl-f">
      <legend>{d.label}</legend>
      <div className="mdl-chk">
        {d.values.map((v) => (
          <label key={v}>
            <input type="checkbox" disabled={!editable} checked={cur.includes(v)} onChange={() => toggle(v)} /> {v}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** The inspector (the prototype's inspector()): a rule's action, path, scope and owner; other steps read-only. */
export function FlowInspector({ s, graph, node, editable, onRule, onConnect, onDisconnect, onRemove }: Props) {
  if (!node) {
    return (
      <div className="mdl-insp">
        <h3>Inspector</h3>
        <p className="note">Select a step. Drag steps to move them; add a business rule with Add rule. Locked steps are the core prediction, the guardrails and owner approval: they can be moved but not edited or removed.</p>
      </div>
    );
  }
  const by = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
  const outs = graph.edges.filter((e) => e.a === node.id);
  const targets = graph.nodes.filter((n) => n.id !== node.id && !outs.some((e) => e.b === n.id) && n.t !== 'trigger');
  const next = (
    <div className="mdl-next">
      <h4>Next steps</h4>
      {outs.length === 0 && <p className="note">None: this step ends here.</p>}
      <ul>
        {outs.map((e) => (
          <li key={e.id}>
            → {by[e.b] ? nodeTitle(by[e.b], s) : e.b}
            {editable && !(node.lock && by[e.b]?.lock) && (
              <button className="btn sm ghost" onClick={() => onDisconnect(e.id)} aria-label={'Remove connection to ' + e.b}>Remove</button>
            )}
          </li>
        ))}
      </ul>
      {editable && node.t !== 'learn' && (
        <label className="mdl-f">
          <span>Connect to</span>
          <select value="" onChange={(e) => e.target.value && onConnect(node.id, e.target.value)}>
            <option value="">choose…</option>
            {targets.map((n) => <option key={n.id} value={n.id}>{nodeTitle(n, s)}</option>)}
          </select>
        </label>
      )}
    </div>
  );

  if (node.t === 'gate' || node.t === 'guard' || node.t === 'approval') {
    const ids: string[] = node.sub.match(/GR-[A-Z]?\d+/g) ?? [];
    return (
      <div className="mdl-insp">
        <h3>{node.label} <LockIcon /></h3>
        <p className="note">Locked. Changed only by the guardrail owner, never through the Modeler. Every outcome must pass through it.</p>
        {byStage(s.template.guardrails.filter((g) => ids.includes(g.id))).map((grp) => (
          <div key={grp.stage}>
            <h4>{grp.label}</h4>
            <table className="t static tight">
              <tbody>
                {grp.items.map((g) => (
                  <tr key={g.id}>
                    <td className="num">{g.id}</td>
                    <td>
                      {g.text} <span className="chip">{g.type}</span> {g.locked && <LockIcon />}
                      <div className="note">Owner: {g.owner}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
        {next}
      </div>
    );
  }
  if (node.t !== 'rule') {
    return (
      <div className="mdl-insp">
        <h3>{node.label} {node.lock && <LockIcon />}</h3>
        <p className="note">{TTAG[node.t]} · {node.sub}</p>
        {node.lock && <p className="note">Core prediction and agents are fixed: the Modeler never edits what this step predicts.</p>}
        {next}
        {editable && !node.lock && <button className="btn sm" onClick={() => onRemove(node.id)}>Delete step</button>}
      </div>
    );
  }
  const scope: Scope = node.scope ?? {};
  const setDim = (k: string, v: Scope[string]) => onRule(node.id, { scope: { ...scope, [k]: v } });
  return (
    <div className="mdl-insp">
      <h3>{node.rid} · business rule</h3>
      {node.src && <p className="note">From: “{node.src}”</p>}
      <div className="mdl-row">
        <label className="mdl-f">
          <span>Action</span>
          <select aria-label="Action" disabled={!editable} value={node.action ?? 'exclude'} onChange={(e) => onRule(node.id, { action: e.target.value as FlowNode['action'] })}>
            {ACTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <label className="mdl-f">
          <span>Path</span>
          <select aria-label="Path" disabled={!editable} value={node.path ?? ''} onChange={(e) => onRule(node.id, { path: e.target.value || null })}>
            <option value="">choose…</option>
            {s.template.paths.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
      </div>
      {s.template.dims.map((d) => <DimField key={d.key} d={d} scope={scope} editable={editable} set={(v) => setDim(d.key, v)} />)}
      <label className="mdl-f">
        <span>Owner</span>
        <input aria-label="Owner" disabled={!editable} value={node.owner ?? ''} onChange={(e) => onRule(node.id, { owner: e.target.value })} />
      </label>
      <p className="mdl-read">{node.path ? nodeTitle(node, s) : 'Pick a path'}.</p>
      {next}
      {editable && <button className="btn sm" onClick={() => onRemove(node.id)}>Delete rule</button>}
    </div>
  );
}
