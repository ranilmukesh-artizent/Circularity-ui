/**
 * Build an analysis: choose a measure and up to two breakdowns, and the answer is drawn at once, in words first. Every bar or
 * cell opens the rows it adds up (View data). Examples fill the form in one click. A saved analysis is kept for this person in
 * this browser (the server's saved views hold worked pack questions only; see the report).
 */
import { useId, useMemo, useState } from 'react';
import type { ClosedRow } from '../../api/analytics';
import { toast } from '../../components/toast';
import {
  analysisTitle, DIMS, EXAMPLES, formatValue, groupSpec, loadSaved, MEASURES, runAnalysis, storeSaved,
  type Analysis, type DimId, type Group, type MeasureId, type SavedAnalysis,
} from './analysisModel';
import { fmtInt, type Labels, type ViewSpec } from './data/dataView';
import { tint } from './charts/chartData';
import { useRoving } from './charts/roving';
import './charts/charts.css';

const NONE = '';

function Pivot({ res, unit, onOpen }: { res: ReturnType<typeof runAnalysis>; unit: Parameters<typeof formatValue>[1]; onOpen: (g: Group) => void }) {
  const { ref: keys, mark } = useRoving();
  const [d1, d2] = res.analysis.by;
  const max = Math.max(1e-9, ...res.groups.map((g) => Math.abs(g.value ?? 0)));
  const diverging = res.analysis.measure === 'uplift';
  const at = (r: number, c: number) => res.groups.find((g) => g.label === `${res.rowLabels[r]}, ${res.colLabels[c]}`);
  let m = 0;
  return (
    <div className="ch-scroll">
      <div className="hg" role="group" aria-label={res.title} ref={keys} style={{ gridTemplateColumns: `minmax(120px, 1.1fr) repeat(${res.colLabels.length}, minmax(84px, 1fr))` }}>
        <span className="hg-h" style={{ textAlign: 'left' }}>{DIMS.find((d) => d.id === d1)?.label} / {DIMS.find((d) => d.id === d2)?.label.toLowerCase()}</span>
        {res.colLabels.map((c) => <span key={c} className="hg-h">{c}</span>)}
        {res.rowLabels.map((rl, r) => [
          <span key={rl} className="hg-r">{rl}</span>,
          ...res.colLabels.map((cl, c) => {
            const g = at(r, c);
            if (!g) return <button key={cl} type="button" className="hg-cell" disabled data-row={r} data-col={c} aria-label={`${rl}, ${cl}: no cases`} />;
            const bg = g.value == null || g.value === 0 ? undefined : `color-mix(in srgb, var(${diverging ? (g.value > 0 ? '--ok' : '--bad') : '--yellow'}) ${Math.round(8 + tint(g.value, max) * 44)}%, var(--panel))`;
            return (
              <button
                key={cl} type="button" className="hg-cell" style={{ background: bg }} data-row={r} data-col={c} {...mark(m++)} onClick={() => onOpen(g)}
                aria-label={`${rl}, ${cl}: ${formatValue(g.value, unit)} across ${fmtInt(g.n)} cases. Opens the rows.`}
              >
                <b>{formatValue(g.value, unit)}</b><span>{fmtInt(g.n)}</span>
              </button>
            );
          }),
        ])}
      </div>
    </div>
  );
}

