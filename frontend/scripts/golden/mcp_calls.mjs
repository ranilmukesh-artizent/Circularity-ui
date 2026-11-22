// B16 golden data for the MCP server: what the demo's tool layer answers for each agent, tool, case and tenant, and the
// call-log entry each call records.
//
//   node frontend/scripts/golden/mcp_calls.mjs   -> fixtures/golden/mcp.json
//
// The demo's MCP layer is the tool playground (fixtures/demo/index.html, "MCP & Tools"): runTool(tool, agent, tenant,
// json) checks the agent's scope, the input schema, the case and the tenant boundary, runs the tool, and ACT.pgRun puts the call
// at the head of the call log (CALLS). Each call here goes through ACT.pgRun itself, so the result (S.pgOut) and the
// log entry (CALLS[0]) are the demo's own; pgRun's re-render afterwards needs a page, which the sandbox does not
// have, and its error is ignored (the result and the log entry are already written by then).
//
// Each scenario runs in a fresh copy of the demo, signed in as the account the server test uses for that tenant (the
// demo's tool layer does not read the account; the server runs every call as one). A call is
// [agent, tool, tenant, input] (input may be a function of the demo); ['approve', case_id] is the human approval
// between two tool calls: decision.approve as the Approver, with the inputs of the demo's RT-1048 journey.
//
// Recorded per call: the result's ok, outcome, result or error, caseId, and its trace (step name, ok, detail; the
// step times are random draws and are dropped), and the log entry (its latency is the sum of those random times, so
// the server compares it as a number only).
import { freshDemo, plain, writeGolden } from '../golden-sandbox.mjs';

const ACCOUNT_OF = { 'Customer A': 'planner-a', 'Customer B': 'planner-b', 'Customer C': 'planner-c' };
const A = 'Customer A', B = 'Customer B', C = 'Customer C';
const approvalRef = (h) => ({ case_id: 'RT-1048', approval_ref: h('CASE_BY_ID')['RT-1048'].approval?.ref ?? 'none' });

