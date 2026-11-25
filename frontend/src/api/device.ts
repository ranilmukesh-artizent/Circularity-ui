/**
 * The device recommerce case view (plan 9, P9-6.4, story DV-01): what the case page's "Device" tab shows for a case opened
 * from a received trade-in (backend/di/services/screens/case.py, the `device` block of the case). A read only: the block
 * comes with the case screen, so a device case needs no call of its own. A one-device case has an IMEI; a bulk lot has
 * none and a line per device.
 */
import type { CaseRec } from './case';

/** One device of a bulk lot. */
export interface DeviceLine { imei: string; model: string; storageGb: number; declaredGrade: string; grade: string; quote: number }

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
}

/** The device block of a case, or null for a case that is not a received device (the industrial book, a tool return). */
export const deviceView = (c: CaseRec): DeviceView | null => c.device ?? null;
