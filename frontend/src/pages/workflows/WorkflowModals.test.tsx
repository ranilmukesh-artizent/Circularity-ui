// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { RedirectNote } from './WorkflowBuilder';
import { TypePicker } from './WorkflowModals';

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

describe('Workflow Studio points decisions to the Modeler (P9-0.16)', () => {
  it('decision type shows demo read only', () => {
    act(() => root.render(<TypePicker type="ingest" onChange={() => {}} />));
    const dec = host.querySelector<HTMLOptionElement>('option[value="dec"]')!;
    expect(dec.textContent).toContain('Decision workflow (demo, read only)');
    expect(dec.disabled).toBe(true);
    const note = host.querySelector('[data-testid="nwDecNote"]')!;
    expect(note.textContent).toContain('Business rules live in the Modeler');
    expect(note.querySelector('a')?.getAttribute('href')).toBe('#/modeler');
    expect(host.querySelector('option[value="ingest"]')?.hasAttribute('disabled')).toBe(false);
  });

  it('redirect shows Modeler link', () => {
    act(() => root.render(<RedirectNote reason="Decisions live in the Modeler." />));
    const box = host.querySelector('[data-testid="wbRedirect"]')!;
    expect(box.textContent).toContain('Decisions live in the Modeler.');
    const a = box.querySelector('a')!;
    expect(a.textContent).toContain('Open the Modeler');
    expect(a.getAttribute('href')).toBe('#/modeler');
  });
});