export function AnalysisBuilder({ rows, labels, onViewData }: { rows: ClosedRow[]; labels: Labels; onViewData: (s: ViewSpec) => void }) {
  const uid = useId();
  const [a, setA] = useState<Analysis>({ measure: 'uplift', by: ['route'] });
  const [saved, setSaved] = useState<SavedAnalysis[]>(loadSaved);
  const res = useMemo(() => runAnalysis(rows, a, labels), [rows, a, labels]);
  const unit = MEASURES.find((x) => x.id === a.measure)!.unit;
  const set = (p: Partial<Analysis>) => setA((x) => ({ ...x, ...p }));
  const setDim = (i: 0 | 1, v: string) => {
    const by = [...a.by];
    if (v === NONE) by.splice(i); else by[i] = v as DimId;
    set({ by: by.filter((d, k) => by.indexOf(d) === k) });
  };
  const { ref: keys, mark } = useRoving();
  const max = Math.max(1e-9, ...res.groups.map((g) => Math.abs(g.value ?? 0)));
  const title = analysisTitle(a);
  const exists = saved.some((s) => analysisTitle(s.a) === title);
  const save = () => {
    const next = [{ name: title, a }, ...saved.filter((s) => analysisTitle(s.a) !== title)];
    if (storeSaved(next)) { setSaved(next); toast('Saved the view ' + title); } else toast('Your browser would not keep the view. Allow site data and try again.');
  };
  const remove = (name: string) => { const next = saved.filter((s) => s.name !== name); storeSaved(next); setSaved(next); };

  return (
    <section className="panel sect" id="an-build" aria-label="Build an analysis">
      <div className="ph"><h3>Build an analysis</h3><span className="note">Pick a measure and how to break it down; the result updates as you choose.</span></div>
      <div className="pb">
        <div className="ab-form">
          <div className="fld">
            <label htmlFor={uid + 'm'}>Measure</label>
            <select id={uid + 'm'} className="sel" value={a.measure} onChange={(e) => set({ measure: e.target.value as MeasureId })}>
              {MEASURES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </div>
          <div className="fld">
            <label htmlFor={uid + 'a'}>Break down by</label>
            <select id={uid + 'a'} className="sel" value={a.by[0] ?? NONE} onChange={(e) => setDim(0, e.target.value)}>
              <option value={NONE}>Nothing (one total)</option>
              {DIMS.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
            </select>
          </div>
          <div className="fld">
            <label htmlFor={uid + 'b'}>and then by</label>
            <select id={uid + 'b'} className="sel" value={a.by[1] ?? NONE} disabled={!a.by[0]} onChange={(e) => setDim(1, e.target.value)}>
              <option value={NONE}>Nothing</option>
              {DIMS.filter((d) => d.id !== a.by[0]).map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
            </select>
          </div>
        </div>
        <ul className="ab-ex" aria-label="Examples">
          <li className="note">Try</li>
          {EXAMPLES.map((e) => <li key={e.label}><button type="button" className="pill" onClick={() => setA(e.a)}>{e.label}</button></li>)}
        </ul>

        <div className="ab-result" aria-live="polite">
          <h4>{title}</h4>
          <p className="ch-sum" style={{ marginBottom: 0 }}>{res.summary}</p>
          <p className="note" style={{ margin: '2px 0 0' }}>{MEASURES.find((m) => m.id === a.measure)!.means}.</p>
          {a.by.length === 1 && res.groups.length > 0 && (
            <ul className="ab-bars" role="group" aria-label={title} ref={keys}>
              {res.groups.map((g, i) => (
                <li key={g.label}>
                  <button type="button" className="ab-bar" {...mark(i)} onClick={() => onViewData(groupSpec(a, g))} aria-label={`${g.label}: ${formatValue(g.value, unit)} across ${fmtInt(g.n)} cases. Opens the rows.`}>
                    <span className="nm">{g.label}</span>
                    <span><span className={'tk' + ((g.value ?? 0) < 0 ? ' neg-b' : '')} style={{ display: 'block', width: `${Math.max(1, (Math.abs(g.value ?? 0) / max) * 100)}%` }} /></span>
                    <span className="v">{formatValue(g.value, unit)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {a.by.length === 2 && res.groups.length > 0 && <Pivot res={res} unit={unit} onOpen={(g) => onViewData(groupSpec(a, g))} />}
          <div className="ab-save">
            <button type="button" className="btn sm" onClick={() => onViewData(groupSpec(a, null))}>View data</button>
            <button type="button" className="btn sm" onClick={save} disabled={exists}>{exists ? 'Saved in this browser' : 'Save in this browser'}</button>
            <span className="note">Kept on this device only; nobody else sees it and it is not synced.</span>
          </div>
        </div>

        {saved.length > 0 && (
          <div>
            <h4 style={{ margin: '16px 0 0', fontSize: 14 }}>Saved in this browser</h4>
            <ul className="ab-saved">
              {saved.map((s) => (
                <li key={s.name}>
                  <button type="button" className="pill" onClick={() => setA(s.a)}>{s.name}</button>
                  <button type="button" className="btn ghost sm" aria-label={`Remove the saved view ${s.name}`} onClick={() => remove(s.name)}>Remove</button>
                </li>
              ))}
            </ul>
            <p className="note" style={{ margin: '6px 0 0' }}>Kept in this browser for you. Views you can share with a team or set alerts on are the worked questions in Packs.</p>
          </div>
        )}
      </div>
    </section>
  );
}
