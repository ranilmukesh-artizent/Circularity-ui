import { useCallback, useDeferredValue, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { forkFlow, saveDraft, useModeler, type Proposal } from '../../api/modeler';
import type { ActionResult, Check, FlowGraph, ModelerScreen } from '../../api/types';
import { can, currentAccount } from '../../api/session';
import { useBackend } from '../../api/useBackend';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { AssistantPanel } from '../../layout/assistant/AssistantPanel';
import { FlowSections } from '../../layout/assistant/flow/FlowSections';
import type { AssistantMode } from '../../layout/assistant/types';
import { registerSurface } from '../../utils/workSurface';
import type { PageProps } from '../registry';
import { ComposePanel } from './compose/ComposePanel';
import { FlowCanvas } from './FlowCanvas';
import { addRule, connect, disconnect, moveNode, nextRid, removeNode, updateRule } from './flowEdit';
import { LifecycleBar, type RolloutStepId } from './LifecycleBar';
import { ModelerRail } from './ModelerRail';
import { ModelerTabs, pageTab, visibleTabs, type PageTab } from './ModelerTabs';
import { OverlayPanel } from './OverlayPanel';
import { PacksPanel } from './PacksPanel';
import { afterCheckClick, afterEsc, afterPick, afterSelect, afterSurfaceSelect, initialRail, type RailState, type RailTab } from './railTab';
import { ReplayPanel, showReplay } from './ReplayPanel';
import { RolloutPanel } from './RolloutPanel';
import { StandingPolicyPanel } from './StandingPolicyPanel';
import { TablesPanel } from './TablesPanel';
import './modeler.css';

/** Edits are saved as a draft this long after the last one (as workflow drafts are, decision log 2026-11-21). */
export const AUTOSAVE_MS = 2000;

/**
 * The Modeler (plan 8, MVP-4.4; plan 10 section 3): agent-first. The pinned assistant column is the first thing on the
 * page, the canvas fills the height beside it, and the rail (Inspector, Checks, Impact, History) is a strip at the right edge.
 * Secondary work (customer layer, policies, tables, packs, set-up) is on page tabs, in the URL as `?tab=`.
 */
export function ModelerPage({ query }: PageProps) {
  useBackend();
  const nav = useNavigate();
  // the template and org live in the URL, so a link ("Open in Set up" from the assistant) can change them while the page is
  // open. The picks change at once, the screen they read follows: while a template loads (2 to 6 s) the page, the pickers
  // and the last flow stay on screen (useDeferredValue keeps the old render when the new one suspends) instead of one "Loading…".
  const template = query.get('template') ?? '';
  const org = query.get('org') ?? '';
  const shownTemplate = useDeferredValue(template);
  const shownOrg = useDeferredValue(org);
  const loading = shownTemplate !== template || shownOrg !== org;
  const s = useModeler(shownTemplate, shownOrg);
  const compose = composeParam(query.get('compose'));
  const tabs = visibleTabs({ managePacks: can('managePacks'), template: s.template.key });
  const tab = pageTab(query.get('tab'), compose, tabs);
  /** The query for a tab link: the other parameters stay, Flow is the absence of `?tab=`. */
  const searchFor = (id: PageTab) => {
    const q = new URLSearchParams(query);
    if (id === 'flow') q.delete('tab');
    else q.set('tab', id);
    const str = q.toString();
    return str ? '?' + str : '';
  };
  const pick = (k: 'template' | 'org', v: string) => {
    const q = new URLSearchParams(query);
    q.set(k, v);
    // another template has another flow: a composition belongs to the pair it was drafted for
    if (k === 'template') q.delete('compose');
    nav({ search: '?' + q.toString() }, { replace: true });
  };
  return (
    <div className="mdl mdl-page" id="modeler">
      <header className="mdl-head">
        <div className="mdl-title">
          <h1>Modeler</h1>
          <div className="mdl-picks" aria-busy={loading}>
            <div className="mdl-pick">
              <label htmlFor="mdl-tpl">Template</label>
              <select id="mdl-tpl" value={template || s.template.key} onChange={(e) => pick('template', e.target.value)}>
                {s.templates.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
              </select>
            </div>
            <div className="mdl-pick">
              <label htmlFor="mdl-org">Organisation</label>
              <select id="mdl-org" value={org || s.org} onChange={(e) => pick('org', e.target.value)}>
                {s.orgs.map((o) => <option key={o} value={o}>{orgLabel(o)}</option>)}
              </select>
            </div>
            {loading && <span className="note mdl-pick-note" role="status">Loading the flow…</span>}
          </div>
        </div>
        <ModelerTabs tabs={tabs} active={tab} search={searchFor} />
      </header>
      <div className="mdl-bodywrap" data-loading={loading}>
        <ModelerBody key={s.flow.id} s={s} tab={tab} compose={compose} />
      </div>
    </div>
  );
}

/** The pinned assistant's mode on each tab (plan 10, 3.3): Change flow on Flow (Ask without edit rights), Set up on Set up, else Ask. */
const TAB_MODE: Record<PageTab, AssistantMode | undefined> = { flow: undefined, setup: 'setup', layer: 'ask', policies: 'ask', tables: 'ask', packs: 'ask' };

/** An org id for people: `workspace` reads "Workspace"; the value stays the id. */
const orgLabel = (id: string) => id.charAt(0).toUpperCase() + id.slice(1).replace(/[_-]+/g, ' ');

/** `?compose=<id>` opens the Set up tab on that composition. */
const composeParam = (v: string | null): number | null => (v && /^\d+$/.test(v) ? Number(v) : null);


function ModelerBody({ s, tab, compose }: { s: ModelerScreen; tab: PageTab; compose: number | null }) {
  const [composeId, setComposeId] = useState<number | null>(compose);
  const editable = s.can.edit;
  const action = useAction();
  const [graph, setGraph] = useState<FlowGraph>(s.flow.graph);
  const [checks, setChecks] = useState<Check[]>(s.checks);
  const [sel, setSel] = useState<string | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [rail, setRail] = useState<RailState>(() => initialRail(window.innerWidth));
  const [drawer, setDrawer] = useState<'rollout' | 'replay' | null>(null);
  const [agentOpen, setAgentOpen] = useState(false);
  /** the node just applied from a proposal: its revision outline closes once (plan 10, 4.4), then the mark goes */
  const [resolved, setResolved] = useState<string | null>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const drawerOpener = useRef<HTMLElement | null>(null);
  const dirty = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef(graph);
  latest.current = graph;

  // a ?compose= link that arrives while the page is open points Set up at that composition
  useEffect(() => {
    if (compose != null) setComposeId(compose);
  }, [compose]);

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
  /** A step was selected (on the canvas or by the assistant): the rail shows it unless another tab is pinned. */
  const select = (id: string | null) => {
    setSel(id);
    setRail((r) => afterSelect(r, id));
  };

  const remove = (id: string) => {
    edit(removeNode(graph, id));
    select(null);
  };

  const fork = async () => {
    const r = await action.run(() => forkFlow(s.template.key, s.org));
    if (r.ok) toast(s.org + ' now has its own ' + s.flow.name + ' flow.');
  };
  const add = () => {
    const rid = nextRid(graph, s.template.pre);
    const g = addRule(graph, rid, currentAccount()?.role ?? '');
    edit(g);
    select(g.nodes.at(-1)?.id ?? null);
  };

  /** Save a proposed graph as the draft (the person's own saveDraft), then show it with its new rule selected. */
  const applyGraph = async (g: FlowGraph | null, nodeId: string | null, call: () => Promise<ActionResult<{ checks: Check[] }>>) => {
    if (!g) return false;
    await flush();
    const r = await action.run(call);
    if (!r.ok) return false;
    setGraph(g);
    setChecks(r.output.checks);
    setResolved(proposal?.node_id ?? null);
    setProposal(null);
    select(nodeId);
    return true;
  };
  useEffect(() => {
    if (!resolved) return;
    const t = setTimeout(() => setResolved(null), 1600);
    return () => clearTimeout(t);
  }, [resolved]);

  // The assistant column works on what this page registers (plan 10, section 5). The handle reads the latest closures
  // through a ref, so it is registered again only when what it names changes.
  const hold = useRef({ flush, applyGraph, setProposal, surfaceSelect: (id: string | null, t?: 'inspector' | 'history') => {
    setSel(id);
    setRail((r) => afterSurfaceSelect(r, id, t));
  } });
  hold.current = { flush, applyGraph, setProposal, surfaceSelect: hold.current.surfaceSelect };
  useEffect(() => {
    if (tab === 'flow') {
      registerSurface({
        kind: 'flow', flowId: s.flow.id, name: s.flow.name, template: s.template.key, org: s.org, canEdit: editable, draftVer: s.flow.dver,
        graph: () => latest.current,
        flush: () => hold.current.flush(),
        showProposal: (p) => hold.current.setProposal(p),
        applyGraph: (g, nodeId, call) => hold.current.applyGraph(g, nodeId, call),
        select: (id, t) => hold.current.surfaceSelect(id, t),
      });
    } else if (tab === 'setup') registerSurface({ kind: 'compose', id: composeId, org: s.org, pack: s.template.key });
    else registerSurface(null);
  }, [tab, s.flow.id, s.flow.name, s.flow.dver, s.template.key, s.org, editable, composeId]);
  useEffect(() => () => registerSurface(null), []);

  // a proposal is drawn on the canvas (dashed) until it is applied or dismissed
  const shown = proposal?.graph ?? graph;
  const bad = new Set(checks.filter((c) => c.level === 'fail' && c.node_id).map((c) => c.node_id as string));
  const blocking = checks.filter((c) => c.level === 'fail').length;
  const node = shown.nodes.find((n) => n.id === sel) ?? null;
  const flowTab = tab === 'flow';

  // The rollout drawer: focus moves into it on open and back to the step that opened it on close; Esc closes it
  const closeDrawer = () => {
    setDrawer(null);
    const o = drawerOpener.current;
    drawerOpener.current = null;
    if (o?.isConnected) requestAnimationFrame(() => o.focus({ preventScroll: true }));
  };
  const closeRef = useRef(closeDrawer);
  closeRef.current = closeDrawer;
  useEffect(() => {
    if (!drawer) return;
    drawerRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && closeRef.current();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [drawer]);
  const openStep = (k: RolloutStepId) => {
    if (!drawer && document.activeElement instanceof HTMLElement) drawerOpener.current = document.activeElement;
    setDrawer(k === 'replay' && showReplay(s) ? 'replay' : 'rollout');
  };

  const central = () => {
    switch (tab) {
      case 'layer': return <OverlayPanel s={s} />;
      case 'policies': return <StandingPolicyPanel s={s} />;
      case 'tables': return <TablesPanel s={s} />;
      case 'packs': return <PacksPanel s={s} />;
      case 'setup': return <ComposePanel org={s.org} pack={s.template.key} id={composeId} onId={setComposeId} onClose={() => undefined} />;
      default: return null;
    }
  };

  return (
    <>
      {flowTab && (
        <div className="mdl-bar">
          <span className="chip line">{s.flow.name} · {s.flow.org_unit_id}</span>
          <LifecycleBar s={s} flush={flush} blocking={blocking} onStep={openStep} />
          {s.flow.org_unit_id !== s.org && <span className="note">{s.org} uses this flow from {s.flow.org_unit_id}.</span>}
          <span className="grow" />
          {currentAccount()?.role !== 'Finance' && <Link className="note" to="/agents">Models used by this flow: Agents › Models</Link>}
          {s.can.fork && <button className="btn sm" disabled={action.pending} onClick={fork}>Give {s.org} its own flow</button>}
          {!editable && !s.can.fork && <span className="note">Read only</span>}
        </div>
      )}
      <div className="mdl-cols" data-tab={tab} data-rail={flowTab && rail.open ? 'open' : 'closed'}>
        <section className="mdl-agent" data-open={agentOpen} aria-label="Ask Circularity">
          <button type="button" className="mdl-agent-bar" aria-expanded={agentOpen} onClick={() => setAgentOpen((o) => !o)}>
            Ask Circularity{proposal ? ' · 1 proposal' : ''}{blocking > 0 ? ` · ${blocking} blocking` : ''}
          </button>
          <div className="mdl-agent-body">
            {/* one panel, pinned: its mode follows the tab (3.3); What I see, Watching, Proposals and Last simulation only on Flow */}
            <AssistantPanel host="pinned" mode={TAB_MODE[tab]} section={tab === 'flow' || tab === 'setup' ? undefined : tab} sections={flowTab ? <FlowSections /> : undefined} />
          </div>
        </section>
        <div className="mdl-center">
          {flowTab ? (
            <div className="mdl-canvaswrap">
              <FlowCanvas
                s={s}
                graph={shown}
                selected={sel}
                bad={proposal?.kind === 'blocked' && proposal.node_id ? new Set([...bad, proposal.node_id]) : bad}
                proposed={proposal?.node_id ?? null}
                revision={s.flow.dver ?? s.flow.ver + 1}
                resolved={resolved}
                editable={editable && !proposal}
                onSelect={select}
                onMove={(id, x, y) => editable && setGraph((g) => moveNode(g, id, x, y))}
                onMoved={schedule}
                onConnect={(a, b) => edit(connect(graph, a, b))}
                onRemove={remove}
                onDisconnect={(id) => edit(disconnect(graph, id))}
              />
              {editable && <button type="button" className="btn sm pri mdl-add" onClick={add}>Add rule</button>}
              {drawer && (
                <div className="mdl-drawer" role="region" aria-label={drawer === 'replay' ? 'Replay' : 'Rollout'} tabIndex={-1} ref={drawerRef}>
                  <button type="button" className="btn sm ghost mdl-drawer-x" onClick={closeDrawer}>Close</button>
                  {drawer === 'replay' ? <ReplayPanel s={s} /> : <RolloutPanel s={s} />}
                </div>
              )}
            </div>
          ) : (
            <div className="mdl-sub">{central()}</div>
          )}
        </div>
        {flowTab && (
          <ModelerRail
            s={s}
            state={rail}
            onPick={(t: RailTab) => setRail((r) => afterPick(r, t))}
            onEsc={() => setRail(afterEsc)}
            graph={shown}
            node={node}
            editable={editable && !proposal}
            onRule={(id, patch) => edit(updateRule(graph, id, patch))}
            onConnect={(a, b) => edit(connect(graph, a, b))}
            onDisconnect={(id) => edit(disconnect(graph, id))}
            onRemove={remove}
            checks={checks}
            onCheck={(id) => {
              setSel(id);
              setRail(afterCheckClick());
            }}
            draft={graph}
          />
        )}
      </div>
    </>
  );
}
