/**
 * The demo's workflow graph logic, ported to TypeScript for the API mode (docs/backend-steps.md, B15 "For B17"): the
 * canvas checks and test-run simulation run in the browser on the unsaved draft, so they need no engine. Every function
 * is pure; the facade (src/api/workflows.ts) passes the reference lists and sources in `Lookups`.
 * Ported from index.html: wfInfo, wfAnalyze, wfValidate, wfBypass, wfCanLink, wfOrder, wfEval, wfRunTimes, frRunCounts,
 * wfRound, wfPathXY, trigText, ageShort, frAgo, hashId, srcLabel, srcCh, srcOr, wfStat.
 */
import type { BlockSpec, Check, Counts, FieldSpec, Rule, RunState, Source, StepInfo, TestRun, Trigger, WfGraph, WfNode, WfStat, Workflow, Xf } from './workflows';

export interface Fixed { label: string; sub: string; desc: string; canon?: boolean; model?: string; in: boolean; out: boolean; start?: boolean; fields?: string[] }
export interface ActType { id: string; ch: string; label: string; sub: string; desc: string }
export interface ToolRef { id: string; rw: 'read' | 'write'; approval: string; desc: string }
export interface Lookups {
  sources: Source[];
  mappings: Record<string, string[][]>;
  XF: (Xf & { fileIn?: boolean })[];
  FR_XF: Xf[];
  FXD: Record<string, Fixed>;
  ACT_TYPES: ActType[];
  TOOLS: ToolRef[];
  MAP_TARGET: Record<string, string>;
  SH: Record<string, string>;
  DELIVER: Record<string, string[]>;
  CH_ARR: Record<string, string>;
  CH_DEL: Record<string, string>;
  /** The block catalogue (GET /api/screens/workflows/blocks); without it the settings are not checked. */
  blocks?: Record<string, BlockSpec>;
  /** Each connection's resources (the choices of a connector's Resources setting). */
  resources?: Record<string, string[]>;
  /** Each target system's writes (the choices of a write connector's Target operation); a target not listed takes none. */
  operations?: Record<string, string[]>;
}

export const WF_W = 176, WF_H = 62;

