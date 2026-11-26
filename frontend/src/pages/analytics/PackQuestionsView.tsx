import { useState } from 'react';
import { packQuestion, type PackAnswer, type PackViewData } from '../../api/analytics';
import { Panel } from '../../components/kit/Panel';
import { answerTitle, plot } from './packQuestions';
import { SavedViewsList, SaveViewForm } from './SavedViews';

const W = 520, H = 150, PAD = 24;

function LineChart({ a }: { a: PackAnswer }) {
  const ys = a.chart.series.flatMap((s) => s.points.flatMap((p) => (p.y === null ? [] : [p.y])));
  const lo = Math.floor(Math.min(...ys, 100) - 2), hi = Math.ceil(Math.max(...ys, 0) + 1);
  const at = (x: number, y: number) => `${PAD + x * (W - 2 * PAD)},${H - PAD - y * (H - 2 * PAD)}`;
  return (
    <svg className="ch" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${answerTitle(a)}: weekly price realised as a share of the feed`}>
      {a.chart.series.map((s, i) => {
        const pts = plot(s.points, lo, hi);
        return (
          <g key={s.name}>
            <polyline points={pts.map((q) => at(q.x, q.y)).join(' ')} fill="none" stroke="var(--ink)" strokeOpacity={i === 0 ? 1 : 0.4} strokeWidth={i === 0 ? 2 : 1} />
            {pts.filter((q) => q.p.launch).map((q) => (
              <line key={q.p.x} x1={PAD + q.x * (W - 2 * PAD)} x2={PAD + q.x * (W - 2 * PAD)} y1={PAD / 2} y2={H - PAD} stroke="currentColor" strokeDasharray="3 3">
                <title>Successor launched, week of {q.p.x}</title>
              </line>
            ))}
          </g>
        );
      })}
      <text x={PAD} y={H - 6} fontSize="10" fill="currentColor">{a.chart.series[0]?.points[0]?.x}</text>
      <text x={W - PAD} y={H - 6} fontSize="10" textAnchor="end" fill="currentColor">{a.chart.series[0]?.points.at(-1)?.x}</text>
    </svg>
  );
}

function BarChart({ a }: { a: PackAnswer }) {
  const pts = a.chart.series[0]?.points ?? [];
  const mx = Math.max(1, ...pts.map((p) => p.y ?? 0));
  return (
    <div role="img" aria-label={answerTitle(a)}>
      {pts.map((p) => (
        <div key={p.x} style={{ margin: '6px 0' }}>
          <div className="row" style={{ justifyContent: 'space-between' }}><span>{p.x}</span><b className="num">{p.y}</b></div>
          <div className="bar"><i style={{ width: ((p.y ?? 0) / mx) * 100 + '%' }} /></div>
        </div>
      ))}
    </div>
  );
}

/** One answered question: the chart, the computed sentence and the example records. Figures come from the server; none is worded here. */
export function QuestionAnswer({ a }: { a: PackAnswer }) {
  const cols = a.examples[0] ? Object.keys(a.examples[0]) : [];
  return (
    <div data-question={a.question_id}>
      {a.chart.series.some((s) => s.points.length > 0) && (
        <div style={{ maxWidth: 640 }}>{a.chart.kind === 'line' ? <LineChart a={a} /> : <BarChart a={a} />}</div>
      )}
      <p data-k="sentence"><b>{a.sentence}</b></p>
      {a.examples.length > 0 && (
        <table className="t static tight" aria-label="Example records">
          <thead><tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, ' ')}</th>)}</tr></thead>
          <tbody>{a.examples.map((e, i) => <tr key={i}>{cols.map((c) => <td key={c}>{String(e[c] ?? '')}</td>)}</tr>)}</tbody>
        </table>
      )}
    </div>
  );
}

function Chosen({ id }: { id: string }) {
  return <QuestionAnswer a={packQuestion(id)} />;
}

/** Analytics › Packs, "Questions": the selected pack's worked questions; choosing one asks `device.question` for it.
 *  Nothing is drawn for a pack with none. Remount per pack (key) so a chosen question never outlives its pack. */
export function PackQuestions({ pack }: { pack: Pick<PackViewData, 'key' | 'name' | 'worked_questions'> }) {
  const [id, setId] = useState('');
  if (pack.worked_questions.length === 0) return null;
  return (
    <section className="sect" aria-label="Questions" data-testid="pack-questions">
      <Panel title="Questions" sub={`${pack.name}: answered from the records you may see`}>
        <div className="row" style={{ gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          {pack.worked_questions.map((q) => (
            <button key={q.id} type="button" className={'btn' + (q.id === id ? ' pri' : '')} aria-pressed={q.id === id} onClick={() => setId(q.id)}>{q.question}</button>
          ))}
        </div>
        {id ? <Chosen id={id} /> : <p className="note" style={{ margin: 0 }}>Choose a question.</p>}
        {id && <SaveViewForm key={id} pack={pack.key} questionId={id} question={pack.worked_questions.find((q) => q.id === id)?.question ?? id} />}
        <SavedViewsList pack={pack.key} />
      </Panel>
    </section>
  );
}
