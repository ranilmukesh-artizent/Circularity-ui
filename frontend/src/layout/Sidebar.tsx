import { useEffect, useRef, useState } from 'react';
import { logos, navBadges, navCounts, navStaged, navigation, type NavGroup } from '../api/nav';
import { currentAccount, roleAvatar, signInEmail } from '../api/session';
import { Icon } from '../components/Icon';
import { collapseOnModeler, keepOpen, keptOpen } from './sidebarRail';
import { COLLAPSIBLE, STAGED_NOTE, advancedOpen, menuSections } from './sidebarView';

const OPEN_KEY = 'circ-react-nav-open';
const ADV_KEY = 'circ-react-nav-advanced'; // the Advanced section: "1" open, "0" closed, absent: the default
const loadAdv = (): boolean | undefined => {
  try {
    const v = localStorage.getItem(ADV_KEY);
    return v === null ? undefined : v === '1';
  } catch {
    return undefined;
  }
};
const loadOpen = (): Record<string, boolean> => {
  try {
    return JSON.parse(localStorage.getItem(OPEN_KEY) || '{}');
  } catch {
    return {};
  }
};

/** The menu with sections (the demo's frSideHTML / frNavHTML). */
export function Sidebar({ page, sectionKey, rail, onRail, onSignOut }: {
  page: string;
  sectionKey: string; // "integration/studio"
  rail: boolean;
  onRail: () => void;
  onSignOut: () => void;
}) {
  const a = currentAccount()!;
  const [open, setOpen] = useState<Record<string, boolean>>(loadOpen);
  const [adv, setAdv] = useState<boolean | undefined>(loadAdv);
  const groups = navigation();
  const staged = navStaged();
  const counts = navCounts();
  const badges = navBadges();

  // The Modeler starts with the icon sidebar below 1600px (plan 10, 3.2) and gives the full one back on leaving, unless
  // the person opened it there. The ref stops a double effect run (StrictMode) from toggling twice.
  const autoRail = useRef(false);
  useEffect(() => {
    if (!autoRail.current && collapseOnModeler(page, window.innerWidth, rail, keptOpen())) {
      autoRail.current = true;
      onRail();
    } else if (autoRail.current && page !== 'modeler') {
      autoRail.current = false;
      onRail();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a change of page decides
  }, [page]);
  const railClick = () => {
    if (page === 'modeler' && rail) keepOpen(); // opened by hand on the Modeler: keep it open there
    autoRail.current = false; // the person's choice from now on
    onRail();
  };

  // One search: Ctrl K (Cmd K) focuses the top bar's box.
  useEffect(() => {
    const f = (ev: KeyboardEvent) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {
        ev.preventDefault();
        document.getElementById('gs')?.focus();
      }
    };
    document.addEventListener('keydown', f);
    return () => document.removeEventListener('keydown', f);
  }, []);

  const toggle = (id: string) => {
    const next = { ...open, [id]: !isOpen(id) };
    setOpen(next);
    try {
      localStorage.setItem(OPEN_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
  };
  const isOpen = (id: string) => open[id] ?? id === page;

  // Keep the current section in view: the menu scrolls under the footer, so the last child (Manual Import) can sit hidden (UI QA 26).
  const navRef = useRef<HTMLElement>(null);
  useEffect(() => {
    navRef.current?.querySelector('.ng.active')?.scrollIntoView({ block: 'nearest' }); // the page you are on (Settings, Audit stay reachable)
    const el = navRef.current?.querySelector<HTMLElement>('.nsl[aria-current="page"]');
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [page, sectionKey, open]);

  const groupRow = (g: NavGroup) => (
    <Group key={g.id} g={g} active={g.id === page} open={isOpen(g.id)} onToggle={() => toggle(g.id)} sectionKey={sectionKey} counts={counts} badges={badges} />
  );
  const toggleAdv = (now: boolean) => {
    setAdv(!now);
    try {
      localStorage.setItem(ADV_KEY, now ? '0' : '1');
    } catch {
      /* ignore */
    }
  };
  const rows: JSX.Element[] = [];
  menuSections(groups).forEach((sec) => {
    const id = sec.groups[0].id;
    if (sec.name === COLLAPSIBLE) {
      const on = advancedOpen(adv, sec, page);
      rows.push(
        <button key={'sec-' + id} type="button" className="frsec frtog" aria-expanded={on} aria-controls="ns-advanced" onClick={() => toggleAdv(on)}>
          <span>{sec.name}</span>
          <Icon name="chevR" />
        </button>,
        <div key={'adv-' + id} id="ns-advanced" role="group" aria-label={sec.name} hidden={!on}>
          {sec.groups.map(groupRow)}
        </div>,
      );
      return;
    }
    if (sec.name === 'More') rows.push(<div key={'sec-' + id} className="frsec frdiv" role="presentation" />);
    else if (sec.name) rows.push(<div key={'sec-' + id} className="frsec" role="presentation">{sec.name}</div>);
    rows.push(...sec.groups.map(groupRow));
  });

  return (
    <aside className="side frside">
      <div className="frbrand">
        <a href="#/home" aria-label="Artizent Circularity home">
          <img className="frlg dk" src={logos().dark} alt="Artizent" />
          <img className="frlg lt" src={logos().light} alt="Artizent" />
        </a>
        <button className="railbtn" aria-pressed={rail} aria-label={rail ? 'Expand sidebar' : 'Collapse sidebar'} onClick={railClick}>
          <Icon name="railc" />
        </button>
      </div>
      <button className="frms" aria-label="Search or ask" data-label="Search" onClick={() => document.getElementById('gs')?.focus()}>
        <Icon name="search" />
        <span>Search</span>
      </button>
      <nav ref={navRef} className="nav frnav" aria-label="Pages">
        {rows}
        {staged && <p className="frstaged" role="note">{STAGED_NOTE}</p>}
      </nav>
      <div className="frfoot">
        <details className="side-foot frco">
          <summary data-label="Northfield Industrial Leasing">
            <Icon name="building" />
            <span className="frcot">
              <b>Northfield Industrial Leasing</b>
              <small>Production · 8 sites</small>
            </span>
            <Icon name="chevD" />
          </summary>
          <div className="frcom">
            <p>
              3 customer tenants · 8 sites
              <br />
              Production · all systems operational
            </p>
          </div>
        </details>
        <div className="fruser" data-label={a.label}>
          <span className="siav" aria-hidden="true">
            {roleAvatar(a.role)}
          </span>
          <span className="frut">
            <b>{a.role}</b>
            <small>{signInEmail(a)}</small>
          </span>
          <button className="iconbtn sm" aria-label="Sign out" title="Sign out" onClick={onSignOut}>
            <Icon name="logout" />
          </button>
        </div>
      </div>
    </aside>
  );
}

function Group({ g, active, open, onToggle, sectionKey, counts, badges }: {
  g: NavGroup; active: boolean; open: boolean; onToggle: () => void; sectionKey: string;
  counts: { tasks: number; alerts: number }; badges: ReturnType<typeof navBadges>;
}) {
  const n =
    g.id === 'tasks' ? badges.mine ?? counts.tasks // what waits on the person, without the data conflicts (one page, one count)
      : g.id === 'alerts' ? counts.alerts
        : g.id === 'product' ? badges.awaiting
          : g.id === 'command' ? badges.inbox
            : g.id === 'integration' ? badges.integration
              : 0;
  const cnt = n ? <span className={'cnt' + (g.id === 'alerts' ? ' bad' : '')}>{n}</span> : null;
  return (
    <div className={'ng' + (g.leaf ? ' leaf' : '') + (active ? ' active' : '')} data-g={g.id}>
      <div className="ngr">
        <a className="ngh" href={g.href} data-label={g.label} aria-label={g.label} aria-current={active && g.leaf ? 'page' : undefined}>
          <Icon name={g.icon} />
          <span className="ngl">{g.label}</span>
          {cnt}
        </a>
        {g.kids.length > 0 && (
          <button className="chev" aria-expanded={open} aria-controls={'ns-' + g.id} aria-label={g.label + ': show sections'} onClick={onToggle}>
            <Icon name="chevR" />
          </button>
        )}
      </div>
      {g.kids.length > 0 && (
        <div className="nsub" id={'ns-' + g.id} role="group" aria-label={g.label + ' sections'} hidden={!open}>
          {g.kids.map((k) => (
            <a key={k.id} className="nsl" href={k.href} aria-current={sectionKey === g.id + '/' + k.id ? 'page' : undefined}>
              {k.label}
              {k.badge && badges.sections[k.badge] ? (
                <span className={'cnt2' + (k.badge !== 'conf' || badges.sections[k.badge] > 0 ? ' bad' : '')} title={k.badge === 'conf' ? `${badges.sections[k.badge]} open conflicts hold a decision. The Conflict Queue lists every open conflict.` : undefined}>{badges.sections[k.badge]}</span>
              ) : null}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
