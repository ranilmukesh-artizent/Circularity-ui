/**
 * The live run board (the demo's lrBoardHTML / lrView / lrTick): ten boxes that play stage by stage, line by line, from the
 * case's own records. Pause, 1×/2×, Skip to now and Replay; a box opens in place. Reduced motion shows the end state.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';
import { fmtDateYear } from '../../api/format';
import {
  escalationDraft, failDrill, LR_PACE, modelTag, nextStep, orCaseById, orDur, runModel, runNext, runSignature, runStates, runTimeline,
  sendEscalation, stageModels, type NextStep, type RunLine, type RunModel, type RunStage, type Segment,
} from '../../api/orchestration';
import { toast } from '../../ui/toast';

interface Play {
  sig: string; m: RunModel; segs: Segment[]; total: number;
  t: number; speed: 1 | 2; playing: boolean; open: number | null | undefined; ann: number; annText: string;
}
type LineState = 'hid' | 'spin' | RunLine['st'];
interface Box { n: number; phase: 'queued' | 'played' | 'playing' | 'ahead'; state: string; open: boolean; lines: LineState[]; cnt: string }

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const lrN = (k: number, one: string, many?: string) => k + ' ' + (k === 1 ? one : many || one + 's');
const lrClock = (ms: number) => {
  const s = Math.floor(ms / 1000);
  return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
};
const agentsOf = (s: RunStage) => [...new Set(s.lines.filter((l) => l.agent).map((l) => l.who))];

export function useReplay() {
  const [n, setN] = useState(0);
  return { n, fire: useCallback(() => setN((x) => x + 1), []) };
}

function build(id: string) {
  const m = runModel(id), tl = runTimeline(id, m);
  return { sig: runSignature(id), m, segs: tl.segs, total: tl.total };
}
function start(id: string, speed: 1 | 2 = 1): Play {
  const b = build(id);
  return reduced()
    ? { ...b, t: b.total, speed, playing: false, open: undefined, ann: b.m.cur, annText: '' }
    : { ...b, t: 0, speed, playing: true, open: undefined, ann: 0, annText: '' };
}

/** What each box and line shows at time t (the demo's lrView). */
function view(L: Play) {
  const t = L.t, ended = t >= L.total, cur = L.m.cur;
  const playN = ended ? cur : (L.segs.find((s) => t >= s.start && t < (s.n < cur ? s.end + LR_PACE.settle : Infinity)) ?? { n: cur }).n;
  const open = L.open === undefined ? playN : L.open;
  let tools = 0, models = 0;
  const aud: string[] = [], agents = new Set<string>();
  const boxes: Box[] = L.m.st.map((s, i) => {
    const sg = L.segs[i], pin = L.open === s.n;
    const phase: Box['phase'] = !sg ? 'queued' : ended || t >= sg.end ? 'played' : t >= sg.start ? 'playing' : 'ahead';
    const lines = s.lines.map((l, j) => {
      let st: LineState = l.st;
      if (!pin && sg && phase !== 'played') {
        const x = sg.lines[j];
        st = phase === 'ahead' || t < x.start ? 'hid' : t < x.land ? 'spin' : l.st;
      }
      if (sg && t >= sg.lines[j].land && l.st === 'done') {
        if (l.tool) tools++;
        aud.push(...l.audit);
        if (l.agent) agents.add(l.agent);
        if (l.model) models++;
      }
      return st;
    });
    const fin = s.lines.filter((l) => l.st === 'done');
    return {
      n: s.n, phase, open: open === s.n, lines,
      state: phase === 'played' || phase === 'queued' || pin ? s.state : phase === 'playing' ? 'play' : 'ahead',
      cnt: lrN(fin.filter((l) => l.tool).length, 'tool') + ' · ' + lrN(fin.reduce((a, l) => a + l.audit.length, 0), 'audit entry', 'audit entries'),
    };
  });
  return { boxes, tools, aud, agents: agents.size, models, ended, playN, open };
}

