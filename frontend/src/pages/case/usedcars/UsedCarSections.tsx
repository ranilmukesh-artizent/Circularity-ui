/**
 * The used-car sections of a case (plan 9 UI audit gap 7): title and lien, odometer check, recall, and the channel choice with
 * each channel's value. Shared by the Overview panel and the stage tabs; read only (every fact comes with the case screen).
 * Title, odometer and recall wording needs review by Kinective's Legal team before it is relied on.
 */
import type { CaseRec } from '../../../api/case';
import { money } from '../../../api/format';
import { Kv } from '../CaseBlocks';
import { gateLine } from '../gates';
import { channelRows, netText, odometerLine, recallLine, titleLine, usedCarView, vehicleGates } from './carView';

const sign = (k: string) => (k === 'v' || k === 'value' ? '' : '−');

/** Title and lien, odometer and recall, each as a line, with the vehicle gates beneath. */
export function VehicleChecks({ c }: { c: CaseRec }) {
  const v = usedCarView(c);
  if (!v) return null;
  const gates = vehicleGates(c.gates);
  const rows: [string, string][] = [
    ['Title and lien', titleLine(v.title)],
    ['Odometer', odometerLine(v.odometer)],
    ['Recall', recallLine(v.recall)],
  ];
  if (v.title?.brand) rows.splice(1, 0, ['Title brand', v.title.brand]);
  if (v.recall?.fleet_size != null) rows.push(['Seller fleet', `${v.recall.fleet_size} vehicles`]);
  return (
    <>
      <Kv rows={rows} />
      {gates.length > 0 && (
        <ul className="stsys stpad" aria-label="Vehicle gates">
          {gates.map((g) => <li key={g.id} className={g.passed ? '' : 'tx-bad'}>{g.name}: {gateLine(g)}</li>)}
        </ul>
      )}
    </>
  );
}

/** The channels (retail per lot, auction, dealer trade, salvage) with the money after costs; a blocked one gives its reason. */
export function ChannelChoice({ c }: { c: CaseRec }) {
  if (!usedCarView(c)) return null;
  const rows = channelRows(c);
  if (!rows.length) return <p className="note stpad">No channel is valued yet.</p>;
  const byId = new Map(c.routes.map((r) => [r.id, r]));
  return (
    <ul className="stsys stpad" aria-label="Channels">
      {rows.map((r) => (
        <li key={r.id} className={r.note ? 'tx-bad' : ''}>
          <details open={r.best}>
            <summary><b>{r.name}</b> · {netText(r)}</summary>
            <ul>
              {(byId.get(r.id)?.terms ?? []).map((t, i) => <li key={i}>{t.label}: {sign(t.kind)}{money(t.amt)}</li>)}
            </ul>
          </details>
        </li>
      ))}
    </ul>
  );
}
