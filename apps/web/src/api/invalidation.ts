/**
 * What a change can touch: which cached reads a live-stream event or an action makes stale (E6 follow-up, scoped
 * invalidation; docs/agents/plans/e6-tanstack-design.md). client.ts calls invalidate(matcher) with what this module
 * returns, instead of marking every answer stale.
 *
 * How it works. Every cached read belongs to one AREA, found from its query key (areaOf): a GET path under
 * /api/screens/<area>, with three sub-paths that have their own area because many pages read them and few changes
 * touch them (home/alerts, nav/scope, nav/accounts), and the read actions the pages use (case.get, case.evidence,
 * analytics.models). A change maps to the set of areas it can change (the tables below); the matcher selects the reads
 * in those areas. Being safe comes first:
 * - a read whose key has no known area (a new endpoint, /api/checks, another read action) is ALWAYS invalidated;
 * - an unknown stream kind, an unknown journal event type, an unknown action family invalidate EVERYTHING;
 * - access and agent changes (who may see or do what) invalidate everything, as does the stream reopening and a
 *   sign-in (client.ts clears the cache).
 * Only reads on screen refetch (the rest refetch when a page reads them again), so what this saves is the requests of
 * the page in view that the change cannot have touched.
 *
 * Why each mapping is right: from what the server's screens read (apps/api/di/screens/*.py and di/reads). Notably the
 * Connection Fabric figures on Home and the Command Center (source health, stale sources, open conflicts, failed
 * workflows, credential alerts) are the demo's starting values (di/reads/fabric.py, golden), so a sync or a workflow
 * run does not change Home's alerts; the menu badges (nav) do read the live source and conflict tables.
 */

/** Where a cached read belongs. */
export type Area =
  | 'home' | 'alerts' | 'command' | 'nav' | 'scope' | 'accounts'
  | 'product' | 'case' | 'orchestration' | 'analytics' | 'audit'
  | 'integration' | 'workflows' | 'mcp' | 'access' | 'reference' | 'catalog'; // prettier-ignore

/** A change: invalidate everything, or the reads in these areas (plus every read without a known area). */
export type Scope = 'all' | readonly Area[];

// ---------------------------------------------------------------- reads → area
const SCREEN = '/api/screens/';
/** Sub-paths with an area of their own, checked before the first path segment. */
const SUB: Record<string, Area> = { 'home/alerts': 'alerts', 'nav/scope': 'scope', 'nav/accounts': 'accounts' };
const SCREEN_AREAS = new Set<Area>(['home', 'command', 'nav', 'product', 'case', 'orchestration', 'analytics', 'audit', 'integration', 'workflows', 'mcp', 'access', 'reference']);
/** The read actions the pages cache (cachedAction): case.get and case.evidence on the Case pages, analytics.models. */
const READ_ACTION_AREA: Record<string, Area> = { 'case.get': 'case', 'case.evidence': 'case', 'analytics.models': 'analytics' };

/** The area of a query key (['GET', path] or ['ACT', id, input]), or null when it has none (always invalidated). */
export function areaOf(key: readonly unknown[]): Area | null {
  if (key[0] === 'ACT') return READ_ACTION_AREA[String(key[1])] ?? null;
  if (key[0] !== 'GET' || typeof key[1] !== 'string') return null;
  const path = key[1].split('?')[0];
  if (path === '/api/actions') return 'catalog'; // the action catalogue: fixed while the server runs
  if (!path.startsWith(SCREEN)) return null;
  const rest = path.slice(SCREEN.length).split('/');
  const sub = SUB[rest.slice(0, 2).join('/')];
  if (sub) return sub;
  return SCREEN_AREAS.has(rest[0] as Area) ? (rest[0] as Area) : null;
}

// ---------------------------------------------------------------- changes → areas
/** Home, the Command Center, the menu badges and the alerts: the summaries most case changes show in. */
const SUMMARY: Area[] = ['home', 'command', 'nav', 'alerts'];
/** Pages built from the cases (their decisions, evidence, steps, outcomes) and nav/scope (case ids, owner, location). */
const CASES: Area[] = ['product', 'case', 'orchestration', 'analytics', 'audit', 'scope'];

/**
 * A case changed (a decision, an approval, evidence, an outcome, a hand-off, a scenario, a notification). The access
 * page is included: its agent metrics are computed from the decisions (di/screens/access.py, median()).
 */
const CASE_WRITE: Area[] = [...SUMMARY, ...CASES, 'access'];
/**
 * A source, its records, tables, mappings or conflicts changed: the Connection Fabric; the menu badges (open conflicts,
 * sources with issues: the live tables); Analytics (ESG telemetry reads whether the IoT source is connected); the
 * Workflow Studio (workflows list the sources they read); Home and the Command Center for good measure (their fabric
 * tiles are the demo's starting values today, but they are the summary pages).
 */
const FABRIC_WRITE: Area[] = ['integration', 'nav', 'analytics', 'workflows', 'home', 'command'];
/** Workflows and their runs: the Workflow Studio and the Connection Fabric pages that list workflows (wf_using). */
const WORKFLOW_WRITE: Area[] = ['workflows', 'integration'];

/**
 * Action id → areas. An exact id first, then its family (the part before the first dot). Read-risk actions change
 * nothing (the action pipeline returns before the journal, di/actions/pipeline.py), so they invalidate nothing.
 */
