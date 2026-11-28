/**
 * Home's "Start here" card (28 Nov 2026, decision log): the five steps of Set up on a route line, which are done, and
 * one button for the next one. Shown to whoever makes or approves a setup until the organisation has published its
 * first; a person may put it away for this browser. Home never waits for it (its own Suspense, no placeholder).
 */
import { useState } from 'react';
import { compositions } from '../../api/compose';
import { can } from '../../api/session';
import { RouteLine } from '../../components/kit/RouteLine';
import { doneCount, hasPublished, LANES, nextAction, orgName, PAGE_HANDOVER, pageStops, pick, setupPath, type StopId } from '../setup/setupView';
import '../setup/setup.css';

const KEY = 'circ-start-here-hidden';
const hidden = (): boolean => {
  try {
    return localStorage.getItem(KEY) === '1';
  } catch {
    return false;
  }
};

export function StartHere() {
  const all = compositions();
  const [gone, setGone] = useState(hidden);
  if (gone || hasPublished(all)) return null;
  const c = pick(all, null);
  if (!c && !can('managePacks')) return null; // an approver has nothing to start: the card shows once a setup exists
  const next = nextAction(c), done = doneCount(c);
  const hide = () => {
    try {
      localStorage.setItem(KEY, '1');
    } catch {
      /* private window: hidden until the page is read again */
    }
    setGone(true);
  };
  return (
    <section className="panel sth" id="frStart" aria-labelledby="frStartH">
      <div className="sth-h">
        <div>
          <h2 id="frStartH">{c ? 'Your setup is ' + (done ? `${done} of 5 steps done` : 'drafted') : 'Start here: set up your returns business'}</h2>
          <p>
            {c
              ? `Setup ${c.id} for ${orgName(c.org_unit_id)}. Agents draft each step; a different person approves before anything is live.`
              : 'Pick the template closest to your business and say what is different. Agents draft the flow, the system mapping and the agent settings; a different person approves.'}
          </p>
        </div>
        <div className="sth-acts">
          <a className="btn pri" href={'#' + setupPath(c ? { compose: c.id, step: next.step } : {})}>{next.label}</a>
          <button className="btn ghost" onClick={hide}>Not now</button>
        </div>
      </div>
      <RouteLine
        stops={pageStops(c)} handover={PAGE_HANDOVER} lanes={LANES} label="Set up steps"
        hrefFor={(id) => (c ? '#' + setupPath({ compose: c.id, step: id as StopId }) : id === 'describe' ? '#' + setupPath() : null)}
      />
    </section>
  );
}
