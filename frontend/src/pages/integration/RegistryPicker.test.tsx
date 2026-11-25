// @vitest-environment jsdom
// The adapter registry picker (plan 9, P9-8.1, X-10): a Developer picks an entry by kind, names the system owner and the org
// unit, and creates a test connection. The credential is a password field, sent once and cleared.
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RegistryEntry } from '../../api/connections';

const m = vi.hoisted(() => ({
  create: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { source_id: 'workday' } })),
  toast: vi.fn(),
  draft: vi.fn(async (): Promise<unknown> => ({ ok: true, output: { run_id: 'AR-1' } })),
}));
vi.mock('../../api/agents', () => ({ startAdapterDraft: m.draft }));
const entry = (o: Partial<RegistryEntry>): RegistryEntry => ({
  id: 'workday', version: 1, kind: 'catalogue', system_type: 'hr', vendor_family: 'Workday HCM', auth_methods: ['oauth_cc'], resources: [],
  canonical_entities: [], write_actions: [], status: 'released', maintainer: 'Circularity', source_licence: null, org_unit_id: null, ...o,
}); // prettier-ignore
vi.mock('../../api/connections', () => ({
  registryEntries: () => [entry({}), entry({ id: 'generic-rest', kind: 'generic_rest', vendor_family: 'Generic REST', system_type: 'api', auth_methods: ['none', 'api_key'] })],
  createConnection: m.create,
}));
vi.mock('../../api/orgs', () => ({ useOrgUnits: () => ({ units: [{ id: 'Customer A', name: 'Customer A', depth: 0 }], can: { manage: true, report: true } }) }));
vi.mock('../../components/toast', () => ({ toast: m.toast }));

import { RegistryPicker } from './RegistryPicker';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;
const onClose = vi.fn();
beforeAll(() => { globalThis.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  m.create.mockClear();
  onClose.mockClear();
  act(() => root.render(<RegistryPicker onClose={onClose} />));
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const type = (id: string, value: string) => {
  const el = host.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>('#' + id)!;
  const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(proto, 'value')!.set!.call(el, value);
    el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }));
  });
};
const click = (el: Element) => act(() => (el as HTMLElement).click());
const create = () => [...host.querySelectorAll('button')].find((b) => b.textContent === 'Create test connection')!;

describe('RegistryPicker', () => {
  it('x-10: lists the entries of a kind, three kinds to choose from', () => {
    const tabs = [...host.querySelectorAll('[role=tab]')].map((t) => t.textContent);
    expect(tabs).toEqual(['Catalogue', 'Generic REST', 'From an API spec']);
    expect(host.textContent).toContain('Workday HCM');
    expect(host.textContent).not.toContain('Generic REST ·');
    click(host.querySelectorAll('[role=tab]')[2]);
    expect(host.textContent).toContain('No API-spec connector is released yet');
  });

  it('x-10: creating needs the owner and the org, sends them, and clears the secret', async () => {
    click(host.querySelector('input[type=radio]')!);
    expect(create().disabled).toBe(true);
    type('rgName', 'Workday test');
    type('rgOwner', 'approver');
    type('rgOrg', 'Customer A');
    type('rgSecret', 'abcdefgh');
    expect(host.querySelector<HTMLInputElement>('#rgSecret')!.type).toBe('password');
    expect(create().disabled).toBe(false);
    await act(async () => { create().click(); });
    expect(m.create).toHaveBeenCalledWith({ registryId: 'workday', version: 1, name: 'Workday test', orgUnitId: 'Customer A', systemOwner: 'approver', secret: 'abcdefgh' });
    expect(host.querySelector<HTMLInputElement>('#rgSecret')!.value).toBe('');
    expect(onClose).toHaveBeenCalled();
    expect(m.toast.mock.calls[0][0]).toContain('test environment');
  });

  it('p9-8.7: "Ask the Integration Assistant to draft it" starts a run from the pasted document', async () => {
    click(host.querySelectorAll('[role=tab]')[2]);
    const ask = () => [...host.querySelectorAll('button')].find((b) => b.textContent === 'Ask the Integration Assistant to draft it')!;
    expect(ask().disabled).toBe(true);
    type('spDoc', '{"openapi":"3.1.0"}');
    type('spName', 'Items API');
    type('spFamily', 'Items');
    expect(ask().disabled).toBe(false);
    await act(async () => { ask().click(); });
    expect(m.draft).toHaveBeenCalledWith({ name: 'Items API', systemType: 'erp', vendorFamily: 'Items', document: '{"openapi":"3.1.0"}' });
    expect(m.toast.mock.calls.at(-1)![0]).toContain('Integration Assistant is drafting Items API');
  });

  it('x-10: a Generic REST entry needs a test base URL', () => {
    click(host.querySelectorAll('[role=tab]')[1]);
    click(host.querySelector('input[type=radio]')!);
    type('rgName', 'Parts');
    type('rgOwner', 'approver');
    type('rgOrg', 'Customer A');
    expect(create().disabled).toBe(true);
    type('rgUrl', 'https://test.example.com/api');
    expect(create().disabled).toBe(false);
  });
});
