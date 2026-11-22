/** Panel with a title, an optional subtitle and an optional right-hand control (the demo's frPanel). */
import type { ReactNode } from 'react';

export function Panel({ title, sub, right, id, cls, children }: { title: ReactNode; sub?: ReactNode; right?: ReactNode; id?: string; cls?: string; children: ReactNode }) {
  return (
    <section className={'panel frp ' + (cls || '')} id={id}>
      <div className="ph">
        <div>
          <h3>{title}</h3>
          {sub != null && <span className="note">{sub}</span>}
        </div>
        {right}
      </div>
      <div className="pb">{children}</div>
    </section>
  );
}
