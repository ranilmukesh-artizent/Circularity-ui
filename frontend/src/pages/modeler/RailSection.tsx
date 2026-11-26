import type { ReactNode } from 'react';
import { Icon } from '../../components/Icon';
import './rail.css';

/**
 * One group in the Modeler's rail (plan 10, 3.4 and 3.5). The rail is the container, so this is not a card: a section
 * title (13px/600, sentence case, an 18px icon from the 4.6 table), an optional line under it, then the content.
 */
export function RailSection({ title, icon, sub, right, cls, children }: {
  title: ReactNode; icon: string; sub?: ReactNode; right?: ReactNode; cls?: string; children: ReactNode;
}) {
  return (
    <section className={'mdl-rsec ' + (cls ?? '')}>
      <header className="mdl-rsec-t">
        <Icon name={icon} />
        <h3>{title}</h3>
        {right && <span className="mdl-rsec-r">{right}</span>}
      </header>
      {sub != null && <p className="mdl-rsec-s">{sub}</p>}
      {children}
    </section>
  );
}
