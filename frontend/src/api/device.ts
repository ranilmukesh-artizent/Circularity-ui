/**
 * The device recommerce case view (plan 9, P9-6.4, story DV-01): what the case page's "Device" tab shows for a case opened
 * from a received trade-in (backend/di/services/screens/case.py, the `device` block of the case). A read only: the block
 * comes with the case screen, so a device case needs no call of its own. A one-device case has an IMEI; a bulk lot has
 * none and a line per device. The one write is `decidePayout` (P9-6.8, DV-05): a person's decision on a payout that waits for
 * Customer care, through the action pipeline.
 */
import { invoke } from './actions';
import type { CaseRec } from './case';
import { forkFlow } from './modeler';
import type { FlowGraph } from './types';

/** The payout adjustment of a received device (P9-6.8, DV-05): the quote, the payout the pack's table gives and the gap. A gap
 * within the limit (`auto`) is adjusted at once; a bigger one is `waiting` for Customer care, with the grading photos, until a
 * person with `decidePayouts` decides it (`decided`). */
export interface PayoutView {
  status: 'adjusted' | 'waiting' | 'decided';
  quote: number;
  adjusted: number;
  /** the share the payout moved: -0.06 is 6% below the quote */
  gapPct: number;
  reason: string;
  /** the table version the rule is from, "US payout rules v1" */
  table: string;
  auto: boolean;
  /** the largest gap adjusted at once (guardrail GR-D11's max_auto_gap): 0.1 is 10% */
  limit: number;
  currency: string;
  /** the grading's photo ids */
  photos: string[];
  /** the `payout_gap` work item while it waits */
  item: number | null;
  decided: { by: string; reason: string; at: string } | null;
}

/** The sale of a received device settled (P9-6.12, DV-09), for one unit: what it sold for, the fees, the logistics and the buyer's
 * returns, the forecast P50 and the share of it realised. `net` is what the unit realised; `kpi` and `line` are the server's words. */
export interface SettlementView {
  price: number;
  fees: number;
  logistics: number;
  buyerReturns: number;
  forecastP50: number;
  /** the price over the forecast P50: 0.986 */
  realisedVsForecast: number;
  settledAt: string;
  saleId: string;
  net: number;
  kpi: string;
  line: string;
}

/** payout.decide: a person sets the payout of a waiting payout (never above the quote), with a reason. */
export const decidePayout = (caseId: string, payout: number, reason: string) =>
  invoke<{ case_id: string; payout: number }>('payout.decide', { case_id: caseId, payout, reason });

/** One device of a bulk lot. */
export interface DeviceLine { imei: string; model: string; storageGb: number; declaredGrade: string; grade: string; quote: number }

/** One field of the quote check (P9-6.5, DV-02): what the trade-in quoted and what the lab read (null: not read yet). */
export interface QuoteRow { field: 'imei' | 'model' | 'storage'; quoted: string | number | null; read: string | number | null; mismatch: boolean }

/** The quote against the lab's read of the device. `waiting`: no diagnostics yet, nothing is held. `item` is the
 * `quote_mismatch` exception a mismatch opened; only a person resolves it (work.resolve). */
export interface QuoteCheck {
  state: 'waiting' | 'match' | 'mismatch';
  rows: QuoteRow[];
  /** the owner label of the exception ("Customer care", role Planner) */
  owner: string;
  item: { id: number; state: 'open' | 'done'; outcome: string | null; by: string | null } | null;
}

/** The device registry's check of the device (P9-6.6, DV-03): blacklist, activation lock and finance, when and by whom. A hit
 * fails every channel and opens a `blacklist_hit` item for Compliance; only a person releases it, with a newer check. */