const SCENARIOS = {
  evidence: [
    ['assembler', 'get_case_evidence', A, { case_id: 'RT-1048' }],
    ['finder', 'get_case_evidence', A, { case_id: 'RT-1049' }],
    ['gap', 'get_case_evidence', A, { case_id: 'RT-1051' }],
    ['coordinator', 'get_case_evidence', A, { case_id: 'RT-1003' }],
    ['reconciler', 'get_case_evidence', A, { case_id: 'RT-1042' }],
    ['assembler', 'get_case_evidence', B, { case_id: 'RT-1050' }],
    ['assembler', 'get_case_evidence', C, { case_id: 'RT-1052' }],
    ['assembler', 'get_case_evidence', A, { case_id: 'RT-1001' }], // another tenant's case
    ['assembler', 'get_case_evidence', B, { case_id: 'RT-1048' }], // another tenant's case
    ['assembler', 'get_case_evidence', A, { case_id: 'RT-9999' }], // no such case
    ['assembler', 'get_case_evidence', A, {}], // missing input
    ['assembler', 'get_case_evidence', A, { case_id: 1048 }], // wrong type
  ],
  scope: [
    ['assembler', 'request_missing_evidence', A, { case_id: 'RT-1051', kind: 'inspection' }],
    ['assembler', 'send_instruction', A, { case_id: 'RT-1048', approval_ref: 'APR-2026-10-0161' }],
    ['assembler', 'find_demand', A, { case_id: 'RT-1049' }],
    ['finder', 'request_approval', A, { case_id: 'RT-1049', rationale: 'Resale narrowly beats refurbishment by $15' }],
    ['finder', 'get_model_validation', A, { version: 'v1.3' }],
    ['gap', 'list_eligible_routes', A, { case_id: 'RT-1048' }],
    ['coordinator', 'reconcile_outcome', A, { case_id: 'CS-2041' }],
    ['reconciler', 'optimize_pool', A, { pool_id: 'RT-1048' }],
  ],
  routes: [
    ['assembler', 'list_eligible_routes', A, { case_id: 'RT-1048' }],
    ['finder', 'list_eligible_routes', A, { case_id: 'RT-1048', include_excluded: false }],
    ['finder', 'list_eligible_routes', A, { case_id: 'RT-1027', include_excluded: true }],
    ['assembler', 'list_eligible_routes', A, { case_id: 'RT-1051' }], // blocked: withheld
    ['finder', 'list_eligible_routes', B, { case_id: 'RT-1050' }], // blocked, every route failed a gate
    ['finder', 'list_eligible_routes', B, { case_id: 'RT-1104' }],
    ['finder', 'list_eligible_routes', A, { case_id: 'RT-1104' }], // another tenant's case
    ['finder', 'list_eligible_routes', A, { case_id: 'RT-1048', include_excluded: 'yes' }], // wrong type
  ],
  predict: [
    ['finder', 'predict_outcomes', A, { case_id: 'RT-1048' }],
    ['finder', 'predict_outcomes', A, { case_id: 'RT-1048', route: 'redeploy' }],
    ['finder', 'predict_outcomes', A, { case_id: 'RT-1048', route: 'extparts' }], // excluded: a failed gate is not waived
    ['finder', 'predict_outcomes', A, { case_id: 'RT-1048', route: 'teleport' }],
    ['finder', 'predict_outcomes', A, { case_id: 'RT-1049' }],
    ['finder', 'predict_outcomes', A, { case_id: 'RT-1051' }], // blocked: withheld
    ['finder', 'predict_outcomes', C, { case_id: 'RT-1052', route: 'extparts' }],
    ['finder', 'predict_outcomes', B, { case_id: 'RT-1049' }], // another tenant's case
  ],
  pools: [
    ['finder', 'optimize_pool', A, { pool_id: 'RT-1048' }],
    ['finder', 'optimize_pool', C, { pool_id: 'RT-1052' }],
    ['finder', 'optimize_pool', A, { pool_id: 'RT-1049' }], // not in a pool
    ['finder', 'optimize_pool', A, { pool_id: 'POOL-9' }],
    ['finder', 'optimize_pool', A, {}],
  ],
  demand: [
    ['finder', 'find_demand', A, { case_id: 'RT-1049' }],
    ['finder', 'find_demand', A, { case_id: 'RT-1048' }],
    ['finder', 'find_demand', B, { case_id: 'RT-1104' }],
    ['finder', 'find_demand', C, { case_id: 'RT-1052' }],
    ['finder', 'find_demand', C, { case_id: 'RT-1104' }], // another tenant's case
  ],
  models: [
    ['assembler', 'get_model_validation', A, { version: 'v1.3' }],
    ['reconciler', 'get_model_validation', B, { version: 'v1.0' }],
    ['reconciler', 'get_model_validation', C, { version: 'v1.2' }],
    ['assembler', 'get_model_validation', A, { version: 'v9' }],
    ['assembler', 'get_model_validation', A, { version: 13 }],
  ],
  gaps: [
    ['gap', 'request_missing_evidence', A, { case_id: 'RT-1051', kind: 'inspection' }],
    ['gap', 'request_missing_evidence', B, { case_id: 'RT-1045', kind: 'test' }],
    ['gap', 'request_missing_evidence', A, { case_id: 'RT-1048', kind: 'photos' }], // nothing missing
    ['gap', 'request_missing_evidence', A, { case_id: 'RT-1051' }], // missing kind
    ['gap', 'request_missing_evidence', A, { case_id: 'RT-1045', kind: 'test' }], // another tenant's case
  ],
  approval: [
    ['coordinator', 'request_approval', A, { case_id: 'RT-1049', rationale: 'Resale narrowly beats refurbishment by $15' }],
    ['coordinator', 'request_approval', C, { case_id: 'RT-1044', rationale: 'Pool allocation lifts the total' }],
    ['coordinator', 'request_approval', A, { case_id: 'RT-1049' }], // missing rationale
    ['coordinator', 'request_approval', B, { case_id: 'RT-1049', rationale: 'Resale narrowly beats refurbishment by $15' }],
  ],
  instructions: [
    ['coordinator', 'send_instruction', A, { case_id: 'RT-1048' }], // no approval reference
    ['coordinator', 'send_instruction', A, { case_id: 'RT-1048', approval_ref: 'APR-2026-10-0161' }], // none recorded
    ['coordinator', 'send_instruction', A, { case_id: 'RT-1003', approval_ref: 'APR-2026-10-0000' }], // not the recorded one
    ['coordinator', 'send_instruction', A, { case_id: 'RT-1003', approval_ref: 'APR-2026-10-3026' }],
    ['coordinator', 'send_instruction', B, { case_id: 'RT-1040', approval_ref: 'APR-2026-10-3137' }],
    ['coordinator', 'send_instruction', B, { case_id: 'RT-1003', approval_ref: 'APR-2026-10-3026' }], // another tenant's case
  ],
  // request approval (held), a person approves, then the instruction goes with the recorded reference
  approve_then_send: [
    ['coordinator', 'send_instruction', A, approvalRef],
    ['coordinator', 'request_approval', A, { case_id: 'RT-1048', rationale: 'Redeploy to the Chennai line; pool uplift confirmed' }],
    ['approve', 'RT-1048'],
    ['coordinator', 'send_instruction', A, approvalRef],
    ['coordinator', 'send_instruction', A, approvalRef], // a retry: idempotent
  ],
  reconcile: [
    ['reconciler', 'reconcile_outcome', A, { case_id: 'CS-2041' }],
    ['reconciler', 'reconcile_outcome', A, { case_id: 'CS-3138' }], // pending
    ['reconciler', 'reconcile_outcome', A, { case_id: 'CS-0001' }],
    ['reconciler', 'reconcile_outcome', A, { case_id: 'RT-1048' }], // a live case, not a closed one
    ['reconciler', 'reconcile_outcome', A, {}],
  ],
};