export function LiveBoard({ caseId, replaySignal }: { caseId: string; replaySignal: number }) {
  const [L, setL] = useState<Play>(() => start(caseId));
  const sig = runSignature(caseId);

  // a case that moved on (an action, a sync) plays again from the stage it left (the demo's lrSync)
  useEffect(() => {
    if (sig === L.sig) return;
    setL((p) => {
      const was = p.m.cur, ended = p.t >= p.total, b = build(caseId);
      if (reduced()) return { ...p, ...b, t: b.total, playing: false, ann: b.m.cur, open: undefined };
      const sg = b.segs[Math.min(was, b.segs.length) - 1];
      return { ...p, ...b, t: ended && sg ? Math.min(sg.start, b.total) : Math.min(p.t, b.total), playing: true, open: undefined, ann: Math.min(p.ann, was - 1) };
    });
  }, [sig, L.sig, caseId]);

  // the clock
  useEffect(() => {
    if (!L.playing) return;
    const iv = window.setInterval(() => {
      setL((p) => {
        if (!p.playing) return p;
        const t = Math.min(p.total, p.t + LR_PACE.tick * p.speed);
        return t >= p.total ? { ...p, t, playing: false, open: undefined } : { ...p, t };
      });
    }, LR_PACE.tick);
    return () => window.clearInterval(iv);
  }, [L.playing]);

  const V = useMemo(() => view(L), [L]);

  // announce each stage as it completes, not each line
  useEffect(() => {
    const done = V.boxes.filter((b) => b.phase === 'played').map((b) => b.n), hi = done.length ? Math.max(...done) : 0;
    if (hi > L.ann) {
      const s = L.m.st[hi - 1], RS = runStates();
      setL((p) => ({ ...p, ann: hi, annText: hi === p.m.cur ? `Stage ${hi}, ${s.t}: ${(RS[s.state]?.[0] ?? '').toLowerCase()}` : `Stage ${hi}, ${s.t}, completed` }));
    }
  }, [V, L.ann, L.m]);

  const replay = useCallback(() => {
    setL((p) => {
      if (reduced()) { toast('Replay: stored results only, nothing was written.'); return { ...p, t: p.total, playing: false, open: undefined }; }
      return { ...p, t: 0, playing: true, open: undefined, ann: 0, annText: '' };
    });
  }, []);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    replay();
  }, [replaySignal, replay]);

  // Esc closes the open box
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || document.querySelector('.modal.on, .drawer.on')) return;
      setL((p) => (view(p).open == null ? p : { ...p, open: null, playing: false }));
    };
    document.addEventListener('keydown', f);
    return () => document.removeEventListener('keydown', f);
  }, []);

  const c = orCaseById(caseId)!, run = L.m.run, RS = runStates();
  const chip = (b: Box): [string, string] => (b.state === 'play' ? ['Running', 'warn'] : b.state === 'ahead' ? ['Pending', 'line'] : RS[b.state] ?? ['—', 'line']);
  const toggle = (n: number) => setL((p) => ({ ...p, open: view(p).open === n ? null : n, playing: false }));
  const pos = (n: number) =>
    ({ '--o5': 2 * n, '--b5': 2 * Math.ceil(n / 5) * 5 + 1, '--o2': 2 * n, '--b2': 2 * Math.ceil(n / 2) * 2 + 1, '--o1': 2 * n, '--b1': 2 * n + 1 }) as CSSProperties;
  let prev: string | Date | null = null;

  return (
    <section className={'sect lrbw' + (L.playing ? ' playing' : '')} id="lrBoard" data-case={caseId} aria-label={'Live run for ' + caseId}>
      <div className="lrhd">
        <div className="lrt">
          <span className="livedot"><i />Live</span>
          <h2>Run {run.id}</h2>
          <span className="note">{c.id} · {c.product} · {run.stage > 10 ? 'complete' : 'stage ' + run.stage + ' of 10'} · orchestrated by <b className="lrorc">✦ Circularity Agent</b></span>
        </div>
        <div className="row lrctl">
          <button className="btn sm" id="lrPlay" disabled={V.ended} onClick={() => setL((p) => (p.t >= p.total ? p : { ...p, playing: !p.playing, open: !p.playing ? undefined : p.open }))}>
            {L.playing ? 'Pause' : 'Resume'}
          </button>
          <div className="seg" role="group" aria-label="Playback speed">
            <button aria-pressed={L.speed === 1} onClick={() => setL((p) => ({ ...p, speed: 1 }))}>1×</button>
            <button aria-pressed={L.speed === 2} onClick={() => setL((p) => ({ ...p, speed: 2 }))}>2×</button>
          </div>
          <button className="btn sm" disabled={V.ended} onClick={() => setL((p) => ({ ...p, t: p.total, playing: false, open: undefined }))}>Skip to now</button>
          <button className="btn sm" onClick={replay}>Replay</button>
        </div>
      </div>
      <div className="lrbar" aria-hidden="true"><i id="lrProg" style={{ width: (L.total ? (100 * L.t) / L.total : 100).toFixed(1) + '%' }} /></div>
      <div className="lrmeta">
        <span className="num" id="lrTime">{lrClock(L.t)}</span>
        <span><b className="num">{V.agents}</b> agents</span>
        <span><b className="num">{V.tools}</b> tool calls</span>
        <span><b className="num">{V.models}</b> model calls</span>
        <span><b className="num">{V.aud.length}</b> audit entries</span>
        <span className="mono note">{V.aud[V.aud.length - 1] || ''}</span>
        <span className="note lrann" role="status" aria-live="polite">{L.annText}</span>
      </div>
      <div className="lrg">
        {L.m.st.map((s, i) => {
          const b = V.boxes[i], ch = chip(b), ag = agentsOf(s), p0 = prev;
          if (s.at) prev = s.at;
          return (
            <div key={s.n} className={`lrb ${b.state}${b.open ? ' open' : ''}${s.n === L.m.cur && b.state !== 'ahead' ? ' cur' : ''}`} data-n={s.n} style={pos(s.n)}>
              <button className="lrh" aria-expanded={b.open} aria-controls={'lrBody-' + s.n} aria-label={`Stage ${s.n}: ${s.t}, ${ch[0]}`} onClick={() => toggle(s.n)}>
                <span className="tin">{s.n}</span>
                <b>{s.t}</b>
                <span className="lrlead note">{ag.length ? '✦ ' + ag[0] + (ag.length > 1 ? ' +' + (ag.length - 1) : '') : '—'}</span>
                <span className={'chip ' + ch[1]}>{ch[0]}</span>
                <span className="lrc note">{b.phase === 'played' ? b.cnt : ''}</span>
              </button>
              <div className="lrbody" id={'lrBody-' + s.n}>
                <StageBody caseId={caseId} s={s} b={b} chip={ch} prev={p0} cur={L.m.cur} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function StageBody({ caseId, s, b, chip, prev, cur }: { caseId: string; s: RunStage; b: Box; chip: [string, string]; prev: string | Date | null; cur: number }) {
  const nav = useNavigate();
  const nx = s.n === cur && failDrill() === '' ? nextStep(caseId) : null;
  const act = nx && ['act', 'approve', 'ack'].includes(nx.kind);
  const ag = agentsOf(s), models = s.state === 'queued' ? [] : stageModels(caseId, s);
  const doNext = async () => {
    if (nx?.kind === 'approve') { nav('/product/' + caseId + '/stage/7'); return; }
    const r = await runNext(caseId);
    if (!r.ok) { toast(r.error.message, 4200); return; }
    if (r.step && r.step.kind !== 'approve') toast('Stage ' + r.step.n + ': ' + r.step.label + ' · done.');
  };
  return (
    <>
      <div className="lrbh">
        <b>Stage {s.n} · {s.t}</b>
        <span className={'chip lrbc ' + chip[1]}>{chip[0]}</span>
        {s.at && <span className="note num">{fmtDateYear(s.at)}{prev ? ' · took ' + orDur(new Date(prev), new Date(s.at)) : ''}</span>}
        {ag.length ? <span className="lrags">{ag.map((a) => <span key={a} className="lra ag"><i aria-hidden="true">✦</i>{a}</span>)}</span> : s.by ? <span className="note">by {s.by}</span> : null}
      </div>
      <ol className="lrls">
        {s.lines.map((l, j) => (
          <li key={j} className={'lrl s-' + b.lines[j]}>
            <span className="lri" aria-hidden="true" />
            <span className={'lra ' + (l.agent ? 'ag' : 'pp')}>{l.agent && <i aria-hidden="true">✦</i>}{l.who}</span>
            <span className="lrw">
              <b>{l.verb}</b>{l.what ? ' · ' + l.what : ''}
              <span className="lrt">
                {l.tool ? <><span className="mono">{l.tool}</span> → {l.sys}</> : l.agent ? '' : 'person'}
                {l.model && <> · <span className="lrmd">{modelTag(caseId, l.model)}</span></>}
                {l.audit.length > 0 && <> · <span className="mono">{l.audit[0]}</span></>}
              </span>
            </span>
            <span className="lrm num">{l.ms ? l.ms + ' ms' : ''}</span>
          </li>
        ))}
      </ol>
      {models.length > 0 && (
        <div className="lrmods">
          <h5>Models used at this stage</h5>
          {models.map((m) => (
            <div key={m.key} className="lrmc">
              <b className="mono">{m.key} {m.version}</b>
              <span className={'chip ' + (m.kind === 'DL' ? 'y' : 'line')}>{m.kind === 'DL' ? 'Deep learning' : 'Machine learning'}</span>
              <span>{m.algo}</span><span className="note">{m.task}</span><span className="num">{m.validation}</span><span className="note">trained on {m.data}</span>
            </div>
          ))}
        </div>
      )}
      <p className="lrres"><b>Result</b> {s.result || '—'}</p>
      {act && nx ? (
        <div className="lrnx"><button className="btn pri sm" onClick={doNext}>{nx.label} →</button></div>
      ) : nx && (nx.kind === 'wait' || nx.kind === 'blocked') ? (
        <>
          <div className="lrnx">
            <span className={'chip ' + (nx.kind === 'blocked' ? 'bad' : 'y')}>{nx.kind === 'blocked' ? 'Blocked' : 'Waiting'}</span>
            <span>{nx.label}{nx.role ? ' Owner: ' + nx.role + '.' : ''}</span>
          </div>
          <EscalationCard caseId={caseId} nx={nx} />
        </>
      ) : null}
    </>
  );
}

/** The drafted escalation beside a waiting or blocked stage (the demo's escalation card). */
function EscalationCard({ caseId, nx }: { caseId: string; nx: NextStep }) {
  const nav = useNavigate();
  const d = escalationDraft(caseId, nx);
  const [msg, setMsg] = useState(d.msg);
  const send = async () => {
    const r = await sendEscalation(d, msg.trim());
    if (!r.ok) { toast(r.error.message, 4200); return; }
    toast('Escalation sent to ' + r.output.to + '.');
  };
  return (
    <article className="afc afc-escalation" data-card="escalation">
      <header className="afch">
        <div><h4>Escalation · {d.case_id}</h4><div className="note">Blocked: {d.blocker}</div></div>
        <span className="afbs"><span className="afb afb-draft">Draft</span></span>
      </header>
      <p className="note">Owner: <b>{d.owner}</b> · to {d.toLabel}</p>
      <div className="fld">
        <label htmlFor={'afesc-' + d.case_id}>Message (it creates an Actions on me item)</label>
        <textarea id={'afesc-' + d.case_id} maxLength={300} value={msg} onChange={(e) => setMsg(e.target.value)} />
      </div>
      <footer className="afcf">
        <button className="btn sm pri" onClick={send}>Send</button>
        <button className="btn sm" onClick={() => nav('/product/' + d.case_id)}>Open case</button>
      </footer>
    </article>
  );
}
