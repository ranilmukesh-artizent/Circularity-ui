/** Timeline (the demo's frTl): an icon tile, a title with a note and extras, and an age with a status on the right. */
import type { ReactNode } from 'react';
import { IconTile } from './IconTile';

export interface TimelineRow { key?: string; ic: string; h: string; t: ReactNode; s?: ReactNode; x?: ReactNode; ago?: string; st?: ReactNode; cls?: string }

export function Timeline({ rows, empty, cls }: { rows: TimelineRow[]; empty?: string; cls?: string }) {
  if (!rows.length) return <p className="note">{empty || 'Nothing yet.'}</p>;
  return (
    <ol className={'frtl' + (cls ? ' ' + cls : '')}>
      {rows.map((r, i) => (
        <li key={r.key ?? i} className={r.cls}>
          <IconTile ic={r.ic} h={r.h} cls="sm" />
          <div className="frtlb">
            <b>{r.t}</b>
            {r.s && <span className="note">{r.s}</span>}
            {r.x && <span className="frtlx">{r.x}</span>}
          </div>
          <span className="frtlr">
            {r.ago && <span className="note num">{r.ago}</span>}
            {r.st}
          </span>
        </li>
      ))}
    </ol>
  );
}
