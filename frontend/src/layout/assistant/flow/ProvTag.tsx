import type { Prov } from '../../../pages/modeler/flowBrief';

/**
 * The provenance tag of plan 10 (4.1): where a fact came from, in the demo's five words (Retrieved, Rules, Model,
 * Simulated, Prepared by agent), sentence case. The colours are the stylesheet's (`.as-prov[data-prov]`).
 */
export function ProvTag({ name }: { name: Prov }) {
  return <span className="as-prov" data-prov={name.toLowerCase().replace(/ /g, '-')}>{name}</span>;
}