export interface RegistryView {
  state: 'none' | 'stale' | 'clear' | 'hit';
  /** "clear", or what the registry reports: "reported stolen", "activation lock on", "balance owed" (joined by "; ") */
  status: string;
  /** the check's calendar day (ISO), null when there is none */
  checkedAt: string | null;
  source: string;
  ageDays: number | null;
  recheckDays: number;
  /** the owner label of the exception ("Compliance", role Approver) */
  owner: string;
  item: 'open' | 'done' | null;
  /** the routes a locked or blacklisted device may still take (the pack's `locked_routes`) */
  allowedRoutes: string[];
}

/** The lab's data-wipe certificate of the device (P9-6.7, DV-04). `none`: no certificate, or one lacking a field (every channel
 * but recycle is blocked and the case waits); `failed`: the verification failed (a step is required); `ok`. `batch` counts
 * the cases of the device's batch that still wait for a certificate. */
export interface WipeView {
  state: 'none' | 'failed' | 'ok';
  certificate: { id: string | null; method: string | null; toolVersion: string | null; verification: string | null; operator: string | null; at: string | null } | null;
  missing: string[];
  batch: { ref: string; total: number; waiting: number } | null;
}

export interface DeviceView {
  /** the device's IMEI; null for a bulk lot */
  imei: string | null;
  sku: string;
  brand: string;
  model: string;
  storageGb: number | null;
  declaredGrade: string;
  /** the grade the case is valued on: the cosmetic grade when graded, else the declared one */
  grade: string;
  graded: boolean;
  quote: { amount: number; currency: string } | null;
  partner: string;
  batch: string | null;
  /** when the lab received it (ISO) */
  received: string;
  /** the reference value a unit and where it came from (the market feed, else the quote) */
  ref: number;
  refSource: 'feed' | 'quote';
  bulk: boolean;
  lines: DeviceLine[];
  /** the quote against the lab's read; null for a bulk lot */
  quoteCheck?: QuoteCheck | null;
  /** the registry's check; null for a bulk lot */
  registry?: RegistryView | null;
  /** the wipe certificate; null for a bulk lot */
  wipe?: WipeView | null;
  /** the payout adjustment; null until the lab has graded the device and read its battery (and for a bulk lot) */
  payout?: PayoutView | null;
  /** the sale's price against the forecast; null until the market reports the sale */
  settlement?: SettlementView | null;
  /** the price of each channel with its interval, best first (P9-6.10); null for a bulk lot */
  channels?: ChannelView[] | null;
  /** the floor (GR-D2) and price-confidence (GR-D8) holds that wait for a person, with their owner label */
  priceHolds?: PriceHold[];
}

/** One channel's price (P9-6.10): expected cash a unit and days to sell; P10 and P90 cash, the week of the market feed and
 * the price model's id when the channel has a price band. */
export interface ChannelView {
  k: string;
  name: string;
  cash: number;
  days: number;
  p10: number | null;
  p90: number | null;
  /** ISO date of the feed week the price rests on */
  feedWeek: string | null;
  modelId: string | null;
  ok: boolean;
  why: string;
}

/** A hold on the price: the guardrail that raised it (GR-D2 floor, GR-D8 confidence), why, and who it waits for. */
export interface PriceHold { id: string; reason: string; owner: string; signals?: string[] }

/** The device block of a case, or null for a case that is not a received device (the industrial book, a tool return). */
export const deviceView = (c: CaseRec): DeviceView | null => c.device ?? null;

/** One bid on a wholesale lot (P9-6.11): what the buyer bids a unit, the fees and logistics a unit that come off it, and the net. */
export interface LotBid { bid_id: string; buyer_code: string; amount: number; fees: number; logistics: number; net: number }

/** A wholesale lot of received devices (P9-6.11, DV-07). It is idding until a person with manageLots proposes it; the best
 * bid is computed among the approved buyers (a bid from any other buyer is in dropped, with its reason) and a person with the
 * Approver role accepts it, never the one who built or proposed it. waits_for says who a proposed lot waits for. */
