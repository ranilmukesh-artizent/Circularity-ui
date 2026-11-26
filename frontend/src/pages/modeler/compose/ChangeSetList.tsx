import type { ChangeSet } from '../../../api/compose';
import { blockedLines, changeLines } from './changeSetView';

/**
 * The drafted changes of a composition as plain sentences (plan 10, T3): one line per operation or rule, an "assumed" tag on
 * what the person did not state, and the guardrail's refusals named. Used by the Describe step's review and by the Set up
 * mode of the assistant, so both read the same.
 */
export function ChangeSetList({ cs }: { cs: ChangeSet }) {
  const lines = changeLines(cs);
  const blocked = blockedLines(cs);
  return (
    <>
      <ul className="cmp-ops">
        {lines.map((l) => (
          <li key={l.id}>
            {l.text}
            {l.assumed && <span className="chip line" title="You did not state this; check it">assumed</span>}
          </li>
        ))}
        {lines.length === 0 && <li className="note">No changes to the pack.</li>}
      </ul>
      {blocked.map((b) => <p key={b} className="err">{b}</p>)}
    </>
  );
}
