/** Tinted icon tile (the demo's frIt): an icon on the hue `h` (`--c: var(--h-<h>)`, neutral when none). */
import type { CSSProperties } from 'react';
import { Icon } from '../Icon';

export function IconTile({ ic, h, cls }: { ic: string; h?: string; cls?: string }) {
  return (
    <span className={'frit ' + (cls || '')} style={{ '--c': `var(--h-${h || 'neutral'})` } as CSSProperties}>
      <Icon name={ic} />
    </span>
  );
}
