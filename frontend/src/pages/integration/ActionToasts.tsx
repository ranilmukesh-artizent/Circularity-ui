/** A toast with an action button (the demo's toastAct), such as Undo; offered to this session's user only. */
import { useSyncExternalStore } from 'react';
import { sessionScoped } from '../../api/view';

type ActT = { id: number; msg: string; label: string; fn: () => void };
const acts = sessionScoped<ActT[]>(() => []); // an undo offered to one user is not offered to the next
let aSeq = 0;
const aSubs = new Set<() => void>();
const aEmit = () => aSubs.forEach((f) => f());
const dropAct = (t: ActT) => { acts.current = acts.current.filter((x) => x !== t); aEmit(); };
export function toastAct(msg: string, label: string, fn: () => void, ms = 8000) {
  const t = { id: ++aSeq, msg, label, fn };
  acts.current = [...acts.current, t];
  aEmit();
  window.setTimeout(() => dropAct(t), ms);
}
export function ActToasts() {
  const list = useSyncExternalStore((f) => (aSubs.add(f), () => aSubs.delete(f)), () => acts.current);
  if (!list.length) return null;
  return (
    <div className="toasts" aria-live="polite" style={{ bottom: 70 }}>
      {list.map((t) => (
        <div key={t.id} className="toast act" role="status">
          <span>{t.msg} </span>
          <button className="toastbtn" onClick={() => { dropAct(t); t.fn(); }}>
            {t.label}
          </button>
        </div>
      ))}
    </div>
  );
}
