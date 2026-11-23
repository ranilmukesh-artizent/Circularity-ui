/**
 * Organisation units (plan 8, MVP-1.5): the org tree (group, segment, company, site, customer) that tenant access
 * reads; a grant on a unit covers every unit below it. The tree is the Access page's `orgs` section (GET
 * /api/screens/access, the same answer as the read action org.tree); every change is an action (org.create,
 * org.update, org.move; Admin, manageOrgs) in di/services/actions/orgs.py. A successful change invalidates every cached
 * read (actionScope: the `org` family is not narrowed, since it changes who sees what), the Access page included.
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
