import { useSyncExternalStore } from 'react';

type Toast = { id: number; msg: string };
let items: Toast[] = [];
let seq = 0;
const subs = new Set<() => void>();
const emit = () => subs.forEach((s) => s());

/** Show a short status message (the demo's toast()). */
export function toast(msg: string, ms = 3200) {
  const t = { id: ++seq, msg };
  items = [...items, t];
  emit();
  window.setTimeout(() => {
    items = items.filter((x) => x !== t);
    emit();
  }, ms);
}

export function Toasts() {
  const list = useSyncExternalStore(
    (f) => (subs.add(f), () => subs.delete(f)),
    () => items,
  );
  return (
    <div className="toasts" aria-live="polite">
      {list.map((t) => (
        <div key={t.id} className="toast" role="status">
          {t.msg}
        </div>
      ))}
    </div>
  );
}
