/** The ⋯ menu of a source row (the demo's frSrcMenu); read-only roles see a View button. */
import { useEffect, useRef, useState } from 'react';
import type { Source } from '../../api/integration';
import { Icon } from '../../components/Icon';
import { canMgr, useInt } from './FabricContext';

export function SourceMenu({ s }: { s: Source }) {
  const ui = useInt();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!open) return;
    const f = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('click', f);
    return () => document.removeEventListener('click', f);
  }, [open]);
  if (!canMgr()) return <button className="btn sm" onClick={() => ui.openSource(s.id, 'ov')}>View</button>;
  const item = (ic: string, l: string, f: () => void, dis?: boolean) => (
    <button role="menuitem" disabled={dis} onClick={() => { setOpen(false); f(); }}>
      <Icon name={ic} />
      <span>{l}</span>
    </button>
  );
  return (
    <details ref={ref} className="frmenu" open={open}>
      <summary className="iconbtn sm" aria-label={'Actions for ' + s.vendor} onClick={(e) => { e.preventDefault(); setOpen((o) => !o); }}>
        <Icon name="more" />
      </summary>
      <div className="frdd" role="menu">
        {item('eye', 'Open', () => ui.openSource(s.id, 'ov'))}
        {s.status === 'unavailable' ? (
          item('unplug', s.disconnected ? 'Reconnect' : 'Connect', () => ui.reconnect(s.id))
        ) : (
          <>
            {item('sync', 'Sync now', () => ui.sync(s.id), !!(s.syncing || s.paused || s.status === 'manual'))}
            {item(s.paused ? 'play' : 'pause', s.paused ? 'Resume' : 'Pause', () => ui.pause(s.id))}
            {item('unplug', 'Disconnect', () => ui.disconnect(s.id))}
          </>
        )}
      </div>
    </details>
  );
}
