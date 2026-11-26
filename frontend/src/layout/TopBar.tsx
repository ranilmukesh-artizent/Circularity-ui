import { Suspense, useEffect, useRef, useState } from 'react';
import { grantEndText, myAccess } from '../api/access';
import { invoke } from '../api/actions';
import { fmtDateYear } from '../api/format';
import { alerts, liveAgo, regionSummary } from '../api/nav';
import { allowedTenants, can, canPage, currentAccount, rolePolicy, roleAvatar, setTenantFilter, tenantFilter, tenants } from '../api/session';
import { Icon } from '../components/Icon';
import { IconTile } from '../components/kit/IconTile';
import { Modal } from '../components/Overlay';
import { toast } from '../components/toast';
import { useAction } from '../hooks/useAction';
import { toggleTheme, useTheme } from '../utils/theme';
import { openAsk, openAssistant } from '../utils/askBus';

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
  const region = useRef<HTMLDetailsElement>(null);
  useOutsideClose(acct);
  useOutsideClose(bell);
  useOutsideClose(region); // the region note closes on any outside click, e.g. when the account menu opens (QA B item 5)
  const [ago, setAgo] = useState(liveAgo);
  const [asking, setAsking] = useState(false);
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
      {/* Nothing searches the records from here, so Enter sends the text to the one assistant (Ask Circularity). */}
      <form
        className="search frsearch"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          const input = e.currentTarget.elements.namedItem('gs') as HTMLInputElement;
          const q = input.value.trim();
          if (q) openAsk(q);
          input.value = '';
        }}
      >
        <label className="sr" htmlFor="gs">
          Ask Circularity
        </label>
        <Icon name="search" />
        <input id="gs" name="gs" type="search" placeholder="Ask about returns, assets or workflows…" autoComplete="off" />
        <kbd aria-label="Shortcut Ctrl K">Ctrl K</kbd>
      </form>
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
          <span className="livet">{ago}</span>
        </span>
        <details className="rgm" ref={region}>
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
                    <IconTile ic={x.ic} h={x.h} cls="sm" />
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
        <button className="iconbtn afask frask" aria-label="Ask Circularity (Ctrl+J)" title="Ask Circularity (Ctrl+J)" onClick={() => openAssistant()}>
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
              <button role="menuitem" onClick={() => setAsking(true)}>
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
      {asking && <TenantAccessDialog onClose={() => setAsking(false)} />}
    </header>
  );
}

const REQ_STATUS: Record<string, [string, string]> = {
  pending: ['warn', 'Waiting for a decision'],
  approved: ['ok', 'Approved'],
  declined: ['bad', 'Declined'],
};

/** The account menu's Request tenant access: your requests and grants, and a form for a tenant you cannot see yet. */
function TenantAccessDialog({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="Request tenant access" onClose={onClose} foot={<button className="btn" onClick={onClose}>Close</button>}>
      <Suspense fallback={<p className="note">Loading your access…</p>}>
        <TenantAccessBody />
      </Suspense>
    </Modal>
  );
}

function TenantAccessBody() {
  const mine = myAccess();
  const open = mine.options.filter((o) => !o.pending);
  const [tenant, setTenant] = useState('');
  const [reason, setReason] = useState('');
  const [err, setErr] = useState('');
  const action = useAction();
  const pick = open.some((o) => o.id === tenant) ? tenant : (open[0]?.id ?? '');
  async function send() {
    setErr('');
    const res = await action.run(() => invoke<{ id: string }>('access.requestTenant', { tenant: pick, reason: reason.trim() }), { ms: 4200, inline: setErr });
    if (!res.ok) return;
    setReason('');
    toast(res.output.id + ' sent. An Approver or Admin decides it.', 4200);
  }
  return (
    <>
      {mine.grants.length > 0 && (
        <div className="callout ok" style={{ marginBottom: 12 }}>
          <b>Extra tenants you can see</b>
          {mine.grants.map((g) => (
            <div className="note" key={g.tenant}>
              {g.tenant} · {grantEndText(g.expires_at)}
            </div>
          ))}
        </div>
      )}
      {mine.requests.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <b>Your requests</b>
          {mine.requests.map((r) => (
            <div className="row" style={{ gap: 6, marginTop: 6 }} key={r.id} data-req={r.id}>
              <span className={'chip ' + REQ_STATUS[r.status][0]}>{REQ_STATUS[r.status][1]}</span>
              <span>{r.tenant}</span>
              <span className="note num">
                {r.id} · {fmtDateYear(r.at)}
                {r.status === 'declined' && r.note ? ' · ' + r.note : ''}
              </span>
            </div>
          ))}
        </div>
      )}
      {open.length ? (
        <>
          <div className="fld">
            <label htmlFor="ta-tenant">Tenant</label>
            <select id="ta-tenant" className="sel" value={pick} onChange={(e) => setTenant(e.target.value)}>
              {mine.options.map((o) => (
                <option key={o.id} value={o.id} disabled={o.pending}>
                  {o.name}
                  {o.pending ? ' · request waiting' : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="fld">
            <label htmlFor="ta-reason">Reason</label>
            <textarea id="ta-reason" maxLength={300} placeholder="Why you need to see this tenant's cases." value={reason} onChange={(e) => setReason(e.target.value)} />
            <div className="hint">At least 10 characters. An Approver or Admin reads it. Do not enter personal data.</div>
            {err && <div className="err">{err}</div>}
          </div>
          <button className="btn pri" onClick={send} disabled={action.pending}>
            Send request
          </button>
        </>
      ) : (
        <p className="note" style={{ margin: 0 }}>
          {mine.options.length ? 'Your requests are waiting for a decision.' : 'You can already see every tenant.'}
        </p>
      )}
    </>
  );
}
