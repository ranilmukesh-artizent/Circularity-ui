// The live check of the assistant (ai-tasks §8.1): real HTTP calls to the running api, real models, no mocks.
//
//   node scripts/dev/ai-live-check.mjs [api url] [--each-model] [--keep] [--only <case id>]
//   bash scripts/dev/ai-live-check.sh  [same arguments]
//
// It signs in over POST /api/auth/login (the token is never printed), asks each case over POST /api/ask (the SSE stream),
// and prints one line per call: forced model | page | question | answered by | model | fallback reason | ms | tools |
// created | PASS/FAIL. A case fails when the rules answered (unless it is the fallback case), the text is empty, a refusal
// phrase or an echo is in it, no tool was called where data was asked, or a build request left no draft (read back over
// workflow.get / flow.get). The drafts it made are removed with the person's own actions unless --keep.
// --each-model also runs the cases with each enabled model first in the chain (llm.setModel as admin; the priorities are
// put back). Exit 1 on any failure of the default chain. Needs Node 20+ (fetch); nothing else.

const args = process.argv.slice(2);
const flag = (f) => args.includes(f);
const opt = (f) => (args.includes(f) ? args[args.indexOf(f) + 1] : null);
const API = args.find((a) => /^https?:/.test(a)) ?? `http://localhost:${process.env.API_PORT || 8000}`;
const ONLY = opt('--only');

const REFUSALS = [
  /i can.?t see any record/i, /i don.?t have (any )?(record|information|data)/i, /not sure which workflow/i,
  /please provide the workflow id/i, /which workflow (are you|do you)/i, /i can.?t do that yet/i,
];

async function login(username) {
  const r = await fetch(API + '/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password: 'demo' }),
  });
  if (!r.ok) throw new Error(`login ${username}: ${r.status}`);
  return (await r.json()).access_token;
}

async function act(token, id, input) {
  const r = await fetch(`${API}/api/actions/${id}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token }, body: JSON.stringify(input), // the body is the action's input itself (di.routes.actions)
  });
  try {
    return await r.json();
  } catch {
    return { ok: false, error: { code: String(r.status), message: r.statusText } };
  }
}

async function ask(token, question, context, conversation_id) {
  const t0 = Date.now();
  const r = await fetch(API + '/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', Authorization: 'Bearer ' + token },
    body: JSON.stringify({ question, context, conversation_id }),
  });
  if (!r.ok) return { http: r.status, ms: Date.now() - t0, events: [], final: null };
  const events = [];
  for (const block of (await r.text()).split('\n\n')) {
    const data = block.split('\n').filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trimStart()).join('\n');
    if (data) try { events.push(JSON.parse(data)); } catch { /* a malformed event */ }
  }
  return { http: 200, ms: Date.now() - t0, events, final: events.find((e) => e.type === 'final') ?? null };
}

// expect: tools (at least one of these was called and ok), anyTool, made (kind of draft), text (regexes that must match),
// rulesOk (the rules may answer), noTool
const CASES = [
  { id: 'home-today', as: 'planner.a', ctx: { page: 'home' }, q: 'What needs me today?', expect: { anyTool: true } },
  { id: 'wf-this', as: 'admin', ctx: { page: 'integration', section: 'studio', object: { kind: 'workflow', id: 'WF-103' } },
    q: 'in this workflow what it does?', expect: { tools: ['get_workflow'], text: [/WF-103|SAP|ingest/i] } },
  { id: 'wf-stuck', as: 'admin', ctx: { page: 'integration', section: 'studio', object: { kind: 'workflow', id: 'WF-103' } },
    q: 'What is stuck in the last sync?', expect: { tools: ['list_workflows', 'get_workflow', 'get_workflow_run'] } },
  { id: 'flow-guardrails', as: 'admin', ctx: { page: 'modeler', section: 'industrial', org: 'workspace', object: { kind: 'flow', id: '$FLOW' } },
    q: 'Which guardrails does this flow keep?', expect: { tools: ['get_decision_flow'], text: [/GR-/] } },
  { id: 'greeting', as: 'planner.a', ctx: { page: 'home' }, q: 'hii', expect: { noEcho: true } },
  { id: 'build-workflow', as: 'admin', ctx: { page: 'home' },
    q: 'Create a workflow that pulls returns from SAP S/4HANA every 5 minutes and drops records without a serial',
    expect: { tools: ['create_workflow'], made: 'workflow' } },
  { id: 'flow-change', as: 'admin', ctx: { page: 'modeler', section: 'industrial', org: 'workspace', object: { kind: 'flow', id: '$FLOW' } },
    q: "Never send Customer C's motors to resale", expect: { tools: ['change_decision_flow'], made: 'flow' } },
  { id: 'publish-refused', as: 'admin', ctx: { page: 'integration', section: 'studio', object: { kind: 'workflow', id: 'WF-103' } },
    q: 'Publish this workflow now.', expect: { nothingMade: true, text: [/publish/i], safety: true } },
];

function judge(c, res, forced) {
  const f = res.final;
  if (res.http !== 200) return [`HTTP ${res.http}`];
  if (!f) return ['no final event'];
  const bad = [];
  const text = (f.text || '').trim();
  const tools = (f.tools || []).filter((t) => t.ok).map((t) => t.name);
  const e = c.expect;
  if (!f.by_model && !e.rulesOk) bad.push(`rules answered (${f.fallback_reason})`);
  if (!text) bad.push('empty text');
  for (const rx of REFUSALS) if (rx.test(text)) bad.push(`refusal phrase ${rx}`);
  if (e.noEcho && text.toLowerCase().includes(c.q.toLowerCase())) bad.push('echo');
  if (e.anyTool && !tools.length) bad.push('no tool call');
  if (e.tools && !e.tools.some((t) => tools.includes(t))) bad.push(`none of ${e.tools.join('/')} called (called: ${tools.join(',') || 'none'})`);
  for (const rx of e.text || []) if (!rx.test(text)) bad.push(`text lacks ${rx}`);
  const made = f.created || [];
  // a draft, or the same write held for a person when the specialist agent's autonomy is "propose" (the proposal is read back)
  if (e.made && !made.some((m) => m.kind === e.made || m.kind === 'proposal')) bad.push(`no ${e.made} draft or held proposal in created`);
  if (e.nothingMade && made.length) bad.push('made something');
  if (forced && f.by_model && f.model !== forced) bad.push(`answered by ${f.model}, not the forced ${forced}`);
  return bad;
}

async function verifyAndClean(admin, res, c, keep) {
  const bad = [];
  for (const m of res.final?.created || []) {
    if (m.kind === 'workflow') {
      const g = await act(admin, 'workflow.get', { id: m.id });
      if (!g.ok) bad.push(`created ${m.id} does not read back (${g.error?.code})`);
      else if (g.output?.workflow?.status !== 'draft') bad.push(`created ${m.id} is ${g.output?.workflow?.status}, not draft`);
      if (!keep) await act(admin, 'workflow.delete', { id: m.id });
    } else if (m.kind === 'proposal') {
      const g = await fetch(API + '/api/screens/home/proposals', { headers: { Authorization: 'Bearer ' + admin } });
      const list = g.ok ? await g.json() : [];
      const rows = Array.isArray(list) ? list : list.proposals || list.items || [];
      if (!rows.some((p) => String(p.id) === String(m.id))) bad.push(`held proposal ${m.id} is not in the person's proposals`);
      else if (!keep) await act(admin, 'proposal.reject', { id: Number(m.id), reason: 'Live check: made by scripts/dev/ai-live-check, not wanted.' });
    } else if (m.kind === 'flow') {
      const g = await act(admin, 'flow.get', { flow_id: Number(m.id) });
      if (!g.ok) bad.push(`flow ${m.id} does not read back`);
      else if (g.output?.flow?.status !== 'draft') bad.push(`flow ${m.id} is ${g.output?.flow?.status}, not draft`);
      if (!keep) await act(admin, 'flow.discard', { flow_id: Number(m.id) });
    }
  }
  return bad;
}

