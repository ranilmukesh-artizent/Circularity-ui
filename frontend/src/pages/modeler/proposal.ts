/** The assistant's proposal as the Modeler shows it (the prototype's chat() and propHtml, lines 2438 and 2461-2465). */
import type { Proposal } from '../../api/modeler';

/** The opening line of the assistant for a template (the prototype's chat(), line 2438). */
export function openingLine(template: string): string {
  return template === 'device'
    ? 'This is the device recommerce template: four channels, routed on cash per unit against days on hand. Describe a change and I will check it, simulate it on the sample lots and, once you approve, apply it to the draft flow.'
    : 'I watch this flow and the decisions it produces. Tell me what you want to change in plain words. I check it against the process, the guardrails and the existing rules, simulate it on the open queue, and only change the flow once you approve.';
}

export interface CheckLine {
  level: 'ok' | 'warn';
  text: string;
}

/** The checks list of a proposal: fits the process, passes the guardrails, the conflicts (or none), models unchanged. */
export function proposalChecks(p: Proposal, guardrails: number): CheckLine[] {
  const conflicts = p.checks.filter((c) => c.level === 'warn');
  return [
    { level: 'ok', text: 'Fits the process: placed between the guardrail gate and the decision' },
    { level: 'ok', text: `Passes all ${guardrails} locked guardrails` },
    ...(conflicts.length ? conflicts.map((c): CheckLine => ({ level: 'warn', text: c.msg })) : [{ level: 'ok' as const, text: 'No conflict with existing rules' }]),
    { level: 'ok', text: 'Prediction models and agents unchanged' },
  ];
}
