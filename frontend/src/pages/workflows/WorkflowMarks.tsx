/**
 * Workflow Studio's marks: vendor logos, icon tiles, the source state chip and the workflow status pill, plus the lock
 * and grip glyphs. The logos, tiles and chips sit in a `display: contents` span, as the HTML strings they replace
 * did (step E2): the demo's CSS (`.frsys>span`, `.frrel>span`) styles direct child spans, so the wrapper keeps the
 * layout as it was.
 */
import type { CSSProperties, ReactNode } from 'react';
import { nodeMark, statusPill, vendorLogos, type Source, type WfNode } from '../../api/workflows';
import { IconTile } from '../../components/kit/IconTile';
import { StatusChip } from '../../components/kit/StatusChip';
import { StatusPill } from '../../components/kit/StatusPill';
import { VendorLogo } from '../../components/kit/VendorLogo';

const CONTENTS: CSSProperties = { display: 'contents' };
const Contents = ({ children }: { children: ReactNode }) => <span style={CONTENTS}>{children}</span>;

/** The vendor's mark: its logo when the app has one and logos are on, else its initials (vlogo). */
export const SourceMark = ({ s }: { s: Pick<Source, 'vendor'> }) => <Contents><VendorLogo vendor={s.vendor} logos={vendorLogos()} /></Contents>;
/** A small tinted icon tile (frIt … 'sm'). */
export const TileMark = ({ ic, h }: { ic: string; h: string }) => <Contents><IconTile ic={ic} h={h} cls="sm" /></Contents>;
/** A step's mark on the canvas (frNodeIcon). */
export function NodeMark({ n }: { n: WfNode }) {
  const m = nodeMark(n);
  return 'source' in m ? <SourceMark s={m.source} /> : <TileMark ic={m.ic} h={m.h} />;
}
/** A source's connection state (stChip); the wrapper stays when there is no chip. */
export const StateChip = ({ s }: { s: string }) => <Contents><StatusChip s={s} /></Contents>;

/** A workflow, run or source status (frSt) from the demo's FR_ST table; `t` replaces the label. */
export function WorkflowStatus({ k, t }: { k: string; t?: string }) {
  const [label, tone] = statusPill(k);
  return <StatusPill tone={tone} label={t ?? label} />;
}

export const LOCK_SVG = (
  <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" />
  </svg>
);
export const GRIP_SVG = (
  <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor" aria-hidden="true">
    <circle cx="9" cy="6" r="1.7" /><circle cx="15" cy="6" r="1.7" /><circle cx="9" cy="12" r="1.7" /><circle cx="15" cy="12" r="1.7" /><circle cx="9" cy="18" r="1.7" /><circle cx="15" cy="18" r="1.7" />
  </svg>
);
