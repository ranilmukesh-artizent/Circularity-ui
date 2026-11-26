/** The used-car panel on the case Overview (plan 9 UI audit gap 7): the vehicle checks, the channel choice and the link to the pack's worked questions. */
import type { CaseRec } from '../../../api/case';
import { Panel } from '../../../components/kit/Panel';
import { QUESTIONS_HREF, usedCarView } from './carView';
import { ChannelChoice, VehicleChecks } from './UsedCarSections';

export function UsedCarPanel({ c }: { c: CaseRec }) {
  const v = usedCarView(c);
  if (!v) return null;
  return (
    <Panel title="Used car" sub={[v.vin, v.returnKind?.replace('_', ' ')].filter(Boolean).join(' · ') || undefined}>
      <VehicleChecks c={c} />
      <h4 className="stpad" style={{ margin: '8px 0 0' }}>Channels</h4>
      <ChannelChoice c={c} />
      <p className="stpad" style={{ margin: '8px 0 0' }}><a className="lnk" href={QUESTIONS_HREF}>Worked questions for used cars</a></p>
    </Panel>
  );
}