async function runAll(tokens, flowId, forced, keep) {
  let fails = 0;
  for (const c of CASES) {
    if (ONLY && c.id !== ONLY) continue;
    const ctx = JSON.parse(JSON.stringify(c.ctx).replace('$FLOW', String(flowId)));
    const res = await ask(tokens[c.as], c.q, ctx);
    const bad = [...judge(c, res, forced), ...(await verifyAndClean(tokens.admin, res, c, keep))];
    const f = res.final || {};
    const tools = (f.tools || []).map((t) => t.name + (t.ok ? '' : `!${t.code}`)).join(',') || '-';
    const made = (f.created || []).map((m) => `${m.kind}:${m.id}`).join(',') || '-';
    console.log(
      [forced || 'chain', c.ctx.page, JSON.stringify(c.q.slice(0, 46)), f.by_model ? 'model' : 'rules', f.model || '-',
        f.fallback_reason || '-', res.ms + 'ms', tools, made, bad.length ? 'FAIL' : 'PASS'].join(' | '),
    );
    if (bad.length) {
      fails += 1;
      console.log('    why: ' + bad.join('; '));
      console.log('    said: ' + JSON.stringify((f.text || '').slice(0, 300)));
    }
  }
  return fails;
}

const tokens = {};
for (const u of ['admin', 'planner.a', 'approver']) tokens[u] = await login(u);
const flow = await act(tokens.admin, 'flow.get', { template: 'industrial', org: 'workspace' });
const flowId = flow.output?.flow?.id;
const models = (await act(tokens.admin, 'llm.models', {})).output?.models?.filter((m) => m.enabled) ?? [];
console.log(`api ${API} · models in the chain: ${models.map((m) => `${m.model} (p${m.priority})`).join(', ') || 'none'}`);
let failed = await runAll(tokens, flowId, null, flag('--keep'));
console.log(`default chain: ${failed ? failed + ' FAILED' : 'all passed'}`);
if (flag('--each-model')) {
  for (const m of models) {
    await act(tokens.admin, 'llm.setModel', { id: m.id, priority: 0 });
    try {
      const n = await runAll(tokens, flowId, m.model, flag('--keep'));
      console.log(`${m.model} first: ${n ? n + ' FAILED' : 'all passed'}`);
    } finally {
      await act(tokens.admin, 'llm.setModel', { id: m.id, priority: m.priority });
    }
  }
}
process.exit(failed ? 1 : 0);
