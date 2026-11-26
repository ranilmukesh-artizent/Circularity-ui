import type { PathView } from '../../../api/toolFleet';
import { money } from '../../../api/format';

interface Marks {
  best?: string | null;
  second?: string | null;
  standard?: string;
  uplift?: number | null;
}

/** "Best", "Second best" or "Standard route" for a path, in that order of weight; both when the best is the standard. */
export const tagsOf = (k: string, m: Marks): string[] =>
  [k === m.best && 'Best', k === m.second && 'Second best', k === m.standard && 'Standard route'].filter((x): x is string => !!x);

/** "Net $1,234" for a ready path, or the reason a blocked one cannot be taken. */
export const netLine = (p: PathView): string => (p.ok ? `Net ${money(p.net)}` : p.why);

/** The hazardous-transport line of a battery pack's take-back (P9-3.19, TF-16): "Hazardous transport (lithium-ion, UN 3480): $14", or null for any other path. */
export const hazardLine = (p: PathView): string | null => {
  const l = p.lines.find((x) => x.type === 'c' && x.label.startsWith('Hazardous transport'));
  return l ? `${l.label}: ${money(l.amt)}` : null;
};

/** "Value Fleet renewal ...: $3,210", "Cost Clean and inspect: −$40": a value line as a sentence with its sign. */
export const lineText = (l: PathView['lines'][number]): string =>
  `${l.type === 'v' ? 'Value' : l.type === 'c' ? 'Cost' : 'Holding'} ${l.label}: ${l.type === 'v' ? '' : '−'}${money(l.amt)}`;

/** "CO2e avoided 83.5 kg · sample factors tf-co2-2026.1" (P9-3.14, TF-13), or null for a path without a factor. */
export const co2Text = (p: PathView): string | null =>
  p.co2 == null ? null : `CO2e avoided ${p.co2} kg${p.co2Source ? ` · ${p.co2Source}` : ''}`;

/** The six paths valued against the live named demand (plan 9, P9-3.12, TF-07): net and value lines, blocked ones with their reason, and the uplift of the best over the standard route. */
export function PathsSection({ paths, best, second, standard, uplift }: { paths: PathView[] } & Marks) {
  if (!paths.length) return null;
  const marks = { best, second, standard };
  return (
    <div style={{ marginTop: 8 }} data-testid="tf-paths">
      {uplift != null && best && (
        <p style={{ margin: '0 0 6px' }} data-testid="tf-uplift">
          Uplift over the standard route: {money(uplift)}
        </p>
      )}
      {paths.map((p) => (
        <details key={p.k} open={p.k === best} data-testid={`tf-path-${p.k}`} style={{ marginBottom: 4 }}>
          <summary>
            <strong>{p.name}</strong> · {netLine(p)}{' '}
            {tagsOf(p.k, marks).map((t) => (
              <span key={t} className={`chip ${t === 'Best' ? 'ok' : ''}`}>{t}</span>
            ))}
            {!p.ok && <span className="chip bad">Blocked</span>}
          </summary>
          {p.ok && <p style={{ margin: '4px 0' }}>{p.why}</p>}
          {hazardLine(p) && (
            <p className="muted" style={{ margin: '4px 0' }} data-testid={`tf-path-${p.k}-hazard`}>
              {hazardLine(p)}
            </p>
          )}
          {p.ok && co2Text(p) && (
            <p className="muted" style={{ margin: '4px 0' }} title={p.co2Formula ?? undefined} data-testid={`tf-path-${p.k}-co2`}>
              {co2Text(p)}
            </p>
          )}
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {p.lines.map((l, i) => (
              <li key={i} title={l.basis} data-testid={`tf-path-${p.k}-line`}>
                {lineText(l)}
                <span className="muted"> · {l.basis}</span>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}
