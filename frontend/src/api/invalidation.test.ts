// @vitest-environment jsdom
// What a live-stream event or an action makes stale (invalidation.ts), and that client.ts uses it.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { actionScope, areaOf, matcher, streamScope, union, type Scope } from './invalidation';
import { apiInvoke, cached, invalidate, login, logout, queryClient } from './client';

const G = (path: string) => ['GET', path] as const;
/** Representative keys, one or more per area, and keys with no known area. */
const KEYS = {
  home: G('/api/screens/home?tenant_filter=All'),
  homeTasks: G('/api/screens/home/tasks'),
  alerts: G('/api/screens/home/alerts'),
  command: G('/api/screens/command/inbox'),
  nav: G('/api/screens/nav?cc_mode=operational&tenant_filter=All'),
  scope: G('/api/screens/nav/scope'),
  accounts: G('/api/screens/nav/accounts'),
  product: G('/api/screens/product/RT-1048'),
  case: G('/api/screens/case/RT-1048/analysis'),
  caseGet: ['ACT', 'case.get', { id: 'RT-1048' }] as const,
  orchestration: G('/api/screens/orchestration/run/RT-1048'),
  analytics: G('/api/screens/analytics?win=30'),
  analyticsModels: ['ACT', 'analytics.models', {}] as const,
  audit: G('/api/screens/audit?tenant_filter=All'),
  integration: G('/api/screens/integration/sources'),
  workflows: G('/api/screens/workflows/WF-1'),
  mcp: G('/api/screens/mcp/calls'),
  access: G('/api/screens/access'),
  reference: G('/api/screens/reference'),
  catalog: G('/api/actions'),
  checks: G('/api/checks'), // no known area
  otherAct: ['ACT', 'cases.list', {}] as const, // no known area
};
type K = keyof typeof KEYS;
const ALL = Object.keys(KEYS) as K[];

/** Which representative keys a scope's matcher selects. */
function hit(scope: Scope): K[] {
  const m = matcher(scope);
  if (m === null) return [];
  if (m === undefined) return ALL;
  return ALL.filter((k) => m(KEYS[k]));
}
const without = (...ks: K[]) => ALL.filter((k) => !ks.includes(k));
const ev = (case_id: string | null, payload: Record<string, unknown> = {}) => ({ id: 1, kind: 'x', case_id, at: '', payload });

describe('areaOf', () => {
  it('puts each read in its area, sub-paths first, query strings ignored', () => {
    expect(areaOf(KEYS.home)).toBe('home');
    expect(areaOf(KEYS.homeTasks)).toBe('home');
    expect(areaOf(KEYS.alerts)).toBe('alerts');
    expect(areaOf(KEYS.nav)).toBe('nav');
    expect(areaOf(KEYS.scope)).toBe('scope');
    expect(areaOf(KEYS.accounts)).toBe('accounts');
    expect(areaOf(KEYS.caseGet)).toBe('case');
    expect(areaOf(KEYS.analyticsModels)).toBe('analytics');
    expect(areaOf(KEYS.catalog)).toBe('catalog');
  });
  it('has no area for reads it does not know', () => {
    expect(areaOf(KEYS.checks)).toBeNull();
    expect(areaOf(KEYS.otherAct)).toBeNull();
    expect(areaOf(G('/api/screens/brand-new/thing'))).toBeNull();
    expect(areaOf(['POST', '/api/x'])).toBeNull();
  });
});

