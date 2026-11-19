/**
 * The in-browser mock backend.
 *
 * It runs the static demo's own logic (seeded world, access policy, actions with invoke(), journal, agent runtime)
 * unchanged, behind inert DOM shims, so every number and rule matches index.html exactly. Its render functions are
 * never called: the React pages draw everything. Nothing outside src/api/ may import this file; when the Python
 * backend lands, src/api/ switches to fetch() and this file goes away.
 */
import SOURCE from './legacy.gen.js';

type Get = <T = any>(name: string) => T; // eslint-disable-line @typescript-eslint/no-explicit-any

/** An element that is never attached to anything. Legacy code that looks for page nodes finds nothing. */
class InertElement {
  classList = { add() {}, remove() {}, toggle: () => false, contains: () => false };
  dataset: Record<string, string> = {};
  style: Record<string, unknown> = { setProperty() {}, removeProperty() {} };
  children: unknown[] = [];
  parentNode = null;
  innerHTML = '';
  textContent = '';
  value = '';
  open = false;
  hidden = true;
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest() { return null; }
  matches() { return false; }
  addEventListener() {}
  removeEventListener() {}
  appendChild<T>(c: T) { return c; }
  remove() {}
  setAttribute() {}
  getAttribute() { return null; }
  removeAttribute() {}
  contains() { return false; }
  focus() {}
  blur() {}
  click() {}
  scrollIntoView() {}
  scrollTo() {}
  insertAdjacentHTML() {}
  getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0, right: 0, bottom: 0 }; }
}

class InertObserver { observe() {} unobserve() {} disconnect() {} }

const safe = (f: () => void) => () => { try { f(); } catch (e) { console.warn('[engine timer]', e); } };

function shims(): Record<string, unknown> {
  const doc = {
    documentElement: new InertElement(), body: new InertElement(), head: new InertElement(), activeElement: null, title: '',
    hidden: false, visibilityState: 'visible',
    querySelector: () => null, querySelectorAll: () => [], getElementById: () => null, createElement: () => new InertElement(),
    addEventListener() {}, removeEventListener() {},
  };
  const loc = { search: '', hash: '', href: window.location.origin + '/', pathname: '/', origin: window.location.origin, reload() {} };
  const win = {
    addEventListener() {}, removeEventListener() {}, scrollTo() {}, open() { return null; }, print() {},
    location: loc, innerWidth: window.innerWidth, innerHeight: window.innerHeight, scrollY: 0,
  };
  return {
    document: doc, window: win, location: loc,
    history: { replaceState() {}, pushState() {}, back() {} },
    addEventListener() {}, removeEventListener() {}, scrollTo() {}, scrollY: 0,
    matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
    getComputedStyle: () => ({ getPropertyValue: () => '' }),
    requestAnimationFrame: () => 0, cancelAnimationFrame() {},
    ResizeObserver: InertObserver, IntersectionObserver: InertObserver, MutationObserver: InertObserver,
    alert() {}, confirm: () => true, print() {},
    setTimeout: (f: () => void, ms?: number) => window.setTimeout(safe(f), ms),
    setInterval: (f: () => void, ms?: number) => window.setInterval(safe(f), ms),
    clearTimeout: (id: number) => window.clearTimeout(id),
    clearInterval: (id: number) => window.clearInterval(id),
  };
}

let get: Get | null = null;
let set: ((name: string, value: unknown) => void) | null = null;

function boot() {
  const s = shims();
  // Non-strict on purpose: the demo's script is sloppy-mode code. eval() inside the returned closures reads and
  // writes the script's own top-level bindings (const CASES, let RNG, function invoke …).
  // eslint-disable-next-line @typescript-eslint/no-implied-eval
  const fn = new Function(
    ...Object.keys(s),
    SOURCE + '\n;return [function(__n){return eval(__n)},function(__n,__v){eval(__n+"=__v")}];',
  );
  [get, set] = fn(...Object.values(s));
  const g = get!;
  g<() => void>('afBoot')(); // replay the journal of earlier actions (localStorage 'circ-af-v1')
  const acct = g<() => unknown>('sessionLoad')();
  g<(a: unknown) => void>('setAcct')(acct);
  g<(t: string, f: () => void) => void>('afOn')('*', bump); // every action, sync and boot event re-renders React
}

/** Read any top-level binding of the engine (data, helpers, functions). */
export function engine(): Get {
  if (!get) boot();
  return get!;
}

/** Assign a top-level `let` binding of the engine. Rarely needed: most state lives on the S object. */
export function engineSet(name: string, value: unknown) {
  if (!set) boot();
  set!(name, value);
}

// ---- change notification: React subscribes through useEngineVersion() (src/api/hooks.ts) ----
let version = 0;
const listeners = new Set<() => void>();
export function bump() {
  version++;
  listeners.forEach((l) => l());
}
export function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}
export const getVersion = () => version;
