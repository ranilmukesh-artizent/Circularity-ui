/** The ageing card's pure helpers (plan 9, P9-6.13, story DV-08): the line a suggestion is shown as and the words after Accept.
 * The server counts the listings and sums their value; nothing here computes a figure. */
import type { AgeingSuggestion } from '../../api/device';
import { usd } from './lots';

/** "Move 12 Offers listings to Auction: 14 days, no offer · $3,840". */
export const ageingLine = (s: Pick<AgeingSuggestion, 'text' | 'value'>): string => `${s.text} · ${usd(s.value)}`;

/** What follows Accept: the rule is in the person's draft, and a different person approves it (maker-checker). */
export const ACCEPTED = 'Added to your draft; a different person approves it';

/** Why a suggestion cannot be accepted (a guardrail blocks the rule), or null. */
export const blockedBy = (s: Pick<AgeingSuggestion, 'proposal'>): string | null =>
  s.proposal.kind === 'blocked' ? s.proposal.msg || 'A guardrail blocks this rule.' : null;
