/**
 * The product photo of an asset class (UI audit gaps 8 and C8). One function for the case page and the asset page, so no
 * class ever asks for `assets/products/undefined.webp` and no class shows a photo of something else.
 *
 * The photos are the demo's five (`motor`, `pump`, `control`, `powertool`, `it`) and cover the demo's classes and the
 * tool fleet's power tools. Every other class (vehicles, network kit, medical devices, IT equipment, batteries, cores,
 * rental machines, apparel, anything a pack adds later) has no photo: `photoSrc` returns null and the page draws the
 * class tile (`components/ClassArt.tsx`: a line icon and the class name) instead. The label of a class comes from the
 * reference `CLASSES` and `PACK_CLASSES` lists, not from here.
 */
const PHOTO = {
  // the demo's industrial classes
  motor: 'motor', pump: 'pump', control: 'control', drill: 'powertool', batch: 'powertool', it: 'it',
  // tool_fleet: power tools
  CMH: 'powertool', BRK: 'powertool', DCD: 'powertool', CRH: 'powertool', AGR: 'powertool', LSR: 'powertool', BAT: 'powertool',
} as const satisfies Record<string, 'motor' | 'pump' | 'control' | 'powertool' | 'it'>;

/** The photo file (without folder or extension) of a class, or null when the class has none and shows its tile. */
export const photoFile = (cls: string | null | undefined): string | null => (cls && Object.hasOwn(PHOTO, cls) ? PHOTO[cls as keyof typeof PHOTO] : null);

/** The photo's URL, or null for a class that shows its tile; the same for every page. */
export const photoSrc = (cls: string | null | undefined): string | null => {
  const f = photoFile(cls);
  return f ? 'assets/products/' + f + '.webp' : null;
};
