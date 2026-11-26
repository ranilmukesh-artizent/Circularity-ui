import { useMemo } from 'react';
import { useLocation } from 'react-router';
import { currentAccount } from '../../api/session';
import { useSurface } from '../../utils/workSurface';
import { contextOf } from './context';
import { useUi } from './store';
import type { AssistantContext } from './types';

/** The context of the page the person is on: the route, the page's registered surface, the account's role and the composition asked for. */
export function useAssistantContext(section?: string): AssistantContext {
  const { pathname } = useLocation();
  const surface = useSurface();
  const role = currentAccount()?.role ?? '';
  const asked = useUi().composeId;
  return useMemo(() => {
    const h = pathname.replace(/^\/+/, '').split('/').filter(Boolean);
    const ctx = contextOf({ page: h[0] || '', a: h[1] || null, b: h[2] || null }, surface, role, section);
    // the page's own composition wins; else the one openAssistant({ composeId }) named
    if (ctx.composeId == null && asked != null) ctx.composeId = asked;
    return ctx;
  }, [pathname, surface, role, section, asked]);
}
