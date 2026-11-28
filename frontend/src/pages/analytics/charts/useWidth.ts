/** The width an SVG chart should draw at, so its text keeps one real size at every width (it scrolls inside its frame below `min`). */
import { useEffect, useRef, useState } from 'react';

export function useWidth(min: number, fallback = 900) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([e]) => setW(Math.floor(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, width: Math.max(min, w) };
}
