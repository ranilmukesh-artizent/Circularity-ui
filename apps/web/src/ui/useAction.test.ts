// @vitest-environment jsdom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ActionResult } from '../api/types';
import { refused, useAction, type Action } from './useAction';

const toast = vi.hoisted(() => vi.fn());
vi.mock('./toast', () => ({ toast }));

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const ok: ActionResult<{ id: string }> = { ok: true, output: { id: 'x' }, key: null, action: 'a.b' };
const no = (code: Extract<ActionResult, { ok: false }>['error']['code'], message: string): ActionResult<{ id: string }> => ({ ok: false, error: { code, message } });

beforeEach(() => toast.mockClear());

describe('refused', () => {
  it('passes a success through without a toast', () => {
    expect(refused(ok)).toBe(false);
    expect(toast).not.toHaveBeenCalled();
  });
  it("shows the server's message as it is, for the given time", () => {
    expect(refused(no('out_of_scope', 'Only an Approver can approve.'), 4200)).toBe(true);
    expect(toast).toHaveBeenCalledWith('Only an Approver can approve.', 4200);
    refused(no('conflict', 'Busy.'));
    expect(toast).toHaveBeenLastCalledWith('Busy.', undefined); // the toast's own default (3200)
  });
  it('sends validation errors to the form when asked, other refusals still toast', () => {
    const inline = vi.fn();
    refused(no('validation_error', 'Enter a reason.'), { inline, ms: 4200 });
    expect(inline).toHaveBeenCalledWith('Enter a reason.');
    expect(toast).not.toHaveBeenCalled();
    refused(no('tenant_boundary', 'Not your tenant.'), { inline, ms: 4200 });
    expect(toast).toHaveBeenCalledWith('Not your tenant.', 4200);
  });
  it('sends every refusal to `all`, with its code, and keeps silent codes quiet', () => {
    const all = vi.fn();
    refused(no('conflict', 'No changes.'), { all });
    expect(all).toHaveBeenCalledWith('No changes.', 'conflict');
    expect(refused(no('duplicate', 'Already sent.'), { silent: ['duplicate'] })).toBe(true);
    expect(toast).not.toHaveBeenCalled();
  });
});

describe('useAction', () => {
  let host: HTMLDivElement, root: Root, a: Action;
  const seen: boolean[] = [];
  function Probe() {
    a = useAction();
    seen.push(a.pending);
    return null;
  }
  beforeAll(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  });
  beforeEach(() => {
    seen.length = 0;
    host = document.createElement('div');
    root = createRoot(host);
    act(() => root.render(createElement(Probe)));
  });
  afterEach(() => act(() => root.unmount()));

  it('is pending while the action runs, and returns its result', async () => {
    let finish!: (r: ActionResult<{ id: string }>) => void;
    let p!: Promise<ActionResult<{ id: string }>>;
    act(() => {
      p = a.run(() => new Promise((res) => (finish = res)));
    });
    expect(a.pending).toBe(true);
    await act(async () => {
      finish(ok);
      await p;
    });
    expect(a.pending).toBe(false);
    expect(await p).toBe(ok);
    expect(toast).not.toHaveBeenCalled();
  });

  it('shows a refusal and returns it', async () => {
    let r!: ActionResult<{ id: string }>;
    await act(async () => {
      r = await a.run(() => Promise.resolve(no('approval_required', 'Above your limit.')), 4200);
    });
    expect(r.ok).toBe(false);
    expect(toast).toHaveBeenCalledWith('Above your limit.', 4200);
    expect(a.pending).toBe(false);
  });

  it('stays pending until the last of two overlapping runs ends', async () => {
    const done: ((r: ActionResult<{ id: string }>) => void)[] = [];
    const ps: Promise<unknown>[] = [];
    act(() => {
      ps.push(a.run(() => new Promise((res) => done.push(res))));
      ps.push(a.run(() => new Promise((res) => done.push(res))));
    });
    await act(async () => {
      done[0](ok);
      await ps[0];
    });
    expect(a.pending).toBe(true);
    await act(async () => {
      done[1](ok);
      await ps[1];
    });
    expect(a.pending).toBe(false);
  });

  it('ends pending when the call throws', async () => {
    await act(async () => {
      await a.run(() => Promise.reject(new Error('boom'))).catch(() => undefined);
    });
    expect(a.pending).toBe(false);
  });
});
