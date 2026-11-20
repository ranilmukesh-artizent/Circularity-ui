import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  activity, alerts, allModules, askExamples, askModes, askStarters, attention, briefing, canManageWorkflows, figures, frPref, greeting, homeUi,
  isTechnical, kfmt, kpis, noWorkflowsMessage, middlePanel, modules, providerLabel, quickActions, setFrPref, setHomeUi, taskItems, unwatch, watches,
} from '../../api/home';
import { useBackend } from '../../api/hooks';
import { canPage, currentAccount } from '../../api/session';
import { Icon } from '../../ui/Icon';
import { Modal } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import { askSoon, FrAttn, FrIt, FrKpi, FrPanel, FrRing, FrSeg, FrSt, FrTl } from './kit';
import { TaskRow } from './TasksPage';

/** Hero drawing (FR_HERO): hidden on phones and in Technical mode. */
const Hero = () => (
  <svg className="frhero" viewBox="0 0 420 150" aria-hidden="true">
    <defs>
      <linearGradient id="frsky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="var(--h-hero1)" />
        <stop offset="1" stopColor="var(--h-hero2)" stopOpacity="0" />
      </linearGradient>
    </defs>
    <rect width="420" height="150" fill="url(#frsky)" />
    <path d="M0 150 L70 92 L110 112 L178 46 L214 76 L250 38 L318 104 L360 84 L420 120 L420 150Z" fill="var(--h-hero3)" />
    <path d="M178 46 L196 62 L188 64 L200 76 L214 76Z M250 38 L268 58 L258 58 L276 76 L262 74Z" fill="var(--h-hero4)" />
    <path d="M0 150 L96 120 L150 132 L232 100 L300 128 L420 110 L420 150Z" fill="var(--h-hero5)" />
    <circle cx="342" cy="40" r="13" fill="#FFDD00" opacity=".85" />
    <path d="M20 140 C120 118 220 142 410 118" stroke="#FFDD00" strokeWidth="2" fill="none" strokeDasharray="4 6" opacity=".7" />
  </svg>
);

function Briefing() {
  const lines = briefing();
  const [all, setAll] = useState(false);
  return (
    <div className={'afc afc-briefing frbrief' + (all ? ' all' : '')} data-card="briefing">
      <p>Your AI agents are ready.{lines.length ? '' : ' Nothing needs you right now.'}</p>
      {lines.length > 0 && (
        <ul className="afbr">
          {lines.map((l, i) => (
            <li key={i} className={i > 2 ? 'frmore' : undefined}>
              <a href={'#/' + l.go}>{l.text}</a>
            </li>
          ))}
        </ul>
      )}
      {lines.length > 3 && (
        <button className="lnk" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? 'Show less' : lines.length - 3 + ' more'}
        </button>
      )}
    </div>
  );
}

/** Ask box with five modes. Asking itself arrives with the Ask Circularity panel. */
function AskBox() {
  const modes = askModes();
  const m = homeUi('frMode') || 'ask', M = modes.find((x) => x[0] === m) || modes[0];
  const [q, setQ] = useState('');
  const [ex, setEx] = useState(false);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    askSoon(q.trim());
    setQ('');
  };
  return (
    <section className="panel frask afhp" id="frAsk">
      <div className="pb">
        <FrSeg name="askmode" label="Ask mode" cur={M[0]} items={modes.map((x) => [x[0], x[1], x[2]])} onPick={(v) => setHomeUi('frMode', v)} />
        <form className="afhpr frhpr" onSubmit={submit}>
          <label className="sr" htmlFor="afhq">{M[1]}: state a goal or ask</label>
          <Icon name="spark" />
          <input id="afhq" type="text" placeholder={M[3]} autoComplete="off" data-mode={M[0]} value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="btn pri" type="submit" aria-label={M[1]}>
            <Icon name="send" />
          </button>
        </form>
        <p className="afopts frex">
          {askStarters().map((s) => (
            <button key={s} className="btn sm" onClick={() => askSoon(s)}>{s}</button>
          ))}
          <button className="lnk" onClick={() => setEx(true)}>View more examples →</button>
        </p>
      </div>
      {ex && (
        <Modal title="Examples you can ask" wide onClose={() => setEx(false)} foot={<button className="btn" onClick={() => setEx(false)}>Close</button>}>
          <p className="note" style={{ marginTop: 0 }}>
            Everything the agent can do for the {currentAccount()?.role} role. Each opens Ask Circularity; anything consequential shows a plan first.
          </p>
          <div className="frexl">
            {askExamples().map((t) => (
              <button key={t} className="btn sm" onClick={() => { setEx(false); askSoon(t); }}>{t}</button>
            ))}
          </div>
        </Modal>
      )}
    </section>
  );
}