// ---------------------------------------------------------------- small helpers
export function hashId(s: string): string {
  let h = 2166136261;
  for (const ch of s) {
    h ^= ch.charCodeAt(0);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(16).toUpperCase().padStart(8, '0');
}

const TRIG_L: Record<string, (t: Trigger) => string> = {
  schedule: (t) => 'Every ' + t.min + ' min', event: () => 'On event', approval: () => 'On approval', manual: () => 'Manual',
  case: () => 'On case request', file: () => 'On file arrival',
};
export const trigText = (t: Trigger): string => (TRIG_L[t.t] ?? TRIG_L.manual)(t);

export function ageShort(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return s < 60 ? s + ' s' : s < 3600 ? Math.floor(s / 60) + ' min ' + (s % 60) + ' s'
    : s < 172800 ? Math.floor(s / 3600) + ' h ' + Math.floor((s % 3600) / 60) + ' min' : Math.floor(s / 86400) + ' days';
}
export function frAgo(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? s + ' sec ago' : s < 3600 ? Math.floor(s / 60) + ' min ago' : s < 172800 ? Math.floor(s / 3600) + ' h ago' : Math.floor(s / 86400) + ' days ago';
}

/** The saved version a published workflow can publish (Publish v{x}): its current version when that is newer than the
 *  one runs use (`pub`, the server's published_ver), else null. A paused or draft workflow has none. */
export const republishVer = (w: Pick<Workflow, 'status' | 'ver'>, pub: string | null): string | null =>
  w.status === 'published' && pub != null && pub !== w.ver ? w.ver : null;
export const wfStat = (w: Workflow): WfStat => (w.status === 'published' && w.last && w.last.state === 'failed' ? 'failing' : w.status);

// ---------------------------------------------------------------- sources
export const srcById = (L: Pick<Lookups, 'sources'>, id: string): Source | undefined => L.sources.find((s) => s.id === id);
export const srcOr = (L: Lookups, id: string): Source =>
  srcById(L, id) ?? {
    id, name: L.SH[id] || 'Deleted source', vendor: 'Deleted', status: 'unavailable', mode: '—', auth: '—', read: [], write: [], cat: 'internal',
    fresh: '—', deleted: true, owner: '', type: '',
  };
/** What the server's checks know about each source now (GET /api/screens/workflows `live`, di/workflow/live.py); for a
 *  source made in the Connection Fabric also the model its mapping feeds (`target`) and how it takes instructions
 *  (`deliver`), which the demo's MAP_TARGET and DELIVER do not know. */
export type LiveState = Record<string, { status: Source['status']; fresh: string; paused?: boolean; target?: string; deliver?: string[] }>;
/** The sources as the checks read them: the integration screen's sources with the status, age and paused flag the
 *  server's checks use (so the canvas and the server agree), without the sources the server no longer has. */
export function liveSources(sources: Source[], live: LiveState | undefined): Source[] {
  if (!live) return sources;
  return sources.filter((s) => live[s.id]).map((s) => {
    const x = live[s.id], o: Source = { ...s, status: x.status, fresh: x.fresh };
    if (x.paused) o.paused = true;
    else delete o.paused;
    if (x.target !== undefined) o.target = x.target;
    if (x.deliver !== undefined) o.deliver = x.deliver;
    return o;
  });
}
/** SH: the demo's short name of a source, or the name of one made in the Connection Fabric (the server's `sh`). */
export const srcShort = (L: Pick<Lookups, 'SH' | 'sources'>, id: string): string => L.SH[id] ?? srcById(L, id)?.name ?? id;
/** MAP_TARGET: the canonical model a source's mapping feeds (one made here: the server's `map_target`, from `live`). */
export const srcTarget = (L: Pick<Lookups, 'MAP_TARGET' | 'sources'>, id: string): string | undefined =>
  L.MAP_TARGET[id] ?? srcById(L, id)?.target;
/** DELIVER: how a source accepts instructions (one made here: the server's `deliver`, from `live`). */
export const srcDeliver = (L: Pick<Lookups, 'DELIVER' | 'sources'>, id: string): string[] => L.DELIVER[id] ?? srcById(L, id)?.deliver ?? [];
export const srcLabel = (L: Lookups, s: Source): string => (L.sources.some((o) => o.id !== s.id && o.name === s.name) ? s.name + ' · ' + s.vendor : s.name);
export function srcCh(x: Source): string[] {
  const m = (x.mode + ' ' + x.auth).toLowerCase(), c: string[] = [];
  if (/api|poll/.test(m)) c.push('api');
  if (/event|webhook/.test(m)) c.push('event');
  if (/csv|sftp/.test(m)) c.push('file');
  return c;
}

// ---------------------------------------------------------------- a step (wfInfo)
export function info(L: Lookups, n: WfNode): StepInfo {
  if (n.k === 'fixed') {
    const f = L.FXD[n.ref];
    return { label: f.label, sub: f.sub, tag: f.canon ? 'Fixed · canonical model' : 'Fixed · platform', in: f.in, out: f.out, desc: f.desc };
  }
  if (n.k === 'conn' || n.k === 'wconn') {
    const s = srcOr(L, n.ref), w = n.k === 'wconn';
    return {
      label: s.deleted ? 'Deleted source' : srcLabel(L, s),
      sub: s.deleted ? 'Reconnect or remove this step' : w ? s.write[0] || 'No write operations' : s.vendor + ' · ' + s.mode,
      tag: w ? 'Connector · write' : 'Connector · read', in: w, out: true,
      desc: w ? 'Sends approved instructions to the system that owns the work, and reports its acknowledgement back.'
        : 'Reads evidence from the system that owns it. The source system keeps owning its transactions.',
    };
  }
  if (n.k === 'act') {
    const a = L.ACT_TYPES.find((t) => t.id === n.ref)!;
    return { label: a.label, sub: a.sub, tag: 'Delivery method', in: true, out: true, desc: a.desc };
  }
  if (n.k === 'xf') {
    const x = L.XF.find((t) => t.id === n.ref)!;
    return { label: x.label, sub: x.sub, tag: x.group === 'ingest' ? 'Integration layer' : x.group === 'file' ? 'File exchange' : 'Transform', in: true, out: true, desc: x.desc };
  }
  if (n.k === 'map') {
    const m = (L.mappings[n.ref] || []).length;
    return {
      label: srcShort(L, n.ref) + ' fields', sub: '→ ' + srcTarget(L, n.ref) + ' · ' + m + ' mapped', tag: 'Field mapping', in: true, out: true,
      desc: 'Maps ' + srcShort(L, n.ref) + ' field names and values into the ' + srcTarget(L, n.ref) + ' canonical model.',
    };
  }
  const t = L.TOOLS.find((x) => x.id === n.ref)!;
  return { label: t.id, sub: t.rw === 'write' ? 'Write · ' + t.approval : 'Read · no approval needed', tag: 'Agent tool', in: true, out: true, desc: t.desc };
}

// ---------------------------------------------------------------- analysis
export interface Analysis {
  by: Record<string, WfNode>; succ: Record<string, string[]>; pred: Record<string, string[]>;
  anc: (id: string) => Set<string>; desc: (id: string) => Set<string>;
}
export function analyze(g: WfGraph): Analysis {
  const by: Record<string, WfNode> = {}, succ: Record<string, string[]> = {}, pred: Record<string, string[]> = {};
  g.nodes.forEach((n) => { by[n.id] = n; succ[n.id] = []; pred[n.id] = []; });
  g.edges.forEach((e) => { if (by[e.a] && by[e.b]) { succ[e.a].push(e.b); pred[e.b].push(e.a); } });
  const reach = (id: string, adj: Record<string, string[]>) => {
    const seen = new Set<string>(), st = [id];
    while (st.length) adj[st.pop()!].forEach((y) => { if (!seen.has(y)) { seen.add(y); st.push(y); } });
    return seen;
  };
  return { by, succ, pred, anc: (id) => reach(id, pred), desc: (id) => reach(id, succ) };
}

export function order(g: WfGraph): string[] {
  const A = analyze(g), deg: Record<string, number> = {}, q: string[] = [], o: string[] = [];
  g.nodes.forEach((n) => { deg[n.id] = A.pred[n.id].length; if (!deg[n.id]) q.push(n.id); });
  while (q.length) {
    const x = q.shift()!;
    o.push(x);
    A.succ[x].forEach((y) => { if (--deg[y] === 0) q.push(y); });
  }
  return o;
}

/** wfBypass: a path upstream of `id` reaches a fixed step without passing a step that `stop` accepts. */
function bypass(A: Analysis, id: string, stop: (m: WfNode) => boolean): boolean {
  const seen = new Set<string>(), st = [id];
  while (st.length) {
    for (const y of A.pred[st.pop()!]) {
      if (seen.has(y)) continue;
      seen.add(y);
      const m = A.by[y];
      if (stop(m)) continue;
      if (m.k === 'fixed') return true;
      st.push(y);
    }
  }
  return false;
}

// the demo's ordering rules for agent tools on a decision canvas, and the names of the steps they cite
const WF_TR: Record<string, { after?: string[]; before?: string[]; why: string }> = {
  get_case_evidence: { after: ['evid'], why: 'It reads the case evidence bundle, so it follows Case evidence.' },
  find_demand: { after: ['evid'], before: ['gates'], why: 'Demand fit is gate 4, so demand has to be found before the gates run.' },
  request_missing_evidence: { after: ['evid'], before: ['gates'], why: 'Missing evidence has to be requested before the gates, or the route is withheld.' },
  list_eligible_routes: { after: ['gates'], why: 'Only the gates decide which routes are eligible.' },
  predict_outcomes: { after: ['gates'], why: 'Predictions run only on routes that passed all six gates.' },
  optimize_pool: { after: ['gates'], before: ['appr'], why: 'Allocation works on eligible routes, and nothing is committed until a person approves.' },
  get_model_validation: { after: ['gates'], why: 'Model validation is read alongside predictions, after the gates.' },
  request_approval: { after: ['gates'], before: ['appr'], why: 'Recommendations go to a person, so this tool has to feed Human approval.' },
  send_instruction: { after: ['appr', 'c_dec'], why: 'Instructions go out only after a person approves and the Decision record carries the approval reference.' },
  reconcile_outcome: { after: ['c_out'], why: 'Reconciliation links actuals to the decision, so it follows returned outcomes.' },
};
const WF_NM: Record<string, string> = { evid: 'Case evidence', gates: 'Six eligibility gates', appr: 'Human approval', c_dec: 'Decision', c_out: 'Outcome' };

/** wfValidate as the demo runs it (with the Connection Fabric's override): starts need no input, branches need no
 *  output, and each branch follows the step it belongs to. Errors, warnings and notes, each with its step, errors first. */
export function validate(L: Lookups, g: WfGraph, kind: 'pipe' | 'dec'): Check[] {
  const A = analyze(g), X = (id: string) => L.FR_XF.find((x) => x.id === id);
  const out = validateBase(L, g, kind).filter((o) => {
    const n = g.nodes.find((x) => x.id === o.id), x = n && n.k === 'xf' && X(n.ref);
    if (!n || !x || !/not wired between/.test(o.msg)) return true;
    return !((x.start && A.succ[n.id].length) || (x.sink && A.pred[n.id].length));
  });
  g.nodes.forEach((n) => {
    if (n.k !== 'xf') return;
    const anc = [...A.anc(n.id)].map((i) => A.by[i]), fed = A.pred[n.id].length > 0, x = X(n.ref);
    if (n.ref === 'x_err' && fed && !anc.some((m) => m.k === 'xf' && m.ref === 'x_val'))
      out.push({ sev: 'error', id: n.id, msg: 'Error handler receives the records that fail validation, so it follows Validation & enrichment.' });
    if (n.ref === 'x_pub' && fed && !anc.some((m) => m.k === 'fixed' && L.FXD[m.ref].canon))
      out.push({ sev: 'error', id: n.id, msg: 'Publish to event stream announces a model update, so it follows a canonical model.' });
    if (x?.start && fed) out.push({ sev: 'warn', id: n.id, msg: x.label + ' starts a workflow, so nothing should feed it.' });
  });
  out.push(...cfgChecks(L, g));
  const rk = { error: 0, warn: 1, info: 2 };
  return out.sort((a, b) => rk[a.sev] - rk[b.sev]);
}

/** The canvas' checks merged with the server's for the draft (workflow.validate with the graph: live sources and the
 *  fields records really carry, which the browser cannot check). Each check once, keyed by step and text; on a
 *  duplicate the server's wins. A server check for a step or link no longer in the graph is dropped (the answer was for
 *  an earlier edit). Errors first, then warnings, then notes; the browser's order within each. */
export function mergeChecks(browser: Check[], server: Check[] | null | undefined, g: WfGraph): Check[] {
  if (!server?.length) return browser;
  const ids = new Set<string>([...g.nodes.map((n) => n.id), ...g.edges.map((e) => e.id)]);
  const key = (c: Check) => c.id + '\u0000' + c.msg;
  const srv = new Map(server.filter((c) => ids.has(c.id)).map((c) => [key(c), c] as const));
  const out = browser.map((c) => srv.get(key(c)) ?? c);
  const seen = new Set(out.map(key));
  srv.forEach((c, k) => { if (!seen.has(k)) { seen.add(k); out.push(c); } });
  const rk = { error: 0, warn: 1, info: 2 };
  return out.sort((a, b) => rk[a.sev] - rk[b.sev]);
}

/** The demo's original wfValidate (before the override above). */
function validateBase(L: Lookups, g: WfGraph, kind: 'pipe' | 'dec'): Check[] {
  const A = analyze(g), out: Check[] = [], add = (sev: Check['sev'], id: string, msg: string) => out.push({ sev, id, msg });
  const xfOf = (ref: string) => L.XF.find((t) => t.id === ref);
  g.nodes.forEach((n) => {
    const lb = info(L, n).label, np = A.pred[n.id].length, ns = A.succ[n.id].length;
    if ((n.k === 'conn' || n.k === 'wconn' || n.k === 'map') && !srcById(L, n.ref)) {
      add('error', n.id, (L.SH[n.ref] || 'This source') + ' was deleted from the Source map. Reconnect it or remove this step.');
      return;
    }
    if (n.k === 'conn') {
      const s = srcOr(L, n.ref);
      if (s.status === 'unavailable') add('error', n.id, `${s.name} has no connected feed. Circularity will not infer data, so this evidence would be missing.`);
      else if (s.status === 'stale') add('warn', n.id, `${s.name} is ${s.fresh} old. Predictions fall back to the last fresh data and say so.`);
      else if (s.status === 'manual') add('info', n.id, `${s.name} is a manual import. It supports evaluation, not live automation.`);
      if (s.paused) add('warn', n.id, `${s.name} is paused. Runs read nothing from it until it is resumed.`);
      const st: [string, boolean, boolean, boolean][] = [[n.id, false, false, false]], vis = new Set<string>(), bad = new Set<string>();
      let hit = false, noIng = false, noVal = false;
      while (st.length) {
        const [x, vm, vi, vv] = st.pop()!, key = x + '|' + vm + vi + vv;
        if (vis.has(key)) continue;
        vis.add(key);
        A.succ[x].forEach((y) => {
          const m = A.by[y], v2 = vm || m.k === 'map', i2 = vi || !!(m.k === 'xf' && xfOf(m.ref)?.ingest), w2 = vv || (m.k === 'xf' && m.ref === 'x_val');
          if (m.k === 'fixed') {
            hit = true;
            if (!v2 && L.FXD[m.ref].canon) bad.add(info(L, m).label);
            if (v2) { if (!i2) noIng = true; if (!w2) noVal = true; }
          } else st.push([y, v2, i2, w2]);
        });
      }
      if (bad.size) add('error', n.id, `${s.name} reaches ${[...bad].join(', ')} without a field mapping. Raw vendor values would enter the canonical model.`);
      else if (!hit) add('warn', n.id, ns ? `${s.name} does not reach a canonical model.` : `${s.name} is not wired into the workflow.`);
      else if (noIng || noVal)
        add('warn', n.id, `${s.name} reaches the models without ${[noIng ? 'an ingestion channel' : '', noVal ? 'validation and enrichment' : ''].filter(Boolean).join(' or ')}. Access, ordering and bad rows are then not handled in one place.`);
    }
    if (n.k === 'map') {
      const anc = [...A.anc(n.id)].map((i) => A.by[i]).filter((m) => m.k === 'conn');
      const canon = [...A.desc(n.id)].map((i) => A.by[i]).filter((m) => m.k === 'fixed' && L.FXD[m.ref].canon).map((m) => L.FXD[m.ref].model!);
      if (!np) add('warn', n.id, `${lb} is not fed by a connector.`);
      else if (!anc.length) add('error', n.id, `${lb} has no connector upstream, so there is nothing to map.`);
      else if (!anc.some((c) => c.ref === n.ref)) add('error', n.id, `${lb} is fed by ${anc.map((c) => srcShort(L, c.ref)).join(', ')}. Field names would not line up.`);
      if (!(L.mappings[n.ref] || []).length) add('error', n.id, `No field mapping is defined for ${srcShort(L, n.ref)} yet.`);
      if (!ns) add('warn', n.id, `${lb} does not lead to a canonical model.`);
      else if (canon.length && !canon.includes(srcTarget(L, n.ref) ?? '')) add('error', n.id, `${lb} maps to ${srcTarget(L, n.ref)}, but it is wired to ${canon.join(', ')}.`);
    }
    if (n.k === 'xf') {
      const x = xfOf(n.ref)!, anc = A.anc(n.id), conns = [...anc].map((i) => A.by[i]).filter((m) => m.k === 'conn');
      const names = (l: WfNode[]) => [...new Set(l.map((c) => srcShort(L, c.ref)))].join(', ');
      if (!np || (!ns && n.ref !== 'x_notify')) add('warn', n.id, `${lb} is not wired between a source and a target.`);
      else {
        if (x.ingest) {
          const bad = conns.filter((c) => { const q = srcOr(L, c.ref); return q.status !== 'unavailable' && !srcCh(q).includes(x.ingest!); });
          if (bad.length) add('error', n.id, `${lb} receives ${names(bad)}, which does not arrive as ${L.CH_ARR[x.ingest]}.`);
        }
        if (x.fileIn && conns.length && !conns.some((c) => srcCh(srcOr(L, c.ref)).includes('file'))) add('error', n.id, `${lb} needs a file to work on, but ${names(conns)} does not deliver files.`);
        if (n.ref === 'x_man' && ![...anc].some((i) => A.by[i].k === 'act' && A.by[i].ref === 'a_file')) add('error', n.id, 'Create manifest follows File generation. The manifest lists the files the target will import.');
        if (n.ref === 'x_cb' && ![...anc].some((i) => A.by[i].k === 'wconn')) add('error', n.id, 'Fetch import log runs after a target system has imported, so it follows a write connector.');
        if (n.ref === 'x_notify' && ![...anc].some((i) => A.by[i].k === 'xf' && A.by[i].ref === 'x_cb')) add('error', n.id, 'The notification carries log links, so it follows Fetch import log.');
      }
    }
    const env = (m: WfNode) => m.k === 'xf' && m.ref === 'x_env', appr = (m: WfNode) => m.id === 'appr';
    if (n.k === 'act') {
      const a = L.ACT_TYPES.find((t) => t.id === n.ref)!, anc = A.anc(n.id), dsc = [...A.desc(n.id)].map((i) => A.by[i]).filter((m) => m.k === 'wconn');
      if (!np) add('warn', n.id, `${lb} is not wired to receive an instruction.`);
      else if (!anc.has('appr') || bypass(A, n.id, appr)) add('error', n.id, `${lb} bypasses Human approval. Anything that commits stock, spend or price always stops at a person.`);
      else if (![...anc].some((i) => env(A.by[i])) || bypass(A, n.id, env)) add('error', n.id, `${lb} needs an Instruction envelope upstream, so the receiving system can trace and de-duplicate it.`);
      if (np) {
        if (!dsc.length) add('warn', n.id, `${lb} does not lead to a system that receives it.`);
        dsc.forEach((w) => {
          const dl = srcDeliver(L, w.ref);
          if (!dl.includes(a.ch)) add('error', n.id, `${srcShort(L, w.ref)} does not accept ${L.CH_DEL[a.ch]}. It accepts ${dl.map((c) => L.CH_DEL[c]).join(', ')}.`);
        });
      }
    }
    if (n.k === 'wconn') {
      const s = srcOr(L, n.ref), anc = A.anc(n.id);
      if (s.status === 'unavailable') add('error', n.id, `${s.name} has no connected system to write to.`);
      else if (s.status === 'stale') add('warn', n.id, `${s.name} has an expired token. Instructions would queue until it is refreshed.`);
      if (!np) add('warn', n.id, `${s.name} is not wired to receive an instruction.`);
      else if (!anc.has('appr') || bypass(A, n.id, appr)) add('error', n.id, `Writes to ${s.name} bypass Human approval. Anything that commits stock, spend or price always stops at a person.`);
      else if (![...anc].some((i) => env(A.by[i])) || bypass(A, n.id, env))
        add('error', n.id, `Writes to ${s.name} need an Instruction envelope. Without the decision ID and approval reference, the receiving system cannot trace or de-duplicate it.`);
    }
    if (n.k === 'tool') {
      const r = WF_TR[n.ref];
      if (!np && !ns) add('warn', n.id, `${n.ref} is not wired in.`);
      else if (r) {
        const anc = A.anc(n.id), dsc = A.desc(n.id), miss = (r.after || []).filter((i) => !anc.has(i)), late = (r.before || []).filter((i) => !dsc.has(i));
        if (miss.length) add('error', n.id, `${n.ref} has to come after ${miss.map((i) => WF_NM[i]).join(' and ')}. ${r.why}`);
        if (late.length) add('error', n.id, `${n.ref} has to come before ${late.map((i) => WF_NM[i]).join(' and ')}. ${r.why}`);
      }
    }
    if (n.k === 'fixed' && kind === 'pipe' && L.FXD[n.ref].canon && !['c_dec', 'c_out'].includes(n.ref) && !np) add('warn', n.id, `Nothing feeds ${lb}. AI services will report an evidence gap.`);
  });
  if (kind === 'dec') {
    const dec = g.nodes.find((n) => n.id === 'c_dec');
    if (dec && ![...A.desc('c_dec')].some((i) => A.by[i].k === 'tool' && A.by[i].ref === 'send_instruction'))
      add('warn', 'c_dec', 'The approved decision is not carried out. Add send_instruction after the Decision record.');
  }
  const rk = { error: 0, warn: 1, info: 2 };
  return out.sort((a, b) => rk[a.sev] - rk[b.sev]);
}

/** wfCanLink: null when a → b may be connected, otherwise why not. */
export function canLink(L: Lookups, g: WfGraph, a: string, b: string): string | null {
  const na = g.nodes.find((n) => n.id === a), nb = g.nodes.find((n) => n.id === b);
  if (!na || !nb) return 'That step no longer exists.';
  const ia = info(L, na), ib = info(L, nb);
  if (a === b) return 'A step cannot connect to itself.';
  if (!ia.out) return `${ia.label} has no output.`;
  if (!ib.in) return `${ib.label} takes no input. Read connectors are where data starts.`;
  if (na.k === 'fixed' && nb.k === 'fixed') return 'Fixed steps are wired by Circularity and cannot be re-wired.';
  if (g.edges.some((e) => e.a === a && e.b === b)) return 'Those two steps are already connected.';
  if (analyze(g).desc(b).has(a)) return 'That would create a loop.';
  return null;
}

// ---------------------------------------------------------------- the test run
/** wfEval: the state a step reaches, given the states of the steps before it. */
export function evalStep(L: Lookups, run: TestRun, A: Analysis, n: WfNode): RunState {
  const ps = A.pred[n.id].map((p) => run.states[p]);
  if (ps.some((s) => s === 'failed' || s === 'upstream_failed')) return 'upstream_failed';
  if (ps.some((s) => s === 'held' || s === 'waiting')) return 'waiting';
  const f = n.k === 'fixed' ? L.FXD[n.ref] : null, needs = f ? f.in && !f.start : n.k !== 'conn';
  if (needs && (!ps.length || ps.every((s) => s === 'skipped'))) return 'skipped';
  if (n.fail) return 'failed';
  if (n.k === 'conn' || n.k === 'wconn') {
    const s = srcOr(L, n.ref);
    if (s.status === 'unavailable') return 'failed';
    if (s.status === 'stale') return 'warning';
  }
  if (n.k === 'fixed' && n.ref === 'appr' && !run.approved) return 'held';
  return 'success';
}

/** wfRunTimes: start, end and duration of each step that ran. */
export function runTimes(r: TestRun, now: number): Record<string, { s: number; e: number; d: number; ex: boolean }> {
  let t = r.t0 || now;
  const o: Record<string, { s: number; e: number; d: number; ex: boolean }> = {};
  r.order.forEach((id) => {
    const st = r.states[id], ex = ['success', 'warning', 'failed', 'running'].includes(st), d = ex ? +r.dur[id] : 0;
    o[id] = { s: t, e: t + d * 1000, d, ex };
    t += d * 1000 + (ex ? 120 : 0);
  });
  return o;
}

/** frRunCounts: records in and out of each step, for the given step states (validation rejects a fixed share). */
export function runCounts(w: Workflow, g: WfGraph, states: Record<string, RunState>): Record<string, Counts> {
  const A = analyze(g), R = w.last ? w.last.rows : 0, o: Record<string, Counts> = {};
  const rej = Math.max(1, Math.round(R * (0.004 + (parseInt(hashId(w.id + 'rej'), 16) % 9) / 1000)));
  order(g).forEach((id) => {
    const n = A.by[id], ps = A.pred[id].map((p) => (o[p] && o[p].out) || 0);
    const inn = n.k === 'conn' ? R : n.ref === 'x_err' ? (o[A.pred[id][0]] && o[A.pred[id][0]].rej) || 0 : Math.max(0, ...ps, 0), s = states[id];
    let out = s === 'failed' || s === 'upstream_failed' || s === 'skipped' ? 0 : inn, r = 0;
    if (n.k === 'xf' && n.ref === 'x_val' && s !== 'failed') { r = Math.min(rej, inn); out = inn - r; }
    o[id] = { in: inn, out, rej: r };
  });
  return o;
}

// ---------------------------------------------------------------- geometry
function round(p: number[][], r: number): string {
  let d = `M${p[0][0]} ${p[0][1]}`;
  for (let i = 1; i < p.length - 1; i++) {
    const a = p[i - 1], b = p[i], c = p[i + 1], l1 = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, l2 = Math.hypot(c[0] - b[0], c[1] - b[1]) || 1, rr = Math.min(r, l1 / 2, l2 / 2);
    d += `L${b[0] - ((b[0] - a[0]) / l1) * rr} ${b[1] - ((b[1] - a[1]) / l1) * rr}Q${b[0]} ${b[1]} ${b[0] + ((c[0] - b[0]) / l2) * rr} ${b[1] + ((c[1] - b[1]) / l2) * rr}`;
  }
  const z = p[p.length - 1];
  return d + `L${z[0]} ${z[1]}`;
}
/** wfPathXY: a curve forward, a rounded detour backward. */
export function pathXY(sx: number, sy: number, tx: number, ty: number): string {
  if (tx >= sx + 12) {
    const d = Math.max(18, Math.min(90, (tx - sx) / 2));
    return `M${sx} ${sy}C${sx + d} ${sy} ${tx - d} ${ty} ${tx} ${ty}`;
  }
  const mid = Math.abs(sy - ty) < WF_H + 10 ? Math.max(sy, ty) + WF_H / 2 + 24 : (sy + ty) / 2, lx = Math.max(8, tx - 22);
  return round([[sx, sy], [sx + 22, sy], [sx + 22, mid], [lx, mid], [lx, ty], [tx, ty]], 10);
}

// ---------------------------------------------------------------- block settings (di/workflow/blocks.py, plan 6 C2)
// A node's `cfg` holds only the settings that differ from its block's defaults; these port the server's rules exactly,
// so the canvas shows the same settings errors the server's checks report (and Publish refuses).
const CHECKS = ['present', 'type', 'regex', 'range', 'in'];
const TYPES = ['string', 'number', 'integer', 'bool', 'date'];
const RANGE = /^\s*(?:(-?\d+(?:\.\d+)?)?\s*\.\.\s*(-?\d+(?:\.\d+)?)?|(>=|<=|!=|>|<|=)\s*(-?\d+(?:\.\d+)?))\s*$/;
const PAIRS: [string, string, string][] = [['x_expr', 'target', 'expression'], ['x_expr', 'expression', 'target'], ['x_join', 'input', 'key']];
/** What the checks may know about the source: its records' field names and its connection's resources. */
export interface CfgCtx { label?: string; fields?: string[] | null; resources?: string[] | null; operations?: string[] | null }

const copyV = (v: unknown): unknown => (Array.isArray(v) ? [...v] : v && typeof v === 'object' ? { ...(v as object) } : v);
const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const strs = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === 'string');
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** The catalogue key of a node: its transform id for an xf node, else its kind. */
export const specKey = (n: Pick<WfNode, 'k' | 'ref'>): string => (n.k === 'xf' ? n.ref : n.k);
export function defaultCfg(B: Record<string, BlockSpec>, key: string): Record<string, unknown> {
  return Object.fromEntries((B[key]?.fields ?? []).map((f) => [f.key, copyV(f.default)]));
}
/** A node's settings with the defaults filled in. */
export const nodeCfg = (B: Record<string, BlockSpec>, n: WfNode): Record<string, unknown> => ({ ...defaultCfg(B, specKey(n)), ...(n.cfg ?? {}) });
/** The node as stored: `cfg` keeps only what differs from the defaults, and goes when nothing does. */
export function compactCfg(B: Record<string, BlockSpec>, n: WfNode): WfNode {
  const { cfg, ...rest } = n;
  if (!isObj(cfg)) return cfg == null ? rest : n;
  const d = defaultCfg(B, specKey(n));
  const keep = Object.fromEntries(Object.entries(cfg).filter(([k, v]) => !(k in d) || !same(d[k], v)));
  return Object.keys(keep).length ? { ...rest, cfg: keep } : rest;
}

