import type { Jdm, MarketTable } from '../../api/marketTables';

/** The grid a decision table is edited as: one column per input and output, one row per rule (first hit order). */
export interface TableGrid {
  hitPolicy: 'first' | 'collect';
  inputs: string[];
  outputs: string[];
  rows: { id: string; inputs: string[]; outputs: string[] }[];
}

interface Column { id: string; name: string; field?: string; type?: string }
interface TableContent { hitPolicy?: string; inputs?: Column[]; outputs?: Column[]; rules?: Record<string, string>[] }

const isTable = (n: Jdm['nodes'][number]) => n.type === 'decisionTableNode';
const contentOf = (j: Jdm): TableContent => (j.nodes.find(isTable)?.content ?? {}) as TableContent;

/** What a priced line cites: "DE labour rates v1". */
export const tableLabel = (r: Pick<MarketTable, 'market' | 'title' | 'version'>): string => `${r.market} ${r.title} v${r.version}`;

/** The decision table node of a JDM graph as a grid. */
export function jdmToRows(j: Jdm): TableGrid {
  const c = contentOf(j);
  const ins = c.inputs ?? [];
  const outs = c.outputs ?? [];
  return {
    hitPolicy: c.hitPolicy === 'collect' ? 'collect' : 'first',
    inputs: ins.map((x) => x.name),
    outputs: outs.map((x) => x.name),
    rows: (c.rules ?? []).map((r) => ({ id: r._id, inputs: ins.map((x) => r[x.id] ?? ''), outputs: outs.map((x) => r[x.id] ?? '') })),
  };
}

/** The graph `base` with its decision table node replaced by the grid; columns keep their ids and fields by name. */
export function rowsToJdm(base: Jdm, g: TableGrid): Jdm {
  const c = contentOf(base);
  const col = (old: Column[] | undefined, name: string, prefix: string): Column =>
    old?.find((x) => x.name === name) ?? { id: `${prefix}_${name}`, name, field: name, type: 'expression' };
  const inputs = g.inputs.map((n) => col(c.inputs, n, 'in'));
  const outputs = g.outputs.map((n) => col(c.outputs, n, 'out'));
  const rules = g.rows.map((r) => ({
    _id: r.id,
    ...Object.fromEntries(inputs.map((x, i) => [x.id, r.inputs[i] ?? ''])),
    ...Object.fromEntries(outputs.map((x, i) => [x.id, r.outputs[i] ?? ''])),
  }));
  return { ...base, nodes: base.nodes.map((n) => (isTable(n) ? { ...n, content: { ...c, hitPolicy: g.hitPolicy, inputs, outputs, rules } } : n)) };
}

/** A new empty rule (every input matches, every output empty) with an id not in use. */
export function blankRow(g: TableGrid): TableGrid['rows'][number] {
  const used = new Set(g.rows.map((r) => r.id));
  let n = g.rows.length + 1;
  while (used.has(`r${n}`)) n += 1;
  return { id: `r${n}`, inputs: g.inputs.map(() => ''), outputs: g.outputs.map(() => '') };
}

/** A rate card's values from what was typed (a rate left empty or not a number is `null`). */
export const valuesFromText = (t: Record<string, string>): Record<string, number | null> =>
  Object.fromEntries(Object.entries(t).map(([k, v]) => [k, v.trim() !== '' && Number.isFinite(Number(v)) ? Number(v) : null]));
