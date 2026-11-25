/**
 * The adapter registry and connections made from it (plan 9, P9-8.1, registry entry I-18; backend/di/services/actions/
 * connections.py). A Developer picks an entry (Catalogue, Generic REST or From an API spec), names the system owner and the
 * org unit, and creates a connection that starts in the test environment, read only. Production access and write-back are
 * each a request the named system owner approves (never the person who asked). Every write is a connection.* or registry.*
 * action through invoke(); the reads are read actions cached per input. A write refreshes every read (invalidation.ts).
 * A secret is sent once, as `secret`, and is never returned: the server stores it encrypted.
 */
import { invoke, read } from './actions';
import type { ActionResult } from './types';

export type ConnectorKind = 'catalogue' | 'generic_rest' | 'from_spec';
export type Environment = 'test' | 'production';
export type Access = 'read' | 'read_write';
export type ApprovalStatus = 'pending' | 'approved' | 'declined';

export interface RegistryEntry {
  id: string;
  version: number;
  kind: ConnectorKind;
  system_type: string;
  vendor_family: string;
  auth_methods: string[];
  resources: Record<string, unknown>[];
  canonical_entities: string[];
  write_actions: string[];
  status: 'draft' | 'tested' | 'released' | 'deprecated';
  maintainer: string;
  source_licence: string | null;
  org_unit_id: string | null;
}

export interface ConnectionApproval {
  id: number;
  source_id: string;
  environment: Environment;
  access: Access;
  requested_by: string;
  owner: string;
  status: ApprovalStatus;
  reason: string | null;
  decided_by: string | null;
  decided_at: string | null;
}

export interface ConnectionState {
  source_id: string;
  name: string;
  environment: Environment;
  access: Access;
  system_owner: string | null;
  registry_id: string | null;
  registry_version: number | null;
  approvals: ConnectionApproval[];
}

export interface NewConnection {
  registryId: string;
  version: number;
  name: string;
  orgUnitId: string;
  systemOwner: string;
  /** required for Generic REST and API-spec entries; optional for a catalogue system */
  testBaseUrl?: string;
  /** how it signs in, one of the entry's auth methods */
  auth?: string;
  /** sent once, stored encrypted, never returned */
  secret?: string;
}

/** The entries a connection can be made from, the three kinds in order (read action, Suspense cache). */
export const registryEntries = (kind?: ConnectorKind): RegistryEntry[] =>
  read<{ entries: RegistryEntry[] }>('registry.list', kind ? { kind } : {}).entries;

type Made = ActionResult<{ source_id: string; environment: Environment; access: Access; system_owner: string; name: string }>;

export const createConnection = (c: NewConnection): Promise<Made> =>
  invoke('connection.create', {
    registry_id: c.registryId, version: c.version, name: c.name, org_unit_id: c.orgUnitId, system_owner: c.systemOwner,
    ...(c.testBaseUrl ? { test_base_url: c.testBaseUrl } : {}), ...(c.auth ? { auth: c.auth } : {}), ...(c.secret ? { secret: c.secret } : {}),
  }); // prettier-ignore

export const requestOwner = (sourceId: string, environment: Environment, access: Access, note?: string): Promise<ActionResult<{ id: number; owner: string }>> =>
  invoke('connection.requestOwner', { source_id: sourceId, environment, access, ...(note ? { note } : {}) });
export const ownerApprove = (id: number): Promise<ActionResult<{ id: number; status: 'approved' }>> => invoke('connection.ownerApprove', { id });
export const ownerDecline = (id: number, reason: string): Promise<ActionResult<{ id: number; status: 'declined' }>> => invoke('connection.ownerDecline', { id, reason });
export const promoteConnection = (sourceId: string, secret: string): Promise<ActionResult<{ source_id: string; environment: 'production' }>> =>
  invoke('connection.promote', { source_id: sourceId, secret });

/** What a sample read found (P9-8.3): records read per resource, and whether the spread over the window was used. */
export interface ConnectionSample {
  source_id: string;
  counts: Record<string, number>;
  spread: Record<string, boolean>;
}
/** Read up to 500 records per resource from a TEST connection into the dry sample store; no canonical fact is written. The
 *  stored sample is what "Suggest mappings" and the Source Tables read. A production connection is refused (conflict). */
export const discoverConnection = (sourceId: string): Promise<ActionResult<ConnectionSample>> => invoke('connection.discover', { source_id: sourceId });

/** What an API-spec import found (P9-8.6): the draft it saved, the resources it read, what it left out and the checks. */
export interface SpecImport {
  id: string;
  version: number;
  status: 'draft';
  resources: { name: string; path: string; id_field?: string; data_selector: string; include_from_parent?: string[] }[];
  auth_methods: string[];
  notes: string[];
  unsupported: string[];
  checks: { field: string; message: string }[];
  needs_fixes: boolean;
}
export interface NewSpecImport {
  name: string;
  systemType: string;
  vendorFamily: string;
  /** the OpenAPI 3 document as the person pasted or uploaded it (JSON or YAML text), never a URL */
  document: string;
  baseUrl?: string;
}
/** Turn an OpenAPI 3 document into a from_spec draft (registry.importSpec). A spec with check errors is still saved, marked
 *  needs fixes; another person releases the draft before a connection is made from it. */
export const importSpec = (s: NewSpecImport): Promise<ActionResult<SpecImport>> =>
  invoke('registry.importSpec', { name: s.name, system_type: s.systemType, vendor_family: s.vendorFamily, document: s.document, ...(s.baseUrl ? { base_url: s.baseUrl } : {}) }); // prettier-ignore

/** Where a connection stands: environment, access, system owner and the owner's approvals (read action). */
export const connectionApprovals = (sourceId: string): ConnectionState => read<ConnectionState>('connection.approvals', { source_id: sourceId });
