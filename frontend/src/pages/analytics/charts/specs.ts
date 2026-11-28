/** The View data spec of each new chart: which rows, which chips, what the rows add up to. Sections match the page's role gates. */
import { facet, measures, type Facet, type Measure, type ViewSpec } from '../data/dataView';
import type { ClosedRow } from '../../../api/analytics';
import type { RowsRef } from '../../../api/analyticsRows';

const reconciled = facet.status('reconciled');

export const flowSpec = (parts: Facet[] = []): ViewSpec => ({
  title: 'Where returned assets go: class, route and outcome', chart: 'flow', section: 'pipeline', facets: parts, measure: measures.count,
});

export const heatSpec = (parts: Facet[] = []): ViewSpec => ({
  title: 'Typical gain over the baseline per case, by route and asset class', chart: 'heatmap', section: 'mix', facets: [reconciled, ...parts],
  measure: { label: 'median recovered above the baseline per case', unit: 'usd', of: measures.uplift.of, agg: 'median' },
  note: 'Cells with fewer than 5 cases show a dash in the chart; every row is here.',
});

export const trendSpec = (parts: Facet[] = []): ViewSpec => ({
  title: 'Net recovered each month, and the gain over the baseline so far', chart: 'trend', section: 'waterfall', facets: [reconciled, ...parts], measure: measures.net,
});

export const ageSpec = (ref: RowsRef, chips: string[]): ViewSpec => ({
  title: 'Open decisions by age and route', chart: ref.chart, key: ref.key, source: 'cases', section: 'pipeline', facets: [], fixedChips: chips,
  note: 'Decisions waiting for approval, by days since the case was received. The value is the forecast net of the recommended route (modelled, not realised).',
});


// ---------------------------------------------------------------- the existing charts: their selection, as a spec
/** An existing chart's selection (a title and a test) opened as View data: one removable chip carries its title. */
export function fromDrill(d: { title: string; fn: (r: ClosedRow) => boolean }, chart: string, section: string, measure: Measure): ViewSpec {
  return { title: d.title, chart, section, facets: [facet.custom(d.title, d.fn)], measure };
}
/** A whole chart's rows (the panel's View data button). */
export const whole = (title: string, chart: string, section: string, facets: Facet[], measure: Measure, note?: string): ViewSpec => ({ title, chart, section, facets, measure, note });

export const measureOf = {
  uplift: measures.uplift,
  count: measures.count,
  avoided: measures.avoided,
  co2: measures.co2,
  days: { label: 'median days to realize', unit: 'days', agg: 'median', of: (r: ClosedRow) => r.days ?? 0 } satisfies Measure,
  lost: { label: 'value lost to repair or early failure', unit: 'usd', of: (r: ClosedRow) => r.ero } satisfies Measure,
  override: { label: 'net effect against the recommended route (estimated)', unit: 'usd', of: (r: ClosedRow) => r.override?.delta ?? 0 } satisfies Measure,
};
