import { useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import {
  caseById, caseVisible, fullAnalysisHtml, landing, stageHref, stageState, stageTitle, syncEngineRoute, type CaseRec,
} from '../../api/case';
import { useBackend } from '../../api/hooks';
import { Modal } from '../../ui/Overlay';
import { ApprovalModal, DeclineModal, ExplainView } from './Dialogs';
import { Overview } from './Overview';
import { StageBar, StageFoot, StagePage, stageDo, type CaseView } from './StagePage';
import { CaseUiContext, Legacy, type CaseUi } from './ui';
import './case.css';

type Resolved = { view: CaseView; redirect: boolean };

/** Which page a product URL means: a stage, the Overview or Full analysis; old links map onto them (stResolve). */
function resolve(c: CaseRec, segs: string[], q: URLSearchParams, hash: string): Resolved {
  const land = (): Resolved => {
    const l = landing(c);
    return { view: l === 'overview' ? { kind: 'overview' } : { kind: 'stage', n: l, tab: null }, redirect: true };
  };
  const [b, sub] = [segs[2] ?? null, segs[3] ?? null];
  if (b === 'stage') {
    const n = parseInt(sub ?? '');
    return n >= 1 && n <= 10 ? { view: { kind: 'stage', n, tab: q.get('tab') }, redirect: false } : land();
  }
  if (b === 'overview') return { view: { kind: 'overview' }, redirect: false };
  if (b === 'full') return { view: { kind: 'full' }, redirect: false };
  const js = parseInt(q.get('jstep') ?? ''), st = q.get('step'), at = q.get('at');
  const T: Record<string, string> = { '2': 'compare', '3': 'why', '4': 'whatif' };
  const stage = (n: number, tab: string | null = null): Resolved => ({ view: { kind: 'stage', n, tab }, redirect: true });
  if (js >= 1 && js <= 10) return stage(js, js === 6 && st && T[st] && st !== '2' ? T[st] : null);
  if (at === 'reconcile') return stage(10);
  if (at === 'handoff') return stage(8);
  if (st === '5') return stage(c.exec ? 8 : 7);
  if (st && T[st]) return stage(6, T[st]);
  if (st === '1') return { view: { kind: 'overview' }, redirect: true };
  if (/[?&]explain\b/.test(hash)) return stage(6, 'why');
  return land();
}

const viewHref = (id: string, v: CaseView) => '/' + stageHref(id, v.kind === 'stage' ? v.n : v.kind, v.kind === 'stage' ? v.tab : null);

/**
 * A live case (#/product/RT-1048, #/product/RT-1048/<stage or view>): the Decision Workbench stage pages,
 * the case Overview and Full analysis. Rendered by the `product` page dispatcher (src/pages/product/).
 * CONTRACT: keep this export name and props; the case area owns everything behind it.
 */
export function CasePage({ caseId, query }: { caseId: string; view: string | null; query: URLSearchParams }) {
  useBackend();
  const loc = useLocation();
  const nav = useNavigate();
  const [approval, setApproval] = useState<{ id: string; mode?: 'review' } | null>(null);
  const [decline, setDecline] = useState<string | null>(null);
  const [explain, setExplain] = useState<string | null>(null);
  const [legacy, setLegacy] = useState<{ title: string; body: string; foot: string; wide: boolean } | null>(null);
  const closeExplain = useMemo(() => () => setExplain(null), []);
  const ui = useMemo<CaseUi>(() => ({
    openApproval: (id, mode) => setApproval({ id, mode }),
    openDecline: (id) => setDecline(id),
    openExplain: (id) => setExplain(id),
    legacyModal: (m) => setLegacy(m),
  }), []);

  syncEngineRoute(loc.pathname + loc.search);
  const c = caseById(caseId);
  const ok = !!c && caseVisible(caseId);
  const r = ok ? resolve(c!, loc.pathname.split('/').filter(Boolean), query, loc.pathname + loc.search) : null;
  const v = r?.view;
  const key = v ? v.kind + (v.kind === 'stage' ? v.n : '') : '';

  useEffect(() => {
    if (!v || r?.redirect) return;
    document.title = (v.kind === 'stage' ? 'Stage ' + v.n + ' · ' + stageTitle(v.n) : v.kind === 'full' ? 'Full analysis' : 'Overview') + ' · ' + caseId;
    window.scrollTo(0, 0);
    const h = document.getElementById('stH1');
    try { h?.focus({ preventScroll: true }); } catch { h?.focus(); }
  }, [caseId, key]); // eslint-disable-line react-hooks/exhaustive-deps

  // Alt+← and Alt+→ move between stages
  useEffect(() => {
    if (!v || v.kind !== 'stage') return;
    const f = (e: KeyboardEvent) => {
      if (!e.altKey || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return;
      const n = v.n + (e.key === 'ArrowRight' ? 1 : -1);
      if (n < 1 || n > 10) return;
      e.preventDefault();
      nav('/' + stageHref(caseId, n));
    };
    document.addEventListener('keydown', f);
    return () => document.removeEventListener('keydown', f);
  }, [caseId, key]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!c || !ok || !v)
    return (
      <div className="empty" style={{ marginTop: 40 }}>
        <b>{c ? caseId + ' is not available for your account' : 'No case ' + caseId}</b>
        <a className="lnk" href="#/product/received">Back to Returned assets</a>
      </div>
    );
  if (r!.redirect) return <Navigate to={viewHref(c.id, v)} replace />;

  const pri = v.kind === 'stage' && stageDo(c, v.n, stageState(c, v.n), ui).pri;
  const ap = approval && caseById(approval.id);
  const dc = decline && caseById(decline);

  return (
    <CaseUiContext.Provider value={ui}>
      <div className="cspage">
        <div id="jmount"><StageBar c={c} view={v} /></div>
        {v.kind === 'stage' ? <StagePage key={c.id + v.n} c={c} n={v.n} tab={v.tab} />
          : v.kind === 'overview' ? <Overview c={c} />
          : <Legacy html={fullAnalysisHtml(c)} />}
        <div id="jgmount"><StageFoot c={c} view={v} pri={pri} /></div>
      </div>
      {ap && ap.recommendation && <ApprovalModal c={ap} mode={approval!.mode} onClose={() => setApproval(null)} />}
      {dc && <DeclineModal c={dc} onClose={() => setDecline(null)} />}
      {explain && caseById(explain)?.recommendation && <ExplainView caseId={explain} onClose={closeExplain} />}
      {legacy && (
        <Modal
          title={legacy.title.replace(/<[^>]*>/g, '')} wide={legacy.wide} onClose={() => setLegacy(null)}
          foot={legacy.foot ? <Legacy html={legacy.foot} style={{ display: 'contents' }} /> : undefined}
        >
          <Legacy html={legacy.body} />
        </Modal>
      )}
    </CaseUiContext.Provider>
  );
}
