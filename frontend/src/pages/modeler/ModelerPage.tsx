import { useCallback, useEffect, useRef, useState } from 'react';
import { applyProposal, applySuggestion, forkFlow, saveDraft, useModeler, type Proposal, type RuleSuggestion } from '../../api/modeler';
import type { Check, FlowGraph, ModelerScreen } from '../../api/types';
import { currentAccount } from '../../api/session';
import { useBackend } from '../../api/useBackend';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { ModelsPanel } from '../agents/ModelsPanel';
import type { PageProps } from '../registry';
import { AssistantPanel } from './AssistantPanel';
import { ChecksPanel } from './ChecksPanel';
import { FlowCanvas } from './FlowCanvas';
import { FlowInspector } from './FlowInspector';
import { addRule, connect, disconnect, moveNode, nextRid, removeNode, updateRule } from './flowEdit';
import { HistoryPanel } from './HistoryPanel';
import { ImpactPanel } from './ImpactPanel';
import { LifecycleBar } from './LifecycleBar';
import { OverlayPanel } from './OverlayPanel';
import { PacksPanel } from './PacksPanel';
import { StandingPolicyPanel } from './StandingPolicyPanel';
import { SuggestionsPanel } from './SuggestionsPanel';
import './modeler.css';

/** Edits are saved as a draft this long after the last one (as workflow drafts are, decision log 2026-11-21). */
export const AUTOSAVE_MS = 2000;