function ruleErrors(f: FieldSpec, rules: unknown): string[] {
  if (!Array.isArray(rules) || !rules.every(isObj)) return [`${f.label} must be a list of rules.`];
  const out: string[] = [];
  rules.forEach((r, i) => {
    const at = `${f.label} rule ${i + 1}`, fld = r.field, check = r.check, arg = r.arg == null ? '' : String(r.arg);
    if (typeof fld !== 'string' || !fld.trim()) { out.push(`${at} has no field.`); return; }
    if (!CHECKS.includes(check as string)) out.push(`${at} has an unknown check ${String(check)} (present, type, regex, range or in).`);
    else if (check === 'type' && !TYPES.includes(arg)) out.push(`${at} needs a type: ${TYPES.join(', ')}.`);
    else if (check === 'regex') {
      let ok = true;
      try { new RegExp(arg); } catch { ok = false; }
      if (!ok) out.push(`${at} has a pattern that does not compile.`);
      else if (!arg) out.push(`${at} needs a pattern.`);
    } else if (check === 'range') {
      const m = RANGE.exec(arg);
      if (!(m && (m[1] || m[2] || m[4]))) out.push(`${at} needs a range such as 0..100, >0 or <=5.`);
    } else if (check === 'in' && !arg.split(',').some((x) => x.trim())) out.push(`${at} needs the values it accepts, separated by commas.`);
  });
  return out;
}