export interface LotView {
  id: string;
  lot_ref: string;
  org_unit_id: string | null;
  model: string;
  grade: string;
  units: number;
  status: 'draft' | 'bidding' | 'proposed' | 'approved' | 'rejected' | 'sold';
  bids_received: number;
  best_bid: LotBid | null;
  dropped: { bid_id: string; buyer_code: string; reason: string }[];
  value_usd: number | null;
  created_by: string;
  proposed_by: string | null;
  approved_by: string | null;
  reason: string | null;
  waits_for: { role: string; owner: string; reason: string } | null;
  case_ids?: string[];
}

export interface LotList { lots: LotView[]; me: string; can: { build: boolean; approve: boolean } }

/** lot.list: the lots of the orgs the signed-in person sees (a read action; the card calls it again after each lot action). */
export const listLots = () => invoke<LotList>('lot.list', {});

/** lot.build: group the org's open wholesale-routed devices into lots and post them for bids. */
export const buildLots = (orgUnitId: string) => invoke<{ lots: LotView[] }>('lot.build', { org_unit_id: orgUnitId });

/** lot.propose: pick the best approved bid. At or under the limit the standing policy approves it; above, it waits for the Commercial manager. */
export const proposeLot = (lotId: string) => invoke<{ status: string; approved_by_policy: boolean }>('lot.propose', { lot_id: lotId });

/** lot.approve: a person accepts the proposed bid (not the person who built or proposed the lot). */
export const approveLot = (lotId: string) => invoke<{ status: string }>('lot.approve', { lot_id: lotId });

/** lot.reject: send a proposed lot back with a reason. */
export const rejectLot = (lotId: string, reason: string) => invoke<{ status: string }>('lot.reject', { lot_id: lotId, reason });

/** One ageing suggestion (P9-6.13, DV-08): listings that sit with no offer (Offers) or unsold (Buy Now) past the customer's days, the
 * move to the next channel, and the draft rule as a checked, simulated proposal. The numbers are counted from the listings. */
export interface AgeingSuggestion {
  kind: 'offers_to_auction' | 'buynow_to_offers';
  from: string;
  to: string;
  /** the age band: the days listed the rule asks for */
  days: number;
  n: number;
  value: number;
  listings: string[];
  /** "Move 12 Offers listings to Auction: 14 days, no offer" */
  text: string;
  rule: Record<string, unknown>;
  proposal: { kind: 'rule' | 'blocked'; graph: FlowGraph; rid: string; guard: string | null; msg: string };
}

export interface AgeingList {
  flow_id: number;
  /** the org that owns the flow: not `org_unit_id` when the org inherits its flow (accepting forks it first) */
  flow_org: string;
  org_unit_id: string;
  as_of: string;
  offers_days: number;
  choices: number[];
  buynow_days: number;
  suggestions: AgeingSuggestion[];
}

/** device.ageingSuggestions: the moves the org's live listings call for (a read action; nothing is saved). */
export const ageingSuggestions = (orgUnitId: string, offersDays?: number) =>
  invoke<AgeingList>('device.ageingSuggestions', { org_unit_id: orgUnitId, ...(offersDays ? { offers_days: offersDays } : {}) });

/** Accept a suggestion: the person's own flow.saveDraft of its graph (the org's flow is forked first when it inherits one). The
 * flow is then submitted and approved by a different person, as any change; nothing here approves or publishes. */
export async function acceptAgeingSuggestion(s: AgeingSuggestion, t: Pick<AgeingList, 'flow_id' | 'flow_org' | 'org_unit_id'>) {
  let flowId = t.flow_id;
  if (t.flow_org !== t.org_unit_id) {
    const f = await forkFlow('device', t.org_unit_id);
    if (!f.ok) return f;
    flowId = f.output.flow_id;
  }
  return invoke<{ id: number }>('flow.saveDraft', { flow_id: flowId, graph: s.proposal.graph, source: 'assistant', note: 'Ageing suggestion: ' + s.text });
}
