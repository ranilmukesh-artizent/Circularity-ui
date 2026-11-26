import { useEffect, useRef, useState } from 'react';
import { logos, navBadge, navBadges, navCounts, navigation, type NavGroup } from '../api/nav';
import { currentAccount, roleAvatar, signInEmail } from '../api/session';
import { Icon } from '../components/Icon';
import { collapseOnModeler, keepOpen, keptOpen } from './sidebarRail';

const OPEN_KEY = 'circ-react-nav-open';
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
  const groups = navigation();
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

  let lastSection = '';
  const rows: JSX.Element[] = [];
  groups.forEach((g) => {
    if (g.section !== lastSection) {
      lastSection = g.section;
      rows.push(
        g.section === 'More' ? (
          <div key={'sec-' + g.id} className="frsec frdiv" role="presentation" />
        ) : (
          <div key={'sec-' + g.id} className="frsec" role="presentation">
            {g.section}
          </div>
        ),
      );
    }
    rows.push(
      <Group key={g.id} g={g} active={g.id === page} open={isOpen(g.id)} onToggle={() => toggle(g.id)} sectionKey={sectionKey} counts={counts} badges={badges} />,
    );
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
      <nav className="nav frnav" aria-label="Pages">
        {rows}
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
    g.id === 'tasks' ? counts.tasks
      : g.id === 'alerts' ? counts.alerts
        : g.id === 'product' ? badges.awaiting
          : g.id === 'command' ? badges.inbox
            : g.id === 'integration' ? badges.integration
              : g.id === 'mywork' ? navBadge('mywork')
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
                <span className={'cnt2' + (k.badge !== 'conf' || badges.sections[k.badge] > 0 ? ' bad' : '')}>{badges.sections[k.badge]}</span>
              ) : null}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
