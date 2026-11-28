/** Closed decisions for the Analytics tests: a small, known set so every count and median can be checked by hand. */
import type { ClosedRow } from '../../../api/analytics';
import type { Labels } from '../data/dataView';

export const LABELS: Labels = {
  months: ['January', 'February', 'March'],
  classes: { pump: 'Pump', motor: 'Motor' },
  routes: { redeploy: 'Redeploy', resale: 'Resale', exit: 'Exit' },
};

let n = 0;
export function row(p: Partial<ClosedRow> = {}): ClosedRow {
  n += 1;
  return {
    id: 'RT-' + (1000 + n), mi: 0, tenant: 'Customer A', site: 'Plant 1', cls: 'pump', route: 'redeploy', model: 'v1.3', assetId: 'A-' + n, snapshot: 's',
    status: 'reconciled', p10: 80, p50: 100, p90: 120, actual: 110, baseline: 100, days: 10, baseDays: 20, avoided: 0, co2e: 5, co2m: null,
    pool: null, ero: 0, comp: 'Seal', equip: 'P1', override: null, ...p,
  };
}

/** 6 redeploy pumps (uplift 10 each), 5 resale motors (uplift -20 each, one in March), 2 pending, 1 cancelled. */
export function sample(): ClosedRow[] {
  n = 0;
  return [
    ...Array.from({ length: 6 }, () => row()),
    ...Array.from({ length: 4 }, () => row({ cls: 'motor', route: 'resale', actual: 80, baseline: 100, mi: 1 })),
    row({ cls: 'motor', route: 'resale', actual: 80, baseline: 100, mi: 2, tenant: 'Customer B', override: { rec: 'redeploy', exec: 'resale', reason: 'Customer asked', cf: 90, delta: -10 } }),
    row({ status: 'pending', actual: null, days: null }),
    row({ status: 'pending', actual: null, days: null, route: 'resale', cls: 'motor' }),
    row({ status: 'cancelled', actual: null, days: null }),
  ];
}
