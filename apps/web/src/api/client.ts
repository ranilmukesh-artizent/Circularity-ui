/**
 * The HTTP side of the facade (VITE_BACKEND=api): the signed-in session, a read cache that lets the facade stay
 * synchronous, actions, and the live stream.
 *
 * How the facade stays synchronous: pages call facade functions during render (listCases(), navBadges() …). In api
 * mode those call cached(path), which returns the last answer for that path at once. On the first read there is no
 * answer yet, so cached() throws the pending fetch: React Suspense shows the page's fallback and renders again when it
 * arrives. When data may have changed (an action, a stream event), invalidate() marks every answer stale; the pages
 * keep showing the old answer while the new one loads, then re-render (stale-while-revalidate).
 */
import type { Account, ActionResult } from './types';
import { bump } from './store';

// ---------------------------------------------------------------- session
const TOKEN_KEY = 'circ-api-token';

export interface Me {
  account: Account & { email: string };
  description: string;
  home: string;
  permissions: string[];
  pages: Record<string, string[]>;
  tenants: string[];
  tenant_scoped: boolean;
  warehouse: string | null;
}

let token: string | null = readToken();
let me: Me | null = null;
let reference: Record<string, unknown> | null = null;

function readToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
function writeToken(t: string | null) {
  token = t;
  try {
    if (t) sessionStorage.setItem(TOKEN_KEY, t);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private window: the session lasts for this page only */
  }
}

export const session = (): Me | null => me;
export const accessToken = (): string | null => token;

/** An error from di-api, with its code ("tenant_boundary", "out_of_scope" …) and HTTP status. */
export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
  }
}

async function errorOf(res: Response): Promise<ApiError> {
  let code = 'error';
  let message = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    const e = body?.error ?? body?.detail ?? body;
    if (e?.code) code = e.code;
    if (e?.message) message = e.message;
    else if (typeof e === 'string') message = e;
  } catch {
    /* not JSON */
  }
  return new ApiError(res.status, code, message);
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  return { Accept: 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}), ...extra };
}

/** GET or POST JSON; on 401 the session has expired, so sign out. */
export async function http<T>(path: string, init: { method?: string; body?: unknown; headers?: Record<string, string> } = {}): Promise<T> {
  const res = await fetch(path, {
    method: init.method ?? 'GET',
    headers: headers({ ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...init.headers }),
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (res.status === 401 && token) expire();
  if (!res.ok) throw await errorOf(res);
  return res.json() as Promise<T>;
}

/** Sign in with an ID or work email and a password. Throws ApiError with the server's message on a refusal. */
export async function login(username: string, password: string): Promise<Me> {
  const out = await http<Me & { access_token: string }>('/api/auth/login', { method: 'POST', body: { username, password } });
  writeToken(out.access_token);
  me = { account: out.account, description: out.description, home: out.home, permissions: out.permissions, pages: out.pages,
         tenants: out.tenants, tenant_scoped: out.tenant_scoped, warehouse: out.warehouse }; // prettier-ignore
  await loadReference();
  clearCache();
  startStream();
  bump();
  return me;
}

export function logout(): void {
  writeToken(null);
  me = null;
  stopStream();
  clearCache();
  bump();
}

function expire() {
  if (!me) return;
  logout();
}

/** Called once before the first render: restore the session from the token this tab holds, and load the reference. */
export async function bootApi(): Promise<void> {
  await loadReference();
  if (!token) return;
  try {
    me = await http<Me>('/api/auth/me');
    startStream();
  } catch {
    writeToken(null);
    me = null;
  }
}

/** Re-read /api/auth/me (after an access change, e.g. a delegation or the identity mapping). */
export async function refreshMe(): Promise<void> {
  if (!token) return;
  me = await http<Me>('/api/auth/me');
  bump();
}

// ---------------------------------------------------------------- reference lists (static, loaded once)
async function loadReference(): Promise<void> {
  if (reference) return;
  reference = await http<Record<string, unknown>>('/api/screens/reference');
}

/** One of the demo's static lists (ROLE_POLICY, NAV, ROUTES …), from GET /api/screens/reference. */
export function ref<T = unknown>(name: string): T {
  if (!reference) throw new Error('Reference lists are not loaded yet.');
  if (!(name in reference)) throw new Error(`No reference list ${name}.`);
  return reference[name] as T;
}

// ---------------------------------------------------------------- the read cache
interface Entry {
  data?: unknown;
  error?: unknown;
  promise?: Promise<void>;
  stale: boolean;
}
const cache = new Map<string, Entry>();

function load(key: string, e: Entry, run: () => Promise<unknown>) {
  e.promise = run()
    .then(
      (d) => {
        e.data = d;
        e.error = undefined;
      },
      (err) => {
        e.error = err;
      },
    )
    .finally(() => {
      e.promise = undefined;
      e.stale = false;
      if (cache.get(key) === e) bump();
    });
}

function readThrough<T>(key: string, run: () => Promise<unknown>): T {
  let e = cache.get(key);
  if (!e) {
    e = { stale: true };
    cache.set(key, e);
  }
  if (e.stale && !e.promise) load(key, e, run);
  if ('data' in e && e.data !== undefined) return e.data as T;
  if (e.error && !e.promise) throw e.error;
  throw e.promise;
}

/** Path with query parameters, leaving out empty ones. */
export function withQuery(path: string, q: Record<string, string | number | boolean | null | undefined> = {}): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v !== null && v !== undefined && v !== '') p.set(k, String(v));
  const s = p.toString();
  return s ? path + (path.includes('?') ? '&' : '?') + s : path;
}

