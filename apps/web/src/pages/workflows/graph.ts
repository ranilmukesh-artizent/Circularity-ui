/**
 * The demo's workflow graph logic, ported to TypeScript for the API mode (docs/BACKEND_STEPS.md, B15 "For B17"): the
 * canvas checks and test-run simulation run in the browser on the unsaved draft, so they need no engine. Every function
 * is pure; the facade (src/api/workflows.ts) passes the reference lists and sources in `Lookups`.
 * Ported from index.html: wfInfo, wfAnalyze, wfValidate, wfBypass, wfCanLink, wfOrder, wfEval, wfRunTimes, frRunCounts,
 * wfRound, wfPathXY, trigText, ageShort, frAgo, hashId, srcLabel, srcCh, srcOr, wfStat.
 */
import type { Check, Counts, RunState, Source, StepInfo, TestRun, Trigger, WfGraph, WfNode, WfStat, Workflow, Xf } from '../../api/workflows';

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

export const wfStat = (w: Workflow): WfStat => (w.status === 'published' && w.last && w.last.state === 'failed' ? 'failing' : w.status);

// ---------------------------------------------------------------- sources
export const srcById = (L: Lookups, id: string): Source | undefined => L.sources.find((s) => s.id === id);
export const srcOr = (L: Lookups, id: string): Source =>
  srcById(L, id) ?? {
    id, name: L.SH[id] || 'Deleted source', vendor: 'Deleted', status: 'unavailable', mode: '—', auth: '—', read: [], write: [], cat: 'internal',
    fresh: '—', deleted: true, owner: '', type: '',
  };
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
      label: L.SH[n.ref] + ' fields', sub: '→ ' + L.MAP_TARGET[n.ref] + ' · ' + m + ' mapped', tag: 'Field mapping', in: true, out: true,
      desc: 'Maps ' + L.SH[n.ref] + ' field names and values into the ' + L.MAP_TARGET[n.ref] + ' canonical model.',
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
      else if (!anc.some((c) => c.ref === n.ref)) add('error', n.id, `${lb} is fed by ${anc.map((c) => L.SH[c.ref]).join(', ')}. Field names would not line up.`);
      if (!(L.mappings[n.ref] || []).length) add('error', n.id, `No field mapping is defined for ${L.SH[n.ref]} yet.`);
      if (!ns) add('warn', n.id, `${lb} does not lead to a canonical model.`);
      else if (canon.length && !canon.includes(L.MAP_TARGET[n.ref])) add('error', n.id, `${lb} maps to ${L.MAP_TARGET[n.ref]}, but it is wired to ${canon.join(', ')}.`);
    }
    if (n.k === 'xf') {
      const x = xfOf(n.ref)!, anc = A.anc(n.id), conns = [...anc].map((i) => A.by[i]).filter((m) => m.k === 'conn');
      const names = (l: WfNode[]) => [...new Set(l.map((c) => L.SH[c.ref]))].join(', ');
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
          const dl = L.DELIVER[w.ref] || [];
          if (!dl.includes(a.ch)) add('error', n.id, `${L.SH[w.ref]} does not accept ${L.CH_DEL[a.ch]}. It accepts ${dl.map((c) => L.CH_DEL[c]).join(', ')}.`);
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
