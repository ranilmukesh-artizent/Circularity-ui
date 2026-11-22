/** The demo's small status pieces (stageChip, condChip, assessChip, thumb, sigHTML), with the same classes. */
import { signals, type Case, type Evidence } from '../../api/product';
import { Icon } from '../../components/Icon';

const CLS_ICON: Record<string, string> = { motor: 'motor', pump: 'pump', control: 'control', drill: 'drill', batch: 'batch', it: 'it' };

export function Thumb({ cls, style }: { cls: string; style?: React.CSSProperties }) {
  return (
    <span className="thumb" style={style}>
      <Icon name={CLS_ICON[cls] ?? cls} />
    </span>
  );
}

export function StageChip({ c }: { c: Case }) {
  switch (c.stage) {
    case 'awaiting_approval': return <span className="chip y">Awaiting approval</span>;
    case 'approved': return <span className="chip dk">Approved · handing off</span>;
    case 'executing':
      return <span className="chip ok" data-tip="Instruction sent; the enterprise system carries out the work and reports the outcome">Handed off</span>;
    case 'reeval': return <span className="chip warn">Re-evaluate</span>;
    case 'none': return c.blocked ? <span className="chip bad">Needs evidence</span> : <span className="chip line">—</span>;
    case 'closed': return <span className="chip ok">Closed</span>;
    default: return null;
  }
}

export function CondChip({ c }: { c: Case }) {
  const m: Record<string, string> = { Inspected: 'ok', 'Test required': 'warn', 'Not inspected': 'line', Mixed: 'line' };
  const k = m[c.condition] || (/^Grade/.test(c.condition) ? 'ok' : 'line');
  return <span className={'chip ' + k}>{c.condition}</span>;
}

export function AssessChip({ c }: { c: Case }) {
  const k = ({ Ready: 'ok', Review: 'warn', Pending: 'warn', Partial: 'line' } as Record<string, string>)[c.assessment];
  return <span className={'chip ' + k}>{c.assessment}</span>;
}

/** Four signals (received, diagnostics, certification, economic path) as a segmented bar. */
export function Signals({ c }: { c: Case }) {
  const s = signals(c);
  const n = s.filter((x) => x[2] === 'done').length;
  const nx = s.find((x) => x[2] !== 'done');
  const W: Record<string, [string, string]> = {
    Diagnostics: ['MRO diagnostics', 'awaiting MRO'], Certification: ['QMS certification', 'awaiting QMS'], 'Economic path': ['economic path', 'pricing'],
  };
  const full = nx ? (nx[2] === 'block' ? 'blocked at the ' + (c.blocked?.gateName ?? '').toLowerCase() + ' gate' : 'awaiting ' + W[nx[0]][0]) : 'economic path ready';
  const short = nx ? (nx[2] === 'block' ? 'blocked' : W[nx[0]][1]) : 'ready';
  const word = { done: 'ready', part: 'partial', todo: 'waiting', block: 'blocked' };
  return (
    <span className="sg" data-sig={n} aria-label={`Signals ${n} of 4, ${full}`}
      data-tip={n + ' of 4 · ' + full + '. ' + s.map((x) => x[0] + ' (' + x[1] + '): ' + word[x[2]]).join(' · ')}>
      <span className="sgb" aria-hidden="true">
        {s.map((x, i) => <i key={i} className={x[2]} />)}
      </span>
      <span className="note nowrap">{n}/4 · {short}</span>
    </span>
  );
}

/** One evidence line (evRow without the trace button, as the demo's case drawer shows it). */
export function EvRow({ e }: { e: Evidence }) {
  const ic = { ready: '✓', missing: '!', partial: '~', stale: '~', conflict: '!' }[e.state];
  return (
    <div className={'ev ' + e.state}>
      <span className="ic" aria-hidden="true">{ic}</span>
      <div>
        <b>
          {e.label}
          {e.state !== 'ready' && (
            <> <span className={'chip ' + (e.state === 'missing' || e.state === 'conflict' ? 'bad' : 'warn')}>{e.state}</span></>
          )}
        </b>
        <small>{e.source}{e.note ? ' · ' + e.note : ''}</small>
      </div>
      <em>{e.state === 'missing' ? '—' : e.fresh}</em>
    </div>
  );
}
