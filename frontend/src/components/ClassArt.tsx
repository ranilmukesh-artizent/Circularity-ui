/**
 * The picture of an asset class that has no product photo (UI audit gap C8): a plain line icon of its family and the
 * class name, on the tile colours of the demo's `.asph` and `.thumb` (light and dark). No photo, logo or vendor name.
 * The family comes from the class id; a class this table does not know falls back to its pack, then to a generic box.
 */
import { packClasses } from '../api/client';

export type ClassFamily = 'vehicle' | 'network' | 'medical' | 'it' | 'battery' | 'core' | 'machine' | 'apparel' | 'generic';

const BY_CLASS: Record<string, ClassFamily> = {
  car_ice: 'vehicle', car_ev: 'vehicle',
  radio: 'network', baseband: 'network', router: 'network', line_card: 'network', power_unit: 'network', microwave_link: 'network',
  infusion_pump: 'medical', patient_monitor: 'medical', electric_bed: 'medical', syringe_driver: 'medical',
  transport_ventilator: 'medical', pulse_oximeter: 'medical',
  laptop: 'it', desktop: 'it', server: 'it', network: 'it', phone: 'it', device: 'it',
  ev_pack: 'battery', industrial_pack: 'battery',
  alternator: 'core', starter: 'core', transmission: 'core',
  excavator_20t: 'machine', wheel_loader: 'machine', scissor_lift: 'machine', telehandler: 'machine', generator: 'machine',
};
const BY_PACK: Record<string, ClassFamily> = {
  used_cars: 'vehicle', telecom_network: 'network', medical_rental: 'medical', itad: 'it', device: 'it', battery: 'battery',
  auto_core: 'core', rental_fleet: 'machine', apparel: 'apparel',
};

/** The family of a class: its own, else its pack's, else generic. */
export function classFamily(cls: string | null | undefined): ClassFamily {
  if (!cls) return 'generic';
  if (Object.hasOwn(BY_CLASS, cls)) return BY_CLASS[cls];
  const pack = packClasses()[cls]?.pack;
  return pack && Object.hasOwn(BY_PACK, pack) ? BY_PACK[pack] : 'generic';
}

// 24 x 24, stroke 1.75, round caps: the demo's icon style
const PATHS: Record<ClassFamily, string> = {
  vehicle: 'M5 16V12l1.6-4.2A2 2 0 0 1 8.5 6.5h7a2 2 0 0 1 1.9 1.3L19 12v4M3.5 16h17M5 16v2.5M19 16v2.5M5 12h14M7.5 14.2h.01M16.5 14.2h.01',
  network: 'M12 20v-8M8.5 20h7M12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM8.4 5.6a5 5 0 0 0 0 7.1M15.6 5.6a5 5 0 0 1 0 7.1M5.6 2.9a9 9 0 0 0 0 12.7M18.4 2.9a9 9 0 0 1 0 12.7',
  medical: 'M4 5.5h16v13H4zM6.5 12h3l1.5-3 2.5 6 1.5-3h2.5',
  it: 'M5 5h14v10H5zM2.5 19h19M9.5 15v4M14.5 15v4',
  battery: 'M3.5 8h15v8h-15zM18.5 10.5h2v3h-2zM7 11v2M10 10v4',
  core: 'M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7zM12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1',
  machine: 'M3.5 18.5h13M5 18.5l1.5-5h6l1 5M7 13.5v-4l7-5.5 2.5 2.5-5 4M17 18.5a2 2 0 1 0 4 0 2 2 0 0 0-4 0z',
  apparel: 'M9 4l-5.5 3 2 3.5L8 9.5V20h8V9.5l2.5 1 2-3.5L15 4a3 3 0 0 1-6 0z',
  generic: 'M4 8l8-4 8 4v8l-8 4-8-4zM4 8l8 4 8-4M12 12v8',
};

export function ClassIcon({ family }: { family: ClassFamily }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[family]} />
    </svg>
  );
}

/** The tile: the family icon over the class name. Fills the picture box it sits in (`.asimg`). */
export function ClassArt({ cls, label }: { cls: string; label: string }) {
  const family = classFamily(cls);
  return (
    <span className="asph classart" data-family={family}>
      <span className="thumb"><ClassIcon family={family} /></span>
      <span>{label}</span>
    </span>
  );
}
