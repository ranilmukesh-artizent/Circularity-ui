/**
 * One tab stop for a chart with many marks: Tab enters the chart, the arrow keys move between its marks (Home and End jump),
 * Enter or Space opens the mark (each mark is a button). Marks carry data-mark; a grid also carries data-row and data-col,
 * and then Up and Down stay in the column.
 */
import { useCallback, useRef, useState } from 'react';

function onKey(ev: Event) {
  const e = ev as KeyboardEvent;
  const root = e.currentTarget as Element;
  const marks = [...root.querySelectorAll<HTMLElement>('[data-mark]')];
  const i = marks.indexOf(document.activeElement as HTMLElement);
  if (i < 0) return;
  const at = marks[i], grid = at.dataset.row !== undefined;
  let to = -1;
  const along = (axis: 'row' | 'col', step: 1 | -1) => {
    // the nearest mark in the same row (or column) in that direction
    const same = axis === 'row' ? 'row' : 'col', move = axis === 'row' ? 'col' : 'row';
    const mine = Number(at.dataset[move]);
    const list = marks
      .map((m, k) => ({ k, m }))
      .filter(({ m }) => m.dataset[same] === at.dataset[same] && (Number(m.dataset[move]) - mine) * step > 0)
      .sort((a, b) => (Number(a.m.dataset[move]) - Number(b.m.dataset[move])) * step);
    return list[0]?.k ?? -1;
  };
  switch (e.key) {
    case 'ArrowRight': to = grid ? along('row', 1) : i + 1; break;
    case 'ArrowLeft': to = grid ? along('row', -1) : i - 1; break;
    case 'ArrowDown': to = grid ? along('col', 1) : i + 1; break;
    case 'ArrowUp': to = grid ? along('col', -1) : i - 1; break;
    case 'Home': to = 0; break;
    case 'End': to = marks.length - 1; break;
    default: return;
  }
  e.preventDefault();
  if (to >= 0 && to < marks.length) marks[to].focus();
}

export function useRoving() {
  const [cur, setCur] = useState(0);
  const off = useRef<(() => void) | null>(null);
  /** put on the element that holds the marks (a callback ref, so it works when the chart appears later) */
  const ref = useCallback((el: Element | null) => {
    off.current?.();
    off.current = null;
    if (el) {
      el.addEventListener('keydown', onKey);
      off.current = () => el.removeEventListener('keydown', onKey);
    }
  }, []);
  /** props for the n-th mark: only the current one is in the tab order */
  const mark = (n: number) => ({ 'data-mark': '', tabIndex: n === cur ? 0 : -1, onFocus: () => setCur(n) });
  return { ref, mark };
}
