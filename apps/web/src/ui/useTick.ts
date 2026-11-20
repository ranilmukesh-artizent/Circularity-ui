import { useEffect, useState } from 'react';

/** Re-render every `ms` while the page is open (live ages, and runs that finish in the backend). */
export function useTick(ms = 1000): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setN((x) => x + 1), ms);
    return () => window.clearInterval(t);
  }, [ms]);
  return n;
}
