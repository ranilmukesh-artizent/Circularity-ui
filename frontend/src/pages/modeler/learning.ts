/** Wording of the Modeler's rule suggestions from overrides (audit U8). */
import type { RuleSuggestion } from '../../api/modeler';

/** "3 of 4 motor decisions overridden to Whole-asset resale (75%)". */
export function shareLine(s: RuleSuggestion, pathName: (id: string) => string): string {
  return `${s.overrides} of ${s.decisions} ${s.value} decisions overridden to ${pathName(s.path)} (${Math.round(s.share * 100)}%)`;
}
