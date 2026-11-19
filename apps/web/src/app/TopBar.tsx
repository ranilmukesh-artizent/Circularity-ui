import { useEffect, useRef, useState } from 'react';
import { alerts, liveAgo, regionSummary } from '../api/nav';
import { allowedTenants, can, canPage, currentAccount, rolePolicy, roleAvatar, setTenantFilter, tenantFilter, tenants } from '../api/session';
import { Icon } from '../ui/Icon';
import { toggleTheme, useTheme } from '../ui/theme';
import { toast } from '../ui/toast';

/** Close a <details> menu when the user clicks outside it. */
function useOutsideClose(ref: React.RefObject<HTMLDetailsElement>) {
  useEffect(() => {
    const f = (e: MouseEvent) => {
      const d = ref.current;
      if (d?.open && (!d.contains(e.target as Node) || (e.target as Element).closest('.acmenu button, .frbl a'))) d.open = false;
    };
    document.addEventListener('click', f);
    return () => document.removeEventListener('click', f);
  }, [ref]);
}

/** The top bar (the demo's frTopHTML): menu button, search, tenant, live pill, theme and the account menu. */
export function TopBar({ onMenu, onSignOut }: { onMenu: () => void; onSignOut: () => void }) {
  const a = currentAccount()!;
  const P = rolePolicy(a.role);
  const theme = useTheme();
  const acct = useRef<HTMLDetailsElement>(null);
  const bell = useRef<HTMLDetailsElement>(null);
  useOutsideClose(acct);
  useOutsideClose(bell);
  const [ago, setAgo] = useState(liveAgo);
  useEffect(() => {
    const t = window.setInterval(() => setAgo(liveAgo()), 15000);
    return () => window.clearInterval(t);
  }, []);

  const allowed = allowedTenants();
  const open = alerts().filter((x) => !x.ack);
  return (
    <header className="top frtop" role="banner">
      <button className="iconbtn frham" aria-label="Menu" onClick={onMenu}>
        <Icon name="menu" />
      </button>
      <div className="search frsearch">
        <label className="sr" htmlFor="gs">
          Search or ask
        </label>
        <Icon name="search" />
        <input id="gs" type="search" placeholder="Search returns, assets, workflows, or ask anything…" autoComplete="off" />
        <kbd aria-label="Shortcut Ctrl K">Ctrl K</kbd>
      </div>
      <div className="tools">
        {canPage('product') && (
          <>
            <label className="sr" htmlFor="tsel">
              Tenant
            </label>
            <select className="sel" id="tsel" value={tenantFilter()} onChange={(e) => setTenantFilter(e.target.value)}>
              <option value="All">{P.tenantScoped ? 'All my tenants' : 'All tenants'}</option>
              {tenants().map((t) =>
                allowed.includes(t) ? (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ) : (
                  <option key={t} value={t} disabled>
                    {t} · locked
                  </option>
                ),
              )}
            </select>
          </>
        )}
        <span className="pill live" title="Data refreshes continuously from the connected systems">
          <span className="dot" />
          <span>{ago}</span>
        </span>
        <details className="rgm">
          <summary className="pill" aria-label="Region: language, time zone and currency" title="Language, time zone and currency">
            <Icon name="globe" />
            <span>{regionSummary()}</span>
          </summary>
          <div className="rgm-list" role="group" aria-label="Region settings">
            <p className="note" style={{ margin: 0 }}>
              Change language, time zone and currency in <a href="#/settings">Settings</a>.
            </p>
          </div>
        </details>
        <details className="frbell" ref={bell}>
          <summary className="iconbtn" aria-label={'Alerts: ' + open.length + ' open'}>
            <Icon name="bell" />
            {open.length > 0 && <span className="afcnt">{open.length}</span>}
          </summary>
          <div className="frdd frbellp">
            <div className="frbh">
              <b>Alerts</b>
              <a className="lnk" href="#/alerts">
                View all ({open.length}) →
              </a>
            </div>
            {open.length ? (
              <ul className="frbl">
                {open.slice(0, 5).map((x) => (
                  <li key={x.id}>
                    <span className="frit sm" style={{ ['--c' as string]: `var(--h-${x.h || 'neutral'})` }}>
                      <Icon name={x.ic} />
                    </span>
                    <span>
                      <a href={'#/' + x.go}>
                        <b>{x.t}</b>
                      </a>
                      <span className="note">{x.s}</span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="note">No open alerts.</p>
            )}
          </div>
        </details>
        <button className="iconbtn afask frask" aria-label="Ask Circularity (Ctrl+J)" title="Ask Circularity (Ctrl+J)" onClick={() => toast('Ask Circularity arrives soon.')}>
          <Icon name="spark" />
        </button>
        <button className="iconbtn" aria-label="Toggle theme" onClick={toggleTheme}>
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
        </button>
        <details className="acctm" ref={acct}>
          <summary className="acchip" aria-label={`Signed in as ${a.label}. Account menu`}>
            <span className="siav" aria-hidden="true">
              {roleAvatar(a.role)}
            </span>
            <b>{a.role}</b>
            {a.tenant && <small>{a.tenant}</small>}
            <span aria-hidden="true">▾</span>
          </summary>
          <div className="acmenu" role="menu">
            <div className="acd">
              <b>{a.label}</b>
              <div className="note">{P.desc}</div>
              {P.tenantScoped && (
                <div className="note" style={{ marginTop: 6 }}>
                  Tenants: {allowed.join(', ')}
                </div>
              )}
            </div>
            {can('requestTenant') && (
              <button role="menuitem" disabled title="Arrives with the Access pages">
                Request tenant access
              </button>
            )}
            <button role="menuitem" onClick={onSignOut}>
              Switch account
            </button>
            <button role="menuitem" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        </details>
      </div>
    </header>
  );
}
