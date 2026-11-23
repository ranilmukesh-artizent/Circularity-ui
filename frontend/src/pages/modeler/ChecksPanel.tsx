import type { Check } from '../../api/types';
import { Panel } from '../../components/kit/Panel';

const ICON: Record<Check['level'], string> = { ok: '✓', warn: '!', fail: '✕' };

/** The flow's checks (the prototype's fValidate list): ok, warn and fail; clicking one selects its step. */
export function ChecksPanel({ checks, onSelect }: { checks: Check[]; onSelect: (id: string) => void }) {
  const fails = checks.filter((c) => c.level === 'fail').length;
  return (
    <Panel title="Checks" sub={fails ? fails + ' blocking' : 'Nothing blocks a submit'} cls="mdl-checks">
      <ul>
        {checks.map((c, i) => (
          <li key={i} className={c.level}>
            <span className="ic" aria-label={c.level}>{ICON[c.level]}</span>
            {c.node_id ? <button onClick={() => onSelect(c.node_id as string)}>{c.msg}</button> : <span>{c.msg}</span>}
          </li>
        ))}
      </ul>
    </Panel>
  );
}
