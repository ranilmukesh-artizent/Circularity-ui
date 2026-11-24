/**
 * Organisation units (plan 8, MVP-1.5): the org tree (group, segment, company, site, customer) that tenant access
 * reads; a grant on a unit covers every unit below it. The tree is the Access page's `orgs` section (GET
 * /api/screens/access, the same answer as the read action org.tree); every change is an action (org.create,
 * org.update, org.move; Admin, manageOrgs) in di/services/actions/orgs.py. A successful change invalidates every cached
 * read (actionScope: the `org` family is not narrowed, since it changes who sees what), the Access page included.
 *
 * Plan 8 UI gaps: GET /api/screens/orgs (di/services/screens/orgs.py) lists the units an account may see (the Connect
 * dialog's org field) with pilot mode per unit; GET /api/screens/orgs/{unit}/pilot is the pilot report with the held
 * instructions (what would have been sent). Pilot mode is org.setPilot; the configuration pack is org.exportPack
 * (read), org.previewPack (read: what an import would create) and org.importPack (never secrets: di/services/actions/
 * org_pack.py). These read screens have no invalidation area, so every change refreshes them.
 */
import { invoke } from './actions';
import { cached } from './client';
import type { ActionResult } from './types';

export type OrgKind = 'group' | 'segment' | 'company' | 'site' | 'customer';
export const ORG_KINDS: OrgKind[] = ['group', 'segment', 'company', 'site', 'customer'];

export interface OrgNode {
  id: string;
  parent_id: string | null;
  kind: OrgKind;
  name: string;
  children: OrgNode[];
}

export interface OrgInput {
  id: string;
  parent_id: string;
  kind: OrgKind;
  name: string;
}

/** The org tree's roots (the workspace), each with its children (Suspense read cache). */
export const useOrgTree = (): OrgNode[] => cached<{ orgs?: { units: OrgNode[] } }>('/api/screens/access').orgs?.units ?? [];

/** Every unit of the tree, depth first, with its depth (for an indented list and the parent selects). */
export function flatten(nodes: OrgNode[], depth = 0): { node: OrgNode; depth: number }[] {
  return nodes.flatMap((n) => [{ node: n, depth }, ...flatten(n.children, depth + 1)]);
}

export const createOrg = (input: OrgInput): Promise<ActionResult<{ id: string }>> =>
  invoke<{ id: string }>('org.create', { ...input });

export const moveOrg = (id: string, parentId: string): Promise<ActionResult<{ id: string }>> =>
  invoke<{ id: string }>('org.move', { id, parent_id: parentId });

export const renameOrg = (id: string, name: string): Promise<ActionResult<{ id: string }>> =>
  invoke<{ id: string }>('org.update', { id, name });

// ---------------------------------------------------------------- units, pilot mode and the pilot report
/** A unit the account may see, depth first; `pilot` and `pilot_via` only for accounts that manage orgs or read reports. */
export interface OrgUnitRow {
  id: string;
  parent_id: string | null;
  kind: OrgKind;
  name: string;
  depth: number;
  pilot?: boolean;
  /** the unit whose setting puts this one in pilot mode (itself or one above it) */
  pilot_via?: string | null;
}
export interface OrgScreen {
  units: OrgUnitRow[];
  can: { manage: boolean; report: boolean };
}
export const ORG_SCREEN = '/api/screens/orgs';
/** The org units the account may see, with pilot mode (Suspense read cache). */
export const useOrgUnits = (): OrgScreen => cached<OrgScreen>(ORG_SCREEN);

/** An instruction pilot mode kept from an enterprise system: what would have been sent. */
export interface HeldInstruction {
  id: number;
  case_id: string;
  step: number;
  kind: string;
  system: string;
  target: string;
  note: string | null;
  sent_at: string | null;
}
export interface PilotReport {
  org_unit_id: string;
  cases_opened: number;
  decisions_submitted: number;
  decisions_approved: number;
  recommended_net_total: number;
  rules_applied_count: number;
  instructions_held: number;
  by_route: Record<string, number>;
  pilot: boolean;
  pilot_via: string | null;
  held: HeldInstruction[];
}
export const pilotPath = (unit: string): string => ORG_SCREEN + '/' + encodeURIComponent(unit) + '/pilot';
/** The pilot report of a unit's subtree (manageOrgs or approve.flows; Suspense read cache). */
export const usePilotReport = (unit: string): PilotReport => cached<PilotReport>(pilotPath(unit));

export const setPilot = (unit: string, on: boolean): Promise<ActionResult<{ org_unit_id: string; pilot: boolean }>> =>
  invoke<{ org_unit_id: string; pilot: boolean }>('org.setPilot', { org_unit_id: unit, on });

// ---------------------------------------------------------------- the configuration pack
/** An org's configuration pack (org.exportPack): connection settings, mappings, workflows and flows; never secrets. */
export interface OrgPack {
  version: number;
  org: { id: string; parent_id: string | null; kind: string; name: string };
  sources: { id: string; name: string; vendor: string; type: string; [k: string]: unknown }[];
  mappings: Record<string, string[][]>;
  workflows: { name: string; source_id?: string | null; [k: string]: unknown }[];
  flows: Record<string, unknown>;
}
/** What importing a pack would create (org.previewPack); nothing is written. */
export interface PackPreview {
  target_org_unit_id: string;
  origin: string;
  sources: { id: string; new_id: string; name: string; vendor: string; type: string }[];
  mappings: string[];
  workflows: { name: string | null; source_id: string | null }[];
  flows: { template: string; fork: boolean; flow_id: number | null }[];
  needs: string[];
}
export interface PackImport {
  created: { org_unit_id: string; sources: string[]; mappings: string[]; workflows: string[]; flows: number[] };
  needs: string[];
}

export const exportPack = (unit: string): Promise<ActionResult<OrgPack>> => invoke<OrgPack>('org.exportPack', { org_unit_id: unit });
export const previewPack = (pack: OrgPack, target: string): Promise<ActionResult<PackPreview>> =>
  invoke<PackPreview>('org.previewPack', { pack, target_org_unit_id: target });
export const importPack = (pack: OrgPack, target: string): Promise<ActionResult<PackImport>> =>
  invoke<PackImport>('org.importPack', { pack, target_org_unit_id: target });

/** The file name an exported pack downloads as. */
export const packFileName = (unit: string): string => 'org-pack-' + (unit.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'org') + '.json';

/** A pack read from a file's text, or why it is not one (the server checks it again). */
export function parsePack(text: string): { pack: OrgPack } | { error: string } {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return { error: 'The file is not JSON.' };
  }
  const p = data as Partial<OrgPack> | null;
  if (!p || typeof p !== 'object' || Array.isArray(p) || typeof p.version !== 'number' || !Array.isArray(p.sources)) {
    return { error: 'The file is not an org configuration pack.' };
  }
  return { pack: p as OrgPack };
}

/** The Connect dialog's org unit at the start: the top bar's tenant when it is a unit the account sees, else none
 *  ('': the source is shared by every org unit, as before the field existed). */
export const defaultConnectOrg = (units: OrgUnitRow[], tenant: string): string =>
  tenant !== 'All' && units.some((u) => u.id === tenant) ? tenant : '';