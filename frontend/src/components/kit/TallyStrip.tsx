/**
 * A tally strip (28 Nov 2026): what waits, one mark per item, in groups on one baseline. A late item's mark is taller and
 * red, and each group also says its count and how many are late in words, so nothing rests on colour. A group is a link
 * (the URL holds the group in view); the one in view links back to the whole list.
 */
import './lines.css';

export interface TallyGroup {
  id: string;
  label: string;
  n: number;
  late: number;
  /** a divider before this group (a different kind of waiting) */
  gap?: boolean;
}

const MAX = 36; // marks drawn per group; the rest are the "+N" beside them

export function TallyStrip({ groups, cur, hrefFor, label }: {
  groups: TallyGroup[];
  cur: string | null;
  hrefFor: (id: string | null) => string;
  label: string;
}) {
  return (
    <nav className="tly" aria-label={label}>
      {groups.map((g) => {
        const drawn = Math.min(g.n, MAX);
        const late = Math.min(g.late, drawn);
        return (
          <a
            key={g.id} className={'tly-g' + (g.gap ? ' gap' : '') + (g.n ? '' : ' none')} data-group={g.id}
            href={hrefFor(cur === g.id ? null : g.id)} aria-current={cur === g.id ? 'true' : undefined}
            style={{ flexGrow: 1 + Math.sqrt(drawn) }}
          >
            <span className="tly-marks" aria-hidden="true">
              {Array.from({ length: drawn }, (_, i) => <i key={i} className={i < late ? 'late' : undefined} />)}
              {g.n > MAX && <span className="tly-more">+{g.n - MAX}</span>}
            </span>
            <span className="tly-cap">
              <b className="num">{g.n}</b>
              <span>{g.label}</span>
              {g.late > 0 && <span className="tly-late">{g.late} late</span>}
            </span>
          </a>
        );
      })}
    </nav>
  );
}
