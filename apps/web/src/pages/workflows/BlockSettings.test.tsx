// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { BlockSpec, FieldSpec } from '../../api/workflows';
import { fieldErrors } from '../../api/workflowGraph';
import { BlockSettings } from './BlockSettings';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const F = (key: string, label: string, type: FieldSpec['type'], dflt: unknown, more: Partial<FieldSpec> = {}): FieldSpec => ({
  key, label, type, default: dflt, required: false, choices: null, help: '', min: null, max: null, source: null, ...more,
});
const ALL: BlockSpec = {
  ref: 'x_test', readonly: false, fields: [
    F('topic', 'Topic', 'text', 'model.updated', { required: true }),
    F('timeout_s', 'Timeout (s)', 'number', 30, { min: 1, max: 600 }),
    F('currency', 'Target currency', 'select', 'USD', { required: true, choices: ['USD', 'EUR', 'INR'] }),
    F('resources', 'Resources', 'multi', [], { source: 'resources' }),
    F('checksum', 'Checksum required', 'bool', true),
    F('keys', 'Key fields', 'fields', []),
    F('rules', 'Rules', 'rules', []),
    F('units', 'Field units', 'mapping', {}, { choices: ['W', 'kW'] }),
  ],
};
const cfg0 = Object.fromEntries(ALL.fields.map((f) => [f.key, f.default]));
const errors = (f: FieldSpec, v: unknown) => fieldErrors(f, v);

function render(spec: BlockSpec | null, cfg: Record<string, unknown>, onChange = vi.fn(), readonly = false) {
  act(() => root.render(<BlockSettings nodeId="n1" spec={spec} cfg={cfg} readonly={readonly} errors={errors} resources={['opps', 'accounts']} onChange={onChange} />));
  return onChange;
}
const el = <T extends Element = HTMLInputElement>(sel: string) => host.querySelector(sel) as unknown as T;
function type(input: HTMLInputElement, value: string) {
  act(() => {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
    set.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  act(() => { input.dispatchEvent(new FocusEvent('focusout', { bubbles: true })); });
}

describe('BlockSettings', () => {
  it('renders a control for each field type from the spec', () => {
    render(ALL, cfg0);
    expect(el('#cfg-n1-topic').value).toBe('model.updated');
    expect(el('#cfg-n1-timeout_s').type).toBe('number');
    expect(el<HTMLSelectElement>('#cfg-n1-currency').value).toBe('USD');
    expect([...el<HTMLSelectElement>('#cfg-n1-currency').options].map((o) => o.value)).toEqual(['USD', 'EUR', 'INR']);
    expect(host.querySelectorAll('#cfg-n1-resources input[type=checkbox]').length).toBe(2);
    expect(el('#cfg-n1-checksum').checked).toBe(true);
    expect(el('#cfg-n1-keys').value).toBe('');
    expect(el('#cfg-n1-rules').textContent).toContain('No rules.');
    expect(el('#cfg-n1-units').textContent).toContain('None.');
    expect(host.querySelectorAll('[role=alert]').length).toBe(0); // the defaults pass
  });

  it('shows a required field left empty as an error in place', () => {
    render(ALL, { ...cfg0, topic: '' });
    const alerts = [...host.querySelectorAll('[role=alert]')].map((x) => x.textContent);
    expect(alerts).toEqual(['Topic is needed.']);
    expect(el('#cfg-n1-topic').closest('.wfcfgf')!.textContent).toContain('Topic is needed.');
  });

  it('sends each edit to onChange with the value the setting takes', () => {
    const on = render(ALL, cfg0);
    act(() => {
      const s = el<HTMLSelectElement>('#cfg-n1-currency');
      s.value = 'EUR';
      s.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(on).toHaveBeenLastCalledWith('currency', 'EUR');
    type(el('#cfg-n1-timeout_s'), '45');
    expect(on).toHaveBeenLastCalledWith('timeout_s', 45);
    type(el('#cfg-n1-keys'), 'opportunity_id, account_id');
    expect(on).toHaveBeenLastCalledWith('keys', ['opportunity_id', 'account_id']);
    act(() => el('#cfg-n1-checksum').click());
    expect(on).toHaveBeenLastCalledWith('checksum', false);
    act(() => (host.querySelector('#cfg-n1-resources input') as HTMLInputElement).click());
    expect(on).toHaveBeenLastCalledWith('resources', ['opps']);
    act(() => [...host.querySelectorAll('#cfg-n1-rules button')].find((b) => b.textContent === '+ Add rule')!.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(on).toHaveBeenLastCalledWith('rules', [{ field: '', check: 'present' }]);
  });

  it('shows a rule left without a field as an error', () => {
    render(ALL, { ...cfg0, rules: [{ field: '', check: 'present' }] });
    expect([...host.querySelectorAll('[role=alert]')].map((x) => x.textContent)).toEqual(['Rules rule 1 has no field.']);
  });

  it('shows the settings of a read-only block without letting them change', () => {
    render({ ...ALL, readonly: true }, cfg0);
    expect(el('#cfg-n1-topic').disabled).toBe(true);
    expect(el<HTMLSelectElement>('#cfg-n1-currency').disabled).toBe(true);
    expect([...host.querySelectorAll('button')].length).toBe(0);
  });

  it('says a fixed step has no settings', () => {
    render({ ref: 'fixed', readonly: true, fields: [] }, {});
    expect(host.textContent).toContain('This step has no settings');
  });
});
