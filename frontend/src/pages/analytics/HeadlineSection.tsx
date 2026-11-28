import { Component, Suspense, useId, useState, useTransition, type ReactNode } from 'react';
import { usePackHeadlines, type PackHeadline as HeadlineData } from '../../api/analytics';
import { TableScroll } from '../../components/kit/TableScroll';
import type { ViewSpec } from './data/dataView';
import { basisTag, carbonSetNote, emptySentence, figureBasis, formatFigure, gradeRows, PERIODS, periodLabel, routeBars } from './headlineFigures';
import './packHeadline.css';

const cap = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

/** Which of the pack's cases a figure counts: closed cases (net, days, carbon), the cases still open (still listed), else every case of the period. */
const FIGURE_STATE: Record<string, string> = { net: 'closed', days: 'closed', carbon: 'closed', listed: 'open' };

/** The View data spec of a part of a pack headline: the server's `pack` chart, keyed `pack:<key>|route:..|grade:..|state:..`, over the headline's period. */
export function headlineSpec(h: Pick<HeadlineData, 'pack' | 'name' | 'route_word' | 'period'>, p: { route?: { id: string; name: string }; grade?: string; state?: string; label?: string }): ViewSpec {
  const parts = ['pack:' + h.pack, ...(p.route ? ['route:' + p.route.id] : []), ...(p.grade !== undefined ? ['grade:' + p.grade] : []), ...(p.state ? ['state:' + p.state] : [])];
  const chips = [`Pack: ${h.name}`, `Period: ${periodLabel(h.period.days)}`, ...(p.route ? [`${cap(h.route_word)}: ${p.route.name}`] : []), ...(p.grade !== undefined ? [`Grade: ${p.grade}`] : []),
    ...(p.state ? [`Cases: ${p.state === 'open' ? 'still open' : p.state}`] : [])];
  return {
    title: p.label ? `${h.name}: ${p.label}` : `${h.name}: the cases behind the headline`, chart: 'pack', key: parts.join('|'), days: h.period.days, source: 'cases', section: 'pack', facets: [],
    fixedChips: chips, note: 'Net is modelled at approval and carbon is estimated from a factor set; neither is realised.',
  };
}
type Open = (s: ViewSpec) => void;