function approve(h, id) {
  const c = h('CASE_BY_ID')[id], rec = c.recommendation;
  h('setAcct')(h('ACCT')('approver'));
  const input = {
    case_id: id, route: rec.plan, rationale: c.packet ? c.packet.rationale : h('afDraftRationale')(c), reviewed: true,
    spend: h('defaultSpend')(c, rec), terms: '',
  };
  const r = h('invoke')('decision.approve', input);
  return { input, result: plain(r.ok ? { ok: true, output: r.output } : { ok: false, error: r.error }) };
}

function runCall(h, agent, tool, tenant, input) {
  const S = h('S'), CALLS = h('CALLS');
  h('setAcct')(h('ACCT')(ACCOUNT_OF[tenant]));
  Object.assign(S, { mcpTool: tool, mcpAgent: agent, mcpTenant: tenant, pgInput: JSON.stringify(input), pgOut: null });
  const before = CALLS.length;
  try {
    h('ACT').pgRun();
  } catch (e) {
    if (!S.pgOut) throw e; // the render after the call needs a page; anything earlier is a real failure
  }
  if (CALLS.length !== before + 1) throw new Error(`${tool}: the call was not logged`);
  const o = S.pgOut;
  return {
    ok: o.ok,
    outcome: o.outcome,
    caseId: o.caseId ?? null,
    ...(o.ok ? { result: plain(o.result) } : { error: plain(o.error) }),
    trace: o.trace.map((s) => ({ n: s.n, ok: s.ok, detail: s.detail })),
    log: plain(CALLS[0]),
  };
}

const scenarios = {};
for (const [name, calls] of Object.entries(SCENARIOS)) {
  const h = freshDemo();
  scenarios[name] = calls.map(([agent, tool, tenant, input]) => {
    if (agent === 'approve') return { approve: tool, as: 'approver', ...approve(h, tool) };
    const i = typeof input === 'function' ? input(h) : input;
    return { agent, tool, tenant, account: ACCOUNT_OF[tenant], input: i, ...runCall(h, agent, tool, tenant, i) };
  });
}

const n = Object.values(scenarios).flat().filter((c) => c.tool).length;
console.log(`wrote ${writeGolden('mcp.json', { scenarios })} (${Object.keys(scenarios).length} scenarios, ${n} tool calls)`);
