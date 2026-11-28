import { Suspense, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { compositionHistory, compositions, fetchComposition, type Composition } from '../../api/compose';
import { useModeler } from '../../api/modeler';
import { can, canPage } from '../../api/session';
import { useBackend } from '../../api/useBackend';
import { RouteLine } from '../../components/kit/RouteLine';
import { AssistantPanel } from '../../layout/assistant/AssistantPanel';
import { registerSurface } from '../../utils/workSurface';
import { AgentsStep } from '../modeler/compose/AgentsStep';
import { ApproveStep } from '../modeler/compose/ApproveStep';
import { DescribeStep } from '../modeler/compose/DescribeStep';
import { MappingStep } from '../modeler/compose/MappingStep';
import { PublishStep } from '../modeler/compose/PublishStep';
import { stateLine } from '../modeler/compose/composeView';
import '../modeler/compose/compose.css';
import type { PageProps } from '../registry';
import { AccessStep } from './AccessStep';
import { ShapeStep } from './ShapeStep';
import { TemplateStep, takeDrafted } from './TemplateStep';
import { compositionLabel, currentStep, isStop, LANES, live, neighbours, orgName, PAGE_HANDOVER, pageStops, pick, setupPath, stopDef, type StopId } from './setupView';
import './setup.css';

/**
 * Set up (28 Nov 2026, decision log): the workspace a business is set up in, on one route line. Choose a template and
 * describe what is different (the assistant sits in the page and drafts), shape the decision flow (the Modeler's own canvas
 * and draft, so the Modeler shows the same thing), connect the systems and map their data, set the agents, check access,
 * then a different person approves and publishes. Compose's actions and steps are underneath (pages/modeler/compose); the
 * server refuses approve and publish for the maker and for every agent. The URL holds the composition and the stop:
 * #/setup?compose=12&step=mapping.
 */
export function SetupPage({ query }: PageProps) {
  useBackend();
  const nav = useNavigate();
  const m = useModeler('', '');
  const all = compositions();
  const list = live(all);
  const fresh = query.get('new') === '1';
  const asked = /^\d+$/.test(query.get('compose') ?? '') ? Number(query.get('compose')) : null;
  const orgAsked = query.get('org');
  const listed = fresh ? null : pick(all, asked, asked == null ? orgAsked : null);
  // a setup asked for by id that the list does not have yet (it was made a moment ago) is read on its own
  const lone = useAsked(!fresh && !listed ? asked : null);
  const c = listed ?? (lone && lone !== 'missing' && lone !== 'reading' ? lone : null);
  const org = c?.org_unit_id ?? (orgAsked && m.orgs.includes(orgAsked) ? orgAsked : m.org);
  const packAsked = query.get('pack');
  const pack = c?.pack_key ?? (packAsked && m.templates.some((t) => t.key === packAsked) ? packAsked : m.template.key);
  const packName = (key: string) => m.templates.find((t) => t.key === key)?.name;
  const stepAsked = query.get('step');
  const step: StopId = c && isStop(stepAsked) ? stepAsked : currentStep(c);
  const def = stopDef(step);
  const five = step !== 'flow' && step !== 'access' ? step : null; // a stop that is one of Compose's own steps

  useEffect(() => {
    document.title = 'Set up · Circularity Decision Workbench';
  }, []);
  // the assistant's Set up mode drafts for the organisation and pack in view; on the flow stop the canvas registers itself
  useEffect(() => {
    if (step === 'flow') return;
    registerSurface({ kind: 'compose', id: c?.id ?? null, org, pack });
    return () => registerSurface(null);
  }, [c?.id, org, pack, step]);
  // once the assistant has drafted the description typed here, the page moves on to the new composition
  const newest = list[0]?.id ?? 0;
  useEffect(() => {
    const id = takeDrafted(newest);
    if (id != null) nav(setupPath({ compose: id }), { replace: true });
  }, [newest, nav]);

  const hrefFor = (id: string) =>
    c ? '#' + setupPath({ compose: c.id, step: id as StopId }) : id === 'describe' ? '#' + setupPath({ org: orgAsked, pack: packAsked, fresh }) : null;

  return (
    <div className="frpage sup" id="setup" data-reading={lone === 'reading' || undefined}>
      <div className="phead frph">
        <div>
          <h1>Set up</h1>
          <p>Set up a returns business in one place: start from a template, shape it by talking to the assistant, connect your systems and agents. A different person approves before anything is live.</p>
        </div>
        <div className="row sup-picks">
          {!c && m.orgs.length > 1 && (
            <label className="sup-pick">
              <span>Organisation</span>
              <select className="sel" value={org} onChange={(e) => nav(setupPath({ org: e.target.value, pack: packAsked, fresh: true }), { replace: true })}>
                {m.orgs.map((o) => <option key={o} value={o}>{orgName(o)}</option>)}
              </select>
            </label>
          )}
          {list.length > 1 && c && (
            <label className="sup-pick">
              <span>Setup</span>
              <select className="sel" value={c.id} onChange={(e) => nav(setupPath({ compose: Number(e.target.value) }))}>
                {list.map((x) => <option key={x.id} value={x.id}>{compositionLabel(x, packName(x.pack_key))}</option>)}
              </select>
            </label>
          )}
          {c && can('managePacks') && <a className="btn sm" href={'#' + setupPath({ fresh: true })}>Start another</a>}
        </div>
      </div>

      {lone === 'missing' && (
        <p className="sup-missing" role="status">
          Setup {asked} is not here: it may have been discarded, or it belongs to an organisation you cannot see.{' '}
          <a className="lnk" href={'#' + setupPath()}>Open the newest setup</a>
        </p>
      )}
      <section className="panel sup-line" aria-label="The steps of a setup" aria-busy={lone === 'reading'}>
        <Suspense fallback={<RouteLine stops={pageStops(c)} handover={PAGE_HANDOVER} lanes={LANES} current={step} hrefFor={hrefFor} label="Set up steps" />}>
          <Line c={c} step={step} hrefFor={hrefFor} />
        </Suspense>
      </section>

      <section className={'panel sup-step' + (step === 'flow' ? ' wide' : '')} aria-labelledby="sup-step-h" data-step={step}>
        <header className="sup-step-h">
          <div>
            <h2 id="sup-step-h">{def.title}</h2>
            <p className="note">{def.help}</p>
            {c && (
              <p className="note sup-state">
                {five ? stateLine(c.steps[five]) + '. ' : ''}{compositionLabel(c, packName(c.pack_key))}.
              </p>
            )}
          </div>
          <Advanced step={step} org={org} pack={pack} />
        </header>

        {step === 'describe' ? (
          <div className="sup-split">
            <div className="sup-body">
              {!c && (can('managePacks')
                ? <Suspense fallback={<StepWait />}><TemplateStep org={org} pack={pack} newest={newest} onPack={(k) => nav(setupPath({ org: orgAsked, pack: k, fresh }), { replace: true })} /></Suspense>
                : <p className="note">Nothing is waiting for approval. A planner or an admin starts a setup; it appears here when they send it for approval.</p>)}
              {c && <DescribeStep composition={c} />}
            </div>
            {can('managePacks') && (
              <aside className="sup-chat" aria-label="Assistant">
                <AssistantPanel host="pinned" mode="setup" />
              </aside>
            )}
          </div>
        ) : (
          <div className={'sup-body' + (step === 'flow' ? ' flush' : '')}>
            {c && step === 'flow' && <Suspense fallback={<StepWait h={520} />}><ShapeStep c={c} /></Suspense>}
            {c && step === 'mapping' && <Suspense fallback={<StepWait />}><MappingStep c={c} /></Suspense>}
            {c && step === 'agents' && <Suspense fallback={<StepWait />}><AgentsStep c={c} /></Suspense>}
            {c && step === 'access' && <Suspense fallback={<StepWait />}><AccessStep c={c} /></Suspense>}
            {c && step === 'approve' && <Suspense fallback={<StepWait />}><ApproveStep c={c} /></Suspense>}
            {c && step === 'publish' && <Suspense fallback={<StepWait />}><PublishStep c={c} /></Suspense>}
          </div>
        )}
        {c && <StepNav c={c} step={step} />}
      </section>
    </div>
  );
}

/** The composition with this id when the list does not have it: read once, without throwing. 'missing' for an id that is
 *  not there (or is discarded, or not the person's to see): the page then says so and offers the way on. */
function useAsked(id: number | null): Composition | 'reading' | 'missing' | null {
  const [got, setGot] = useState<{ id: number; c: Composition | 'missing' } | null>(null);
  useEffect(() => {
    if (id == null) return;
    let live = true;
    void fetchComposition(id).then((r) => live && setGot({ id, c: r.ok && r.output.status !== 'discarded' ? r.output : 'missing' }));
    return () => {
      live = false;
    };
  }, [id]);
  if (id == null) return null;
  return got?.id === id ? got.c : 'reading';
}

/** The line with the flow's state on it (a read of its own, so the page never waits for it). */
function Line({ c, step, hrefFor }: { c: Composition | null; step: StopId; hrefFor: (id: string) => string | null }) {
  const flow = c ? compositionHistory(c.id).publish.flow_status : null;
  return <RouteLine stops={pageStops(c, flow)} handover={PAGE_HANDOVER} lanes={LANES} current={step} hrefFor={hrefFor} label="Set up steps" />;
}

const StepWait = ({ h = 160 }: { h?: number }) => <div className="hskel" style={{ minHeight: h, margin: 0 }} role="status" aria-label="Loading this step" aria-busy="true" />;

/** The full pages behind a stop: Set up is the way in, these are where everything about that part lives. */
function Advanced({ step, org, pack }: { step: StopId; org: string; pack: string }) {
  const flow = '#/modeler?' + new URLSearchParams({ template: pack, org }).toString();
  const links: [string, string][] = [];
  if ((step === 'describe' || step === 'flow') && canPage('modeler')) links.push([flow, 'Open this flow in the Modeler']);
  if (step === 'mapping' && canPage('integration', 'studio')) links.push(['#/integration/studio', 'Data workflows in Workflow Studio']);
  if (step === 'mapping' && canPage('integration', 'overview')) links.push(['#/integration/overview', 'Every connected source']);
  if (step === 'agents' && canPage('agents')) links.push(['#/agents', 'All agents and their runs']);
  if (step === 'access' && canPage('access')) links.push(['#/access/accounts', 'Access & Governance']);
  if (!links.length) return null;
  return (
    <ul className="sup-adv" aria-label="More on this part">
      {links.map(([href, text]) => <li key={href}><a className="lnk" href={href}>{text}</a></li>)}
    </ul>
  );
}

/** Back and forward along the line, so a person never has to find the next stop. */
function StepNav({ c, step }: { c: Composition; step: StopId }) {
  const { prev, next } = neighbours(step);
  return (
    <footer className="sup-nav">
      {prev ? <a className="btn sm ghost" href={'#' + setupPath({ compose: c.id, step: prev })}>Back: {stopDef(prev).label.toLowerCase()}</a> : <span />}
      {next && <a className="btn sm" href={'#' + setupPath({ compose: c.id, step: next })}>Next: {stopDef(next).label.toLowerCase()}</a>}
    </footer>
  );
}
