import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { createHashRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom'; // the DOM build: hands react-dom's flushSync to the router
import './styles/legacy.gen.css';
import './styles/assistant.css';
import './layout/app.css';
import { App } from './layout/App';
import { StatusPage } from './pages/StatusPage';
import { applyTheme } from './utils/theme';
import { bootApi, queryClient } from './api/client';

// The demo's revamped look (fr) and stage pages (st) are scoped by classes on <html>; they are the default build.
document.documentElement.classList.add('fr', 'st');
applyTheme();

// Hash routes, as in the demo (#/product/asset/RT-1048), so existing links and the demo script still work.
const router = createHashRouter([
  { path: '/_status', element: <StatusPage /> }, // stack health (web → di-api → Postgres, source-sim)
  { path: '*', element: <App /> },
]);
const root = createRoot(document.getElementById('root')!);

// useTransitions={false}: react-router 7 otherwise wraps every navigation in React.startTransition, and React then keeps
// the old page on screen while the next one suspends on its first read (no "Loading…", the sidebar lags behind the
// click). Off, navigations render at once and the page's Boundary shows its fallback, as with react-router 6.
function render() {
  root.render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} useTransitions={false} />
      </QueryClientProvider>
    </StrictMode>,
  );
}

// Restore the session this tab holds and load the reference lists before the first render.
bootApi().then(render, (err) => {
  console.error(err);
  root.render(<p className="note" style={{ padding: 24 }}>Could not reach di-api ({String(err?.message ?? err)}). Check that the stack is running, then reload.</p>);
});
