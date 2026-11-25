/**
 * One workflow step as a React Flow node (P9-8.13). Owns the step's look: the `.wfn` box with its mark, label, run state
 * chip, record count and the two handles, so the demo's class names and the smokes' selectors keep working. Never
 * decides what a step may do: Canvas.tsx passes everything in `data` and handles every event.
 */
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { stepInfo, type WfNode } from '../../api/workflows';
import { LOCK_SVG, NodeMark } from './WorkflowMarks';

export interface StepData extends Record<string, unknown> {
  n: WfNode;
  /** The run state, its label, and the "N records" text; empty when there is no run. */
  st?: string;
  stLabel: string;
  records: string;
  /** "3 → 2 · 1 held" after a test run (P9-8.15). */
  io?: string;
  /** Records are pinned on this step: the next test run starts here. */
  pinned?: boolean;
  /** The worst check on the step: 'error' or 'warn'. */
  sev?: string;
}

export function StepNode({ data, selected }: NodeProps) {
  const { n, st, stLabel, records, io, pinned, sev } = data as StepData;
  const i = stepInfo(n), fx = n.k === 'fixed';
  return (
    <div className={'wfn frn ' + (fx ? 'fixed' : 'mov') + (selected ? ' sel' : '') + (n.fail ? ' inj' : '')}
      data-id={n.id} data-sev={sev} data-st={st} tabIndex={0} role="button"
      aria-label={`${i.label}. ${fx ? 'Fixed' : 'Movable'} ${i.tag.replace(/^Fixed · /, '')}.`} title={i.sub}>
      {i.in && <Handle type="target" position={Position.Left} className="port in" isConnectable />}
      {i.out && <Handle type="source" position={Position.Right} className="port out" />}
      <span className="frnh"><NodeMark n={n} /><span className="frnt"><span className="lb">{i.label}</span><span className="sb">{i.sub}</span></span>{fx && <span className="frlk" aria-hidden="true">{LOCK_SVG}</span>}</span>
      <span className="frnf"><span className="st">{stLabel}</span><span className="frrcn num" data-rc={n.id}>{records}</span>{io && <span className="frio num" data-io={n.id} style={{ marginLeft: 6, fontSize: 11 }}>{io}</span>}{pinned && <span className="chip line" data-pin={n.id} title="Pinned test input">pinned</span>}</span>
      <span className="tag">{i.tag}</span>
    </div>
  );
}
