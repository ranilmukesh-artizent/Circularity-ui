/**
 * The menu: groups, sections and counts the signed-in account may see (the demo's NAV after the revamp), from
 * GET /api/screens/nav (groups, badges, tasks) and the home area's alerts.
 */
import { ICON, LOGO, LOGO_INK } from '../assets/assets.gen';
import { cached, ref, session, withQuery } from './client';
import { view } from './view';

export interface NavSection { id: string; label: string; sub: string; href: string; badge?: string }
export interface NavGroup { id: string; label: string; sub: string; icon: string; section: string; leaf: boolean; href: string; kids: NavSection[] }

interface Badges { awaiting: number; inbox: number; integration: number; sections: Record<string, number> }
interface NavAnswer { groups: NavGroup[]; badges: Badges; tasks: number }

/** GET /api/screens/nav with the view settings it depends on. */
function navAnswer(): NavAnswer {
  const v = view();
  return cached<NavAnswer>(withQuery('/api/screens/nav', { cc_mode: v.ccMode, last_asset: v.lastAsset, tenant_filter: v.tenant }));
}

export const navigation = (): NavGroup[] => navAnswer().groups;

/** Badges in the menu: decisions awaiting approval (Decision Workbench), the approvals inbox (Command Center),
 *  open conflicts that hold up a pending decision (Connection Fabric; di/services/screens/nav.py), and per-section badges keyed
 *  as in NAV (conf, srcissue, wffail, inbox). */
export const navBadges = (): Badges => navAnswer().badges;

export interface AlertItem { id: string; kind: string; ic: string; h: string; t: string; s: string; sev: number; go: string; ack: boolean }

/** Alerts for the signed-in account, unacknowledged and most severe first (the demo's frAlerts). */
export function alerts(): AlertItem[] {
  if (!session()) return [];
  const acks = view().acks;
  const all = cached<AlertItem[]>('/api/screens/home/alerts').map((a) => ({ ...a, ack: a.ack || !!acks[a.id] }));
  return [...all.filter((a) => !a.ack), ...all.filter((a) => a.ack)];
}

const LIVE_T0 = Date.now();
/** "Live · updated 2 min ago" */
export const liveAgo = (): string => 'Live · updated ' + (1 + (Math.floor((Date.now() - LIVE_T0) / 60000) % 3)) + ' min ago';

const TZ_SHORT: Record<string, string> = {
  UTC: 'UTC', 'Asia/Kolkata': 'IST', 'Asia/Tokyo': 'JST', 'Europe/Berlin': 'CET', 'Europe/Helsinki': 'EET', 'America/New_York': 'ET',
};

/** Region summary for the top bar, e.g. "EN · UTC · ₹". */
export function regionSummary(): string {
  const rg = view().rg;
  return `${rg.lang.toUpperCase()} · ${TZ_SHORT[rg.tz] ?? rg.tz} · ${ref('RG_CUR')[rg.cur][0]}`;
}

/** Open counts shown in the menu and the bell. */
export function navCounts(): { tasks: number; alerts: number } {
  if (!session()) return { tasks: 0, alerts: 0 };
  return { tasks: navAnswer().tasks, alerts: alerts().filter((a) => !a.ack).length };
}

// Assets bundled with the app (the demo's LOGO, LOGO_INK and Lucide ICON set: src/assets/assets.gen.ts).
export const logos = () => ({ dark: LOGO, light: LOGO_INK });

/** The demo's icon set (Lucide paths), as SVG markup strings keyed by name. */
export const iconSvg = (name: string): string | undefined => ICON[name];
