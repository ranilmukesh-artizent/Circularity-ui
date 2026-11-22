/** Workflow Studio's menus: the ⋯ row menu (the demo's details.frmenu) and the quick actions list (frQa). */
import type { ReactNode } from 'react';
import { Icon } from '../../components/Icon';

/** ⋯ menu that closes after a choice. */
export function WorkflowMenu({ summary, summaryCls, label, children }: { summary: ReactNode; summaryCls: string; label?: string; children: ReactNode }) {
  return (
    // closes after a choice: a click on a menu item, which Enter and Space on that item's button also send
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions -- delegated from the items
    <details className="frmenu" onClick={(e) => {
      if ((e.target as HTMLElement).closest('[role=menuitem]')) (e.currentTarget as HTMLDetailsElement).open = false;
    }}>
      <summary className={summaryCls} aria-label={label}>{summary}</summary>
      <div className="frdd" role="menu">{children}</div>
    </details>
  );
}

/** Quick actions (frQa). */
export function QuickActions({ rows }: { rows: { l: string; ic: string; on: () => void }[] }) {
  return (
    <div className="frqa">
      {rows.map((r) => <button key={r.l} className="frqr" onClick={r.on}><Icon name={r.ic} /><span>{r.l}</span><Icon name="chevR" /></button>)}
    </div>
  );
}
