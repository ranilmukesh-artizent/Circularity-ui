/**
 * The manual import's checks and wording (Connection Fabric › Records › Import). The server checks the rows again
 * (backend/di/services/actions/fabric_records.py row_errors): for an industrial case the asset id follows the demo's
 * class pattern; a tool-fleet or device case may carry any id-shaped asset id, and its template columns travel with
 * each row (backend/di/connectors/manual.py TEMPLATE_COLUMNS).
 */
import { TEMPLATE_IMPORT_COLUMNS, type ImportResult, type ImportRow } from '../../api/integration';

export type Row = ImportRow & { warn: string[] };
export type Csv = { rows: Row[]; ok: number; err: number; committed?: boolean };

const NEED = ['asset_id', 'qty', 'condition_grade', 'location', 'owner', 'received'];
const ID_ANY = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const ID_INDUSTRIAL = /^(MTR|PMP|CTL|DRL|BAT|ITE)-\d{4}$/;

const columnsOf = (template: string): readonly string[] => TEMPLATE_IMPORT_COLUMNS[template as keyof typeof TEMPLATE_IMPORT_COLUMNS] ?? [];

/** Validate pasted CSV for the template the cases open with (industrial when no case is opened); a message when the header is wrong. */
export function validateCsv(t: string, template: string, facilities: readonly string[], tenants: readonly string[]): Csv | string {
  const lines = t.split(/\r?\n/).filter(Boolean), hd = lines[0].split(',').map((x) => x.trim().toLowerCase());
  const miss = NEED.filter((n) => !hd.includes(n));
  if (miss.length) return 'Missing required column: ' + miss.join(', ');
  const extra = columnsOf(template);
  const rows = lines.slice(1).map((l): Row => {
    const c = l.split(',').map((x) => x.trim()), o: Record<string, string> = {};
    hd.forEach((h, i) => { o[h] = c[i] || ''; });
    const errors: string[] = [], warn: string[] = [];
    if (extra.length) {
      if (!ID_ANY.test(o.asset_id)) errors.push("asset_id is required (letters, digits, '.', '_' or '-')");
    } else if (!ID_INDUSTRIAL.test(o.asset_id)) errors.push('asset_id does not match a known class pattern');
    if (!/^[1-9]\d*$/.test(o.qty)) errors.push('qty must be a positive whole number');
    let g = o.condition_grade;
    if (/^[ABCD]\+$/.test(g)) { warn.push(g + ' mapped to ' + g[0]); g = g[0]; } else if (!/^[ABCD]$/.test(g)) errors.push('grade must be A–D');
    if (!facilities.includes(o.location)) errors.push('unknown location "' + o.location + '"');
    if (!tenants.includes(o.owner)) errors.push('owner is not a tenant on this account');
    let d = o.received;
    if (/^\d{4}\/\d{2}\/\d{2}$/.test(d)) { warn.push('date reformatted'); d = d.replace(/\//g, '-'); } else if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) errors.push('received must be YYYY-MM-DD');
    const own = Object.fromEntries(extra.map((k) => [k, o[k] ?? '']));
    return { asset_id: o.asset_id, qty: o.qty, grade: g, location: o.location, owner: o.owner, received: d, ...own, errors, warn };
  });
  return { rows, ok: rows.filter((r) => !r.errors.length).length, err: rows.filter((r) => r.errors.length).length };
} // prettier-ignore

/** The help line under the required columns: what a tool-fleet or device case also reads; empty for industrial. */
export function templateColumnsNote(template: string): string {
  const extra = columnsOf(template);
  if (!extra.length) return '';
  const name = template === 'device' ? 'Device' : 'Tool fleet';
  return `${name} cases also read: ${extra.join(', ')} (grade from condition_grade${template === 'device' ? ', qty from qty' : ''}).`;
}

/** The toast after a load: the rows, then the cases opened, already open and not opened, with each failure's reason. */
export function importSummary(ok: number, o: ImportResult): string {
  const base = ok + ' rows loaded for evaluation. They are tagged manual and will not trigger any instruction.';
  if (o.cases_opened === undefined) return base;
  const why = (o.case_failures ?? []).map((f) => f.asset_id + ': ' + f.reason).join('; ');
  return `${base} Cases: ${o.cases_opened} opened, ${o.cases_skipped ?? 0} already open, ${o.cases_failed ?? 0} not opened.` + (why ? ' ' + why : '');
}
