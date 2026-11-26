/** Wording of the case page's Device tab (P9-6.4, DV-01) over the `device` block of a case. */
import { money } from '../../api/format';
import type { ChannelView, DeviceView, DiversionView, PayoutView, QuoteCheck, QuoteRow, RegistryView, RepairQuote, SettlementView, WipeView } from '../../api/device';

/** "iPhone 14 · 128 GB · declared B · quote $410 · partner P01"; a bulk lot: "20 devices · batch BATCH-0020 · grade B · partner P01". */
export function deviceLine(v: DeviceView): string {
  if (v.bulk) {
    return [`${v.lines.length} devices`, v.batch ? `batch ${v.batch}` : '', `grade ${v.grade}`, `partner ${v.partner}`].filter(Boolean).join(' · ');
  }
  return [
    v.model, v.storageGb != null ? `${v.storageGb} GB` : '', `declared ${v.declaredGrade}`,
    v.quote ? `quote ${money(v.quote.amount)}` : '', `partner ${v.partner}`,
  ].filter(Boolean).join(' · ');
}

/** "Reference $330 a unit, from the market feed" or "... from the quote". */
export function refLine(v: DeviceView): string {
  return `Reference ${money(v.ref)} a unit, from ${v.refSource === 'feed' ? 'the market feed' : 'the quote'}`;
}

/** "grade C (graded)" or "grade B (declared)". */
export function gradeLine(v: DeviceView): string {
  return `grade ${v.grade} (${v.graded ? 'graded' : 'declared'})`;
}

const FIELD_LABEL = { imei: 'IMEI', model: 'Model', storage: 'Storage' } as const;
const said = (field: QuoteRow['field'], v: string | number | null) => (field === 'storage' ? `${v} GB` : String(v));

/** "Storage quoted 256 GB, read 128 GB" (the backend says the same, verify.mismatch_line). */
export function mismatchLine(m: Pick<QuoteRow, 'field' | 'quoted' | 'read'>): string {
  return `${FIELD_LABEL[m.field]} quoted ${said(m.field, m.quoted)}, read ${said(m.field, m.read)}`;
}

/** What the quote check says in one line: "Quote matches the device read", "Waiting for the lab's diagnostics" or the
 * mismatches joined, then who owns the exception and where it stands. */
export function quoteCheckLine(q: QuoteCheck): string {
  if (q.state === 'waiting') return "Waiting for the lab's diagnostics";
  if (q.state === 'match') return 'Quote matches the device read';
  const lines = q.rows.filter((r) => r.mismatch).map(mismatchLine).join('; ');
  const where = q.item ? (q.item.state === 'open' ? 'open' : `resolved${q.item.outcome ? `: ${q.item.outcome}` : ''}`) : 'not opened';
  return `${lines}. ${q.owner}, ${where}`;
}

/** "6 Oct 2026" (the registry's check date, a calendar day). */
const day = (d: string) => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });

/** "Registry: reported stolen · checked 6 Oct 2026 · Device registry (synthetic)"; with no check: "Registry: no check on file". */
export function registryLine(e: Pick<RegistryView, 'status' | 'checkedAt' | 'source'>): string {
  if (!e.checkedAt && e.status === 'clear') return 'Registry: no check on file';
  return ['Registry: ' + e.status, e.checkedAt ? `checked ${day(e.checkedAt)}` : 'no check date', e.source].filter(Boolean).join(' · ');
}

/** "Purge · tool 4.2 · verified · operator OP-17 · 6 Oct 2026" (the certificate's method, tool version, verification, operator
 * and day); a verification that failed reads "verification failed". */
export function wipeLine(c: NonNullable<WipeView['certificate']>): string {
  const how = c.verification === 'pass' ? 'verified' : c.verification === 'fail' ? 'verification failed' : (c.verification ?? '');
  return [c.method, c.toolVersion ? `tool ${c.toolVersion}` : '', how, c.operator ? `operator ${c.operator}` : '', c.at ? day(c.at) : '']
    .filter(Boolean).join(' · ');
}

/** What the Compliance tab says of the wipe: the certificate line, "Wipe verification failed: re-run the wipe or destroy the
 * storage", or "Waiting for the wipe certificate (batch BATCH-0007: 12 of 40 waiting)". */
export function wipeState(w: WipeView): string {
  if (w.state === 'ok' && w.certificate) return wipeLine(w.certificate);
  if (w.state === 'failed') return 'Wipe verification failed: re-run the wipe or destroy the storage';
  return 'Waiting for the wipe certificate' + (w.batch ? ` (batch ${w.batch.ref}: ${w.batch.waiting} of ${w.batch.total} waiting)` : '');
}

/** Where a registry hit stands: "Waiting for Compliance" while its item is open, "Released by Compliance" once a person
 * resolved it, else a short reading of the state. The routes a locked device may still take follow. */
