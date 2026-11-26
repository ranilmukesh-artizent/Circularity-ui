import type { Check } from '../../api/types';
import { Icon } from '../../components/Icon';
import { RailSection } from './RailSection';

/** A pass is `check`; a warning and a failure are `alert`, told apart by colour and by the sentence (plan 10, 4.6). */
const ICON: Record<Check['level'], string> = { ok: 'check', warn: 'alert', fail: 'alert' };
const LEVEL: Record<Check['level'], string> = { ok: 'Passed', warn: 'Warning', fail: 'Blocking' };

/** The flow's checks (the prototype's fValidate list): ok, warn and fail; clicking one selects its step. */
export function ChecksPanel({ checks, onSelect }: { checks: Check[]; onSelect: (id: string) => void }) {
  const fails = checks.filter((c) => c.level === 'fail').length;
  return (
    <RailSection title="Checks" icon="checks" sub={fails ? fails + ' blocking' : 'Nothing blocks a submit'}>
      <ul className="mdl-checks">
        {checks.map((c, i) => (
          <li key={i} className={c.level}>
            <Icon name={ICON[c.level]} />
            <span className="sr">{LEVEL[c.level]}: </span>
            {c.node_id ? <button onClick={() => onSelect(c.node_id as string)}>{c.msg}</button> : <span>{c.msg}</span>}
          </li>
        ))}
      </ul>
    </RailSection>
  );
}
