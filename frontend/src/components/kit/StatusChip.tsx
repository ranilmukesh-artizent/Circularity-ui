/** A source's connection state as a chip (the demo's stChip); nothing for other states. */
const ST_CHIP: Record<string, [string, string]> = { live: ['ok', 'Live'], manual: ['dk', 'Manual import'], unavailable: ['bad', 'Unavailable'], stale: ['warn', 'Stale'] };

export function StatusChip({ s }: { s: string }) {
  const c = ST_CHIP[s];
  return c ? <span className={'chip ' + c[0]}>{c[1]}</span> : null;
}
