/**
 * The journey strip (jgStrip) and its guide (jgGuide) for Returned assets (Start) and Asset intelligence (step 1).
 * Each step is a link to its own screen for the case in view; the case pages draw their own stage bar.
 */
import {
  asModel, caseById, continueLabel, journeyEstablished, journeyHref, journeyLabel, journeyNextText, journeyProgress, journeySteps,
  journeyTitle, journeyWaiting,
} from '../../api/product';

const ST: Record<string, string> = { done: 'done', cur: 'the case is here now', todo: 'not reached yet' };

export function JourneyStrip({ id, at }: { id: string; at: 0 | 1 }) {
  const c = caseById(id);
  if (!c) return null;
  const p = journeyProgress(c);
  const prev = at > 0 ? at - 1 : null;
  const next = at + 1;
  return (
    <div className="pjs">
      <nav className="jstrip jgnav" id="jgNav" aria-label={`Journey for ${id}. Each step opens its screen.`}>
        <span className="jl jgcase" data-tip={asModel(c) + ' · ' + c.owner + ' · ' + c.location}>
          Journey · <b>{id}</b>
          <span className="jgm"> · {asModel(c)}</span>
        </span>
        <a className={'jgstart ' + (at === 0 ? 'on' : '')} href={'#/' + journeyHref(0, id)} aria-current={at === 0 ? 'step' : undefined}
          data-tip={`Start: Returned assets, with ${id} selected`}>
          <span aria-hidden="true">▶</span>
          <span className="t">Start</span>
        </a>
        <ol className="jgol">
          {journeySteps().map((j) => {
            const n = j[0], st = n < p ? 'done' : n === p ? 'cur' : 'todo';
            return (
              <li key={n}>
                <a className={`jstep ${j[2] === 'built' ? 'built' : j[2]} jg-${st} ${n === at ? 'on' : ''}`} href={'#/' + journeyHref(n, id)}
                  aria-current={n === at ? 'step' : undefined} aria-label={`Step ${n}: ${j[1]}, ${ST[st]}`}
                  data-tip={`Step ${n}: ${j[1]}. ${j[3]}. ${id}: ${ST[st]}.`}>
                  <span className="n">{n}</span>
                  <span className="t">{j[1]}</span>
                </a>
              </li>
            );
          })}
        </ol>
        <span className="jgnav2">
          {prev != null && (
            <a className="btn sm" id="jgBack" href={'#/' + journeyHref(prev, id)} aria-label={'Back: ' + journeyLabel(prev)}>← Back</a>
          )}
          <a className="btn sm pri" id="jgNext" href={'#/' + journeyHref(next, id)} aria-label={'Next: ' + journeyLabel(next)} data-tip={'Next: ' + journeyLabel(next)}>
            Next →
          </a>
        </span>
      </nav>
    </div>
  );
}

export function JourneyGuide({ id, at }: { id: string; at: 0 | 1 }) {
  const c = caseById(id);
  if (!c) return null;
  const p = journeyProgress(c);
  const s = at ? (at < p ? 'done' : at === p ? 'cur' : 'todo') : 'done';
  const nx = at + 1;
  const key = at ? 'Step ' + at + ' · ' + journeyTitle(at) : 'Start · Returned assets';
  return (
    <div id="jgmount" className="pjg">
      <aside className="jgg" id="jgGuide" aria-label="What this step established and what comes next" data-state={s}>
        <p className="jgl" id="jgEst">
          <span className="jgk">{key}</span>
          <b>{s === 'done' ? 'Established here' : s === 'cur' ? 'Where it stands' : 'Not reached yet'}:</b>{' '}
          {s === 'done' ? journeyEstablished(c, at) : journeyWaiting(c, at, s)}
        </p>
        <p className="jgl" id="jgNextL">
          <span className="jgk">Next</span>
          <b>{'Step ' + nx + ' · ' + journeyTitle(nx)}:</b> {journeyNextText(nx)}
        </p>
        <span className="jgb">
          {at > 0 && <a className="btn sm" id="jgGuideBack" href={'#/' + journeyHref(at - 1, id)}>← Back</a>}
          <a className="btn pri" id="jgContinue" href={'#/' + journeyHref(nx, id)}>{continueLabel(nx)} →</a>
        </span>
      </aside>
    </div>
  );
}
