import type { PackVersion } from '../../api/types';

/** "13 of 13 parts": how many of the pack's parts check out. */
export const partsLine = (v: Pick<PackVersion, 'parts'>): string => `${v.parts.ok} of ${v.parts.total} parts`;

const money = (n: number): string => (n < 0 ? '-' : '+') + '$' + Math.abs(n).toLocaleString('en-US');

/** "Would change 3 of 41 decisions (+$1,240)": what publishing a version does to the open cases and the sample queue. */
export function impactLine(impact: PackVersion['impact']): string {
  if (!impact) return 'Impact not calculated';
  if (impact.total === 0) return 'No decisions to compare';
  if (impact.changed === 0) return `Would change none of ${impact.total} decisions`;
  const value = impact.dv === 0 ? '$0' : money(impact.dv);
  return `Would change ${impact.changed} of ${impact.total} decisions (${value})`;
}

/** The server's refusal of an import with its part first: "Part 5 (routes): Field required". Other texts stay as they are. */
export function refusalLine(message: string): string {
  const m = /: part (\d+) \(([^)]+)\): (.+)$/.exec(message);
  return m ? `Part ${m[1]} (${m[2]}): ${m[3]}` : message;
}

export const STATUS_LABEL: Record<PackVersion['status'], string> = { draft: 'Draft', review: 'In review', pub: 'Published', retired: 'Retired' };

const ACRONYMS = new Set(['itad']);

/** A pack's title for people: its name, or the key spelled out ("medical_rental" reads "Medical rental") when the name is the key. */
export function packTitle(k: { key: string; name: string }): string {
  if (k.name !== k.key) return k.name;
  if (ACRONYMS.has(k.key)) return k.key.toUpperCase();
  const words = k.key.replace(/[_-]+/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}
