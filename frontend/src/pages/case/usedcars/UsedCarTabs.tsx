/** The used-car stage tabs (plan 9 UI audit gap 7): "Vehicle checks" at the condition stage, "Channels" at the decision stage. */
import { QUESTIONS_HREF } from './carView';
import { ChannelChoice, VehicleChecks } from './UsedCarSections';
import type { TabProps } from '../tabs';

export const VehicleChecksTab = ({ c }: TabProps) => <VehicleChecks c={c} />;

export const CarChannelsTab = ({ c }: TabProps) => (
  <>
    <ChannelChoice c={c} />
    <p className="stpad"><a className="lnk" href={QUESTIONS_HREF}>Worked questions for used cars</a></p>
  </>
);