describe('stream events', () => {
  it('a sync run refreshes the Connection Fabric, the menu badges, Analytics, Home and the Command Center', () => {
    const s = streamScope('sync', ev(null, { id: 9, source_id: 'erp', status: 'ok' }));
    expect(hit(s)).toEqual(['home', 'homeTasks', 'command', 'nav', 'analytics', 'analyticsModels', 'integration', 'checks', 'otherAct']);
  });
  it('a workflow change or run step refreshes the Workflow Studio and the Connection Fabric only', () => {
    expect(hit(streamScope('workflow', ev(null, { collection: 'workflow_runs', op: 'update' })))).toEqual(['integration', 'workflows', 'checks', 'otherAct']);
  });
  it('a notification refreshes the alerts, the badges, Home, the Command Center and the asset page', () => {
    expect(hit(streamScope('notification', ev('RT-1048', { to: 'approver' })))).toEqual(['home', 'homeTasks', 'alerts', 'command', 'nav', 'product', 'checks', 'otherAct']);
  });
  it('an instruction step refreshes the summaries and the case pages', () => {
    expect(hit(streamScope('step', ev('RT-1048', { status: 'sent' })))).toEqual(
      without('accounts', 'integration', 'workflows', 'mcp', 'access', 'reference', 'catalog'),
    );
  });
  it('an event-log item refreshes the case pages only when it is about a case', () => {
    expect(hit(streamScope('event', ev('RT-1048')))).toEqual(without('accounts', 'workflows', 'mcp', 'access', 'reference', 'catalog'));
    expect(hit(streamScope('event', ev(null)))).toEqual(['home', 'homeTasks', 'command', 'nav', 'audit', 'integration', 'checks', 'otherAct']);
  });
  it('a decision (journal action.decision.approve) refreshes product, case, command, home, inbox, analytics, audit', () => {
    const got = hit(streamScope('journal', ev('RT-1048', { type: 'action.decision.approve', seq: 3 })));
    for (const k of ['product', 'case', 'caseGet', 'command', 'home', 'alerts', 'nav', 'analytics', 'audit', 'orchestration', 'access'] as K[]) expect(got).toContain(k);
    for (const k of ['integration', 'workflows', 'mcp', 'reference', 'catalog', 'accounts'] as K[]) expect(got).not.toContain(k);
  });
  it('journal types an action emits, and stage moves, are case writes', () => {
    for (const type of ['decision.submitted', 'outcome.confirmed', 'instruction.sent', 'case.stage_changed']) {
      expect(streamScope('journal', ev('RT-1048', { type }))).toEqual(streamScope('journal', ev('RT-1048', { type: 'action.decision.submit' })));
    }
  });
  it('a source action on the journal refreshes the Connection Fabric', () => {
    expect(hit(streamScope('journal', ev(null, { type: 'action.source.sync' })))).toContain('integration');
  });
  it('access changes, unknown journal types, unknown kinds and malformed data refresh everything', () => {
    expect(hit(streamScope('journal', ev(null, { type: 'action.access.setDelegation' })))).toEqual(ALL);
    expect(hit(streamScope('journal', ev(null, { type: 'action.agent.setEnabled' })))).toEqual(ALL);
    expect(hit(streamScope('journal', ev(null, { type: 'something.new' })))).toEqual(ALL);
    expect(hit(streamScope('journal', ev(null, { type: 'action.brandnew.do' })))).toEqual(ALL);
    expect(hit(streamScope('journal', 'not json'))).toEqual(ALL);
    expect(hit(streamScope('message', ev(null)))).toEqual(ALL);
    expect(hit(streamScope('tenant_grant', ev(null)))).toEqual(ALL);
  });
});

describe('actions', () => {
  it('maps families; an unknown family is everything; read actions touch nothing', () => {
    expect(hit(actionScope('workflow.run'))).toEqual(['integration', 'workflows', 'checks', 'otherAct']);
    expect(hit(actionScope('source.sync'))).toContain('integration');
    expect(hit(actionScope('source.sync'))).not.toContain('product');
    expect(hit(actionScope('comment.add'))).toContain('integration');
    expect(hit(actionScope('comment.add'))).toContain('audit');
    expect(hit(actionScope('mcp.propose'))).toEqual(expect.arrayContaining(['mcp', 'access', 'nav']));
    expect(hit(actionScope('access.decideRequest'))).toEqual(ALL);
    expect(hit(actionScope('nobody.knows'))).toEqual(ALL);
    expect(matcher(actionScope('case.whatIf'))).toBeNull();
    expect(matcher(actionScope('analytics.models'))).toBeNull();
  });
});

describe('union of a burst', () => {
  it('joins the areas, and everything wins', () => {
    expect(hit(union([streamScope('workflow', {}), streamScope('sync', {})]))).toEqual(
      ['home', 'homeTasks', 'command', 'nav', 'analytics', 'analyticsModels', 'integration', 'workflows', 'checks', 'otherAct'],
    );
    expect(union([streamScope('workflow', {}), 'all'])).toBe('all');
    expect(matcher(union([]))).toBeNull();
  });
});

// ---------------------------------------------------------------- client.ts uses it
function fakeFetch(answers: Record<string, () => unknown>) {
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    const key = (init?.method ?? 'GET') + ' ' + path;
    calls.push(key);
    const a = answers[key];
    if (!a) return new Response(JSON.stringify({ detail: 'nope' }), { status: 404 });
    return new Response(JSON.stringify(a()), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));
  return calls;
}
async function suspendRead<T>(f: () => T): Promise<T> {
  for (let i = 0; i < 5; i++) {
    try {
      return f();
    } catch (p) {
      if (p instanceof Promise) await p;
      else throw p;
    }
  }
  throw new Error('never resolved');
}
const tick = async () => {
  for (let i = 0; i < 3; i++) await new Promise((r) => setTimeout(r, 0));
};
const count = (calls: string[], key: string) => calls.filter((c) => c === key).length;

const WF = '/api/screens/workflows';
const HOME = '/api/screens/home/alerts';
const CHECKS = '/api/checks';

