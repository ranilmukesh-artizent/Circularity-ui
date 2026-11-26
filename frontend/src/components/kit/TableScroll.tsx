/**
 * A table that scrolls sideways inside its card, with a visible cue: a soft shadow on each edge that still has
 * hidden columns, and a sticky first column (see tables.css). Wraps the demo's `.tw` scroller; presentation only.
 */
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import './tables.css';

export function TableScroll({ children, style, sticky = true, label = 'Table' }: { children: ReactNode; style?: CSSProperties; sticky?: boolean; label?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [edge, setEdge] = useState({ left: false, right: false });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const left = el.scrollLeft > 1, right = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
      setEdge((p) => (p.left === left && p.right === right ? p : { left, right }));
    };
    measure();
    el.addEventListener('scroll', measure, { passive: true });
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    ro?.observe(el);
    if (el.firstElementChild) ro?.observe(el.firstElementChild);
    return () => { el.removeEventListener('scroll', measure); ro?.disconnect(); };
  }, []);

  const scrolls = edge.left || edge.right;
  return (
    <div className="twc" data-left={edge.left} data-right={edge.right}>
      <div className={'tw' + (sticky ? ' tw-sticky' : '')} ref={ref} style={style} tabIndex={scrolls ? 0 : undefined}
        role={scrolls ? 'region' : undefined} aria-label={scrolls ? label + ', scrolls sideways' : undefined}>
        {children}
      </div>
    </div>
  );
}
