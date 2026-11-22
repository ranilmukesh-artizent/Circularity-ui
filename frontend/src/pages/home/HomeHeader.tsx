/** The header of the Home pages (the demo's frHead): title, a line under it, and controls on the right. */
import type { ReactNode } from 'react';

export const HomeHeader = ({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) => (
  <div className="phead frph">
    <div>
      <h1>{title}</h1>
      {sub && <p>{sub}</p>}
    </div>
    {right && <div className="row">{right}</div>}
  </div>
);
