import { useEffect, useId, useRef, useState, type ReactNode, type RefObject } from 'react';
import { Icon } from './Icon';

// Open overlays, newest last. Esc closes only the top one (a dialog over a drawer closes the dialog first; the Ask
// panel opened over a dialog closes before the dialog), and Tab stays inside the top one when it is a dialog.
interface Entry { close: { current: () => void }; box?: RefObject<HTMLElement | null> }
const stack: Entry[] = [];
document.addEventListener('keydown', (e) => {
  const top = stack[stack.length - 1];
  if (!top) return;
  if (e.key === 'Escape') {
    e.stopPropagation();
    top.close.current();
  } else if (e.key === 'Tab' && top.box?.current) {
    trapTab(e, top.box.current);
  }
});

const FOCUSABLE =
  'a[href], area[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, iframe, [contenteditable="true"], [tabindex]';

/** The controls Tab reaches inside box, in order (drawn, enabled, not taken out of the tab order). */
function tabbables(box: HTMLElement): HTMLElement[] {
  return [...box.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (el) => el.tabIndex >= 0 && !el.closest('[hidden], [inert]') && el.getClientRects().length > 0,
  );
}

/** Tab past the last control goes to the first, Shift+Tab before the first to the last; focus outside comes back in. */
function trapTab(e: KeyboardEvent, box: HTMLElement) {
  const list = tabbables(box);
  if (!list.length) return void e.preventDefault();
  const first = list[0], last = list[list.length - 1], at = document.activeElement;
  let to: HTMLElement | null = null;
  if (!at || !box.contains(at)) to = e.shiftKey ? last : first;
  else if (e.shiftKey && (at === first || at === box)) to = last;
  else if (!e.shiftKey && at === last) to = first;
  if (to) {
    e.preventDefault();
    to.focus();
  }
}

/**
 * Put an overlay on the Escape stack while `active`: Esc calls onClose when it is the newest one. With `box` (a
 * dialog), Tab is kept inside box and, when the overlay goes away, focus goes back to what had it when it opened.
 */
export function useOverlay(onClose: () => void, box?: RefObject<HTMLElement | null>, active = true) {
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });
  // what had focus when the overlay first rendered: read before the dialog's own controls take focus
  const [opener] = useState(() => document.activeElement);
  useEffect(() => {
    if (!active) return;
    const entry: Entry = { close, box };
    stack.push(entry);
    return () => {
      const i = stack.indexOf(entry);
      if (i >= 0) stack.splice(i, 1);
      if (box && opener instanceof HTMLElement && opener.isConnected) opener.focus({ preventScroll: true });
    };
  }, [active, box, opener]);
}

/** Side panel (the demo's openDrawer): same classes, so the demo's CSS applies. Render it only while open. */
export function Drawer({ title, sub, foot, wide, onClose, children }: {
  title: ReactNode; sub?: ReactNode; foot?: ReactNode; wide?: boolean; onClose: () => void; children: ReactNode;
}) {
  const box = useRef<HTMLElement>(null);
  useOverlay(onClose, box);
  const close = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  useEffect(() => close.current?.focus(), []);
  return (
    <>
      <div className="scrim on" aria-hidden="true" onClick={onClose} />
      <aside ref={box} className={'drawer on' + (wide ? ' wide' : '')} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="dh">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id={titleId}>{title}</h2>
            {sub && <div className="note">{sub}</div>}
          </div>
          <button ref={close} className="iconbtn" aria-label="Close panel" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <div className="db">{children}</div>
        {foot && <div className="df">{foot}</div>}
      </aside>
    </>
  );
}

/** Dialog (the demo's openModal). Render it only while open. */
export function Modal({ title, foot, wide, onClose, children }: {
  title: string; foot?: ReactNode; wide?: boolean; onClose: () => void; children: ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  useOverlay(onClose, box);
  const titleId = useId();
  useEffect(() => {
    (box.current?.querySelector('input,textarea,select,.btn') as HTMLElement | null)?.focus();
  }, []);
  return (
    // the backdrop closes the dialog on a click; the keyboard closes it with Esc (the overlay stack)
    <div className="modal on" role="presentation" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={box} className={'box' + (wide ? ' wide' : '')} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="mh">
          <h2 id={titleId}>{title}</h2>
          <button className="iconbtn" aria-label="Close" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <div className="mb">{children}</div>
        {foot && <div className="mf">{foot}</div>}
      </div>
    </div>
  );
}
