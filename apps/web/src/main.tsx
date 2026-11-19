import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createHashRouter, RouterProvider } from 'react-router-dom';
import './styles/legacy.gen.css';
import './app/app.css';
import { App } from './app/App';
import { StatusPage } from './pages/StatusPage';
import { applyTheme } from './ui/theme';

// The demo's revamped look (fr) and stage pages (st) are scoped by classes on <html>; they are the default build.
document.documentElement.classList.add('fr', 'st');
applyTheme();

// Hash routes, as in the demo (#/product/asset/RT-1048), so existing links and the demo script still work.
const router = createHashRouter([
  { path: '/_status', element: <StatusPage /> }, // stack health (web → di-api → Postgres, source-sim)
  { path: '*', element: <App /> },
]);
const queryClient = new QueryClient();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
