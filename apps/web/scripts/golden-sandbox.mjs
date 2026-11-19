// The demo (index.html) run headless, shared by the golden-data scripts (dump-golden.mjs and scripts/golden/*.mjs).
//
// freshDemo() runs a fresh copy of the demo's script in its own sandbox, with inert DOM shims, the clock pinned to its
// as-of time (7 Oct 2026 09:00 UTC) and Math.random seeded, and returns a lookup of its globals: g('CASES'),
// g('invoke')(...). plain() turns any value into JSON the Python tests compare against (functions dropped, cycles as
// {"$ref": path}, dates as ISO strings, numbers rounded to 1e-6). writeGolden() writes one file under fixtures/golden.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
export const goldenDir = join(root, 'fixtures/golden');
const html = readFileSync(process.env.LEGACY_HTML ?? join(root, 'index.html'), 'utf8');
let src = /<script>([\s\S]*)<\/script>\s*<\/body>/.exec(html)[1];
src = src.replace(/^afBoot\(\);S\.acct=sessionLoad\(\);.*$/m, '').replace(/^setInterval\(\(\)=>\{try\{smTick\(\)\}.*$/m, '');

const T0 = Date.parse('2026-10-07T09:00:00Z');
class FixedDate extends Date {
  constructor(...a) { if (a.length === 0) super(T0); else super(...a); }
  static now() { return T0; }
}
const prelude = `
class El{constructor(){this.classList={add(){},remove(){},toggle(){return false},contains(){return false}};this.dataset={};this.style={setProperty(){}};this.children=[];this.parentNode=null;this.innerHTML='';this.textContent='';this.value=''}
 querySelector(){return null}querySelectorAll(){return[]}closest(){return null}matches(){return false}addEventListener(){}removeEventListener(){}appendChild(c){return c}remove(){}setAttribute(){}getAttribute(){return null}removeAttribute(){}contains(){return false}focus(){}blur(){}scrollIntoView(){}getBoundingClientRect(){return{top:0,left:0,width:0,height:0,right:0,bottom:0}}insertAdjacentHTML(){}}
var document={documentElement:new El(),body:new El(),head:new El(),activeElement:null,title:'',querySelector(){return null},querySelectorAll(){return[]},getElementById(){return null},createElement(){return new El()},addEventListener(){},removeEventListener(){},hidden:false,visibilityState:'visible'};
var __store={};var localStorage={getItem:k=>k in __store?__store[k]:null,setItem:(k,v)=>{__store[k]=String(v)},removeItem:k=>{delete __store[k]}};var sessionStorage=localStorage;
var location={search:'',hash:'',href:'http://localhost/',pathname:'/',reload(){}};
var history={replaceState(){},pushState(){},back(){}};var navigator={userAgent:'node',clipboard:{writeText:async()=>{}},language:'en-GB'};
var window=globalThis;var addEventListener=()=>{};var removeEventListener=()=>{};var scrollTo=()=>{};var scrollY=0;var innerWidth=1280;var innerHeight=800;
var matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});var getComputedStyle=()=>({getPropertyValue:()=>''});
var requestAnimationFrame=f=>0;var cancelAnimationFrame=()=>{};var ResizeObserver=class{observe(){}disconnect(){}};var IntersectionObserver=ResizeObserver;var MutationObserver=ResizeObserver;
var CSS={escape:s=>s};var alert=()=>{};var confirm=()=>true;
(function(){let s=20261007;Math.random=function(){s=(s+0x6D2B79F5)|0;let t=Math.imul(s^(s>>>15),1|s);t=(t+Math.imul(t^(t>>>7),61|t))^t;return((t^(t>>>14))>>>0)/4294967296}})();
`;

/** A fresh copy of the demo in its own sandbox; returns a lookup of its globals. */
export function freshDemo() {
  const ctx = vm.createContext({
    console, Date: FixedDate, Intl, TextEncoder, crypto: globalThis.crypto, performance: { now: () => 0 },
    setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  });
  vm.runInContext(prelude + src + '\n;globalThis.__get=function(n){return eval(n)};', ctx, { timeout: 60000 });
  return (n) => ctx.__get(n);
}

/** Plain JSON: drop functions, break cycles, dates as ISO, numbers rounded to 1e-6. */
export function plain(v, seen = new WeakMap(), path = '$') {
  if (v === null || typeof v === 'string' || typeof v === 'boolean') return v;
  if (typeof v === 'number') return Number.isFinite(v) ? Math.round(v * 1e6) / 1e6 : String(v);
  if (typeof v === 'function' || typeof v === 'undefined' || typeof v === 'symbol') return undefined;
  if (v instanceof Date) return isNaN(v) ? null : v.toISOString();
  if (v instanceof Set) return plain([...v], seen, path);
  if (v instanceof Map) return plain(Object.fromEntries(v), seen, path);
  if (seen.has(v)) return { $ref: seen.get(v) };
  seen.set(v, path);
  if (Array.isArray(v)) return v.map((x, i) => plain(x, seen, `${path}[${i}]`) ?? null);
  const o = {};
  for (const k of Object.keys(v).sort()) {
    const x = plain(v[k], seen, `${path}.${k}`);
    if (x !== undefined) o[k] = x;
  }
  return o;
}

/** Write fixtures/golden/<name> (a relative path such as "screens/home.json") as plain JSON. */
export function writeGolden(name, data) {
  const file = join(goldenDir, name);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, JSON.stringify(plain(data), null, 1) + '\n');
  return file;
}
