/** The Device tab of a received-device case (P9-6.4, DV-01): IMEI, model and storage, grade and quote, partner, batch, received
 * date and, for a bulk lot, the device lines. Starts stage 5 of a device case (tabs/index.tsx). */
import { deviceView } from '../../../api/device';
import { fmtDateYear } from '../../../api/format';
import { Kv } from '../CaseBlocks';
import { deviceLine, gradeLine, lotLines, refLine } from '../device';
import type { TabProps } from './index';

export function DeviceTab({ c }: TabProps) {
  const v = deviceView(c);
  if (!v) return null;
  const rows: [string, string][] = [
    [v.bulk ? 'Lot' : 'Device', deviceLine(v)],
    ['IMEI', v.imei ?? 'None (a bulk lot)'],
    ['Model', v.model + (v.storageGb != null ? ` · ${v.storageGb} GB` : '')],
    ['Grade', gradeLine(v) + (v.declaredGrade !== v.grade ? ` · declared ${v.declaredGrade}` : '')],
    ['Reference', refLine(v)],
    ['Partner', v.partner],
    ['Batch', v.batch ?? 'None'],
    ['Received', fmtDateYear(v.received)],
  ];
  const lines = lotLines(v);
  return (
    <>
      <Kv rows={rows} />
      {lines.length > 0 && (
        <ul className="stsys stpad" aria-label="Device lines">{lines.map((l) => <li key={l}>{l}</li>)}</ul>
      )}
    </>
  );
}
