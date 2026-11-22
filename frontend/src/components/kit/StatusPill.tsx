/** Status pill (the demo's frSt): a dot and a label in a tone (ok, info, warn, bad, line). */
import type { ReactNode } from 'react';

/** Status keys to [label, tone], as the demo's FR_ST tables. */
export type StatusTable = Record<string, readonly [string, string]>;

export function StatusPill({ tone, label }: { tone: string; label: ReactNode }) {
  return (
    <span className={'frst ' + tone}>
      <i />
      {label}
    </span>
  );
}

/** The pill for status key `k` in `table`; an unknown key shows itself in the line tone, and `t` replaces the label. */
export function KeyedStatus({ k, t, table }: { k: string; t?: string | null; table: StatusTable }) {
  const [label, tone] = table[k] ?? [k, 'line'];
  return <StatusPill tone={tone} label={t || label} />;
}
