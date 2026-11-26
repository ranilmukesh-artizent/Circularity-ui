import type { ReactNode } from 'react';
import { Icon } from '../../../components/Icon';
import type { Prov } from '../../../pages/modeler/flowBrief';
import { ProvTag } from './ProvTag';
import './flow.css';

/** One section of the agent column (plan 10, 3.3): an 18px icon, a sentence-case title, its provenance tag at the right. */
export function Sec({ icon, title, tag, right, children }: { icon: string; title: string; tag?: Prov; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="as-sec" aria-label={title}>
      <div className="as-sec-t">
        <Icon name={icon} className="as-ic-lg" />
        <h3>{title}</h3>
        {right}
        {tag && <ProvTag name={tag} />}
      </div>
      {children}
    </section>
  );
}

/** A row of a section: a 16px icon, a sentence, and an optional link button (the target is spelled out, not "click here"). */
export function Row({ icon, tag, children, go, onGo }: { icon: string; tag?: Prov; children: ReactNode; go?: string; onGo?: () => void }) {
  return (
    <div className="as-row">
      <Icon name={icon} className="as-ic" />
      <span className="as-row-t">{children}</span>
      {tag && <ProvTag name={tag} />}
      {go && onGo && <button type="button" className="as-link" onClick={onGo}>{go}</button>}
    </div>
  );
}
