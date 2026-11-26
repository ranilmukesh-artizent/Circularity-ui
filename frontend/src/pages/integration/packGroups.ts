/* The mock systems of the packs, grouped by pack (UI audit gaps 10 and 11). The server sends them in pack order
   (GET /api/screens/integration/overview, `pack_systems`); this only groups the flat list for display. */
import type { PackSystem } from '../../api/integration';

export type { PackSystem };
export interface PackGroup { pack: string; name: string; systems: PackSystem[]; open: number }

/** One group per pack in first-seen order; `open` counts the systems nobody has registered yet. */
export function groupByPack(list: PackSystem[]): PackGroup[] {
  const out = new Map<string, PackGroup>();
  for (const x of list) {
    const g = out.get(x.pack) ?? { pack: x.pack, name: x.pack_name, systems: [], open: 0 };
    g.systems.push(x);
    if (!x.registered) g.open++;
    out.set(x.pack, g);
  }
  return [...out.values()];
}
