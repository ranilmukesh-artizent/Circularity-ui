import { useEffect, useRef, type ReactNode } from 'react';
import { Icon } from './Icon';

// Open overlays, newest last: Esc closes only the top one (a dialog over a drawer closes the dialog first).
const stack: { current: () => void }[] = [];
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || !stack.length) return;
  e.stopPropagation();
  stack[stack.length - 1].current();
});

function useEscape(onClose: () => void) {
  const ref = useRef(onClose);
  ref.current = onClose;
  useEffect(() => {
    stack.push(ref);
    return () => {
      const i = stack.indexOf(ref);
      if (i >= 0) stack.splice(i, 1);
    };
  }, []);
}

/** Side panel (the demo's openDrawer): same classes, so the demo's CSS applies. Render it only while open. */
export function Drawer({ title, sub, foot, wide, onClose, children }: {
  title: ReactNode; sub?: ReactNode; foot?: ReactNode; wide?: boolean; onClose: () => void; children: ReactNode;
}) {
  useEscape(onClose);
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => close.current?.focus(), []);
  return (
    <>
      <div className="scrim on" onClick={onClose} />
      <aside className={'drawer on' + (wide ? ' wide' : '')} aria-label="Details">
        <div className="dh">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2>{title}</h2>
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
  useEscape(onClose);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    (box.current?.querySelector('input,textarea,select,.btn') as HTMLElement | null)?.focus();
  }, []);
  return (
    <div className="modal on" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={box} className={'box' + (wide ? ' wide' : '')} role="dialog" aria-modal="true" aria-label={title}>
        <div className="mh">
          <h2>{title}</h2>
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