function ActivityTimeline({ win, compact }: { win: string; compact?: boolean }) {
  const rows = activity(win);
  return (
    <FrTl
      empty={compact ? 'No activity yet today.' : 'Nothing yet. Ask the agent to prepare something and it appears here with a trace.'}
      rows={(compact ? rows.slice(0, 6) : rows).map((o, i) => ({
        key: String(i), ic: o.ic, h: o.h,
        t: <>{o.title}{o.badge && <> <span className="afb afb-preparedbyagent">{o.badge}</span></>}</>,
        s: o.sub, ago: o.ago, st: <FrSt s={o.st} />,
        x: !compact && o.links.length ? <>{o.links.map((l) => <button key={l.act} className="lnk" onClick={askSoon}>{l.label}</button>)}</> : undefined,
      }))}
    />
  );
}

function RightTabs() {
  const needs = taskItems(), al = alerts().filter((a) => !a.ack), w = watches();
  const tab = homeUi('frRt') || (needs.length ? 'needs' : 'activity');
  const T: [string, string, number?][] = [['needs', 'Needs you', needs.length], ['activity', 'Activity'], ['watch', 'Watchlist'], ['notes', 'Notifications', al.length]];
  return (
    <section className="panel frrt">
      <div className="frtabs" role="tablist" aria-label="Right column">
        {T.map((t) => (
          <button key={t[0]} role="tab" aria-selected={t[0] === tab} aria-controls={'frrt-' + t[0]} onClick={() => setHomeUi('frRt', t[0])}>
            {t[1]}
            {!!t[2] && <span className="frtn">{t[2]}</span>}
          </button>
        ))}
      </div>
      <div className="pb frrtp" role="tabpanel" id="afNeeds" hidden={tab !== 'needs'}>
        <h3 className="sr">Needs you</h3>
        {needs.length ? (
          <>
            <ul className="aol">{needs.slice(0, 8).map((i, k) => <TaskRow key={k} i={i} />)}</ul>
            {needs.length > 8 && (
              <p className="note"><a className="lnk" href="#/tasks">{needs.length - 8} more in My Tasks →</a></p>
            )}
          </>
        ) : (
          <div className="empty"><b>Nothing waits on you</b>New items appear here when a step becomes yours.</div>
        )}
      </div>
      <div className="pb frrtp" role="tabpanel" id="frrt-activity" hidden={tab !== 'activity'}>
        <ActivityTimeline win="today" compact />
      </div>
      <div className="pb frrtp" role="tabpanel" id="frrt-watch" hidden={tab !== 'watch'}>
        {w.length ? (
          <ul className="aftl">
            {w.map((x) => (
              <li key={x.id}>{x.text} <button className="lnk" onClick={() => unwatch(x.id)}>Stop</button></li>
            ))}
          </ul>
        ) : (
          <p className="note">No watch rules yet. Try “tell me when inspection arrives for RT-1051”.</p>
        )}
        <button className="btn sm" onClick={askSoon}><Icon name="plus" /> Add watch</button>
      </div>
      <div className="pb frrtp" role="tabpanel" id="frrt-notes" hidden={tab !== 'notes'}>
        {al.length ? (
          <>
            <ul className="frbl">
              {al.slice(0, 6).map((a) => (
                <li key={a.id}>
                  <FrIt ic={a.ic} h={a.h} cls="sm" />
                  <span><b>{a.t}</b><span className="note">{a.s}</span></span>
                </li>
              ))}
            </ul>
            <a className="lnk" href="#/alerts">All alerts →</a>
          </>
        ) : (
          <p className="note">No notifications.</p>
        )}
      </div>
    </section>
  );
}