const ACTION_EXACT: Record<string, Scope> = Object.fromEntries(
  [
    'cases.list', 'case.get', 'case.evidence', 'case.routes', 'case.whatIf', 'case.trace', 'demand.find', 'pool.optimize',
    'analytics.query', 'analytics.models', 'audit.search', 'sources.health', 'sources.diagnose', 'workflow.validate',
    'inbox.get', 'receiving.plan', 'access.lookup', 'asset.compare', 'asset.summary', 'kpi.explain', 'conflict.suggest',
    'event.explain', 'mapping.preview',
  ].map((id) => [id, [] as Area[]]), // prettier-ignore
);
const ACTION_FAMILY: Record<string, Scope> = {
  decision: CASE_WRITE,
  outcome: CASE_WRITE,
  evidence: CASE_WRITE,
  case: CASE_WRITE, // case.reevaluate
  scenario: CASE_WRITE, // saved what-if scenarios, on the Case page
  instruction: CASE_WRITE, // instruction.resend: a hand-off step
  adapter: CASE_WRITE, // adapter.acknowledge: a hand-off step
  notify: CASE_WRITE, // notifications: alerts, the asset page's notes, tasks
  escalation: CASE_WRITE,
  comment: [...CASE_WRITE, 'integration'], // comments sit under audit entries, cases and Connection Fabric records
  source: FABRIC_WRITE,
  credentials: FABRIC_WRITE,
  conflict: FABRIC_WRITE,
  import: FABRIC_WRITE,
  tables: FABRIC_WRITE,
  mapping: FABRIC_WRITE,
  workflow: WORKFLOW_WRITE, // what a run then changes elsewhere arrives as its own stream events
  mcp: [...SUMMARY, 'mcp', 'access'], // mcp.propose: a request for a person, in the inboxes and the MCP page
  access: 'all', // who may see or do what: every page can change
  agent: 'all', // agent.setEnabled: what the agents may do (access)
};

/** What a successful action can have changed. */
export function actionScope(id: string): Scope {
  return ACTION_EXACT[id] ?? ACTION_FAMILY[id.split('.')[0]] ?? 'all';
}

/** Journal event types besides "action.<id>": what the actions declare (emits) and the case lifecycle's stage moves. */
const JOURNAL_TYPES: Record<string, Scope> = {
  'case.stage_changed': CASE_WRITE,
  'decision.submitted': CASE_WRITE,
  'decision.declined': CASE_WRITE,
  'decision.reevaluated': CASE_WRITE,
  'evidence.requested': CASE_WRITE,
  'inspection.result': CASE_WRITE,
  'instruction.sent': CASE_WRITE,
  'notification.sent': CASE_WRITE,
  'notification.acknowledged': CASE_WRITE,
  'outcome.confirmed': CASE_WRITE,
};

interface StreamData {
  case_id?: string | null;
  payload?: { type?: unknown } | null;
}

/**
 * What a stream event can have changed. Kinds and payloads: di/stream.py and migrations 0008 and 0009 (database
 * triggers copy every change into stream_event).
 */
export function streamScope(kind: string, data: unknown): Scope {
  const d = (data && typeof data === 'object' ? data : {}) as StreamData;
  switch (kind) {
    case 'journal': {
      // a domain_event: "action.<id>" for every state-changing action, plus the types it emits
      const type = typeof d.payload?.type === 'string' ? d.payload.type : '';
      if (type.startsWith('action.')) return actionScope(type.slice('action.'.length));
      return JOURNAL_TYPES[type] ?? 'all';
    }
    case 'event':
      // an item of the demo-shaped event log: Home's activity, the Command Center, Connection Fabric's Event Streams,
      // Audit's event entries; with a case, also that case's pages (they list the case's events)
      return d.case_id ? [...SUMMARY, ...CASES, 'integration'] : ['home', 'command', 'nav', 'integration', 'audit'];
    case 'notification':
      // a notification: the alerts, the tasks and inbox counts, Home and the Command Center, the asset page's notes
      return [...SUMMARY, 'product'];
    case 'sync':
      // a sync run started or finished: sources, records and conflicts (FABRIC_WRITE minus the workflow list)
      return ['integration', 'nav', 'analytics', 'home', 'command'];
    case 'step':
      // an instruction step queued, sent, acknowledged or failed: hand-offs, execution, escalation clocks (alerts)
      return [...SUMMARY, ...CASES];
    case 'workflow':
      // a workflow changed or a run progressed (the worker writes after each step)
      return WORKFLOW_WRITE;
    default:
      return 'all';
  }
}

/** Several changes at once (a burst of stream events): the union of their areas; 'all' wins. */
export function union(scopes: readonly Scope[]): Scope {
  if (scopes.some((s) => s === 'all')) return 'all';
  return [...new Set(scopes.flatMap((s) => s as readonly Area[]))];
}

/**
 * The matcher for invalidate(): undefined means everything (invalidate() with no argument); otherwise it selects the
 * reads in the scope's areas and every read without a known area. Returns null when nothing needs invalidating.
 */
export function matcher(scope: Scope): ((key: readonly unknown[]) => boolean) | undefined | null {
  if (scope === 'all') return undefined;
  if (scope.length === 0) return null;
  const areas = new Set(scope);
  return (key) => {
    const a = areaOf(key);
    return a === null || areas.has(a);
  };
}
