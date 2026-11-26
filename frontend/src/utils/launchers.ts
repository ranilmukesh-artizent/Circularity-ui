/**
 * The questions the inline launchers send to the one assistant (plan 10, T6). A launcher is a text button on a page
 * ("Explain", "Summarise", "Ask about RT-1048"); it opens Ask Circularity with a question that names the thing the
 * person is looking at, so the answer needs no further context. The case page's own context (Case: RT-1048) comes
 * from the route; the KPI, alert, check or report is named in the question itself.
 */
import { openAssistant } from './askBus';

/** Each question as a pure string, so a test can say exactly what a launcher sends. */
export const launch = {
  explainAlert: (title: string) => `Explain the alert "${title}": what raised it and what should I do about it?`,
  explainCheck: (name: string) => `Explain the check "${name}": what it tests and what to do when it fails.`,
  explainKpi: (label: string) => `Explain this number: ${label}. Where does it come from and what moves it?`,
  summariseReport: (title: string) => `Summarise the report "${title}" in a few sentences.`,
  askAboutCase: (id: string) => `Tell me about ${id}: where it stands, why this route, and what it is waiting for.`,
  askAboutStage: (id: string, n: number, title: string) => `Tell me about stage ${n} (${title}) of ${id}: what it needs and who owns it.`,
  notifyOwner: (who: string) => `Draft a note to ${who} asking them to act on the step this case is waiting for.`,
  howToDo: (group: string, count: number) => `How do I do these ${count} "${group}" tasks? Walk me through what to open and what to check.`,
  howToDoTask: (task: string, caseId?: string) => `How do I do this: ${task}${caseId ? ` (${caseId})` : ''}?`,
  explainWorkflow: (name: string, id: string) => `Explain the workflow ${name} (${id}).`,
  diagnoseWorkflows: () => 'Which workflows are failing and why?',
  diagnoseRun: (name: string, id: string, step: string, run: string) => `Why did ${name} (${id}) fail at ${step} in run ${run}, and how do I fix it?`,
  fixRun: (name: string, id: string, step: string, run: string) => `How do I fix ${name} (${id}) after it failed at ${step} in run ${run}?`,
  suggestMappings: (system: string) => `Which fields of ${system} should map to the canonical model?`,
  whyRecommended: (system: string, why: string) => `Why is ${system} recommended? ${why}`,
  escalateCase: (id: string) => `Who should ${id} go to if I escalate it, and what do they need from me?`,
};

/** Open the one assistant in Ask mode with a question (openAsk stays as the alias for older callers). */
export const ask = (question: string): void => openAssistant({ mode: 'ask', question });
