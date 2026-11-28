/**
 * A route line (28 Nov 2026): the stops of a sequence drawn as one line, like a transit map. The stops before `handover`
 * sit on the upper lane and the rest on the lower one, and the line steps down between them, so who does which part is
 * read from the drawing. A stop is a link when `hrefFor` is given (the URL holds the step in view), else plain text.
 * Below 640px of its own width the line stands upright, one stop under the other.
 */
import './lines.css';

export type StopState = 'done' | 'now' | 'todo' | 'back';
export interface Stop {
  id: string;
  label: string;
  state: StopState;
  /** the word under the name: "Done", "Next", "Sent back" */
  note: string;
}

const DROP = 30; // px between the two lanes

const Mark = ({ state }: { state: StopState }) =>
  state === 'done' ? (
    <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.6 6.4l2.3 2.3 4.6-5" fill="none" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" /></svg>
  ) : state === 'back' ? (
    <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 2.8v3.9M6 9v.2" fill="none" strokeWidth="1.9" strokeLinecap="round" /></svg>
  ) : null;

export function RouteLine({ stops, handover, lanes, current, hrefFor, label }: {
  stops: Stop[];
  /** index of the first stop on the lower lane; stops.length when there is one lane */
  handover: number;
  /** who does each lane, e.g. ["You", "An approver"] */
  lanes: [string, string];
  /** the stop in view */
  current?: string;
  hrefFor?: (id: string) => string | null;
  label: string;
}) {
  return (
    <div className="rl-wrap">
      <ol className="rl" aria-label={label} style={{ ['--rl-n' as string]: stops.length, ['--rl-drop' as string]: DROP + 'px' }}>
        {stops.map((s, i) => {
          const low = i >= handover;
          const last = i === stops.length - 1;
          const href = hrefFor?.(s.id) ?? null;
          const body = (
            <>
              <span className="rl-dot"><Mark state={s.state} /></span>
              <span className="rl-text">
                <span className="rl-name">{s.label}</span>
                <span className="rl-note">{s.note}</span>
              </span>
            </>
          );
          return (
            <li key={s.id} className={(low ? 'low ' : '') + (i === handover - 1 && !last ? 'hand ' : '') + (last ? 'last' : '')} data-state={s.state} data-stop={s.id}>
              {(i === 0 || i === handover) && <span className="rl-lane">{lanes[low ? 1 : 0]}</span>}
              {href ? (
                <a className="rl-stop" href={href} aria-current={current === s.id ? 'step' : undefined}>{body}</a>
              ) : (
                <span className="rl-stop" aria-current={current === s.id ? 'step' : undefined}>{body}</span>
              )}
              {i === handover - 1 && !last && (
                <svg className="rl-step" viewBox={`0 0 100 ${DROP + 6}`} preserveAspectRatio="none" aria-hidden="true">
                  <path d={`M0 3 C 62 3, 38 ${DROP + 3}, 100 ${DROP + 3}`} fill="none" vectorEffect="non-scaling-stroke" />
                </svg>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
