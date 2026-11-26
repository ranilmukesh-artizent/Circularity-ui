import { useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router';
import { useBackend } from '../api/useBackend';
import { canRoute, currentAccount, homeRoute, setBackendTheme, signOut } from '../api/session';
import type { RouteRef } from '../api/types';
import { NotPortedPage } from '../pages/NotPortedPage';
import { pageFor } from '../pages/registry';
import { OAuthConsentPage } from '../pages/OAuthConsentPage';
import { SignInPage } from '../pages/SignInPage';
import { Boundary } from '../components/Boundary';
import { useTheme } from '../utils/theme';
import { toast, Toasts } from '../components/toast';
import { AssistantDock } from './assistant/AssistantDock';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

function parse(pathname: string): RouteRef {
  const h = pathname.replace(/^\/+/, '').split('/').filter(Boolean);
  return { page: h[0] || '', a: h[1] || null, b: h[2] || null };
}

/** Root: sign-in when signed out, otherwise the shell with the page for the current #/route. */
export function App() {
  useBackend();
  const theme = useTheme();
  useEffect(() => setBackendTheme(theme), [theme]);
  const loc = useLocation();
  const route = parse(loc.pathname);
  const acct = currentAccount();

  if (!acct) {
    const next = route.page && route.page !== 'signin' ? loc.pathname.slice(1) + loc.search : undefined;
    return (
      <>
        <div id="app" className="app signedout">
          {/* the account list is a cached read: after sign-out clears the cache it suspends until it is refetched */}
          <Boundary>
            <SignInPage next={next} />
          </Boundary>
        </div>
        <Toasts />
      </>
    );
  }
  if (route.page === 'oauth' && route.a === 'consent') {
    // P9-13.10: the consent page of an outside MCP client's authorization request, outside the shell like the sign-in page
    return <Boundary><OAuthConsentPage req={new URLSearchParams(loc.search).get('req') ?? ''} /></Boundary>;
  }
  if (!route.page || route.page === 'signin') return <Navigate to={'/' + homeRoute()} replace />;
  return (
    <Boundary>
      <Shell route={route} search={loc.search} />
    </Boundary>
  );
}

function Shell({ route, search }: { route: RouteRef; search: string }) {
  const nav = useNavigate();
  const [rail, setRail] = useState(() => {
    try {
      return localStorage.getItem('circ-react-rail') === '1';
    } catch {
      return false; // blocked site data: start with the full sidebar
    }
  });
  const [menu, setMenu] = useState(false);
  const allowed = canRoute(route);
  const Page = pageFor(route.page) ?? NotPortedPage;

  useEffect(() => setMenu(false), [route.page, route.a, route.b]);
  useEffect(() => {
    if (allowed === true) return;
    toast(allowed === 'tenant' ? 'That record belongs to a tenant or warehouse you cannot see.' : 'That page is not available for your role.');
  }, [allowed]);

  const doSignOut = () => {
    const label = currentAccount()?.label;
    signOut();
    nav('/signin', { replace: true });
    toast('Signed out of ' + label + '.');
  };
  const toggleRail = () =>
    setRail((r) => {
      try {
        localStorage.setItem('circ-react-rail', r ? '0' : '1');
      } catch {
        /* private window: the choice lasts for this page only */
      }
      return !r;
    });

  if (allowed !== true) return <Navigate to={'/' + homeRoute()} replace />;

  return (
    <>
      <div id="app" className={'app' + (rail ? ' rail' : '') + (menu ? ' navm' : '')}>
        <Sidebar page={route.page} sectionKey={route.page + '/' + (route.a ?? '')} rail={rail} onRail={toggleRail} onSignOut={doSignOut} />
        <div className="main">
          <TopBar onMenu={() => setMenu((m) => !m)} onSignOut={doSignOut} />
          <main className="page" id="view" tabIndex={-1}>
            <Boundary resetKey={route.page + '/' + (route.a ?? '') + '/' + (route.b ?? '')}>
              <Page route={route} query={new URLSearchParams(search)} />
            </Boundary>
          </main>
        </div>
        <div className="frscrim" aria-hidden="true" onClick={() => setMenu(false)} />
      </div>
      <AssistantDock />
      <Toasts />
    </>
  );
}
