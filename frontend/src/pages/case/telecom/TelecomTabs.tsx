/** The telecom stage tabs (registered in tabs/index.tsx): the unit's checks at stage 4, export and spares at stage 6, the close at stage 10. */
import type { TabProps } from '../tabs/index';
import { BatterySection, CloseSection, ExportSection, SparesSection, UnitSection } from './TelecomPanel';
import type { TelecomCase } from './telecom';

export const TelecomUnitTab = ({ c }: TabProps) => (
  <div className="stpad"><UnitSection c={c as TelecomCase} /><BatterySection c={c as TelecomCase} /></div>
);
export const TelecomExportTab = ({ c }: TabProps) => <div className="stpad"><ExportSection c={c as TelecomCase} /></div>;
export const TelecomSparesTab = ({ c }: TabProps) => <div className="stpad"><SparesSection c={c as TelecomCase} /></div>;
export const TelecomCloseTab = ({ c }: TabProps) => <div className="stpad"><CloseSection c={c as TelecomCase} /></div>;
