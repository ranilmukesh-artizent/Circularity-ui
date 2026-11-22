/**
 * A vendor's mark (the demo's vlogo): its initials on a hue from the name; with `logos` (the demo's FEAT.logos), the
 * vendor's logo from the app's assets when there is one.
 */
import type { CSSProperties } from 'react';
import { LOGO_KEY, SYSLOGO } from '../../assets/assets.gen';

/** The hue of a vendor's initials tile. */
export const vendorHue = (v: string): number => {
  let h = 7;
  for (const c of v) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
};
/** The two letters of a vendor's initials tile. */
const vendorInitials = (v: string): string => v.replace(/[^A-Za-z0-9 ]/g, '').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();

export function VendorLogo({ vendor, logos }: { vendor: string; logos?: boolean }) {
  if (logos) {
    const k = LOGO_KEY.find((x) => x[0].test(vendor || ''))?.[1];
    if (k && SYSLOGO[k]) {
      // static, trusted marks from the demo's logo set (src/assets/assets.gen.ts)
      return <span className="vlg" data-logo={k} aria-hidden="true"><svg viewBox="0 0 32 32" dangerouslySetInnerHTML={{ __html: SYSLOGO[k] }} /></span>;
    }
  }
  return <span className="vlogo" style={{ '--h': vendorHue(vendor) } as CSSProperties} aria-hidden="true">{vendorInitials(vendor)}</span>;
}
