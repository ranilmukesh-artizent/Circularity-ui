import { useCallback, useEffect, useState } from 'react';
import { acceptAgeingSuggestion, ageingSuggestions, type AgeingList } from '../../api/device';
import { allowedTenants } from '../../api/session';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { ACCEPTED, ageingLine, blockedBy } from './ageing';

/** Ageing suggestions (plan 9, P9-6.13, story DV-08): listings that sit on Offers with no offer or on Buy Now unsold, with the move to the
 *  next channel. The person picks the Offers days (7, 10, 14 or 21); Accept puts the rule into their own draft. A different person
 *  approves and publishes it from the Modeler: the server checks maker-checker again. An agent never accepts. */
export function AgeingCard() {
  const [org, setOrg] = useState(() => allowedTenants()[0] ?? '');
  const [days, setDays] = useState<number | undefined>(undefined);
  const [list, setList] = useState<AgeingList | null>(null);
  const action = useAction();
  const reload = useCallback(async () => {
    if (!org) return;
    const r = await ageingSuggestions(org, days);
    setList(r.ok ? r.output : null);
  }, [org, days]);
  useEffect(() => {
    void reload();
  }, [reload]);
  if (!list || (!list.suggestions.length && days === undefined)) return null;
  return (
    <section aria-label="Ageing suggestions" data-testid="ageing-card" style={{ marginBottom: 12 }}>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>Ageing listings</h2>
        {allowedTenants().length > 1 && (
          <select aria-label="Org unit" value={org} onChange={(e) => setOrg(e.target.value)}>
            {allowedTenants().map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        )}
        <label htmlFor="ageing-days" className="note">Offers move after</label>
        <select id="ageing-days" value={days ?? list.offers_days} onChange={(e) => setDays(Number(e.target.value))}>
          {list.choices.map((d) => <option key={d} value={d}>{d} days</option>)}
        </select>
      </div>
      {!list.suggestions.length && <p className="note">No listing is old enough for that setting.</p>}
      <ul className="frbl" aria-label="Ageing suggestions">
        {list.suggestions.map((s) => {
          const blocked = blockedBy(s);
          return (
            <li key={s.kind} data-kind={s.kind}>
              <span>
                <b>{ageingLine(s)}</b>
                {blocked && <span className="note">{blocked}</span>}
                <span className="row">
                  <button
                    className="btn sm pri"
                    disabled={action.pending || !!blocked}
                    title={blocked ?? undefined}
                    onClick={async () => {
                      const r = await action.run(() => acceptAgeingSuggestion(s, list));
                      if (r.ok) toast(ACCEPTED + '.');
                      await reload();
                    }}
                  >
                    Accept
                  </button>
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
