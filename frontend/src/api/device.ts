/**
 * The device recommerce case view (plan 9, P9-6.4, story DV-01): what the case page's "Device" tab shows for a case opened
 * from a received trade-in (backend/di/services/screens/case.py, the `device` block of the case). A read only: the block
 * comes with the case screen, so a device case needs no call of its own. A one-device case has an IMEI; a bulk lot has
 * none and a line per device.
 */
import type { CaseRec } from './case';

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
}

/** The device block of a case, or null for a case that is not a received device (the industrial book, a tool return). */
export const deviceView = (c: CaseRec): DeviceView | null => c.device ?? null;