/** The answer of GET path, synchronously (suspends on the first read). */
export function cached<T>(path: string): T {
  return readThrough<T>('GET ' + path, () => http(path));
}

/** The answer of a read action (POST /api/actions/{id}), synchronously; throws ApiError on a refusal. */
export function cachedAction<T>(id: string, input: Record<string, unknown> = {}): T {
  return readThrough<T>('ACT ' + id + ' ' + JSON.stringify(input), async () => {
    const r = await postAction<T>(id, input);
    if (!r.ok) throw new ApiError(400, r.error.code, r.error.message);
    return r.output;
  });
}

/** Has GET path an answer already (no suspending)? For pages that prefetch. */
export function peek<T>(path: string): T | undefined {
  return cache.get('GET ' + path)?.data as T | undefined;
}

/** Everything may have changed: refetch what pages read, keeping the old answers on screen meanwhile. */
export function invalidate(): void {
  for (const e of cache.values()) e.stale = true;
  bump();
}

function clearCache() {
  cache.clear();
}

// ---------------------------------------------------------------- actions
export interface ActionOptions {
  idempotencyKey?: string;
  confirmed?: boolean;
}

async function postAction<T>(id: string, input: Record<string, unknown>, opts: ActionOptions = {}): Promise<ActionResult<T>> {
  const res = await fetch('/api/actions/' + encodeURIComponent(id), {
    method: 'POST',
    headers: headers({
      'Content-Type': 'application/json',
      ...(opts.idempotencyKey ? { 'Idempotency-Key': opts.idempotencyKey } : {}),
      ...(opts.confirmed ? { 'X-Circularity-Confirmed': 'true' } : {}),
    }),
    body: JSON.stringify(input),
  });
  if (res.status === 401 && token) expire();
  try {
    return (await res.json()) as ActionResult<T>;
  } catch {
    return { ok: false, error: { code: 'validation_error', message: `${res.status} ${res.statusText}` } };
  }
}

/** POST /api/actions/{id}; a change makes every cached read stale. */
export async function apiInvoke<T>(id: string, input: Record<string, unknown> = {}, opts: ActionOptions = {}): Promise<ActionResult<T>> {
  const r = await postAction<T>(id, input, opts);
  if (r.ok) invalidate();
  return r;
}

// ---------------------------------------------------------------- the live stream (B15)
type StreamListener = (kind: string, data: unknown) => void;
const streamListeners = new Set<StreamListener>();
let source: EventSource | null = null;
let pending: number | null = null;
let lastStreamAt = 0;

const KINDS = ['journal', 'event', 'notification', 'sync', 'step', 'workflow']; // di/stream.py, migrations 0008-0009

/** Listen to stream events (kind, data); returns the unsubscribe function. */
export function onStream(l: StreamListener): () => void {
  streamListeners.add(l);
  return () => {
    streamListeners.delete(l);
  };
}

/** When the stream last delivered an event (ms since epoch; 0 before any). */
export const lastStreamEvent = () => lastStreamAt;

function startStream() {
  stopStream();
  if (!token || typeof EventSource === 'undefined') return;
  source = new EventSource('/api/stream?access_token=' + encodeURIComponent(token));
  const handle = (kind: string) => (ev: MessageEvent) => {
    lastStreamAt = Date.now();
    let data: unknown = ev.data;
    try {
      data = JSON.parse(ev.data);
    } catch {
      /* plain text */
    }
    streamListeners.forEach((l) => l(kind, data));
    // several events often arrive together (a sync, an approval's journal and events): refetch once
    if (pending === null) pending = window.setTimeout(() => ((pending = null), invalidate()), 150);
  };
  for (const k of KINDS) source.addEventListener(k, handle(k) as EventListener);
  source.onmessage = handle('message');
}

function stopStream() {
  source?.close();
  source = null;
}
