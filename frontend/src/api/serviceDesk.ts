/**
 * The service desk case view (plan 9, P9-4.3, story SD-01): what the case page's "Ticket" tab shows for a case opened from a
 * customer's service ticket or batch (backend/di/services/service_desk/intake.py, the `serviceDesk` block of the case). A read
 * only: the block comes with the case screen, so a service-desk case needs no call of its own.
 */
import type { CaseRec } from './case';

/** The result of one check of one line: the contract right (GR-07) or the safety recall check (GR-12). */
export interface LineGate { id: 'G-CON-2' | 'G-TOOL-REC'; name: string; guardrail: 'GR-07' | 'GR-12'; passed: boolean; reason: string }

/** One priced line of an estimate and the rate table version it cites ("US labour rates v1"). */
export interface EstimateLine { label: string; amount: number; basis: string; cites: string }

/** The estimate of a line from similar past repairs (P9-4.4, SD-02), computed by the server: never written by a model. `auto`
 * is true when it may be priced without a technician; `item` is the technician-check work item of a draft. */
export interface LineEstimate {
  point: number; p10: number; p90: number; n: number; key_used: 'class_fault_age' | 'class_fault'; lines: EstimateLine[];
  auto: boolean; reason: string; confidence: number; currency: string; as_of: string; item: number | null;
}

/** The three ways to settle a line: fix it, a covered swap, an upgrade offer (P9-4.6, SD-04). */
export type OptionKey = 'fix' | 'swap' | 'upgrade';

/** One value line of an option and the table it cites. `type` v is value, c is cost. */
export interface OptionLine { type: 'v' | 'c'; label: string; amt: number; basis: string; cites: string }

/** One option of a line (or of the whole case), computed by the server from the estimate, the approved tables, the refurbished
 * stock and the past offers; never written by a model. An ineligible option has only its `why`. `takeUp` is the chance the
 * customer accepts an upgrade. */
export interface TicketOption {
  k: OptionKey; name: string; eligible: boolean; why: string; customer_price: number | null; margin: number | null;
  expected_margin: number | null; days: number | null; take_up: number | null; credit: number | null; cost: number | null; lines: OptionLine[];
}

/** Who approves the recommendation, and what holds it for a person (GR-14, GR-C1, GR-S3, GR-S1). */
export interface Approval { route: string; owner: string; holds: { id: string; reason: string; owner: string }[] }

/** One tool of the ticket. `fault_code` is empty when the fault is unclear; `life_used_pct` is its age against its rated life. */
export interface TicketLine {
  n: number; serial: string; model_class: string; family: string; age_months: number; fault_code: string | null; fault_text: string | null;
  cover_type: string | null; cover_until: string | null; life_used_pct: number; gates: LineGate[]; estimate?: LineEstimate | null;
  options?: TicketOption[]; best?: OptionKey | null;
}

/** A service ticket (or a batch of tools) and its lines. */
export interface ServiceDeskView {
  ticket: string; account: string | null; market: string | null; site: string | null; batch: boolean; batchId: string | null;
  loanerPromised: boolean; requesterRole: string | null; lines: TicketLine[]; options?: TicketOption[]; approval?: Approval | null;
}

/** The service-desk block of a case, or null for a case that is not opened from a ticket (the industrial book, a return). */
export const serviceDeskView = (c: CaseRec): ServiceDeskView | null => c.serviceDesk ?? null;