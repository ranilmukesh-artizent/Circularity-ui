import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({ invoke: vi.fn(async () => ({ ok: true, output: {}, key: null, action: 'x' })) }));
vi.mock('./actions', () => ({ invoke: m.invoke }));

import { connectFromCatalog, disconnectSource, pauseSource, resumeSource, sandboxKey, suggestMappings, testConnection, testDraft, type Draft } from './integration';

beforeEach(() => m.invoke.mockClear());
const call = () => m.invoke.mock.calls[0] as unknown as [string, Record<string, unknown>];

describe('source lifecycle actions', () => {
  it('pause, resume and disconnect go to their server actions', async () => {
    await pauseSource('erp');
    expect(call()).toEqual(['source.pause', { source_id: 'erp' }]);
    m.invoke.mockClear();
    await resumeSource('erp');
    expect(call()).toEqual(['source.resume', { source_id: 'erp' }]);
    m.invoke.mockClear();
    await disconnectSource('erp', 'SAP S/4HANA');
    expect(call()).toEqual(['source.disconnect', { source_id: 'erp', confirm: 'SAP S/4HANA' }]);
  });

  it('the connection test is the server read source.test', async () => {
    await testConnection({ source_id: 'cat:workday', auth: 'OAuth 2.0' });
    expect(call()).toEqual(['source.test', { source_id: 'cat:workday', auth: 'OAuth 2.0' }]);
  });

  it("the drawer's test sends the draft's endpoint (buildUrl) and its operation counts, not its settings", async () => {
    const d: Draft = {
      type: 'erp', name: 'ERP', vendor: 'SAP S/4HANA', ver: '', env: 'Production', url: '', method: 'jdbc',
      cfg: { driver: 'Oracle DB', host: 'db1', port: 1521, database: 'ORCL' }, interval: 15, auth: 'Basic', owner: '',
    };
    await testDraft('erp', d, { read: ['SELECT * FROM a', ' '], write: [] });
    expect(call()).toEqual(['source.test', { source_id: 'erp', draft: { method: 'jdbc', url: 'jdbc:oracledb://db1:1521/ORCL', auth: 'Basic', read: 1, write: 0 } }]);
  });

  it('Suggest mappings is the server read mapping.catalogSuggest for the catalogue system', async () => {
    await suggestMappings('postgres');
    expect(call()).toEqual(['mapping.catalogSuggest', { catalog_id: 'postgres' }]);
  });

  it('connecting from the catalogue is source.update in catalog mode with the accepted rows', async () => {
    const rows: [string, string, string, string, number][] = [['A.B', '1', 'asset.asset_id', '1', 97]];
    await connectFromCatalog('workday', 'oauth', ['read'], rows);
    expect(call()).toEqual(['source.update', { mode: 'catalog', id: '', d: { catalog: 'workday', auth: 'oauth', scopes: ['read'] }, maps: rows, ops: {} }]);
  });

  it('the key typed in the Connect dialog is sent, to the test and to the connection', async () => {
    await connectFromCatalog('postgres', 'key', ['read'], [], 'typed-key-0001');
    expect(call()).toEqual(['source.update', { mode: 'catalog', id: '', d: { catalog: 'postgres', auth: 'key', scopes: ['read'] }, maps: [], ops: {}, secret: 'typed-key-0001' }]);
    m.invoke.mockClear();
    await testConnection({ source_id: 'cat:postgres', auth: 'API key', secret: 'typed-key-0001' });
    expect(call()).toEqual(['source.test', { source_id: 'cat:postgres', auth: 'API key', secret: 'typed-key-0001' }]);
  });

  it('the sandbox key is the server read source.sandboxKey', async () => {
    await sandboxKey('postgres');
    expect(call()).toEqual(['source.sandboxKey', { catalog_id: 'postgres' }]);
  });
});
