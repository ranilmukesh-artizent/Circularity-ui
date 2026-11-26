import { useMemo } from 'react';
import { useLocation } from 'react-router';
import { currentAccount } from '../../api/session';
import { useSurface } from '../../utils/workSurface';
import { contextOf } from './context';
import type { AssistantContext } from './types';

/** The context of the page the person is on: the route, the page's registered surface and the account's role. */
export function useAssistantContext(section?: string): AssistantContext {
  const { pathname } = useLocation();
  const surface = useSurface();
  const role = currentAccount()?.role ?? '';
  return useMemo(() => {
    const h = pathname.replace(/^\/+/, '').split('/').filter(Boolean);
    return contextOf({ page: h[0] || '', a: h[1] || null, b: h[2] || null }, surface, role, section);
  }, [pathname, surface, role, section]);
}
