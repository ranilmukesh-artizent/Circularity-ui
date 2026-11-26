/** What the assistant may read: the route and the page's registered work surface, as the contract's AssistantContext. */
import type { AskContext } from '../../api/ask';
import type { RouteRef } from '../../api/types';
import type { Surface } from '../../utils/workSurface';
import type { AssistantContext } from './types';

const CASE_RX = /^RT-\d{4}$/;

export function contextOf(route: RouteRef, surface: Surface | null, role: string, section?: string): AssistantContext {
  const caseId = [route.a, route.b].find((x) => x && CASE_RX.test(x)) ?? undefined;
  const ctx: AssistantContext = {
    page: route.page || 'home',
    section: section ?? (route.a && !CASE_RX.test(route.a) ? route.a : undefined),
    caseId,
    role,
  };
  if (surface?.kind === 'flow') {
    const { flowId: id, name, template, org, canEdit, draftVer } = surface;
    ctx.flow = { id, name, template, org, canEdit, draftVer };
    ctx.org = org;
  } else if (surface?.kind === 'compose') {
    ctx.pack = surface.pack;
    ctx.org = surface.org;
    if (surface.id != null) ctx.composeId = surface.id;
  }
  return ctx;
}

/** The body of POST /api/ask's context. On the Modeler the section is the flow's template (plan 10, section 7). */
export function askContext(ctx: AssistantContext): AskContext {
  return { page: ctx.page, section: ctx.flow?.template ?? ctx.section, case_id: ctx.caseId };
}

/** "Looking at: ...", the parts the assistant may read, in the order they matter. */
export function contextParts(ctx: AssistantContext): string[] {
  const parts = [ctx.page.charAt(0).toUpperCase() + ctx.page.slice(1)];
  if (ctx.flow) {
    parts.push('Flow: ' + ctx.flow.name);
    if (ctx.org) parts.push('Org: ' + ctx.org);
    if (ctx.flow.draftVer != null) parts.push('Draft v' + ctx.flow.draftVer);
  } else {
    if (ctx.section) parts.push('Section: ' + ctx.section);
    if (ctx.pack) parts.push('Pack: ' + ctx.pack);
    if (ctx.org) parts.push('Org: ' + ctx.org);
    if (ctx.composeId != null) parts.push('Composition ' + ctx.composeId);
  }
  if (ctx.caseId) parts.push('Case: ' + ctx.caseId);
  return parts;
}