/** One setting's problems (without the block's name). */
export function fieldErrors(f: FieldSpec, v: unknown, ctx: CfgCtx = {}): string[] {
  const lb = f.label, choices = f.choices;
  switch (f.type) {
    case 'text':
      if (typeof v !== 'string') return [`${lb} must be text.`];
      if (f.source === 'operations' && ctx.operations && v.trim() && !ctx.operations.includes(v.trim())) // a write connector's Target operation
        return [`${lb} ${v.trim()} is not a write of this system (${ctx.operations.join(', ') || 'it takes none'}).`];
      return f.required && !v.trim() ? [`${lb} is needed.`] : [];
    case 'number':
      if (!isNum(v)) return [`${lb} must be a number.`];
      if (f.min != null && v < f.min) return [`${lb} must be at least ${f.min}.`];
      if (f.max != null && v > f.max) return [`${lb} must be at most ${f.max}.`];
      return [];
    case 'bool':
      return typeof v === 'boolean' ? [] : [`${lb} must be yes or no.`];
    case 'select':
      if (f.key === 'version') return v === 'latest' || (isNum(v) && Number.isInteger(v) && v >= 1) ? [] : [`${lb} must be latest or a version number.`];
      if (v === '' && !f.required) return [];
      if (v === '' || v == null) return [`${lb} is needed.`];
      return (choices ?? []).includes(v as string) ? [] : [`${lb} ${String(v)} is not one of ${(choices ?? []).join(', ')}.`];
    case 'multi':
    case 'fields': {
      if (!strs(v)) return [`${lb} must be a list of ${f.type === 'fields' ? 'field names' : 'values'}.`];
      if (f.required && !v.length) return [`${lb} needs at least one.`];
      const out: string[] = [];
      if (choices) v.filter((x) => !choices.includes(x)).forEach((x) => out.push(`${lb} ${x} is not one of ${choices.join(', ')}.`));
      if (f.source === 'resources' && ctx.resources) v.filter((x) => !ctx.resources!.includes(x)).forEach((x) => out.push(`${lb} ${x} is not a resource of this connection.`));
      if (f.type === 'fields' && ctx.fields) v.filter((x) => !ctx.fields!.includes(x)).forEach((x) => out.push(`${lb} ${x} is not a field the records carry.`));
      return out;
    }
    case 'rules': {
      let errs = ruleErrors(f, v);
      const rs = v as Rule[];
      if (!errs.length && f.required && !rs.length) errs = [`${lb} needs at least one rule.`];
      if (!errs.length && ctx.fields)
        errs = rs.flatMap((r, i) => (ctx.fields!.includes(r.field) ? [] : [`${lb} rule ${i + 1}: ${r.field} is not a field the records carry.`]));
      return errs;
    }
    case 'mapping': {
      if (!isObj(v) || !Object.values(v).every((x) => typeof x === 'string')) return [`${lb} must pair each field with a value.`];
      const out: string[] = Object.keys(v).some((k) => !k.trim()) ? [`${lb}: a field name is empty.`] : [];
      if (choices) Object.values(v).filter((x) => !choices.includes(x as string)).forEach((x) => out.push(`${lb}: ${String(x)} is not one of ${choices.join(', ')}.`));
      if (ctx.fields) Object.keys(v).filter((k) => k.trim() && !ctx.fields!.includes(k)).forEach((k) => out.push(`${lb}: ${k} is not a field the records carry.`));
      return out;
    }
  }
  return [];
}