function QuickActions() {
  const nav = useNavigate();
  const [cfg, setCfg] = useState(false);
  const all = quickActions(), hide = frPref<string[]>('qa') || [];
  const run = (act: string) => {
    if (act === 'frConnect') return nav('/integration/overview');
    if (act === 'wfNew') {
      if (!canManageWorkflows()) return toast(noWorkflowsMessage());
      return nav('/integration/studio');
    }
    askSoon(); // frCompare opens Ask Circularity
  };
  const toggle = (label: string, on: boolean) => setFrPref('qa', on ? hide.filter((x) => x !== label) : [...hide, label]);
  return (
    <FrPanel
      title="Quick actions" id="frQa"
      right={<button className="iconbtn sm" aria-label="Choose quick actions" onClick={() => setCfg(true)}><Icon name="settings" /></button>}
    >
      <div className="frqa">
        {all.filter((q) => !hide.includes(q.label)).map((q) =>
          q.go ? (
            <a key={q.label} className="frqr" href={'#/' + q.go}><Icon name={q.icon} /><span>{q.label}</span><Icon name="chevR" /></a>
          ) : (
            <button key={q.label} className="frqr" onClick={() => run(q.act!)}><Icon name={q.icon} /><span>{q.label}</span><Icon name="chevR" /></button>
          ),
        )}
      </div>
      {cfg && (
        <Modal title="Choose quick actions" onClose={() => setCfg(false)} foot={<button className="btn pri" onClick={() => setCfg(false)}>Done</button>}>
          <div className="frchk">
            {all.map((q) => (
              <label key={q.label} className="tog">
                <input type="checkbox" checked={!hide.includes(q.label)} onChange={(e) => toggle(q.label, e.target.checked)} /> {q.label}
              </label>
            ))}
          </div>
        </Modal>
      )}
    </FrPanel>
  );
}

type ModCfg = { view?: string; order?: string[]; hide?: string[] };
function Modules() {
  const [cus, setCus] = useState(false);
  const c = frPref<ModCfg>('mods') || {}, view = c.view || 'grid', hid = c.hide || [];
  const shown = modules(), every = allModules();
  const ord = shown.map((m) => m.id).concat(every.map((m) => m.id).filter((id) => hid.includes(id)));
  const save = (n: ModCfg) => setFrPref('mods', { ...c, ...n });
  const move = (i: number, d: number) => {
    const o = ord.slice(), j = i + d;
    if (j < 0 || j >= o.length) return;
    [o[i], o[j]] = [o[j], o[i]];
    save({ order: o });
  };
  return (
    <section className="sect" id="frModules">
      <div className="sh">
        <div>
          <h2>Classic modules</h2>
          <p className="note" style={{ margin: '2px 0 0' }}>Jump into any module or let an agent guide you.</p>
        </div>
        <div className="row">
          <FrSeg name="mods" label="Module view" cur={view} items={[['grid', 'Grid', 'grid'], ['list', 'List', 'list']]} onPick={(v) => save({ view: v })} />
          <button className="btn sm" onClick={() => setCus(true)}>Customize</button>
        </div>
      </div>
      <div className={'frmods ' + view}>
        {shown.map((g) => (
          <a key={g.id} className="frmod" href={'#/' + g.go}>
            <FrIt ic={g.icon} h={g.hue} />
            <span><b>{g.label}</b><span className="note">{g.sub}</span></span>
            <Icon name="arrow" />
          </a>
        ))}
      </div>
      {cus && (
        <Modal
          title="Customize modules" onClose={() => setCus(false)}
          foot={<><button className="btn" onClick={() => save({ order: undefined, hide: undefined })}>Reset</button><button className="btn pri" onClick={() => setCus(false)}>Done</button></>}
        >
          <p className="note" style={{ marginTop: 0 }}>Show, hide and reorder the module cards on your Home. Remembered for this account.</p>
          <ul className="frcus">
            {ord.map((id, i) => {
              const g = every.find((x) => x.id === id);
              return g ? (
                <li key={id}>
                  <label className="tog">
                    <input type="checkbox" checked={!hid.includes(id)} onChange={(e) => save({ hide: e.target.checked ? hid.filter((x) => x !== id) : [...hid, id] })} /> {g.label}
                  </label>
                  <span className="row">
                    <button className="iconbtn sm" aria-label={'Move ' + g.label + ' up'} disabled={!i} onClick={() => move(i, -1)}>↑</button>
                    <button className="iconbtn sm" aria-label={'Move ' + g.label + ' down'} disabled={i >= ord.length - 1} onClick={() => move(i, 1)}>↓</button>
                  </span>
                </li>
              ) : null;
            })}
          </ul>
        </Modal>
      )}
    </section>
  );
}

