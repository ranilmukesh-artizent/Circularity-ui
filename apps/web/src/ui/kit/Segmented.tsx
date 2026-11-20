/** Pill tabs (the demo's frSeg) with roving focus: ← and → move to the previous or next tab and pick it. */
import { useRef, type KeyboardEvent } from 'react';
import { Icon } from '../Icon';

export function Segmented<T extends string>({ name, items, cur, onPick, label }: {
  /** data-seg; left out when undefined */
  name?: string;
  /** [id, label, icon?] */
  items: readonly (readonly [T, string, string?])[];
  cur: T;
  onPick: (id: T) => void;
  /** aria-label (the name when none) */
  label?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const key = (e: KeyboardEvent, i: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const n = (i + (e.key === 'ArrowRight' ? 1 : items.length - 1)) % items.length;
    (ref.current?.querySelectorAll('[role=tab]')[n] as HTMLElement | undefined)?.focus();
    onPick(items[n][0]);
  };
  return (
    <div ref={ref} className="frseg" role="tablist" aria-label={label || name} data-seg={name}>
      {items.map((x, i) => (
        <button key={x[0]} role="tab" aria-selected={x[0] === cur} tabIndex={x[0] === cur ? 0 : -1} onClick={() => onPick(x[0])} onKeyDown={(e) => key(e, i)}>
          {x[2] && <Icon name={x[2]} />}
          {x[1]}
        </button>
      ))}
    </div>
  );
}
