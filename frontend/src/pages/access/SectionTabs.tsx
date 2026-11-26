import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { navigation } from '../../api/nav';
import '../../components/kit/tables.css';

/** The sections of a page the account may see (the demo's navKids), and the one the route asks for (secKey). */
export function sectionsOf(page: string, a: string | null) {
  const g = navigation().find((x) => x.id === page);
  const kids = g?.kids ?? [];
  const key = kids.some((k) => k.id === a) ? (a as string) : kids[0]?.id ?? '';
  return { label: g?.label ?? page, kids, key };
}

/**
 * One section per route, with a tab strip under the page head (the demo's secPage for MCP & Tools and Access). When the
 * strip is wider than the window it scrolls, shows a fade on the edge that hides tabs and keeps the open tab in view.
 */
export function SectionTabs({ page, a }: { page: string; a: string | null }) {
  const nav = useNavigate();
  const { label, kids, key } = sectionsOf(page, a);
  const ref = useRef<HTMLDivElement>(null);
  const [edge, setEdge] = useState({ left: false, right: false });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const left = el.scrollLeft > 1, right = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
      setEdge((p) => (p.left === left && p.right === right ? p : { left, right }));
    };
    el.querySelector<HTMLElement>('[aria-selected=true]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    measure();
    el.addEventListener('scroll', measure, { passive: true });
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    ro?.observe(el);
    return () => { el.removeEventListener('scroll', measure); ro?.disconnect(); };
  }, [key, kids.length]);

  return (
    <div className="twc tabsc" data-left={edge.left} data-right={edge.right}>
      <div className="tabs" role="tablist" aria-label={label + ' sections'} ref={ref}>
        {kids.map((k) => (
          <button key={k.id} role="tab" aria-selected={k.id === key} onClick={() => nav('/' + page + '/' + k.id)}>
            {k.label}
          </button>
        ))}
      </div>
    </div>
  );
}
