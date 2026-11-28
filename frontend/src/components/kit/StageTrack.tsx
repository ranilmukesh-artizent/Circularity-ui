/**
 * A stage track (28 Nov 2026): the parts of a whole as lengths of one line, in their order, with the total beside it and
 * each part's number under it. Home draws "Decisions by stage" with it: the stages are a sequence, so they read left to
 * right. The numbers and colours are the server's (the same record the ring drew).
 */
import { fmtNumber } from '../../api/format';
import type { RingSegment } from './Ring';
import './lines.css';

export function StageTrack({ segs, center, sub, label }: { segs: RingSegment[]; center: string; sub?: string; label?: string }) {
  const shown = segs.filter((s) => s.v > 0);
  return (
    <div className="stk">
      <p className="stk-total">
        <b className="num">{center}</b>
        {sub && <span>{sub}</span>}
      </p>
      <div className="stk-line" role="img" aria-label={label || segs.map((s) => `${s.l} ${fmtNumber(s.v)}`).join(', ')}>
        {shown.map((s, i) => <i key={i} style={{ flexGrow: s.v, background: s.c }} />)}
        {!shown.length && <i className="none" style={{ flexGrow: 1 }} />}
      </div>
      <ul className="stk-parts">
        {segs.map((s, i) => (
          <li key={i} className={s.v ? undefined : 'none'}>
            <i style={{ background: s.c }} aria-hidden="true" />
            <b className="num">{fmtNumber(s.v)}</b>
            <span>{s.l}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