export function registryState(r: RegistryView): string {
  if (r.state === 'hit') {
    const where = r.item === 'done' ? 'Released by ' + r.owner : 'Waiting for ' + r.owner;
    return r.allowedRoutes.length ? `${where} · may still go to ${r.allowedRoutes.join(', ')}` : where;
  }
  if (r.state === 'none') return 'No registry check yet: the case waits for one';
  if (r.state === 'stale') return `Check older than ${r.recheckDays} days: the case waits for a new one`;
  return 'Clear';
}

/** The lines of a bulk lot: "<imei> · iPhone 14 · 128 GB · grade B · quote $410". */
export function lotLines(v: DeviceView): string[] {
  return v.lines.map((l) => [l.imei, l.model, `${l.storageGb} GB`, `grade ${l.grade}`, `quote ${money(l.quote)}`].join(' · '));
}

/** "$410" for a whole amount, "$385.40" otherwise (a payout is paid to the cent; the page's `money` rounds to dollars). */
export const usd = (n: number): string => '$' + (Number.isInteger(n) ? n.toLocaleString('en-US') : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

/** "−6%" for a payout 6% below the quote, "+3%", "0%". */
export const gapText = (g: number): string => {
  const p = Math.round(g * 1000) / 10;
  return (p < 0 ? '−' : p > 0 ? '+' : '') + Math.abs(p) + '%';
};

/** "$410 → $385.40 (−6%) · Battery health 80–84%": the quote, the adjusted payout, the gap and the rule (the table's words). */
export function payoutLine(p: PayoutView): string {
  return `${usd(p.quote)} → ${usd(p.adjusted)} (${gapText(p.gapPct)}) · ${p.reason}`;
}

/** Where a payout stands: "Adjusted by the table: US payout rules v1", "Waiting for Customer care: the gap is above 10%" or
 * "Decided by planner.a: $300 (Cracked glass)". */
export function payoutState(p: PayoutView): string {
  if (p.status === 'decided' && p.decided) return `Decided by ${p.decided.by}: ${usd(p.adjusted)} (${p.decided.reason})`;
  if (p.status === 'waiting') return `Waiting for Customer care: the gap is above ${gapText(p.limit).replace(/^[+−]/, '')}`;
  return `Adjusted by the table: ${p.table}`;
}

/** "Buy Now · $312 net · 11.6 days · $280–$335 · feed 5 Oct 2026" (P9-6.10): a channel's expected net a unit, days to sell, the
 * P10 to P90 cash and the feed week, the last two only when the channel was priced from a band; the model follows its id. */
export function channelRow(v: ChannelView): string {
  const band = v.p10 != null && v.p90 != null ? `${money(v.p10)}–${money(v.p90)}` : '';
  const feed = v.feedWeek ? `feed ${day(v.feedWeek)}` : '';
  return [v.name, `${money(v.cash)} net`, `${v.days.toFixed(1)} days`, band, feed, v.modelId ? `model ${v.modelId}` : '', v.ok ? '' : 'not allowed']
    .filter(Boolean).join(' · ');
}

/** "battery swap +$28 price, −$24 cost, +5 days" (P9-6.15, DV-11): what a repair quote adds to the price, costs and takes. */
export function evidenceLine(q: RepairQuote): string {
  const n = (v: number) => String(Number(v.toFixed(2)));
  return `${q.repair.toLowerCase()} +$${n(q.priceUplift)} price, −$${n(q.cost)} cost, +${n(q.days)} days`;
}

/** "98.6%" for a sale at 0.986 of the forecast, "90%" at 0.9 (one decimal, no trailing zero). */
const sharePct = (r: number): string => `${Number((r * 100).toFixed(1))}%`;

/** "Sold $318 · fees $9.54 · returns $0 · 98.6% of forecast" (P9-6.12, DV-09): what the unit sold for, the fees and returns, and the
 * price over the forecast P50. */
export function settlementLine(s: SettlementView): string {
  return `Sold ${usd(s.price)} · fees ${usd(s.fees)} · returns ${usd(s.buyerReturns)} · ${sharePct(s.realisedVsForecast)} of forecast`;
}

/** "Price realised against forecast 98.6%": the KPI of a settled device case. */
export const realisedKpi = (s: SettlementView): string => `Price realised against forecast ${sharePct(s.realisedVsForecast)}`;

/** "Diversion: second grading check (partner P02)" or "Diversion: straight to wholesale lot (grade C, model over 3 years)": what a
 * customer's diversion did, then why. A route other than wholesale reads "straight to <route>". */
export function diversionLine(d: Pick<DiversionView, 'kind' | 'step' | 'to' | 'because'>): string {
  const what = d.kind === 'step' ? (d.step ?? 'extra step').toLowerCase() : `straight to ${d.to === 'wholesale' ? 'wholesale lot' : (d.to ?? 'a route')}`;
  return `Diversion: ${what}${d.because.length ? ` (${d.because.join(', ')})` : ''}`;
}
