/** The telecom network panels on the case page: the Overview panel (every section) and the stage tabs draw the same sections.
 * Export-control and battery wording is reviewed by Kinective's Legal team before it is relied on. */
import { Panel } from '../../../components/kit/Panel';
import { approvalLines, batteryLines, benchLine, closeLine, exportLine, inventoryLine, recyclerLine, sparesLines, wipeLine, type TelecomCase } from './telecom';

const Line = ({ label, text, bad, id }: { label: string; text: string; bad?: boolean; id: string }) => (
  <p className={bad ? 'note tx-bad' : 'note'} style={{ margin: '4px 0' }} data-testid={id}><b>{label}:</b> {text}</p>
);

export function UnitSection({ c }: { c: TelecomCase }) {
  const inv = inventoryLine(c);
  const wipe = wipeLine(c);
  const bench = benchLine(c);
  return (
    <>
      <Line id="tn-inventory" label="Inventory" text={inv} bad={inv.startsWith('Does not')} />
      {bench && <Line id="tn-bench" label="Test bench" text={bench.replace('Test bench: ', '')} />}
      <Line id="tn-wipe" label="Wipe" text={wipe ?? ''} bad={!wipe?.startsWith('Wipe verified')} />
    </>
  );
}

export function ExportSection({ c }: { c: TelecomCase }) {
  const a = approvalLines(c);
  return (
    <>
      <Line id="tn-export" label="Export control" text={exportLine(c)} />
      {a && (
        <div data-testid="tn-approval">
          <span className="chip warn">Trade compliance approval</span>
          <p className="note" style={{ margin: '4px 0' }}>{a.bid}</p>
          <p className="note" style={{ margin: '4px 0' }}>{a.alternative}</p>
        </div>
      )}
    </>
  );
}

export function SparesSection({ c }: { c: TelecomCase }) {
  const lines = sparesLines(c);
  if (!lines.length) return null;
  return <ul className="note" style={{ margin: '4px 0', paddingLeft: 16 }} aria-label="Spares before new" data-testid="tn-spares">{lines.map((l) => <li key={l}>{l}</li>)}</ul>;
}

export function BatterySection({ c }: { c: TelecomCase }) {
  const lines = batteryLines(c);
  const rec = recyclerLine(c);
  if (!lines.length && !rec) return null;
  return (
    <ul className="note" style={{ margin: '4px 0', paddingLeft: 16 }} aria-label="Battery lane and recycler" data-testid="tn-battery">
      {lines.map((l) => <li key={l}>{l}</li>)}
      {rec && <li>{rec}</li>}
    </ul>
  );
}

export function CloseSection({ c }: { c: TelecomCase }) {
  const l = closeLine(c);
  return l ? <Line id="tn-close" label="Close" text={l} /> : null;
}

/** The Overview panel of a telecom network case. */
export function TelecomPanel({ c }: { c: TelecomCase }) {
  return (
    <Panel title="Network unit" sub={c.network?.serial ? `${c.network.serial} · ${c.network.model ?? ''}` : 'telecom_network pack'}>
      <UnitSection c={c} />
      <ExportSection c={c} />
      <SparesSection c={c} />
      <BatterySection c={c} />
      <CloseSection c={c} />
      <p className="note" style={{ margin: '8px 0 0' }}>
        Worked questions WQ-TN-1 and WQ-TN-2 (idle spares and units bought new): <a href="#/analytics/packs">Analytics, Packs</a>
      </p>
    </Panel>
  );
}