/** One pack's headline: up to five figures with their counts and period, cases and net by route, and grades against routes. */
export function Headline({ h, onDays, pending = false, onViewData }: { h: HeadlineData; onDays: (d: number) => void; pending?: boolean; onViewData?: Open }) {
  const id = useId();
  const word = h.route_word;
  const bars = routeBars(h.routes);
  const grades = gradeRows(h.grades);
  const note = carbonSetNote(h.carbon_sets);
  const routeName = (id: string) => h.grades.routes.find((r) => r.id === id)?.name ?? id;
  const open = (p: Parameters<typeof headlineSpec>[1]) => onViewData?.(headlineSpec(h, p));
  return (
    <section className="panel phl" data-pack={h.pack} aria-labelledby={id + 'h'} aria-busy={pending}>
      <div className="ph">
        <div>
          <h2 id={id + 'h'} className="phl-title">{h.name}</h2>
          <span className="note">{h.cases} {h.cases === 1 ? 'case' : 'cases'} opened in the {periodLabel(h.period.days)}, {h.closed} closed</span>
        </div>
        <label className="phl-period">
          <span className="note">Period</span>
          <select className="sel" value={h.period.days} onChange={(e) => onDays(Number(e.target.value))}>
            {PERIODS.map((d) => <option key={d} value={d}>Last {d} days</option>)}
          </select>
        </label>
      </div>
      <div className="pb">
        {h.cases === 0 ? (
          <p className="phl-empty" data-testid="headline-empty">{emptySentence(h)}</p>
        ) : (
          <>
            <dl className="phl-figs">
              {h.figures.map((f) => {
                const v = formatFigure(f), tag = basisTag(f.basis);
                return (
                  <div key={f.id} className="phl-fig" data-fig={f.id}>
                    <dt>{f.label}</dt>
                    {v === null ? <dd className="phl-none">{f.needs}</dd> : <dd className="num">{onViewData ? <button type="button" className="phl-open" aria-label={`${f.label}: ${v}${tag ? ', ' + tag.toLowerCase() : ''}. Opens the cases behind it.`} onClick={() => open({ state: FIGURE_STATE[f.id], label: f.label })}>{v}</button> : v}{tag && <span className="phl-tag">{tag}</span>}</dd>}
                    {v !== null && <p className="phl-basis">{figureBasis(f, h.period.days)}</p>}
                    {v !== null && (f.id === 'carbon' ? note : f.note) ? <p className="phl-note">{f.id === 'carbon' ? note : f.note}</p> : null}
                  </div>
                );
              })}
            </dl>
            <div className="phl-cols">
              <div>
                <h3 className="phl-h">Cases and net by {word}</h3>
                {bars.length === 0 ? (
                  <p className="phl-empty">No case has a {word} yet. One appears once a case passes its checks.</p>
                ) : (
                  <TableScroll label={'Cases by ' + word}>
                    <table className="t phl-t">
                      <thead>
                        <tr>
                          <th scope="col">{cap(word)}</th><th scope="col">Closed and open</th>
                          <th scope="col" className="r">Cases</th><th scope="col" className="r">Closed</th><th scope="col" className="r">Net, modelled</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bars.map((b) => (
                          <tr key={b.id}>
                            <th scope="row">{onViewData ? <button type="button" className="phl-open phl-name" aria-label={`${b.name}: ${b.cases} cases. Opens the cases.`} onClick={() => open({ route: { id: b.id, name: b.name }, label: `by ${word}, ${b.name}` })}>{b.name}</button> : b.name}</th>
                            <td>
                              <span className="phl-bar" role="img" aria-label={`${b.closed} closed, ${b.total - b.closed} open`}>
                                <i className="c" style={{ width: b.closedShare * 100 + '%' }} /><i className="o" style={{ width: b.openShare * 100 + '%' }} />
                              </span>
                            </td>
                            <td className="num r">{onViewData && b.total ? <button type="button" className="phl-open" aria-label={`${b.name}: ${b.cases} cases. Opens the cases.`} onClick={() => open({ route: { id: b.id, name: b.name }, label: `by ${word}, ${b.name}` })}>{b.cases}</button> : b.cases}</td><td className="num r">{b.sold}</td><td className="num r">{b.net}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </TableScroll>
                )}
              </div>
              <div>
                <h3 className="phl-h">Grade to {word}</h3>
                {grades.length === 0 ? (
                  <p className="phl-empty">No graded case has a {word} yet.</p>
                ) : (
                  <TableScroll label={'Grades by ' + word}>
                    <table className="t phl-t phl-grid">
                      <thead>
                        <tr>
                          <th scope="col">Grade</th>
                          {h.grades.routes.map((r) => <th key={r.id} scope="col" className="r">{r.name}</th>)}
                          <th scope="col" className="r">All</th>
                        </tr>
                      </thead>
                      <tbody>
                        {grades.map((g) => (
                          <tr key={g.grade}>
                            <th scope="row">{g.grade}</th>
                            {g.cells.map((c) => (
                              <td key={c.route} className="num r phl-cell" data-hi={c.strength > 0.5} style={{ ['--s' as string]: c.strength }}>
                                {c.n && onViewData ? (
                                  <button type="button" className="phl-open" aria-label={`Grade ${g.grade} on ${routeName(c.route)}: ${c.n} ${c.n === 1 ? 'case' : 'cases'}. Opens the cases.`} onClick={() => open({ grade: g.grade, route: { id: c.route, name: routeName(c.route) }, label: `grade ${g.grade} on ${routeName(c.route)}` })}>{c.n}</button>
                                ) : c.n || <span className="phl-zero">0</span>}
                              </td>
                            ))}
                            <td className="num r">{g.total}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </TableScroll>
                )}
                <p className="phl-note">Cases per grade and {word}, on the {word} each case is approved on, else the one recommended.</p>
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

/** Whatever fails to load here leaves the rest of Analytics as it was. */
class Quiet extends Component<{ children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  override render() {
    return this.state.failed ? null : this.props.children;
  }
}

function Packs({ days, onDays, pending, onViewData }: { days: number; onDays: (d: number) => void; pending: boolean; onViewData?: Open }) {
  const packs = usePackHeadlines(days);
  return <>{packs.map((h) => <Headline key={h.pack} h={h} onDays={onDays} pending={pending} onViewData={onViewData} />)}</>;
}

/** At the top of Analytics: the headline of each pack (tool fleet, device recommerce) the signed-in person has cases of; nothing otherwise. */
export function PackHeadlines({ onViewData }: { onViewData?: Open }) {
  const [days, setDays] = useState(90);
  const [pending, start] = useTransition();
  return (
    <Quiet>
      <Suspense fallback={null}>
        <Packs days={days} onDays={(d) => start(() => setDays(d))} pending={pending} onViewData={onViewData} />
      </Suspense>
    </Quiet>
  );
}