/** The Modeler (plan 8, MVP-4.4): a decision flow per template and org unit, edited on a canvas and saved as a draft. */
export function ModelerPage({ query }: PageProps) {
  useBackend();
  const [template, setTemplate] = useState(query.get('template') ?? '');
  const [org, setOrg] = useState(query.get('org') ?? '');
  const s = useModeler(template, org);
  return (
    <div className="frpage mdl" id="modeler">
      <div className="phead frph">
        <div>
          <h1>Modeler</h1>
          <p>The decision process and its business rules. Locked guardrails and the core prediction stay fixed; rules change which path a decision may take.</p>
        </div>
        <div className="row">
          <label className="sr" htmlFor="mdl-tpl">Template</label>
          <select id="mdl-tpl" value={s.template.key} onChange={(e) => setTemplate(e.target.value)}>
            {s.templates.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
          </select>
          <label className="sr" htmlFor="mdl-org">Organisation</label>
          <select id="mdl-org" value={s.org} onChange={(e) => setOrg(e.target.value)}>
            {s.orgs.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
      </div>
      <ModelerBody key={s.flow.id} s={s} />
    </div>
  );
}

function ModelerBody({ s }: { s: ModelerScreen }) {
  const editable = s.can.edit;
  const action = useAction();
  const [graph, setGraph] = useState<FlowGraph>(s.flow.graph);
  const [checks, setChecks] = useState<Check[]>(s.checks);
  const [sel, setSel] = useState<string | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const dirty = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef(graph);
  latest.current = graph;

  // the server's copy wins while nothing is waiting to be saved (another person's change, a lifecycle step)
  const server = JSON.stringify(s.flow.graph);
  useEffect(() => {
    if (!dirty.current) {
      setGraph(JSON.parse(server) as FlowGraph);
      setChecks(s.checks);
    }
  }, [server, s.checks]);

  const save = useCallback(async () => {
    timer.current = null;
    const r = await action.run(() => saveDraft(s.flow.id, latest.current));
    dirty.current = false;
    if (r.ok) setChecks(r.output.checks);
  }, [action, s.flow.id]);

  useEffect(() => () => {
    if (timer.current) {
      clearTimeout(timer.current);
      void saveDraft(s.flow.id, latest.current);
    }
  }, [s.flow.id]);

  /** Save a pending edit now (before a lifecycle step). */
  const flush = async () => {
    if (!timer.current) return;
    clearTimeout(timer.current);
    await save();
  };
  const schedule = () => {
    dirty.current = true;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => void save(), AUTOSAVE_MS);
  };
  const edit = (g: FlowGraph) => {
    if (!editable || g === graph) return;
    setGraph(g);
    schedule();
  };

  const fork = async () => {
    const r = await action.run(() => forkFlow(s.template.key, s.org));
    if (r.ok) toast(s.org + ' now has its own ' + s.flow.name + ' flow.');
  };
  const add = () => {
    const rid = nextRid(graph, s.template.pre);
    const g = addRule(graph, rid, currentAccount()?.role ?? '');
    edit(g);
    setSel(g.nodes.at(-1)?.id ?? null);
  };

  /** Save a proposed graph as the draft (the person's own saveDraft), then show it with its new rule selected. */
  const applyGraph = async (g: FlowGraph | null, nodeId: string | null, call: () => ReturnType<typeof saveDraft>) => {
    if (!g) return false;
    await flush();
    const r = await action.run(call);
    if (!r.ok) return false;
    setGraph(g);
    setChecks(r.output.checks);
    setSel(nodeId);
    return true;
  };
  /** Apply the assistant's proposal, with the assistant's note. */
  const apply = (p: Proposal) => applyGraph(p.graph, p.node_id, () => applyProposal(s.flow.id, p));
  /** Apply a rule suggested by overrides (audit U8): into the draft only, never published. */
  const applySug = (sg: RuleSuggestion) => applyGraph(sg.proposal.graph, sg.proposal.node_id, () => applySuggestion(s.flow.id, sg));
  // a proposal is drawn on the canvas (dashed) until it is applied or dismissed
  const shown = proposal?.graph ?? graph;

  const bad = new Set(checks.filter((c) => c.level === 'fail' && c.node_id).map((c) => c.node_id as string));
  const node = shown.nodes.find((n) => n.id === sel) ?? null;

  return (
    <>
      <div className="mdl-bar">
        <span className="chip line">{s.flow.name} · {s.flow.org_unit_id}</span>
        <LifecycleBar s={s} flush={flush} />
        {s.flow.org_unit_id !== s.org && <span className="note">{s.org} uses this flow from {s.flow.org_unit_id}.</span>}
        <span className="grow" />
        {s.can.fork && <button className="btn sm" disabled={action.pending} onClick={fork}>Give {s.org} its own flow</button>}
        {editable && <button className="btn sm pri" onClick={add}>Add rule</button>}
        {!editable && !s.can.fork && <span className="note">Read only</span>}
      </div>
      <div className="mdl-main">
        <FlowCanvas
          s={s}
          graph={shown}
          selected={sel}
          bad={proposal?.kind === 'blocked' && proposal.node_id ? new Set([...bad, proposal.node_id]) : bad}
          proposed={proposal?.node_id ?? null}
          editable={editable && !proposal}
          onSelect={setSel}
          onMove={(id, x, y) => editable && setGraph((g) => moveNode(g, id, x, y))}
          onMoved={schedule}
        />
        <div className="mdl-side">
          <FlowInspector
            s={s}
            graph={shown}
            node={node}
            editable={editable && !proposal}
            onRule={(id, patch) => edit(updateRule(graph, id, patch))}
            onConnect={(a, b) => edit(connect(graph, a, b))}
            onDisconnect={(id) => edit(disconnect(graph, id))}
            onRemove={(id) => {
              edit(removeNode(graph, id));
              setSel(null);
            }}
          />
          <AssistantPanel s={s} proposal={proposal} onProposal={setProposal} onApply={apply} />
          <ChecksPanel checks={checks} onSelect={setSel} />
        </div>
      </div>
      <div className="mdl-main mdl-lower">
        <ImpactPanel s={s} graph={graph} />
        <HistoryPanel s={s} />
      </div>
      {(s.can.edit || s.can.approve) && (
        <div className="mdl-main mdl-lower">
          <SuggestionsPanel s={s} onApply={applySug} />
        </div>
      )}
      <div className="mdl-main mdl-lower" style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}>
        <OverlayPanel s={s} />
      </div>
      <div className="mdl-main mdl-lower" style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}>
        <PacksPanel s={s} />
      </div>
      <StandingPolicyPanel s={s} />
      <ModelsPanel />
    </>
  );
}
