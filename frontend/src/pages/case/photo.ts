/**
 * The product photo of an asset class (UI audit gap 8). One function for the case page and the asset page, so no class
 * ever asks for `assets/products/undefined.webp`.
 *
 * The photos are the demo's five (`motor`, `pump`, `control`, `powertool`, `it`); a pack class without a photo of its own
 * shows one generic placeholder per pack (vehicles: the motor, network kit: the control unit, medical devices: the IT
 * electronics unit, tools: the power tool). The classes are the packs' own ids
 * (backend/di/services/modeler/packs/*.json `classes`); a class a pack adds later and this list does not know gets
 * `FALLBACK`, never a missing file. The label shown when a photo fails to load comes from the reference `CLASSES` and
 * `PACK_CLASSES` lists, not from here.
 */
const IMG = {
  // the demo's industrial classes
  motor: 'motor', pump: 'pump', control: 'control', drill: 'powertool', batch: 'powertool', it: 'it',
  // used_cars
  car_ice: 'motor', car_ev: 'motor',
  // telecom_network
  radio: 'control', baseband: 'control', router: 'control', line_card: 'control', power_unit: 'control', microwave_link: 'control',
  // medical_rental
  infusion_pump: 'it', patient_monitor: 'it', electric_bed: 'it', syringe_driver: 'it', transport_ventilator: 'it', pulse_oximeter: 'it',
  // itad and device recommerce
  laptop: 'it', desktop: 'it', server: 'it', network: 'it', phone: 'it', device: 'it',
  // rental_fleet
  excavator_20t: 'motor', wheel_loader: 'motor', scissor_lift: 'motor', telehandler: 'motor', generator: 'motor',
  // tool_fleet (and its battery pack class)
  CMH: 'powertool', BRK: 'powertool', DCD: 'powertool', CRH: 'powertool', AGR: 'powertool', LSR: 'powertool', BAT: 'powertool',
} as const satisfies Record<string, 'motor' | 'pump' | 'control' | 'powertool' | 'it'>;

const FALLBACK = 'powertool';

/** The photo file (without folder or extension) for a class: the class's own, else the generic one. */
export const photoFile = (cls: string | null | undefined): string => (cls && Object.hasOwn(IMG, cls) ? IMG[cls as keyof typeof IMG] : FALLBACK);

/** The photo's URL; the same for every page. */
export const photoSrc = (cls: string | null | undefined): string => 'assets/products/' + photoFile(cls) + '.webp';
