/* Pure helpers of the "Connect your systems" step: which table of a source is ticked, the line that says so, the three parts
   of a system (Connection, Data, Mapping) as a track, and the sentences about what a model did. No React, no calls. */
import type { MappingModelNote, Table } from '../../../api/integration';
import type { ComposeSystem } from '../../../api/compose';

/** What mapping.suggest takes to limit a run to one table: the resource the table was discovered from (none for a modelled table). */
export const resourceOf = (t: Pick<Table, 'resource'>): string | undefined => t.resource || undefined;
/** The key a table is ticked by. */
export const tableKey = (t: Pick<Table, 'n'>): string => t.n;

/** The tables ticked, in the source's order. `ticked` is the person's choice, or null while they have made none (every table). */
export function tickedTables<T extends Pick<Table, 'n'>>(tables: readonly T[], ticked: ReadonlySet<string> | null): T[] {
  return ticked === null ? [...tables] : tables.filter((t) => ticked.has(tableKey(t)));
}

/** Tick or untick one table; the first change starts from "every table". */
export function toggleTable(tables: readonly Pick<Table, 'n'>[], ticked: ReadonlySet<string> | null, name: string): Set<string> {
  const next = new Set(ticked ?? tables.map(tableKey));
  if (next.has(name)) next.delete(name);
  else next.add(name);
  return next;
}

/** One run of mapping.suggest: a single resource, or (no resource) every table of the source. */
export interface RunUnit { key: string; label: string; resource?: string }
export const WHOLE_SOURCE: RunUnit = { key: '*', label: 'Every table of the source' };

/** The runs for the ticked tables, one per table that came from a resource; modelled tables have no resource, so they share one run on the whole source. */
export function runUnits(used: readonly Pick<Table, 'n' | 'resource'>[]): RunUnit[] {
  const units: RunUnit[] = used.filter((t) => resourceOf(t)).map((t) => ({ key: resourceOf(t)!, label: t.n, resource: resourceOf(t) }));
  if (used.some((t) => !resourceOf(t))) units.push(WHOLE_SOURCE);
  return units;
}

const plural =(n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`;

/** "All 5 tables used", "2 of 5 tables used", "No table used". */
export function selectionLine(used: number, total: number): string {
  if (total === 0) return 'No tables yet';
  if (used === 0) return 'No table used';
  if (used === total) return total === 1 ? 'The table is used' : `All ${total} tables used`;
  return `${used} of ${plural(total, 'table')} used`;
}

/** "1,204 rows" from the server's row count (a string such as "1204" or "1.2k"); empty when it gave none. */
export function rowsText(rows: string | number | null | undefined): string {
  if (rows === null || rows === undefined || rows === '') return '';
  const n = typeof rows === 'number' ? rows : /^\d+$/.test(rows) ? Number(rows) : null;
  if (n === null) return `${rows} rows`;
  return `${n.toLocaleString('en-US')} ${n === 1 ? 'row' : 'rows'}`;
}

export type PartState = 'done' | 'now' | 'todo' | 'back';
export interface Part { name: 'Connection' | 'Data' | 'Mapping'; state: PartState; note: string }

/** The three parts of a system as a track: what is done, where the person is, what is still to do. */
export function partsOf(x: Pick<ComposeSystem, 'status' | 'source_id' | 'mapping'>, tables: number, used: number, canRead: boolean): Part[] {
  const connected = x.source_id !== null && x.status !== 'needs_adapter';
  const connection: Part = connected
    ? { name: 'Connection', state: x.status === 'awaiting_owner' ? 'now' : 'done', note: x.status === 'awaiting_owner' ? 'Waiting for the system owner' : x.status === 'test_connection' ? 'Test connection' : 'Connected' }
    : { name: 'Connection', state: 'now', note: 'Needs an adapter' };
  if (!connected) return [connection, { name: 'Data', state: 'todo', note: 'After it is connected' }, { name: 'Mapping', state: 'todo', note: 'After the data' }];
  let data: Part;
  if (!canRead) data = { name: 'Data', state: 'todo', note: 'Not shown to your role' };
  else if (tables === 0 && x.mapping.fields > 0) data = { name: 'Data', state: 'done', note: 'Records sent, no tables' };
  else if (tables === 0) data = { name: 'Data', state: 'now', note: 'No sample yet' };
  else data = { name: 'Data', state: used > 0 ? 'done' : 'now', note: selectionLine(used, tables) };
  const m = x.mapping;
  const mapping: Part =
    m.fields === 0 ? { name: 'Mapping', state: data.state === 'done' || !canRead ? 'now' : 'todo', note: 'Not suggested yet' }
    : m.asked_owner > 0 ? { name: 'Mapping', state: 'now', note: `${plural(m.asked_owner, 'field')} with the owner` }
    : { name: 'Mapping', state: 'done', note: plural(m.fields, 'field') + ' read' };
  return [connection, data, mapping];
}

/** What the model did, in one sentence for the person; empty when the server did not say. */
export function modelSentence(model: MappingModelNote | undefined, totalFields: number): string {
  if (!model) return '';
  const rest = 'the rest were matched by name and values.';
  if (model.answered <= 0 || model.stopped === 'no_model') return 'No model answered; every field was matched by name and values.';
  const of = model.fields || totalFields;
  const head = `A model read ${model.answered} of ${plural(of, 'field')}`;
  return model.stopped === 'budget' ? `${head} before its time ran out; ${rest}` : `${head}; ${rest}`;
}

/** The progress line while tables are read one at a time: "Reading table 2 of 3…". */
export const readingLine = (index: number, total: number): string => `Reading table ${index + 1} of ${total}…`;

/** Seconds waited, as the loading note shows it. */
export const waitedLine = (seconds: number): string => (seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min ${String(seconds % 60).padStart(2, '0')} s`);
/** The seconds after which the wait is called long. */
export const LONG_WAIT = 60;