/** The problems with a node's settings, each "<block>: <field> <problem>" ([] for the defaults). */
export function cfgErrors(B: Record<string, BlockSpec>, n: WfNode, ctx: CfgCtx = {}): string[] {
  const s = B[specKey(n)], label = ctx.label || n.ref || 'This step', raw = n.cfg as unknown;
  if (raw == null || !s) return [];
  if (!isObj(raw)) return [`${label}: the settings must be an object.`];
  if (s.readonly && Object.keys(raw).length) return [`${label}: this step has no settings to change.`];
  const keys = new Set(s.fields.map((f) => f.key));
  const out = Object.keys(raw).filter((k) => !keys.has(k)).map((k) => `${k} is not a setting of this block.`);
  const cfg = { ...defaultCfg(B, s.ref), ...raw };
  s.fields.forEach((f) => out.push(...fieldErrors(f, cfg[f.key], ctx)));
  PAIRS.forEach(([ref, a, b]) => {
    const fa = s.fields.find((f) => f.key === a), fb = s.fields.find((f) => f.key === b), va = cfg[a], vb = cfg[b];
    if (s.ref === ref && fa && fb && typeof va === 'string' && typeof vb === 'string' && va.trim() && !vb.trim()) out.push(`${fb.label} is needed with ${fa.label}.`);
  });
  return out.map((m) => `${label}: ${m}`);
}

/** The settings errors of every node in a graph, as checks (the server's cfg_checks). */
export function cfgChecks(L: Lookups, g: WfGraph): Check[] {
  const B = L.blocks;
  if (!B) return [];
  return g.nodes.flatMap((n) => {
    if (n.cfg == null) return [];
    const ctx: CfgCtx = {
      label: info(L, n).label, resources: n.k === 'conn' ? L.resources?.[n.ref] ?? null : null,
      operations: n.k === 'wconn' && L.operations ? L.operations[n.ref] ?? [] : null,
    };
    return cfgErrors(B, n, ctx).map((msg) => ({ sev: 'error' as const, id: n.id, msg }));
  });
}
