import { useEffect, useRef } from 'react';
import type { Check, FlowGraph, FlowNode, ModelerScreen } from '../../api/types';
import { Icon } from '../../components/Icon';
import { ChecksPanel } from './ChecksPanel';
import { FlowInspector } from './FlowInspector';
import { HistoryPanel } from './HistoryPanel';
import { ImpactPanel } from './ImpactPanel';
import { RAIL_TABS, type RailState, type RailTab } from './railTab';

interface Props {
  s: ModelerScreen;
  state: RailState;
  onPick: (tab: RailTab) => void;
  onEsc: () => void;
  /** what the Inspector shows */
  graph: FlowGraph;
  node: FlowNode | null;
  editable: boolean;
  onRule: (id: string, patch: Pick<Partial<FlowNode>, 'action' | 'path' | 'scope' | 'owner'>) => void;
  onConnect: (a: string, b: string) => void;
  onDisconnect: (edgeId: string) => void;
  onRemove: (id: string) => void;
  checks: Check[];
  onCheck: (nodeId: string) => void;
  /** the flow as drawn without a proposal (Impact simulates it) */
  draft: FlowGraph;
}

const idOf = (t: RailTab) => 'mdl-rail-' + t;

/**
 * The Modeler's rail (plan 10, 3.4): a 44px tab strip that is always there, and a 340px panel for Inspector, Checks, Impact
 * and History. The panels are hosted as they are; this file only decides which one shows. Arrow keys move between the tabs.
 */
export function ModelerRail(p: Props) {
  const { s, state } = p;
  const blocking = p.checks.filter((c) => c.level === 'fail').length;
  const ref = useRef<HTMLElement>(null);
  const latest = useRef(p);
  latest.current = p;
  // Esc closes the rail; Up and Down move between the tabs (listeners on the element, as it is a landmark, not a control)
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onKey = (e: KeyboardEvent) => {
      const { state: st, onPick, onEsc } = latest.current;
      if (e.key === 'Escape' && st.open) return onEsc();
      const step = e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0;
      if (!step || !(e.target as HTMLElement).closest('.mdl-strip')) return;
      e.preventDefault();
      const i = RAIL_TABS.findIndex((t) => t.id === st.tab);
      const next = RAIL_TABS[(i + step + RAIL_TABS.length) % RAIL_TABS.length].id;
      onPick(next);
      requestAnimationFrame(() => document.getElementById('mdl-railtab-' + next)?.focus());
    };
    el.addEventListener('keydown', onKey);
    return () => el.removeEventListener('keydown', onKey);
  }, []);
  return (
    <aside className="mdl-rail" data-open={state.open} aria-label="Flow details" ref={ref}>
      <div className="mdl-strip" role="tablist" aria-orientation="vertical" aria-label="Flow detail tabs">
        {RAIL_TABS.map((t) => {
          const on = state.open && state.tab === t.id;
          return (
            <button key={t.id} id={'mdl-railtab-' + t.id} type="button" role="tab" aria-selected={on} aria-controls={on ? idOf(t.id) : undefined}
                    title={t.label} tabIndex={on || (!state.open && t.id === state.tab) ? 0 : -1} onClick={() => p.onPick(t.id)}>
              <Icon name={t.icon} />
              <span className="sr">{t.label}</span>
              {t.id === 'checks' && blocking > 0 && <span className="mdl-badge" aria-hidden="true">{blocking}</span>}
              {t.id === 'checks' && blocking > 0 && <span className="sr">, {blocking} blocking</span>}
            </button>
          );
        })}
      </div>
      {state.open && (
        <div className="mdl-rail-panel" role="tabpanel" id={idOf(state.tab)} aria-labelledby={'mdl-railtab-' + state.tab}>
          {state.tab === 'inspector' && (
            <>
              {!p.node && (
                <p className="mdl-rail-intro">
                  The decision process and its business rules. Locked guardrails and the core prediction stay fixed; rules change which path a decision may take. Select a step to see it here.
                </p>
              )}
              <FlowInspector s={s} graph={p.graph} node={p.node} editable={p.editable} onRule={p.onRule} onConnect={p.onConnect} onDisconnect={p.onDisconnect} onRemove={p.onRemove} />
            </>
          )}
          {state.tab === 'checks' && <ChecksPanel checks={p.checks} onSelect={p.onCheck} />}
          {state.tab === 'impact' && <ImpactPanel s={s} graph={p.draft} />}
          {state.tab === 'history' && <HistoryPanel s={s} />}
        </div>
      )}
    </aside>
  );
}
