import { Link } from 'react-router';

/** The Modeler's page tabs (plan 10, 3.4): Flow is the work, the others are secondary and show one at a time. */
export type PageTab = 'flow' | 'layer' | 'policies' | 'tables' | 'packs' | 'setup';

export interface TabDef {
  id: PageTab;
  label: string;
}

/** Which tabs this person sees: Tables for the tool fleet, Packs for those who manage or approve packs (an approver reaches the Approve button there), Set up for those who manage packs. */
export function visibleTabs(o: { managePacks: boolean; approvePacks?: boolean; template: string }): TabDef[] {
  return [
    { id: 'flow', label: 'Flow' },
    { id: 'layer', label: 'Customer layer' },
    { id: 'policies', label: 'Policies' },
    ...(o.template === 'tool_fleet' ? [{ id: 'tables' as const, label: 'Tables' }] : []),
    ...(o.managePacks || o.approvePacks ? [{ id: 'packs' as const, label: 'Packs' }] : []),
    ...(o.managePacks ? [{ id: 'setup' as const, label: 'Set up' }] : []),
  ];
}

/** The tab for `?tab=` and `?compose=`: an unknown or hidden tab is Flow; a compose link alone opens Set up. */
export function pageTab(tab: string | null, compose: number | null, shown: TabDef[]): PageTab {
  const has = (id: string) => shown.some((t) => t.id === id);
  if (tab && has(tab)) return tab as PageTab;
  return !tab && compose != null && has('setup') ? 'setup' : 'flow';
}

/** Tabs as links (they change the URL, so a tab can be linked, reloaded and opened in a new tab). */
export function ModelerTabs({ tabs, active, search }: { tabs: TabDef[]; active: PageTab; search: (id: PageTab) => string }) {
  return (
    <nav className="mdl-tabs" aria-label="Modeler sections">
      {tabs.map((t) => (
        <Link key={t.id} to={{ search: search(t.id) }} replace aria-current={t.id === active ? 'page' : undefined} data-tab={t.id}>
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