function Middle({ role }: { role: string }) {
  const p = middlePanel(role);
  return (
    <FrPanel title={p.title} sub={p.sub} id={p.id} right={p.link && <a className="lnk" href={'#/' + p.link.go}>{p.link.label}</a>}>
      {p.ring && <FrRing {...p.ring} />}
      {p.bars?.map((b) => (
        <div className="frwf" key={b.l}>
          <span>{b.l}</span>
          <i style={{ width: b.w + '%', background: b.c }} />
          <b className="num">{kfmt(b.v)}</b>
        </div>
      ))}
    </FrPanel>
  );
}

function Figures() {
  const per = homeUi('frPer') || '30';
  return (
    <FrPanel
      title="Key figures" id="afFigures"
      right={
        <>
          <label className="sr" htmlFor="frPer">Period</label>
          <select className="sel" id="frPer" value={per} onChange={(e) => setHomeUi('frPer', e.target.value)}>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
            <option value="365">Last 12 months</option>
          </select>
        </>
      }
    >
      <div className="frfig">
        {figures(per).map((f) => (
          <div className="frfg" key={f.k}>
            <FrIt ic={f.ic} h={f.h} />
            <div>
              <b className="num">{f.v}</b>
              <span className="note">{f.l}</span>
              <span className="frfgs">
                {f.delta && <span className={'frd ' + f.delta.cls} data-tip={f.delta.tip}>{f.delta.text}</span>}
                <span className="note">{f.sub}</span>
              </span>
              <button className="lnk" onClick={askSoon}><Icon name="spark" /> Explain this number</button>
            </div>
          </div>
        ))}
      </div>
    </FrPanel>
  );
}

/** Home (frHome, 5.13): greeting and briefing, Ask box, KPI tiles per role, agent activity, a role panel, key figures, modules, and the right column. */
export function HomePage() {
  useBackend();
  const nav = useNavigate();
  const a = currentAccount()!, role = a.role, tech = isTechnical(), { greet, date } = greeting();
  const act = homeUi('frAct') || 'today';
  const attn = attention();
  return (
    <div className="afh frhome">
      <header className="frhh">
        <div className="frhg">
          <span className="sr">Home</span>
          <span className="note">{date}</span>
          <h1>{greet}, {role}</h1>
          <Briefing />
        </div>
        {!tech && (
          <div className="frhr">
            <Hero />
            <p className="frtag">“From data to decisions,<br />with clarity.”</p>
          </div>
        )}
        <div className="frhm">
          <span className="afprovl"><i aria-hidden="true" />{providerLabel()}</span>
          {canPage('orchestration') && (
            <div className="seg" role="group" aria-label="Experience mode">
              <button aria-pressed={!tech} onClick={() => setHomeUi('mode', 'business')}>Business</button>
              <button aria-pressed={tech} onClick={() => setHomeUi('mode', 'technical')}>Technical</button>
            </div>
          )}
        </div>
      </header>
      <div className="frhg2">
        <div className="frhmain">
          <AskBox />
          <div className="frkpis" id="frKpis">
            {kpis(role).map((k) => <FrKpi key={k.k + k.l} o={k} />)}
          </div>
          <div className="frh2">
            <FrPanel
              title="Agent activity" id="afActivity" sub="What your agents and workflows are doing across systems"
              right={<a className="lnk" href="#/audit/log">View all →</a>}
            >
              <FrSeg name="act" label="Activity period" cur={act} items={[['live', 'Live'], ['today', 'Today'], ['week', 'This week']]} onPick={(v) => setHomeUi('frAct', v)} />
              <ActivityTimeline win={act} />
            </FrPanel>
            <div className="frhst">
              <Middle role={role} />
              <Figures />
            </div>
          </div>
          <Modules />
        </div>
        <aside className="frhside">
          <RightTabs />
          {attn && <FrAttn head={attn.head} line={attn.line} btn={attn.btn} onClick={() => nav('/' + attn.go)} />}
          <QuickActions />
        </aside>
      </div>
    </div>
  );
}
