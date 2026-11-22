// @vitest-environment jsdom
import { act, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { Drawer, Modal, useOverlay } from './Overlay';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let host: HTMLDivElement, root: Root;

beforeAll(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  // jsdom has no layout: every element reports no boxes, so the trap would see nothing to focus. Pretend all are drawn.
  vi.spyOn(Element.prototype, 'getClientRects').mockImplementation(() => [{}] as unknown as DOMRectList);
});
beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const render = (ui: React.ReactNode) => act(() => root.render(ui));
const press = (key: string, shiftKey = false) =>
  act(() => {
    (document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent('keydown', { key, shiftKey, bubbles: true, cancelable: true }));
  });
const active = () => document.activeElement as HTMLElement;

/** A page with an opener button; the overlay opens on click and closes through onClose. */
function Page({ kind, onClose }: { kind: 'modal' | 'drawer'; onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  const close = () => { onClose?.(); setOpen(false); };
  const body = (
    <>
      <input aria-label="Reason" />
      <button className="btn">Middle</button>
    </>
  );
  const foot = <button className="btn pri">Approve</button>;
  return (
    <>
      <button id="opener" onClick={() => setOpen(true)}>Open</button>
      <button id="after">After</button>
      {open && (kind === 'modal'
        ? <Modal title="Approve RT-1048" foot={foot} onClose={close}>{body}</Modal>
        : <Drawer title="RT-1048" foot={foot} onClose={close}>{body}</Drawer>)}
    </>
  );
}

function openFrom(kind: 'modal' | 'drawer', onClose?: () => void) {
  render(<Page kind={kind} onClose={onClose} />);
  const opener = document.getElementById('opener') as HTMLButtonElement;
  opener.focus();
  act(() => opener.click());
  return opener;
}

describe.each(['modal', 'drawer'] as const)('%s', (kind) => {
  it('is a labelled modal dialog', () => {
    openFrom(kind);
    const dlg = document.querySelector('[role="dialog"]')!;
    expect(dlg).not.toBeNull();
    expect(dlg.getAttribute('aria-modal')).toBe('true');
    const label = document.getElementById(dlg.getAttribute('aria-labelledby')!);
    expect(label?.textContent).toBe(kind === 'modal' ? 'Approve RT-1048' : 'RT-1048');
    expect(dlg.contains(active())).toBe(true); // focus moved inside on open
  });

  it('keeps Tab inside: past the last control back to the first, and Shift+Tab the other way', () => {
    openFrom(kind);
    const dlg = document.querySelector('[role="dialog"]') as HTMLElement;
    const inside = [...dlg.querySelectorAll<HTMLElement>('button, input')];
    const first = inside[0], last = inside[inside.length - 1];
    last.focus();
    press('Tab');
    expect(active()).toBe(first);
    press('Tab', true);
    expect(active()).toBe(last);
    // focus that got out (a click behind the dialog) comes back in on the next Tab
    (document.getElementById('after') as HTMLElement).focus();
    press('Tab');
    expect(dlg.contains(active())).toBe(true);
  });

  it('closes on Escape and gives focus back to the control that opened it', () => {
    const onClose = vi.fn();
    const opener = openFrom(kind, onClose);
    expect(active()).not.toBe(opener);
    press('Escape');
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(active()).toBe(opener);
  });
});

describe('the Escape stack', () => {
  /** Something else that closes on Escape (the Ask panel), open or not. */
  function Panel({ open, onClose }: { open: boolean; onClose: () => void }) {
    useOverlay(onClose, undefined, open);
    return null;
  }

  it('closes only the newest overlay: a panel opened over a dialog closes first', () => {
    const closeDialog = vi.fn(), closePanel = vi.fn();
    render(
      <>
        <Modal title="Dialog" onClose={closeDialog}><button>x</button></Modal>
        <Panel open onClose={closePanel} />
      </>,
    );
    press('Escape');
    expect(closePanel).toHaveBeenCalledTimes(1);
    expect(closeDialog).not.toHaveBeenCalled();
  });

  it('a closed panel takes no Escape away from the dialog under it', () => {
    const closeDialog = vi.fn(), closePanel = vi.fn();
    render(
      <>
        <Modal title="Dialog" onClose={closeDialog}><button>x</button></Modal>
        <Panel open={false} onClose={closePanel} />
      </>,
    );
    press('Escape');
    expect(closeDialog).toHaveBeenCalledTimes(1);
    expect(closePanel).not.toHaveBeenCalled();
  });
});
