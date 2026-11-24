import type { FlowGuardrail, GuardrailStage } from '../../api/types';

/** The seven decision stages in order (mirrors backend `services/modeler/stages.py`). */
export const STAGE_ORDER: GuardrailStage[] = ['receive', 'match', 'condition', 'value', 'decide', 'execute', 'close'];

export interface StageGroup {
  stage: GuardrailStage;
  label: string;
  items: FlowGuardrail[];
}

/** Guardrails grouped by stage, in stage order; stages without a guardrail are left out. */
export function byStage(guardrails: FlowGuardrail[]): StageGroup[] {
  return STAGE_ORDER.flatMap((stage) => {
    const items = guardrails.filter((g) => g.stage === stage);
    return items.length ? [{ stage, label: items[0].stage_label, items }] : [];
  });
}
