/** The menu: groups, sections and counts the signed-in account may see (the demo's NAV after the revamp). */
import { engine } from '../engine/engine';

export interface NavSection { id: string; label: string; sub: string; href: string; badge?: string }
export interface NavGroup { id: string; label: string; sub: string; icon: string; section: string; leaf: boolean; href: string; kids: NavSection[] }

type RawGroup = { id: string; label: string; sub: string; icon: string; sec?: string; leaf?: boolean; mode?: number; kids: string[][] };

export function navigation(): NavGroup[] {
  const g = engine();
  const NAV = g<RawGroup[]>('NAV');
  const visible = g<(x: RawGroup) => boolean>('frVisible');
  const kidsOf = g<(x: RawGroup) => string[][]>('navKids');
  const hrefOf = g<(x: RawGroup, k: string) => string>('navHref');
  return NAV.filter(visible).map((x) => {
    const kids = x.leaf ? [] : kidsOf(x);
    const first = x.mode ? (kids.some((k) => k[0] === 'received') ? 'received' : kids[0]?.[0] ?? '') : '';
    return {
      id: x.id, label: x.label, sub: x.sub, icon: x.icon, section: x.sec ?? '', leaf: !!x.leaf,
      href: x.leaf ? '#/' + x.id : hrefOf(x, first),
      kids: kids.map(([id, label, sub, badge]) => ({ id, label, sub, href: hrefOf(x, id), badge })),
    };
  });
}

/** Badges in the menu: decisions awaiting approval (Decision Workbench), the approvals inbox (Command Center),
 *  open conflicts (Connection Fabric), and per-section badges keyed as in NAV (conf, srcissue, wffail, inbox). */
export function navBadges(): { awaiting: number; inbox: number; integration: number; sections: Record<string, number> } {
  const g = engine();
  const S = g<{ acct: unknown; wf?: { list: { status: string; last?: { state: string } }[] } }>('S');
  const conf = g<{ status: string }[]>('CONFLICTS').filter((c) => c.status === 'open').length;
  const srcissue = g<{ status: string }[]>('SOURCES').filter((s) => s.status === 'stale' || s.status === 'unavailable').length;
  const wffail = S.wf ? S.wf.list.filter((w) => w.status === 'published' && w.last?.state === 'failed').length : 0;
  const inbox = S.acct ? g<() => unknown[]>('inboxReqs')().length : 0;
  const awaiting = g<() => { stage: string }[]>('visCases')().filter((c) => c.stage === 'awaiting_approval').length;
  const canPage = g<(p: string, s?: string) => boolean>('canPage');
  return {
    awaiting,
    inbox: canPage('command', 'approvals') ? inbox : 0,
    integration: canPage('integration', 'conflicts') ? conf : 0,
    sections: { conf, srcissue, wffail, inbox },
  };
}

export interface AlertItem { id: string; kind: string; ic: string; h: string; t: string; s: string; sev: number; go: string; ack: boolean }
/** Alerts for the signed-in account, unacknowledged and most severe first (the demo's frAlerts). */
export const alerts = (): AlertItem[] => engine()<() => AlertItem[]>('frAlerts')();

/** "Live · updated 2 min ago" */
export const liveAgo = (): string => engine()<() => string>('liveAgo')();

/** Region summary for the top bar, e.g. "EN · UTC · ₹". */
export function regionSummary(): string {
  const g = engine();
  const rg = g<{ rg: { lang: string; cur: string } }>('S').rg;
  return `${rg.lang.toUpperCase()} · ${g<() => string>('rgTzShort')()} · ${g<Record<string, string[]>>('RG_CUR')[rg.cur][0]}`;
}

/** Open counts shown in the menu and the bell. */
export const navCounts = (): { tasks: number; alerts: number } => engine()<() => { tasks: number; alerts: number }>('frCounts')();

export const logos = () => ({ dark: engine()<string>('LOGO'), light: engine()<string>('LOGO_INK') });

/** The demo's icon set (Lucide paths), as SVG markup strings keyed by name. */
export const iconSvg = (name: string): string | undefined => engine()<Record<string, string>>('ICON')[name];