describe('client.ts invalidates by scope', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    queryClient.clear();
  });
  afterEach(() => {
    logout();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('an action marks stale only what it can change (and reads with no known area)', async () => {
    const calls = fakeFetch({ ['GET ' + WF]: () => 1, ['GET ' + HOME]: () => 2, ['GET ' + CHECKS]: () => 3, 'POST /api/actions/workflow.save': () => ({ ok: true, output: {} }) });
    for (const p of [WF, HOME, CHECKS]) await suspendRead(() => cached(p));
    await apiInvoke('workflow.save', { id: 'WF-1' });
    for (const p of [WF, HOME, CHECKS]) cached(p);
    await tick();
    expect([count(calls, 'GET ' + WF), count(calls, 'GET ' + HOME), count(calls, 'GET ' + CHECKS)]).toEqual([2, 1, 2]);
  });

  it('a read action marks nothing stale; an unknown action marks everything stale', async () => {
    const calls = fakeFetch({ ['GET ' + WF]: () => 1, ['GET ' + HOME]: () => 2, 'POST /api/actions/case.whatIf': () => ({ ok: true, output: {} }), 'POST /api/actions/new.thing': () => ({ ok: true, output: {} }) });
    for (const p of [WF, HOME]) await suspendRead(() => cached(p));
    await apiInvoke('case.whatIf', {});
    for (const p of [WF, HOME]) cached(p);
    await tick();
    expect([count(calls, 'GET ' + WF), count(calls, 'GET ' + HOME)]).toEqual([1, 1]);
    await apiInvoke('new.thing', {});
    for (const p of [WF, HOME]) cached(p);
    await tick();
    expect([count(calls, 'GET ' + WF), count(calls, 'GET ' + HOME)]).toEqual([2, 2]);
  });

  it('refetches once more a read that was invalidated while its fetch was running', async () => {
    let n = 0;
    let release!: () => void;
    vi.stubGlobal('fetch', vi.fn(async () => {
      const v = ++n;
      if (v === 2) await new Promise<void>((r) => (release = r));
      return new Response(JSON.stringify(v), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    await suspendRead(() => cached(WF)); // answer 1
    queryClient.invalidateQueries({ refetchType: 'none' });
    cached(WF); // refetch 2 starts and waits
    await tick();
    invalidate(); // a change arrives while fetch 2 runs: its answer may predate it
    release();
    await tick();
    expect(cached(WF)).toBe(2); // fetch 2's answer, and a new fetch started for the change
    await tick();
    expect(cached(WF)).toBe(3);
    expect(n).toBe(3);
  });
});

class FakeEventSource {
  static opened: FakeEventSource[] = [];
  listeners = new Map<string, (ev: MessageEvent) => void>();
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  constructor(readonly url: string) {
    FakeEventSource.opened.push(this);
  }
  addEventListener(kind: string, l: (ev: MessageEvent) => void) {
    this.listeners.set(kind, l);
  }
  close() {}
  emit(kind: string, data: unknown, id: string) {
    this.listeners.get(kind)?.({ data: JSON.stringify(data), lastEventId: id } as MessageEvent);
  }
}

describe('client.ts: a burst of stream events', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    queryClient.clear();
    FakeEventSource.opened = [];
    vi.stubGlobal('EventSource', FakeEventSource);
  });
  afterEach(() => {
    logout();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  async function signIn() {
    await login('admin', 'x');
    await vi.waitFor(() => expect(FakeEventSource.opened).toHaveLength(1));
  }

  it('marks stale the union of what its events can change, once', async () => {
    const answers = {
      'GET /api/screens/reference': () => ({}),
      'POST /api/auth/login': () => ({ account: { id: 'admin' }, access_token: 'T' }),
      'POST /api/auth/stream-ticket': () => ({ ticket: 'k', expires_in: 60 }),
      ['GET ' + WF]: () => 1,
      ['GET ' + HOME]: () => 2,
      'GET /api/screens/integration/overview': () => 3,
    };
    const calls = fakeFetch(answers);
    await signIn();
    const INT = '/api/screens/integration/overview';
    for (const p of [WF, HOME, INT]) await suspendRead(() => cached(p));
    const es = FakeEventSource.opened[0];
    es.emit('workflow', { id: 1, kind: 'workflow', case_id: null, payload: { collection: 'workflow_runs' } }, '1');
    es.emit('sync', { id: 2, kind: 'sync', case_id: null, payload: { source_id: 'erp', status: 'ok' } }, '2');
    await new Promise((r) => setTimeout(r, 200));
    for (const p of [WF, HOME, INT]) cached(p);
    await tick();
    // workflow ∪ sync: the studio and the fabric, not Home's alerts
    expect([count(calls, 'GET ' + WF), count(calls, 'GET ' + HOME), count(calls, 'GET ' + INT)]).toEqual([2, 1, 2]);

    es.emit('tenant_grant', {}, '3'); // never registered: nothing happens
    es.onmessage?.({ data: '{}', lastEventId: '4' } as MessageEvent); // an unnamed message: everything
    await new Promise((r) => setTimeout(r, 200));
    for (const p of [WF, HOME, INT]) cached(p);
    await tick();
    expect([count(calls, 'GET ' + WF), count(calls, 'GET ' + HOME), count(calls, 'GET ' + INT)]).toEqual([3, 2, 3]);
  });
});
