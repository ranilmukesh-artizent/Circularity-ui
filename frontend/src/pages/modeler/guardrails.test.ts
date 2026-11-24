import { describe, expect, it } from 'vitest';
import type { FlowGuardrail, GuardrailStage, GuardrailType } from '../../api/types';
import { byStage } from './guardrails';

const g = (id: string, stage: GuardrailStage, type: GuardrailType = 'Compliance'): FlowGuardrail => ({
  id, text: id, owner: 'x', type, stage, stage_label: stage, locked: type === 'Compliance',
});

describe('guardrails grouped by stage (P9-0.11)', () => {
  it('groups in stage order and skips empty stages', () => {
    const out = byStage([g('c', 'decide'), g('a', 'condition'), g('b', 'condition'), g('d', 'execute')]);
    expect(out.map((x) => x.stage)).toEqual(['condition', 'decide', 'execute']);
    expect(out[0].items.map((x) => x.id)).toEqual(['a', 'b']);
  });
});
